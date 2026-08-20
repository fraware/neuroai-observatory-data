from __future__ import annotations
import json, math
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

ROOT=Path(__file__).parents[1]
SCHEMAS=ROOT/"schemas"/"vnext"
REGISTRY=ROOT/"source-universes"/"p0-registry-v0.1.json"

def load_registry_records(registry):
    records=[]
    for fragment in registry["fragments"]:
        path=ROOT/fragment["path"]
        if not path.is_file():
            raise ValueError(f"missing registry fragment: {fragment['path']}")
        payload=json.loads(path.read_text())
        if len(payload.get("records",[]))!=fragment["record_count"]:
            raise ValueError(f"fragment record_count mismatch: {fragment['path']}")
        actual_domains=sorted({r["domain"] for r in payload["records"]})
        if actual_domains!=sorted(fragment["domains"]):
            raise ValueError(f"fragment domain declaration mismatch: {fragment['path']}")
        records.extend(payload["records"])
    return records

def _load(name):
    return json.loads((SCHEMAS/name).read_text())

SU_VALIDATOR=Draft202012Validator(_load("source-universe.schema.json"), format_checker=FormatChecker())
COV_VALIDATOR=Draft202012Validator(_load("coverage-report.schema.json"), format_checker=FormatChecker())

def _structural(validator,obj,label):
    errors=sorted(validator.iter_errors(obj), key=lambda e:list(e.path))
    if errors:
        e=errors[0]
        path=".".join(map(str,e.path)) or "<root>"
        raise ValueError(f"{label}:{path}: {e.message}")

def validate_universe(obj):
    _structural(SU_VALIDATOR,obj,obj.get("universe_id","SOURCE_UNIVERSE"))
    closure=obj["closure"]
    if closure["closure_type"]=="OPEN_WORLD_DISCOVERY" and closure["allowed_completeness_claim"]!="COVERAGE_ONLY_NO_COMPLETENESS":
        raise ValueError("open-world source universe cannot claim completeness")
    if closure["denominator_method"]=="NO_GLOBAL_DENOMINATOR" and closure["allowed_completeness_claim"]!="COVERAGE_ONLY_NO_COMPLETENESS":
        raise ValueError("no-global-denominator universe cannot claim completeness")
    if obj["planning_state"]=="DEFERRED" and obj["priority"]=="P0":
        raise ValueError("P0 source universe cannot be DEFERRED")
    if obj["interface"]["authentication_class"]=="LICENSE_REQUIRED" and obj["rights"]["access_rights_class"]!="LICENSED_RESTRICTED":
        raise ValueError("licensed authentication must bind licensed-restricted access")
    if obj["rights"]["redistribution_rights_class"]=="NO_REDISSEMINATION" and obj["rights"]["raw_bytes_publication"]=="PERMITTED":
        raise ValueError("no-redistribution universe cannot permit raw publication")
    if obj["planning_state"]=="VERIFIED_INTERFACE":
        if obj["interface"]["base_url"] is None:
            raise ValueError("verified interface requires base_url")
        if obj["interface"]["authentication_class"]=="UNKNOWN_PENDING_VERIFICATION":
            raise ValueError("verified interface cannot retain unknown authentication")
        if obj["rights"]["access_rights_class"]=="UNKNOWN_PENDING_REVIEW" or obj["rights"]["redistribution_rights_class"]=="UNKNOWN_PENDING_REVIEW":
            raise ValueError("verified interface cannot retain unknown rights")
        if obj["update_semantics"]["cadence_state"]=="UNKNOWN_PENDING_VERIFICATION":
            raise ValueError("verified interface cannot retain unknown cadence")
    return True

def validate_registry(registry):
    if registry.get("status")!="PLANNING_CONTROL_METADATA_NOT_CANONICAL_PRODUCTION_DATA":
        raise ValueError("registry authority state must remain planning-only")
    records=load_registry_records(registry)
    seen=set()
    for obj in records:
        validate_universe(obj)
        uid=obj["universe_id"]
        if uid in seen:
            raise ValueError(f"duplicate universe_id: {uid}")
        seen.add(uid)
    required=set(registry["required_p0_domains"])
    present={r["domain"] for r in records if r["priority"]=="P0"}
    missing=required-present
    if missing:
        raise ValueError(f"missing P0 domains: {sorted(missing)}")
    return True

def _expected_rates(c):
    eligible=c["denominator"]["eligible"]
    if eligible==0:
        return {k:None for k in ("discovery","resolution","sourcing","temporal_verification","linkage")}
    s=c["states"]
    return {
        "discovery":s["discovered"]/eligible,
        "resolution":s["resolved"]/eligible,
        "sourcing":s["sourced"]/eligible,
        "temporal_verification":s["temporally_verified"]/eligible,
        "linkage":s["linked"]/eligible,
    }

def validate_coverage(c,universe=None):
    _structural(COV_VALIDATOR,c,c.get("coverage_id","COVERAGE_REPORT"))
    s=c["states"]; eligible=c["denominator"]["eligible"]
    if s["excluded"]>s["discovered"]:
        raise ValueError("excluded exceeds discovered")
    for key in ("resolved","sourced","temporally_verified","linked","stale","conflicted","inaccessible"):
        if s[key]>s["discovered"]:
            raise ValueError(f"{key} exceeds discovered")
    if eligible and s["discovered"]>eligible:
        raise ValueError("discovered exceeds eligible denominator")
    for key,expected in _expected_rates(c).items():
        actual=c["rates"][key]
        if expected is None:
            if actual is not None:
                raise ValueError(f"{key} rate must be null for zero denominator")
        elif actual is None or not math.isclose(actual,expected,rel_tol=0,abs_tol=1e-12):
            raise ValueError(f"{key} rate does not reconcile")
    if sum(row["count"] for row in c["exclusions"])!=s["excluded"]:
        raise ValueError("exclusion detail does not reconcile")
    if universe:
        if c["universe_id"]!=universe["universe_id"]:
            raise ValueError("coverage universe mismatch")
        if c["denominator"]["method"]!=universe["closure"]["denominator_method"]:
            raise ValueError("coverage denominator method mismatches universe contract")
    return True

def main():
    registry=json.loads(REGISTRY.read_text())
    validate_registry(registry)
    print(f"PASS source-universe registry: {len(load_registry_records(registry))} universes")

if __name__=="__main__":
    main()
