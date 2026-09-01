#!/usr/bin/env python3
"""Deterministic recorded replay for bounded openFDA device-recall discovery."""
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
PROGRAMME=ROOT/"curation"/"openfda_device_recall_discovery_programme_v0.1.json"
CFRES_RE=re.compile(r'cfres_id\s*(?:=|:)\s*"?([A-Za-z0-9._-]+)"?',re.I)
Projector=Callable[...,dict[str,Any]]
ALLOWED_NORMALIZED_FIELDS={
    "record_kind","cfres_id","res_event_number","product_res_number","event_date_initiated",
    "event_date_created","event_date_posted","event_date_terminated","recall_status","recalling_firm",
    "firm_fei_number","reason_for_recall","root_cause_description","action","product_description",
    "product_code","k_numbers","pma_numbers","query_memberships","boundary","normalized_record_sha256",
}

def _canon(v:Any)->bytes:return (json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode("utf-8")
def _digest(v:Any)->str:return hashlib.sha256(_canon(v)).hexdigest()
def _load(p:Path)->Any:return json.loads(p.read_text(encoding="utf-8"))

def _programme()->dict[str,Any]:
    p=_load(PROGRAMME);dep=p.get("workbench_dependency") or {}
    if p.get("programme_id")!="SU-REGULATION-OPENFDA-DEVICE-RECALLS-v0.1":raise ValueError("Invalid recall programme")
    if dep.get("required_capability")!="project_openfda_device_recall_pages" or dep.get("integration_state")!="AVAILABLE":raise ValueError("Current merged recall capability unavailable")
    return p

def _load_projector()->Projector:
    try:from neuroai_workbench.discovery import project_openfda_device_recall_pages
    except (ImportError,AttributeError) as exc:raise RuntimeError("Required Workbench recall projector unavailable") from exc
    return project_openfda_device_recall_pages

def _eligible(source:Mapping[str,Any])->bool:
    token=str(source.get("source_class") or "").upper();return any(x in token for x in ("RECALL","POSTMARKET","ENFORCEMENT"))

def _cfres_from_locator(locator:str)->set[str]:
    text=unquote_plus(locator);return {m.group(1) for m in CFRES_RE.finditer(text)}

def build_known_cfres_source_index()->dict[str,Any]:
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
        for rid in sorted(_cfres_from_locator(locator)):
            prior=index.get(rid)
            if prior is not None and prior!=sid:raise ValueError(f"Conflicting controlled Sources for cfres_id {rid}")
            index[rid]=sid;lineage[rid]={"source_id":sid,"lineage_family":str(source.get("lineage_family") or "")}
    return {"materialized_source_count":248,"source_id_set_sha256":source_digest,"recall_typed_source_count":len(eligible),"known_cfres_id_count":len(index),"cfres_to_source":dict(sorted(index.items())),"cfres_lineage":{k:lineage[k] for k in sorted(lineage)},"global_recall_completeness_claim":False}

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
        if not isinstance(c,dict):raise ValueError("Recall leaf must be object")
        qid=c.get("query_id");leaf=c.get("leaf_query_id")
        if qid not in configured or not isinstance(leaf,str) or not leaf or leaf in seen:raise ValueError("Invalid or duplicate recall leaf")
        seen.add(leaf);root=configured[str(qid)]["search"];effective=c.get("effective_search");parts=c.get("partition_path")
        if not isinstance(effective,str) or not effective or not isinstance(parts,list):raise ValueError(f"{leaf}: invalid search/partition")
        if not parts:
            if effective!=root:raise ValueError(f"{leaf}: unpartitioned search must equal programme control")
        else:
            if len(parts)!=1 or not isinstance(parts[0],Mapping) or set(parts[0])!={"dimension","lower_bound","upper_bound"} or parts[0].get("dimension")!="EVENT_DATE_POSTED":raise ValueError(f"{leaf}: exactly one EVENT_DATE_POSTED partition is permitted")
            lo=_date8(parts[0].get("lower_bound"),f"{leaf}.lower_bound");hi=_date8(parts[0].get("upper_bound"),f"{leaf}.upper_bound")
            if lo>hi:raise ValueError(f"{leaf}: reversed date partition")
            expected=f"({root})+AND+event_date_posted:[{lo}+TO+{hi}]"
            if effective!=expected:raise ValueError(f"{leaf}: partitioned search must exactly bind date interval")
        pages=c.get("pages")
        if not isinstance(pages,list) or not pages or not all(isinstance(x,dict) for x in pages):raise ValueError(f"{leaf}: pages required")
    return str(scope),captures,configured

def _leaf_blockers(cov:Mapping[str,Any],p:Mapping[str,Any])->list[str]:
    blockers=[];missing=sorted(set(p["coverage_contract"]["required_metrics_per_leaf_query"])-set(cov))
    if missing:blockers.append("MISSING_METRICS:"+",".join(missing))
    for k,v in p["coverage_contract"]["mechanical_completion_requires"].items():
        if cov.get(k)!=v:blockers.append(f"GATE:{k}:{cov.get(k)!r}!={v!r}")
    if cov.get("address_or_contact_fields_projected") is not False:blockers.append("ADDRESS_OR_CONTACT_MINIMIZATION_VIOLATION")
    if cov.get("code_info_lot_serial_text_projected") is not False:blockers.append("CODE_INFO_MINIMIZATION_VIOLATION")
    if cov.get("distribution_pattern_projected") is not False:blockers.append("DISTRIBUTION_PATTERN_MINIMIZATION_VIOLATION")
    return blockers

def _validate_normalized(row:Any,leaf:str)->dict[str,Any]:
    if not isinstance(row,dict) or not isinstance(row.get("cfres_id"),str) or not row["cfres_id"]:raise ValueError(f"{leaf}: normalized recall identity missing")
    extra=set(row)-ALLOWED_NORMALIZED_FIELDS
    if extra:raise ValueError(f"{leaf}/{row['cfres_id']}: normalized recall contains prohibited/unexpected fields: {','.join(sorted(extra))}")
    digest=row.get("normalized_record_sha256")
    if not isinstance(digest,str) or len(digest)!=64:raise ValueError(f"{leaf}/{row['cfres_id']}: normalized digest invalid")
    return row

def build_replay(bundle:Mapping[str,Any],*,projector:Projector|None=None,known_index:Mapping[str,Any]|None=None)->dict[str,Any]:
    p=_programme();scope,captures,configured=_validate_bundle(bundle,p);projector=projector or _load_projector();known=dict(known_index) if known_index is not None else build_known_cfres_source_index()
    if known.get("materialized_source_count")!=248:raise ValueError("Known Source index must bind 248 Sources")
    source_digest=known.get("source_id_set_sha256");known_map=known.get("cfres_to_source")
    if not isinstance(source_digest,str) or len(source_digest)!=64 or not isinstance(known_map,dict):raise ValueError("Known Source index incomplete")
    reports=[];union:dict[str,dict[str,Any]]={};blocker_count=0;raw_pages=0
    represented={str(c["query_id"]) for c in captures};partitioned=sum(bool(c["partition_path"]) for c in captures)
    for c in sorted(captures,key=lambda x:str(x["leaf_query_id"])):
        leaf=str(c["leaf_query_id"]);raw_pages+=len(c["pages"])
        proj=projector(query_id=str(c["query_id"]),search=str(c["effective_search"]),pages=c["pages"],known_cfres_sources=known_map)
        cov=proj.get("coverage");records=proj.get("result_records");norms=proj.get("normalized_records")
        if not isinstance(cov,dict) or not isinstance(records,list) or not isinstance(norms,list):raise ValueError(f"{leaf}: invalid Workbench recall projection")
        blockers=_leaf_blockers(cov,p);blocker_count+=len(blockers);reports.append({"query_id":c["query_id"],"leaf_query_id":leaf,"partition_path":c["partition_path"],"effective_search":c["effective_search"],"capture_sha256":_digest(c),"coverage":cov,"mechanical_blockers":blockers})
        norm_by:dict[str,dict[str,Any]]={}
        for raw in norms:
            n=_validate_normalized(raw,leaf);rid=n["cfres_id"]
            if rid in norm_by:raise ValueError(f"{leaf}: duplicate normalized cfres_id {rid}")
            norm_by[rid]=n
        for r in records:
            key=r.get("record_key") if isinstance(r,dict) else None
            rid=key.removeprefix("OPENFDA_RECALL:") if isinstance(key,str) and key.startswith("OPENFDA_RECALL:") else None
            if rid is None or rid not in norm_by:raise ValueError(f"{leaf}: recall candidate lacks normalized record")
            n=norm_by[rid];digest=n["normalized_record_sha256"]
            candidate={k:r.get(k) for k in ("record_key","title","url","publisher","source_class","suggested_source_id","classification_hint","duplicate_of_source_id")}
            prior=union.get(rid)
            if prior is None:union[rid]={"normalized":n,"digest":digest,"candidate":candidate,"queries":{str(c["query_id"])},"leaves":{leaf}}
            else:
                if prior["digest"]!=digest or prior["candidate"]!=candidate:raise ValueError(f"Cross-leaf conflict for cfres_id {rid}")
                prior["queries"].add(str(c["query_id"]));prior["leaves"].add(leaf)
    normalized=[];known_dups=[];new=[]
    for rid in sorted(union):
        row=union[rid];n=dict(row["normalized"]);n["query_memberships"]=sorted(row["queries"]);n["leaf_memberships"]=sorted(row["leaves"]);normalized.append(n)
        cand={**row["candidate"],"query_memberships":sorted(row["queries"]),"leaf_memberships":sorted(row["leaves"]),"normalized_record_sha256":row["digest"]}
        if cand.get("classification_hint")=="DUPLICATE":known_dups.append(cand)
        elif cand.get("classification_hint")=="NEW":new.append(cand)
        else:raise ValueError(f"Unexpected recall classification for {rid}")
    all_queries=set(configured)==represented;complete=scope=="FULL_PROGRAMME" and all_queries and partitioned==0 and blocker_count==0
    reconciliation={"scope":scope,"materialized_source_namespace_count":248,"controlled_source_id_set_sha256":source_digest,"known_cfres_id_count_before_run":known.get("known_cfres_id_count"),"configured_active_query_count":len(configured),"represented_query_count":len(represented),"all_logical_queries_represented":all_queries,"partitioned_leaf_count":partitioned,"partition_reconciliation_required":partitioned>0,"leaf_mechanical_blocker_count":blocker_count,"union_unique_cfres_id_count":len(union),"known_controlled_duplicate_count":len(known_dups),"new_candidate_input_count":len(new),"raw_input_page_count":raw_pages,"raw_openfda_pages_emitted":False,"address_or_contact_fields_emitted":False,"code_info_lot_serial_text_emitted":False,"distribution_pattern_emitted":False,"mechanically_complete":complete,"automatic_recall_event_entity_creation":False,"automatic_system_or_firm_entity_creation":False,"automatic_submission_relationship_creation":False,"automatic_system_nonconformance_claim_creation":False,"automatic_reopening_decision":False,"automatic_assessment_mutation":False,"recall_status_is_complete_lifecycle_tracker":False,"global_neuroai_device_recall_claim":False,"canonical_successor_ready":False}
    return {"schema_version":"0.1.0","status":"NONCANONICAL_SU_REGULATION_DEVICE_RECALL_RECORDED_REPLAY_PROJECTION","programme_id":p["programme_id"],"normalized_recall_records":normalized,"known_duplicates":known_dups,"new_candidate_inputs":new,"query_reports":reports,"known_source_index_summary":{"materialized_source_count":248,"source_id_set_sha256":source_digest,"recall_typed_source_count":known.get("recall_typed_source_count"),"known_cfres_id_count":known.get("known_cfres_id_count"),"global_recall_completeness_claim":False},"reconciliation":reconciliation,"input_provenance":{"bundle_sha256":_digest(bundle),"captured_at":bundle["captured_at"],"controlled_source_id_set_sha256":source_digest,"known_cfres_index_sha256":_digest(known_map),"raw_provider_pages_retained_in_output":False}}

def _write_jsonl(path:Path,rows:list[dict[str,Any]])->dict[str,Any]:
    payload=b"".join(_canon(r) for r in rows);path.write_bytes(payload);return {"path":path.name,"bytes":len(payload),"sha256":hashlib.sha256(payload).hexdigest(),"records":len(rows)}
def write_projection(result:Mapping[str,Any],out:Path)->dict[str,Any]:
    out.mkdir(parents=True,exist_ok=True);files=[]
    for key,name in (("normalized_recall_records","normalized-recalls.jsonl"),("known_duplicates","known-recall-duplicates.jsonl"),("new_candidate_inputs","new-recall-candidate-inputs.jsonl")):files.append(_write_jsonl(out/name,list(result[key])))
    for key,name in (("query_reports","query-reports.json"),("reconciliation","reconciliation.json"),("known_source_index_summary","known-source-index-summary.json"),("input_provenance","input-provenance.json")):
        payload=_canon(result[key]);(out/name).write_bytes(payload);files.append({"path":name,"bytes":len(payload),"sha256":hashlib.sha256(payload).hexdigest(),"records":1})
    manifest={"programme_id":result["programme_id"],"status":result["status"],"files":sorted(files,key=lambda x:x["path"]),"file_count":len(files),"raw_openfda_pages_emitted":False,"address_or_contact_fields_emitted":False,"code_info_lot_serial_text_emitted":False,"distribution_pattern_emitted":False,"canonical_successor_ready":False};payload=_canon(manifest);(out/"manifest.json").write_bytes(payload);return {**manifest,"manifest_sha256":hashlib.sha256(payload).hexdigest()}
def main()->int:
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("--input-bundle",type=Path,required=True);ap.add_argument("--output-dir",type=Path,required=True);args=ap.parse_args();result=build_replay(_load(args.input_bundle));manifest=write_projection(result,args.output_dir);print(json.dumps({"reconciliation":result["reconciliation"],"manifest":manifest},indent=2,sort_keys=True));return 0 if result["reconciliation"]["mechanically_complete"] else 1
if __name__=="__main__":raise SystemExit(main())
