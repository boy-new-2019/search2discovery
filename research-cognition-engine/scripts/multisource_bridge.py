"""Connect standalone multi-source acquisition to the original reader and evidence store."""
from __future__ import annotations
import pathlib,shutil
import store

def catalog(ws):
    if not (ws/'source_routing.json').is_file():return None
    from literature_sources.catalog import Catalog
    return Catalog(ws)

def category(family):return (family.get('legacy_categories') or [family.get('screened_candidate_category')])[0]

def downloads(ws):
    cat=catalog(ws)
    if cat is None:return []
    active=cat.active();rows=[]
    for item in cat.usable_downloads().values():
        p=pathlib.Path(item['path']).resolve()
        if not p.is_relative_to(ws.resolve()) or not p.is_file() or store.hashbytes(p.read_bytes())!=item['sha256']:
            raise ValueError('Multi-source fulltext path/hash integrity failed')
        family=active.get(item['family_id'])
        if family is None:raise ValueError('Downloaded source identity is not an active family')
        rows.append({**item,'category':category(family)})
    return rows

def downloadable_core(ws):
    cat=catalog(ws)
    if cat is None:return 0
    done={x['family_id'] for x in downloads(ws)}
    return sum(category(f)=='core' and fid not in done and any(cat.data['records'][rid].get('fulltexts') for rid in f['record_ids'])
        for fid,f in cat.active().items())

def sync(ws):
    cat=catalog(ws)
    if cat is None:return {'status':'NOT_ENABLED','imported':0}
    result=cat.sync_memory();rows=downloads(ws);seen={}
    inputs=ws/'input'
    if inputs.exists():
        for p in inputs.rglob('*.pdf'):seen[store.hashbytes(p.read_bytes())]=p
    imported=0;materialized=[]
    for item in rows:
        with store.connect(ws) as c:
            existing=c.execute('SELECT work_id FROM sources WHERE file_sha=?',(item['sha256'],)).fetchone()
        wid=existing['work_id'] if existing else item['family_id']
        store.import_source(ws,wid,pathlib.Path(item['path']));imported+=not bool(existing)
        if item['category'] not in ('core','related'):continue
        if item['sha256'] in seen:continue
        dest=inputs/('multisource_'+item['category'])/(item['sha256']+'.pdf')
        dest.parent.mkdir(parents=True,exist_ok=True)
        # Exclusive creation never overwrites a researcher file.
        try:
            with dest.open('xb') as f:f.write(pathlib.Path(item['path']).read_bytes())
        except FileExistsError:
            if store.hashbytes(dest.read_bytes())!=item['sha256']:raise ValueError('Reader input integrity mismatch')
        seen[item['sha256']]=dest;materialized.append(dest.relative_to(ws).as_posix())
    return {**result,'imported':imported,'materialized_inputs':materialized,'scientific_claims_created':0}

def venue_records(ws):
    cat=catalog(ws)
    if cat is None:return {}
    result={}
    for fid,family in cat.active().items():
        rec=cat.data['records'][family['record_ids'][0]]
        result[fid]={'id':fid,'venue':rec.get('venue',''),'year':rec.get('year'),
            'category_sources':[category(family)],'source_id':'','venue_type':'UNKNOWN_VERIFY_SOURCE',
            'oa_pdf_url':next((o['url'] for rid in family['record_ids'] for o in cat.data['records'][rid].get('fulltexts',[])),'')}
    return result

def pending_reader_inputs(ws,state=None):
    """Authenticated acquired files can enter screening before bibliography completeness."""
    if state and state.get('frozen'):return []
    if any(not (p.parent/'commit.json').exists() for p in (ws/'output/native/tasks').glob('*/manifest.json')):return []
    known={x.get('sha256') for x in (state or {}).get('papers',[])};result=[]
    eligible={x['sha256'] for x in downloads(ws) if x['category'] in ('core','related')}
    # Acquisition ranking can change categories before ingest. Follow authentic
    # materialized file identity, not the current category-derived destination.
    for p in sorted((ws/'input').glob('multisource_*/*.pdf')):
        if p.stem not in eligible or p.stem in known:continue
        if store.hashbytes(p.read_bytes())!=p.stem:raise ValueError('Reader input integrity mismatch')
        result.append(p.relative_to(ws/'input').as_posix())
    return result
