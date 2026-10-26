"""All OpenAlex and PDF responses in tests are synthetic; no real paper discovered."""
import copy, datetime as dt, hashlib, json, pathlib, sys, tempfile, unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import paper_discovery as m


def fake_work(name,idx,date='2025-09-14',venue='CVPR',cat='core',domain=''):
    idxhash=int(hashlib.sha256((name+str(idx)).encode()).hexdigest()[:11],16)
    if cat=='core':title=f'Streaming 3D Occupancy Prediction for Autonomous Driving {idxhash}'
    elif cat=='related':title=f'BEV Perception for Autonomous Driving with Visual Features {idxhash}'
    else:title=f'{domain.replace("_"," ")} Study of Human Decisions and Social Mechanisms {idxhash}'
    return {'id':f'https://openalex.org/W{idxhash}','doi':f'https://doi.org/10.9900/test{idxhash}',
            'display_name':title,'publication_date':date,'publication_year':int(date[:4]),'type':'article',
            'cited_by_count':idx%100,'authorships':[{'author':{'display_name':'Synthetic Author'}}],
            'abstract_inverted_index':{'temporal':[0],'occupancy':[1],'autonomous':[2], 'driving':[3]} if cat!='inspiration' else {'economic':[0],'reasoning':[1]},
            'primary_location':{'source':{'display_name':venue,'type':'journal'},'landing_page_url':f'https://doi.org/10.9900/test{idxhash}'},
            'best_oa_location':{'pdf_url':f'https://arxiv.org/pdf/{idxhash}.pdf','is_oa':True},
            'open_access':{'is_oa':True}}


class FakeAPI:
    key=False
    def __init__(self,config,year_ranges=None):
        self.config=config
        self.calls=[]
        self.year_ranges=year_ranges or ['RECENT']
    def query(self,q,start,end,page):
        self.calls.append((q,start,end,page))
        keys=self.config['queries']
        if q in keys['core']:
            cat='core';domain='';n=9;index=keys['core'].index(q)
        elif q in keys['related']:
            cat='related';domain='';n=14;index=keys['related'].index(q)
        else:
            domain=next(d for d,a in keys['inspiration'].items() if q in a)
            cat='inspiration';n=5;index=sum(len(v) for d,v in keys['inspiration'].items() if d<domain)+keys['inspiration'][domain].index(q)
        date='2025-09-14'
        if start > date and 'EXTENDED' not in self.year_ranges:return [],{}
        if end < date and 'EXTENDED' not in self.year_ranges:return [],{}
        if 'EXTENDED' in self.year_ranges:
            date='2022-09-14'
            if start > date or end < date:return [],{}
        papers=[fake_work(q,index*40+i,date, 'CVPR' if cat!='inspiration' and i%2==0 else 'American Economic Review' if cat=='inspiration' and i%2==0 else 'Other Academic Venue',cat,domain) for i in range(n)]
        return papers,{'result_count':len(papers),'rate_remaining':'fake-test'}


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.ws=pathlib.Path(self.t.name)
        m.init(self.ws)
        self.c=m.config(self.ws)
        self.c['as_of_date']='2026-10-25'
        m.write(self.ws/'discovery_config.json',self.c)
    def tearDown(self):self.t.cleanup()
    def test_exact_250_disjoint_pools_and_no_llm_calls(self):
        api=FakeAPI(self.c)
        first=m.run(self.ws,online=True,request_limit=25,fetcher=api)
        self.assertEqual(first['status'],'PAUSED_REQUEST_BUDGET')
        self.assertEqual(len(api.calls),25)
        n_after=len(m.state_at(self.ws,self.c)['works'])
        self.assertGreater(n_after,150)
        second=m.run(self.ws,online=True,request_limit=25,fetcher=api)
        self.assertEqual(second['status'],'CATALOG_COMPLETE')
        selection=m.state_at(self.ws,self.c)['selection']
        self.assertEqual(selection['counts'],{'core':50,'related':150,'inspiration':50})
        pools=selection['selected']
        ids=[w['id'] for cat in m.CATEGORIES for w in pools[cat]]
        self.assertEqual(len(ids),250)
        self.assertEqual(len(set(ids)),250)
        self.assertGreater(selection['preferred_venue_counts']['core'],0)
        self.assertGreater(selection['recent_3_year_counts']['related'],140)
        self.assertFalse((self.ws/'input').exists())
        self.assertFalse((self.ws/'cross_domain_input').exists())
        self.assertTrue((m.root_out(self.ws)/'discovery_core_target_50.csv').exists())
        self.assertTrue((m.root_out(self.ws)/'discovery_report.md').exists())
        calls_done=len(api.calls)
        again=m.run(self.ws,online=True,fetcher=api)
        self.assertEqual(again['status'],'ALREADY_COMPLETE')
        self.assertEqual(len(api.calls),calls_done)
    def test_stage_expansion_when_recent_not_enough(self):
        c=self.c
        c['quotas']={'core':1,'related':1,'inspiration':1}
        c['preferred_domains']={key:0 for key in c['preferred_domains']}
        m.write(self.ws/'discovery_config.json',c)
        api=FakeAPI(c,year_ranges=['EXTENDED'])
        result={}
        for _ in range(5):
            result=m.run(self.ws,online=True,request_limit=25,fetcher=api)
            if result['status']!='PAUSED_REQUEST_BUDGET':break
        self.assertEqual(result['status'],'CATALOG_COMPLETE')
        self.assertEqual(result['expansion_stopped_at'],'EXTENDED_3_TO_5Y')
        selected=m.state_at(self.ws,c)['selection']['selected']
        self.assertEqual(selected['core'][0]['year'],2022)
    def test_incomplete_quota_never_fakes_count(self):
        c=self.c
        c['api']['max_queries_per_run']=1
        m.write(self.ws/'discovery_config.json',c)
        result=m.run(self.ws,online=True,fetcher=FakeAPI(c))
        self.assertEqual(result['status'],'PAUSED_REQUEST_BUDGET')
        self.assertGreater(result['shortfalls']['related'],0)
        status=m.status(self.ws)
        self.assertEqual(status['fulltexts_downloaded'],0)
        self.assertNotEqual(status['status'],'CATALOG_250_PLUS_COMPLETE')
    def test_offline_without_authorization_blocks(self):
        with self.assertRaises(ValueError):
            m.run(self.ws,online=False)
        self.assertEqual(m.state_at(self.ws,self.c)['api_calls'],0)
    def test_goal_or_config_change_rejects_cache(self):
        m.state_at(self.ws,self.c)
        (self.ws/'goal.md').write_text('different frozen main direction','utf-8')
        with self.assertRaises(ValueError):
            m.state_at(self.ws,self.c)
    def test_duplicate_doi_and_cross_category_exclusivity(self):
        c=self.c;c['quotas']={'core':1,'related':1,'inspiration':1}
        c['preferred_domains']={k:0 for k in c['preferred_domains']}
        m.write(self.ws/'discovery_config.json',c)
        s=m.state_at(self.ws,c)
        corea=m.work_normalized(fake_work('core',1), 'core','','core search')
        related=copy.deepcopy(corea);related['id']='https://openalex.org/W999999999998';related['category_sources']=['related'];related['query_provenance']=[{'category':'related','domain':'','query':'x'}]
        rel_other=m.work_normalized(fake_work('related',1,cat='related'),'related','','related query')
        cross=m.work_normalized(fake_work('cross',1,cat='inspiration',domain='philosophy'),'inspiration','philosophy','philosophy query')
        s['works']={r['id']:r for r in (corea,related,rel_other,cross)}
        chosen=m.select(self.ws,c,s)
        self.assertEqual(chosen['counts'],{'core':1,'related':1,'inspiration':1})
        self.assertEqual(chosen['unique_selected'],3)
    def test_ranked_recent_preferred_venue_before_later_and_other(self):
        main=m.work_normalized(fake_work('cvpr',10,date='2025-03-21',venue='CVPR'),'core','','x')
        general=m.work_normalized(fake_work('other',10,date='2026-01-10',venue='Some Else'),'core','','x')
        older=m.work_normalized(fake_work('old',10,date='2022-11-10',venue='CVPR'),'core','','x')
        order=sorted((main,general,older),key=lambda v:m.rank(v,self.c,dt.date(2026,10,25)))
        self.assertEqual([v['id'] for v in order],[main['id'],general['id'],older['id']])
    def test_source_link_and_pdf_distinction(self):
        paper=fake_work('test',22)
        paper['best_oa_location']=None;paper['open_access']={'is_oa':False}
        row=m.work_normalized(paper,'core','','')
        self.assertTrue(row['doi'].startswith('10.'))
        self.assertEqual(row['oa_pdf_url'],'')
        self.assertIn('doi.org',row['bibliographic_link'])
    def test_no_key_pagination_disallowed(self):
        api=m.OpenAlex(self.c)
        api.key=''
        with self.assertRaisesRegex(ValueError,'API key'):
            api.query('test query','2024-01-01','2026-10-25',2)
    def test_download_requires_separate_consent(self):
        with self.assertRaises(ValueError):
            m.obtain_fulltexts(self.ws,online=False,category='core')
    def test_fake_oa_pdf_is_only_metadata_without_parse(self):
        c=self.c
        c['quotas']={'core':1,'related':1,'inspiration':1}
        c['preferred_domains']={k:0 for k in c['preferred_domains']}
        m.write(self.ws/'discovery_config.json',c)
        s=m.state_at(self.ws,c)
        data=[m.work_normalized(fake_work('core',x,cat=t,domain='philosophy' if t=='inspiration' else ''),t,'philosophy' if t=='inspiration' else '',t) for x,t in enumerate(('core','related','inspiration'))]
        s['works']={d['id']:d for d in data};m.select(self.ws,c,s);m.write(m.root_out(self.ws)/'state.json',s)
        status=m.status(self.ws)
        self.assertEqual(status['fulltexts_downloaded'],0)
        self.assertEqual(status['fulltext_ready_for_deepread'],'CHECK_INPUT_AND_INGEST_FIRST')
    def test_safe_url_rejects_private_ipv4_ipv6_and_plain_http(self):
        for url in ('http://arxiv.org/pdf/x.pdf','https://127.0.0.1/x.pdf',
                    'https://[::1]/x.pdf','https://localhost.localdomain/x',
                    'https://user:pass@site.com/x.pdf','file:///etc/passwd'):
            self.assertFalse(m.safe_url(url),url)
    def test_csv_formula_injection_neutralized(self):
        self.assertEqual(m._safe_cell('=HYPERLINK(\"http://foo\")'),"'=HYPERLINK(\"http://foo\")")

if __name__=='__main__':unittest.main()


class ExtraQualityTests(unittest.TestCase):
    def test_same_metadata_count_not_accepted_until_current_window_done(self):
        with tempfile.TemporaryDirectory() as d:
            ws=pathlib.Path(d);m.init(ws);c=m.config(ws);c['as_of_date']='2026-10-25'
            c['quotas']={'core':1,'related':1,'inspiration':1}
            c['preferred_domains']={k:0 for k in c['preferred_domains']}
            m.write(ws/'discovery_config.json',c)
            fake=FakeAPI(c)
            for _ in range(20):
                response=m.run(ws,online=True,request_limit=3,fetcher=fake)
                if response['status']=='CATALOG_COMPLETE':break
                self.assertNotEqual(m.status(ws)['status'],'CATALOG_250_PLUS_COMPLETE')
            self.assertEqual(response['status'],'CATALOG_COMPLETE')
            self.assertEqual(m.status(ws)['status'],'CATALOG_250_PLUS_COMPLETE')
    def test_top_venue_workshop_not_mistaken_for_flagship(self):
        with tempfile.TemporaryDirectory() as d:
            ws=pathlib.Path(d);m.init(ws);c=m.config(ws)
            w=m.work_normalized(fake_work('venuex',2,venue='CVPR Workshop 2025'),'core','','')
            self.assertFalse(m.priority_venue(w,c))
            w['venue']='Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition'
            self.assertTrue(m.priority_venue(w,c))
    def test_inspiration_50_count_insufficient_if_cross_domain_minima_not_met(self):
        with tempfile.TemporaryDirectory() as d:
            ws=pathlib.Path(d);m.init(ws);c=m.config(ws)
            c['as_of_date']='2026-10-25'
            c['quotas']={'core':1,'related':1,'inspiration':5}
            c['preferred_domains']={k:(1 if k in ('philosophy','sociology') else 0) for k in c['preferred_domains']}
            m.write(ws/'discovery_config.json',c);s=m.state_at(ws,c)
            records=[]
            records.append(m.work_normalized(fake_work('coreq',101),'core','',''))
            records.append(m.work_normalized(fake_work('relq',202,cat='related'),'related','',''))
            for i in range(7):records.append(m.work_normalized(fake_work(f'phil{i}',300+i,cat='inspiration',domain='philosophy'),'inspiration','philosophy',''))
            s['works']={r['id']:r for r in records}
            outcome=m.select(ws,c,s)
            self.assertEqual(outcome['counts']['inspiration'],5)
            self.assertEqual(outcome['inspiration_domain_shortfalls']['sociology'],1)
            self.assertEqual(outcome['status'],'INCOMPLETE_NEEDS_MORE_SOURCES')
    def test_complete_when_full_range_scanned_and_early_stop_false(self):
        with tempfile.TemporaryDirectory() as d:
            ws=pathlib.Path(d);m.init(ws);c=m.config(ws)
            c['as_of_date']='2026-10-25';c['stop_on_quota_complete']=False
            c['quotas']={'core':1,'related':1,'inspiration':1}
            c['preferred_domains']={k:0 for k in c['preferred_domains']}
            c['api']['max_queries_per_run']=200
            m.write(ws/'discovery_config.json',c)
            out=m.run(ws,online=True,request_limit=200,fetcher=FakeAPI(c))
            self.assertEqual(out['status'],'CATALOG_COMPLETE')
            self.assertEqual(m.status(ws)['status'],'CATALOG_250_PLUS_COMPLETE')
