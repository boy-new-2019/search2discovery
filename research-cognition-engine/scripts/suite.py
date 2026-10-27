#!/usr/bin/env python3
"""Unified Windows Codex Desktop orchestrator: ORIGINAL v4.4 + v5.0 + v6.0.

This CLI runs LOCAL deterministic Python only: no model/CLI/API dispatch. It
suggests the next authorized step; actual PDF downloads, native subagents and
experiments remain separate permission-gated actions in their original skills.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import pathlib
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE if (HERE / "paper-discovery-preflight").is_dir() else HERE.parents[1]
V5 = ROOT / "paper-discovery-preflight" / "scripts"
V44 = ROOT / "batch-paper-deepread-desktop" / "scripts"
V6 = ROOT / "research-cognition-engine" / "scripts"
for sub in (V5, V44, V6):
    if not sub.is_dir():
        raise RuntimeError('Source path, lawful access or network permission check failed at suite.module (check 26). Do not bypass paywalls or source integrity checks.')
    if str(sub) not in sys.path:
        sys.path.insert(0, str(sub))

import paper_discovery as discovery
import batch as original_batch
import deepread as original_core
import native_v44_launcher as native_runtime
desktop = native_runtime.bridge
import quota_guard as native_budget
import rce
import engine
import store
import v44_original_adapter as adapter
import venue_authority as official_venues


def _safe(fn, *args) -> dict:
    try:
        return fn(*args)
    except (ValueError, RuntimeError, KeyError, OSError, TypeError) as ex:
        return {"status": "BLOCKED", "reason": str(ex)[:550]}


def _reader_installed(ws: pathlib.Path) -> bool:
    return (ws / ".agents" / "skills" / "batch-paper-deepread-desktop" / "scripts" / "batch.py").is_file()


def initialize(ws: pathlib.Path) -> dict:
    ws = ws.expanduser().resolve()
    if not _reader_installed(ws):
        return {"status": "SKILLS_NOT_INSTALLED", "hint": 'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
    existed_goal = (ws / "goal.md").is_file()
    discovered = _safe(discovery.init, ws)
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
        code = desktop.main(["init", "--workspace", str(ws)])
    if code != 0:
        return {"status": "READER_INIT_BLOCKED", "reason": captured.getvalue()[-1300:]}
    if not existed_goal:
        cognition = {"status": "NEEDS_USER_CONFIRMED_GOAL", "hint": 'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
    else:
        cognition = _safe(rce.init, ws)
    return {"status": "INSTALL_READY" if cognition.get("status") != "BLOCKED" else "NEEDS_INSPECTION",
            "v44_original": True, "components": {"v5_discovery": discovered,
            "v44_original_reader": {"status": "INITIALIZED", "native_agents": 16,
                                    "source": "original_v4.4_with_declared_runtime_patches"},
            "v6_cognition": cognition},
            "notes": ['Research evidence and workflow notes (suite.initialize). Use original source evidence; keep frozen constraints and independent quality gates.', 'Research evidence and workflow notes (suite.initialize). Use original source evidence; keep frozen constraints and independent quality gates.', 'Research evidence and workflow notes (suite.initialize). Use original source evidence; keep frozen constraints and independent quality gates.']}


def doctor(ws: pathlib.Path) -> dict:
    ws = ws.expanduser().resolve()
    manifest = ROOT / "research-cognition-engine" / "references" / "original_v44_file_manifest.json"
    if not manifest.is_file():
        return {"status": "BLOCKED", "reason": 'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
    import release_integrity
    audit = release_integrity.verify(ROOT)
    missing = audit['missing']; corrupt = audit['modified']
    authorized_patches = audit['authorized_utility_patches']
    patch_status = audit['runtime_patch_status']
    # Bundle root holds .codex/agents; installed skill root is project/.agents/skills.
    role_dir = ROOT.parents[1] / ".codex" / "agents" if ROOT.name == "skills" else ROOT / ".codex" / "agents"
    if not role_dir.is_dir(): role_dir = ROOT / 'search2discovery/resources/agents'
    role_counts = {k: len(list(role_dir.glob(k + "*.toml"))) for k in ("bpd_", "rce_")}
    import agent_profiles
    profile_audit = agent_profiles.audit(role_dir)
    bad = profile_audit['status'] != 'VALID' or missing or corrupt or patch_status in ('INVALID','PATCH_INTEGRITY_MISMATCH') or role_counts != {"bpd_":16, "rce_":11}
    return {"status": "BLOCKED" if bad else ('PATCHED_V44_VERIFIED' if authorized_patches else 'ORIGINAL_V44_VERIFIED'),
            "runtime_patch_status": patch_status, "authorized_utility_patches": authorized_patches,
            "source_archive_sha256": audit["source_archive_sha256"],
            "source_file_count": audit["source_file_count"],
            "missing": missing, "modified": corrupt, "role_counts": role_counts,
            "project": str(ws), "agent_profile_validation": profile_audit,
            "native_subagent_availability": "REQUIRES_REAL_WINDOWS_CODEX_APP_CHECK"}


def status(ws: pathlib.Path) -> dict:
    ws = ws.expanduser().resolve()
    return {"v5_discovery": _safe(discovery.status, ws),
            "v44_original_reader": _safe(desktop.status, ws),
            "v6_cognition": _safe(rce.status, ws),
            "official_venue_authority": official_venues.status(ws),
            "shared_native_budget": (_safe(native_budget.status, ws, desktop.native_cfg(ws)["budget"])
                                     if (ws / "native_config.json").is_file() else None)}


def plan(ws: pathlib.Path) -> dict:
    ws = ws.expanduser().resolve()
    return {"v5_catalogue": _safe(discovery.status, ws),
            "v44_original_native_budget_plan": (_safe(native_budget.plan, ws, desktop.native_cfg(ws)["budget"])
                                               if (ws / "native_config.json").is_file() else {"status":"NOT_INITIALIZED"}),
            "v6_cognition": _safe(rce.status, ws),
            "official_venue_authority":official_venues.status(ws),
            "academic_contract": 'Research evidence and workflow notes (suite.plan). Use original source evidence; keep frozen constraints and independent quality gates.'}


def next_action(ws: pathlib.Path, *, allow_incomplete_discovery: bool = False) -> dict:
    ws = ws.expanduser().resolve()
    try:
        found = discovery.status(ws)
    except (ValueError, RuntimeError, OSError) as exc:
        return {"status": "NEEDS_DISCOVERY_INIT", "reason": str(exc),
                "next": "Run paper_discovery.py init, then execute real searches only with explicit user authorization"}
    import evidence_gain_scheduler as gain_scheduler
    acquisition = gain_scheduler.acquisition_gate(found)
    discovery_pending = acquisition["pending"] and not allow_incomplete_discovery
    # Acquisition is still mandatory for final acceptance. It must not starve
    # an already admitted, source-verified reader campaign of original work.
    if not (ws / "output" / "batch" / "state.json").is_file():
        if discovery_pending:
            return {"status": "NEEDS_DISCOVERY", "counts": found.get("counts"),
                    "shortfalls": found.get("shortfalls"), "acquisition_gate": acquisition,
                    "next": "Complete reviewed discovery; no admitted reader campaign exists"}
        return {"status": "NEEDS_ORIGINAL_V44_INGEST",
                "next": 'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
    try:
        state = original_batch.load_state(ws)
    except (ValueError, KeyError, RuntimeError, OSError) as exc:
        return {"status": "BLOCKED_ORIGINAL_V44_READER_STATE", "reason": str(exc)[:600],
                "next": 'Inspect the signed checkpoint, verify the original full-text evidence and reviewer receipts, then continue only the stage justified by a substantive evidence gap and available quota.'}
    if not original_batch.available(state):
        return {"status": "NEEDS_READABLE_FULLTEXT", "next": 'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
    if not state.get("frozen"):
        job = original_batch.next_screen(ws, state)
        if job:
            pause = gain_scheduler.automatic_search_pause(ws)
            if pause:
                return {"status": "PAUSED_FOR_EVIDENCE_STRATEGY_REVIEW",
                        "job": job["id"], "evidence_gain_policy": pause,
                        "next": "Review target-gap routing before any new screening; retain every pending job and charge"}
            return {"status": "READ_SCREENING", "stage":job["stage"], "job":job["id"],
                    "next": 'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
        if not state.get("selection"):
            return {"status": "READY_FOR_ORIGINAL_V44_SELECT", "next": "Run native_v44_launcher.py select; S1/S2 already done"}
        if len(state["selection"].get("last_selected", [])) < original_batch.cfg_at(ws)["core_min"]:
            return {"status": "INSUFFICIENT_ELIGIBLE_CORE", "core_count":len(state["selection"].get("last_selected", [])),
                    "next": 'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
        can, gaps = original_batch.can_seal(ws, state)
        if not can:
            return {"status": "READER_SEAL_BLOCKED", "reasons":gaps,
                    "next": 'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
        # Match seal()'s original target/supplement requirements as well as
        # can_seal(). Coverage warnings are retained, never silently cleared.
        shortfalls = gain_scheduler.original_seal_shortfalls(original_batch, ws, state)
        if any(shortfalls.values()):
            return {"status": "READER_SEAL_BLOCKED", "reasons": shortfalls,
                    "acquisition_gate": acquisition,
                    "next": "Meet original target and supplemental requirements; no automatic gap waiver"}
        original_batch.verify_sources(ws, state)
        return {"status": "READY_TO_SEAL_ORIGINAL_V44", "selected_core_papers":len(state["selection"]["last_selected"]),
                "coverage_gaps": state["selection"].get("gaps", []),
                "acquisition_gate": acquisition,
                "evidence_gain_policy": gain_scheduler.status(ws),
                "next": "Run original native_v44_launcher.py seal without a gap waiver; retain coverage warnings"}
    sub = pathlib.Path(state["frozen"]["core_workspace"])
    try:
        ctx = original_core.env(sub)
        job = original_core.next_job(ctx)
        reading = original_core.run_status(ctx)
    except (ValueError, RuntimeError, KeyError, OSError) as exc:
        return {"status": "BLOCKED_CORE_SNAPSHOT", "reason": str(exc)[:600],
                "next": 'Inspect the signed checkpoint, verify the original full-text evidence and reviewer receipts, then continue only the stage justified by a substantive evidence gap and available quota.'}
    if job is not None:
        return {"status": "READ_ORIGINAL_V44_CORE", "job":job["id"], "job_type":job["type"],
                "round":job.get("round"), "acquisition_gate": acquisition,
                "evidence_gain_policy": gain_scheduler.status(ws),
                "next": "Prepare only with available authorized quota; retain five rounds, independent roles and veto"}
    if reading.get("status") not in ("COMPLETE",):
        return {"status": "READER_NOT_APPROVED", "reading_status":reading["status"],
                "next": "Failed/missing audit, coverage or visual check requires correction; never silently PASS"}
    if discovery_pending:
        return {"status": "NEEDS_DISCOVERY", "counts": found.get("counts"),
                "shortfalls": found.get("shortfalls"), "acquisition_gate": acquisition,
                "next": "Reader work is complete; unresolved acquisition still blocks downstream acceptance"}
    if not (ws / "research_cognition_config.json").is_file():
        return {"status":"NEEDS_RCE_INIT", "next":"Run suite.py init after user confirms goal.md"}
    with store.connect(ws) as con:
        works = con.execute("SELECT COUNT(*) FROM works").fetchone()[0]
        claims = con.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
    if not works or not claims:
        return {"status":"NEEDS_ORIGINAL_V44_EVIDENCE_SYNC",
                "next":"Run suite.py sync-reading-evidence after original five-round final audit; no second model reading required"}
    try:
        rce_state = engine.get_state(ws)
    except (ValueError, RuntimeError):
        return {"status":"NEEDS_RCE_INIT"}
    if not rce_state["cycles"]:
        return {"status":"READY_FOR_RCE_CYCLE", "next":"Explicitly approve a research cognition cycle, then rce.py new-cycle/prepare/collect/commit"}
    tail = rce_state["cycles"][-1]
    if tail["stage"] != "COMPLETE":
        return {"status":"READY_FOR_RCE_NATIVE_TASK", "stage":tail["stage"],
                "next":"Use original v6 rce.py prepare to dispatch real Codex Desktop subagents, then collect/commit"}
    return {"status":"SCIENTIFIC_RECOMMENDATION_PENDING_USER_APPROVAL",
            "next":"Review research_discovery_package; research hypotheses are not experimentally validated or approved algorithm updates"}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ('gap-record','gap-status'):
        import evidence_gain_scheduler as gaps
        parser=argparse.ArgumentParser();parser.add_argument('command');parser.add_argument('--workspace',required=True,type=pathlib.Path);parser.add_argument('--event-file',type=pathlib.Path)
        args=parser.parse_args(argv)
        if args.command=='gap-record' and not args.event_file:parser.error('--event-file is required')
        result=gaps.record_batch(args.workspace,store.read(args.event_file)) if args.command=='gap-record' else gaps.status(args.workspace)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    if argv and argv[0]=='campaign-plan':
        import campaign
        return campaign.main(argv[1:])
    if argv and argv[0] in ('round-reports','smart-next','round-baseline'):
        import round_intelligence as rounds
        sub=argparse.ArgumentParser(description='v6.5 round reports and evidence-aware efficiency decisions')
        sub.add_argument('command')
        sub.add_argument('--workspace',required=True,type=pathlib.Path)
        sub.add_argument('--authorized',action='store_true')
        options=sub.parse_args(argv)
        ws=options.workspace.expanduser().resolve()
        try:
            if options.command=='round-reports': result=rounds.refresh(ws)
            elif options.command=='smart-next':result=rounds.next_decision(ws)
            else:
                if not options.authorized:raise ValueError('Signed task, stage, commit receipt or report provenance check failed at suite.main (check 211). Resume only from a verified state.')
                result=rounds.record_cycle_baseline(ws)
            print(json.dumps(result,ensure_ascii=False,indent=2))
            return 0
        except (OSError,ValueError,RuntimeError,KeyError) as exc:
            print(json.dumps({'status':'BLOCKED','reason':str(exc)},ensure_ascii=False),file=sys.stderr)
            return 2
    extended = {'next-v61','auto','auto-sync','question-plan','question-search','question-download',
                'reader-prepare','reader-collect','reader-commit','rce-prepare','rce-collect','rce-commit'}
    if argv and argv[0]=='pro5x-shortlist':
        import pro5x_shortlist
        return pro5x_shortlist.main(argv[1:])
    if argv and argv[0].startswith('pro5x-'):
        import pro5x_optimizer
        return pro5x_optimizer.main([argv[0].removeprefix('pro5x-'),*argv[1:]])
    if argv and argv[0].startswith('official-'):
        return official_venues.main([argv[0].removeprefix('official-'),*argv[1:]])
    if argv and argv[0].startswith('topic-'):
        import topic_to_plan
        return topic_to_plan.main([argv[0].removeprefix('topic-'), *argv[1:]])
    if argv and argv[0] in extended:
        if argv[0] in ('next-v61','auto') and '--workspace' in argv:
            ws=pathlib.Path(argv[argv.index('--workspace')+1]);official_venues.check(ws,online=True)
        import workflow_v61
        return workflow_v61.main(argv)
    p = argparse.ArgumentParser(description='Inspect the signed checkpoint, verify the original full-text evidence and reviewer receipts, then continue only the stage justified by a substantive evidence gap and available quota.')
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("init", "doctor", "status", "plan", "next", "sync-reading-evidence"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--workspace", type=pathlib.Path, required=True)
        if name == "next":
            cmd.add_argument("--allow-incomplete-discovery", action="store_true")
        if name == "sync-reading-evidence":
            cmd.add_argument("--max-papers", type=int)
    args = p.parse_args(argv)
    ws = args.workspace.expanduser().resolve()
    try:
        if args.cmd in ('init','next','plan'):
            official_venues.check(ws,online=True)
        if args.cmd == "init": out = initialize(ws)
        elif args.cmd == "doctor": out = doctor(ws)
        elif args.cmd == "status": out = status(ws)
        elif args.cmd == "plan": out = plan(ws)
        elif args.cmd == "next": out = next_action(ws,allow_incomplete_discovery=args.allow_incomplete_discovery)
        elif args.cmd == "sync-reading-evidence": out = adapter.sync(ws,limit_papers=args.max_papers)
        else: raise ValueError('Authentic source, page quotation or evidence integrity check failed at suite.main (check 256). Never accept unverified material.')
        print(json.dumps(out,ensure_ascii=False,indent=2,default=str))
        return 0 if out.get("status") not in ("BLOCKED","READER_INIT_BLOCKED","SKILLS_NOT_INSTALLED") else 2
    except (ValueError,RuntimeError,KeyError,OSError,TypeError) as exc:
        print(json.dumps({"status":"BLOCKED","reason":str(exc),"command":args.cmd},ensure_ascii=False),file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
