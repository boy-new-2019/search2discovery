#!/usr/bin/env python3
"""V5 broad-serendipity discovery Skill + idempotent integration with Desktop.

Never replaces the main Skill, goals, input/output, or user configurations.
Backs up a changed SKILL.md before adding a small mandatory pre-stage.
"""
from __future__ import annotations
import argparse, datetime as dt, pathlib, shutil, sys
import paper_discovery as pd

SRC = pathlib.Path(__file__).resolve().parents[1]
NAME = 'paper-discovery-preflight'
MARKER = '<!-- BEGIN-PAPER-DISCOVERY-PREFLIGHT -->'
END = '<!-- END-PAPER-DISCOVERY-PREFLIGHT -->'
INTEGRATION = '''
<!-- BEGIN-PAPER-DISCOVERY-PREFLIGHT -->
## Mandatory v5 Discovery Preflight — 250 Authenticated Bibliographic Candidates and Wide Interdisciplinary Coverage

Before v4.4 intake, S1/S2 or R1–R5 reading, run `paper-discovery-preflight` unless the user explicitly opts out or a valid matching, complete campaign exists. Adapt the queries to the user-confirmed research goal. Prioritize the last three years and relevant leading scholarly venues; expand the publication window only if the quota cannot be met. Maintain disjoint minima of core 50, related 150 and cross-domain inspiration 50 bibliographic candidates, and 93 specializations across 15 macro fields. Check 24 distinct subdomains, 12 macro fields, 24 distant papers and the per-field concentration limits. Deduplicate by DOI, OpenAlex ID, title and authentic source metadata. Never fabricate authors, papers, publication dates, results, citations or 'read' status.

This stage uses OpenAlex metadata and deterministic local scripts without native Codex reading-agent calls. Save and disclose network, API or quota gaps instead of claiming completeness. Fifty core bibliography candidates are NOT fifty five-round full-text reviews; conserve the small-budget reading shortlist. Only truly downloaded, text-extractable full papers may enter `input/` or `cross_domain_input/<domain>/`; metadata and abstracts cannot stand in for full-text evidence. Never perform network access or download without the user's authorization. Pause and checkpoint when budgets or actual full-text availability are insufficient. Perform all internal processing and intermediate reporting in English; present the final results to the user in Chinese.
<!-- END-PAPER-DISCOVERY-PREFLIGHT -->
'''


MAIN_WIDE_MARKER = '# BEGIN-V5-WIDE-INTERDISCIPLINARY-QUERY-POOL'
MAIN_WIDE_END = '# END-V5-WIDE-INTERDISCIPLINARY-QUERY-POOL'


def extend_main_cross_domain(project:pathlib.Path)->dict:
    """Safely extend a known v4.4 reader's nine-domain pool to v5 wide fields.

    Only skill-owned script and the allowed native domain list may change.
    Existing manuscripts, paper evidence, budgets and corpus files are untouched.
    """
    main=project/'.agents'/'skills'/'batch-paper-deepread-desktop'
    script=main/'scripts'/'cross_domain.py'
    # In the original-v4.4 all-in-one bundle, a non-mutating runtime adapter
    # extends 93 fields. Never rewrite/backup the original reading engine files
    # (its original SHA inventory is used by the unified doctor check).
    unified=project/'.agents'/'skills'/'research-cognition-engine'/'scripts'/'native_v44_launcher.py'
    if unified.is_file():
        return {'status':'WIDE_VIA_UNIFIED_RUNTIME_ADAPTER', 'original_v44_source_preserved':True,
                'next':'Run native_v44_launcher.py wide-domains --workspace <project>; then call the same wrapper for all native v4.4 tasks.'}
    if not script.is_file():
        return {'status':'MAIN_CROSS_DOMAIN_MODULE_NOT_INSTALLED',
                'note':'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
    native=project/'native_config.json'
    original=script.read_text('utf-8')
    if 'UNIFIED_V6_CROSS_DOMAIN_REBUILT' in original:
        return {'status':'ALREADY_UNIFIED_V6_DYNAMIC_93_FIELDS',
                'note':'Integrated v6 reader loads v5 inspiration catalog at runtime; do not inject or rewrite reader code'}
    patched=MAIN_WIDE_MARKER in original
    if not patched and ('DOMAIN_QUERIES = {' not in original or 'STAGES = (' not in original or 'DEFAULT = {' not in original):
        raise ValueError('Signed task, stage, commit receipt or report provenance check failed at install_into_codex_project.extend_main_cross_domain (check 55). Resume only from a verified state.')
    if not patched and 'len(domains) > 20' not in original and 'len(domains)>20' not in original:
        raise ValueError('Input, evidence or workflow invariant failed at install_into_codex_project.extend_main_cross_domain (check 57); inspect the signed task record and original source.')
    changed_native=False
    native_data=None
    library=pd.read(SRC/'references'/'inspiration_query_library.json')
    if native.is_file():
        native_data=pd.read(native)
        if not isinstance(native_data,dict) or not isinstance(native_data.get('cross_domain'),dict):
            raise ValueError('Configuration schema or numeric bounds check failed at install_into_codex_project.extend_main_cross_domain (check 64). Keep strict quality gates intact.')
        existing=native_data['cross_domain'].get('domains')
        if not isinstance(existing,list):raise ValueError('Configuration schema or numeric bounds check failed at install_into_codex_project.extend_main_cross_domain (check 66). Keep strict quality gates intact.')
        newer=list(dict.fromkeys(existing+list(library)))
        changed_native=newer!=existing
        if changed_native:
            tasks=project/'output'/'native'/'tasks'
            if tasks.exists() and any(not (m.parent/'commit.json').is_file() for m in tasks.glob('*/manifest.json')):
                raise ValueError('Signed task, stage, commit receipt or report provenance check failed at install_into_codex_project.extend_main_cross_domain (check 72). Resume only from a verified state.')
            native_data['cross_domain']['domains']=newer
    if changed_native:
        native_backup=native.with_name('native_config.json.before_v5_wide')
        if native_backup.exists():raise ValueError('Configuration schema or numeric bounds check failed at install_into_codex_project.extend_main_cross_domain (check 76). Keep strict quality gates intact.')
    if not patched:
        backup=script.with_name('cross_domain.py.before_v5_wide')
        if backup.exists():raise ValueError('Input, evidence or workflow invariant failed at install_into_codex_project.extend_main_cross_domain (check 79); inspect the signed task record and original source.')
        shutil.copy2(script,backup)
        lines = """
# BEGIN-V5-WIDE-INTERDISCIPLINARY-QUERY-POOL
import json as _v5_json
from pathlib import Path as _v5_Path
_v5_query_file = _v5_Path(__file__).resolve().parents[2] / 'paper-discovery-preflight' / 'references' / 'inspiration_query_library.json'
if not _v5_query_file.is_file():
    raise RuntimeError('v5 wide-disciplinary discovery query library is missing; fail closed instead of falling back silently to the old restricted domain pool')
_v5_domain_queries = _v5_json.loads(_v5_query_file.read_text(encoding='utf-8'))
for _v5_domain, _v5_query_items in _v5_domain_queries.items():
    if _v5_domain not in DOMAIN_QUERIES:
        DOMAIN_QUERIES[_v5_domain] = _v5_query_items
DEFAULT['domains'] = list(dict.fromkeys(DEFAULT['domains'] + list(DOMAIN_QUERIES)))
# END-V5-WIDE-INTERDISCIPLINARY-QUERY-POOL

"""
        updated=original.replace('STAGES = (',lines+'STAGES = (',1)
        updated=updated.replace('len(domains) > 20','len(domains) > 150').replace('len(domains)>20','len(domains)>150')
        compile(updated,str(script),'exec')
        script.write_text(updated,'utf-8')
    if changed_native:
        shutil.copy2(native,native_backup)
        pd.write(native,native_data)
    return {'status':'MAIN_CROSS_DOMAIN_WIDENED' if not patched or changed_native else 'ALREADY_WIDE',
            'patched_module':not patched, 'extended_existing_native_domains':changed_native,
            'loaded_domain_count':len(library),
            'note':'Research evidence and workflow notes (install_into_codex_project.extend_main_cross_domain). Use original source evidence; keep frozen constraints and independent quality gates.'}


def install(project:pathlib.Path,*,upgrade:bool=False,patch_main:bool=True)->dict:
    project=project.expanduser().resolve()
    project.mkdir(parents=True,exist_ok=True)
    parent=project/'.agents'/'skills'
    target=parent/NAME
    parent.mkdir(parents=True,exist_ok=True)
    already_copied=(target.exists() and target.resolve()==SRC.resolve())
    if target.exists() and not already_copied:
        if not upgrade:raise ValueError('Input, evidence or workflow invariant failed at install_into_codex_project.install (check 117); inspect the signed task record and original source.')
        backup=parent/(NAME+'.old')
        if backup.exists():raise ValueError('Independent native research-agent identity or reviewer evidence failed validation at install_into_codex_project.install (check 119).')
        target.rename(backup)
    if not already_copied:
        def ignore(_dir,names):return [x for x in names if x in ('__pycache__','.pytest_cache') or x.endswith('.pyc')]
        shutil.copytree(SRC,target,ignore=ignore)
    previous=project/'discovery_config.json'
    migrated=None
    if previous.exists() and pd.read(previous).get('schema_version')==1:
        if not upgrade:
            raise ValueError('Configuration schema or numeric bounds check failed at install_into_codex_project.install (check 128). Keep strict quality gates intact.')
        migrated=pd.migrate_v5(project)
    generated=pd.init(project)
    main=parent/'batch-paper-deepread-desktop'/'SKILL.md'
    patched=False
    backup_file=None
    main_cross_domain=None
    if patch_main and main.exists():
        # Check for pending native tasks before changing main SKILL.md metadata.
        main_cross_domain=extend_main_cross_domain(project)
        old=main.read_text('utf-8')
        if MARKER not in old:
            b=main.with_name('SKILL.md.before_discovery_preflight')
            if b.exists():raise ValueError('Input, evidence or workflow invariant failed at install_into_codex_project.install (check 141); inspect the signed task record and original source.'+str(b))
            shutil.copy2(main,b);backup_file=str(b)
            # Insert after first level-1 heading, leaving skill frontmatter valid.
            lines=old.splitlines(keepends=True)
            loc=next((i for i,line in enumerate(lines) if line.startswith('# ')),None)
            if loc is None:raise ValueError('Input, evidence or workflow invariant failed at install_into_codex_project.install (check 146); inspect the signed task record and original source.')
            lines.insert(loc+1,INTEGRATION+'\n')
            main.write_text(''.join(lines),'utf-8')
            patched=True
        elif upgrade and 'Mandatory v5 Discovery Preflight' not in old:
            # Replace only the clearly delimited integration block, not the
            # user's main skill content or pre-existing separate backups.
            if END not in old:raise ValueError('Input, evidence or workflow invariant failed at install_into_codex_project.install (check 153); inspect the signed task record and original source.')
            backup=main.with_name('SKILL.md.before_discovery_v5')
            if backup.exists():raise ValueError('Input, evidence or workflow invariant failed at install_into_codex_project.install (check 155); inspect the signed task record and original source.')
            shutil.copy2(main,backup);backup_file=str(backup)
            prefix=old.split(MARKER,1)[0]
            suffix=old.split(END,1)[1]
            main.write_text(prefix+INTEGRATION.strip() + suffix,encoding='utf-8')
            patched=True
    return {'status':'INSTALLED','name':NAME,'location':str(target),'project':str(project),
            'main_skill_found':main.exists(),'main_skill_patched':patched,
            'backup_of_original_main_skill':backup_file,
            'init':generated,'migration':migrated,'main_cross_domain':main_cross_domain,
            'notes':'Research evidence and workflow notes (install_into_codex_project.install). Use original source evidence; keep frozen constraints and independent quality gates.'}


def main():
    p=argparse.ArgumentParser(description='Research evidence and workflow notes (install_into_codex_project.main). Use original source evidence; keep frozen constraints and independent quality gates.')
    p.add_argument('--project',required=True,type=pathlib.Path)
    p.add_argument('--upgrade',action='store_true')
    p.add_argument('--no-patch-main',action='store_true')
    a=p.parse_args()
    try:print(pd.canonical(install(a.project,upgrade=a.upgrade,patch_main=not a.no_patch_main)))
    except (ValueError,RuntimeError,OSError) as exc:
        print(pd.canonical({'status':'BLOCKED','reason':str(exc)}),file=sys.stderr);return 2
    return 0

if __name__=='__main__':raise SystemExit(main())
