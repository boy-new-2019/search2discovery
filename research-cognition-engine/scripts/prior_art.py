#!/usr/bin/env python3
"""Hypothesis-specific falsification search, OpenAlex metadata only.

Follows v6.2 topic contract; requires real reviewed English search queries
and explicit per-call network authorization. Does not claim that a returned
bibliography disproves/proves novelty; actual source reading remains mandatory.
"""
from __future__ import annotations
import datetime as dt
import json
import pathlib
import re
from typing import Any

import store
import suite

V5=suite.discovery
MAX_ATTEMPTS=60
MAX_PER_RUN=4


def root(ws:pathlib.Path)->pathlib.Path:
    return store.root(ws)/'prior_art_search'


def init_db(ws:pathlib.Path)->None:
    with store.connect(ws) as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS prior_art_queries (
            query_id TEXT PRIMARY KEY, hypothesis_id TEXT NOT NULL REFERENCES hypotheses(hypothesis_id),
            query TEXT NOT NULL, band TEXT NOT NULL, start_date TEXT NOT NULL,end_date TEXT NOT NULL,
            query_plan_sha TEXT NOT NULL, status TEXT NOT NULL, raw_count INTEGER NOT NULL,
            created_at TEXT NOT NULL, completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS prior_art_links (
            hypothesis_id TEXT NOT NULL REFERENCES hypotheses(hypothesis_id),
            work_id TEXT NOT NULL REFERENCES works(work_id),
            query_id TEXT NOT NULL REFERENCES prior_art_queries(query_id),
            source_openalex_id TEXT NOT NULL, raw_bibliography_sha TEXT NOT NULL,
            created_at TEXT NOT NULL, PRIMARY KEY(hypothesis_id,work_id,query_id)
        );
        CREATE TABLE IF NOT EXISTS prior_art_metadata (
            work_id TEXT PRIMARY KEY REFERENCES works(work_id),
            json_text TEXT NOT NULL, raw_bibliography_sha TEXT NOT NULL, recorded_at TEXT NOT NULL
        );
        ''')


def _goal_sha(ws:pathlib.Path)->str:
    f=ws/'goal.md'
    if not f.is_file():raise ValueError('Frozen research topic or signed research contract mismatch at prior_art._goal_sha (check 52). Reconfirm boundaries; do not overwrite approved work.')
    return store.hashbytes(f.read_bytes())


def _hypotheses(ws:pathlib.Path)->list[dict]:
    with store.connect(ws) as c:
        return [dict(x) for x in c.execute('SELECT hypothesis_id,statement,mechanism,prediction,nearest_works FROM hypotheses ORDER BY hypothesis_id')]


def _hyp_hash(h:dict)->str:
    return store.hashobj({k:h[k] for k in ('hypothesis_id','statement','mechanism','prediction','nearest_works')})


def template(ws:pathlib.Path)->dict:
    ws=ws.expanduser().resolve();init_db(ws)
    hs=_hypotheses(ws)
    if not hs:return {'status':'NO_HYPOTHESES_YET','hypotheses':0}
    # Do not auto-generate vaguely translated pseudo-queries from Chinese papers.
    data={'schema_version':1,'goal_sha256':_goal_sha(ws),
          'hypotheses':[{'hypothesis_id':h['hypothesis_id'],'hypothesis_sha':_hyp_hash(h),
                         'hypothesis_statement':h['statement'],
                         'queries':['REPLACE WITH ENGLISH NEAREST PRIOR METHOD SEARCH',
                                    'REPLACE WITH ENGLISH COUNTEREXAMPLE MECHANISM SEARCH']}
                        for h in hs],
          'reviewer_role':'rce_novelty_sol',
          'reviewer_thread_ref':'REPLACE_WITH_REAL_NATIVE_CODEX_THREAD',
          'caution':'Bibliographic metadata, source-page quote matching and agent judgments are distinct epistemic levels. No unperformed simulation, training or experiment provides scientific measurements; verify figures and prior art independently.'}
    reviewed=root(ws)/'reviewed_novelty_queries.json'
    if not reviewed.exists():store.write(root(ws)/'review_template.json',data)
    return {'status':'NEEDS_PRIOR_ART_QUERY_REVIEW' if not reviewed.is_file() else 'REVIEWED_QUERY_FILE_PRESENT',
            'template':str(root(ws)/'review_template.json'),
            'reviewed_file':str(reviewed),'hypotheses':len(hs)}


def _validated(ws:pathlib.Path)->dict:
    file=root(ws)/'reviewed_novelty_queries.json'
    if not file.is_file():raise ValueError('Source path, lawful access or network permission check failed at prior_art._validated (check 88). Do not bypass paywalls or source integrity checks.')
    data=store.read(file)
    if data.get('schema_version')!=1 or data.get('goal_sha256')!=_goal_sha(ws):
        raise ValueError('Frozen research topic or signed research contract mismatch at prior_art._validated (check 91). Reconfirm boundaries; do not overwrite approved work.')
    if data.get('reviewer_role')!='rce_novelty_sol' or not isinstance(data.get('reviewer_thread_ref'),str) or len(data['reviewer_thread_ref'])<6 or 'REPLACE' in data['reviewer_thread_ref'].upper():
        raise ValueError('Independent native research-agent identity or reviewer evidence failed validation at prior_art._validated (check 93).')
    actual={h['hypothesis_id']:h for h in _hypotheses(ws)}
    records={row.get('hypothesis_id'):row for row in data.get('hypotheses',[]) if isinstance(row,dict)}
    if set(actual)!=set(records):raise ValueError('Input, evidence or workflow invariant failed at prior_art._validated (check 96); inspect the signed task record and original source.')
    for hid,h in actual.items():
        x=records[hid]
        if x.get('hypothesis_sha')!=_hyp_hash(h):raise ValueError('Input, evidence or workflow invariant failed at prior_art._validated (check 99); inspect the signed task record and original source.'+hid)
        xs=x.get('queries')
        if not isinstance(xs,list) or not 2<=len(xs)<=4 or len(set(xs))!=len(xs):
            raise ValueError('Input, evidence or workflow invariant failed at prior_art._validated (check 102); inspect the signed task record and original source.')
        for q in xs:
            if not isinstance(q,str) or not 10<=len(q)<=190 or not re.search('[a-zA-Z]{3,}',q) or 'REPLACE' in q.upper() or any(ord(c)<32 for c in q):
                raise ValueError('Input, evidence or workflow invariant failed at prior_art._validated (check 105); inspect the signed task record and original source.')
    return data


def plan(ws:pathlib.Path)->dict:
    ws=ws.expanduser().resolve();init_db(ws)
    marker=template(ws)
    if marker['status']=='NO_HYPOTHESES_YET':return marker
    if marker['status']=='NEEDS_PRIOR_ART_QUERY_REVIEW':return marker
    data=_validated(ws)
    rec=store.read(store.root(ws)/'topic_to_plan'/'contract.json')
    if rec['goal_sha256']!=_goal_sha(ws):raise ValueError('Frozen research topic or signed research contract mismatch at prior_art.plan (check 116). Reconfirm boundaries; do not overwrite approved work.')
    conf=V5.config(ws)
    asof=dt.date.fromisoformat(rec['as_of_date'])
    windows=V5.windows(conf,asof)
    # Only recent-first bounded bands; foundational search may follow on request.
    jobs=[]
    plan_sha=store.hashobj({'goal':data['goal_sha256'],'file':data})
    with store.connect(ws) as c:
        completed={x[0] for x in c.execute("SELECT query_id FROM prior_art_queries WHERE status='COMPLETE'")}
    for band,start,end in windows:
        for x in data['hypotheses']:
            for q in x['queries']:
                key='PA-'+store.hashobj({'hyp':x['hypothesis_id'],'q':q,'band':band,'since':start,'until':end,'plan_sha':plan_sha})[:18]
                jobs.append({'query_id':key,'hypothesis_id':x['hypothesis_id'],'query':q,
                             'band':band,'start_date':start,'end_date':end,'plan_sha':plan_sha,
                             'completed':key in completed})
    out={'status':'PRIOR_ART_PLAN_READY','jobs':jobs,'total_queries':len(jobs),
         'completed_queries':sum(x['completed'] for x in jobs),
         'pending_queries':sum(not x['completed'] for x in jobs),
         'no_scientific_novelty_attestation':True}
    store.write(root(ws)/'plan.json',out)
    return out


def coverage(ws:pathlib.Path)->dict:
    ws=ws.expanduser().resolve();init_db(ws)
    hypotheses=_hypotheses(ws)
    with store.connect(ws) as c:
        counts={h['hypothesis_id']:{'completed_recent_queries':0,'completed_expansion_queries':0,'registered_prior_works':0} for h in hypotheses}
        for r in c.execute("SELECT hypothesis_id,band,COUNT(*) AS n FROM prior_art_queries WHERE status='COMPLETE' GROUP BY hypothesis_id,band"):
            key='completed_recent_queries' if r['band']=='RECENT_3Y' else 'completed_expansion_queries'
            counts[r['hypothesis_id']][key]+=r['n']
        for x in c.execute('SELECT hypothesis_id,COUNT(DISTINCT work_id) AS n FROM prior_art_links GROUP BY hypothesis_id'):
            counts[x['hypothesis_id']]['registered_prior_works']=x['n']
    missing_recent=[h for h,x in counts.items() if x['completed_recent_queries']<2]
    missing_prior=[h for h,x in counts.items() if x['registered_prior_works']==0]
    if not hypotheses:status='NO_HYPOTHESES_YET'
    elif missing_recent:status='PRIOR_ART_SEARCH_INCOMPLETE'
    elif not missing_prior:status='PRIOR_ART_RECENT_SEARCH_DONE'
    else:
        # If no close work is returned in the last 3 years, keep searching
        # older works rather than treating zero hits as proof of novelty.
        with store.connect(ws) as c:
            present={h: c.execute("SELECT COUNT(*) FROM prior_art_queries WHERE hypothesis_id=? AND status='COMPLETE' AND band!='RECENT_3Y'",(h,)).fetchone()[0]
                     for h in missing_prior}
        status='PRIOR_ART_EXPANSION_REQUIRED' if any(present[h]<2 for h in missing_prior) else 'PRIOR_ART_NO_MATCHES_REQUIRES_MANUAL_EVIDENCE'
    return {'status':status,'hypotheses_missing_two_recent_queries':missing_recent,
            'hypotheses_without_found_prior_art':missing_prior,'counts':counts,
            'caution':'Bibliographic metadata, source-page quote matching and agent judgments are distinct epistemic levels. No unperformed simulation, training or experiment provides scientific measurements; verify figures and prior art independently.'}


def search(ws:pathlib.Path,*,online:bool=False,max_requests:int=2,fetcher:Any=None)->dict:
    if not online:raise ValueError('Source path, lawful access or network permission check failed at prior_art.search (check 168). Do not bypass paywalls or source integrity checks.')
    if not 1<=max_requests<=MAX_PER_RUN:raise ValueError('Source path, lawful access or network permission check failed at prior_art.search (check 169). Do not bypass paywalls or source integrity checks.')
    p=plan(ws)
    if p['status']!='PRIOR_ART_PLAN_READY':return p
    with store.connect(ws) as c:
        attempted=c.execute('SELECT COUNT(*) FROM prior_art_queries').fetchone()[0]
    if attempted>=MAX_ATTEMPTS:return {'status':'PRIOR_ART_REQUEST_LIMIT','requests':0,'max_lifetime':MAX_ATTEMPTS}
    cfg=V5.config(ws);api=fetcher or V5.OpenAlex(cfg)
    executed=0;created=0;linked=0;errors=[]
    for task in p['jobs']:
        if task['completed'] or executed>=min(max_requests,MAX_ATTEMPTS-attempted):continue
        with store.connect(ws) as c:
            if c.execute('SELECT 1 FROM prior_art_queries WHERE query_id=?',(task['query_id'],)).fetchone():continue
            c.execute('''INSERT INTO prior_art_queries(query_id,hypothesis_id,query,band,start_date,end_date,query_plan_sha,status,raw_count,created_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?)''',
                      (task['query_id'],task['hypothesis_id'],task['query'],task['band'],
                       task['start_date'],task['end_date'],task['plan_sha'],'STARTED',0,store.utc()))
        executed+=1
        try:raws,_=api.query(task['query'],task['start_date'],task['end_date'],1)
        except Exception as ex:
            errors.append({'query_id':task['query_id'],'error':str(ex)[:180]})
            with store.connect(ws) as c:
                c.execute("UPDATE prior_art_queries SET status='FAILED',completed_at=? WHERE query_id=?",(store.utc(),task['query_id']))
            continue
        works=[]
        for r in raws:
            w=V5.work_normalized(r,'related','',task['query'])
            if w and w['publication_date']<=task['end_date'] and w['publication_date']>=task['start_date']:
                works.append(w)
        with store.connect(ws) as c:
            for w in works:
                wid=w['id']
                exist=c.execute('SELECT work_id FROM works WHERE work_id=?',(wid,)).fetchone()
                if not exist:
                    alt=None
                    if w.get('doi'):alt=c.execute("SELECT work_id FROM works WHERE doi=? AND doi!=''",(w['doi'],)).fetchone()
                    if not alt:alt=c.execute('SELECT work_id FROM works WHERE lower(title)=lower(?) LIMIT 1',(w['title'],)).fetchone()
                    if alt:wid=alt['work_id']
                    else:
                        c.execute("INSERT INTO works(work_id,title,category,doi,year,venue,url,record_sha,source_status) VALUES (?,?,?,?,?,?,?,?,?)",
                                  (wid,w['title'],'prior_art_candidate',w.get('doi',''),w['year'],w['venue'],w['bibliographic_link'],store.hashobj(w),'BIB_ONLY'))
                        created+=1
                c.execute('INSERT OR IGNORE INTO prior_art_metadata VALUES(?,?,?,?)',
                          (wid,store.dump(w),store.hashobj(w),store.utc()))
                found=c.execute('SELECT 1 FROM prior_art_links WHERE hypothesis_id=? AND work_id=? AND query_id=?',
                                (task['hypothesis_id'],wid,task['query_id'])).fetchone()
                if not found:
                    c.execute('INSERT INTO prior_art_links VALUES(?,?,?,?,?,?)',
                              (task['hypothesis_id'],wid,task['query_id'],w['id'],store.hashobj(w),store.utc()))
                    linked+=1
            c.execute("UPDATE prior_art_queries SET status='COMPLETE',raw_count=?,completed_at=? WHERE query_id=?",
                      (len(raws),store.utc(),task['query_id']))
            store.event(c,'PRIOR_ART_METADATA_SEARCH',{'hypothesis_id':task['hypothesis_id'],
                         'query_id':task['query_id'],'raw_results':len(raws),'registered':len(works),'metadata_only':True})
    return {'status':'PRIOR_ART_SEARCH_ERRORS' if errors else 'PRIOR_ART_SEARCH_BATCH_DONE',
            'requests':executed,'new_prior_art_bibliography':created,'hypothesis_links':linked,
            'errors':errors,'coverage':coverage(ws),
            'truth_boundary':'OpenAlex search is a bibliography lead, not proof of novelty or scientific effectiveness.'}


def context_for_review(ws:pathlib.Path)->list[dict]:
    init_db(ws)
    with store.connect(ws) as c:
        rows=c.execute('''SELECT p.hypothesis_id,w.work_id,w.title,w.category,w.year,w.venue,w.source_status,
            COUNT(DISTINCT p.query_id) AS matched_search_queries
            FROM prior_art_links p JOIN works w ON w.work_id=p.work_id
            GROUP BY p.hypothesis_id,w.work_id ORDER BY matched_search_queries DESC,w.year DESC LIMIT 80''').fetchall()
    return [dict(x) for x in rows]


def downloadable(ws:pathlib.Path)->dict:
    """Only already audited OpenAlex best OA PDF pointers; not a paywall bypass."""
    init_db(ws)
    with store.connect(ws) as c:
        rows=c.execute('''SELECT m.work_id,m.json_text,w.source_status
            FROM prior_art_metadata m JOIN works w ON w.work_id=m.work_id
            ORDER BY w.year DESC,w.work_id LIMIT 250''').fetchall()
    eligible=[]
    for row in rows:
        if row['source_status']=='TEXT_AVAILABLE':continue
        item=json.loads(row['json_text']);url=item.get('oa_pdf_url') or ''
        if url and V5.safe_url(url):eligible.append({'work_id':row['work_id'],'url':url})
    return {'status':'PRIOR_ART_OA_AVAILABLE' if eligible else 'NO_ADDITIONAL_TRUSTED_OA',
            'count':len(eligible),'work_ids':[x['work_id'] for x in eligible[:12]],
            'fulltext_not_implied_by_metadata':True}


def download(ws:pathlib.Path,*,online:bool=False,limit:int=2,download_fn:Any=None)->dict:
    if not online:raise ValueError('Source path, lawful access or network permission check failed at prior_art.download (check 256). Do not bypass paywalls or source integrity checks.')
    if not 1<=limit<=8:raise ValueError('Frozen research topic or signed research contract mismatch at prior_art.download (check 257). Reconfirm boundaries; do not overwrite approved work.')
    ws=ws.expanduser().resolve();_goal_sha(ws);init_db(ws)
    with store.connect(ws) as c:
        rows=c.execute('''SELECT m.work_id,m.json_text,w.source_status
             FROM prior_art_metadata m JOIN works w ON w.work_id=m.work_id
             ORDER BY w.year DESC,w.work_id LIMIT 250''').fetchall()
    cfg=V5.config(ws)
    fetch=download_fn or V5.download_pdf
    finished=[];failures=[];attempts=0
    for row in rows:
        if attempts>=limit:break
        wid=row['work_id']
        if row['source_status']=='TEXT_AVAILABLE':continue
        meta=json.loads(row['json_text']);pdf=meta.get('oa_pdf_url') or ''
        match=re.fullmatch(r'https://openalex\.org/(W\d+)',meta.get('id') or '')
        if not pdf or not match or not V5.safe_url(pdf):continue
        attempts+=1
        dst=root(ws)/'source_pdf'/f'prior_{match.group(1)}.pdf'
        if dst.exists():
            with store.connect(ws) as c:
                registered=c.execute('SELECT file_sha FROM sources WHERE work_id=? AND file_path=?',(wid,str(dst.resolve()))).fetchone()
            if registered and store.hashbytes(dst.read_bytes())==registered['file_sha']:continue
            failures.append({'work_id':wid,'reason':'Source state and independent reviewer provenance must satisfy the specified quality gate.'})
            continue
        try:
            fetch(pdf,dst,cfg['retrieval']['max_pdf_size_mb'],cfg['retrieval']['min_extractable_pdf_chars'])
            result=store.import_source(ws,wid,dst)
            with store.connect(ws) as c:
                store.event(c,'PRIOR_ART_OA_TEXT_READY',{'work_id':wid,'url':pdf,
                              'sha256':result['original_sha256'],'source_id':result['source_id']})
            finished.append({'work_id':wid,'source_id':result['source_id'],
                             'sha256':result['original_sha256'],'path':str(dst)})
        except (ValueError,RuntimeError,OSError) as ex:
            failures.append({'work_id':wid,'reason':str(ex)[:200]})
    return {'status':'PRIOR_ART_DOWNLOAD_PARTIAL' if failures else 'PRIOR_ART_DOWNLOAD_BATCH_DONE',
            'attempted':attempts,'downloaded':finished,'failed':failures,
            'source_limit':'Bibliographic metadata, source-page quote matching and agent judgments are distinct epistemic levels. No unperformed simulation, training or experiment provides scientific measurements; verify figures and prior art independently.'}
