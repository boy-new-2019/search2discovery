#!/usr/bin/env python3
"""Broad, reproducible, provenance-aware inspiration-paper field diversification.

Editorial domain/distance tags are discovery heuristics, not verified attributes of
works or proof that an analogy can be transferred to the main research field.
"""
from __future__ import annotations
from collections import Counter
import hashlib
import json
import pathlib
import random
import re
from typing import Any, Callable

ROOT = pathlib.Path(__file__).resolve().parents[1]
REQUIRED_POLICY = (
    'enabled', 'apply_min_quota', 'min_unique_domains', 'min_macro_groups',
    'min_far_distance', 'max_per_domain', 'max_per_macro_group', 'random_seed',
    'random_tail_fraction', 'custom_domains',
)
DISTANCES = {'far', 'bridge'}


def load_catalog(cfg: dict) -> dict:
    location = cfg.get('inspiration_domain_catalog_file')
    if not isinstance(location, str) or not location:
        raise ValueError('missing interdisciplinary field catalog path')
    p=pathlib.Path(location)
    if p.is_absolute() or '..' in p.parts or (not p.parts or p.parts[0]!='references'):
        raise ValueError('Source path, lawful access or network permission check failed at inspiration_diversity.load_catalog (check 31). Do not bypass paywalls or source integrity checks.')
    path=ROOT/p
    if not path.is_file():raise ValueError('Source path, lawful access or network permission check failed at inspiration_diversity.load_catalog (check 33). Do not bypass paywalls or source integrity checks.')
    raw=json.loads(path.read_text('utf-8'))
    families={}
    for group in raw.get('macro_groups',[]):
        name=group.get('id')
        if not name or not re.fullmatch('[a-z][a-z_]{1,50}',name) or name in families:
            raise ValueError('Input, evidence or workflow invariant failed at inspiration_diversity.load_catalog (check 39); inspect the signed task record and original source.')
        families[name]=group
    domains={}
    for entry in raw.get('domains',[]):
        name=entry.get('id')
        if not name or not re.fullmatch('[a-z][a-z_]{1,50}',name) or name in domains:
            raise ValueError('Frozen research topic or signed research contract mismatch at inspiration_diversity.load_catalog (check 45). Reconfirm boundaries; do not overwrite approved work.')
        if entry.get('macro_group') not in families or entry.get('distance_to_mainline_heuristic') not in DISTANCES:
            raise ValueError('Frozen research topic or signed research contract mismatch at inspiration_diversity.load_catalog (check 47). Reconfirm boundaries; do not overwrite approved work.')
        domains[name]=entry
    if len(domains)<30 or len(families)<8:
        raise ValueError('Configuration schema or numeric bounds check failed at inspiration_diversity.load_catalog (check 50). Keep strict quality gates intact.')
    policy=cfg.get('inspiration_diversity')
    if not isinstance(policy,dict) or set(policy)!=set(REQUIRED_POLICY):
        raise ValueError('Configuration schema or numeric bounds check failed at inspiration_diversity.load_catalog (check 53). Keep strict quality gates intact.')
    if policy['enabled'] is not True:
        raise ValueError('Configuration schema or numeric bounds check failed at inspiration_diversity.load_catalog (check 55). Keep strict quality gates intact.')
    for name,lo,hi in (
        ('apply_min_quota',1,1000),('min_unique_domains',1,200),('min_macro_groups',1,60),
        ('min_far_distance',0,10000),('max_per_domain',1,30),('max_per_macro_group',1,100),
        ('random_seed',0,2**31-1),
    ):
        val=policy.get(name)
        if type(val) is not int or not lo<=val<=hi:
            raise ValueError(f'inspiration_diversity.{name} must be {lo}..{hi} integer')
    prob=policy.get('random_tail_fraction')
    if type(prob) not in (int,float) or not 0<=prob<=0.45:
        raise ValueError('Input, evidence or workflow invariant failed at inspiration_diversity.load_catalog (check 66); inspect the signed task record and original source.')
    custom=policy.get('custom_domains')
    if not isinstance(custom,dict) or len(custom)>100:
        raise ValueError('Input, evidence or workflow invariant failed at inspiration_diversity.load_catalog (check 69); inspect the signed task record and original source.')
    for ident,definition in custom.items():
        if not re.fullmatch('[a-z][a-z_]{1,50}',ident) or ident in domains:
            raise ValueError('Frozen research topic or signed research contract mismatch at inspiration_diversity.load_catalog (check 72). Reconfirm boundaries; do not overwrite approved work.'+str(ident))
        if not isinstance(definition,dict) or set(definition)!={'name_zh','macro_group','distance_to_mainline_heuristic'}:
            raise ValueError('Frozen research topic or signed research contract mismatch at inspiration_diversity.load_catalog (check 74). Reconfirm boundaries; do not overwrite approved work.')
        if (not isinstance(definition['name_zh'],str) or not definition['name_zh'].strip()
            or not isinstance(definition['macro_group'],str)
            or not re.fullmatch('[a-z][a-z_]{1,50}',definition['macro_group'])
            or definition['distance_to_mainline_heuristic'] not in DISTANCES):
            raise ValueError('Frozen research topic or signed research contract mismatch at inspiration_diversity.load_catalog (check 79). Reconfirm boundaries; do not overwrite approved work.')
        domains[ident]={'id':ident, **definition, 'custom':True}
        families.setdefault(definition['macro_group'],{'id':definition['macro_group'],
                            'name_zh':definition['macro_group'],'custom':True})
    if policy['min_macro_groups']>len(families) or policy['min_unique_domains']>len(domains):
        raise ValueError('Frozen research topic or signed research contract mismatch at inspiration_diversity.load_catalog (check 84). Reconfirm boundaries; do not overwrite approved work.')
    return {'domains':domains,'families':families,'policy':policy,'path':str(p)}


def query_schedule(queries:dict, catalog:dict) -> list[tuple[str,str]]:
    """Round-robin through editorial macro/domain order, regardless of JSON key sort.

    The v4.5 config serializer alphabetically sorted query dictionaries. Using
    that alphabetical order would leave entire disciplines unseen during the
    first 25-50 API requests, so we instead use the *catalog* field order.
    """
    families:dict[str,list[str]]={key:[] for key in catalog['families']}
    for domain in catalog['domains']:
        if domain in queries:
            families[catalog['domains'][domain]['macro_group']].append(domain)
    ordered=[]
    max_domains=max((len(x) for x in families.values()),default=0)
    for offset in range(max_domains):
        for group,fields in families.items():
            if offset<len(fields):ordered.append(fields[offset])
    result=[]
    for position in range(max((len(x) for x in queries.values()),default=0)):
        for domain in ordered:
            if position<len(queries[domain]):result.append((domain,queries[domain][position]))
    return result


def _random_tie(seed:int,id_:str)->int:
    return int(hashlib.sha256(f'{seed}:{id_}'.encode('utf-8')).hexdigest()[:15],16)


def diversify(ordered:list[dict], *, used_ids:set[str], eligible:dict[str,bool],
              catalog:dict, preferred:dict[str,int], target:int,
              rank:Callable[[dict],tuple])->list[tuple[dict,str]]:
    """Pick (work, one assigned domain) to meet breadth before relevance-weighted fill.

    Always preserves the highest publication/venue priority band. If impossible,
    it returns fewer/less diverse papers and reports the exact unmet constraints.
    """
    policy=catalog['policy']
    if target<policy['apply_min_quota']:
        return _legacy_small_quota(ordered,used_ids,eligible,preferred,target)
    domain_defs=catalog['domains']
    selected:list[tuple[dict,str]]=[]
    seen=set(used_ids)
    dcounts=Counter(); fcounts=Counter()
    tie={w['id']:_random_tie(policy['random_seed'],w['id']) for w in ordered}
    def available(w:dict,d:str)->bool:
        if w['id'] in seen or not eligible.get(w['id'],False) or d not in w.get('inspiration_domains',[]):
            return False
        if d not in domain_defs or dcounts[d]>=policy['max_per_domain']:
            return False
        family=domain_defs[d]['macro_group']
        if fcounts[family]>=policy['max_per_macro_group']:
            return False
        return True
    def candidates(predicate:Callable[[str],bool],*,tail:bool=False):
        pool=[]
        for w in ordered:
            if w['id'] in seen or not eligible.get(w['id'],False):continue
            for d in w.get('inspiration_domains',[]):
                if available(w,d) and predicate(d):
                    family=domain_defs[d]['macro_group']
                    r=rank(w)
                    if tail:
                        key=(r[0],fcounts[family],dcounts[d],tie[w['id']],r[1:],d)
                    else:
                        key=(r[0],fcounts[family],dcounts[d],r[1:],tie[w['id']],d)
                    pool.append((key,w,d))
        if not pool:return None
        _,w,d=min(pool,key=lambda x:x[0])
        return w,d
    def take(pair:tuple[dict,str]|None):
        if pair is None or len(selected)>=target:return False
        w,d=pair
        family=domain_defs[d]['macro_group']
        selected.append((w,d))
        seen.add(w['id']);dcounts[d]+=1;fcounts[family]+=1
        return True
    # 1. Explicit, user-auditable per-field minimum coverage (typically 15x1).
    for domain,mincount in preferred.items():
        while dcounts[domain]<mincount and len(selected)<target:
            if not take(candidates(lambda d,domain=domain:d==domain)):break
    # 2. Ensure different major intellectual traditions are represented.
    while len(fcounts)<min(policy['min_macro_groups'],target) and len(selected)<target:
        nxt=candidates(lambda d:domain_defs[d]['macro_group'] not in fcounts)
        if not take(nxt):break
    # 3. Force non-adjacent disciplines, not only mathematics and cognition.
    def far():return sum(domain_defs[d]['distance_to_mainline_heuristic']=='far' for _,d in selected)
    while far()<min(policy['min_far_distance'],target) and len(selected)<target:
        nxt=candidates(lambda d:domain_defs[d]['distance_to_mainline_heuristic']=='far')
        if not take(nxt):break
    # 4. Spread remaining records over many distinct areas.
    while len(dcounts)<min(policy['min_unique_domains'],target) and len(selected)<target:
        nxt=candidates(lambda d:d not in dcounts)
        if not take(nxt):break
    # 5. Fill using recent/top-venue strata first, with deterministic random
    # tie-breaks for the novelty tail inside the SAME date/venue quality band.
    stochastic_n=round(target*policy['random_tail_fraction'])
    while len(selected)<target:
        nxt=candidates(lambda _:True,tail=len(selected)>=target-stochastic_n)
        if not take(nxt):break
    return selected


def _legacy_small_quota(ordered:list[dict],used:set[str],eligible:dict[str,bool],
                       preferred:dict[str,int],quota:int)->list[tuple[dict,str]]:
    """Meaningful diversity constraints cannot apply to a 1-5 paper demo batch."""
    selected=[];chosen=set(used)
    for domain,n in preferred.items():
        for w in ordered:
            if sum(d==domain for _,d in selected)>=n:break
            if w['id'] not in chosen and eligible.get(w['id'],False) and domain in w.get('inspiration_domains',[]):
                selected.append((w,domain));chosen.add(w['id'])
                if len(selected)>=quota:return selected
    for w in ordered:
        if w['id'] not in chosen and eligible.get(w['id'],False):
            domains=w.get('inspiration_domains',[])
            if domains:selected.append((w,domains[0]));chosen.add(w['id'])
            if len(selected)>=quota:break
    return selected


def summarize(items:list[dict], cfg:dict, catalog:dict)->dict:
    policy=catalog['policy'];target=cfg['quotas']['inspiration']
    enforce=target>=policy['apply_min_quota']
    dc=Counter(x['assigned_inspiration_domain'] for x in items)
    mc=Counter(x['inspiration_macro_group'] for x in items)
    far=sum(x['inspiration_transfer_distance']=='far' for x in items)
    preferred_gaps={d:max(0,n-dc[d]) for d,n in cfg['preferred_domains'].items()}
    breadth={
        'unique_domains':len(dc),'unique_macro_groups':len(mc),'far_field_papers':far,
        'required_unique_domains':min(policy['min_unique_domains'],target) if enforce else 0,
        'required_macro_groups':min(policy['min_macro_groups'],target) if enforce else 0,
        'required_far_field_papers':min(policy['min_far_distance'],target) if enforce else 0,
        'per_domain_counts':dict(sorted(dc.items())),
        'per_macro_group_counts':dict(sorted(mc.items())),
        'enforced':enforce,
    }
    breadth['shortfalls']={
        'unique_domains':max(0,breadth['required_unique_domains']-breadth['unique_domains']),
        'macro_groups':max(0,breadth['required_macro_groups']-breadth['unique_macro_groups']),
        'far_field_papers':max(0,breadth['required_far_field_papers']-far),
    }
    return {'preferred_domain_shortfalls':preferred_gaps,'breadth':breadth}
