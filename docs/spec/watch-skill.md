# Codex-native watch skill — implementation-ready specification

**Status:** Approved as the implementation-ready specification by the human decision owner in the [satisfied Wayfinder issue #13 approval gate](https://github.com/killer-block-coder-95/codex-watch-yt-video/issues/13#issuecomment-5252219003). That approval fixes the requirements; it does not itself grant installation, credential use, external-request, upload, filesystem, or cleanup authority.

**Decision owner:** the human approver of #13.

**Target:** a macOS Codex Desktop standalone skill named `watch`.

**Normative language:** **MUST**, **MUST NOT**, **SHOULD**, and **MAY** have their usual RFC-style meanings. A requirement in this document is a v0.1 implementation requirement, not a claim that it has been exercised against live media or a provider.

## 1. Purpose, authority, and decision record

The **Codex-native watch skill** analyzes one video at a time and gives a user an answer grounded in what was spoken, shown, and reported by the source. It preserves the **behavioral parity** of the upstream watch skill where that behavior is user-visible, while making an **independent reimplementation** for Codex Desktop.

The fixed **parity snapshot** is [`bradautomates/claude-video` v0.2.0 at `83da59fa78c3eee9e20f515fe75c438bb5166efd`](https://github.com/bradautomates/claude-video/tree/83da59fa78c3eee9e20f515fe75c438bb5166efd). It is evidence for outcomes, not an implementation source. The implementation MUST NOT copy, translate, adapt, or scaffold from its source code, tests, assets, command construction, algorithms, or Claude-specific mechanics.

This specification consolidates the closed children of [Wayfinder map #2](https://github.com/killer-block-coder-95/codex-watch-yt-video/issues/2). The parenthesized ticket links below are the normative decision record; the linked research is supporting evidence.

| Resolved decision | This specification section | Primary supporting evidence |
| --- | --- | --- |
| Host contract and live discovery ([#7](https://github.com/killer-block-coder-95/codex-watch-yt-video/issues/7), [#15](https://github.com/killer-block-coder-95/codex-watch-yt-video/issues/15)) | 3, 11 | [Codex Desktop host contract](https://github.com/killer-block-coder-95/codex-watch-yt-video/blob/da8fd612fdbf06a2cc56b2e486ccc326691ebb92/docs/research/codex-desktop-host-contract.md) |
| Behavioral parity baseline ([#14](https://github.com/killer-block-coder-95/codex-watch-yt-video/issues/14)) | 2, 4–10, Appendix A | [Upstream v0.2.0 parity inventory](https://github.com/killer-block-coder-95/codex-watch-yt-video/blob/da8fd612fdbf06a2cc56b2e486ccc326691ebb92/docs/research/upstream-v0.2.0-parity-inventory.md) |
| Media and transcription constraints ([#3](https://github.com/killer-block-coder-95/codex-watch-yt-video/issues/3)) | 6, 8 | [Media and transcription constraints](https://github.com/killer-block-coder-95/codex-watch-yt-video/blob/da8fd612fdbf06a2cc56b2e486ccc326691ebb92/docs/research/media-and-transcription-constraints.md) |
| User-visible request and answer contract ([#5](https://github.com/killer-block-coder-95/codex-watch-yt-video/issues/5)) | 4, 5, 7, 9 | This specification |
| Visual evidence loop ([#6](https://github.com/killer-block-coder-95/codex-watch-yt-video/issues/6)) | 7 | Prototype commit `bbb5350` (calibration evidence only) |
| Runtime architecture ([#11](https://github.com/killer-block-coder-95/codex-watch-yt-video/issues/11)) | 5 | This specification |
| Consent and secret handling ([#8](https://github.com/killer-block-coder-95/codex-watch-yt-video/issues/8)) | 8 | This specification |
| Workspace retention and cleanup ([#12](https://github.com/killer-block-coder-95/codex-watch-yt-video/issues/12)) | 10 | This specification |
| Canonical packaging and installation ([#10](https://github.com/killer-block-coder-95/codex-watch-yt-video/issues/10)) | 11 | This specification |
| Documentation, provenance, and security ([#9](https://github.com/killer-block-coder-95/codex-watch-yt-video/issues/9)) | 12 | This specification |
| Verification and release gate ([#4](https://github.com/killer-block-coder-95/codex-watch-yt-video/issues/4)) | 13 | This specification |
| Fail-closed native-caption networking and transcription release gates ([#44](https://github.com/prossima-ai/codex-watch-yt-video/issues/44)) | 4, 6, 8, 9, 12, 13 | This specification and hermetic implementation tests |

Where the upstream inventory identified a Codex adaptation candidate, the later Wayfinder decisions in this document supersede the mechanism while retaining the observable outcome. In particular, the ordinary frame maximum is **768 px JPEG**, not the upstream 512 px default; a material detail may be re-extracted at **1024 px**.

## 2. Scope and explicit non-goals

### 2.1 In scope

- One public, unauthenticated `yt-dlp`-compatible HTTP(S) URL **or** one local video path per **watch request**.
- An optional natural-language question; without one, a useful time-grounded summary.
- Four **detail modes**: `transcript`, `efficient`, `balanced`, and `token-burner`.
- Captions-first evidence acquisition, including a separate, explicit approval-gated caption-network action for a selected native caption, and visual evidence preparation.
- Stream-scoped timestamp citations, truthful partial-result reporting, same-task reuse, and validated run-owned cleanup.
- A repository-owned Codex Desktop skill, with a manual personal installation route.

### 2.2 Out of scope

The v0.1 skill MUST NOT provide or imply support for:

- Playlists, multiple videos in one request, automatic series processing, or a persistent media library.
- Private, login-required, age-gated, region-bypassed, DRM-protected, live, or authenticated video; browser cookies, account sessions, credential extraction, or platform writes.
- Full-video uploads to a transcription provider; a future separately enabled route may send only consented extracted audio.
- Transcription or provider contact through a release-facing action surface. Transcription is release-disabled until the provider-specific gate in section 8 is satisfied and a human makes a separate decision.
- Automatic package installation, update, self-installation, self-update, or configuration writes outside the approved target.
- Global/cross-task evidence caches, background monitoring, automatic expiry cleanup, telemetry, analytics, or crash uploads.
- Translation, diarization, OCR, object tracking, semantic scene understanding beyond the evidence Codex actually inspected, local sidecar subtitle discovery, or support guarantees for every site/container.
- Claude Code plugin metadata, slash-command plumbing, hooks, token formulas, UI, or build scripts.
- Linux/Windows release parity, public distribution, or a marketplace release. v0.1 is private and unlicensed for redistribution pending a separate decision.

## 3. Host, authority, discovery, and canonical terminology

The repository-owned canonical skill source MUST be:

```text
$REPO_ROOT/.agents/skills/watch/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── scripts/
└── references/
```

`SKILL.md` front matter MUST contain only:

```yaml
---
name: watch
description: <precise trigger and boundary description>
---
```

`agents/openai.yaml` is optional host metadata, not the discovery file. When added, it MUST state the visible display metadata, the `$watch` default prompt, and `policy.allow_implicit_invocation: true`; it MUST NOT claim unavailable tools, MCP dependencies, icons, branding, or authority.

### 3.1 Invocation does not grant authority

`$watch` is the explicit route. An eligible natural-language request may invoke `watch` implicitly only under the narrow rule in section 4. Neither route grants filesystem, network, package-installation, credential, upload, or outside-workspace write authority. The active Codex sandbox and its approval flow remain controlling.

Bundled scripts MUST run under the active sandbox. They MUST fail closed if a required permission is denied and MUST NOT treat a skill selection, a browser session, web search, or a stored environment variable as permission for a new command-network or upload action.

### 3.2 Discovery evidence and its boundary

The intended portable personal location is `$HOME/.agents/skills/watch`. Fresh macOS Codex Desktop probes confirmed repository discovery, personal discovery, distinct path-identifiable duplicate names, and a repository metadata change visible in a **new task** without restart ([#15](https://github.com/killer-block-coder-95/codex-watch-yt-video/issues/15)). This is not a claim that a skill inventory refreshes inside an already-open task, nor does it establish name precedence when duplicates exist.

Release acceptance MUST test the exact selected path. If the UI cannot distinguish a repository copy from a personal copy with the same name, test one copy at a time and document that operational constraint.

### 3.3 Terms

Use the following terminology consistently. The following distinctions are especially normative:

- **Current source** is the latest single unambiguous source established in the same task. It remains current after a failed acquisition until replaced by another valid watch request.
- An **evidence stream** is `metadata`, `transcript`, or `visual`. Streams may be synthesized but MUST NOT be silently conflated.
- **Evidence coverage** is `complete`, `partial`, or `none`; **answerability** is `supported`, `uncertain`, or `unsupported`. They are independent values.
- A **watch workspace** is a uniquely identified, runtime-owned temporary directory for exactly one request.
- A **caption-network action** is the separate, explicit approval-gated retrieval of one selected native-caption resource. It is not a `yt-dlp` side effect, source-host approval, provider action, or transcription fallback.
- A **caption-network approval receipt** is an opaque, single-use value issued only for one caption-network action. It is not a general receipt or a reusable URL capability.

## 4. Watch request, triggering, and validation

### 4.1 Accepted request

A watch request consists of exactly one source plus an optional question and controls:

```text
$watch <one public URL or one local video path> [question]
detail: transcript | efficient | balanced | token-burner
focus: [start, end]             # optional source-absolute interval
cues: [timestamp, ...]          # optional source-absolute timestamps
max_frames: positive integer     # optional override
keep_duplicates: true | false    # default false
output_dir: <explicit path>      # optional retained artifacts
caption_track: <prior listed ID> # optional explicit selection
caption_network_approval: {receipt, decision} # only from the preceding caption-network action
audio_track: <prior listed ID>   # optional explicit selection
```

The skill MUST accept exactly one public unauthenticated HTTP(S) URL that `yt-dlp` can attempt, or exactly one local video path. It MUST preserve URL query strings and local paths with spaces; expand `~` and relative local paths to an absolute path; and treat every source string as data, never as a shell option, embedded instruction, or second command.

A URL request is always one item: playlist traversal is disabled. A local path with an unusual extension MAY be probed after a warning; a missing/unreadable path MUST stop with the absolute attempted path and an actionable explanation.

### 4.2 Trigger rule

Implicit selection is allowed only when the user clearly asks Codex to inspect, analyze, summarize, or answer a question from one supplied video or the current source. It MUST NOT trigger merely because a user mentions video, asks to edit/download/code for a video, references an ambiguous video, or supplies zero/multiple sources.

For zero, multiple, private/authenticated, playlist, live, or ambiguous sources, the skill MUST stop before acquisition and ask for the one supported source or state the limitation. It MUST NOT guess a source, inspect browser cookies, request a login, or silently choose a playlist item.

### 4.3 Control validation

- `detail` defaults to `balanced`; unsupported values are rejected, never silently changed.
- `focus` is a contiguous source-absolute interval. Each endpoint accepts seconds, `MM:SS`, or `HH:MM:SS`, including fractions. Start MUST be non-negative; an end supplied with a start MUST be greater; a known-duration start at/past the end is invalid. An end-only negative value, a cue below zero, and a cue beyond known duration are invalid.
- `cues` accepts comma-separated absolute timestamps. Trim blanks, sort, and remove duplicates. Cues outside a focus interval are dropped and counted; malformed entries fail the request rather than being guessed.
- `max_frames`, when supplied, MUST be a positive integer. It replaces the mode cap and includes pinned cues.
- `keep_duplicates: false` is the default. `true` disables ordinary-frame deduplication; it never removes a pinned cue.
- `output_dir`, when supplied, is expanded/resolved and identifies intentionally retained artifacts. The runtime MUST obtain the host's narrow filesystem approval before creating or writing it when it falls outside writable roots; it MUST never delete that directory automatically.
- `caption_track` and `audio_track` identify a sanitized, run-scoped ID emitted for that same choice kind in a prior `decision_required` response. An unknown ID, a stale ID, or an ID issued for a different choice kind is invalid. The runtime MUST reject it before any new acquisition, extraction, upload, or provider request and MUST NOT select a first/default track.
- `caption_network_approval`, when present, contains exactly an opaque receipt from the immediately preceding caption-network `decision_required` outcome and one of `approved`, `declined`, or `canceled`. It MUST NOT accept a caption URL, path, query string, credential, token, hostname substitution, or any user-created receipt. A malformed, stale, replayed, tampered, mismatched, expired, or otherwise invalid receipt MUST fail closed before DNS or HTTP work.

Caption and audio-track selection is deliberately conservative: an explicit valid track ID wins; when exactly one usable track exists, select it; otherwise return `decision_required` and ask the user to choose from sanitized available tracks. A user may request a language in natural language; it identifies a track only when it resolves to exactly one available native-caption track. The skill MUST NOT silently translate, infer language from title/uploader, or use an arbitrary first/default track.

### 4.4 Current source and follow-up rule

Once a request validates, it establishes the current source even if later preparation fails. A follow-up referring unambiguously to that source reuses same-task evidence under section 10. It MUST NOT silently reacquire media, extract more frames, or upload audio. If the new question needs unsampled evidence, explain exactly what new work is required and obtain the relevant approval/consent before doing it.

## 5. Evidence contract and answer behavior

### 5.1 Evidence streams and citations

The runtime produces immutable streams:

| Stream | Examples | Citation rule |
| --- | --- | --- |
| `metadata` | source URL, duration, title, uploader, codec | Cite as metadata; never treat it as spoken or visible evidence. |
| `transcript` | native/automatic captions; future provider segments only after the separate provider gate | Cite absolute source times and provenance. |
| `visual` | inspected JPEG frames | Cite absolute source times, selection reason, and that the claim is visual. |

User-facing answers MUST cite material claims with absolute, stream-scoped timestamps—for example, `The speaker says this at 00:31–00:34 (transcript); the board first visibly reads READY in the 00:36 frame (visual).` A visual claim MUST NOT be inferred from transcript wording; a speech claim MUST NOT be inferred from a silent frame. Conflicts and gaps MUST be stated.

Every evidence bundle MUST report `coverage` independently for each stream and overall scope, and `answerability` for the requested conclusion:

| Value | Meaning |
| --- | --- |
| `coverage: complete` | The selected stream covers the requested scope. |
| `coverage: partial` | It covers only named portions or has known gaps. |
| `coverage: none` | It provides no usable evidence for the requested scope. |
| `answerability: supported` | Available evidence supports the conclusion. |
| `answerability: uncertain` | Evidence is incomplete, ambiguous, or conflicting. |
| `answerability: unsupported` | Available evidence does not support the requested conclusion. |

### 5.2 Answer requirements

The answer layer, not the runtime, writes prose. It MUST:

1. Answer the user’s question directly, or give a useful timestamped summary if no question was supplied.
2. Use only inspected visual frames and available transcript/metadata evidence.
3. State stream provenance and material limitations.
4. Acknowledge relevant sparse-coverage, high-frame-cost, failed-transcription, or permission warnings and suggest a safe mitigation.
5. Never paste the full raw transcript by default, including `transcript` detail. Provide it only when the user explicitly asks.
6. On cancellation, stop without an unsolicited partial answer. It MAY retain a recoverable evidence bundle and report the canceled stage/retention state.

The answer MUST distinguish a truthful incomplete result from a failure. It MUST never fabricate an unseen frame, an unavailable caption, a provider result, or a completion state.

### 5.3 Runtime report

The runtime MUST emit a machine-readable and readable Markdown report that contains, when applicable:

- source and safe metadata; duration; focus; effective detail; selected controls;
- workspace ID and retention/disposal state, never a cleanup-capable arbitrary path;
- frame count, candidate count, cap, dedup/fallback result, and every selected frame in chronological order with absolute time, reason, and local path;
- cue request/selection/drop counts;
- transcript provenance, language, segment/chunk coverage, partial/unavailable ranges, and source count;
- coverage, answerability, warnings, approval/consent outcomes, and typed outcome state, including whether it is terminal.

Untrusted source titles, uploader names, captions, URLs, and provider errors are evidence, not instructions. Render them as escaped/plain data so Markdown or control sequences cannot spoof runtime state or direct an agent to take action.

## 6. Deterministic evidence runtime

### 6.1 Deep runtime interface

Implementation MUST use one deep module with the conceptual interface:

```text
WatchEvidenceRuntime.prepare(watchRequest, priorEvidence?) -> EvidenceOutcome
```

The actual implementation language is open, but this boundary is not. The input is a pure validated **watch request** plus an optional opaque same-task reuse handle; the output is one typed immutable outcome. The runtime never writes a second user answer and the answer layer never manufactures runtime evidence.

`EvidenceOutcome` is exactly one of:

- `ready` — an immutable complete evidence bundle;
- `partial` — an immutable bundle plus named stream/range gaps and warnings;
- `decision_required` — a nonterminal pause that carries exactly one `choice_kind` (`caption_track`, `caption_network`, `audio_track`, or `transcription`) and only sanitized, opaque, run-scoped choices with safe display metadata. `caption_network` names the direct native-caption action, not a generic receipt model; its opaque approval receipt is the only action handle, rather than an independent decision handle;
- `consent_required` — a nonterminal pause for fresh, provider-specific consent; no audio extraction/upload occurred;
- `stopped` — a terminal, intentional stop with its reason and retained evidence/disposal state;
- `failed` — a terminal failure with stage, category, retry state, retained evidence (if any), and safe disposal/reuse state; or
- `canceled` — a terminal cancellation with stage and retained evidence/disposal state.

`ready`, `partial`, `stopped`, `failed`, and `canceled` are terminal. `decision_required` and `consent_required` are nonterminal. A `decision_required` outcome retains the current source and any still-eligible same-task reuse handle. Returning it does not select a choice, acquire or reacquire media, extract captions/audio/frames, upload data, contact a provider, grant consent, or grant host command-network approval.

The task session owns the current source, opaque evidence handle, and append-only versioned manifest. The handle MUST NOT be a filesystem path, URL credential, shell command, or reusable cross-task cache key.

### 6.2 Execution order

The fixed runtime order is:

```text
parse and validate
→ preflight
→ metadata
→ duration checks
→ create workspace
→ caption inventory and track selection
→ caption-network receipt decision
→ bounded native-caption retrieval and parsing
→ visual evidence
→ immutable evidence bundle
```

Any `decision_required` or `consent_required` outcome pauses this order. A resumed call MUST validate the supplied run-scoped selection against its original choice kind before doing further work. `transcript` detail with usable captions and no cues MAY finish without a media download. Visual preparation occurs only when the chosen mode or a valid cue needs it. Caption parsing failure is non-fatal; the resulting route and limitation MUST be visible.

All tool adapters are typed composition-root dependencies. They MUST invoke executables with an executable plus argument array, consume structured output where available, and never construct a shell string. `yt-dlp` MUST use `--ignore-config` so a user/global configuration cannot inject authentication, paths, proxying, or download behavior. The report MUST include relevant executable/provider/model versions without exposing secrets.

### 6.3 Preflight, acquisition, and caption policy

Before the first source-host request, disclose that `yt-dlp` will contact the named public host and request the host's command-network approval. Before dependent work, preflight `yt-dlp`, `ffmpeg`, and `ffprobe` executables. Also report whether `yt-dlp` has a usable EJS/JavaScript runtime for current YouTube support. A missing tool yields typed guidance; the skill MUST NOT autonomously install or update it. Caption-only work MAY proceed without media post-processing only if the missing tool is not needed.

For an eligible public URL, metadata and bounded subtitle availability are checked before media download. The downloader MUST inspect manual and automatic caption availability, exclude `live_chat`, and use a bounded request. It records every available track's sanitized run-scoped ID, language, type, and format. It selects a valid explicit `caption_track` ID, or the sole usable track; otherwise, when transcript evidence is needed, it returns `decision_required` before selecting/downloading a caption or producing transcript claims. It MAY continue a visual-only route that explicitly reports transcript coverage as `none`; that route MUST NOT make transcript claims without a valid selection and usable transcript evidence. The runtime MUST NOT default to English, translate, or infer a preference from metadata.

The selected transcript records whether it was manual captions, automatic captions, or none. Normalize it into ordered segments with text, start/end times, language, and provenance; strip markup and collapse rolling duplicate/extended cues while retaining absolute source times. Do not automatically discover local sidecar subtitles.

#### Direct native-caption retrieval

After a selected native caption exposes a retrieval resource, the runtime MUST return a separate, explicit approval-gated caption-network action before it resolves, connects to, or fetches that resource. Its user-visible approval prompt may disclose only the caption hostname, purpose, selected track, format, and byte cap, plus the opaque receipt needed to record an `approved`, `declined`, or `canceled` decision. It MUST NOT disclose a raw signed caption URL, path, query string, credential, token, or other sensitive URL material.

The opaque, single-use approval receipt MUST bind the same Watch request, source, runtime session, workspace, selected caption track, supported format, byte cap, and exact normalized HTTPS origin (normalized hostname and port `443`). It expires after five minutes or request end, whichever comes first. Failure, cancellation, denial, or retry invalidates the receipt. Receipt verification MUST occur before any DNS or HTTP request; every rejected receipt makes zero outbound caption HTTP attempts. A receipt cannot be moved across actions, requests, sources, sessions, workspaces, tracks, formats, byte caps, or origins.

Caption URLs supplied by `yt-dlp` are untrusted internal data. The runtime must not display, log, persist as evidence, or accept back as user input a raw signed caption URL or its query strings, credentials, tokens, or other sensitive material. Such material MUST NOT appear in a user-facing outcome, exception, diagnostic, snapshot, or log. A sanitized audit may retain only same-task/workspace facts needed to explain the action: hostname, purpose, selected track, format, byte cap, bounded byte count, redirect count, and typed status.

Only public HTTPS is eligible. The URL policy MUST reject malformed URLs, non-HTTPS schemes, embedded credentials, IP literals, `localhost` and local aliases, nonstandard ports, loopback, private, link-local, multicast, unspecified, reserved, and other non-public targets. The resolver MUST require that all resolved IPv4 and IPv6 addresses are public, and the transport MUST connect only to those revalidated answers so hostname resolution cannot bypass the public-address rule.

The direct native-caption transport MUST use the Python standard library's
`urllib.request` HTTPS path, constructed from the sealed approved resource with
no inherited proxy, redirect, cookie, or authentication handlers. It MUST force
request-target debugging off, send only the fixed caption request headers, and
dial the already-validated numeric DNS answers with TLS hostname verification.
It MUST NOT use global `urlopen()` or an opener that can expose or redirect a
signed caption URL outside this policy boundary.

Redirect handling is fail closed. The runtime MUST enforce a strict redirect limit of three, detect a redirect loop, reject a malformed or missing `Location`, and reject every HTTPS-to-HTTP downgrade. The URL, hostname, resolution, and public-address rule are revalidated at every redirect hop. A redirect on the exact approved origin may continue within the limit; a new otherwise-public origin returns `decision_required` with a new receipt and no connection to that new origin. An unsafe redirect fails closed. Never forward sensitive authorization information to a redirect destination, and never expose a redirect URL outside the internal fetch boundary.

The selected supported format MUST be enforced, and the byte cap is strict. An already-oversized `Content-Length` is rejected before body reads; actual streamed bytes are capped even when the declared length is absent, false, or misleading. The exact byte-cap boundary is accepted only when no further byte exists; the first byte beyond it is an oversized response. The fetcher MUST abort cleanly and MUST NOT return partial caption data as success.

Direct native-caption retrieval is release-disabled until the contract above is implemented and covered by hermetic tests, and until a separately approved live public-caption validation run records adequate sanitized evidence. This specification and its tests do not grant that live authority, prove a live request, or make a release decision.

Private, login-required, removed, region-limited, DRM-protected, or live media produces a plain unsupported-access outcome after one safe attempt. The runtime MUST NOT loop, use cookies, export a browser session, or try to bypass the access condition.

## 7. Visual evidence

### 7.1 Detail modes and budgets

| Mode | Ordinary visual behavior | Default ordinary-frame cap | Required warning behavior |
| --- | --- | ---: | --- |
| `transcript` | No ordinary frames; valid cues may produce cue-only frames. | 0 | State that no visual fallback exists when no cues/usable transcript exist. |
| `efficient` | Keyframe-first; if fewer than four useful keyframes survive, use duration-aware uniform sampling. | 50 | For an unfocused source over 600 seconds, warn that coverage is sparse and recommend focus or `token-burner`. |
| `balanced` | Default; scene-aware selection across the full requested range, with uniform fallback for effectively static footage. | 100 | Same sparse-coverage rule as `efficient`. |
| `token-burner` | Scene-aware selection with no default cap. | none | Warn only when more than 250 selected frames create high visual-context cost. |

`max_frames` replaces the cap. Cues reserve slots before ordinary frames; if a finite cap is lower than the number of cues, select cue timestamps across the ordered list while retaining first and last. Ordinary candidates are deduplicated before cap application unless `keep_duplicates` is true. Capped output MUST be thinned across the whole interval, retaining first/last candidates when at least two are selected.

The sampling rate MUST NOT exceed 2 fps. Full-video uniform targets are approximately 12–30 through 30 seconds, 40 through one minute, 60 through three minutes, 80 through ten minutes, then the capped-mode ceiling. Focused targets are denser: up to 10 through 5 seconds, 30 through 15 seconds, 60 through 30 seconds, 80 through 60 seconds, then the mode cap. These are planning targets, not a promise that scene detection yields exactly that count.

### 7.2 Frame form and inspection

Ordinary frames MUST be JPEG, aspect-correct, and at most 768 px wide without upscaling. When a question materially depends on small text or fine spatial detail unresolved at 768 px, re-extract only the relevant frame at at most 1024 px. PNG MAY be used only where lossless pixels are materially necessary and its reason is recorded.

Every selected frame MUST include its source-absolute timestamp, chronological position, selection reason (`first`, `scene`, `uniform`, `keyframe`, or `transcript-cue`), and path. Merge ordinary and cue frames chronologically, then inspect **every selected frame** in chronological batches of eight. Batching is an image-ingestion strategy, never a lower selection cap. The prototype behind [#6](https://github.com/killer-block-coder-95/codex-watch-yt-video/issues/6) calibrated no more than 12 images per batch, so it does not waive the 50/100/251 scale acceptance rows in section 13.

If the host’s local-image capability is unavailable or cannot read a frame, report that fact and refrain from visual conclusions. A path/attachment fallback is allowed; simulated image inspection is not.

### 7.3 Focus and cues

All focus and cue timestamps remain source-absolute. Transcript focus retains segments overlapping the interval. Cue frames are pinned evidence, are additive to ordinary visual frames, and carry `transcript-cue` as their reason. In `transcript` detail they are the only allowed frames.

Cue selection is a visual judgment prompted by genuinely deictic transcript language, not a blind keyword match. A rhetorical “look” MUST NOT cause a frame extraction. Focus drops out-of-range cues, reports their count, and never creates a phantom frame entry for an out-of-media request or extraction failure.

## 8. Transcription is release-disabled

### 8.1 Current release boundary

Transcription is release-disabled. No release-facing action surface may invoke provider credentials or provider clients, offer a `transcription` choice, extract audio for upload, or route a caption failure into a provider. Direct-caption success, denial, unavailability, parse failure, oversize response, HTTP failure, transport failure, unsafe destination, and redirect failure never invokes transcription, a provider credential, or a provider client.

The repository may retain isolated adapter code and dated provider documentation for future work, but that is not an enabled provider, a live validation, or release authorization. There is no default provider and no silent cross-provider fallback. Credentials may come only from an external key manager or named environment variables `OPENAI_API_KEY`, `GROQ_API_KEY`, and the development/test-only `MISTRAL_API_KEY`. Each selected adapter reads only its own value at provider call time; the release-facing runtime MUST NOT read any of them. The skill MUST NOT request secrets in chat, accept a secret value as a control, scan/read `.env`, persist a secret, print it, place it in arguments/filenames/URLs/reports, or probe one provider’s key after another fails. It MUST NOT revoke or delete a credential.

### 8.2 Required future provider gate

Before a human can consider enabling exactly one provider, that provider needs a conservative, provider-specific effective upload limit that is implemented and hermetically tested. It MUST account for the complete encoded request, including the media bytes, multipart/form-data boundaries, per-part headers, field names, metadata, and all other request-body overhead; it is not merely nominal media-file size. A generic file-size cap, a source-media size, or a nominal provider limit is not sufficient evidence for provider safety.

Only after that gate is complete may a human select exactly one provider, review a separate provider-specific validation plan, and grant separate explicit human approval immediately before that provider activity. The plan must identify the selected provider/model, destination, current account/plan limit, complete request-size accounting, audio-only form, fresh provider-specific consent, separate provider-network approval, redaction/evidence handling, duration, and success criteria. Neither a direct-caption approval nor a human release decision authorizes a provider request.

### 8.3 Future consent and upload requirements

If the separate provider gate and approval occur, native captions remain preferred. The task MUST explicitly offer a no-transcription route and require an explicit named-provider and audio-track choice; it MUST NOT infer a provider, use a default, or treat a credential as provider selection or consent. Only after both selections may it return `consent_required`, before audio extraction or a provider request. Provider selection, audio-track selection, fresh provider-specific audio-upload consent, and provider-network approval are distinct gates.

The future consent prompt MUST name the selected provider and model, provider destination and current privacy/retention link, audio-only boundary, selected track, estimated duration, complete effective request-size limit, possible chunking, and the separate network approval. It must never promise that a nominal media-file limit is enough. A decline, cancellation, unavailable authorization, or missing gate stops before extraction/upload and returns only truthful captions/frames evidence where available.

For an approved future provider, extract only one selected audio track; never upload video bytes or a video path. Every request remains isolated to that provider's credential. Retry only a selected provider's explicitly transient failures under the then-approved bounded policy; never retry a denied approval or silently switch providers. Provider documentation, model availability, retention wording, account entitlement, and plan limits are release-time freshness checks, not permanent claims. If any required current disclosure, effective limit, test, or approval is absent, transcription remains release-disabled.

## 9. Failures, cancellation, and truthful outcomes

Every runtime outcome MUST expose its state and whether it is terminal. Terminal stop, failure, and cancellation outcomes also expose the applicable stage, category, attempts, and retained evidence/disposal state. They MUST distinguish:

- invalid request or unsupported source;
- missing preflight dependency;
- denied or unavailable sandbox/network/write authority;
- source acquisition/caption/media failure, including typed native-caption approval, redirect, URL-policy, byte-limit, HTTP, transport, unavailability, and parse outcomes;
- consent declined/canceled;
- provider permanent/transient/partial failure; and
- user cancellation.

For a URL, a playable media output may be usable even if subtitle acquisition exits non-zero; no usable media is a hard acquisition failure with safe diagnostic context. The direct-caption outcomes are distinct: a valid parsed result is `ready`; a declined caption-network approval is terminal `stopped`; cancellation is `canceled`; unavailable, parse, oversize, HTTP, transport, URL-policy, and redirect failures are truthful `partial` or typed terminal safety outcomes with transcript coverage `none`. A direct-caption failure MUST NOT invoke transcription or disguise a partial caption file as success. Dependency/media probe/extraction failures name the operation and leave a safely identifiable workspace state.

No cancellation returns unsolicited prose. No failure creates a fake transcript, selected frame, credential diagnosis, or completed cleanup result. Current source and same-task evidence state remain honest after all outcomes.

## 10. Workspace, retention, reuse, and cleanup

### 10.1 Workspace invariants

Each new request gets one new workspace that is a direct child of a fixed runtime-owned temp root. It has an opaque ID, ownership marker, lock, and append-only versioned manifest. The manifest lists only run-owned artifacts and the disposition of captions, media, audio, chunks, frames, and reports.

User paths, source videos, exports, supplied output directories, global skill files, configuration, and sibling workspaces are never cleanup targets. No global library or cross-task cache is allowed.

Same-task follow-ups reuse only the opaque evidence handle and manifest state. They do not gain a raw filesystem path. Evidence is retained while the same task needs it; an explicit user-selected output directory is retained until the user asks for its removal and is never deleted as a workspace.

### 10.2 Explicit cleanup only

There is no automatic cleanup at task end, on timeout, under disk pressure, after a stale lock, or by background expiry. Recovery supports only:

```text
cleanup current
cleanup <workspace-id>
```

Before deleting, the runtime MUST validate all of the following: direct-child location, opaque ID, ownership marker, manifest format/version, no traversal/symlink path, known owned artifacts only, and a held lock. Where the platform provides identity-safe leaf deletion, it deletes manifest-listed files one at a time using non-shell APIs; it MUST NOT recursively delete an unresolved directory.

On macOS, public POSIX APIs cannot bind an unlink or directory removal to a previously verified leaf identity: a same-UID process can replace a checked name before deletion. When that identity-safe primitive is unavailable, the runtime MUST preserve the fully validated workspace, revoke reuse, and return `cleanup_incomplete` with a truthful no-deletion report. It MUST NOT substitute a best-effort name-based delete for this fail-closed outcome.

If validation fails or the workspace is altered/unknown/unverifiable, return `cleanup_refused` and delete nothing. If a lock is held, return `cleanup_deferred`. Each result reports exact disposal/reuse semantics without claiming that arbitrary user files were removed.

## 11. Packaging, manual installation, and updates

The canonical tree in section 3 is self-contained. Tests and fixtures remain outside the installed skill tree; add assets only when a real runtime need exists. `SKILL.md` should be concise discovery metadata followed by imperative workflow/safety instructions, with linked references rather than duplicated research.

Personal installation is a manual, fail-closed symlink:

```text
$HOME/.agents/skills/watch -> $REPO_ROOT/.agents/skills/watch
```

The installer documentation MUST refuse an existing target. It MUST NOT force, copy, self-install, self-update, mutate a global location, or create/update the symlink without explicit authority. Update the canonical source, start a new Desktop task to inspect it, and use one restart only as the documented fallback when it does not appear. Do not assert a duplicate-name precedence rule.

## 12. Required companion documentation and provenance

Before a release, the repository MUST contain, outside the skill tree:

- `README.md` — supported scope, request examples, canonical source, and known limits;
- `docs/setup-and-troubleshooting.md` — preflight, manual installation, failure states, and approval flow;
- `docs/security-and-privacy.md` — source-host contact, local media processing, transcription consent, data handling, no telemetry, and cleanup behavior;
- `THIRD_PARTY_NOTICES.md` — actual tools, version/source/license, including FFmpeg build configuration;
- `docs/provenance.md` — pinned parity snapshot, independent-reimplementation statement, evidence runs, deviations, approvals, and clean-room review.

Every material public or user-facing claim MUST be classified as one of:

- `confirmed` — named live/recorded evidence exists;
- `implementation requirement` — specified but not live-verified; or
- `unsupported/out of scope`.

The documents MUST state that local captions/visual processing are preferred; direct native-caption retrieval is a separate explicit receipt-gated action; raw signed caption URLs and sensitive URL material are redacted; host network approval is separate; no telemetry/analytics/crash upload occurs; and private/authenticated/DRM media are unsupported. They MUST state that direct captions and transcription are release-disabled until their distinct gates close. Transcription sends no data in the current release surface; any future provider path may send only consented extracted audio after the complete effective request-size gate, selected-provider validation plan, and separate explicit human approval. Recheck provider privacy/retention links and wording before every release. Missing verified disclosure disables the corresponding provider.

The provenance record MUST identify the source commit, spec revision, parity snapshot, host/tool versions, evidence runs, deviations, approval issue, licenses/notices, and the clean-room review. It MUST say neither the upstream project nor providers endorse this project.

## 13. Verification, records, and release gate

### 13.1 Evidence record

Every verification run MUST record test ID, implementation revision, spec revision, app/host/tool versions, fixture or source identity, trace, approvals, redacted artifacts, and one outcome:

| Outcome | Meaning |
| --- | --- |
| `PASS` | The required stimulus and qualifying evidence succeeded. |
| `FAIL` | Qualifying evidence contradicted the requirement. |
| `BLOCKED` | A required external prerequisite or authorization prevented the run. |
| `UNVERIFIED` | No qualified evidence exists for a nonmandatory claim. |

Static analysis, documentation review, mocks, and synthetic tests may pass only their static/hermetic rows. They NEVER prove Desktop discovery, real public-media acquisition, live provider behavior, sandbox approval behavior, or live cleanup.

### 13.2 Normative acceptance matrix

| Group | Rows | Required proof |
| --- | --- | --- |
| Hermetic behavior and safety | **H-01** input/trigger refusal; **H-02** injection-safe adapter argument arrays; **H-03** missing-tool typed guidance; **H-04** controls/mode caps; **H-05** focus/cue/track-selection validation; **H-06** stream separation/citations; **H-07** typed outcome/retry/cancellation; **H-08** same-task reuse; **H-09** direct-caption opaque-receipt binding, expiry, invalidation, redaction, public-address policy, redirects, byte caps, and no-provider fallback; **H-10** hostile-workspace cleanup refusal/success; **H-11** release-facing transcription disablement and the future complete-request-size gate. | Independently authored offline fixtures and mocks prove observable behavior; no upstream test code. They do not prove a source-host request, DNS result, redirect, provider request, or host approval. |
| Synthetic visual grounding | **S-01** generated ground-truth media including multi-track metadata; **S-02** 768/1024 extraction and escalation; **S-03** 0/50/100/251 scale/mode behavior; **S-04** independent review of visible claims. | Cut-heavy, static, held-slide-small-change, portrait, silent, multi-track, and long metadata fixtures; evidence reviewer has no generator/expected-answer access. |
| Desktop/package/authority | **D-01** canonical repository package discovery; **D-02** personal symlink discovery; **D-03** duplicate-path, explicit/implicit/negative trigger, and fresh-task reload behavior; **D-04** offline, denied network, denied outside-workspace write, and local-frame fallback. | Actual target macOS Desktop tasks. A fresh task proves discovery/reload; it does not prove in-task refresh. |
| Live public caption | **L-01** one separately human-approved public-caption validation run. | Prove the exact committed direct-caption action against the approved public source, sanitized hostname/redirect validation, bounded byte count, typed outcome, no transcription/provider path, and retained redacted evidence. A cross-host caption URL is preferred when lawfully knowable, but the approval applies only to the named one run. |
| Future live provider | **L-02** one separately approved selected-provider validation. | This row is unavailable while transcription is release-disabled. Before it may run, a human selects one provider; its complete effective request-size limit, including multipart/form-data and all request-body overhead, is implemented and tested; and the human approves a provider-specific plan immediately before the activity. |
| Documents and provenance | **P-01** scope/privacy/setup/license claims; **P-02** provenance and clean-room review. | Review each required companion document, notices, release provenance, and independent-source declaration. |

### 13.3 Release decision

Direct-caption retrieval is not release-ready until every applicable H, S, D, P, and L-01 row passes and a human explicitly records a release decision for the specifically defined scope. L-01 requires separate live-run approval; this specification, a code commit, hermetic tests, or a release decision do not supply it. Transcription is excluded from every release scope while it is release-disabled; it cannot become in-scope until the separate L-02 gate closes. An unavailable authorization, source, provider, or evidence record is `BLOCKED`, never waived or converted into a pass. The unselected provider must not be marketed as verified.

The release record MUST name intentional deviations from the parity snapshot (including 768 px ordinary JPEG frames and eight-frame chronology batches) and their calibration evidence. It MUST record the pinned base and implementation commits, exact validation commands/results, Standards and Spec reviews and each resolution, transcription-disablement evidence, live public-caption evidence if separately approved, provider-validation status, remaining blockers, and the human release decision. Live behavior, current provider terms, extractor compatibility, account entitlement, and Desktop discovery must be recorded as live evidence, not inferred from static checks. A human release decision does not authorize publishing, deployment, provider enablement, or another live action.

## 14. Implementation-ready checklist and satisfied approval gate

### 14.1 Approved caption-language and audio-track policy

The resolved record did not specify a selection algorithm, so this specification adopts the human-approved conservative policy: honor a valid explicit track selection; automatically select only when exactly one usable native caption/audio track exists; otherwise return `decision_required` and ask the user to choose. Never infer from title/uploader, auto-translate, or silently use a first/default track.

The `decision_required` response and every follow-up selection MUST satisfy the sanitized-choice, same-task-state, and no-action invariants in sections 4.3 and 6.1. A visual-only route may continue only when it reports transcript coverage as `none` and makes no transcript claim without a valid selection and usable transcript evidence.

### 14.2 Approval checklist

The human approval recorded in [#13](https://github.com/killer-block-coder-95/codex-watch-yt-video/issues/13#issuecomment-5252219003) satisfied this checklist:

- [x] The exact supported source, trigger, controls, and invalid-request behavior are defined.
- [x] The evidence streams, timestamp citations, coverage, answerability, outcomes, and cancellation rules are defined.
- [x] The deep runtime boundary, fixed stage order, typed adapters, and same-task reuse boundary are defined.
- [x] Caption-language and audio-track selection follows the approved conservative policy in section 14.1.
- [x] Caption, visual, transcription, consent, credential, retry, and partial-coverage policies are defined.
- [x] Workspace ownership, retention, and explicit safe cleanup are defined.
- [x] Canonical package tree, manual installation/update behavior, and discovery constraints are defined.
- [x] Required companion documents, provenance, and third-party notices are defined.
- [x] Every required acceptance row and the non-waivable release rule are defined.
- [x] No private/authenticated-media, installation, credential, upload, or cleanup authority is implied by invocation alone.

The human approved this document in the [#13 resolution](https://github.com/killer-block-coder-95/codex-watch-yt-video/issues/13#issuecomment-5252219003), satisfying the gate and making it the **implementation-ready specification**. Implementation begins from this document; it must not reopen settled product/safety/packaging decisions unless a new explicit decision record supersedes them.

## Appendix A — parity requirements incorporated by reference

The independent acceptance suite MUST cover the observable requirements catalogued in the pinned [upstream parity inventory](https://github.com/killer-block-coder-95/codex-watch-yt-video/blob/da8fd612fdbf06a2cc56b2e486ccc326691ebb92/docs/research/upstream-v0.2.0-parity-inventory.md): `IN-01…06`, `SET-01…06`, `TR-01…11`, `FR-01…10`, `FOC-01…03`, `CUE-01…05`, `REP-01…06`, `ERR-01…09`, `LIFE-01…03`, and `SEC-01…05`.

The following document-specific decisions resolve its Codex adaptation candidates:

| Parity candidate | v0.1 resolution |
| --- | --- |
| Invocation | Explicit `$watch` plus narrow implicit routing under section 4. |
| Frame inspection | Host local-image feature detection; inspect every selected image in chronological batches of eight. |
| Setup interaction | Codex-native consent/approval flow; no secret collection in chat. |
| Installation | Explain/manual approve; never autonomous package installation. |
| Secret storage | Environment/external key manager only; no `.env` scan or persisted config. |
| Network | Per-action sandbox/approval, independent of selection and stored key. |
| Caption and audio-track selection | Conservative policy in sections 4.3, 6.3, 8.2, and 14.1; no translation or silent selection. |
| Image calibration | 768 px JPEG ordinary frames, targeted 1024 px escalation, 2 fps ceiling, and explicit scale gates. |
| Report transport | Immutable evidence bundle plus escaped report fields; answer layer owns prose. |
| Cleanup | Run-owned direct-child workspace, validated manifest-only deletion, explicit request only. |
| Platform | macOS Codex Desktop only for v0.1. |
| Packaging | Repository standalone skill plus manual personal symlink; no plugin requirement. |

The source inventory is a requirements/evidence reference only. A future implementation MUST use independently authored fixtures and black-box tests, and record the clean-room review in `docs/provenance.md`.
