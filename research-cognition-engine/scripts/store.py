#!/usr/bin/env python3
"""SQLite-backed research memory with verifiable source-text provenance.

All scientific semantics beyond literal quote-matching remain *unverified* until
independent review/experiments. Data are persistent between Codex sessions.
"""
from __future__ import annotations
import hashlib, json, os, pathlib, re, sqlite3, tempfile, datetime as dt
from contextlib import contextmanager
from typing import Any


def utc()->str:return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
def dump(x:Any)->str:return json.dumps(x,ensure_ascii=False,sort_keys=True,indent=2)
def hashbytes(x:bytes)->str:return hashlib.sha256(x).hexdigest()
def hashobj(x:Any)->str:return hashbytes(dump(x).encode('utf-8'))
def read(p:pathlib.Path)->Any:return json.loads(p.read_text(encoding='utf-8'))
def write(p:pathlib.Path,x:Any)->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile('w',encoding='utf-8',newline='\n',delete=False,dir=str(p.parent),prefix='.rce-tmp') as f:
        f.write(dump(x)+'\n'); tmp=f.name
    os.replace(tmp,str(p))
def textwrite(p:pathlib.Path,text:str)->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile('w',encoding='utf-8',newline='\n',delete=False,dir=str(p.parent),prefix='.rce-tmp') as f:
        f.write(text); tmp=f.name
    os.replace(tmp,str(p))
def norm(t:str)->str:return re.sub(r'\s+',' ',str(t)).strip()

def root(ws:pathlib.Path)->pathlib.Path:return ws/'output'/'research_cognition'
def dbfile(ws:pathlib.Path)->pathlib.Path:return root(ws)/'research_memory.sqlite3'

def _open(ws:pathlib.Path)->sqlite3.Connection:
    db=dbfile(ws);db.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(str(db),timeout=30)
    c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA busy_timeout=30000')
    c.row_factory=sqlite3.Row
    c.executescript('''
    CREATE TABLE IF NOT EXISTS works(
       work_id TEXT PRIMARY KEY,title TEXT NOT NULL,category TEXT NOT NULL,
       doi TEXT NOT NULL DEFAULT '',year INTEGER,venue TEXT NOT NULL DEFAULT '',
       url TEXT NOT NULL DEFAULT '',record_sha TEXT NOT NULL,source_status TEXT NOT NULL DEFAULT 'BIB_ONLY');
    CREATE TABLE IF NOT EXISTS sources(
       source_id TEXT PRIMARY KEY,work_id TEXT NOT NULL REFERENCES works(work_id),
       file_path TEXT NOT NULL,file_sha TEXT NOT NULL,page_count INTEGER NOT NULL,
       extract_path TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS claims(
       claim_id TEXT PRIMARY KEY,source_id TEXT NOT NULL REFERENCES sources(source_id),
       work_id TEXT NOT NULL REFERENCES works(work_id),text TEXT NOT NULL,claim_kind TEXT NOT NULL,
       page INTEGER NOT NULL,quote TEXT NOT NULL,role TEXT NOT NULL,status TEXT NOT NULL,
       created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS questions(
       question_id TEXT PRIMARY KEY,question TEXT NOT NULL,impact REAL NOT NULL,
       uncertainty REAL NOT NULL,domain TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS contradictions(
       id TEXT PRIMARY KEY,left_id TEXT NOT NULL REFERENCES claims(claim_id),
       right_id TEXT NOT NULL REFERENCES claims(claim_id),rationale TEXT NOT NULL,
       protocol_check TEXT NOT NULL,alternative TEXT NOT NULL,discriminating_test TEXT NOT NULL,
       status TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS hypotheses(
       hypothesis_id TEXT PRIMARY KEY,question_id TEXT NOT NULL REFERENCES questions(question_id),
       statement TEXT NOT NULL,mechanism TEXT NOT NULL,prediction TEXT NOT NULL,
       falsifier TEXT NOT NULL,assumptions TEXT NOT NULL,linked_claims TEXT NOT NULL,
       nearest_works TEXT NOT NULL,minimal_test TEXT NOT NULL,novelty_status TEXT NOT NULL,
       status TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS assessments(
       hypothesis_id TEXT NOT NULL REFERENCES hypotheses(hypothesis_id),role TEXT NOT NULL,
       verdict TEXT NOT NULL,nearest_works TEXT NOT NULL,reason TEXT NOT NULL,
       thread_ref TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(hypothesis_id,role));
    CREATE TABLE IF NOT EXISTS experiments(
       plan_id TEXT PRIMARY KEY,hypothesis_id TEXT NOT NULL REFERENCES hypotheses(hypothesis_id),
       plan TEXT NOT NULL,baselines TEXT NOT NULL,metrics TEXT NOT NULL,
       reject_condition TEXT NOT NULL,resource TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS decisions(
       decision_id TEXT PRIMARY KEY,hypothesis_id TEXT NOT NULL REFERENCES hypotheses(hypothesis_id),
       recommendation TEXT NOT NULL,risks TEXT NOT NULL,review_note TEXT NOT NULL,
       status TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS feedback(
       feedback_id TEXT PRIMARY KEY,plan_id TEXT NOT NULL REFERENCES experiments(plan_id),
       experiment_log_path TEXT NOT NULL,experiment_log_sha256 TEXT NOT NULL,
       observations TEXT NOT NULL,interpretation TEXT NOT NULL,claimed_direction TEXT NOT NULL,
       review_verdict TEXT NOT NULL,reviewer_role TEXT NOT NULL,reviewer_thread_ref TEXT NOT NULL,
       status TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS events(
       seq INTEGER PRIMARY KEY AUTOINCREMENT,event_type TEXT NOT NULL,payload TEXT NOT NULL,
       payload_sha TEXT NOT NULL,created_at TEXT NOT NULL);
    ''')
    return c

@contextmanager
def connect(ws:pathlib.Path):
    c=_open(ws)
    try:
        with c:
            yield c
    finally:
        c.close()

def event(c:sqlite3.Connection,typ:str,data:dict)->None:
    body=dump(data)
    c.execute('INSERT INTO events(event_type,payload,payload_sha,created_at) VALUES(?,?,?,?)',
              (typ,body,hashbytes(body.encode()),utc()))

def source_pages(path:pathlib.Path)->list[str]:
    ext=path.suffix.lower()
    if ext=='.json':
        data=read(path)
        pages=data.get('pages') if isinstance(data,dict) else None
        if not isinstance(pages,list) or not pages or not all(isinstance(x,str) for x in pages):
            raise ValueError('JSON source must contain a nonempty pages array')
        return pages
    if ext=='.pdf':
        try:
            import fitz  # optional: AGPL/commercial licensing, see docs/DEPENDENCIES.md
        except ImportError:
            try:
                from pypdf import PdfReader  # BSD-3-Clause fallback
            except ImportError as exc:
                raise RuntimeError('PDF text extraction requires pypdf>=4 or a separately licensed PyMuPDF installation') from exc
            reader=PdfReader(str(path))
            if reader.is_encrypted:
                raise ValueError('Encrypted PDF cannot be accepted as independently readable full text')
            pages=[page.extract_text() or '' for page in reader.pages]
        else:
            doc=fitz.open(path)
            try:
                if doc.needs_pass:
                    raise ValueError('Encrypted PDF cannot be accepted as independently readable full text')
                pages=[p.get_text('text') for p in doc]
            finally:
                doc.close()
        if not pages or sum(len(p.strip()) for p in pages)<500:
            raise ValueError('PDF has insufficient extractable text; NOT full-text verified')
        return pages
    if ext not in ('.txt','.md','.tex'):
        raise ValueError('Only PDF, TXT, MD, TEX or source corpus JSON accepted')
    data=path.read_text(encoding='utf-8')
    if len(data.strip())<100:raise ValueError('Too little full text; no bibliography-as-fulltext promotion')
    # preserve form-feed virtual pages if explicitly supplied
    return data.split('\f') if '\f' in data else [data]

def import_source(ws:pathlib.Path,work_id:str,path:pathlib.Path)->dict:
    file=path.expanduser().resolve()
    if not file.is_file():raise ValueError('Source file does not exist')
    with connect(ws) as c:
        found=c.execute('SELECT 1 FROM works WHERE work_id=?',(work_id,)).fetchone()
        if not found:raise ValueError('Work ID missing from imported catalogue; no invented paper identity')
    blob=file.read_bytes();digest=hashbytes(blob)
    pages=source_pages(file)
    sid='SRC-'+digest[:18]
    cache=root(ws)/'source_cache'/f'{sid}.json'
    # Reject evidence identity conflicts BEFORE touching the cached original
    # pages; otherwise a failed second registration could corrupt provenance.
    with connect(ws) as c:
        current=c.execute('SELECT work_id,file_sha FROM sources WHERE source_id=?',(sid,)).fetchone()
        if current and (current['work_id']!=work_id or current['file_sha']!=digest):
            raise ValueError('Source hash collision/duplicate across different work IDs')
    write(cache,{'source_id':sid,'work_id':work_id,'original_sha256':digest,'pages':pages,'extract_kind':'text_only_figure_not_audited'})
    with connect(ws) as c:
        c.execute('INSERT OR IGNORE INTO sources VALUES (?,?,?,?,?,?,?)',
                  (sid,work_id,str(file),digest,len(pages),str(cache),utc()))
        c.execute("UPDATE works SET source_status='TEXT_AVAILABLE' WHERE work_id=?",(work_id,))
        event(c,'SOURCE_INDEXED',{'source_id':sid,'work_id':work_id,'file_sha':digest,'page_count':len(pages)})
    return {'source_id':sid,'paper_id':work_id,'pages':len(pages),'original_sha256':digest,'figures':'VISUAL_PENDING'}

def checked_quote(ws:pathlib.Path,source_id:str,page:int,quote:str)->dict:
    if not isinstance(quote,str) or not 10<=len(norm(quote))<=280:
        raise ValueError('Source quote must have 10–280 meaningful characters')
    with connect(ws) as c:
        src=c.execute('SELECT * FROM sources WHERE source_id=?',(source_id,)).fetchone()
    if not src:raise ValueError('Unknown source_id')
    f=pathlib.Path(src['file_path'])
    if not f.is_file() or hashbytes(f.read_bytes())!=src['file_sha']:
        raise ValueError('Original source changed/missing; previous anchors cannot be trusted')
    cache=read(pathlib.Path(src['extract_path']))
    pages=cache['pages']
    if not isinstance(page,int) or not 1<=page<=len(pages):raise ValueError('Quote page missing')
    if norm(quote) not in norm(pages[page-1]):
        raise ValueError('Claim quote not present on the stated source page')
    return {'work_id':src['work_id'],'source_sha256':src['file_sha'],'page':page}

def import_catalogue(ws:pathlib.Path)->dict:
    path=ws/'output'/'discovery_preflight'/'paper_library.json'
    if not path.is_file():return {'status':'NO_V5_CATALOGUE','imported':0}
    data=read(path);selected=data.get('selected',{})
    if not isinstance(selected,dict):raise ValueError('v5 catalogue selected must be a map')
    count=0
    with connect(ws) as c:
        for category in ('core','related','inspiration'):
            for x in selected.get(category,[]):
                wid=x.get('id')
                if not wid or not isinstance(wid,str) or not isinstance(x.get('title'),str):
                    raise ValueError('v5 record lacks OpenAlex id or verified title')
                current=c.execute('SELECT category FROM works WHERE work_id=?',(wid,)).fetchone()
                if current and current['category']!=category:
                    raise ValueError(f'v5 disjoint catalogue conflict: {wid}')
                c.execute('INSERT OR IGNORE INTO works(work_id,title,category,doi,year,venue,url,record_sha) VALUES (?,?,?,?,?,?,?,?)',
                    (wid,x['title'],category,x.get('doi') or '',x.get('year'),x.get('venue') or '',
                    x.get('bibliographic_link') or x.get('landing_url') or '',hashobj(x)))
                count+=bool(not current)
        event(c,'V5_CATALOGUE_SYNC',{'created_works':count,'origin':str(path),'file_sha':hashbytes(path.read_bytes()),'metadata_only':True})
    return {'status':'SYNCED','new_bibliographic_works':count,'note':'No title/abstract has been promoted to verified full-text scientific evidence'}

def listrows(ws:pathlib.Path,table:str,limit:int=500)->list[dict]:
    names={'works','sources','claims','questions','contradictions','hypotheses','assessments','experiments','feedback','decisions','events'}
    if table not in names:raise ValueError('Invalid table')
    with connect(ws) as c:return [dict(x) for x in c.execute(f'SELECT * FROM {table} LIMIT ?', (limit,)).fetchall()]


def import_v5_downloads(ws:pathlib.Path)->dict:
    """Index ONLY recorded, SHA-verified v5 real OA PDFs; no network and no guessing.

    This is a one-command bridge between the v5 bibliographic stage and RCE.
    Works with pre-existing v5 download_log state without touching those logs.
    """
    file=root(ws).parent/'discovery_preflight'/'state.json'
    if not file.is_file():return {'status':'NO_V5_DOWNLOAD_LOG','imported':0,'skipped':0}
    state=read(file);entries=state.get('download_log',{})
    imported=[];skipped=[];failed=[]
    with connect(ws) as c:
        works={r['work_id'] for r in c.execute('SELECT work_id FROM works')}
    for workid,record in entries.items():
        if record.get('status')!='FULLTEXT_READY':continue
        if workid not in works:
            skipped.append({'work_id':workid,'reason':'not selected in disjoint v5 catalogue'});continue
        rel=pathlib.Path(record.get('relative_path',''))
        if rel.is_absolute() or '..' in rel.parts or not rel.parts:
            failed.append({'work_id':workid,'reason':'unsafe source path'});continue
        f=(ws/rel).resolve()
        if not f.is_relative_to(ws.resolve()) or not f.is_file():
            failed.append({'work_id':workid,'reason':'file missing/outside workspace'});continue
        if hashbytes(f.read_bytes())!=record.get('sha256'):
            failed.append({'work_id':workid,'reason':'SHA256 mismatch or modified PDF'});continue
        try:imported.append(import_source(ws,workid,f))
        except (ValueError,RuntimeError) as exc:
            failed.append({'work_id':workid,'reason':str(exc)[:190]})
    return {'status':'PARTIAL' if failed else 'IMPORTED','imported':len(imported),
            'skipped':skipped,'failed':failed,'no_new_model_calls':True}
