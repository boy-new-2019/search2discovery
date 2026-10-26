#!/usr/bin/env python3
"""v6.5: zero-model, source-bound per-round research reviews & decision support.

Additive integration. NEVER edit the original v4.4 skill or any original answers.
This module does not claim that lexical quote checks establish scientific truth.
"""
from __future__ import annotations
import hashlib
import json
import pathlib
from collections import Counter
from typing import Any

import store
import engine

HERE = pathlib.Path(__file__).resolve().parent
REPORTS = 'round_reports'
RCE_FIELDS = {
    'MAP': ('questions', 'question'),
    'MECHANISM': ('observations', 'claim'),
    'CONTRADICTION': ('contradictions', 'rationale'),
    'HYPOTHESIS': ('hypotheses', 'statement'),
    'NOVELTY': ('assessments', 'justification'),
    'EXPERIMENT': ('plans', 'test'),
    'FINAL': ('recommendations', 'recommendation'),
}


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def home(ws: pathlib.Path) -> pathlib.Path:
    return ws.resolve() / 'output' / 'research_cognition' / REPORTS


def _read(path: pathlib.Path) -> Any:
    return json.loads(path.read_text('utf8'))


def _dump(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False, sort_keys=True, indent=2)


def _fingerprint(payload: Any) -> str:
    return hashlib.sha256(_dump(payload).encode('utf8')).hexdigest()


def _brief(text: Any, limit: int=340) -> str:
    value = str(text or '').replace('\r', ' ').replace('\n', ' ').strip()
    return value[:limit] + ('…' if len(value)>limit else '')


def _safe_md(text: Any) -> str:
    return str(text).replace('|','\\|').replace('\n',' ').replace('\r',' ').strip()


def _citations(observations: list[dict], paper: str, maximum: int=16) -> tuple[list[dict], int]:
    found=[];seen=set()
    for x in observations:
        for e in x.get('evidence',[]):
            if not isinstance(e,dict):continue
            pair=(paper,e.get('page'),e.get('quote'))
            if pair in seen:continue
            seen.add(pair)
            found.append({'paper_id':paper,'page':e.get('page'),'quote':e.get('quote'),
                          'about':_brief(x.get('claim') or x.get('category'),180),
                          'kind':x.get('status','reported')})
    return found[:maximum],len(found)


def _audit_commit(ws:pathlib.Path,jid:str,payload:dict,core_receipt:pathlib.Path|None=None)->dict:
    """Validate a v4.4 original commit/receipt, incl. deterministic compilation."""
    from v44_original_adapter import _verified_member_commit
    task=ws/'output'/'native'/'tasks'/jid
    cm=task/'commit.json'
    if not cm.is_file():raise ValueError('Round native-task commit missing: '+jid)
    data=_read(cm)
    if data.get('status')!='COMMITTED':raise ValueError('Round native-task is not COMMITTED: '+jid)
    if data.get('route')=='LOCAL_EVIDENCE_COMPILATION':
        if core_receipt is None or not core_receipt.is_file():raise ValueError('Unverified native task: '+jid)
        if data.get('source_receipt_sha256')!=sha(core_receipt):raise ValueError('Unverified native task: '+jid)
    else:_verified_member_commit(ws,jid,payload)
    return {'job':jid,'commit_sha256':sha(cm),'consolidated_sha256':sha(task/'consolidated.json') if (task/'consolidated.json').is_file() else '',
            'reading_receipt_sha256':sha(core_receipt) if core_receipt and core_receipt.is_file() else None,
            'route':data.get('route'),'members':data.get('member_roles',[])}


def _screen_items(ws:pathlib.Path)->list[dict]:
    from native_v44_launcher import bridge
    from v44_original_adapter import _verified_member_commit
    import batch
    root=ws/'output'/'batch'/'state.json'
    if not root.is_file():return []
    state=batch.load_state(ws)
    result=[]
    if not state.get('groups'):return []
    batch_id=f'{state["campaign"]}_{_fingerprint([g["id"] for g in state["groups"]])[:9]}'
    for stage in ('S1','S2'):
        round_key=f'SCREEN_{batch_id}_{stage}'
        ids=[batch.stage_jid(stage,g) for g in state['groups']]
        if not all(batch.done(ws,jid) for jid in ids):
            # A previously generated report must never silently disappear.
            result.append({'key':round_key,'complete':False})
            continue
        jobs=[];papers=[]
        for group,jid in zip(state['groups'],ids):
            record=_read(batch.screen_path(ws,jid,'answers'))
            job={'id':jid,'stage':stage,'group':group}
            _,excerpt=batch.make_screen_prompt(ws,state,job)
            batch.verify_screen(ws,state,job,record,excerpt)
            _verified_member_commit(ws,jid,record)
            jobs.append({'id':jid,'answer_sha256':sha(batch.screen_path(ws,jid,'answers')),
                         'receipt_sha256':sha(batch.screen_path(ws,jid,'receipts')),
                         'native_commit_sha256':sha(ws/'output/native/tasks'/jid/'commit.json')})
            papers.extend(record['papers'])
        score=[];cites=[];out=[];uncertainty=[]
        for p in papers:
            scores=p.get('scores',{});quality=scores.get('evidence_quality')
            if isinstance(quality,(int,float)):score.append(quality)
            evidence=[{'paper_id':p['paper_id'],'page':x.get('page'),'quote':x.get('quote')} for x in p.get('evidence',[])[:2]]
            cites.extend(evidence)
            if str(p.get('uncertainty','none')).strip().lower()!='none':uncertainty.append(p['paper_id'])
            out.append({'paper_id':p['paper_id'],'decision':p['verdict'],'reason':p.get('reason',''),
                        'uncertainty':p.get('uncertainty',''), 'evidence':evidence})
        counts=Counter(x['decision'] for x in out)
        result.append({'key':round_key,'complete':True,'kind':'SCREEN','label':stage,
                       'source_files':jobs,'summary':f'{stage}: {len(out)} papers screened; decision counts: {dict(counts)}.',
                       'items':out,'citations':cites[:24],'citation_total':len(cites),
                       'issues':[f'{len(uncertainty)} papers require further uncertainty review: '+', '.join(uncertainty[:12])] if uncertainty else [],
                       'stats':{'papers':len(out),'verdicts':dict(counts),'avg_evidence_quality':round(sum(score)/len(score),2) if score else None,
                                'uncertain_paper_count':len(uncertainty)},
                       'scientific_limit':'S1/S2 decisions are bounded relevance judgments supported by excerpt anchors; they are not complete full-text or experimental evidence.'})
    return result


def _round_items(ws:pathlib.Path)->list[dict]:
    import batch, deepread as core
    statepath=ws/'output'/'batch'/'state.json'
    if not statepath.is_file():return []
    state=batch.load_state(ws)
    batch.verify_sources(ws,state)
    frozen=state.get('frozen')
    if not frozen:return []
    ctx=core.env(pathlib.Path(frozen['core_workspace']))
    output=[]
    earlier_obs:set[tuple]=set()
    for rnd in range(1,ctx['cfg']['rounds']+1):
        tag=f'R{rnd:02d}'
        jobs=[];observations=[];issues=[];papers=[];verified_citations=[];total_citations=0;routes=Counter()
        tasks=[]
        for pid in ctx['paper_ids']:
            for ch in core.paper_chunks(ctx,pid):tasks.append((f'{tag}_{pid}_{ch["chunk_id"]}','leaf',pid))
            tasks.append((f'{tag}_{pid}_MERGE','merge',pid))
        for gid,_ in core.group_defs(ctx):tasks.append((f'{tag}_{gid}_GROUP','group',''))
        tasks.append((f'{tag}_ALL_MASTER','master',''))
        if not all(core.completed(ctx,jid) for jid,_,_ in tasks):
            output.append({'key':f'DEEP_{ctx["run_id"]}_{tag}','complete':False})
            # Cannot claim later rounds complete when an earlier one is incomplete.
            break
        for jid,typ,pid in tasks:
            data=core.answer(ctx,jid)
            receipt=core.rec_path(ctx,jid)
            # original .verified means quote validations passed; independently validate native membership/receipt.
            audit=_audit_commit(ws,jid,data,receipt)
            jobs.append(audit)
            routes[audit['route'] or 'UNKNOWN']+=1
            if typ=='leaf':
                evidence,ct=_citations(data.get('observations',[]),pid,maximum=24)
                verified_citations.extend(evidence)
                total_citations+=ct
                for obs in data.get('observations',[]):
                    key=(pid,_brief(obs.get('claim'),800).casefold(),tuple((e.get('page'),e.get('quote')) for e in obs.get('evidence',[])))
                    observations.append(key)
                for flag in data.get('visual_flags', []):
                    issues.append(f"{pid} PDF page {flag.get('page', '?')}: visual review pending — {_brief(flag.get('reason', 'figure, table or equation not independently checked'), 180)}")
            if typ=='merge':
                papers.append({'paper_id':pid,'overview':data.get('overview',''),
                               'key_points':data.get('key_points',[])[:12],
                               'weaknesses':data.get('weaknesses',[])[:12],
                               'open_questions':data.get('open_questions',[])[:12],
                               'visual_flags':data.get('visual_flags',[])[:12],
                               'locally_compiled':audit['route']=='LOCAL_EVIDENCE_COMPILATION'})
            if typ=='master':
                master={'overview':data.get('overview',''),'comparisons':data.get('comparisons',[])[:14],
                        'gaps':data.get('gaps',[])[:24],'priorities':data.get('priorities',[])[:20]}
        unique=set(observations)
        new=unique-earlier_obs
        earlier_obs |= unique
        total_unique=len(unique)
        if total_unique and len(new)==0:
            issues.append('Zero new exact claim/quote tuples were detected in this round. This lexical measure does not establish zero scientific gain or authorize skipping rounds.')
        for row in papers:
            issues.extend(f'{row["paper_id"]}: {_brief(q,210)}' for q in row['open_questions'][:4])
        output.append({'key':f'DEEP_{ctx["run_id"]}_{tag}','complete':True,'kind':'DEEP','label':tag,
                       'run_id':ctx['run_id'],'title':core.round_goal(rnd),
                       'source_files':jobs,'summary':master.get('overview',''),
                       'master':master,'papers':papers,'citations':verified_citations[:28],
                       'citation_total':total_citations,'issues':issues[:90],
                       'stats':{'papers':len(papers),'jobs':len(tasks),'routes':dict(routes),'observations':len(observations),
                                'unique_observations':total_unique,'new_lexical_observations_since_earlier_rounds':len(new),
                                'verified_quote_occurrences':total_citations,'local_compilations':routes.get('LOCAL_EVIDENCE_COMPILATION',0),
                                'requested_subagent_assignments_proxy':sum(len(j.get('members',[])) for j in jobs)},
                       'scientific_limit':'All five original-source rounds remain mandatory. Exact claim/quote overlap is not semantic novelty. Any deterministic compilation is an index, not another independent reading. Figure/table verification requires separate visual review.'})
    return output


def _cognition_items(ws:pathlib.Path)->list[dict]:
    folder=ws/'output'/'research_cognition'/'engine_state.json'
    if not folder.is_file():return []
    state=engine.get_state(ws)
    output=[]
    for cycle in state.get('cycles',[]):
        for phase in cycle.get('completed_stages',[]):
            if phase not in RCE_FIELDS:raise ValueError('Unknown cognition stage: '+phase)
            jid=cycle['id']+'_'+phase
            d=engine.taskdir(ws,jid)
            commit=d/'commit.json'; manifest=d/'manifest.json'
            if not (commit.is_file() and manifest.is_file()):raise ValueError('Signed task, stage, commit receipt or report provenance check failed at round_intelligence._cognition_items (check 219). Resume only from a verified state.'+jid)
            record=_read(commit);m=_read(manifest)
            if record.get('status')!='COMMITTED' or record.get('stage')!=phase:raise ValueError('Signed task, stage, commit receipt or report provenance check failed at round_intelligence._cognition_items (check 221). Resume only from a verified state.'+jid)
            if m.get('job_id')!=jid or m.get('cycle_id')!=cycle['id']:raise ValueError('Signed task, stage, commit receipt or report provenance check failed at round_intelligence._cognition_items (check 222). Resume only from a verified state.'+jid)
            results=engine._get_member_results(ws,m)
            signature=store.hashobj({k:store.hashobj(v) for k,v in results.items()})
            if record.get('source_sha256')!=signature:raise ValueError('Authentic source, page quotation or evidence integrity check failed at round_intelligence._cognition_items (check 225). Never accept unverified material.'+jid)
            documents=[{'job':jid,'commit_sha256':sha(commit),'manifest_sha256':sha(manifest)}]
            citations=[];rows=[];issues=[]
            for role in m['roles']:
                rf=d/'receipts'/f'{role}.json'; af=d/'answers'/f'{role}.json'
                if not (rf.is_file() and af.is_file()):raise ValueError('independent Unverified native task: '+jid)
                r=_read(rf)
                if not r.get('thread_ref') or r.get('role')!=role:raise ValueError('Independent agent provenance invalid: '+jid)
                documents.append({'role':role,'answer_sha256':sha(af),'receipt_sha256':sha(rf),'thread_ref':r['thread_ref']})
                for item in results[role][RCE_FIELDS[phase][0]]:
                    rows.append({'role':role,'item':item})
                    if phase=='MECHANISM':
                        citations.append({'source_id':item['source_id'],'page':item['page'],'quote':item['quote'],'about':item['claim']})
                    if phase=='NOVELTY' and item.get('verdict') in ('KNOWN','REJECT','UNCERTAIN'):
                        issues.append(f'{role}: {item.get("hypothesis_id")} novelty{item.get("verdict")}, {_brief(item.get("unresolved"),220)}')
            key,display=RCE_FIELDS[phase]
            output.append({'key':f'COGNITION_{cycle["id"]}_{phase}','complete':True,'kind':'COGNITION','label':phase,
                           'cycle_id':cycle['id'],'source_files':documents,
                           'summary':f'{cycle["id"]} / {phase}: {len(rows)} verified records from {len(m["roles"])} independent role submissions.',
                           'rows':rows[:65],'citations':citations[:18],'citation_total':len(citations),
                           'issues':issues[:40], 'stats':{'records':len(rows),'roles':len(m['roles']),
                             'role_list':list(m['roles']),'stage':phase, 'requested_subagent_assignments_proxy':len(m['roles'])},
                           'scientific_limit':'Committed stage outputs are agent judgments with cited-source provenance, not proof of scientific correctness, novelty, or new experiment results. Independent source review remains mandatory.'})
    return output


def collect(ws:pathlib.Path)->list[dict]:
    """Scan existing committed outputs only; no network or model calls."""
    ws=ws.expanduser().resolve()
    return _screen_items(ws)+_round_items(ws)+_cognition_items(ws)


def _render(x:dict)->str:
    lines=[f'# {x["kind"]} | {x["label"]} | Verified round review', '',
           f'- Task: `{x["key"]}`', '- State: `COMMITTED_SOURCE_CHECKED`',
           f'- Stage: {x.get("title",x["label"])}',
           '- Provenance: deterministic indexing of verified original reviewer commits; NOT a separate academic judgment.',
           '', '## Round summary', '', _brief(x['summary'],2000), '', '## Operational evidence statistics', '']
    for k,v in x.get('stats',{}).items():lines.append(f'- `{k}`: {v}')
    if x.get('kind')=='SCREEN':
        lines+=['','## Per-paper screening decisions (partial excerpts, not fulltext confirmation)','']
        for row in x.get('items',[])[:70]:
            lines.append(f'- `{row["paper_id"]}` **{row["decision"]}**: {_brief(row["reason"],280)}; uncertainty: {_brief(row["uncertainty"],180)}')
        if len(x.get('items',[]))>70:lines.append(f'- {len(x["items"])-70} more records are available in the round JSON.')
    elif x.get('kind')=='DEEP':
        lines+=['','## Per-paper reading insights and unresolved questions','']
        for row in x.get('papers',[]):
            lines.extend([f'### `{row["paper_id"]}`','',_brief(row['overview'],900)])
            if row['locally_compiled']:lines.append('This section is a zero-model deterministic evidence index, not another interpretive model summary.')
            for k in row['key_points'][:7]:lines.append(f'- Extracted observation: {_brief(k.get("claim") if isinstance(k,dict) else k,230)}')
            for k in row['weaknesses'][:5]:lines.append(f'- Potential limitation: {_brief(k,260)}')
            for k in row['open_questions'][:7]:lines.append(f'- Unresolved question: {_brief(k,260)}')
            lines.append('')
        lines+=['## Cross-paper comparison', '', _brief(x.get('master',{}).get('overview'),1600)]
        for k in x.get('master',{}).get('comparisons',[])[:12]:
            lines.append(f'- {_brief(k.get("claim"),450)}; agent-stated confidence: {k.get("confidence","?")}')
        for k in x.get('master',{}).get('gaps',[])[:15]:lines.append(f'- Evidence gap: {_brief(k,320)}')
    else:
        lines+=['','## Independent specialist submissions','']
        field=RCE_FIELDS[x['label']][1]
        for rr in x.get('rows',[])[:50]:
            item=rr['item'];lines.append(f'- **{rr["role"]}**: {_brief(item.get(field),500)}')
            if x['label']=='NOVELTY':lines.append(f'  - Novelty verdict: {item.get("verdict")}; nearest works: {item.get("nearest_work_ids")}')
            if x['label']=='EXPERIMENT':lines.append(f'  - PLANNED_NOT_EXECUTED; metrics: {item.get("metrics")}; rejection condition: {_brief(item.get("reject_condition"),300)}')
    lines+=['','## Source-page quotations and provenance (sample; full list in JSON)','']
    for quote in x.get('citations',[])[:24]:
        who=quote.get('paper_id') or quote.get('source_id')
        lines.append(f'- `{who}` p.{quote.get("page")}: "{_brief(quote.get("quote"),240)}"')
    if x.get('citation_total',0)>len(x.get('citations',[])):
        lines.append(f'- {x["citation_total"]-len(x.get("citations",[]))} other quotations are indexed in JSON or original reviewer answers.')
    lines+=['','## Remaining risks, questions and next action','']
    if x.get('issues'):
        for issue in x['issues'][:45]:lines.append(f'- {_brief(issue,420)}')
    else:lines.append('- No open issues were explicitly recorded in the submitted stage; this does not establish an absence of scientific risk.')
    if x['kind']=='DEEP':
        k=x['stats']['new_lexical_observations_since_earlier_rounds']
        lines.append(f'- Distinct new lexical claim+quote tuples: {k}. This is not a count of new discoveries and cannot skip any mandatory round.')
        if x['label'] in ('R3','R03'):
            lines.append('- R3: published paper results and non-executable qualitative desk scenarios only. No simulations/tests were executed by this Skill.')
    lines+=['','## Original source and independent task attestations','']
    for source in x['source_files'][:100]:lines.append('- `'+_brief(_dump(source),460)+'`')
    if len(x['source_files'])>100:lines.append(f'- See JSON for {len(x["source_files"])-100} additional receipts.')
    lines+=['','## Epistemic status and limitations','',x['scientific_limit'],'',
            '> Corrections must preserve this immutable report and create a new reviewed version; never silently rewrite accepted original findings.','']
    return '\n'.join(lines)

def _efficiency_dashboard(ws:pathlib.Path,records:list[dict],entries:dict)->dict:
    deep=[r for r in records if r.get('complete') and r.get('kind')=='DEEP']
    cognition=[r for r in records if r.get('complete') and r.get('kind')=='COGNITION']
    screening=[r for r in records if r.get('complete') and r.get('kind')=='SCREEN']
    saved=sum(r['stats'].get('local_compilations',0) for r in deep)
    requests=sum(r['stats'].get('requested_subagent_assignments_proxy',0) for r in deep+cognition)
    overlaps=[]
    for row in deep:
        total=row['stats'].get('unique_observations',0)
        overlaps.append({'round':row['label'],'run_id':row.get('run_id'),
                         'exact_anchor_overlap_fraction':round(1-row['stats'].get('new_lexical_observations_since_earlier_rounds',0)/total,4) if total else None,
                         'not_semantic_novelty':True})
    unresolved=sum(len(row.get('issues',[])) for row in deep+cognition)
    checks={'all_reports_source_bound':True,'no_unapproved_extra_scientific_cycle':True,
            'five_core_rounds_still_mandatory':True,'original_strict_academic_review_still_required':True}
    result={'status':'LOCAL_EFFICIENCY_DIAGNOSTIC_ONLY','generated_at':store.utc(),
            'screen_reports':len(screening),'fulltext_round_reports':len(deep),
            'cognition_stage_reports':len(cognition),'local_zero_model_compilation_tasks':saved,
            'requested_subagent_assignments_proxy':requests,'reviewed_unresolved_items_in_report':unresolved,
            'per_round_exact_overlap':overlaps,'quality_gates':checks,
            'next_action':'Prioritize important unresolved scientific questions and new source evidence before another high-cost cognition cycle. Never skip mandatory five original-text rounds, independent audit, or two independent novelty reviewers.',
            'caution':'Local dispatch proxies are not actual Codex token accounting; lexical overlap is not a semantic understanding measure.'}
    out=home(ws)
    store.write(out/'efficiency_dashboard.json',result)
    lines=['# Research efficiency and quality dashboard','',
           '> This internal report requires no extra model call. Metrics are local scheduling and citation proxies, not product token billing.','',
           f'- Completed screening reports: {len(screening)}',
           f'- Completed original fulltext rounds: {len(deep)}',
           f'- Completed cognition stage reports: {len(cognition)}',
           f'- Zero-model deterministic compilation tasks: {saved}',
           f'- Native subagent assignment proxy: {requests}',
           f'- Explicit unresolved items and audit checks: {unresolved}', '',
           '## Exact claim+quote overlap by round (not scientific novelty)', '']
    for row in overlaps:
        lines.append(f'- {row["run_id"]} / {row["round"]}: {row["exact_anchor_overlap_fraction"]} (must not be used to skip required source reading)')
    lines.extend(['','## Evidence-preserving low-quota research protocol','',
         '1. Use APIs and deterministic code for authentic metadata; screen only legally readable papers that answer key questions.',
         '2. Reuse completed source-verified jobs and quotes. R1--R5 still reread original material and retain independent final veto.',
         '3. Do not spend strong-model calls to restate the same deterministic evidence index.',
         '4. Triage substantive new source/question changes before launching another complete cognition cycle.',
         '5. Escalate meaningful prior-art or mechanism disagreements to independent novelty reviewers; retain falsifiable future experimental design.',
         '6. Invoke harness evolution only after repeatable quality failures, not automatically every round.',
         '', 'Actual subscription savings and scientific quality improvements require live task measurements and external validation.',''])
    store.textwrite(out/'efficiency_dashboard.md','\n'.join(lines))
    return result

def refresh(ws:pathlib.Path)->dict:
    ws=ws.expanduser().resolve()
    out=home(ws)
    reports=collect(ws)
    indexpath=out/'manifest.json'
    old=_read(indexpath) if indexpath.is_file() else {'schema':1,'entries':{}}
    entries=old.get('entries',{})
    made=[];not_ready=[]
    for data in reports:
        key=data['key']
        if not data['complete']:
            if key in entries:raise ValueError('A previously archived round lost its source evidence or completion state: '+key)
            not_ready.append(key)
            continue
        # All verified provenance & source receipts are bound into fingerprint.
        code=_fingerprint({k:v for k,v in data.items() if k!='complete'})
        dest=out/data['kind'].lower()/key
        content={**data,'report_fingerprint':code,'state':'SOURCE_ANCHOR_CHECKED_NOT_SEMANTIC_PROOF'}
        markdown=_render(data)
        objpath=dest/'report.json'; mdpath=dest/'report.md'
        metadata=entries.get(key)
        if metadata:
            if not objpath.is_file() or not mdpath.is_file() or sha(objpath)!=metadata['json_sha256'] or sha(mdpath)!=metadata['md_sha256']:
                raise ValueError('Committed historical research report missing or modified: '+key)
            if metadata['fingerprint']!=code:
                # Upgrade-safe rule: only preserve an old report if its actual
                # source/receipt bindings and indexed observations are identical.
                # The deterministic narration changed language in v6.6; this
                # is not a license to ignore source changes or overwrite history.
                historical=_read(objpath)
                binding_keys=('source_files','citations','citation_total','stats')
                if any(historical.get(k)!=data.get(k) for k in binding_keys):
                    raise ValueError('Signed round source evidence changed; archive and independent review required: '+key)
                # Retain source-authenticated older-language report as an immutable
                # legacy research artifact. Only newly committed stages use English.
            continue
        dest.mkdir(parents=True,exist_ok=True)
        if objpath.exists() or mdpath.exists():raise ValueError('Unexpected report collision; refuse to overwrite: '+key)
        store.write(objpath,content)
        store.textwrite(mdpath,markdown)
        entries[key]={'fingerprint':code,'kind':data['kind'],'label':data['label'],
                      'json_path':str(objpath.relative_to(ws)), 'md_path':str(mdpath.relative_to(ws)),
                      'json_sha256':sha(objpath),'md_sha256':sha(mdpath),
                      'created_at':store.utc()}
        store.write(indexpath,{'schema':1,'entries':entries})
        made.append(key)
    # Links are relative to index location, not project root.
    lines=['# Research round reports: verified review checkpoints','', '**Each entry is generated from committed reviewer records; incomplete rounds have no completion report.**','']
    for key,v in sorted(entries.items()):
        rel=pathlib.Path(v['md_path']).relative_to(pathlib.Path('output/research_cognition/round_reports'))
        lines.append(f'- `{key}`: [Open verified round report]({rel.as_posix()}) (created {v["created_at"]})')
    store.textwrite(out/'INDEX.md','\n'.join(lines)+'\n')
    _efficiency_dashboard(ws,reports,entries)
    return {'status':'ROUND_REPORTS_UPDATED','new_reports':made,'existing_reports':len(entries)-len(made),
            'incomplete_rounds':not_ready,'index':str(out/'INDEX.md'),'model_calls':0,
            'report_granularity':'v44 S1/S2; R1..R5 each round; RCE MAP..FINAL each stage'}


def evidence_digest(ws:pathlib.Path)->dict:
    """Compute immutable, source-backed signal; not a model-estimated novelty score."""
    with store.connect(ws) as c:
        cl=[(r['claim_id'],r['source_id'],r['page'],r['quote']) for r in c.execute(
            'SELECT claim_id,source_id,page,quote FROM claims ORDER BY claim_id')]
        questions=[(r['question_id'],r['question']) for r in c.execute('SELECT question_id,question FROM questions ORDER BY question_id')]
        rows=[dict(r) for r in c.execute('SELECT source_id,file_path,file_sha,extract_path FROM sources ORDER BY source_id')]
        sources=[(r['source_id'],r['file_sha']) for r in rows]
    # Do not advise reuse of old scientific results when the original real
    # full-text file is missing/replaced. Bibliographic data alone cannot fix it.
    for row in rows:
        original=pathlib.Path(row['file_path'])
        if not original.is_file() or sha(original)!=row['file_sha']:
            raise ValueError('Verified full-text source missing or altered; cannot reuse old conclusions: '+row['source_id'])
        extraction=pathlib.Path(row['extract_path'])
        if not extraction.is_file() or _read(extraction).get('original_sha256')!=row['file_sha']:
            raise ValueError('Extracted source page cache missing or signature mismatch: '+row['source_id'])
    # Track scientific records separately; bibliography growth alone does not
    # justify an expensive 9-agent new research cycle.
    return {'claims':len(cl),'questions':len(questions),'sources':len(sources),
            'claim_ids':[x[0] for x in cl], 'source_ids':[x[0] for x in sources],
            'fingerprint':_fingerprint({'claims':cl,'questions':questions,'sources':sources})}


def _latest_completed_cycle(ws:pathlib.Path)->dict|None:
    file=engine.statefile(ws)
    if not file.is_file():return None
    s=engine.get_state(ws)
    return next((x for x in reversed(s['cycles']) if x['stage']=='COMPLETE'),None)


def _read_cycle_baselines(ws:pathlib.Path)->dict:
    file=home(ws)/'cycle_evidence_baselines.json'
    return _read(file) if file.is_file() else {'schema':1,'cycles':{}}


def record_cycle_baseline(ws:pathlib.Path)->dict:
    ws=ws.expanduser().resolve();last=_latest_completed_cycle(ws)
    if not last:return {'status':'NO_COMPLETED_CYCLE'}
    evidence=evidence_digest(ws)
    path=home(ws)/'cycle_evidence_baselines.json'
    data=_read_cycle_baselines(ws)
    existing=data['cycles'].get(last['id'])
    if existing:
        if existing['fingerprint']!=evidence['fingerprint']:
            # Evidence may grow after cycle completion: baseline is immutable.
            return {'status':'BASELINE_PRESERVED','cycle':last['id'],'baseline':existing['fingerprint']}
        return {'status':'BASELINE_ALREADY_RECORDED','cycle':last['id']}
    data['cycles'][last['id']]={'fingerprint':evidence['fingerprint'], 'claim_ids':evidence['claim_ids'],
                                'source_ids':evidence['source_ids'],'questions_count':evidence['questions'],'recorded_at':store.utc()}
    store.write(path,data)
    return {'status':'CYCLE_BASELINE_SAVED','cycle':last['id'],'fingerprint':evidence['fingerprint']}


def next_decision(ws:pathlib.Path)->dict:
    """A conservative, no-model scheduler advisory. Never authorizes bypassing audits."""
    ws=ws.expanduser().resolve()
    baseline=_read_cycle_baselines(ws)
    last=_latest_completed_cycle(ws)
    if not last:return {'status':'NO_PREVIOUS_COMPLETE_RESEARCH_CYCLE',
                        'decision':'CONTINUE_REQUIRED_STAGES', 'reason':'No completed cognition cycle. Continue required original-text reading and independent audit; do not skip stages based on lexical duplication.',
                        'model_calls':0}
    evidence=evidence_digest(ws)
    before=baseline.get('cycles',{}).get(last['id'])
    if not before:return {'status':'NEEDS_BASELINE_REVIEW','decision':'PAUSE_AND_REVIEW',
                           'reason':'A completed cycle has no immutable evidence baseline. Require explicit review; do not infer or overwrite historical baseline.','model_calls':0}
    if evidence['fingerprint']==before['fingerprint']:
        result={'status':'NO_MEANINGFUL_SOURCE_CHANGE','decision':'DO_NOT_START_RESEARCH_CYCLE',
                'reason':'No changes to the registered full-text evidence or open research questions since the completed cycle. Reuse prior outputs, rather than dispatching duplicate specialist agents.',
                'new_claims':0,'new_sources':0,'requires_model':False}
    else:
        new_claims=set(evidence['claim_ids'])-set(before['claim_ids'])
        new_sources=set(evidence['source_ids'])-set(before['source_ids'])
        if not new_claims and not new_sources:
            result={'status':'RESEARCH_QUESTION_OR_METADATA_CHANGED','decision':'HUMAN_OR_AGENT_TRIAGE_FIRST',
                    'reason':'A question or evidence-record identity changed without new source facts. Triage relevance before repeating high-cost research analysis.',
                    'new_claims':0,'new_sources':0,'requires_model':False}
        else:
            result={'status':'SOURCE_EVIDENCE_CHANGED','decision':'HUMAN_OR_AGENT_TRIAGE_FIRST',
                    'reason':'New source-backed observations exist. First examine the scientific importance and specific open questions; do not automatically rerun all experts.',
                    'new_claims':len(new_claims),'new_sources':len(new_sources),'requires_model':False}
    result.update({'baseline_cycle':last['id'],'current_fingerprint':evidence['fingerprint'],
                   'baseline_fingerprint':before['fingerprint'],'model_calls':0,
                   'hard_gates':'Mandatory R1-R5, independent veto audit, two blinded novelty reviewers, and design-only experiments remain unchanged.'})
    file=home(ws)/'latest_next_decision.json'
    store.write(file,result)
    return result
