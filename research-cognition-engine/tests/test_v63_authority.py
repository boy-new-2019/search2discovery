import importlib.util
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parents[1] / 'scripts'
if str(HERE) not in sys.path:sys.path.insert(0,str(HERE))
import venue_authority as authority

JCR_TEXT = '<html><h1>Clarivate Releases Journal Citation Reports 2026</h1><p>Clarivate released Journal Citation Reports 2026 on June 17, 2026.</p></html>'
CAS_TEXT = '<html><h1>声 明</h1><p>中国科学院文献情报中心：自2026年起，不再更新与发布期刊分区表。</p></html>'
CCF_TEXT = '<html><h1>第七版《中国计算机学会推荐国际学术会议和期刊目录》正式发布</h1><p>2026年03月31日（目录于4月9日更新，修正勘误）</p></html>'

class AnnualAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.ws=pathlib.Path(self.tmp.name)/'lab';self.ws.mkdir()
        self.calls=[]

    def fetch(self,source,url):
        self.calls.append((source,url))
        return {'JCR':JCR_TEXT,'CAS':CAS_TEXT,'CCF':CCF_TEXT}[source]

    def test_first_run_search_and_calendar_year_reuse(self):
        self.assertTrue(authority.status(self.ws,year=2026)['should_search'])
        a=authority.check(self.ws,online=True,year=2026,fetcher=self.fetch)
        self.assertEqual(a['status'],'ANNUAL_OFFICIAL_CHECK_COMPLETED')
        self.assertFalse(a['cache_reused']); self.assertEqual(a['network_requests'],3)
        self.assertEqual(set(a['official_coverage']),{'JCR','CAS','CCF'})
        b=authority.check(self.ws,online=True,year=2026,fetcher=self.fetch)
        self.assertTrue(b['cache_reused']);self.assertEqual(b['network_requests'],0)
        self.assertEqual(len(self.calls),3)
        self.assertIn('historical 2025 data',pathlib.Path(a['report']).read_text('utf-8'))

    def test_cross_year_new_search_and_historical_jcr_not_new_release(self):
        authority.check(self.ws,online=True,year=2026,fetcher=self.fetch)
        a=authority.check(self.ws,online=True,year=2027,fetcher=self.fetch)
        self.assertEqual(a['status'],'ANNUAL_OFFICIAL_CHECK_COMPLETED')
        self.assertEqual(a['editions']['JCR'],'2026')
        raw=authority.read_json(authority.record_file(self.ws,2027))
        self.assertFalse(raw['sources']['JCR']['edition_is_current_calendar_year'])
        self.assertEqual(raw['sources']['CAS']['edition'],'DISCONTINUED_SINCE_2026')
        self.assertEqual(raw['sources']['CCF']['edition'],'CCF directory edition 7')
        self.assertEqual(raw['sources']['JCR']['specific_journal_quartiles'],'NOT_VERIFIED_REQUIRE_LICENSED_JCR_ACCESS')

    def test_failed_site_does_not_fake_official(self):
        def partial(src,url):
            if src=='JCR':raise OSError('403 forbidden')
            return self.fetch(src,url)
        a=authority.check(self.ws,online=True,year=2026,fetcher=partial)
        self.assertEqual(a['status'],'ANNUAL_OFFICIAL_CHECK_PARTIAL')
        self.assertEqual(a['editions']['JCR'],'UNKNOWN')
        self.assertFalse(a['publication_check_complete'])
        # Same-year calls are skipped even if partial, but status remains honest.
        b=authority.check(self.ws,online=True,year=2026,fetcher=partial)
        self.assertEqual(b['network_requests'],0)
        c=authority.check(self.ws,online=True,year=2026,fetcher=self.fetch,force=True)
        self.assertEqual(c['status'],'ANNUAL_OFFICIAL_CHECK_COMPLETED')
        self.assertEqual(c['editions']['JCR'],'2026')

    def test_no_network_no_yearly_cache(self):
        a=authority.check(self.ws,year=2026,online=False)
        self.assertEqual(a['status'],'ANNUAL_OFFICIAL_CHECK_REQUIRES_NETWORK')
        self.assertFalse(authority.record_file(self.ws,2026).exists())

    def test_reject_non_official_hosts_and_redirect(self):
        self.assertFalse(authority.official_url('JCR','https://jcr.clarivate.com.evil.test/'))
        self.assertFalse(authority.official_url('CCF','http://www.ccf.org.cn/Academic_Evaluation/By_category/'))
        self.assertFalse(authority.official_url('CCF','https://www.ccf.org.cn:123/'))
        with self.assertRaises(ValueError): authority.fetch('CCF','https://fake.ccf.org.cn/rank')
        redirect=authority._OfficialRedirects('JCR')
        with self.assertRaises(ValueError):redirect.redirect_request(None,None,302,'found',{},'https://not-clarivate.org/bad')

    def test_bogus_page_rejected(self):
        self.assertIsNone(authority.assess('JCR',authority.JCR_RELEASE_2026,'Subscribe to our Journal Citation Reports 2026 newsletter by Clarivate',2026))
        self.assertIsNone(authority.assess('CCF',authority.CCF_DIRECTORY,'CCF hypothetical public draft 第七版',2026))
        self.assertIsNone(authority.assess('CAS',authority.CAS_NOTICE,'中科院2026分区表已更新',2026))

    def test_venue_report_uses_unknown_specific_ranks(self):
        annual=authority.check(self.ws,online=True,year=2026,fetcher=self.fetch)
        self.assertFalse(annual['specific_journal_rankings_verified'])
        raw=authority.read_json(authority.record_file(self.ws,2026))
        self.assertNotIn('Q1',str(raw['sources']['JCR']))
        self.assertIn('publication status only', raw['sources']['JCR']['data_scope'])

    def test_force_refresh_maintains_historical_year_file(self):
        authority.check(self.ws,online=True,year=2026,fetcher=self.fetch)
        old=authority.record_file(self.ws,2026).read_bytes()
        authority.check(self.ws,online=True,year=2027,fetcher=self.fetch)
        self.assertEqual(old,authority.record_file(self.ws,2026).read_bytes())


class EntrypointAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.ws=pathlib.Path(self.tmp.name)/'project';self.ws.mkdir()

    def test_topic_start_automatically_attempts_annual_check(self):
        import topic_to_plan
        marker=self.ws/'.agents'/'skills'/'research-cognition-engine'/'SKILL.md'
        marker.parent.mkdir(parents=True);marker.write_text('installed',encoding='utf-8')
        with mock.patch.object(topic_to_plan.official_venues, 'check', return_value={'status':'ANNUAL_OFFICIAL_CHECK_PARTIAL'}) as checker:
            from contextlib import redirect_stdout
            import io
            with redirect_stdout(io.StringIO()):
                status=topic_to_plan.main(['start','--workspace',str(self.ws),'--topic','General partially observable task-state revision'])
            self.assertEqual(status,0)
            checker.assert_called_once_with(self.ws.resolve(),online=True)

    def test_unified_init_attempts_annual_check(self):
        import suite
        with mock.patch.object(suite.official_venues,'check',return_value={'status':'ANNUAL_OFFICIAL_CHECK_COMPLETED'}) as checker:
            import io
            from contextlib import redirect_stdout
            with redirect_stdout(io.StringIO()):
                code=suite.main(['init','--workspace',str(self.ws)])
            self.assertEqual(code,2)  # Uninstalled project, no false success.
            checker.assert_called_once_with(self.ws.resolve(),online=True)

if __name__=='__main__':unittest.main()
