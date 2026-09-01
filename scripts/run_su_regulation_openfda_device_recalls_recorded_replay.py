#!/usr/bin/env python3
"""Deterministic recorded replay for bounded openFDA device-recall discovery."""
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
PROGRAMME=ROOT/"curation/openfda_device_recall_discovery_programme_v0.1.json"
CFRES_RE=re.compile(r"cfres_id(?:=|:|%3A|%3D)%?22?([A-Za-z0-9._-]+)",re.I)
Projector=Callable[...,dict[str,Any]]

def _canon(v:Any)->bytes: return (json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode()
def _digest(v:Any)->str: return hashlib.sha256(_canon(v)).hexdigest()
def _load(p:Path)->Any: return json.loads(p.read_text(encoding="utf-8"))
def _programme()->dict[str,Any]:
    p=_load(PROGRAMME)
    if p.get("programme_id")!="SU-REGULATION-OPENFDA-DEVICE-RECALLS-v0.1": raise ValueError("Invalid recall programme")
    return p

def _load_projector()->Projector:
    try: from neuroai_workbench.discovery import project_openfda_device_recall_pages
    except (ImportError,AttributeError) as exc: raise RuntimeError("Required Workbench capability project_openfda_device_recall_pages unavailable; integration remains PENDING_S1_MERGE") from exc
    return project_openfda_device_recall_pages

def _eligible(source:Mapping[str,Any])->bool:
    c=str(source.get("source_class") or "").upper()
    return any(x in c for x in ("RECALL","POSTMARKET","ENFORCEMENT"))

def _cfres_from_locator(locator:str)->set[str]:
    text=unquote(locator)
    return {m.group(1) for m in CFRES_RE.finditer(text)}

def build_known_cfres_source_index()->dict[str,Any]:
    modules=(("V1_4",project_v14_sources_to_v2),("V1_6",project_v16_sources_observations_to_v2),("V1_7",project_v17_prima_sources_to_v2))
    all_ids=set(); eligible=set(); index={}
    for family,module in modules:
        for source in module.project().get("sources",[]):
            sid=source.get("source_id")
            if not isinstance(sid,str) or not sid: raise ValueError(f"{family}: missing source_id")
            if sid in all_ids: raise ValueError(f"Duplicate Source identity {sid}")
            all_ids.add(sid)
            if not _eligible(source): continue
            eligible.add(sid)
            loc=source.get("canonical_locator")
            if not isinstance(loc,str): continue
            for rid in _cfres_from_locator(loc):
                prior=index.get(rid)
                if prior and prior!=sid: raise ValueError(f"Conflicting controlled Sources for cfres_id {rid}")
                index[rid]=sid
    if len(all_ids)!=248: raise ValueError(f"Expected 248 Sources, found {len(all_ids)}")
    return {"materialized_source_count":248,"recall_typed_source_count":len(eligible),"known_cfres_id_count":len(index),"cfres_to_source":dict(sorted(index.items())),"global_recall_completeness_claim":False}

def _active(p:Mapping[str,Any])->dict[str,dict[str,Any]]:
    return {r["query_id"]:dict(r) for r in p["query_streams"] if r.get("status")=="ACTIVE"}

def _validate_bundle(bundle:Mapping[str,Any],p:dict[str,Any])->tuple[str,list[dict[str,Any]],dict[str,dict[str,Any]]]:
    if bundle.get("schema_version")!="0.1.0" or bundle.get("programme_id")!=p["programme_id"] or bundle.get("provider")!=p["provider_contract"]["provider"]: raise ValueError("Replay identity mismatch")
    scope=bundle.get("capture_scope")
    if scope not in {"FULL_PROGRAMME","PARTIAL_VALIDATION"}: raise ValueError("Invalid capture_scope")
    captures=bundle.get("leaf_query_captures"); configured=_active(p)
    if not isinstance(captures,list) or not captures: raise ValueError("leaf_query_captures required")
    seen=set()
    for c in captures:
        qid=c.get("query_id"); leaf=c.get("leaf_query_id")
        if qid not in configured or not isinstance(leaf,str) or not leaf or leaf in seen: raise ValueError("Invalid or duplicate recall leaf")
        seen.add(leaf); root=configured[qid]["search"]; effective=c.get("effective_search"); part=c.get("partition_path")
        if not isinstance(part,list) or not isinstance(effective,str): raise ValueError(f"{leaf}: invalid search/partition")
        if not part and effective!=root: raise ValueError(f"{leaf}: unpartitioned search must equal programme control")
        if part:
            if len(part)!=1 or part[0].get("dimension")!="EVENT_DATE_POSTED": raise ValueError(f"{leaf}: only EVENT_DATE_POSTED partition supported")
            lo,hi=part[0].get("lower_bound"),part[0].get("upper_bound")
            expected=f'({root})+AND+event_date_posted:[{lo}+TO+{hi}]'
            if effective!=expected: raise ValueError(f"{leaf}: partitioned search must exactly bind date interval")
        pages=c.get("pages")
        if not isinstance(pages,list) or not pages or not all(isinstance(x,dict) for x in pages): raise ValueError(f"{leaf}: pages required")
    return str(scope),captures,configured

def _leaf_blockers(cov:Mapping[str,Any],p:Mapping[str,Any])->list[str]:
    blockers=[]
    missing=set(p["coverage_contract"]["required_metrics_per_leaf_query"])-set(cov)
    if missing: blockers.append("MISSING_METRICS:"+",".join(sorted(missing)))
    for k,v in p["coverage_contract"]["mechanical_completion_requires"].items():
        if cov.get(k)!=v: blockers.append(f"GATE:{k}:{cov.get(k)!r}!={v!r}")
    if cov.get("address_or_contact_fields_projected") or cov.get("code_info_lot_serial_text_projected") or cov.get("distribution_pattern_projected"): blockers.append("MINIMIZATION_VIOLATION")
    return blockers

def build_replay(bundle:Mapping[str,Any],*,projector:Projector|None=None,known_index:Mapping[str,Any]|None=None)->dict[str,Any]:
    p=_programme(); scope,captures,configured=_validate_bundle(bundle,p); projector=projector or _load_projector(); known=dict(known_index) if known_index is not None else build_known_cfres_source_index(); known_map=known["cfres_to_source"]
    reports=[]; union={}; blocker_count=0
    represented={c["query_id"] for c in captures}; partitioned=sum(bool(c["partition_path"]) for c in captures)
    for c in sorted(captures,key=lambda x:x["leaf_query_id"]):
        proj=projector(query_id=c["query_id"],search=c["effective_search"],pages=c["pages"],known_cfres_sources=known_map)
        cov=proj.get("coverage"); records=proj.get("result_records"); norms=proj.get("normalized_records")
        if not isinstance(cov,dict) or not isinstance(records,list) or not isinstance(norms,list): raise ValueError("Invalid Workbench recall projection shape")
        blockers=_leaf_blockers(cov,p); blocker_count+=len(blockers)
        reports.append({"query_id":c["query_id"],"leaf_query_id":c["leaf_query_id"],"partition_path":c["partition_path"],"effective_search":c["effective_search"],"capture_sha256":_digest(c),"coverage":cov,"mechanical_blockers":blockers})
        norm_by={n.get("cfres_id"):n for n in norms if isinstance(n,dict)}
        if len(norm_by)!=len(norms): raise ValueError("Missing/duplicate normalized cfres_id")
        for r in records:
            key=r.get("record_key"); rid=str(key).split(":",1)[1] if isinstance(key,str) and key.startswith("OPENFDA_RECALL:") else None
            if rid not in norm_by: raise ValueError("Recall candidate lacks normalized record")
            n=norm_by[rid]; digest=n.get("normalized_record_sha256")
            candidate={k:r.get(k) for k in ("record_key","title","url","publisher","source_class","suggested_source_id","classification_hint","duplicate_of_source_id")}
            prior=union.get(rid)
            if prior:
                if prior["normalized_record_sha256"]!=digest or prior["candidate"]!=candidate: raise ValueError(f"Cross-query conflict for cfres_id {rid}")
                prior["query_memberships"].add(c["query_id"])
            else: union[rid]={"normalized":n,"normalized_record_sha256":digest,"candidate":candidate,"query_memberships":{c["query_id"]}}
    normalized=[]; known_dups=[]; new=[]
    for rid in sorted(union):
        row=union[rid]; n=dict(row["normalized"]); n["query_memberships"]=sorted(row["query_memberships"]); normalized.append(n)
        cand=dict(row["candidate"]); cand["query_memberships"]=sorted(row["query_memberships"])
        (known_dups if cand.get("classification_hint")=="DUPLICATE" else new).append(cand)
    all_queries=set(configured)==represented
    mechanically_complete=(scope=="FULL_PROGRAMME" and all_queries and partitioned==0 and blocker_count==0)
    reconciliation={"capture_scope":scope,"materialized_source_namespace_count":known["materialized_source_count"],"known_cfres_id_count":known["known_cfres_id_count"],"configured_active_query_count":len(configured),"represented_query_count":len(represented),"all_logical_queries_represented":all_queries,"partitioned_leaf_count":partitioned,"partition_reconciliation_required":partitioned>0,"leaf_mechanical_blocker_count":blocker_count,"union_unique_cfres_id_count":len(union),"known_controlled_duplicate_count":len(known_dups),"new_candidate_input_count":len(new),"mechanically_complete":mechanically_complete,"automatic_recall_event_entity_creation":False,"automatic_system_or_firm_entity_creation":False,"automatic_submission_relationship_creation":False,"automatic_system_nonconformance_claim_creation":False,"automatic_reopening_decision":False,"automatic_assessment_mutation":False,"recall_status_is_complete_lifecycle_tracker":False,"canonical_successor_ready":False,"global_neuroai_device_recall_claim":False}
    return {"normalized_records":normalized,"known_duplicates":known_dups,"new_candidates":new,"query_reports":reports,"known_source_index_summary":{k:v for k,v in known.items() if k!="cfres_to_source"},"reconciliation":reconciliation,"input_provenance":{"programme_id":p["programme_id"],"provider":p["provider_contract"]["provider"],"captured_at":bundle.get("captured_at"),"input_sha256":_digest(bundle)}}

def write_projection(result:Mapping[str,Any],out:Path)->dict[str,str]:
    out.mkdir(parents=True,exist_ok=True)
    files={"normalized-recalls.jsonl":b"".join(_canon(r) for r in result["normalized_records"]),"known-recall-duplicates.jsonl":b"".join(_canon(r) for r in result["known_duplicates"]),"new-recall-candidate-inputs.jsonl":b"".join(_canon(r) for r in result["new_candidates"]),"query-reports.json":_canon(result["query_reports"]),"reconciliation.json":_canon(result["reconciliation"]),"known-source-index-summary.json":_canon(result["known_source_index_summary"]),"input-provenance.json":_canon(result["input_provenance"])}
    manifest={}
    for name,data in files.items(): (out/name).write_bytes(data); manifest[name]=hashlib.sha256(data).hexdigest()
    m=_canon({"files":dict(sorted(manifest.items())),"raw_openfda_pages_emitted":False,"canonical_successor_ready":False}); (out/"manifest.json").write_bytes(m); manifest["manifest.json"]=hashlib.sha256(m).hexdigest(); return manifest

def main()->None:
    ap=argparse.ArgumentParser(); ap.add_argument("--input",type=Path,required=True); ap.add_argument("--output",type=Path,required=True); args=ap.parse_args(); write_projection(build_replay(_load(args.input)),args.output)
if __name__=="__main__": main()
