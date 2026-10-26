import tempfile, pathlib,sys,json,unittest,hashlib,shutil
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import paper_discovery as d
import install_into_codex_project as installer
from test_preflight import fake_work


class InstallAndDownload(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.project=pathlib.Path(self.temp.name)
        self.core=self.project/'.agents/skills/batch-paper-deepread-desktop'
        self.core.mkdir(parents=True)
        (self.core/'SKILL.md').write_text('---\nname: batch-paper-deepread-desktop\ndescription: old\n---\n# Main Codex Paper Skill v4.4\n\nExisting important content\n','utf8')
        (self.project/'goal.md').write_text('Streaming 3D occupancy and memory, user confirmed direction.','utf8')
        (self.project/'input').mkdir();(self.project/'input'/'user.pdf').write_bytes(b'user-owned-existing-pdf')
        (self.project/'output').mkdir();(self.project/'output'/'notes.txt').write_text('KEEP OLD NOTES','utf8')
    def tearDown(self):self.temp.cleanup()
    def test_install_patches_main_and_never_touches_user_sources(self):
        old=(self.core/'SKILL.md').read_bytes()
        got=installer.install(self.project)
        self.assertTrue(got['main_skill_patched'])
        self.assertIn('BEGIN-PAPER-DISCOVERY-PREFLIGHT',(self.core/'SKILL.md').read_text('utf8'))
        self.assertEqual((self.core/'SKILL.md.before_discovery_preflight').read_bytes(),old)
        self.assertEqual((self.project/'input'/'user.pdf').read_bytes(),b'user-owned-existing-pdf')
        self.assertEqual((self.project/'output'/'notes.txt').read_text(), 'KEEP OLD NOTES')
        self.assertTrue((self.project/'.agents/skills/paper-discovery-preflight/SKILL.md').exists())
        self.assertTrue((self.project/'discovery_config.json').exists())
        with self.assertRaises(ValueError):
            installer.install(self.project)
        r=installer.install(self.project,upgrade=True)
        self.assertFalse(r['main_skill_patched'])
        self.assertEqual((self.core/'SKILL.md.before_discovery_preflight').read_bytes(),old)
    def test_already_copied_skill_can_patch_original_without_recopying(self):
        source=ROOT
        target=self.project/'.agents'/'skills'/'paper-discovery-preflight'
        shutil.copytree(source,target,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        import subprocess
        p=subprocess.run([sys.executable,str(target/'scripts'/'install_into_codex_project.py'),
                          '--project',str(self.project)],capture_output=True,text=True,timeout=20)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('BEGIN-PAPER-DISCOVERY-PREFLIGHT',(self.core/'SKILL.md').read_text('utf8'))
        again=subprocess.run([sys.executable,str(target/'scripts'/'install_into_codex_project.py'),
                              '--project',str(self.project)],capture_output=True,text=True,timeout=20)
        self.assertEqual(again.returncode,0,again.stderr)
        self.assertEqual((self.core/'SKILL.md').read_text('utf8').count('BEGIN-PAPER-DISCOVERY-PREFLIGHT'),1)
    def test_install_without_old_skill_does_not_create_fake_main_skill(self):
        shutil.rmtree(self.core)
        r=installer.install(self.project)
        self.assertFalse(r['main_skill_found'])
        self.assertFalse((self.core/'SKILL.md').exists())
    def _seed(self):
        c=d.config(self.project)
        c['as_of_date']='2026-10-25'
        c['quotas']={'core':1,'related':1,'inspiration':1}
        c['preferred_domains']={k:0 for k in c['preferred_domains']}
        d.write(self.project/'discovery_config.json',c)
        s=d.state_at(self.project,c)
        docs=[d.work_normalized(fake_work('source'+str(i),i,cat=cat,domain='philosophy' if cat=='inspiration' else ''),cat,
                                'philosophy' if cat=='inspiration' else '',cat)
              for i,cat in enumerate(('core','related','inspiration'))]
        s['works']={r['id']:r for r in docs}
        d.select(self.project,c,s)
        d.write(d.root_out(self.project)/'state.json',s)
        return c,s
    def test_download_writes_only_verified_target_categories(self):
        installer.install(self.project)
        c,s=self._seed()
        def fake_pdf(url,dst,max_mb,minchars):
            import fitz
            dst.parent.mkdir(parents=True,exist_ok=True)
            f=fitz.open()
            for i in range(2):
                pg=f.new_page()
                pg.insert_text((20,20),('Paper fulltext evidence study context. '*10),fontsize=8)
            f.save(dst);f.close()
        answer=d.obtain_fulltexts(self.project,online=True,category='core',limit=1,download_fn=fake_pdf)
        self.assertEqual(len(answer['downloaded']),1)
        self.assertTrue(answer['downloaded'][0].startswith('input/discovery_core/'))
        self.assertEqual(d.status(self.project)['fulltexts_downloaded'],1)
        same=d.obtain_fulltexts(self.project,online=True,category='core',limit=1,download_fn=fake_pdf)
        self.assertEqual(same['downloaded'],[])
        insp=d.obtain_fulltexts(self.project,online=True,category='inspiration',limit=1,download_fn=fake_pdf)
        self.assertEqual(len(insp['downloaded']),1)
        self.assertTrue(insp['downloaded'][0].startswith('cross_domain_input/philosophy/'))
        self.assertEqual((self.project/'input'/'user.pdf').read_bytes(),b'user-owned-existing-pdf')
        self.assertEqual((self.project/'output'/'notes.txt').read_text('utf8'),'KEEP OLD NOTES')
    def test_download_wrong_original_oa_rejected_before_using_fake_downloader(self):
        installer.install(self.project)
        c,s=self._seed()
        for x in s['selection']['selected']['core']:x['oa_pdf_url']='http://localhost/private'
        d.write(d.root_out(self.project)/'state.json',s)
        count=[]
        def fake_download(url,dst,max_mb,minchars):count.append(url)
        outcome=d.obtain_fulltexts(self.project,online=True,category='core',limit=1,download_fn=fake_download)
        # Reject potentially malicious metadata irrespective of test backend.
        self.assertEqual(count,[])
        self.assertEqual(len(outcome['failed']),1)
    def test_api_date_validated_and_query_keyword_thresholds(self):
        installer.install(self.project)
        c,s=self._seed()
        c['min_classification_score']['core']=0
        d.write(self.project/'discovery_config.json',c)
        with self.assertRaises(ValueError):
            d.config(self.project)
    def test_discard_books_and_unattributed_works(self):
        w=fake_work('fake',3,cat='core')
        w['type']='book'
        self.assertIsNone(d.work_normalized(w,'core','',''))
        w['type']='article';w['authorships']=[]
        self.assertIsNone(d.work_normalized(w,'core','',''))

if __name__=='__main__':unittest.main()
