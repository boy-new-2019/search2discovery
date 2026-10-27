"""Offline regression tests for transport and source-bound native budget recovery."""
import concurrent.futures,datetime,email.message,io,json,os,pathlib,shutil,sys,tempfile,unittest
import urllib.error
from unittest import mock
WS=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(WS/'paper-discovery-preflight/scripts'))
sys.path.insert(0,str(WS/'research-cognition-engine/scripts'))
import openalex_http as http
import native_v44_launcher
import desktop_bridge as app,quota_guard as quota,deepread as core,batch

def headers(**values):
    m=email.message.Message()
    for k,v in values.items():m[k.replace('_','-')]=str(v)
    return m
class Clock:
    def __init__(self):self.now=1800000000.;self.waits=[]
    def time(self):return self.now
    def sleep(self,t):self.waits.append(t);self.now+=t
class Response(io.BytesIO):
    def __init__(self,obj,h=None):
        super().__init__(json.dumps(obj).encode());self.headers=h or headers()
class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.ws=pathlib.Path(self.tmp.name);self.clock=Clock();self.calls=[]
        self.cfg={'api':{'api_key_env':'S2D_TEST_KEY','per_page':75,'timeout_seconds':5,'retry_429':3,
                         'minimum_request_interval_seconds':.5,'max_requests_total':420,'per_page':75}}
        self.env=mock.patch.dict(os.environ,{'S2D_TEST_KEY':''});self.env.start()
    def tearDown(self):self.env.stop();self.tmp.cleanup()
    def client(self,items):
        queue=list(items)
        def opener(req,timeout):
            self.calls.append(req.full_url)
            if not queue:raise AssertionError('Unexpected extra HTTP request')
            item=queue.pop(0)
            if isinstance(item,Exception):raise item
            return item
        return http.OpenAlex(self.cfg,self.ws,opener=opener,clock=self.clock.time,sleeper=self.clock.sleep,jitter=lambda:0)
    def err(self,body='Too Many Requests',**h):
        return urllib.error.HTTPError('https://api.openalex.org/works',429,'limit',headers(**h),io.BytesIO(body.encode()))
    def query(self,client,q='memory shared state'):return client.query(q,'2023-10-26','2026-10-26',1)
    def ok(self,**h):return Response({'results':[{'id':'https://openalex.org/W123'}],'meta':{'count':1}},headers(**h))
    def test_english_chinese_mixed_cache_keys_and_repeated_query(self):
        c=self.client([self.ok(),self.ok(),self.ok()])
        for q in ('shared state','共享状态校正','SyntheticMemory 共享 state 🚗'):
            first=self.query(c,q);second=self.query(c,q);self.assertEqual(first[0],second[0]);self.assertTrue(second[1]['cache_hit'])
        self.assertEqual(len(self.calls),3)
    def test_daily_header_stops_without_retry_and_survives_restart(self):
        c=self.client([self.err(X_RateLimit_Remaining=0,X_RateLimit_Reset=3600)])
        with self.assertRaises(http.OpenAlexPause) as e:self.query(c)
        self.assertEqual(e.exception.info['kind'],'DAILY_BUDGET_EXHAUSTED')
        c=self.client([])
        with self.assertRaises(http.OpenAlexPause):self.query(c)
        self.assertEqual(len(self.calls),1)
    def test_daily_structured_credit_refusal_even_positive_balance(self):
        c=self.client([self.err('{"error":"not_enough_credits"}',X_RateLimit_Remaining=1)])
        with self.assertRaises(http.OpenAlexPause) as e:self.query(c)
        self.assertEqual(e.exception.info['kind'],'DAILY_BUDGET_EXHAUSTED');self.assertEqual(len(self.calls),1)
    def test_per_second_retry_after_and_exponential_backoff(self):
        c=self.client([self.err('per-second limit',Retry_After=3),self.err('per-second limit'),self.ok()])
        self.query(c);self.assertEqual(len(self.calls),3);self.assertGreaterEqual(sum(self.clock.waits),5)
    def test_unknown_429_is_bounded_not_falsely_daily(self):
        c=self.client([self.err() for _ in range(4)])
        with self.assertRaises(http.OpenAlexPause) as e:self.query(c)
        self.assertEqual(e.exception.info['kind'],'HTTP429_UNCLASSIFIED');self.assertEqual(len(self.calls),4)
    def test_long_retry_after_is_cooldown_not_daily(self):
        c=self.client([self.err(Retry_After=3600)])
        with self.assertRaises(http.OpenAlexPause) as e:self.query(c)
        self.assertEqual(e.exception.info['kind'],'HTTP429_UNCLASSIFIED');self.assertEqual(len(self.calls),1)
        self.assertFalse(self.clock.waits)
    def test_http_date_retry_after(self):
        value=email.utils.format_datetime(datetime.datetime.fromtimestamp(self.clock.now+6,datetime.timezone.utc),usegmt=True)
        c=self.client([self.err('per second',Retry_After=value),self.ok()]);self.query(c)
        self.assertGreaterEqual(sum(self.clock.waits),6)
    def test_success_exhausts_budget_but_cache_remains_usable(self):
        c=self.client([self.ok(X_RateLimit_Remaining=0,X_RateLimit_Reset=1000)])
        self.query(c);self.query(c)
        with self.assertRaises(http.OpenAlexPause):self.query(c,'different query')
        self.assertEqual(len(self.calls),1)
    def test_cache_integrity_refuses_corruption(self):
        c=self.client([self.ok()]);self.query(c)
        p=next((c.root/'cache').glob('*.json'));d=json.loads(p.read_text('utf-8'));d['response']['results']=[];http.write(p,d)
        with self.assertRaisesRegex(ValueError,'integrity'):self.query(c)
    def test_minimum_interval_persists_between_clients(self):
        c=self.client([self.ok()]);self.query(c)
        c=self.client([self.ok()]);self.query(c,'second query')
        self.assertGreaterEqual(sum(self.clock.waits),.5)
    def test_reset_expiry_only_allows_probe_not_invented_restoration(self):
        c=self.client([self.err(X_RateLimit_Remaining=0,X_RateLimit_Reset=100)])
        with self.assertRaises(http.OpenAlexPause):self.query(c)
        self.clock.now+=101;c=self.client([self.err(X_RateLimit_Remaining=0,X_RateLimit_Reset=200)])
        with self.assertRaises(http.OpenAlexPause):self.query(c)
        self.assertEqual(len(self.calls),2)
    def test_secret_redacted_from_error_and_files(self):
        with mock.patch.dict(os.environ,{'S2D_TEST_KEY':'test-super-secret-key'}):
            c=self.client([self.err('daily budget api_key=test-super-secret-key',X_RateLimit_Reset=100)])
            with self.assertRaises(http.OpenAlexPause) as e:self.query(c)
            self.assertNotIn('test-super-secret-key',str(e.exception))
            for p in c.root.rglob('*'):
                if p.is_file():self.assertNotIn('test-super-secret-key',p.read_text('utf-8'))
    def test_network_failure_has_finite_retry(self):
        c=self.client([urllib.error.URLError('offline'),urllib.error.URLError('offline')])
        with self.assertRaises(http.OpenAlexPause) as e:self.query(c)
        self.assertEqual(e.exception.info['kind'],'NETWORK_UNAVAILABLE');self.assertEqual(len(self.calls),2)
    def test_status_endpoint_401_does_not_erase_daily_search_pause(self):
        unauthorized=urllib.error.HTTPError('https://api.openalex.org/rate-limit',401,'key required',headers(),io.BytesIO(b'Authentication required'))
        c=self.client([self.err(X_RateLimit_Remaining=0,X_RateLimit_Reset=3600),unauthorized])
        with self.assertRaises(http.OpenAlexPause):self.query(c)
        with self.assertRaises(http.OpenAlexPause):c.inspect_allowance()
        with self.assertRaises(http.OpenAlexPause) as e:self.query(c)
        self.assertEqual(e.exception.info['kind'],'DAILY_BUDGET_EXHAUSTED');self.assertEqual(len(self.calls),2)
    def test_actual_request_ceiling_includes_retries(self):
        self.cfg['api']['max_requests_total']=1;c=self.client([self.err('per-second limit')])
        with self.assertRaises(http.OpenAlexPause) as e:self.query(c)
        self.assertEqual(e.exception.info['kind'],'LOCAL_PHYSICAL_REQUEST_CEILING');self.assertEqual(len(self.calls),1)

class PromptQuotaTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.ws=pathlib.Path(self.tmp.name)
        self.cfg={**quota.DEFAULT,'max_assignments_per_cycle':4,'max_prompt_chars_per_cycle':10000}
    def tearDown(self):self.tmp.cleanup()
    def prompt(self,text,kind='captain',jid='S2_B1',role='bpd_lead_sol'):
        p=self.ws/'output/native/tasks'/jid/('captain_prompt.md' if kind=='captain' else 'prompts/'+role+'.md')
        p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(text.encode());return f'{jid}:{kind}:{role}',p
    def test_unicode_units_and_duplicate_submission(self):
        for i,text in enumerate(('English prompt','中文提示词','shared共享 state🚗\r\nnext')):
            key,p=self.prompt(text,jid=f'S2_B{i}');quota.reserve_prompt(self.ws,self.cfg,key,p)
            original=quota.path(self.ws).read_bytes();quota.reserve_prompt(self.ws,self.cfg,key,p)
            self.assertEqual(quota.path(self.ws).read_bytes(),original)
            row=quota._load(self.ws)['cycles']['cycle-001']['reservations'][key]
            self.assertEqual(row['prompt_chars'],len(p.read_text('utf-8')))
            self.assertEqual(row['reserved_prompt_chars'],len(p.read_text('utf-8')))
    def test_legacy_utf8_byte_charge_preserved_without_refund(self):
        key,p=self.prompt('中文仲裁 and English')
        old=p.stat().st_size;quota.reserve(self.ws,self.cfg,{key:old})
        quota.reserve_prompt(self.ws,self.cfg,key,p)
        row=quota._load(self.ws)['cycles']['cycle-001']['reservations'][key]
        self.assertEqual(row['reserved_prompt_chars'],old);self.assertEqual(row['historical_reservation']['reserved_prompt_chars'],old)
        self.assertEqual(row['prompt_chars'],len(p.read_text('utf-8')))
    def test_old_base_prompt_underreserve_expands_within_cap(self):
        key,p=self.prompt('English prompt plus wrapper')
        quota.reserve(self.ws,self.cfg,{key:5});quota.reserve_prompt(self.ws,self.cfg,key,p)
        self.assertEqual(quota.status(self.ws,self.cfg)['reserved_prompt_chars'],len(p.read_text('utf-8')))
    def test_tampered_same_length_prompt_refused(self):
        key,p=self.prompt('aaaa');quota.reserve_prompt(self.ws,self.cfg,key,p);p.write_text('bbbb','utf-8')
        with self.assertRaisesRegex(ValueError,'hash'):quota.reserve_prompt(self.ws,self.cfg,key,p)
    def test_reconciliation_over_cap_is_atomic(self):
        key,p=self.prompt('x'*10001);quota.reserve(self.ws,self.cfg,{key:1});old=quota.path(self.ws).read_bytes()
        with self.assertRaises(quota.QuotaExceeded):quota.reserve_prompt(self.ws,self.cfg,key,p)
        self.assertEqual(old,quota.path(self.ws).read_bytes())
    def test_generic_strict_reservation_mismatch_still_fails(self):
        quota.reserve(self.ws,self.cfg,{'A':3})
        with self.assertRaises(ValueError):quota.reserve(self.ws,self.cfg,{'A':4})
    def test_archived_reservation_cannot_expand_silently(self):
        key,p=self.prompt('longer prompt');quota.reserve(self.ws,self.cfg,{key:1})
        quota.renew(self.ws,self.cfg,'cycle-002',user_authorized=True)
        with self.assertRaises(quota.QuotaExceeded):quota.reserve_prompt(self.ws,self.cfg,key,p)
    def test_receipt_bound_prompt_refused_after_edit(self):
        key,p=self.prompt('original',kind='reader')
        receipt=p.parent.parent/'receipts/bpd_lead_sol.json';core.jwrite(receipt,{'prompt_sha256':core.file_hash(p)})
        p.write_text('tampered','utf-8')
        with self.assertRaisesRegex(ValueError,'receipt'):quota.reserve_prompt(self.ws,self.cfg,key,p)
    def test_concurrent_same_prompt_occupies_one_seat(self):
        key,p=self.prompt('并发 concurrent')
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _:quota.reserve_prompt(self.ws,self.cfg,key,p),range(8)))
        self.assertEqual(quota.status(self.ws,self.cfg)['reserved_assignments'],1)

class AdditionalRecoveryTests(unittest.TestCase):
    def test_historical_zero_remaining_prevents_a_new_query(self):
        with tempfile.TemporaryDirectory() as folder:
            root=pathlib.Path(folder);p=root/'sources/openalex_transport/retained.json';p.parent.mkdir(parents=True)
            clock=Clock();observed=datetime.datetime.fromtimestamp(clock.now,datetime.timezone.utc).isoformat()
            p.write_text(json.dumps({'fetched_at':observed,'meta':{'rate_remaining':'0'}}),'utf-8')
            cfg={'api':{'api_key_env':'S2D_TEST_KEY','max_requests_total':420,'per_page':75}}
            with mock.patch.dict(os.environ,{'S2D_TEST_KEY':''}):
                client=http.OpenAlex(cfg,root,clock=clock.time,opener=lambda *a,**k:self.fail('Daily pause must prevent all search requests'))
                with self.assertRaises(http.OpenAlexPause) as e:client.query('memory','2023-01-01','2026-01-01',1)
                self.assertEqual(e.exception.info['kind'],'DAILY_BUDGET_EXHAUSTED')
    def test_reader_budget_includes_separate_base_prompt(self):
        with tempfile.TemporaryDirectory() as folder:
            ws=pathlib.Path(folder);root=ws/'output/native/tasks/S1_B1';prompt=root/'prompts/bpd_topic_luna.md'
            prompt.parent.mkdir(parents=True);prompt.write_text('Read base_prompt.md 中文','utf-8')
            (root/'base_prompt.md').write_text('Long original source 材料','utf-8')
            quota.reserve_prompt(ws,quota.DEFAULT,'S1_B1:reader:bpd_topic_luna',prompt)
            row=quota._load(ws)['cycles']['cycle-001']['reservations']['S1_B1:reader:bpd_topic_luna']
            self.assertEqual(row['prompt_chars'],len(prompt.read_text('utf-8'))+len((root/'base_prompt.md').read_text('utf-8')))
    def test_persisted_daily_cache_still_works_after_restart(self):
        test=HTTPTests();test.setUp()
        try:
            client=test.client([test.ok(X_RateLimit_Remaining=0,X_RateLimit_Reset=3600)])
            test.query(client);client=test.client([]);test.query(client)
            self.assertEqual(len(test.calls),1)
        finally:test.tearDown()

if __name__=='__main__':unittest.main()
