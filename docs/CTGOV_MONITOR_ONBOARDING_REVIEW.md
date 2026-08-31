# CT.gov monitor onboarding review

Status: **NONCANONICAL OPERATIONAL DESIGN**

This slice converts an explicit human review of a `PENDING_MONITOR_REVIEW` recommendation into a non-executable onboarding plan. Approval authorizes only preparation of a draft monitor identity, route-resilience definitions and a first-capture request template.

Approval does not authorize network execution, quarantine approval, monitor-registry succession, Source publication, Trial or site creation, assessment mutation or canonical publication.

Current `OFFICIAL_TRIAL_REGISTRY` recommendations must remain `RECURRING / MONTHLY / HIGH`. If a reviewer disagrees with that policy-derived recommendation, the correct action in this slice is `DEFER` or `REJECT`; recommendation overrides require a later explicit curation mechanism.

For ClinicalTrials.gov, the onboarding route order is:

1. primary structured API: `/api/v2/studies/{NCT}`;
2. identity-equivalent fallback: `/api/v2/studies?query.id={NCT}&pageSize=1&format=json`;
3. public study page `/study/{NCT}` for liveness corroboration only.

The primary structured API is the only initial capture target in this slice. The HTML route cannot substitute for structured registry state merely because it contains the NCT identifier.
