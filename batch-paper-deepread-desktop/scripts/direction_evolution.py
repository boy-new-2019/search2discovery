#!/usr/bin/env python3
"""Bounded, evidence-backed micro-direction evolution for native Codex Desktop.

Never edits the macro goal, manuscript/method, original source or old team receipts.
A successful change queues limited two-pass re-screening instead of re-reading
all 600 papers. Model judgments arrive from actual external native subagents.
"""
from __future__ import annotations

import copy
import pathlib
import re
from typing import Any

import batch
import deepread as core

PREFERENCE_DEFAULT = {
    'mode': 'bounded_auto',       # or propose_only; no automatic model-driven change without review
    'max_accepted_changes': 3,
    'max_abs_priority': 2,
    'max_cumulative_movement': 4,
    'max_recheck_papers_per_change': 120,
    'min_distinct_support_papers': 2,
    'require_adversarial_review': True,
}
REVIEWERS = ('bpd_adversary_astra', 'bpd_method_sol')
PROPOSERS = ('bpd_transfer_sol', 'bpd_synthesis_sol')
OPERATIONS = ('SHIFT_PRIORITY', 'REFINE_FOCUS')


def _path(ws:pathlib.Path)->pathlib.Path:
    return batch.root_dir(ws)/'direction_state.json'


def _log_path(ws:pathlib.Path, sha:str)->pathlib.Path:
    return batch.root_dir(ws)/'direction_history'/(sha+'.json')


def current(ws:pathlib.Path, *, create:bool=False)->dict|None:
    f=_path(ws)
    if not f.is_file():
        if not create:return None
        theme_names=[t['name'] for t in batch.cfg_at(ws)['coverage_themes']]
        state={'schema_version':1,'macro_goal_sha256':core.file_hash(ws/'goal.md'),
               'allowed_parent_themes':theme_names,'revision':0,
               'priorities':{k:0 for k in theme_names},'focuses':{},
               'accepted':[],'cumulative_movement':0}
        core.jwrite(f,state)
    s=core.jread(f)
    if s.get('macro_goal_sha256')!=core.file_hash(ws/'goal.md'):
        raise ValueError('Frozen research topic or signed research contract mismatch at direction_evolution.current (check 52). Reconfirm boundaries; do not overwrite approved work.')
    if set(s.get('allowed_parent_themes',[]))!={t['name'] for t in batch.cfg_at(ws)['coverage_themes']}:
        raise ValueError('Frozen research topic or signed research contract mismatch at direction_evolution.current (check 54). Reconfirm boundaries; do not overwrite approved work.')
    if s.get('schema_version')!=1 or not isinstance(s.get('revision'),int):
        raise ValueError('Frozen research topic or signed research contract mismatch at direction_evolution.current (check 56). Reconfirm boundaries; do not overwrite approved work.')
    # A route revision and its two-pass recheck queue form one logical transaction.
    # A crash between their writes must not silently drop the recheck obligation.
    state_file=batch.root_dir(ws)/'state.json'
    if state_file.is_file():
        campaign=core.jread(state_file)
        known={g['id'] for g in campaign.get('groups',[])}
        for change in s['accepted']:
            history=_log_path(ws,change['proposal_sha256'])
            if not history.is_file():raise ValueError('Frozen research topic or signed research contract mismatch at direction_evolution.current (check 65). Reconfirm boundaries; do not overwrite approved work.')
            expected=set(core.jread(history)['event']['new_groups'])
            if not expected.issubset(known):
                raise ValueError('Frozen research topic or signed research contract mismatch at direction_evolution.current (check 68). Reconfirm boundaries; do not overwrite approved work.')
    return s


def note(ws:pathlib.Path)->str:
    s=current(ws)
    if not s or not s['revision']:return ''
    lines=['## Bounded subdirection reading focus (NOT a macro-topic change)',
           f'The macro goal remains frozen by goal.md; subdirection revision R{s["revision"]}.',
           'These priorities guide only incremental screening and reading. Never modify confirmed network structure, innovation claims, algorithms, protocols or experiments.']
    for theme,val in s['priorities'].items():
        if val: lines.append(f'- {theme}: relative priority {val:+d}; never replace source-evidence scoring or force irrelevant papers into the core set.')
    for theme,focus in s['focuses'].items():
        if focus:lines.append(f'- {theme}: provisional micro-focus {focus}; a changeable reading question, NOT an approved technical method.')
    return '\n'.join(lines)+'\n'


def _prefs(prefs:dict)->dict:
    if not isinstance(prefs,dict) or set(prefs)!=set(PREFERENCE_DEFAULT):
        raise ValueError('Frozen research topic or signed research contract mismatch at direction_evolution._prefs (check 87). Reconfirm boundaries; do not overwrite approved work.')
    if prefs['mode'] not in ('bounded_auto','propose_only'):raise ValueError('direction.mode invalid')
    for k,lo,hi in [('max_accepted_changes',0,8),('max_abs_priority',1,3),
                    ('max_cumulative_movement',1,12),('max_recheck_papers_per_change',1,1000),
                    ('min_distinct_support_papers',2,5)]:
        if type(prefs[k]) is not int or not lo<=prefs[k]<=hi:raise ValueError('Frozen research topic or signed research contract mismatch at direction_evolution._prefs (check 92). Reconfirm boundaries; do not overwrite approved work.')
    if prefs['require_adversarial_review'] is not True:
        raise ValueError('Frozen research topic or signed research contract mismatch at direction_evolution._prefs (check 94). Reconfirm boundaries; do not overwrite approved work.')
    return prefs


def _screened(ws:pathlib.Path)->tuple[dict,dict]:
    state=batch.load_state(ws)
    batch.verify_sources(ws,state)
    if state.get('frozen'):raise ValueError('Frozen research topic or signed research contract mismatch at direction_evolution._screened (check 101). Reconfirm boundaries; do not overwrite approved work.')
    if batch.next_screen(ws,state):raise ValueError('Frozen research topic or signed research contract mismatch at direction_evolution._screened (check 102). Reconfirm boundaries; do not overwrite approved work.')
    if not state.get('selection') or not state['selection'].get('decisions'):
        raise ValueError('Authentic source, page quotation or evidence integrity check failed at direction_evolution._screened (check 104). Never accept unverified material.')
    for manifest in (ws/'output'/'native'/'tasks').glob('*/manifest.json'):
        if not (manifest.parent/'commit.json').exists():
            raise ValueError('Signed task, stage, commit receipt or report provenance check failed at direction_evolution._screened (check 107). Resume only from a verified state.')
    return state,current(ws,create=True)


def _validated_evidence(ws:pathlib.Path, proposal:dict,prefs:dict)->int:
    seen=set()
    evidence=proposal.get('evidence')
    if not isinstance(evidence,list) or not 2<=len(evidence)<=10:
        raise ValueError('Frozen research topic or signed research contract mismatch at direction_evolution._validated_evidence (check 115). Reconfirm boundaries; do not overwrite approved work.')
    ready={p['id'] for p in batch.available(batch.load_state(ws))}
    for cite in evidence:
        if not isinstance(cite,dict):raise ValueError('evidence must be object')
        pid,page,quote=cite.get('paper_id'),cite.get('page'),cite.get('quote')
        if pid not in ready:raise ValueError('Authentic source, page quotation or evidence integrity check failed at direction_evolution._validated_evidence (check 120). Never accept unverified material.')
        pages=core.jread(batch.corpus_path(ws,pid))['pages']
        if type(page) is not int or not 1<=page<=len(pages):raise ValueError('Authentic source, page quotation or evidence integrity check failed at direction_evolution._validated_evidence (check 122). Never accept unverified material.')
        if not isinstance(quote,str) or not 6<=len(core.norm(quote))<=260 or core.norm(quote) not in core.norm(pages[page-1]):
            raise ValueError('Authentic source, page quotation or evidence integrity check failed at direction_evolution._validated_evidence (check 124). Never accept unverified material.')
        seen.add(pid)
    if len(seen)<prefs['min_distinct_support_papers']:
        raise ValueError('Authentic source, page quotation or evidence integrity check failed at direction_evolution._validated_evidence (check 127). Never accept unverified material.')
    # At least one primary supporting paper must have already been classified
    # into the target theme. Cross-disciplinary transfer alone is not enough.
    batch_state=batch.load_state(ws)
    s2=batch.screen_results(ws,'S2',batch_state)
    if not any(s2.get(pid,{}).get('theme')==proposal['parent_theme'] for pid in seen):
        raise ValueError('Authentic source, page quotation or evidence integrity check failed at direction_evolution._validated_evidence (check 133). Never accept unverified material.')
    return len(seen)


def preview(ws:pathlib.Path,proposal:dict,prefs:dict)->dict:
    prefs=_prefs(prefs)
    state,route=_screened(ws)
    if not isinstance(proposal,dict):raise ValueError('route proposal must beJSONobject')
    if set(proposal)!={'operation','parent_theme','focus','priority_delta','rationale','evidence','proposer_role','proposer_thread_ref','scope'}:
        raise ValueError('Authentic source, page quotation or evidence integrity check failed at direction_evolution.preview (check 142). Never accept unverified material.')
    if proposal['proposer_role'] not in PROPOSERS or not isinstance(proposal['proposer_thread_ref'],str) or len(proposal['proposer_thread_ref'].strip())<4:
        raise ValueError('Configuration schema or numeric bounds check failed at direction_evolution.preview (check 144). Keep strict quality gates intact.')
    operation=proposal['operation'];theme=proposal['parent_theme']
    if operation not in OPERATIONS or theme not in route['allowed_parent_themes']:
        raise ValueError('Input, evidence or workflow invariant failed at direction_evolution.preview (check 147); inspect the signed task record and original source.')
    delta=proposal['priority_delta']
    if type(delta) is not int or delta not in (-1,0,1):raise ValueError('Input, evidence or workflow invariant failed at direction_evolution.preview (check 149); inspect the signed task record and original source.')
    focus=proposal['focus']
    if not isinstance(focus,str) or len(focus)>150 or '\n' in focus or '\r' in focus:
        raise ValueError('Input, evidence or workflow invariant failed at direction_evolution.preview (check 152); inspect the signed task record and original source.')
    if operation=='SHIFT_PRIORITY' and (delta==0 or focus!=''):
        raise ValueError('Input, evidence or workflow invariant failed at direction_evolution.preview (check 154); inspect the signed task record and original source.')
    if operation=='REFINE_FOCUS' and (delta!=0 or len(focus.strip())<8 or focus.strip()==route['focuses'].get(theme,'')):
        raise ValueError('Input, evidence or workflow invariant failed at direction_evolution.preview (check 156); inspect the signed task record and original source.')
    if not isinstance(proposal['rationale'],str) or len(proposal['rationale'].strip())<20:
        raise ValueError('Input, evidence or workflow invariant failed at direction_evolution.preview (check 158); inspect the signed task record and original source.')
    scope=proposal['scope']
    if not isinstance(scope,dict) or set(scope)!={'macro_unchanged','confirmed_paper_core_unchanged','justification'}:
        raise ValueError('Frozen research topic or signed research contract mismatch at direction_evolution.preview (check 161). Reconfirm boundaries; do not overwrite approved work.')
    if scope['macro_unchanged'] is not True or scope['confirmed_paper_core_unchanged'] is not True or len(str(scope['justification']).strip())<20:
        raise ValueError('Frozen research topic or signed research contract mismatch at direction_evolution.preview (check 163). Reconfirm boundaries; do not overwrite approved work.')
    if len(route['accepted'])>=prefs['max_accepted_changes']:
        raise ValueError('Input, evidence or workflow invariant failed at direction_evolution.preview (check 165); inspect the signed task record and original source.')
    if abs(route['priorities'][theme]+delta)>prefs['max_abs_priority'] or route['cumulative_movement']+abs(delta)+(1 if operation=='REFINE_FOCUS' else 0)>prefs['max_cumulative_movement']:
        raise ValueError('Authentic source, page quotation or evidence integrity check failed at direction_evolution.preview (check 167). Never accept unverified material.')
    cited=_validated_evidence(ws,proposal,prefs)
    impacted=[x['paper_id'] for x in state['selection']['decisions'] if x['theme']==theme]
    if len(impacted)>prefs['max_recheck_papers_per_change']:
        raise ValueError('Input, evidence or workflow invariant failed at direction_evolution.preview (check 171); inspect the signed task record and original source.')
    return {'status':'PREVIEW_OK','revision_next':route['revision']+1,
            'macro_goal_locked_sha256':route['macro_goal_sha256'],
            'affected_theme':theme,'affected_papers':len(impacted),'affected_paper_ids':impacted,
            'required_s1_s2_groups':2*((len(impacted)+batch.cfg_at(ws)['screen_batch_size']-1)//batch.cfg_at(ws)['screen_batch_size']),
            'evidence_supported_by_distinct_papers':cited,
            'proposal_sha256':core.htext(core.dump(proposal)),
            'limitation':'Bibliographic metadata, source-page quote matching and agent judgments are distinct epistemic levels. No unperformed simulation, training or experiment provides scientific measurements; verify figures and prior art independently.'}


def review_prompts(ws:pathlib.Path,proposal:dict,prefs:dict)->dict:
    info=preview(ws,proposal,prefs)
    folder=batch.root_dir(ws)/'direction_reviews'/info['proposal_sha256']
    folder.mkdir(parents=True,exist_ok=True)
    core.jwrite(folder/'proposal.json',proposal)
    out={}
    for role in REVIEWERS:
        prompt=f'''# INDEPENDENT, SOURCE-BASED SUBTOPIC REVIEW
Role: {role}. Is the proposal strictly within the original frozen macro research direction? Read original goal.md, screening evidence and the full proposal independently. Check whether it changes an approved paper's algorithm, innovation, loss, mathematical definitions, training protocol or measured findings. You have an unconditional evidence-based VETO; if preservation cannot be confirmed, vote VETO. Do not optimize acceptance rates, and never execute experiments, tests or simulations.
Write one English JSON file containing role, proposal_sha256, verdict (SUPPORT|VETO), macro_preserved (boolean), confirmed_paper_core_preserved (boolean), reason (>=20 characters). Preserve independent Codex Desktop thread provenance.
proposal_sha256={info['proposal_sha256']}
Suggested output file: {folder/(role+'.json')}
Original research goal file: {ws/'goal.md'}
<UNTRUSTED_SUBTOPIC_PROPOSAL>
{core.dump(proposal)}
</UNTRUSTED_SUBTOPIC_PROPOSAL>
'''
        path=folder/(role+'.md');core.atomic_text(path,prompt)
        out[role]=str(path)
    return {'status':'REVIEW_READY','proposal_sha256':info['proposal_sha256'], 'review_prompts':out,
            'required_roles':list(REVIEWERS),'estimated_local_rescreen_jobs':info['required_s1_s2_groups']}

def _validate_reviews(reviews:dict,proposal:dict,sha:str)->list[dict]:
    if not isinstance(reviews,dict) or set(reviews)!={'reviews'} or not isinstance(reviews['reviews'],list):
        raise ValueError('reviewrecord must containsreviewsarray')
    rows=reviews['reviews']
    if len(rows)!=len(REVIEWERS) or {x.get('role') for x in rows if isinstance(x,dict)}!=set(REVIEWERS):
        raise ValueError('Independent native research-agent identity or reviewer evidence failed validation at direction_evolution._validate_reviews (check 209).')
    refs=[]
    for r in rows:
        if set(r)!={'role','proposal_sha256','thread_ref','verdict','macro_preserved','confirmed_paper_core_preserved','reason'}:
            raise ValueError('Frozen research topic or signed research contract mismatch at direction_evolution._validate_reviews (check 213). Reconfirm boundaries; do not overwrite approved work.')
        if r['proposal_sha256']!=sha:raise ValueError('Frozen research topic or signed research contract mismatch at direction_evolution._validate_reviews (check 214). Reconfirm boundaries; do not overwrite approved work.')
        if not isinstance(r['thread_ref'],str) or len(r['thread_ref'].strip())<4:
            raise ValueError('Independent native research-agent identity or reviewer evidence failed validation at direction_evolution._validate_reviews (check 216).')
        refs.append(r['thread_ref'])
        if r['verdict'] not in ('SUPPORT','VETO') or type(r['macro_preserved']) is not bool or type(r['confirmed_paper_core_preserved']) is not bool or len(str(r['reason']).strip())<20:
            raise ValueError('invalid independent review report')
    if len(set(refs+[proposal['proposer_thread_ref']]))!=len(refs)+1:
        raise ValueError('Independent native research-agent identity or reviewer evidence failed validation at direction_evolution._validate_reviews (check 221).')
    return rows


def apply(ws:pathlib.Path,proposal:dict,reviews:dict,prefs:dict)->dict:
    info=preview(ws,proposal,prefs)
    if _log_path(ws,info['proposal_sha256']+'_veto').is_file():
        raise ValueError('Source path, lawful access or network permission check failed at direction_evolution.apply (check 228). Do not bypass paywalls or source integrity checks.')
    rows=_validate_reviews(reviews,proposal,info['proposal_sha256'])
    if any(x['verdict']=='VETO' or not x['macro_preserved'] or not x['confirmed_paper_core_preserved'] for x in rows):
        result={'status':'REJECTED_BY_INDEPENDENT_VETO','proposal_sha256':info['proposal_sha256'],
                'reviewers':rows,'at':core.ts()}
        core.jwrite(_log_path(ws,info['proposal_sha256']+'_veto'),result)
        return result
    if prefs['mode']=='propose_only':
        return {'status':'AWAIT_USER_APPROVAL','proposal_sha256':info['proposal_sha256'],
                'instruction':'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
    state=batch.load_state(ws);route=current(ws,create=True)
    if any(x['proposal_sha256']==info['proposal_sha256'] for x in route['accepted']):
        raise ValueError('Input, evidence or workflow invariant failed at direction_evolution.apply (check 240); inspect the signed task record and original source.')
    revision=route['revision']+1
    target=info['affected_paper_ids']
    size=batch.cfg_at(ws)['screen_batch_size']
    additions=[]
    for idx in range(0,len(target),size):
        gid=f'EV{revision:02d}B{idx//size+1:04d}'
        if any(g['id']==gid for g in state['groups']):raise ValueError('Input, evidence or workflow invariant failed at direction_evolution.apply (check 247); inspect the signed task record and original source.')
        additions.append({'id':gid,'paper_ids':target[idx:idx+size],
                          'direction_revision':revision,'parent_theme':proposal['parent_theme']})
    updated=copy.deepcopy(route)
    updated['revision']=revision
    if proposal['operation']=='SHIFT_PRIORITY':
        updated['priorities'][proposal['parent_theme']]+=proposal['priority_delta']
    else:updated['focuses'][proposal['parent_theme']]=proposal['focus'].strip()
    updated['cumulative_movement']+=abs(proposal['priority_delta'])+(1 if proposal['operation']=='REFINE_FOCUS' else 0)
    event={'revision':revision,'proposal_sha256':info['proposal_sha256'],'proposal':proposal,
           'independent_reviews':rows,'original_macro_sha256':route['macro_goal_sha256'],
           'recheck_papers':len(target),'new_groups':[g['id'] for g in additions],
           'recheck_groups':copy.deepcopy(additions),
           'previous_selection_sha256':core.htext(core.dump(state['selection'])),
           'accepted_at':core.ts(),'status':'ACCEPTED_RESCREEN_PENDING' if target else 'ACCEPTED_NO_LOCAL_RESCREEN'}
    updated['accepted'].append({'revision':revision,'proposal_sha256':info['proposal_sha256'],
                                'theme':proposal['parent_theme'],'operation':proposal['operation']})
    state['groups'].extend(additions)
    # Keep prior decisions as an immutable evidence snapshot. Prevent discover/seal
    # before targeted rechecks are complete and select_core has re-evaluated ranking.
    core.jwrite(_log_path(ws,info['proposal_sha256']),{'event':event,'before':route,
                'original_selection':state['selection'],'after':updated})
    state['selection']={}
    # Save direction first so any subsequent screen task receives revised focus.
    # Writes are atomic; on crash state discrepancies fail as review logs show next_screen.
    core.jwrite(_path(ws),updated)
    batch.save_state(ws,state)
    return {'status':event['status'],'revision':revision,'changed_theme':proposal['parent_theme'],
            'rescreen_papers':len(target),'rescreen_group_pairs':len(additions),
            'next_action':'Inspect the signed checkpoint, verify the original full-text evidence and reviewer receipts, then continue only the stage justified by a substantive evidence gap and available quota.'}


def kit(ws:pathlib.Path,prefs:dict)->dict:
    prefs=_prefs(prefs);state,route=_screened(ws)
    selection=state['selection']
    # Compact input: structured, already checked paper quotes; not a claim of full-text context.
    by_theme={}
    for row in selection['decisions']:
        a=by_theme.setdefault(row['theme'],[])
        if len(a)<6 and row['decision'] in ('CORE','HOLD','RESERVE'):
            a.append({'paper_id':row['paper_id'],'decision':row['decision'],'score':row['score'],
                      'evidence':row['screen_evidence']['S2'][:1]})
    material={'goal_file':str(ws/'goal.md'),'current_priorities':route['priorities'],
              'current_focuses':route['focuses'],'coverage_gaps':selection.get('gaps',[]),
              'per_theme_sample_evidence':by_theme,'already_accepted':len(route['accepted'])}
    base=batch.root_dir(ws)/'direction_suggestions';base.mkdir(parents=True,exist_ok=True)
    role='bpd_transfer_sol'
    prompt='Research evidence and workflow notes (direction_evolution.kit). Use original source evidence; keep frozen constraints and independent quality gates.'
    out=base/'suggestion_prompt.md';core.atomic_text(out,prompt)
    return {'status':'PROPOSAL_READY','role':role,'proposal_prompt':str(out),
            'existing_direction_revision':route['revision'],'mode':prefs['mode']}


def recover(ws:pathlib.Path)->dict:
    """Safely complete an interrupted route-state+screen-queue transaction.

    Only restore exact recheck groups from an accepted, hashed on-disk log.
    No papers, votes or archived evidence can be created by the repair command.
    """
    p=_path(ws)
    if not p.is_file():return {'status':'NO_DIRECTION_STATE'}
    route=core.jread(p)
    campaign=batch.load_state(ws)
    missing=[]
    known={g['id'] for g in campaign.get('groups',[])}
    for change in route.get('accepted',[]):
        log=_log_path(ws,change['proposal_sha256'])
        if not log.is_file():raise ValueError('Source path, lawful access or network permission check failed at direction_evolution.recover (check 324). Do not bypass paywalls or source integrity checks.')
        recorded=core.jread(log)
        after=recorded.get('after')
        if after.get('revision')!=change['revision'] or not any(
            x.get('proposal_sha256')==change['proposal_sha256'] for x in after.get('accepted',[])
        ):
            raise ValueError('Input, evidence or workflow invariant failed at direction_evolution.recover (check 330); inspect the signed task record and original source.')
        for group in recorded['event'].get('recheck_groups',[]):
            if group['id'] not in known:
                # Each recheck group must target previously screened paper IDs.
                ready={p['id'] for p in batch.available(campaign)}
                if not set(group['paper_ids']).issubset(ready):
                    raise ValueError('Input, evidence or workflow invariant failed at direction_evolution.recover (check 336); inspect the signed task record and original source.')
                missing.append(group)
                known.add(group['id'])
    if missing:
        # If a crash occurred after writing revised route but before state.json,
        # selection cannot be treated as valid until the pending rechecks finish.
        campaign['groups'].extend(missing)
        campaign['selection']={}
        batch.save_state(ws,campaign)
    current(ws)  # Full invariant check.
    return {'status':'RECOVERED_PENDING_RECHECK' if missing else 'CONSISTENT',
            'restored_screen_groups':len(missing),
            'remaining_screen_job':(batch.next_screen(ws,batch.load_state(ws)) or {}).get('id')}
