#!/usr/bin/env python3
"""Deterministic recorded replay for bounded openFDA PMA discovery."""
from __future__ import annotations
import argparse, hashlib, json, re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote

import project_v14_sources_to_v2
import project_v16_sources_observations_to_v2
import project_v17_prima_sources_to_v2

ROOT=Path(__file__).parents[1]
PROGRAMME=ROOT/"curation/openfda_pma_discovery_programme_v0.1.json"
PMA_LOCATOR_RE=re.compile(r"(?:pma_number|pma)(?:=|:|/|%3A|%3D)%?22?((?:BP|P|D)[A-Za-z0-9._-]+)",re.I)
SUPP_LOCATOR_RE=re.compile(r"(?:supplement_number|supplement|supp)(?:=|:|/|%3A|%3D)%?22?([A-Za-z0-9._-]+)",re.I)
Projector=Callable[...,dict[str,Any]]

def _canon(v:Any)->bytes:return (json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode()
def _digest(v:Any)->str:return hashlib.sha256(_canon(v)).hexdigest()
def _load(p:Path)->Any:return json.loads(p.read_text(encoding="utf-8"))
def _programme()->dict[str,Any]:
    p=_load(PROGRAMME)
    if p.get("programme_id")!="SU-REGULATION-OPENFDA-PMA-v0.1":raise ValueError("Invalid PMA programme")
    return p

def _load_projector()->Projector:
    try:from neuroai_workbench.discovery import project_openfda_pma_pages
    except (ImportError,AttributeError) as exc:raise RuntimeError("Required Workbench capability project_openfda_pma_pages unavailable; integration remains PENDING_S1_MERGE") from exc
    return project_openfda_pma_pages

def _eligible(source:Mapping[str,Any])->bool:
    c=str(source.get("source_class") or "").upper()
    return "REGULATORY" in c or "PMA" in c or "APPROVAL" in c

def _composite_from_locator(locator:str)->set[str]:
    text=unquote(locator);pmas={m.group(1).upper() for m in PMA_LOCATOR_RE.finditer(text)};supps={m.group(1).upper() for m in SUPP_LOCATOR_RE.finditer(text)}
    if len(pmas)!=1:return set()
    pma=next(iter(pmas))
    if len(supps)==1:return {f"PMA:{pma}:{next(iter(supps))}"}
    # A bare PMA locator is not enough to infer ORIGINAL when the source could describe a lineage/supplement.
    explicit_original=any(token in text.lower() for token in ("original_application","original-application","record_role=original","record_role:original"))
    return {f"PMA:{pma}:ORIGINAL"} if explicit_original else set()

def build_known_record_source_index()->dict[str,Any]:
    modules=(("V1_4",project_v14_sources_to_v2),("V1_6",project_v16_sources_observations_to_v2),("V1_7",project_v17_prima_sources_to_v2))
    all_ids=set();eligible=set();index={}
    for family,module in modules:
        sources=module.project().get("sources",[])
        for source in sources:
            sid=source.get("source_id")
            if not isinstance(sid,str) or not sid:raise ValueError(f"{family}: missing source_id")
            if sid in all_ids:raise ValueError(f"Duplicate Source identity {sid}")
            all_ids.add(sid)
            if not _eligible(source):continue
            eligible.add(sid);loc=source.get("canonical_locator")
            if not isinstance(loc,str):continue
            for identity in _composite_from_locator(loc):
                prior=index.get(identity)
                if prior and prior!=sid:raise ValueError(f"Conflicting controlled Sources for PMA record {identity}")
                index[identity]=sid
    if len(all_ids)!=248:raise ValueError(f"Expected 248 Sources, found {len(all_ids)}")
    return {"materialized_source_count":248,"regulatory_typed_source_count":len(eligible),"known_composite_pma_record_count":len(index),"record_to_source":dict(sorted(index.items())),"global_pma_completeness_claim":False}

def _active(p:Mapping[str,Any])->dict[str,dict[str,Any]]:return {r["query_id"]:dict(r) for r in p["query_streams"] if r.get("status")=="ACTIVE"}

def _validate_bundle(bundle:Mapping[str,Any],p:dict[str,Any])->tuple[str,list[dict[str,Any]],dict[str,dict[str,Any]]]:
    if bundle.get("schema_version")!="0.1.0" or bundle.get("programme_id")!=p["programme_id"] or bundle.get("provider")!=p["provider_contract"]["provider"]:raise ValueError("Replay identity mismatch")
    scope=bundle.get("capture_scope")
    if scope not in {"FULL_PROGRAMME","PARTIAL_VALIDATION"}:raise ValueError("Invalid capture_scope")
    captures=bundle.get("leaf_query_captures");configured=_active(p)
    if not isinstance(captures,list) or not captures:raise ValueError("leaf_query_captures required")
    seen=set()
    for c in captures:
        qid=c.get("query_id");leaf=c.get("leaf_query_id")
        if qid not in configured or not isinstance(leaf,str) or not leaf or leaf in seen:raise ValueError("Invalid or duplicate PMA leaf")
        seen.add(leaf);root=configured[qid]["search"];effective=c.get("effective_search");part=c.get("partition_path")
        if not isinstance(part,list) or not isinstance(effective,str):raise ValueError(f"{leaf}: invalid search/partition")
        if not part and effective!=root:raise ValueError(f"{leaf}: unpartitioned search must equal programme control")
        if part:
            if len(part)!=1 or part[0].get("field")!="decision_date":raise ValueError(f"{leaf}: only decision_date partition supported")
            lo,hi=part[0].get("lower"),part[0].get("upper");expected=f'({root})+AND+decision_date:[{lo}+TO+{hi}]'
            if effective!=expected:raise ValueError(f"{leaf}: partitioned search must exactly bind decision-date interval")
            if not (isinstance(lo,str) and isinstance(hi,str) and re.fullmatch(r"\d{8}",lo) and re.fullmatch(r"\d{8}",hi) and lo<=hi):raise ValueError(f"{leaf}: invalid decision-date bounds")
        pages=c.get("pages")
        if not isinstance(pages,list) or not pages or not all(isinstance(x,dict) for x in pages):raise ValueError(f"{leaf}: pages required")
    return str(scope),captures,configured

def _leaf_blockers(cov:Mapping[str,Any],p:Mapping[str,Any])->list[str]:
    blockers=[];missing=set(p["coverage_contract"]["required_metrics_per_leaf_query"])-set(cov)
    if missing:blockers.append("MISSING_METRICS:"+",".join(sorted(missing)))
    for k,v in p["coverage_contract"]["mechanical_completion_requires"].items():
        if cov.get(k)!=v:blockers.append(f"GATE:{k}:{cov.get(k)!r}!={v!r}")
    if cov.get("decision_semantics_derived_only_from_exact_decision_code") is not True:blockers.append("DECISION_SEMANTICS_BOUNDARY_MISSING")
    return blockers

def build_replay(bundle:Mapping[str,Any],*,projector:Projector|None=None,known_index:Mapping[str,Any]|None=None)->dict[str,Any]:
    p=_programme();scope,captures,configured=_validate_bundle(bundle,p);projector=projector or _load_projector();known=dict(known_index) if known_index is not None else build_known_record_source_index();known_map=known["record_to_source"]
    reports=[];union={};blockers=0;represented={c["query_id"] for c in captures};partitioned=sum(bool(c["partition_path"]) for c in captures);hde_total=0;nda_total=0;unresolved_total=0
    for c in sorted(captures,key=lambda x:x["leaf_query_id"]):
        proj=projector(query_id=c["query_id"],search=c["effective_search"],pages=c["pages"],known_record_sources=known_map)
        cov=proj.get("coverage");records=proj.get("result_records");norms=proj.get("normalized_records")
        if not isinstance(cov,dict) or not isinstance(records,list) or not isinstance(norms,list):raise ValueError("Invalid Workbench PMA projection shape")
        leaf_blockers=_leaf_blockers(cov,p);blockers+=len(leaf_blockers);hde_total+=int(cov.get("out_of_scope_hde_count") or 0);nda_total+=int(cov.get("out_of_scope_legacy_nda_count") or 0);unresolved_total+=int(cov.get("unresolved_pma_number_count") or 0)
        reports.append({"query_id":c["query_id"],"leaf_query_id":c["leaf_query_id"],"partition_path":c["partition_path"],"effective_search":c["effective_search"],"capture_sha256":_digest(c),"coverage":cov,"mechanical_blockers":leaf_blockers})
        norm_by={n.get("record_identity"):n for n in norms if isinstance(n,dict)}
        if len(norm_by)!=len(norms):raise ValueError("Missing/duplicate normalized PMA record identity")
        for r in records:
            identity=r.get("record_key")
            if identity not in norm_by:raise ValueError("PMA candidate lacks normalized record")
            n=norm_by[identity];digest=n.get("normalized_record_sha256");candidate={x:r.get(x) for x in ("record_key","title","url","publisher","source_class","suggested_source_id","classification_hint","duplicate_of_source_id","decision_semantics")}
            prior=union.get(identity)
            if prior:
                if prior["normalized_record_sha256"]!=digest or prior["candidate"]!=candidate:raise ValueError(f"Cross-query conflict for PMA record {identity}")
                prior["query_memberships"].add(c["query_id"])
            else:union[identity]={"normalized":n,"normalized_record_sha256":digest,"candidate":candidate,"query_memberships":{c["query_id"]}}
    normalized=[];known_dups=[];new=[]
    for identity in sorted(union):
        row=union[identity];n=dict(row["normalized"]);n["query_memberships"]=sorted(row["query_memberships"]);normalized.append(n);cand=dict(row["candidate"]);cand["query_memberships"]=sorted(row["query_memberships"]);(known_dups if cand.get("classification_hint")=="DUPLICATE" else new).append(cand)
    all_queries=set(configured)==represented;complete=(scope=="FULL_PROGRAMME" and all_queries and partitioned==0 and blockers==0)
    reconciliation={"capture_scope":scope,"materialized_source_namespace_count":known["materialized_source_count"],"known_composite_pma_record_count":known["known_composite_pma_record_count"],"configured_active_query_count":len(configured),"represented_query_count":len(represented),"all_logical_queries_represented":all_queries,"partitioned_leaf_count":partitioned,"partition_reconciliation_required":partitioned>0,"leaf_mechanical_blocker_count":blockers,"union_unique_composite_record_count":len(union),"out_of_scope_hde_count":hde_total,"out_of_scope_legacy_nda_count":nda_total,"unresolved_pma_number_count":unresolved_total,"known_controlled_duplicate_count":len(known_dups),"new_candidate_input_count":len(new),"mechanically_complete":complete,"exact_decision_code_map":p["decision_semantics_policy"]["exact_code_map"],"approval_state_requires_exact_appr_code":True,"automatic_original_supplement_lineage_relationship_creation":False,"automatic_device_or_applicant_entity_creation":False,"automatic_current_commercial_configuration_claim_creation":False,"automatic_global_authorization_claim_creation":False,"automatic_system_conformance_claim_creation":False,"automatic_reopening_decision":False,"automatic_assessment_mutation":False,"canonical_successor_ready":False,"global_neuroai_pma_coverage_claim":False}
    return {"normalized_records":normalized,"known_duplicates":known_dups,"new_candidates":new,"query_reports":reports,"known_source_index_summary":{k:v for k,v in known.items() if k!="record_to_source"},"reconciliation":reconciliation,"input_provenance":{"programme_id":p["programme_id"],"provider":p["provider_contract"]["provider"],"captured_at":bundle.get("captured_at"),"input_sha256":_digest(bundle)}}

def write_projection(result:Mapping[str,Any],out:Path)->dict[str,str]:
    out.mkdir(parents=True,exist_ok=True);files={"normalized-pma-records.jsonl":b"".join(_canon(r) for r in result["normalized_records"]),"known-pma-duplicates.jsonl":b"".join(_canon(r) for r in result["known_duplicates"]),"new-pma-candidate-inputs.jsonl":b"".join(_canon(r) for r in result["new_candidates"]),"query-reports.json":_canon(result["query_reports"]),"reconciliation.json":_canon(result["reconciliation"]),"known-source-index-summary.json":_canon(result["known_source_index_summary"]),"input-provenance.json":_canon(result["input_provenance"])};manifest={}
    for name,data in files.items():(out/name).write_bytes(data);manifest[name]=hashlib.sha256(data).hexdigest()
    m=_canon({"files":dict(sorted(manifest.items())),"raw_openfda_pages_emitted":False,"canonical_successor_ready":False});(out/"manifest.json").write_bytes(m);manifest["manifest.json"]=hashlib.sha256(m).hexdigest();return manifest

def main()->None:
    ap=argparse.ArgumentParser();ap.add_argument("--input",type=Path,required=True);ap.add_argument("--output",type=Path,required=True);a=ap.parse_args();write_projection(build_replay(_load(a.input)),a.output)
if __name__=="__main__":main()
