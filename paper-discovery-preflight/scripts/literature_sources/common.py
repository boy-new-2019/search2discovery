"""Utilities shared by the source adapters; no scientific judgements."""
import contextlib,datetime as dt,hashlib,json,os,pathlib,re,tempfile,time,unicodedata
def utc():return dt.datetime.now(dt.timezone.utc).isoformat()
def sha(data):return hashlib.sha256(data).hexdigest()
def stable(obj):return sha(json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode())
def read(path):return json.loads(path.read_text('utf-8'))
def write(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,delete=False) as f:
        json.dump(obj,f,ensure_ascii=False,indent=2);f.write('\n');tmp=f.name
    os.replace(tmp,path)
def norm(text):return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(text))).strip()
def title_key(text):return re.sub(r'[^\w]','',norm(text).casefold())
def doi_id(value):
    value=norm(value).lower()
    value=re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)','',value)
    return value if re.fullmatch(r'10\.\d{4,9}/\S+',value) else ''
def arxiv_id(value):
    value=str(value)
    m=re.search(r'(?:arxiv:|/abs/|/pdf/)?((?:\d{4}\.\d{4,5}|[a-zA-Z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?)',value,re.I)
    if not m:return '',None
    text=m.group(1);version=re.search(r'v(\d+)$',text)
    return re.sub(r'v\d+$','',text),int(version.group(1)) if version else None
@contextlib.contextmanager
def locked(folder,sleep=time.sleep):
    folder.mkdir(parents=True,exist_ok=True);lock=folder/'.lock'
    for _ in range(120):
        try:lock.mkdir();break
        except FileExistsError:sleep(.05)
    else:raise RuntimeError('Source state is locked by another process; checkpoint retained')
    try:yield
    finally:lock.rmdir()
SOURCES=('arxiv','cvf','pmlr','openreview','crossref','openalex')
DEFAULTS={
 'schema_version':1,'enabled':True,
 'routes':{'ai':['arxiv','cvf','pmlr','openreview','crossref','openalex'],
           'cross_disciplinary':['crossref','openalex','arxiv','pmlr','openreview','cvf']},
 'providers':{s:{'enabled':True,'minimum_interval':3.1 if s=='arxiv' else 1.1,
                 'timeout':18,'max_retries':1,'max_wait':8,'max_requests_per_run':4,'max_lifetime_requests':500}
              for s in SOURCES},
 'cvf_venues':['CVPR','ICCV','WACV'],'pmlr_venues':['ICML','CoRL','AISTATS','COLT'],
 'lookback_years':3,'page_size':20,'max_index_units_per_task':2,
 'max_pdfs_per_run':4,'max_pdf_bytes':33554432,'min_pdf_chars':600,
 'primary_sources':['arxiv','cvf','pmlr','openreview']}
def config(ws):
    cfg=read(ws/'source_routing.json')
    if cfg.get('schema_version')!=1 or cfg.get('enabled') is not True:raise ValueError('Invalid source routing configuration')
    if set(cfg['providers'])!=set(SOURCES):raise ValueError('All six source policies must be explicit')
    for s,p in cfg['providers'].items():
        for name,lo,hi in [('minimum_interval',.1,60),('timeout',1,90),('max_retries',0,4),
                           ('max_requests_per_run',1,100),('max_lifetime_requests',1,10000),('max_wait',0,30)]:
            value=p[name]
            if not isinstance(value,(int,float)) or isinstance(value,bool) or not lo<=value<=hi:raise ValueError('Invalid provider policy: '+s+'.'+name)
        if s=='arxiv' and p['minimum_interval']<3:raise ValueError('arXiv requires at least three-second spacing')
    for route in cfg['routes'].values():
        if not route or len(route)!=len(set(route)) or set(route)-set(SOURCES):raise ValueError('Invalid route')
    if not 1<=cfg['page_size']<=100 or not 1<=cfg['max_pdfs_per_run']<=20:raise ValueError('Invalid retrieval bounds')
    return cfg