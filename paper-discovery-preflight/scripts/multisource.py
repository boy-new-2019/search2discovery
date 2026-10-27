#!/usr/bin/env python3
"""Additive source routing, bounded continuation and status CLI."""
import argparse,json,pathlib
from literature_sources.coordinator import Coordinator,configure
from literature_sources.downloader import obtain
def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['configure','status','run','download','sync-memory'])
    p.add_argument('--workspace',required=True);p.add_argument('--online',action='store_true')
    p.add_argument('--max-requests',type=int,default=12);p.add_argument('--max-steps',type=int,default=24)
    p.add_argument('--limit',type=int,default=3);p.add_argument('--category',default='core')
    a=p.parse_args();ws=pathlib.Path(a.workspace).resolve()
    if a.command=='configure':result=configure(ws)
    elif a.command=='download':result=obtain(ws,online=a.online,limit=a.limit,category=a.category,request_limit=a.max_requests)
    else:
        c=Coordinator(ws,online=a.online,request_limit=a.max_requests)
        if a.command=='run':result=c.run(max_steps=a.max_steps)
        elif a.command=='status':result=c.status()
        else:c.seed();result=c.catalog.sync_memory()
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
