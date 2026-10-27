"""Selection reports may advance while historical scientific receipts stay fixed."""
import hashlib,json,pathlib,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'research-cognition-engine/scripts'))
import evidence_gain_scheduler as eg
class SelectionSnapshots(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.ws=pathlib.Path(self.tmp.name)
  self.report=self.ws/eg.MUTABLE_SELECTION_REPORT;self.report.parent.mkdir(parents=True);self.report.write_text('{"selected":8}')
  self.commit=self.ws/'commit.json';self.commit.write_text('{"status":"COMMITTED"}')
  self.event={'batch_id':'initial','gap_id':'history','strategy':'reviewed','effective_gain':0,'gain_basis':'COMMITTED_INDEPENDENT_SCREENING_TARGET_GAP','artifacts':[{'path':p.relative_to(self.ws).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [self.commit,self.report]]}
 def test_new_event_automatically_snapshots_only_mutable_report(self):
  eg.record_batch(self.ws,self.event);before=eg._path(self.ws).read_bytes();self.report.write_text('{"selected":10}')
  self.assertEqual(eg.status(self.ws)['gaps']['history']['consecutive_zero_gain'],1)
  eg.record_batch(self.ws,self.event);self.assertEqual(eg._path(self.ws).read_bytes(),before)
  self.commit.write_text('{"status":"PENDING"}')
  with self.assertRaisesRegex(ValueError,'Changed gap evidence'):eg.status(self.ws)
 def test_exact_historical_bytes_restore_legacy_report_without_rewriting_gain(self):
  ledger=eg._path(self.ws);ledger.parent.mkdir(parents=True);ledger.write_text(json.dumps({'schema_version':1,'batches':[self.event]}));before=ledger.read_bytes()
  old=self.ws/'old_selection.json';old.write_bytes(self.report.read_bytes());self.report.write_text('{"selected":10}')
  with self.assertRaises(ValueError):eg.status(self.ws)
  result=eg.archive_registered_selection(self.ws,old)
  self.assertFalse(result['historical_events_changed']);self.assertEqual(ledger.read_bytes(),before)
  self.assertEqual(eg.status(self.ws)['gaps']['history']['batch_ids'],['initial'])
 def test_unregistered_or_tampered_snapshot_cannot_repair_history(self):
  eg.record_batch(self.ws,self.event);wrong=self.ws/'wrong.json';wrong.write_text('unregistered bytes')
  with self.assertRaisesRegex(ValueError,'does not match'):eg.archive_registered_selection(self.ws,wrong)
  digest=self.event['artifacts'][1]['sha256'];eg._selection_archive(self.ws,digest).write_text('tampered');self.report.write_text('advanced')
  with self.assertRaises(ValueError):eg.status(self.ws)
class StaleSelection(unittest.TestCase):
 def test_newly_screened_cohort_reselects_instead_of_reusing_old_shortfall(self):
  sys.path.insert(0,str(ROOT/'research-cognition-engine/tests'));import test_evidence_scheduler as fixture
  f=fixture.SchedulerTests();f.setUp();self.addCleanup(f.doCleanups)
  f.state['selection']['decisions']=[{'paper_id':'old-paper'}]
  self.assertEqual(fixture.suite.next_action(f.w)['status'],'READY_FOR_ORIGINAL_V44_SELECT')
if __name__=='__main__':unittest.main()
