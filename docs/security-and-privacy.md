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
named source host only after separate command-network approval. Before future
transcription, it processes metadata, captions, frames, media, and audio locally.
When `yt-dlp` returns a selected native-caption URL, that untrusted internal
value does not grant the direct caption request. Native captions and visual
evidence remain local by default.
A local file is not uploaded merely because it is selected for analysis.

### Direct native-caption networking

**Classification: implementation requirement. Evidence:** Decision #44, the
[normative direct-caption contract](spec/watch-skill.md#direct-native-caption-retrieval),
and hermetic implementation tests. This is not live source-host, DNS, redirect,
caption, provider, or Desktop-approval evidence.

The direct caption step means not every source contact goes through `yt-dlp`.
Decision #44 resolves the former release/spec gate by making the direct request a
separate native-caption network action rather than a side effect of source-host
approval. The runtime directly retrieves the selected public HTTPS caption
resource only after that action's receipt is verified. Direct-caption retrieval
is release-disabled pending hermetic coverage and one separately approved live
public-caption validation run; this document makes no live approval, caption-fetch,
or release claim.

The approval prompt may disclose only the caption hostname, purpose, selected
track, format, and byte cap. It returns an opaque, single-use receipt for an
`approved`, `declined`, or `canceled` decision; the receipt is bound to one Watch
request, source, runtime session, workspace, selected track, supported format,
byte cap, and normalized HTTPS origin (hostname and port 443). It expires after
five minutes or request end, whichever comes first, and denial, cancellation,
failure, retry, use, or mismatch invalidates it. Invalid, malformed, tampered,
replayed, mismatched, or expired receipts fail closed before DNS or HTTP work.

Caption URLs from `yt-dlp` are untrusted internal data. The runtime must not
display, log, persist as evidence, or accept back as user input a raw signed
caption URL or its query strings, credentials, tokens, or other sensitive URL
material. They must not appear in any user-facing outcome, exception, diagnostic,
snapshot, or log. Sanitized same-task audit data may identify only the hostname,
purpose, selected track, format, byte cap, bounded byte count, redirect count,
and typed outcome.

Only public HTTPS endpoints are eligible. The URL policy rejects malformed URLs,
non-HTTPS schemes, embedded credentials, IP literals, `localhost` and local
aliases, nonstandard ports, loopback, private, link-local, multicast,
unspecified, reserved, and other non-public targets. Every initial and redirect
hostname resolution must yield only public IPv4 and IPv6 addresses; the network
transport connects only to those checked answers so a hostname cannot bypass the
public-address requirement.

The direct request uses a sealed Python `urllib.request` HTTPS path rather than
an ambient browser, global opener, proxy, cookie, redirect, or authentication
configuration. It disables request-target debugging, uses only fixed caption
headers, and dials the already checked numeric answer while retaining ordinary
TLS hostname verification. This is an implementation requirement, not evidence
that a caption request has been made.

Redirects fail closed: there is a limit of three, loops and missing or malformed
locations are rejected, and HTTPS-to-HTTP downgrades are rejected. URL, hostname,
resolution, and public-address validation repeat at every hop. A redirect on the
same approved origin can continue within the limit. A different otherwise-public
origin returns a new `decision_required` action and receipt before any request to
that origin; a non-public destination fails closed. The request must never forward
sensitive authorization information to a redirect destination or expose redirect
URLs in diagnostics.

The caption byte cap is strict. An oversized `Content-Length` is rejected before
the body is read, and actual streamed bytes are checked even if that header is
absent, incorrect, or misleading. The exact cap is accepted only after an
additional-byte check; the first byte beyond it aborts the fetch and never makes
partial caption data successful. The chosen format must be one of the supported
native formats; malformed/unavailable data does not become transcript evidence.

The direct-caption outcome contract preserves the distinction between success
(`ready`), denial (`stopped`), cancellation (`canceled`), unavailability
(`partial`), parse/oversize/HTTP/transport/policy failure (`partial` or a typed
terminal safety outcome), and a new-origin approval (`decision_required`). A
direct-caption outcome does not fall back to transcription, audio extraction,
provider credentials, or provider clients.

For a normally reachable selected caption, failure (`partial`) means transcript
coverage remains `none` and the safe typed category is retained; it never
represents partially read bytes as usable caption evidence. An invalid receipt or
other pre-request safety violation instead stops before the request with its
typed terminal category.

## Telemetry boundary and independent parties

**Classification: implementation requirement. Evidence:** specification
[sections 2 and 12](spec/watch-skill.md#12-required-companion-documentation-and-provenance)
and the accepted [Issue #9 resolution](https://github.com/prossima-ai/codex-watch-yt-video/issues/9#issuecomment-5249321562).

No skill-controlled telemetry, analytics, or crash uploads are part of v0.1.
This is a statement about this skill only: Codex, installed tools, a source site,
or a selected provider may process data under their own controls and disclosures.
This repository makes no claim that it controls, disables, or audits those
independent systems.

## Transcription is release-disabled

**Classification: implementation requirement. Evidence:** Decision #44,
[specification section 8](spec/watch-skill.md#8-transcription-is-release-disabled),
and hermetic disablement tests. No provider has been enabled, contacted, or
live-validated for this work.

Transcription is release-disabled. The release-facing public action surface does
not offer `decision_required` transcription choices or `consent_required`
audio-upload prompts, extract audio, read provider credentials, instantiate
provider clients, or make provider requests. No direct-caption outcome may route
into transcription: success, denial, cancellation, unavailability, parse error,
oversize response, HTTP/transport failure, unsafe destination, and redirect
failure remain caption outcomes. No automatic audio upload occurs.

Before a future provider can be considered, it must have a conservative
provider-specific effective upload limit for the complete encoded request. That
limit includes media bytes, multipart/form-data boundaries, per-part headers,
field names, metadata, and all other request-body overhead; it is not merely
nominal media-file size. A generic file-size cap or an audio-file measurement is
not evidence that a provider request is safe. A human must then select exactly
one provider, review a provider-specific validation plan, and grant separate
explicit human approval immediately before that provider activity. Direct-caption
approval and a future human release decision do not authorize it.

If those future gates close, native captions remain preferred. The task would
first return `decision_required` for an explicit named provider and audio-track
choice, then `consent_required` before audio extraction. Provider selection,
audio-track selection, fresh provider-specific audio-upload consent, and
provider-network approval are distinct gates. No choice implies another:
source-host approval is not provider-network approval, and a credential is
neither provider selection nor consent. A declined/canceled consent or denied
approval stops before extraction and upload, preserving only truthful
captions/frames evidence where available.

Only bounded extracted audio chunks may be uploaded to a future selected
provider, and only after its complete effective request-size limit is enforced.
The adapter receives audio bytes for the selected track only; it never receives
video bytes, video paths, workspace paths, unrelated tracks, or another
provider's state. The runtime must not silently fall back to another provider.
Partial provider results remain partial and name missing intervals rather than
being represented as a complete transcript.

The only named environment credentials are `OPENAI_API_KEY` and `GROQ_API_KEY`.
After a future selected-provider gate has passed, an adapter may read only its
own value at provider call time. The release-facing path reads neither value. The
skill must never request secrets in chat, accept a secret as a control, scan
`.env`, persist or log a credential, include one in a report, filename, URL, or
command argument, probe an unselected provider, or silently fall back after a
provider failure. No credential is read to decide which provider to present.

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
official provider pages above, and [the future provider gate](spec/watch-skill.md#82-required-future-provider-gate).

The historical adapter ceiling is 25,165,823 bytes (`24 * 1024 * 1024 - 1`) before
multipart overhead. The current public documentation reports 25 MB for OpenAI and
25 MB for the Groq free tier; a 25,000,000-byte limit is below that ceiling, and
the implementation does not discover a provider account tier or effective limit.
More importantly, this is not merely nominal media-file size: any future limit
must conservatively account for multipart/form-data boundaries, per-part headers,
metadata, and all other request-body overhead. Therefore this documentation does
not claim either provider is live-ready or that every accepted upload fits a
current account limit. Transcription remains release-disabled. A human must first
select one provider, approve a provider-specific validation plan, and grant
separate explicit human approval immediately before any provider activity. If a
release cannot verify and honor a provider's required disclosure and effective
limit, disable that provider for release; retain captions and visual evidence where
available. The provider-specific effective-limit work remains a future gate;
this implementation enforces only the present release-facing disablement.

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
