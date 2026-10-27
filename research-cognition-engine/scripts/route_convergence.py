"""Validate a concrete route from the signed FINAL specialist answer, not a lead assertion."""
from __future__ import annotations
import json,pathlib
import store
METHOD_FIELDS=('problem','baseline_model','dataset','information_boundary','representation','update_operator',
               'objective','supervision','protocol','resources','falsifier','expected_contribution')
def instructions():
    return ('For FINAL also return route_selection with status RECOMMENDED_FOR_VALIDATION or NO_VIABLE_CANDIDATE, '
        'selected_hypothesis_id (null for no viable candidate), rationale, novelty_risk, candidate_comparison '
        '[{hypothesis_id, verdict: ACCEPT|PROVISIONAL|REJECT, reason}], and method_card. '
        'Select one primary route; never recommend a KNOWN/REJECT hypothesis or repackage it under a new name. '
        'Compare materially distinct mechanisms and the user existing methods; naming, new datasets and module combinations alone are not novelty. '
        'For a selected route method_card must contain substantive strings for '+', '.join(METHOD_FIELDS)+
        ', and nearest_work_comparison [{work_id,shared_mechanism,technical_delta,evidence_claim_ids}]. '
        'Distinguish sourced facts from proposed operators and estimated resources. Include the full objective or precise pseudocode in update_operator/objective. '
        'State training/inference information availability, supervision provenance, fair resource matching, ablations and explicit kill criteria. '
        'If no candidate survives, return empty recommendations with an evidence-based no_recommendation_reason and NO_VIABLE_CANDIDATE; do not manufacture novelty.')

def validate(ws,route):
    if not isinstance(route,dict):raise ValueError('FINAL needs a concrete route_selection object')
    for field in ('rationale','novelty_risk'):
        if not isinstance(route.get(field),str) or len(route[field].strip())<25:raise ValueError('Missing route '+field)
    with store.connect(ws) as c:
        hypotheses={x['hypothesis_id']:dict(x) for x in c.execute('SELECT * FROM hypotheses')}
        works={x[0] for x in c.execute('SELECT work_id FROM works')}
        claim_works={x['claim_id']:x['work_id'] for x in c.execute('SELECT claim_id,work_id FROM claims')}
        claims=set(claim_works)
        reviews=[dict(x) for x in c.execute('SELECT * FROM assessments')]
    comparison=route.get('candidate_comparison')
    if not isinstance(comparison,list) or {x.get('hypothesis_id') for x in comparison}!=set(hypotheses):
        raise ValueError('Compare all registered candidate hypotheses, including rejections')
    for row in comparison:
        if row.get('verdict') not in ('ACCEPT','PROVISIONAL','REJECT') or len(str(row.get('reason','')).strip())<25:
            raise ValueError('Each candidate needs a disposition and mechanism-level reason')
    selected=route.get('selected_hypothesis_id')
    if route.get('status')=='NO_VIABLE_CANDIDATE':
        if selected is not None or any(x['verdict']!='REJECT' for x in comparison):raise ValueError('No viable route cannot silently accept a candidate')
        return {'status':'NO_VIABLE_CANDIDATE','selected':None,'novelty_proven':False}
    if route.get('status')!='RECOMMENDED_FOR_VALIDATION' or selected not in hypotheses:raise ValueError('Unknown selected route')
    if hypotheses[selected]['novelty_status']=='REJECTED_BY_PRIOR_ART':raise ValueError('Rejected prior-art mechanism cannot become the final route')
    if next(x for x in comparison if x['hypothesis_id']==selected)['verdict']=='REJECT':raise ValueError('Selected candidate was rejected')
    rr=[x for x in reviews if x['hypothesis_id']==selected]
    required={'rce_novelty_sol','rce_skeptic_astra'}
    if not required.issubset({x['role'] for x in rr}) or len({x['thread_ref'] for x in rr})<2:
        raise ValueError('Two distinct independent novelty reviews are required')
    if any(x['verdict'] in ('KNOWN','REJECT') for x in rr):raise ValueError('Independent prior-art rejection blocks recommendation')
    card=route.get('method_card')
    if not isinstance(card,dict):raise ValueError('Missing method_card')
    for field in METHOD_FIELDS:
        if not isinstance(card.get(field),str) or len(card[field].strip())<20:raise ValueError('Incomplete method card: '+field)
    nearest=card.get('nearest_work_comparison')
    if not isinstance(nearest,list) or not nearest:raise ValueError('Compare concrete nearest prior mechanisms')
    for row in nearest:
        if row.get('work_id') not in works:raise ValueError('Unregistered nearest prior work')
        for field in ('shared_mechanism','technical_delta'):
            if len(str(row.get(field,'')).strip())<25:raise ValueError('Missing nearest-work '+field)
        anchors=row.get('evidence_claim_ids')
        if not isinstance(anchors,list) or not anchors or not set(anchors).issubset(claims):raise ValueError('Nearest-work comparison needs actual anchored claims')
        if not any(claim_works[x]==row['work_id'] for x in anchors):raise ValueError('Nearest-work evidence belongs to a different paper')
    return {'status':'RECOMMENDED_FOR_VALIDATION','selected':selected,'novelty_proven':False}

def committed(ws):
    import engine
    state=engine.get_state(ws);cycle=state['cycles'][-1]
    if cycle['stage']!='COMPLETE' or 'FINAL' not in cycle['completed_stages']:raise ValueError('Independent FINAL stage is not complete')
    folder=engine.taskdir(ws,cycle['id']+'_FINAL')
    engine.commit(ws,folder.name)  # Revalidates prompt/answer receipts without new spending.
    answer=store.read(folder/'answers/rce_general_manager_astra.json')
    route=answer.get('route_selection');result=validate(ws,route)
    return result,route

def render(ws):
    result,route=committed(ws);out=store.root(ws)/'research_discovery_package';out.mkdir(parents=True,exist_ok=True)
    store.write(out/'route_selection.json',route)
    lines=['# Final route and method specification','',result['status'],'',route['rationale'],'',route['novelty_risk'],'','## Candidate dispositions','']
    for row in route['candidate_comparison']:lines.append('- '+row['hypothesis_id']+' / '+row['verdict']+': '+row['reason'])
    if result['selected']:
        for key in METHOD_FIELDS:lines.extend(['','## '+key.replace('_',' '),'',route['method_card'][key]])
        lines.extend(['','## Nearest prior mechanisms','',json.dumps(route['method_card']['nearest_work_comparison'],ensure_ascii=False,indent=2)])
    lines.extend(['','DESIGN ONLY. No experiment executed. Novelty remains subject to source and empirical review.'])
    store.textwrite(out/'final_route_and_method.md','\n'.join(lines)+'\n')
    return result
