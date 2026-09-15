# ClinicalTrials.gov first-capture boundary

Status: **NONCANONICAL DESIGN NOTE**

A reviewed CT.gov monitoring recommendation and draft onboarding plan do not authorize or constitute a monitor-registry entry. The next permitted transition is a separately authorized first controlled capture into Workbench quarantine.

Required sequence:

1. Bind an explicit first-capture authorization to one onboarding manifest and one draft monitor plan.
2. Materialize a Workbench collection request from the plan's **PRIMARY** `/api/v2/studies/{NCT}` route only.
3. Supply execution-time fields (`requested_at`, registry/configuration digests, collector version and collector boundary) at execution time; do not predate or synthesize them in the onboarding plan.
4. Execute through the hardened Workbench collector into S3/ephemeral quarantine. Raw bytes do not enter S2.
5. Require HTTP-success semantics and exact JSON `NCTId` identity matching the plan's NCT identity. Redirect or response content must not silently change registry identity.
6. Treat the resulting evidence state as `RETRIEVED_BYTES_NOT_SUBSTANTIVELY_ADJUDICATED`.
7. Do not create a monitor-registry successor from retrieval alone.
8. Require a separate human quarantine disposition. Only `APPROVED_FOR_HANDOFF` may advance toward monitoring handoff.
9. Monitoring handoff proves byte custody/integrity and exact source/monitor binding; it does not establish clinical truth or canonical publication authority.
10. Only after approved handoff may a separate draft monitor-registry successor be proposed.

The fallback `query.id` API route is identity-equivalent route resilience. The public `/study/{NCT}` HTML route is liveness corroboration only and must not serve as the first structured capture when the primary API route is available.

No operation in this boundary creates a Trial entity, trial-site relationship, assessment mutation, canonical Source release, institutional endorsement, or global completeness claim.
