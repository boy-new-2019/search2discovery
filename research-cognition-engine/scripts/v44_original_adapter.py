#!/usr/bin/env python3
"""Non-destructive v4.4 ORIGINAL -> v6 research-memory evidence bridge.

Uses original frozen-core paper hashes and page-extraction rules. It does not
rewrite either the original v4.4 reading engine or the v6 store schema.
Only independently committed, SHA-verified source observations are imported;
no scientific interpretation or genuine experiment is inferred from citations.
"""
from __future__ import annotations

import hashlib
import pathlib
import sqlite3
import sys
import unicodedata
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
SKILLS = HERE.parents[1]  # <project>/.agents/skills when installed, package root when bundled
READ = SKILLS / "batch-paper-deepread-desktop" / "scripts"
if str(READ) not in sys.path:
    sys.path.insert(0, str(READ))
import batch
import deepread as original
import store


class EvidenceBridgeError(ValueError):
    pass


def _literal_source_quote(page_text: str, quote: str) -> str:
    """Map an already validated reader quote back to an exact source substring.

    Reader normalization removes PDF whitespace, soft hyphens and compatibility
    glyphs. Memory retains its stricter literal matcher and unchanged sources.
    """
    if store.norm(quote) in store.norm(page_text):
        return quote
    # NFKC composition can cross character boundaries elsewhere on a PDF page.
    # Map canonically decomposed characters, retaining exact source offsets.
    decomposed, pending = [], []
    for index, char in enumerate(page_text):
        for normalized in unicodedata.normalize("NFKD", char):
            item = (normalized, index)
            if unicodedata.combining(normalized):
                pending.append(item)
            else:
                decomposed.extend(sorted(pending, key=lambda x: unicodedata.combining(x[0])))
                pending = []
                decomposed.append(item)
    decomposed.extend(sorted(pending, key=lambda x: unicodedata.combining(x[0])))
    chars, offsets = [], []
    for char, index in decomposed:
        if char != "\u00ad" and not char.isspace():
            chars.append(char)
            offsets.append(index)
    def decomposed_norm(value):
        return "".join(x for x in unicodedata.normalize("NFKD", value)
                       if x != "\u00ad" and not x.isspace())
    flat, target = "".join(chars), decomposed_norm(quote)
    if flat != decomposed_norm(page_text) or not target:
        raise EvidenceBridgeError("Reader quotation cannot map to a literal source span")
    start = flat.find(target)
    while start >= 0:
        positions = offsets[start:start + len(target)]
        literal = page_text[min(positions):max(positions) + 1]
        # Reject partial compatibility-character or combining-cluster matches.
        # The original NFKC reader and strict literal memory matcher stay intact.
        if original.norm(literal) == original.norm(quote):
            if not 10 <= len(store.norm(literal)) <= 280:
                raise EvidenceBridgeError("Literal source span exceeds memory quotation bounds")
            return literal
        start = flat.find(target, start + 1)
    raise EvidenceBridgeError("Reader quotation cannot map to a literal source span")



def _raw_file(ws: pathlib.Path, relative: str) -> pathlib.Path:
    folder = (ws / "input").resolve()
    file = (folder / relative).resolve()
    if not file.is_relative_to(folder) or not file.is_file():
        raise EvidenceBridgeError('Authentic source, page quotation or evidence integrity check failed at v44_original_adapter._raw_file (check 35). Never accept unverified material.')
    return file


def _original_catalogue(ws: pathlib.Path) -> dict:
    index = ws / "output" / "discovery_preflight" / "state.json"
    if not index.exists():
        return {}
    state = store.read(index)
    result = {}
    download_log = state.get("download_log", {})
    if not isinstance(download_log, dict):
        raise EvidenceBridgeError('Authentic source, page quotation or evidence integrity check failed at v44_original_adapter._original_catalogue (check 47). Never accept unverified material.')
    with store.connect(ws) as con:
        known = {x["work_id"] for x in con.execute("SELECT work_id FROM works")}
    for workid, info in download_log.items():
        if workid in known and info.get("status") == "FULLTEXT_READY" and isinstance(info.get("sha256"), str):
            digest = info["sha256"].lower()
            if digest in result and result[digest] != workid:
                raise EvidenceBridgeError('Authentic source, page quotation or evidence integrity check failed at v44_original_adapter._original_catalogue (check 54). Never accept unverified material.')
            result[digest] = workid
    return result


def _get_work(ws: pathlib.Path, paper: dict, digest: str, verified_v5: dict) -> str:
    candidate = verified_v5.get(digest)
    with store.connect(ws) as con:
        existing_source = con.execute("SELECT work_id,file_sha FROM sources WHERE source_id=?",
                                      ("SRC-" + digest[:18],)).fetchone()
        if existing_source:
            if existing_source["file_sha"] != digest:
                raise EvidenceBridgeError('Authentic source, page quotation or evidence integrity check failed at v44_original_adapter._get_work (check 66). Never accept unverified material.')
            if candidate and candidate != existing_source["work_id"]:
                raise EvidenceBridgeError('Authentic source, page quotation or evidence integrity check failed at v44_original_adapter._get_work (check 68). Never accept unverified material.')
            candidate = existing_source["work_id"]
        if not candidate:
            candidate = "LOCAL_ORIGINAL_V44_" + digest[:18]
        found = con.execute("SELECT work_id FROM works WHERE work_id=?", (candidate,)).fetchone()
        if not found:
            name = pathlib.PurePosixPath(paper["file"]).name
            title = paper.get("title_guess") or ("LOCAL_FULLTEXT_FILENAME:" + name)
            con.execute(
                "INSERT INTO works(work_id,title,category,doi,year,venue,url,record_sha,source_status) VALUES (?,?,?,?,?,?,?,?,?)",
                (candidate, title, "core", paper.get("doi_guess") or "", None, "", "", digest, "BIB_ONLY"),
            )
            store.event(con, "ORIGINAL_V44_LOCAL_WORK_REGISTERED", {
                "work_id": candidate, "file_label": name, "original_file_sha256": digest,
                "metadata_unverified": True,
            })
        return candidate


def _register_source(ws: pathlib.Path, workid: str, original_path: pathlib.Path,
                     digest: str, frozen_pages: list[str]) -> str:
    source_id = "SRC-" + digest[:18]
    cache = store.root(ws) / "source_cache" / (source_id + ".json")
    with store.connect(ws) as con:
        row = con.execute("SELECT * FROM sources WHERE source_id=?", (source_id,)).fetchone()
        if row:
            if row["work_id"] != workid or row["file_sha"] != digest:
                raise EvidenceBridgeError('Authentic source, page quotation or evidence integrity check failed at v44_original_adapter._register_source (check 95). Never accept unverified material.')
            cached = store.read(pathlib.Path(row["extract_path"]))
            if cached.get("pages") == frozen_pages:
                return source_id
            # This happens when v5/RCE first extracted a PDF with a different
            # page-text ordering (e.g., fitz sort=False) from original v4.4's
            # published sort=True. Preserve both anchors; never overwrite
            # already-proven v5 quotes or mutate the source cache in place.
            source_id = "SRC-" + digest[:18] + "-V44"
            cache = store.root(ws) / "source_cache" / (source_id + ".json")
            alt = con.execute("SELECT * FROM sources WHERE source_id=?", (source_id,)).fetchone()
            if alt:
                if alt["work_id"] != workid or alt["file_sha"] != digest:
                    raise EvidenceBridgeError('Frozen research topic or signed research contract mismatch at v44_original_adapter._register_source (check 108). Reconfirm boundaries; do not overwrite approved work.')
                if store.read(pathlib.Path(alt["extract_path"])).get("pages") != frozen_pages:
                    raise EvidenceBridgeError('Frozen research topic or signed research contract mismatch at v44_original_adapter._register_source (check 110). Reconfirm boundaries; do not overwrite approved work.')
                return source_id
    # Trust original v4.4 published extraction only after source SHA and frozen
    # snapshot pages are independently matched in sync() below.
    store.write(cache, {"source_id": source_id, "work_id": workid,
                        "original_sha256": digest, "pages": frozen_pages,
                        "extract_kind": "ORIGINAL_V44_PUBLISHED_PAGE_CONTRACT_FIGURES_UNCHECKED"})
    with store.connect(ws) as con:
        con.execute("INSERT OR IGNORE INTO sources VALUES (?,?,?,?,?,?,?)",
                    (source_id, workid, str(original_path), digest, len(frozen_pages), str(cache), store.utc()))
        con.execute("UPDATE works SET source_status='TEXT_AVAILABLE' WHERE work_id=?", (workid,))
        store.event(con, "ORIGINAL_V44_SOURCE_ANCHORED", {"source_id": source_id, "file_sha256": digest,
                     "original_path": str(original_path), "v44_page_count": len(frozen_pages)})
    return source_id


def _verified_member_commit(ws: pathlib.Path, job: str, payload: dict) -> dict:
    folder = ws / "output" / "native" / "tasks" / job
    record = folder / "commit.json"
    answer = folder / "consolidated.json"
    if not (record.is_file() and answer.is_file()):
        raise EvidenceBridgeError('Authentic source, page quotation or evidence integrity check failed at v44_original_adapter._verified_member_commit (check 131). Never accept unverified material.')
    c = store.read(record)
    if c.get("status") != "COMMITTED" or c.get("consolidated_sha256") != hashlib.sha256(answer.read_bytes()).hexdigest():
        raise EvidenceBridgeError('Authentic source, page quotation or evidence integrity check failed at v44_original_adapter._verified_member_commit (check 134). Never accept unverified material.')
    if store.hashobj(payload) != store.hashobj(store.read(answer)):
        raise EvidenceBridgeError('Authentic source, page quotation or evidence integrity check failed at v44_original_adapter._verified_member_commit (check 136). Never accept unverified material.')
    member_ids = c.get("member_roles")
    receipts = c.get("receipt_shas")
    if not isinstance(member_ids, list) or not member_ids or not isinstance(receipts, dict) or set(member_ids) != set(receipts):
        raise EvidenceBridgeError('Authentic source, page quotation or evidence integrity check failed at v44_original_adapter._verified_member_commit (check 140). Never accept unverified material.')
    for role in member_ids:
        member_receipt = folder / "receipts" / (role + ".json")
        member_answer = folder / "answers" / (role + ".json")
        if not (member_receipt.is_file() and member_answer.is_file()):
            raise EvidenceBridgeError('Authentic source, page quotation or evidence integrity check failed at v44_original_adapter._verified_member_commit (check 145). Never accept unverified material.')
        if hashlib.sha256(member_receipt.read_bytes()).hexdigest() != receipts[role]:
            raise EvidenceBridgeError('Authentic source, page quotation or evidence integrity check failed at v44_original_adapter._verified_member_commit (check 147). Never accept unverified material.')
        r = store.read(member_receipt)
        if (r.get("role") != role or r.get("job_id") != job or
            r.get("answer_sha256") != hashlib.sha256(member_answer.read_bytes()).hexdigest()):
            raise EvidenceBridgeError('Authentic source, page quotation or evidence integrity check failed at v44_original_adapter._verified_member_commit (check 151). Never accept unverified material.')
        if not r.get("native_subagent_thread_ref"):
            raise EvidenceBridgeError('Authentic source, page quotation or evidence integrity check failed at v44_original_adapter._verified_member_commit (check 153). Never accept unverified material.')
    return c


def sync(ws: pathlib.Path, *, limit_papers: int | None = None) -> dict:
    """Idempotent; safe to call after any validated v4.4 reading round.

    Core paper IDs in v4.4 subworkspace differ from original corpus IDs.
    Match by SHA256, not name. Re-read scientific claims only from original
    validated leaf results; no model calls or semantic promotion.
    """
    ws = ws.expanduser().resolve()
    if not (ws / "output" / "batch" / "state.json").is_file():
        raise EvidenceBridgeError('Authentic source, page quotation or evidence integrity check failed at v44_original_adapter.sync (check 166). Never accept unverified material.')
    state = batch.load_state(ws)
    frozen = state.get("frozen")
    if not frozen:
        raise EvidenceBridgeError('Frozen research topic or signed research contract mismatch at v44_original_adapter.sync (check 170). Reconfirm boundaries; do not overwrite approved work.')
    sub = pathlib.Path(frozen["core_workspace"]).resolve()
    if not sub.is_dir() or not sub.is_relative_to(ws.resolve()):
        raise EvidenceBridgeError('Frozen research topic or signed research contract mismatch at v44_original_adapter.sync (check 173). Reconfirm boundaries; do not overwrite approved work.')
    ctx = original.env(sub)
    import rce
    rce.init(ws)
    bibliographic = store.import_catalogue(ws)
    v5_downloads = _original_catalogue(ws)
    original_papers = {x["sha256"]: x for x in state["papers"] if x.get("status") == "READY"}
    result = []
    created_works = 0
    created_sources = 0
    imported = 0
    examined = 0
    skipped_short = 0
    completed_leaves = 0
    not_completed = 0
    max_count = limit_papers or len(ctx["paper_ids"])
    if type(max_count) is not int or max_count < 1:
        raise ValueError('Input, evidence or workflow invariant failed at v44_original_adapter.sync (check 190); inspect the signed task record and original source.')
    for corepid in ctx["paper_ids"][:max_count]:
        record = original.paper_row(ctx, corepid)
        digest = record["sha256"].lower()
        paper = original_papers.get(digest)
        if paper is None:
            raise EvidenceBridgeError('Authentic source, page quotation or evidence integrity check failed at v44_original_adapter.sync (check 196). Never accept unverified material.')
        original_path = _raw_file(ws, paper["file"])
        if hashlib.sha256(original_path.read_bytes()).hexdigest() != digest:
            raise EvidenceBridgeError('Authentic source, page quotation or evidence integrity check failed at v44_original_adapter.sync (check 199). Never accept unverified material.')
        snap = (sub / "input" / record["file"]).resolve()
        if not snap.is_file() or hashlib.sha256(snap.read_bytes()).hexdigest() != digest:
            raise EvidenceBridgeError('Authentic source, page quotation or evidence integrity check failed at v44_original_adapter.sync (check 202). Never accept unverified material.')
        pages = original.paper_pages(ctx, corepid)
        # Strictly preserve original v4.4 source page extraction and chapter offsets.
        original_corpus = batch.corpus_path(ws, paper["id"])
        from_corpus = store.read(original_corpus)
        if from_corpus.get("sha256") != digest or from_corpus.get("pages") != pages:
            raise EvidenceBridgeError('Authentic source, page quotation or evidence integrity check failed at v44_original_adapter.sync (check 208). Never accept unverified material.')
        workid = v5_downloads.get(digest) or ("LOCAL_ORIGINAL_V44_" + digest[:18])
        with store.connect(ws) as con:
            existed_work = bool(con.execute("SELECT 1 FROM works WHERE work_id=?", (workid,)).fetchone())
            existed_source = bool(con.execute("SELECT 1 FROM sources WHERE source_id=?", ("SRC-" + digest[:18],)).fetchone())
        workid = _get_work(ws, paper, digest, v5_downloads)
        with store.connect(ws) as con:
            existed_alt = bool(con.execute("SELECT 1 FROM sources WHERE source_id=?", ("SRC-" + digest[:18] + "-V44",)).fetchone())
        source_id = _register_source(ws, workid, original_path, digest, pages)
        created_works += not existed_work
        created_sources += (not existed_alt if source_id.endswith("-V44") else not existed_source)
        for round_no in range(1, ctx["cfg"]["rounds"] + 1):
            for chunk in original.paper_chunks(ctx, corepid):
                jid = f"R{round_no:02d}_{corepid}_{chunk['chunk_id']}"
                if not original.completed(ctx, jid):
                    not_completed += 1
                    continue
                data = original.answer(ctx, jid)
                _verified_member_commit(ws, jid, data)
                job = {"id": jid, "type": "leaf", "round": round_no, "paper_id": corepid,
                       "chunk_id": chunk["chunk_id"]}
                # Strictly revalidate each anchor against the exact original
                # v4.4 frozen snapshot, not a machine-created summary.
                original.validate(ctx, job, data)
                completed_leaves += 1
                for obs in data.get("observations", []):
                    status = obs.get("status")
                    claim_kind = f"{status}:{obs.get('category','unknown')}"
                    for cite in obs.get("evidence", []):
                        examined += 1
                        quote = cite["quote"]
                        if len(store.norm(quote)) < 10:
                            skipped_short += 1
                            continue
                        native_quote = quote
                        quote = _literal_source_quote(pages[cite["page"] - 1], native_quote)
                        store.checked_quote(ws, source_id, cite["page"], quote)
                        claim_id = "CLM-" + store.hashobj({"original_sha256": digest,
                                   "text": obs["claim"], "page": cite["page"],
                                   "quote": native_quote, "kind": claim_kind})[:18]
                        with store.connect(ws) as con:
                            exists = bool(con.execute("SELECT 1 FROM claims WHERE claim_id=?", (claim_id,)).fetchone())
                            if not exists:
                                con.execute("INSERT INTO claims VALUES (?,?,?,?,?,?,?,?,?,?)",
                                            (claim_id, source_id, workid, obs["claim"], claim_kind,
                                             cite["page"], quote,
                                             obs.get("source_role") or "ORIGINAL_V44_VERIFIED_READING_TEAM",
                                             "ANCHOR_CHECKED_SEMANTICS_NOT_AUDITED", store.utc()))
                                store.event(con, "ORIGINAL_V44_READING_EVIDENCE_IMPORTED",
                                            {"claim_id": claim_id, "source_id": source_id, "job": jid,
                                             "research_inference_only": status == "inferred",
                                             "native_quote": native_quote,
                                             "source_literal_quote": quote,
                                             "quote_mapping": "LITERAL_SOURCE_SPAN" if quote != native_quote else "UNCHANGED"})
                                imported += 1
        result.append({"core_paper_id": corepid, "source_paper_id": paper["id"],
                       "work_id": workid, "source_id": source_id,
                       "sha256": digest})
    return {"status": "SOURCE_EVIDENCE_SYNCED", "original_v44": True,
            "v5_catalogue": bibliographic.get("status"),
            "new_works": created_works, "new_sources": created_sources,
            "new_anchor_checked_claims": imported,
            "existing_or_empty_leaf_jobs": completed_leaves,
            "pending_leaf_jobs": not_completed, "citations_checked": examined,
            "short_v44_quotes_not_promoted": skipped_short,
            "papers": result,
            "scientific_limit": 'Bibliographic metadata, source-page quote matching and agent judgments are distinct epistemic levels. No unperformed simulation, training or experiment provides scientific measurements; verify figures and prior art independently.'}
