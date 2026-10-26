#!/usr/bin/env python3
"""Conservative, file-backed Codex Desktop dispatch reservation ledger.

These are local *proxy* budgets for requested native subagents / prompt chars,
not OpenAI usage metering and not a guarantee that a Pro 5x plan suffices.
Reserving *before* dispatch prevents the v4.3 receipt-only overrun failure.
"""
from __future__ import annotations
import contextlib
import json
import os
import pathlib
import re
import time
from typing import Any
import deepread as core

DEFAULT={
    'profile':'economy',
    'max_assignments_per_cycle':40,
    'max_prompt_chars_per_cycle':1100000,
    'local_synthesis':True,
    'risk_review_for_s2':True,
}
class QuotaExceeded(ValueError):pass

def validate(cfg:dict)->dict:
    if not isinstance(cfg,dict) or set(cfg)!=set(DEFAULT):
        raise ValueError('Local assignment budget or reserved quota check failed at quota_guard.validate (check 29). Save the checkpoint before resuming.')
    if cfg['profile'] not in ('economy','balanced','strict'):
        raise ValueError('budget.profile must be economy/balanced/strict')
    for k,lo,hi in [('max_assignments_per_cycle',1,300000),('max_prompt_chars_per_cycle',1000,500000000)]:
        if type(cfg[k]) is not int or not lo<=cfg[k]<=hi:
            raise ValueError('Local assignment budget or reserved quota check failed at quota_guard.validate (check 34). Save the checkpoint before resuming.')
    for k in ('local_synthesis','risk_review_for_s2'):
        if type(cfg[k]) is not bool:raise ValueError('native.budget.'+k+' must be boolean')
    return cfg

def path(ws:pathlib.Path)->pathlib.Path:
    return ws/'output'/'native'/'budget_ledger.json'

def _empty():
    return {'version':1,'active_cycle':'cycle-001','cycles':{'cycle-001':{'reservations':{},'created_at':core.ts()}},'renewal_history':[]}

def _load(ws:pathlib.Path):
    p=path(ws)
    if not p.exists():
        # Upgrade safety: old v4.3 *verified* reports may already have consumed
        # this real usage window. Conservatively count them until the user
        # explicitly opens a new cycle. Never silently grant a fresh allowance.
        d=_empty()
        folder=ws/'output'/'native'/'tasks'
        if folder.exists():
            rs=d['cycles'][d['active_cycle']]['reservations']
            for f in folder.glob('*/receipts/*.json'):
                key=f'{f.parent.parent.name}:reader:{f.stem}'
                prompt=f.parent.parent/'prompts'/(f.stem+'.md')
                sz=len(prompt.read_text('utf8')) if prompt.is_file() else 0
                rs[key]={'reserved_prompt_chars':sz,'reserved_at':'PRE_V44_UNKNOWN',
                         'status':'LEGACY_RECEIPT_IMPORTED_UNKNOWN_REAL_CYCLE'}
            for f in folder.glob('*/captain_receipt.json'):
                try:role=core.jread(f).get('role','bpd_lead_sol')
                except Exception:role='bpd_lead_sol'
                key=f'{f.parent.name}:captain:{role}'
                prompt=f.parent/'captain_prompt.md'
                sz=len(prompt.read_text('utf8')) if prompt.is_file() else 0
                rs[key]={'reserved_prompt_chars':sz,'reserved_at':'PRE_V44_UNKNOWN',
                         'status':'LEGACY_CAPTAIN_IMPORTED_UNKNOWN_REAL_CYCLE'}
        return d
    d=core.jread(p)
    if d.get('version')!=1 or d.get('active_cycle') not in d.get('cycles',{}):
        raise RuntimeError('Input, evidence or workflow invariant failed at quota_guard._load (check 72); inspect the signed task record and original source.')
    return d

@contextlib.contextmanager
def _locked(ws:pathlib.Path):
    folder=ws/'output'/'native';folder.mkdir(parents=True,exist_ok=True)
    lock=folder/'.budget-atomic-lock'
    held=False
    for _ in range(80):
        try:
            lock.mkdir();held=True;break
        except FileExistsError:time.sleep(.05)
    if not held:
        raise RuntimeError('Input, evidence or workflow invariant failed at quota_guard._locked (check 85); inspect the signed task record and original source.')
    try:yield
    finally:
        try:lock.rmdir()
        except OSError:pass

def status(ws:pathlib.Path,conf:dict)->dict:
    validate(conf)
    d=_load(ws)
    reservations=d['cycles'][d['active_cycle']]['reservations']
    used=len(reservations)
    chars=sum(x['reserved_prompt_chars'] for x in reservations.values())
    lifetime=sum(len(c['reservations']) for c in d['cycles'].values())
    return {'active_cycle':d['active_cycle'],'budget_profile':conf['profile'],
            'reserved_assignments':used,'max_assignments':conf['max_assignments_per_cycle'],
            'remaining_assignments':max(0,conf['max_assignments_per_cycle']-used),
            'reserved_prompt_chars':chars,'max_prompt_chars':conf['max_prompt_chars_per_cycle'],
            'remaining_prompt_chars':max(0,conf['max_prompt_chars_per_cycle']-chars),
            'lifetime_reserved_assignments':lifetime,
            'warning':'Research evidence and workflow notes (quota_guard.status). Use original source evidence; keep frozen constraints and independent quality gates.'}

def reserve(ws:pathlib.Path,conf:dict,requests:dict[str,int])->dict:
    validate(conf)
    if not isinstance(requests,dict) or not requests:
        raise ValueError('Input, evidence or workflow invariant failed at quota_guard.reserve (check 109); inspect the signed task record and original source.')
    for key,v in requests.items():
        if not isinstance(key,str) or len(key)>260 or type(v) is not int or v<0:
            raise ValueError('Signed task, stage, commit receipt or report provenance check failed at quota_guard.reserve (check 112). Resume only from a verified state.')
    with _locked(ws):
        d=_load(ws)
        rs=d['cycles'][d['active_cycle']]['reservations']
        for k,n in requests.items():
            if k in rs and rs[k]['reserved_prompt_chars']!=n:
                raise ValueError('Local assignment budget or reserved quota check failed at quota_guard.reserve (check 118). Save the checkpoint before resuming.')
        new={k:n for k,n in requests.items() if k not in rs}
        if len(rs)+len(new)>conf['max_assignments_per_cycle']:
            raise QuotaExceeded('Local assignment budget or reserved quota check failed at quota_guard.reserve (check 121). Save the checkpoint before resuming.')
        total=sum(x['reserved_prompt_chars'] for x in rs.values())+sum(new.values())
        if total>conf['max_prompt_chars_per_cycle']:
            raise QuotaExceeded('Local assignment budget or reserved quota check failed at quota_guard.reserve (check 125). Save the checkpoint before resuming.')
        for k,n in new.items():
            rs[k]={'reserved_prompt_chars':n,'reserved_at':core.ts(),'status':'DISPATCH_RESERVED_NOT_BILLED_USAGE'}
        if new:core.jwrite(path(ws),d)
    return status(ws,conf)

def renew(ws:pathlib.Path,conf:dict,label:str,*,user_authorized:bool=False)->dict:
    validate(conf)
    if not user_authorized:
        raise ValueError('Input, evidence or workflow invariant failed at quota_guard.renew (check 135); inspect the signed task record and original source.')
    if not isinstance(label,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{2,60}',label):
        raise ValueError('Input, evidence or workflow invariant failed at quota_guard.renew (check 137); inspect the signed task record and original source.')
    with _locked(ws):
        d=_load(ws)
        if label in d['cycles']:
            raise ValueError('Input, evidence or workflow invariant failed at quota_guard.renew (check 141); inspect the signed task record and original source.')
        prior=d['active_cycle']
        d['cycles'][label]={'reservations':{},'created_at':core.ts()}
        d['active_cycle']=label
        d['renewal_history'].append({'from':prior,'to':label,'time':core.ts(),
                                      'assurance':'OPERATOR_SAID_REAL_QUOTA_RENEWED_NOT_PROVIDER_ATTESTED'})
        core.jwrite(path(ws),d)
    return status(ws,conf)


def has_reservation(ws:pathlib.Path,key:str)->bool:
    d=_load(ws)
    return any(key in cycle['reservations'] for cycle in d['cycles'].values())

def ensure_existing_or_expand(ws:pathlib.Path,conf:dict,key:str,new_size:int)->dict:
    validate(conf)
    with _locked(ws):
        d=_load(ws)
        for cycle in d['cycles'].values():
            if key in cycle['reservations']:
                old=cycle['reservations'][key]['reserved_prompt_chars']
                if new_size<=old:return status(ws,conf)
                # A reservation made in a previous cycle does not gain fresh spend capacity
                # automatically, but existing dispatch remains accepted.
                if cycle is d['cycles'][d['active_cycle']]:
                    current=sum(x['reserved_prompt_chars'] for x in cycle['reservations'].values())
                    if current-old+new_size>conf['max_prompt_chars_per_cycle']:
                        raise QuotaExceeded('Local assignment budget or reserved quota check failed at quota_guard.ensure_existing_or_expand (check 168). Save the checkpoint before resuming.')
                    cycle['reservations'][key]['reserved_prompt_chars']=new_size
                    core.jwrite(path(ws),d)
                return status(ws,conf)
    # unreserved old task is not free: first request a fresh slot explicitly
    return reserve(ws,conf,{key:new_size})


def plan(ws:pathlib.Path,conf:dict)->dict:
    """Lower-bound estimate in *native requests*, not subscription charges.

    Before selection, paper length estimate comes from the candidate median;
    no eligibility or token consumption claims are made.
    """
    validate(conf)
    from statistics import median
    import math
    import batch
    path_state=ws/'output'/'batch'/'state.json'
    out={'status':'NOT_INGESTED','budget':status(ws,conf)}
    if not path_state.is_file():
        core.jwrite(ws/'output'/'native'/'budget_plan.json',out)
        return out
    state=batch.load_state(ws)
    selection=batch.cfg_at(ws)
    readcfg=core.config_for(ws)
    all_ready=batch.available(state)
    groups=len(state['groups'])
    # Group count includes supplementary batches; the estimate assumes no new additions.
    native_s1=1 if conf['profile']=='economy' else (2 if conf['profile']=='balanced' else 3)
    native_s2=native_s1
    existing_screen=groups*(native_s1+native_s2)
    stages_completed=sum(1 for g in state['groups'] for stage in ('S1','S2')
                         if batch.screen_path(ws,batch.stage_jid(stage,g),'receipts').is_file())
    remaining_screen=max(0,existing_screen-stages_completed*native_s1)
    chosen=state.get('selection',{}).get('last_selected',[])
    core_count=len(chosen) if chosen else min(selection['core_target'],len(all_ready))
    def pages_size(p):
        try:
            return len(''.join(core.jread(batch.corpus_path(ws,p['id']))['pages']))
        except (OSError,ValueError,KeyError):return 0
    sample=[pages_size(p) for p in all_ready[:min(len(all_ready),50)]]
    sample=[n for n in sample if n]
    rough_chunks=max(1,math.ceil(median(sample)/readcfg['chunk_chars'])) if sample else 2
    if state.get('frozen'):
        try:
            ctx=core.env(pathlib.Path(state['frozen']['core_workspace']))
            core_count=len(ctx['paper_ids'])
            chunks=sum(len(core.paper_chunks(ctx,p)) for p in ctx['paper_ids'])
        except Exception:
            chunks=core_count*rough_chunks
    else:
        chunks=core_count*rough_chunks
    rounds=readcfg['rounds']
    if conf['profile']=='economy':
        # Per fragment: R1/R2/R3/R5=1, R4=2. 6 calls for the first five rounds.
        leaf_per_chunk=rounds+1
    elif conf['profile']=='balanced':leaf_per_chunk=rounds*2+2
    else:leaf_per_chunk=rounds*3
    leaves=chunks*leaf_per_chunk
    # Real analytic grouping remains a model task. If only one group, the
    # master is a deterministic copy with citations intact.
    groups_per_round=math.ceil(core_count/readcfg['group_size']) if core_count else 0
    group_synthesis=groups_per_round*rounds
    master=rounds if groups_per_round>1 else 0
    merge_fallback='variable: local compilation needs >=2 independently anchored observations'
    native_path=ws/'native_config.json'
    native=core.jread(native_path) if native_path.exists() else {}
    cross_cfg=native.get('cross_domain',{})
    cross=(4*cross_cfg.get('max_papers_total',0) if cross_cfg.get('enabled',False) else 0)
    # Bound by cross-domain explicit total assignment cap.
    cross=min(cross,cross_cfg.get('max_model_assignments',cross))
    lower=existing_screen+leaves+group_synthesis+master+1+2+cross
    remaining_lower=remaining_screen+leaves+group_synthesis+master+1+2+cross
    out={'status':'LOWER_BOUND_PLAN','candidate_papers':len(all_ready),'screening_batches':groups,
         'screening_two_pass_reader_assignments':existing_screen,
         'screening_stages_completed':stages_completed,'remaining_base_screening_assignments':remaining_screen,
         'core_papers_estimate':core_count,'assumed_chunks_per_core_paper':round(chunks/max(1,core_count),2),
         'core_leaf_reader_assignments_estimate':leaves,'core_group_and_master_calls':group_synthesis+master,
         'final_and_independent_audit_calls_min':3,
         'cross_domain_calls_assumed':cross,'estimated_min_total_assignments':lower,
         'estimated_min_unfinished_assignments_before_core_progress':remaining_lower,
         'available_assignment_proxy_units_this_cycle':status(ws,conf)['remaining_assignments'],
         'cycle_sufficiency_check':'BELOW_ESTIMATED_NEED' if remaining_lower>status(ws,conf)['remaining_assignments'] else 'ONLY_PROXY_SUFFICIENCY_NOT_PROVIDER_GUARANTEE',
         'extra_calls':'Core estimate includes even already completed core rounds; screening uses unfinished stages. S2 risk second opinion / disagreement captain / some merges / retries / finding new papers / re-audits not included',
         'source':'local indexed candidate lengths and current selected-count; does NOT observe real Codex plan usage',
         'budget':status(ws,conf)}
    core.jwrite(ws/'output'/'native'/'budget_plan.json',out)
    return out
