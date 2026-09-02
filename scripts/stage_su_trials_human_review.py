#!/usr/bin/env python3
"""Stage one verified current SU-TRIALS replay into local Workbench human review."""
from __future__ import annotations
import argparse,hashlib,json,os,re,tempfile
from pathlib import Path
from typing import Any,Callable,Mapping,NamedTuple
import run_su_trials_recorded_replay as replay
PROGRAMME_ID="SU-TRIALS-CTGOV-v0.1"
EXPECTED_FILES={"normalized-studies.jsonl","known-duplicates.jsonl","new-candidate-inputs.jsonl","input-provenance.json","known-source-index-summary.json","query-reports.json","reconciliation.json"}
HEX64=re.compile(r"^[0-9a-f]{64}$")
class WorkbenchAPI(NamedTuple):
 store_query:Callable[...,dict[str,Any]]
 execute_discovery_query:Callable[...,dict[str,Any]]
def load_workbench_api()->WorkbenchAPI:
 try:
  from neuroai_workbench.discovery import execute_discovery_query,store_query
 except (ImportError,AttributeError) as exc:raise RuntimeError("Required Workbench discovery API unavailable") from exc
 return WorkbenchAPI(store_query,execute_discovery_query)
def sha(data:bytes)->str:return hashlib.sha256(data).hexdigest()
def canon(v:Any)->bytes:return (json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode("utf-8")
def digest(v:Any)->str:return sha(canon(v))
def load_json(path:Path)->Any:return json.loads(path.read_text(encoding="utf-8"))
def load_jsonl(path:Path)->list[dict[str,Any]]:
 out=[]
 for i,line in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
  if not line.strip():continue
  row=json.loads(line)
  if not isinstance(row,dict):raise ValueError(f"{path.name}:{i}: JSONL row must be object")
  out.append(row)
 return out
def atomic_json(path:Path,v:Any)->None:
 path.parent.mkdir(parents=True,exist_ok=True);payload=json.dumps(v,indent=2,sort_keys=True,ensure_ascii=False)+"\n";fd,tmp=tempfile.mkstemp(prefix=f".{path.name}.",dir=path.parent,text=True)
 try:
  with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as f:f.write(payload);f.flush();os.fsync(f.fileno())
  os.replace(tmp,path)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
def verify_projection(projection_dir:Path)->dict[str,Any]:
 root=projection_dir.resolve();mp=root/"manifest.json"
 if not mp.is_file():raise ValueError("Replay projection missing manifest.json")
 mb=mp.read_bytes();m=json.loads(mb)
 if not isinstance(m,dict) or m.get("programme_id")!=PROGRAMME_ID or m.get("status")!="NONCANONICAL_SU_TRIALS_RECORDED_REPLAY_PROJECTION":raise ValueError("Replay manifest identity/status mismatch")
 for k in ("canonical_successor_ready","raw_api_page_payloads_emitted","participant_level_data_emitted"):
  if m.get(k) is not False:raise ValueError(f"Replay manifest boundary weakened: {k}")
 entries=m.get("files")
 if not isinstance(entries,list) or m.get("file_count")!=len(entries):raise ValueError("Replay manifest file metadata invalid")
 paths=[e.get("path") for e in entries if isinstance(e,dict)]
 if set(paths)!=EXPECTED_FILES or len(paths)!=len(set(paths)):raise ValueError("Replay manifest file set mismatch")
 for e in entries:
  rel=e.get("path")
  if not isinstance(rel,str) or Path(rel).name!=rel:raise ValueError("Unsafe replay manifest path")
  p=root/rel
  if not p.is_file():raise ValueError(f"Replay file missing: {rel}")
  data=p.read_bytes();expected=e.get("sha256")
  if not isinstance(expected,str) or not HEX64.fullmatch(expected) or sha(data)!=expected or e.get("bytes")!=len(data):raise ValueError(f"Replay manifest verification failed: {rel}")
 rec=load_json(root/"reconciliation.json");prov=load_json(root/"input-provenance.json");summary=load_json(root/"known-source-index-summary.json");reports=load_json(root/"query-reports.json");candidates=load_jsonl(root/"new-candidate-inputs.jsonl")
 if not isinstance(rec,dict) or rec.get("mechanically_complete") is not True:raise ValueError("Replay projection is not mechanically complete")
 for k in ("raw_api_page_payloads_emitted","participant_level_data_emitted","automatic_source_admission","automatic_trial_entity_creation","automatic_trial_site_relationship_creation","automatic_monitor_creation","automatic_assessment_mutation","human_adjudication_performed","global_neuroai_trial_recall_claim","registry_completeness_claim","canonical_successor_ready"):
  if rec.get(k) is not False:raise ValueError(f"Replay reconciliation boundary weakened: {k}")
 if not isinstance(prov,dict) or not isinstance(summary,dict) or not isinstance(reports,list):raise ValueError("Replay provenance/summary/reports invalid")
 ds={prov.get("controlled_source_id_set_sha256"),summary.get("source_id_set_sha256"),rec.get("controlled_source_id_set_sha256")}
 if len(ds)!=1 or not all(isinstance(x,str) and HEX64.fullmatch(x) for x in ds):raise ValueError("Replay Source namespace digest mismatch")
 return {"root":root,"manifest_sha256":sha(mb),"reconciliation":rec,"input_provenance":prov,"projection_source_id_set_sha256":next(iter(ds)),"candidates":candidates,"query_reports":reports}
def validate_candidates(candidates:list[dict[str,Any]],current_index:Mapping[str,Any])->list[dict[str,Any]]:
 p=replay.programme();configured={r["query_id"] for r in p["query_streams"] if r.get("status")=="ACTIVE"};current=current_index.get("nct_to_source")
 if not isinstance(current,dict):raise ValueError("Current controlled NCT index unavailable")
 seen=set();out=[]
 for r in sorted(candidates,key=lambda x:str(x.get("record_key") or "")):
  nct=r.get("record_key")
  if not isinstance(nct,str) or not re.fullmatch(r"NCT\d{8}",nct) or nct in seen:raise ValueError(f"Invalid/duplicate NEW candidate NCT {nct!r}")
  seen.add(nct)
  if nct in current:raise ValueError(f"STALE_PROJECTION_RECLASSIFICATION_REQUIRED: {nct} is now controlled as {current[nct]}")
  if r.get("classification_hint")!="NEW" or r.get("duplicate_of_source_id") is not None:raise ValueError(f"{nct}: invalid NEW classification")
  if r.get("url")!=f"https://clinicaltrials.gov/study/{nct}" or r.get("publisher")!="ClinicalTrials.gov" or r.get("source_class")!="OFFICIAL_TRIAL_REGISTRY" or r.get("suggested_source_id")!=f"SRC-CTGOV-{nct}":raise ValueError(f"{nct}: candidate source boundary mismatch")
  qs=r.get("query_ids")
  if not isinstance(qs,list) or not qs or qs!=sorted(set(qs)) or not set(qs).issubset(configured):raise ValueError(f"{nct}: invalid query memberships")
  ag=r.get("normalized_aggregate_digest")
  if not isinstance(ag,str) or not HEX64.fullmatch(ag):raise ValueError(f"{nct}: invalid normalized digest")
  out.append(r)
 return out
def union_query(manifest_sha:str,captured_at:str,count:int)->dict[str,Any]:
 p=replay.programme();suffix=manifest_sha[:12].upper();qid=f"DISCOVERY-CTGOV-SU-TRIALS-UNION-{suffix}"
 return {"query_id":qid,"object_family":"DISCOVERY_QUERY","query_text":f"Manifest-bound union of {PROGRAMME_ID} configured ClinicalTrials.gov streams","filters":{"programme_id":PROGRAMME_ID,"projection_manifest_sha256":manifest_sha,"original_query_ids":sorted(r["query_id"] for r in p["query_streams"] if r.get("status")=="ACTIVE"),"candidate_count":count,"execution_semantics":"OFFLINE_REPLAY_SANITIZED_UNION"},"source_system":"CLINICALTRIALS_GOV","created_at":captured_at,"created_by":"SU-TRIALS-RECORDED-REPLAY-STAGER","status":"ACTIVE","network_access_required":False,"notes":"Operational review union only; per-candidate query memberships remain in the review index.","boundary":"Local manifest-bound review query only; no completeness, Source admission, trial/site relationship, assessment, or canonical authority."}
def existing_staging(workspace:Path,manifest_sha:str)->dict[str,Any]|None:
 rr=workspace/"programme-review"/PROGRAMME_ID
 if not rr.exists():return None
 matches=[]
 for p in sorted(rr.glob("*.json")):
  v=load_json(p)
  if not isinstance(v,dict) or v.get("status")!="LOCAL_OPERATIONAL_HUMAN_REVIEW_INDEX" or v.get("programme_id")!=PROGRAMME_ID:raise ValueError(f"Unexpected review-index file {p.name}")
  if v.get("projection_manifest_sha256")==manifest_sha:matches.append(v)
 if len(matches)>1:raise ValueError("DUPLICATE_OPERATIONAL_STAGING_STATE")
 return matches[0] if matches else None
def stage_projection(projection_dir:Path,workspace:Path,*,actor:str="local-user",staged_at:str|None=None,workbench_api:WorkbenchAPI|None=None)->dict[str,Any]:
 verified=verify_projection(projection_dir);current=replay.build_known_nct_source_index();current_map=current.get("nct_to_source");current_sd=current.get("source_id_set_sha256")
 if current.get("materialized_source_count")!=248 or not isinstance(current_map,dict) or not isinstance(current_sd,str) or not HEX64.fullmatch(current_sd):raise ValueError("Current controlled Source namespace unavailable")
 candidates=validate_candidates(verified["candidates"],current);workspace=workspace.resolve();workspace.mkdir(parents=True,exist_ok=True)
 old=existing_staging(workspace,verified["manifest_sha256"])
 if old is not None:raise ValueError(f"PROJECTION_ALREADY_STAGED: manifest already bound to run {old.get('workbench_run_id')}")
 current_nct_sha=digest(dict(sorted(current_map.items())));changed=current_sd!=verified["projection_source_id_set_sha256"]
 if not candidates:return {"status":"NO_NEW_CANDIDATES_TO_STAGE","programme_id":PROGRAMME_ID,"projection_manifest_sha256":verified["manifest_sha256"],"candidate_count":0,"discovery_run_id":None,"review_index_path":None,"projection_source_id_set_sha256":verified["projection_source_id_set_sha256"],"current_source_id_set_sha256":current_sd,"source_namespace_changed_since_projection":changed,"current_known_nct_index_sha256":current_nct_sha,"automatic_mutation_performed":False,"human_adjudication_performed":False,"canonical_successor_ready":False}
 captured=verified["input_provenance"].get("captured_at")
 if not isinstance(captured,str) or not captured:raise ValueError("Replay captured_at missing")
 when=staged_at or captured;api=workbench_api or load_workbench_api();query=union_query(verified["manifest_sha256"],captured,len(candidates));api.store_query(workspace,query)
 records=[{"record_key":r["record_key"],"title":r["title"],"url":r["url"],"publisher":r["publisher"],"source_class":r["source_class"],"suggested_source_id":r["suggested_source_id"],"classification_hint":"NEW"} for r in candidates]
 outcome=api.execute_discovery_query(workspace,query["query_id"],actor=actor,execution_mode="OFFLINE_REPLAY",result_records=records,executed_at=when)
 if not isinstance(outcome,dict) or not isinstance(outcome.get("run"),dict) or not isinstance(outcome.get("proposals"),list):raise ValueError("Invalid Workbench staging outcome")
 run=outcome["run"];props=outcome["proposals"]
 if run.get("query_id")!=query["query_id"] or run.get("execution_mode")!="OFFLINE_REPLAY" or run.get("automatic_registry_mutation_performed") is not False:raise ValueError("Workbench staging run boundary mismatch")
 if run.get("result_counts")!={"total":len(candidates),"new":len(candidates),"duplicate":0,"excluded":0} or len(props)!=len(candidates):raise ValueError("Workbench staging classification/proposal count mismatch")
 by_candidate={r["record_key"]:r for r in candidates};by_prop={}
 for pr in props:
  ps=pr.get("proposed_source") if isinstance(pr,dict) else None;nct=ps.get("record_key") if isinstance(ps,dict) else None
  if nct not in by_candidate or nct in by_prop or pr.get("classification")!="NEW" or pr.get("status")!="PENDING_HUMAN_ACCEPTANCE" or pr.get("automatic_mutation_performed") is not False:raise ValueError(f"Invalid Workbench proposal {nct!r}")
  by_prop[nct]=pr
 if set(by_prop)!=set(by_candidate):raise ValueError("Workbench proposal identity set mismatch")
 rows=[]
 for nct in sorted(by_candidate):
  pid=by_prop[nct].get("proposal_id")
  if not isinstance(pid,str) or not pid:raise ValueError(f"{nct}: proposal_id missing")
  c=by_candidate[nct];rows.append({"proposal_id":pid,"nct_id":nct,"query_ids":c["query_ids"],"normalized_aggregate_digest":c["normalized_aggregate_digest"],"candidate_input_sha256":digest(c)})
 run_id=run.get("run_id")
 if not isinstance(run_id,str) or not run_id:raise ValueError("Workbench run_id missing")
 index={"schema_version":"0.1.0","status":"LOCAL_OPERATIONAL_HUMAN_REVIEW_INDEX","programme_id":PROGRAMME_ID,"projection_manifest_sha256":verified["manifest_sha256"],"projection_source_id_set_sha256":verified["projection_source_id_set_sha256"],"current_source_id_set_sha256":current_sd,"source_namespace_changed_since_projection":changed,"current_known_nct_index_sha256":current_nct_sha,"current_known_ctgov_nct_count":len(current_map),"materialized_source_namespace_count":248,"workbench_query_id":query["query_id"],"workbench_run_id":run_id,"staged_at":when,"staged_by":actor,"identity_boundary":"Actor is a local workflow identity; this record does not authenticate identity, independence, delegation, or institutional authority.","proposal_count":len(rows),"proposals":rows,"automatic_mutation_performed":False,"human_adjudication_performed":False,"canonical_successor_ready":False,"authority_boundary":"Operational proposal index only. No proposal is accepted, no Source is admitted, no trial/site relationship or assessment is changed, and no canonical publication is authorized."}
 path=workspace/"programme-review"/PROGRAMME_ID/f"{run_id}.json";atomic_json(path,index)
 return {"status":"STAGED_FOR_HUMAN_ACCEPTANCE","programme_id":PROGRAMME_ID,"projection_manifest_sha256":verified["manifest_sha256"],"projection_source_id_set_sha256":verified["projection_source_id_set_sha256"],"current_source_id_set_sha256":current_sd,"source_namespace_changed_since_projection":changed,"current_known_nct_index_sha256":current_nct_sha,"candidate_count":len(candidates),"discovery_query_id":query["query_id"],"discovery_run_id":run_id,"proposal_ids":[r["proposal_id"] for r in rows],"review_index_path":str(path),"automatic_mutation_performed":False,"human_adjudication_performed":False,"canonical_successor_ready":False}
def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument("--projection-dir",type=Path,required=True);ap.add_argument("--workspace",type=Path,required=True);ap.add_argument("--actor",default="local-user");ap.add_argument("--staged-at");a=ap.parse_args();print(json.dumps(stage_projection(a.projection_dir,a.workspace,actor=a.actor,staged_at=a.staged_at),indent=2,sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
