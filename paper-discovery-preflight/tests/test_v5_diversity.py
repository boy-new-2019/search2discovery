"""V5 wide serendipity: real source provenance and deliberately heterogeneous fields.
All bibliographic fixtures in this suite are synthetic; no network access.
"""
import copy
import pathlib
import sys
import tempfile
import unittest
from collections import Counter

BASE=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'scripts'))
import paper_discovery as p
import inspiration_diversity as div
from test_preflight import fake_work, FakeAPI


class WideInspirationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.ws=pathlib.Path(self.tmp.name)
        p.init(self.ws)
        self.c=p.config(self.ws)
        self.c['as_of_date']='2026-10-25'
        p.write(self.ws/'discovery_config.json',self.c)
    def tearDown(self):self.tmp.cleanup()

    def test_v5_catalog_is_broad_nontrivial_and_prompt_configurable(self):
        catalog=div.load_catalog(self.c)
        self.assertEqual(self.c['schema_version'],2)
        self.assertGreaterEqual(len(catalog['domains']),90)
        self.assertGreaterEqual(len(catalog['families']),15)
        self.assertGreaterEqual(sum(d['distance_to_mainline_heuristic']=='far' for d in catalog['domains'].values()),60)
        expected=['nobel_economics','philosophy','sociology','linguistics','musicology','archaeology',
                  'astronomy','immunology','ecology','culinary_science','museum_studies',
                  'sports_science','meteorology','criminalogies']
        for name in expected[:-1]:self.assertIn(name,catalog['domains'])
        self.assertNotIn(expected[-1],catalog['domains'])
        self.assertEqual(self.c['quotas'],{'core':50,'related':150,'inspiration':50})
        policy=self.c['inspiration_diversity']
        self.assertEqual(policy['min_unique_domains'],24)
        self.assertEqual(policy['min_macro_groups'],12)
        self.assertEqual(policy['min_far_distance'],24)
        self.assertLessEqual(policy['max_per_domain'],3)

    def test_first_queries_cover_all_macro_disciplines_before_repeats(self):
        queries=[(cat,dom,q) for cat,dom,q in p.queries_for(self.c) if cat=='inspiration']
        first=queries[:15]
        macros=[div.load_catalog(self.c)['domains'][d]['macro_group'] for _,d,_ in first]
        self.assertEqual(len(set(macros)),15)
        self.assertEqual(len(set(d for _,d,_ in first)),15)
        self.assertEqual(len(queries),sum(map(len,self.c['queries']['inspiration'].values())))
        self.assertNotIn('autonomous driving',' '.join(q for _,_,q in first))

    def test_true_250_catalog_is_exclusive_and_has_v5_breadth(self):
        fetcher=FakeAPI(self.c)
        first=p.run(self.ws,online=True,request_limit=25,fetcher=fetcher)
        self.assertEqual(first['status'],'PAUSED_REQUEST_BUDGET')
        second=p.run(self.ws,online=True,request_limit=25,fetcher=fetcher)
        self.assertEqual(second['status'],'CATALOG_COMPLETE')
        report=p.state_at(self.ws,self.c)['selection']
        self.assertEqual(report['counts'],self.c['quotas'])
        b=report['inspiration_breadth']
        self.assertGreaterEqual(b['unique_domains'],24)
        self.assertGreaterEqual(b['unique_macro_groups'],12)
        self.assertGreaterEqual(b['far_field_papers'],24)
        self.assertFalse(any(b['shortfalls'].values()))
        chosen=report['selected']['inspiration']
        perdom=Counter(x['assigned_inspiration_domain'] for x in chosen)
        perfamily=Counter(x['inspiration_macro_group'] for x in chosen)
        self.assertLessEqual(max(perdom.values()),3)
        self.assertLessEqual(max(perfamily.values()),7)
        self.assertTrue(all(x['nobel_laureate_verified'] is False for x in chosen))
        urls=[x['id'] for cat in p.CATEGORIES for x in report['selected'][cat]]
        self.assertEqual(len(urls),len(set(urls)))
        csv=(p.root_out(self.ws)/'discovery_inspiration_target_50.csv').read_text('utf-8-sig')
        self.assertIn('assigned_domain,macro_group,transfer_distance_heuristic',csv)
        readme=(p.root_out(self.ws)/'discovery_report.md').read_text('utf8')
        self.assertIn('interdisciplinary breadth audit',readme)

    def test_monoculture_50_cannot_be_marked_complete(self):
        s=p.state_at(self.ws,self.c)
        for i in range(60):
            work=p.work_normalized(fake_work('allphilosophy',i,cat='inspiration',domain='philosophy'),
                                   'inspiration','philosophy','query')
            s['works'][work['id']]=work
        selected=p.select(self.ws,self.c,s)
        self.assertLessEqual(selected['counts']['inspiration'],3)
        self.assertGreater(selected['shortfalls']['inspiration'],0)
        self.assertGreater(selected['inspiration_breadth']['shortfalls']['unique_domains'],0)
        self.assertEqual(selected['status'],'INCOMPLETE_NEEDS_MORE_SOURCES')

    def test_missing_macro_family_is_a_real_coverage_gap_even_at_50(self):
        # Only seven macro groups have enough candidates to supply 50 works if
        # a user relaxed the group cap; it must still fail min 12 broad families.
        c=copy.deepcopy(self.c)
        c['inspiration_diversity']['max_per_macro_group']=50
        c['inspiration_diversity']['max_per_domain']=10
        c['preferred_domains']={x:0 for x in c['preferred_domains']}
        s=p.fresh_state(self.ws,c)
        familymap=div.load_catalog(c)['domains']
        names=[]
        for field in c['queries']['inspiration']:
            if familymap[field]['macro_group'] not in {familymap[d]['macro_group'] for d in names} and len(names)<7:
                names.append(field)
        for fld in names:
            for i in range(20):
                item=p.work_normalized(fake_work(fld,i,cat='inspiration',domain=fld),'inspiration',fld,'query')
                s['works'][item['id']]=item
        x=p.select(self.ws,c,s)
        self.assertEqual(x['counts']['inspiration'],50)
        self.assertGreater(x['inspiration_breadth']['shortfalls']['macro_groups'],0)
        self.assertEqual(x['status'],'INCOMPLETE_NEEDS_MORE_SOURCES')

    def test_extension_falls_back_without_fabricating_sources(self):
        c=copy.deepcopy(self.c)
        c['quotas']={'core':1,'related':1,'inspiration':1}
        c['preferred_domains']={x:0 for x in c['preferred_domains']}
        p.write(self.ws/'discovery_config.json',c)
        fetcher=FakeAPI(c,year_ranges=['EXTENDED'])
        out=None
        for _ in range(4):
            out=p.run(self.ws,online=True,request_limit=35,fetcher=fetcher)
            if out['status']=='CATALOG_COMPLETE':break
        self.assertEqual(out['status'],'CATALOG_COMPLETE')
        self.assertEqual(out['expansion_stopped_at'],'EXTENDED_3_TO_5Y')
        self.assertEqual(p.status(self.ws)['fulltexts_downloaded'],0)

    def test_user_added_obscure_domain_must_have_explicit_macro_and_query(self):
        c=copy.deepcopy(self.c)
        c['inspiration_diversity']['custom_domains']['paleontology']={
            'name_zh':'古生物学','macro_group':'earth_climate','distance_to_mainline_heuristic':'far'}
        c['queries']['inspiration']['paleontology']=['paleontology fossil preservation taphonomy history',
                                                     'mass extinction paleobiology evolutionary deep time']
        p.write(self.ws/'discovery_config.json',c)
        self.assertIn('paleontology',div.load_catalog(p.config(self.ws))['domains'])
        del c['inspiration_diversity']['custom_domains']['paleontology']
        p.write(self.ws/'discovery_config.json',c)
        with self.assertRaises(ValueError):
            p.config(self.ws)

    def test_existing_goal_freeze_and_seeded_selection_repeatability(self):
        s=p.state_at(self.ws,self.c)
        for dom in list(self.c['queries']['inspiration'])[:60]:
            for idx in range(3):
                row=p.work_normalized(fake_work(f'novel_{dom}',idx,cat='inspiration',domain=dom),
                                       'inspiration',dom,'test')
                s['works'][row['id']]=row
        first=p.select(self.ws,self.c,s)['selected']['inspiration']
        second=p.select(self.ws,self.c,s)['selected']['inspiration']
        self.assertEqual([w['id'] for w in first],[w['id'] for w in second])
        self.assertEqual(len(first),50)

if __name__=='__main__':unittest.main()
