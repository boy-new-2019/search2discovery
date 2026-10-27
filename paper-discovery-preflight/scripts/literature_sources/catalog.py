"""Cross-source work families, immutable manifestations and version relationships."""
import pathlib,sqlite3,json
from .common import norm,title_key,doi_id,arxiv_id,stable,sha,read,write,utc
def names(rec):
    return {re.sub(r'[^\w]','',norm(str(a)).casefold()).split()[-1] for a in rec.get('authors',[]) if norm(a)}
import re
def author_keys(rec):
    result=set()
    for name in rec.get('authors',[]):
        tokens=re.findall(r'\w+',str(name).casefold())
        if tokens:result.add(tokens[-1])
    return result
def matches(a,b):
    if a.get('doi') and a.get('doi')==b.get('doi'):return 'DOI'
    if a.get('arxiv_id') and a.get('arxiv_id')==b.get('arxiv_id'):return 'ARXIV_ID'
    ta=title_key(a['title']);tb=title_key(b['title'])
    if ta!=tb or len(ta)<18:return ''
    aa,bb=author_keys(a),author_keys(b)
    if aa and bb:return 'TITLE_AND_AUTHOR' if aa&bb else ''
    if len(ta)>=40:return 'EXACT_LONG_TITLE_AUTHOR_MISSING'
    return ''
class Catalog:
    def __init__(self,ws):
        self.ws=pathlib.Path(ws);self.root=self.ws/'output/discovery_preflight/multisource'
        self.path=self.root/'catalog.json'
        self.data=read(self.path) if self.path.exists() else {
            'schema_version':1,'records':{},'families':{},'record_family':{},'relations':[],
            'query_links':{},'downloads':{},'created_at':utc()}
    def save(self):write(self.path,self.data)
    def add(self,rec,task=None,*,legacy_category=None):
        rec=dict(rec);rec['doi']=doi_id(rec.get('doi',''))
        if not rec.get('title'):raise ValueError('A genuine title is required')
        if not rec.get('record_id') or not rec.get('source'):raise ValueError('Source identity required')
        signature={k:v for k,v in rec.items() if k not in ('observed_at','source_response','index_response')}
        digest=stable(signature);base=rec['record_id'];rid=base
        if rid in self.data['records']:
            old=self.data['records'][rid]
            oldsig={k:v for k,v in old.items() if k not in ('observed_at','source_response','index_response')}
            if stable(oldsig)!=digest:rid=base+'@metadata-'+digest[:16]
        if rid in self.data['records']:
            family=self.data['record_family'][rid]
            if task and task['category'] not in self.data['families'][family]['nominations']:self.data['families'][family]['nominations'].append(task['category'])
            if task:self.data['query_links'].setdefault(task['id'],[])
            if task and rid not in self.data['query_links'][task['id']]:self.data['query_links'][task['id']].append(rid)
            return family,False
        found={}
        for existing_id,other in self.data['records'].items():
            reason=matches(rec,other)
            if reason:found[self.data['record_family'][existing_id]]=reason
        if found:
            ids=sorted(found,key=lambda f:(not f.startswith('https://openalex.org/'),f));family=ids[0]
            # Preserve old database IDs as aliases; never delete their scientific records.
            for other_family in ids[1:]:
                for oldrid in self.data['families'][other_family]['record_ids']:
                    self.data['record_family'][oldrid]=family
                    if oldrid not in self.data['families'][family]['record_ids']:self.data['families'][family]['record_ids'].append(oldrid)
                for cat in self.data['families'][other_family].get('legacy_categories',[]):
                    if cat not in self.data['families'][family]['legacy_categories']:self.data['families'][family]['legacy_categories'].append(cat)
                for nomination in self.data['families'][other_family].get('nominations',[]):
                    if nomination not in self.data['families'][family]['nominations']:self.data['families'][family]['nominations'].append(nomination)
                self.data['families'][other_family]['redirect_to']=family
            match_reason=';'.join(sorted(set(found.values())))
        else:
            family=rec.get('legacy_work_id') or 'MS-WORK-'+stable({'record':rid})[:24];match_reason='NEW_IDENTITY'
            self.data['families'][family]={'record_ids':[],'legacy_categories':[],'nominations':[]}
        item=self.data['families'][family]
        if legacy_category and legacy_category not in item['legacy_categories']:item['legacy_categories'].append(legacy_category)
        if task and task['category'] not in item['nominations']:item['nominations'].append(task['category'])
        for oldrid in item['record_ids']:
            other=self.data['records'][oldrid];kind='SAME_WORK_MANIFESTATION'
            statuses={rec.get('publication_status'),other.get('publication_status')}
            if 'PREPRINT' in statuses and any(str(s).startswith('PUBLISHED_') for s in statuses):kind='PREPRINT_AND_PROCEEDINGS'
            elif 'PREPRINT' in statuses and any('OPENREVIEW' in str(s) or 'PUBLIC_SUBMISSION' in str(s) for s in statuses):kind='PREPRINT_AND_PUBLIC_REVIEW_NOTE'
            self.data['relations'].append({'left':oldrid,'right':rid,'kind':kind,'basis':match_reason,
                                          'acceptance_or_scientific_equivalence_not_inferred':True})
        rec['record_id']=rid;self.data['records'][rid]=rec;self.data['record_family'][rid]=family;item['record_ids'].append(rid)
        payload=self.root/'records'/(stable(rid)+'.'+digest+'.json')
        if not payload.exists():write(payload,rec)
        if task:self.data['query_links'].setdefault(task['id'],[]).append(rid)
        return family,True
    def active(self):return {k:v for k,v in self.data['families'].items() if not v.get('redirect_to')}
    def identity_reviews(self):
        reviews={}
        for p in sorted((self.root/'identity_reviews').glob('*.json')):
            row=read(p);key=row['download_id'];download=self.data['downloads'].get(key)
            if download is None or row['sha256']!=download['sha256'] or row['family_id']!=download['family_id']:
                raise ValueError('Identity review binding integrity failed')
            if row['status'] not in ('REJECTED_IDENTITY_MISMATCH','VERIFIED_HEADER_IDENTITY'):
                raise ValueError('Unknown identity review state')
            reviews[key]=row
        return reviews
    def usable_downloads(self):
        reviews=self.identity_reviews()
        return {k:v for k,v in self.data['downloads'].items() if reviews.get(k,{}).get('status')!='REJECTED_IDENTITY_MISMATCH'}
    def counts(self):
        counts={'core':0,'related':0,'inspiration':0,'unclassified':0};conflicts=[]
        for family,row in self.active().items():
            categories=row['legacy_categories']
            if len(categories)>1:conflicts.append({'family':family,'legacy_categories':categories})
            # Cross-category aliases do not silently count as two separate works.
            category=categories[0] if categories else row.get('screened_candidate_category','unclassified')
            counts[category]=counts.get(category,0)+1
        return counts,conflicts
    def sync_memory(self):
        db=self.ws/'output/research_cognition/research_memory.sqlite3'
        if not db.exists():return {'status':'NO_EXISTING_RESEARCH_DB','new_works':0}
        con=sqlite3.connect(f'file:{db.as_posix()}?mode=rw',uri=True)
        try:
            con.execute('PRAGMA foreign_keys=ON')
            con.executescript('''
            CREATE TABLE IF NOT EXISTS multisource_records(record_id TEXT PRIMARY KEY,family_id TEXT NOT NULL,source TEXT NOT NULL,record_json TEXT NOT NULL,record_sha256 TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS multisource_relations(relation_id TEXT PRIMARY KEY,relation_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS multisource_downloads(download_id TEXT PRIMARY KEY,provenance_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS multisource_identity_reviews(download_id TEXT PRIMARY KEY,review_json TEXT NOT NULL);
            ''')
            added=0
            for fid,family in self.active().items():
                rec=self.data['records'][family['record_ids'][0]]
                if not con.execute('SELECT 1 FROM works WHERE work_id=?',(fid,)).fetchone():
                    con.execute('INSERT INTO works(work_id,title,category,doi,year,venue,url,record_sha) VALUES(?,?,?,?,?,?,?,?)',
                        (fid,rec['title'],'multisource_candidate',rec.get('doi',''),rec.get('year'),rec.get('venue',''),rec.get('landing_url',''),stable(rec)))
                    added+=1
            for rid,rec in self.data['records'].items():
                family=self.data['record_family'][rid]
                con.execute('INSERT OR IGNORE INTO multisource_records VALUES(?,?,?,?,?)',(rid,family,rec['source'],json.dumps(rec,ensure_ascii=False),stable(rec)))
            for relation in self.data['relations']:
                con.execute('INSERT OR IGNORE INTO multisource_relations VALUES(?,?)',(stable(relation),json.dumps(relation,ensure_ascii=False)))
            for key,download in self.data['downloads'].items():
                con.execute('INSERT OR IGNORE INTO multisource_downloads VALUES(?,?)',(key,json.dumps(download,ensure_ascii=False)))
            for key,review in self.identity_reviews().items():
                con.execute('INSERT OR IGNORE INTO multisource_identity_reviews VALUES(?,?)',(key,json.dumps(review,ensure_ascii=False)))
            con.commit()
            return {'status':'ADDITIVE_BIBLIOGRAPHIC_SYNC','new_works':added,'scientific_claims_created':0,
                    'existing_work_rows_updated':0,'fulltext_reading_status_not_promoted':True}
        finally:con.close()