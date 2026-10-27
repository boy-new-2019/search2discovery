"""Regression coverage for concrete route gates, null conclusions and global bootstrap."""
import copy,importlib.util,json,pathlib,shutil,subprocess,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'research-cognition-engine/scripts'))
sys.path.insert(0,str(ROOT/'research-cognition-engine/tests'))
import route_convergence as route,engine,store,rce
import test_e2e as fixture
class RouteGates(unittest.TestCase):
 def setUp(self):
  self.f=fixture.CognitionE2E();self.f.setUp();self.addCleanup(self.f.tearDown)
  self.ws=self.f.ws;engine.new_cycle(self.ws,self.f.config)
  for _ in range(5):self.f.submit(self.f.task(),self.f.response)
  h=store.listrows(self.ws,'hypotheses')[0]['hypothesis_id'];self.h=h
  claims=store.listrows(self.ws,'claims');anchor=next(x['claim_id'] for x in claims if x['work_id']=='W-occupancy')
  self.payload={'status':'RECOMMENDED_FOR_VALIDATION','selected_hypothesis_id':h,
    'rationale':'This candidate targets a specific failure mechanism with source-backed discriminating comparisons.',
    'novelty_risk':'Semantic equivalence remains uncertain; the researcher must verify the nearest mechanisms and experimental feasibility.',
    'candidate_comparison':[{'hypothesis_id':h,'verdict':'PROVISIONAL','reason':'Requires a distinct operator and matched protocol test against the nearest source mechanism.'}],
    'method_card':{k:'Concrete '+k+' specification with independently traceable evidence and clearly proposed design.' for k in route.METHOD_FIELDS}}
  self.payload['method_card']['nearest_work_comparison']=[{'work_id':'W-occupancy','shared_mechanism':'Both methods update state under partial observation and must use the same information boundary.',
    'technical_delta':'Proposed update rule differs in its explicit counterevidence operator; this remains a falsifiable hypothesis.', 'evidence_claim_ids':[anchor]}]
 def test_complete_card_is_provisional_not_proof(self):
  self.assertEqual(route.validate(self.ws,self.payload)['selected'],self.h);self.assertFalse(route.validate(self.ws,self.payload)['novelty_proven'])
 def test_vague_card_rejected(self):
  self.payload['method_card']['objective']='improve';self.assertRaises(ValueError,route.validate,self.ws,self.payload)
 def test_known_candidate_cannot_be_final(self):
  with store.connect(self.ws) as c:c.execute("UPDATE assessments SET verdict='KNOWN' WHERE role='rce_skeptic_astra'")
  self.assertRaisesRegex(ValueError,'rejection',route.validate,self.ws,self.payload)
 def test_missing_independent_review_rejected(self):
  with store.connect(self.ws) as c:c.execute("DELETE FROM assessments WHERE role='rce_skeptic_astra'")
  self.assertRaisesRegex(ValueError,'Two distinct',route.validate,self.ws,self.payload)
 def test_claims_from_another_work_are_not_nearest_work_evidence(self):
  self.payload['method_card']['nearest_work_comparison'][0]['evidence_claim_ids']=[x['claim_id'] for x in store.listrows(self.ws,'claims') if x['work_id']=='W-belief']
  self.assertRaisesRegex(ValueError,'different paper',route.validate,self.ws,self.payload)
 def test_signed_final_renders_and_rejects_prompt_tampering(self):
  self.f.submit(self.f.task(),self.f.response) # EXPERIMENT
  task=self.f.task()
  def answer(stage,role):
   result=self.f.response(stage,role);result['route_selection']=self.payload;return result
  self.f.submit(task,answer);self.assertEqual(route.render(self.ws)['selected'],self.h)
  self.assertTrue((store.root(self.ws)/'research_discovery_package/final_route_and_method.md').is_file())
  prompt=engine.taskdir(self.ws,task['job_id'])/'prompts/rce_general_manager_astra.md'
  prompt.write_text('changed source prompt',encoding='utf8');self.assertRaisesRegex(ValueError,'prompt',route.committed,self.ws)
class NullConclusion(unittest.TestCase):
 def test_new_campaign_no_supported_hypothesis_reaches_independent_final(self):
  f=fixture.CognitionE2E();f.setUp();self.addCleanup(f.tearDown);engine.new_cycle(f.ws,f.config)
  state=engine.get_state(f.ws);state['cycles'][-1]['route_contract_version']=2;store.write(engine.statefile(f.ws),state)
  for _ in range(3):f.submit(f.task(),f.response)
  result=f.submit(f.task(),lambda stage,role:{'stage':'HYPOTHESIS','hypotheses':[],
   'no_supported_hypothesis_reason':'Source evidence does not support a mechanism distinct from the closest prior methods.'})
  self.assertEqual(result['next_stage'],'FINAL')
  payload={'status':'NO_VIABLE_CANDIDATE','selected_hypothesis_id':None,'candidate_comparison':[],
   'rationale':'The full source comparison supports no distinct candidate; identify discriminating evidence before a new campaign.',
   'novelty_risk':'No positive novelty claim is made and no method or empirical improvement is manufactured.'}
  f.submit(f.task(),lambda stage,role:{'stage':'FINAL','recommendations':[],
   'no_recommendation_reason':'Independent final review found no grounded new mechanism in the existing source evidence.', 'route_selection':payload})
  self.assertEqual(route.render(f.ws)['status'],'NO_VIABLE_CANDIDATE')
class BootstrapAndIntegrity(unittest.TestCase):
 def test_bootstrap_from_personal_skill_without_repository(self):
  with tempfile.TemporaryDirectory() as folder:
   root=pathlib.Path(folder);personal=root/'personal';ws=root/'research'
   names=['search2discovery','research-cognition-engine','paper-discovery-preflight','batch-paper-deepread-desktop']
   for name in names:shutil.copytree(ROOT/name,personal/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
   p=personal/'search2discovery/scripts/bootstrap.py'
   out=subprocess.run([sys.executable,str(p),'--project',str(ws)],capture_output=True,text=True,encoding='utf8')
   self.assertEqual(out.returncode,0,out.stderr);self.assertEqual(len(list((ws/'.codex/agents').glob('*.toml'))),27)
   (ws/'goal.md').write_text('Preserve user research constraints and all approved results.',encoding='utf8')
   before=(ws/'goal.md').read_bytes()
   out=subprocess.run([sys.executable,str(p),'--project',str(ws),'--upgrade'],capture_output=True,text=True,encoding='utf8')
   self.assertEqual(out.returncode,0,out.stderr);self.assertEqual((ws/'goal.md').read_bytes(),before)
 def test_release_overlay_fails_closed_on_unlisted_edit(self):
  import release_integrity
  with tempfile.TemporaryDirectory() as folder:
   root=pathlib.Path(folder)
   for name in ['batch-paper-deepread-desktop','research-cognition-engine']:
    shutil.copytree(ROOT/name,root/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
   self.assertEqual(release_integrity.verify(root)['modified'],[])
   with (root/'batch-paper-deepread-desktop/scripts/configure.py').open('a',encoding='utf8') as f:f.write('\n# unauthorized edit\n')
   self.assertIn('scripts/configure.py',release_integrity.verify(root)['modified'])
 def test_cognition_default_can_admit_required_stages(self):
  self.assertGreaterEqual(rce.DEFAULT['budget']['max_native_assignments_per_cycle'],sum(map(len,engine.DEFAULT_ROLES.values())))
if __name__=='__main__':unittest.main()
