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


def _check_event(ws, event):
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
    for row in artifacts:
        p = (root / row['path']).resolve()
        if not p.is_relative_to(root) or not p.is_file():
            raise ValueError('Missing or external evidence artifact')
        if hashlib.sha256(p.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('Changed gap evidence; no scheduling from stale receipts')
    commits = [row for row in artifacts if Path(row['path']).name == 'commit.json']
    if not commits or any(json.loads((root / row['path']).read_text('utf-8')).get('status') != 'COMMITTED' for row in commits):
        raise ValueError('A real committed screening receipt is required')


def record_batch(ws, event):
    """Append idempotently. Contradictory re-submissions are rejected."""
    _check_event(ws, event)
    data = _read(ws)
    key = (event['batch_id'], event['gap_id'])
    for old in data['batches']:
        if (old['batch_id'], old['gap_id']) == key:
            if old != event:
                raise ValueError('Conflicting repeated batch evidence; preserve original')
            return status(ws)
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
        _check_event(ws, event)
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
