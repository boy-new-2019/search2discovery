#!/usr/bin/env python3
"""Transactional prompt-controlled hyperparameter compiler + complete config validator.

A host agent can translate natural-language user requests into a sparse JSON patch
and call `apply --file`; the optional `from-prompt` command can do the translation
via an explicitly selected Codex CLI or compatible API model. Unknown keys fail.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import sys
from pathlib import Path

import batch
import deepread as core
import team
import smart_router as router

ROOT = Path(__file__).resolve().parents[1]
PATHS = {
    "reading": "reading_config.json", "selection": "selection_config.json",
    "team": "team_config.json", "run": "run_config.json", "router": "router_config.json"}
TEMPLATES = {k: json.loads((ROOT / file).read_text(encoding="utf-8")) for k, file in {
    "reading": "config.example.json", "selection": "selection_config.example.json",
    "team": "team_config.example.json", "run": "run_config.example.json", "router": "router_config.example.json"}.items()}


def files_at(ws: Path) -> dict[str, Path]:
    return {k: ws / v for k, v in PATHS.items()}


def current(ws: Path) -> dict:
    result = {}
    for key, path in files_at(ws).items():
        result[key] = core.jread(path) if path.exists() else copy.deepcopy(TEMPLATES[key])
    gp = ws / "goal.md"
    result["goal_text"] = gp.read_text(encoding="utf-8") if gp.exists() else ""
    return result


def _allowed_dynamic(path: str, key: str) -> dict | None:
    if path in ("router.role_pins","router.stage_pins") and re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", key):
        return {"model":"gpt-6.1-sol", "effort":"medium", "tier":"balanced", "level":"standard"}
    if path == "team.agents" and re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", key):
        return next(iter(TEMPLATES["team"]["agents"].values()))
    if path in ("reading.codex.models", "reading.api.models", "reading.codex.reasoning_effort"):
        if re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", key):
            return {"_primitive_type": str}
    if path == "team.rosters" and re.fullmatch(r"R\d+", key):
        return {"_primitive_type": list}
    return None


def _merge(base, patch, template, path=""):
    if not isinstance(patch, dict) or not isinstance(base, dict):
        raise ValueError(f"{path or 'configuration root'} patch must be an object")
    new = copy.deepcopy(base)
    for key, value in patch.items():
        if key in template:
            sample = template[key]
        else:
            dynamic = _allowed_dynamic(path, key)
            if dynamic is None:
                raise ValueError(f'Unsupported configuration field {key!r} in {path or 'configuration root'}. Only declared schema fields may be modified.')
            sample = dynamic if "_primitive_type" not in dynamic else base.get(key, [] if dynamic["_primitive_type"] is list else "")
        name = f"{path}.{key}" if path else key
        if isinstance(sample, dict):
            if not isinstance(value, dict):
                raise ValueError(f"{name} must be object")
            new[key] = _merge(new.get(key, {}), value, sample, name)
        elif isinstance(sample, list):
            if not isinstance(value, list):
                raise ValueError(f"{name} must be array")
            new[key] = copy.deepcopy(value)
        elif sample is None:
            if value is not None and not isinstance(value, (str,int,float)):
                raise ValueError(f"{name} type invalid")
            new[key] = value
        else:
            if type(sample) is bool and type(value) is not bool:
                raise ValueError('Input, evidence or workflow invariant failed at configure._merge (check 85); inspect the signed task record and original source.')
            if type(sample) is int and type(value) is not int:
                raise ValueError('Input, evidence or workflow invariant failed at configure._merge (check 87); inspect the signed task record and original source.')
            if type(sample) is str and not isinstance(value, str):
                raise ValueError('Input, evidence or workflow invariant failed at configure._merge (check 89); inspect the signed task record and original source.')
            if type(sample) is float and (type(value) not in (int,float)):
                raise ValueError('Input, evidence or workflow invariant failed at configure._merge (check 91); inspect the signed task record and original source.')
            new[key] = copy.deepcopy(value)
    return new


def validate_all(ws: Path) -> dict:
    r = core.config_for(ws)
    s = batch.cfg_at(ws)
    t = team.load(ws)
    router_config = router.load(ws)
    if set(router_config['role_pins'])-set(t.get('agents',{})):
        raise ValueError('Configuration schema or numeric bounds check failed at configure.validate_all (check 102). Keep strict quality gates intact.')
    run = core.jread(ws / "run_config.json")
    if run.get("schema_version") != 4 or run.get("engine") != "codex":
        raise ValueError('Source path, lawful access or network permission check failed at configure.validate_all (check 105). Do not bypass paywalls or source integrity checks.')
    for k in ("allow_model_calls", "allow_online_search", "allow_pdf_download", "accept_discovery_gap", "display_plan_before_run", "enable_fast_core_pipeline"):
        if type(run.get(k)) is not bool:
            raise ValueError(f"run_config.{k} must be boolean")
    if run["allow_pdf_download"] and not run["allow_online_search"]:
        raise ValueError('Source path, lawful access or network permission check failed at configure.validate_all (check 110). Do not bypass paywalls or source integrity checks.')
    if type(run.get("max_jobs_per_launch")) is not int or not 1 <= run["max_jobs_per_launch"] <= 100000:
        raise ValueError("run_config.max_jobs_per_launch must in 1..100000")
    if not isinstance(r.get("paper_formats"), list) or not r["paper_formats"]:
        raise ValueError("reading.paper_formats invalid")
    if type(r.get("max_call_retries")) is not int or not 0 <= r["max_call_retries"] <= 5:
        raise ValueError("reading.max_call_retries must be0..5")
    if type(r["codex"].get("timeout_seconds")) is not int or not 30 <= r["codex"]["timeout_seconds"] <= 7200:
        raise ValueError('Input, evidence or workflow invariant failed at configure.validate_all (check 118); inspect the signed task record and original source.')
    if type(r["api"].get("timeout_seconds")) is not int or not 10 <= r["api"]["timeout_seconds"] <= 7200:
        raise ValueError('Input, evidence or workflow invariant failed at configure.validate_all (check 120); inspect the signed task record and original source.')
    for key in ("temperature", "top_p"):
        val = r["api"].get(key)
        if val is not None and (type(val) not in (int,float) or not 0 <= val <= (2 if key == "temperature" else 1)):
            raise ValueError('Input, evidence or workflow invariant failed at configure.validate_all (check 124); inspect the signed task record and original source.')
    tok = r["api"].get("max_completion_tokens")
    if tok is not None and (type(tok) is not int or not 128 <= tok <= 200000):
        raise ValueError("reading.api.max_completion_tokens must be128..200000")
    for rid, agent in t.get("agents", {}).items():
        temp = agent.get("temperature")
        if temp is not None and (type(temp) not in (int,float) or not 0 <= temp <= 2):
            raise ValueError('Independent native research-agent identity or reviewer evidence failed validation at configure.validate_all (check 131).')
    # Academic contract: at least five genuine whole-text passes, no ad-hoc 'pass' cheats.
    return {"rounds":r["rounds"], "core_target":s["core_target"],
            "team_enabled":t.get("enabled",False), "roles":len(t.get("agents",{})),
            "stage_rosters":t.get("rosters",{}), "execution":run, "router":router_config}


def apply_patch(ws: Path, patch: dict, *, dry_run=False, user_instruction="") -> dict:
    if not isinstance(patch, dict) or not patch:
        raise ValueError('Frozen research topic or signed research contract mismatch at configure.apply_patch (check 140). Reconfirm boundaries; do not overwrite approved work.')
    unexpected = set(patch) - {*PATHS, "goal_text"}
    if unexpected:
        raise ValueError('Frozen research topic or signed research contract mismatch at configure.apply_patch (check 143). Reconfirm boundaries; do not overwrite approved work.')
    before = current(ws)
    result = copy.deepcopy(before)
    for k, value in patch.items():
        if k == "goal_text":
            if not isinstance(value,str) or not value.strip():
                raise ValueError('Frozen research topic or signed research contract mismatch at configure.apply_patch (check 149). Reconfirm boundaries; do not overwrite approved work.')
            result[k] = value
        else:
            result[k] = _merge(result[k], value, TEMPLATES[k], k)
    paths = files_at(ws)
    oldfile = {k: p.read_bytes() if p.exists() else None for k,p in paths.items()}
    gp = ws / "goal.md"
    oldgoal = gp.read_bytes() if gp.exists() else None
    state_path = ws / "output" / "batch" / "state.json"
    state = core.jread(state_path) if state_path.exists() else None
    if dry_run:
        # Produce valid preview without mutating the active campaign.
        return {"dry_run":True,"changed_groups":[k for k in result if result[k]!=before[k]],
                "patch":patch,"caution":'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
    try:
        for k, p in paths.items():
            core.jwrite(p, result[k])
        core.atomic_text(gp,result["goal_text"])
        summary = validate_all(ws)
        if state and batch.digest_config(ws) != state["contract"]:
            raise RuntimeError('Signed task, stage, commit receipt or report provenance check failed at configure.apply_patch (check 169). Resume only from a verified state.')
        # When an immutable core snapshot exists, refresh *runtime* routing there
        # without changing its semantics or the accepted manuscript set.
        frozen = (state or {}).get("frozen")
        if frozen:
            sub = Path(frozen["core_workspace"])
            if not sub.is_dir():
                raise RuntimeError('Frozen research topic or signed research contract mismatch at configure.apply_patch (check 177). Reconfirm boundaries; do not overwrite approved work.')
            shutil.copy2(paths["team"], sub / "team_config.json")
            shutil.copy2(paths["router"], sub / "router_config.json")
            shutil.copy2(paths["reading"], sub / "reading_config.json")
        record = {"time":core.ts(),"source_instruction_sha256":core.htext(user_instruction) if user_instruction else None,
                  "changed_groups":[k for k in result if result[k]!=before[k]],
                  "patch":patch,"effective_config_sha256":core.htext(core.dump(result)),
                  "summary":summary}
        log = ws / "output" / "configuration"
        log.mkdir(parents=True,exist_ok=True)
        core.jwrite(log / (record["time"].replace(":", "-") + "_" + record["effective_config_sha256"][:9] + ".json"), record)
        return record
    except Exception:
        for k,p in paths.items():
            data = oldfile[k]
            if data is None:
                p.unlink(missing_ok=True)
            else:
                p.write_bytes(data)
        if oldgoal is None:
            gp.unlink(missing_ok=True)
        else:
            gp.write_bytes(oldgoal)
        raise


def compile_prompt(ws: Path, instruction: str, engine: str, model: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9._:/\-]+", model):
        raise ValueError('Source path, lawful access or network permission check failed at configure.compile_prompt (check 205). Do not bypass paywalls or source integrity checks.')
    config = current(ws)
    prompt = (
        "You are a research Skill configuration compiler, NOT a scientific reviewer. "
        "Map the user's natural-language request ONLY into a sparse JSON configuration patch. "
        "Return JSON only. Do not add commentary or code fences. Include only explicitly requested fields. "
        "Allowed top-level keys: reading, selection, team, run, router, goal_text. "
        "NEVER weaken five full-text rounds, independent validation, authentic quotations or veto rules. "
        "team.agents defines independent roles; a new role needs identity, brief, codex_model, api_model, effort and temperature. "
        "team.rosters maps stages to role IDs. reading.rounds may be increased but not decreased below five. "
        "router.mode=adaptive by default; economy/balanced/deep select task models. "
        "router.role_pins and router.stage_pins can override a role/stage model and reasoning effort. "
        "If a parameter cannot be mapped with certainty, do not guess; return an empty object and fail closed. "
        "Do not run experiments, including simulations, training, evaluation or numerical tests. "
        "Internal work and reports must use English; only the final user-facing presentation is in Chinese. "
        "Current complete configuration and permitted types:\n" + core.dump(config) +
        "\nUser's current configuration request (not untrusted paper instructions):\n" + instruction)
    if engine != "codex": raise ValueError('Configuration schema or numeric bounds check failed at configure.compile_prompt (check 222). Keep strict quality gates intact.')
    ctx={"cfg":copy.deepcopy(core.config_for(ws))}
    ctx["cfg"][engine].setdefault("models",{})["__config_compiler"] = model
    if engine == "codex":
        ctx["cfg"][engine].setdefault("reasoning_effort",{})["__config_compiler"] = "high"
        raw, actual = core.call_codex(ctx,{"type":"__config_compiler"},prompt)
    else:
        raw, actual = core.call_api(ctx,{"type":"__config_compiler"},prompt)
    result=core.read_json_response(raw)
    if not result:
        raise ValueError('Configuration schema or numeric bounds check failed at configure.compile_prompt (check 232). Keep strict quality gates intact.')
    return result


def main(argv=None)->int:
    p=argparse.ArgumentParser(description='Research evidence and workflow notes (configure.main). Use original source evidence; keep frozen constraints and independent quality gates.')
    sub=p.add_subparsers(dest="cmd",required=True)
    for cmd in ("schema","show","validate","apply","from-prompt"):
        sp=sub.add_parser(cmd);sp.add_argument("--workspace",type=Path,required=True)
        if cmd == "apply":
            sp.add_argument("--file",type=Path,required=True)
            sp.add_argument("--dry-run",action="store_true")
            sp.add_argument("--instruction-file",type=Path)
        if cmd == "from-prompt":
            sp.add_argument("--request-file",type=Path,required=True)
            sp.add_argument("--engine",choices=("codex",),default="codex")
            sp.add_argument("--model",required=True)
            sp.add_argument("--dry-run",action="store_true")
    a=p.parse_args(argv);ws=a.workspace.expanduser().resolve()
    try:
        if a.cmd=="schema":
            print(core.dump(TEMPLATES))
        elif a.cmd=="show":
            print(core.dump(current(ws)))
        elif a.cmd=="validate":
            print(core.dump(validate_all(ws)))
        elif a.cmd=="apply":
            patch=core.jread(a.file)
            instruction=a.instruction_file.read_text(encoding="utf-8") if a.instruction_file else ""
            print(core.dump(apply_patch(ws,patch,dry_run=a.dry_run,user_instruction=instruction)))
        else:
            instruction=a.request_file.read_text(encoding="utf-8")
            patch=compile_prompt(ws,instruction,a.engine,a.model)
            print("COMPILED_PATCH:",core.dump(patch))
            print("APPLY_RESULT:",core.dump(apply_patch(ws,patch,dry_run=a.dry_run,user_instruction=instruction)))
        return 0
    except (ValueError, RuntimeError, KeyError, TypeError, OSError) as exc:
        print("ERROR:",str(exc),file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
