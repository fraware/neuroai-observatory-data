# G1/G2 Authority Boundaries (Human Interpretation)

This repository contains *fail-closed* governance artifacts that prepare human review, without granting authority by themselves.

## Human G1 disposition packet

`curation/HUMAN_G1_DISPOSITION_PACKET_OBSERVATORY_RECOVERY_2026-09-03_v0.1.json` references the exact D1 and D2 identities/digests introduced in this recovery:

- D1: `curation/LANDSCAPE_RESEARCH_CONTRACT_v0.1.json`
- D2: `curation/CAPABILITY_CONTEXT_TAXONOMY_v0.1.json` (including its `d1_contract_binding`)

Interpretation rule: the packet keeps `g1_approved=false` until an attributable human governance disposition is recorded elsewhere with a binding to the exact D1/D2 identity/digest values referenced by the packet.

This packet is *not* an approval record. It contains no private/protected evidence.

## Public PRE-G2 S2 bindings (bound)

`curation/PUBLIC_PRE_G2_S2_BINDINGS_OBSERVATORY_RECOVERY_2026-09-03_BOUND_v0.1.json` records the Workbench-confirmed public PRE-G2 lineage bindables (software-binding SHA `336da167…`) while keeping `g2_passed=false`, `canonical_s2_authority=false`, and `publication_authority=false`. The G0 transport pin remains `685f1597…` and is recorded separately from the software binding.

The UNKNOWN template below remains historical and immutable.

## Public PRE-G2 S2 bindings (bound)

`curation/PUBLIC_PRE_G2_S2_BINDINGS_OBSERVATORY_RECOVERY_2026-09-03_BOUND_v0.1.json` records the Workbench-confirmed public PRE-G2 lineage bindables (software-binding SHA `336da167…`) while keeping `g2_passed=false`, `canonical_s2_authority=false`, and `publication_authority=false`. The G0 transport pin remains `685f1597…` and is recorded separately from the software binding.

The UNKNOWN template below remains historical and immutable.

## Public PRE-G2 S2 bindings template

`curation/PUBLIC_PRE_G2_S2_BINDINGS_TEMPLATE_OBSERVATORY_RECOVERY_2026-09-03_v0.1.json` is a public checklist template used to prepare PRE-G2 S2 schema/provenance placeholders.

Interpretation rule: treat any `"UNKNOWN"` fields as unresolved. Do not guess workbench lineage, commits, run IDs, or candidate descriptors. Replace UNKNOWN placeholders only after externally verified public governance/provenance material is recorded (see the bound artifact above).

The template must not be used to:

- authorize operator actions,
- authorize publication,
- synthesize G1/G2 approvals,
- or include held-out test labels, secret membership, HMAC/commitment secrets, private adjudicator packets, licensed commercial materials, or proprietary raw captures.

## Boundary intent

These artifacts exist to keep authority boundaries technically coherent while humans perform governance. They cannot be used as evidence of substantive scientific, clinical, regulatory, or institutional truth.

