"""Official-source metadata parsers and bounded search/page adapters."""
from __future__ import annotations
import datetime as dt,json,re,urllib.parse,xml.etree.ElementTree as ET
from html.parser import HTMLParser
from .common import norm,doi_id,arxiv_id,stable,utc
from .transport import SourcePause
def urljoin(base,link):return urllib.parse.urljoin(base,str(link))
def value(content,key,default=''):
    item=content.get(key,default)
    return item.get('value',default) if isinstance(item,dict) else item
def record(source,key,title,**kw):
    return {'record_id':source+':'+str(key),'source':source,'source_record_id':str(key),
            'title':norm(title),'authors':[],'doi':'','arxiv_id':'','arxiv_version':None,
            'year':None,'publication_date':None,'date_precision':'UNKNOWN','venue':'',
            'publication_status':'METADATA_ONLY','version':'UNKNOWN','landing_url':'',
            'abstract':'','fulltexts':[],'citation_count':None,'observed_at':utc(),**kw}
def oa(source,url,version,legal):
    return {'source':source,'url':url,'version':version,'legal_basis':legal}
class HTML(HTMLParser):
    """Collect public citation metadata, links and named text; never execute HTML."""
    def __init__(self,text,base):
        super().__init__(convert_charrefs=True);self.base=base;self.links=[];self.meta={};self.ids={};self.stack=[];self.active=None;self.papers=[];self.paper=None
        self.feed(text)
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='meta':
            name=a.get('name') or a.get('property')
            if name and a.get('content'):self.meta.setdefault(name.casefold(),[]).append(a['content'])
        if tag=='div' and 'paper' in a.get('class','').split():self.paper={'title':'','links':[]};self.papers.append(self.paper)
        if tag not in ('meta','link','img','br','hr','input','source','wbr'):self.stack.append((tag,a.get('id',''),a.get('class','')))
        if tag=='a':
            self.active={'url':urljoin(self.base,a.get('href','')),'label':''};self.links.append(self.active)
            if self.paper:self.paper['links'].append(self.active)
    def handle_endtag(self,tag):
        if tag=='a':self.active=None
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag:
                dropped=self.stack[i:];self.stack=self.stack[:i]
                if any(x[0]=='div' and 'paper' in x[2].split() for x in dropped):self.paper=None
                break
    def handle_data(self,data):
        if self.active:self.active['label']+=data
        for tag,ident,cls in self.stack:
            if ident in ('papertitle','authors','abstract'):self.ids[ident]=self.ids.get(ident,'')+data
            if self.paper and tag=='p' and 'title' in cls.split():self.paper['title']+=data
    def first(self,key):return (self.meta.get(key) or [''])[0]
    def paper_record(self,source,url):
        title=self.first('citation_title') or norm(self.ids.get('papertitle',''))
        if not title:return None
        authors=self.meta.get('citation_author') or [norm(x) for x in self.ids.get('authors','').split(',') if norm(x)]
        date=self.first('citation_publication_date') or self.first('citation_date')
        year_match=re.search(r'(20\d{2}|19\d{2})',date or url)
        year=int(year_match.group()) if year_match else None
        pdf=self.first('citation_pdf_url') or next((x['url'] for x in self.links if x['url'].split('?')[0].lower().endswith('.pdf') and not any(t in x['url'].lower() for t in ('supplement','supp.pdf'))),'')
        preprint=next((x['url'] for x in self.links if 'arxiv.org/' in x['url']),'');aid,av=arxiv_id(preprint)
        workshop=bool(re.search(r'workshop|CVPR\d{4}W|ICCV\d{4}W',url,re.I))
        version='ACCEPTED_OPEN_ACCESS'
        return record(source,url,title,authors=authors,year=year,
            doi=doi_id(self.first('citation_doi')),arxiv_id=aid,arxiv_version=av,
            venue=self.first('citation_conference_title') or self.first('citation_journal_title') or
                  ('CVF workshop' if workshop else 'CVF main proceedings') if source=='cvf' else
                  self.first('citation_conference_title') or self.first('citation_journal_title') or 'PMLR',
            publication_status='PUBLISHED_WORKSHOP' if workshop else 'PUBLISHED_PROCEEDINGS',
            version=version,landing_url=url,abstract=norm(self.ids.get('abstract','')),
            fulltexts=[oa(source,urljoin(url,pdf),version,'OFFICIAL_OPEN_ACCESS_REPOSITORY')] if pdf else [])
def disciplinary_anchor(query):
    stop={'a','an','and','or','the','of','for','to','in','on','with','under','from','by'}
    return ' '.join(t for t in re.findall(r'[\w-]+',query.casefold()) if t not in stop).split()[:2]

def query_phrases(query,*,disciplinary=False):
    """Bounded lexical broad retrieval; reviewed query text remains the task identity."""
    if disciplinary:return [' '.join(disciplinary_anchor(query))]
    tokens=re.findall(r'[\w-]+',query.casefold())
    stop={'a','an','and','or','the','of','for','to','in','on','with','under','from','by'}
    pairs=[' '.join((a,b)) for a,b in zip(tokens,tokens[1:]) if a not in stop and b not in stop]
    return list(dict.fromkeys(pairs or [t for t in tokens if t not in stop]))[:24]

def title_query_match(title,query,*,disciplinary=False):
    # Long reviewed queries describe several facets, not a verbatim paper title.
    # Retrieval admits candidates only; downstream scoring and S1/S2 decide relevance.
    text=norm(title).casefold()
    return any(re.search(r'(?<!\w)'+re.escape(phrase)+r'(?!\w)',text) for phrase in query_phrases(query,disciplinary=disciplinary))

class Arxiv:
    name='arxiv'
    def __init__(self,http,cfg):self.http=http;self.cfg=cfg
    def search(self,task,cursor):
        start=int(cursor or 0);size=self.cfg['page_size'];q=task['query']
        quoted=' OR '.join('all:"'+phrase+'"' for phrase in query_phrases(q,disciplinary=task.get('category')=='inspiration'))
        date=f"submittedDate:[{task['start'].replace('-','')}0000 TO {task['end'].replace('-','')}2359]"
        url='https://export.arxiv.org/api/query?'+urllib.parse.urlencode({'search_query':f'({quoted}) AND {date}','start':start,'max_results':size,'sortBy':'submittedDate','sortOrder':'descending'})
        raw,proof=self.http.get(url);root=ET.fromstring(raw)
        ns={'a':'http://www.w3.org/2005/Atom','x':'http://arxiv.org/schemas/atom','o':'http://a9.com/-/spec/opensearch/1.1/'}
        if root.find('a:entry/a:id',ns) is not None and 'api/errors' in root.findtext('a:entry/a:id','',ns):raise SourcePause(self.name,'API_QUERY_ERROR')
        rows=[]
        for e in root.findall('a:entry',ns):
            link=e.findtext('a:id','',ns);aid,v=arxiv_id(link)
            if not aid:continue
            date=e.findtext('a:published','',ns)[:10];title=e.findtext('a:title','',ns)
            pdf=next((x.attrib['href'] for x in e.findall('a:link',ns) if x.attrib.get('title')=='pdf'),'')
            pdf=pdf.replace('http://','https://') if pdf else 'https://arxiv.org/pdf/'+aid+(f'v{v}' if v else '')
            rows.append(record(self.name,aid+(f'v{v}' if v else ''),title,
                authors=[x.findtext('a:name','',ns) for x in e.findall('a:author',ns)],
                arxiv_id=aid,arxiv_version=v,doi=doi_id(e.findtext('x:doi','',ns)),
                year=int(date[:4]) if date else None,publication_date=date or None,date_precision='DAY' if date else 'UNKNOWN',
                venue=e.findtext('x:journal_ref','',ns) or 'arXiv',publication_status='PREPRINT',
                version=f'arXiv v{v}' if v else 'ARXIV_VERSION_NOT_SPECIFIED',landing_url=link.replace('http://','https://'),
                abstract=norm(e.findtext('a:summary','',ns)),source_response=proof,
                fulltexts=[oa(self.name,pdf,f'arXiv v{v}' if v else 'LATEST_AT_FETCH','ARXIV_PUBLIC_FULLTEXT')]))
        total=int(root.findtext('o:totalResults',str(start+len(rows)),ns))
        return rows,str(start+size) if start+len(rows)<total and rows else None
class CVF:
    name='cvf'
    def __init__(self,http,cfg):self.http=http;self.cfg=cfg
    def units(self,task):
        years=range(int(task['end'][:4]),int(task['start'][:4])-1,-1)
        return [f'https://openaccess.thecvf.com/{v}{y}?day=all' for y in years for v in self.cfg['cvf_venues'] if v!='ICCV' or y%2==1]
    def search(self,task,cursor):
        state=json.loads(cursor) if cursor else {'unit':0,'paper':0}
        if 'units' not in state:state['units']=self.units(task)
        units=state['units']
        if state['unit']>=len(units):return [],None
        url=units[state['unit']]
        try:raw,proof=self.http.get(url,max_bytes=32*1024*1024)
        except SourcePause as e:
            if e.info['kind']=='NOT_FOUND':
                state={**state,'unit':state['unit']+1,'paper':0}
                return [],json.dumps(state) if state['unit']<len(units) else None
            raise
        doc=HTML(raw.decode('utf-8','replace'),url)
        matches=[x for x in doc.links if '_paper.html' in x['url'] and title_query_match(x['label'],task['query'],disciplinary=task.get('category')=='inspiration')]
        # An offset is committed only after each bounded detail page succeeds.
        if state['paper']<len(matches):
            item=matches[state['paper']];body,detail=self.http.get(item['url'])
            rec=HTML(body.decode('utf-8','replace'),item['url']).paper_record(self.name,item['url'])
            state['paper']+=1;out=[{**rec,'source_response':detail,'index_response':proof}] if rec else []
        else:
            state={**state,'unit':state['unit']+1,'paper':0};out=[]
        return out,json.dumps(state) if state['unit']<len(units) else None
class PMLR(CVF):
    name='pmlr'
    def units(self,task):
        url='https://proceedings.mlr.press/';raw,proof=self.http.get(url)
        doc=HTML(raw.decode('utf-8','replace'),url);result=[]
        # Official volume links have adjacent venue/year text in the index.
        text=raw.decode('utf-8','replace')
        for entry in re.findall(r'<li\b[^>]*>(.*?)</li>',text,re.I|re.S):
            part=HTML(entry,url);trail=re.sub('<[^>]+>',' ',entry)
            volume=next((x['url'] for x in part.links if re.search(r'/v\d+/?(?:index\.html)?$',x['url'])),'')
            years=re.findall(r'\b20\d{2}\b',trail)
            if volume and years and int(task['start'][:4])<=int(years[0])<=int(task['end'][:4]) and any(re.search(r'\b'+re.escape(v)+r'\b',trail,re.I) for v in self.cfg['pmlr_venues']):
                result.append(volume)
        return list(dict.fromkeys(result))
    def search(self,task,cursor):
        state=json.loads(cursor) if cursor else {'unit':0,'paper':0}
        if 'units' not in state:state['units']=self.units(task)
        units=state['units']
        if state['unit']>=len(units):return [],None
        url=units[state['unit']];raw,proof=self.http.get(url);doc=HTML(raw.decode('utf-8','replace'),url)
        matches=[p for p in doc.papers if title_query_match(p['title'],task['query'],disciplinary=task.get('category')=='inspiration')]
        if state['paper']<len(matches):
            item=matches[state['paper']]
            link=next((x['url'] for x in item['links'] if urllib.parse.urlsplit(x['url']).path.endswith('.html')),'')
            if not link:state['paper']+=1;return [],json.dumps(state)
            body,detail=self.http.get(link);rec=HTML(body.decode('utf-8','replace'),link).paper_record(self.name,link)
            state['paper']+=1;out=[{**rec,'source_response':detail,'index_response':proof}] if rec else []
        else:state={**state,'unit':state['unit']+1,'paper':0};out=[]
        return out,json.dumps(state) if state['unit']<len(units) else None
class OpenReview:
    name='openreview'
    def __init__(self,http,cfg):self.http=http;self.cfg=cfg
    def search(self,task,cursor):
        offset=int(cursor or 0);size=self.cfg['page_size']
        version=str(task.get('api_version','2'))
        if version not in ('1','2'):raise ValueError('OpenReview api_version must be 1 or 2')
        params={'term':task['query'],'content':'title','source':'forum','limit':size,'offset':offset,'sort':'cdate:desc'}
        for key in ('venueid','invitation'):
            if task.get(key):params[key]=task[key]
        host='api2.openreview.net' if version=='2' else 'api.openreview.net'
        url='https://'+host+'/notes/search?'+urllib.parse.urlencode(params)
        raw,proof=self.http.get(url);obj=json.loads(raw)
        if not isinstance(obj.get('notes'),list):raise SourcePause(self.name,'UNEXPECTED_PUBLIC_API_SCHEMA')
        rows=[]
        for note in obj['notes']:
            c=note.get('content') or {};title=value(c,'title');pdf=value(c,'pdf')
            if not title or not pdf:continue
            date=dt.datetime.fromtimestamp((note.get('pdate') or note.get('cdate') or note.get('tcdate') or 0)/1000,dt.timezone.utc).date().isoformat()
            venue=norm(value(c,'venue') or value(c,'venueid'))
            status='PUBLIC_SUBMISSION_ACCEPTANCE_UNVERIFIED'
            if any(t in venue.casefold() for t in ('reject','withdraw')):status='REJECTED_OR_WITHDRAWN_PUBLIC_NOTE'
            rows.append(record(self.name,note['id'],title,authors=value(c,'authors',[]),
                doi=doi_id(value(c,'doi')),year=int(date[:4]),publication_date=date,date_precision='DAY',
                venue=venue,publication_status=status,version='OPENREVIEW_NOTE_AT_'+str(note.get('mdate') or note.get('tmdate') or ''),
                landing_url='https://openreview.net/forum?id='+note['id'],abstract=norm(value(c,'abstract')),
                fulltexts=([oa(self.name,'https://openreview.net/pdf?id='+urllib.parse.quote(note['id'],safe=''),'PUBLIC_NOTE_PDF','PUBLIC_OPENREVIEW_ATTACHMENT')]
                           if str(pdf).startswith(('/pdf/', '/pdf?')) and (not note.get('readers') or 'everyone' in note['readers']) else []),
                original_pdf_attachment=pdf,public_readers=note.get('readers'),api_version=version,venue_id=value(c,'venueid'),
                source_response=proof))
        count=int(obj.get('count',offset+len(obj['notes'])))
        return rows,str(offset+size) if offset+len(obj['notes'])<count and obj['notes'] else None
class Crossref:
    name='crossref'
    def __init__(self,http,cfg):self.http=http;self.cfg=cfg
    def search(self,task,cursor):
        explicit=doi_id(task.get('doi',''))
        url='https://api.crossref.org/works/'+urllib.parse.quote(explicit,safe='') if explicit else 'https://api.crossref.org/works?'+urllib.parse.urlencode({
            'query.bibliographic':task['query'],'rows':self.cfg['page_size'],'offset':int(cursor or 0),
            'filter':f'from-pub-date:{task["start"]},until-pub-date:{task["end"]}'})
        raw,proof=self.http.get(url);obj=json.loads(raw);message=obj.get('message',{})
        items=[message] if explicit else message.get('items',[])
        rows=[]
        for item in items:
            doi=doi_id(item.get('DOI',''));title=(item.get('title') or [''])[0]
            if explicit and doi!=explicit:raise ValueError('Crossref DOI verification mismatch')
            if item.get('type') not in ('journal-article','proceedings-article','posted-content','review'):continue
            date=((item.get('published') or {}).get('date-parts') or [[]])[0]
            if not title or not doi or not date:continue
            authors=[norm(a.get('given','')+' '+a.get('family','')) for a in item.get('author',[])]
            links=[]
            for link in item.get('link',[]):
                # A Crossref link does not itself establish permission to download.
                from .transport import DOMAINS
                u=link.get('URL','');host=urllib.parse.urlsplit(u).hostname
                src=next((s for s,hosts in DOMAINS.items() if host in hosts and s not in ('crossref','openalex')),None)
                if src and ('pdf' in link.get('content-type','') or '.pdf' in u):links.append(oa(src,u,'PUBLISHER_LINK','LINK_TO_OFFICIAL_PUBLIC_REPOSITORY'))
            rows.append(record(self.name,doi,title,doi=doi,authors=authors,year=date[0],
                publication_date='-'.join(f'{n:02d}' if i else str(n) for i,n in enumerate(date)) if len(date)==3 else None,
                date_precision='DAY' if len(date)==3 else 'YEAR',venue=(item.get('container-title') or [''])[0],
                publication_status='DOI_REGISTERED_'+item.get('type','UNKNOWN').upper(),
                version=item.get('type','DOI_METADATA'),landing_url=item.get('URL') or 'https://doi.org/'+doi,
                abstract=norm(re.sub(r'<[^>]+>',' ',item.get('abstract') or '')),
                fulltexts=links,citation_count=item.get('is-referenced-by-count'),source_response=proof,
                doi_verification='EXACT_REGISTRY_RESPONSE' if explicit else 'REGISTRY_SEARCH_METADATA',
                declared_relations=item.get('relation',{})))
        count=int(message.get('total-results',len(rows))) if not explicit else len(rows)
        offset=int(cursor or 0);return rows,str(offset+self.cfg['page_size']) if not explicit and offset+len(items)<count and items else None
class OpenAlex:
    name='openalex'
    def __init__(self,http,cfg):self.http=http;self.cfg=cfg
    def search(self,task,cursor):
        # Preserve the existing key/account-specific daily checkpoint and cache.
        import paper_discovery as discovery
        import copy
        runtime=copy.deepcopy(discovery.config(self.http.ws))
        remaining=self.http.policy['max_requests_per_run']-self.http.sent
        if self.http.budget:remaining=min(remaining,self.http.budget['limit']-self.http.budget['sent'])
        if remaining<=0:raise SourcePause(self.name,'RUN_REQUEST_BOUND')
        runtime['api']['retry_429']=min(runtime['api']['retry_429'],remaining-1)
        runtime['api']['minimum_request_interval_seconds']=max(runtime['api']['minimum_request_interval_seconds'],self.http.policy['minimum_interval'])
        client=discovery.OpenAlex(runtime,workspace=self.http.ws)
        statepath=self.http.ws/'output/discovery_preflight/openalex_http/state.json'
        from .common import read
        before=read(statepath).get('physical_requests_after_repair',0) if statepath.exists() else 0
        try:raws,meta=client.query(task['query'],task['start'],task['end'],int(cursor or 1))
        except Exception as exc:
            info=getattr(exc,'info',None)
            if info:raise SourcePause(self.name,info.get('kind','OPENALEX_PAUSE'),checkpoint=info)
            raise
        finally:
            after=read(statepath).get('physical_requests_after_repair',0) if statepath.exists() else before
            delta=after-before
            self.http.sent+=delta
            if self.http.budget:self.http.budget['sent']+=delta
        rows=[]
        for raw in raws:
            old=discovery.work_normalized(raw,task['category'],task.get('domain',''),task['query'])
            if old:rows.append(from_legacy(old,source_response=meta))
        return rows,None
def from_legacy(old,**extra):
    aid,v=arxiv_id(old.get('landing_url','')+' '+old.get('oa_pdf_url','')+' '+old.get('doi',''))
    source='openalex' if str(old.get('id','')).startswith('https://openalex.org/') else 'legacy'
    fulltexts=[]
    from .transport import DOMAINS
    url=old.get('oa_pdf_url','');host=urllib.parse.urlsplit(url).hostname
    target=next((s for s,hosts in DOMAINS.items() if host in hosts and s not in ('openalex','crossref')),None)
    if url and target and old.get('oa_reported'):fulltexts=[oa(target,url,'LEGACY_VERSION_UNSPECIFIED','RETAINED_REPORTED_OA_URL')]
    return record(source,old['id'],old['title'],authors=old.get('authors',[]),doi=doi_id(old.get('doi','')),
        arxiv_id=aid,arxiv_version=v,year=old.get('year'),publication_date=old.get('publication_date'),
        date_precision='DAY' if old.get('publication_date') else 'UNKNOWN',venue=old.get('venue',''),
        version='LEGACY_METADATA_VERSION_UNSPECIFIED',publication_status='RETAINED_METADATA_NOT_REVIEWED',
        landing_url=old.get('landing_url') or old.get('bibliographic_link',''),fulltexts=fulltexts,
        abstract=old.get('abstract',''),legacy_work_id=old['id'],category=old.get('category',''),
        citation_count=old.get('cited_by_count'),inspiration_domains=old.get('inspiration_domains',[]),
        assigned_inspiration_domain=old.get('assigned_inspiration_domain'),**extra)
ADAPTERS={c.name:c for c in (Arxiv,CVF,PMLR,OpenReview,Crossref,OpenAlex)}