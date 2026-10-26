#!/usr/bin/env python3
"""Research Cognition Engine v6.0: Windows native Codex subagent workflow.

Python standard library; no Codex CLI, SDK, API model requests or network calls.
Requires existing project goal.md and v5 discovery papers, or manual real work
registration. Human user authorizes method changes and budget periods explicitly.
"""
from __future__ import annotations
import argparse, importlib.util, json, os, pathlib, re, sys, time
from contextlib import contextmanager
from typing import Any
import store,engine,harness,feedback

SKILL=pathlib.Path(__file__).resolve().parents[1]
DEFAULT=store.read(SKILL/'config.example.json')
CONF='research_cognition_config.json'

class BudgetPause(RuntimeError):pass


def check_cfg(c:dict)->dict:
    if not isinstance(c,dict) or c.get('schema_version')!=6 or c.get('enabled') is not True:
        raise ValueError('Unsupported/disabled RCE schema')
    for fixed in ('propose_probe_compose','budget','ranking','research_contract','native_roles'):
        if not isinstance(c.get(fixed),dict) or set(c[fixed])!=set(DEFAULT[fixed]):
            raise ValueError(f'{fixed} fields changed or missing')
    for k in ('allow_script_self_edit','allow_guardrail_edit'):
        if c['propose_probe_compose'][k] is not False:raise ValueError('No self-edit of scripts and academic guardrails')
    if c['propose_probe_compose']['require_holdout_benchmark'] is not True or c['propose_probe_compose']['require_independent_review'] is not True:
        raise ValueError('Cannot bypass held-out probe or independent veto')
    if c['propose_probe_compose']['k']!=1:raise ValueError('Budgeted Harness²-style recursion is k=1 only')
    for k,lo,hi in [('max_native_assignments_per_cycle',1,50),('max_input_chars_per_cycle',1000,5000000),
                    ('max_papers_in_task_context',1,50),('max_context_chars',2000,300000),
                    ('max_hypotheses_per_cycle',1,5)]:
        if type(c['budget'][k]) is not int or not lo<=c['budget'][k]<=hi:raise ValueError(f'Invalid budget.{k}')
    for k in harness.WEIGHTS:
        v=c['ranking'].get(k)
        if type(v) not in (int,float) or not harness.LIMITS[k][0]<=v<=harness.LIMITS[k][1]:
            raise ValueError(f'Illegal RCE ranking weight {k}')
    if set(c['ranking'])!=set(harness.WEIGHTS):raise ValueError('Unknown ranking weight')
    if c['research_contract']['immutable_confirmed_methods'] is not True or c['research_contract']['require_human_approval_for_method_adoption'] is not True:
        raise ValueError('User manuscript and established results are frozen')
    if c['stage_order']!=list(engine.STAGES) or c['native_roles']!=engine.DEFAULT_ROLES:
        raise ValueError('Stage order and independent specialist jury may not be weakened through tuning')
    if c['windows_codex_native_agents'] is not True or c['offline_without_model_calls'] is not True:
        raise ValueError('Do not silently switch to unverified CLI or API execution')
    return c


def config(ws:pathlib.Path)->dict:
    p=ws/CONF
    if not p.is_file():raise ValueError('Run init to create RCE config')
    return check_cfg(store.read(p))


def init(ws:pathlib.Path)->dict:
    out=engine.init(ws)
    p=ws/CONF
    if not p.exists():store.write(p,DEFAULT)
    check_cfg(store.read(p))
    harness.state(ws)
    return {**out,'created_config':str(p), 'native_agents':sum(len(x) for x in DEFAULT['native_roles'].values())}


def patch(ws:pathlib.Path,request:dict)->dict:
    c=config(ws)
    if not isinstance(request,dict) or not request or set(request)-{'budget','ranking','propose_probe_compose'}:
        raise ValueError('Only budget/ranking/probe tuning is allowed; no academic gate relaxation')
    changed={**c}
    for k,v in request.items():
        if not isinstance(v,dict) or set(v)-set(c[k]):raise ValueError(f'Unknown RCE parameter {k}')
        changed[k]={**c[k],**v}
    check_cfg(changed)
    current=engine.get_state(ws)
    if current['cycles'] and current['cycles'][-1]['stage']!='COMPLETE' and ('ranking' in request):
        raise ValueError('Cannot change semantic ranking in middle of frozen cognition cycle; use Harness adoption after stage ends')
    # Ranking must be evolved via held-out tests, not by a direct unreviewed patch.
    if 'ranking' in request:
        raise ValueError('Ranking changes require harness-propose/probe/adopt with independent review')
    store.write(ws/CONF,changed)
    return {'status':'CONFIG_APPLIED','config_sha256':store.hashobj(changed),'groups_changed':list(request)}


def _budget_path(ws:pathlib.Path)->pathlib.Path:return store.root(ws)/'local_model_budget.json'


def budget(ws:pathlib.Path,cfg:dict)->dict:
    f=_budget_path(ws)
    if not f.exists():
        store.write(f,{'active_period':'research-period-001','periods':{'research-period-001':{'requests':{},'created_at':store.utc()}},'renewals':[]})
    state=store.read(f)
    rs=state['periods'][state['active_period']]['requests']
    total=sum(v['prompt_chars'] for v in rs.values())
    return {'active_period':state['active_period'],'reserved_assignments':len(rs),
            'allowed_assignments':cfg['budget']['max_native_assignments_per_cycle'],
            'remaining_assignments':max(0,cfg['budget']['max_native_assignments_per_cycle']-len(rs)),
            'reserved_prompt_chars':total,'max_prompt_chars':cfg['budget']['max_input_chars_per_cycle'],
            'remaining_prompt_chars':max(0,cfg['budget']['max_input_chars_per_cycle']-total),
            'warning':'Local task reservation proxy; NOT verified real Pro 5x subscription usage'}


def _native_budget_owner(ws:pathlib.Path):
    native=ws/'.agents'/'skills'/'batch-paper-deepread-desktop'/'scripts'/'quota_guard.py'
    settings=ws/'native_config.json'
    if not native.is_file() or not settings.is_file():return None
    conf=store.read(settings).get('budget')
    if not isinstance(conf,dict):return None
    loc=native.parent
    # Path insertion is for self-contained local validation modules only,
    # never for executing untrusted paper text or arbitrary external plugins.
    if str(loc) not in sys.path:sys.path.insert(0,str(loc))
    spec=importlib.util.spec_from_file_location('rce_linked_native_quota',native)
    mod=importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    mod.validate(conf)
    return mod,conf


@contextmanager
def _budget_lock(ws:pathlib.Path):
    lock=store.root(ws)/'.allocation_lock'
    lock.parent.mkdir(parents=True,exist_ok=True)
    for attempt in range(100):
        try:
            lock.mkdir()
            break
        except FileExistsError:
            time.sleep(0.05)
    else:
        raise BudgetPause('Budget file lock busy; cannot safely dispatch concurrently')
    try:
        yield
    finally:
        lock.rmdir()


def _reserve(ws:pathlib.Path,cfg:dict,requests:dict[str,int])->dict:
    with _budget_lock(ws):
        budget(ws,cfg)
        state=store.read(_budget_path(ws));rs=state['periods'][state['active_period']]['requests']
        for k,v in requests.items():
            if k in rs and rs[k]['prompt_chars']!=v:raise ValueError('Previously reserved task changed prompt length')
        new={k:v for k,v in requests.items() if k not in rs}
        if len(rs)+len(new)>cfg['budget']['max_native_assignments_per_cycle'] or sum(x['prompt_chars'] for x in rs.values())+sum(new.values())>cfg['budget']['max_input_chars_per_cycle']:
            raise BudgetPause('BUDGET_PAUSED: task dispatch would exceed the local Pro 5x safety proxy; do not auto-renew or spawn agents')
        linked=_native_budget_owner(ws)
        if linked and new:
            module,ncfg=linked
            # Share the original v4.4 budget ledger so these are not free extra agents.
            module.reserve(ws,ncfg,new)
        for k,v in new.items():rs[k]={'prompt_chars':v,'reserved_at':store.utc(),'status':'NATIVE_DISPATCH_RESERVED_NOT_PROVIDER_MEASURED'}
        if new:store.write(_budget_path(ws),state)
    return {'reservations':len(requests),'new_reservations':len(new),'linked_v44_budget':bool(linked),**budget(ws,cfg)}


def renew(ws:pathlib.Path,label:str,authorized:bool)->dict:
    if not authorized:raise ValueError('Explicit user approval and real quota-reset confirmation required')
    if not re.fullmatch('[a-zA-Z0-9][a-zA-Z0-9_-]{4,60}',label):raise ValueError('Invalid unique budget period label')
    state=store.read(_budget_path(ws))
    if label in state['periods']:raise ValueError('Cannot reuse historical budget period label')
    linked=_native_budget_owner(ws)
    if linked:
        module,ncfg=linked
        module.renew(ws,ncfg,label,user_authorized=True)
    prior=state['active_period'];state['active_period']=label
    state['periods'][label]={'requests':{},'created_at':store.utc()}
    state['renewals'].append({'prior':prior,'new':label,'authorization':'USER_REPORTS_REAL_ACCOUNT_RESET','at':store.utc()})
    store.write(_budget_path(ws),state)
    return budget(ws,config(ws))


def status(ws:pathlib.Path)->dict:
    b=budget(ws,config(ws));s=engine.get_state(ws)
    with store.connect(ws) as c:
        counts={t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('works','sources','claims','questions','contradictions','hypotheses','assessments','experiments','feedback','decisions')}
    linked=_native_budget_owner(ws)
    return {'status':s['cycles'][-1]['stage'] if s['cycles'] else 'READY_FOR_NEW_CYCLE',
            'cycle_count':len(s['cycles']),'research_entities':counts,
            'harness_revision':harness.state(ws)['revision'], 'budget':b,
            'shared_v44_budget':linked[0].status(ws,linked[1]) if linked else None,
            'next':'sync-catalogue -> register-source -> new-cycle -> prepare -> separate native agents -> collect -> commit -> ... -> report'}


def execute(argv=None)->int:
    p=argparse.ArgumentParser(description='Research Cognition Engine v6.0; deterministic local tools only; no native model spawned by Python')
    sub=p.add_subparsers(dest='op',required=True)
    operations=('init','sync-catalogue','sync-downloaded-pdfs','register-source','new-cycle','prepare','collect','commit','status',
                'next-reading','search-plan','report','budget','renew-budget','tune','experiment-feedback','harness-propose','harness-probe','harness-adopt','harness-rollback')
    for name in operations:
        cmd=sub.add_parser(name);cmd.add_argument('--workspace',required=True,type=pathlib.Path)
        if name=='register-source':cmd.add_argument('--work-id',required=True);cmd.add_argument('--file',required=True,type=pathlib.Path)
        if name in ('collect','commit'):cmd.add_argument('--job-id',required=True)
        if name=='new-cycle':
            cmd.add_argument('--researcher-approved',action='store_true',help='Source state and independent reviewer provenance must satisfy the specified quality gate.')
            cmd.add_argument('--reason',default='',help='Source state and independent reviewer provenance must satisfy the specified quality gate.')
        if name=='collect':
            cmd.add_argument('--role',required=True);cmd.add_argument('--file',required=True,type=pathlib.Path)
            cmd.add_argument('--thread-ref',required=True)
        if name in ('tune','experiment-feedback','harness-propose','harness-adopt'):
            cmd.add_argument('--file',required=True,type=pathlib.Path)
        if name in ('harness-probe','harness-adopt'):cmd.add_argument('--proposal-id',required=True)
        if name=='experiment-feedback':cmd.add_argument('--review-file',required=True,type=pathlib.Path)
        if name=='harness-propose':
            cmd.add_argument('--reason',required=True)
            cmd.add_argument('--task-ref',action='append',required=True)
            cmd.add_argument('--proposer-thread-ref',required=True)
        if name=='harness-rollback':cmd.add_argument('--reason',required=True)
        if name in ('harness-rollback','renew-budget'):cmd.add_argument('--authorized',action='store_true')
        if name=='renew-budget':cmd.add_argument('--label',required=True)
    a=p.parse_args(argv);ws=a.workspace.expanduser().resolve()
    try:
        op=a.op
        if op=='init':out=init(ws)
        elif op=='sync-catalogue':out=store.import_catalogue(ws)
        elif op=='sync-downloaded-pdfs':out=store.import_v5_downloads(ws)
        elif op=='register-source':out=store.import_source(ws,a.work_id,a.file)
        elif op=='new-cycle':
            import round_intelligence as rounds
            decision=rounds.next_decision(ws)
            kind=decision.get('decision')
            if kind in ('DO_NOT_START_RESEARCH_CYCLE','HUMAN_OR_AGENT_TRIAGE_FIRST','PAUSE_AND_REVIEW'):
                if not (a.researcher_approved and len(a.reason.strip())>=25):
                    raise ValueError('REFUSE_REDUNDANT_RESEARCH_CYCLE: '+decision.get('status','')+
                                     'Authentic source, page quotation or evidence integrity check failed at rce.execute (check 225). Never accept unverified material.')
                with store.connect(ws) as c:
                    store.event(c,'HUMAN_APPROVED_REPEAT_RESEARCH_CYCLE',
                                {'decision':decision,'reason':a.reason,'scientific_quality_gates_unchanged':True})
            out=engine.new_cycle(ws,config(ws))
        elif op=='prepare':out=engine.prepare(ws,config(ws),_reserve)
        elif op=='collect':out=engine.collect(ws,a.job_id,a.role,a.file,a.thread_ref)
        elif op=='commit':
            out=engine.commit(ws,a.job_id)
            import round_intelligence as rounds
            saved=rounds.refresh(ws)
            recorded=rounds.record_cycle_baseline(ws)
            out={**out,'round_reports_new':saved['new_reports'],'cycle_evidence_baseline':recorded['status']}
        elif op=='status':out=status(ws)
        elif op=='next-reading':out=engine.next_reading(ws,config(ws))
        elif op=='search-plan':out=engine.search_plan(ws)
        elif op=='report':out=engine.report(ws)
        elif op=='budget':out=budget(ws,config(ws))
        elif op=='renew-budget':out=renew(ws,a.label,a.authorized)
        elif op=='tune':out=patch(ws,store.read(a.file))
        elif op=='experiment-feedback':out=feedback.ingest(ws,store.read(a.file),store.read(a.review_file))
        elif op=='harness-propose':out=harness.propose(ws,store.read(a.file),a.reason,a.task_ref,config(ws),a.proposer_thread_ref)
        elif op=='harness-probe':out=harness.probe(ws,a.proposal_id,config(ws))
        elif op=='harness-adopt':out=harness.adopt(ws,a.proposal_id,store.read(a.file),config(ws))
        elif op=='harness-rollback':out=harness.rollback(ws,a.reason,a.authorized)
        else:raise ValueError('Unsupported operation')
        print(store.dump(out));return 0
    except (ValueError,RuntimeError,KeyError,TypeError,OSError) as e:
        print(store.dump({'status':'PAUSED_BUDGET' if isinstance(e,BudgetPause) else 'BLOCKED','error':str(e),'command':a.op}),file=sys.stderr)
        return 2
if __name__=='__main__':raise SystemExit(execute())
