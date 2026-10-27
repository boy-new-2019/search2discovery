"""Per-source HTTP isolation, append-only raw caches and durable pause state."""
from __future__ import annotations
import datetime as dt,email.utils,ipaddress,json,pathlib,random,re,socket,time,urllib.error,urllib.parse,urllib.request
from .common import read,write,stable,sha,locked,utc
DOMAINS={
 'arxiv':{'arxiv.org','export.arxiv.org'},
 'cvf':{'openaccess.thecvf.com'},
 'pmlr':{'proceedings.mlr.press'},
 'openreview':{'api2.openreview.net','api.openreview.net','openreview.net'},
 'crossref':{'api.crossref.org'},
 'openalex':{'api.openalex.org'}}
def allowed(source,url):
    try:
        p=urllib.parse.urlsplit(url)
        return p.scheme=='https' and p.hostname in DOMAINS[source] and not p.username and not p.password and p.port in (None,443)
    except (ValueError,TypeError,KeyError):return False
def public_host(url):
    host=urllib.parse.urlsplit(url).hostname
    try:answers=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
    except (socket.gaierror,OSError):return False
    return bool(answers) and all(ipaddress.ip_address(a[4][0]).is_global for a in answers)
class Redirect(urllib.request.HTTPRedirectHandler):
    def __init__(self,source,check):self.source=source;self.check=check
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        newurl=urllib.parse.urljoin(req.full_url,newurl)
        if not allowed(self.source,newurl) or not self.check(newurl):raise ValueError('Redirect leaves the legal public source boundary')
        return super().redirect_request(req,fp,code,msg,headers,newurl)
class SourcePause(RuntimeError):
    def __init__(self,source,kind,**details):
        self.info={'source':source,'kind':kind,**details}
        super().__init__(json.dumps(self.info,ensure_ascii=False))
class HTTP:
    def __init__(self,ws,source,policy,*,online,opener=None,clock=None,sleeper=None,dns_check=None,budget=None):
        self.ws=pathlib.Path(ws);self.source=source;self.policy=policy;self.online=online
        self.root=self.ws/'output/discovery_preflight/multisource/providers'/source
        self.clock=clock or time.time;self.sleep=sleeper or time.sleep;self.check=dns_check or public_host
        self.opener=opener or urllib.request.build_opener(Redirect(source,self.check)).open
        self.sent=0;self.hits=0;self.budget=budget
    def state(self):
        p=self.root/'state.json'
        return read(p) if p.exists() else {'schema_version':1,'physical_requests':0,'next_request_at':0,'pause':None}
    def event(self,info):
        self.root.mkdir(parents=True,exist_ok=True)
        with (self.root/'events.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps({'at':utc(),**info},ensure_ascii=False)+'\n')
    def pause(self,state,kind,seconds=60,**details):
        info={'source':self.source,'kind':kind,'observed_at':self.clock(),'resume_after':self.clock()+max(0,seconds),**details}
        state['pause']=info;write(self.root/'state.json',state);self.event({'event':'PAUSE',**info})
        raise SourcePause(self.source,kind,**{k:v for k,v in info.items() if k not in ('source','kind')})
    def cache(self,key,url):
        meta=self.root/'cache'/(key+'.json')
        if not meta.exists():return None
        data=read(meta);blob=self.root/'blobs'/data['sha256']
        if data['url']!=url or not blob.is_file() or sha(blob.read_bytes())!=data['sha256']:raise ValueError('Source cache integrity/binding mismatch')
        self.hits+=1
        return blob.read_bytes(),data
    def get(self,url,*,max_bytes=8*1024*1024):
        if not allowed(self.source,url):raise ValueError('Unapproved source URL')
        key=stable({'method':'GET','url':url});result=self.cache(key,url)
        if result:
            if len(result[0])>max_bytes:raise SourcePause(self.source,'RESPONSE_SIZE_BOUND')
            return result
        if not self.online:raise SourcePause(self.source,'OFFLINE_CACHE_MISS',url=url)
        with locked(self.root,self.sleep):
            result=self.cache(key,url)
            if result:return result
            state=self.state();now=self.clock()
            if state.get('pause') and now<state['pause']['resume_after']:
                raise SourcePause(self.source,state['pause']['kind'],resume_after=state['pause']['resume_after'])
            for attempt in range(self.policy['max_retries']+1):
                if self.budget and self.budget['sent']>=self.budget['limit']:raise SourcePause(self.source,'GLOBAL_RUN_BOUND')
                if self.sent>=self.policy['max_requests_per_run']:raise SourcePause(self.source,'RUN_REQUEST_BOUND')
                if state['physical_requests']>=self.policy['max_lifetime_requests']:raise SourcePause(self.source,'LIFETIME_REQUEST_BOUND')
                wait=max(0,state['next_request_at']-self.clock())
                if wait>self.policy['max_wait']:self.pause(state,'SERVER_COOLDOWN',wait)
                if wait:self.sleep(wait)
                if not self.check(url):raise SourcePause(self.source,'PUBLIC_DNS_CHECK_FAILED')
                request=urllib.request.Request(url,headers={'User-Agent':'search2discovery/1.1 scholarly metadata and legal OA retrieval'})
                self.sent+=1
                if self.budget:self.budget['sent']+=1
                state['physical_requests']+=1
                state['next_request_at']=self.clock()+self.policy['minimum_interval'];write(self.root/'state.json',state)
                try:
                    with self.opener(request,timeout=self.policy['timeout']) as response:
                        final=response.geturl()
                        if not allowed(self.source,final):raise ValueError('Final response leaves the approved source')
                        raw=response.read(max_bytes+1)
                        if len(raw)>max_bytes:raise SourcePause(self.source,'RESPONSE_SIZE_BOUND')
                        headers={str(k).lower():str(v) for k,v in response.headers.items()
                                 if str(k).lower() in ('content-type','retry-after','x-ratelimit-limit','x-ratelimit-remaining','x-ratelimit-reset')}
                    digest=sha(raw);blob=self.root/'blobs'/digest;blob.parent.mkdir(parents=True,exist_ok=True)
                    if not blob.exists():
                        with blob.open('xb') as f:f.write(raw)
                    elif sha(blob.read_bytes())!=digest:raise ValueError('Existing raw-source blob changed')
                    data={'url':url,'final_url':final,'sha256':digest,'source':self.source,
                          'headers':headers,'fetched_at':utc(),'http_status':200}
                    write(self.root/'cache'/(key+'.json'),data)
                    state['pause']=None;write(self.root/'state.json',state)
                    self.event({'event':'SUCCESS','url':url,'sha256':digest,'attempt':attempt+1})
                    return raw,data
                except urllib.error.HTTPError as exc:
                    body=exc.read(4096).decode('utf-8','replace')
                    headers={k.lower():v for k,v in exc.headers.items() if k.lower() in ('retry-after','x-ratelimit-limit','x-ratelimit-remaining','x-ratelimit-reset')}
                    self.event({'event':'HTTP_ERROR','url':url,'status':exc.code,'headers':headers,'body':body})
                    if exc.code in (401,403):self.pause(state,'AUTHORIZATION_REQUIRED',3600,status=exc.code)
                    if exc.code==404:raise SourcePause(self.source,'NOT_FOUND',status=404,url=url)
                    if exc.code==429:
                        text=body.lower()
                        daily=any(x in text for x in ('daily budget','daily limit','daily quota','not_enough_credits'))
                        # Short/hourly remaining=0 is not proof of a daily account quota.
                        if daily:
                            try:delay=float(headers['x-ratelimit-reset'])
                            except (KeyError,ValueError):delay=86400-(self.clock()%86400)
                            if delay>1_000_000_000:delay-=self.clock()
                            self.pause(state,'DAILY_BUDGET_EXHAUSTED',delay,status=429,headers=headers)
                    if exc.code not in (429,500,502,503,504):self.pause(state,'HTTP_ERROR',300,status=exc.code)
                    retry=headers.get('retry-after','0')
                    try:delay=float(retry)
                    except ValueError:
                        try:delay=email.utils.parsedate_to_datetime(retry).timestamp()-self.clock()
                        except (ValueError,TypeError):delay=0
                    delay=max(delay,2**attempt+random.uniform(0,.25))
                    state['next_request_at']=self.clock()+delay;write(self.root/'state.json',state)
                    if attempt==self.policy['max_retries'] or delay>self.policy['max_wait']:
                        self.pause(state,'HTTP429_UNCLASSIFIED' if exc.code==429 else 'TRANSIENT_HTTP',max(60,delay),status=exc.code)
                except (urllib.error.URLError,TimeoutError,OSError) as exc:
                    self.event({'event':'NETWORK_ERROR','error_type':type(exc).__name__,'url':url})
                    state['next_request_at']=self.clock()+2**attempt;write(self.root/'state.json',state)
                    if attempt==self.policy['max_retries']:self.pause(state,'NETWORK_UNAVAILABLE',60)
            raise AssertionError('Bounded retry exit')