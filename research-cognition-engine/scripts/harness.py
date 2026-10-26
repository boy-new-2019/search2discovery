#!/usr/bin/env python3
"""Harness²-inspired evidence-bounded Propose / Probe / Compose.

This is an adaptation, not Google's Harness² code. Never modifies source,
scientific guardrails, experiments, frozen goals, or benchmark labels.
"""
from __future__ import annotations
import copy,json,pathlib,math
from typing import Any
import store

WEIGHTS=('relevance','uncertainty','coverage','recency','cost')
LIMITS={name:(0.05,5.0) for name in WEIGHTS}

def root(ws:pathlib.Path)->pathlib.Path:return store.root(ws)/'harness_evolution'
def statefile(ws:pathlib.Path)->pathlib.Path:return root(ws)/'state.json'

def state(ws:pathlib.Path)->dict:
    f=statefile(ws)
    if not f.exists():store.write(f,{'revision':0,'proposals':{},'probes':{},'adopted':[],'lessons':[],'rejected':[]})
    return store.read(f)

def validate_patch(patch:dict)->None:
    if not isinstance(patch,dict) or set(patch)!={'ranking'} or not isinstance(patch['ranking'],dict) or not patch['ranking']:
        raise ValueError('Only allowlisted ranking weights can evolve; no source/guardrail/benchmark edits')
    if set(patch['ranking'])-set(WEIGHTS):raise ValueError('Cannot edit protected/non-ranking fields')
    for k,v in patch['ranking'].items():
        if type(v) not in (float,int) or not LIMITS[k][0]<=v<=LIMITS[k][1]:
            raise ValueError(f'Invalid weight {k}: outside preapproved bounds')

def propose(ws:pathlib.Path,patch:dict,reason:str,prior_task_ids:list[str],cfg:dict,proposer_thread_ref:str)->dict:
    if not cfg['propose_probe_compose']['enabled']:raise ValueError('Harness evolution disabled')
    if cfg['propose_probe_compose']['k']!=1:raise ValueError('Only one bounded trial at a time permitted')
    validate_patch(patch)
    if not isinstance(proposer_thread_ref,str) or len(proposer_thread_ref.strip())<5:
        raise ValueError('Must reference an actual independent proposal-generating Codex Desktop thread')
    if len(reason.strip())<25 or not prior_task_ids or not all(isinstance(x,str) and len(x)>3 for x in prior_task_ids):
        raise ValueError('An experience-supported proposal requires a detailed reason and prior task IDs')
    # Do not credit imagined/reflection-only failures. The proposed harness
    # modification must reference an actual committed task/event from this
    # workspace, or a signed legacy native task receipt.
    import engine
    known=set()
    st=store.root(ws)/'engine_state.json'
    if st.exists():
        for row in store.read(st)['cycles']:
            known.update(f"{row['id']}_{name}" for name in row['completed_stages'])
    path=ws/'output'/'native'/'tasks'
    if path.is_dir():
        known.update(x.parent.name for x in path.glob('*/commit.json'))
    if not any(x in known for x in prior_task_ids):
        raise ValueError('No actual committed task behind the proposed improvement; introspective guesses are not training evidence')
    cands={**cfg['ranking'],**patch['ranking']}
    if cands==cfg['ranking']:raise ValueError('No effective harness change')
    s=state(ws)
    if any(p.get('status') in ('PROPOSED','PROBED') for p in s['proposals'].values()):
        raise ValueError('An unreviewed candidate exists; do not spawn unbounded recursive trials')
    pid='HP-'+store.hashobj({'patch':patch,'reason':reason,'task_ids':prior_task_ids})[:16]
    if pid in s['proposals']:raise ValueError('Same proposal was already evaluated/rejected')
    s['proposals'][pid]={'candidate_patch':patch,'candidate_ranking':cands,
                         'baseline_ranking':cfg['ranking'],'baseline_cfg_sha256':store.hashobj(cfg),
                         'reason':reason,'prior_task_ids':prior_task_ids,'proposer_thread_ref':proposer_thread_ref,'status':'PROPOSED',
                         'created_at':store.utc()}
    store.write(statefile(ws),s)
    return {'status':'PROPOSED','proposal_id':pid,'sandbox_test_only':True,
            'permitted_changes':list(patch['ranking']), 'next':'harness-probe'}

def rank(items:list[dict],weights:dict)->list[str]:
    pairs=[]
    for x in items:
        score=sum(weights[name]*float(x.get(name,0))*(-1 if name=='cost' else 1) for name in WEIGHTS)
        pairs.append((score,x['id']))
    pairs.sort(key=lambda x:(-x[0],x[1]))
    return [x[1] for x in pairs]

def fixture_path()->pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[1]/'references'/'holdout_fixtures.json'

def bench(weights:dict,fixtures:dict|None=None)->dict:
    fixtures=fixtures if fixtures is not None else store.read(fixture_path())
    tests=fixtures.get('cases')
    if not isinstance(tests,list) or len(tests)<3:raise ValueError('Holdout fixture set too small')
    details=[];precisions=[];critical_recalls=[]
    for case in tests:
        items=case['items'];k=case['k'];wanted=set(case['relevant']);critical=set(case.get('critical',[]))
        if not wanted or not isinstance(k,int) or not 1<=k<=len(items):raise ValueError('Invalid fixture structure')
        ids=rank(items,weights)[:k]
        recall=len(wanted.intersection(ids))/len(wanted)
        critical_rec=len(critical.intersection(ids))/len(critical) if critical else 1.0
        details.append({'name':case['name'],'top_k':ids,'recall_at_k':recall,'critical_recall':critical_rec})
        precisions.append(recall);critical_recalls.append(critical_rec)
    return {'score':round(sum(precisions)/len(precisions),6),
            'critical_score':round(sum(critical_recalls)/len(critical_recalls),6),
            'per_case':details,'fixture_sha256':store.hashobj(fixtures),
            'interpretation':'Fixed offline priority ranking only; NOT scientific truth / LLM inference correctness'}

def probe(ws:pathlib.Path,proposal_id:str,cfg:dict)->dict:
    s=state(ws);p=s['proposals'].get(proposal_id)
    if not p or p['status']!='PROPOSED':raise ValueError('Proposal not in PROPOSED state')
    if store.hashobj(cfg)!=p['baseline_cfg_sha256']:
        raise ValueError('Current harness config changed while probing candidate')
    base=bench(p['baseline_ranking']);cand=bench(p['candidate_ranking'])
    floor=cfg['propose_probe_compose']['minimum_ranking_gain'];regress=cfg['propose_probe_compose']['max_canary_regression']
    delta=cand['score']-base['score'];critical_regression=base['critical_score']-cand['critical_score']
    cases=[(old['name'],old['recall_at_k']-new['recall_at_k'],old['critical_recall']-new['critical_recall'])
           for old,new in zip(base['per_case'],cand['per_case'])]
    critical_canary_ok=all(y<=regress for _,_,y in cases)
    approved=delta>=floor and critical_regression<=regress and critical_canary_ok
    result={'proposal_id':proposal_id,'baseline':base,'candidate':cand,'improvement':round(delta,6),
            'critical_regression':round(critical_regression,6),'canary_case_regressions':cases,
            'threshold':floor,'candidate_passed_offline_probe':approved,
            'heldout_fixture_sha256':base['fixture_sha256'],
            'warning':'No real Codex task executed; only offline prioritization fixtures were tested',
            'created_at':store.utc()}
    s['probes'][proposal_id]=result
    p['status']='PROBED'
    store.write(statefile(ws),s)
    store.write(root(ws)/'probes'/(proposal_id+'.json'),result)
    return result

def adopt(ws:pathlib.Path,proposal_id:str,review:dict,cfg:dict)->dict:
    s=state(ws);p=s['proposals'].get(proposal_id);probe_result=s['probes'].get(proposal_id)
    if not p or p['status']!='PROBED' or not probe_result:raise ValueError('No completed probe')
    if store.hashobj(cfg)!=p['baseline_cfg_sha256']:raise ValueError('Current config mismatch; no stale acceptance')
    if not isinstance(review,dict) or set(review)!={'proposal_id','reviewer_role','thread_ref','verdict','reason'}:
        raise ValueError('Independent evolution reviewer record required')
    if review['proposal_id']!=proposal_id or review['reviewer_role']!='rce_evolution_auditor_astra' or len(str(review['thread_ref']).strip())<5:
        raise ValueError('Need explicit independent native audit thread from rce_evolution_auditor_astra')
    if review['thread_ref']==p['proposer_thread_ref']:
        raise ValueError('Proposal and adoption auditor cannot be the same subagent thread')
    if review['verdict'] not in ('PASS','VETO') or len(str(review['reason']).strip())<25:
        raise ValueError('Independent evolution judgment inadequate')
    # Evidence and canary results outrank subjective judge preference.
    if not probe_result['candidate_passed_offline_probe'] or review['verdict']=='VETO':
        s['proposals'][proposal_id]['status']='REJECTED'
        s['rejected'].append({'proposal_id':proposal_id,'reason':review['reason'],
                             'probe_pass':probe_result['candidate_passed_offline_probe'],'date':store.utc()})
        store.write(statefile(ws),s)
        return {'status':'REJECTED','reason':'Probe failed or independent veto'}
    if store.hashobj(store.read(fixture_path()))!=probe_result['heldout_fixture_sha256']:
        raise ValueError('Protected offline fixtures changed; no adoption')
    # Do not rewrite ranking while an RCE task manifest is already dispatched.
    import engine
    es=engine.get_state(ws)
    if es['cycles'] and es['cycles'][-1]['stage']!='COMPLETE':
        active=engine.taskdir(ws,es['cycles'][-1]['id']+'_'+es['cycles'][-1]['stage'])/'manifest.json'
        if active.exists():raise ValueError('An in-flight cognition task would have a stale harness context; complete it before adopting')
    new=copy.deepcopy(cfg)
    new['ranking']=p['candidate_ranking']
    path=ws/'research_cognition_config.json'
    previous_path=root(ws)/'versions'/f'harness-r{s["revision"]:03d}.json'
    store.write(previous_path,cfg)
    store.write(path,new)
    s['revision']+=1
    s['proposals'][proposal_id]['status']='ADOPTED'
    s['adopted'].append({'revision':s['revision'],'proposal_id':proposal_id,
                         'reviewer_thread_ref':review['thread_ref'],
                         'probe_sha256':store.hashobj(probe_result),'date':store.utc()})
    s['lessons'].append({'proposal_id':proposal_id,'task_refs':p['prior_task_ids'],
                         'supported_improvement':probe_result['improvement'],
                         'limited_to':'offline task prioritization',
                         'lesson':p['reason'], 'created_at':store.utc()})
    store.write(statefile(ws),s)
    return {'status':'ADOPTED','version':s['revision'], 'protected_frozen_research_unchanged':True,
            'changed_only':'research_cognition_config.ranking','next':'research reading tasks; monitor real task results for regression'}

def rollback(ws:pathlib.Path,reason:str,authorized:bool)->dict:
    if not authorized or len(reason.strip())<15:raise ValueError('Rollback requires explicit rationale and authorization')
    s=state(ws)
    if not s['adopted']:raise ValueError('No harness version to roll back')
    current_revision=s['revision']
    backup=root(ws)/'versions'/f'harness-r{current_revision-1:03d}.json'
    if not backup.is_file():raise ValueError('Backed-up original harness missing')
    cfg=store.read(backup)
    store.write(ws/'research_cognition_config.json',cfg)
    s['revision']=current_revision-1
    s['adopted'].pop()
    s['lessons'].append({'event':'ROLLBACK','from_revision':current_revision,
                         'reason':reason,'created_at':store.utc()})
    store.write(statefile(ws),s)
    return {'status':'ROLLED_BACK','revision':s['revision'],'reason':reason}
