#!/usr/bin/env python3
"""Materialize human-accepted SU-TRIALS Source candidates and separate monitoring proposals."""
from __future__ import annotations
import argparse,hashlib,json,re
from pathlib import Path
from typing import Any,Mapping
import adjudicate_su_trials_source_namespace as adjudication
import build_monitoring_eligibility as monitoring
PROGRAMME_ID='SU-TRIALS-CTGOV-v0.1';SUCCESSOR=re.compile(r'^SNSP-[0-9a-f]{32}$');HEX64=re.compile(r'^[0-9a-f]{64}$');NCT=re.compile(r'^NCT[0-9]{8}$');DSP=re.compile(r'^DSP-[0-9a-f]{32}$');DADJ=re.compile(r'^DADJ-[0-9a-f]{32}$')
def canon(v:Any)->bytes:return (json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode('utf-8')
def digest(v:Any)->str:return hashlib.sha256(canon(v)).hexdigest()
def sha(data:bytes)->str:return hashlib.sha256(data).hexdigest()
def load_successor(path:Path)->dict[str,Any]:
 if not path.is_file():raise ValueError('Source-namespace successor proposal missing')
 raw=path.read_bytes();v=json.loads(raw)
 if not isinstance(v,dict) or v.get('schema_version')!='0.1.0' or v.get('artifact')!='source_namespace_successor_proposal' or v.get('status')!='DRAFT_NONCANONICAL_SOURCE_NAMESPACE_SUCCESSOR' or v.get('programme_id')!=PROGRAMME_ID:raise ValueError('Source-namespace successor contract/status mismatch')
 if not isinstance(v.get('proposal_id'),str) or not SUCCESSOR.fullmatch(v['proposal_id']):raise ValueError('Source-namespace successor proposal_id invalid')
 flags={'overwrite_refused':True,'source_namespace_publication_performed':False,'monitor_creation_performed':False,'trial_entity_creation_performed':False,'trial_site_relationship_creation_performed':False,'assessment_mutation_performed':False,'canonical_successor_ready':False}
 for k,e in flags.items():
  if v.get(k) is not e:raise ValueError(f'Source successor boundary weakened: {k}')
 base=v.get('base_source_namespace');prov=v.get('decision_provenance');accepted_ids=v.get('accepted_proposal_ids');accepted=v.get('accepted_sources')
 if not isinstance(base,dict) or base.get('materialized_source_count')!=248 or not isinstance(base.get('source_id_set_sha256'),str) or not HEX64.fullmatch(base['source_id_set_sha256']) or not isinstance(base.get('known_nct_index_sha256'),str) or not HEX64.fullmatch(base['known_nct_index_sha256']):raise ValueError('Source successor base namespace invalid')
 if not isinstance(prov,dict):raise ValueError('Source successor decision provenance missing')
 for k in ('projection_manifest_sha256','review_index_sha256','decision_packet_sha256','projection_source_id_set_sha256','staging_source_id_set_sha256'):
  if not isinstance(prov.get(k),str) or not HEX64.fullmatch(prov[k]):raise ValueError(f'Invalid successor provenance digest: {k}')
 if not isinstance(prov.get('workbench_run_id'),str) or not re.fullmatch(r'DRUN-[0-9a-f]{32}',prov['workbench_run_id']):raise ValueError('Invalid successor Workbench run')
 if not isinstance(accepted_ids,list) or not accepted_ids or accepted_ids!=sorted(set(accepted_ids)) or not isinstance(accepted,list) or len(accepted)!=len(accepted_ids):raise ValueError('Accepted Source/proposal set invalid')
 sids=set();ncts=set();pids=set()
 for r in accepted:
  sid=r.get('source_id');nct=r.get('nct_id');pid=r.get('from_proposal_id');aid=r.get('workbench_adjudication_id')
  if not isinstance(sid,str) or not sid or sid in sids or not isinstance(nct,str) or not NCT.fullmatch(nct) or nct in ncts or not isinstance(pid,str) or not DSP.fullmatch(pid) or pid in pids or pid not in accepted_ids or not isinstance(aid,str) or not DADJ.fullmatch(aid):raise ValueError('Accepted Source identity/provenance invalid or duplicate')
  sids.add(sid);ncts.add(nct);pids.add(pid)
  if r.get('source_origin')!='DISCOVERY_CTGOV_RECORDED_REPLAY_HUMAN_ACCEPTED' or r.get('namespace_admission_state')!='PROPOSED_NOT_CANONICAL' or r.get('source_class')!='OFFICIAL_TRIAL_REGISTRY':raise ValueError(f'{sid}: accepted Source state/class invalid')
  if r.get('canonical_locator')!=f'https://clinicaltrials.gov/study/{nct}' or r.get('publisher')!='ClinicalTrials.gov':raise ValueError(f'{sid}: accepted Source locator/publisher invalid')
  qs=r.get('query_ids')
  if not isinstance(qs,list) or not qs or qs!=sorted(set(qs)):raise ValueError(f'{sid}: query provenance invalid')
  for k in ('normalized_aggregate_digest','candidate_input_sha256'):
   if not isinstance(r.get(k),str) or not HEX64.fullmatch(r[k]):raise ValueError(f'{sid}: invalid accepted Source digest {k}')
 if pids!=set(accepted_ids):raise ValueError('Accepted Source/proposal identity sets differ')
 return {'path':path.resolve(),'file_sha256':sha(raw),'record':v}
def require_unchanged_base(successor:Mapping[str,Any])->dict[str,Any]:
 current=adjudication.current_namespace();base=successor['base_source_namespace'];checks={'materialized_source_count':current['materialized_source_count'],'source_id_set_sha256':current['source_id_set_sha256'],'known_ctgov_nct_count':current['known_ctgov_nct_count'],'known_nct_index_sha256':current['known_nct_index_sha256']}
 for k,e in checks.items():
  if base.get(k)!=e:raise ValueError(f'SOURCE_NAMESPACE_BASE_DRIFT_REBASE_REQUIRED: {k} successor={base.get(k)!r} current={e!r}')
 return current
def source_candidate(successor:Mapping[str,Any],accepted:Mapping[str,Any])->dict[str,Any]:
 d=successor['decision_provenance'];base=successor['base_source_namespace']
 return {'schema_version':'2.0.0-draft','source_id':accepted['source_id'],'title':accepted['title'],'publisher':accepted['publisher'],'canonical_locator':accepted['canonical_locator'],'source_class':accepted['source_class'],'legacy_source_ids':[],'source_claim_boundary':accepted['claim_boundary'],'source_origin':'DISCOVERY_HUMAN_ACCEPTED_SOURCE_NAMESPACE_PROPOSAL','discovery_provenance':{'source_namespace_successor_proposal_id':successor['proposal_id'],'programme_id':PROGRAMME_ID,'projection_manifest_sha256':d['projection_manifest_sha256'],'review_index_sha256':d['review_index_sha256'],'decision_packet_sha256':d['decision_packet_sha256'],'workbench_query_id':d['workbench_query_id'],'workbench_run_id':d['workbench_run_id'],'workbench_proposal_id':accepted['from_proposal_id'],'workbench_adjudication_id':accepted['workbench_adjudication_id'],'nct_id':accepted['nct_id'],'query_ids':accepted['query_ids'],'normalized_aggregate_digest':accepted['normalized_aggregate_digest'],'candidate_input_sha256':accepted['candidate_input_sha256'],'projection_source_id_set_sha256':d['projection_source_id_set_sha256'],'staging_source_id_set_sha256':d['staging_source_id_set_sha256'],'adjudication_base_source_id_set_sha256':base['source_id_set_sha256']},'record_state':'NONCANONICAL_DISCOVERY_ADMITTED_CANDIDATE','authority_boundary':'Human-accepted Source identity materialized as a noncanonical candidate only; no substantive truth, monitor, Trial/site relation, assessment effect, regulatory status, or canonical publication is established.'}
def monitoring_proposal(successor_id:str,source:Mapping[str,Any])->dict[str,Any]:
 mode,cadence,priority,reason=monitoring._rule_for(source['source_class'],source['title']);basis={'source_namespace_successor_proposal_id':successor_id,'source_id':source['source_id'],'nct_id':source['discovery_provenance']['nct_id'],'recommended_mode':mode,'recommended_cadence':cadence,'priority':priority,'reason':reason}
 return {'proposal_id':'SMEP-'+digest(basis)[:32],'source_id':source['source_id'],'nct_id':source['discovery_provenance']['nct_id'],'source_class':source['source_class'],'recommended_mode':mode,'recommended_cadence':cadence,'priority':priority,'reason':reason,'review_state':'PENDING_MONITOR_REVIEW','monitor_present':False,'monitor_creation_performed':False}
def materialize(successor_path:Path)->dict[str,Any]:
 loaded=load_successor(successor_path);s=loaded['record'];current=require_unchanged_base(s);sources=sorted((source_candidate(s,r) for r in s['accepted_sources']),key=lambda x:x['source_id']);ids=[r['source_id'] for r in sources];ncts=[r['discovery_provenance']['nct_id'] for r in sources]
 if len(ids)!=len(set(ids)) or len(ncts)!=len(set(ncts)):raise ValueError('Materialized candidate identities not unique')
 for src in sources:
  if src['source_id'] in current['source_ids']:raise ValueError(f"SOURCE_NAMESPACE_BASE_COLLISION: {src['source_id']}")
  if src['discovery_provenance']['nct_id'] in current['nct_to_source']:raise ValueError(f"SOURCE_NAMESPACE_NCT_COLLISION: {src['discovery_provenance']['nct_id']}")
 proposals=[monitoring_proposal(s['proposal_id'],src) for src in sources]
 if len({p['proposal_id'] for p in proposals})!=len(proposals):raise ValueError('Monitoring proposal IDs not unique')
 monitoring_package={'schema_version':'0.1.0','artifact':'source_monitoring_eligibility_proposal','status':'NONCANONICAL_PENDING_MONITOR_REVIEW','source_namespace_successor_proposal_id':s['proposal_id'],'source_candidate_count':len(sources),'proposals':proposals,'automatic_registry_mutation':False,'monitor_creation_performed':False,'source_namespace_publication_performed':False,'trial_entity_creation_performed':False,'trial_site_relationship_creation_performed':False,'assessment_mutation_performed':False,'canonical_successor_ready':False,'authority_boundary':'Monitoring recommendations only; no monitor-registry entry, cadence, collection authorization, graph relation, assessment, or publication is created.'}
 rec={'schema_version':'0.1.0','scope':'DISCOVERY_ORIGIN_SOURCE_MATERIALIZATION_AND_MONITORING_PROPOSAL_ONLY','source_namespace_successor_proposal_id':s['proposal_id'],'source_namespace_successor_file_sha256':loaded['file_sha256'],'base_materialized_source_count':248,'base_source_id_set_sha256':current['source_id_set_sha256'],'base_known_ctgov_nct_count':current['known_ctgov_nct_count'],'base_known_nct_index_sha256':current['known_nct_index_sha256'],'accepted_source_count':len(s['accepted_sources']),'materialized_source_candidate_count':len(sources),'monitoring_proposal_count':len(proposals),'all_source_ids_unique':True,'all_nct_ids_unique':True,'monitoring_classifier':'build_monitoring_eligibility._rule_for','automatic_registry_mutation':False,'source_namespace_publication_performed':False,'monitor_creation_performed':False,'trial_entity_creation_performed':False,'trial_site_relationship_creation_performed':False,'assessment_mutation_performed':False,'canonical_successor_ready':False,'authority_boundary':'Deterministic noncanonical Source-candidate materialization and monitoring recommendation only.'}
 return {'schema_version':'0.1.0','status':'NONCANONICAL_DISCOVERY_SOURCE_MATERIALIZATION','source_namespace_successor_proposal_id':s['proposal_id'],'source_namespace_successor_file_sha256':loaded['file_sha256'],'sources':sources,'monitoring':monitoring_package,'reconciliation':rec}
def json_bytes(v:Any)->bytes:return (json.dumps(v,indent=2,sort_keys=True,ensure_ascii=False)+'\n').encode('utf-8')
def jsonl_bytes(rows:list[Mapping[str,Any]])->bytes:return b''.join((json.dumps(r,sort_keys=True,ensure_ascii=False)+'\n').encode('utf-8') for r in rows)
def write_exact(path:Path,payload:bytes)->None:
 path.parent.mkdir(parents=True,exist_ok=True)
 if path.exists():
  if path.read_bytes()!=payload:raise ValueError(f'OUTPUT_COLLISION_REFUSED: {path}')
  return
 path.write_bytes(payload)
def write_projection(result:Mapping[str,Any],output_dir:Path)->dict[str,Any]:
 out=output_dir.resolve();payloads={'discovery-sources.jsonl':jsonl_bytes(list(result['sources'])),'monitoring-eligibility-proposals.json':json_bytes(result['monitoring']),'reconciliation.json':json_bytes(result['reconciliation'])}
 for n,p in payloads.items():write_exact(out/n,p)
 files=[{'path':n,'sha256':sha(p),'bytes':len(p)} for n,p in sorted(payloads.items())];m={'schema_version':'0.1.0','status':'NONCANONICAL_DISCOVERY_SOURCE_MATERIALIZATION','source_namespace_successor_proposal_id':result['source_namespace_successor_proposal_id'],'source_namespace_successor_file_sha256':result['source_namespace_successor_file_sha256'],'file_count':len(files),'files':files,'source_namespace_publication_performed':False,'monitor_creation_performed':False,'trial_entity_creation_performed':False,'trial_site_relationship_creation_performed':False,'assessment_mutation_performed':False,'canonical_successor_ready':False,'authority_boundary':'Checksum manifest for noncanonical Source candidates and monitoring proposals only; not a governing release manifest.'};write_exact(out/'manifest.json',json_bytes(m));return m
def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--source-namespace-successor',type=Path,required=True);ap.add_argument('--output-dir',type=Path,required=True);a=ap.parse_args();r=materialize(a.source_namespace_successor);m=write_projection(r,a.output_dir);print(json.dumps({'status':r['status'],'source_candidate_count':len(r['sources']),'monitoring_proposal_count':len(r['monitoring']['proposals']),'manifest':m},indent=2,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
