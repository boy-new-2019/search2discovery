#!/usr/bin/env python3
"""Zero-LLM bibliographic priority queue; NEVER a substitute for S1/S2.

Read only the user's real v5 OpenAlex selected entries. Report small staged
fulltext reading waves; no external model and no downloads are performed.
"""
from __future__ import annotations
import argparse, datetime as dt, json, pathlib, sys
from collections import Counter
import pro5x_optimizer as opt

TARGET={'core':12,'related':3,'inspiration':2}

def tier(record:dict,now:dt.date)->tuple:
    try: age=(now-dt.date.fromisoformat(record['publication_date'])).days
    except (ValueError,KeyError,TypeError):age=999999
    # bibliographic metadata heuristic, NEVER scholarly relevance certification
    oa=bool(record.get('oa_pdf_url'))
    return (0 if oa else 1,0 if record.get('priority_venue_shortlist_match') else 1,
            0 if age<=1096 else 1, -float(record.get('relevance_score') or 0),
            -int(record.get('cited_by_count') or 0), str(record.get('id','')))

def shortlist(ws:pathlib.Path,*,core:int=12,related:int=3,inspiration:int=2)->dict:
    ws=ws.expanduser().resolve()
    if any(type(n) is not int or not 0<=n<=30 for n in (core,related,inspiration)) or core<1:
        raise ValueError('Input, evidence or workflow invariant failed at pro5x_shortlist.shortlist (check 26); inspect the signed task record and original source.')
    f=ws/'output'/'discovery_preflight'/'paper_library.json'
    if not f.is_file():
        return {'status':'NEEDS_REAL_V5_BIBLIOGRAPHY','message':'Source state and independent reviewer provenance must satisfy the specified quality gate.'}
    data=opt.read(f)
    if data.get('provenance')!='OpenAlex bibliographic metadata only':
        raise ValueError('Input, evidence or workflow invariant failed at pro5x_shortlist.shortlist (check 32); inspect the signed task record and original source.')
    pools=data.get('selected',{})
    asof=dt.date.fromisoformat(data['as_of_date'])
    limits={'core':core,'related':related,'inspiration':inspiration}
    out={'schema_version':1,'as_of_date':data['as_of_date'],
         'source_file_sha256':opt.sha(f),'status':'BIBLIOGRAPHIC_PRIORITY_ONLY_NOT_S1_S2_OR_READ',
         'waves':{},'remaining':{},'source_count':{},
         'no_llm_calls':True,'no_pdfs_downloaded_by_this_operation':True,
         'warning':'Research evidence and workflow notes (pro5x_shortlist.shortlist). Use original source evidence; keep frozen constraints and independent quality gates.'}
    for category,n in limits.items():
        rows=pools.get(category,[])
        if not isinstance(rows,list):raise ValueError('Input, evidence or workflow invariant failed at pro5x_shortlist.shortlist (check 43); inspect the signed task record and original source.'+category)
        seen=set(); clean=[]
        for record in rows:
            if not isinstance(record,dict) or not record.get('title') or not record.get('id'):continue
            if record['id'] in seen:continue
            seen.add(record['id']);clean.append(record)
        eligible=sorted(clean,key=lambda x:tier(x,asof))
        # Soft venue diversity, without hiding high relevance works permanently.
        chosen=[];venuecounts=Counter()
        for x in eligible:
            if len(chosen)>=n:break
            source=x.get('source_id') or x.get('venue') or x['id']
            if venuecounts[source]>=3:continue
            chosen.append(x);venuecounts[source]+=1
        for x in eligible:
            if len(chosen)>=n:break
            if x not in chosen:chosen.append(x)
        out['waves'][category]=[{'id':x['id'],'title':x['title'],'year':x.get('year'),
           'venue':x.get('venue'), 'doi':x.get('doi'),'landing_url':x.get('landing_url'),
           'oa_pdf_url':x.get('oa_pdf_url'), 'priority_venue_shortlist_match':x.get('priority_venue_shortlist_match',False),
           'metadata_relevance_score':x.get('relevance_score'),
           'requires_real_S1_S2_and_fulltext_confirmation':True} for x in chosen]
        out['remaining'][category]=len(clean)-len(chosen)
        out['source_count'][category]=len(clean)
    outdir=ws/'output'/'research_cognition'/'pro5x_survival'
    opt.write(outdir/'first_wave.json',out)
    lines=['This section indexes existing source-verified reviewer observations. It does not certify scientific validity, novelty or new experimental outcomes.','','This section indexes existing source-verified reviewer observations. It does not certify scientific validity, novelty or new experimental outcomes.',
           'This section indexes existing source-verified reviewer observations. It does not certify scientific validity, novelty or new experimental outcomes.','']
    for cat in ('core','related','inspiration'):
        lines.append('## '+cat)
        for row in out['waves'][cat]:
            lines.append('- '+row['title']+' ('+str(row['year'])+') | '+str(row['venue'])+' | '+('This section indexes existing source-verified reviewer observations. It does not certify scientific validity, novelty or new experimental outcomes.' if row['oa_pdf_url'] else 'This section indexes existing source-verified reviewer observations. It does not certify scientific validity, novelty or new experimental outcomes.'))
    (outdir/'first_wave.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return {'status':'SHORTLIST_ONLY_NOT_DEEPREAD',
            'metadata_counts':out['source_count'],
            'first_wave_counts':{k:len(v) for k,v in out['waves'].items()},
            'not_assessed':out['remaining'],
            'output_file':str(outdir/'first_wave.json'),
            'plan_file':str(outdir/'first_wave.md'),
            'warning':out['warning']}

def main(argv=None):
    p=argparse.ArgumentParser(description='Rank authentic v5 OpenAlex metadata for a small first-wave study, no model calls')
    p.add_argument('--workspace',type=pathlib.Path,required=True)
    for key,val in TARGET.items():p.add_argument('--'+key,type=int,default=val)
    x=p.parse_args(argv)
    try: print(json.dumps(shortlist(x.workspace,core=x.core,related=x.related,inspiration=x.inspiration),ensure_ascii=False,indent=2));return 0
    except (ValueError,KeyError,OSError) as ex:
        print(json.dumps({'status':'BLOCKED','error':str(ex)},ensure_ascii=False),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
