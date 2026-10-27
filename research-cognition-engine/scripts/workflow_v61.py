#!/usr/bin/env python3
"""v6.1 bounded project-wide orchestration and certified evidence auto-sync.

No Codex CLI/model dispatch; real independent native subagents operate in the
Windows desktop UI. Deterministic local transitions are executable. All network
calls and new research cycles require explicit caller options. Checkpoints are
recoverable; old v4.4 and v5 state are never reset to force a successful run.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import pathlib
import re
import sys
import time
from typing import Any

import suite
import question_retrieval as questions
import store

SCHEMA=1


def _where(ws:pathlib.Path)->pathlib.Path:return store.root(ws)/'unified_scheduler.json'


def _state(ws:pathlib.Path)->dict:
    path=_where(ws)
    if not path.is_file():
        data={'schema_version':SCHEMA,'research_goal_sha256':_goalhash(ws),
              'last_evidence_fingerprint':'','last_evidence_report':{},'last_evidence_job_ids':[],
              'last_v5_fingerprint':'','last_v5_report':{},'last_v5_categories':{},
              'events':[],'created_at':store.utc()}
        store.write(path,data)
        return data
    data=store.read(path)
    if data.get('schema_version')!=SCHEMA or data.get('research_goal_sha256')!=_goalhash(ws):
        raise ValueError('Frozen research topic or signed research contract mismatch at workflow_v61._state (check 44). Reconfirm boundaries; do not overwrite approved work.')
    return data


def _goalhash(ws:pathlib.Path)->str:
    f=ws/'goal.md'
    if not f.is_file() or len(f.read_text('utf-8').strip())<15:
        raise ValueError('Frozen research topic or signed research contract mismatch at workflow_v61._goalhash (check 51). Reconfirm boundaries; do not overwrite approved work.')
    return store.hashbytes(f.read_bytes())


def _event(ws:pathlib.Path,kind:str,details:dict)->None:
    state=_state(ws)
    event={'at':store.utc(),'type':kind,'details':details}
    events=state['events']
    # Keep bounded control journal; detailed provenance remains in original
    # skill workspaces/SQLite and per-command append-only logs.
    events.append(event)
    if len(events)>250:state['events']=events[-250:]
    store.write(_where(ws),state)
    trace=store.root(ws)/'scheduler_events.jsonl'
    trace.parent.mkdir(parents=True,exist_ok=True)
    with trace.open('a',encoding='utf-8') as f:
        f.write(store.dump(event).replace('\n',' ')+'\n')


def _readable(ws:pathlib.Path)->bool:
    return (ws/'research_cognition_config.json').is_file() and (ws/'native_config.json').is_file()


def _v5_fingerprint(ws:pathlib.Path)->str:
    root=ws/'output'/'discovery_preflight'
    paths=[root/'paper_library.json',root/'state.json']
    if (ws/'source_routing.json').is_file():paths.append(root/'multisource/catalog.json')
    available=[p for p in paths if p.is_file()]
    if not available:return ''
    return store.hashobj({str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in available})


def sync_discovery(ws:pathlib.Path,*,force:bool=False)->dict:
    """Idempotently ingest authenticated v5 bibliography and downloaded OA files.

    Reconcile the same OpenAlex work already discovered by a question query
    without discarding original question-to-work links or overriding results.
    """
    ws=ws.expanduser().resolve()
    if not _readable(ws):return {'status':'V5_SYNC_SKIPPED_NOT_INITIALIZED'}
    signature=_v5_fingerprint(ws)
    if not signature:return {'status':'NO_V5_LIBRARY_OR_DOWNLOAD_LOG'}
    state=_state(ws)
    if signature==state.get('last_v5_fingerprint') and not force:
        return {'status':'V5_ALREADY_SYNCED'}
    path=ws/'output'/'discovery_preflight'/'paper_library.json'
    promoted=[]
    category_map={}
    if path.is_file():
        catalogue=store.read(path)
        selected=catalogue.get('selected',{})
        if not isinstance(selected,dict):raise ValueError('Source path, lawful access or network permission check failed at workflow_v61.sync_discovery (check 101). Do not bypass paywalls or source integrity checks.')
        with store.connect(ws) as c:
            for category in ('core','related','inspiration'):
                for item in selected.get(category,[]):
                    wid=item.get('id');doi=item.get('doi') or ''
                    if not isinstance(wid,str) or not wid:
                        raise ValueError('Input, evidence or workflow invariant failed at workflow_v61.sync_discovery (check 107); inspect the signed task record and original source.')
                    if wid in category_map and category_map[wid]!=category:
                        raise ValueError('Input, evidence or workflow invariant failed at workflow_v61.sync_discovery (check 109); inspect the signed task record and original source.')
                    category_map[wid]=category
                    existing=c.execute('SELECT category,doi FROM works WHERE work_id=?',(wid,)).fetchone()
                    if not existing or existing['category']==category:continue
                    if existing['category']!='question_candidate':
                        previous=state.get('last_v5_categories',{}).get(wid)
                        if previous!=existing['category']:
                            raise ValueError('Input, evidence or workflow invariant failed at workflow_v61.sync_discovery (check 116); inspect the signed task record and original source.')
                    if existing['doi'] and doi and existing['doi'].lower()!=doi.lower():
                        raise ValueError('Input, evidence or workflow invariant failed at workflow_v61.sync_discovery (check 118); inspect the signed task record and original source.')
                    c.execute('UPDATE works SET category=? WHERE work_id=?',(category,wid))
                    promoted.append({'work_id':wid,'category':category})
            if promoted:store.event(c,'QUESTION_BIBLIOGRAPHY_RECLASSIFIED_FROM_V5',{'works':promoted})
    multisource={}
    if (ws/'source_routing.json').is_file():
        from literature_sources.coordinator import Coordinator
        acquisition=Coordinator(ws);acquisition.seed()
        import multisource_bridge
        multisource=multisource_bridge.sync(ws)
    result=store.import_catalogue(ws)
    files=store.import_v5_downloads(ws)
    if files.get('status')=='PARTIAL':
        raise ValueError('Source path, lawful access or network permission check failed at workflow_v61.sync_discovery (check 125). Do not bypass paywalls or source integrity checks.'+str(files.get('failed',[]))[:400])
    state=_state(ws)
    state['last_v5_fingerprint']=signature
    state['last_v5_categories']=category_map
    state['last_v5_report']={'at':store.utc(),'imported_bibliography':result.get('new_bibliographic_works',0),
                             'source_imported':files.get('imported',0),'question_promoted_to_v5':len(promoted),'multisource':multisource}
    store.write(_where(ws),state)
    _event(ws,'DISCOVERY_METADATA_AND_AUTHENTIC_OA_SYNC',state['last_v5_report'])
    return {'status':'V5_CATALOGUE_AND_SOURCE_SYNCED',**state['last_v5_report'],
            'scientific_limit':'Bibliographic metadata, source-page quote matching and agent judgments are distinct epistemic levels. No unperformed simulation, training or experiment provides scientific measurements; verify figures and prior art independently.'}


def sync_all(ws:pathlib.Path,*,force:bool=False)->dict:
    return {'v5':sync_discovery(ws,force=force),'v44':auto_sync(ws,force=force),
            'v6_memory':str(store.dbfile(ws))}


def _commit_fingerprint(ws:pathlib.Path)->tuple[str,int,list[str]]:
    statefile=ws/'output'/'batch'/'state.json'
    if not statefile.is_file():return '',0,[]
    state=suite.original_batch.load_state(ws)
    if not state.get('frozen'):return '',0,[]
    home=ws/'output'/'native'/'tasks'
    jobs=[]
    if home.is_dir():
        for folder in sorted(home.iterdir()):
            if not folder.is_dir() or not re.fullmatch(r'R\d{2}_.+_C\d{3}',folder.name):continue
            commit=folder/'commit.json'
            if not commit.is_file():continue
            record=store.read(commit)
            if record.get('status')!='COMMITTED':continue
            consolidated=folder/'consolidated.json'
            if not consolidated.is_file():
                raise ValueError('Signed task, stage, commit receipt or report provenance check failed at workflow_v61._commit_fingerprint (check 158). Resume only from a verified state.'+folder.name)
            # Verify all finalized round-level receipts too, not only the
            # scientific leaf observations later imported into RCE.
            suite.adapter._verified_member_commit(ws,folder.name,store.read(consolidated))
            paths=[commit,consolidated]
            for sub in ('receipts','answers'):
                if (folder/sub).is_dir(): paths.extend(sorted((folder/sub).glob('*.json')))
            combined=[]
            for path in paths:
                if not path.is_file():
                    combined.append({'path':str(path.relative_to(ws)),'sha256':'MISSING'})
                else:
                    combined.append({'path':str(path.relative_to(ws)),
                                     'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
            jobs.append({'job':folder.name,'files':combined})
    if not jobs:return '',0,[]
    # Include original research contract and the frozen file identity.
    return store.hashobj({'core_workspace':state['frozen']['core_workspace'],
                          'contract':state['contract'],'commits':jobs}),len(jobs),[job['job'] for job in jobs]


def auto_sync(ws:pathlib.Path,*,force:bool=False)->dict:
    ws=ws.expanduser().resolve()
    if not _readable(ws):return {'status':'SYNC_SKIPPED_NOT_INITIALIZED'}
    state=_state(ws)
    fingerprint,count,job_ids=_commit_fingerprint(ws)
    missing=sorted(set(state.get('last_evidence_job_ids',[]))-set(job_ids))
    if missing:raise ValueError('Authentic source, page quotation or evidence integrity check failed at workflow_v61.auto_sync (check 185). Never accept unverified material.'+str(missing[:6]))
    if not fingerprint:
        if state.get('last_evidence_fingerprint'):
            raise ValueError('Authentic source, page quotation or evidence integrity check failed at workflow_v61.auto_sync (check 188). Never accept unverified material.')
        return {'status':'NO_COMMITTED_CORE_EVIDENCE','committed_leaf_jobs':count}
    if not force and fingerprint==state['last_evidence_fingerprint']:
        return {'status':'EVIDENCE_ALREADY_SYNCED','committed_leaf_jobs':count}
    # Protect the checkpoint: failure in any original citation/receipt leaves
    # last_evidence_fingerprint unchanged, so the next attempt can retry.
    result=suite.adapter.sync(ws)
    if result.get('status')!='SOURCE_EVIDENCE_SYNCED':
        raise ValueError('Original v4.4 did not certify the evidence synchronization')
    state=_state(ws)
    state['last_evidence_fingerprint']=fingerprint
    state['last_evidence_job_ids']=job_ids
    state['last_evidence_report']={'at':store.utc(),'committed_leaf_jobs':count,
                                   'new_claims':result.get('new_anchor_checked_claims',0),
                                   'pending_leaf_jobs':result.get('pending_leaf_jobs',0)}
    store.write(_where(ws),state)
    _event(ws,'ORIGINAL_READING_EVIDENCE_SYNC',state['last_evidence_report'])
    return {'status':'EVIDENCE_AUTO_SYNCED',**state['last_evidence_report'],
            'scientific_limit':result['scientific_limit']}


def _question_next(ws:pathlib.Path)->dict|None:
    if not (ws/'research_cognition_config.json').is_file():return None
    with store.connect(ws) as c:
        nq=c.execute('SELECT COUNT(*) FROM questions').fetchone()[0]
    if not nq:return None
    prepared=questions.plan(ws)
    if prepared['pending_review']:
        # Can search other English questions when some require review; no
        # invisible translation/LLM summarization performed by Python.
        if not prepared['new_queries']:
            return {'status':'NEEDS_QUESTION_QUERY_REVIEW','count':len(prepared['pending_review']),
                    'next':'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
    if prepared['new_queries']:
        return {'status':'NEEDS_QUESTION_DRIVEN_SEARCH','pending_queries':prepared['new_queries'],
                'pending_translation_or_review':len(prepared['pending_review']),
                'next':'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
    return None


def _new_question_papers_after_freeze(ws:pathlib.Path)->list[dict]:
    statefile=ws/'output'/'batch'/'state.json'
    if not statefile.is_file():return []
    state=suite.original_batch.load_state(ws)
    if not state.get('frozen'):return []
    questions.db_init(ws)
    with store.connect(ws) as c:
        rows=c.execute("""SELECT DISTINCT w.work_id,w.title,s.file_path
             FROM question_papers p JOIN works w ON p.work_id=w.work_id
             JOIN sources s ON s.work_id=w.work_id
             WHERE NOT EXISTS(SELECT 1 FROM claims cl WHERE cl.work_id=w.work_id)
             ORDER BY w.work_id""").fetchall()
    indexed={x['sha256'] for x in state.get('papers',[]) if x.get('status')=='READY'}
    pending=[]
    for row in rows:
        file=pathlib.Path(row['file_path'])
        if not file.is_file():continue
        digest=store.hashbytes(file.read_bytes())
        if digest not in indexed:
            pending.append({'work_id':row['work_id'],'title':row['title'],'file':str(file)})
    return pending


def choose(ws:pathlib.Path,*,allow_incomplete_discovery:bool=False)->dict:
    ws=ws.expanduser().resolve()
    if not _readable(ws):
        return {'status':'NEEDS_INIT','next':'research_suite.py init --workspace <path>'}
    # Prioritize a changed, verified original reading snapshot; a source
    # tampering error is fatal and cannot silently be treated as no evidence.
    fingerprint,count,job_ids=_commit_fingerprint(ws)
    missing=sorted(set(_state(ws).get('last_evidence_job_ids',[]))-set(job_ids))
    if missing:raise ValueError('Authentic source, page quotation or evidence integrity check failed at workflow_v61.choose (check 259). Never accept unverified material.'+str(missing[:6]))
    if not fingerprint and _state(ws).get('last_evidence_fingerprint'):
        raise ValueError('Authentic source, page quotation or evidence integrity check failed at workflow_v61.choose (check 261). Never accept unverified material.')
    if fingerprint and fingerprint!=_state(ws)['last_evidence_fingerprint']:
        return {'status':'NEEDS_AUTO_EVIDENCE_SYNC','committed_leaf_jobs':count,
                'next':'Run research_suite.py auto-sync --workspace <path>'}
    signature=_v5_fingerprint(ws)
    if signature and signature!=_state(ws).get('last_v5_fingerprint'):
        return {'status':'NEEDS_V5_EVIDENCE_SYNC',
                'next':'Run research_suite.py auto-sync --workspace <path> to register only authentic v5 metadata/full text'}
    import evidence_gain_scheduler as gain_scheduler
    # Preserve the established ordering for empty/non-ready reader campaigns:
    # discovery.status itself can change local acquisition fingerprints.
    step = (suite.next_action(ws,allow_incomplete_discovery=allow_incomplete_discovery)
            if gain_scheduler.ready_reader_checkpoint(suite.original_batch, ws) else None)
    # Preserve integrity/sync checks above. Ready original-source reading has
    # priority over optional new leads; acquisition is not certified complete.
    reader_priority = step is not None and step['status'] in ('READY_TO_SEAL_ORIGINAL_V44', 'READ_ORIGINAL_V44_CORE')
    research = None
    if not reader_priority:
        pending=_new_question_papers_after_freeze(ws)
        if pending:
            return {'status':'NEEDS_SEPARATE_READING_CAMPAIGN','papers':pending[:10],
                    'total_new_fulltext_papers':len(pending),
                    'next':'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
        research=_question_next(ws)
        if research and research['status'] in ('NEEDS_QUESTION_DRIVEN_SEARCH','NEEDS_QUESTION_QUERY_REVIEW'):
            import evidence_gain_scheduler as gain_scheduler
            pause=gain_scheduler.automatic_search_pause(ws)
            if pause:
                return {'status':'PAUSED_FOR_EVIDENCE_STRATEGY_REVIEW',
                        'evidence_gain_policy':pause, 'pending_action':research,
                        'next':'Triage paused gap strategies before more automatic question searches; do not alter quota or reviewer gates'}
            return research
    if step is None:
        step=suite.next_action(ws,allow_incomplete_discovery=allow_incomplete_discovery)
    if step['status']=='READY_FOR_RCE_CYCLE':
        import round_intelligence as rounds
        decision=rounds.next_decision(ws)
        if decision['decision']=='DO_NOT_START_RESEARCH_CYCLE':
            return {'status':'PAUSED_NO_NEW_RESEARCH_EVIDENCE',
                    'efficiency_gate':decision,
                    'next':'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
        if decision['decision']=='PAUSE_AND_REVIEW':
            return {'status':'NEEDS_LEGACY_CYCLE_BASELINE_REVIEW',
                    'efficiency_gate':decision,
                    'next':'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
        if decision['decision']=='HUMAN_OR_AGENT_TRIAGE_FIRST':
            return {'status':'NEEDS_EVIDENCE_VALUE_TRIAGE',
                    'efficiency_gate':decision,
                    'next':'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
    if step['status']=='READY_FOR_RCE_NATIVE_TASK':
        # A previously prepared model task may already be assigned; do not
        # reserve a second quota or hallucinate completion.
        current=suite.engine.get_state(ws)
        cycle=current['cycles'][-1]
        task=suite.engine.taskdir(ws,cycle['id']+'_'+cycle['stage'])
        if (task/'manifest.json').is_file():
            return {'status':'WAIT_FOR_NATIVE_RCE_SUBAGENTS','job':task.name,'next':'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
        return {**step,'status':'PREPARE_RCE_NATIVE_TASK'}
    if step['status'] in ('READ_SCREENING','READ_ORIGINAL_V44_CORE'):
        job=step['job']
        pending=ws/'output'/'native'/'tasks'/job/'manifest.json'
        if pending.is_file() and not (pending.parent/'commit.json').exists():
            return {'status':'WAIT_FOR_NATIVE_READER_SUBAGENTS','job':job,
                    'next':'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
        return {**step,'status':'PREPARE_NATIVE_READER_TASK'}
    if research and research['status']=='NEEDS_QUESTION_QUERY_REVIEW' and step['status'] in (
            'READY_FOR_RCE_CYCLE','SCIENTIFIC_RECOMMENDATION_PENDING_USER_APPROVAL'):
        return research
    return step


def _capture_native(argv:list[str])->dict:
    stream=io.StringIO()
    with contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
        code=suite.native_runtime.main(argv)
    body=stream.getvalue().strip()
    if code!=0:raise ValueError('Input, evidence or workflow invariant failed at workflow_v61._capture_native (check 319); inspect the signed task record and original source.'+body[-700:])
    try:return json.loads(body)
    except (ValueError,TypeError):return {'status':'NATIVE_COMMAND_COMPLETE','detail':body[-950:]}


def _capture_rce(argv:list[str])->dict:
    stream=io.StringIO()
    with contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
        code=suite.rce.execute(argv)
    body=stream.getvalue().strip()
    if code!=0:raise ValueError('Input, evidence or workflow invariant failed at workflow_v61._capture_rce (check 329); inspect the signed task record and original source.'+body[-700:])
    try:return json.loads(body)
    except (ValueError,TypeError):return {'status':'RCE_COMMAND_COMPLETE','detail':body[-900:]}


def run(ws:pathlib.Path,*,max_steps:int=5,allow_network:bool=False,
        allow_incomplete_discovery:bool=False,prepare_native:bool=False,
        start_research_cycle:bool=False,allow_ingest:bool=False)->dict:
    """Execute bounded deterministic tasks; pauses for genuine model/human.

    Caller permission flags apply only to this invocation and are NOT stored
    as perpetual permission; no background worker is started.
    """
    ws=ws.expanduser().resolve()
    if not 1<=max_steps<=20:raise ValueError('max_stepsmust in1..20')
    report=[]
    for _ in range(max_steps):
        choice=choose(ws,allow_incomplete_discovery=allow_incomplete_discovery)
        status=choice['status']
        if status=='NEEDS_V5_EVIDENCE_SYNC':
            result=sync_discovery(ws)
        elif status=='NEEDS_AUTO_EVIDENCE_SYNC':
            result=auto_sync(ws)
        elif status=='NEEDS_QUESTION_DRIVEN_SEARCH' and allow_network:
            result=questions.search(ws,online=True,max_requests=3)
        elif status=='NEEDS_DISCOVERY' and allow_network:
            result=suite.discovery.run(ws,online=True,request_limit=3)
        elif status=='NEEDS_ORIGINAL_V44_INGEST' and allow_ingest:
            result=_capture_native(['ingest','--workspace',str(ws)])
        elif status=='READY_FOR_ORIGINAL_V44_SELECT':
            result=_capture_native(['select','--workspace',str(ws)])
        elif status=='READY_TO_SEAL_ORIGINAL_V44':
            # Original v4.4 quality gate still applies. No discovery-gap
            # override is passed and a non-zero return is a hard failure.
            result=_capture_native(['seal','--workspace',str(ws)])
        elif status=='NEEDS_RCE_INIT':
            result=suite.rce.init(ws)
        elif status=='READY_FOR_RCE_CYCLE' and start_research_cycle:
            result=_capture_rce(['new-cycle','--workspace',str(ws)])
        elif status=='PREPARE_NATIVE_READER_TASK' and prepare_native:
            result=_capture_native(['prepare','--workspace',str(ws)])
        elif status=='PREPARE_RCE_NATIVE_TASK' and prepare_native:
            result=_capture_rce(['prepare','--workspace',str(ws)])
        else:
            return {'status':'PAUSED_FOR_PERMISSION_OR_EXTERNAL_WORK','next_action':choice,
                    'performed':report,'model_agents_spawned_by_python':0}
        report.append({'action':status,'result':result})
        _event(ws,'SCHEDULER_STEP',{'action':status,'result_status':result.get('status','UNKNOWN')})
        # A failed/blocked operation cannot be treated as progress, even when
        # the original API reports a nonexceptional shortfall status.
        if result.get('status','').startswith(('BLOCKED','SOURCE_SEARCH_BUDGET_EXHAUSTED')):
            return {'status':'PAUSED_ON_BLOCKER','performed':report,'next_action':choice}
        if status in ('NEEDS_DISCOVERY','NEEDS_QUESTION_DRIVEN_SEARCH') and not result.get('requests',result.get('api_requests_this_run',0)):
            return {'status':'PAUSED_SOURCE_BUDGET_OR_EMPTY','performed':report,'next_action':choice}
    return {'status':'STEP_LIMIT_REACHED','performed':report,
            'next_action':choose(ws,allow_incomplete_discovery=allow_incomplete_discovery),
            'model_agents_spawned_by_python':0}


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description='v6.1 research cognition unified scheduler: local, resumed, permissioned')
    sub=p.add_subparsers(dest='command',required=True)
    for name in ('next-v61','auto','auto-sync','question-plan','question-search','question-download',
                 'reader-prepare','reader-collect','reader-commit','rce-prepare','rce-collect','rce-commit'):
        cmd=sub.add_parser(name)
        cmd.add_argument('--workspace',required=True,type=pathlib.Path)
        if name=='auto':
            cmd.add_argument('--max-steps',type=int,default=5)
            cmd.add_argument('--allow-network',action='store_true')
            cmd.add_argument('--allow-incomplete-discovery',action='store_true')
            cmd.add_argument('--prepare-native',action='store_true')
            cmd.add_argument('--start-research-cycle',action='store_true')
            cmd.add_argument('--allow-ingest',action='store_true')
        if name=='next-v61':cmd.add_argument('--allow-incomplete-discovery',action='store_true')
        if name=='auto-sync':cmd.add_argument('--force',action='store_true')
        if name=='question-plan':cmd.add_argument('--max-questions',type=int,default=6)
        if name in ('question-search','question-download'):cmd.add_argument('--online',action='store_true')
        if name=='question-search':cmd.add_argument('--max-requests',type=int,default=4)
        if name=='question-download':cmd.add_argument('--limit',type=int,default=3)
        if name in ('reader-collect','reader-commit','rce-collect','rce-commit'):
            cmd.add_argument('--job-id',required=True)
        if name in ('reader-collect','rce-collect'):
            cmd.add_argument('--role',required=True)
            cmd.add_argument('--file',required=True,type=pathlib.Path)
        if name in ('rce-collect',):cmd.add_argument('--thread-ref',required=True)
        if name=='reader-collect':cmd.add_argument('--thread-ref')
    args=p.parse_args(argv)
    ws=args.workspace.expanduser().resolve()
    try:
        if args.command=='next-v61':out=choose(ws,allow_incomplete_discovery=args.allow_incomplete_discovery)
        elif args.command=='auto':out=run(ws,max_steps=args.max_steps,allow_network=args.allow_network,
                                         allow_incomplete_discovery=args.allow_incomplete_discovery,
                                         prepare_native=args.prepare_native,start_research_cycle=args.start_research_cycle,
                                         allow_ingest=args.allow_ingest)
        elif args.command=='auto-sync':out=sync_all(ws,force=args.force)
        elif args.command=='question-plan':out=questions.plan(ws,max_questions=args.max_questions)
        elif args.command=='question-search':out=questions.search(ws,online=args.online,max_requests=args.max_requests)
        elif args.command=='question-download':out=questions.download(ws,online=args.online,limit=args.limit)
        elif args.command.startswith('reader-'):
            cmd=args.command.removeprefix('reader-')
            call=[cmd,'--workspace',str(ws)]
            if cmd in ('collect','commit'):call+=['--job',args.job_id]
            if cmd=='collect':
                call+=['--role',args.role,'--file',str(args.file)]
                if args.thread_ref:call+=['--thread-ref',args.thread_ref]
            out=_capture_native(call)
            if cmd=='commit':out={'reader_commit':out,'auto_sync':auto_sync(ws)}
        elif args.command.startswith('rce-'):
            cmd=args.command.removeprefix('rce-')
            call=[cmd,'--workspace',str(ws)]
            if cmd in ('collect','commit'):call+=['--job-id',args.job_id]
            if cmd=='collect':call+=['--role',args.role,'--file',str(args.file),'--thread-ref',args.thread_ref]
            out=_capture_rce(call)
            if cmd=='commit':
                # Search plan recomputed on next scheduler step; new questions
                # never change a frozen v5 campaign configuration implicitly.
                out={'rce_commit':out,'question_plan':questions.plan(ws)}
        else:raise ValueError('Unsupported command')
        print(json.dumps(out,ensure_ascii=False,indent=2,default=str))
        return 0 if out.get('status') not in ('BLOCKED','ERROR') else 2
    except (ValueError,RuntimeError,KeyError,TypeError,OSError) as ex:
        print(json.dumps({'status':'BLOCKED','reason':str(ex)[:900]},ensure_ascii=False),file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
