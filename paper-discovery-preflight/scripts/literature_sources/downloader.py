"""Lawful OA acquisition with title checks and immutable provenance; no reading claims."""
import csv,datetime as dt,json,pathlib,re,time
from .common import sha,stable,read,write,utc,title_key,locked
from .transport import SourcePause,allowed
from .coordinator import Coordinator
def title_evidence(first_pages,title,authors=()):
    """Match a title in one header extraction, never scattered reference words."""
    key=title_key(title)
    variant=re.sub(r'\([A-Z][A-Z0-9-]{1,9}\)\s*','',title)
    for index,page in enumerate(first_pages):
        # Raw and sorted extraction are independent views of the same page.
        for text in page if isinstance(page,(tuple,list)) else [page]:
            if index and not re.search(r'(?im)^\s*abstract(?:\s|[:\u2014-])',text):continue
            cut=re.search(r"(?im)^\s*abstract(?:\s|[:\u2014-])|^\s*(?:1[. ]+)?(?:introduction|references)\b",text)
            header=text[:cut.start() if cut else 3500];found=title_key(header)
            author_hits=[a for a in authors if len(title_key(a))>=5 and title_key(a) in found]
            if key and key in found and (len(key)>=18 or author_hits):
                return {'title_check':'EXACT_NORMALIZED_TITLE' if len(key)>=18 else 'EXACT_HEADER_TITLE_AND_AUTHOR','matched_authors':author_hits}
            if variant!=title and len(title_key(variant))>=18 and title_key(variant) in found and author_hits:
                return {'title_check':'TITLE_WITH_OPTIONAL_ACRONYM_AND_AUTHOR','matched_authors':author_hits}
    return None

def inspect_pdf(raw,title,minchars,authors=()):
    if not raw.startswith(b'%PDF-'):raise ValueError('Response is not a PDF')
    try:import fitz
    except ImportError:
        import io
        from pypdf import PdfReader
        doc=PdfReader(io.BytesIO(raw))
        if doc.is_encrypted:raise ValueError('Encrypted PDF is not accepted')
        pages=len(doc.pages);texts=[p.extract_text() or '' for p in doc.pages]
        text='\n'.join(texts);first_pages=texts[:2];extractor='pypdf'
    else:
        with fitz.open(stream=raw,filetype='pdf') as doc:
            if doc.needs_pass:raise ValueError('Encrypted PDF is not accepted')
            pages=len(doc);text='\n'.join(p.get_text() for p in doc)
            first_pages=[(doc[i].get_text(sort=True),doc[i].get_text()) for i in range(min(2,pages))]
        extractor='pymupdf'
    if len(text.strip())<minchars:raise ValueError('Insufficient extractable original text')
    evidence=title_evidence(first_pages,title,authors)
    if not evidence:raise ValueError('PDF header title identity is not sufficiently supported')
    return {'pages':pages,'extractable_chars':len(text),'text_sha256':sha(text.encode()),'text_extractor':extractor,
            **evidence,'title_token_coverage':1.0}
_LOCAL_TITLE_INDEX={}

def local_candidates(ws,title,authors=()):
    ledger=ws.parent/'deep_reading/full_read_ledger.csv'
    if ledger.exists():
        with ledger.open(encoding='utf-8-sig',newline='') as f:
            for row in csv.DictReader(f):
                if title_key(row.get('title',''))!=title_key(title):continue
                folder=ledger.parent/pathlib.Path(row['coverage_file']).parent
                for name in row.get('pdf_files','').split(';'):
                    path=folder/name
                    if path.is_file():yield path,row
    for path in sorted((ws/'input').rglob('*.pdf')) if (ws/'input').exists() else []:
        stat=path.stat();key=(str(path.resolve()),stat.st_size,stat.st_mtime_ns)
        if key not in _LOCAL_TITLE_INDEX:
            try:
                import fitz
                with fitz.open(path) as doc:
                    first=[(doc[i].get_text(sort=True),doc[i].get_text()) for i in range(min(2,len(doc)))]
                _LOCAL_TITLE_INDEX[key]=first
            except (ValueError,RuntimeError):continue
        if title_evidence(_LOCAL_TITLE_INDEX[key],title,authors):
            yield path,{'version':'EXISTING_LOCAL_SOURCE','source_url':''}

def obtain(ws,*,online,category='core',limit=3,request_limit=12,http_factory=None,family_ids=None):
    if not online:raise ValueError('Explicit online/OA authorization is required')
    if category not in ('core','related','inspiration','all'):raise ValueError('Unknown candidate category')
    from .transport import HTTP
    co=Coordinator(ws,online=True,request_limit=request_limit,http_factory=http_factory or HTTP)
    co.seed();cfg=co.cfg;limit=min(limit,cfg['max_pdfs_per_run'])
    if limit<1:raise ValueError('Positive download bound required')
    ready=[];failures=[];blocked=set();attempted=0
    with locked(co.root):
        families=[(f,r) for f,r in co.catalog.active().items() if family_ids is None or f in family_ids]
        # New official manifestations first; deterministic IDs break ties.
        families.sort(key=lambda pair:(not any(co.catalog.data['records'][r]['source'] in cfg['primary_sources'] for r in pair[1]['record_ids']),pair[0]))
        for fid,family in families:
            if attempted>=limit:break
            cat=(family['legacy_categories'] or [family.get('screened_candidate_category')])[0]
            if category!='all' and cat!=category:continue
            prior=[x for x in co.catalog.usable_downloads().values() if x['family_id']==fid]
            if prior:
                for item in prior:
                    path=pathlib.Path(item['path'])
                    if not path.is_file() or sha(path.read_bytes())!=item['sha256']:raise ValueError('Previously retained PDF integrity failed')
                continue
            recs=[co.catalog.data['records'][r] for r in family['record_ids']]
            options=[(r,o) for r in recs for o in r.get('fulltexts',[]) if allowed(o['source'],o['url'])]
            # Old immutable records may contain an attachment hash under the web host.
            # Use the public note PDF endpoint; preserve the original attachment URL.
            from urllib.parse import urlsplit,quote
            options=[(r,{**o,'original_attachment_url':o['url'],'url':'https://openreview.net/pdf?id='+quote(r['source_record_id'],safe='')})
                     if o['source']=='openreview' and urlsplit(o['url']).path.startswith('/pdf/') and r.get('source_record_id') else (r,o) for r,o in options]
            # A bounded oversized response must not be fetched again every batch.
            # Bind cooldown to source identity, URL and current byte ceiling; a new
            # version/URL or explicit larger legal bound remains independently eligible.
            failures_by_option=co.catalog.data.setdefault('download_option_failures',{})
            def option_key(rec,option):
                return stable({'record_id':rec['record_id'],'url':option['url'],'max_bytes':cfg['max_pdf_bytes']})
            options=[(r,o) for r,o in options if failures_by_option.get(option_key(r,o),{}).get('resume_after',0)<=time.time()]
            if not options:continue
            title=recs[0]['title'];saved=None
            for path,info in local_candidates(co.ws,title,recs[0].get('authors',[])):
                raw=path.read_bytes()
                try:checks=inspect_pdf(raw,title,cfg['min_pdf_chars'],recs[0].get('authors',[]))
                except (ValueError,RuntimeError):continue
                saved={'family_id':fid,'record_id':recs[0]['record_id'],'source':'existing_local',
                       'original_url':info.get('source_url',''),'final_url':info.get('source_url',''),
                       'version':info.get('version','EXISTING_LOCAL_SOURCE'),'legal_basis':'RETAINED_USER_LOCAL_SOURCE',
                       'path':str(path.resolve()),'sha256':sha(raw),'bytes':len(raw),'downloaded_at':None,
                       'recorded_at':utc(),'reused_local':True,**checks}
                break
            if saved is None and not any(o['source'] not in blocked for r,o in options):continue
            attempted+=1
            for rec,option in sorted(options,key=lambda pair:({'cvf':0,'pmlr':1,'openreview':2,'arxiv':3}.get(pair[1]['source'],9),pair[1]['url'])) if saved is None else []:
                source=option['source']
                if source in blocked:continue
                try:
                    raw,proof=co.clients[source].get(option['url'],max_bytes=cfg['max_pdf_bytes'])
                    checks=inspect_pdf(raw,rec['title'],cfg['min_pdf_chars'],rec.get('authors',[]));digest=sha(raw)
                    path=co.ws/'sources/multisource/fulltexts'/(digest+'.pdf')
                    path.parent.mkdir(parents=True,exist_ok=True)
                    if path.exists():
                        if sha(path.read_bytes())!=digest:raise ValueError('Immutable PDF integrity failure')
                    else:
                        with path.open('xb') as f:f.write(raw)
                    saved={'family_id':fid,'record_id':rec['record_id'],'source':source,
                           'original_url':option.get('original_attachment_url',option['url']),'request_url':option['url'],'final_url':proof['final_url'],'landing_url':rec['landing_url'],
                           'version':option['version'],'legal_basis':option['legal_basis'],'sha256':digest,'bytes':len(raw),
                           'path':str(path.resolve()),'downloaded_at':proof['fetched_at'],'recorded_at':utc(),
                           'reused_local':False,'source_response':proof,**checks};break
                except SourcePause as exc:
                    failures.append({'family_id':fid,**exc.info})
                    if exc.info['kind']=='RESPONSE_SIZE_BOUND':
                        failures_by_option[option_key(rec,option)]={'family_id':fid,'record_id':rec['record_id'],
                            'url':option['url'],'kind':'RESPONSE_SIZE_BOUND','max_bytes':cfg['max_pdf_bytes'],
                            'observed_at':utc(),'resume_after':time.time()+86400}
                    if exc.info['kind'] not in ('NOT_FOUND','RESPONSE_SIZE_BOUND'):blocked.add(source)
                except (ValueError,RuntimeError) as exc:
                    if 'integrity' in str(exc).lower():raise
                    failures.append({'family_id':fid,'source':source,'error':str(exc)[:250]})
            if saved:
                saved['status']='PDF_IDENTITY_CHECKED_NOT_S1_OR_FULLTEXT_REVIEWED'
                key=stable({'family':fid,'sha256':saved['sha256'],'version':saved['version']})
                co.catalog.data['downloads'][key]=saved
                provenance=co.ws/'sources/multisource/provenance'/(key+'.json')
                if not provenance.exists():write(provenance,saved)
                ready.append(saved);co.save()
        co.save()
        report={'status':'OA_CHECKPOINT_SAVED','at':utc(),'ready':ready,'failed':failures,
                'physical_requests':co.budget['sent'],'attempted_families':attempted,
                'reading_rounds_completed':0,'existing_input_and_native_tasks_untouched':True}
        write(co.root/'runs'/('oa_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json'),report)
        return report
