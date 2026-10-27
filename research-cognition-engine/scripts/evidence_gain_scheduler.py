"""Deterministic gap triage; no model dispatch, networking or quota mutation.

Scientific evidence gain means qualified support for the targeted gap, not
more downloads, total CORE admissions, citations, or an unrelated theme gain.
Unknown gain requires review. Two completed zero-gain batches pause automatic
search pending explicit strategy review, even when strategy names differ.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

SCHEMA = 1
ZERO_GAIN_LIMIT = 2


def _path(ws):
    return Path(ws) / 'output/research_cognition/evidence_gain_scheduler.json'


def _read(ws):
    p = _path(ws)
    if not p.exists():
        return {'schema_version': SCHEMA, 'batches': []}
    data = json.loads(p.read_text('utf-8'))
    if data.get('schema_version') != SCHEMA or not isinstance(data.get('batches'), list):
        raise ValueError('Invalid evidence-gain checkpoint; preserve and repair it')
    return data


def acquisition_gate(found):
    return {'status': found.get('status'),
            'pending': found.get('status') != 'CATALOG_250_PLUS_COMPLETE',
            'final_acceptance_required': True,
            'reader_phase_exception': 'Only original admitted-reader work may proceed; no acquisition PASS'}


def original_seal_shortfalls(batch, ws, state):
    cfg = batch.cfg_at(ws)
    quality = batch.supplementary_quality(state)
    return {'target': max(0, cfg['core_target'] - len(state['selection']['last_selected'])),
            'imported': max(0, cfg['min_supplemental_pdfs'] - quality['imported']),
            'qualified': max(0, cfg['min_supplemental_qualified'] - quality['qualified'])}


MUTABLE_SELECTION_REPORT = 'output/batch/selection_decisions.json'


def _selection_archive(ws, digest):
    if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('Invalid selection evidence hash')
    return Path(ws)/'output/research_cognition/evidence_gain_artifacts'/(digest+'.json')


def _archive_selection(ws, raw, digest):
    if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Selection archive hash mismatch')
    p=_selection_archive(ws,digest);p.parent.mkdir(parents=True,exist_ok=True)
    try:
        with p.open('xb') as f:f.write(raw)
    except FileExistsError:
        if p.read_bytes()!=raw:raise ValueError('Changed immutable selection archive')
    return p


def archive_registered_selection(ws, file):
    """Recover exact registered report bytes; never change a historical gain event."""
    root=Path(ws).resolve();file=Path(file).resolve()
    if not file.is_relative_to(root) or not file.is_file():raise ValueError('Selection snapshot must be inside workspace')
    raw=file.read_bytes();digest=hashlib.sha256(raw).hexdigest();matches=[]
    for event in _read(root)['batches']:
        if any(a['path']==MUTABLE_SELECTION_REPORT and a['sha256']==digest for a in event['artifacts']):
            matches.append([event['batch_id'],event['gap_id']])
    if not matches:raise ValueError('Snapshot does not match any already registered mutable selection evidence')
    p=_archive_selection(root,raw,digest)
    import store
    audit={'status':'REGISTERED_SELECTION_BYTES_ARCHIVED','sha256':digest,'source_snapshot':str(file.relative_to(root)),
           'archive':str(p.relative_to(root)),'matched_events':matches,'at':store.utc(),'historical_events_changed':False}
    store.write(p.with_suffix('.receipt.json'),audit)
    return audit


def _artifact_bytes(root, row, *, allow_archive=False):
    p=(root/row['path']).resolve()
    if not p.is_relative_to(root):raise ValueError('Missing or external evidence artifact')
    if p.is_file():
        raw=p.read_bytes()
        if hashlib.sha256(raw).hexdigest()==row['sha256']:return raw
    # Only this known mutable report can be superseded. Current scientific
    # commit receipts and all other evidence still fail closed on tampering.
    if allow_archive and row['path']==MUTABLE_SELECTION_REPORT:
        archived=_selection_archive(root,row['sha256'])
        if archived.is_file():
            raw=archived.read_bytes()
            if hashlib.sha256(raw).hexdigest()==row['sha256']:return raw
    raise ValueError('Changed gap evidence; no scheduling from stale receipts')


def _check_event(ws, event, *, allow_archive=False):
    for key in ('batch_id', 'gap_id', 'strategy', 'gain_basis'):
        if not isinstance(event.get(key), str) or not event[key].strip():
            raise ValueError('Missing gap-evidence identity: ' + key)
    gain = event.get('effective_gain')
    if gain is not None and (type(gain) is not int or gain < 0):
        raise ValueError('Gain must be a nonnegative integer or unknown')
    if event['gain_basis'] != 'COMMITTED_INDEPENDENT_SCREENING_TARGET_GAP':
        raise ValueError('Downloads or unrelated admissions cannot certify gap gain')
    artifacts = event.get('artifacts')
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError('Hash-bound committed evidence is required')
    root = Path(ws).resolve()
    verified={row['path']:_artifact_bytes(root,row,allow_archive=allow_archive) for row in artifacts}
    commits = [row for row in artifacts if Path(row['path']).name == 'commit.json']
    if not commits or any(json.loads(verified[row['path']]).get('status') != 'COMMITTED' for row in commits):
        raise ValueError('A real committed screening receipt is required')



def record_batch(ws, event):
    """Append idempotently. Contradictory re-submissions are rejected."""
    data = _read(ws)
    key = (event['batch_id'], event['gap_id'])
    for old in data['batches']:
        if (old['batch_id'], old['gap_id']) == key:
            if old != event:
                raise ValueError('Conflicting repeated batch evidence; preserve original')
            _check_event(ws,event,allow_archive=True)
            return status(ws)
    _check_event(ws,event)
    for row in event['artifacts']:
        if row['path']==MUTABLE_SELECTION_REPORT:
            _archive_selection(ws,(Path(ws)/row['path']).read_bytes(),row['sha256'])
    data['batches'].append(event)
    p = _path(ws)
    p.parent.mkdir(parents=True, exist_ok=True)
    temp = p.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    temp.replace(p)
    return status(ws)


def status(ws):
    data = _read(ws)
    gaps = {}
    for event in data['batches']:
        _check_event(ws, event, allow_archive=True)
        row = gaps.setdefault(event['gap_id'], {'consecutive_zero_gain': 0,
                             'batch_ids': [], 'strategies': [], 'requires_review': False})
        row['batch_ids'].append(event['batch_id'])
        row['strategies'].append(event['strategy'])
        gain = event['effective_gain']
        if gain is None:
            row['requires_review'] = True
            row['consecutive_zero_gain'] = 0
        elif gain == 0:
            row['consecutive_zero_gain'] += 1
        else:
            row['consecutive_zero_gain'] = 0
    for row in gaps.values():
        row['paused'] = row['requires_review'] or row['consecutive_zero_gain'] >= ZERO_GAIN_LIMIT
    return {'schema_version': SCHEMA, 'zero_gain_limit': ZERO_GAIN_LIMIT, 'gaps': gaps,
            'native_calls': 0, 'quota_changed': False,
            'resumption_rule': 'Review existing evidence and a changed evidence-yield strategy; never rename a gap or reset history to resume'}


def automatic_search_pause(ws):
    """Conservative fallback triage; never interrupts valid frozen-core reading."""
    data = status(ws)
    paused = {gap: row for gap, row in data['gaps'].items() if row['paused']}
    if not paused:
        return None
    return {'paused_gaps': paused,
            'scope': 'Pause automatic question-search fallback for target-gap triage; unrelated work may continue after explicit routing review'}


def ready_reader_checkpoint(batch, ws):
    """Pure local eligibility probe; do not call discovery for an empty reader.

    Existing discovery/status implementations can update local fingerprints.
    Keep their old ordering for non-reader work and inspect only real reader
    checkpoints early. Invalid reader contracts still fail closed.
    """
    if not (Path(ws) / 'output/batch/state.json').is_file():
        return False
    state = batch.load_state(ws)
    if state.get('frozen'):
        return True
    if not batch.available(state) or not state.get('selection'):
        return False
    if len(state['selection'].get('last_selected', [])) < batch.cfg_at(ws)['core_min']:
        return False
    can, _ = batch.can_seal(ws, state)
    return can and not any(original_seal_shortfalls(batch, ws, state).values())
