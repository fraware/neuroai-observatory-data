"""Build a deterministic pre-attestation review packet for the Observatory v2 candidate.

The packet binds reviewers to one exact candidate representation. It never records PASS,
BLOCK, authorization or publication; those remain later human/governance operations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_observatory_v2_whole_current_candidate as candidate_builder

TRACKS: dict[str, dict[str, list[str]]] = {
    "SECURITY": {
        "review_questions": [
            "Does the candidate contain only S2-public metadata and exclude protected evidence bytes, credentials, secrets and protected paths?",
            "Do content hashes, capture states and redistribution states avoid implying custody or rights that are not established?",
            "Are deterministic build and manifest mechanics free of a path that could silently import protected S3 material?"
        ],
        "required_evidence": [
            "candidate reconciliation and manifest",
            "S2/S3 evidence-boundary contract",
            "Observation records with protected_bytes_in_record=false"
        ]
    },
    "METHODOLOGY": {
        "review_questions": [
            "Does v2 preserve the methodological meaning and limitations of v1.4/v1.6/v1.7 without inventing precision, source links or promotion semantics?",
            "Are source observations, candidates, accepted changes, reopening decisions and successor lineage correctly separated?",
            "Are effective-state summaries reconstructed only where the underlying records support reconstruction?"
        ],
        "required_evidence": [
            "all slice reconciliations",
            "v1-to-v2 migration specification",
            "effective-state reconciliation",
            "v1.6 semantic-coverage gate"
        ]
    },
    "DATA_GOVERNANCE": {
        "review_questions": [
            "Is every normalized public record traceable to an immutable predecessor payload/digest or explicitly identified successor lineage?",
            "Are public/protected/generated/archive boundaries maintained and redistribution/custody uncertainty preserved?",
            "Are canonical authority and publication kept separate from migration mechanics and review?"
        ],
        "required_evidence": [
            "predecessor payload/digest fields",
            "248-source namespace reconciliation",
            "data-storage boundary documentation",
            "candidate manifest"
        ]
    },
    "ACCESSIBILITY": {
        "review_questions": [
            "Can a qualified external reviewer inspect the candidate, reconciliation and provenance without relying on undocumented repository knowledge?",
            "Are unresolved states, claim boundaries and prohibited inferences legible and distinguishable from failures?",
            "Does the machine-readable structure support later accessible public presentation without making generated views canonical?"
        ],
        "required_evidence": [
            "candidate family files and reconciliation",
            "v2 ontology/temporal model documentation",
            "public-observatory presentation boundary documentation"
        ]
    },
    "DOMAIN": {
        "review_questions": [
            "Do NeuroAI organization, model, registry, clinical-site, participant-authority, dependency, regulatory, capital and governance semantics remain substantively faithful to the predecessor records?",
            "Are company announcements, regulatory procedure, preprints, supplier capability and clinical evidence kept within their evidence-class boundaries?",
            "Does the PRIMA successor preserve the distinction among EU/EEA CE announcement, US HUD pathway, clinical evidence, commercial implantation and CL-4 assessment state?"
        ],
        "required_evidence": [
            "typed entity/assertion/event/relationship records",
            "source/evidence-state and claim-boundary fields",
            "PRIMA successor lineage and prohibited inferences"
        ]
    },
    "AFFECTED_COMMUNITY": {
        "review_questions": [
            "Are participant powers represented narrowly enough to avoid converting consent, registry interest or operational control into governance authority?",
            "Do missing public evidence and no-change findings avoid creating unsupported negative judgments about people, communities or systems?",
            "Are open access, support, continuity, safety and participant-impact conditions preserved where the predecessor records state them?"
        ],
        "required_evidence": [
            "participant-authority relationship records",
            "no-change comparison provenance",
            "PRIMA open conditions and prohibited inferences"
        ]
    }
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(*, execution_verified: bool = False) -> dict[str, Any]:
    result = candidate_builder.build()
    with tempfile.TemporaryDirectory() as td:
        output = Path(td)
        manifest = candidate_builder.write_candidate(result, output)
        manifest_sha = _sha256(output / "manifest.json")
        reconciliation_sha = _sha256(output / "reconciliation.json")

    rec = result["reconciliation"]
    blocking_conditions: list[dict[str, str]] = []
    if not execution_verified:
        blocking_conditions.append({
            "condition_id": "V2-EXECUTION-VERIFICATION",
            "status": "OPEN",
            "release_effect": "BLOCKS_RELEASE",
            "summary": "Whole-candidate execution has not been independently verified in an available execution environment; GitHub Actions runner execution is unresolved."
        })
    if not rec["mechanically_clean"]:
        blocking_conditions.append({
            "condition_id": "V2-MECHANICAL-RECONCILIATION",
            "status": "OPEN",
            "release_effect": "BLOCKS_RELEASE",
            "summary": "Whole-candidate reconciliation contains one or more mechanical blockers."
        })

    tracks = []
    for track in sorted(TRACKS):
        definition = TRACKS[track]
        tracks.append({
            "track": track,
            "state": "PENDING",
            "review_questions": definition["review_questions"],
            "required_evidence": definition["required_evidence"],
            "reviewer": {"name": None, "affiliation": None, "claimed_independence": None},
            "rationale": None,
            "conditions": [],
            "evidence_requests": []
        })

    return {
        "schema_version": "1.0.0-draft",
        "status": "NONCANONICAL_PRE_ATTESTATION_REVIEW_PACKET",
        "candidate_reference": {
            "candidate_id": manifest["candidate_id"],
            "manifest_sha256": manifest_sha,
            "reconciliation_sha256": reconciliation_sha,
            "mechanically_clean": bool(rec["mechanically_clean"])
        },
        "tracks": tracks,
        "blocking_conditions": blocking_conditions,
        "review_identity_boundary": "Reviewer name, affiliation and claimed independence are assertions supplied by reviewers; this packet does not authenticate identity, independence, institutional delegation or authority.",
        "release_authorized": False,
        "authority_boundary": "This packet creates a bounded review scope only. PENDING review fields cannot authorize release. Later reviewer opinions, designated release attestation and publication remain separate operations."
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execution-verified", action="store_true", help="Use only when the exact candidate has actually executed successfully in a trusted execution environment.")
    args = parser.parse_args()
    packet = build(execution_verified=args.execution_verified)
    args.output.write_text(json.dumps(packet, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"tracks": [row["track"] for row in packet["tracks"]], "blocking_conditions": packet["blocking_conditions"], "release_authorized": False}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
