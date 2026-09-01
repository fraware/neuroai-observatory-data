#!/usr/bin/env python3
"""Deterministic recorded replay for bounded NIH RePORTER grant discovery.

Raw provider pages are ephemeral input. Outputs are noncanonical discovery projections only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any, Callable

try:
    from scripts.current_source_namespace import materialize_effective_source_namespace
except ModuleNotFoundError:
    from current_source_namespace import materialize_effective_source_namespace

ROOT=Path(__file__).parents[1]
PROGRAMME=ROOT/"curation"/"nih_reporter_grants_discovery_programme_v0.1.json"
REPORTER_APPL_RE=re.compile(r"^https?://reporter\.nih\.gov/project-details/(\d+)/?(?:[?#].*)?$",re.I)
Projector=Callable[...,dict[str,Any]]


def _canon(value:Any)->bytes:
    return (json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode("utf-8")
def _digest(value:Any)->str:return hashlib.sha256(_canon(value)).hexdigest()
def _load(path:Path)->Any:return json.loads(path.read_text(encoding="utf-8"))


def _programme()->dict[str,Any]:
    p=_load(PROGRAMME)
    if p.get("programme_id")!="SU-GRANTS-NIH-REPORTER-v0.1":raise ValueError("Invalid NIH RePORTER programme")
    d=p.get("workbench_dependency") or {}
    if d.get("required_capability")!="project_nih_reporter_search_pages" or d.get("integration_state")!="AVAILABLE":raise ValueError("NIH RePORTER programme requires AVAILABLE Workbench capability")
    return p


def _load_projector()->Projector:
    try:from neuroai_workbench.discovery import project_nih_reporter_search_pages
    except (ImportError,AttributeError) as exc:raise RuntimeError("Required Workbench NIH RePORTER projector unavailable") from exc
    return project_nih_reporter_search_pages


def _eligible_grant_source(source:Mapping[str,Any])->bool:
    token=str(source.get("source_class") or "").upper()
    return any(part in token for part in ("GRANT","FUNDER","FUNDING","AWARD"))


def _appl_from_locator(locator:str)->int|None:
    match=REPORTER_APPL_RE.fullmatch(locator.strip())
    if not match:return None
    value=int(match.group(1));return value if value>0 else None


def build_known_appl_source_index()->dict[str,Any]:
    ns=materialize_effective_source_namespace();sources=ns.get("sources")
    if not isinstance(sources,list) or ns.get("materialized_source_count")!=248 or len(sources)!=248:raise ValueError("Expected exact 248-Source controlled namespace")
    source_digest=ns.get("source_id_set_sha256")
    if not isinstance(source_digest,str) or len(source_digest)!=64:raise ValueError("Controlled Source namespace digest unavailable")
    eligible:set[str]=set();mapping:dict[int,str]={};lineage:dict[int,dict[str,str]]={}
    for source in sources:
        if not isinstance(source,Mapping):raise ValueError("Controlled Source row must be object")
        sid=source.get("source_id")
        if not isinstance(sid,str) or not sid:raise ValueError("Controlled Source row missing source_id")
        if not _eligible_grant_source(source):continue
        eligible.add(sid);locator=source.get("canonical_locator")
        if not isinstance(locator,str):continue
        appl=_appl_from_locator(locator)
        if appl is None:continue
        prior=mapping.get(appl)
        if prior is not None and prior!=sid:raise ValueError(f"Controlled grant namespace maps appl_id {appl} to conflicting Sources")
        mapping[appl]=sid;lineage[appl]={"source_id":sid,"lineage_family":str(source.get("lineage_family") or "")}
    return {"materialized_source_count":248,"source_id_set_sha256":source_digest,"grant_typed_source_count":len(eligible),"known_reporter_appl_id_count":len(mapping),"appl_to_source":{str(k):mapping[k] for k in sorted(mapping)},"appl_lineage":{str(k):lineage[k] for k in sorted(lineage)},"global_grant_completeness_claim":False}


def _active(p:Mapping[str,Any])->dict[str,dict[str,Any]]:
    return {str(row["query_id"]):dict(row) for row in p["query_streams"] if row.get("status")=="ACTIVE"}


def _iso_date(value:Any,field:str)->str:
    if not isinstance(value,str):raise ValueError(f"{field} must be ISO date")
    try:parsed=date.fromisoformat(value)
    except ValueError as exc:raise ValueError(f"{field} must be ISO date") from exc
    return parsed.isoformat()


def _expected_criteria(config:Mapping[str,Any],partition_path:Any,leaf_id:str)->dict[str,Any]:
    if not isinstance(partition_path,list):raise ValueError(f"{leaf_id}: partition_path must be array")
    criteria={"advanced_text_search":config["advanced_text_search"]};seen:set[str]=set()
    for i,part in enumerate(partition_path):
        if not isinstance(part,Mapping):raise ValueError(f"{leaf_id}: partition_path[{i}] must be object")
        dim=part.get("dimension")
        if dim in seen:raise ValueError(f"{leaf_id}: duplicate partition dimension {dim}")
        seen.add(str(dim))
        if dim=="FISCAL_YEAR":
            if set(part)!={"dimension","fiscal_year"}:raise ValueError(f"{leaf_id}: FISCAL_YEAR partition fields changed")
            year=part.get("fiscal_year")
            if not isinstance(year,int) or isinstance(year,bool) or not 1900<=year<=2100:raise ValueError(f"{leaf_id}: invalid fiscal_year")
            criteria["fiscal_years"]=[year]
        elif dim=="AWARD_NOTICE_DATE":
            if set(part)!={"dimension","from_date","to_date"}:raise ValueError(f"{leaf_id}: AWARD_NOTICE_DATE partition fields changed")
            lower=_iso_date(part.get("from_date"),f"{leaf_id}.from_date");upper=_iso_date(part.get("to_date"),f"{leaf_id}.to_date")
            if lower>upper:raise ValueError(f"{leaf_id}: award notice date interval reversed")
            criteria["award_notice_date"]={"from_date":lower,"to_date":upper}
        else:raise ValueError(f"{leaf_id}: unsupported partition dimension")
    return criteria


def _validate_bundle(bundle:Mapping[str,Any],p:dict[str,Any])->tuple[str,list[dict[str,Any]],dict[str,dict[str,Any]]]:
    if bundle.get("schema_version")!="0.1.0" or bundle.get("programme_id")!=p["programme_id"] or bundle.get("provider")!=p["provider_contract"]["provider"]:raise ValueError("Replay identity mismatch")
    scope=bundle.get("capture_scope")
    if scope not in {"FULL_PROGRAMME","PARTIAL_VALIDATION"}:raise ValueError("Invalid capture_scope")
    if not isinstance(bundle.get("captured_at"),str) or not bundle["captured_at"].strip():raise ValueError("captured_at required")
    captures=bundle.get("leaf_query_captures");configured=_active(p)
    if not isinstance(captures,list) or not captures:raise ValueError("leaf_query_captures required")
    seen:set[str]=set()
    for capture in captures:
        if not isinstance(capture,dict):raise ValueError("leaf capture must be object")
        qid=capture.get("query_id");leaf=capture.get("leaf_query_id")
        if qid not in configured:raise ValueError(f"Unconfigured RePORTER query {qid!r}")
        if not isinstance(leaf,str) or not leaf or leaf in seen:raise ValueError("Invalid or duplicate leaf_query_id")
        seen.add(leaf);expected_criteria=_expected_criteria(configured[str(qid)],capture.get("partition_path"),leaf)
        payload=capture.get("query_payload")
        expected_payload={"criteria":expected_criteria,"offset":0,"limit":p["pagination_partition_policy"]["page_limit"]}
        if payload!=expected_payload:raise ValueError(f"{leaf}: query_payload must exactly match governed root and partition criteria")
        pages=capture.get("pages")
        if not isinstance(pages,list) or not pages or not all(isinstance(page,dict) for page in pages):raise ValueError(f"{leaf}: pages required")
    return str(scope),captures,configured


def _logical(captures:list[dict[str,Any]],configured:Mapping[str,Any])->dict[str,Any]:
    represented={str(row["query_id"]) for row in captures};missing=sorted(set(configured)-represented);partitioned=[row for row in captures if row.get("partition_path")]
    return {"configured_active_query_count":len(configured),"represented_query_count":len(represented),"missing_query_ids":missing,"partitioned_leaf_count":len(partitioned),"partition_reconciliation_required":bool(partitioned),"all_logical_queries_represented":not missing}


def _blockers(coverage:Mapping[str,Any],p:Mapping[str,Any])->list[str]:
    out:list[str]=[];missing=sorted(set(p["coverage_contract"]["required_metrics_per_leaf_query"])-set(coverage))
    if missing:out.append("MISSING_COVERAGE_METRICS:"+",".join(missing))
    for key,expected in p["coverage_contract"]["mechanical_completion_requires"].items():
        if coverage.get(key)!=expected:out.append(f"COVERAGE_GATE:{key}:{coverage.get(key)!r}!={expected!r}")
    if coverage.get("candidate_emission_refused_due_to_over_limit") is True:out.append("OVER_LIMIT_CANDIDATE_EMISSION_REFUSED")
    return out


def build_replay(bundle:Mapping[str,Any],*,projector:Projector|None=None,known_index:Mapping[str,Any]|None=None)->dict[str,Any]:
    p=_programme();scope,captures,configured=_validate_bundle(bundle,p);projector=projector or _load_projector();known=dict(known_index) if known_index is not None else build_known_appl_source_index()
    if known.get("materialized_source_count")!=248:raise ValueError("Known Source index must bind 248 Sources")
    source_digest=known.get("source_id_set_sha256")
    if not isinstance(source_digest,str) or len(source_digest)!=64:raise ValueError("Known Source index digest missing")
    known_map=known.get("appl_to_source")
    if not isinstance(known_map,dict):raise ValueError("Known appl_id index missing")
    logical=_logical(captures,configured);reports:list[dict[str,Any]]=[];union:dict[int,dict[str,Any]]={};blocker_count=0;raw_pages=0
    for capture in sorted(captures,key=lambda row:str(row["leaf_query_id"])):
        qid=str(capture["query_id"]);leaf=str(capture["leaf_query_id"]);pages=capture["pages"];raw_pages+=len(pages)
        projection=projector(query_id=qid,query_payload=capture["query_payload"],pages=pages,known_appl_sources=known_map)
        coverage=projection.get("coverage");records=projection.get("result_records");normalized=projection.get("normalized_records")
        if not isinstance(coverage,dict) or not isinstance(records,list) or not isinstance(normalized,list):raise ValueError(f"{leaf}: invalid Workbench projection")
        blockers=_blockers(coverage,p);blocker_count+=len(blockers);reports.append({"query_id":qid,"leaf_query_id":leaf,"partition_path":capture.get("partition_path"),"query_payload_sha256":_digest(capture["query_payload"]),"capture_sha256":_digest(capture),"coverage":coverage,"mechanical_blockers":blockers})
        by_appl:dict[int,dict[str,Any]]={}
        for row in normalized:
            if not isinstance(row,dict) or not isinstance(row.get("appl_id"),int) or isinstance(row.get("appl_id"),bool) or row["appl_id"]<=0:raise ValueError(f"{leaf}: invalid normalized appl_id")
            appl=row["appl_id"]
            if appl in by_appl:raise ValueError(f"{leaf}: duplicate normalized appl_id")
            digest=row.get("normalized_record_sha256")
            if not isinstance(digest,str) or len(digest)!=64:raise ValueError(f"{leaf}/{appl}: invalid normalized digest")
            by_appl[appl]=row
        for record in records:
            if not isinstance(record,dict):raise ValueError(f"{leaf}: candidate must be object")
            key=record.get("record_key")
            if not isinstance(key,str) or not key.startswith("REPORTER:APPL:"):raise ValueError(f"{leaf}: invalid candidate key")
            try:appl=int(key.rsplit(":",1)[1])
            except ValueError as exc:raise ValueError(f"{leaf}: invalid candidate appl_id") from exc
            norm=by_appl.get(appl)
            if norm is None:raise ValueError(f"{leaf}: candidate lacks normalized record")
            candidate={k:record.get(k) for k in ("record_key","title","url","publisher","source_class","suggested_source_id","classification_hint","duplicate_of_source_id")};digest=norm["normalized_record_sha256"]
            prior=union.get(appl)
            if prior is None:union[appl]={"normalized":norm,"digest":digest,"candidate":candidate,"queries":{qid},"leaves":{leaf}}
            else:
                if prior["digest"]!=digest or prior["candidate"]!=candidate:raise ValueError(f"Cross-leaf conflict for RePORTER appl_id {appl}")
                prior["queries"].add(qid);prior["leaves"].add(leaf)
    normalized_out=[];duplicates=[];new=[]
    for appl in sorted(union):
        entry=union[appl];norm=dict(entry["normalized"]);norm["query_memberships"]=sorted(entry["queries"]);norm["leaf_memberships"]=sorted(entry["leaves"]);normalized_out.append(norm)
        cand={**entry["candidate"],"query_memberships":sorted(entry["queries"]),"leaf_memberships":sorted(entry["leaves"]),"normalized_record_sha256":entry["digest"]}
        if cand.get("classification_hint")=="DUPLICATE":duplicates.append(cand)
        elif cand.get("classification_hint")=="NEW":new.append(cand)
        else:raise ValueError(f"Unexpected candidate classification for appl_id {appl}")
    mechanically_complete=scope=="FULL_PROGRAMME" and logical["all_logical_queries_represented"] and blocker_count==0 and not logical["partition_reconciliation_required"]
    reconciliation={"scope":scope,**logical,"executed_leaf_query_count":len(captures),"leaf_mechanical_blocker_count":blocker_count,"union_unique_appl_id_count":len(union),"known_controlled_duplicate_count":len(duplicates),"new_candidate_input_count":len(new),"materialized_source_namespace_count":248,"controlled_source_id_set_sha256":source_digest,"grant_typed_source_count_before_run":known.get("grant_typed_source_count"),"known_reporter_appl_id_count_before_run":known.get("known_reporter_appl_id_count"),"raw_input_page_count":raw_pages,"raw_reporter_pages_emitted":False,"automatic_source_admission":False,"automatic_project_entity_creation":False,"automatic_pi_or_organization_entity_creation":False,"automatic_system_or_model_relationship_creation":False,"automatic_funding_success_claim_creation":False,"automatic_monitor_creation":False,"automatic_assessment_mutation":False,"human_adjudication_performed":False,"mechanically_complete":mechanically_complete,"reporter_database_completeness_claim":False,"global_neuroai_grant_recall_claim":False,"query_recall_claim":False,"funding_success_claim":False,"canonical_successor_ready":False,"authority_boundary":"Mechanical replay establishes deterministic processing of exact supplied RePORTER traversals only. Partitioned traversals require a separate parent/child proof before baseline completion. Award existence or amount does not establish research success, scientific validity, effectiveness, entity identity, commercialization, implementation, regulatory status, assessment effect, global grant recall, or canonical authority."}
    return {"schema_version":"0.1.0","status":"NONCANONICAL_SU_GRANTS_NIH_REPORTER_RECORDED_REPLAY_PROJECTION","programme_id":p["programme_id"],"input_provenance":{"bundle_sha256":_digest(bundle),"captured_at":bundle["captured_at"],"capture_scope":scope,"raw_provider_pages_retained_in_output":False,"controlled_source_id_set_sha256":source_digest,"known_appl_index_sha256":_digest(known_map)},"known_source_index_summary":{"materialized_source_count":248,"source_id_set_sha256":source_digest,"grant_typed_source_count":known.get("grant_typed_source_count"),"known_reporter_appl_id_count":known.get("known_reporter_appl_id_count"),"global_grant_completeness_claim":False},"query_reports":reports,"normalized_grants":normalized_out,"known_duplicates":duplicates,"new_candidate_inputs":new,"reconciliation":reconciliation}


def _write_jsonl(path:Path,rows:list[dict[str,Any]])->dict[str,Any]:
    payload=b"".join(_canon(row) for row in rows);path.write_bytes(payload);return {"path":path.name,"bytes":len(payload),"sha256":hashlib.sha256(payload).hexdigest(),"records":len(rows)}

def write_projection(result:Mapping[str,Any],output:Path)->dict[str,Any]:
    output.mkdir(parents=True,exist_ok=True);files=[]
    for key,name in (("normalized_grants","normalized-grants.jsonl"),("known_duplicates","known-grant-duplicates.jsonl"),("new_candidate_inputs","new-grant-candidate-inputs.jsonl")):files.append(_write_jsonl(output/name,list(result[key])))
    for key,name in (("input_provenance","input-provenance.json"),("known_source_index_summary","known-source-index-summary.json"),("query_reports","query-reports.json"),("reconciliation","reconciliation.json")):
        payload=_canon(result[key]);(output/name).write_bytes(payload);files.append({"path":name,"bytes":len(payload),"sha256":hashlib.sha256(payload).hexdigest(),"records":1})
    manifest={"programme_id":result["programme_id"],"status":result["status"],"files":sorted(files,key=lambda row:row["path"]),"file_count":len(files),"raw_reporter_pages_emitted":False,"canonical_successor_ready":False};payload=_canon(manifest);(output/"manifest.json").write_bytes(payload);return {**manifest,"manifest_sha256":hashlib.sha256(payload).hexdigest()}

def main()->int:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--input-bundle",type=Path,required=True);parser.add_argument("--output-dir",type=Path,required=True);args=parser.parse_args();result=build_replay(_load(args.input_bundle.resolve()));manifest=write_projection(result,args.output_dir.resolve());print(json.dumps({"reconciliation":result["reconciliation"],"manifest":manifest},indent=2,sort_keys=True));return 0 if result["reconciliation"]["mechanically_complete"] else 1
if __name__=="__main__":raise SystemExit(main())
