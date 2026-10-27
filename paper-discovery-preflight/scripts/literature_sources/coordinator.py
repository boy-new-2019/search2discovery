"""Bounded multi-source discovery; failed sources never disable healthy sources."""
from __future__ import annotations
import datetime as dt,json,pathlib,re,sqlite3,xml.etree.ElementTree as ET
from .common import DEFAULTS,SOURCES,config,read,write,stable,sha,utc,locked
from .transport import HTTP,SourcePause
from .adapters import ADAPTERS,from_legacy
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
        task={**semantic,'source':source};tid=stable(task)[:24]
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
        pool=[];used=set()
        for family,row in self.catalog.active().items():
            allowed_crossref={'DOI_REGISTERED_JOURNAL-ARTICLE','DOI_REGISTERED_PROCEEDINGS-ARTICLE','DOI_REGISTERED_POSTED-CONTENT','DOI_REGISTERED_REVIEW'}
            eligible_records=[self.catalog.data['records'][rid] for rid in row['record_ids']
                if self.catalog.data['records'][rid]['source']!='crossref' or self.catalog.data['records'][rid].get('publication_status') in allowed_crossref]
            if not eligible_records and not row['legacy_categories']:
                row.pop('screened_candidate_category',None);continue
            rec=eligible_records[0] if eligible_records else self.catalog.data['records'][row['record_ids'][0]]
            task_domains={t.get('domain') for t in self.state['tasks'].values()
                          if t.get('category')=='inspiration' and t.get('domain') and
                          set(row['record_ids']) & set(self.catalog.data['query_links'].get(t['id'],[]))}
            task_domains.update(d for rid in row['record_ids'] for d in self.catalog.data['records'][rid].get('inspiration_domains',[]))
            shim={**rec,'id':family,'category_sources':row.get('nominations',[]),
                  'inspiration_domains':sorted(task_domains),'cited_by_count':rec.get('citation_count') or 0}
            if row['legacy_categories']:
                used.add(family);continue
            if all(self.catalog.data['records'][rid].get('date_window_status')=='YEAR_ONLY_BOUNDARY_UNCERTAIN' for rid in row['record_ids']):continue
            score=self.discovery.paper_scores(shim,self.dc)
            # Keyword nominations are metadata screening, never S1/S2 reviewer decisions.
            category='core' if score['core_eligible'] else 'related' if score['related_eligible'] else None
            if category:row['screened_candidate_category']=category;used.add(family)
            elif score['inspiration_eligible'] and rec.get('publication_date'):
                pool.append(shim)
        legacy_inspiration=sum('inspiration' in r['legacy_categories'] for r in self.catalog.active().values())
        remaining=max(0,self.dc['quotas']['inspiration']-legacy_inspiration)
        proposals=[] if not remaining else self.discovery.diversity.diversify(pool,used_ids=used,
            eligible={r['id']:True for r in pool},catalog=domains,preferred=self.dc['preferred_domains'],
            target=remaining,rank=lambda r:self.discovery.rank(r,self.dc,dt.date.fromisoformat(self.dc['as_of_date'])))
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
            tasks=[t for t in self.state['tasks'].values() if t['source']==source and (not question_only or t.get('question_id')) and t['status'] not in ('DONE','REUSED_LEGACY_SUCCESS')]
            if not tasks:continue
            task=min(tasks,key=lambda t:(t['priority'],t.get('last_step_at',''),t['id']))
            try:
                rows,cursor=self.adapters[source].search(task,task.get('cursor'))
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
                events.append({'source':source,'task_id':task['id'],'status':'PAGE_COMMITTED','new_manifestations':added,'rejected_outside_window':rejected,'next_cursor':cursor})
            except SourcePause as exc:
                task['last_error']=exc.info;task['status']='PAUSED';blocked.add(source)
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
        completed_semantics={(x.get('category'),x.get('domain',''),x.get('query')) for x in baseline.get('queries_done',{}).values() if x.get('band')=='RECENT_3Y'}
        completed_semantics.update((t['category'],t.get('domain',''),t['query']) for t in self.state['tasks'].values() if t['status']=='DONE' and t.get('band')=='RECENT_3Y')
        missing_semantics=[list(q) for q in self.discovery.queries_for(self.dc) if tuple(q) not in completed_semantics]
        pending_legacy=[]
        plan_path=self.ws/'sources/openalex_transport/request_plan.json'
        if plan_path.exists():
            for request in read(plan_path).get('requests',[]):
                if request['task_key'] in baseline.get('queries_done',{}):continue
                equivalent=[t for t in self.state['tasks'].values() if t['query']==request['q'] and t['category']==request['category'] and t['start']==request['start'] and t['end']==request['end']]
                if not any(t['pages_completed']>0 and (t['status']=='DONE' or t['source'] in ('crossref','arxiv','openalex','openreview')) for t in equivalent):
                    pending_legacy.append(request['task_key'])
        domains=self.discovery.diversity.load_catalog(self.dc)
        queried={domains['domains'][x['domain']]['macro_group'] for x in baseline.get('queries_done',{}).values()
                 if x.get('band')=='RECENT_3Y' and x.get('category')=='inspiration' and x.get('domain') in domains['domains']}
        for task in self.state['tasks'].values():
            if task['status']=='DONE' and task.get('category')=='inspiration' and task.get('band')=='RECENT_3Y' and task.get('domain') in domains['domains']:
                queried.add(domains['domains'][task['domain']]['macro_group'])
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
          'legacy_pending_queries_without_equivalent_source_page':pending_legacy,
          'inspiration_domain_shortfalls':summary['preferred_domain_shortfalls'],'legacy_openalex_source_window':baseline.get('selection',{}).get('status'),
          'legacy_windows_not_falsely_marked_complete':True,'metadata_gate_not_semantic_review':True,
          'pending_tasks':sum(t['status'] not in ('DONE','REUSED_LEGACY_SUCCESS') for t in self.state['tasks'].values()),
          'library':str(self.catalog.path),'fulltext_ready_for_deepread':'REQUIRES_EXPLICIT_ADMISSION_AND_NATIVE_INGEST',
          'api_requests':self.budget['sent'],'api_requests_this_run':self.budget['sent'],
          'fulltexts_downloaded':len(self.catalog.data['downloads']),
          'usable_download_records':len(self.catalog.usable_downloads()),
          'rejected_download_identity_links':len(self.catalog.data['downloads'])-len(self.catalog.usable_downloads())}