from __future__ import annotations
import copy
import importlib
import json
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE=pathlib.Path(__file__).resolve().parents[1]
ROOT=HERE.parent
sys.path.insert(0,str(HERE/'scripts'))
import topic_to_plan as topic
import store

class TopicPipelineV62Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws=pathlib.Path(self.tmp.name)/'study'
        self.ws.mkdir()
        # Copy install directory sentinel without changing the original v4.4.
        dest=self.ws/'.agents'/'skills'/'research-cognition-engine'
        dest.mkdir(parents=True)
        (dest/'SKILL.md').write_text('real installed skill',encoding='utf-8')

    def begin(self,topic_str='有限历史信息与部分可观测条件下的时序认知及任务预测研究'):
        return topic.start(self.ws,topic_str)

    def brief(self):
        t=store.read(topic.here(self.ws)/'topic_brief_template.json')
        t.update({
            'topic_interpretation':'研究有限历史信息和不完全观测条件下的时序证据、状态修订与未来预测，重点在数据可比性、机制假设和任务改进边界。',
            'problem_dimensions':['历史状态是否会随动态交通场景造成错误状态滞后问题？',
                 '固定信息容量下如何根据观测证据决定历史信息的保留问题？',
                 '任务状态修订和未来轨迹预测之间是否存在可验证关系？'],
            'core_keywords':['temporal state estimation','partial observability','historical memory','task-aware belief update'],
            'related_keywords':['sequential decision making','memory selection','future prediction','latent world model','trajectory planning'],
            'core_queries':['partial observability temporal belief state revision',
                            'memory constrained state estimation future prediction',
                            'historical evidence adaptive update driving tasks',
                            'streaming memory prediction in dynamic scenes'],
            'related_queries':['partially observable markov decision processes learning',
                               'belief state filtering with uncertain observations',
                               'temporal world models sequential decision learning',
                               'selective memory update under resource constraints',
                               'trajectory prediction uncertainty models'],
            'coverage_themes':[{'name':'Partial Observability','min_core':2},
                               {'name':'Evidence Memory Update','min_core':2},
                               {'name':'World Action Models','min_core':1}],
            'venue_hints':{'conferences':['NeurIPS','ICLR'],
                           'journals':['IEEE Transactions on Intelligent Transportation Systems']},
            'reviewer_thread_ref':'native-codex-topic-123456',
            'reasoning_boundary':'仅限研究信息不完整条件下的持续状态更新与未来任务预测；不得宣称未见原文的效果，也不得改动已有算法。'
        })
        p=topic.here(self.ws)/'topic_brief_reviewed.json'
        store.write(p,t)
        return p

    def commit(self):
        self.begin()
        with mock.patch.object(topic.suite,'initialize',return_value={'status':'INSTALL_READY'}):
            return topic.commit(self.ws,self.brief())

    def test_topic_creation_and_template(self):
        r=self.begin()
        self.assertEqual(r['status'],'NEEDS_NATIVE_TOPIC_INTERPRETATION')
        self.assertIn('有限历史信息', (self.ws/'goal.md').read_text('utf-8'))
        self.assertFalse(topic.contract(self.ws)['experiment_execution_enabled'])
        self.assertEqual(topic.next_action(self.ws)['status'],'NEEDS_NATIVE_TOPIC_INTERPRETATION')

    def test_existing_goal_is_immutable(self):
        self.ws.joinpath('goal.md').write_text('已有研究主线与已确认的冻结核心，不得改写。',encoding='utf-8')
        existing=self.ws.joinpath('goal.md').read_bytes()
        self.begin()
        self.assertEqual(self.ws.joinpath('goal.md').read_bytes(),existing)
        t=self.brief(); b=store.read(t)
        b['scope_relation']='NEW_TOPIC';store.write(t,b)
        with self.assertRaises(ValueError):
            topic.commit(self.ws,t)
        self.assertEqual(self.ws.joinpath('goal.md').read_bytes(),existing)

    def test_reject_fake_semantic_review_and_contract_change(self):
        self.begin();p=self.brief();b=store.read(p)
        b['reviewer_thread_ref']='REPLACE_WITH_ACTUAL_CODEX_THREAD';store.write(p,b)
        with self.assertRaises(ValueError):
            topic.commit(self.ws,p)
        goal=self.ws/'goal.md';goal.write_text(goal.read_text('utf-8')+'增加错误内容',encoding='utf-8')
        with self.assertRaises(ValueError):
            topic.contract(self.ws)

    def test_commit_config_is_topic_specific_and_no_relaxation(self):
        r=self.commit()
        self.assertEqual(r['status'],'TOPIC_CONFIG_COMMITTED')
        cfg=topic.V5.config(self.ws)
        self.assertNotIn('streaming 3D occupancy prediction temporal memory', cfg['queries']['core'])
        self.assertEqual(cfg['main_direction'],topic.contract(self.ws)['topic'])
        self.assertEqual(cfg['quotas'],{'core':50,'related':150,'inspiration':50})
        self.assertEqual(topic.BATCH.cfg_at(self.ws)['coverage_themes'][0]['name'],'Partial Observability')
        self.assertEqual(topic.contract(self.ws)['state'],'TOPIC_CONFIG_COMMITTED')
        self.assertEqual(topic.commit(self.ws,self.brief())['status'],'TOPIC_ALREADY_COMMITTED')

    def test_reject_reconfig_existing_discovery_campaign(self):
        self.begin();p=self.brief()
        state=self.ws/'output'/'discovery_preflight'/'state.json'
        store.write(state,{'contract':{},'works':{}})
        with self.assertRaises(ValueError):
            topic.commit(self.ws,p)

    def test_venue_profile_observed_vs_unverified_hints(self):
        self.commit()
        config=topic.V5.config(self.ws)
        state=topic.V5.fresh_state(self.ws,config)
        def sample(wid,venue,stype,year):
            return {'id':'https://openalex.org/'+wid,'venue':venue,'source_id':'https://openalex.org/S'+wid[1:],
                'venue_type':stype,'category_sources':['core'],'year':year,'oa_pdf_url':'https://papers.example.org/a.pdf',
                'title':'Credible scientific paper on memory '+wid}
        state['works']={'A':sample('W123','IEEE Transactions on Intelligent Transportation Systems','journal',2025),
                        'B':sample('W456','Neural Information Processing Systems','conference',2025),
                        'C':sample('W789','Unclassified proceedings','other',2022)}
        store.write(self.ws/'output'/'discovery_preflight'/'state.json',state)
        result=topic.venues(self.ws)
        self.assertEqual(result['source_count'],3)
        self.assertEqual(result['verified_conference_sources'],1)
        self.assertEqual(result['verified_journal_sources'],1)
        metadata=store.read(topic.here(self.ws)/'venue_landscape.json')
        self.assertIn('NOT an official JCR/CAS/CCF rank', metadata['source_disclaimer'])
        self.assertEqual(next(x for x in metadata['sources'] if x['name']=='Unclassified proceedings')['type'],'UNKNOWN_VERIFY_SOURCE')

    def test_auth_download_gate_no_auto_paywall(self):
        self.commit()
        config=topic.V5.config(self.ws)
        state=topic.V5.fresh_state(self.ws,config)
        state['selection']={'selected':{'core':[{'id':'https://openalex.org/W111','oa_pdf_url':'https://research.example/paper.pdf'}]}}
        store.write(self.ws/'output'/'discovery_preflight'/'state.json',state)
        with mock.patch.object(topic.wf,'choose',return_value={'status':'NEEDS_ORIGINAL_V44_INGEST'}):
            next_=topic.next_action(self.ws)
            self.assertEqual(next_['status'],'NEEDS_AUTHORIZED_CORE_PDF_DOWNLOAD')
            with mock.patch.object(topic.V5,'obtain_fulltexts',return_value={'status':'DOWNLOAD_BATCH_DONE','downloaded':['a.pdf']}) as dl:
                out=topic.drive(self.ws,online=True,download=True)
                self.assertIn('NEEDS_AUTHORIZED_CORE_PDF_DOWNLOAD',str(out['performed']))
                self.assertTrue(dl.call_args.kwargs['online'])
                self.assertEqual(dl.call_args.kwargs['limit'],3)
            no_online=topic.drive(self.ws)
            self.assertEqual(no_online['status'],'PAUSED_FOR_EXTERNAL_ACTION_OR_LIMIT')
            self.assertEqual(no_online['performed'],[])

    def test_final_quality_blocker_without_real_reading(self):
        self.commit()
        res=topic.finalize(self.ws)
        self.assertEqual(res['status'],'BLOCKED_INSUFFICIENT_SCIENTIFIC_EVIDENCE')
        self.assertTrue(res['no_false_final_report'])
        self.assertFalse((topic.store.root(self.ws)/'research_discovery_package'/'topic_to_experiment_plan.md').exists())

    def test_reading_english_adapted_source_matches_integrity_manifest(self):
        original=ROOT/'batch-paper-deepread-desktop'/'scripts'/'deepread.py'
        manifest=store.read(ROOT/'research-cognition-engine'/'references'/'original_v44_file_manifest.json')
        expected=manifest['skill_files_sha256']['scripts/deepread.py']
        self.assertIn('scripts/deepread.py',manifest['original_v44_skill_files_sha256'])
        self.assertEqual(store.hashbytes(original.read_bytes()),expected)

if __name__=='__main__':unittest.main()

class GenericTopicSearchV62Tests(unittest.TestCase):
    def test_dynamic_topic_scorer_does_not_require_vehicle_words(self):
        defaults=store.read(topic.V5.DEFAULT)
        record={'title':'Novel mathematical study of memory constrained belief state update',
                'abstract':'Sequential state estimation under partial observability',
                'category_sources':['core'],'inspiration_domains':[]}
        standard=topic.V5.paper_scores(record,defaults)
        self.assertFalse(standard['core_eligible'])
        generic=copy.deepcopy(defaults)
        generic['topic_generic_research_mode']=True
        generic['core_keywords']=['memory constrained belief','partial observability']
        adapted=topic.V5.paper_scores(record,generic)
        self.assertTrue(adapted['core_eligible'])
        self.assertGreater(adapted['core'],0)

class FinalPlanGateV62Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws=pathlib.Path(self.tmp.name)/'lab'
        self.ws.mkdir()
        goal='限定研究：面向部分可观测任务的证据记忆修订，仅提出研究问题和实验计划，不执行实验。'
        (self.ws/'goal.md').write_text(goal,encoding='utf-8')
        store.write(topic.contract_path(self.ws),{
            'schema_version':1,'version':'6.2.0','topic':'部分可观测任务证据记忆修订',
            'topic_sha256':store.hashbytes('部分可观测任务证据记忆修订'.encode()),
            'goal_sha256':store.hashbytes((self.ws/'goal.md').read_bytes()),
            'created_goal':False,'state':'TOPIC_CONFIG_COMMITTED','as_of_date':'2026-10-25'})
        store.write(topic.here(self.ws)/'topic_brief_reviewed.json',{
            'venue_hints':{'conferences':['CVPR'],'journals':['IEEE T-ITS']}})
        cfg=store.read(topic.V5.DEFAULT);cfg['as_of_date']='2026-10-25'
        store.write(self.ws/'discovery_config.json',cfg)
        state=topic.V5.fresh_state(self.ws,cfg)
        state['works']={'id1':{'id':'https://openalex.org/W123','title':'Source-backed paper',
            'year':2025,'category_sources':['core'],'source_id':'https://openalex.org/S9',
            'venue':'Neural Information Processing Systems','venue_type':'conference','oa_pdf_url':''}}
        store.write(self.ws/'output'/'discovery_preflight'/'state.json',state)
        with store.connect(self.ws) as c:
            c.execute('INSERT INTO works(work_id,title,category,doi,year,venue,url,record_sha) VALUES (?,?,?,?,?,?,?,?)',
                  ('https://openalex.org/W123','Source-backed paper','core','',2025,'Neural Information Processing Systems','', 'sha'))
        f=self.ws/'original.txt';q='The method conditions memory updates on observed evidence and temporal context.'
        f.write_text(('The source contains laboratory provenance. '*100)+q+(' Source conclusion. '*100),encoding='utf-8')
        entry=store.import_source(self.ws,'https://openalex.org/W123',f)
        self.source=entry['source_id'];self.quote=q
        with store.connect(self.ws) as c:
            c.execute('INSERT INTO claims VALUES (?,?,?,?,?,?,?,?,?,?)',
                     ('CL1',self.source,'https://openalex.org/W123',
                      'Author defines memory evidence updates in temporal context',
                      'METHOD',1,q,'rce_method_sol','ANCHOR_CHECKED_SEMANTICS_NOT_AUDITED',store.utc()))
            c.execute('INSERT INTO questions VALUES (?,?,?,?,?,?,?)',
                     ('Q1','How should evidence memory adapt to changing observations?',.9,.8,'memory','OPEN',store.utc()))
            c.execute('INSERT INTO hypotheses VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                     ('H1','Q1','Partial-observability memory revision potentially improves planning accuracy',
                      'Use conflicting observations to correct persistent task-relevant belief representations',
                      'Temporal decisions should improve with corrected belief state information',
                      'Reject if no robust improvements relative to the fixed memory baseline',
                      'Comparable training resources and observation protocols',
                      '["CL1"]','["https://openalex.org/W123"]',
                      'Use the fixed baseline with controlled information availability and repeated seeds',
                      'NOVELTY_UNVERIFIED','PROPOSED_UNTESTED',store.utc()))
            for role,thread in [('rce_novelty_sol','thread_s_111'),('rce_skeptic_astra','thread_a_222')]:
                c.execute('INSERT INTO assessments VALUES (?,?,?,?,?,?,?)',
                          ('H1',role,'UNCERTAIN','["https://openalex.org/W123"]',
                           'The closest registered prior work may address the same memory mechanism but scope differs.',thread,store.utc()))
            c.execute('INSERT INTO experiments VALUES (?,?,?,?,?,?,?,?,?)',
                      ('XP1','H1','Controlled temporal prediction test with matched resource budget and ablations',
                       '["Baseline deterministic memory selection"]','["temporal accuracy"]',
                       'If no gain across repeated seeds and protocol-matched comparisons, reject hypothesis',
                       'Public driving dataset; requires researcher-run compute only','PLANNED_NOT_EXECUTED',store.utc()))
            c.execute('INSERT INTO decisions VALUES (?,?,?,?,?,?,?)',
                      ('D1','H1','Validate the hypothesis with protocol-matched experiments and nearest-work comparison',
                       'Current novelty remains uncertain and the comparison source needs deeper semantic analysis',
                       'Only the researcher may approve and execute any experiment','PENDING_USER_APPROVAL',store.utc()))
        store.write(topic.ENGINE.statefile(self.ws),{
            'schema_version':6,'macro_goal_sha256':store.hashbytes((self.ws/'goal.md').read_bytes()),
            'cycles':[{'id':'RC0001','stage':'COMPLETE','completed_stages':list(topic.ENGINE.STAGES)}]})
        prior=importlib.import_module('prior_art')
        prior.init_db(self.ws)
        with store.connect(self.ws) as c:
            for i in range(2):
                qid=f'PA-TEST-{i}'
                c.execute('INSERT INTO prior_art_queries(query_id,hypothesis_id,query,band,start_date,end_date,query_plan_sha,status,raw_count,created_at,completed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                          (qid,'H1','memory belief query','RECENT_3Y','2023-10-25','2026-10-25','sha','COMPLETE',1,store.utc(),store.utc()))
                c.execute('INSERT INTO prior_art_links VALUES (?,?,?,?,?,?)',
                          ('H1','https://openalex.org/W123',qid,'https://openalex.org/W123','sha',store.utc()))

    def test_valid_plan_not_execution(self):
        rec=store.read(topic.contract_path(self.ws));rec['route_contract_version']=1;store.write(topic.contract_path(self.ws),rec)
        with mock.patch.object(topic.V5,'status',return_value={'status':'CATALOG_250_PLUS_COMPLETE','counts':{'core':50,'related':150,'inspiration':50}}),\
             mock.patch.object(topic.BATCH,'load_state',return_value={'frozen':{'core_workspace':str(self.ws)}}),\
             mock.patch.object(topic.suite.original_core,'env',return_value={'test':'environment'}),\
             mock.patch.object(topic.suite.original_core,'run_status',return_value={'status':'COMPLETE'}):
            q=topic.quality(self.ws)
            self.assertEqual(q['status'],'FINAL_PLAN_READY_FOR_USER',q['hard_blockers'])
            res=topic.finalize(self.ws)
            self.assertEqual(res['status'],'FINAL_PLAN_READY_FOR_USER')
            report=pathlib.Path(res['final_report']).read_text('utf-8')
            self.assertIn('experiment plan',report.lower())
            self.assertIn('researcher',report.lower())
            self.assertTrue(res['no_experiment_executed'])
            self.assertFalse((self.ws/'experiment_results.json').exists())

    def test_no_independent_novelty_audit_no_final(self):
        with store.connect(self.ws) as c:
            c.execute("DELETE FROM assessments WHERE role='rce_skeptic_astra'")
        with mock.patch.object(topic.V5,'status',return_value={'status':'CATALOG_250_PLUS_COMPLETE'}),\
             mock.patch.object(topic.BATCH,'load_state',return_value={'frozen':{'core_workspace':str(self.ws)}}),\
             mock.patch.object(topic.suite.original_core,'env',return_value={}),\
             mock.patch.object(topic.suite.original_core,'run_status',return_value={'status':'COMPLETE'}):
            q=topic.finalize(self.ws)
        self.assertEqual(q['status'],'BLOCKED_INSUFFICIENT_SCIENTIFIC_EVIDENCE')
        self.assertTrue(q['blocking_reasons'])
