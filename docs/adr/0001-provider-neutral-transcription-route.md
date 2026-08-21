# ADR-0001: Provider-neutral transcription route and Mistral release posture

## Status

Accepted — Issue #56. This is an `implementation requirement`, not evidence of
a live Provider request, release authorization, or current end-user availability.

## Context

The repository has a provider-neutral batch-transcription boundary and an
isolated Mistral `voxtral-mini-2602` adapter route. Those implementation facts
must not be mistaken for an enabled release feature. Documentation needs terms
that separate a Provider route from Provider eligibility and Provider support
state, and it needs a single truthful account of what may be persisted after a
future provider activity.

## Decision

- A **Provider route** is an immutable provider/model/destination/credential and
  complete-request-limit description. It neither selects the Provider nor grants
  consent, approval, entitlement, or availability.
- **Provider eligibility** is determined per future activity only after all
  required selection, Audio-upload consent, Provider-network approval,
  disclosure, size, and support-state gates are satisfied.
- **Provider support state** is recorded separately. Mistral is
  `development/test-only` and `release-disabled`; it has no current end-user
  availability.
- The only provider-facing batch input is a **Prepared audio chunk**: bounded,
  locally prepared audio bytes for the selected track, with no source or
  workspace path and no authority to retry, select, consent, or approve.
- A **Provider-derived transcript** is normalized runtime evidence, not a raw
  provider response. Safe persisted provenance contains only the identity and
  coverage information required to label that evidence truthfully; it excludes
  raw requests, raw responses, credentials, headers, IDs, and audio paths.

Mistral may not be considered for a release until all of these future gates are
independently satisfied for the selected route: verified entitlement,
route-specific ZDR and current disclosure, a forward-test, separately approved
live-provider evidence, and a human release decision for a defined scope. These
are requirements to prove in the future, not data-residency, retention, price,
availability, or live-service claims.

## Consequences

No release-facing action exposes Mistral or any other Provider route today.
Adapter presence, a `MISTRAL_API_KEY`, hermetic tests, this ADR, or a human
release decision for another scope cannot bypass the gates above. Missing evidence
is `BLOCKED`, never an implied Provider eligibility or release approval.
