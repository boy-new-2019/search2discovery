"""Bounded whole-record evidence packing with an immutable complete lookup index."""
from __future__ import annotations
import collections,json,pathlib
import store


def archive(ws, sources, claims):
    payload={"scope":"SOURCE_METADATA_AND_ANCHOR_CHECKED_CLAIMS_NOT_SCIENTIFIC_TRUTH",
             "sources":sources,"claims":claims}
    raw=(store.dump(payload)+"\n").encode("utf-8")
    digest=store.hashbytes(raw)
    path=store.root(ws)/"evidence_context_index"/(digest+".json")
    path.parent.mkdir(parents=True,exist_ok=True)
    try:
        with path.open("xb") as handle:handle.write(raw)
    except FileExistsError:
        if path.read_bytes()!=raw:raise ValueError("Changed immutable evidence context index")
    return {"path":str(path),"sha256":digest,"fulltext_sources":len(sources),
            "anchor_records":len(claims),
            "use":"Lookup omitted original source paths and claim IDs when needed; verify hashes and original pages. The index is not a semantic review."}


def required_ids(context):
    result=set()
    for row in context.get("hypotheses",[]):
        values=row.get("linked_claims",[])
        if isinstance(values,str):values=json.loads(values)
        result.update(values)
    for row in context.get("contradictions",[]):
        result.update(row[k] for k in ("left_id","right_id") if row.get(k))
    return result


def balanced(claims):
    groups=collections.defaultdict(lambda:collections.defaultdict(collections.deque))
    for row in claims:
        groups[row.get("source_id") or row["work_id"]][row.get("claim_kind","")].append(row)
    # Rotate source and claim kind so one prolific, recently read paper cannot
    # replace all other papers or all published evidence with its conclusions.
    queues={source:collections.deque(sorted(kinds)) for source,kinds in groups.items()}
    active=collections.deque(sorted(groups))
    while active:
        source=active.popleft();kinds=queues[source];kind=kinds.popleft()
        yield groups[source][kind].popleft()
        if groups[source][kind]:kinds.append(kind)
        if kinds:active.append(source)


def fit(context, cap, render):
    """Never truncate quote/text fields or drop hypothesis-linked evidence."""
    claims=context.get("claims",[])
    pinned=required_ids(context)
    known={row["claim_id"] for row in claims}
    if pinned-known:raise ValueError("Linked claim missing from complete evidence context")
    selected=[row for row in claims if row["claim_id"] in pinned]
    result={**context,"claims":selected}
    result["evidence_selection"]={"policy":"WHOLE_RECORD_SOURCE_AND_KIND_ROUND_ROBIN",
        "available_claims":len(claims),"included_claims":len(selected),
        "omitted_claims":len(claims)-len(selected),"required_claims":len(pinned),
        "omissions_available_in_hash_bound_index":True}
    def size():return max(len(render(result,role)) for role in render.roles)
    if size()>cap:
        raise ValueError("Required stage evidence exceeds context budget; retain linked claims, reviews and plans and explicitly revise the evidence scope")
    for row in balanced(claims):
        if row["claim_id"] in pinned:continue
        if len(selected)>=150:break
        selected.append(row)
        result["evidence_selection"]["included_claims"]=len(selected)
        result["evidence_selection"]["omitted_claims"]=len(claims)-len(selected)
        if size()>cap:selected.pop()
    result["evidence_selection"]["included_claims"]=len(selected)
    result["evidence_selection"]["omitted_claims"]=len(claims)-len(selected)
    if claims and not selected:raise ValueError("No complete source claim fits the context budget")
    if size()>cap:raise ValueError("Packed evidence still exceeds context budget")
    return result
