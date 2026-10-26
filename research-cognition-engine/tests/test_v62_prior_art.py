from __future__ import annotations
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

SKILL=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SKILL/'scripts'))
import prior_art
import topic_to_plan as topic
import store

class PriorArtV62Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws=pathlib.Path(self.tmp.name)/'project'
        self.ws.mkdir()
        (self.ws/'goal.md').write_text('真正的研究主线：部分可观测与历史信息修订下的任务状态估计，不修改论文的已有核心算法。',encoding='utf-8')
        store.write(topic.contract_path(self.ws),{'schema_version':1,'version':'6.2.0','topic':'部分可观测状态修订',
            'topic_sha256':store.hashbytes('部分可观测状态修订'.encode()),
            'goal_sha256':store.hashbytes((self.ws/'goal.md').read_bytes()),
            'created_goal':False,'state':'TOPIC_CONFIG_COMMITTED','as_of_date':'2026-10-25'})
        v5=store.read(topic.V5.DEFAULT)
        v5['as_of_date']='2026-10-25'
        store.write(self.ws/'discovery_config.json',v5)
        with store.connect(self.ws) as c:
            c.execute('INSERT INTO works(work_id,title,category,doi,year,venue,url,record_sha) VALUES (?,?,?,?,?,?,?,?)',
                      ('https://openalex.org/W111','Recorded real-method identity for test only','core','',2025,'Journal Example','', 'sha'))
            c.execute('INSERT INTO questions VALUES (?,?,?,?,?,?,?)',
                      ('Q1','What happens to task belief updates?',.8,.8,'temporal','OPEN',store.utc()))
            c.execute('INSERT INTO hypotheses VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      ('H1','Q1','新状态机制基于记忆有限时仍可修订动态事件的历史证据','通过当前观测与历史状态之间的证据冲突校正下一步信念状态',
                       '不完全观测下减小状态估计误差并改善预测稳定性','如果对照实验未发现性能差异则放弃此研究假设','相机时间同步和训练协议一致',
                       '["CL1"]','["https://openalex.org/W111"]','固定容量任务预测基线对照',
                       'NOVELTY_UNVERIFIED','PROPOSED_UNTESTED',store.utc()))

    def template(self):
        r=prior_art.template(self.ws)
        self.assertEqual(r['status'],'NEEDS_PRIOR_ART_QUERY_REVIEW')
        p=prior_art.root(self.ws)/'review_template.json'
        data=store.read(p)
        data['reviewer_thread_ref']='native-rce-novelty-review-88'
        data['hypotheses'][0]['queries']=[
            'belief state revision under partial observability',
            'memory update uncertainty counterexamples for prediction']
        store.write(prior_art.root(self.ws)/'reviewed_novelty_queries.json',data)

    def test_unreviewed_templates_never_search(self):
        p=prior_art.plan(self.ws)
        self.assertEqual(p['status'],'NEEDS_PRIOR_ART_QUERY_REVIEW')
        with self.assertRaises(ValueError):
            prior_art.search(self.ws,online=False)
        self.assertFalse((prior_art.root(self.ws)/'reviewed_novelty_queries.json').exists())

    def test_changed_hypothesis_blocks_stale_queries(self):
        self.template()
        with store.connect(self.ws) as c:
            c.execute("UPDATE hypotheses SET mechanism=? WHERE hypothesis_id='H1'",('新的内容导致原查询过期',))
        with self.assertRaises(ValueError):
            prior_art.plan(self.ws)

    def test_verified_real_metadata_search_and_dedup(self):
        self.template()
        class Fake:
            def query(self,q,start,end,page):
                self.calls=(getattr(self,'calls',0)+1)
                return ([{'id':'https://openalex.org/W999','display_name':'Memory mechanism studies under uncertainty',
                    'publication_date':'2025-04-03','type':'article','doi':'https://doi.org/10.1000/sample',
                    'authorships':[{'author':{'display_name':'Researcher A'}}],
                    'primary_location':{'source':{'id':'https://openalex.org/S123','display_name':'Journal X','type':'journal'}},
                    'best_oa_location':{'pdf_url':'https://research.example.org/open.pdf'},
                    'open_access':{'is_oa':True}}],{'result_count':1})
        fake=Fake()
        p=prior_art.plan(self.ws)
        self.assertTrue(p['pending_queries'])
        first=prior_art.search(self.ws,online=True,max_requests=2,fetcher=fake)
        self.assertEqual(first['requests'],2)
        self.assertEqual(first['new_prior_art_bibliography'],1)
        self.assertEqual(first['coverage']['status'],'PRIOR_ART_RECENT_SEARCH_DONE')
        self.assertEqual(prior_art.coverage(self.ws)['counts']['H1']['registered_prior_works'],1)
        self.assertEqual(len(prior_art.context_for_review(self.ws)),1)
        with store.connect(self.ws) as c:
            x=c.execute("SELECT category,source_status FROM works WHERE work_id='https://openalex.org/W999'").fetchone()
            self.assertEqual((x['category'],x['source_status']),('prior_art_candidate','BIB_ONLY'))
        self.assertEqual(prior_art.downloadable(self.ws)['count'],1)
        retry=prior_art.search(self.ws,online=True,max_requests=2,fetcher=fake)
        self.assertEqual(retry['requests'],2)  # next older band, not same query repeated

    def test_query_review_is_not_free_pass(self):
        self.template()
        p=prior_art.root(self.ws)/'reviewed_novelty_queries.json'
        data=store.read(p)
        data['hypotheses'][0]['queries'][0]='REPLACE WITH ANYTHING'
        store.write(p,data)
        with self.assertRaises(ValueError):
            prior_art.plan(self.ws)

if __name__=='__main__':unittest.main()
