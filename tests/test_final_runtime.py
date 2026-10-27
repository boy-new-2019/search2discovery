"""Offline runtime regressions; fixtures never enter scientific evidence."""
import copy,json,pathlib,sys,tempfile,unittest,shutil
W=pathlib.Path(__file__).resolve().parents[1]
for rel in ['research-cognition-engine/scripts','batch-paper-deepread-desktop/scripts','paper-discovery-preflight/scripts','scripts']:sys.path.insert(0,str(W/rel))
import agent_profiles
from test_multisource import FakeHTTP,Base,TASK,TITLE
from literature_sources.adapters import OpenReview
from literature_sources.common import DEFAULTS,read,write
from literature_sources.coordinator import Coordinator,configure
class Profiles(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.folder=pathlib.Path(self.tmp.name)/'agents';shutil.copytree(W/'.codex/agents',self.folder)
 def tearDown(self):self.tmp.cleanup()
 def test_all_27(self):self.assertEqual(agent_profiles.audit(self.folder)['status'],'VALID')
 def test_missing_rce_fails(self):
  (self.folder/'rce_method_sol.toml').unlink();self.assertEqual(agent_profiles.audit(self.folder)['status'],'BLOCKED')
 def test_bad_toml_fails(self):
  (self.folder/'rce_method_sol.toml').write_text('name = [','utf8');self.assertEqual(agent_profiles.audit(self.folder)['status'],'BLOCKED')
 def test_bad_model_fails(self):
  p=self.folder/'rce_method_sol.toml';p.write_text(p.read_text().replace('gpt-6.1-sol','unverified-model'),'utf8');self.assertEqual(agent_profiles.audit(self.folder)['status'],'BLOCKED')
 def test_route_declares_actual_mechanism(self):
  a=agent_profiles.dispatch_profile(self.folder,'rce_method_sol',[]);self.assertEqual(a['agent_type'],'default');self.assertIn('EXPLICIT_PROFILE',a['route']);self.assertFalse(a['provider_attestation'])
  b=agent_profiles.dispatch_profile(self.folder,'rce_method_sol',['rce_method_sol']);self.assertEqual(b['route'],'NATIVE_NAMED_TYPE')
class Retrieval(Base):
 def note(self,**kw):
  n={'id':'note123','readers':['everyone'],'cdate':1790000000000,'content':{'title':{'value':TITLE},'pdf':{'value':'/pdf/attachment.pdf'},'venueid':{'value':'ICLR.cc/2027/Conference/Submission'}}};n.update(kw);return n
 def adapter(self,n,task=None):
  h=FakeHTTP([('notes/search',json.dumps({'notes':[n],'count':1}))]);rows,cursor=OpenReview(h,DEFAULTS).search(task or TASK,None);return rows,h
 def test_canonical_public_pdf(self):
  rows,h=self.adapter(self.note());self.assertEqual(rows[0]['fulltexts'][0]['url'],'https://openreview.net/pdf?id=note123');self.assertEqual(rows[0]['original_pdf_attachment'],'/pdf/attachment.pdf');self.assertIn('api2.',h.urls[0])
 def test_v1_flat_content_and_venue(self):
  n=self.note(content={'title':TITLE,'pdf':'/pdf/old.pdf'});rows,h=self.adapter(n,{**TASK,'api_version':'1','invitation':'ICLR.cc/2023/Conference/-/Blind_Submission'});self.assertIn('api.openreview.net',h.urls[0]);self.assertIn('invitation=',h.urls[0]);self.assertEqual(rows[0]['api_version'],'1')
 def test_restricted_readers_no_download(self):
  rows,h=self.adapter(self.note(readers=['ICLR.cc/2027/Conference/Program_Chairs']));self.assertEqual(rows[0]['fulltexts'],[])
 def test_external_publisher_link_not_relabelled_oa(self):
  rows,h=self.adapter(self.note(content={'title':TITLE,'pdf':'https://publisher.invalid/paper.pdf'}));self.assertEqual(rows[0]['fulltexts'],[])
 def test_maintenance_preserves_pending_queue_and_no_requests(self):
  self.workspace();cfg=read(self.ws/'source_routing.json');cfg['acquisition_mode']='MAINTENANCE_ONLY';write(self.ws/'source_routing.json',cfg)
  co=Coordinator(self.ws,online=True);before=copy.deepcopy(co.state);out=co.run();self.assertEqual(out['status'],'BROAD_EXPANSION_STOPPED_TARGET_250_RETAINED');self.assertEqual(co.budget['sent'],0);self.assertEqual(before,co.state)
class RCECollect(unittest.TestCase):
 def setUp(self):
  import engine,rce,store
  self.engine=engine;self.store=store;self.tmp=tempfile.TemporaryDirectory();self.ws=pathlib.Path(self.tmp.name)
  (self.ws/'goal.md').write_text('Frozen shared-state correction research question fixture only.','utf8')
  engine.init(self.ws)
  with store.connect(self.ws) as c:c.execute("INSERT INTO works(work_id,title,category,record_sha) VALUES('fixture','Fixture paper','core','fixture-hash')")
  cfg=copy.deepcopy(rce.DEFAULT);engine.new_cycle(self.ws,cfg);self.job=engine.prepare(self.ws,cfg,lambda *args:None)['job_id'];self.role='rce_cartographer_sol'
  self.folder=engine.taskdir(self.ws,self.job);self.answer=self.folder/'answers'/(self.role+'.json')
 def tearDown(self):self.tmp.cleanup()
 def output(self,text='English fixture shared-state question needing evidence?'):
  return {'stage':'MAP','questions':[{'question':text,'domain':'memory','impact':.8,'uncertainty':.9,'evidence_needed':'Original fulltext and independent review are required.'}]}
 def collect(self):return self.engine.collect(self.ws,self.job,self.role,self.answer,'/independent/real-test-fixture')
 def test_direct_answer_english_chinese_mixed_preserved(self):
  for text in ['English shared-state question requiring verification?','共享状态校正中的有效历史保持与有效新证据纠错如何获得可靠监督来源？','Shared state 共享状态 correction: 有效历史 remains valid?']:
   with self.subTest(text=text):
    # Each content uses a distinct isolated task; no scientific fixture enters the real DB.
    other=RCECollect();other.setUp()
    try:
     raw=json.dumps(other.output(text),ensure_ascii=False,separators=(',',':')).encode('utf8');other.answer.parent.mkdir(exist_ok=True,parents=True);other.answer.write_bytes(raw)
     self.assertEqual(other.collect()['status'],'VERIFIED');self.assertEqual(other.answer.read_bytes(),raw)
    finally:other.tearDown()
 def test_duplicate_after_commit_byte_stable(self):
  self.store.write(self.answer,self.output());self.collect();commit=self.engine.commit(self.ws,self.job)
  receipt=self.folder/'receipts'/(self.role+'.json');before=receipt.read_bytes();saved=(self.folder/'commit.json').read_bytes()
  self.assertEqual(self.collect()['status'],'ALREADY_COLLECTED');self.assertEqual(self.engine.commit(self.ws,self.job),commit);self.assertEqual(receipt.read_bytes(),before);self.assertEqual((self.folder/'commit.json').read_bytes(),saved)
 def test_changed_identity_rejected(self):
  self.store.write(self.answer,self.output());self.collect()
  with self.assertRaises(ValueError):self.engine.collect(self.ws,self.job,self.role,self.answer,'/different/identity')
 def test_tampered_committed_answer_rejected(self):
  self.store.write(self.answer,self.output());self.collect();self.engine.commit(self.ws,self.job);self.store.write(self.answer,self.output('Changed shared-state question with different contents?'))
  with self.assertRaises(ValueError):self.engine.commit(self.ws,self.job)
if __name__=='__main__':unittest.main(verbosity=2)
