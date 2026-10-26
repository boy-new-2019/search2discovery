"""Release-specific checks for previously lost English source-report semantics."""
from __future__ import annotations
import inspect
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'batch-paper-deepread-desktop/scripts'))
sys.path.insert(0,str(ROOT/'research-cognition-engine/scripts'))
import batch
import venue_authority

class ReleaseIntegrityTests(unittest.TestCase):
    def test_mainline_example_is_readable_english(self):
        for rel in ('paper-discovery-preflight/discovery_config.example.json',
                    'paper-discovery-preflight/references/legacy_v45_config.example.json'):
            data=json.loads((ROOT/rel).read_text('utf8'))
            self.assertTrue(data['main_direction'].isascii())
            self.assertIn('Gaussian memory',data['main_direction'])
            self.assertIn('autonomous-driving',data['main_direction'])
            self.assertNotIn('review detail',data['main_direction'])

    def test_ccf_release_metadata_is_not_generic_text(self):
        edition=venue_authority.SOURCE_FACTS_2026['CCF']['known_edition']
        self.assertIn('7th edition',edition)
        self.assertIn('CCF',edition)
        self.assertNotIn('Research evidence and workflow notes',edition)

    def test_original_screen_report_preserves_all_key_audit_fields(self):
        body=inspect.getsource(batch.report)
        for key in ('candidate_files','screen_batches','S1_done','S2_done',
                    'supplemental_imported','coverage_gaps','discovery_attempts',
                    'BLOCKED','selected','reason'):
            self.assertIn(key,body)
        self.assertNotIn('Research evidence and workflow notes',body)
        self.assertNotIn('Source state and independent reviewer provenance',body)

if __name__=='__main__': unittest.main()
