"""Validate standalone agent profiles and explicit native compatibility routes."""
from __future__ import annotations
import pathlib,tomllib,hashlib
RCE={
 'rce_cartographer_sol':('gpt-6.1-sol','medium'),
 'rce_contradiction_astra':('gpt-6-astra','high'),
 'rce_evidence_sol':('gpt-6.1-sol','high'),
 'rce_evolution_analyst_sol':('gpt-6.1-sol','medium'),
 'rce_evolution_auditor_astra':('gpt-6-astra','high'),
 'rce_experiment_sol':('gpt-6.1-sol','high'),
 'rce_general_manager_astra':('gpt-6-astra','high'),
 'rce_hypothesis_sol':('gpt-6.1-sol','high'),
 'rce_method_sol':('gpt-6.1-sol','high'),
 'rce_novelty_sol':('gpt-6.1-sol','high'),
 'rce_skeptic_astra':('gpt-6-astra','xhigh')}
def audit(folder):
 import profiles,engine
 expected={k:(v[0],v[1]) for k,v in profiles.ROLE_INFO.items()};expected.update(RCE)
 rows=[];errors=[]
 for name,route in sorted(expected.items()):
  p=pathlib.Path(folder)/(name+'.toml')
  try:
   d=tomllib.loads(p.read_text(encoding='utf8'))
   if d.get('name')!=name:raise ValueError('Profile identity mismatch')
   if any(not isinstance(d.get(k),str) or not d[k].strip() for k in ('description','developer_instructions')):raise ValueError('Required instructions missing')
   if (d.get('model'),d.get('model_reasoning_effort'))!=route:raise ValueError('Unverified model/effort route')
   rows.append({'name':name,'model':route[0],'effort':route[1],'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
  except (OSError,ValueError) as ex:errors.append({'role':name,'error':str(ex)})
 for stage,names in engine.DEFAULT_ROLES.items():
  for name in names:
   if name not in expected:errors.append({'stage':stage,'error':'Unknown routed role '+name})
 extras=sorted(p.stem for p in pathlib.Path(folder).glob('*.toml') if p.stem.startswith(('bpd_','rce_')) and p.stem not in expected)
 if extras:errors.append({'error':'Unexpected scientific roles','roles':extras})
 return {'status':'VALID' if not errors and len(rows)==27 else 'BLOCKED','profiles':rows,'errors':errors,'runtime_startup':'REQUIRES_SEPARATE_NATIVE_RECEIPTS'}
def dispatch_profile(folder,name,available_roles):
 result=audit(folder)
 if result['status']!='VALID':raise ValueError('Agent profile doctor blocked')
 row=next((x for x in result['profiles'] if x['name']==name),None)
 if not row:raise ValueError('Unknown role')
 d=tomllib.loads((pathlib.Path(folder)/(name+'.toml')).read_text('utf8'))
 return {**row,'agent_type':name if name in available_roles else 'default',
         'route':'NATIVE_NAMED_TYPE' if name in available_roles else 'NATIVE_DEFAULT_EXPLICIT_PROFILE_AND_MODEL',
         'instructions':d['developer_instructions'],'provider_attestation':False,
         'must_use_distinct_real_native_thread':True}
