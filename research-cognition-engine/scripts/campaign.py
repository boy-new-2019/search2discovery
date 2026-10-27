"""Phase feasibility report without quota mutation; local caps are not account quota."""
import argparse,json,pathlib
import store

def plan(ws):
    ws=pathlib.Path(ws).resolve()
    import suite
    from quota_guard import DEFAULT
    native=suite.desktop.native_cfg(ws)['budget'] if (ws/'native_config.json').is_file() else DEFAULT
    ledger=ws/'output/native/budget_ledger.json'
    used=0
    if ledger.exists():
        d=store.read(ledger);used=len(d['cycles'][d['active_cycle']]['reservations'])
    remaining=max(0,native['max_assignments_per_cycle']-used)
    reader=None
    if (ws/'output/batch/state.json').is_file():
        reader=suite.native_budget.plan(ws,native)
    # Nine RCE specialist assignments per complete cycle (two independent novelty roles).
    cognition=sum(len(v) for v in suite.engine.DEFAULT_ROLES.values())
    state_file=store.root(ws)/'engine_state.json'
    if state_file.is_file():
        cycles=store.read(state_file).get('cycles',[])
        if cycles:
            stage=cycles[-1]['stage']
            cognition=0 if stage=='COMPLETE' else sum(len(suite.engine.DEFAULT_ROLES[x]) for x in suite.engine.STAGES[suite.engine.STAGES.index(stage):])
    need=reader['estimated_min_unfinished_assignments_before_core_progress'] if reader else None
    rcfg=ws/'research_cognition_config.json';rce_remaining=None
    if rcfg.is_file():
        cfg=store.read(rcfg);local=ws/'output/research_cognition/local_model_budget.json';taken=0
        if local.exists():
            d=store.read(local);taken=len(d['periods'][d['active_period']]['requests'])
        rce_remaining=max(0,cfg['budget']['max_native_assignments_per_cycle']-taken)
    lower=(need+cognition) if need is not None else None
    infeasible=(lower is not None and lower>remaining) or (rce_remaining is not None and cognition>rce_remaining)
    result={'status':'LOCAL_CAP_BELOW_ESTIMATED_NEED' if infeasible else 'ESTIMATE_REQUIRES_REVIEW',
        'shared_assignments_remaining':remaining,'rce_local_assignments_remaining':rce_remaining,
        'reader_lower_bound':need,'cognition_assignments_reserved_in_plan':cognition,
        'estimated_combined_lower_bound':lower,'reader_estimate':reader,
        'account_quota_observed':False,'automatic_cap_change':False,'ledger_reset':False,
        'phase_policy':['Reserve original R1-R5, reader final auditors, and cognition/novelty/final assignments before further breadth screening.',
            'If infeasible, report local-cap shortfall early; do not spend the balance on optional screening or claim account exhaustion.',
            'Reuse completed signed tasks; choose a bounded cohort before sealing only within the approved quality configuration.',
            'No cap renewal or weakening of independent reviewers is automatic.'],
        'estimate_limit':'Reader estimate may include already completed rounds and excludes contingencies; not a price or provider-availability guarantee.'}
    store.write(store.root(ws)/'execution_plan.json',result)
    return result

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--workspace',required=True,type=pathlib.Path);a=p.parse_args(argv)
    print(json.dumps(plan(a.workspace),ensure_ascii=False,indent=2));return 0
