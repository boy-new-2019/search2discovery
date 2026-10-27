"""Authoring guidance must expose the same constraints enforced at topic commit."""
import json,pathlib,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'research-cognition-engine/scripts'))
import topic_to_plan as topic
class TopicAuthoring(unittest.TestCase):
 def test_new_template_exposes_acquisition_theme_bounds(self):
  with tempfile.TemporaryDirectory() as folder:
   ws=pathlib.Path(folder);skill=ws/'.agents/skills/research-cognition-engine/SKILL.md'
   skill.parent.mkdir(parents=True);skill.write_text('installed',encoding='utf8')
   result=topic.start(ws,'Shared-state correction for recurrent world-action models')
   template=json.loads(pathlib.Path(result['review_template']).read_text('utf8'))
   self.assertIn('3-90',template['authoring_constraints']['coverage_themes'])
   self.assertIn('actual',template['authoring_constraints']['identity'])
class CoverageClarification(unittest.TestCase):
 def fixture(self):
  sys.path.insert(0,str(ROOT/'research-cognition-engine/tests'))
  import test_v62_topic_pipeline as fixtures
  f=fixtures.TopicPipelineV62Tests();f.setUp();self.addCleanup(f.doCleanups);return f
 def review(self,f):
  import store
  cfg=store.read(f.ws/'selection_config.json')
  review={'reviewer_role':'rce_cartographer_sol','reviewer_thread_ref':'actual-independent-native-test-fixture',
   'rationale':'Clarify bibliographic acquisition counts versus mutually exclusive admitted reader cohort coverage before indexing.',
   'coverage_themes':[{**x,'min_core':1} for x in cfg['coverage_themes']]}
  path=f.ws/'clarification.json';store.write(path,review);return path
 def test_impossible_minima_rejected_before_commit(self):
  import store
  f=self.fixture();f.begin();path=f.brief();b=store.read(path)
  for x in b['coverage_themes']:x['min_core']=5
  with self.assertRaisesRegex(ValueError,'admitted reading cohort'):topic._check_brief(f.ws,b,topic.contract(f.ws))
 def test_pre_ingest_repair_retains_original_brief(self):
  f=self.fixture();f.commit();brief=topic.here(f.ws)/'topic_brief_reviewed.json';before=brief.read_bytes()
  result=topic.repair_initial_coverage(f.ws,self.review(f))
  self.assertEqual(result['minima_sum'],3);self.assertEqual(brief.read_bytes(),before)
  self.assertTrue(pathlib.Path(result['audit']).is_file())
 def test_repair_forbidden_after_reader_index(self):
  f=self.fixture();f.commit();path=self.review(f);state=f.ws/'output/batch/state.json'
  state.parent.mkdir(parents=True,exist_ok=True);state.write_text('{}',encoding='utf8')
  with self.assertRaisesRegex(ValueError,'forbidden after reader ingestion'):topic.repair_initial_coverage(f.ws,path)
if __name__=='__main__':unittest.main()
