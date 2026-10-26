#!/usr/bin/env python3
"""Task-aware zero-LLM-overhead Codex model router.

It chooses an *explicit requested* model and reasoning level using job type,
role, prompt length, attempt count, recorded dispute marker and vetted probe
availability. No model availability or backend identity is inferred from names.
All user-editable knobs are in router_config.json and can be prompt-overridden.
"""
from __future__ import annotations
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

import deepread as core

ROOT=Path(__file__).resolve().parents[1]
TEMPLATE=core.jread(ROOT/'router_config.example.json')
TIERS=['economy','balanced','deep']
LEVELS=['routine','standard','difficult','critical']
STAGES={'S1','S2','MERGE','GROUP','MASTER','FINAL','AUDIT','R_default',*[f'R{i}' for i in range(1,41)]}
MODEL_RE=re.compile(r'^[a-zA-Z0-9._:/-]{1,150}$')


def load(ws:Path) ->dict:
    path=ws/'router_config.json'
    c=core.jread(path) if path.exists() else TEMPLATE
    if c.get('schema_version')!=4 or c.get('mode') not in ('adaptive','fixed'):
        raise ValueError('router.schema_versionmust be4; modeonly canadaptive/fixed')
    for tier in TIERS:
        val=c.get('models',{}).get(tier)
        if not isinstance(val,str) or not MODEL_RE.fullmatch(val):
            raise ValueError('router.models.'+tier+'Input, evidence or workflow invariant failed at smart_router.load (check 34); inspect the signed task record and original source.')
    for key in LEVELS:
        if c.get('efforts',{}).get(key) not in ('low','medium','high','xhigh'):
            raise ValueError('router.efforts.'+key+' invalid')
    bounds={'large_screen_prompt_chars':(5000,300000),
            'large_leaf_prompt_chars':(5000,500000),
            'very_long_prompt_chars':(10000,1500000), 'retry_escalate_from':(2,6)}
    for name,(lo,hi) in bounds.items():
        val=c.get('thresholds',{}).get(name)
        if type(val) is not int or not lo<=val<=hi:
            raise ValueError('router.thresholds.'+name+'Signed task, stage, commit receipt or report provenance check failed at smart_router.load (check 44). Resume only from a verified state.')
    for name,options in (('role_pins',None),('stage_pins',STAGES)):
        pins=c.get(name)
        if not isinstance(pins,dict) or len(pins)>100:
            raise ValueError(name+'Input, evidence or workflow invariant failed at smart_router.load (check 48); inspect the signed task record and original source.')
        for key,value in pins.items():
            if not re.fullmatch(r'[A-Za-z0-9_\-]{1,65}',key) or (options and key not in options):
                raise ValueError(name+'Input, evidence or workflow invariant failed at smart_router.load (check 51); inspect the signed task record and original source.'+key)
            if not isinstance(value,dict) or not value or set(value)-{'model','effort','tier','level'}:
                raise ValueError('Input, evidence or workflow invariant failed at smart_router.load (check 53); inspect the signed task record and original source.')
            if 'model' in value and (not isinstance(value['model'],str) or not MODEL_RE.fullmatch(value['model'])):
                raise ValueError(f'{name}.{key}.modelinvalid')
            if 'effort' in value and value['effort'] not in ('low','medium','high','xhigh'):
                raise ValueError(f'{name}.{key}.effortinvalid')
            if 'tier' in value and value['tier'] not in TIERS:
                raise ValueError(f'{name}.{key}.tierinvalid')
            if 'level' in value and value['level'] not in LEVELS:
                raise ValueError(f'{name}.{key}.levelinvalid')
    av=c.get('availability',{})
    for k in ('require_live_probe','allow_verified_fallback','allow_critical_downgrade'):
        if type(av.get(k)) is not bool:raise ValueError('router.availability.'+k+'must be boolean')
    if type(av.get('max_probe_age_hours')) is not int or not 1<=av['max_probe_age_hours']<=720:
        raise ValueError('router.availability.max_probe_age_hours invalid')
    e=c.get('efficiency',{})
    if e.get('leaf_captain_strategy') not in ('adaptive','always','paper_only'):
        raise ValueError('router.efficiency.leaf_captain_strategymust beadaptive/always/paper_only')
    if e.get('screen_captain_strategy') not in ('adaptive','always'):
        raise ValueError('router.efficiency.screen_captain_strategymust beadaptive/always')
    x=e.get('screen_consensus_max_score_spread')
    if type(x) not in (int,float) or not 0<=x<=2.0:raise ValueError('invalid ofscore spread')
    x=e.get('screen_consensus_min_evidence_quality')
    if type(x) not in (int,float) or not 0<=x<=5:raise ValueError('Authentic source, page quotation or evidence integrity check failed at smart_router.load (check 75). Never accept unverified material.')
    if type(e.get('screen_consensus_require_no_uncertainty')) is not bool:raise ValueError('Authentic source, page quotation or evidence integrity check failed at smart_router.load (check 76). Never accept unverified material.')
    x=e.get('core_parallel_leaf_jobs')
    if type(x) is not int or not 1<=x<=32:raise ValueError('Local assignment budget or reserved quota check failed at smart_router.load (check 78). Save the checkpoint before resuming.')
    weights=e.get('relative_model_cost_weights',{})
    if set(weights)!=set(TIERS) or any(type(weights[k]) not in (int,float) or weights[k]<=0 for k in TIERS):
        raise ValueError('Local assignment budget or reserved quota check failed at smart_router.load (check 81). Save the checkpoint before resuming.')
    return c


def stage_for(jid:str,role:str)->str:
    if jid.startswith('S1_'):return 'S1'
    if jid.startswith('S2_'):return 'S2'
    if jid.startswith('AUDIT_'):return 'AUDIT'
    if jid.startswith('FINAL_'):return 'FINAL'
    m=re.match(r'^R\d\d_',jid)
    if m:
        if jid.endswith('_MERGE'):return 'MERGE'
        if jid.endswith('_GROUP'):return 'GROUP'
        if jid.endswith('_MASTER'):return 'MASTER'
        round_id=int(jid[1:3])
        return f'R{round_id}' if round_id<=40 else 'R_default'
    return 'R_default'


def _baseline(stage:str,role:str)->tuple[str,str]:
    # Always vary by task, *then* by identity. This prevents the launcher model
    # or role-only static assignments from taking over all reading rounds.
    if stage=='S1':
        if role in ('topic','transfer'):return ('economy','routine' if role=='topic' else 'standard')
        if role=='skeptic':return ('balanced','standard')
        if role=='screen_captain':return ('economy','standard')
        return ('balanced','standard')
    if stage=='S2':
        if role=='screen_captain':return ('balanced','standard')
        if role=='skeptic':return ('balanced','difficult')
        return ('balanced','standard')
    if stage=='R1':
        return {'topic':('economy','standard'),'transfer':('balanced','standard'),
                'skeptic':('balanced','difficult'),'core_captain':('balanced','standard')}.get(role,('balanced','standard'))
    if stage=='R2':
        return {'method':('deep','difficult'),'reproducer':('balanced','standard'),
                'skeptic':('deep','difficult'),'core_captain':('balanced','difficult')}.get(role,('balanced','difficult'))
    if stage=='R3':
        return {'experimentalist':('balanced','difficult'),'reproducer':('balanced','standard'),
                'skeptic':('balanced','difficult'),'core_captain':('balanced','difficult')}.get(role,('balanced','standard'))
    if stage=='R4':
        return {'skeptic':('deep','critical'),'method':('deep','difficult'),
                'experimentalist':('balanced','difficult'),'core_captain':('deep','difficult')}.get(role,('deep','difficult'))
    if stage=='R5':
        return {'synthesist':('balanced','difficult'),'transfer':('balanced','standard'),
                'skeptic':('deep','difficult'),'core_captain':('balanced','difficult')}.get(role,('balanced','difficult'))
    if stage=='AUDIT':
        return ('deep','critical') if role=='audit_methods' else ('balanced','difficult')
    if stage=='FINAL':return ('deep','critical')
    if stage=='MASTER':return ('deep','difficult')
    if stage=='GROUP':return ('balanced','standard')
    if stage=='MERGE':return ('balanced','standard')
    if stage=='R_default':return ('balanced','difficult')
    return ('balanced','standard')


def _live_probe(ws:Path,conf:dict)->dict:
    path=ws/'output'/'router'/'probe.json'
    if not path.is_file() and ws.parent.name=='core_runs' and ws.parent.parent.name=='batch':
        parent=ws.parents[3]
        path=parent/'output'/'router'/'probe.json'
    if not path.is_file():return {}
    try:
        result=core.jread(path)
        stamp=dt.datetime.fromisoformat(result['time'])
        age=dt.datetime.now(dt.timezone.utc)-stamp.astimezone(dt.timezone.utc)
        if not 0<=age.total_seconds()<=conf['availability']['max_probe_age_hours']*3600:
            return {}
        return result.get('models',{}) if isinstance(result.get('models'),dict) else {}
    except Exception:return {}


def choose(ws:Path,role:str,jid:str,prompt:str,attempt:int, *,fixed_model:str='',fixed_effort:str='')->dict:
    conf=load(ws)
    stage=stage_for(jid,role)
    if conf['mode']=='fixed':
        if not fixed_model or not MODEL_RE.fullmatch(fixed_model) or fixed_effort not in ('low','medium','high','xhigh'):
            raise RuntimeError('Independent native research-agent identity or reviewer evidence failed validation at smart_router.choose (check 158).')
        tier=next((k for k,v in conf['models'].items() if v==fixed_model),'custom')
        model,effort=fixed_model,fixed_effort
        reason=['FIXED_ROLE_MODEL']
        level='custom'
    else:
        tier,level=_baseline(stage,role)
        reason=[f'TASK={stage}',f'IDENTITY={role}']
        threshold=conf['thresholds']
        if (stage in ('S1','S2') and len(prompt)>=threshold['large_screen_prompt_chars']) or (stage.startswith('R') and len(prompt)>=threshold['large_leaf_prompt_chars']):
            level=LEVELS[min(3,LEVELS.index(level)+1)]
            reason.append('LONG_INPUT')
        if len(prompt)>=threshold['very_long_prompt_chars']:
            tier=TIERS[min(2,TIERS.index(tier)+1)]
            level=LEVELS[min(3,LEVELS.index(level)+1)]
            reason.append('VERY_LONG_INPUT')
        if '[[ROUTE_SIGNAL:DISPUTE]]' in prompt:
            tier='deep'
            level='critical' if stage in ('R4','AUDIT','FINAL') else 'difficult'
            reason.append('EVIDENCE_DISPUTE')
        if attempt>=threshold['retry_escalate_from']:
            tier=TIERS[min(2,TIERS.index(tier)+1)]
            level=LEVELS[min(3,LEVELS.index(level)+1)]
            reason.append('EVIDENCE_RETRY_ESCALATION')
        pin=conf['stage_pins'].get(stage,{})
        if role in conf['role_pins']:
            pin={**pin,**conf['role_pins'][role]}
        if pin:
            tier=pin.get('tier',tier)
            level=pin.get('level',level)
            reason.append('USER_PROMPT_PIN')
        model=pin.get('model',conf['models'][tier])
        if 'model' in pin:
            tier=next((name for name,target in conf['models'].items() if target==model),'custom')
            reason.append('EXPLICIT_MODEL_PIN')
        effort=pin.get('effort',conf['efforts'][level])
    status=_live_probe(ws,conf)
    if conf['availability']['require_live_probe'] and status.get(model,{}).get('status') not in ('available','unavailable'):
        raise RuntimeError('Input, evidence or workflow invariant failed at smart_router.choose (check 196); inspect the signed task record and original source.')
    selected=model
    if status and status.get(model,{}).get('status')=='unavailable':
        if not conf['availability']['allow_verified_fallback']:
            raise RuntimeError('Input, evidence or workflow invariant failed at smart_router.choose (check 200); inspect the signed task record and original source.')
        if 'EXPLICIT_MODEL_PIN' in reason and not conf['availability']['allow_critical_downgrade']:
            raise RuntimeError('Signed task, stage, commit receipt or report provenance check failed at smart_router.choose (check 202). Resume only from a verified state.')
        if tier=='custom':
            raise RuntimeError('Signed task, stage, commit receipt or report provenance check failed at smart_router.choose (check 204). Resume only from a verified state.')
        # Only choose a *live verified* alternative. Never silently downgrade
        # rigorous audit / mathematically demanding stages by default.
        is_critical=(level=='critical' or effort=='xhigh' or stage in ('AUDIT','FINAL','R4'))
        try:tier_index=TIERS.index(tier)
        except ValueError:tier_index=2
        ordered=sorted(TIERS,key=lambda t:(abs(TIERS.index(t)-tier_index),-TIERS.index(t)))
        allowed=[t for t in ordered if conf['availability']['allow_critical_downgrade'] or not is_critical or TIERS.index(t)>=tier_index]
        replacement=next((conf['models'][t] for t in allowed if status.get(conf['models'][t],{}).get('status')=='available'),None)
        if not replacement:
            raise RuntimeError('Signed task, stage, commit receipt or report provenance check failed at smart_router.choose (check 214). Resume only from a verified state.')
        model=replacement
        reason.append('VERIFIED_FALLBACK_FROM_'+selected)
    return {'job':jid,'role':role,'stage':stage,'requested_model':model,'requested_effort':effort,
            'tier':tier,'difficulty':level,'reason':reason,'probe_status':status.get(model,{}).get('status','NOT_PROBED'),
            'model_primary':selected,'router_mode':conf['mode']}


def estimate(ws:Path,number:int=1,stage:str='S1')->dict:
    c=load(ws)
    def w(tier):return c['efficiency']['relative_model_cost_weights'][tier]
    rosters={'S1':['topic','transfer','skeptic'],'S2':['method','experimentalist','skeptic'],
             'R1':['topic','transfer','skeptic'],'R2':['method','reproducer','skeptic'],
             'R3':['experimentalist','reproducer','skeptic'],'R4':['skeptic','method','experimentalist'],
             'R5':['synthesist','transfer','skeptic']}
    members=rosters.get(stage,rosters['S1'])
    tiers=[_baseline(stage,role)[0] for role in members]
    lead='screen_captain' if stage.startswith('S') else 'core_captain'
    cost=sum(w(t) for t in tiers)
    leaf_policy=c['efficiency']['leaf_captain_strategy']
    minimum_captain=0 if (stage.startswith('S') and c['efficiency']['screen_captain_strategy']=='adaptive') or (stage in ('R1','R3','R5') and leaf_policy=='adaptive') or (stage.startswith('R') and leaf_policy=='paper_only') else number
    return {'stage':stage,'jobs':number,'reader_calls':number*len(tiers),
            'reader_relative_weight_units':round(number*cost,1),
            'captain_calls_max':number,'captain_calls_min':minimum_captain,
            'captain_relative_weight_units_max':number*w(_baseline(stage,lead)[0]),
            'note':'Research evidence and workflow notes (smart_router.estimate). Use original source evidence; keep frozen constraints and independent quality gates.'}


def academic_snapshot(c:dict)->dict:
    """Screening consensus rules influence decisions and are campaign-immutable."""
    e=c['efficiency']
    return {k:e[k] for k in ('screen_captain_strategy',
        'screen_consensus_max_score_spread','screen_consensus_min_evidence_quality',
        'screen_consensus_require_no_uncertainty')}
