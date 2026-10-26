#!/usr/bin/env python3
"""Optional source-preserving evidence compiler, NOT a substitute for scholarly synthesis.

Only emits verified observations from completed source-reading jobs, with zero
new scientific assertions. If insufficient evidence exists, hands off to the
original real expert group. Each produced artifact passes core.validate().
"""
from __future__ import annotations
import copy
import deepread as core

def _stable_unique(seq):
    seen=set();result=[]
    for x in seq:
        key=core.htext(core.dump(x))
        if key not in seen:
            result.append(x);seen.add(key)
    return result

def make(ctx:dict,job:dict)->dict|None:
    typ=job['type'];r=job.get('round');pid=job.get('paper_id')
    if typ=='merge':
        leaves=[core.answer(ctx,f'R{r:02d}_{pid}_{ch["chunk_id"]}') for ch in core.paper_chunks(ctx,pid)]
        cited=[]
        for leaf in leaves:
            for obs in leaf['observations']:
                if obs.get('evidence'):
                    cited.append(copy.deepcopy(obs))
        pts=_stable_unique(cited)
        if len(pts)<2:return None
        flags=_stable_unique([copy.deepcopy(f) for v in leaves for f in v['visual_flags']])
        qs=list(dict.fromkeys(q for v in leaves for q in v['open_questions']))
        d={'round':r,'paper_id':pid,
           'overview':f'Round {r} source evidence index: {len(pts)} observations from {len(leaves)} verified source chunks. Mechanical compilation only, NOT a new interpretive method evaluation.',
           'key_points':pts[:160], 'method_details':[], 'weaknesses':[],
           'open_questions':qs[:100], 'visual_flags':flags[:150], 'facts':[]}
        # Avoid producing an invalid claim. This deterministic compilation can
        # be replaced by a user-chosen real expert when deeper synthesis is needed.
        core.validate(ctx,job,d)
        return d
    if typ=='group' and len(job['paper_ids'])==1:
        row=core.answer(ctx,f'R{r:02d}_{job["paper_ids"][0]}_MERGE')
        d={'round':r,'group_id':job['group_id'],'paper_ids':list(job['paper_ids']),
           'overview':f'Round {r} single-paper group index (no cross-paper comparison): '+row['overview'],
           'comparisons':[],'gaps':['A single-paper group cannot support a cross-paper comparison.'], 'priorities':[]}
        core.validate(ctx,job,d)
        return d
    if typ=='master' and len(core.group_defs(ctx))==1:
        group_id=core.group_defs(ctx)[0][0]
        prev=core.answer(ctx,f'R{r:02d}_{group_id}_GROUP')
        d=copy.deepcopy(prev)
        d.update({'round':r,'group_id':'ALL','paper_ids':list(job['paper_ids'])})
        core.validate(ctx,job,d)
        return d
    return None
