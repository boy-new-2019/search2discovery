#!/usr/bin/env python3
"""Run ORIGINAL v4.4 Desktop-native bridge with V5's 93 domain vocabulary.

Only non-persistent, in-process dynamic extension of the original cross-domain
query/validation tables. The user's original v4.4.py files are not modified.
Never starts Codex CLI, model API, or unapproved network traffic by itself.
"""
from __future__ import annotations
import argparse
import copy
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
SKILLS = HERE.parents[1]
BPD = SKILLS / "batch-paper-deepread-desktop" / "scripts"
V5LIB = SKILLS / "paper-discovery-preflight" / "references" / "inspiration_query_library.json"
if str(BPD) not in sys.path:sys.path.insert(0, str(BPD))
import cross_domain

if not V5LIB.is_file():
    raise RuntimeError('Input, evidence or workflow invariant failed at native_v44_launcher.module (check 23); inspect the signed task record and original source.')
wide = json.loads(V5LIB.read_text(encoding="utf-8"))
if not isinstance(wide,dict) or len(wide)<93 or any(not isinstance(x,list) or not x for x in wide.values()):
    raise RuntimeError('Configuration schema or numeric bounds check failed at native_v44_launcher.module (check 26). Keep strict quality gates intact.')
ORIGINAL_PREFS=cross_domain.prefs
ORIGINAL_DOMAINS=copy.deepcopy(cross_domain.DEFAULT['domains'])
cross_domain.DOMAIN_QUERIES.update({key:value for key,value in wide.items() if key not in cross_domain.DOMAIN_QUERIES})
CATEGORIES=list(dict.fromkeys([*ORIGINAL_DOMAINS,*cross_domain.DOMAIN_QUERIES.keys()]))
cross_domain.DEFAULT['domains']=CATEGORIES


def widened_prefs(cfg:dict)->dict:
    # The unmodified v4.4 quality/budget bounds are validated by the original
    # code on a non-mutating copy of the first 20 unique domains. We separately
    # extend only the count and keys allowed from the verified v5 catalogue.
    if not isinstance(cfg,dict):raise ValueError('Configuration schema or numeric bounds check failed at native_v44_launcher.widened_prefs (check 38). Keep strict quality gates intact.')
    domains=cfg.get('domains')
    if not isinstance(domains,list) or not domains or len(domains)>150 or len(set(domains))!=len(domains):
        raise ValueError('Configuration schema or numeric bounds check failed at native_v44_launcher.widened_prefs (check 41). Keep strict quality gates intact.')
    if any(x not in cross_domain.DOMAIN_QUERIES for x in domains):
        raise ValueError('Configuration schema or numeric bounds check failed at native_v44_launcher.widened_prefs (check 43). Keep strict quality gates intact.')
    narrow={**cfg,'domains':domains[:20]}
    ORIGINAL_PREFS(narrow)
    return cfg

cross_domain.prefs=widened_prefs
import desktop_bridge as bridge
# bridge.DEFAULT is made from a deep copy at module import. Set the new default
# only for freshly initialized workspaces; previously tuned configs stay intact.
bridge.DEFAULT['cross_domain']['domains']=CATEGORIES


def migrate_wide(ws:pathlib.Path)->dict:
    config=ws/'native_config.json'
    if not config.is_file():raise ValueError('first run init')
    existing=bridge.jread(config)
    bridge.native_cfg(ws)  # widened_prefs is already patched in memory.
    current=existing['cross_domain']['domains']
    target=list(dict.fromkeys([*current,*CATEGORIES]))
    if target==current:
        return {'status':'ALREADY_WIDE','fields':len(current),'original_source_modified':False}
    unfinished=ws/'output'/'native'/'tasks'
    if unfinished.is_dir() and any(not (m.parent/'commit.json').is_file() for m in unfinished.glob('*/manifest.json')):
        raise ValueError('Frozen research topic or signed research contract mismatch at native_v44_launcher.migrate_wide (check 66). Reconfirm boundaries; do not overwrite approved work.')
    # Backup user-tuned native config, never delete/rewrite source ZIP or goal.
    backup=ws/'output'/'unified_v6_compat'/'native_config_before_wide.json'
    backup.parent.mkdir(parents=True,exist_ok=True)
    if backup.is_file():
        if bridge.jread(backup).get('cross_domain',{}).get('domains')!=current:
            raise ValueError('Configuration schema or numeric bounds check failed at native_v44_launcher.migrate_wide (check 72). Keep strict quality gates intact.')
    else:
        bridge.jwrite(backup,existing)
    existing['cross_domain']['domains']=target
    bridge.jwrite(config,existing)
    bridge.native_cfg(ws)
    return {'status':'WIDE_DOMAIN_VOCABULARY_ENABLED','fields':len(target),
            'original_source_modified':False,'native_config_backup':str(backup),
            'requires_original_desktop_launcher':True,
            'hint':'Inspect the signed checkpoint, verify the original full-text evidence and reviewer receipts, then continue only the stage justified by a substantive evidence gap and available quota.'}


def main(argv=None)->int:
    args = sys.argv[1:] if argv is None else argv
    if not args:raise SystemExit('usage: native_v44_launcher.py init|wide-domains|ingest|prepare|collect|commit|... --workspace WORKSPACE')
    if args[0]=='wide-domains':
        p=argparse.ArgumentParser()
        p.add_argument('--workspace',type=pathlib.Path,required=True)
        opts=p.parse_args(args[1:]);ws=opts.workspace.expanduser().resolve()
        try:
            print(json.dumps(migrate_wide(ws),ensure_ascii=False,indent=2))
            return 0
        except (ValueError,RuntimeError,OSError,KeyError) as exc:
            print(json.dumps({'status':'BLOCKED','reason':str(exc)},ensure_ascii=False),file=sys.stderr)
            return 2
    code=bridge.main(args)
    # After an original commit (or prepare with zero-model local compilations),
    # persist any newly finished S1/S2/R1..R5 report without another model.
    if code==0 and args[0] in ('commit','prepare','select','seal'):
        from round_intelligence import refresh
        try:
            ix=args.index('--workspace')
            ws=pathlib.Path(args[ix+1]).expanduser().resolve()
            refresh(ws)
        except (ValueError, RuntimeError, OSError, KeyError) as exc:
            print(json.dumps({'status':'ROUND_REPORT_BLOCKED','reason':str(exc)},ensure_ascii=False),file=sys.stderr)
            return 2
    return code

if __name__=='__main__':raise SystemExit(main())
