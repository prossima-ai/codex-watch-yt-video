# Security and privacy

This is the public safety and privacy contract for the Codex-native `watch`
skill. It applies to the repository-owned canonical skill source, not to Codex,
installed tools, source sites, or a selected provider acting independently.

## Claim classification

Every material user-facing or release claim in the public documentation uses one
of these labels:

- `confirmed` — a named recorded evidence source exists. Its stated evidence
  boundary still applies.
- `implementation requirement` — specified or implemented behavior that has
  not received qualifying live verification.
- `unsupported/out of scope` — behavior the v0.1 skill does not provide or
  claim to provide.

Static analysis, hermetic tests, mocks, documentation review, and a closed
issue may confirm only their recorded static scope. They never prove live Codex
Desktop discovery, personal installation, source-host acquisition, sandbox
approval behavior, provider behavior or retention, or live cleanup.

## Sources and local processing

**Classification: implementation requirement. Evidence:** specification
[sections 2 and 4](spec/watch-skill.md#2-scope-and-explicit-non-goals) and
hermetic source-validation evidence in
`tests/test_prepare_metadata.py::PrepareMetadataTests.test_multiple_ambiguous_and_credentialed_sources_stop_in_validation`.

The supported request boundary is exactly one public, unauthenticated
yt-dlp-compatible HTTP(S) URL or one lawful local video. Private, authenticated,
DRM-protected, live, playlist, ambiguous, and multiple sources are
`unsupported/out of scope`; the skill does not request a login, inspect cookies,
use a session, or bypass protection.
Diagnostic refusal is not a universal live proof that every protection mechanism
can be recognized.

**Classification: implementation requirement. Evidence:** specification
[sections 3–4](spec/watch-skill.md#3-host-authority-discovery-and-canonical-terminology)
and `tests/test_prepare_metadata.py::PrepareMetadataTests.test_public_url_stops_before_source_contact_without_host_approval`.

For a supported public yt-dlp-compatible HTTP(S) URL, `yt-dlp` may contact the
named source host only after separate command-network approval. Before optional
transcription, it processes metadata, captions, frames, media, and audio locally.
When `yt-dlp` returns a selected native-caption URL, the runtime directly retrieves the selected public HTTP(S) caption resource with Python `urllib` under that
same approved source-network action. That resource can be a distinct public CDN
host; the initial and redirected resource URLs are validated as public HTTP(S).
Native captions and visual evidence remain local by default.
A local file is not uploaded merely because it is selected for analysis.

**Classification: implementation requirement. Evidence:** pinned
`.agents/skills/watch/scripts/watch_evidence.py::UrlCaptionFetcher`, its
`source_network_approved` gate, and
`tests/test_caption_evidence.py::CaptionEvidenceTests.test_caption_retrieval_urls_remain_internal_to_the_runtime`.

The direct caption step means not every source contact goes through `yt-dlp`.
The current runtime uses the same source-network-approval input for that step;
it does not model a separate approval for the selected caption endpoint. This is
hermetic implementation evidence only, not proof that Desktop will present,
scope, or honor an approval in a live task.

### Direct-caption approval discrepancy

**Classification: implementation requirement. Evidence:** the pinned runtime
and approved [specification section 6.3](spec/watch-skill.md#63-preflight-acquisition-and-caption-policy).

The public contract cannot truthfully say that every source contact is through
`yt-dlp` only. Resolving the direct selected-caption retrieval path is a
release/spec gate: before release, an explicit decision must either route caption
retrieval through `yt-dlp` or amend the approved policy and approval disclosure
to name direct selected-caption endpoint retrieval. This documentation ticket
makes no runtime change and provides no live approval or caption-fetch proof.

## Telemetry boundary and independent parties

**Classification: implementation requirement. Evidence:** specification
[sections 2 and 12](spec/watch-skill.md#12-required-companion-documentation-and-provenance)
and the accepted [Issue #9 resolution](https://github.com/prossima-ai/codex-watch-yt-video/issues/9#issuecomment-5249321562).

No skill-controlled telemetry, analytics, or crash uploads are part of v0.1.
This is a statement about this skill only: Codex, installed tools, a source site,
or a selected provider may process data under their own controls and disclosures.
This repository makes no claim that it controls, disables, or audits those
independent systems.

## Optional transcription, consent, and credentials

**Classification: implementation requirement. Evidence:** specification
[section 8](spec/watch-skill.md#8-optional-transcription-consent-secrets-and-retries)
and hermetic tests
`tests/test_provider_transcription.py::ProviderTranscriptionTests.test_selected_audio_track_returns_provider_specific_consent_prompt`
and
`tests/test_provider_transcription.py::ProviderTranscriptionTests.test_source_approval_does_not_replace_provider_network_approval`.

Native captions are preferred. When captions are absent or unusable, the runtime
first returns `decision_required` so the user can choose whether to transcribe
and, if applicable, select a named provider and an audio track. It later returns
`consent_required` before audio extraction. Provider selection, audio-track selection, fresh provider-specific audio-upload consent, and provider-network approval are distinct gates. No choice implies another: source-host approval is not provider-network approval, and an existing credential is neither provider selection nor consent. A declined/canceled consent or denied approval stops before extraction and upload, while preserving only truthful captions/frames evidence where available. Audio can contain sensitive information; read the consent disclosure before accepting it.

No automatic audio upload occurs: extraction and upload require the named provider,
selected track, fresh consent, and separate provider-network approval for that
same Watch request.

**Classification: implementation requirement. Evidence:** specification
[section 8.3](spec/watch-skill.md#83-upload-form-chunking-and-retries) and
`tests/test_provider_transcription.py::ProviderTranscriptionTests.test_fresh_consent_uploads_only_selected_bounded_audio_to_selected_provider`.

Only bounded extracted audio chunks may be uploaded to the selected provider.
The adapter receives audio bytes for the selected track only; it never receives
video bytes, video paths, workspace paths, unrelated tracks, or another
provider's state. The runtime must not silently fall back to another provider.
Partial provider results remain partial and name missing intervals rather than
being represented as a complete transcript.

**Classification: implementation requirement. Evidence:** specification
[sections 8.1–8.2](spec/watch-skill.md#81-provider-selection-and-credentials) and
`tests/test_provider_transcription.py::ProviderTranscriptionTests.test_selected_adapter_reads_only_its_credential_at_provider_call_time`.

The only named environment credentials are `OPENAI_API_KEY` and `GROQ_API_KEY`;
the selected adapter reads only its own value at provider-call time. The skill
must never request secrets in chat, accept a secret as a control, scan `.env`,
persist or log a credential, include one in a report, filename, URL, or command
argument, probe an unselected provider, or silently fall back after a provider
failure. No credential is read to decide which provider to present.

## Truthful outcomes and retained evidence

**Classification: implementation requirement. Evidence:** specification
[sections 5 and 9](spec/watch-skill.md#9-failures-cancellation-and-truthful-outcomes)
and hermetic answer evidence in
`tests/test_answer_layer.py::WatchAnswerLayerTests.test_cancellation_with_retained_evidence_suppresses_the_answer_plan`.

`decision_required` and `consent_required` are nonterminal: they describe a
specific user choice still needed and do not silently select or upload anything.
`stopped`, `failed`, and `canceled` are terminal; their reports distinguish
validation, permission, acquisition, provider, and cancellation stages where
applicable. A truthful partial result can retain named usable evidence while
reporting the unavailable ranges, per-stream coverage, answerability, warnings,
and disposal state. It is never represented as a complete transcript, unseen
frame, or completed cleanup.

**Classification: implementation requirement. Evidence:** specification
[section 10.1](spec/watch-skill.md#101-workspace-invariants) and
`tests/test_prepare_metadata.py::PrepareMetadataTests.test_session_reuses_an_opaque_handle_then_allows_explicit_cleanup`.

Evidence reuse is same-task-only evidence reuse through an opaque handle, not a
raw workspace path. There is no global media library or cross-task evidence
cache. A follow-up must not silently acquire another source, re-extract evidence,
or upload audio; it requires a new explicit preparation and the applicable
approval/consent. There is no automatic source reacquisition or automatic deletion.

## Explicit cleanup only

**Classification: implementation requirement. Evidence:** specification
[section 10.2](spec/watch-skill.md#102-explicit-cleanup-only) and hermetic
workspace-lifecycle tests. Those tests do not prove live cleanup on a user
machine.

Explicit, validated, fail-closed cleanup only is supported. Cleanup requires an
explicit `cleanup current` or `cleanup <workspace-id>` request; it validates the
runtime-owned workspace identity, manifest, ownership, path shape, artifacts,
and lock before deletion. It never targets a supplied source, output directory,
configuration, sibling workspace, or arbitrary path.

| State | Meaning and disposal boundary |
| --- | --- |
| `cleanup_deferred` | A lock prevents cleanup now; nothing is deleted and any already-eligible same-task reuse remains eligible. |
| `cleanup_refused` | Validation, integrity, ownership, or path safety failed; nothing is deleted and reuse is revoked. |
| `cleanup_incomplete` | Safe deletion is unavailable after validation; nothing further is claimed deleted and reuse is revoked. |
| `cleanup_succeeded` | The validated owned artifacts were removed under the runtime protocol; this does not assert removal of arbitrary user files. |
| `cleanup_already_absent` | A previously known workspace is already absent; the result does not claim a new deletion. |

On macOS, if identity-bound safe leaf deletion is unavailable, `cleanup_incomplete`
preserves the workspace rather than risking deletion. The runtime must not replace
that fail-closed result with a best-effort recursive or name-based delete, and a
later cleanup attempt requires another explicit request.

## Provider disclosures and release gate

**Classification: confirmed. Evidence:** first-party provider documentation
inspection on 2026-08-14. Provider documentation checked: 2026-08-14. This is a
date-bound documentation observation, not a live transcription request,
credential use, account-entitlement check, source-host request, or proof of
provider behavior or retention.

### OpenAI

**Classification: confirmed. Evidence:** [OpenAI `whisper-1` model page](https://developers.openai.com/api/docs/models/whisper-1), [speech-to-text guide](https://developers.openai.com/api/docs/guides/speech-to-text), and [endpoint data-controls table](https://developers.openai.com/api/docs/guides/your-data#default-usage-policies-by-endpoint), checked 2026-08-14.

The published documentation lists OpenAI `whisper-1` for
`/v1/audio/transcriptions`, including `verbose_json` and timestamp granularities.
Its endpoint table publishes no training, no abuse-monitoring retention, no
application-state retention, and ZDR-eligibility for that endpoint on the check
date. This is provider-published policy information, not a live request result, or an account guarantee. It is not a blanket claim about OpenAI, ChatGPT, or other endpoints.

### Groq

**Classification: confirmed. Evidence:** [Groq speech-to-text guide](https://console.groq.com/docs/speech-to-text), [Groq `whisper-large-v3` model page](https://console.groq.com/docs/model/whisper-large-v3), and [Groq Your Data](https://console.groq.com/docs/your-data), checked 2026-08-14.

The published documentation lists Groq `whisper-large-v3` for the
OpenAI-compatible `/openai/v1/audio/transcriptions` endpoint, with `verbose_json`
and timestamps. It says inference customer data is not retained by default, but
temporary reliability/abuse logs up to 30 days can be retained unless ZDR and
usage metadata is always collected. The skill therefore does not claim that Groq
never retains data. This is a dated provider disclosure, not a live request or
account-specific retention guarantee.

### Current size-limit discrepancy

**Classification: implementation requirement. Evidence:** pinned adapter
configuration in `.agents/skills/watch/scripts/watch_transcription.py`, the
official provider pages above, and [specification section 8.3](spec/watch-skill.md#83-upload-form-chunking-and-retries).

The current adapter ceiling is 25,165,823 bytes (`24 * 1024 * 1024 - 1`) before
multipart overhead. The current public documentation reports 25 MB for OpenAI and
25 MB for the Groq free tier; a 25,000,000-byte limit is below the configured
ceiling, and the implementation does not discover a provider account tier or
effective limit. Therefore this documentation does not claim either provider is
live-ready or that every accepted upload fits a current account limit. If a release
cannot verify and honor a provider's required disclosure and effective limit,
disable that provider for release; retain captions and visual evidence where
available. This is a release gate, not a runtime change made by this ticket.

## Security reporting boundary

**Classification: unsupported/out of scope. Evidence:** accepted [Issue #9
resolution](https://github.com/prossima-ai/codex-watch-yt-video/issues/9#issuecomment-5249321562).

v0.1 makes no public security-response promise. A designated private reporting channel is required before public distribution; this private, unlicensed v0.1 record does not establish one.

## Related records

**Classification: confirmed. Evidence:** the current Issue #29 worktree/diff
inspected on 2026-08-14; this statement does not claim those files existed at the
pinned implementation base.

See [third-party notices](../THIRD_PARTY_NOTICES.md) for external-tool/provider
terms and dated source observations, and [provenance](provenance.md) for the
inspected base, evidence record, and remaining release gates.
