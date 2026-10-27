"""Offline regressions. Fixtures are synthetic and never enter the research library."""
import contextlib,copy,io,json,pathlib,sqlite3,sys,tempfile,unittest,urllib.error
WS=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(WS/'paper-discovery-preflight/scripts'))
from literature_sources.common import DEFAULTS,read,write,sha
from literature_sources.transport import HTTP,SourcePause,allowed,Redirect,public_host
from literature_sources.adapters import Arxiv,CVF,PMLR,OpenReview,Crossref,HTML,record,oa,from_legacy,query_phrases,title_query_match
from literature_sources.catalog import Catalog,matches
from literature_sources.coordinator import Coordinator,configure
from literature_sources.downloader import inspect_pdf,obtain
TASK={'id':'fixture-task','query':'world model','category':'core','domain':'','band':'RECENT_3Y','start':'2023-10-26','end':'2026-10-26'}
TITLE='A World Model for Autonomous Driving Memory'
class FakeHTTP:
    def __init__(self,data):self.data=data;self.urls=[]
    def get(self,url,**kw):
        self.urls.append(url)
        for part,payload in self.data:
            if part in url:return payload.encode() if isinstance(payload,str) else payload,{'url':url,'final_url':url,'sha256':'fixture','fetched_at':'2026-10-26'}
        raise AssertionError('Unexpected fixture URL '+url)
class Response:
    def __init__(self,raw,url):self.raw=raw;self.url=url;self.headers={'Content-Type':'application/json'}
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def geturl(self):return self.url
    def read(self,n):return self.raw[:n]
class Base(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.ws=pathlib.Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def workspace(self):
        (self.ws/'goal.md').write_text('Investigate learning and memory mechanisms using authentic evidence.',encoding='utf8')
        write(self.ws/'discovery_config.json',read(WS/'paper-discovery-preflight/discovery_config.example.json'))
        write(self.ws/'output/discovery_preflight/state.json',{'queries_done':{},'selection':{}})
        configure(self.ws)
    def transport(self,source='cvf',sequence=None):
        clock=[10000.];calls=[];seq=list(sequence or [b'{}'])
        def sleep(t):clock[0]+=t
        def opening(req,timeout):
            calls.append((req.full_url,clock[0]));result=seq.pop(0)
            if isinstance(result,Exception):raise result
            return Response(result,req.full_url)
        policy=copy.deepcopy(DEFAULTS['providers'][source])
        h=HTTP(self.ws,source,policy,online=True,opener=opening,clock=lambda:clock[0],sleeper=sleep,dns_check=lambda u:True)
        return h,calls,clock
    def error(self,code=429,body=b'limited',headers=None):
        return urllib.error.HTTPError('https://openaccess.thecvf.com/test',code,'fixture',headers or {},io.BytesIO(body))
class TransportTests(Base):
    def test_dns_failure_is_source_local_typed_pause(self):
        from unittest.mock import patch
        import socket
        with patch('literature_sources.transport.socket.getaddrinfo',side_effect=socket.gaierror(11001,'fixture')):
            self.assertFalse(public_host('https://arxiv.org/pdf/2501.12345'))
            h,c,t=self.transport('arxiv');h.check=public_host
            with self.assertRaises(SourcePause) as err:h.get('https://arxiv.org/pdf/2501.12345')
            self.assertEqual(err.exception.info['kind'],'PUBLIC_DNS_CHECK_FAILED')
            self.assertFalse(c)
    def test_each_source_has_separate_cache(self):
        for s,host in [('arxiv','arxiv.org'),('cvf','openaccess.thecvf.com'),('pmlr','proceedings.mlr.press'),('openreview','openreview.net'),('crossref','api.crossref.org')]:
            h,c,t=self.transport(s);u='https://'+host+'/fixture';h.get(u)
            self.assertEqual(h.get(u)[0],b'{}');self.assertEqual(len(c),1)
            offline=HTTP(self.ws,s,h.policy,online=False);self.assertEqual(offline.get(u)[0],b'{}')
    def test_short_rate_zero_is_not_daily(self):
        h,c,t=self.transport(sequence=[self.error(headers={'x-ratelimit-remaining':'0','x-ratelimit-reset':'1'}),b'{}'])
        h.get('https://openaccess.thecvf.com/fixture');self.assertEqual(len(c),2);self.assertIsNone(h.state()['pause'])
    def test_daily_stops_and_persists(self):
        h,c,t=self.transport(sequence=[self.error(body=b'daily quota exhausted',headers={'x-ratelimit-reset':'86400'})])
        for _ in range(2):
            with self.assertRaises(SourcePause) as e:h.get('https://openaccess.thecvf.com/fixture')
            self.assertEqual(e.exception.info['kind'],'DAILY_BUDGET_EXHAUSTED')
        self.assertEqual(len(c),1)
    def test_daily_one_source_does_not_pause_another(self):
        h,c,t=self.transport(sequence=[self.error(body=b'daily quota')])
        with self.assertRaises(SourcePause):h.get('https://openaccess.thecvf.com/f')
        other,oc,ot=self.transport('pmlr');other.get('https://proceedings.mlr.press/f')
        self.assertEqual(len(oc),1)
    def test_auth_not_retried(self):
        h,c,t=self.transport(sequence=[self.error(401)])
        with self.assertRaises(SourcePause) as e:h.get('https://openaccess.thecvf.com/f')
        self.assertEqual(e.exception.info['kind'],'AUTHORIZATION_REQUIRED');self.assertEqual(len(c),1)
    def test_finite_unknown429(self):
        h,c,t=self.transport(sequence=[self.error(),self.error()])
        with self.assertRaises(SourcePause) as e:h.get('https://openaccess.thecvf.com/f')
        self.assertEqual(e.exception.info['kind'],'HTTP429_UNCLASSIFIED');self.assertEqual(len(c),2)
    def test_long_retry_after_no_sleep_loop(self):
        h,c,t=self.transport(sequence=[self.error(headers={'retry-after':'3600'})])
        with self.assertRaises(SourcePause):h.get('https://openaccess.thecvf.com/f')
        self.assertEqual(len(c),1);self.assertEqual(t[0],10000)
    def test_http_date_retry(self):
        import email.utils
        h,c,t=self.transport(sequence=[self.error(headers={'retry-after':email.utils.formatdate(10004,usegmt=True)}),b'{}'])
        h.get('https://openaccess.thecvf.com/f');self.assertGreaterEqual(c[1][1]-c[0][1],4)
    def test_arxiv_spacing_is_durable(self):
        h,c,t=self.transport('arxiv',[b'one',b'two'])
        h.get('https://arxiv.org/one');h.get('https://arxiv.org/two')
        self.assertGreaterEqual(c[1][1]-c[0][1],3)
    def test_global_request_bound(self):
        h,c,t=self.transport();h.budget={'sent':1,'limit':1}
        with self.assertRaises(SourcePause) as e:h.get('https://openaccess.thecvf.com/f')
        self.assertEqual(e.exception.info['kind'],'GLOBAL_RUN_BOUND');self.assertFalse(c)
    def test_cache_corruption_fails_closed(self):
        h,c,t=self.transport();url='https://openaccess.thecvf.com/f';_,meta=h.get(url)
        (h.root/'blobs'/meta['sha256']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'integrity'):h.get(url)
    def test_pdf_bound_on_cache(self):
        h,c,t=self.transport(sequence=[b'123456']);url='https://openaccess.thecvf.com/f';h.get(url)
        with self.assertRaises(SourcePause):h.get(url,max_bytes=3)
    def test_nonpublic_or_foreign_url_refused(self):
        self.assertFalse(allowed('cvf','http://openaccess.thecvf.com/x'))
        self.assertFalse(allowed('cvf','https://example.org/x'))
        h,c,t=self.transport();h.check=lambda u:False
        with self.assertRaises(SourcePause):h.get('https://openaccess.thecvf.com/x')
        self.assertFalse(c)
    def test_redirect_does_not_leave_official_host(self):
        import urllib.request
        handler=Redirect('cvf',lambda u:True)
        with self.assertRaises(ValueError):handler.redirect_request(urllib.request.Request('https://openaccess.thecvf.com/a'),None,302,'',{},'https://example.org/p.pdf')
class ParserTests(Base):
    def test_inspiration_search_omits_generic_tail_phrases(self):
        query='bounded rationality Herbert Simon decision costs original research'
        self.assertEqual(query_phrases(query,disciplinary=True),['bounded rationality'])
        self.assertFalse(title_query_match('Original Research on Particle Physics',query,disciplinary=True))
        self.assertTrue(title_query_match('Bounded Rationality in Economics',query,disciplinary=True))
    def test_long_reviewed_query_is_broad_retrieval_not_exact_title_conjunction(self):
        query='recurrent world model shared latent state prediction planning autonomous driving'
        self.assertTrue(title_query_match('DriveWorld: World Model for Autonomous Driving',query))
        self.assertTrue(title_query_match('Latent State Correction from Historical Evidence',query))
        self.assertFalse(title_query_match('Ocean salinity measurements',query))
        self.assertIn('world model',query_phrases(query))
        h=FakeHTTP([('api/query','<feed xmlns="http://www.w3.org/2005/Atom"/>')])
        Arxiv(h,DEFAULTS).search({**TASK,'query':query},None)
        import urllib.parse
        compiled=urllib.parse.parse_qs(urllib.parse.urlsplit(h.urls[0]).query)['search_query'][0]
        self.assertIn(' OR ',compiled)
        self.assertIn('all:"world model"',compiled)
    def test_arxiv_version_doi_and_date(self):
        xml="""<feed xmlns="http://www.w3.org/2005/Atom" xmlns:x="http://arxiv.org/schemas/atom"><entry><id>http://arxiv.org/abs/2501.12345v2</id><title>A World Model</title><published>2025-01-12T00:00:00Z</published><author><name>Alice Li</name></author><x:doi>10.1234/abc</x:doi><link title="pdf" href="http://arxiv.org/pdf/2501.12345v2"/></entry></feed>"""
        rows,c=Arxiv(FakeHTTP([('api/query',xml)]),DEFAULTS).search(TASK,None)
        self.assertEqual(rows[0]['arxiv_id'],'2501.12345');self.assertEqual(rows[0]['arxiv_version'],2)
        self.assertEqual(rows[0]['publication_date'],'2025-01-12');self.assertTrue(rows[0]['fulltexts'][0]['url'].startswith('https:'))
    def detail(self,source):
        pdf='https://openaccess.thecvf.com/p.pdf' if source=='cvf' else 'https://proceedings.mlr.press/v306/a/a.pdf'
        return '<meta name="citation_title" content="'+TITLE+'"><meta name="citation_author" content="Alice Li"><meta name="citation_date" content="2026"><meta name="citation_pdf_url" content="'+pdf+'"><div id="abstract">True metadata.</div><a href="https://arxiv.org/abs/2501.12345">arxiv</a>'
    def test_cvf_index_detail_cursor(self):
        url='https://openaccess.thecvf.com/content/CVPR2026/html/A_paper.html'
        h=FakeHTTP([('A_paper.html',self.detail('cvf')),('CVPR2026?','<a href="'+url+'">'+TITLE+'</a>')])
        a=CVF(h,DEFAULTS);rows,c=a.search(TASK,None)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['year'],2026)
        self.assertEqual(rows[0]['publication_status'],'PUBLISHED_PROCEEDINGS');self.assertEqual(json.loads(c)['paper'],1)
    def test_workshop_not_main(self):
        row=HTML(self.detail('cvf'),'https://openaccess.thecvf.com/content/CVPR2026W/x_paper.html').paper_record('cvf','https://openaccess.thecvf.com/content/CVPR2026W/x_paper.html')
        self.assertEqual(row['publication_status'],'PUBLISHED_WORKSHOP')
    def test_pmlr_index_volume_detail(self):
        root='<li><a href="/v337/">Volume 337</a> UAI 2026</li><li><a href="/v306/">Volume 306</a> ICML 2026</li>'
        volume='<div class="paper"><p class="title">'+TITLE+'</p><p><a href="a.html">abs</a></p></div>'
        h=FakeHTTP([('a.html',self.detail('pmlr')),('/v306/',volume),('https://proceedings.mlr.press/',root)])
        rows,c=PMLR(h,DEFAULTS).search(TASK,None)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['source'],'pmlr')
        self.assertEqual(json.loads(c)['units'],['https://proceedings.mlr.press/v306/'])
    def test_openreview_v2_no_acceptance_invention(self):
        note={'id':'abc','cdate':1750000000000,'content':{'title':{'value':TITLE},'pdf':{'value':'/pdf?id=abc'},'authors':{'value':['Alice Li']},'venue':{'value':'Submitted to ICLR'}}}
        rows,c=OpenReview(FakeHTTP([('notes/search',json.dumps({'notes':[note],'count':1}))]),DEFAULTS).search(TASK,None)
        self.assertEqual(rows[0]['publication_status'],'PUBLIC_SUBMISSION_ACCEPTANCE_UNVERIFIED')
    def test_openreview_rejection_explicit(self):
        n={'id':'x','cdate':1750000000000,'content':{'title':TITLE,'pdf':'/pdf?id=x','venue':'Rejected from ICLR'}}
        rows,_=OpenReview(FakeHTTP([('notes/search',json.dumps({'notes':[n]}))]),DEFAULTS).search(TASK,None)
        self.assertIn('REJECTED',rows[0]['publication_status'])
    def test_crossref_retains_genuine_jats_abstract_for_later_screening(self):
        data={'message':{'items':[{'DOI':'10.1234/abstract','type':'journal-article','title':[TITLE],
             'published':{'date-parts':[[2025,1,1]]},'abstract':'<jats:p>Historical evidence informs <jats:italic>state correction</jats:italic>.</jats:p>'}]}}
        rows,_=Crossref(FakeHTTP([('/works?',json.dumps(data))]),DEFAULTS).search(TASK,None)
        self.assertEqual(rows[0]['abstract'],'Historical evidence informs state correction .')
        self.assertEqual(rows[0]['source_response']['sha256'],'fixture')
    def test_crossref_exact_doi_and_unlicensed_link(self):
        data={'message':{'DOI':'10.1234/abc','type':'journal-article','title':[TITLE],'published':{'date-parts':[[2025]]},'link':[{'URL':'https://publisher.example/p.pdf','content-type':'application/pdf'}]}}
        h=FakeHTTP([('/works/',json.dumps(data))]);rows,_=Crossref(h,DEFAULTS).search({**TASK,'doi':'10.1234/abc'},None)
        self.assertEqual(rows[0]['fulltexts'],[]);self.assertIsNone(rows[0]['publication_date'])
        with self.assertRaisesRegex(ValueError,'DOI verification'):Crossref(h,DEFAULTS).search({**TASK,'doi':'10.1234/wrong'},None)
    def test_crossref_books_do_not_pad_paper_quotas(self):
        data={'message':{'items':[{'DOI':'10.1234/book','title':[TITLE],'type':'book-chapter','published':{'date-parts':[[2025,1,1]]}}]}}
        rows,cursor=Crossref(FakeHTTP([('/works?',json.dumps(data))]),DEFAULTS).search(TASK,None)
        self.assertEqual(rows,[])
class CatalogTests(Base):
    def test_record_payload_basename_is_bounded_and_identity_bound(self):
        self.workspace();c=Catalog(self.ws)
        first=record('cvf','first',TITLE,year=2025)
        second=record('cvf','second',TITLE+' variant',year=2025)
        c.add(first);c.add(second)
        paths=list((c.root/'records').glob('*.json'))
        self.assertEqual(len(paths),2)
        self.assertTrue(all(len(p.name)==69 for p in paths))
        self.assertEqual({read(p)['record_id'] for p in paths},{'cvf:first','cvf:second'})
    def rec(self,source='arxiv',key='one',**kw):
        return record(source,key,TITLE,authors=['Alice Li'],year=2025,publication_date='2025-01-01',**kw)
    def test_doi_preprint_and_conference_count_once(self):
        c=Catalog(self.ws);c.add(self.rec(doi='10.1234/x',publication_status='PREPRINT'),TASK)
        c.add(self.rec('cvf','two',doi='https://doi.org/10.1234/x',publication_status='PUBLISHED_PROCEEDINGS'),TASK)
        self.assertEqual(len(c.active()),1);self.assertEqual(len(c.data['records']),2)
        self.assertEqual(c.data['relations'][0]['kind'],'PREPRINT_AND_PROCEEDINGS')
    def test_arxiv_versions_retained(self):
        c=Catalog(self.ws)
        c.add(self.rec(arxiv_id='2501.12345',arxiv_version=1));c.add(self.rec(key='v2',arxiv_id='2501.12345',arxiv_version=2))
        self.assertEqual(len(c.active()),1);self.assertEqual(len(c.data['records']),2)
    def test_title_author_merge_and_conflicting_author_separate(self):
        c=Catalog(self.ws);c.add(self.rec());other=self.rec('cvf','two');c.add(other)
        self.assertEqual(len(c.active()),1)
        other=self.rec('pmlr','three');other['authors']=['Bob Smith'];c.add(other)
        self.assertEqual(len(c.active()),2)
    def test_repeat_and_restart_preserve_payload(self):
        c=Catalog(self.ws);r=self.rec();c.add(r);c.save();before=c.path.read_bytes()
        c=Catalog(self.ws);c.add(r);c.save();self.assertEqual(before,c.path.read_bytes())
    def test_cross_category_conflict_not_double_counted(self):
        c=Catalog(self.ws);r=self.rec(doi='10.1234/x');c.add(r,legacy_category='core')
        c.add(self.rec('cvf','x',doi='10.1234/x'),legacy_category='related')
        counts,conflicts=c.counts();self.assertEqual(sum(counts.values()),1);self.assertTrue(conflicts)
    def test_db_additive_only(self):
        db=self.ws/'output/research_cognition/research_memory.sqlite3';db.parent.mkdir(parents=True)
        with contextlib.closing(sqlite3.connect(db)) as con, con:
            con.execute('CREATE TABLE works(work_id TEXT PRIMARY KEY,title TEXT,category TEXT,doi TEXT,year INT,venue TEXT,url TEXT,record_sha TEXT)')
            con.execute("INSERT INTO works VALUES('old','Protected evidence','core','',2025,'','','abc')")
            con.execute('CREATE TABLE claims(claim TEXT)');con.execute("INSERT INTO claims VALUES('untouched')")
        c=Catalog(self.ws);c.add(self.rec());result=c.sync_memory()
        self.assertEqual(result['new_works'],1);self.assertEqual(c.sync_memory()['new_works'],0)
        with contextlib.closing(sqlite3.connect(db)) as con, con:
            self.assertEqual(con.execute("SELECT title,category FROM works WHERE work_id='old'").fetchone(),('Protected evidence','core'))
            self.assertEqual(con.execute('SELECT * FROM claims').fetchall(),[('untouched',)])
class CoordinatorTests(Base):
    def test_openalex_bounded_none_cursor_does_not_attest_exhaustion(self):
        self.workspace();c=Coordinator(self.ws)
        semantic={k:TASK[k] for k in ('query','category','domain','band','start','end')}
        task=c.add_task(semantic,'openalex',0)
        task.update(status='DONE',pages_completed=1,last_step_at='2026-10-26T01:00:00Z')
        c.record_query_pass(task,None,None,20,20,0)
        receipt=read(pathlib.Path(task['query_pass_receipts'][0]['path']))
        self.assertIsNone(receipt['retrieval_exhaustive'])
        self.assertTrue(receipt['exhaustion_not_attested_by_bounded_adapter'])
        self.assertTrue(c.query_coverage_completed(task))
        coverage=c.status()['reviewed_query_coverage']
        proof=next(x for x in coverage['task_evidence'] if x['task_id']==task['id'])
        self.assertIsNone(proof['pagination_exhausted'])
        self.assertEqual(coverage['bounded_openalex_passes_without_exhaustion_attestation'],1)
    def test_crossref_missing_registry_doi_does_not_pause_healthy_query_source(self):
        self.workspace();seen=[]
        class A:
            def __init__(self,http,cfg):pass
            def search(self,task,cursor):
                seen.append(task.get('doi') or task['query'])
                if task.get('doi'):raise SourcePause('crossref','NOT_FOUND',status=404,url='https://api.crossref.org/works/10.1234/missing')
                return [],None
        c=Coordinator(self.ws,online=True,adapter_classes={name:A for name in DEFAULTS['providers']})
        c.cfg['routes']={'ai':['crossref'],'cross_disciplinary':['crossref']};c.plan()
        semantic={k:TASK[k] for k in ('query','category','domain','band','start','end')}
        missing=c.add_task({**semantic,'doi':'10.1234/missing'},'crossref',-1000)
        result=c.run(max_steps=2)
        self.assertEqual(missing['status'],'RESOURCE_NOT_FOUND');self.assertEqual(missing['last_error']['status'],404)
        self.assertFalse(c.query_coverage_completed(missing));self.assertEqual(len(seen),2)
        self.assertEqual([x['status'] for x in result['source_events']],['TASK_RESOURCE_NOT_FOUND','PAGE_COMMITTED'])
        c.run(max_steps=1);self.assertEqual(seen.count('10.1234/missing'),1)
    def test_existing_crossref_doi_404_checkpoint_is_terminalized_without_retry(self):
        self.workspace();c=Coordinator(self.ws)
        semantic={k:TASK[k] for k in ('query','category','domain','band','start','end')}
        task=c.add_task({**semantic,'doi':'10.1234/missing'},'crossref',-1000)
        error={'source':'crossref','kind':'NOT_FOUND','status':404,'url':'https://api.crossref.org/works/10.1234/missing'}
        task.update(status='PAUSED',last_error=error);c.plan()
        self.assertEqual(task['status'],'RESOURCE_NOT_FOUND');self.assertEqual(task['last_error'],error)
        self.assertFalse(c.query_coverage_completed(task))
    def test_bounded_api_query_pass_covers_semantic_without_exhausting_cursor(self):
        self.workspace()
        class A:
            def __init__(self,http,cfg):pass
            def search(self,task,cursor):return [],'20'
        c=Coordinator(self.ws,online=True,adapter_classes={name:A for name in DEFAULTS['providers']})
        c.plan();result=c.run(max_steps=1)
        passed=next(t for t in c.state['tasks'].values() if t.get('query_pass_receipts'))
        self.assertEqual(passed['status'],'PENDING');self.assertEqual(passed['cursor'],'20')
        semantic=(passed['category'],passed['domain'],passed['query'])
        self.assertIn(semantic,c.completed_semantics())
        self.assertNotIn(list(semantic),result['summary']['reviewed_queries_pending'])
        self.assertGreater(result['summary']['reviewed_query_coverage']['non_exhaustive_api_passes'],0)
        self.assertFalse(result['summary']['reviewed_query_coverage']['exhaustive_corpus_search_claimed'])
    def test_query_pass_requires_receipt_and_excludes_doi_superseded_and_old_broad(self):
        self.workspace();c=Coordinator(self.ws)
        semantic={k:TASK[k] for k in ('query','category','domain','band','start','end')}
        task=c.add_task(semantic,'crossref',0)
        task.update(status='PENDING',pages_completed=1,cursor='20',last_step_at='2026-10-26T01:00:00Z')
        self.assertFalse(c.query_coverage_completed(task))
        c.record_query_pass(task,None,'20',0,0,0);self.assertTrue(c.query_coverage_completed(task))
        proof_path=pathlib.Path(task['query_pass_receipts'][0]['path']);proof_path.write_text('{}',encoding='utf-8')
        self.assertFalse(c.query_coverage_completed(task))
        c.record_query_pass(task,None,'20',0,0,0)
        for field,value in [('doi','10.1234/verification'),('superseded_by','new-task')]:
            task[field]=value;self.assertFalse(c.query_coverage_completed(task));task.pop(field)
        task.update(category='inspiration',retrieval_profile='ADJACENT_PHRASE_BROAD_V1')
        c.record_query_pass(task,None,'20',0,0,0);self.assertFalse(c.query_coverage_completed(task))
    def test_repository_index_scope_still_requires_completion(self):
        self.workspace();c=Coordinator(self.ws)
        semantic={k:TASK[k] for k in ('query','category','domain','band','start','end')}
        for source in ('cvf','pmlr'):
            task=c.add_task(semantic,source,0)
            task.update(status='PENDING',pages_completed=1,cursor='next-index',last_step_at='2026-10-26T01:00:00Z')
            c.record_query_pass(task,None,'next-index',0,0,0)
            self.assertFalse(c.query_coverage_completed(task))
            task.update(status='DONE',cursor=None);self.assertTrue(c.query_coverage_completed(task))
    def test_existing_immutable_committed_run_authenticates_page_on_restart(self):
        self.workspace();c=Coordinator(self.ws)
        semantic={k:TASK[k] for k in ('query','category','domain','band','start','end')}
        task=c.add_task(semantic,'crossref',0);task.update(status='PENDING',pages_completed=1,cursor='20');c.save()
        write(c.root/'runs/run_fixture.json',{'status':'MULTISOURCE_CHECKPOINT_SAVED',
              'source_events':[{'status':'PAGE_COMMITTED','source':'crossref','task_id':task['id']}]})
        restarted=Coordinator(self.ws)
        self.assertTrue(restarted.query_coverage_completed(restarted.state['tasks'][task['id']]))
    def test_met_mainline_quotas_prioritize_real_preferred_domain_gap(self):
        self.workspace();seen=[]
        class A:
            def __init__(self,http,cfg):pass
            def search(self,task,cursor):seen.append(task);return [],None
        c=Coordinator(self.ws,online=True,adapter_classes={name:A for name in DEFAULTS['providers']})
        c.dc['quotas'].update(core=1,related=1);c.dc['preferred_domains']={'philosophy':1}
        c.catalog.add(record('legacy','core','Immutable core source fixture',year=2025),legacy_category='core')
        c.catalog.add(record('legacy','related','Immutable related source fixture',year=2025),legacy_category='related');c.save()
        c.run(max_steps=1)
        self.assertEqual((seen[0]['category'],seen[0]['domain']),('inspiration','philosophy'))
    def test_scheduler_prioritizes_original_semantics_not_completed_elsewhere(self):
        self.workspace();seen=[]
        class A:
            def __init__(self,http,cfg):pass
            def search(self,task,cursor):seen.append(task['query']);return [],None
        c=Coordinator(self.ws,online=True,adapter_classes={name:A for name in DEFAULTS['providers']});c.plan()
        first=min((t for t in c.state['tasks'].values() if t['source']=='arxiv'),key=lambda t:t['priority'])
        other=next(t for t in c.state['tasks'].values() if t['source']=='openalex' and t['query']==first['query'])
        other.update(status='DONE',pages_completed=1,last_step_at='2026-10-26T01:00:00Z')
        c.record_query_pass(other,None,None,0,0,0);c.save()
        result=c.run(max_steps=1)
        self.assertNotEqual(seen[0],first['query'])
        self.assertTrue(result['summary']['reviewed_queries_pending'])
    def test_inspiration_requires_original_disciplinary_anchor_not_tail_or_doi(self):
        self.workspace();c=Coordinator(self.ws)
        semantic={**{k:TASK[k] for k in ('query','category','domain','band','start','end')},
                  'category':'inspiration','domain':'nobel_economics',
                  'query':'bounded rationality Herbert Simon decision costs original research'}
        task=c.add_task(semantic,'arxiv',0)
        self.assertEqual(task['retrieval_profile'],'DISCIPLINARY_ANCHOR_V1')
        good=record('arxiv','good','Bounded Rationality and Economic Decisions',year=2025,publication_date='2025-01-01')
        bad=record('arxiv','tail','MoEDAL MAPP: Original Research on Particle Physics',year=2025,publication_date='2025-01-01')
        goodfid,_=c.catalog.add(good,task);badfid,_=c.catalog.add(bad,task)
        verify=c.add_task({**semantic,'query':'Bounded Rationality Verification Only','doi':'10.1234/verify'},'crossref',-1000)
        doi=record('crossref','verify','Bounded Rationality Verification Only',year=2025,publication_date='2025-01-01',publication_status='DOI_REGISTERED_JOURNAL-ARTICLE')
        doifid,_=c.catalog.add(doi,verify);c.classify()
        self.assertEqual(c.catalog.data['families'][goodfid]['assigned_inspiration_domain'],'nobel_economics')
        self.assertNotIn('assigned_inspiration_domain',c.catalog.data['families'][badfid])
        self.assertNotIn('assigned_inspiration_domain',c.catalog.data['families'][doifid])
    def test_quota_aware_rank_allocation_keeps_core_related_disjoint(self):
        self.workspace();c=Coordinator(self.ws)
        c.dc.update(topic_generic_research_mode=True,core_keywords=['world models'],related_keywords=['latent states'])
        c.dc['quotas'].update(core=1,related=1)
        for name,year in [('Older',2024),('Newer',2025),('Third',2023)]:
            row=record('arxiv',name,name+' World Models and Latent States',year=year,publication_date=str(year)+'-06-01')
            c.catalog.add(row,TASK)
        c.classify();counts,_=c.catalog.counts()
        self.assertEqual((counts['core'],counts['related']),(1,1))
        core=[r for r in c.catalog.active().values() if r.get('screened_candidate_category')=='core'][0]
        self.assertIn('Newer',c.catalog.data['records'][core['record_ids'][0]]['title'])
        c.classify();self.assertEqual(c.catalog.counts()[0],counts)
    def test_generic_keyword_requires_all_reviewed_stems_without_adjacency(self):
        import paper_discovery as discovery
        cfg=read(WS/'paper-discovery-preflight/discovery_config.example.json')
        cfg.update(topic_generic_research_mode=True,core_keywords=['autonomous driving planning','recurrent world models'])
        positive={'title':'Planning for autonomous driving using recurrent world-models','abstract':'','category_sources':['core'],'inspiration_domains':[]}
        result=discovery.paper_scores(positive,cfg)
        self.assertEqual(result['core'],6.6);self.assertTrue(result['core_eligible'])
        self.assertFalse(discovery.paper_scores({**positive,'title':'Autonomous driving and world images'},cfg)['core_eligible'])
        self.assertFalse(discovery.metadata_phrase_match('recurrent world models','A world model with no recurrence label'))
        cfg['topic_generic_research_mode']=False
        self.assertEqual(discovery.paper_scores(positive,cfg)['core'],0)
    def test_richer_same_work_manifestation_supplies_metadata_scoring_abstract(self):
        self.workspace();cfg=read(self.ws/'discovery_config.json')
        cfg['topic_generic_research_mode']=True
        cfg['core_keywords']=['shared latent state','latent state correction','historical evidence']
        write(self.ws/'discovery_config.json',cfg);c=Coordinator(self.ws)
        title='Unified driving simulator architecture'
        a=record('crossref','10.1234/same',title,doi='10.1234/same',year=2025,
                 publication_status='DOI_REGISTERED_JOURNAL-ARTICLE')
        b=record('arxiv','2501.00001',title,doi='10.1234/same',year=2025,
                 abstract='Shared latent state uses latent state correction and historical evidence.')
        fid,_=c.catalog.add(a,TASK);c.catalog.add(b,TASK);c.classify()
        self.assertEqual(c.catalog.data['families'][fid]['screened_candidate_category'],'core')
        self.assertEqual(c.catalog.data['records'][a['record_id']]['abstract'],'')
    def test_retrieval_profile_change_preserves_old_cursor_additively(self):
        self.workspace();c=Coordinator(self.ws);c.seed()
        semantic={k:TASK[k] for k in ('query','category','domain','band','start','end')}
        legacy={**semantic,'source':'arxiv'}
        from literature_sources.common import stable
        tid=stable(legacy)[:24]
        c.state['tasks'][tid]={**legacy,'id':tid,'cursor':'40','status':'PENDING','pages_completed':2,'priority':0}
        fresh=c.add_task(semantic,'arxiv',0)
        self.assertNotEqual(fresh['id'],tid)
        self.assertEqual(c.state['tasks'][tid]['cursor'],'40')
        self.assertEqual(c.state['tasks'][tid]['superseded_by'],fresh['id'])
        self.assertIsNone(fresh['cursor'])
    def test_fresh_reviewed_query_precedes_deeper_pagination(self):
        self.workspace();seen=[]
        class A:
            def __init__(self,http,cfg):pass
            def search(self,task,cursor):seen.append(task['query']);return [],'20'
        classes={name:A for name in DEFAULTS['providers']}
        c=Coordinator(self.ws,online=True,adapter_classes=classes);c.plan()
        tasks=[t for t in c.state['tasks'].values() if t['source']=='arxiv']
        first=min(tasks,key=lambda t:(t['priority'],t['id']))
        first['pages_completed']=1;first['cursor']='20';c.save()
        c.run(max_steps=1)
        self.assertNotEqual(seen[0],first['query'])
    def test_configure_is_additive_and_idempotent(self):
        self.workspace();before=(self.ws/'source_routing.json').read_bytes()
        self.assertEqual(configure(self.ws)['status'],'ALREADY_CONFIGURED')
        self.assertEqual(before,(self.ws/'source_routing.json').read_bytes())
    def test_routing_by_discipline(self):
        self.workspace();c=Coordinator(self.ws)
        self.assertEqual(c.route(TASK)[0],'arxiv')
        self.assertEqual(c.route({'query':c.dc['main_direction'],'category':'core'})[0],'arxiv')
        self.assertEqual(c.route({**TASK,'category':'inspiration'})[0],'crossref')
    def test_resume_query_does_not_reset(self):
        self.workspace();c=Coordinator(self.ws);c.plan();tid=next(iter(c.state['tasks']))
        c.state['tasks'][tid].update(status='DONE',cursor='kept',pages_completed=3);c.save()
        c=Coordinator(self.ws);c.plan();self.assertEqual(c.state['tasks'][tid]['pages_completed'],3)
        self.assertEqual(c.state['tasks'][tid]['status'],'DONE')
    def test_failover_does_not_stop_healthy_source(self):
        self.workspace();classes={}
        for name in DEFAULTS['providers']:
            def factory(name):
                class A:
                    def __init__(self,http,cfg):pass
                    def search(self,task,cursor):
                        if name in ('arxiv','openreview','openalex'):raise SourcePause(name,'AUTHORIZATION_REQUIRED' if name=='openreview' else 'DAILY_BUDGET_EXHAUSTED')
                        return [record(name,name,TITLE+' '+name,authors=['Alice Li'],year=2025,publication_date='2025-01-01')],None
                return A
            classes[name]=factory(name)
        c=Coordinator(self.ws,online=True,adapter_classes=classes);r=c.run(max_steps=6)
        statuses={e['source']:e['status'] for e in r['source_events']}
        self.assertEqual(statuses['cvf'],'PAGE_COMMITTED');self.assertEqual(statuses['pmlr'],'PAGE_COMMITTED')
        self.assertEqual(statuses['crossref'],'PAGE_COMMITTED');self.assertEqual(statuses['arxiv'],'SOURCE_PAUSED')
    def test_quota_alone_never_certifies_gate(self):
        self.workspace();c=Coordinator(self.ws);c.seed();s=c.status()
        self.assertNotEqual(s['status'],'CATALOG_250_PLUS_COMPLETE');self.assertTrue(s['reviewed_queries_pending'])
    def test_frozen_contract_refused(self):
        self.workspace();Coordinator(self.ws).save();(self.ws/'goal.md').write_text('changed research contract','utf-8')
        with self.assertRaisesRegex(ValueError,'contract'):Coordinator(self.ws)
    def test_year_boundary_marked_uncertain(self):
        self.workspace();c=Coordinator(self.ws);r=record('crossref','x',TITLE,year=2023)
        self.assertTrue(c.validate_row(r,TASK));self.assertIn('UNCERTAIN',r['date_window_status'])
    def test_openalex_existing_pause_and_library_untouched(self):
        self.workspace();p=self.ws/'output/discovery_preflight/openalex_http/state.json';write(p,{'pause':'daily-zero'})
        original=p.read_bytes();Coordinator(self.ws).plan();self.assertEqual(original,p.read_bytes())

class QuestionHookTests(Base):
    def setup_question(self):
        self.workspace()
        rce=WS/'research-cognition-engine/scripts'
        if str(rce) not in sys.path:sys.path.insert(0,str(rce))
        import question_retrieval as qs,store
        qs.db_init(self.ws)
        with store.connect(self.ws) as c:c.execute("INSERT INTO questions VALUES('Q-fixture','Fixture question',1,1,'test','OPEN','2026-10-26')")
        return qs,store,{'queries':[{'query':'world model','band':'RECENT_3Y','start_date':TASK['start'],'end_date':TASK['end'],'question_id':'Q-fixture','query_id':'QQ-fixture','completed':False}]}
    def test_question_links_and_conservative_reservation(self):
        from unittest.mock import patch
        qs,store,plan=self.setup_question()
        def run_fixture(co,**kw):
            tasks=[t for t in co.state['tasks'].values() if t.get('question_id')]
            for t in tasks:t.update(status='DONE',pages_completed=1)
            task=next(t for t in tasks if t['source']=='arxiv')
            co.catalog.add(record('arxiv','fixture',TITLE,year=2025,publication_date='2025-01-01'),task)
            co.budget['sent']=1;co.save()
            return {'report':'OFFLINE_FIXTURE_NOT_RESEARCH','source_events':[]}
        with patch.object(Coordinator,'_run_locked',run_fixture):
            result=qs._multisource_search(self.ws,plan,2)
        self.assertEqual(result['question_budget']['new_reserved'],2)
        co=Coordinator(self.ws)
        self.assertEqual(co.state['question_request_reservations'][0]['actual_physical_requests'],1)
        with store.connect(self.ws) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM multisource_question_links').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT search_openalex_id FROM question_papers').fetchall()[0][0],'')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM claims').fetchone()[0],0)
        again=qs._multisource_search(self.ws,plan,2)
        self.assertEqual(again['requests'],0)
        self.assertEqual(len(Coordinator(self.ws).state['question_request_reservations']),1)
    def test_question_lifetime_cap_not_reset(self):
        from unittest.mock import patch
        qs,store,plan=self.setup_question();co=Coordinator(self.ws)
        co.state['question_request_reservations']=[{'reserved_physical_requests':80,'actual_physical_requests':None}];co.save()
        with patch.object(Coordinator,'_run_locked',side_effect=AssertionError('Must not request')):
            result=qs._multisource_search(self.ws,plan,4)
        self.assertEqual(result['status'],'QUESTION_REQUEST_LIFETIME_CAP')
class PDFTests(Base):
    def pdf(self,title=TITLE):
        import fitz
        d=fitz.open();p=d.new_page();p.insert_text((40,50),title,fontsize=10)
        for i in range(25):p.insert_text((40,80+18*i),'Original scholarly text for fixture metadata identity '+str(i),fontsize=8)
        raw=d.tobytes();d.close();return raw
    def test_pdf_pypdf_fallback_keeps_identity_and_readability_gates(self):
        from unittest.mock import patch
        raw=self.pdf();wrong=self.pdf('Different mathematical article')
        with patch.dict(sys.modules,{'fitz':None}):
            result=inspect_pdf(raw,TITLE,600)
            self.assertEqual(result['text_extractor'],'pypdf')
            self.assertEqual(result['title_check'],'EXACT_NORMALIZED_TITLE')
            self.assertGreater(result['extractable_chars'],600)
            with self.assertRaises(ValueError):inspect_pdf(wrong,TITLE,600)
    def test_pdf_identity_and_text(self):
        r=inspect_pdf(self.pdf(),TITLE,600);self.assertEqual(r['title_check'],'EXACT_NORMALIZED_TITLE')
    def test_wrong_pdf_and_html_rejected(self):
        with self.assertRaises(ValueError):inspect_pdf(b'<html>paywall</html>',TITLE,600)
        with self.assertRaises(ValueError):inspect_pdf(self.pdf('Different mathematical article'),TITLE,600)
    def test_auth_only_families_do_not_starve_other_download_sources(self):
        self.workspace();c=Coordinator(self.ws);c.seed()
        for key in ['A0','A1','A2','Z9']:
            source='cvf' if key=='Z9' else 'openreview'
            title=TITLE+' '+key
            url='https://openaccess.thecvf.com/healthy.pdf' if source=='cvf' else 'https://openreview.net/pdf?id='+key
            row=record(source,key,title,legacy_work_id=key,year=2025,publication_date='2025-01-01',
                       fulltexts=[oa(source,url,'PUBLIC','OFFICIAL_OPEN_ACCESS')])
            fid,_=c.catalog.add(row);c.catalog.data['families'][fid]['screened_candidate_category']='core'
        c.save();raw=self.pdf(TITLE+' Z9');calls=[]
        class H:
            def __init__(self,ws,source,policy,online,budget):self.source=source;self.budget=budget
            def get(self,url,**kw):
                calls.append(self.source);self.budget['sent']+=1
                if self.source=='openreview':raise SourcePause(self.source,'AUTHORIZATION_REQUIRED')
                return raw,{'final_url':url,'fetched_at':'2026-10-26','sha256':sha(raw)}
        r=obtain(self.ws,online=True,limit=2,http_factory=H)
        self.assertEqual(calls,['openreview','cvf']);self.assertEqual(len(r['ready']),1)
        self.assertEqual(r['attempted_families'],2)
    def test_oversized_pdf_option_cooldown_survives_next_batch(self):
        self.workspace();c=Coordinator(self.ws);c.seed()
        row=record('arxiv','2501.12345',TITLE,year=2025,
            fulltexts=[oa('arxiv','https://arxiv.org/pdf/2501.12345v1','V1','ARXIV_PUBLIC_FULLTEXT')])
        fid,_=c.catalog.add(row);c.catalog.data['families'][fid]['screened_candidate_category']='core';c.save();calls=[]
        class H:
            def __init__(self,ws,source,policy,online,budget):self.source=source
            def get(self,url,**kw):calls.append(url);raise SourcePause(self.source,'RESPONSE_SIZE_BOUND')
        first=obtain(self.ws,online=True,limit=1,http_factory=H)
        self.assertEqual(first['failed'][0]['kind'],'RESPONSE_SIZE_BOUND')
        self.assertEqual(obtain(self.ws,online=True,limit=1,http_factory=H)['attempted_families'],0)
        self.assertEqual(len(calls),1)
    def test_download_provenance_and_no_duplicate_fetch(self):
        self.workspace();c=Coordinator(self.ws);c.seed()
        row=record('cvf','fixture',TITLE,authors=['Alice Li'],year=2025,publication_date='2025-01-01',
            landing_url='https://openaccess.thecvf.com/f.html',fulltexts=[oa('cvf','https://openaccess.thecvf.com/f.pdf','ACCEPTED','OFFICIAL_OPEN_ACCESS')])
        fid,_=c.catalog.add(row);c.catalog.data['families'][fid]['screened_candidate_category']='core';c.save()
        raw=self.pdf();calls=[]
        class H:
            def __init__(self,ws,source,policy,online,budget):self.source=source;self.budget=budget
            def get(self,url,**kw):
                calls.append(url);self.budget['sent']+=1
                return raw,{'final_url':url,'fetched_at':'2026-10-26','sha256':sha(raw)}
        r=obtain(self.ws,online=True,limit=1,http_factory=H);self.assertEqual(len(r['ready']),1)
        self.assertEqual(r['ready'][0]['sha256'],sha(raw));self.assertEqual(r['ready'][0]['version'],'ACCEPTED')
        self.assertEqual(obtain(self.ws,online=True,limit=1,http_factory=H)['ready'],[]);self.assertEqual(len(calls),1)
if __name__=='__main__':unittest.main(verbosity=2)

class CrossrefPagination(unittest.TestCase):
 def test_filtered_first_page_keeps_the_raw_result_cursor(self):
  cfg=copy.deepcopy(DEFAULTS);cfg['page_size']=2
  first={'message':{'total-results':3,'items':[{'type':'book-chapter'},{'type':'book-chapter'}]}}
  second={'message':{'total-results':3,'items':[{'type':'journal-article','DOI':'10.1234/fixture','title':['Synthetic methods article'],'published':{'date-parts':[[2025,1,1]]}}]}}
  http=FakeHTTP([('offset=0',json.dumps(first)),('offset=2',json.dumps(second))])
  adapter=Crossref(http,cfg);rows,cursor=adapter.search(TASK,None)
  self.assertEqual(rows,[]);self.assertEqual(cursor,'2')
  rows,cursor=adapter.search(TASK,cursor);self.assertEqual(len(rows),1);self.assertIsNone(cursor)

class FreshMultisourceBridge(Base):
 def prepare_download(self):
  self.workspace()
  sys.path.insert(0,str(WS/'research-cognition-engine/scripts'))
  import store,rce,multisource_bridge as bridge
  from test_public_release import Search2DiscoveryPublicTests
  rce.init(self.ws);cat=Catalog(self.ws)
  rec=record('arxiv','2601.12345',TITLE,venue='Synthetic Conference',year=2026,
     fulltexts=[oa('arxiv','https://arxiv.org/pdf/2601.12345','PREPRINT','OFFICIAL_PUBLIC_REPOSITORY')])
  fid,_=cat.add(rec,TASK);cat.data['families'][fid]['screened_candidate_category']='core'
  p=self.ws/'sources/multisource/fulltexts/fixture.pdf';p.parent.mkdir(parents=True)
  import fitz
  doc=fitz.open();page=doc.new_page();page.insert_textbox(fitz.Rect(40,40,550,800),('Synthetic source methods and evidence for a controlled literature bridge fixture. '*18),fontsize=10);doc.save(str(p));doc.close()
  cat.data['downloads']['synthetic-download']={'family_id':fid,'record_id':rec['record_id'],
   'path':str(p),'sha256':sha(p.read_bytes()),'status':'PDF_IDENTITY_CHECKED_NOT_S1_OR_FULLTEXT_REVIEWED'}
  cat.save();return bridge,store,fid,p
 def test_fresh_download_enters_reader_and_memory_without_legacy_library(self):
  bridge,store,fid,p=self.prepare_download();result=bridge.sync(self.ws)
  self.assertEqual(len(result['materialized_inputs']),1);self.assertEqual(result['scientific_claims_created'],0)
  self.assertEqual(store.listrows(self.ws,'sources')[0]['work_id'],fid)
  self.assertEqual(store.listrows(self.ws,'claims'),[])
  self.assertEqual(len(bridge.sync(self.ws)['materialized_inputs']),0)
  self.assertEqual(bridge.venue_records(self.ws)[fid]['venue'],'Synthetic Conference')
 def test_topic_router_ingests_retained_multisource_pdf_before_more_breadth(self):
  bridge,store,fid,p=self.prepare_download();bridge.sync(self.ws)
  import topic_to_plan as topic
  sentinel=self.ws/'.agents/skills/research-cognition-engine/SKILL.md';sentinel.parent.mkdir(parents=True);sentinel.write_text('installed fixture skill')
  topic.start(self.ws,'A bounded topic grounded in original source literature')
  contract=store.read(topic.contract_path(self.ws));contract['state']='TOPIC_CONFIG_COMMITTED';store.write(topic.contract_path(self.ws),contract)
  from unittest.mock import patch
  with patch.object(topic.wf,'choose',return_value={'status':'NEEDS_DISCOVERY'}):
   self.assertEqual(topic.next_action(self.ws)['status'],'NEEDS_ORIGINAL_V44_INGEST')
  self.assertEqual(topic._verified_download_stats(self.ws)['core'],1)
 def test_changed_multisource_pdf_cannot_become_reader_input(self):
  bridge,store,fid,p=self.prepare_download();p.write_bytes(b'changed fixture')
  self.assertRaisesRegex(ValueError,'integrity',bridge.sync,self.ws)
