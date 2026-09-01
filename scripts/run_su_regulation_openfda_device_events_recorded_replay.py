#!/usr/bin/env python3
"""Deterministic recorded replay for bounded openFDA/MAUDE device-event discovery."""
from __future__ import annotations
import argparse,hashlib,json,re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any,Callable
from urllib.parse import unquote_plus
try:
    from scripts.current_source_namespace import materialize_effective_source_namespace
except ModuleNotFoundError:
    from current_source_namespace import materialize_effective_source_namespace
ROOT=Path(__file__).parents[1];PROGRAMME=ROOT/"curation"/"openfda_device_event_discovery_programme_v0.1.json";MDR_LOCATOR_RE=re.compile(r'mdr_report_key:\s*"?([^"&\s]+)"?',re.I);Projector=Callable[...,dict[str,Any]]
def _canon(v:Any)->bytes:return (json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode("utf-8")
def _digest(v:Any)->str:return hashlib.sha256(_canon(v)).hexdigest()
def _load(p:Path)->Any:return json.loads(p.read_text(encoding="utf-8"))
def _programme()->dict[str,Any]:
    p=_load(PROGRAMME);d=p.get("workbench_dependency") or {}
    if p.get("programme_id")!="SU-REGULATION-OPENFDA-DEVICE-EVENTS-v0.1" or d.get("required_capability")!="project_openfda_device_event_pages" or d.get("integration_state")!="AVAILABLE":raise ValueError("Invalid/current MAUDE programme dependency")
    return p
def _load_projector()->Projector:
    try:from neuroai_workbench.discovery import project_openfda_device_event_pages
    except (ImportError,AttributeError) as exc:raise RuntimeError("Required Workbench MAUDE projector unavailable") from exc
    return project_openfda_device_event_pages
def _eligible(s:Mapping[str,Any])->bool:
    token=str(s.get("source_class") or "").upper();return any(x in token for x in ("MAUDE","ADVERSE_EVENT","POSTMARKET"))
def _mdr_from_locator(locator:str)->str|None:
    m=MDR_LOCATOR_RE.search(unquote_plus(locator));return m.group(1).strip() if m and m.group(1).strip() else None
def build_known_mdr_source_index()->dict[str,Any]:
    ns=materialize_effective_source_namespace();sources=ns.get("sources");digest=ns.get("source_id_set_sha256")
    if not isinstance(sources,list) or ns.get("materialized_source_count")!=248 or len(sources)!=248:raise ValueError("Expected exact 248-Source controlled namespace")
    if not isinstance(digest,str) or len(digest)!=64:raise ValueError("Controlled Source digest unavailable")
    eligible:set[str]=set();mapping:dict[str,str]={};lineage:dict[str,dict[str,str]]={}
    for s in sources:
        if not isinstance(s,Mapping):raise ValueError("Controlled Source row must be object")
        sid=s.get("source_id")
        if not isinstance(sid,str) or not sid:raise ValueError("Controlled Source missing source_id")
        if not _eligible(s):continue
        eligible.add(sid);loc=s.get("canonical_locator")
        if not isinstance(loc,str):continue
        key=_mdr_from_locator(loc)
        if key is None:continue
        prior=mapping.get(key)
        if prior is not None and prior!=sid:raise ValueError(f"Conflicting controlled Sources for MDR key {key}")
        mapping[key]=sid;lineage[key]={"source_id":sid,"lineage_family":str(s.get("lineage_family") or "")}
    return {"materialized_source_count":248,"source_id_set_sha256":digest,"postmarket_typed_source_count":len(eligible),"known_mdr_report_key_count":len(mapping),"mdr_to_source":dict(sorted(mapping.items())),"mdr_lineage":{k:lineage[k] for k in sorted(lineage)},"global_postmarket_completeness_claim":False}
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
        if not isinstance(c,dict):raise ValueError("leaf capture must be object")
        qid=c.get("query_id");leaf=c.get("leaf_query_id")
        if qid not in configured:raise ValueError(f"Unconfigured MAUDE query {qid!r}")
        if not isinstance(leaf,str) or not leaf or leaf in seen:raise ValueError("Invalid or duplicate leaf_query_id")
        seen.add(leaf);root=configured[str(qid)]["search"];effective=c.get("effective_search");parts=c.get("partition_path")
        if not isinstance(effective,str) or not effective:raise ValueError(f"{leaf}: effective_search required")
        if not isinstance(parts,list):raise ValueError(f"{leaf}: partition_path must be array")
        if not parts:
            if effective!=root:raise ValueError(f"{leaf}: unpartitioned effective_search must exactly match programme control")
        else:
            if len(parts)!=1 or not isinstance(parts[0],Mapping) or set(parts[0])!={"dimension","lower_bound","upper_bound"} or parts[0].get("dimension")!="DATE_RECEIVED":raise ValueError(f"{leaf}: exactly one DATE_RECEIVED partition interval is permitted")
            lower=_date8(parts[0].get("lower_bound"),f"{leaf}.lower_bound");upper=_date8(parts[0].get("upper_bound"),f"{leaf}.upper_bound")
            if lower>upper:raise ValueError(f"{leaf}: reversed date partition")
            expected=f"({root})+AND+date_received:[{lower}+TO+{upper}]"
            if effective!=expected:raise ValueError(f"{leaf}: partitioned effective_search must exactly match declared interval")
        pages=c.get("pages")
        if not isinstance(pages,list) or not pages or not all(isinstance(page,dict) for page in pages):raise ValueError(f"{leaf}: pages required")
    return str(scope),captures,configured
def _logical(captures:list[dict[str,Any]],configured:Mapping[str,Any])->dict[str,Any]:
    represented={str(c["query_id"]) for c in captures};missing=sorted(set(configured)-represented);part=[c for c in captures if c.get("partition_path")]
    return {"configured_active_query_count":len(configured),"represented_query_count":len(represented),"missing_query_ids":missing,"partitioned_leaf_count":len(part),"partition_reconciliation_required":bool(part),"all_logical_queries_represented":not missing}
def _blockers(cov:Mapping[str,Any],p:Mapping[str,Any])->list[str]:
    out=[];missing=sorted(set(p["coverage_contract"]["required_metrics_per_leaf_query"])-set(cov))
    if missing:out.append("MISSING_COVERAGE_METRICS:"+",".join(missing))
    for k,e in p["coverage_contract"]["mechanical_completion_requires"].items():
        if cov.get(k)!=e:out.append(f"COVERAGE_GATE:{k}:{cov.get(k)!r}!={e!r}")
    if cov.get("candidate_emission_refused_due_to_over_limit") is True:out.append("OVER_LIMIT_CANDIDATE_EMISSION_REFUSED")
    if cov.get("patient_level_fields_projected") is not False:out.append("PATIENT_FIELD_BOUNDARY_VIOLATION")
    if cov.get("mdr_text_narrative_projected") is not False:out.append("MDR_NARRATIVE_BOUNDARY_VIOLATION")
    return out
def build_replay(bundle:Mapping[str,Any],*,projector:Projector|None=None,known_index:Mapping[str,Any]|None=None)->dict[str,Any]:
    p=_programme();scope,captures,configured=_validate_bundle(bundle,p);projector=projector or _load_projector();known=dict(known_index) if known_index is not None else build_known_mdr_source_index()
    if known.get("materialized_source_count")!=248:raise ValueError("Known Source index must bind 248 Sources")
    sd=known.get("source_id_set_sha256");known_map=known.get("mdr_to_source")
    if not isinstance(sd,str) or len(sd)!=64 or not isinstance(known_map,dict):raise ValueError("Known Source index incomplete")
    logical=_logical(captures,configured);reports=[];union:dict[str,dict[str,Any]]={};blocker_count=0;raw_pages=0
    for c in sorted(captures,key=lambda x:str(x["leaf_query_id"])):
        qid=str(c["query_id"]);leaf=str(c["leaf_query_id"]);raw_pages+=len(c["pages"]);projection=projector(query_id=qid,search=c["effective_search"],pages=c["pages"],known_mdr_sources=known_map);cov=projection.get("coverage");records=projection.get("result_records");normalized=projection.get("normalized_records")
        if not isinstance(cov,dict) or not isinstance(records,list) or not isinstance(normalized,list):raise ValueError(f"{leaf}: invalid Workbench projection")
        blockers=_blockers(cov,p);blocker_count+=len(blockers);reports.append({"query_id":qid,"leaf_query_id":leaf,"partition_path":c.get("partition_path"),"effective_search":c["effective_search"],"capture_sha256":_digest(c),"coverage":cov,"mechanical_blockers":blockers})
        by_key:dict[str,dict[str,Any]]={}
        for row in normalized:
            if not isinstance(row,dict) or not isinstance(row.get("mdr_report_key"),str) or not row["mdr_report_key"]:raise ValueError(f"{leaf}: normalized MDR identity missing")
            key=row["mdr_report_key"]
            if key in by_key:raise ValueError(f"{leaf}: duplicate normalized MDR key")
            if row.get("patient_level_fields_included") is not False or row.get("mdr_text_narrative_included") is not False:raise ValueError(f"{leaf}/{key}: minimized metadata boundary violated")
            digest=row.get("normalized_record_sha256")
            if not isinstance(digest,str) or len(digest)!=64:raise ValueError(f"{leaf}/{key}: invalid normalized digest")
            by_key[key]=row
        for rec in records:
            token=rec.get("record_key") if isinstance(rec,dict) else None
            if not isinstance(token,str) or not token.startswith("MAUDE:MDR:"):raise ValueError(f"{leaf}: invalid candidate record_key")
            key=token.removeprefix("MAUDE:MDR:");norm=by_key.get(key)
            if norm is None:raise ValueError(f"{leaf}: candidate lacks normalized MDR")
            candidate={k:rec.get(k) for k in ("record_key","title","url","publisher","source_class","suggested_source_id","classification_hint","duplicate_of_source_id")};digest=norm["normalized_record_sha256"];prior=union.get(key)
            if prior is None:union[key]={"normalized":norm,"digest":digest,"candidate":candidate,"queries":{qid},"leaves":{leaf}}
            else:
                if prior["digest"]!=digest or prior["candidate"]!=candidate:raise ValueError(f"Cross-leaf conflict for MDR report {key}")
                prior["queries"].add(qid);prior["leaves"].add(leaf)
    normalized_out=[];duplicates=[];new=[]
    for key in sorted(union):
        e=union[key];norm=dict(e["normalized"]);norm["query_memberships"]=sorted(e["queries"]);norm["leaf_memberships"]=sorted(e["leaves"]);normalized_out.append(norm);cand={**e["candidate"],"query_memberships":sorted(e["queries"]),"leaf_memberships":sorted(e["leaves"]),"normalized_record_sha256":e["digest"]}
        if cand.get("classification_hint")=="DUPLICATE":duplicates.append(cand)
        elif cand.get("classification_hint")=="NEW":new.append(cand)
        else:raise ValueError(f"Unexpected classification for MDR {key}")
    complete=scope=="FULL_PROGRAMME" and logical["all_logical_queries_represented"] and blocker_count==0 and not logical["partition_reconciliation_required"]
    r={"scope":scope,**logical,"executed_leaf_query_count":len(captures),"leaf_mechanical_blocker_count":blocker_count,"union_unique_mdr_report_key_count":len(union),"known_controlled_duplicate_count":len(duplicates),"new_candidate_input_count":len(new),"materialized_source_namespace_count":248,"controlled_source_id_set_sha256":sd,"postmarket_typed_source_count_before_run":known.get("postmarket_typed_source_count"),"known_mdr_report_key_count_before_run":known.get("known_mdr_report_key_count"),"raw_input_page_count":raw_pages,"raw_reporter_pages_emitted":False,"patient_level_fields_emitted":False,"mdr_text_narratives_emitted":False,"automatic_source_admission":False,"automatic_system_or_device_entity_creation":False,"automatic_manufacturer_entity_creation":False,"automatic_safety_signal_creation":False,"automatic_regulatory_action_creation":False,"automatic_assessment_mutation":False,"mechanically_complete":complete,"maude_database_completeness_claim":False,"global_neuroai_postmarket_recall_claim":False,"causality_claim":False,"incidence_or_rate_claim":False,"comparative_safety_claim":False,"canonical_successor_ready":False}
    return {"schema_version":"0.1.0","status":"NONCANONICAL_SU_REGULATION_MAUDE_RECORDED_REPLAY_PROJECTION","programme_id":p["programme_id"],"input_provenance":{"bundle_sha256":_digest(bundle),"captured_at":bundle["captured_at"],"controlled_source_id_set_sha256":sd,"known_mdr_index_sha256":_digest(known_map),"raw_provider_pages_retained_in_output":False},"known_source_index_summary":{"materialized_source_count":248,"source_id_set_sha256":sd,"postmarket_typed_source_count":known.get("postmarket_typed_source_count"),"known_mdr_report_key_count":known.get("known_mdr_report_key_count"),"global_postmarket_completeness_claim":False},"query_reports":reports,"normalized_mdr_reports":normalized_out,"known_duplicates":duplicates,"new_candidate_inputs":new,"reconciliation":r}
def _write_jsonl(path:Path,rows:list[dict[str,Any]])->dict[str,Any]:
    payload=b"".join(_canon(x) for x in rows);path.write_bytes(payload);return {"path":path.name,"bytes":len(payload),"sha256":hashlib.sha256(payload).hexdigest(),"records":len(rows)}
def write_projection(result:Mapping[str,Any],out:Path)->dict[str,Any]:
    out.mkdir(parents=True,exist_ok=True);files=[]
    for key,name in (("normalized_mdr_reports","normalized-mdr-reports.jsonl"),("known_duplicates","known-mdr-duplicates.jsonl"),("new_candidate_inputs","new-mdr-candidate-inputs.jsonl")):files.append(_write_jsonl(out/name,list(result[key])))
    for key,name in (("input_provenance","input-provenance.json"),("known_source_index_summary","known-source-index-summary.json"),("query_reports","query-reports.json"),("reconciliation","reconciliation.json")):
        payload=_canon(result[key]);(out/name).write_bytes(payload);files.append({"path":name,"bytes":len(payload),"sha256":hashlib.sha256(payload).hexdigest(),"records":1})
    m={"programme_id":result["programme_id"],"status":result["status"],"files":sorted(files,key=lambda x:x["path"]),"file_count":len(files),"raw_reporter_pages_emitted":False,"patient_level_fields_emitted":False,"mdr_text_narratives_emitted":False,"canonical_successor_ready":False};payload=_canon(m);(out/"manifest.json").write_bytes(payload);return {**m,"manifest_sha256":hashlib.sha256(payload).hexdigest()}
def main()->int:
    pa=argparse.ArgumentParser(description=__doc__);pa.add_argument("--input-bundle",type=Path,required=True);pa.add_argument("--output-dir",type=Path,required=True);a=pa.parse_args();res=build_replay(_load(a.input_bundle.resolve()));man=write_projection(res,a.output_dir.resolve());print(json.dumps({"reconciliation":res["reconciliation"],"manifest":man},indent=2,sort_keys=True));return 0 if res["reconciliation"]["mechanically_complete"] else 1
if __name__=="__main__":raise SystemExit(main())
