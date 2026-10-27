#!/usr/bin/env python3
"""v6.1 research-question -> auditable OpenAlex search -> linked bibliographic leads.

Scientific questions are not assumed true. Supplemental records never modify the
v5 50/150/50 disjoint catalogue and never become full-text evidence by search.
No model calls, network only via explicit caller authorization.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
SKILLS = HERE.parents[1]
V5 = SKILLS / 'paper-discovery-preflight' / 'scripts'
if str(V5) not in sys.path: sys.path.insert(0, str(V5))
import paper_discovery as disc
import store
import engine

STOP = frozenset(('this','that','when','what','which','should','could','would','under','with',
                  'from','into','about','where','why','how','does','have','been','being',
                  'there','their','they','them','are','and','the','for','among','between',
                  'versus','using','used','study','model','models','methods','research',
                  'system','systems','effect','effects','different','based','does',
                  'compare','compared','possible','approach','approaches','such'))
SCHEMA = 1
MAX_QUERIES_TOTAL = 80  # conservative cap per research project, no silent override
MAX_PER_INVOCATION = 8


def root(ws:pathlib.Path)->pathlib.Path:
    return store.root(ws) / 'question_retrieval'


def _sha(x:Any)->str: return store.hashobj(x)


def db_init(ws:pathlib.Path)->None:
    with store.connect(ws) as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS question_queries (
            query_id TEXT PRIMARY KEY, question_id TEXT NOT NULL REFERENCES questions(question_id),
            question_sha TEXT NOT NULL, goal_sha TEXT NOT NULL,
            query TEXT NOT NULL, window_name TEXT NOT NULL, start_date TEXT NOT NULL,
            end_date TEXT NOT NULL, status TEXT NOT NULL, started_at TEXT NOT NULL,
            completed_at TEXT, result_count INTEGER NOT NULL DEFAULT 0, failure TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS question_papers (
            question_id TEXT NOT NULL REFERENCES questions(question_id),
            work_id TEXT NOT NULL REFERENCES works(work_id),
            query_id TEXT NOT NULL REFERENCES question_queries(query_id),
            search_openalex_id TEXT NOT NULL, recorded_at TEXT NOT NULL,
            PRIMARY KEY (question_id, work_id, query_id)
        );
        CREATE TABLE IF NOT EXISTS question_query_attempts (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            query_id TEXT NOT NULL,
            attempted_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'STARTED'
        );
        CREATE TABLE IF NOT EXISTS question_metadata (
            work_id TEXT PRIMARY KEY REFERENCES works(work_id),
            metadata_json TEXT NOT NULL, metadata_sha TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        );
        ''')


def _goal_sha(ws:pathlib.Path)->str:
    file=ws/'goal.md'
    if not file.is_file() or len(file.read_text('utf-8').strip())<15:
        raise ValueError('Frozen research topic or signed research contract mismatch at question_retrieval._goal_sha (check 78). Reconfirm boundaries; do not overwrite approved work.')
    digest=store.hashbytes(file.read_bytes())
    if engine.statefile(ws).is_file() and engine.get_state(ws)['macro_goal_sha256']!=digest:
        raise ValueError('Frozen research topic or signed research contract mismatch at question_retrieval._goal_sha (check 81). Reconfirm boundaries; do not overwrite approved work.')
    return digest


def _tokens(s:str)->list[str]:
    terms=re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}",s.lower())
    return list(dict.fromkeys(x for x in terms if x not in STOP and len(x)<=48))


def _questions(ws:pathlib.Path,max_questions:int=6)->list[dict]:
    with store.connect(ws) as c:
        rows=c.execute('''SELECT q.question_id,q.question,q.domain,q.impact,q.uncertainty,q.status,
          (SELECT COUNT(*) FROM question_papers p WHERE p.question_id=q.question_id) AS prior
          FROM questions q
          ORDER BY q.impact*q.uncertainty DESC,q.question_id LIMIT ?''',(max_questions,)).fetchall()
    return [dict(x) for x in rows]


def _reviewed(ws:pathlib.Path)->dict[str,list[str]]:
    file=root(ws)/'reviewed_queries.json'
    if not file.is_file():return {}
    data=store.read(file)
    if not isinstance(data,dict) or data.get('schema_version')!=1 or data.get('goal_sha')!=_goal_sha(ws):
        raise ValueError('Frozen research topic or signed research contract mismatch at question_retrieval._reviewed (check 104). Reconfirm boundaries; do not overwrite approved work.')
    result={}
    questions={x['question_id']:x for x in _questions(ws,1000)}
    for item in data.get('questions',[]):
        qid=item.get('question_id')
        if qid not in questions or item.get('question_sha')!=_sha(questions[qid]['question']):
            raise ValueError('Input, evidence or workflow invariant failed at question_retrieval._reviewed (check 110); inspect the signed task record and original source.')
        queries=item.get('queries')
        if not isinstance(queries,list) or not 1<=len(queries)<=5:
            raise ValueError('Input, evidence or workflow invariant failed at question_retrieval._reviewed (check 113); inspect the signed task record and original source.')
        out=[]
        for text in queries:
            if not isinstance(text,str) or not 5<=len(text.strip())<=180 or any(ord(x)<32 for x in text):
                raise ValueError('Input, evidence or workflow invariant failed at question_retrieval._reviewed (check 117); inspect the signed task record and original source.')
            if 'REPLACE WITH' in text.upper():
                raise ValueError('Source path, lawful access or network permission check failed at question_retrieval._reviewed (check 119). Do not bypass paywalls or source integrity checks.')
            if text not in out:out.append(text)
        result[qid]=out
    return result


def plan(ws:pathlib.Path, *, max_questions:int=6)->dict:
    ws=ws.expanduser().resolve()
    if not 1<=max_questions<=24:raise ValueError('Frozen research topic or signed research contract mismatch at question_retrieval.plan (check 127). Reconfirm boundaries; do not overwrite approved work.')
    gh=_goal_sha(ws)
    db_init(ws)
    cfg=disc.config(ws)
    # Anchor supplemental queries to the already-frozen v5 campaign date,
    # not a floating clock date after midnight during a resumed run.
    statefile=ws/'output'/'discovery_preflight'/'state.json'
    if statefile.is_file():
        frozen_date=store.read(statefile).get('contract',{}).get('as_of_date')
    else:frozen_date=None
    asof=dt.date.fromisoformat(cfg['as_of_date'] or frozen_date) if (cfg.get('as_of_date') or frozen_date) else dt.date.today()
    bands=disc.windows(cfg,asof)
    reviewed=_reviewed(ws)
    rows=_questions(ws,max_questions)
    records=[];pending=[]
    with store.connect(ws) as c:
        completed={x[0] for x in c.execute("SELECT query_id FROM question_queries WHERE status='COMPLETE'")}
    for q in rows:
        qid=q['question_id']
        terms=_tokens(q['question'])
        if qid in reviewed:
            queries=reviewed[qid]
            query_origin='REVIEWED_QUERY_FILE'
        elif len(terms)>=2:
            # Heuristic candidate; never claim LLM semantic verification.
            queries=[' '.join(terms[:min(7,len(terms))])]
            if len(terms)>7:queries.append(' '.join(terms[-6:]))
            query_origin='HEURISTIC_ENGLISH_TOKENS'
        else:
            pending.append({'question_id':qid,'question':q['question'],
                            'reason':'Source state and independent reviewer provenance must satisfy the specified quality gate.',
                            'question_sha':_sha(q['question'])})
            continue
        for band,start,end in bands:
            for text in queries:
                key='QQ-'+_sha({'goal':gh,'question_id':qid,'question':q['question'],
                                 'q':text,'band':band,'from':start,'to':end})[:20]
                records.append({'query_id':key,'question_id':qid,'question':q['question'],
                                'query':text,'query_origin':query_origin,'priority':round(float(q['impact'])*float(q['uncertainty'])/(1+q['prior']),5),
                                'band':band,'start_date':start,'end_date':end,'completed':key in completed,
                                'question_sha':_sha(q['question']),'goal_sha':gh})
    order={name:ix for ix,(name,_,_) in enumerate(bands)}
    records.sort(key=lambda x:(order[x['band']],-x['priority'],x['question_id'],x['query_id']))
    output={'status':'QUERY_REVIEW_REQUIRED' if pending else 'QUESTION_SEARCH_PLAN_READY' if records else 'NO_RESEARCH_QUESTIONS',
            'schema_version':SCHEMA,'goal_sha':gh,'as_of_date':asof.isoformat(),
            'questions_considered':len(rows),'queries':records,'pending_review':pending,
            'completed_queries':sum(x['completed'] for x in records),
            'new_queries':sum(not x['completed'] for x in records),
            'source_truth':'The query is a search heuristic, not a scientific or relevance verdict.',
            'v5_catalogue_untouched':True}
    store.write(root(ws)/'plan.json',output)
    if pending:
        template={'schema_version':1,'goal_sha':gh,
                  'questions':[{'question_id':x['question_id'],'question_sha':x['question_sha'],
                                'queries':['REPLACE WITH VERIFIED ENGLISH RESEARCH QUERY']}
                               for x in pending],
                  'instructions':'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
        store.write(root(ws)/'review_template.json',template)
    return output


def search(ws:pathlib.Path, *, online:bool=False,max_requests:int=4,fetcher:Any=None)->dict:
    if not online:raise ValueError('Network access requires explicit authorization: pass --online only when the user has authorized current scholarly retrieval.')
    if not 1<=max_requests<=MAX_PER_INVOCATION:
        raise ValueError('Source path, lawful access or network permission check failed at question_retrieval.search (check 191). Do not bypass paywalls or source integrity checks.')
    p=plan(ws)
    if not p['queries']:
        return {'status':p['status'],'requests':0,'pending_review':p['pending_review']}
    if fetcher is None and (ws/'source_routing.json').is_file():
        return _multisource_search(ws,p,max_requests)
    cfg=disc.config(ws)
    api=fetcher if fetcher is not None else disc.OpenAlex(cfg,workspace=ws)
    found=[];calls=0;failures=[];newworks=0;relations=0;duplicates=0
    with store.connect(ws) as c:
        usage=c.execute('SELECT COUNT(*) FROM question_query_attempts').fetchone()[0]
    if usage>=MAX_QUERIES_TOTAL:
        return {'status':'QUESTION_REQUEST_LIFETIME_CAP','requests':0,'limit':MAX_QUERIES_TOTAL}
    for task in p['queries']:
        if task['completed']:continue
        if calls>=min(max_requests,MAX_QUERIES_TOTAL-usage):break
        # Reserve each actual API attempt in append-only local budget before
        # connecting; retries and failures count rather than bypassing the cap.
        with store.connect(ws) as c:
            cursor=c.execute('INSERT INTO question_query_attempts(query_id,attempted_at) VALUES(?,?)',
                             (task['query_id'],store.utc()))
            attempt_no=cursor.lastrowid
        # Never cache incomplete success when provider fails.
        try:
            raws,meta=api.query(task['query'],task['start_date'],task['end_date'],1)
        except Exception as ex:
            with store.connect(ws) as c:
                c.execute('UPDATE question_query_attempts SET status=? WHERE seq=?',('ERROR',attempt_no))
                c.execute('''INSERT OR REPLACE INTO question_queries
                            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                          (task['query_id'],task['question_id'],task['question_sha'],task['goal_sha'],
                           task['query'],task['band'],task['start_date'],task['end_date'],
                           'ERROR',store.utc(),None,0,str(ex)[:250]))
                store.event(c,'QUESTION_SEARCH_REQUEST_ERROR',{'query_id':task['query_id'],'error':str(ex)[:250]})
            calls+=1;failures.append({'id':task['query_id'],'reason':str(ex)[:170]})
            continue
        normalized=[]
        for raw in raws:
            w=disc.work_normalized(raw,'related','',task['query'])
            if w and task['start_date']<=w['publication_date']<=task['end_date']:
                normalized.append(w)
        with store.connect(ws) as c:
            c.execute('UPDATE question_query_attempts SET status=? WHERE seq=?',('COMPLETE',attempt_no))
            old=c.execute('SELECT status FROM question_queries WHERE query_id=?',(task['query_id'],)).fetchone()
            if old and old['status']=='COMPLETE':continue
            c.execute('''INSERT OR REPLACE INTO question_queries
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                      (task['query_id'],task['question_id'],task['question_sha'],task['goal_sha'],
                       task['query'],task['band'],task['start_date'],task['end_date'],
                       'COMPLETE',store.utc(),store.utc(),len(raws),''))
            for w in normalized:
                wid=w['id']
                existing=c.execute('SELECT work_id,doi,title FROM works WHERE work_id=?',(wid,)).fetchone()
                if existing:
                    if existing['title'].casefold().strip()!=w['title'].casefold().strip() and existing['doi'] and w['doi'] and existing['doi']!=w['doi']:
                        raise ValueError('Input, evidence or workflow invariant failed at question_retrieval.search (check 244); inspect the signed task record and original source.')
                else:
                    same=None
                    if w['doi']:
                        same=c.execute('SELECT work_id FROM works WHERE doi=? AND doi!=\'\' LIMIT 1',(w['doi'],)).fetchone()
                    if not same:
                        same=c.execute('SELECT work_id FROM works WHERE lower(title)=lower(?) LIMIT 1',(w['title'],)).fetchone()
                    if same:
                        wid=same['work_id'];duplicates+=1
                    else:
                        c.execute('''INSERT INTO works(work_id,title,category,doi,year,venue,url,record_sha,source_status)
                                     VALUES(?,?,?,?,?,?,?,?,?)''',
                                  (wid,w['title'],'question_candidate',w['doi'],w['year'],w['venue'],
                                   w['bibliographic_link'],_sha(w),'BIB_ONLY'))
                        newworks+=1
                if not c.execute('SELECT 1 FROM question_metadata WHERE work_id=?',(wid,)).fetchone():
                    body=store.dump(w)
                    c.execute('INSERT INTO question_metadata VALUES(?,?,?,?)',
                              (wid,body,_sha(w),store.utc()))
                if not c.execute('SELECT 1 FROM question_papers WHERE question_id=? AND work_id=? AND query_id=?',
                                 (task['question_id'],wid,task['query_id'])).fetchone():
                    c.execute('INSERT INTO question_papers VALUES(?,?,?,?,?)',
                              (task['question_id'],wid,task['query_id'],w['id'],store.utc()))
                    relations+=1
                found.append({'work_id':wid,'title':w['title'],'question_id':task['question_id'],
                              'category':'QUESTION_CANDIDATE_METADATA_ONLY',
                              'oa_pdf_available_in_metadata':bool(w['oa_pdf_url'])})
            store.event(c,'QUESTION_SEARCH_COMPLETED',{'query_id':task['query_id'],
                      'raw_results':len(raws),'valid_works':len(normalized),'metadata_only':True})
        calls+=1
    output={'status':'QUESTION_SEARCH_PARTIAL_ERRORS' if failures else 'QUESTION_SEARCH_BATCH_DONE',
            'requests':calls,'new_bibliographic_works':newworks,'new_question_work_links':relations,
            'known_metadata_duplicates':duplicates,'papers':found[:50], 'errors':failures,
            'search_provenance':'OpenAlex metadata only; not peer review, full text, scientific claim, or novelty proof',
            'v5_disjoint_catalogue_untouched':True,
            'next':'Inspect the signed checkpoint, verify the original full-text evidence and reviewer receipts, then continue only the stage justified by a substantive evidence gap and available quota.'}
    store.write(root(ws)/'last_search_report.json',output)
    return output


def download(ws:pathlib.Path,*,online:bool=False,limit:int=3,download_fn:Any=None)->dict:
    if not online:raise ValueError('Source path, lawful access or network permission check failed at question_retrieval.download (check 285). Do not bypass paywalls or source integrity checks.')
    if not 1<=limit<=10:raise ValueError('Frozen research topic or signed research contract mismatch at question_retrieval.download (check 286). Reconfirm boundaries; do not overwrite approved work.')
    ws=ws.expanduser().resolve();_goal_sha(ws);db_init(ws)
    cfg=disc.config(ws)
    if download_fn is None and (ws/'source_routing.json').is_file():
        from literature_sources.downloader import obtain
        with store.connect(ws) as c:
            known={x[0] for x in c.execute('SELECT work_id FROM question_papers')}
            if c.execute("SELECT 1 FROM sqlite_master WHERE name='multisource_question_links'").fetchone():
                known.update(x[0] for x in c.execute('SELECT work_id FROM multisource_question_links'))
        return obtain(ws,online=online,category='all',limit=limit,family_ids=known)
    fetch=download_fn or disc.download_pdf
    out=[];failed=[]
    with store.connect(ws) as c:
        rows=c.execute('''SELECT w.work_id,w.source_status,m.metadata_json FROM question_metadata m
                         JOIN works w ON w.work_id=m.work_id
                         JOIN question_papers p ON p.work_id=w.work_id
                         GROUP BY w.work_id ORDER BY COUNT(DISTINCT p.question_id) DESC,w.work_id''').fetchall()
    for row in rows:
        if len(out)>=limit:break
        wid=row['work_id'];meta=json.loads(row['metadata_json'])
        if row['source_status']=='TEXT_AVAILABLE':continue
        url=meta.get('oa_pdf_url')
        if not url or not disc.safe_url(url):continue
        name=re.fullmatch(r'https://openalex\.org/(W\d+)',meta['id'])
        if not name:continue
        dest=ws/'input'/'question_driven'/('q_'+name.group(1)+'.pdf')
        if dest.exists():
            with store.connect(ws) as c:
                old=c.execute('SELECT file_sha FROM sources WHERE work_id=? AND file_path=?',(wid,str(dest.resolve()))).fetchone()
            if old and store.hashbytes(dest.read_bytes())==old['file_sha']:
                continue
            failed.append({'work_id':wid,'error':'Source state and independent reviewer provenance must satisfy the specified quality gate.'})
            continue
        try:
            fetch(url,dest,cfg['retrieval']['max_pdf_size_mb'],cfg['retrieval']['min_extractable_pdf_chars'])
            result=store.import_source(ws,wid,dest)
            with store.connect(ws) as c:
                store.event(c,'QUESTION_OA_FULLTEXT_READY',{'work_id':wid,'file_sha':result['original_sha256'],
                                  'source_id':result['source_id'],'oa_url':url})
            out.append({'work_id':wid,'relative_path':str(dest.relative_to(ws)),
                        'source_id':result['source_id'],'sha256':result['original_sha256']})
        except Exception as ex:
            # Avoid leaving incomplete download bytes with no certified source ledger.
            if dest.exists():
                with store.connect(ws) as c:
                    present=c.execute('SELECT 1 FROM sources WHERE file_path=?',(str(dest.resolve()),)).fetchone()
                if not present:dest.unlink()
            failed.append({'work_id':wid,'error':str(ex)[:200]})
    output={'status':'QUESTION_FULLTEXT_PARTIAL' if failed else 'QUESTION_FULLTEXT_BATCH_DONE',
            'downloaded':out,'failed':failed,
            'scientific_boundary':'This section indexes existing source-verified reviewer observations. It does not certify scientific validity, novelty or new experimental outcomes.'}
    store.write(root(ws)/'last_download_report.json',output)
    return output


def _multisource_search(ws,p,max_requests):
    from literature_sources.coordinator import Coordinator
    from literature_sources.common import write,utc
    from literature_sources.common import locked
    co=Coordinator(ws,online=True,request_limit=max_requests)
    with locked(co.root):
        extras=[{'query':q['query'],'category':'related','domain':'','band':q['band'],
                 'start':q['start_date'],'end':q['end_date'],'question_id':q['question_id'],'query_id':q['query_id']}
                for q in p['queries'] if not q['completed']]
        co.plan(extras)
        pending=[t for t in co.state['tasks'].values() if t.get('question_id') and t['status'] not in ('DONE','REUSED_LEGACY_SUCCESS')]
        if not pending:return {'status':'QUESTION_SOURCE_TASKS_ALREADY_COMMITTED','requests':0}
        with store.connect(ws) as c:old_usage=c.execute('SELECT COUNT(*) FROM question_query_attempts').fetchone()[0]
        reservations=co.state.setdefault('question_request_reservations',[])
        remaining=MAX_QUERIES_TOTAL-old_usage-sum(x['reserved_physical_requests'] for x in reservations)
        bound=min(max_requests,remaining)
        if bound<=0:return {'status':'QUESTION_REQUEST_LIFETIME_CAP','requests':0,'limit':MAX_QUERIES_TOTAL}
        # Retain conservative reservation after a crash. Never silently refund unknown requests.
        reservation={'at':utc(),'reserved_physical_requests':bound,'actual_physical_requests':None}
        reservations.append(reservation);co.save();co.budget['limit']=bound
        report=co._run_locked(max_steps=min(100,bound*6),extra_queries=extras,question_only=True)
        reservation['actual_physical_requests']=co.budget['sent'];reservation['report']=report['report'];co.save()
        report['memory_sync']=co.catalog.sync_memory()
        with store.connect(ws) as c:
            c.execute("CREATE TABLE IF NOT EXISTS multisource_question_links(question_id TEXT,query_id TEXT,work_id TEXT,source_record_id TEXT,recorded_at TEXT,PRIMARY KEY(question_id,query_id,source_record_id))")
            for q in p['queries']:
                c.execute('INSERT OR IGNORE INTO question_queries VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (q['query_id'],q['question_id'],q.get('question_sha',''),p.get('goal_sha',''),
                     q['query'],q['band'],q['start_date'],q['end_date'],'MULTISOURCE_PARTIAL',utc(),None,0,''))
            for t in co.state['tasks'].values():
                if not t.get('question_id'):continue
                for rid in co.catalog.data['query_links'].get(t['id'],[]):
                    c.execute('INSERT OR IGNORE INTO multisource_question_links VALUES(?,?,?,?,?)',
                              (t['question_id'],t['query_id'],co.catalog.data['record_family'][rid],rid,utc()))
                    rec=co.catalog.data['records'][rid];fid=co.catalog.data['record_family'][rid]
                    # Preserve the legacy field truthfully: non-OpenAlex identities live in the extension table.
                    legacy_id=rec.get('source_record_id','') if rec['source']=='openalex' else ''
                    c.execute('INSERT OR IGNORE INTO question_papers VALUES(?,?,?,?,?)',(t['question_id'],fid,t['query_id'],legacy_id,utc()))
        report['question_budget']={'legacy_attempts':old_usage,'new_reserved':sum(x['reserved_physical_requests'] for x in reservations),
                                  'limit':MAX_QUERIES_TOTAL,'crash_reservations_not_refunded':True}
        report['question_query_completion']='SOURCE_TASK_LEVEL; ORIGINAL OPENALEX COMPLETION ROWS UNMODIFIED'
        store.write(root(ws)/'last_multisource_search_report.json',report)
        return report
