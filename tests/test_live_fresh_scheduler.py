"""Fresh authenticated fulltexts must reach the inner scheduler before breadth is complete."""
import pathlib,sys,unittest
from unittest import mock
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'research-cognition-engine/scripts'))
import suite,workflow_v61 as wf,multisource_bridge as bridge
class FreshReaderScheduling(unittest.TestCase):
 def ready(self):
  import test_multisource as fixtures
  f=fixtures.FreshMultisourceBridge();f.setUp();self.addCleanup(f.tearDown)
  _,_,_,_=f.prepare_download();bridge.sync(f.ws);return f.ws
 def test_inner_scheduler_returns_ingest_for_verified_source_despite_pending_discovery(self):
  ws=self.ready();found={'status':'NEEDS_DISCOVERY','counts':{'core':1,'related':0,'inspiration':0},'shortfalls':{'core':49,'related':150,'inspiration':50},'coverage':{'status':'MULTISOURCE_COVERAGE_PENDING'}}
  with mock.patch.object(suite.discovery,'status',return_value=found):
   self.assertEqual(suite.next_action(ws)['status'],'NEEDS_ORIGINAL_V44_INGEST')
 def test_signed_pending_job_prevents_mutating_its_input_cohort(self):
  ws=self.ready();pending=ws/'output/native/tasks/S1_fixture/manifest.json'
  pending.parent.mkdir(parents=True);pending.write_text('{}',encoding='utf8')
  self.assertEqual(bridge.pending_reader_inputs(ws),[])
 def test_bibliographic_reranking_keeps_existing_uningested_file_discoverable(self):
  ws=self.ready();cat=bridge.catalog(ws)
  for family in cat.active().values():family['screened_candidate_category']='related'
  cat.save();inputs=bridge.pending_reader_inputs(ws)
  self.assertEqual(len(inputs),1);self.assertTrue(inputs[0].startswith('multisource_core/'))
  digest=(ws/'input'/inputs[0]).stem
  self.assertEqual(bridge.pending_reader_inputs(ws,{'papers':[{'sha256':digest,'file':inputs[0]}]}),[])
 def test_materialized_input_tamper_is_not_an_ingest_opportunity(self):
  ws=self.ready();next((ws/'input').rglob('*.pdf')).write_bytes(b'changed')
  with self.assertRaisesRegex(ValueError,'integrity'):bridge.pending_reader_inputs(ws)
class NativeCaptainCLI(unittest.TestCase):
 def test_captain_identity_and_answer_forward_to_original_validator(self):
  with __import__('tempfile').TemporaryDirectory() as d:
   ws=pathlib.Path(d);answer=ws/'captain.json';answer.write_text('{}')
   with mock.patch.object(wf,'_capture_native',return_value={'status':'COMMITTED'}) as capture,mock.patch.object(wf,'auto_sync',return_value={}):
    code=wf.main(['reader-commit','--workspace',str(ws),'--job-id','S2_fixture','--lead-file',str(answer),'--captain-thread-ref','actual-independent-captain'])
   self.assertEqual(code,0);call=capture.call_args.args[0]
   self.assertEqual(call[-4:],['--lead-file',str(answer),'--captain-thread-ref','actual-independent-captain'])
 def test_captain_answer_without_thread_is_blocked_before_original_dispatch(self):
  with __import__('tempfile').TemporaryDirectory() as d:
   with mock.patch.object(wf,'_capture_native') as capture:
    code=wf.main(['reader-commit','--workspace',d,'--job-id','S2_fixture','--lead-file',d+'/captain.json'])
   self.assertEqual(code,2);capture.assert_not_called()
if __name__=='__main__':unittest.main()
