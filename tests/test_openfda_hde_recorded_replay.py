from __future__ import annotations
import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,"scripts")
import run_su_regulation_openfda_hde_recorded_replay as replay

def page(rows,total=None,skip=0,limit=1000):return {"meta":{"results":{"total":len(rows) if total is None else total,"skip":skip,"limit":limit}},"results":rows}
def rec(h="H123456",supp=None,decision="APPR",trade="HUD Neural System"):return {"pma_number":h,"supplement_number":supp,"decision_code":decision,"trade_name":trade,"generic_name":"Neural interface","applicant":"HUD Applicant","decision_date":"20260801","product_code":"XYZ"}
def fake_projector(*,query_id,search,pages,known_record_sources):
    decision_map={"APPR":"HDE_APPROVAL_RECORDED","WTDR":"WITHDRAWAL_RECORDED","DENY":"DENIAL_RECORDED","LE30":"THIRTY_DAY_NOTICE_ACCEPTANCE_RECORDED","APRL":"RECLASSIFICATION_AFTER_APPROVAL_RECORDED","APWD":"WITHDRAWAL_AFTER_APPROVAL_RECORDED","GT30":"NO_DECISION_WITHIN_30_DAYS_RECORDED","APCV":"CONVERSION_AFTER_APPROVAL_RECORDED"};by={};non_h=unresolved=raw=0;totals=[];seq=True;prev_skip=prev_limit=None
    for i,p in enumerate(pages):
        m=p["meta"]["results"];totals.append(m["total"]);skip,limit=m["skip"],m["limit"]
        if i==0 and skip!=0:seq=False
        if prev_skip is not None and skip!=prev_skip+prev_limit:seq=False
        prev_skip,prev_limit=skip,limit;raw+=len(p["results"])
        for r in p["results"]:
            h=str(r.get("pma_number") or "").upper()
            if not h:unresolved+=1;continue
            if not h.startswith("H"):non_h+=1;continue
            supp=str(r.get("supplement_number") or "ORIGINAL").upper();identity=f"HDE:{h}:{supp}";code=str(r.get("decision_code") or "").upper();sem=decision_map.get(code,"UNRESOLVED_DECISION_CODE")
            n={"record_kind":"NORMALIZED_OPENFDA_HDE_DECISION","hde_number":h,"supplement_number":supp,"record_identity":identity,"record_role":"ORIGINAL_APPLICATION" if supp=="ORIGINAL" else "SUPPLEMENT","trade_name":r.get("trade_name"),"generic_name":r.get("generic_name"),"applicant":r.get("applicant"),"date_received":r.get("date_received"),"decision_date":r.get("decision_date"),"decision_code":code or None,"decision_semantics":sem,"decision_code_recognized":code in decision_map,"decision_supports_hde_approval":code=="APPR","decision_supports_reasonable_assurance_of_effectiveness":False,"decision_establishes_facility_irb_approval":False,"product_code":r.get("product_code"),"supplement_type":r.get("supplement_type"),"supplement_reason":r.get("supplement_reason"),"ao_statement":r.get("ao_statement"),"query_memberships":[query_id],"boundary":"fixture"};core=dict(n);core.pop("query_memberships");n["normalized_record_sha256"]=replay._digest(core)
            prior=by.get(identity)
            if prior and prior["normalized_record_sha256"]!=n["normalized_record_sha256"]:raise ValueError(f"Conflicting normalized HDE representations for {identity}")
            by[identity]=n
    reported=totals[0] if totals and len(set(totals))==1 else None;over=reported is not None and reported>26000;accounted=len(by)+non_h+unresolved;state="DENOMINATOR_UNAVAILABLE" if reported is None else "OVER_LIMIT_SEARCH_AFTER_OR_PARTITION_REQUIRED" if over else "INVALID_SEQUENCE" if not seq else "MATCH" if accounted==reported else "PARTIAL_OR_MISMATCH"
    records=[];norms=[];dups=[]
    if not over:
        for identity in sorted(by):
            n=by[identity];dup=known_record_sources.get(identity);r={"record_key":identity,"title":n.get("trade_name") or identity,"url":"https://api.fda.gov/device/pma.json","publisher":"U.S. FDA","source_class":"OFFICIAL_REGULATORY_HDE_RECORD","suggested_source_id":"SRC-"+identity.replace(":","-"),"classification_hint":"DUPLICATE" if dup else "NEW","decision_semantics":n["decision_semantics"]}
            if dup:r["duplicate_of_source_id"]=dup;dups.append({"record_identity":identity,"source_id":dup})
            records.append(r);norms.append(n)
    cov={"supplied_page_count":len(pages),"returned_record_count":raw,"unique_composite_record_count":len(by),"reported_total_count":reported,"reported_total_count_state":"CONSISTENT" if reported is not None else "INCONSISTENT_ACROSS_PAGES","skip_sequence_valid":seq,"skip_coverage_state":state,"over_26000_limit":over,"search_after_or_partition_required":over,"out_of_scope_non_h_prefix_count":non_h,"known_controlled_duplicate_count":len(dups),"new_candidate_count":len(records)-len(dups),"duplicate_representation_count":0,"unresolved_hde_number_count":unresolved,"decision_semantics_derived_only_from_exact_decision_code":True,"hde_approval_is_reasonable_assurance_effectiveness_claim":False,"hde_approval_establishes_facility_irb_approval":False}
    return {"result_records":records,"normalized_records":norms,"coverage":cov}

class HdeReplayTests(unittest.TestCase):
    def bundle(self,rows_by_query,scope="PARTIAL_VALIDATION",partition=False):
        p=replay._programme();captures=[]
        for r in p["query_streams"]:
            if r["query_id"] not in rows_by_query:continue
            part=[];search=r["search"]
            if partition:part=[{"field":"decision_date","lower":"20260101","upper":"20261231"}];search=f'({search})+AND+decision_date:[20260101+TO+20261231]'
            captures.append({"query_id":r["query_id"],"leaf_query_id":r["query_id"]+"-leaf","effective_search":search,"partition_path":part,"pages":[page(rows_by_query[r["query_id"]])]})
        return {"schema_version":"0.1.0","programme_id":p["programme_id"],"provider":p["provider_contract"]["provider"],"capture_scope":scope,"captured_at":"2026-09-01T00:00:00Z","leaf_query_captures":captures}
    def known(self,values=None):return {"materialized_source_count":248,"known_composite_hde_record_count":len(values or {}),"record_to_source":values or {}}
    def test_real_namespace_materializes_248(self):self.assertEqual(replay.build_known_record_source_index()["materialized_source_count"],248)
    def test_bare_hde_locator_does_not_guess_original(self):
        self.assertEqual(replay._composite_from_locator("https://api.fda.gov/device/pma.json?search=pma_number:H123456"),set());self.assertEqual(replay._composite_from_locator("https://example.org/hde/H123456?record_role=original"),{"HDE:H123456:ORIGINAL"})
    def test_original_and_supplement_remain_distinct(self):
        q=replay._programme()["query_streams"][0]["query_id"];r=replay.build_replay(self.bundle({q:[rec(),rec(supp="S001")]}),projector=fake_projector,known_index=self.known());self.assertEqual({x["record_identity"] for x in r["normalized_records"]},{"HDE:H123456:ORIGINAL","HDE:H123456:S001"})
    def test_exact_duplicate_only(self):
        q=replay._programme()["query_streams"][0]["query_id"];r=replay.build_replay(self.bundle({q:[rec(),rec(supp="S001")]}),projector=fake_projector,known_index=self.known({"HDE:H123456:S001":"SRC-KNOWN"}));self.assertEqual(r["reconciliation"]["known_controlled_duplicate_count"],1)
    def test_partition_does_not_imply_completion(self):
        rows={x["query_id"]:[rec(h=f"H{i+100000}")] for i,x in enumerate(replay._programme()["query_streams"])};r=replay.build_replay(self.bundle(rows,"FULL_PROGRAMME",True),projector=fake_projector,known_index=self.known());self.assertTrue(r["reconciliation"]["partition_reconciliation_required"]);self.assertFalse(r["reconciliation"]["mechanically_complete"])
    def test_full_clean_can_be_mechanically_complete_but_noncanonical(self):
        rows={x["query_id"]:[rec(h=f"H{i+200000}")] for i,x in enumerate(replay._programme()["query_streams"])};r=replay.build_replay(self.bundle(rows,"FULL_PROGRAMME"),projector=fake_projector,known_index=self.known());self.assertTrue(r["reconciliation"]["mechanically_complete"]);self.assertFalse(r["reconciliation"]["canonical_successor_ready"]);self.assertFalse(r["reconciliation"]["hde_approval_is_reasonable_assurance_effectiveness_claim"]);self.assertFalse(r["reconciliation"]["hde_approval_establishes_facility_irb_approval"])
    def test_non_h_and_unknown_decision_do_not_escalate(self):
        q=replay._programme()["query_streams"][0]["query_id"];r=replay.build_replay(self.bundle({q:[rec(h="P123456"),rec(decision="XXXX")]}),projector=fake_projector,known_index=self.known());self.assertEqual(r["reconciliation"]["out_of_scope_non_h_prefix_count"],1);self.assertEqual(r["normalized_records"][0]["decision_semantics"],"UNRESOLVED_DECISION_CODE");self.assertFalse(r["normalized_records"][0]["decision_supports_hde_approval"])
    def test_cross_query_conflict_fails_closed(self):
        p=replay._programme();q1,q2=p["query_streams"][0]["query_id"],p["query_streams"][1]["query_id"]
        with self.assertRaisesRegex(ValueError,"Cross-query conflict"):replay.build_replay(self.bundle({q1:[rec(trade="A")],q2:[rec(trade="B")]}),projector=fake_projector,known_index=self.known())
    def test_deterministic_output_no_raw_pages(self):
        q=replay._programme()["query_streams"][0]["query_id"];r=replay.build_replay(self.bundle({q:[rec()]}),projector=fake_projector,known_index=self.known())
        with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
            self.assertEqual(replay.write_projection(r,Path(a)),replay.write_projection(r,Path(b)));m=json.loads((Path(a)/"manifest.json").read_text());self.assertFalse(m["raw_openfda_pages_emitted"]);self.assertFalse(m["canonical_successor_ready"])
if __name__=="__main__":unittest.main()
