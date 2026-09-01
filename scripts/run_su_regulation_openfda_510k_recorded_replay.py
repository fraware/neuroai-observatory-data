#!/usr/bin/env python3
"""Deterministic recorded replay for bounded openFDA 510(k) discovery."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote_plus

try:
    from scripts.current_source_namespace import materialize_effective_source_namespace
except ModuleNotFoundError:
    from current_source_namespace import materialize_effective_source_namespace

ROOT=Path(__file__).parents[1]
PROGRAMME=ROOT/"curation"/"openfda_510k_discovery_programme_v0.1.json"
K_LOCATOR_RE=re.compile(r'(?:k_number|510k|510\(k\))\s*(?:=|:|/)\s*"?((?:BK|K)[A-Za-z0-9._-]+)"?',re.I)
K_ID_RE=re.compile(r'^(?:K|BK)[A-Z0-9._-]+$',re.I)
DEN_ID_RE=re.compile(r'^DEN[A-Z0-9._-]+$',re.I)
Projector=Callable[...,dict[str,Any]]
ALLOWED_NORMALIZED_FIELDS={
    "record_kind","k_number","device_name","applicant","date_received","decision_date","decision_code",
    "decision_description","clearance_type","product_code","statement_or_summary","expedited_review_flag",
    "third_party_flag","decision_semantics","decision_supports_substantial_equivalence","decision_code_recognized",
    "query_memberships","boundary","normalized_record_sha256",
}

def _canon(v:Any)->bytes:return (json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode("utf-8")
def _digest(v:Any)->str:return hashlib.sha256(_canon(v)).hexdigest()
def _load(p:Path)->Any:return json.loads(p.read_text(encoding="utf-8"))

def _programme()->dict[str,Any]:
    p=_load(PROGRAMME);dep=p.get("workbench_dependency") or {}
    if p.get("programme_id")!="SU-REGULATION-OPENFDA-510K-v0.1":raise ValueError("Invalid 510(k) programme")
    if dep.get("required_capability")!="project_openfda_510k_pages" or dep.get("integration_state")!="AVAILABLE":raise ValueError("Current merged 510(k) capability unavailable")
    return p

def _load_projector()->Projector:
    try:from neuroai_workbench.discovery import project_openfda_510k_pages
    except (ImportError,AttributeError) as exc:raise RuntimeError("Required Workbench 510(k) projector unavailable") from exc
    return project_openfda_510k_pages

def _eligible(source:Mapping[str,Any])->bool:
    token=str(source.get("source_class") or "").upper();return "REGULATORY" in token or "510" in token or "CLEARANCE" in token

def _k_from_locator(locator:str)->set[str]:
    text=unquote_plus(locator);return {m.group(1).upper() for m in K_LOCATOR_RE.finditer(text) if K_ID_RE.fullmatch(m.group(1).upper())}

def build_known_k_source_index()->dict[str,Any]:
    ns=materialize_effective_source_namespace();sources=ns.get("sources");source_digest=ns.get("source_id_set_sha256")
    if ns.get("materialized_source_count")!=248 or not isinstance(sources,list) or len(sources)!=248:raise ValueError("Expected exact 248-Source controlled namespace")
    if not isinstance(source_digest,str) or len(source_digest)!=64:raise ValueError("Controlled Source digest unavailable")
    eligible:set[str]=set();index:dict[str,str]={};lineage:dict[str,dict[str,str]]={}
    for source in sources:
        if not isinstance(source,Mapping):raise ValueError("Controlled Source row must be object")
        sid=source.get("source_id")
        if not isinstance(sid,str) or not sid:raise ValueError("Controlled Source missing source_id")
        if not _eligible(source):continue
        eligible.add(sid);locator=source.get("canonical_locator")
        if not isinstance(locator,str):continue
        for k in sorted(_k_from_locator(locator)):
            prior=index.get(k)
            if prior is not None and prior!=sid:raise ValueError(f"Conflicting controlled Sources for k_number {k}")
            index[k]=sid;lineage[k]={"source_id":sid,"lineage_family":str(source.get("lineage_family") or "")}
    return {"materialized_source_count":248,"source_id_set_sha256":source_digest,"regulatory_typed_source_count":len(eligible),"known_k_number_count":len(index),"k_to_source":dict(sorted(index.items())),"k_lineage":{k:lineage[k] for k in sorted(lineage)},"global_510k_completeness_claim":False}

def _active(p:Mapping[str,Any])->dict[str,dict[str,Any]]:return {str(r["query_id"]):dict(r) for r in p["query_streams"] if r.get("status")=="ACTIVE"}
def _date8(v:Any,field:str)->str:
    if not isinstance(v,str) or not re.fullmatch(r"\d{8}",v):raise ValueError(f"{field} must be YYYYMMDD")
    try:datetime.strptime(v,"%Y%m%d")
    except ValueError as exc:raise ValueError(f"{field} must be valid YYYYMMDD") from exc
    return v

def _validate_bundle(bundle:Mapping[str,Any],p:dict[str,Any])->tuple[str,list[dict[str,Any]],dict[str,dict[str,Any]]]:
    if bundle.get("schema_version")!="0.1.0" or bundle.get("programme_id")!=p["programme_id"] or bundle.get("provider")!=p["provider_contract"]["provider"]:raise ValueError("Replay identity mismatch")
    scope=bundle.get("capture_scope")
    if scope not in {"FULL_PROGRAMME","PARTIAL_VALIDATION"}:raise ValueError("Invalid capture_scope")
    if not isinstance(bundle.get("captured_at"),str) or not bundle["captured_at"].strip():raise ValueError("captured_at required")
    captures=bundle.get("leaf_query_captures");configured=_active(p)
    if not isinstance(captures,list) or not captures:raise ValueError("leaf_query_captures required")
    seen:set[str]=set()
    for c in captures:
        if not isinstance(c,dict):raise ValueError("510(k) leaf must be object")
        qid=c.get("query_id");leaf=c.get("leaf_query_id")
        if qid not in configured or not isinstance(leaf,str) or not leaf or leaf in seen:raise ValueError("Invalid or duplicate 510(k) leaf")
        seen.add(leaf);root=configured[str(qid)]["search"];effective=c.get("effective_search");parts=c.get("partition_path")
        if not isinstance(effective,str) or not effective or not isinstance(parts,list):raise ValueError(f"{leaf}: invalid search/partition")
        if not parts:
            if effective!=root:raise ValueError(f"{leaf}: unpartitioned search must equal programme control")
        else:
            if len(parts)!=1 or not isinstance(parts[0],Mapping) or set(parts[0])!={"dimension","lower_bound","upper_bound"} or parts[0].get("dimension")!="DECISION_DATE":raise ValueError(f"{leaf}: exactly one DECISION_DATE partition is permitted")
            lo=_date8(parts[0].get("lower_bound"),f"{leaf}.lower_bound");hi=_date8(parts[0].get("upper_bound"),f"{leaf}.upper_bound")
            if lo>hi:raise ValueError(f"{leaf}: reversed decision-date partition")
            expected=f"({root})+AND+decision_date:[{lo}+TO+{hi}]"
            if effective!=expected:raise ValueError(f"{leaf}: partitioned search must exactly bind decision-date interval")
        pages=c.get("pages")
        if not isinstance(pages,list) or not pages or not all(isinstance(x,dict) for x in pages):raise ValueError(f"{leaf}: pages required")
    return str(scope),captures,configured

def _leaf_blockers(cov:Mapping[str,Any],p:Mapping[str,Any])->list[str]:
    blockers=[];missing=sorted(set(p["coverage_contract"]["required_metrics_per_leaf_query"])-set(cov))
    if missing:blockers.append("MISSING_METRICS:"+",".join(missing))
    for k,v in p["coverage_contract"]["mechanical_completion_requires"].items():
        if cov.get(k)!=v:blockers.append(f"GATE:{k}:{cov.get(k)!r}!={v!r}")
    if cov.get("decision_semantics_derived_only_from_exact_decision_code") is not True:blockers.append("DECISION_SEMANTICS_BOUNDARY_MISSING")
    if cov.get("record_presence_is_clearance_claim") is not False:blockers.append("RECORD_PRESENCE_CLEARANCE_BOUNDARY_VIOLATION")
    return blockers

def _expected_decision(code:Any,p:Mapping[str,Any])->tuple[str,bool,bool]:
    normalized=str(code or "").strip().upper();allow=set(p["decision_semantics_policy"]["recognized_substantial_equivalence_codes"])
    if normalized in allow:return p["decision_semantics_policy"]["recognized_state"],True,True
    return p["decision_semantics_policy"]["unknown_or_missing_code_state"],False,False

def _validate_normalized(row:Any,leaf:str,p:Mapping[str,Any])->dict[str,Any]:
    if not isinstance(row,dict):raise ValueError(f"{leaf}: normalized 510(k) record must be object")
    k=str(row.get("k_number") or "").upper()
    if not K_ID_RE.fullmatch(k) or DEN_ID_RE.fullmatch(k):raise ValueError(f"{leaf}: normalized 510(k) identity must be exact K/BK, got {k!r}")
    extra=set(row)-ALLOWED_NORMALIZED_FIELDS
    if extra:raise ValueError(f"{leaf}/{k}: normalized 510(k) contains prohibited/unexpected fields: {','.join(sorted(extra))}")
    expected=_expected_decision(row.get("decision_code"),p);actual=(row.get("decision_semantics"),row.get("decision_supports_substantial_equivalence"),row.get("decision_code_recognized"))
    if actual!=expected:raise ValueError(f"{leaf}/{k}: decision semantics do not match exact FDA decision code")
    digest=row.get("normalized_record_sha256")
    if not isinstance(digest,str) or len(digest)!=64:raise ValueError(f"{leaf}/{k}: normalized digest invalid")
    return row

def build_replay(bundle:Mapping[str,Any],*,projector:Projector|None=None,known_index:Mapping[str,Any]|None=None)->dict[str,Any]:
    p=_programme();scope,captures,configured=_validate_bundle(bundle,p);projector=projector or _load_projector();known=dict(known_index) if known_index is not None else build_known_k_source_index()
    if known.get("materialized_source_count")!=248:raise ValueError("Known Source index must bind 248 Sources")
    source_digest=known.get("source_id_set_sha256");known_map=known.get("k_to_source")
    if not isinstance(source_digest,str) or len(source_digest)!=64 or not isinstance(known_map,dict):raise ValueError("Known Source index incomplete")
    reports=[];union:dict[str,dict[str,Any]]={};blocker_count=0;raw_pages=0;den_total=0;unresolved_total=0
    represented={str(c["query_id"]) for c in captures};partitioned=sum(bool(c["partition_path"]) for c in captures)
    for c in sorted(captures,key=lambda x:str(x["leaf_query_id"])):
        leaf=str(c["leaf_query_id"]);raw_pages+=len(c["pages"])
        proj=projector(query_id=str(c["query_id"]),search=str(c["effective_search"]),pages=c["pages"],known_k_sources=known_map)
        cov=proj.get("coverage");records=proj.get("result_records");norms=proj.get("normalized_records")
        if not isinstance(cov,dict) or not isinstance(records,list) or not isinstance(norms,list):raise ValueError(f"{leaf}: invalid Workbench 510(k) projection")
        blockers=_leaf_blockers(cov,p);blocker_count+=len(blockers);den_total+=int(cov.get("out_of_scope_den_count") or 0);unresolved_total+=int(cov.get("unresolved_k_number_count") or 0)
        reports.append({"query_id":c["query_id"],"leaf_query_id":leaf,"partition_path":c["partition_path"],"effective_search":c["effective_search"],"capture_sha256":_digest(c),"coverage":cov,"mechanical_blockers":blockers})
        norm_by:dict[str,dict[str,Any]]={}
        for raw in norms:
            n=_validate_normalized(raw,leaf,p);k=n["k_number"].upper()
            if k in norm_by:raise ValueError(f"{leaf}: duplicate normalized k_number {k}")
            norm_by[k]=n
        for r in records:
            key=r.get("record_key") if isinstance(r,dict) else None
            k=key.removeprefix("OPENFDA_510K:").upper() if isinstance(key,str) and key.startswith("OPENFDA_510K:") else None
            if k is None or k not in norm_by:raise ValueError(f"{leaf}: 510(k) candidate lacks normalized record")
            n=norm_by[k];digest=n["normalized_record_sha256"]
            if r.get("decision_semantics")!=n.get("decision_semantics"):raise ValueError(f"{leaf}/{k}: candidate decision semantics conflict with normalized decision")
            candidate={x:r.get(x) for x in ("record_key","title","url","publisher","source_class","suggested_source_id","classification_hint","duplicate_of_source_id","decision_semantics")}
            prior=union.get(k)
            if prior is None:union[k]={"normalized":n,"digest":digest,"candidate":candidate,"queries":{str(c["query_id"])},"leaves":{leaf}}
            else:
                if prior["digest"]!=digest or prior["candidate"]!=candidate:raise ValueError(f"Cross-leaf conflict for k_number {k}")
                prior["queries"].add(str(c["query_id"]));prior["leaves"].add(leaf)
    normalized=[];known_dups=[];new=[]
    for k in sorted(union):
        row=union[k];n=dict(row["normalized"]);n["query_memberships"]=sorted(row["queries"]);n["leaf_memberships"]=sorted(row["leaves"]);normalized.append(n)
        cand={**row["candidate"],"query_memberships":sorted(row["queries"]),"leaf_memberships":sorted(row["leaves"]),"normalized_record_sha256":row["digest"]}
        if cand.get("classification_hint")=="DUPLICATE":known_dups.append(cand)
        elif cand.get("classification_hint")=="NEW":new.append(cand)
        else:raise ValueError(f"Unexpected 510(k) classification for {k}")
    all_queries=set(configured)==represented;complete=scope=="FULL_PROGRAMME" and all_queries and partitioned==0 and blocker_count==0
    reconciliation={"scope":scope,"materialized_source_namespace_count":248,"controlled_source_id_set_sha256":source_digest,"known_k_number_count_before_run":known.get("known_k_number_count"),"configured_active_query_count":len(configured),"represented_query_count":len(represented),"all_logical_queries_represented":all_queries,"partitioned_leaf_count":partitioned,"partition_reconciliation_required":partitioned>0,"leaf_mechanical_blocker_count":blocker_count,"union_unique_k_number_count":len(union),"out_of_scope_den_count":den_total,"unresolved_k_number_count":unresolved_total,"known_controlled_duplicate_count":len(known_dups),"new_candidate_input_count":len(new),"raw_input_page_count":raw_pages,"raw_openfda_pages_emitted":False,"mechanically_complete":complete,"recognized_substantial_equivalence_codes":p["decision_semantics_policy"]["recognized_substantial_equivalence_codes"],"record_presence_is_clearance_claim":False,"automatic_device_or_applicant_entity_creation":False,"automatic_predicate_relationship_creation":False,"automatic_global_authorization_claim_creation":False,"automatic_safety_effectiveness_claim_creation":False,"automatic_system_conformance_claim_creation":False,"automatic_reopening_decision":False,"automatic_assessment_mutation":False,"global_neuroai_510k_coverage_claim":False,"canonical_successor_ready":False}
    return {"schema_version":"0.1.0","status":"NONCANONICAL_SU_REGULATION_510K_RECORDED_REPLAY_PROJECTION","programme_id":p["programme_id"],"normalized_510k_records":normalized,"known_duplicates":known_dups,"new_candidate_inputs":new,"query_reports":reports,"known_source_index_summary":{"materialized_source_count":248,"source_id_set_sha256":source_digest,"regulatory_typed_source_count":known.get("regulatory_typed_source_count"),"known_k_number_count":known.get("known_k_number_count"),"global_510k_completeness_claim":False},"reconciliation":reconciliation,"input_provenance":{"bundle_sha256":_digest(bundle),"captured_at":bundle["captured_at"],"controlled_source_id_set_sha256":source_digest,"known_k_index_sha256":_digest(known_map),"raw_provider_pages_retained_in_output":False}}

def _write_jsonl(path:Path,rows:list[dict[str,Any]])->dict[str,Any]:
    payload=b"".join(_canon(r) for r in rows);path.write_bytes(payload);return {"path":path.name,"bytes":len(payload),"sha256":hashlib.sha256(payload).hexdigest(),"records":len(rows)}
def write_projection(result:Mapping[str,Any],out:Path)->dict[str,Any]:
    out.mkdir(parents=True,exist_ok=True);files=[]
    for key,name in (("normalized_510k_records","normalized-510k-records.jsonl"),("known_duplicates","known-510k-duplicates.jsonl"),("new_candidate_inputs","new-510k-candidate-inputs.jsonl")):files.append(_write_jsonl(out/name,list(result[key])))
    for key,name in (("query_reports","query-reports.json"),("reconciliation","reconciliation.json"),("known_source_index_summary","known-source-index-summary.json"),("input_provenance","input-provenance.json")):
        payload=_canon(result[key]);(out/name).write_bytes(payload);files.append({"path":name,"bytes":len(payload),"sha256":hashlib.sha256(payload).hexdigest(),"records":1})
    manifest={"programme_id":result["programme_id"],"status":result["status"],"files":sorted(files,key=lambda x:x["path"]),"file_count":len(files),"raw_openfda_pages_emitted":False,"den_records_emitted_as_510k_candidates":False,"record_presence_is_clearance_claim":False,"canonical_successor_ready":False};payload=_canon(manifest);(out/"manifest.json").write_bytes(payload);return {**manifest,"manifest_sha256":hashlib.sha256(payload).hexdigest()}
def main()->int:
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("--input-bundle",type=Path,required=True);ap.add_argument("--output-dir",type=Path,required=True);a=ap.parse_args();result=build_replay(_load(a.input_bundle));manifest=write_projection(result,a.output_dir);print(json.dumps({"reconciliation":result["reconciliation"],"manifest":manifest},indent=2,sort_keys=True));return 0 if result["reconciliation"]["mechanically_complete"] else 1
if __name__=="__main__":raise SystemExit(main())
