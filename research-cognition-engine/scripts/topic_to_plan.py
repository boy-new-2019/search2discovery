#!/usr/bin/env python3
"""v6.2 topic-to-research-plan orchestration for Codex Desktop.

Deterministic state/metadata/download/gates only; semantic interpretation and
independent paper reading are delegated to genuine Codex Desktop subagents.
No experiment execution, no Codex CLI, no fabricated scientific findings.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
from collections import Counter, defaultdict
from typing import Any

import store
import suite
import workflow_v61 as wf
import prior_art
import venue_authority as official_venues

V5=suite.discovery
BATCH=suite.original_batch
ENGINE=suite.engine
VERSION='6.3.0'
SCHEMA=1
MIN_TOPICS=3


def here(ws:pathlib.Path)->pathlib.Path:
    return store.root(ws)/'topic_to_plan'


def contract_path(ws:pathlib.Path)->pathlib.Path:
    return here(ws)/'contract.json'


def contract(ws:pathlib.Path)->dict:
    f=contract_path(ws)
    if not f.is_file():raise ValueError('No active research topic. Run topic-start --topic "your research topic".')
    data=store.read(f)
    if data.get('schema_version')!=SCHEMA:raise ValueError('Frozen research topic or signed research contract mismatch at topic_to_plan.contract (check 46). Reconfirm boundaries; do not overwrite approved work.')
    goal=ws/'goal.md'
    if not goal.is_file() or store.hashbytes(goal.read_bytes())!=data.get('goal_sha256'):
        raise ValueError('Research goal.md was changed or removed. Refuse to reuse the frozen scientific contract.')
    if data.get('topic_sha256')!=store.hashbytes(data['topic'].encode('utf-8')):
        raise ValueError('Research topic SHA256 does not match the signed topic contract.')
    return data


def start(ws:pathlib.Path,topic:str)->dict:
    ws=ws.expanduser().resolve()
    if not isinstance(topic,str):raise ValueError('Research topic must be a nonempty string.')
    topic=topic.strip()
    if not 6<=len(topic)<=1200 or any(ord(x)<32 for x in topic):
        raise ValueError('Research topic must contain 6–1200 printable characters.')
    if contract_path(ws).exists():
        old=contract(ws)
        if topic!=old['topic']:
            raise ValueError('This project already has a different locked research topic. Start a separate project rather than replacing the frozen topic.')
        return {'status':'TOPIC_ALREADY_REGISTERED','topic':topic,'next':'topic-next','contract':str(contract_path(ws))}
    if not (ws/'.agents'/'skills'/'research-cognition-engine'/'SKILL.md').is_file():
        raise ValueError('RCE Skill has not been installed in this workspace; install it first.')
    goal=ws/'goal.md'
    created=False
    if not goal.exists():
        text=('# User-confirmed research topic\n\n'+topic+'\n\n'
              '## Research protection boundaries\n'
              '- The topic was supplied explicitly; its background and methods still require real literature searches and independent review.\n'
              '- No unapproved changes to confirmed innovations, algorithms, mathematical definitions, protocols or genuine results.\n'
              '- Deliver candidate scientific questions, methods and experiment PLANS ONLY; the researcher performs all experiments.\n'
              '- Internal reasoning, tasks and intermediate reports use English. Present the final user-facing recommendations in Chinese.\n')
        goal.parent.mkdir(parents=True,exist_ok=True)
        goal.write_text(text,encoding='utf-8')
        created=True
    if len(goal.read_text('utf-8').strip())<15:
        raise ValueError('Existing goal.md is empty or invalid; confirm research constraints before continuing.')
    record={'schema_version':SCHEMA,'version':VERSION,'topic':topic,
            'topic_sha256':store.hashbytes(topic.encode('utf-8')),
            'goal_sha256':store.hashbytes(goal.read_bytes()),
            'created_goal':created,'started_at':store.utc(),
            'state':'AWAITING_NATIVE_TOPIC_INTERPRETATION',
            'experiment_execution_enabled':False,'route_contract_version':2,
            'paper_quotas':{'core':50,'related':150,'inspiration':50}}
    store.write(contract_path(ws),record)
    template={
        'schema_version':SCHEMA,'topic_sha256':record['topic_sha256'],
        'goal_sha256':record['goal_sha256'],
        'scope_relation':'NEW_TOPIC' if created else 'COMPATIBLE_WITH_EXISTING_GOAL',
        'topic_interpretation':'Explain the research objects, tasks, hypotheses and scope boundaries established by the actual user topic.',
        'problem_dimensions':['Independent native research specialist must identify at least three substantive scientific problem dimensions.'],
        'core_keywords':['verified English research term 1','verified English research term 2'],
        'related_keywords':['verified adjacent mechanism 1','verified adjacent mechanism 2'],
        'core_queries':['replace with a precise English research search phrase'],
        'related_queries':['replace with a related English academic search phrase'],
        'coverage_themes':[{'name':'pending theme review','min_core':1}],
        'venue_hints':{'conferences':[],'journals':[]},
        'reviewer_role':'rce_cartographer_sol','reviewer_thread_ref':'REPLACE_WITH_ACTUAL_CODEX_THREAD',
        'reasoning_boundary':'Explain connections among search queries, scientific problems and the fixed main topic; do not claim unexamined papers support any conclusion.',
    }
    store.write(here(ws)/'topic_brief_template.json',template)
    return {'status':'NEEDS_NATIVE_TOPIC_INTERPRETATION',
            'topic':topic,'created_goal_md':created,
            'review_template':str(here(ws)/'topic_brief_template.json'),
            'review_output':str(here(ws)/'topic_brief_reviewed.json'),
            'instruction':'Dispatch a genuine independent Codex Desktop research cartographer. Analyze the exact topic in English, produce research questions, search queries and editorial venue hints (not official certifications), then save topic_brief_reviewed.json and run topic-commit.'}


def _english_phrase(s:Any,kind:str)->str:
    if not isinstance(s,str):raise ValueError(kind+'Input, evidence or workflow invariant failed at topic_to_plan._english_phrase (check 114); inspect the signed task record and original source.')
    t=s.strip()
    if not 4<=len(t)<=170 or any(ord(x)<32 for x in t) or 'replace' in t.lower() or 'pending review' in t.lower():
        raise ValueError(kind+'Input, evidence or workflow invariant failed at topic_to_plan._english_phrase (check 117); inspect the signed task record and original source.')
    if not re.search('[a-zA-Z]{3,}',t):raise ValueError(kind+'Input, evidence or workflow invariant failed at topic_to_plan._english_phrase (check 118); inspect the signed task record and original source.')
    if len(re.findall(r'[a-zA-Z][a-zA-Z0-9-]*',t))<2:
        raise ValueError(kind+'Input, evidence or workflow invariant failed at topic_to_plan._english_phrase (check 120); inspect the signed task record and original source.')
    return t


def _list_text(data:dict,key:str,lo:int,hi:int,query:bool)->list[str]:
    items=data.get(key)
    if not isinstance(items,list) or not lo<=len(items)<=hi:raise ValueError(key+'Input, evidence or workflow invariant failed at topic_to_plan._list_text (check 126); inspect the signed task record and original source.')
    clean=[]
    for s in items:
        t=_english_phrase(s,key) if query else str(s).strip()
        if not query and (not 3<=len(t)<=130 or 'pending review' in t.lower() or 'verified ' in t.lower() or not re.search(r'[a-zA-Z]{2,}',t)):
            raise ValueError(key+'Input, evidence or workflow invariant failed at topic_to_plan._list_text (check 131); inspect the signed task record and original source.')
        if t.lower() not in [x.lower() for x in clean]:clean.append(t)
    if len(clean)<lo:raise ValueError(key+'Input, evidence or workflow invariant failed at topic_to_plan._list_text (check 133); inspect the signed task record and original source.')
    return clean


def _check_brief(ws:pathlib.Path,brief:dict,rec:dict)->dict:
    if not isinstance(brief,dict) or brief.get('schema_version')!=SCHEMA or brief.get('topic_sha256')!=rec['topic_sha256'] or brief.get('goal_sha256')!=rec['goal_sha256']:
        raise ValueError('Frozen research topic or signed research contract mismatch at topic_to_plan._check_brief (check 139). Reconfirm boundaries; do not overwrite approved work.')
    valid='NEW_TOPIC' if rec['created_goal'] else 'COMPATIBLE_WITH_EXISTING_GOAL'
    if brief.get('scope_relation')!=valid:
        raise ValueError('Frozen research topic or signed research contract mismatch at topic_to_plan._check_brief (check 142). Reconfirm boundaries; do not overwrite approved work.')
    interpretation=brief.get('topic_interpretation')
    if not isinstance(interpretation,str) or len(interpretation.strip())<35 or interpretation.startswith('Explain the research objects'):
        raise ValueError('Input, evidence or workflow invariant failed at topic_to_plan._check_brief (check 145); inspect the signed task record and original source.')
    dimensions=brief.get('problem_dimensions')
    if not isinstance(dimensions,list) or not MIN_TOPICS<=len(dimensions)<=12 or any(not isinstance(s,str) or len(s.strip())<15 or s.startswith('Independent native research specialist') for s in dimensions):
        raise ValueError('Independent native research-agent identity or reviewer evidence failed validation at topic_to_plan._check_brief (check 148).')
    _list_text(brief,'core_keywords',4,25,False)
    _list_text(brief,'related_keywords',5,35,False)
    _list_text(brief,'core_queries',4,18,True)
    _list_text(brief,'related_queries',5,18,True)
    themes=brief.get('coverage_themes')
    if not isinstance(themes,list) or not 2<=len(themes)<=10 or len({x.get('name') for x in themes if isinstance(x,dict)})!=len(themes):
        raise ValueError('Input, evidence or workflow invariant failed at topic_to_plan._check_brief (check 155); inspect the signed task record and original source.')
    for t in themes:
        if not isinstance(t,dict) or not isinstance(t.get('name'),str) or not 3<=len(t['name'])<=90 or 'pending review' in t['name'].lower():
            raise ValueError('Input, evidence or workflow invariant failed at topic_to_plan._check_brief (check 158); inspect the signed task record and original source.')
        if type(t.get('min_core')) is not int or not 0<=t['min_core']<=15:raise ValueError('Input, evidence or workflow invariant failed at topic_to_plan._check_brief (check 159); inspect the signed task record and original source.')
    if sum(x['min_core'] for x in themes)>80:raise ValueError('Input, evidence or workflow invariant failed at topic_to_plan._check_brief (check 160); inspect the signed task record and original source.')
    venue=brief.get('venue_hints')
    if not isinstance(venue,dict) or set(venue)!={'conferences','journals'}:raise ValueError('Input, evidence or workflow invariant failed at topic_to_plan._check_brief (check 162); inspect the signed task record and original source.')
    for name in ('conferences','journals'):
        xs=venue[name]
        if not isinstance(xs,list) or len(xs)>30 or any(not isinstance(s,str) or not 3<=len(s.strip())<=110 for s in xs):
            raise ValueError('Input, evidence or workflow invariant failed at topic_to_plan._check_brief (check 166); inspect the signed task record and original source.')
    if brief.get('reviewer_role')!='rce_cartographer_sol':raise ValueError('Independent native research-agent identity or reviewer evidence failed validation at topic_to_plan._check_brief (check 167).')
    ref=brief.get('reviewer_thread_ref')
    if not isinstance(ref,str) or len(ref.strip())<6 or 'REPLACE' in ref.upper():
        raise ValueError('Independent native research-agent identity or reviewer evidence failed validation at topic_to_plan._check_brief (check 170).')
    if len(str(brief.get('reasoning_boundary','')).strip())<25:raise ValueError('Independent native research-agent identity or reviewer evidence failed validation at topic_to_plan._check_brief (check 171).')
    return brief


def commit(ws:pathlib.Path,brief_path:pathlib.Path)->dict:
    ws=ws.expanduser().resolve(); rec=contract(ws)
    if rec['state']=='TOPIC_CONFIG_COMMITTED':
        original=here(ws)/'topic_brief_reviewed.json'
        if original.exists() and store.hashbytes(original.read_bytes())==rec.get('reviewed_sha256'):
            return {'status':'TOPIC_ALREADY_COMMITTED','next':'topic-next'}
        raise ValueError('Source path, lawful access or network permission check failed at topic_to_plan.commit (check 181). Do not bypass paywalls or source integrity checks.')
    src=brief_path.expanduser().resolve()
    if not src.is_file():raise ValueError('Source path, lawful access or network permission check failed at topic_to_plan.commit (check 183). Do not bypass paywalls or source integrity checks.')
    b=_check_brief(ws,store.read(src),rec)
    if (ws/'output'/'discovery_preflight'/'state.json').is_file():
        raise ValueError('Configuration schema or numeric bounds check failed at topic_to_plan.commit (check 186). Keep strict quality gates intact.')
    if (ws/'output'/'batch'/'state.json').is_file():
        raise ValueError('Source path, lawful access or network permission check failed at topic_to_plan.commit (check 188). Do not bypass paywalls or source integrity checks.')
    cfg_path=ws/'discovery_config.json'
    if cfg_path.exists():
        existing=store.read(cfg_path)
        if existing!=store.read(V5.DEFAULT):raise ValueError('Local assignment budget or reserved quota check failed at topic_to_plan.commit (check 192). Save the checkpoint before resuming.')
    # Original v5 schema and strict quotas/diversity/authority gates preserved.
    v5=store.read(V5.DEFAULT)
    v5['main_direction']=rec['topic']
    for src_key,dst_key in [('core_keywords','core_keywords'),('related_keywords','related_keywords')]:
        v5[dst_key]=_list_text(b,src_key,4 if src_key=='core_keywords' else 5,35,False)
    v5['queries']['core']=_list_text(b,'core_queries',4,18,True)
    v5['queries']['related']=_list_text(b,'related_queries',5,18,True)
    v5['topic_generic_research_mode']=True
    v5['topic_editorial_venue_hints']=b['venue_hints']['conferences']+b['venue_hints']['journals']
    # Freeze date at first semantic topic interpretation instead of re-floating during resume.
    v5['as_of_date']=dt.date.today().isoformat()
    sel=store.read(suite.ROOT/'batch-paper-deepread-desktop'/'selection_config.example.json')
    sel['coverage_themes']=b['coverage_themes']
    sel['search_queries']=v5['queries']['core'][:4]+v5['queries']['related'][:3]
    prior_config=cfg_path.read_bytes() if cfg_path.exists() else None
    sel_path=ws/'selection_config.json'
    prior_sel=sel_path.read_bytes() if sel_path.exists() else None
    if prior_sel is not None and store.read(sel_path)!=store.read(suite.ROOT/'batch-paper-deepread-desktop'/'selection_config.example.json'):
        raise ValueError('Source path, lawful access or network permission check failed at topic_to_plan.commit (check 211). Do not bypass paywalls or source integrity checks.')
    try:
        store.write(cfg_path,v5)
        store.write(sel_path,sel)
        V5.config(ws);BATCH.cfg_at(ws)
        result=suite.initialize(ws)
        if result['status']!='INSTALL_READY':raise ValueError('Configuration schema or numeric bounds check failed at topic_to_plan.commit (check 217). Keep strict quality gates intact.'+str(result))
    except Exception:
        if prior_config is None:cfg_path.unlink(missing_ok=True)
        else:cfg_path.write_bytes(prior_config)
        if prior_sel is None:sel_path.unlink(missing_ok=True)
        else:sel_path.write_bytes(prior_sel)
        raise
    store.write(here(ws)/'topic_brief_reviewed.json',b)
    rec['state']='TOPIC_CONFIG_COMMITTED'
    rec['as_of_date']=v5['as_of_date']
    rec['reviewed_sha256']=store.hashbytes((here(ws)/'topic_brief_reviewed.json').read_bytes())
    rec['reviewer_role']=b['reviewer_role'];rec['reviewer_thread_ref']=b['reviewer_thread_ref']
    store.write(contract_path(ws),rec)
    if rec.get('route_contract_version',1)>=2:
        from literature_sources.coordinator import configure
        configure(ws)
    return {'status':'TOPIC_CONFIG_COMMITTED','topic':rec['topic'],
            'as_of_date':rec['as_of_date'],'v5_quota':v5['quotas'],
            'configured_core_queries':len(v5['queries']['core']),
            'configured_related_queries':len(v5['queries']['related']),
            'venue_hints_are_unverified':True,'next':'topic-next'}


def _source_rank(w:dict,c:dict)->bool:
    # Only curated shortlist, NOT externally certified "top" ranking.
    try:return V5.priority_venue(w,c)
    except (KeyError,ValueError,TypeError):return False


def venues(ws:pathlib.Path)->dict:
    ws=ws.expanduser().resolve();rec=contract(ws)
    if rec['state']!='TOPIC_CONFIG_COMMITTED':
        return {'status':'NEEDS_TOPIC_CONFIG','sources':[]}
    cfg=V5.config(ws)
    library=ws/'output'/'discovery_preflight'/'state.json'
    allworks=store.read(library).get('works',{}) if library.is_file() else {}
    if (ws/'source_routing.json').is_file():
        import multisource_bridge
        allworks={**allworks,**multisource_bridge.venue_records(ws)}
    hints=store.read(here(ws)/'topic_brief_reviewed.json')['venue_hints']
    groups={}
    for w in allworks.values():
        if not isinstance(w,dict) or not w.get('venue'):continue
        source=w.get('source_id') or 'UNVERIFIED:'+str(w['venue']).casefold()
        key=str(source)
        if key not in groups:
            stype=(w.get('venue_type') or '').lower()
            if stype not in ('journal','conference','repository','ebook platform','book series'):
                stype='UNKNOWN_VERIFY_SOURCE'
            groups[key]={'source_id':str(w.get('source_id') or ''),'name':w['venue'],'type':stype,
                         'paper_count':0,'recent_papers':0,'core_relevant_papers':0,
                         'oa_pdf_links':0,'shortlist_match':False,'sample_paper_ids':[],
                         'classification':'METADATA_ONLY_NOT_OFFICIAL_RANK','jcr_quartile':'UNKNOWN_UNVERIFIED','cas_partition':'NO_NEW_DATA_AFTER_2025','ccf_category':'UNKNOWN_UNVERIFIED'}
        g=groups[key]
        g['paper_count']+=1
        if int(w.get('year') or 0)>=dt.date.fromisoformat(rec['as_of_date']).year-3:g['recent_papers']+=1
        if 'core' in w.get('category_sources',[]):g['core_relevant_papers']+=1
        if w.get('oa_pdf_url'):g['oa_pdf_links']+=1
        g['shortlist_match']=g['shortlist_match'] or _source_rank(w,cfg)
        if len(g['sample_paper_ids'])<5:g['sample_paper_ids'].append(w.get('id',''))
    rows=sorted(groups.values(),key=lambda x:(not x['shortlist_match'],-x['core_relevant_papers'],-x['paper_count'],x['name']))
    suggestions=[]
    actuals={re.sub(r'\W','',x['name'].lower()) for x in rows}
    for label in ('conferences','journals'):
        for h in hints[label]:
            if re.sub(r'\W','',h.lower()) not in actuals:
                suggestions.append({'name':h,'type':'UNVERIFIED_'+label.upper(),
                                    'status':'USER_OR_AGENT_HINT_NOT_YET_FOUND_IN_PAPER_METADATA'})
    output={'status':'VENUE_METADATA_PROFILE_READY' if rows else 'NEEDS_REAL_OPENALEX_WORKS',
            'topic_sha256':rec['topic_sha256'],'sources':rows,'unverified_hints':suggestions,
            'source_disclaimer':'OpenAlex source metadata and editorial shortlist are NOT an official JCR/CAS/CCF ranking; official annual publication verification is separate from specific venue classification.',
            'official_annual_check':official_venues.status(ws),
            'recent_years_preferred':3,'count':len(rows)}
    store.write(here(ws)/'venue_landscape.json',output)
    lines = [
        '# Publication venues actually encountered in verified paper metadata', '',
        '> The evidence below comes from OpenAlex bibliographic records. A venue shortlist match is an editorial retrieval signal, not an official JCR, CAS, or CCF entry.', '',
        '| Venue | OpenAlex source type | Recent papers | Core candidates | OA PDF links | Editorial shortlist | Official item-level classification | Source ID |',
        '|---|---|---:|---:|---:|---|---|---|',
    ]
    for r in rows[:150]:
        name = r['name'].replace('|', '\\|').replace('\n', ' ')
        shortlist = 'Shortlist match; NOT official ranking' if r['shortlist_match'] else 'Unverified editorial status'
        lines.append(f"|{name}|{r['type']}|{r['recent_papers']}|{r['core_relevant_papers']}|{r['oa_pdf_links']}|{shortlist}|NOT_ITEM_LEVEL_VERIFIED|{r['source_id']}|")
    lines.extend(['', '## Official annual authority check', '',
                  '- Annual release/policy state: '+str(official_venues.status(ws)),
                  '- A checked authority website does not certify the JCR quartile or CCF category of individual journals and conferences.',
                  '- CAS journal partitions ceased annual updates from 2026; a 2025 edition remains historical evidence only.',
                  '- JCR item-level quartiles require licensed and identifiable records; a journal promotion page is insufficient.',
                  '- CCF classifications must match exact official directory entries and eligible conference tracks.', ''])
    if not rows:
        lines.append('No authentic bibliographic venue data have been collected. Do not invent venue identities or rankings.')
    if suggestions:
        lines.extend(['', '## User/agent editorial venue hints not yet observed in authentic metadata', ''])
        lines.extend('- '+x['name']+' (unverified hint)' for x in suggestions)
    store.textwrite(here(ws)/'venue_landscape.md','\n'.join(lines)+'\n')
    return {'status':output['status'],'source_count':len(rows),'shortlist_matches':sum(x['shortlist_match'] for x in rows),
            'verified_conference_sources':sum(x['type']=='conference' for x in rows),
            'verified_journal_sources':sum(x['type']=='journal' for x in rows),
            'unverified_hints':len(suggestions),'report':str(here(ws)/'venue_landscape.md')}


def _verified_download_stats(ws:pathlib.Path)->dict:
    f=ws/'output'/'discovery_preflight'/'state.json'
    if not f.is_file():return {'core':0,'related':0,'inspiration':0,'total':0,'tampered':[]}
    records=store.read(f).get('download_log',{})
    counts=Counter();bad=[];digests=set()
    for wid,rec in records.items():
        if rec.get('status')!='FULLTEXT_READY':continue
        rel=pathlib.Path(rec.get('relative_path',''))
        if rel.is_absolute() or '..' in rel.parts or not rel.parts:
            bad.append(wid);continue
        source=(ws/rel).resolve()
        if not source.is_relative_to(ws) or not source.is_file() or store.hashbytes(source.read_bytes())!=rec.get('sha256'):
            bad.append(wid);continue
        counts[rec.get('category','other')]+=1;digests.add(rec['sha256'])
    if (ws/'source_routing.json').is_file():
        import multisource_bridge
        for item in multisource_bridge.downloads(ws):
            if item['sha256'] not in digests:
                counts[item['category'] or 'other']+=1;digests.add(item['sha256'])
    if bad:raise ValueError('Source path, lawful access or network permission check failed at topic_to_plan._verified_download_stats (check 327). Do not bypass paywalls or source integrity checks.'+str(bad[:5]))
    return {'core':counts['core'],'related':counts['related'],'inspiration':counts['inspiration'],
            'total':sum(counts.values()),'tampered':[]}


def next_action(ws:pathlib.Path,*,allow_incomplete_discovery:bool=False)->dict:
    ws=ws.expanduser().resolve();rec=contract(ws)
    if rec['state']!='TOPIC_CONFIG_COMMITTED':
        return {'status':'NEEDS_NATIVE_TOPIC_INTERPRETATION','next':'Source state and independent reviewer provenance must satisfy the specified quality gate.',
                'brief_template':str(here(ws)/'topic_brief_template.json')}
    # Before novelty appraisal, require an actual problem-specific prior-art
    # search with native-reviewed English phrases, not merely agent intuition.
    state_file=ENGINE.statefile(ws)
    if state_file.is_file():
        current=ENGINE.get_state(ws)
        if current.get('cycles') and current['cycles'][-1]['stage']=='NOVELTY':
            prior_plan=prior_art.plan(ws)
            if prior_plan['status']=='NEEDS_PRIOR_ART_QUERY_REVIEW':
                return {'status':'NEEDS_NATIVE_PRIOR_ART_QUERY_REVIEW',
                        'next':'Source state and independent reviewer provenance must satisfy the specified quality gate.',
                        'template':prior_plan['template']}
            if prior_plan['status']=='PRIOR_ART_PLAN_READY':
                prior_cov=prior_art.coverage(ws)
                if prior_cov['status']=='PRIOR_ART_NO_MATCHES_REQUIRES_MANUAL_EVIDENCE':
                    return {'status':'NEEDS_MANUAL_PRIOR_ART_EVIDENCE','coverage':prior_cov,
                            'next':'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
                if prior_cov['status']!='PRIOR_ART_RECENT_SEARCH_DONE':
                    return {'status':'NEEDS_PRIOR_ART_SEARCH','coverage':prior_cov,
                            'next':'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
                eligible=prior_art.downloadable(ws)
                if eligible['count']:
                    return {'status':'NEEDS_PRIOR_ART_OA_DOWNLOAD','available':eligible['count'],
                            'next':'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
    # Already frozen scientific documents remain authoritative; never run old goal-rewrite.
    base=wf.choose(ws,allow_incomplete_discovery=allow_incomplete_discovery)
    status=base['status']
    if status in ('NEEDS_DISCOVERY','NEEDS_READABLE_FULLTEXT','NEEDS_ORIGINAL_V44_INGEST','INSUFFICIENT_ELIGIBLE_CORE') and (ws/'source_routing.json').is_file():
        import multisource_bridge
        state_file=ws/'output/batch/state.json'
        reading=BATCH.load_state(ws) if state_file.is_file() else {}
        if not reading.get('frozen'):
            known={row['file'] for row in reading.get('papers',[])}
            local=ws/'input'
            new=[p for p in local.rglob('*') if p.is_file() and p.suffix.lower() in ('.pdf','.md','.txt','.tex') and p.relative_to(local).as_posix() not in known] if local.exists() else []
            if new:return {'status':'NEEDS_ORIGINAL_V44_INGEST','new_unindexed_papers':len(new),'next':'Ingest retained authentic full texts before further breadth discovery'}
            available=multisource_bridge.downloadable_core(ws)
            if available:
                return {'status':'NEEDS_AUTHORIZED_CORE_PDF_DOWNLOAD','available_oa_candidates':available,
                        'next':'Download a bounded admitted-topic candidate batch from authentic multi-source OA locations'}
    if status in ('NEEDS_ORIGINAL_V44_INGEST','NEEDS_READABLE_FULLTEXT','INSUFFICIENT_ELIGIBLE_CORE'):
        eligible=_verified_download_stats(ws)
        sourcepath=ws/'input'
        local_fulltexts=[p for p in sourcepath.rglob('*') if p.is_file() and p.suffix.lower() in ('.pdf','.md','.txt','.tex')] if sourcepath.is_dir() else []
        if local_fulltexts and status in ('NEEDS_READABLE_FULLTEXT','INSUFFICIENT_ELIGIBLE_CORE'):
            reading_file=ws/'output'/'batch'/'state.json'
            state=BATCH.load_state(ws) if reading_file.is_file() else None
            known={row['file'] for row in (state or {}).get('papers',[])}
            newfiles=[p for p in local_fulltexts if p.relative_to(sourcepath).as_posix() not in known]
            if newfiles and state and not state.get('frozen'):
                return {'status':'NEEDS_ORIGINAL_V44_INGEST','new_unindexed_papers':len(newfiles),
                        'next':'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
        if not local_fulltexts or (status=='NEEDS_READABLE_FULLTEXT' and eligible['core']<BATCH.cfg_at(ws)['core_min']):
            # If v5 picked papers without OA links, this is an honest stop.
            statefile=ws/'output'/'discovery_preflight'/'state.json'
            selection=(store.read(statefile).get('selection') or {}) if statefile.is_file() else {}
            choices=selection.get('selected',{}).get('core',[])
            to_get=[x for x in choices if x.get('oa_pdf_url') and x.get('id')]
            if to_get:
                return {'status':'NEEDS_AUTHORIZED_CORE_PDF_DOWNLOAD',
                        'downloaded_core':eligible['core'],'reader_core_min':BATCH.cfg_at(ws)['core_min'],
                        'available_oa_candidates':len(to_get),'next':'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
            return {'status':'NEEDS_LEGAL_FULLTEXT','downloaded_core':eligible['core'],
                    'next':'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
    if status in ('SCIENTIFIC_RECOMMENDATION_PENDING_USER_APPROVAL',):
        return {'status':'READY_FOR_FINAL_RESEARCH_AUDIT',
                'next':'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
    return base


def _read_source_safe(ws:pathlib.Path)->list[dict]:
    with store.connect(ws) as db:
        return [dict(x) for x in db.execute('SELECT source_id,work_id,file_path,file_sha FROM sources')]


def quality(ws:pathlib.Path,*,allow_incomplete_discovery:bool=False)->dict:
    ws=ws.expanduser().resolve();rec=contract(ws)
    hard=[];soft=[];stats={};null_route=False
    if rec.get('route_contract_version',1)>=2:
        try:
            import route_convergence
            route_result,_=route_convergence.committed(ws)
            stats['route_convergence']=route_result
            null_route=route_result['status']=='NO_VIABLE_CANDIDATE'
        except (ValueError,OSError,KeyError,IndexError) as ex:
            hard.append('Concrete route and method contract: '+str(ex)[:250])
    annual=official_venues.status(ws)
    stats['official_venue_authority']=annual
    if annual.get('should_search'):
        soft.append('Source state and independent reviewer provenance must satisfy the specified quality gate.')
    elif annual['status']=='ANNUAL_OFFICIAL_CHECK_PARTIAL':
        soft.append('Source state and independent reviewer provenance must satisfy the specified quality gate.')
    if rec['state']!='TOPIC_CONFIG_COMMITTED':hard.append('Source state and independent reviewer provenance must satisfy the specified quality gate.')
    if rec['state']=='TOPIC_CONFIG_COMMITTED':
        try:
            s=V5.status(ws)
            stats['bibliography']=s.get('counts',{})
            if s.get('status')!='CATALOG_250_PLUS_COMPLETE':
                msg='Source state and independent reviewer provenance must satisfy the specified quality gate.'
                if allow_incomplete_discovery:soft.append('Source state and independent reviewer provenance must satisfy the specified quality gate.'+msg)
                else:hard.append(msg)
        except Exception as ex:hard.append('Source state and independent reviewer provenance must satisfy the specified quality gate.'+str(ex)[:180])
    if rec['state']=='TOPIC_CONFIG_COMMITTED':
        try:
            v=venues(ws)
            stats['venue_source_count']=v['source_count']
            if not v['source_count']:
                hard.append('Source state and independent reviewer provenance must satisfy the specified quality gate.')
        except (ValueError,KeyError,OSError) as ex:
            hard.append('journal conference source audit failed: '+str(ex)[:120])
    try:
        x=BATCH.load_state(ws)
        if not x.get('frozen'):hard.append('Source state and independent reviewer provenance must satisfy the specified quality gate.')
        else:
            env=suite.original_core.env(pathlib.Path(x['frozen']['core_workspace']))
            r=suite.original_core.run_status(env)
            stats['reader_status']=r.get('status')
            if r.get('status')!='COMPLETE':hard.append('Source state and independent reviewer provenance must satisfy the specified quality gate.')
    except Exception as ex:hard.append('Research evidence and workflow notes (topic_to_plan.quality). Use original source evidence; keep frozen constraints and independent quality gates.'+str(ex)[:200])
    try:
        stage=ENGINE.get_state(ws)
        stats['research_cycles']=len(stage.get('cycles',[]))
        if not stage['cycles'] or stage['cycles'][-1]['stage']!='COMPLETE':
            hard.append('Source state and independent reviewer provenance must satisfy the specified quality gate.')
    except Exception as ex:hard.append('Research evidence and workflow notes (topic_to_plan.quality). Use original source evidence; keep frozen constraints and independent quality gates.'+str(ex)[:180])
    data={}
    with store.connect(ws) as db:
        for table in ('works','sources','claims','questions','hypotheses','assessments','experiments','decisions'):
            data[table]=[dict(x) for x in db.execute('SELECT * FROM '+table)]
    stats['knowledge_counts']={k:len(v) for k,v in data.items()}
    if not data['sources']:hard.append('Source state and independent reviewer provenance must satisfy the specified quality gate.')
    if not data['claims']:hard.append('Source state and independent reviewer provenance must satisfy the specified quality gate.')
    if not data['questions']:hard.append('Source state and independent reviewer provenance must satisfy the specified quality gate.')
    if not null_route and not data['hypotheses']:hard.append('Source state and independent reviewer provenance must satisfy the specified quality gate.')
    if not null_route and not data['decisions']:hard.append('Source state and independent reviewer provenance must satisfy the specified quality gate.')
    if not null_route and not data['experiments']:hard.append('Source state and independent reviewer provenance must satisfy the specified quality gate.')
    for src in data['sources']:
        p=pathlib.Path(src['file_path'])
        if not p.is_file() or store.hashbytes(p.read_bytes())!=src['file_sha']:
            hard.append('Source state and independent reviewer provenance must satisfy the specified quality gate.'+src['source_id'])
    for claim in data['claims']:
        try:store.checked_quote(ws,claim['source_id'],claim['page'],claim['quote'])
        except (ValueError,OSError) as e:hard.append('Research evidence and workflow notes (topic_to_plan.quality). Use original source evidence; keep frozen constraints and independent quality gates.'+claim['claim_id']+' '+str(e)[:85])
    reviews=defaultdict(list)
    for a in data['assessments']:reviews[a['hypothesis_id']].append(a)
    experiments=defaultdict(list)
    for x in data['experiments']:experiments[x['hypothesis_id']].append(x)
    byhyp={h['hypothesis_id']:h for h in data['hypotheses']}
    prior_art.init_db(ws)
    prior=prior_art.coverage(ws)
    stats['prior_art_search']=prior
    for d in data['decisions']:
        hid=d['hypothesis_id']
        if hid in prior['hypotheses_missing_two_recent_queries']:
            hard.append('Source state and independent reviewer provenance must satisfy the specified quality gate.'+hid)
        if hid in prior['hypotheses_without_found_prior_art']:
            hard.append('Source state and independent reviewer provenance must satisfy the specified quality gate.'+hid)
        if hid not in byhyp:hard.append('Source state and independent reviewer provenance must satisfy the specified quality gate.'+hid);continue
        h=byhyp[hid]
        if h['novelty_status']=='REJECTED_BY_PRIOR_ART':hard.append('Source state and independent reviewer provenance must satisfy the specified quality gate.'+hid)
        agents=reviews[hid]
        roles={a['role'] for a in agents}
        if not {'rce_novelty_sol','rce_skeptic_astra'}.issubset(roles):
            hard.append('Source state and independent reviewer provenance must satisfy the specified quality gate.'+hid)
        if len({a['thread_ref'] for a in agents})<2:hard.append('Source state and independent reviewer provenance must satisfy the specified quality gate.'+hid)
        if any(a['verdict'] in ('REJECT','KNOWN') for a in agents):hard.append('Source state and independent reviewer provenance must satisfy the specified quality gate.'+hid)
        if not experiments[hid]:hard.append('Source state and independent reviewer provenance must satisfy the specified quality gate.'+hid)
        try:
            linked=json.loads(h['linked_claims'])
            if not linked or any(not any(c['claim_id']==x for c in data['claims']) for x in linked):
                hard.append('Source state and independent reviewer provenance must satisfy the specified quality gate.'+hid)
        except Exception:hard.append('Research evidence and workflow notes (topic_to_plan.quality). Use original source evidence; keep frozen constraints and independent quality gates.'+hid)
        if h['novelty_status']!='NOVELTY_UNVERIFIED':
            soft.append('Source state and independent reviewer provenance must satisfy the specified quality gate.'+hid)
    # We do not allow this system to run experimental code; users own all experiments.
    stats['experiments_executed_by_pipeline']=0
    stats['user_experiment_execution_required']=True
    return {'status':('NO_VIABLE_RESEARCH_METHOD' if null_route else 'FINAL_PLAN_READY_FOR_USER') if not hard else 'BLOCKED_INSUFFICIENT_SCIENTIFIC_EVIDENCE',
            'hard_blockers':hard,'cautions':soft,'stats':stats,
            'non_experimental_scope':True,
            'scientific_limit':'Bibliographic metadata, source-page quote matching and agent judgments are distinct epistemic levels. No unperformed simulation, training or experiment provides scientific measurements; verify figures and prior art independently.'}


def finalize(ws:pathlib.Path,*,allow_incomplete_discovery:bool=False)->dict:
    ws=ws.expanduser().resolve()
    report=quality(ws,allow_incomplete_discovery=allow_incomplete_discovery)
    store.write(here(ws)/'final_gate.json',report)
    if report['status'] not in ('FINAL_PLAN_READY_FOR_USER','NO_VIABLE_RESEARCH_METHOD'):
        lines=['Source state and independent reviewer provenance must satisfy the specified quality gate.','','Source state and independent reviewer provenance must satisfy the specified quality gate.','','Source state and independent reviewer provenance must satisfy the specified quality gate.','']
        lines.extend('- '+str(x) for x in report['hard_blockers'])
        if report.get('cautions'):
            lines.extend(['','Source state and independent reviewer provenance must satisfy the specified quality gate.',''])
            lines.extend('- '+str(x) for x in report['cautions'])
        lines.extend(['','Source state and independent reviewer provenance must satisfy the specified quality gate.'])
        notice=here(ws)/'evidence_shortfalls.md'
        store.textwrite(notice,'\n'.join(lines)+'\n')
        return {'status':report['status'],'blocking_reasons':report['hard_blockers'],
                'gate_file':str(here(ws)/'final_gate.json'),
                'evidence_shortfalls_report':str(notice),'no_false_final_report':True}
    if contract(ws).get('route_contract_version',1)>=2:
        import route_convergence
        route_convergence.render(ws)
    r=ENGINE.report(ws)
    if report['status']=='NO_VIABLE_RESEARCH_METHOD':
        return {'status':report['status'],'final_report':str(store.root(ws)/'research_discovery_package/final_route_and_method.md'),
                'no_experiment_executed':True,'no_viable_method':True,'quality_gate':str(here(ws)/'final_gate.json')}
    venue=venues(ws)
    with store.connect(ws) as db:
        qs=[dict(x) for x in db.execute('SELECT * FROM questions ORDER BY impact*uncertainty DESC')]
        hs=[dict(x) for x in db.execute('SELECT * FROM hypotheses ORDER BY created_at')]
        es=[dict(x) for x in db.execute('SELECT * FROM experiments ORDER BY created_at')]
        ds=[dict(x) for x in db.execute('SELECT * FROM decisions ORDER BY created_at')]
        reviews=[dict(x) for x in db.execute('SELECT * FROM assessments ORDER BY hypothesis_id')]
    out=store.root(ws)/'research_discovery_package'
    note = [
        '# Source-grounded scientific questions, candidate methods and experimental plans', '',
        '## Confirmed research topic', '', contract(ws)['topic'], '',
        '## Bibliographic and original-source coverage', '',
        f"- Bibliographic records: {report['stats']['knowledge_counts']['works']}; readable full-text sources: {report['stats']['knowledge_counts']['sources']}; page-anchored source quotations: {report['stats']['knowledge_counts']['claims']}.",
        f"- Publication venue profile: `{pathlib.Path(venue.get('report','')).name}` (observed venue metadata, not an official item-level rating).",
        '- The target of 250 unique bibliographic records does not establish 250 full-text readings.',
        f"- Annual authority check: {official_venues.status(ws).get('status')}. No individual JCR/CCF category is claimed without authorized entry-level evidence. CAS partitions after 2025 are not available as new releases.", '',
        '## Research questions (unverified until substantive evidence review)', '',
    ]
    for q in qs[:60]:
        note.append(f"- `{q['question_id']}`: {q['question']} (importance={q['impact']}; uncertainty={q['uncertainty']}).")
    note += ['', '## Candidate research hypotheses, methods and detailed experiment plans (not executed)', '']
    byh = {h['hypothesis_id']: h for h in hs}
    byxp = defaultdict(list)
    for xp in es:
        byxp[xp['hypothesis_id']].append(xp)
    for d in ds:
        h = byh[d['hypothesis_id']]
        note.extend([
            f"### {h['hypothesis_id']}: {h['statement']}",
            '- Proposed mechanism: '+h['mechanism'],
            '- Falsifiable prediction: '+h['prediction'],
            '- Explicit rejection criterion: '+h['falsifier'],
            '- Linked source-anchored evidence IDs: '+h['linked_claims'],
            '- Nearest identified prior-work IDs: '+h['nearest_works'],
            '- Novelty assessment: '+h['novelty_status']+' (not a proof of originality)',
            '- Recommended research direction: '+d['recommendation'],
            '- Remaining scientific risks: '+d['risks'],
        ])
        for xp in byxp[d['hypothesis_id']]:
            note.extend([
                '- PLANNED_NOT_EXECUTED experimental design: '+xp['plan'],
                '- Fair comparison baselines: '+xp['baselines'],
                '- Planned metrics and evaluation protocol: '+xp['metrics'],
                '- Rejection condition: '+xp['reject_condition'],
                '- Intended data, resources and estimated budget: '+xp['resource'],
            ])
        note.append('')
    note += [
        '## Execution boundary', '',
        '**DESIGN ONLY. No simulation, training, testing or experimental execution has been performed by this Skill.**',
        'All proposed experiments, ablations and measurements must be implemented and validated by the researcher.', '',
        '## Linked evidence and quality-gate annexes', '',
        '- `research_landscape.md`', '- `method_evidence_matrix.md`',
        '- `research_gap_report.md`', '- `candidate_methods.md`',
        '- `experiment_blueprint.md`', '- `final_research_recommendation.md`',
        '- `../topic_to_plan/venue_landscape.md`', '- `../topic_to_plan/final_gate.json`',
        '- `verified_bibliography.md`', '- `closest_prior_art.md`', '',
        '**Epistemic limit:** A favorable panel verdict is not experimental validation or proof of methodological novelty.',
    ]
    path=out/'topic_to_experiment_plan.md'
    store.textwrite(path,'\n'.join(note)+'\n')
    # Separate bibliography annex: contains only identities that exist in the
    # source database, with transparent bibliography/fulltext distinction.
    with store.connect(ws) as c:
        papers=[dict(x) for x in c.execute('''SELECT w.work_id,w.title,w.year,w.venue,w.doi,w.url,w.category,
                      w.source_status,COUNT(DISTINCT cl.claim_id) AS evidence_claims
                      FROM works w LEFT JOIN claims cl ON cl.work_id=w.work_id
                      GROUP BY w.work_id ORDER BY CASE w.category WHEN 'core' THEN 0 WHEN 'related' THEN 1 ELSE 2 END,
                      evidence_claims DESC,w.year DESC LIMIT 600''')]
    references = ['# Source-verified bibliography and evidence coverage', '',
                  '> A bibliographic record alone is not full-text evidence. Only verified, readable full text with authentic quotations supports method-level analysis.', '',
                  '| Paper | Year | Venue | Category | Full-text status | Source-anchored quotes | DOI / OpenAlex |',
                  '|---|---:|---|---|---|---:|---|']
    for w in papers:
        safe=lambda x:str(x or '').replace('|','\\|').replace('\n',' ')[:190]
        doi='https://doi.org/'+w['doi'] if w['doi'] else w['work_id']
        references.append(f"|{safe(w['title'])}|{w['year'] or ''}|{safe(w['venue'])}|{w['category']}|{w['source_status']}|{w['evidence_claims']}|{doi}|")
    store.textwrite(out/'verified_bibliography.md','\n'.join(references)+'\n')
    import prior_art as pa
    closest=pa.context_for_review(ws)
    prior_lines = ['# Nearest identified prior art: bibliographic leads only', '',
                   'Search results are real OpenAlex identity records, not proof of method equivalence or complete full-text review.', '',
                   '| Hypothesis | Paper ID | Paper title | Year | Venue | Source status | Search-match count |',
                   '|---|---|---|---:|---|---|---:|']
    for x in closest:
        escape=lambda a:str(a or '').replace('|','\\|').replace('\n',' ')
        prior_lines.append(f"|{x['hypothesis_id']}|{x['work_id']}|{escape(x['title'])}|{x['year'] or ''}|{escape(x['venue'])}|{x['source_status']}|{x['matched_search_queries']}|")
    store.textwrite(out/'closest_prior_art.md','\n'.join(prior_lines)+'\n')
    return {'status':'FINAL_PLAN_READY_FOR_USER','final_report':str(path),'venue_profile':venue.get('report'),
            'original_reports':r.get('package_dir'),'no_experiment_executed':True,
            'hypotheses':len(hs),'experiment_plans':len(es),'quality_gate':str(here(ws)/'final_gate.json'),
            'cautions':report['cautions']}


def drive(ws:pathlib.Path,*,max_steps:int=6,online:bool=False,download:bool=False,
          prepare_native:bool=False,allow_incomplete_discovery:bool=False)->dict:
    """Bounded on-demand progress; no background agent/experimental computation."""
    ws=ws.expanduser().resolve()
    if not 1<=max_steps<=20:raise ValueError('Signed task, stage, commit receipt or report provenance check failed at topic_to_plan.drive (check 613). Resume only from a verified state.')
    steps=[]
    for _ in range(max_steps):
        todo=next_action(ws,allow_incomplete_discovery=allow_incomplete_discovery)
        what=todo['status']
        if what=='NEEDS_AUTHORIZED_CORE_PDF_DOWNLOAD' and online and download:
            operation=V5.obtain_fulltexts(ws,online=True,category='core',limit=3)
            # Synchronization of downloaded files is a separate deterministic step.
            steps.append({'step':what,'result':operation})
            break   # bound network effects and model cost to one invocation
        if what=='NEEDS_PRIOR_ART_SEARCH' and online:
            operation=prior_art.search(ws,online=True,max_requests=2)
            steps.append({'step':what,'result':operation})
            break
        if what=='NEEDS_PRIOR_ART_OA_DOWNLOAD' and online and download:
            operation=prior_art.download(ws,online=True,limit=2)
            steps.append({'step':what,'result':operation})
            break
        if what=='READY_FOR_FINAL_RESEARCH_AUDIT':
            result=finalize(ws,allow_incomplete_discovery=allow_incomplete_discovery)
            steps.append({'step':what,'result':result})
            return {'status':result['status'],'performed':steps,'next_action':result,
                    'experimental_execution':False}
        if what.startswith('NEEDS_NATIVE_TOPIC'):
            return {'status':'PAUSED_FOR_REAL_NATIVE_TOPIC_AGENT','next_action':todo,'performed':steps}
        allowed={ 'NEEDS_V5_EVIDENCE_SYNC','NEEDS_AUTO_EVIDENCE_SYNC',
                  'READY_FOR_ORIGINAL_V44_SELECT','READY_TO_SEAL_ORIGINAL_V44',
                  'NEEDS_RCE_INIT','READY_FOR_RCE_CYCLE','PREPARE_NATIVE_READER_TASK',
                  'PREPARE_RCE_NATIVE_TASK','NEEDS_ORIGINAL_V44_INGEST',
                  'NEEDS_QUESTION_DRIVEN_SEARCH','NEEDS_DISCOVERY'}
        if what in allowed:
            # Reuse v6.1 orchestration; it already reserves actual shared local quota.
            result=wf.run(ws,max_steps=1,allow_network=online,
                    allow_incomplete_discovery=allow_incomplete_discovery,
                    prepare_native=prepare_native,start_research_cycle=True,
                    allow_ingest=True)
            steps.append({'step':what,'result':result})
            if result['status'].startswith(('PAUSED','BLOCKED')):break
            if not result.get('performed'):break
            if what in ('NEEDS_DISCOVERY','NEEDS_QUESTION_DRIVEN_SEARCH'):
                venues(ws);break  # network bound
        else:break
    return {'status':'PAUSED_FOR_EXTERNAL_ACTION_OR_LIMIT','performed':steps,
            'next_action':next_action(ws,allow_incomplete_discovery=allow_incomplete_discovery),
            'model_agents_spawned_by_python':0,'experiments_executed':0}


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description='Inspect the signed checkpoint, verify the original full-text evidence and reviewer receipts, then continue only the stage justified by a substantive evidence gap and available quota.')
    commands=p.add_subparsers(dest='op',required=True)
    for name in ('start','commit','venues','next','auto','quality','finalize','status','prior-art-plan','prior-art-search','prior-art-download'):
        s=commands.add_parser(name);s.add_argument('--workspace',type=pathlib.Path,required=True)
        if name=='start':s.add_argument('--topic',required=True)
        if name in ('prior-art-search','prior-art-download'):
            s.add_argument('--online',action='store_true')
            if name=='prior-art-search':s.add_argument('--max-requests',type=int,default=2)
            else:s.add_argument('--limit',type=int,default=2)
        if name=='commit':s.add_argument('--file',type=pathlib.Path,required=True)
        if name in ('next','auto','quality','finalize'):s.add_argument('--allow-incomplete-discovery',action='store_true')
        if name=='auto':
            s.add_argument('--max-steps',type=int,default=6)
            s.add_argument('--online',action='store_true')
            s.add_argument('--download',action='store_true')
            s.add_argument('--prepare-native',action='store_true')
    x=p.parse_args(argv);ws=x.workspace.expanduser().resolve()
    try:
        if x.op not in ('status',):
            # Once-per-calendar-year official-only public website check.
            # On failure the honest partial cache is kept; this never asserts a
            # subscription-only JCR quartile or reanimates discontinued CAS data.
            official_venues.check(ws,online=True)
        if x.op=='start':o=start(ws,x.topic)
        elif x.op=='commit':o=commit(ws,x.file)
        elif x.op=='venues':o=venues(ws)
        elif x.op=='next':o=next_action(ws,allow_incomplete_discovery=x.allow_incomplete_discovery)
        elif x.op=='auto':o=drive(ws,max_steps=x.max_steps,online=x.online,download=x.download,
                                prepare_native=x.prepare_native,allow_incomplete_discovery=x.allow_incomplete_discovery)
        elif x.op=='quality':o=quality(ws,allow_incomplete_discovery=x.allow_incomplete_discovery)
        elif x.op=='finalize':o=finalize(ws,allow_incomplete_discovery=x.allow_incomplete_discovery)
        elif x.op=='prior-art-plan':o=prior_art.plan(ws)
        elif x.op=='prior-art-search':o=prior_art.search(ws,online=x.online,max_requests=x.max_requests)
        elif x.op=='prior-art-download':o=prior_art.download(ws,online=x.online,limit=x.limit)
        else:
            record=contract(ws)
            o={'status':'TOPIC_CONFIG_COMMITTED' if record['state']=='TOPIC_CONFIG_COMMITTED' else record['state'],
               'topic':record['topic'],'as_of_date':record.get('as_of_date'),
               'next_action':next_action(ws) if record['state']=='TOPIC_CONFIG_COMMITTED' else 'await native topic interpretation'}
        print(json.dumps(o,ensure_ascii=False,indent=2,default=str))
        return 0 if o.get('status') not in ('BLOCKED_INSUFFICIENT_SCIENTIFIC_EVIDENCE','BLOCKED') else 2
    except (ValueError,RuntimeError,OSError,KeyError,TypeError,ImportError) as e:
        print(json.dumps({'status':'BLOCKED','reason':str(e)[:1200]},ensure_ascii=False),file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
