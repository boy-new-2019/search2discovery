import pathlib, sys, tempfile, unittest, datetime, json
ROOT=pathlib.Path(__file__).resolve().parents[1] / 'scripts'
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import pro5x_optimizer as op
import pro5x_shortlist as sq

class ShortlistTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.ws=pathlib.Path(t.name)
    def test_without_library_no_false_papers(self):
        a=sq.shortlist(self.ws)
        self.assertEqual(a['status'],'NEEDS_REAL_V5_BIBLIOGRAPHY')
        self.assertFalse((self.ws/'output'/'research_cognition').exists())
    def fake(self):
        ws=self.ws; d=ws/'output'/'discovery_preflight';d.mkdir(parents=True)
        records=[]
        for i in range(25):
            records.append(dict(id='https://openalex.org/W'+str(i),title='Study '+str(i),year=2025,publication_date='2025-01-01',
                                source_id='S'+str(i%4),venue='Venue'+str(i%4),
                                priority_venue_shortlist_match=(i%2==0),
                                relevance_score=i/10,oa_pdf_url=('https://example.org/paper.pdf' if i%2 else '')))
        op.write(d/'paper_library.json',{'provenance':'OpenAlex bibliographic metadata only','as_of_date':'2026-10-26',
                                         'selected':{'core':records,'related':records[:7],'inspiration':records[7:10]}})
    def test_true_metadata_only_and_dedup(self):
        self.fake();a=sq.shortlist(self.ws,core=12,related=3,inspiration=2)
        self.assertEqual(a['status'],'SHORTLIST_ONLY_NOT_DEEPREAD')
        self.assertEqual(a['first_wave_counts'],{'core':12,'related':3,'inspiration':2})
        result=op.read(pathlib.Path(a['output_file']))
        self.assertTrue(result['no_llm_calls'])
        self.assertTrue(result['no_pdfs_downloaded_by_this_operation'])
        self.assertEqual(len({x['id'] for x in result['waves']['core']}),12)
        self.assertTrue(all(x['requires_real_S1_S2_and_fulltext_confirmation'] for x in result['waves']['core']))
        self.assertEqual(result['source_file_sha256'],op.sha(self.ws/'output'/'discovery_preflight'/'paper_library.json'))
    def test_wrong_provenance_blocked(self):
        self.fake();p=self.ws/'output'/'discovery_preflight'/'paper_library.json';a=op.read(p);a['provenance']='made up';op.write(p,a)
        with self.assertRaises(ValueError):sq.shortlist(self.ws)
    def test_no_duplicate_and_no_leak_on_repeat(self):
        self.fake()
        a=sq.shortlist(self.ws)
        f=pathlib.Path(a['output_file']);before=f.read_bytes()
        self.assertEqual(f.read_bytes(),before)
        sq.shortlist(self.ws)
        self.assertEqual(f.read_bytes(),before)

if __name__=='__main__':unittest.main()
