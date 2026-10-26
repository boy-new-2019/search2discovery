#!/usr/bin/env python3
"""Experiment results feedback: provenance and independent review required.

Cannot perform experiments or invent metrics. Even reviewed logs are NOT a
proof of causal efficacy or publication-quality replication.
"""
from __future__ import annotations
import pathlib,os
from typing import Any
import store


def ingest(ws:pathlib.Path,packet:dict,review:dict)->dict:
    if not isinstance(packet,dict) or set(packet)!={'plan_id','experiment_log_path','observations','interpretation','claimed_direction'}:
        raise ValueError('Feedback packet must have only the mandatory explicit fields')
    if packet['claimed_direction'] not in ('SUPPORT','COUNTER','INCONCLUSIVE'):
        raise ValueError('Feedback direction must be SUPPORT/COUNTER/INCONCLUSIVE')
    if not isinstance(packet.get('observations'),list) or not packet['observations'] or len(packet['observations'])>80:
        raise ValueError('Feedback needs explicit test results, not a verbal assertion')
    for obs in packet['observations']:
        if not isinstance(obs,dict) or set(obs)!={'metric','value','baseline','conditions','repeats'}:
            raise ValueError('Each result needs metric/value/baseline/conditions/repeats')
        for fld in ('metric','conditions'):
            if not isinstance(obs[fld],str) or len(obs[fld].strip())<(2 if fld=='metric' else 4):raise ValueError(f'Invalid {fld}')
        for fld in ('value','baseline'):
            if type(obs[fld]) not in (float,int):raise ValueError('Metric values must be numeric')
        if type(obs['repeats']) is not int or obs['repeats']<1:raise ValueError('Invalid repeat count')
    if not isinstance(packet['interpretation'],str) or len(packet['interpretation'].strip())<30:
        raise ValueError('Feedback interpretation and confounders required')
    log=pathlib.Path(packet['experiment_log_path']).expanduser().resolve()
    if not log.is_file() or log.stat().st_size<30:raise ValueError('Missing actual experiment log artifact')
    if not isinstance(review,dict) or set(review)!={'role','thread_ref','verdict','reason','log_sha256'}:
        raise ValueError('Independent feedback audit record is required')
    if (review['role']!='rce_evidence_sol' or review['verdict'] not in ('PASS','VETO')
        or not isinstance(review['thread_ref'],str) or len(review['thread_ref'])<5
        or not isinstance(review['reason'],str) or len(review['reason'].strip())<20):
        raise ValueError('Independent source/result review invalid')
    sha=store.hashbytes(log.read_bytes())
    if review['log_sha256']!=sha:raise ValueError('Reviewer did not check this exact experiment log')
    with store.connect(ws) as c:
        plan=c.execute('SELECT hypothesis_id FROM experiments WHERE plan_id=?',(packet['plan_id'],)).fetchone()
        if not plan:raise ValueError('Unknown proposed experiment')
        hid=plan['hypothesis_id']
        fid='FB-'+store.hashobj({'plan_id':packet['plan_id'],'log_sha':sha,'observations':packet['observations']})[:16]
        if c.execute('SELECT 1 FROM feedback WHERE feedback_id=?',(fid,)).fetchone():
            raise ValueError('Same feedback artifact already processed; append a new real replicate instead of double-counting')
        status='VETOED_EVIDENCE_INVALID' if review['verdict']=='VETO' else 'REVIEWED_EXPERIMENT_NOT_CAUSAL_PROOF'
        c.execute('INSERT INTO feedback VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
              (fid,packet['plan_id'],str(log),sha,store.dump(packet['observations']),packet['interpretation'],
               packet['claimed_direction'],review['verdict'],review['role'],review['thread_ref'],status,store.utc()))
        if review['verdict']=='PASS':
            c.execute('UPDATE hypotheses SET status=? WHERE hypothesis_id=?',
                      ('REAL_EXPERIMENT_OBSERVED_REQUIRES_REPLICATION',hid))
        store.event(c,'EXPERIMENT_FEEDBACK',{'feedback_id':fid,'plan_id':packet['plan_id'],
                        'hypothesis_id':hid,'log_sha':sha,'review_verdict':review['verdict'],
                        'scientific_causality_verified':False})
    return {'status':status,'feedback_id':fid,'hypothesis_id':hid,'log_sha256':sha,
            'next':'re-evaluate hypothesis on new evidence, test replicates, and consider a new cognition cycle'}
