from __future__ import annotations
import json,pathlib,sys,tempfile,unittest,hashlib,shutil
SKILL=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SKILL/'scripts'))
import store,rce,engine,feedback,harness

class Extensions(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.ws=pathlib.Path(self.temp.name)
        (self.ws/'goal.md').write_text('研究方向：流式三维占用预测与证据记忆修订的长期科学问题；任何既有核心网络与实验不允许被软件更改。','utf8')
        rce.init(self.ws)
        self.workid='https://openalex.org/W1234'
        store.write(self.ws/'output/discovery_preflight/paper_library.json',{'selected':{
                'core':[{'id':self.workid,'title':'Research test work','year':2025,'doi':'10.1234/fake','venue':'Test Venue'}],
                'related':[],'inspiration':[]}})
        store.import_catalogue(self.ws)
    def tearDown(self):self.temp.cleanup()
    def test_work_coverage_not_promoted_to_fulltext(self):
        with store.connect(self.ws) as c:
            self.assertEqual(c.execute("SELECT source_status FROM works").fetchone()[0],'BIB_ONLY')
        self.assertEqual(store.listrows(self.ws,'claims'),[])
        engine.new_cycle(self.ws,rce.config(self.ws))
        with self.assertRaisesRegex(ValueError,'NO_FULLTEXT'):
            engine._context(self.ws,'MECHANISM',rce.config(self.ws))
    def test_downloaded_pdf_sha_and_bibliographic_identity(self):
        import fitz
        f=self.ws/'input/discovery_core/discovery_W1234.pdf';f.parent.mkdir(parents=True)
        pdf=fitz.open();p=pdf.new_page()
        for idx in range(10):p.insert_text((45,50+idx*30),'Experimental streaming occupancy memory validation with baseline and assumptions',fontsize=10)
        pdf.save(f);pdf.close()
        digest=store.hashbytes(f.read_bytes())
        store.write(self.ws/'output/discovery_preflight/state.json',{'download_log':{
              self.workid:{'status':'FULLTEXT_READY','relative_path':'input/discovery_core/discovery_W1234.pdf','sha256':digest}}})
        result=store.import_v5_downloads(self.ws)
        self.assertEqual(result['status'],'IMPORTED');self.assertEqual(result['imported'],1)
        self.assertEqual(len(store.listrows(self.ws,'sources')),1)
        s=store.listrows(self.ws,'sources')[0]
        pages=store.source_pages(f)
        self.assertEqual(store.checked_quote(self.ws,s['source_id'],1,'Experimental streaming occupancy memory validation with baseline and assumptions')['work_id'],self.workid)
        f.write_bytes(b'corrupted-after-import')
        with self.assertRaisesRegex(ValueError,'changed/missing'):
            store.checked_quote(self.ws,s['source_id'],1,'Experimental streaming occupancy memory validation with baseline and assumptions')
        result2=store.import_v5_downloads(self.ws)
        self.assertEqual(result2['status'],'PARTIAL')
    def test_experiment_feedback_needs_log_and_two_separate_contributions(self):
        with store.connect(self.ws) as c:
            c.execute('INSERT INTO questions VALUES(?,?,?,?,?,?,?)',('Q1','A research question sufficiently explained',.8,.6,'macro','OPEN',store.utc()))
            c.execute('INSERT INTO hypotheses VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',('H1','Q1','A falsifiable hypothesis sufficiently long',
                        'A mechanism sufficiently described and measurable','Predict a measurable performance improvement',
                        'Reject if the baseline is better under equal resources','Assume data and protocol identical',
                        '[]','[]','A cost-bounded test','NOVELTY_UNVERIFIED','PROPOSED_UNTESTED',store.utc()))
            c.execute('INSERT INTO experiments VALUES(?,?,?,?,?,?,?,?,?)',('XP1','H1','A fair full test with baseline','["A"]','["IoU"]',
                        'Reject when the baseline is at least as good','6 GPUs','PLANNED_NOT_EXECUTED',store.utc()))
        log=self.ws/'experiment_logs'/'run3407.json';store.write(log,{'metrics':{'IoU':[27.1,27.2,27.0]},'baseline':26.7,'actual_training':'mock for offline integration'})
        sha=store.hashbytes(log.read_bytes())
        packet={'plan_id':'XP1','experiment_log_path':str(log),'observations':[{'metric':'IoU','value':27.1,'baseline':26.7,
                   'conditions':'Same evaluation split and allocation','repeats':3}],
                'interpretation':'The observed direction is positive but this short test cannot prove causation or robust superiority.',
                'claimed_direction':'SUPPORT'}
        review={'role':'rce_evidence_sol','thread_ref':'independent-experiment-evidence-thread-1234','verdict':'PASS',
                 'reason':'A reported metric exists with matching log hash; it needs replication and confound checks.',
                 'log_sha256':sha}
        self.assertEqual(feedback.ingest(self.ws,packet,review)['status'],'REVIEWED_EXPERIMENT_NOT_CAUSAL_PROOF')
        self.assertEqual(store.listrows(self.ws,'hypotheses')[0]['status'],'REAL_EXPERIMENT_OBSERVED_REQUIRES_REPLICATION')
        with self.assertRaisesRegex(ValueError,'already processed'):
            feedback.ingest(self.ws,packet,review)
        self.assertEqual(len(store.listrows(self.ws,'feedback')),1)
        self.assertEqual(engine.report(self.ws)['status'],'REPORTED')
    def test_unapproved_model_or_algorithm_edits_refused(self):
        with self.assertRaisesRegex(ValueError,'Only budget'):
            rce.patch(self.ws,{'research_contract':{'immutable_confirmed_methods':False}})
        with self.assertRaisesRegex(ValueError,'require harness'):
            rce.patch(self.ws,{'ranking':{'relevance':4.9}})
        with self.assertRaisesRegex(ValueError,'No self-edit'):
            bad=store.read(self.ws/rce.CONF);bad['propose_probe_compose']['allow_script_self_edit']=True
            rce.check_cfg(bad)
    def test_proposal_cannot_be_fabricated_without_real_task(self):
        patch={'ranking':{'cost':1.25}}
        with self.assertRaisesRegex(ValueError,'No actual committed task'):
            harness.propose(self.ws,patch,'An unsupported thought about task execution without a committed prior job.',
                            ['FICTITIOUS_TASK_ID'],rce.config(self.ws),'proposer-thread-unverified-1234')
    def test_goal_change_invalidates_persistent_memory(self):
        old=store.hashbytes((self.ws/'goal.md').read_bytes())
        (self.ws/'goal.md').write_text('我现在研究一个完全不同的学科和无关联的历史主题，且不属于原宏观锁定方向。','utf8')
        self.assertNotEqual(old,store.hashbytes((self.ws/'goal.md').read_bytes()))
        with self.assertRaisesRegex(ValueError,'Macro research goal'):
            engine.get_state(self.ws)

if __name__=='__main__':unittest.main()

class ProvenanceSafety(unittest.TestCase):
    def test_same_source_cannot_change_registered_paper_identity(self):
        with tempfile.TemporaryDirectory() as d:
            ws=pathlib.Path(d)
            (ws/'goal.md').write_text('Research fixed macro direction for paper provenance verification with stable data.','utf8')
            rce.init(ws)
            works={'selected':{'core':[{'id':'WA','title':'A source document'}],
                        'related':[{'id':'WB','title':'A distinct source document'}],'inspiration':[]}}
            store.write(ws/'output/discovery_preflight/paper_library.json',works)
            store.import_catalogue(ws)
            p=ws/'paper_a.txt';p.write_text('A meaningful source about partial observation and frozen memory states. '*9,'utf8')
            before=store.import_source(ws,'WA',p)
            cache=ws/'output/research_cognition/source_cache'/(before['source_id']+'.json')
            original=cache.read_bytes()
            with self.assertRaisesRegex(ValueError,'duplicate across different work IDs'):
                store.import_source(ws,'WB',p)
            self.assertEqual(original,cache.read_bytes())
    def test_edited_original_fulltext_blocks_research_report(self):
        with tempfile.TemporaryDirectory() as d:
            ws=pathlib.Path(d);(ws/'goal.md').write_text('A preserved research direction with a valid original source document.','utf8')
            rce.init(ws)
            store.write(ws/'output/discovery_preflight/paper_library.json',{'selected':{'core':[{'id':'W1','title':'Source'}], 'related':[],'inspiration':[]}})
            store.import_catalogue(ws)
            p=ws/'a.txt';content='Evidence demonstrates an input state revision under observational uncertainty. '*10;p.write_text(content,'utf8')
            src=store.import_source(ws,'W1',p)
            with store.connect(ws) as c:
                c.execute('INSERT INTO claims VALUES (?,?,?,?,?,?,?,?,?,?)',('C1',src['source_id'],'W1','A reported method from the paper',
                    'METHOD',1,'Evidence demonstrates an input state revision under observational uncertainty.',
                    'rce_method_sol','ANCHOR_CHECKED_SEMANTICS_NOT_AUDITED',store.utc()))
            p.write_text(content+'modified and re-saved',encoding='utf8')
            with self.assertRaisesRegex(ValueError,'changed/missing'):
                engine.report(ws)

class HonestNoDiscovery(unittest.TestCase):
    def test_allow_no_supported_hypothesis_and_end_cycle(self):
        with tempfile.TemporaryDirectory() as d:
            w=pathlib.Path(d)
            (w/'goal.md').write_text('研究主线为流式占用与驾驶任务状态修订，已有数据和核心算法锁定不允许变更。','utf8')
            rce.init(w)
            store.write(w/'output/discovery_preflight/paper_library.json',{'selected':{'core':[{'id':'W1','title':'Full-text test'}],'related':[],'inspiration':[]}})
            store.import_catalogue(w)
            f=w/'article.txt';text='This article studies partial observation evidence, streaming memory and policy prediction. '*12
            f.write_text(text,'utf8');sid=store.import_source(w,'W1',f)['source_id']
            cfg=rce.config(w);engine.new_cycle(w,cfg)
            # Import prior source-checked observations explicitly, then test honest
            # HYP stage null result with actual role prompt and real commit record.
            with store.connect(w) as c:
                c.execute('INSERT INTO questions VALUES(?,?,?,?,?,?,?)',('Q1','What are the failure modes of updating memory under partial observations?',
                    .8,.7,'Memory','OPEN',store.utc()))
                c.execute('INSERT INTO claims VALUES(?,?,?,?,?,?,?,?,?,?)',('C1',sid,'W1','The method updates an evidence memory under partial observation',
                    'METHOD',1,text[:70],'rce_method_sol','ANCHOR_CHECKED_SEMANTICS_NOT_AUDITED',store.utc()))
            s=engine.get_state(w);s['cycles'][-1]['stage']='HYPOTHESIS';s['cycles'][-1]['completed_stages']=['MAP','MECHANISM','CONTRADICTION']
            store.write(engine.statefile(w),s)
            task=engine.prepare(w,cfg,rce._reserve)
            role=task['roles'][0]
            report={'stage':'HYPOTHESIS','hypotheses':[],
                'no_supported_hypothesis_reason':'Current source evidence does not distinguish a new mechanism from existing methods; more counterexample reading is needed.'}
            out=w/'model.json';store.write(out,report)
            engine.collect(w,task['job_id'],role,out,'unique-genuine-subagent-1234')
            result=engine.commit(w,task['job_id'])
            self.assertEqual(result['next_stage'],'COMPLETE')
            self.assertEqual(engine.get_state(w)['cycles'][-1]['stop_reason'],'NO_SUPPORTED_HYPOTHESIS')
            self.assertEqual(store.listrows(w,'hypotheses'),[])
            engine.report(w)
            self.assertIn('NO_SUPPORTED_HYPOTHESIS',(store.root(w)/'research_discovery_package/final_research_recommendation.md').read_text('utf8'))
