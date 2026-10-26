#!/usr/bin/env python3
"""Bibliography-first, Pro-budget-safe preflight for Codex Windows Desktop.

Searches OpenAlex without spawning a single LLM; sources and citations are only
bibliographic metadata until actual PDFs are separately downloaded/parsed.
Three disjoint pools: core >=50, related >=150, inspiration >=50. Strictly logs
shortfalls. Staged preference: last 3 years + target venues, other recent,
3-5 years, historical foundations.
"""
from __future__ import annotations
import argparse, csv, datetime as dt, hashlib, io, ipaddress, json, os, pathlib, random
import re, shutil, socket, tempfile, time, unicodedata, urllib.error, urllib.parse, urllib.request
from collections import Counter
from typing import Any
import inspiration_diversity as diversity

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT = ROOT/'discovery_config.example.json'
VERSION = '5.0.0'
CATEGORIES = ('core','related','inspiration')
CATALOG_TARGET = ('core','related','inspiration')
YEAR_MIN = 1900


def now() -> str: return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
def canonical(obj:Any) -> str: return json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)
def sha(obj:Any)->str:return hashlib.sha256((obj if isinstance(obj,bytes) else canonical(obj).encode('utf-8'))).hexdigest()
def read(p:pathlib.Path)->Any:return json.loads(p.read_text('utf-8'))
def write(p:pathlib.Path,obj:Any):
    p.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile('w',encoding='utf-8',delete=False,dir=p.parent,prefix='.part-') as f:
        f.write(canonical(obj)+'\n');tmp=pathlib.Path(f.name)
    os.replace(tmp,p)
def text_file(p:pathlib.Path,t:str):
    p.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile('w',encoding='utf-8',delete=False,dir=p.parent,prefix='.part-') as f:
        f.write(t);tmp=pathlib.Path(f.name)
    os.replace(tmp,p)


def norm(s:str)->str:
    return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(s)).casefold()).strip()
def title_key(s:str)->str:
    return re.sub(r'[^\w]+','',norm(s))[:240]
def dated(s:str)->dt.date:return dt.date.fromisoformat(s)
def minus_years(x:dt.date,n:int)->dt.date:
    try:return x.replace(year=x.year-n)
    except ValueError:return x.replace(year=x.year-n,day=28)


def config(ws:pathlib.Path)->dict:
    path=ws/'discovery_config.json'
    if not path.is_file():raise ValueError('missingdiscovery_config.json: first run init')
    c=read(path)
    if c.get('schema_version')!=2:raise ValueError('Run migrate-v5 explicitly to convert a legacy discovery_config.json; never silently overwrite existing bibliographic research records.')
    quota=c.get('quotas')
    if not isinstance(quota,dict) or set(quota)!=set(CATEGORIES) or any(type(quota[k]) is not int or not 1<=quota[k]<=10000 for k in CATEGORIES):
        raise ValueError('Local assignment budget or reserved quota check failed at paper_discovery.config (check 58). Save the checkpoint before resuming.')
    if not c.get('category_disjoint') or not c.get('require_disjoint_counts') or not c.get('preserve_existing_main_project_files'):
        raise ValueError('Configuration schema or numeric bounds check failed at paper_discovery.config (check 60). Keep strict quality gates intact.')
    if not (1<=c.get('recent_years',0)<c.get('extension_years',0)<=30):raise ValueError('Input, evidence or workflow invariant failed at paper_discovery.config (check 61); inspect the signed task record and original source.')
    if not (1900<=c.get('oldest_publication_year',0)<=dt.date.today().year):raise ValueError('oldest_publication_yearinvalid')
    if c.get('as_of_date') is not None:dated(c['as_of_date'])
    if c.get('api',{}).get('provider')!='OpenAlex':raise ValueError('Input, evidence or workflow invariant failed at paper_discovery.config (check 64); inspect the signed task record and original source.')
    ap=c['api']
    for k,lo,hi in [('per_page',1,100),('pages_per_query_with_key',1,10),('max_requests_total',1,5000),
                     ('max_queries_per_run',1,1000),('timeout_seconds',5,90),('retry_429',0,5)]:
        if type(ap.get(k)) is not int or not lo<=ap[k]<=hi:raise ValueError('Authentic source, page quotation or evidence integrity check failed at paper_discovery.config (check 68). Never accept unverified material.')
    x=ap.get('minimum_request_interval_seconds')
    if type(x) not in (int,float) or not 0<=x<=10:raise ValueError('Input, evidence or workflow invariant failed at paper_discovery.config (check 70); inspect the signed task record and original source.')
    retrieval=c['retrieval']
    for k,lo,hi in [('max_fulltext_pdfs_per_run',0,200),('max_pdf_size_mb',1,120),('min_extractable_pdf_chars',200,20000)]:
        if type(retrieval.get(k)) is not int or not lo<=retrieval[k]<=hi:raise ValueError('Source path, lawful access or network permission check failed at paper_discovery.config (check 73). Do not bypass paywalls or source integrity checks.'+k)
    if not isinstance(c.get('queries'),dict) or set(c['queries'])!=set(CATEGORIES):raise ValueError('Source path, lawful access or network permission check failed at paper_discovery.config (check 74). Do not bypass paywalls or source integrity checks.')
    for k in ('core','related'):
        if not isinstance(c['queries'][k],list) or not all(isinstance(q,str) and len(q.strip())>8 for q in c['queries'][k]):raise ValueError('Input, evidence or workflow invariant failed at paper_discovery.config (check 76); inspect the signed task record and original source.'+k)
    if not isinstance(c['queries']['inspiration'],dict) or not c['queries']['inspiration']:raise ValueError('Input, evidence or workflow invariant failed at paper_discovery.config (check 77); inspect the signed task record and original source.')
    for domain,queries in c['queries']['inspiration'].items():
        if not isinstance(domain,str) or not re.fullmatch('[a-z][a-z_]{1,40}',domain) or not isinstance(queries,list) or not all(isinstance(q,str) and q for q in queries):raise ValueError('Input, evidence or workflow invariant failed at paper_discovery.config (check 79); inspect the signed task record and original source.')
    if not isinstance(c.get('preferred_domains'),dict) or any(type(n) is not int or n<0 for n in c['preferred_domains'].values()):raise ValueError('Input, evidence or workflow invariant failed at paper_discovery.config (check 80); inspect the signed task record and original source.')
    catdiv=diversity.load_catalog(c)
    domains=catdiv['domains']
    if set(c['queries']['inspiration'])-set(domains):
        raise ValueError('Configuration schema or numeric bounds check failed at paper_discovery.config (check 84). Keep strict quality gates intact.')
    if set(c['preferred_domains'])-set(c['queries']['inspiration']):
        raise ValueError('Configuration schema or numeric bounds check failed at paper_discovery.config (check 86). Keep strict quality gates intact.')
    for domain,qs in c['queries']['inspiration'].items():
        if len(qs)>10 or len(set(qs))!=len(qs):
            raise ValueError('Local assignment budget or reserved quota check failed at paper_discovery.config (check 89). Save the checkpoint before resuming.')
    if c['quotas']['inspiration']>=catdiv['policy']['apply_min_quota']:
        target=c['quotas']['inspiration']
        if (catdiv['policy']['min_unique_domains']>target or
            catdiv['policy']['min_macro_groups']>target or
            catdiv['policy']['min_far_distance']>target):
            raise ValueError('Frozen research topic or signed research contract mismatch at paper_discovery.config (check 95). Reconfirm boundaries; do not overwrite approved work.')
        if catdiv['policy']['max_per_domain']*len(c['queries']['inspiration'])<target:
            raise ValueError('Frozen research topic or signed research contract mismatch at paper_discovery.config (check 97). Reconfirm boundaries; do not overwrite approved work.')
        families={domains[d]['macro_group'] for d in c['queries']['inspiration']}
        if len(families)<catdiv['policy']['min_macro_groups'] or len(c['queries']['inspiration'])<catdiv['policy']['min_unique_domains']:
            raise ValueError('Frozen research topic or signed research contract mismatch at paper_discovery.config (check 100). Reconfirm boundaries; do not overwrite approved work.')

    if sum(c['preferred_domains'].values())>c['quotas']['inspiration']:raise ValueError('Frozen research topic or signed research contract mismatch at paper_discovery.config (check 102). Reconfirm boundaries; do not overwrite approved work.')
    if not c.get('main_direction') or not isinstance(c['main_direction'],str):raise ValueError('Frozen research topic or signed research contract mismatch at paper_discovery.config (check 103). Reconfirm boundaries; do not overwrite approved work.')
    if not isinstance(c.get('venue_shortlist_file'),str) or pathlib.Path(c['venue_shortlist_file']).is_absolute() or '..' in pathlib.Path(c['venue_shortlist_file']).parts:raise ValueError('Frozen research topic or signed research contract mismatch at paper_discovery.config (check 104). Reconfirm boundaries; do not overwrite approved work.')
    if not (ROOT/c['venue_shortlist_file']).is_file():raise ValueError('Frozen research topic or signed research contract mismatch at paper_discovery.config (check 105). Reconfirm boundaries; do not overwrite approved work.')
    if not isinstance(c.get('core_keywords'),list) or not c['core_keywords'] or not isinstance(c.get('related_keywords'),list) or not c['related_keywords']:
        raise ValueError('Input, evidence or workflow invariant failed at paper_discovery.config (check 107); inspect the signed task record and original source.')
    if type(c.get('topic_generic_research_mode',False)) is not bool:
        raise ValueError('topic_generic_research_modemust be boolean')
    hints=c.get('topic_editorial_venue_hints',[])
    if not isinstance(hints,list) or len(hints)>60 or any(not isinstance(t,str) or not 3<=len(t)<=120 for t in hints):
        raise ValueError('Configuration schema or numeric bounds check failed at paper_discovery.config (check 112). Keep strict quality gates intact.')
    scores=c.get('min_classification_score',{})
    if not isinstance(scores,dict) or set(scores)!=set(CATEGORIES):raise ValueError('Configuration schema or numeric bounds check failed at paper_discovery.config (check 114). Keep strict quality gates intact.')
    for name,low in [('core',2.0),('related',1.0),('inspiration',0.0)]:
        if type(scores[name]) not in (int,float) or not low<=scores[name]<=30:
            raise ValueError('Configuration schema or numeric bounds check failed at paper_discovery.config (check 117). Keep strict quality gates intact.')
    return c


def goal_contract(ws:pathlib.Path,c:dict)->str:
    # Never overwrite established mainline research. The goal can be supplied
    # by the previous skill, but editing it invalidates this campaign snapshot.
    goal=ws/'goal.md'
    return goal.read_text('utf-8') if goal.is_file() else c['main_direction']


def root_out(ws:pathlib.Path)->pathlib.Path:return ws/'output'/'discovery_preflight'


def init(ws:pathlib.Path)->dict:
    ws.mkdir(parents=True,exist_ok=True)
    dest=ws/'discovery_config.json'
    if not dest.exists():shutil.copy2(DEFAULT,dest)
    c=config(ws)
    (root_out(ws)/'downloads').mkdir(parents=True,exist_ok=True)
    return {'status':'INITIALIZED','config':str(dest),'quotas':c['quotas'],
            'protected_existing_goal':(ws/'goal.md').is_file(),'next':'run --online --max-requests 12 (only with explicit network authorization)'}



# Historical v4.5 default distribution: 42/50 inspiration minimum slots were
# locked to just nine closely related fields. Only this UNMODIFIED default is
# upgraded to the broad v5 distribution automatically. Custom user quotas are
# preserved or rejected if incompatible, never silently overwritten.
LEGACY_V45_DOMAINS={'nobel_economics':6,'philosophy':5,'sociology':5,
                    'cognitive_science':5,'mathematics':5,'complex_systems':5,
                    'ecology':4,'history_of_science':4,'design_theory':3}


def migrate_v5(ws:pathlib.Path)->dict:
    """Explicit and reversible catalog migration, retaining verified metadata.

    Results are NEVER silently considered v5-complete: new diversity constraints
    require reclassification and additional queries. The previous v4.5 data and
    outputs are copied to an immutable archive before any write takes place.
    """
    config_path=ws/'discovery_config.json'
    if not config_path.is_file():
        return {'status':'NO_EXISTING_CONFIG','next':'run init to create v5 config'}
    old=read(config_path)
    if old.get('schema_version')==2:
        c=config(ws)
        return {'status':'ALREADY_V5','schema_version':2,'current_targets':c['quotas']}
    if old.get('schema_version')!=1:
        raise ValueError('Local assignment budget or reserved quota check failed at paper_discovery.migrate_v5 (check 166). Save the checkpoint before resuming.')
    statepath=root_out(ws)/'state.json'
    olds=read(statepath) if statepath.exists() else None
    if olds and olds.get('contract',{}).get('config_sha256')!=sha(old):
        raise ValueError('Frozen research topic or signed research contract mismatch at paper_discovery.migrate_v5 (check 170). Reconfirm boundaries; do not overwrite approved work.')
    if olds and olds.get('contract',{}).get('goal_sha256')!=sha(goal_contract(ws,old)):
        raise ValueError('Frozen research topic or signed research contract mismatch at paper_discovery.migrate_v5 (check 172). Reconfirm boundaries; do not overwrite approved work.')
    new=read(DEFAULT)
    for key in ('main_direction','core_keywords','related_keywords','quotas','category_disjoint',
                'recent_years','extension_years','oldest_publication_year','as_of_date',
                'min_title_length','min_classification_score','top_venue_bonus',
                'require_bibliographic_links','require_disjoint_counts','stop_on_quota_complete',
                'preserve_existing_main_project_files'):
        if key in old:new[key]=old[key]
    # Anchor resumed historical searches to their original evaluation date,
    # including cases where the old run used a floating null as_of_date.
    if olds and new.get('as_of_date') is None:
        new['as_of_date']=olds['contract']['as_of_date']
    for category in ('core','related'):
        new['queries'][category]=old.get('queries',{}).get(category,new['queries'][category])
    for domain,queries in old.get('queries',{}).get('inspiration',{}).items():
        if domain in new['queries']['inspiration']:
            merged=list(queries)
            merged.extend(q for q in new['queries']['inspiration'][domain] if q not in merged)
            new['queries']['inspiration'][domain]=merged[:10]
        else:
            # A custom v4.5 domain without a v5 field definition cannot safely
            # be assigned to a macro family. Stop and request explicit mapping.
            raise ValueError('Frozen research topic or signed research contract mismatch at paper_discovery.migrate_v5 (check 194). Reconfirm boundaries; do not overwrite approved work.')
    old_preferred=old.get('preferred_domains',{})
    if old_preferred!=LEGACY_V45_DOMAINS:
        # Respect bespoke preference settings, but the old concentration may be
        # incompatible with a maximum of three per field. Fail instead of
        # silently weakening the user's old requirements.
        if (sum(old_preferred.values())>new['quotas']['inspiration'] or
            any(v>new['inspiration_diversity']['max_per_domain'] for v in old_preferred.values())):
            raise ValueError('Local assignment budget or reserved quota check failed at paper_discovery.migrate_v5 (check 202). Save the checkpoint before resuming.')
        new['preferred_domains']=old_preferred
    if 'api' in old:
        new['api'].update(old['api'])
        if old['api'].get('max_requests_total')==220:
            new['api']['max_requests_total']=420
    if 'retrieval' in old:new['retrieval'].update(old['retrieval'])
    # Backup only files owned by this discovery module, never other project
    # input/output/goal files or private research materials.
    stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    archive=root_out(ws)/('v45_backup_before_v5_'+stamp)
    if archive.exists():raise ValueError('Input, evidence or workflow invariant failed at paper_discovery.migrate_v5 (check 213); inspect the signed task record and original source.')
    archive.mkdir(parents=True,exist_ok=False)
    shutil.copy2(config_path,archive/'discovery_config.json')
    if statepath.exists():shutil.copy2(statepath,archive/'state.json')
    for f in root_out(ws).glob('discovery_*.csv'):
        shutil.copy2(f,archive/f.name)
    for f in root_out(ws).glob('discovery_*.bib'):
        shutil.copy2(f,archive/f.name)
    for name in ('discovery_report.md','discovery_progress.json','paper_library.json','query_audit.json'):
        oldoutput=root_out(ws)/name
        if oldoutput.exists():shutil.copy2(oldoutput,archive/name)
    old_config_bytes=config_path.read_bytes()
    old_state_bytes=statepath.read_bytes() if statepath.exists() else None
    try:
        write(config_path,new)
        c=config(ws)
        state=fresh_state(ws,c)
        if olds:
            for fld in ('works','queries_done','api_calls','attempt_log','download_log'):
                if fld in olds:state[fld]=olds[fld]
            state['created_at']=olds.get('created_at',state['created_at'])
            state['previous_campaign_sha256']=sha(old_state_bytes)
        state['catalog_commit_band']=None
        state['windows_completed']=[]
        state['last_status']='MIGRATED_V5_BREADTH_RECHECK_PENDING'
        report=select(ws,c,state)
        write(statepath,state)
        export(ws,c,state)
        return {'status':'V5_MIGRATED_RESUME_NEW_FIELDS',
                'backup_dir':str(archive),'retained_metadata_works':len(state['works']),
                'retained_api_queries':len(state['queries_done']),
                'new_diversity':report['inspiration_breadth'],
                'next':'run --online --max-requests 12 to fetch missing diverse fields; no model calls'}
    except Exception:
        config_path.write_bytes(old_config_bytes)
        if old_state_bytes is None:statepath.unlink(missing_ok=True)
        else:statepath.write_bytes(old_state_bytes)
        raise


def fresh_state(ws:pathlib.Path,c:dict)->dict:
    asof=dated(c['as_of_date']) if c.get('as_of_date') else dt.date.today()
    snapshot={'config_sha256':sha(c),'goal_sha256':sha(goal_contract(ws,c)),
              'venue_shortlist_sha256':sha(read(ROOT/c['venue_shortlist_file'])),
              'inspiration_domain_catalog_sha256':sha(read(ROOT/c['inspiration_domain_catalog_file'])),
              'as_of_date':asof.isoformat()}
    return {'schema_version':1,'version':VERSION,'contract':snapshot,'created_at':now(),
            'queries_done':{},'windows_completed':[], 'catalog_commit_band':None, 'works':{},'api_calls':0,'attempt_log':[],
            'download_log':{},'selection':{},'last_status':'NOT_STARTED'}


def state_at(ws:pathlib.Path,c:dict, *,create=True)->dict:
    p=root_out(ws)/'state.json'
    if not p.is_file():
        if not create:raise ValueError('Input, evidence or workflow invariant failed at paper_discovery.state_at (check 267); inspect the signed task record and original source.')
        s=fresh_state(ws,c);write(p,s);return s
    s=read(p)
    contract=fresh_state(ws,c)['contract']
    if s.get('contract')!=contract:raise ValueError('Configuration schema or numeric bounds check failed at paper_discovery.state_at (check 271). Keep strict quality gates intact.')
    return s


def queries_for(c:dict)->list[tuple[str,str,str]]:
    result=[]
    for category in ('core','related'):
        result.extend((category,'',q) for q in c['queries'][category])
    catdiv=diversity.load_catalog(c)
    domain_queries=c['queries']['inspiration']
    if c['quotas']['inspiration']<catdiv['policy']['apply_min_quota']:
        # Small test/demo collections do not need to exhaust 93 disciplines per
        # year window. Keep the classic 9-field sampler plus user requirements.
        classic=('nobel_economics','philosophy','sociology','cognitive_science',
                 'mathematics','complex_systems','ecology','history_of_science','design_theory')
        subset={d:domain_queries[d] for d in classic if d in domain_queries}
        subset.update({d:domain_queries[d] for d,count in c['preferred_domains'].items()
                       if count>0 and d in domain_queries})
        domain_queries=subset
    result.extend(('inspiration',domain,q) for domain,q in diversity.query_schedule(domain_queries,catdiv))
    return result


def windows(c:dict,asof:dt.date)->list[tuple[str,str,str]]:
    a=minus_years(asof,c['recent_years'])
    b=minus_years(asof,c['extension_years'])
    cstart=dt.date(c['oldest_publication_year'],1,1)
    return [('RECENT_3Y',a.isoformat(),asof.isoformat()),
            ('EXTENDED_3_TO_5Y',b.isoformat(),(a-dt.timedelta(days=1)).isoformat()),
            ('FOUNDATIONAL_OLDER',cstart.isoformat(),(b-dt.timedelta(days=1)).isoformat())]


def abstract_text(inv:Any)->str:
    if not isinstance(inv,dict):return ''
    word_list=[]
    for word,indexes in inv.items():
        if not isinstance(word,str) or not isinstance(indexes,list):continue
        for ix in indexes:
            if type(ix) is int and 0<=ix<=1200:word_list.append((ix,word))
    return ' '.join(w for _,w in sorted(word_list))[:6000]


def work_normalized(raw:dict,category:str,domain:str,query:str)->dict|None:
    oid=raw.get('id')
    if not isinstance(oid,str) or not re.fullmatch(r'https://openalex\.org/W\d+',oid):return None
    title=raw.get('display_name') or ''
    if not isinstance(title,str) or len(title.strip())<16:return None
    pub_date=raw.get('publication_date') or ''
    if not isinstance(pub_date,str):return None
    try:d=dated(pub_date)
    except ValueError:return None
    if d>dt.date.today()+dt.timedelta(days=40):return None
    typ=raw.get('type') or ''
    # Do not let monographs, datasets, chapters or non-scholarly metadata pad paper counts.
    if typ not in ('article','preprint','review','proceedings-article','journal-article'):return None
    pl=raw.get('primary_location') or {}
    best=raw.get('best_oa_location') or {}
    source=(pl.get('source') or {}) if isinstance(pl,dict) else {}
    venue=source.get('display_name') or ''
    venue_type=source.get('type') or ''
    pdf=(best.get('pdf_url') or '') if isinstance(best,dict) else ''
    best_landing=(best.get('landing_page_url') or '') if isinstance(best,dict) else ''
    landing=(pl.get('landing_page_url') or '') if isinstance(pl,dict) else ''
    raw_doi=raw.get('doi') or ''
    doi=raw_doi.removeprefix('https://doi.org/').removeprefix('http://doi.org/').strip().lower()
    if not doi.startswith('10.') or '/' not in doi:doi=''
    oa=raw.get('open_access') or {}
    is_oa=bool(oa.get('is_oa'))
    if not is_oa:pdf=''
    cites=raw.get('cited_by_count') or 0
    if not isinstance(cites,(int,float)) or cites<0:cites=0
    authors=[]
    for a in (raw.get('authorships') or [])[:8]:
        if not isinstance(a,dict):continue
        person=a.get('author') or {}
        if isinstance(person,dict) and person.get('display_name'):authors.append(person['display_name'])
    if not authors:return None
    return {'id':oid,'title':title.strip(),'title_key':title_key(title),'doi':doi,
            'year':d.year,'publication_date':d.isoformat(),'venue':venue,'venue_type':venue_type,
            'type':typ,'abstract':abstract_text(raw.get('abstract_inverted_index')),
            'cited_by_count':round(float(cites),2),'authors':authors,
            'oa_reported':is_oa,'oa_pdf_url':pdf,'landing_url':landing or best_landing or oid,
            'source_id':source.get('id') or '',
            'query_provenance':[{'category':category,'domain':domain,'query':query}],
            'category_sources':[category], 'inspiration_domains':[domain] if domain else [],
            'catalog_origin':'OpenAlex metadata; not fulltext inspected',
            'bibliographic_link':('https://doi.org/'+doi) if doi else oid}


def combine(old:dict,new:dict)->dict:
    out=dict(old)
    for key in ('query_provenance','category_sources','inspiration_domains'):
        values=list(old.get(key,[]))
        for v in new.get(key,[]):
            if v not in values:values.append(v)
        out[key]=values
    if not out['doi'] and new['doi']:out['doi']=new['doi'];out['bibliographic_link']=new['bibliographic_link']
    if not out['oa_pdf_url'] and new['oa_pdf_url']:out['oa_pdf_url']=new['oa_pdf_url'];out['oa_reported']=True
    if not out['venue'] and new['venue']:out['venue']=new['venue'];out['source_id']=new['source_id']
    if not out['abstract'] and new['abstract']:out['abstract']=new['abstract']
    if new['cited_by_count']>out['cited_by_count']:out['cited_by_count']=new['cited_by_count']
    return out


def priority_venue(w:dict,c:dict)->bool:
    table=read(ROOT/c['venue_shortlist_file'])
    matches=table['inspiration_priority_venues'] if 'inspiration' in w['category_sources'] and not any(x in w['category_sources'] for x in ('core','related')) else table['main_priority_venues']
    # v6.2 topic-specific editorial hints: candidate sources suggested by a
    # genuine subject-matter review; NOT an official conference/journal tier.
    if matches is table['main_priority_venues']:
        hints=c.get('topic_editorial_venue_hints',[])
        if isinstance(hints,list) and len(hints)<=60 and all(isinstance(v,str) and 2<len(v)<120 for v in hints):
            matches=matches+hints
    # A short acronym must be an independent venue token; longer names allow exact phrase.
    value=norm(w.get('venue') or '')
    if any(x in value for x in ('workshop','companion volume','extended abstract','tutorial proceedings')):
        return False
    for needle in matches:
        term=norm(needle)
        if len(term)<=5:
            if re.search(r'(?<![a-z])'+re.escape(term)+r'(?![a-z])',value):return True
        elif term==value or (len(term)>10 and term in value):return True
    return False


def paper_scores(w:dict,c:dict)->dict:
    title=norm(w['title']); abstract=norm(w.get('abstract',''))
    def score(keys):
        return round(sum((3.3 if norm(x) in title else 0)+(1.4 if norm(x) in abstract else 0) for x in set(keys) if x),2)
    core_score=score(c['core_keywords'])
    related_score=score(c['related_keywords'])
    # Legacy automotive anchor is kept for the untouched default campaign.
    # A user-selected topic must NOT be silently filtered out just because its
    # papers do not mention cars/BEV. Scientific topicality remains an S1/S2
    # judgment, not a mere keyword classifier output.
    if c.get('topic_generic_research_mode') is True:
        anchor=any(norm(k) in (title+' '+abstract) for k in c['core_keywords'] if k and len(norm(k))>=3)
    else:
        anchor=any(x in (title+' '+abstract) for x in ('driving','vehicle','automotive','camera','lidar','autonomous','perception','bev','occupancy','gaussian','3d'))
    core_eligible=(core_score>=c['min_classification_score']['core'] and anchor)
    related_eligible=(related_score>=c['min_classification_score']['related'] or (core_eligible and related_score>=1.4))
    # Exploration papers must be sourced from independent disciplinary queries;
    # the term 'driving' in an unrelated paper title does not confer mainline eligibility.
    cross_excluded=any(x in (title+' '+abstract) for x in ('autonomous driving','3d occupancy','bev occupancy',
                                    'self-driving car','lidar sensor','autonomous vehicle perception','end-to-end driving'))
    cross_eligible='inspiration' in w['category_sources'] and bool(w['inspiration_domains']) and not cross_excluded
    return {'core':core_score,'related':related_score,'core_eligible':core_eligible,
            'related_eligible':related_eligible,'inspiration_eligible':cross_eligible}


def rank(w:dict,c:dict,asof:dt.date)->tuple:
    date=dated(w['publication_date']); year3=minus_years(asof,c['recent_years']); year5=minus_years(asof,c['extension_years'])
    tier=(0 if date>=year3 else 2 if date>=year5 else 4)+(0 if priority_venue(w,c) else 1)
    return (tier, -int(priority_venue(w,c)), -w['year'], -min(w['cited_by_count'],2000),w['id'])


def select(ws:pathlib.Path,c:dict,s:dict)->dict:
    works=list(s['works'].values());asof=dated(s['contract']['as_of_date'])
    works=[w for w in works if dated(w['publication_date'])<=asof and len(w['title'])>=c['min_title_length']]
    # Semantic dedupe across OpenAlex IDs, DOI, preprint/venue title aliases.
    dedup:dict[str,dict]={}
    for w in works:
        key=w['doi'] or w['title_key']
        if not key:continue
        if key not in dedup:dedup[key]=w
        else:dedup[key]=combine(dedup[key],w)
    seen_title:dict[str,str]={}
    for key,w in list(dedup.items()):
        prior=seen_title.get(w['title_key'])
        if prior and prior in dedup:
            dedup[prior]=combine(dedup[prior],w);del dedup[key]
        else:seen_title[w['title_key']]=key
    worklist=list(dedup.values());evaluated={w['id']:paper_scores(w,c) for w in worklist}
    order=sorted(worklist,key=lambda w:rank(w,c,asof))
    result={cat:[] for cat in CATEGORIES};used=set();counts=Counter()
    catdiv=diversity.load_catalog(c)
    def take(cat,w, *,assigned_domain:str|None=None):
        if w['id'] in used or len(result[cat])>=c['quotas'][cat]:return False
        data={k:v for k,v in w.items() if k not in ('abstract','query_provenance','title_key')}
        data['record_status']='OPENALEX_METADATA_RETRIEVED_NOT_INDEPENDENTLY_VERIFIED';data['category']=cat
        data['priority_venue_shortlist_match']=priority_venue(w,c)
        data['period_bucket']=rank(w,c,asof)[0]
        data['relevance_score']=evaluated[w['id']]['core' if cat=='core' else 'related' if cat=='related' else 'inspiration_eligible']
        if cat=='inspiration':
            if assigned_domain not in catdiv['domains'] or assigned_domain not in w['inspiration_domains']:
                raise ValueError('Input, evidence or workflow invariant failed at paper_discovery.take (check 456); inspect the signed task record and original source.')
            metadata=catdiv['domains'][assigned_domain]
            data['assigned_inspiration_domain']=assigned_domain
            data['assigned_inspiration_macro_group']=metadata['macro_group']
            data['inspiration_macro_group']=metadata['macro_group']
            data['inspiration_transfer_distance']=metadata['distance_to_mainline_heuristic']
            data['inspiration_domain_label_zh']=metadata['name_zh']
            data['nobel_laureate_verified']=False
        result[cat].append(data);used.add(w['id']);return True
    for w in order:
        if evaluated[w['id']]['core_eligible'] and ('core' in w['category_sources'] or 'related' in w['category_sources']):take('core',w)
    for w in order:
        if evaluated[w['id']]['related_eligible'] and ('related' in w['category_sources'] or 'core' in w['category_sources']):take('related',w)
    proposals=diversity.diversify(order,used_ids=used,
         eligible={wid:v['inspiration_eligible'] for wid,v in evaluated.items()},
         catalog=catdiv,preferred=c['preferred_domains'],
         target=c['quotas']['inspiration'],rank=lambda w:rank(w,c,asof))
    for w,domain in proposals:take('inspiration',w,assigned_domain=domain)
    total={k:len(result[k]) for k in CATEGORIES}
    coverage=diversity.summarize(result['inspiration'],c,catdiv)
    domain_counts={d:coverage['breadth']['per_domain_counts'].get(d,0) for d in c['preferred_domains']}
    domain_gaps=coverage['preferred_domain_shortfalls']
    breadth=coverage['breadth']
    complete=(all(total[k]>=c['quotas'][k] for k in CATEGORIES) and not any(domain_gaps.values())
              and not any(breadth['shortfalls'].values()))
    gap={k:max(0,c['quotas'][k]-total[k]) for k in CATEGORIES}
    stage_sealed=bool(s.get('catalog_commit_band'))
    display_status=('CATALOG_250_PLUS_COMPLETE' if stage_sealed and complete else
                    'TARGET_COUNTS_MET_AWAITING_CURRENT_WINDOW_FINISH' if complete else
                    'INCOMPLETE_NEEDS_MORE_SOURCES')
    report={'status':display_status,
            'selected':result,'counts':total,'shortfalls':gap,
            'inspiration_domain_counts':domain_counts,'inspiration_domain_shortfalls':domain_gaps,
            'inspiration_breadth':breadth,
            'unique_selected':len(used),
            'unique_candidates_seen':len(worklist),'preferred_venue_counts':{k:sum(x['priority_venue_shortlist_match'] for x in result[k]) for k in CATEGORIES},
            'recent_3_year_counts':{k:sum(x['period_bucket'] in (0,1) for x in result[k]) for k in CATEGORIES},
            'as_of_date':asof.isoformat(), 'recent_cutoff':minus_years(asof,c['recent_years']).isoformat(),
            'note':'This section indexes existing source-verified reviewer observations. It does not certify scientific validity, novelty or new experimental outcomes.'}
    s['selection']=report;s['last_status']=report['status']
    return report


class OpenAlex:
    def __init__(self,c:dict):
        self.cfg=c['api'];self.key=os.environ.get(self.cfg.get('api_key_env','OPENALEX_API_KEY'),'').strip()
        self.last_request=0.0
    def query(self,q:str,start:str,end:str,page:int)->tuple[list[dict],dict]:
        if page>1 and not self.key:raise ValueError('OpenAlex API key is required for pagination beyond the free page limit; obtain a legitimate key or reduce page count.')
        params={'search':q,'filter':f'from_publication_date:{start},to_publication_date:{end}',
                'per_page':self.cfg['per_page'],'page':page,
                'select':'id,doi,display_name,publication_year,publication_date,primary_location,best_oa_location,open_access,cited_by_count,type,abstract_inverted_index,authorships'}
        if self.key:params['api_key']=self.key
        url='https://api.openalex.org/works?'+urllib.parse.urlencode(params)
        wait=max(0.0,self.cfg['minimum_request_interval_seconds']-(time.monotonic()-self.last_request))
        if wait:time.sleep(wait)
        request=urllib.request.Request(url,headers={'User-Agent':'BatchPaperDiscovery/1.0 (research metadata discovery; no AI requests)'})
        for attempt in range(self.cfg['retry_429']+1):
            try:
                self.last_request=time.monotonic()
                with urllib.request.urlopen(request,timeout=self.cfg['timeout_seconds']) as r:
                    obj=json.load(r)
                    if not isinstance(obj,dict) or not isinstance(obj.get('results'),list):raise ValueError('Source path, lawful access or network permission check failed at paper_discovery.query (check 518). Do not bypass paywalls or source integrity checks.')
                    return obj['results'], {'result_count':(obj.get('meta') or {}).get('count'),
                                            'rate_remaining':r.headers.get('X-RateLimit-Remaining'),'page':page}
            except urllib.error.HTTPError as exc:
                if exc.code==429 and attempt<self.cfg['retry_429']:
                    time.sleep(min(8,2**attempt));continue
                raise RuntimeError('Source path, lawful access or network permission check failed at paper_discovery.query (check 524). Do not bypass paywalls or source integrity checks.') from exc
            except (urllib.error.URLError,TimeoutError,OSError,ValueError) as exc:
                if attempt<1:
                    time.sleep(.5);continue
                raise RuntimeError('Input, evidence or workflow invariant failed at paper_discovery.query (check 528); inspect the signed task record and original source.'+type(exc).__name__+'Input, evidence or workflow invariant failed at paper_discovery.query (check 528); inspect the signed task record and original source.') from exc
        raise RuntimeError('Input, evidence or workflow invariant failed at paper_discovery.query (check 529); inspect the signed task record and original source.')


def run(ws:pathlib.Path,*,online:bool,request_limit:int|None=None,fetcher:Any=None)->dict:
    if not online:raise ValueError('Source path, lawful access or network permission check failed at paper_discovery.run (check 533). Do not bypass paywalls or source integrity checks.')
    c=config(ws);s=state_at(ws,c)
    if fetcher is None:fetcher=OpenAlex(c)
    haskey=bool(getattr(fetcher,'key',False))
    limit=min(c['api']['max_queries_per_run'],request_limit if request_limit is not None else c['api']['max_queries_per_run'])
    if limit<1:raise ValueError('--max-requests must>=1')
    calls=0
    asof=dated(s['contract']['as_of_date'])
    query_specs=queries_for(c)
    windows_list=windows(c,asof)
    result=select(ws,c,s)
    if result['status']=='CATALOG_250_PLUS_COMPLETE' and s.get('catalog_commit_band'):
        export(ws,c,s);return {'status':'ALREADY_COMPLETE','counts':result['counts'],'additional_api_requests':0}
    for band,start,end in windows_list:
        if band in s.get('windows_completed',[]):continue
        for cat,domain,q in query_specs:
            # Later-year searches prioritize only still-missing mainline categories.
            # The default research project has already searched recent venues;
            # don't spend its API quota repeating completed CORE/RELATED pools.
            if (band!='RECENT_3Y' and c['stop_on_quota_complete'] and
                    cat in ('core','related') and result['shortfalls'][cat]==0):
                continue
            pages= c['api']['pages_per_query_with_key'] if haskey else 1
            for page in range(1,pages+1):
                taskkey=sha({'band':band,'query':q,'cat':cat,'domain':domain,'page':page})[:18]
                if taskkey in s['queries_done']:continue
                if calls>=limit or s['api_calls']>=c['api']['max_requests_total']:
                    select(ws,c,s);write(root_out(ws)/'state.json',s);export(ws,c,s)
                    hard_cap=s['api_calls']>=c['api']['max_requests_total']
                    return {'status':'SOURCE_SEARCH_BUDGET_EXHAUSTED' if hard_cap else 'PAUSED_REQUEST_BUDGET','counts':s['selection']['counts'],
                            'shortfalls':s['selection']['shortfalls'],'inspiration_domain_shortfalls':s['selection']['inspiration_domain_shortfalls'],'api_requests_this_run':calls,
                            'next':'Source state and independent reviewer provenance must satisfy the specified quality gate.' if hard_cap else 'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
                try:
                    raws,meta=fetcher.query(q,start,end,page)
                except Exception as exc:
                    s['attempt_log'].append({'status':'REQUEST_ERROR','task':taskkey,'band':band,'category':cat,'query':q,
                                             'at':now(),'reason':str(exc)[:200]})
                    write(root_out(ws)/'state.json',s)
                    raise
                count_new=0
                for raw in raws:
                    record=work_normalized(raw,cat,domain,q)
                    if not record:continue
                    if dated(record['publication_date'])<dated(start) or dated(record['publication_date'])>dated(end):continue
                    old=s['works'].get(record['id'])
                    s['works'][record['id']]=combine(old,record) if old else record
                    count_new+=not bool(old)
                s['queries_done'][taskkey]={'band':band,'category':cat,'domain':domain,'query':q,
                                            'page':page,'at':now(),'api_count':len(raws),'new_ids':count_new}
                s['attempt_log'].append({'status':'OK','band':band,'category':cat,'domain':domain,'query':q,
                                         'page':page,'returned':len(raws),'new_ids':count_new,'at':now(),
                                         'remaining_external_api_budget':meta.get('rate_remaining')})
                s['api_calls']+=1;calls+=1
                write(root_out(ws)/'state.json',s)
                divcfg=diversity.load_catalog(c)
                if (c['stop_on_quota_complete'] and
                        c['quotas']['inspiration']>=divcfg['policy']['apply_min_quota'] and
                        band=='RECENT_3Y' and cat=='inspiration'):
                    candidate_report=select(ws,c,s)
                    full=(not any(candidate_report['shortfalls'].values()) and
                          not any(candidate_report['inspiration_domain_shortfalls'].values()) and
                          not any(candidate_report['inspiration_breadth']['shortfalls'].values()))
                    # Completion requires a broad and audited sweep, not merely
                    # the first few famous/close-to-AI disciplines.
                    represented={divcfg['domains'][a['domain']]['macro_group']
                                 for a in s['queries_done'].values()
                                 if a.get('band')==band and a.get('category')=='inspiration'
                                 and a.get('domain') in divcfg['domains']}
                    if full and len(represented)>=divcfg['policy']['min_macro_groups']:
                        s['catalog_commit_band']=band+':V5_DIVERSITY_QUORUM'
                        sealed=select(ws,c,s)
                        write(root_out(ws)/'state.json',s);export(ws,c,s)
                        return {'status':'CATALOG_COMPLETE','counts':sealed['counts'],
                                'api_requests_this_run':calls,'expansion_stopped_at':s['catalog_commit_band'],
                                'coverage':sealed['inspiration_breadth']}
                if not raws or len(raws)<c['api']['per_page']:
                    # Keyed pagination must not re-query nonexistent pages after resume.
                    for leftover in range(page+1,pages+1):
                        skip=sha({'band':band,'query':q,'cat':cat,'domain':domain,'page':leftover})[:18]
                        s['queries_done'][skip]={'band':band,'category':cat,'domain':domain,'query':q,
                                                'page':leftover,'at':now(),'status':'SKIPPED_NO_NEXT_PAGE'}
                    write(root_out(ws)/'state.json',s)
                    break
        result=select(ws,c,s)
        if band not in s['windows_completed']:s['windows_completed'].append(band)
        write(root_out(ws)/'state.json',s);export(ws,c,s)
        if all(result['shortfalls'][k]==0 for k in CATEGORIES) and not any(result['inspiration_domain_shortfalls'].values()) and not any(result['inspiration_breadth']['shortfalls'].values()) and c['stop_on_quota_complete']:
            s['catalog_commit_band']=band
            result=select(ws,c,s)
            write(root_out(ws)/'state.json',s);export(ws,c,s)
            return {'status':'CATALOG_COMPLETE','counts':result['counts'],'api_requests_this_run':calls,'expansion_stopped_at':band}
    result=select(ws,c,s)
    if all(result['shortfalls'][k]==0 for k in CATEGORIES) and not any(result['inspiration_domain_shortfalls'].values()) and not any(result['inspiration_breadth']['shortfalls'].values()):
        s['catalog_commit_band']=s['windows_completed'][-1] if s['windows_completed'] else 'ALL_WINDOWS_FINISHED'
        result=select(ws,c,s)
    write(root_out(ws)/'state.json',s);export(ws,c,s)
    return {'status':'CATALOG_COMPLETE' if result['status']=='CATALOG_250_PLUS_COMPLETE' else 'SOURCE_SHORTFALL_AFTER_EXPANSION',
            'counts':result['counts'],'shortfalls':result['shortfalls'],
            'inspiration_domain_shortfalls':result['inspiration_domain_shortfalls'], 'api_requests_this_run':calls,
            'exhausted_coverage':len(s['queries_done'])}


def _safe_cell(x:Any)->str:
    t=str(x if x is not None else '')
    return ("'"+t if t.lstrip().startswith(('=','+','-','@')) else t).replace('\n',' ')


def export(ws:pathlib.Path,c:dict,s:dict)->dict:
    result=s.get('selection') or select(ws,c,s)
    out=root_out(ws);out.mkdir(parents=True,exist_ok=True)
    write(out/'paper_library.json', {'provenance':'OpenAlex bibliographic metadata only','as_of_date':result['as_of_date'],
                                    'quotas':c['quotas'],'selected':result['selected']})
    write(out/'discovery_progress.json',{k:v for k,v in result.items() if k!='selected'})
    write(out/'query_audit.json',s['attempt_log'])
    columns=['category','title','year','publication_date','venue','venue_type','doi','bibliographic_link','landing_url','oa_pdf_url','oa_reported','openalex_id','cited_by_count','authors','domain','assigned_domain','macro_group','transfer_distance_heuristic','priority_venue_shortlist_match','relevance_score','record_status']
    for cat in CATEGORIES:
        filepath=out/f'discovery_{cat}_target_{c["quotas"][cat]}.csv'
        with filepath.open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=columns);w.writeheader()
            for x in result['selected'][cat]:
                values={'category':cat,'title':x['title'],'year':x['year'],'publication_date':x['publication_date'],
                        'venue':x['venue'],'venue_type':x['venue_type'],'doi':x['doi'],'bibliographic_link':x['bibliographic_link'],
                        'landing_url':x['landing_url'],'oa_pdf_url':x['oa_pdf_url'],'oa_reported':x['oa_reported'],
                        'openalex_id':x['id'],'cited_by_count':x['cited_by_count'],
                        'authors':'; '.join(x['authors']),'domain':'; '.join(x['inspiration_domains']),
                        'assigned_domain':x.get('assigned_inspiration_domain',''),
                        'macro_group':x.get('inspiration_macro_group',''),
                        'transfer_distance_heuristic':x.get('inspiration_transfer_distance',''),
                        'priority_venue_shortlist_match':x['priority_venue_shortlist_match'],
                        'relevance_score':x['relevance_score'],'record_status':x['record_status']}
                w.writerow({k:_safe_cell(v) for k,v in values.items()})
    # Citation-manager export: never invent absent authors/DOI/venue fields.
    def esc(value:Any)->str:
        return str(value).replace('\\','___BIBTEX_BACKSLASH___').replace('{','\\{').replace('}','\\}').replace('___BIBTEX_BACKSLASH___','\\textbackslash{}').replace('\n',' ')
    for cat in CATEGORIES:
        bib=[]
        for work in result['selected'][cat]:
            short=work['id'].rsplit('/',1)[-1]
            kind='inproceedings' if work.get('venue_type') in ('conference','proceedings') else 'misc' if work['type']=='preprint' else 'article'
            fields={'title':work['title'],'year':work['year'],'url':work['bibliographic_link']}
            if work.get('authors'):fields['author']=' and '.join(work['authors'])
            if work.get('venue'):fields['booktitle' if kind=='inproceedings' else 'journal']=work['venue']
            if work.get('doi'):fields['doi']=work['doi']
            bib.append('@'+kind+'{'+short+',\n'+',\n'.join('  '+k+' = {'+esc(v)+'}' for k,v in fields.items())+'\n}')
        text_file(out/f'discovery_{cat}_target_{c["quotas"][cat]}.bib','\n\n'.join(bib)+'\n')
    lines=['# Discovery Preflight: Real Bibliography and Source Audit', '',
           f'- Research direction: {c["main_direction"]}',
           f'- Reference date: {result["as_of_date"]}; recent three-year cutoff: {result["recent_cutoff"]}.',
           f'- Status: **{result["status"]}** (BIBLIOGRAPHIC METADATA only; not downloaded or read).',
           f'- Unique indexed candidates: {result["unique_candidates_seen"]}; unique selected works: {result["unique_selected"]}.', '',
           '| Category | Target | Selected authentic records | Missing | Recent three-year records | Preferred venue shortlist matches |',
           '|---|---:|---:|---:|---:|---:|']
    for category,label in [('core','Core candidate'),('related','Related candidate'),('inspiration','Cross-domain inspiration')]:
        lines.append(f'| {label} | {c["quotas"][category]} | {result["counts"][category]} | {result["shortfalls"][category]} | {result["recent_3_year_counts"][category]} | {result["preferred_venue_counts"][category]} |')
    lines+=['', '## Interdisciplinary quota coverage']
    for domain,target in c['preferred_domains'].items():
        lines.append(f'- {domain}: {result["inspiration_domain_counts"].get(domain,0)}/{target}; missing {result["inspiration_domain_shortfalls"].get(domain,0)}.')
    breadth=result.get('inspiration_breadth',{})
    lines+=['', '## v5.0 interdisciplinary breadth audit',
            f'- Distinct subdomains: {breadth.get("unique_domains",0)}/{breadth.get("required_unique_domains",0)}; '
            f'macro disciplines: {breadth.get("unique_macro_groups",0)}/{breadth.get("required_macro_groups",0)}; '
            f'distant-domain papers: {breadth.get("far_field_papers",0)}/{breadth.get("required_far_field_papers",0)}.',
            '- All diversity categories are heuristic editorial search pools; they do not certify a scientific contribution.',
            '- If any compulsory coverage or concentration test fails, the campaign is INCOMPLETE even when fifty inspiration metadata records exist.',
            f'- Deterministic random seed: {c["inspiration_diversity"]["random_seed"]}; randomness never outranks source veracity and recency.']
    family_names=diversity.load_catalog(c)['families']
    for macro,count in breadth.get('per_macro_group_counts',{}).items():
        lines.append(f'- Macro group `{macro}` ({family_names.get(macro,{}).get("name_zh",macro)}): {count} papers.')
    for dimension,gap in breadth.get('shortfalls',{}).items():
        if gap:lines.append(f'- **Unmet diversity requirement**: {dimension}: {gap}.')
    lines+=['', '## Scientific limitations and next actions',
            '- The target of fifty CORE candidates concerns bibliography; it is NOT fifty completed original v4.4 five-round reviews.',
            '- CORE, RELATED and INSPIRATION sets are mutually exclusive. Report shortfalls accurately.',
            '- Source venue rankings are editorial shortlist signals, NOT official JCR, CAS or CCF item-level certification.',
            '- DOI, OpenAlex ID and URLs require identity checks; an OA URL alone does not establish a downloaded/readable full paper.',
            '- A Nobel-related economic theme does not establish any specific Nobel laureate authorship.',
            '- API failures, rate limits, missing access and date limits must be reported without invented records.',
            '',f'Actual API requests: {s["api_calls"]}; Codex reading-agent calls in this stage: **0**.','']
    text_file(out/'discovery_report.md','\n'.join(lines))
    return {'status':result['status'],'counts':result['counts'],'shortfalls':result['shortfalls'],
            'report':str(out/'discovery_report.md'),'metadata_library':str(out/'paper_library.json'),
            'inspiration_domain_shortfalls':result['inspiration_domain_shortfalls'],
        'inspiration_breadth':result.get('inspiration_breadth',{})}


def status(ws:pathlib.Path)->dict:
    c=config(ws);s=state_at(ws,c)
    out=export(ws,c,s)
    out['api_requests']=s['api_calls'];out['fulltexts_downloaded']=sum(x.get('status')=='FULLTEXT_READY' for x in s['download_log'].values())
    out['metadata_works_indexed']=len(s['works']);out['completed_query_pages']=len(s['queries_done'])
    out['fulltext_ready_for_deepread']='CHECK_INPUT_AND_INGEST_FIRST'
    return out


def safe_url(url:str)->bool:
    try:
        p=urllib.parse.urlsplit(url)
        if p.scheme!='https' or not p.hostname or p.username or p.password or p.port not in (None,443):return False
        hostname=p.hostname.casefold()
        if hostname in ('localhost','localhost.localdomain') or hostname.endswith(('.local','.internal','.localhost')):return False
        try:return ipaddress.ip_address(hostname).is_global
        except ValueError:return True
    except (ValueError,TypeError):return False


def public_dns(hostname:str)->bool:
    try:
        answers=socket.getaddrinfo(hostname,443,type=socket.SOCK_STREAM)
        addresses={item[4][0] for item in answers}
        return bool(addresses) and all(ipaddress.ip_address(x).is_global for x in addresses)
    except (OSError,ValueError):return False


class RedirectHTTPS(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if not safe_url(newurl) or not public_dns(urllib.parse.urlsplit(newurl).hostname or ''):raise RuntimeError('Source path, lawful access or network permission check failed at paper_discovery.redirect_request (check 748). Do not bypass paywalls or source integrity checks.')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def download_pdf(url:str,dst:pathlib.Path,maxmb:int,minchars:int):
    if not safe_url(url) or not public_dns(urllib.parse.urlsplit(url).hostname or ''):
        raise ValueError('Source path, lawful access or network permission check failed at paper_discovery.download_pdf (check 754). Do not bypass paywalls or source integrity checks.')
    dst.parent.mkdir(parents=True,exist_ok=True)
    opener=urllib.request.build_opener(RedirectHTTPS)
    req=urllib.request.Request(url,headers={'User-Agent':'BatchPaperDiscovery/1.0 OA-research-lookup'})
    with tempfile.NamedTemporaryFile(dir=dst.parent,prefix='.pdftmp_',suffix='.pdf',delete=False) as f:temp=pathlib.Path(f.name)
    try:
        size=0
        with opener.open(req,timeout=35) as r,temp.open('wb') as out:
            if not safe_url(r.geturl()):raise ValueError('Source path, lawful access or network permission check failed at paper_discovery.download_pdf (check 762). Do not bypass paywalls or source integrity checks.')
            for buf in iter(lambda:r.read(64*1024),b''):
                size+=len(buf)
                if size>maxmb*1024*1024:raise ValueError('Source path, lawful access or network permission check failed at paper_discovery.download_pdf (check 765). Do not bypass paywalls or source integrity checks.')
                out.write(buf)
        with temp.open('rb') as header_file:
            if header_file.read(5)!=b'%PDF-':
                raise ValueError('OA response is not a PDF (missing %PDF- signature); file discarded.')
        try:
            import fitz  # optional AGPL/commercial parser
        except ImportError:
            try:
                from pypdf import PdfReader  # BSD-3-Clause fallback
            except ImportError as exc:
                raise ValueError('PDF validation needs pypdf>=4 or a separately licensed PyMuPDF installation') from exc
            reader=PdfReader(str(temp))
            if reader.is_encrypted:
                raise ValueError('Cannot verify encrypted PDF full text')
            text_length=sum(len(page.extract_text() or '') for page in reader.pages)
        else:
            doc=fitz.open(str(temp))
            try:
                if doc.needs_pass:
                    raise ValueError('Cannot verify encrypted PDF full text')
                text_length=sum(len(page.get_text('text')) for page in doc)
            finally:doc.close()
        if text_length<minchars:raise ValueError('Authentic source, page quotation or evidence integrity check failed at paper_discovery.download_pdf (check 774). Never accept unverified material.')
        os.replace(temp,dst)
    finally:temp.unlink(missing_ok=True)


def obtain_fulltexts(ws:pathlib.Path,*,online:bool,category:str,limit:int|None=None,download_fn=None)->dict:
    if not online:raise ValueError('Source path, lawful access or network permission check failed at paper_discovery.obtain_fulltexts (check 780). Do not bypass paywalls or source integrity checks.')
    if category not in CATEGORIES:raise ValueError('Source path, lawful access or network permission check failed at paper_discovery.obtain_fulltexts (check 781). Do not bypass paywalls or source integrity checks.')
    c=config(ws);s=state_at(ws,c)
    if not s.get('selection'):raise ValueError('Source path, lawful access or network permission check failed at paper_discovery.obtain_fulltexts (check 783). Do not bypass paywalls or source integrity checks.')
    max_items=c['retrieval']['max_fulltext_pdfs_per_run']
    if limit is not None:max_items=min(max_items,limit)
    if max_items<=0:return {'status':'DOWNLOAD_DISABLED','files':[]}
    fn=download_fn or download_pdf
    attempted=0;downloaded=[];failed=[]
    for rec in s['selection']['selected'][category]:
        if attempted>=max_items:break
        entry=s['download_log'].get(rec['id'])
        if entry and entry.get('status')=='FULLTEXT_READY':
            dest=ws/entry['relative_path']
            if not dest.is_file() or hashlib.sha256(dest.read_bytes()).hexdigest()!=entry['sha256']:
                raise ValueError('Source path, lawful access or network permission check failed at paper_discovery.obtain_fulltexts (check 795). Do not bypass paywalls or source integrity checks.')
            continue
        pdf=rec.get('oa_pdf_url')
        if not pdf:continue
        if not safe_url(pdf):
            failed.append({'id':rec['id'],'reason':'Source state and independent reviewer provenance must satisfy the specified quality gate.'})
            continue
        attempted+=1
        filename='discovery_'+rec['id'].rsplit('/',1)[-1]+'.pdf'
        if category=='inspiration':
            domain=rec.get('assigned_inspiration_domain') or (rec.get('inspiration_domains') or ['other'])[0]
            dst=ws/'cross_domain_input'/domain/filename
        else:
            dst=ws/'input'/('discovery_'+category)/filename
        if dst.exists():
            # No automatic replacement of an existing project file.
            failed.append({'id':rec['id'],'reason':'Source state and independent reviewer provenance must satisfy the specified quality gate.'})
            continue
        try:
            fn(pdf,dst,c['retrieval']['max_pdf_size_mb'],c['retrieval']['min_extractable_pdf_chars'])
            digest=hashlib.sha256(dst.read_bytes()).hexdigest()
            s['download_log'][rec['id']]={'status':'FULLTEXT_READY','category':category,
                                          'relative_path':dst.relative_to(ws).as_posix(),
                                          'sha256':digest,'source_url':pdf,'downloaded_at':now()}
            downloaded.append(dst.relative_to(ws).as_posix())
        except Exception as exc:
            failed.append({'id':rec['id'],'reason':str(exc)[:240]})
            s['download_log'][rec['id']]={'status':'FULLTEXT_FAILED','category':category,
                                          'source_url':pdf,'reason':str(exc)[:240],'last_attempt':now()}
        write(root_out(ws)/'state.json',s)
    return {'status':'DOWNLOAD_PARTIAL' if failed else 'DOWNLOAD_BATCH_DONE','downloaded':downloaded,
            'failed':failed,'attempted':attempted,'note':'Research evidence and workflow notes (paper_discovery.obtain_fulltexts). Use original source evidence; keep frozen constraints and independent quality gates.'}


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description='Research evidence and workflow notes (paper_discovery.main). Use original source evidence; keep frozen constraints and independent quality gates.')
    sub=p.add_subparsers(dest='op',required=True)
    for cmd in ('init','run','status','export','download','migrate-v5'):
        sp=sub.add_parser(cmd);sp.add_argument('--workspace',required=True,type=pathlib.Path)
        if cmd in ('run','download'):sp.add_argument('--online',action='store_true',help='Source state and independent reviewer provenance must satisfy the specified quality gate.')
        if cmd=='run':sp.add_argument('--max-requests',type=int,default=None)
        if cmd=='download':sp.add_argument('--category',choices=CATEGORIES,default='core');sp.add_argument('--limit',type=int,default=None)
    x=p.parse_args(argv);ws=x.workspace.expanduser().resolve()
    try:
        if x.op=='init':response=init(ws)
        elif x.op=='migrate-v5':response=migrate_v5(ws)
        elif x.op=='run':response=run(ws,online=x.online,request_limit=x.max_requests)
        elif x.op=='status':response=status(ws)
        elif x.op=='export':c=config(ws);response=export(ws,c,state_at(ws,c))
        else:response=obtain_fulltexts(ws,online=x.online,category=x.category,limit=x.limit)
        print(canonical(response));return 0
    except (ValueError,OSError,RuntimeError,KeyError,TypeError) as exc:
        print(canonical({'status':'BLOCKED','operation':x.op,'reason':str(exc)}),file=__import__('sys').stderr);return 2

if __name__=='__main__':raise SystemExit(main())
