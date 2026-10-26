#!/usr/bin/env python3
"""Install search2discovery v1.0.0 in a Windows Codex Desktop project.

A standalone package that never overwrites input/, output/ research data,
existing goal.md, or user-tuned project configs. All three skills are installed
under .agents/skills/ and all 27 project native subagent TOMLs under
.codex/agents/. No Codex CLI or live model calls.
"""
from __future__ import annotations

import argparse
import datetime as dt
import filecmp
import hashlib
import json
import os
import pathlib
import shutil
import sys
import tempfile
import tomllib
import uuid

ROOT = pathlib.Path(__file__).resolve().parent
SKILLS = ("paper-discovery-preflight", "batch-paper-deepread-desktop", "research-cognition-engine", "search2discovery")
EXPECTED_AGENTS = {"bpd_": 16, "rce_": 11}
IGNORE = {"__pycache__", ".pytest_cache", ".git", ".DS_Store"}


def _files(root: pathlib.Path) -> dict[str, pathlib.Path]:
    return {p.relative_to(root).as_posix(): p for p in root.rglob("*")
            if p.is_file() and not (set(p.relative_to(root).parts) & IGNORE)
            and p.suffix not in (".pyc", ".pyo")}


def _same(a: pathlib.Path, b: pathlib.Path) -> bool:
    if a.is_file() and b.is_file():
        return a.read_bytes() == b.read_bytes()
    if a.is_dir() and b.is_dir():
        left = _files(a)
        right = _files(b)
        return left.keys() == right.keys() and all(left[k].read_bytes() == right[k].read_bytes() for k in left)
    return False


def _check_bundle() -> list[tuple[pathlib.Path, pathlib.Path]]:
    # Fail closed if any of the 35 versioned v4.4 engine files differs from
    # the v6.6 English-policy release manifest. Historical hashes are audited
    # separately; translated prompts cannot be byte-identical to v4.4.
    origin = ROOT / 'research-cognition-engine' / 'references' / 'original_v44_file_manifest.json'
    if not origin.is_file():
        raise ValueError('Missing original v4.4 source provenance manifest')
    manifest = json.loads(origin.read_text(encoding='utf-8'))
    expected = manifest.get('skill_files_sha256', {})
    if len(expected) != 35:
        raise ValueError('v4.4 adapted manifest file count mismatch')
    for rel, digest in expected.items():
        file = ROOT / 'batch-paper-deepread-desktop' / rel
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != digest:
            raise ValueError('v6.6 English-adapted v4.4 file missing or modified: ' + rel)
    sources = []
    for name in SKILLS:
        source = ROOT / name
        if not (source / "SKILL.md").is_file():
            raise ValueError("Missing Skill entry in full bundle: " + name)
        sources.append((source, pathlib.Path(".agents") / "skills" / name))
    agents = ROOT / ".codex" / "agents"
    all_names = []
    for prefix, count in EXPECTED_AGENTS.items():
        matching = sorted(agents.glob(prefix + "*.toml"))
        if len(matching) != count:
            raise ValueError(f"Missing native subagent configuration: {prefix} expected {count}, actual {len(matching)}")
        for path in matching:
            settings = tomllib.loads(path.read_text(encoding="utf-8"))
            if settings.get("name") != path.stem or not settings.get("model") or not settings.get("model_reasoning_effort"):
                raise ValueError("Invalid native agent configuration: " + path.name)
            all_names.append(path.stem)
            sources.append((path, pathlib.Path(".codex") / "agents" / path.name))
    if len(all_names) != len(set(all_names)):
        raise ValueError("Duplicate native agent names; installation blocked")
    return sources


def install(project: pathlib.Path, upgrade: bool = False) -> dict:
    ws = project.expanduser().resolve()
    ws.mkdir(parents=True, exist_ok=True)
    files = _check_bundle()
    collisions = []
    unchanged = []
    modifications = []
    for src, rel in files:
        target = ws / rel
        if target.exists():
            if _same(src, target):
                unchanged.append(rel.as_posix())
                continue
            collisions.append(rel.as_posix())
        modifications.append((src, rel))
    # Complete preflight BEFORE any filesystem edits: a mixture of old/new
    # versions must not result from a partial default installation.
    if collisions and not upgrade:
        return {"status": "BLOCKED_EXISTING_COMPONENTS_UNCHANGED",
                "project": str(ws), "conflicts": collisions,
                "unchanged": unchanged, "installed": [],
                "hint": "Use --upgrade after confirming backups; preserves goal.md and all research input/output data."}

    if collisions and upgrade:
        # A signed dispatch created under an earlier language policy must
        # finish before agent prompts are changed. Completed historical
        # evidence and user-authored results remain immutable.
        unfinished = []
        for pattern in ("output/native/tasks/*/manifest.json", "output/research_cognition/tasks/*/manifest.json"):
            for manifest_path in ws.glob(pattern):
                if not (manifest_path.parent / "commit.json").is_file():
                    unfinished.append(str(manifest_path.relative_to(ws)))
        if unfinished:
            return {"status":"BLOCKED_ACTIVE_SIGNED_TASKS", "project":str(ws),
                    "unfinished_dispatch_manifests":sorted(unfinished),
                    "hint":"Finish or explicitly close earlier-language native tasks before changing Skill prompts. No research data or report was changed."}

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    backup_root = ws / "output" / "unified_v6_install_backups" / stamp
    staged_root = ws / ".agents" / (".rce_v6_stage_" + stamp)
    installed = []
    backups = []
    made: list[pathlib.Path] = []
    replaced: list[tuple[pathlib.Path, pathlib.Path]] = []
    try:
        for src, rel in modifications:
            stage = staged_root / rel
            stage.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, stage, ignore=lambda d, names: [x for x in names if x in IGNORE or x.endswith((".pyc", ".pyo"))])
            else:
                shutil.copy2(src, stage)
            if not _same(src, stage):
                raise RuntimeError("Staged install integrity mismatch: " + rel.as_posix())
        for src, rel in modifications:
            target = ws / rel
            stage = staged_root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                backup = backup_root / rel
                backup.parent.mkdir(parents=True, exist_ok=True)
                # Same-volume rename preserves all original bytes & metadata.
                target.rename(backup)
                replaced.append((target, backup))
                backups.append(str(backup))
            else:
                made.append(target)
            stage.rename(target)
            installed.append(rel.as_posix())
    except Exception:
        # Restore old code if any installation copy/rename fails.
        for target in reversed(made):
            if target.is_dir(): shutil.rmtree(target, ignore_errors=True)
            elif target.exists(): target.unlink()
        for target, backup in reversed(replaced):
            if target.is_dir(): shutil.rmtree(target, ignore_errors=True)
            elif target.exists(): target.unlink()
            if backup.exists(): backup.rename(target)
        raise
    finally:
        if staged_root.exists(): shutil.rmtree(staged_root, ignore_errors=True)
    return {"status": "FULL_STACK_INSTALLED", "project": str(ws),
            "original_v44_source": True, "original_v44_logic_preserved_english_prompts": True, "v5_discovery": True, "v6_cognition": True,"v61_unified_scheduler": True,"v62_topic_to_plan": True,"v63_annual_official_venue_authority": True,"v64_pro5x_survival": True,"v65_round_reports_and_smart_cycle": True, "v66_english_internal_R3_paper_only": True,
            "native_desktop_agents": sum(EXPECTED_AGENTS.values()),
            "installed": installed, "unchanged": unchanged, "backups": backups,
            "preserved": ["goal.md", "input/", "output/", "native_config.json", "reading_config.json", "selection_config.json"],
            "next": "Restart the project in Codex Desktop and invoke $search2discovery. Start with topic-start; complete independent topic review before search."}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="search2discovery v1.0.0 Windows Codex Desktop installer")
    p.add_argument("--project", type=pathlib.Path, required=True)
    p.add_argument("--upgrade", action="store_true", help="Replace installed Skill code and agent profiles after backup; does not change research data")
    args = p.parse_args(argv)
    try:
        result = install(args.project, upgrade=args.upgrade)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "FULL_STACK_INSTALLED" else 2
    except (RuntimeError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
