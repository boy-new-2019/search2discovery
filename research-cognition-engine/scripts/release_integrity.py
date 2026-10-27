"""Verify legacy source with a separately versioned, explicit utility patch overlay."""
from __future__ import annotations
import hashlib,json,pathlib
PATCHED_FILES={'scripts/deepread.py','tests/test_deepread.py','SKILL.md','scripts/configure.py','scripts/desktop_bridge.py','scripts/quota_guard.py'}
def verify(root):
    root=pathlib.Path(root)
    p=root/'research-cognition-engine/references/original_v44_file_manifest.json'
    spec=json.loads(p.read_text('utf-8'));expected=dict(spec['skill_files_sha256'])
    if len(expected)!=35:raise ValueError('Historical file count mismatch')
    overlay=p.with_name('runtime_patch_manifest.json')
    approved={}
    if overlay.exists():
        patch=json.loads(overlay.read_text('utf-8'));approved=patch.get('files',{})
        if (patch.get('schema_version')!=1 or patch.get('base_manifest_sha256')!=hashlib.sha256(p.read_bytes()).hexdigest()
            or not approved or set(approved)-PATCHED_FILES):raise ValueError('Invalid release patch provenance')
        for rel,row in approved.items():
            if row.get('before_sha256')!=expected.get(rel) or not row.get('reason'):raise ValueError('Invalid patch base '+rel)
            expected[rel]=row['after_sha256']
    missing=[];modified=[]
    for rel,digest in expected.items():
        file=root/'batch-paper-deepread-desktop'/rel
        if not file.is_file():missing.append(rel)
        elif hashlib.sha256(file.read_bytes()).hexdigest()!=digest:modified.append(rel)
    return {'missing':missing,'modified':modified,'authorized_utility_patches':sorted(approved),
            'runtime_patch_status':'VERIFIED_RELEASE_PATCH' if approved and not missing and not modified else 'NONE_OR_INVALID',
            'source_archive_sha256':spec['original_archive_sha256'],'source_file_count':len(expected)}
