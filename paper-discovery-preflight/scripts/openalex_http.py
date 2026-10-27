"""Durable OpenAlex transport. No model calls or scientific gate changes."""
from __future__ import annotations
import contextlib,datetime as dt,email.utils,hashlib,json,os,pathlib,random,tempfile,time
import urllib.error,urllib.parse,urllib.request

SELECT='id,doi,display_name,publication_year,publication_date,primary_location,best_oa_location,open_access,cited_by_count,type,abstract_inverted_index,authorships'
HEADERS=('retry-after','x-ratelimit-limit','x-ratelimit-remaining','x-ratelimit-credits-used','x-ratelimit-reset')
def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def write(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile('w',encoding='utf-8',delete=False,dir=path.parent) as f:
        json.dump(obj,f,ensure_ascii=False,indent=2);f.write('\n');tmp=f.name
    os.replace(tmp,path)
def number(v):
    try:return float(v)
    except (ValueError,TypeError):return None
def retry_after(value,now):
    n=number(value)
    if n is not None:return max(0,n)
    try:return max(0,email.utils.parsedate_to_datetime(value).timestamp()-now)
    except (ValueError,TypeError,OverflowError):return 0.0
def reset_at(headers,now):
    n=number(headers.get('x-ratelimit-reset'))
    if n is not None:return n if n>1_000_000_000 else now+max(0,n)
    tomorrow=dt.datetime.fromtimestamp(now,dt.timezone.utc).date()+dt.timedelta(days=1)
    return dt.datetime.combine(tomorrow,dt.time(),dt.timezone.utc).timestamp()
def classify(status,headers,body):
    """Long Retry-After alone does not prove daily exhaustion."""
    remaining=number(headers.get('x-ratelimit-remaining'))
    text=str(body).lower()
    if status==429:
        if remaining is not None and remaining<=0:return 'DAILY_BUDGET_EXHAUSTED'
        if any(s in text for s in ('not_enough_credits','daily budget','daily credit','daily limit','daily quota','daily_limit','daily_budget')):
            return 'DAILY_BUDGET_EXHAUSTED'
        if any(s in text for s in ('per-second','per second','rate_limit_exceeded','rate limit exceeded','too many requests per','requests_per_second')):
            return 'PER_SECOND_RATE_LIMIT'
        return 'HTTP429_UNCLASSIFIED'
    if status in (401,403):return 'AUTHORIZATION_REQUIRED'
    return 'TRANSIENT_HTTP' if status in (500,502,503,504) else 'HTTP_ERROR'
class OpenAlexPause(RuntimeError):
    def __init__(self,info):
        self.info=info
        super().__init__(json.dumps(info,ensure_ascii=False))
class OpenAlex:
    def __init__(self,c,workspace=None,*,opener=None,clock=None,sleeper=None,jitter=None):
        self.cfg=c['api'];self.key=os.environ.get(self.cfg.get('api_key_env','OPENALEX_API_KEY'),'').strip()
        self.workspace=pathlib.Path(workspace) if workspace is not None else None
        self.root=self.workspace/'output/discovery_preflight/openalex_http' if self.workspace else None
        self.opener=opener or urllib.request.urlopen;self.clock=clock or time.time;self.sleep=sleeper or time.sleep
        self.jitter=jitter or (lambda:random.uniform(0,.25))
        self.scope=hashlib.sha256(self.key.encode()).hexdigest()[:20] if self.key else 'KEYLESS_NETWORK_SCOPE'
        self.local={};self.last_request=0
    def clean(self,value):
        text=str(value)
        if self.key:text=text.replace(self.key,'[REDACTED]')
        import re
        return re.sub(r'(api_key(?:=|%3D))[^&\s"<>]+',r'\1[REDACTED]',text,flags=re.I)[:3000]
    @contextlib.contextmanager
    def locked(self):
        if not self.root:yield;return
        self.root.mkdir(parents=True,exist_ok=True);lock=self.root/'.request-lock'
        for _ in range(100):
            try:lock.mkdir();break
            except FileExistsError:self.sleep(.05)
        else:raise OpenAlexPause({'kind':'CLIENT_LOCK_BUSY','retryable_now':False})
        try:yield
        finally:lock.rmdir()
    def state(self):
        p=self.root/'state.json' if self.root else None
        if p and p.exists():return json.loads(p.read_text('utf-8'))
        known=0
        if self.workspace:
            old=self.workspace/'output/discovery_preflight/state.json'
            if old.exists():known=json.loads(old.read_text('utf-8')).get('api_calls',0)
        state={'version':1,'known_successful_queries_before_repair':known,'physical_requests_after_repair':0,
                'prior_physical_attempts_unknown':True,'next_request_at':0,'accounts':{}}
        # The previous client retained daily remaining credits but lost error headers.
        # Reuse an observed zero; never turn an old generic 429 into a daily claim.
        if self.workspace and not self.key:
            exhausted=[]
            for path in (self.workspace/'sources/openalex_transport').glob('*.json'):
                try:
                    data=json.loads(path.read_text('utf-8'))
                    if not isinstance(data,dict):continue
                    if number(data.get('meta',{}).get('rate_remaining'))==0:
                        observed=dt.datetime.fromisoformat(data['fetched_at']).timestamp()
                        exhausted.append((observed,path))
                except (ValueError,KeyError,TypeError):continue
            if exhausted:
                observed,path=max(exhausted)
                state['accounts'][self.scope]={'pause':{'kind':'DAILY_BUDGET_EXHAUSTED',
                    'observed_at':observed,'resume_after':reset_at({},observed),
                    'headers':{'x-ratelimit-remaining':'0'},'http_status':200,
                    'retryable_now':False,'reset_time_provider_supplied':False,
                    'allowance_restored_not_attested':True,
                    'seeded_from_retained_response':path.relative_to(self.workspace).as_posix(),
                    'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}}
        return state
    def persist(self,s):
        if self.root:write(self.root/'state.json',s)
        else:self.local['state']=s
    def event(self,info):
        if self.root:
            with (self.root/'events.jsonl').open('a',encoding='utf-8') as f:
                f.write(json.dumps({'at':self.clock(),**info},ensure_ascii=False)+'\n')
    def pause(self,s,kind,headers=None,body='',delay=None,status=None,account_pause=True):
        now=self.clock();headers=headers or {}
        after=reset_at(headers,now) if kind=='DAILY_BUDGET_EXHAUSTED' else now+max(delay or 60,0)
        info={'kind':kind,'http_status':status,'headers':headers,'body':self.clean(body),
              'observed_at':now,'resume_after':after,'retryable_now':False,
              'reset_time_provider_supplied':'x-ratelimit-reset' in headers,
              'allowance_restored_not_attested':True}
        account=s['accounts'].setdefault(self.scope,{})
        if account_pause:
            existing=account.get('pause')
            if existing and existing.get('kind')=='DAILY_BUDGET_EXHAUSTED' and existing['resume_after']>now and kind!='DAILY_BUDGET_EXHAUSTED':
                account.setdefault('secondary_observations',[]).append(info)
            else:account['pause']=info
        else:
            account.setdefault('status_probe_observations',[]).append(info)
        self.persist(s);self.event({'event':'PAUSED',**info})
        raise OpenAlexPause(info)
    def _get(self,path,params,*,force_probe=False):
        identity={'endpoint':path,'params':params};key=digest(identity)
        cached=self.root/'cache'/(key+'.json') if self.root and path=='/works' else None
        # Authentic cached results remain usable even during a server-enforced pause.
        if cached and cached.exists():
            obj=json.loads(cached.read_text('utf-8'))
            if obj['request']!=identity or digest(obj['response'])!=obj['response_sha256']:
                raise ValueError('OpenAlex cache binding/integrity mismatch')
            self.event({'event':'CACHE_HIT','query_key':key})
            return obj['response'],obj['headers'],True
        with self.locked():
            # Another process may have filled this exact cache while we waited.
            if cached and cached.exists():
                obj=json.loads(cached.read_text('utf-8'))
                if obj['request']!=identity or digest(obj['response'])!=obj['response_sha256']:
                    raise ValueError('OpenAlex cache binding/integrity mismatch')
                return obj['response'],obj['headers'],True
            s=self.state() if self.root else self.local.get('state',self.state())
            account=s['accounts'].setdefault(self.scope,{})
            now=self.clock();pause=account.get('pause')
            if pause and now<pause['resume_after'] and not force_probe:
                raise OpenAlexPause({**pause,'source':'PERSISTED_SERVER_CHECKPOINT'})
            retries=min(5,max(0,int(self.cfg.get('retry_429',3))))
            interval=max(1.1,float(self.cfg.get('minimum_request_interval_seconds',1.1)))
            max_wait=30.0
            for attempt in range(retries+1):
                now=self.clock();wait=max(0,s.get('next_request_at',0)-now)
                if wait>max_wait:
                    self.pause(s,'SERVER_COOLDOWN_PENDING',delay=wait)
                if wait:self.sleep(wait)
                if s['known_successful_queries_before_repair']+s['physical_requests_after_repair']>=self.cfg['max_requests_total']:
                    raise OpenAlexPause({'kind':'LOCAL_PHYSICAL_REQUEST_CEILING','retryable_now':False})
                real_params=dict(params)
                if self.key:real_params['api_key']=self.key
                request=urllib.request.Request('https://api.openalex.org'+path+'?'+urllib.parse.urlencode(real_params),
                        headers={'User-Agent':'search2discovery/1.0.0-runtime.1 (scholarly metadata)'})
                now=self.clock();s['physical_requests_after_repair']+=1;s['next_request_at']=now+interval
                self.persist(s)
                try:
                    with self.opener(request,timeout=self.cfg['timeout_seconds']) as response:
                        headers={k:response.headers.get(k) for k in HEADERS if response.headers.get(k) is not None}
                        obj=json.load(response)
                    if not isinstance(obj,dict) or (path=='/works' and not isinstance(obj.get('results'),list)):
                        raise ValueError('Invalid OpenAlex response schema')
                    if cached:
                        write(cached,{'request':identity,'response':obj,'response_sha256':digest(obj),'headers':headers,'fetched_at':self.clock()})
                    if not force_probe or number(headers.get('x-ratelimit-remaining')) is not None:
                        account.pop('pause',None)
                    account['last_headers']=headers
                    # Persist exhausted allowance without discarding this final successful response.
                    if number(headers.get('x-ratelimit-remaining')) is not None and number(headers['x-ratelimit-remaining'])<=0:
                        account['pause']={'kind':'DAILY_BUDGET_EXHAUSTED','resume_after':reset_at(headers,self.clock()),
                           'observed_at':self.clock(),'http_status':200,'headers':headers,'retryable_now':False,
                           'allowance_restored_not_attested':True}
                    self.persist(s);self.event({'event':'SUCCESS','endpoint':path,'query_key':key,'attempt':attempt+1,'headers':headers})
                    return obj,headers,False
                except urllib.error.HTTPError as exc:
                    headers={k:exc.headers.get(k) for k in HEADERS if exc.headers.get(k) is not None}
                    body=self.clean(exc.read(8192).decode('utf-8','replace'));kind=classify(exc.code,headers,body)
                    self.event({'event':'HTTP_ERROR','query_key':key,'attempt':attempt+1,'http_status':exc.code,'kind':kind,'headers':headers,'body':body})
                    if kind in ('DAILY_BUDGET_EXHAUSTED','AUTHORIZATION_REQUIRED','HTTP_ERROR'):
                        self.pause(s,kind,headers,body,status=exc.code,account_pause=not force_probe)
                    delay=max(retry_after(headers.get('retry-after'),self.clock()),min(8,2**attempt)+self.jitter())
                    s['next_request_at']=max(s['next_request_at'],self.clock()+delay);self.persist(s)
                    if attempt==retries or delay>max_wait or force_probe:
                        self.pause(s,kind,headers,body,delay=delay if delay>max_wait else max(60,delay),status=exc.code,account_pause=not force_probe)
                except (urllib.error.URLError,TimeoutError,OSError) as exc:
                    self.event({'event':'NETWORK_ERROR','query_key':key,'attempt':attempt+1,'error_type':type(exc).__name__})
                    delay=min(8,2**attempt)+self.jitter();s['next_request_at']=self.clock()+delay;self.persist(s)
                    if force_probe or attempt>=min(1,retries):
                        self.pause(s,'NETWORK_UNAVAILABLE',delay=max(60,delay),account_pause=not force_probe)
            raise AssertionError('Unreachable bounded retry exit')
    def query(self,q,start,end,page):
        if page>1 and not self.key:raise ValueError('A legitimate API key is required for pagination beyond page 1')
        params={'search':q,'filter':f'from_publication_date:{start},to_publication_date:{end}',
                'per_page':self.cfg['per_page'],'page':page,'select':SELECT}
        obj,headers,cached=self._get('/works',params)
        return obj['results'],{'result_count':(obj.get('meta') or {}).get('count'),
                              'rate_remaining':headers.get('x-ratelimit-remaining'),'page':page,
                              'response_headers':headers,'cache_hit':cached}
    def inspect_allowance(self):
        """One non-retried status request; never asserts a reset from elapsed time."""
        obj,headers,cached=self._get('/rate-limit',{},force_probe=True)
        return {'response':obj,'headers':headers,'key_configured':bool(self.key),'observed_at':self.clock()}