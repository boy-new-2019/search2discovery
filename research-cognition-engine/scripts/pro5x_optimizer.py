#!/usr/bin/env python3
"""Pro 5x survival preset for RCE integrated Windows Codex Desktop project.

Operates on local configuration only. Does NOT call any model/network, assert real
provider usage, or renew the external quota. Never weakens source/independent
review/5-round/final-veto gates. Original v4.4 source is never edited.
"""
from __future__ import annotations
import argparse, copy, datetime as dt, hashlib, json, math, pathlib, shutil, sys
from typing import Any

PROFILE='pro5x_survival_v64'
ASSIGNMENTS=12
PROMPT_CHARS=420000
RCE_ASSIGNMENTS=4
RCE_CHARS=160000


def read(p:pathlib.Path)->dict:
    return json.loads(p.read_text('utf-8'))

def write(p:pathlib.Path,obj:Any):
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+'.pro5x_tmp')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    tmp.replace(p)

def sha(p:pathlib.Path)->str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

def locations(ws:pathlib.Path)->dict[str,pathlib.Path]:
    return {'native':ws/'native_config.json',
            'rce':ws/'research_cognition_config.json',
            'selection':ws/'selection_config.json',
            'reader':ws/'reading_config.json'}

def current_budget(ws:pathlib.Path)->dict:
    p=ws/'output'/'native'/'budget_ledger.json'
    if not p.exists():return {'active_cycle':'UNINITIALIZED','assignments':0,'prompt_chars':0}
    s=read(p); a=s['active_cycle']; requests=s['cycles'][a]['reservations']
    return {'active_cycle':a,'assignments':len(requests),
            'prompt_chars':sum(x['reserved_prompt_chars'] for x in requests.values())}

def rce_budget(ws:pathlib.Path)->dict:
    p=ws/'output'/'research_cognition'/'local_model_budget.json'
    if not p.exists():return {'active_period':'UNINITIALIZED','assignments':0,'prompt_chars':0}
    s=read(p);a=s['active_period']; requests=s['periods'][a]['requests']
    return {'active_period':a,'assignments':len(requests),
            'prompt_chars':sum(x['prompt_chars'] for x in requests.values())}

def active_reader(ws:pathlib.Path)->bool:
    return (ws/'output'/'batch'/'state.json').exists()

def active_rce(ws:pathlib.Path)->bool:
    f=ws/'output'/'research_cognition'/'engine_state.json'
    if not f.is_file():return False
    cycles=read(f).get('cycles',[])
    return bool(cycles and cycles[-1].get('stage')!='COMPLETE')

def model_overview(ws:pathlib.Path)->dict:
    result={}
    for name,p in locations(ws).items():
        if p.is_file():result[name]={'sha256':sha(p)}
    return result

def _native_tuning(cur:dict,*,fresh:bool)->dict:
    new=copy.deepcopy(cur)
    if new['budget']['profile']!='economy':
        # Preserve an intentional existing strict/balanced mode; require the
        # researcher to review a profile migration before changing juries.
        raise ValueError('Local assignment budget or reserved quota check failed at pro5x_optimizer._native_tuning (check 71). Save the checkpoint before resuming.')
    new['budget']['max_assignments_per_cycle']=min(cur['budget']['max_assignments_per_cycle'],ASSIGNMENTS)
    new['budget']['max_prompt_chars_per_cycle']=min(cur['budget']['max_prompt_chars_per_cycle'],PROMPT_CHARS)
    new['max_native_subagent_threads']=1
    new['max_jobs_per_desktop_turn']=1
    # Expensive random cross-domain *deep reading* deferred only for a fresh
    # campaign. 50/150/50 bibliographic discovery remains fully enabled.
    if fresh:new['cross_domain']['enabled']=False
    return new

def _rce_tuning(cur:dict)->dict:
    new=copy.deepcopy(cur)
    b=new['budget']
    b['max_native_assignments_per_cycle']=min(b['max_native_assignments_per_cycle'],RCE_ASSIGNMENTS)
    b['max_input_chars_per_cycle']=min(b['max_input_chars_per_cycle'],RCE_CHARS)
    b['max_papers_in_task_context']=min(b['max_papers_in_task_context'],4)
    b['max_context_chars']=min(b['max_context_chars'],40000)
    # Retain original 3 hypothesis candidates, 7 stages, both independent
    # novelty reviewers, offline benchmark and falsification requirements.
    return new

def _selection_tuning(cur:dict)->dict:
    new=copy.deepcopy(cur)
    new['screen_batch_size']=max(cur['screen_batch_size'],24)
    # Preserve 2600 characters per paper: evidence quality outranks prompt
    # savings; users can tune excerpts explicitly in a NEW campaign.
    lower=max(cur['core_min'],sum(t['min_core'] for t in cur['coverage_themes']))
    new['core_target']=max(lower,min(cur['core_target'],lower))
    # No lowering of academic keep/reject thresholds or coverage minima.
    return new

def apply(ws:pathlib.Path,*,dry_run:bool=False)->dict:
    ws=ws.expanduser().resolve();ps=locations(ws)
    missing=[x for x in ('native','rce') if not ps[x].is_file()]
    if missing:raise ValueError('Configuration schema or numeric bounds check failed at pro5x_optimizer.apply (check 105). Keep strict quality gates intact.'+', '.join(missing))
    originals={k:read(p) for k,p in ps.items() if p.is_file()}
    running_rce=active_rce(ws)
    fresh=not active_reader(ws)
    # While a native cognition stage is in flight, preserve its exact model
    # context and RCE configuration. The linked original reader quota may
    # still be tightened (it is excluded from native task's academic hash).
    changes={'native':_native_tuning(originals['native'],fresh=fresh),
             'rce':originals['rce'] if running_rce else _rce_tuning(originals['rce'])}
    changes_info={}
    if running_rce:
        changes_info['rce']='ACTIVE_COGNITION_TASK_PRESERVED_REAPPLY_AFTER_CYCLE; linked native dispatch cap still tightened'
    if fresh and 'selection' in originals:
        # Never overwrite existing researcher-tuned selection config.
        skill_file=ws/'.agents'/'skills'/'batch-paper-deepread-desktop'/'selection_config.example.json'
        if skill_file.is_file() and originals['selection']==read(skill_file):
            changes['selection']=_selection_tuning(originals['selection'])
        else:
            changes_info['selection']='SKIPPED_CUSTOM_CONFIG_PRESERVED'
    if active_reader(ws):
        changes_info['cross_domain']='EXISTING_CAMPAIGN_UNCHANGED; v5 cross-domain bibliography still exists'
    modified={k: {'before_sha256':sha(ps[k]),
                   'changed':orig!=changes[k],
                   'fields': sorted(f for f in changes[k] if changes[k][f]!=orig.get(f))}
              for k,orig in originals.items() if k in changes}
    if not dry_run:
        root=ws/'output'/'research_cognition'/'pro5x_survival'
        backup=root/'before_preset'
        backup.mkdir(parents=True,exist_ok=True)
        for k in changes:
            if k not in originals or originals[k]==changes[k]:continue
            dst=backup/ps[k].name
            if dst.exists() and read(dst)!=originals[k]:
                # Reapply/idempotent use: do not overwrite a previous backup.
                raise ValueError('Configuration schema or numeric bounds check failed at pro5x_optimizer.apply (check 139). Keep strict quality gates intact.'+str(dst))
            if not dst.exists():shutil.copy2(ps[k],dst)
        for k in changes:
            if originals[k]!=changes[k]:write(ps[k],changes[k])
        manifest={'profile':PROFILE,'updated_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
                  'patches':modified,'skipped':changes_info,
                  'reader_five_fulltext_rounds_preserved':True,
                  'independent_final_auditors_preserved':True,
                  'actual_provider_usage_observed':False,
                  'automatic_quota_renewal':False,
                  'experimental_execution':False,
                  'note':'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
        write(root/'policy.json',manifest)
        (root/'WORKFLOW.md').write_text(RECOMMENDED_FLOW,encoding='utf-8')
    return {'status':'DRY_RUN' if dry_run else 'PRO5X_SURVIVAL_CONFIGURED',
            'profile':PROFILE,'modifications':modified,'skipped':changes_info,
            'original_v44_source_modified':False,'v5_quota_modified':False,
            'reader_five_rounds_and_independent_final_audit_preserved':True,
            'current_shared_quota':current_budget(ws), 'rce_quota':rce_budget(ws),
            'notes':['Research evidence and workflow notes (pro5x_optimizer.apply). Use original source evidence; keep frozen constraints and independent quality gates.','Research evidence and workflow notes (pro5x_optimizer.apply). Use original source evidence; keep frozen constraints and independent quality gates.']}


def plan(ws:pathlib.Path)->dict:
    ws=ws.expanduser().resolve();ps=locations(ws)
    native=read(ps['native']) if ps['native'].is_file() else None
    rce=read(ps['rce']) if ps['rce'].is_file() else None
    sel=read(ps['selection']) if ps['selection'].is_file() else None
    meta=ws/'output'/'discovery_preflight'/'paper_library.json'
    pools={}
    if meta.is_file():
        data=read(meta)
        pools={k:len(data.get('selected',{}).get(k,[])) for k in ('core','related','inspiration')}
    native_use=current_budget(ws);rce_use=rce_budget(ws)
    cycles=None
    if native and sel:
        slots=native['budget']['max_assignments_per_cycle']
        goal=sel['core_target']; candidates=250
        # Illustrative upper-bound workload, NOT live model usage or source count.
        screening=math.ceil(candidates/sel['screen_batch_size'])*2
        deepread=goal*2*6
        remaining=screening+deepread+9+2  # unknown audits; conservative simplified illustrative
        cycles=math.ceil(remaining/max(1,slots))
    return {'status':'PROXY_ONLY_NOT_ACCOUNT_USAGE',
            'profile':PROFILE if (ws/'output'/'research_cognition'/'pro5x_survival'/'policy.json').is_file() else 'NOT_APPLIED',
            'metadata_pools':pools,'original_title_abstract_discovery_model_calls':0,
            'reader_budget':native['budget'] if native else None,
            'rce_budget':rce['budget'] if rce else None,
            'shared_reserved':native_use,'rce_reserved':rce_use,
            'illustrative_250_fulltext_screening_plus_core_2_chunks':{'estimated_screening_and_reading_tasks':remaining,'periods_at_proxy_cap':cycles} if cycles is not None else None,
            'recommended_mode':'Only a SMALL question-driven full-text batch enters native S1/S2; preserve 250 metadata library. RCE 7-stage full loop only after meaningful verified source changes.',
            'warning':'Research evidence and workflow notes (pro5x_optimizer.plan). Use original source evidence; keep frozen constraints and independent quality gates.'}

RECOMMENDED_FLOW='''# Pro 5x Survival — Low-Cost Scientific Research Workflow

1. Discover 250 authentic bibliographic candidates using v5/OpenAlex without inference-model calls. This does not authorize S1/S2 and five full-text rounds for all 250 papers.
2. Start with a small batch of actual full texts (typically 8–12); selection remains conditional on fixed v4.4 minimum coverage.
3. Preserve five complete source-grounded passes, independent final review and veto. Insufficient evidence causes a pause, never a lowered quality threshold.
4. Use bounded native-agent dispatches with durable checkpoints. Never assume a calendar-week or server quota reset without user confirmation.
5. Start another seven-stage RCE research cycle only for substantial new, verified source evidence. One downloaded PDF is not sufficient by itself.
6. Keep 50 cross-domain bibliographic candidates; launch extra interdisciplinary agents only when their expected information value warrants it.
7. Harness-style strategy evolution runs only when repeated, traceable workflow failures justify a bounded probe.
8. Final method recommendations require page-anchored quotations, mechanism comparison, reverse prior-art retrieval, two independent novelty reviewers and a falsifiable EXPERIMENT PLAN. No experiments or computational simulations are executed.
9. Local quota settings are conservative dispatch proxies, not actual Codex account usage. Reauthorize a budget cycle only after confirming live availability.
10. If evidence is incomplete, report PRELIMINARY_NOT_FINAL and list concrete blockers; do not pretend scientific originality is proven.
11. All internal prompts and intermediate reports are English. Only the final user-facing presentation is Chinese.
'''


def main(argv=None)->int:
    p=argparse.ArgumentParser(description='v6.4 Pro 5x survival configuration; local only')
    sub=p.add_subparsers(dest='command',required=True)
    for name in ('plan','status','apply'):
        a=sub.add_parser(name);a.add_argument('--workspace',required=True,type=pathlib.Path)
        if name=='apply':a.add_argument('--dry-run',action='store_true')
    args=p.parse_args(argv)
    try:
        result=plan(args.workspace) if args.command in ('plan','status') else apply(args.workspace,dry_run=args.dry_run)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except (ValueError,KeyError,OSError,TypeError,json.JSONDecodeError) as exc:
        print(json.dumps({'status':'BLOCKED','error':str(exc)},ensure_ascii=False),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
