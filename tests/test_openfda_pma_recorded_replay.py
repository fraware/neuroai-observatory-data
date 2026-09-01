from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, "scripts")
import run_su_regulation_openfda_pma_recorded_replay as replay


def _page(rows, total=None, skip=0, limit=1000):
    return {"meta":{"results":{"total":len(rows) if total is None else total,"skip":skip,"limit":limit}},"results":rows}


def _record(pma="P123456", supp=None, decision="APPR", trade="Neural System"):
    return {"pma_number":pma,"supplement_number":supp,"decision_code":decision,"trade_name":trade,"generic_name":"Neural interface","applicant":"Example Applicant","decision_date":"20260801","product_code":"XYZ"}


def _fake_projector(*,query_id,search,pages,known_record_sources):
    by={};hde=nda=unresolved=0;raw=0;totals=[];seq=True;prev_skip=prev_limit=None
    decision_map={"APPR":"APPROVAL_RECORDED","WTDR":"WITHDRAWAL_RECORDED","DENY":"DENIAL_RECORDED","LE30":"THIRTY_DAY_NOTICE_ACCEPTANCE_RECORDED","APRL":"RECLASSIFICATION_AFTER_APPROVAL_RECORDED","APWD":"WITHDRAWAL_AFTER_APPROVAL_RECORDED","GT30":"NO_DECISION_WITHIN_30_DAYS_RECORDED","APCV":"CONVERSION_AFTER_APPROVAL_RECORDED"}
    for i,page in enumerate(pages):
        meta=page["meta"]["results"];totals.append(meta["total"]);skip=meta["skip"];limit=meta["limit"]
        if i==0 and skip!=0:seq=False
        if prev_skip is not None and skip!=prev_skip+prev_limit:seq=False
        prev_skip,prev_limit=skip,limit;raw+=len(page["results"])
        for r in page["results"]:
            pma=str(r.get("pma_number") or "").upper()
            if pma.startswith("H"):hde+=1;continue
            if pma.startswith("N"):nda+=1;continue
            if not (pma.startswith("P") or pma.startswith("BP") or pma.startswith("D")):unresolved+=1;continue
            supp=str(r.get("supplement_number") or "ORIGINAL").upper();identity=f"PMA:{pma}:{supp}";code=str(r.get("decision_code") or "").upper();sem=decision_map.get(code,"UNRESOLVED_DECISION_CODE")
            normalized={"record_kind":"NORMALIZED_OPENFDA_PMA_DECISION","pma_number":pma,"supplement_number":supp,"record_identity":identity,"record_role":"ORIGINAL_APPLICATION" if supp=="ORIGINAL" else "SUPPLEMENT","trade_name":r.get("trade_name"),"generic_name":r.get("generic_name"),"applicant":r.get("applicant"),"date_received":r.get("date_received"),"decision_date":r.get("decision_date"),"decision_code":code or None,"decision_semantics":sem,"decision_code_recognized":code in decision_map,"decision_supports_approval":code=="APPR","product_code":r.get("product_code"),"supplement_type":r.get("supplement_type"),"supplement_reason":r.get("supplement_reason"),"ao_statement":r.get("ao_statement"),"expedited_review_flag":r.get("expedited_review_flag"),"query_memberships":[query_id],"boundary":"fixture"}
            core=dict(normalized);core.pop("query_memberships");normalized["normalized_record_sha256"]=replay._digest(core)
            prior=by.get(identity)
            if prior and prior["normalized_record_sha256"]!=normalized["normalized_record_sha256"]:raise ValueError(f"Conflicting normalized PMA representations for {identity}")
            by[identity]=normalized
    reported=totals[0] if totals and len(set(totals))==1 else None;over=reported is not None and reported>26000
    accounted=len(by)+hde+nda+unresolved
    state="DENOMINATOR_UNAVAILABLE" if reported is None else "OVER_LIMIT_SEARCH_AFTER_OR_PARTITION_REQUIRED" if over else "INVALID_SEQUENCE" if not seq else "MATCH" if accounted==reported else "PARTIAL_OR_MISMATCH"
    records=[];norms=[];dups=[]
    if not over:
        for identity in sorted(by):
            n=by[identity];dup=known_record_sources.get(identity);r={"record_key":identity,"title":n.get("trade_name") or identity,"url":"https://api.fda.gov/device/pma.json","publisher":"U.S. FDA","source_class":"OFFICIAL_REGULATORY_RECORD","suggested_source_id":"SRC-"+identity.replace(":","-"),"classification_hint":"DUPLICATE" if dup else "NEW","decision_semantics":n["decision_semantics"]}
            if dup:r["duplicate_of_source_id"]=dup;dups.append({"record_identity":identity,"source_id":dup})
            records.append(r);norms.append(n)
    cov={"supplied_page_count":len(pages),"returned_record_count":raw,"unique_composite_record_count":len(by),"reported_total_count":reported,"reported_total_count_state":"CONSISTENT" if reported is not None else "INCONSISTENT_ACROSS_PAGES","skip_sequence_valid":seq,"skip_coverage_state":state,"over_26000_limit":over,"search_after_or_partition_required":over,"out_of_scope_hde_count":hde,"out_of_scope_legacy_nda_count":nda,"known_controlled_duplicate_count":len(dups),"new_candidate_count":len(records)-len(dups),"duplicate_representation_count":0,"unresolved_pma_number_count":unresolved,"decision_semantics_derived_only_from_exact_decision_code":True}
    return {"result_records":records,"normalized_records":norms,"coverage":cov}


class OpenFdaPmaReplayTests(unittest.TestCase):
    def _bundle(self, rows_by_query, scope="PARTIAL_VALIDATION", partition=False):
        p=replay._programme();captures=[]
        for row in p["query_streams"]:
            qid=row["query_id"]
            if qid not in rows_by_query:continue
            part=[];effective=row["search"]
            if partition:
                part=[{"field":"decision_date","lower":"20260101","upper":"20261231"}]
                effective=f'({effective})+AND+decision_date:[20260101+TO+20261231]'
            captures.append({"query_id":qid,"leaf_query_id":qid+"-leaf","effective_search":effective,"partition_path":part,"pages":[_page(rows_by_query[qid])]})
        return {"schema_version":"0.1.0","programme_id":p["programme_id"],"provider":p["provider_contract"]["provider"],"capture_scope":scope,"captured_at":"2026-09-01T00:00:00Z","leaf_query_captures":captures}

    def test_real_controlled_namespace_materializes_248_sources(self):
        index=replay.build_known_record_source_index()
        self.assertEqual(index["materialized_source_count"],248)
        self.assertFalse(index["global_pma_completeness_claim"])

    def test_bare_pma_locator_does_not_guess_original_record(self):
        self.assertEqual(replay._composite_from_locator("https://api.fda.gov/device/pma.json?search=pma_number:P123456"),set())
        self.assertEqual(replay._composite_from_locator("https://example.org/pma/P123456?record_role=original"),{"PMA:P123456:ORIGINAL"})

    def test_partial_replay_preserves_original_and_supplement_as_distinct(self):
        q=replay._programme()["query_streams"][0]["query_id"]
        result=replay.build_replay(self._bundle({q:[_record(),_record(supp="S001")]}),projector=_fake_projector,known_index={"materialized_source_count":248,"known_composite_pma_record_count":0,"record_to_source":{}})
        ids={r["record_identity"] for r in result["normalized_records"]}
        self.assertEqual(ids,{"PMA:P123456:ORIGINAL","PMA:P123456:S001"})
        self.assertFalse(result["reconciliation"]["mechanically_complete"])

    def test_exact_composite_duplicate_only(self):
        q=replay._programme()["query_streams"][0]["query_id"]
        known={"materialized_source_count":248,"known_composite_pma_record_count":1,"record_to_source":{"PMA:P123456:S001":"SRC-KNOWN"}}
        result=replay.build_replay(self._bundle({q:[_record(),_record(supp="S001")]}),projector=_fake_projector,known_index=known)
        self.assertEqual(result["reconciliation"]["known_controlled_duplicate_count"],1)
        self.assertEqual(result["known_duplicates"][0]["record_key"],"PMA:P123456:S001")

    def test_partition_never_implies_programme_completion(self):
        rows={r["query_id"]:[_record(pma=f"P{i+100000}")] for i,r in enumerate(replay._programme()["query_streams"])}
        result=replay.build_replay(self._bundle(rows,scope="FULL_PROGRAMME",partition=True),projector=_fake_projector,known_index={"materialized_source_count":248,"known_composite_pma_record_count":0,"record_to_source":{}})
        self.assertTrue(result["reconciliation"]["partition_reconciliation_required"])
        self.assertFalse(result["reconciliation"]["mechanically_complete"])

    def test_full_unpartitioned_clean_programme_can_be_mechanically_complete(self):
        rows={r["query_id"]:[_record(pma=f"P{i+200000}")] for i,r in enumerate(replay._programme()["query_streams"])}
        result=replay.build_replay(self._bundle(rows,scope="FULL_PROGRAMME"),projector=_fake_projector,known_index={"materialized_source_count":248,"known_composite_pma_record_count":0,"record_to_source":{}})
        self.assertTrue(result["reconciliation"]["mechanically_complete"])
        self.assertFalse(result["reconciliation"]["canonical_successor_ready"])
        self.assertTrue(result["reconciliation"]["approval_state_requires_exact_appr_code"])

    def test_cross_query_content_conflict_fails_closed(self):
        p=replay._programme();q1,q2=p["query_streams"][0]["query_id"],p["query_streams"][1]["query_id"]
        bundle=self._bundle({q1:[_record(trade="A")],q2:[_record(trade="B")]})
        with self.assertRaisesRegex(ValueError,"Cross-query conflict"):
            replay.build_replay(bundle,projector=_fake_projector,known_index={"materialized_source_count":248,"known_composite_pma_record_count":0,"record_to_source":{}})

    def test_hde_and_legacy_nda_are_not_pma_candidates(self):
        q=replay._programme()["query_streams"][0]["query_id"]
        result=replay.build_replay(self._bundle({q:[_record(pma="H123456"),_record(pma="N123456"),_record(pma="P123456")]}),projector=_fake_projector,known_index={"materialized_source_count":248,"known_composite_pma_record_count":0,"record_to_source":{}})
        self.assertEqual(result["reconciliation"]["out_of_scope_hde_count"],1)
        self.assertEqual(result["reconciliation"]["out_of_scope_legacy_nda_count"],1)
        self.assertEqual(result["reconciliation"]["union_unique_composite_record_count"],1)

    def test_deterministic_outputs_do_not_emit_raw_pages(self):
        q=replay._programme()["query_streams"][0]["query_id"]
        result=replay.build_replay(self._bundle({q:[_record()]}),projector=_fake_projector,known_index={"materialized_source_count":248,"known_composite_pma_record_count":0,"record_to_source":{}})
        with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
            ma=replay.write_projection(result,Path(a));mb=replay.write_projection(result,Path(b));self.assertEqual(ma,mb)
            names={p.name for p in Path(a).iterdir()};self.assertNotIn("raw-pages.json",names)
            manifest=json.loads((Path(a)/"manifest.json").read_text());self.assertFalse(manifest["raw_openfda_pages_emitted"]);self.assertFalse(manifest["canonical_successor_ready"])

if __name__=="__main__":unittest.main()
