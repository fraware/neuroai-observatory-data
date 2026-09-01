#!/usr/bin/env python3
"""Deterministic recorded replay for bounded Europe PMC publication discovery."""
from __future__ import annotations
import argparse,hashlib,json,re
from collections.abc import Mapping
from pathlib import Path
from typing import Any,Callable
from urllib.parse import unquote
try:
    from scripts.current_source_namespace import materialize_effective_source_namespace
except ModuleNotFoundError:
    from current_source_namespace import materialize_effective_source_namespace
ROOT=Path(__file__).parents[1];PROGRAMME=ROOT/"curation/europepmc_publications_discovery_programme_v0.1.json"
DOI_RE=re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+",re.I);PUBMED_RE=re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)",re.I);PMCID_RE=re.compile(r"\bPMC\d+\b",re.I);EPMC_RE=re.compile(r"europepmc\.org/article/([^/?#]+)/([^/?#]+)",re.I)
Projector=Callable[...,dict[str,Any]]
def _canon(v:Any)->bytes:return (json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode()
def _digest(v:Any)->str:return hashlib.sha256(_canon(v)).hexdigest()
def _load(p:Path)->Any:return json.loads(p.read_text(encoding="utf-8"))
def _programme()->dict[str,Any]:
    p=_load(PROGRAMME)
    if p.get("programme_id")!="SU-PUBLICATIONS-EUROPEPMC-v0.1" or (p.get("workbench_dependency") or {}).get("integration_state")!="AVAILABLE":raise ValueError("Invalid/current Europe PMC programme")
    return p
def _load_projector()->Projector:
    try:from neuroai_workbench.discovery import project_europepmc_search_pages
    except (ImportError,AttributeError) as exc:raise RuntimeError("Required Workbench Europe PMC capability unavailable") from exc
    return project_europepmc_search_pages
def _bibliographic(source:Mapping[str,Any])->bool:
    token=str(source.get("source_class") or "").upper();return "BIBLIOGRAPHIC" in token or token=="PUBLICATION_RECORD"
def _identities(locator:str)->set[str]:
    text=unquote(locator.strip());out={f"DOI:{m.lower()}" for m in DOI_RE.findall(text)}
    pm=PUBMED_RE.search(text)
    if pm:out.add(f"PMID:{pm.group(1)}")
    for value in PMCID_RE.findall(text):out.add(f"PMCID:{value.upper()}")
    ep=EPMC_RE.search(text)
    if ep:
        source=ep.group(1).upper();ext=ep.group(2);out.add(f"EPMC:{source}:{ext}")
        if source=="MED" and ext.isdigit():out.add(f"PMID:{ext}")
        if source=="PMC" and PMCID_RE.fullmatch(ext.upper()):out.add(f"PMCID:{ext.upper()}")
    return out
def build_known_publication_source_index()->dict[str,Any]:
    ns=materialize_effective_source_namespace();sources=ns.get("sources")
    if ns.get("materialized_source_count")!=248 or not isinstance(sources,list) or len(sources)!=248:raise ValueError("Expected exact 248-Source namespace")
    eligible=set();index={}
    for source in sources:
        if not isinstance(source,Mapping):raise ValueError("Controlled Source row must be object")
        sid=source.get("source_id")
        if not isinstance(sid,str) or not sid:raise ValueError("Controlled Source missing source_id")
        if not _bibliographic(source):continue
        eligible.add(sid);locator=source.get("canonical_locator")
        if not isinstance(locator,str):continue
        for identity in _identities(locator):
            prior=index.get(identity)
            if prior and prior!=sid:raise ValueError(f"Conflicting controlled bibliographic Sources for {identity}")
            index[identity]=sid
    digest=ns.get("source_id_set_sha256")
    if not isinstance(digest,str) or len(digest)!=64:raise ValueError("Controlled Source digest unavailable")
    return {"materialized_source_count":248,"source_id_set_sha256":digest,"eligible_bibliographic_source_count":len(eligible),"known_publication_identity_count":len(index),"identity_to_source":dict(sorted(index.items())),"source_admission_completeness_claim":False,"publication_universe_completeness_claim":False}
def _anchor_aliases(p:Mapping[str,Any])->dict[str,set[str]]:
    out={}
    for row in p["known_identifier_anchors"]:
        aliases={f"DOI:{str(row['doi']).strip().lower()}",f"PMID:{row['pmid']}"};out[row["anchor_id"]]=aliases
    return out
def _validate_bundle(bundle:Mapping[str,Any],p:Mapping[str,Any])->tuple[str,list[dict[str,Any]],dict[str,dict[str,Any]]]:
    if bundle.get("schema_version")!="0.1.0" or bundle.get("programme_id")!=p["programme_id"] or bundle.get("provider")!="Europe PMC":raise ValueError("Replay identity mismatch")
    if bundle.get("raw_input_contains_full_text") is not False or bundle.get("participant_level_data_expected") is not False:raise ValueError("Full text/participant data outside replay contract")
    scope=bundle.get("capture_scope")
    if scope not in {"FULL_PROGRAMME","PARTIAL_VALIDATION"}:raise ValueError("Invalid capture_scope")
    configured={r["query_id"]:dict(r) for r in p["query_streams"] if r.get("status")=="ACTIVE"};captures=bundle.get("query_captures")
    if not isinstance(captures,list) or not captures:raise ValueError("query_captures required")
    seen=set();provider=p["provider_contract"];expected={"endpoint":provider["api_endpoint"],"format":provider["format"],"result_type":provider["result_type"],"page_size":provider["page_size"],"synonym_expansion":provider["synonym_expansion"],"first_cursor_mark":provider["first_cursor_mark"]}
    for capture in captures:
        qid=capture.get("query_id")
        if qid not in configured or qid in seen:raise ValueError("Invalid or duplicate Europe PMC query capture")
        seen.add(qid)
        if capture.get("query_term")!=configured[qid]["query_term"] or capture.get("request")!=expected:raise ValueError(f"{qid}: capture does not match programme control")
        if not isinstance(capture.get("pages"),list) or not capture["pages"]:raise ValueError(f"{qid}: pages required")
    if scope=="FULL_PROGRAMME" and seen!=set(configured):raise ValueError("FULL_PROGRAMME requires all active Europe PMC streams")
    return str(scope),captures,configured
def _blockers(cov:Mapping[str,Any],p:Mapping[str,Any])->list[str]:
    missing=set(p["coverage_contract"]["required_metrics_per_query"])-set(cov);out=[]
    if missing:out.append("MISSING_METRICS:"+",".join(sorted(missing)))
    for k,v in p["coverage_contract"]["mechanical_completion_requires"].items():
        if cov.get(k)!=v:out.append(f"GATE:{k}:{cov.get(k)!r}!={v!r}")
    for k in ("publication_database_completeness_claim","query_recall_claim","global_neuroai_publication_recall_claim","automatic_source_admission_performed","automatic_relationship_creation_performed","automatic_assessment_mutation_performed"):
        if cov.get(k) is not False:out.append(f"BOUNDARY:{k}")
    return out
def build_replay(bundle:Mapping[str,Any],*,projector:Projector|None=None,known_index:Mapping[str,Any]|None=None)->dict[str,Any]:
    p=_programme();scope,captures,configured=_validate_bundle(bundle,p);projector=projector or _load_projector();known=dict(known_index) if known_index is not None else build_known_publication_source_index();known_map=known["identity_to_source"]
    aliases=_anchor_aliases(p);anchor_values=sorted(set().union(*aliases.values()));reports=[];union={};blocker_count=0;represented=set()
    for capture in sorted(captures,key=lambda r:r["query_id"]):
        qid=capture["query_id"];represented.add(qid);projection=projector(query_id=qid,query_text=configured[qid]["query_term"],pages=capture["pages"],known_publication_sources=known_map,known_anchor_identities=anchor_values);cov=projection.get("coverage");records=projection.get("result_records");norms=projection.get("normalized_records")
        if not isinstance(cov,dict) or not isinstance(records,list) or not isinstance(norms,list):raise ValueError("Invalid Workbench Europe PMC projection shape")
        blockers=_blockers(cov,p);blocker_count+=len(blockers);reports.append({"query_id":qid,"capture_sha256":_digest(capture),"coverage":cov,"mechanical_blockers":blockers})
        by={row.get("resolved_identity"):row for row in norms if isinstance(row,dict)}
        if len(by)!=len(norms):raise ValueError("Missing/duplicate normalized publication identity")
        for record in records:
            identity=record.get("record_key")
            if identity not in by:raise ValueError("Europe PMC candidate lacks normalized publication")
            normalized=by[identity];digest=normalized.get("normalized_record_sha256");candidate={k:record.get(k) for k in ("record_key","title","url","publisher","source_class","suggested_source_id","classification_hint","duplicate_of_source_id")};prior=union.get(identity)
            if prior:
                if prior["digest"]!=digest or prior["candidate"]!=candidate:raise ValueError(f"Cross-query conflict for publication {identity}")
                prior["queries"].add(qid)
            else:union[identity]={"normalized":normalized,"digest":digest,"candidate":candidate,"queries":{qid}}
    normalized=[];duplicates=[];new=[]
    for identity in sorted(union):
        row=union[identity];n=dict(row["normalized"]);n["query_memberships"]=sorted(row["queries"]);normalized.append(n);c=dict(row["candidate"]);c["query_memberships"]=sorted(row["queries"]);(duplicates if c.get("classification_hint")=="DUPLICATE" else new).append(c)
    recovered=[];missing=[];present=set(union)
    for aid,vals in aliases.items():
        (recovered if vals & present else missing).append(aid)
    all_queries=represented==set(configured);complete=scope=="FULL_PROGRAMME" and all_queries and blocker_count==0
    reconciliation={"capture_scope":scope,"materialized_source_namespace_count":known["materialized_source_count"],"controlled_source_id_set_sha256":known.get("source_id_set_sha256"),"known_publication_identity_count":known["known_publication_identity_count"],"configured_active_query_count":len(configured),"represented_query_count":len(represented),"all_logical_queries_represented":all_queries,"leaf_mechanical_blocker_count":blocker_count,"union_unique_publication_count":len(union),"known_controlled_duplicate_count":len(duplicates),"new_candidate_input_count":len(new),"recovered_anchor_ids":sorted(recovered),"missing_anchor_ids":sorted(missing),"mechanically_complete":complete,"publication_database_completeness_claim":False,"global_neuroai_publication_recall_claim":False,"query_recall_claim":False,"automatic_source_admission":False,"automatic_relationship_creation":False,"automatic_assessment_mutation":False,"canonical_successor_ready":False}
    return {"normalized_records":normalized,"known_duplicates":duplicates,"new_candidates":new,"query_reports":reports,"known_source_index_summary":{k:v for k,v in known.items() if k!="identity_to_source"},"reconciliation":reconciliation,"input_provenance":{"programme_id":p["programme_id"],"provider":"Europe PMC","captured_at":bundle.get("captured_at"),"input_sha256":_digest(bundle)}}
def write_projection(result:Mapping[str,Any],output:Path)->dict[str,str]:
    output.mkdir(parents=True,exist_ok=True);files={"normalized-publications.jsonl":b"".join(_canon(r) for r in result["normalized_records"]),"known-bibliographic-duplicates.jsonl":b"".join(_canon(r) for r in result["known_duplicates"]),"new-candidate-inputs.jsonl":b"".join(_canon(r) for r in result["new_candidates"]),"query-reports.json":_canon(result["query_reports"]),"reconciliation.json":_canon(result["reconciliation"]),"known-source-index-summary.json":_canon(result["known_source_index_summary"]),"input-provenance.json":_canon(result["input_provenance"])};hashes={}
    for name,data in files.items():(output/name).write_bytes(data);hashes[name]=hashlib.sha256(data).hexdigest()
    manifest={"files":dict(sorted(hashes.items())),"raw_api_pages_emitted":False,"full_text_emitted":False,"participant_level_data_emitted":False,"canonical_successor_ready":False};data=_canon(manifest);(output/"manifest.json").write_bytes(data);hashes["manifest.json"]=hashlib.sha256(data).hexdigest();return dict(sorted(hashes.items()))
def main()->None:
    parser=argparse.ArgumentParser();parser.add_argument("bundle",type=Path);parser.add_argument("output",type=Path);args=parser.parse_args();bundle=_load(args.bundle)
    if not isinstance(bundle,dict):raise ValueError("Replay input must be object")
    write_projection(build_replay(bundle),args.output)
if __name__=="__main__":main()
