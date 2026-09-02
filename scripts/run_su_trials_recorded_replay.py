#!/usr/bin/env python3
"""Deterministic recorded replay for the current bounded ClinicalTrials.gov SU-TRIALS programme."""
from __future__ import annotations
import argparse,hashlib,json,re,sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any,Callable
ROOT=Path(__file__).parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from current_source_namespace import materialize_effective_source_namespace
PROGRAMME=ROOT/"curation"/"clinicaltrials_discovery_programme_v0.1.json"
NCT_RE=re.compile(r"\bNCT\d{8}\b",re.I)
HEX64=re.compile(r"^[0-9a-f]{64}$")
NORMALIZED_FIELDS={"record_kind","nct_id","brief_title","overall_status","study_type","last_update_post_date","primary_completion_date","enrollment_count","phase","field_digests","aggregate_digest","boundary"}
DIGEST_FIELDS={"nct_id","brief_title","overall_status","study_type","last_update_post_date","primary_completion_date","enrollment_count","phase"}
Projector=Callable[...,dict[str,Any]]
def canon(v:Any)->bytes:return (json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode("utf-8")
def digest(v:Any)->str:return hashlib.sha256(canon(v)).hexdigest()
def load(path:Path)->Any:return json.loads(path.read_text(encoding="utf-8"))
def programme()->dict[str,Any]:
 p=load(PROGRAMME);d=p.get("workbench_dependency") or {}
 if p.get("programme_id")!="SU-TRIALS-CTGOV-v0.1" or d.get("required_capability")!="project_clinicaltrials_search_pages" or d.get("integration_state")!="AVAILABLE":raise ValueError("Invalid/current SU-TRIALS programme dependency")
 return p
def load_workbench()->tuple[Any,Projector]:
 try:
  from neuroai_workbench.collector.adapters.clinicaltrials import ClinicalTrialsGovAdapter
  from neuroai_workbench.discovery import project_clinicaltrials_search_pages
 except (ImportError,AttributeError) as exc:raise RuntimeError("Required Workbench ClinicalTrials projector unavailable") from exc
 return ClinicalTrialsGovAdapter.__new__(ClinicalTrialsGovAdapter),project_clinicaltrials_search_pages
def build_known_nct_source_index()->dict[str,Any]:
 ns=materialize_effective_source_namespace();sources=ns.get("sources");sd=ns.get("source_id_set_sha256")
 if not isinstance(sources,list) or ns.get("materialized_source_count")!=248 or len(sources)!=248:raise ValueError("Expected exact current 248-Source namespace")
 if not isinstance(sd,str) or not HEX64.fullmatch(sd):raise ValueError("Current Source-ID-set digest unavailable")
 mapping:dict[str,str]={};lineage={}
 for s in sources:
  loc=s.get("canonical_locator");sid=s.get("source_id")
  if not isinstance(loc,str) or "clinicaltrials.gov" not in loc.lower():continue
  ncts=sorted({m.group(0).upper() for m in NCT_RE.finditer(loc)})
  if len(ncts)>1:raise ValueError(f"{sid}: ClinicalTrials.gov locator contains multiple NCT identifiers")
  if not ncts:continue
  nct=ncts[0];prior=mapping.get(nct)
  if prior is not None and prior!=sid:raise ValueError(f"Conflicting controlled Sources for {nct}")
  mapping[nct]=str(sid);lineage[nct]={"source_id":str(sid),"lineage_family":str(s.get("lineage_family") or "")}
 return {"materialized_source_count":248,"source_id_set_sha256":sd,"known_ctgov_nct_count":len(mapping),"nct_to_source":dict(sorted(mapping.items())),"nct_lineage":{k:lineage[k] for k in sorted(lineage)},"global_completeness_claim":False}
def validate_bundle(bundle:Mapping[str,Any],p:dict[str,Any])->tuple[str,list[dict[str,Any]],dict[str,dict[str,Any]]]:
 if bundle.get("schema_version")!="0.1.0" or bundle.get("programme_id")!=p["programme_id"]:raise ValueError("Replay identity mismatch")
 scope=bundle.get("capture_scope")
 if scope not in {"FULL_PROGRAMME","PARTIAL_VALIDATION"}:raise ValueError("Invalid capture_scope")
 if not isinstance(bundle.get("captured_at"),str) or not bundle["captured_at"].strip():raise ValueError("captured_at required")
 caps=bundle.get("query_captures");configured={r["query_id"]:dict(r) for r in p["query_streams"] if r.get("status")=="ACTIVE"}
 if not isinstance(caps,list) or not caps:raise ValueError("query_captures required")
 seen=set()
 for c in caps:
  if not isinstance(c,dict):raise ValueError("query capture must be object")
  q=c.get("query_id")
  if q not in configured or q in seen:raise ValueError("Unconfigured or duplicate query capture")
  seen.add(q)
  if c.get("query_term")!=configured[q]["query_term"]:raise ValueError(f"{q}: query term mismatch")
  if not isinstance(c.get("count_total_first_page_requested"),bool) or not isinstance(c.get("count_total_later_pages_requested"),bool):raise ValueError(f"{q}: countTotal request flags must be boolean")
  pages=c.get("pages")
  if not isinstance(pages,list) or not pages or not all(isinstance(x,dict) for x in pages):raise ValueError(f"{q}: pages required")
 if scope=="FULL_PROGRAMME" and seen!=set(configured):raise ValueError("FULL_PROGRAMME requires all active query streams")
 return str(scope),caps,configured
def blockers(c:Mapping[str,Any],cov:Mapping[str,Any],p:Mapping[str,Any])->list[str]:
 out=[];rp=p["request_policy"]
 if c.get("count_total_first_page_requested") is not rp["count_total_first_page"]:out.append("COUNT_TOTAL_FIRST_PAGE_POLICY_MISMATCH")
 if c.get("count_total_later_pages_requested") is not rp["count_total_later_pages"]:out.append("COUNT_TOTAL_LATER_PAGE_POLICY_MISMATCH")
 missing=sorted(set(p["coverage_contract"]["required_metrics"])-set(cov))
 if missing:out.append("MISSING_COVERAGE_METRICS:"+",".join(missing))
 for k,e in p["coverage_contract"]["mechanical_completion_requires"].items():
  if cov.get(k)!=e:out.append(f"COVERAGE_GATE:{k}:{cov.get(k)!r}!={e!r}")
 if cov.get("registry_completeness_claim") is not False:out.append("REGISTRY_COMPLETENESS_BOUNDARY_VIOLATION")
 if cov.get("neuroai_discovery_recall_claim") is not False:out.append("NEUROAI_RECALL_BOUNDARY_VIOLATION")
 if cov.get("automatic_registry_mutation_performed") is not False:out.append("AUTOMATIC_MUTATION_BOUNDARY_VIOLATION")
 return out
def validate_normalized(n:Mapping[str,Any])->str:
 if set(n)!=NORMALIZED_FIELDS:raise ValueError(f"Unexpected normalized ClinicalTrials fields: {sorted(set(n)-NORMALIZED_FIELDS)}")
 if n.get("record_kind")!="NORMALIZED_CTGOV_STUDY":raise ValueError("Unexpected normalized record_kind")
 nct=n.get("nct_id")
 if not isinstance(nct,str) or not re.fullmatch(r"NCT\d{8}",nct):raise ValueError("Invalid normalized NCT identity")
 if str(n.get("study_type") or "").upper()!="INTERVENTIONAL":raise ValueError(f"{nct}: emitted normalized candidate must be INTERVENTIONAL")
 fd=n.get("field_digests")
 if not isinstance(fd,dict) or set(fd)!=DIGEST_FIELDS or any(not isinstance(v,str) or not HEX64.fullmatch(v) for v in fd.values()):raise ValueError(f"{nct}: invalid field_digests")
 ag=n.get("aggregate_digest")
 if not isinstance(ag,str) or not HEX64.fullmatch(ag):raise ValueError(f"{nct}: invalid aggregate_digest")
 return nct
def build_replay(bundle:Mapping[str,Any],*,adapter:Any|None=None,projector:Projector|None=None,known_index:Mapping[str,Any]|None=None)->dict[str,Any]:
 p=programme();scope,caps,configured=validate_bundle(bundle,p)
 if adapter is None or projector is None:
  a,pr=load_workbench();adapter=adapter if adapter is not None else a;projector=projector if projector is not None else pr
 known=dict(known_index) if known_index is not None else build_known_nct_source_index();known_map=known.get("nct_to_source");sd=known.get("source_id_set_sha256")
 if known.get("materialized_source_count")!=248 or not isinstance(known_map,dict) or not isinstance(sd,str) or not HEX64.fullmatch(sd):raise ValueError("Known NCT index must bind exact current 248-Source namespace and digest")
 for a in p["known_identifier_anchors"]:
  if known_map.get(a["nct_id"])!=a["existing_source_id"]:raise ValueError("Configured ClinicalTrials anchor does not match current Source namespace")
 reports=[];union={};blocker_count=0;raw_pages=0
 for c in sorted(caps,key=lambda x:str(x["query_id"])):
  q=str(c["query_id"]);cfg=configured[q];raw_pages+=len(c["pages"])
  proj=projector(adapter,query_id=q,query_text=cfg["query_term"],pages=c["pages"],required_study_types=cfg["post_retrieval_required_study_types"],known_nct_sources=known_map)
  cov=proj.get("coverage");records=proj.get("result_records");norms=proj.get("normalized_records")
  if not isinstance(cov,dict) or not isinstance(records,list) or not isinstance(norms,list):raise ValueError(f"{q}: invalid Workbench projection shape")
  if cov.get("query_id")!=q or cov.get("query_text")!=cfg["query_term"] or cov.get("required_study_types")!=["INTERVENTIONAL"]:raise ValueError(f"{q}: Workbench coverage identity mismatch")
  bs=blockers(c,cov,p);blocker_count+=len(bs);reports.append({"query_id":q,"query_term":cfg["query_term"],"capture_sha256":digest(c),"coverage":cov,"mechanical_blockers":bs})
  by_nct={}
  for raw in norms:
   if not isinstance(raw,dict):raise ValueError(f"{q}: normalized record must be object")
   nct=validate_normalized(raw)
   if nct in by_nct:raise ValueError(f"{q}: duplicate normalized NCT identity")
   by_nct[nct]=raw
  for r in records:
   if not isinstance(r,dict):raise ValueError(f"{q}: candidate must be object")
   nct=r.get("record_key")
   if nct not in by_nct:raise ValueError(f"{q}: candidate lacks normalized study")
   expected_dup=known_map.get(nct);expected_class="DUPLICATE" if expected_dup else "NEW"
   if r.get("classification_hint")!=expected_class:raise ValueError(f"{q}/{nct}: candidate classification disagrees with current Source namespace")
   if expected_dup and r.get("duplicate_of_source_id")!=expected_dup:raise ValueError(f"{q}/{nct}: duplicate Source identity mismatch")
   if not expected_dup and r.get("duplicate_of_source_id") is not None:raise ValueError(f"{q}/{nct}: NEW candidate cannot carry duplicate identity")
   if r.get("url")!=f"https://clinicaltrials.gov/study/{nct}" or r.get("publisher")!="ClinicalTrials.gov" or r.get("source_class")!="OFFICIAL_TRIAL_REGISTRY":raise ValueError(f"{q}/{nct}: candidate source identity boundary mismatch")
   core={k:r.get(k) for k in ("record_key","title","url","publisher","source_class","suggested_source_id","classification_hint","duplicate_of_source_id")}
   n=by_nct[nct];prior=union.get(nct)
   if prior is None:union[nct]={"normalized":n,"aggregate_digest":n["aggregate_digest"],"candidate":core,"queries":{q}}
   else:
    if prior["aggregate_digest"]!=n["aggregate_digest"] or prior["normalized"]!=n or prior["candidate"]!=core:raise ValueError(f"Cross-query conflict for {nct}")
    prior["queries"].add(q)
 normalized=[];dups=[];new=[];repeat=0
 for nct in sorted(union):
  e=union[nct];qs=sorted(e["queries"]);repeat+=max(0,len(qs)-1);normalized.append({"nct_id":nct,"query_ids":qs,"normalized_study":e["normalized"]});cand={**e["candidate"],"query_ids":qs,"normalized_aggregate_digest":e["aggregate_digest"]};(dups if cand["classification_hint"]=="DUPLICATE" else new).append(cand)
 executed={str(c["query_id"]) for c in caps};all_active=executed==set(configured);complete=scope=="FULL_PROGRAMME" and all_active and blocker_count==0
 rec={"scope":scope,"configured_active_query_count":len(configured),"executed_query_count":len(executed),"all_active_queries_executed":all_active,"query_mechanical_blocker_count":blocker_count,"union_unique_nct_count":len(union),"known_controlled_duplicate_count":len(dups),"new_candidate_input_count":len(new),"cross_query_repeat_membership_count":repeat,"materialized_source_namespace_count":248,"controlled_source_id_set_sha256":sd,"known_ctgov_nct_count_before_run":known.get("known_ctgov_nct_count"),"raw_input_page_count":raw_pages,"raw_api_page_payloads_emitted":False,"participant_level_data_emitted":False,"automatic_source_admission":False,"automatic_trial_entity_creation":False,"automatic_trial_site_relationship_creation":False,"automatic_monitor_creation":False,"automatic_assessment_mutation":False,"human_adjudication_performed":False,"mechanically_complete":complete,"global_neuroai_trial_recall_claim":False,"registry_completeness_claim":False,"canonical_successor_ready":False}
 return {"schema_version":"0.1.0","status":"NONCANONICAL_SU_TRIALS_RECORDED_REPLAY_PROJECTION","programme_id":p["programme_id"],"input_provenance":{"bundle_sha256":digest(bundle),"captured_at":bundle["captured_at"],"api_data_timestamp":bundle.get("api_data_timestamp"),"controlled_source_id_set_sha256":sd,"known_nct_index_sha256":digest(known_map),"raw_provider_pages_retained_in_output":False},"known_source_index_summary":{"materialized_source_count":248,"source_id_set_sha256":sd,"known_ctgov_nct_count":known.get("known_ctgov_nct_count"),"global_completeness_claim":False},"query_reports":reports,"normalized_studies":normalized,"known_duplicates":dups,"new_candidate_inputs":new,"reconciliation":rec}
def write_jsonl(path:Path,rows:list[dict[str,Any]])->dict[str,Any]:
 payload=b"".join(canon(r) for r in rows);path.write_bytes(payload);return {"path":path.name,"bytes":len(payload),"sha256":hashlib.sha256(payload).hexdigest(),"records":len(rows)}
def write_projection(result:Mapping[str,Any],out:Path)->dict[str,Any]:
 out.mkdir(parents=True,exist_ok=True);files=[]
 for key,name in (("normalized_studies","normalized-studies.jsonl"),("known_duplicates","known-duplicates.jsonl"),("new_candidate_inputs","new-candidate-inputs.jsonl")):files.append(write_jsonl(out/name,list(result[key])))
 for key,name in (("input_provenance","input-provenance.json"),("known_source_index_summary","known-source-index-summary.json"),("query_reports","query-reports.json"),("reconciliation","reconciliation.json")):
  payload=canon(result[key]);(out/name).write_bytes(payload);files.append({"path":name,"bytes":len(payload),"sha256":hashlib.sha256(payload).hexdigest(),"records":1})
 manifest={"programme_id":result["programme_id"],"status":result["status"],"files":sorted(files,key=lambda x:x["path"]),"file_count":len(files),"raw_api_page_payloads_emitted":False,"participant_level_data_emitted":False,"canonical_successor_ready":False};payload=canon(manifest);(out/"manifest.json").write_bytes(payload);return {**manifest,"manifest_sha256":hashlib.sha256(payload).hexdigest()}
def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument("--input-bundle",type=Path,required=True);ap.add_argument("--output-dir",type=Path,required=True);a=ap.parse_args();r=build_replay(load(a.input_bundle.resolve()));m=write_projection(r,a.output_dir.resolve());print(json.dumps({"reconciliation":r["reconciliation"],"manifest":m},indent=2,sort_keys=True));return 0 if r["reconciliation"]["mechanically_complete"] else 1
if __name__=="__main__":raise SystemExit(main())
