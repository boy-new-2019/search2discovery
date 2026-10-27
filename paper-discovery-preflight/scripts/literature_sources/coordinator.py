"""Bounded multi-source discovery; failed sources never disable healthy sources."""
from __future__ import annotations
import datetime as dt,json,pathlib,re,sqlite3,xml.etree.ElementTree as ET
from .common import DEFAULTS,SOURCES,config,read,write,stable,sha,utc,locked
from .transport import HTTP,SourcePause
from .adapters import ADAPTERS,from_legacy,disciplinary_anchor
from .catalog import Catalog
def enabled(ws):return (pathlib.Path(ws)/'source_routing.json').is_file()
def configure(ws):
    import copy
    ws=pathlib.Path(ws)
    if not (ws/'goal.md').is_file() or not (ws/'discovery_config.json').is_file():raise ValueError('Use the existing research workspace; do not initialize from this command')
    path=ws/'source_routing.json'
    if path.exists():config(ws);return {'status':'ALREADY_CONFIGURED','path':str(path)}
    write(path,copy.deepcopy(DEFAULTS));return {'status':'CONFIGURED_ADDITIVELY','path':str(path),'project_reinitialized':False}
class Coordinator:
    def __init__(self,ws,*,online=False,http_factory=HTTP,adapter_classes=None,request_limit=12):
        self.ws=pathlib.Path(ws);self.cfg=config(self.ws);self.online=online
        import paper_discovery as d
        self.discovery=d;self.dc=d.config(self.ws)
        self.root=self.ws/'output/discovery_preflight/multisource';self.root.mkdir(parents=True,exist_ok=True)
        self.path=self.root/'state.json';self.catalog=Catalog(self.ws)
        contract={'goal_sha256':sha((self.ws/'goal.md').read_bytes()),'discovery_contract_sha256':d.sha(self.dc)}
        self.state=read(self.path) if self.path.exists() else {'schema_version':1,'contract':contract,'tasks':{},'runs':[]}
        if self.state['contract']!=contract:raise ValueError('Frozen research contract changed; never reset the source checkpoint')
        self.budget={'sent':0,'limit':request_limit}
        self.clients={s:http_factory(self.ws,s,self.cfg['providers'][s],online=online,budget=self.budget) for s in SOURCES}
        classes=adapter_classes or ADAPTERS
        self.adapters={s:classes[s](self.clients[s],self.cfg) for s in SOURCES}
        self.committed_page_evidence={}
        # Recover only actual immutable successful run events, never a page counter alone.
        for receipt_path in sorted((self.root/'runs').glob('run_*.json')):
            receipt=read(receipt_path)
            if receipt.get('status')!='MULTISOURCE_CHECKPOINT_SAVED':continue
            digest=sha(receipt_path.read_bytes())
            for event in receipt.get('source_events',[]):
                task=self.state['tasks'].get(event.get('task_id'))
                if event.get('status')=='PAGE_COMMITTED' and task and event.get('source')==task['source']:
                    self.committed_page_evidence[task['id']]={'kind':'COMMITTED_SOURCE_PAGE_RUN_RECEIPT',
                        'path':str(receipt_path),'sha256':digest}
    def save(self):
        self.catalog.save();write(self.path,self.state)
    def seed(self):
        if self.state.get('legacy_seeded'):return
        path=self.ws/'output/discovery_preflight/paper_library.json'
        if path.exists():
            data=read(path)
            for category,rows in data.get('selected',{}).items():
                for row in rows:self.catalog.add(from_legacy(row),legacy_category=category)
        self.state['legacy_seeded']={'at':utc(),'library_sha256':sha(path.read_bytes()) if path.exists() else None}
        self.save()
    def route(self,task):
        text=(task['query']+' '+self.dc.get('main_direction','')+' '+' '.join(self.dc.get('core_keywords',[]))).casefold()
        ai=task.get('category')!='inspiration' and any(t in text for t in ('driving','vision','learning','world model','neural','computer','robot','state'))
        return self.cfg['routes']['ai' if ai else 'cross_disciplinary']
    def add_task(self,semantic,source,priority):
        task={**semantic,'source':source}
        if source in ('arxiv','cvf','pmlr'):
            task['retrieval_profile']='DISCIPLINARY_ANCHOR_V1' if task.get('category')=='inspiration' else 'ADJACENT_PHRASE_BROAD_V1'
        tid=stable(task)[:24]
        # Compilation changes start an additive pass, retaining original cursor/results.
        for old in self.state['tasks'].values():
            if old.get('source')==source and all(old.get(k)==task.get(k) for k in semantic) and old.get('retrieval_profile')!=task.get('retrieval_profile'):
                old['superseded_by']=tid
        if tid not in self.state['tasks']:
            self.state['tasks'][tid]={**task,'id':tid,'priority':priority,'cursor':None,'status':'PENDING','pages_completed':0}
        return self.state['tasks'][tid]
    def plan(self,extra_queries=None):
        self.seed();asof=self.dc.get('as_of_date') or dt.date.today().isoformat()
        end=dt.date.fromisoformat(asof);start=self.discovery.minus_years(end,self.cfg['lookback_years']).isoformat()
        # Use only independently reviewed topic queries; no case-study keywords.
        queries=self.discovery.queries_for(self.dc)
        for i,(category,domain,q) in enumerate(queries):
            semantic={'query':q,'category':category,'domain':domain,'start':start,'end':asof,'band':'RECENT_3Y'}
            for source in self.route(semantic):
                if self.cfg['providers'][source]['enabled']:self.add_task(semantic,source,i)
        # Preserve the old acquisition checkpoint and add its missing plan entries.
        pending=self.ws/'sources/openalex_transport/request_plan.json'
        if pending.exists():
            oldstate=read(self.ws/'output/discovery_preflight/state.json')
            for t in read(pending).get('requests',[]):
                if t['task_key'] in oldstate.get('queries_done',{}):continue
                semantic={'query':t['q'],'category':t['category'],'domain':t.get('domain',''),'start':t['start'],'end':t['end'],'band':t.get('band','EXPLICIT_LEGACY_PENDING')}
                for source in self.route(semantic):
                    self.add_task(semantic,source,-20 if source in ('crossref','openalex') else 10000)
        if extra_queries:
            for i,semantic in enumerate(extra_queries):
                semantic={**semantic,'start':semantic.get('start',start),'end':semantic.get('end',asof),'band':semantic.get('band','QUESTION_DRIVEN')}
                for source in self.route(semantic):self.add_task(semantic,source,-100+i)
        for task in self.state['tasks'].values():
            if task['source']=='crossref' and task.get('doi') and task.get('last_error',{}).get('kind')=='NOT_FOUND':
                # A registry-specific identifier miss is task-local, not a source outage.
                task['status']='RESOURCE_NOT_FOUND'
            if task.get('band')=='FOUNDATIONAL_OLDER' and task['source'] not in ('crossref','openalex'):
                task['priority']=10000
        # A successful old OpenAlex query is never sent again just to populate the new scheduler.
        oldpath=self.ws/'output/discovery_preflight/state.json'
        old=read(oldpath) if oldpath.exists() else {}
        windows={band:(s,e) for band,s,e in self.discovery.windows(self.dc,end)}
        done={(x.get('category'),x.get('domain',''),x.get('query'),*(windows.get(x.get('band')) or ('',''))) for x in old.get('queries_done',{}).values()}
        for t in self.state['tasks'].values():
            if t['source']=='openalex' and (t['category'],t['domain'],t['query'],t['start'],t['end']) in done:
                t['status']='REUSED_LEGACY_SUCCESS'
        self.save()
    def classify(self):
        domains=self.discovery.diversity.load_catalog(self.dc)
        candidates=[];used=set();legacy_counts={c:0 for c in self.dc['quotas']}
        # Build provenance links once instead of rescanning every task per family.
        record_domains={}
        for task in self.state['tasks'].values():
            if (task.get('category')=='inspiration' and task.get('domain') and not task.get('doi')
                    and task.get('retrieval_profile')!='ADJACENT_PHRASE_BROAD_V1'):
                anchor=' '.join(disciplinary_anchor(task['query']))
                for rid in self.catalog.data['query_links'].get(task['id'],[]):
                    record=self.catalog.data['records'][rid]
                    if self.discovery.metadata_phrase_match(anchor,record['title']+' '+(record.get('abstract') or '')+' '+(record.get('venue') or '')):
                        record_domains.setdefault(rid,set()).add(task['domain'])
        for family,row in self.catalog.active().items():
            if row['legacy_categories']:
                used.add(family)
                for category in row['legacy_categories']:
                    legacy_counts[category]=legacy_counts.get(category,0)+1
                continue
            row.pop('screened_candidate_category',None);row.pop('assigned_inspiration_domain',None)
            allowed_crossref={'DOI_REGISTERED_JOURNAL-ARTICLE','DOI_REGISTERED_PROCEEDINGS-ARTICLE','DOI_REGISTERED_POSTED-CONTENT','DOI_REGISTERED_REVIEW'}
            eligible_records=[self.catalog.data['records'][rid] for rid in row['record_ids']
                if self.catalog.data['records'][rid]['source']!='crossref' or self.catalog.data['records'][rid].get('publication_status') in allowed_crossref]
            if not eligible_records:continue
            if all(r.get('date_window_status')=='YEAR_ONLY_BOUNDARY_UNCERTAIN' for r in eligible_records):continue
            # A DOI-only record must not hide a subsequently retrieved real abstract.
            rec=max(eligible_records,key=lambda r:len(r.get('abstract') or ''))
            task_domains=set()
            for rid in row['record_ids']:
                task_domains.update(record_domains.get(rid,set()))
            shim={**rec,'id':family,'category_sources':row.get('nominations',[]),
                  'inspiration_domains':sorted(task_domains),'cited_by_count':rec.get('citation_count') or 0}
            candidates.append((shim,self.discovery.paper_scores(shim,self.dc)))
        asof=dt.date.fromisoformat(self.dc.get('as_of_date') or dt.date.today().isoformat())
        year3=self.discovery.minus_years(asof,self.dc['recent_years'])
        year5=self.discovery.minus_years(asof,self.dc['extension_years'])
        def rank(rec):
            # Year-only interior records retain YEAR precision; conservative year
            # comparison is used solely for ordering, never as a fabricated date.
            date=dt.date.fromisoformat(rec['publication_date']) if rec.get('publication_date') else None
            year=rec.get('year') or 0
            band=0 if (date>=year3 if date else year>year3.year) else 2 if (date>=year5 if date else year>year5.year) else 4
            venue=self.discovery.priority_venue(rec,self.dc)
            return (band+(0 if venue else 1),-int(venue),-year,-min(rec['cited_by_count'],2000),rec['id'])
        candidates.sort(key=lambda pair:rank(pair[0]))
        # Match the original quota-aware core-then-related disjoint allocation.
        # Metadata nominations do not certify independent S1/S2 acceptance.
        for category,eligible_key in (('core','core_eligible'),('related','related_eligible')):
            remaining=max(0,self.dc['quotas'][category]-legacy_counts.get(category,0))
            for rec,score in candidates:
                if not remaining:break
                if rec['id'] in used or not score[eligible_key] or not set(rec['category_sources'])&{'core','related'}:continue
                self.catalog.data['families'][rec['id']]['screened_candidate_category']=category
                used.add(rec['id']);remaining-=1
        pool=[rec for rec,score in candidates if score['inspiration_eligible'] and rec.get('publication_date')]
        remaining=max(0,self.dc['quotas']['inspiration']-legacy_counts.get('inspiration',0))
        proposals=[] if not remaining else self.discovery.diversity.diversify(pool,used_ids=used,
            eligible={r['id']:True for r in pool},catalog=domains,preferred=self.dc['preferred_domains'],
            target=remaining,rank=rank)
        for rec,domain in proposals:
            row=self.catalog.data['families'][rec['id']]
            row['screened_candidate_category']='inspiration';row['assigned_inspiration_domain']=domain
    def validate_row(self,row,task):
        if not isinstance(row,dict) or not row.get('title') or not row.get('source'):return False
        date=row.get('publication_date')
        if date:
            try:
                if not task['start']<=dt.date.fromisoformat(date).isoformat()<=task['end']:return False
            except ValueError:return False
        elif row.get('year') is not None:
            if not int(task['start'][:4])<=int(row['year'])<=int(task['end'][:4]):return False
            row['date_window_status']='YEAR_INTERIOR_VERIFIED' if int(task['start'][:4])<int(row['year'])<int(task['end'][:4]) else 'YEAR_ONLY_BOUNDARY_UNCERTAIN'
        else:return False
        return True
    def run(self,*,max_steps=12,extra_queries=None,question_only=False):
        if not self.online:raise ValueError('Online discovery requires explicit caller authorization')
        if not 1<=max_steps<=100 or not 1<=self.budget['limit']<=100:raise ValueError('Invalid bounded run')
        with locked(self.root):
            return self._run_locked(max_steps=max_steps,extra_queries=extra_queries,question_only=question_only)
    def _run_locked(self,*,max_steps=12,extra_queries=None,question_only=False):
        if self.cfg.get('acquisition_mode') == 'MAINTENANCE_ONLY' and not question_only:
            return {'status':'BROAD_EXPANSION_STOPPED_TARGET_250_RETAINED','api_requests_this_run':0,'checkpoint_preserved':True,'next':'Use question_only with explicit evidence gaps; local fulltext admission and screening remain available'}
        self.plan(extra_queries);events=[];blocked=set()
        order=self.route({'query':self.dc['main_direction'],'category':'core'})
        for step in range(max_steps):
            if self.budget['sent']>=self.budget['limit']:break
            source=order[step%len(order)]
            if source in blocked:continue
            tasks=[t for t in self.state['tasks'].values() if t['source']==source and not t.get('superseded_by') and (not question_only or t.get('question_id')) and t['status'] not in ('DONE','REUSED_LEGACY_SUCCESS','RESOURCE_NOT_FOUND')]
            if not tasks:continue
            # Breadth before deeper pagination: one prolific first query must not starve
            # the remaining independently reviewed semantic queries. Explicit DOI
            # verification/question tasks keep their higher admission priority.
            completed=self.completed_semantics();domain_gaps=self.preferred_domain_gaps()
            task=min(tasks,key=lambda t:(t['priority']>=0,
                not (t['category']=='inspiration' and t.get('domain') in domain_gaps),
                (t['category'],t.get('domain',''),t['query']) in completed,
                t['pages_completed'],t['priority'],t.get('last_step_at',''),t['id']))
            try:
                request_cursor=task.get('cursor')
                rows,cursor=self.adapters[source].search(task,request_cursor)
                added=0;rejected=0
                for row in rows:
                    if not self.validate_row(row,task):rejected+=1;continue
                    fid,new=self.catalog.add(row,task);added+=new
                    if row.get('doi') and source not in ('crossref','openalex'):
                        sem={k:task[k] for k in ('query','category','domain','start','end','band')}
                        sem.update({'doi':row['doi'],'query':row['title']})
                        self.add_task(sem,'crossref',-1000)
                task['cursor']=cursor;task['status']='DONE' if cursor is None else 'PENDING'
                task['pages_completed']+=1;task['last_step_at']=utc();task.pop('last_error',None)
                self.record_query_pass(task,request_cursor,cursor,len(rows),added,rejected)
                events.append({'source':source,'task_id':task['id'],'status':'PAGE_COMMITTED','new_manifestations':added,'rejected_outside_window':rejected,'next_cursor':cursor})
            except SourcePause as exc:
                task['last_error']=exc.info
                if source=='crossref' and task.get('doi') and exc.info.get('kind')=='NOT_FOUND':
                    task['status']='RESOURCE_NOT_FOUND'
                    events.append({'source':source,'task_id':task['id'],'status':'TASK_RESOURCE_NOT_FOUND','details':exc.info})
                else:
                    task['status']='PAUSED';blocked.add(source)
                    events.append({'source':source,'task_id':task['id'],'status':'SOURCE_PAUSED','details':exc.info})
            except (ValueError,KeyError,TypeError,ET.ParseError) as exc:
                # Parser/API shape failure is source-local. Integrity failures are fatal.
                if 'integrity' in str(exc).casefold() or 'binding' in str(exc).casefold():raise
                task['last_error']={'kind':'SOURCE_SCHEMA_ERROR','error':str(exc)[:300]};task['status']='PAUSED';blocked.add(source)
                events.append({'source':source,'task_id':task['id'],'status':'SOURCE_SCHEMA_ERROR','details':task['last_error']})
            self.classify();self.save()
        self.classify();self.save()
        report={'status':'MULTISOURCE_CHECKPOINT_SAVED','at':utc(),'source_events':events,'requests':self.budget['sent'],
                'api_requests_this_run':self.budget['sent'],'metadata_only':True,'new_model_dispatches':0,
                'source_failures_are_isolated':True,'summary':self.status()}
        self.state['runs'].append({'at':report['at'],'requests':self.budget['sent'],'event_count':len(events)})
        self.save()
        runfile=self.root/'runs'/('run_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
        write(runfile,report);report['report']=str(runfile);return report
    def preferred_domain_gaps(self):
        counts,_=self.catalog.counts()
        if any(counts.get(category,0)<self.dc['quotas'][category] for category in ('core','related')):return set()
        domains={}
        for family in self.catalog.active().values():
            category=(family['legacy_categories'] or [family.get('screened_candidate_category')])[0]
            if category!='inspiration':continue
            rec=self.catalog.data['records'][family['record_ids'][0]]
            domain=family.get('assigned_inspiration_domain') or rec.get('assigned_inspiration_domain')
            if domain:domains[domain]=domains.get(domain,0)+1
        return {domain for domain,minimum in self.dc['preferred_domains'].items() if domains.get(domain,0)<minimum}
    def query_identity(self,task):
        return {k:task.get(k) for k in ('id','source','query','category','domain','band','start','end','retrieval_profile')}
    def record_query_pass(self,task,request_cursor,next_cursor,returned,added,rejected):
        # A committed bounded API page is the original discovery query-pass unit.
        # Preserve pagination; QUERY_PASS never means corpus/search exhaustion.
        receipt={'status':'QUERY_PASS','task':self.query_identity(task),'at':task['last_step_at'],
                 'request_cursor':request_cursor,'next_cursor':next_cursor,
                 'page_number':task['pages_completed'],'returned_rows':returned,
                 'new_manifestations':added,'rejected_outside_window':rejected,
                 'retrieval_exhaustive':None if task['source']=='openalex' else next_cursor is None,
                 'exhaustion_not_attested_by_bounded_adapter':task['source']=='openalex'}
        path=self.root/'query_passes'/(stable(receipt)+'.json');write(path,receipt)
        proof={'path':str(path),'sha256':sha(path.read_bytes())}
        task.setdefault('query_pass_receipts',[]).append(proof)
        self.committed_page_evidence[task['id']]={'kind':'QUERY_PASS',**proof}
    def has_committed_page(self,task):
        if not task.get('pages_completed'):return False
        for proof in task.get('query_pass_receipts',[]):
            path=pathlib.Path(proof.get('path',''))
            if not path.is_file() or sha(path.read_bytes())!=proof.get('sha256'):continue
            receipt=read(path)
            if receipt.get('status')=='QUERY_PASS' and receipt.get('task')==self.query_identity(task):return True
        return self.committed_page_evidence.get(task.get('id'),{}).get('kind')=='COMMITTED_SOURCE_PAGE_RUN_RECEIPT'
    def query_coverage_completed(self,task):
        if (task.get('superseded_by') or task.get('doi') or
                (task.get('category')=='inspiration' and task.get('retrieval_profile')=='ADJACENT_PHRASE_BROAD_V1')):return False
        if not self.has_committed_page(task):return False
        if task['source'] in ('crossref','arxiv','openreview','openalex'):return True
        # Repository index scanning needs its configured full index scope, unlike APIs.
        return task['status']=='DONE'
    def completed_semantics(self,baseline=None):
        if baseline is None:
            path=self.ws/'output/discovery_preflight/state.json'
            baseline=read(path) if path.exists() else {}
        result={(x.get('category'),x.get('domain',''),x.get('query')) for x in baseline.get('queries_done',{}).values()
                if x.get('band')=='RECENT_3Y' and not x.get('doi')}
        result.update((t['category'],t.get('domain',''),t['query']) for t in self.state['tasks'].values()
            if t.get('band')=='RECENT_3Y' and self.query_coverage_completed(t))
        return result
    def status(self):
        self.seed();counts,conflicts=self.catalog.counts()
        baseline_path=self.ws/'output/discovery_preflight/state.json'
        baseline=read(baseline_path) if baseline_path.exists() else {}
        items=[]
        for fid,family in self.catalog.active().items():
            category=(family['legacy_categories'] or [family.get('screened_candidate_category')])[0]
            if category!='inspiration':continue
            rec=self.catalog.data['records'][family['record_ids'][0]]
            domain=family.get('assigned_inspiration_domain') or rec.get('assigned_inspiration_domain')
            if domain:
                defs=self.discovery.diversity.load_catalog(self.dc)['domains']
                if domain in defs:items.append({'assigned_inspiration_domain':domain,
                    'inspiration_macro_group':defs[domain]['macro_group'],
                    'inspiration_transfer_distance':defs[domain]['distance_to_mainline_heuristic']})
        summary=self.discovery.diversity.summarize(items,self.dc,self.discovery.diversity.load_catalog(self.dc))
        coverage=summary['breadth']
        policy=self.discovery.diversity.load_catalog(self.dc)['policy']
        concentration={'domains':[k for k,n in coverage['per_domain_counts'].items() if n>policy['max_per_domain']],
                       'macro_groups':[k for k,n in coverage['per_macro_group_counts'].items() if n>policy['max_per_macro_group']]}
        # All reviewed recent-window semantic queries need a completed source pass.
        # Added cues and raw quota counts cannot seal the original acquisition gate.
        completed_semantics=self.completed_semantics(baseline)
        missing_semantics=[list(q) for q in self.discovery.queries_for(self.dc) if tuple(q) not in completed_semantics]
        pending_legacy=[]
        plan_path=self.ws/'sources/openalex_transport/request_plan.json'
        if plan_path.exists():
            for request in read(plan_path).get('requests',[]):
                if request['task_key'] in baseline.get('queries_done',{}):continue
                equivalent=[t for t in self.state['tasks'].values() if t['query']==request['q'] and t['category']==request['category'] and t['start']==request['start'] and t['end']==request['end']]
                if not any(self.query_coverage_completed(t) for t in equivalent):
                    pending_legacy.append(request['task_key'])
        domains=self.discovery.diversity.load_catalog(self.dc)
        queried={domains['domains'][domain]['macro_group'] for category,domain,query in completed_semantics
                 if category=='inspiration' and domain in domains['domains']}
        covered_tasks=[t for t in self.state['tasks'].values() if t.get('band')=='RECENT_3Y' and self.query_coverage_completed(t)]
        pass_evidence=[{'task_id':t['id'],'source':t['source'],
            'scope':'BOUNDED_API_QUERY_PASS' if t['source'] in ('crossref','arxiv','openreview','openalex') else 'COMPLETED_REPOSITORY_INDEX_SCOPE',
            'pagination_exhausted':None if t['source']=='openalex' else t.get('cursor') is None,
            'exhaustion_not_attested_by_bounded_adapter':t['source']=='openalex',
            'receipt':self.committed_page_evidence.get(t['id']) or (t.get('query_pass_receipts') or [None])[-1]} for t in covered_tasks]
        continuing_api=[t['id'] for t in covered_tasks if t['source'] in ('crossref','arxiv','openreview','openalex') and t.get('cursor') is not None]
        sources={r['source'] for r in self.catalog.data['records'].values() if r['source'] in self.cfg['primary_sources']}
        short={c:max(0,self.dc['quotas'][c]-counts.get(c,0)) for c in self.dc['quotas']}
        complete=(not any(short.values()) and not conflicts and coverage and not any(coverage.get('shortfalls',{}).values())
                  and not any(summary['preferred_domain_shortfalls'].values()) and not any(concentration.values()) and not missing_semantics and not pending_legacy
                  and len(queried)>=domains['policy']['min_macro_groups'] and len(sources)>=2)
        return {'status':'CATALOG_250_PLUS_COMPLETE' if complete else 'MULTISOURCE_COVERAGE_PENDING',
          'counts':{c:counts[c] for c in ('core','related','inspiration')},'shortfalls':short,
          'unclassified':counts['unclassified'],'unique_work_families':len(self.catalog.active()),
          'manifestations':len(self.catalog.data['records']),'category_conflicts':conflicts,
          'primary_sources_with_actual_metadata':sorted(sources),'queried_inspiration_macro_groups':len(queried),
          'inspiration_breadth':coverage,'inspiration_concentration_violations':concentration,'reviewed_queries_pending':missing_semantics,
          'reviewed_query_coverage':{'unit':'BOUNDED_SUCCESSFUL_API_QUERY_PASS_OR_COMPLETED_REPOSITORY_INDEX_SCOPE',
            'completed_reviewed_semantics':len(set(self.discovery.queries_for(self.dc)) & completed_semantics),
            'verified_task_passes':len(covered_tasks),'task_evidence':pass_evidence,
            'continuing_api_task_ids':continuing_api,'non_exhaustive_api_passes':len(continuing_api),
            'exhaustive_corpus_search_claimed':False,
            'bounded_openalex_passes_without_exhaustion_attestation':sum(t['source']=='openalex' for t in covered_tasks),
            'pagination_cursors_and_task_statuses_preserved':True},
          'legacy_pending_queries_without_equivalent_source_page':pending_legacy,
          'inspiration_domain_shortfalls':summary['preferred_domain_shortfalls'],'legacy_openalex_source_window':baseline.get('selection',{}).get('status'),
          'legacy_windows_not_falsely_marked_complete':True,'metadata_gate_not_semantic_review':True,
          'pending_tasks':sum(not t.get('superseded_by') and t['status'] not in ('DONE','REUSED_LEGACY_SUCCESS','RESOURCE_NOT_FOUND') for t in self.state['tasks'].values()),
          'library':str(self.catalog.path),'fulltext_ready_for_deepread':'REQUIRES_EXPLICIT_ADMISSION_AND_NATIVE_INGEST',
          'api_requests':self.budget['sent'],'api_requests_this_run':self.budget['sent'],
          'fulltexts_downloaded':len(self.catalog.data['downloads']),
          'usable_download_records':len(self.catalog.usable_downloads()),
          'rejected_download_identity_links':len(self.catalog.data['downloads'])-len(self.catalog.usable_downloads())}