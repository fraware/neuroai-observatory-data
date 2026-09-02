#!/usr/bin/env python3
"""Apply explicit SU-TRIALS human decisions and draft a noncanonical Source-namespace successor."""
from __future__ import annotations
import argparse,hashlib,json,os,re,sys,tempfile
from pathlib import Path
from typing import Any,Callable,Mapping,NamedTuple
import run_su_trials_recorded_replay as replay
import stage_su_trials_human_review as staging
ROOT=Path(__file__).parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from current_source_namespace import materialize_effective_source_namespace
PROGRAMME_ID='SU-TRIALS-CTGOV-v0.1';HEX64=re.compile(r'^[0-9a-f]{64}$');PROPOSAL=re.compile(r'^DSP-[0-9a-f]{32}$');RUN=re.compile(r'^DRUN-[0-9a-f]{32}$');NCT=re.compile(r'^NCT[0-9]{8}$');DADJ=re.compile(r'^DADJ-[0-9a-f]{32}$');FINAL={'ACCEPT':'ACCEPTED','REJECT':'REJECTED','DEFER':'DEFERRED','EXCLUDE':'EXCLUDED'}
class WorkbenchAPI(NamedTuple):
 load_proposal:Callable[...,dict[str,Any]]
 load_adjudication:Callable[...,dict[str,Any]]
 adjudicate_candidate_source:Callable[...,dict[str,Any]]
def load_workbench_api()->WorkbenchAPI:
 try:
  from neuroai_workbench.discovery import adjudicate_candidate_source,load_adjudication,load_proposal
 except (ImportError,AttributeError) as exc:raise RuntimeError('Required Workbench adjudication API unavailable') from exc
 return WorkbenchAPI(load_proposal,load_adjudication,adjudicate_candidate_source)
def canon(v:Any)->bytes:return (json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode('utf-8')
def digest(v:Any)->str:return hashlib.sha256(canon(v)).hexdigest()
def sha(data:bytes)->str:return hashlib.sha256(data).hexdigest()
def load_json(p:Path)->Any:return json.loads(p.read_text(encoding='utf-8'))
def atomic_json(p:Path,v:Any)->None:
 p.parent.mkdir(parents=True,exist_ok=True);payload=json.dumps(v,indent=2,sort_keys=True,ensure_ascii=False)+'\n';fd,tmp=tempfile.mkstemp(prefix=f'.{p.name}.',dir=p.parent,text=True)
 try:
  with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as f:f.write(payload);f.flush();os.fsync(f.fileno())
  os.replace(tmp,p)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
def review_index(workspace:Path,path:Path)->dict[str,Any]:
 root=(workspace.resolve()/'programme-review'/PROGRAMME_ID).resolve();p=path.resolve()
 if not p.is_relative_to(root) or not p.is_file():raise ValueError('Review index must be an existing file inside SU-TRIALS review workspace')
 raw=p.read_bytes();v=json.loads(raw)
 if not isinstance(v,dict) or v.get('schema_version')!='0.1.0' or v.get('status')!='LOCAL_OPERATIONAL_HUMAN_REVIEW_INDEX' or v.get('programme_id')!=PROGRAMME_ID:raise ValueError('Review index contract/status mismatch')
 for k in ('automatic_mutation_performed','human_adjudication_performed','canonical_successor_ready'):
  if v.get(k) is not False:raise ValueError(f'Review index boundary weakened: {k}')
 for k in ('projection_manifest_sha256','projection_source_id_set_sha256','current_source_id_set_sha256','current_known_nct_index_sha256'):
  if not isinstance(v.get(k),str) or not HEX64.fullmatch(v[k]):raise ValueError(f'Review index digest invalid: {k}')
 if not isinstance(v.get('source_namespace_changed_since_projection'),bool):raise ValueError('Review index source-namespace drift flag missing')
 if v['source_namespace_changed_since_projection'] != (v['projection_source_id_set_sha256']!=v['current_source_id_set_sha256']):raise ValueError('Review index source-namespace drift flag inconsistent')
 run=v.get('workbench_run_id');query=v.get('workbench_query_id')
 if not isinstance(run,str) or not RUN.fullmatch(run) or not isinstance(query,str) or not query.startswith('DISCOVERY-'):raise ValueError('Review index Workbench binding invalid')
 rows=v.get('proposals')
 if not isinstance(rows,list) or not rows or v.get('proposal_count')!=len(rows):raise ValueError('Review index proposals invalid')
 by={};ncts=set()
 for r in rows:
  pid=r.get('proposal_id');nct=r.get('nct_id')
  if not isinstance(pid,str) or not PROPOSAL.fullmatch(pid) or pid in by or not isinstance(nct,str) or not NCT.fullmatch(nct) or nct in ncts:raise ValueError('Review index proposal/NCT identity invalid or duplicate')
  qs=r.get('query_ids')
  if not isinstance(qs,list) or not qs or qs!=sorted(set(qs)):raise ValueError(f'{pid}: invalid query memberships')
  for k in ('normalized_aggregate_digest','candidate_input_sha256'):
   if not isinstance(r.get(k),str) or not HEX64.fullmatch(r[k]):raise ValueError(f'{pid}: invalid provenance digest {k}')
  by[pid]=r;ncts.add(nct)
 return {'path':p,'sha256':sha(raw),'record':v,'proposal_rows':by}
def decision_packet(path:Path,review:Mapping[str,Any])->dict[str,Any]:
 if not path.is_file():raise ValueError('Decision packet missing')
 raw=path.read_bytes();v=json.loads(raw)
 if not isinstance(v,dict) or v.get('schema_version')!='0.1.0' or v.get('artifact')!='su_trials_human_decision_packet' or v.get('status')!='EXPLICIT_LOCAL_HUMAN_DECISION_PACKET' or v.get('programme_id')!=PROGRAMME_ID:raise ValueError('Decision packet contract/status mismatch')
 rr=review['record'];bindings={'projection_manifest_sha256':rr['projection_manifest_sha256'],'review_index_sha256':review['sha256'],'workbench_query_id':rr['workbench_query_id'],'workbench_run_id':rr['workbench_run_id']}
 for k,e in bindings.items():
  if v.get(k)!=e:raise ValueError(f'Decision packet binding mismatch: {k}')
 if not isinstance(v.get('adjudicated_by'),str) or not v['adjudicated_by'].strip() or not isinstance(v.get('adjudicated_at'),str) or len(v['adjudicated_at'])<10 or v.get('identity_boundary')!='LOCAL_UNAUTHENTICATED_ATTRIBUTION':raise ValueError('Decision packet attribution boundary invalid')
 boundary={'source_namespace_admission_only':True,'monitor_creation_authorized':False,'trial_entity_creation_authorized':False,'trial_site_relationship_creation_authorized':False,'assessment_mutation_authorized':False,'canonical_publication_authorized':False}
 for k,e in boundary.items():
  if v.get(k) is not e:raise ValueError(f'Decision packet authority boundary weakened: {k}')
 decisions=v.get('decisions');review_rows=review['proposal_rows']
 if not isinstance(decisions,list) or not decisions:raise ValueError('Decision packet decisions required')
 by={}
 for r in decisions:
  pid=r.get('proposal_id');nct=r.get('nct_id');d=r.get('decision');reason=r.get('rationale')
  if not isinstance(pid,str) or not PROPOSAL.fullmatch(pid) or pid in by or pid not in review_rows or nct!=review_rows[pid]['nct_id'] or d not in FINAL or not isinstance(reason,str) or not reason.strip():raise ValueError(f'Invalid decision row for {pid!r}')
  by[pid]=r
 if set(by)!=set(review_rows):raise ValueError('Decision packet must dispose every staged proposal exactly once')
 return {'path':path.resolve(),'sha256':sha(raw),'record':v,'decisions':by}
def projection_candidates(projection_dir:Path,review:Mapping[str,Any])->dict[str,dict[str,Any]]:
 verified=staging.verify_projection(projection_dir)
 if verified['manifest_sha256']!=review['record']['projection_manifest_sha256']:raise ValueError('Projection manifest differs from staged review index')
 by={}
 for c in verified['candidates']:
  nct=c.get('record_key') if isinstance(c,dict) else None
  if not isinstance(nct,str) or not NCT.fullmatch(nct) or nct in by:raise ValueError('Projection candidate identity invalid/duplicate')
  by[nct]=c
 if set(by)!={r['nct_id'] for r in review['proposal_rows'].values()}:raise ValueError('Projection candidate set differs from staged review index')
 for pid,r in review['proposal_rows'].items():
  c=by[r['nct_id']]
  if digest(c)!=r['candidate_input_sha256'] or c.get('query_ids')!=r['query_ids'] or c.get('normalized_aggregate_digest')!=r['normalized_aggregate_digest']:raise ValueError(f'{pid}: projection provenance mismatch')
 return by
def current_namespace()->dict[str,Any]:
 ns=materialize_effective_source_namespace();sources=ns.get('sources');sd=ns.get('source_id_set_sha256')
 if not isinstance(sources,list) or ns.get('materialized_source_count')!=248 or len(sources)!=248 or not isinstance(sd,str) or not HEX64.fullmatch(sd):raise ValueError('Current 248-Source namespace unavailable')
 ids={s.get('source_id') for s in sources if isinstance(s,dict)}
 if len(ids)!=248 or any(not isinstance(x,str) or not x for x in ids):raise ValueError('Current Source identity set invalid')
 n=replay.build_known_nct_source_index();mapping=n.get('nct_to_source')
 if n.get('source_id_set_sha256')!=sd or not isinstance(mapping,dict):raise ValueError('Current NCT index not bound to current Source namespace')
 return {'materialized_source_count':248,'source_ids':ids,'source_id_set_sha256':sd,'known_ctgov_nct_count':len(mapping),'nct_to_source':mapping,'known_nct_index_sha256':digest(dict(sorted(mapping.items())))}
def registry_successor_files(workspace:Path)->set[str]:
 root=workspace/'discovery'/'registry_successors';return {str(p.resolve()) for p in root.glob('*.json') if p.is_file()} if root.exists() else set()
def validate_proposal(p:Mapping[str,Any],review_row:Mapping[str,Any],candidate:Mapping[str,Any],review_record:Mapping[str,Any])->None:
 pid=review_row['proposal_id']
 if p.get('proposal_id')!=pid or p.get('run_id')!=review_record['workbench_run_id'] or p.get('query_id')!=review_record['workbench_query_id'] or p.get('classification')!='NEW' or p.get('automatic_mutation_performed') is not False:raise ValueError(f'{pid}: Workbench proposal binding invalid')
 ps=p.get('proposed_source');expected={'record_key':candidate['record_key'],'title':candidate['title'],'url':candidate['url'],'publisher':candidate['publisher'],'source_class':candidate['source_class'],'suggested_source_id':candidate['suggested_source_id']}
 if not isinstance(ps,dict) or any(ps.get(k)!=v for k,v in expected.items()):raise ValueError(f'{pid}: Workbench proposed Source drift')
def reconcile_existing(api:WorkbenchAPI,workspace:Path,p:Mapping[str,Any],decision:Mapping[str,Any],packet:Mapping[str,Any])->dict[str,Any]|None:
 if p.get('status')=='PENDING_HUMAN_ACCEPTANCE':
  if p.get('adjudication_id') is not None:raise ValueError(f"{p['proposal_id']}: pending proposal has adjudication_id")
  return None
 if p.get('status')!=FINAL[decision['decision']]:raise ValueError(f"{p['proposal_id']}: prior adjudication conflicts with decision packet")
 aid=p.get('adjudication_id')
 if not isinstance(aid,str) or not DADJ.fullmatch(aid):raise ValueError(f"{p['proposal_id']}: final proposal missing adjudication")
 a=api.load_adjudication(workspace,aid);expected={'proposal_id':p['proposal_id'],'run_id':p['run_id'],'decision':decision['decision'],'rationale':decision['rationale'],'adjudicated_by':packet['record']['adjudicated_by'],'adjudicated_at':packet['record']['adjudicated_at'],'registry_successor_id':None,'automatic_mutation_performed':False}
 if any(a.get(k)!=v for k,v in expected.items()):raise ValueError(f"{p['proposal_id']}: prior adjudication differs from packet")
 return a
def output_root(workspace:Path,run_id:str,packet_sha:str)->Path:return workspace/'programme-adjudication'/PROGRAMME_ID/run_id/packet_sha[:16]
def write_failure(root:Path,review:Mapping[str,Any],packet:Mapping[str,Any],completed:set[str],failed:str,error:Exception)->None:
 atomic_json(root/'adjudication-summary.json',{'schema_version':'0.1.0','status':'PARTIAL_WORKBENCH_ADJUDICATION_FAILURE','programme_id':PROGRAMME_ID,'projection_manifest_sha256':review['record']['projection_manifest_sha256'],'review_index_sha256':review['sha256'],'decision_packet_sha256':packet['sha256'],'workbench_run_id':review['record']['workbench_run_id'],'completed_proposal_ids':sorted(completed),'failed_proposal_id':failed,'remaining_proposal_ids':sorted(set(packet['decisions'])-completed-{failed}),'error':f'{type(error).__name__}: {error}','safe_resume_supported':True,'source_namespace_successor_emitted':False,'monitor_creation_performed':False,'trial_entity_creation_performed':False,'trial_site_relationship_creation_performed':False,'assessment_mutation_performed':False,'canonical_successor_ready':False})
def adjudicate(projection_dir:Path,workspace:Path,review_index_path:Path,decision_packet_path:Path,*,workbench_api:WorkbenchAPI|None=None)->dict[str,Any]:
 workspace=workspace.resolve();review=review_index(workspace,review_index_path);packet=decision_packet(decision_packet_path,review);candidates=projection_candidates(projection_dir,review);ns=current_namespace();api=workbench_api or load_workbench_api();root=output_root(workspace,review['record']['workbench_run_id'],packet['sha256']);rows=review['proposal_rows'];before=registry_successor_files(workspace);completed={};final_props={};accepted_source_ids=set()
 for pid in sorted(rows):
  rr=rows[pid];c=candidates[rr['nct_id']];p=api.load_proposal(workspace,pid);validate_proposal(p,rr,c,review['record']);d=packet['decisions'][pid]
  if d['decision']=='ACCEPT':
   if rr['nct_id'] in ns['nct_to_source']:raise ValueError(f"STALE_ACCEPT_RECLASSIFICATION_REQUIRED: {rr['nct_id']} is now controlled")
   sid=c['suggested_source_id']
   if sid in ns['source_ids'] or sid in accepted_source_ids:raise ValueError(f'STALE_ACCEPT_SOURCE_ID_COLLISION: {sid}')
   accepted_source_ids.add(sid)
  existing=reconcile_existing(api,workspace,p,d,packet)
  if existing is not None:completed[pid]=existing;final_props[pid]=p
 for pid in sorted(rows):
  if pid in completed:continue
  d=packet['decisions'][pid]
  try:
   result=api.adjudicate_candidate_source(workspace,pid,d['decision'],rationale=d['rationale'],actor=packet['record']['adjudicated_by'],create_successor=False,adjudicated_at=packet['record']['adjudicated_at'])
   if not isinstance(result,dict) or result.get('successor') is not None:raise ValueError('WORKBENCH_REGISTRY_SUCCESSOR_LEAKAGE')
   a=result.get('adjudication');p=result.get('proposal')
   if not isinstance(a,dict) or not isinstance(p,dict):raise ValueError('Workbench adjudication result invalid')
   expected={'proposal_id':pid,'decision':d['decision'],'rationale':d['rationale'],'adjudicated_by':packet['record']['adjudicated_by'],'adjudicated_at':packet['record']['adjudicated_at'],'registry_successor_id':None,'automatic_mutation_performed':False}
   if any(a.get(k)!=v for k,v in expected.items()) or p.get('status')!=FINAL[d['decision']] or p.get('automatic_mutation_performed') is not False:raise ValueError(f'{pid}: Workbench adjudication boundary mismatch')
   if registry_successor_files(workspace)!=before:raise ValueError('WORKBENCH_REGISTRY_SUCCESSOR_LEAKAGE')
   completed[pid]=a;final_props[pid]=p
  except Exception as exc:
   write_failure(root,review,packet,set(completed),pid,exc);raise RuntimeError(f'PARTIAL_WORKBENCH_ADJUDICATION_FAILURE at {pid}; safe resume supported') from exc
 if set(completed)!=set(rows) or registry_successor_files(workspace)!=before:raise ValueError('Adjudication did not reconcile exactly or leaked Workbench successor')
 accepted=sorted(pid for pid,d in packet['decisions'].items() if d['decision']=='ACCEPT');successor=None;successor_path=None
 if accepted:
  basis={'programme_id':PROGRAMME_ID,'projection_manifest_sha256':review['record']['projection_manifest_sha256'],'review_index_sha256':review['sha256'],'decision_packet_sha256':packet['sha256'],'base_source_id_set_sha256':ns['source_id_set_sha256'],'base_known_nct_index_sha256':ns['known_nct_index_sha256'],'accepted_proposal_ids':accepted,'accepted_source_ids':[candidates[rows[pid]['nct_id']]['suggested_source_id'] for pid in accepted]};sid='SNSP-'+digest(basis)[:32];accepted_sources=[]
  for pid in accepted:
   rr=rows[pid];c=candidates[rr['nct_id']];a=completed[pid];aid=a.get('adjudication_id')
   if not isinstance(aid,str) or not DADJ.fullmatch(aid):raise ValueError(f'{pid}: adjudication identity invalid')
   accepted_sources.append({'source_id':c['suggested_source_id'],'nct_id':c['record_key'],'title':c['title'],'publisher':c['publisher'],'canonical_locator':c['url'],'source_class':c['source_class'],'source_origin':'DISCOVERY_CTGOV_RECORDED_REPLAY_HUMAN_ACCEPTED','namespace_admission_state':'PROPOSED_NOT_CANONICAL','from_proposal_id':pid,'workbench_adjudication_id':aid,'query_ids':rr['query_ids'],'normalized_aggregate_digest':rr['normalized_aggregate_digest'],'candidate_input_sha256':rr['candidate_input_sha256'],'claim_boundary':'Human ACCEPT supports only draft Source-identity admission. It does not establish clinical truth, trial/site relationships, authorization, safety, effectiveness, conformance, monitoring, assessment effect, or publication.'})
  successor={'schema_version':'0.1.0','artifact':'source_namespace_successor_proposal','status':'DRAFT_NONCANONICAL_SOURCE_NAMESPACE_SUCCESSOR','proposal_id':sid,'programme_id':PROGRAMME_ID,'created_at':packet['record']['adjudicated_at'],'created_by':packet['record']['adjudicated_by'],'identity_boundary':'LOCAL_UNAUTHENTICATED_ATTRIBUTION','base_source_namespace':{'materialized_source_count':248,'source_id_set_sha256':ns['source_id_set_sha256'],'known_ctgov_nct_count':ns['known_ctgov_nct_count'],'known_nct_index_sha256':ns['known_nct_index_sha256']},'decision_provenance':{'projection_manifest_sha256':review['record']['projection_manifest_sha256'],'review_index_sha256':review['sha256'],'decision_packet_sha256':packet['sha256'],'workbench_query_id':review['record']['workbench_query_id'],'workbench_run_id':review['record']['workbench_run_id'],'projection_source_id_set_sha256':review['record']['projection_source_id_set_sha256'],'staging_source_id_set_sha256':review['record']['current_source_id_set_sha256']},'accepted_proposal_ids':accepted,'accepted_sources':accepted_sources,'overwrite_refused':True,'source_namespace_publication_performed':False,'monitor_creation_performed':False,'trial_entity_creation_performed':False,'trial_site_relationship_creation_performed':False,'assessment_mutation_performed':False,'canonical_successor_ready':False,'authority_boundary':'Draft Source-namespace succession only; no canonical Source registry, monitoring, graph mutation, assessment update, publication authorization, or institutional endorsement.'};successor_path=root/f'{sid}.json';atomic_json(successor_path,successor)
 dispositions=[{'proposal_id':pid,'nct_id':rows[pid]['nct_id'],'decision':packet['decisions'][pid]['decision'],'rationale':packet['decisions'][pid]['rationale'],'workbench_adjudication_id':completed[pid]['adjudication_id'],'proposal_final_status':FINAL[packet['decisions'][pid]['decision']]} for pid in sorted(rows)];summary={'schema_version':'0.1.0','status':'COMPLETED_WITH_DRAFT_SOURCE_NAMESPACE_SUCCESSOR' if successor else 'COMPLETED_NO_SOURCE_NAMESPACE_ACCEPTANCES','programme_id':PROGRAMME_ID,'projection_manifest_sha256':review['record']['projection_manifest_sha256'],'review_index_sha256':review['sha256'],'decision_packet_sha256':packet['sha256'],'workbench_query_id':review['record']['workbench_query_id'],'workbench_run_id':review['record']['workbench_run_id'],'adjudicated_by':packet['record']['adjudicated_by'],'adjudicated_at':packet['record']['adjudicated_at'],'identity_boundary':'LOCAL_UNAUTHENTICATED_ATTRIBUTION','base_source_id_set_sha256':ns['source_id_set_sha256'],'proposal_count':len(rows),'accept_count':len(accepted),'dispositions':dispositions,'source_namespace_successor_proposal_id':successor['proposal_id'] if successor else None,'source_namespace_successor_path':str(successor_path) if successor_path else None,'workbench_monitor_registry_successor_created':False,'source_namespace_publication_performed':False,'monitor_creation_performed':False,'trial_entity_creation_performed':False,'trial_site_relationship_creation_performed':False,'assessment_mutation_performed':False,'canonical_successor_ready':False};sp=root/'adjudication-summary.json';atomic_json(sp,summary)
 return {'status':summary['status'],'programme_id':PROGRAMME_ID,'decision_packet_sha256':packet['sha256'],'proposal_count':len(rows),'accept_count':len(accepted),'summary_path':str(sp),'source_namespace_successor_proposal_id':successor['proposal_id'] if successor else None,'source_namespace_successor_path':str(successor_path) if successor_path else None,'workbench_monitor_registry_successor_created':False,'monitor_creation_performed':False,'trial_entity_creation_performed':False,'trial_site_relationship_creation_performed':False,'assessment_mutation_performed':False,'canonical_successor_ready':False}
def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--projection-dir',type=Path,required=True);ap.add_argument('--workspace',type=Path,required=True);ap.add_argument('--review-index',type=Path,required=True);ap.add_argument('--decision-packet',type=Path,required=True);a=ap.parse_args();print(json.dumps(adjudicate(a.projection_dir,a.workspace,a.review_index,a.decision_packet),indent=2,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
