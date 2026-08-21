# Codex-native `watch` skill

**Classification: implementation requirement. Evidence:** the normative [watch specification](docs/spec/watch-skill.md), the canonical skill source, and hermetic implementation tests. This describes specified and implemented behavior; it is not a claim of live Desktop, source-host, provider, approval, or cleanup verification.

`watch` prepares evidence for exactly one public, unauthenticated
yt-dlp-compatible HTTP(S) URL or one lawful local video. It is a
repository-owned Codex Desktop skill; it is not a general-purpose downloader or
export tool, editor, installer, credential manager, provider client, or media
library. Transcription is release-disabled in the current action surface.

## Claim classification

Every material user-facing or release claim in this repository is labeled:

- `confirmed` — named recorded evidence exists, limited to that evidence's scope.
- `implementation requirement` — specified or implemented, but not qualifyingly live-verified.
- `unsupported/out of scope` — intentionally excluded behavior.

Static analysis, hermetic tests, mocks, documentation review, and a closed issue never prove a live Desktop discovery, personal installation, source-host request, sandbox approval, provider behavior/retention, or cleanup outcome.

## Supported scope

**Classification: implementation requirement. Evidence:** specification [sections 2–5](docs/spec/watch-skill.md#2-scope-and-explicit-non-goals) and hermetic evidence in `tests/test_prepare_metadata.py` and `tests/test_answer_layer.py`.

- A Watch request has exactly one public, unauthenticated yt-dlp-compatible
  HTTP(S) URL or one lawful local video. Private, authenticated, DRM-protected,
  live, playlist, ambiguous, and multiple sources are `unsupported/out of scope`.
- Captions-first preparation keeps metadata, transcript, and visual evidence separate, with distinct coverage and citations.
- A supported public yt-dlp-compatible HTTP(S) URL needs source-host
  command-network approval before `yt-dlp` can contact its named host. Optional
  transcription is release-disabled; a future provider would need separately
  selected provider, audio track, fresh audio-upload consent, provider-network
  approval, and the effective complete-request-size gate. Source-host and
  provider-network approvals are separate.
- When `yt-dlp` returns a selected native-caption URL, the current runtime can
  retrieve that public HTTPS caption resource only through a separate,
  explicit, receipt-gated caption-network action. The approval exposes the
  hostname, purpose, selected track, format, and byte cap—not a signed URL or
  query string—and it expires or is consumed fail closed. Direct-caption
  transport is a sealed Python `urllib.request` HTTPS path with no ambient
  proxy, redirect, cookie, or authentication configuration. Direct-caption
  retrieval remains release-disabled until hermetic coverage and one separately
  approved live public-caption run produce adequate sanitized evidence. See the
  [security and privacy contract](docs/security-and-privacy.md#direct-native-caption-networking)
  for the network and redaction boundary.
- No global media library, cross-task evidence cache, automatic reacquisition, automatic deletion, telemetry, analytics, or crash upload is part of v0.1.

## Canonical source and discovery

**Classification: implementation requirement. Evidence:** specification [section 3](docs/spec/watch-skill.md#3-host-authority-discovery-and-canonical-terminology) and `tests/test_skill_package_contract.py`.

The canonical skill source is [`$REPO_ROOT/.agents/skills/watch`](.agents/skills/watch/SKILL.md). `SKILL.md` is the discovery file. Its optional `agents/openai.yaml` contains only visible display metadata, the `$watch` default prompt, and the narrow implicit-invocation policy.

Use `$watch` explicitly. Implicit matching is limited to a clear request to inspect, analyze, summarize, or answer a question from exactly one supplied video or the Current source. Mentioning video, editing, downloading, coding, zero/multiple/ambiguous sources, or private/authenticated/live/playlists are not implicit routes.

## Request examples

**Classification: confirmed. Evidence:** these are static syntax examples only; they perform no source or provider request.

These are request syntax examples only; this documentation does not contact either source.

```text
$watch https://video.example/watch?v=one What is the speaker's conclusion?
$watch "/path/to/local video.mp4" Give a timestamped summary.
```

## Manual personal installation

**Classification: implementation requirement. Evidence:** specification [section 11](docs/spec/watch-skill.md#11-packaging-manual-installation-and-updates) and `tests/test_skill_package_contract.py::CanonicalSkillPackageTests.test_documented_manual_installation_is_fail_closed_and_truthful`.

The only personal-installation route is the manual symlink:

```text
$HOME/.agents/skills/watch -> $REPO_ROOT/.agents/skills/watch
```

It is a human-controlled outside-workspace action. The skill, its runtime, tests, and repository tooling never create, copy, update, repair, or remove a personal skill target. See [setup and troubleshooting](docs/setup-and-troubleshooting.md) before considering that action.

Read the [security and privacy contract](docs/security-and-privacy.md) before
using a source URL, approving the separate native-caption action, considering
future transcription, or requesting cleanup.

## Documentation and known limits

**Classification: confirmed. Evidence:** the accepted [Issue #9 resolution](https://github.com/prossima-ai/codex-watch-yt-video/issues/9#issuecomment-5249321562) and [specification section 2.2](docs/spec/watch-skill.md#22-out-of-scope).

v0.1 is macOS Codex Desktop only, private, and unlicensed for redistribution. Public distribution, marketplace publication, and Linux/Windows release parity are `unsupported/out of scope` pending a separate public-release decision.

- [Setup and troubleshooting](docs/setup-and-troubleshooting.md) covers the manual personal-symlink refusal rules, preflight, approvals, failure states, and live-check boundaries.
- [Security and privacy](docs/security-and-privacy.md) covers source contact, local processing, provider consent, credential handling, telemetry, retention, outcomes, and cleanup.
- [Third-party notices](THIRD_PARTY_NOTICES.md) records actually used external tools/services and their license or service-terms boundary.
- [Provenance](docs/provenance.md) records the inspected implementation base, parity snapshot, evidence, intentional deviations, and remaining release gates.

## Verification boundary

**Classification: confirmed. Evidence:** PR #43 / Issue #28’s merged record and the package-contract tests. No live Desktop probe, personal installation, media acquisition, or provider request was performed for #28.

The repository includes hermetic package-contract tests for paths, metadata, routing policy, symlink integrity, and refusal behavior. Static package evidence does not prove live Desktop discovery, an already-open task's inventory refresh, a personal installation, sandbox approvals, media acquisition, provider behavior, provider retention, or live cleanup. No live media or provider request is part of package discovery validation.

## Direct-caption and transcription release gates

**Classification: implementation requirement. Evidence:** Decision #44,
[the normative specification](docs/spec/watch-skill.md#direct-native-caption-retrieval),
and hermetic tests. No live caption, provider, or release activity was performed
for this implementation work.

Direct native-caption retrieval accepts only a public HTTPS endpoint after a
separate opaque, single-use, five-minute approval receipt that is bound to the
same Watch request, source, session, workspace, selected track, format, byte cap,
and normalized origin. Invalid, expired, denied, canceled, replayed, or
mismatched receipts make no caption HTTP attempt. Redirects, DNS answers, byte
limits, and user-visible redaction are fail closed; direct-caption failures do
not fall back to transcription.

Transcription and all provider contact remain release-disabled. A future selected
provider needs a conservative provider-specific effective upload limit for the
complete encoded request—not merely nominal media-file size—including
multipart/form-data boundaries, per-part headers, metadata, and every other
request-body overhead, followed by a separate validation plan and separate
explicit human approval. A human release decision, if one is later made, does
not authorize provider enablement or a live request.

Mistral's `voxtral-mini-2602` Provider route is development/test-only and
release-disabled, not a current end-user feature. Its remaining entitlement,
route-specific ZDR, forward-test, live-provider-evidence, disclosure, and human
release-decision gates are recorded in the [provider-route ADR](docs/adr/0001-provider-neutral-transcription-route.md).
