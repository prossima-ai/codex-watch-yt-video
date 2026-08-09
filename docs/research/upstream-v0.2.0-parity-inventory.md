# Upstream v0.2.0 behavioral parity inventory

- Status: resolved research input for [Wayfinder issue #14](https://github.com/killer-block-coder-95/codex-watch-yt-video/issues/14)
- Pinned parity source: [`bradautomates/claude-video@83da59fa78c3eee9e20f515fe75c438bb5166efd`](https://github.com/bradautomates/claude-video/tree/83da59fa78c3eee9e20f515fe75c438bb5166efd)
- Upstream release: [`v0.2.0`](https://github.com/bradautomates/claude-video/releases/tag/v0.2.0)
- Research date: 2026-08-09

## Resolution

The Codex-native watch skill should preserve the upstream release's user-visible contract, not its implementation: one public URL or local video plus an optional question; captions before Whisper; four detail modes; bounded, time-grounded visual sampling; focused ranges and transcript-cue frames; a transparent report; actionable warnings and partial-result behavior; no redundant work on follow-ups; and explicit cleanup and data-flow disclosures. Host-specific Claude mechanics, automatic package installation, token estimates, packaging, and internal Python structure are not parity requirements.

Every MUST below is phrased as an observable acceptance case. It can therefore be implemented independently without copying or adapting upstream code or tests.

## Research boundary and evidence

This inventory treats the immutable commit above as authoritative. It cross-checks four first-party surfaces:

- The canonical skill contract and published README describe the intended user and agent behavior. [Contract overview][skill-overview] [Published workflow][readme-workflow]
- The changelog identifies the v0.2.0 delta and security fixes inherited from earlier releases. [v0.2.0 changelog][changelog-v020] [Inherited security fixes][changelog-security]
- The upstream tests assert configuration, setup, mode routing, sampling coverage, deduplication, timestamp cues, caption request bounds, and Whisper chunk behavior. [Test inventory][readme-tests]
- The GitHub release associates `v0.2.0` with the pinned commit and publishes `watch.skill` as its artifact. [Release page](https://github.com/bradautomates/claude-video/releases/tag/v0.2.0) [Release workflow][release-workflow]

Verification performed for this report:

- Checked out the exact tag/commit in detached state.
- Downloaded the official `watch.skill` asset. Its SHA-256 was `e889b727724f0ff3fef9a72c4561f38065b81f4eb61b36b3d38710d934043c8f` on 2026-08-09.
- Unpacked the artifact and compared it recursively with the pinned `skills/watch/` tree; there was no content difference.
- Ran the complete upstream no-network suite on macOS with Python 3.13.3 and ffmpeg/ffprobe available: **71 tests passed**.
- Inspected the command help and structured setup report. No live third-party video download or Whisper upload was performed, so provider availability, current yt-dlp extractor compatibility, account limits, and real network performance are not claimed as verified.

The upstream source and tests were read only to derive requirements and black-box cases. This report contains no upstream implementation code, and a later implementation must not copy or adapt that code or its test bodies.

## Classification rule

- **MUST parity** means an outcome, safety property, disclosure, or interaction that a v0.2.0 user can observe and should still receive from the Codex-native skill.
- **Codex adaptation candidate** means the outcome matters, but the mechanism or exact value is Claude-specific, unsafe under Codex permissions, or needs product calibration.
- **Explicitly out of scope** means it is not part of the behavioral promise for the first independent Codex implementation.

## MUST parity surface and acceptance cases

### 1. Request and accepted-input contract

| ID | Required behavior | Independent black-box acceptance case | Primary evidence |
|---|---|---|---|
| IN-01 | Accept one video source as either an HTTP(S) URL supported by yt-dlp or a local path. The optional natural-language question is separated from the source before invoking the runtime. | Give the skill a URL with query parameters plus a question, then a local path containing spaces plus a question. In both cases the runtime receives one unchanged source value and the final answer addresses the question. | [Skill input contract][skill-inputs] [README inputs][readme-inputs] |
| IN-02 | If no question is supplied, produce a useful summary rather than asking the user to restate the request. | Invoke with only a source. The final response synthesizes structure, key moments, visuals, and spoken content with timestamps. | [Answer contract][skill-answer] |
| IN-03 | Treat URL acquisition as one video, not a playlist expansion. Only public, unauthenticated source access is promised. | Stub acquisition for a playlist-like URL and verify the request disables playlist traversal. Verify no cookies, login, or account session is requested. | [Downloader behavior][download-url] [Security contract][skill-security] |
| IN-04 | Resolve `~` and relative local paths to an absolute file; fail clearly when the path does not exist. Known video suffixes are accepted, while an unknown suffix warns and is still probed. | Exercise a known video, a playable video with an unusual suffix, and a missing file. Expect success, warning-plus-attempt, and a non-zero actionable failure respectively. | [Local input behavior][download-local] |
| IN-05 | Prevent option injection through the source. A leading-hyphen string is not treated as a URL, URL arguments are separated from yt-dlp options, and local paths passed to media tools are absolute. | Use a source beginning with `-` and a URL containing shell metacharacters. Verify neither becomes a command option or a second shell command, and no subprocess is invoked through a shell string. | [Security changelog][changelog-security] [URL classification][download-local] |
| IN-06 | Use an automatically created per-run temporary working directory unless the caller supplies an explicit output directory. Surface the chosen directory. | Run once without and once with an output directory. Verify artifacts stay under the reported directory and the supplied path is expanded and resolved. | [Runtime work directory][watch-workdir] [Invocation flags][skill-flags] |

### 2. Setup, preferences, and configuration

| ID | Required behavior | Independent black-box acceptance case | Primary evidence |
|---|---|---|---|
| SET-01 | Preflight requires `ffmpeg`, `ffprobe`, and `yt-dlp`. A missing Whisper key is encouraged but is not permanently blocking when the user deliberately opts out. | Test the matrix of all binaries present/missing, key present/missing, and setup marker present/missing. Binaries missing must block; a keyless completed setup must proceed. | [Setup state contract][skill-setup] [Setup tests][test-setup] |
| SET-02 | First-run status is structured; subsequent healthy checks are silent. Do not repeatedly announce successful setup. | On first run, verify the report exposes status, ability to proceed, first-run marker, missing binaries, provider/key state, config path, selected detail, and platform. After completion, verify the fast check exits successfully with empty stdout/stderr. | [Structured preflight][skill-setup-structured] [Setup implementation contract][setup-status] |
| SET-03 | A user may decline Whisper. That choice is remembered, the run continues with native captions or frames, and the user is not nagged again. | Complete setup without a key, run the silent check twice, and verify both succeed silently. For a captionless input, verify a frames-only limitation is disclosed. | [Keyless setup behavior][skill-setup] [Keyless regression tests][test-setup] |
| SET-04 | Default detail is `balanced`. Effective detail precedence is explicit request, then process environment, then user config, then default. Unsupported configured values fall back to `balanced`; the pinned release also tolerates a whitespace-delimited inline comment in an unquoted config value. | Cover all precedence layers, an invalid value, a bare configured value, and a value followed by a whitespace/comment. Assert the selected detail shown in the report. | [Config resolution][config-source] [Config tests][test-config] [Pinned fix](https://github.com/bradautomates/claude-video/commit/83da59fa78c3eee9e20f515fe75c438bb5166efd) |
| SET-05 | Secret configuration is created with owner-only permissions; existing secrets are not overwritten. Loose group/world readability produces a remediation warning. | Create a new config and assert mode `0600`; rerun setup with sentinel values and assert they survive; loosen permissions and assert a `chmod 600` warning without printing secret values. | [Setup file behavior][setup-config] [Security contract][skill-security] |
| SET-06 | Setup failures give platform-appropriate, actionable remediation and never use sudo automatically. | With dependency discovery stubbed, verify macOS identifies Homebrew, Linux identifies apt/dnf/pipx, Windows identifies winget/pip, and an unknown platform requests manual installation. | [Installer behavior][setup-install] |

### 3. Acquisition, captions, and transcription

| ID | Required behavior | Independent black-box acceptance case | Primary evidence |
|---|---|---|---|
| TR-01 | For URL inputs, check metadata and native captions before downloading media. Request manual and auto-generated VTT captions using the bounded English pattern, not every translated track. | Capture the yt-dlp argument vector for metadata-only and media acquisition. Assert manual plus auto captions, VTT conversion, English-only language tokens, and no playlist. | [Caption acquisition][download-captions] [Caption-bound regression tests][test-download] |
| TR-02 | Prefer native captions over Whisper. When a captioned URL runs in transcript detail without cue timestamps, do not download video. | Return a valid VTT from the caption probe and assert there is no media download or Whisper request, zero frames, and transcript source `captions`. | [Transcript-detail behavior][skill-detail] [Published acquisition order][readme-workflow] |
| TR-03 | A local file has no platform-caption probe or automatic sidecar-subtitle discovery; when it has audio, transcription therefore starts at the optional Whisper fallback. | Run a local clip with an adjacent subtitle file and a mocked provider. Assert the sidecar is not silently consumed as v0.2.0 parity, the provider is used when enabled, and keyless/disabled operation is frames-only. | [Runtime acquisition routing][watch-captions] [Transcription contract][skill-transcription] |
| TR-04 | Normalize captions into timestamped segments: ignore markup, collapse consecutive rolling duplicates/extensions, and preserve source-relative times. | Feed independently authored VTT fixtures containing tags, repeated rolling cues, and extended cues. Assert clean, ordered segments with merged time spans and timestamped display lines. | [Caption normalization behavior][transcribe-source] |
| TR-05 | When captions are absent and audio exists, fall back to Whisper unless disabled. Groq `whisper-large-v3` is preferred; OpenAI `whisper-1` is secondary; an explicit provider selection only uses that provider's matching key. | Mock both keys and assert Groq wins by default. Force each provider and verify only its endpoint/model/key is used. Force a provider whose key is absent and expect a clear limitation rather than silently sending the other key. | [Transcription contract][skill-transcription] [Provider selection][whisper-config] |
| TR-06 | `--no-whisper` disables only the Whisper fallback; native captions still work. If neither captions nor Whisper yields text, frame modes continue frames-only and transcript detail explains that it has no visual fallback. | Run captioned and captionless cases with Whisper disabled. The first still includes captions; the second returns frames-only, while transcript detail returns zero frames and recommends a visual mode. | [Failure handling][skill-failures] [Report fallback][watch-report-transcript] |
| TR-07 | Do not invoke Whisper when the media has no audio. | Probe a silent local clip and verify there is no provider request, the run continues visually, and the no-audio limitation is visible. | [Runtime transcription routing][watch-transcription] |
| TR-08 | Whisper input is extracted audio only: mono, 16 kHz, 64 kbps MP3. The video itself is never uploaded. | Inspect the media-tool invocation and provider multipart request. Assert exactly one audio file is sent, no video bytes/path are included, and upload occurs only after captions are absent and Whisper is enabled. | [Transcription contract][skill-transcription] [Security disclosure][skill-security] |
| TR-09 | Audio that would exceed the provider upload limit is split below a 24 MiB working ceiling, transcribed in contiguous chunks, and stitched back to absolute source timestamps. | Mock a 71 MiB/one-hour audio asset. Assert three contiguous chunks, shifted segment timestamps, chronological concatenation, and no per-request payload above the ceiling. | [v0.2.0 chunking release note][changelog-v020] [Chunk tests][test-whisper] |
| TR-10 | A failed Whisper chunk does not discard successful chunks. All chunks failing yields no transcript and a clear failure. | Make one of multiple mocked chunks fail, then all chunks fail. Expect surviving segments plus a visible chunk-failure diagnostic in the first case and a handled no-transcript result in the second. | [Failure contract][skill-failures] [Chunk failure tests][test-whisper] |
| TR-11 | Transcript focus filtering includes segments that overlap the requested range and keeps their original absolute timestamps. | Use segments before, across, inside, and after a range. Assert the three overlapping/inside cases remain and displayed times are not rebased to zero. | [Focus transcript contract][skill-focus] [Range filtering][transcribe-source] |

### 4. Detail modes, frame selection, and budgets

| ID | Required behavior | Independent black-box acceptance case | Primary evidence |
|---|---|---|---|
| FR-01 | `transcript` produces no ordinary frames. Captioned URLs can finish without media download; cue timestamps are the one exception and produce cue-only frames. | Run transcript detail with captions, without captions, and with two cue timestamps. Expect 0, 0, and 2 cue frames respectively, subject to valid timestamps. | [Detail contract][skill-detail] [Mode-routing tests][test-watch] |
| FR-02 | `efficient` is the fast keyframe tier with a default cap of 50. If fewer than four useful keyframes are found, it falls back to duration-aware uniform sampling. | Use an independently generated cut-heavy clip and a static/long-GOP clip. Assert keyframe reasons and cap in the first; uniform fallback and at least one frame in the second. | [Detail engines][skill-detail] [Frame tests][test-frames] |
| FR-03 | `balanced` is the default scene-aware tier with a cap of 100. It detects across the full range and falls back to uniform sampling for effectively static footage. | Use cut-heavy, over-cap, and static clips. Assert scene selection, full-range temporal coverage after capping, and uniform fallback for the static case. | [Detail engines][skill-detail] [Coverage tests][test-frames] |
| FR-04 | `token-burner` uses the same scene-aware behavior but has no default frame cap. It does not show the capped-mode sparse-scan warning. | Generate more than 100 distinct scene candidates. Assert more than 100 can survive, no long sparse warning appears solely because duration exceeds ten minutes, and a high-token warning appears only after 250 selected frames. | [Limits][skill-limits] [Runtime warnings][watch-warnings] |
| FR-05 | `--max-frames N` replaces the mode cap and must be greater than zero. Cue frames reserve slots before ordinary detail frames. | Set a lower cap in efficient, balanced, and token-burner modes. Assert total cue plus detail frames never exceeds it, pinned cues survive, and zero/negative values fail before extraction. | [Flag contract][skill-flags] [Runtime validation][watch-args] |
| FR-06 | Sampling never exceeds 2 fps, including a caller override. Full-video budgets are duration-aware: approximately 12–30 through 30 seconds, 40 through one minute, 60 through three minutes, 80 through ten minutes, and the capped-mode ceiling beyond ten minutes. These are targets for uniform sampling and report budgeting, not a promise that scene selection returns exactly that count. | Exercise durations immediately around 30, 60, 180, and 600 seconds plus a requested fps above 2. Assert the reported target changes at the boundaries, actual uniform rate stays at or below 2, and scene results remain bounded by the mode cap. | [Budget contract][skill-limits] [Budget implementation contract][frames-budgets] |
| FR-07 | Capped candidate sets are thinned across the whole range rather than taking the first N; first and last candidates survive when at least two are selected. | Create a clip with more candidates than the cap and assert ordered output reaches the final portion of the clip. | [Published sampling rule][readme-detail] [Coverage regression tests][test-frames] |
| FR-08 | Near-duplicate removal is on by default for ordinary detail-engine frames and runs before the cap; `--no-dedup` disables it. Observable intent is to collapse held/static visuals while retaining meaningful small changes. | Use a static clip, a held-slide clip with one small text change, and distinct cuts. Assert one/few, both changed states, and all distinct states survive respectively; then disable dedup and assert repeated samples remain. The test must assert outcomes, not reproduce the upstream algorithm. | [Dedup behavior][readme-dedup] [Dedup tests][test-dedup] |
| FR-09 | Extracted frames preserve aspect ratio, do not upscale beyond the requested width, default to 512 px maximum width, and report the applied size bound. | Probe a small landscape, tall portrait, and large frame at default and 1024 requests. Assert aspect ratio and bounded dimensions, and verify the report describes the applied bound. | [Published frame behavior][readme-workflow] [Frame report][watch-report] |
| FR-10 | Every emitted frame has an absolute timestamp, chronological position, path, and selection reason sufficient to align it with speech. | Mix ordinary and cue frames and assert the merged report is chronological and reasons distinguish first/scene/uniform/keyframe/transcript-cue selections. | [Frame-reading contract][skill-answer] [Report rendering][watch-report] |

### 5. Focus ranges and transcript-cue timestamps

| ID | Required behavior | Independent black-box acceptance case | Primary evidence |
|---|---|---|---|
| FOC-01 | `--start` and `--end` accept seconds, `MM:SS`, and `HH:MM:SS`, including fractional seconds. Start must be non-negative, end must be greater than start when both are present, and start cannot be at/past known duration. | Cover every accepted notation plus malformed, negative-start, reversed/equal, and past-end-start cases. Invalid inputs fail with the offending field and expected format/correction. | [Focus flag contract][skill-flags] [Time parsing and validation][frames-time] [Runtime validation][watch-args] |
| FOC-02 | Supplying either boundary enables focused mode, filters the transcript to overlapping segments, and keeps frame/report timestamps absolute. | Test start-only, end-only, and bounded range. Assert focus metadata is printed, selected evidence is in range, and a source event at 2:15 remains `2:15`, not `0:00`. | [Focus behavior][skill-focus] [Runtime focus routing][watch-focus] |
| FOC-03 | Focused mode allocates denser targets, still capped at 2 fps and by the selected detail mode: up to roughly 10 frames through 5 seconds, 30 through 15, 60 through 30, 80 through 60, and the mode cap thereafter. | Exercise boundary durations under balanced and efficient modes. Assert target density increases relative to a full scan without crossing 2 fps or the 100/50 caps. | [Focused budgets][skill-focus] [Budget implementation contract][frames-budgets] |
| CUE-01 | `--timestamps` accepts comma-separated absolute times in all supported formats, trims blanks, sorts, and removes duplicates; malformed values fail. | Pass mixed, repeated, blank, unordered, and malformed tokens. Assert one ordered unique cue per valid time and an actionable parse error for malformed input. | [Cue contract][skill-cues] [Cue parsing tests][test-timestamps] |
| CUE-02 | Cue frames are additive to ordinary detail frames, merged chronologically, and labeled `transcript-cue`. Under transcript detail they are the only frames. | Run balanced plus two cues and transcript plus two cues. Assert scene plus cue reasons in the first and cue reasons only in the second. | [Cue behavior][skill-cues] [Mode-routing tests][test-watch] |
| CUE-03 | Cue frames are pinned and counted before ordinary frames. If cues alone exceed a finite cap, they are spread across the requested cue list with first and last retained. | Request five cues with a three-frame cap. Assert exactly three cue frames containing the earliest and latest valid requests, and no ordinary frame evicts them. | [Cue behavior][skill-cues] [Cue cap tests][test-timestamps] |
| CUE-04 | Focus windows drop cues outside the inclusive range, report the drop count, and keep source-absolute coordinates. | Request cues below, inside, and above a focus range. Assert only the in-range cue is emitted and both stderr/status and report summarize two drops. | [Cue behavior][skill-cues] [Cue focus tests][test-timestamps] |
| CUE-05 | Transcript-cue selection is a model judgment based on deictic language, not a blind phrase match. | Give a transcript with a true visual direction and a rhetorical use of “look.” Verify the agent selects only the visually grounded moment and explains why a second pass is useful. | [Cue workflow][skill-cues] |

### 6. Runtime report and user answer

| ID | Required behavior | Independent black-box acceptance case | Primary evidence |
|---|---|---|---|
| REP-01 | Produce a readable Markdown run report containing source; optional title/uploader; duration; optional focus range; optional source resolution/codec; effective detail; frame/candidate/fallback/dedup/cap summary; cue summary; transcript source/count; evidence sections; and work directory. | Run URL-metadata, local, focused, fallback, dedup, cue, and no-transcript fixtures. Assert applicable fields appear and inapplicable optional fields do not fabricate values. | [Runtime report][watch-report] |
| REP-02 | List every selected frame path in chronological order with absolute time and reason, and tell the agent to inspect every frame. A no-frame run says so explicitly. | Compare report entries with generated files and assert a one-to-one match, ordered timestamps, and no missing or invented file. | [Frame report][watch-report] [Skill frame loop][skill-answer] |
| REP-03 | Identify transcript provenance as native captions, Groq Whisper, OpenAI Whisper, or none. Focused transcripts say they were filtered. | Mock each source and a no-source case; assert an unambiguous provenance label and focus qualifier. | [Evidence streams][skill-answer] [Runtime report][watch-report] |
| REP-04 | The runtime may surface the timestamped transcript to the agent, but the user-facing answer synthesizes it. Do not paste the full transcript by default, including transcript detail; offer raw text only when explicitly requested. | Ask for a summary in transcript detail and verify a structured summary with relevant timestamps and minimal quotation. Ask explicitly for raw transcript and verify that separate path is allowed. | [Answer contract][skill-answer] |
| REP-05 | Answer the user's specific question directly from both available evidence streams, using timestamps. If there is no question, summarize. Do not imply visual certainty when only a transcript exists or speech certainty when only frames exist. | Use frame-only, transcript-only, and combined fixtures with deliberately conflicting/missing facts. Assert the answer scopes claims to evidence and cites the supporting times. | [Evidence and answer contract][skill-answer] |
| REP-06 | A long-video or high-frame warning printed by the runtime is acknowledged in the user answer with the relevant mitigation. | Trigger each warning and assert the final response mentions sparse coverage plus a focused rerun, or high image cost plus a narrower/capped rerun. | [Failure-handling contract][skill-failures] [Runtime warnings][watch-warnings] |

### 7. Warnings, failures, and partial results

| ID | Required behavior | Independent black-box acceptance case | Primary evidence |
|---|---|---|---|
| ERR-01 | Full-video `efficient` or `balanced` runs over 600 seconds warn that coverage is sparse and recommend focus or token-burner. Transcript, focused, and token-burner runs do not receive that capped-mode warning. | Test 600 and 601 seconds across the mode/focus matrix. Expect the warning only for an unfocused capped visual run over 600 seconds. | [Limits contract][skill-limits] [Runtime warnings][watch-warnings] |
| ERR-02 | More than 250 selected frames under token-burner produces a high image-token warning. | Test exactly 250 and 251 selected frames. Expect the warning only for 251. | [Limits contract][skill-limits] [Runtime warnings][watch-warnings] |
| ERR-03 | A URL download is considered usable when media exists even if subtitle acquisition makes yt-dlp exit non-zero; no media file is a hard failure that includes the tool exit context. | Stub a non-zero acquisition with and without a playable output. The first continues; the second exits once with an actionable error. | [Download failure behavior][download-url] |
| ERR-04 | Login-required, private, unavailable, or region-locked media fails plainly and is not retried in a loop or bypassed with cookies/account access. | Return representative yt-dlp failures. Assert one acquisition attempt, preserved diagnostic context, and a user-facing access limitation. | [Failure contract][skill-failures] [Security contract][skill-security] |
| ERR-05 | Caption parse failure is non-fatal: log the parse problem, then try the allowed fallback. Missing captions plus missing/failed Whisper yields frames-only, not a fabricated transcript. | Supply malformed VTT with and without a provider key. Assert fallback routing, explicit provenance, and no text invented from metadata. | [Runtime caption handling][watch-captions] [Failure contract][skill-failures] |
| ERR-06 | Media-tool discovery/probe/extraction failures are blocking and name the failed dependency or operation. Already-created working data remains identifiable for safe cleanup. | Remove each dependency from discovery and inject ffprobe/frame/audio failures. Assert non-zero termination, cause, remediation, and a known work path. | [Media failure behavior][frames-time] [Whisper media behavior][whisper-media] |
| ERR-07 | Whisper retries transient network/server errors within a finite policy, does not retry ordinary client errors, respects rate-limit guidance, and ultimately degrades to a partial/no-transcript result instead of hanging forever. | Mock non-429 4xx, 429 with retry guidance, 5xx, timeout, and connection reset. Assert bounded attempts/delay handling and final partial-result behavior. Exact retry numbers may be independently implemented if the externally visible bound remains documented. | [Whisper request behavior][whisper-request] [Failure contract][skill-failures] |
| ERR-08 | A focus range with a caption file but no overlapping lines reports that fact, distinguishing it from “captions unavailable.” | Give valid captions wholly outside the range and assert the report says no lines fell in range rather than recommending API setup. | [Runtime transcript report][watch-report-transcript] |
| ERR-09 | Cue timestamps outside focus are counted and disclosed. Cue extraction failures/out-of-media requests do not create phantom frame entries. | Mix out-of-window, beyond-duration, and valid cues. Assert only existing files are listed and out-of-window requests are counted. The beyond-duration diagnostic is a known gap requiring a Codex decision below. | [Cue extraction behavior][frames-cues] |

### 8. Follow-ups and cleanup

| ID | Required behavior | Independent black-box acceptance case | Primary evidence |
|---|---|---|---|
| LIFE-01 | A follow-up about the same video in the same task reuses frames and transcript already in context rather than downloading, extracting, or transcribing again. | Complete one run, ask a factual follow-up, and assert zero new acquisition/provider/media-tool calls. | [Token/follow-up contract][skill-followups] |
| LIFE-02 | Preserve the working directory while follow-ups are likely; otherwise remove only that exact run directory after evidence has been consumed. | Ask an immediate follow-up and verify files remain. End the analysis and verify the reported run directory is removed without affecting siblings, user-supplied media, or config. | [Cleanup contract][skill-cleanup] [Security contract][skill-security] |
| LIFE-03 | An explicit output directory means the files are intentionally retained unless the user asks for cleanup; cleanup must never delete the source video. | Run against a local source with an explicit output directory, finish, and verify the output policy is stated and the source remains untouched. | [Output flag][skill-flags] [Runtime work directory][watch-workdir] |

### 9. Security and data-flow disclosures

| ID | Required behavior | Independent black-box acceptance case | Primary evidence |
|---|---|---|---|
| SEC-01 | Disclose that yt-dlp contacts the supplied public host and that ffmpeg/ffprobe process media locally. | Before the first network/command approval, present the host and local-tool actions in plain language. | [Security disclosure][skill-security] |
| SEC-02 | Disclose that only extracted audio may be sent to Groq or OpenAI, only after captions are unavailable and Whisper is enabled. Never upload the full video. | Instrument all outbound requests for captioned, captionless, disabled-Whisper, and forced-provider cases. Assert the documented conditions and payload type. | [Security disclosure][skill-security] |
| SEC-03 | Provider credentials are isolated: a Groq key goes only to Groq and an OpenAI key only to OpenAI. Keys never appear in stdout, stderr, reports, command arguments, filenames, or cached work artifacts. | Use distinct sentinel keys and scan commands, logs, reports, and artifacts after success and every failure path. Assert each sentinel appears only in its authorized request header. | [Security disclosure][skill-security] [Provider routing][whisper-config] |
| SEC-04 | Persist only the chosen user config and per-run work artifacts. Warn about insecure secret-file permissions and identify cleanup responsibility. | Snapshot allowed locations before/after setup and a run. Assert changes are limited to the selected config location and run directory, then verify cleanup. | [Security disclosure][skill-security] [Setup file behavior][setup-config] |
| SEC-05 | Do not use platform accounts, cookies, login sessions, posting actions, or credential sharing. | Run an access-controlled URL and assert a clear unsupported-access result with no cookie flags, browser-session extraction, or posting side effects. | [Security disclosure][skill-security] |

## Codex adaptation candidates

These items need an explicit host/product decision. They must not be inherited accidentally as “parity.”

| Candidate | Upstream behavior to inventory | Codex-native decision needed |
|---|---|---|
| Invocation and triggering | The release is presented as `/watch`, has Claude-oriented frontmatter, and separately advertises Agent Skills installation. [Skill metadata][skill-overview] [Install surfaces][readme-install] | Choose the real Codex entry contract (`$watch`, implicit video prompt, or both) and independently specify how source, question, and flags are parsed. Slash-command parity itself is not required. |
| Frame inspection tool | The contract tells Claude to `Read` every JPEG, preferably in parallel. [Frame-reading contract][skill-answer] | Map this to the Codex image-inspection capability available in the target app, and forward-test that every listed frame is actually viewed before answering. |
| First-run questions | The contract names `AskUserQuestion` and prescribes a Claude-specific option presentation. [Setup preferences][skill-setup-preferences] | Use Codex-native user-input UX. Preserve the choices and remembered opt-out, but follow the host's interaction constraints and do not collect secrets in chat if a safer path exists. |
| Package installation | macOS setup automatically runs Homebrew when tools are missing. [Installer behavior][setup-install] | Codex should explain the exact packages and request narrow approval before mutating the system or using network access. Auto-install without approval is not parity. |
| Secret/config storage | Upstream uses `~/.config/watch/.env`, process variables, and as a fallback the current directory's `.env`. [Provider selection][whisper-config] | Decide whether Codex permits a home-directory config, uses environment-only/keychain-backed credentials, and whether project `.env` fallback is safe. Preserve provider isolation and permission checks regardless of path. |
| Network approvals | Upstream assumes direct yt-dlp and provider network access. | Align each source-host and optional transcription request with Codex sandbox/approval behavior. A stored key should not silently broaden network access. |
| Caption language | The v0.2.0 downloader intentionally requests English caption variants only; tests guard against an unbounded `all` request. [Caption tests][test-download] | Either preserve English-only behavior and disclose it, or deliberately supersede it with a bounded user-language policy. Do not claim multilingual parity without acceptance cases. |
| Image sizing and token budgets | Upstream defaults to 512 px width, clamps height to 1998 px for Claude Read, and publishes Anthropic token estimates. [Published frame behavior][readme-workflow] [Measured modes][readme-detail] | Retain bounded/aspect-correct images, but calibrate width, height, caps, and warning thresholds against Codex image limits and context cost. Record any intentional deviation. |
| Report transport | The runtime prints a full Markdown report and transcript for Claude's context. [Runtime report][watch-report] | Decide whether Codex should consume stdout directly, a report file, or structured output. Preserve provenance and fields, and escape untrusted metadata so a title/uploader cannot inject misleading Markdown/instructions. |
| Cleanup primitive | Upstream instructs the agent to remove the work directory with recursive deletion. [Cleanup contract][skill-cleanup] | Use a validated, run-owned directory and the safest available deletion mechanism. Never interpolate an unresolved variable or delete a broad/user-supplied path. |
| Platform scope | Upstream describes macOS, Linux, and Windows, with a Windows interpreter exception. [Setup contract][skill-setup] | The parent specification targets macOS Desktop. Treat other operating systems as later compatibility work unless the product scope expands. |
| Packaging and install location | The release ships Claude plugin, Codex plugin, Agent Skills, and claude.ai surfaces. [Repository structure][readme-structure] | Choose repo skill, personal skill, or plugin in the separate host-contract decision. Behavioral acceptance must run from the selected real install location. |

## Explicitly out of scope

- Copying, translating, porting, or structurally imitating upstream Python, shell scripts, tests, function boundaries, command construction, or algorithms. The MIT license does not supersede this project's independent-reimplementation requirement.
- Exact Claude Code plugin metadata, marketplace commands, SessionStart hook behavior, `allowed-tools`, `AskUserQuestion`, `/watch` command plumbing, claude.ai upload UX, or the upstream `.skill` build script.
- Reproducing Anthropic image-token formulas, published benchmark times, or the 1998 px Claude Read limit as fixed Codex requirements. They are calibration evidence only.
- Authenticated/private-account video access, cookies, session extraction, paywall/DRM bypass, region bypass, posting, likes, comments, or any platform write.
- Playlist traversal or automatic multi-video note creation. The upstream downloader explicitly selects one item even though the README describes a manual “run it across a series” use case. [Downloader behavior][download-url] [Usage examples][readme-inputs]
- Uploading a full video to Groq, OpenAI, or any other model/provider.
- Returning the entire raw transcript by default. It is opt-in output only.
- Persistent media libraries, note-taking destinations, cross-task caches, background monitoring, or automatic retention beyond the current task.
- Guaranteed support for every site yt-dlp has ever supported, every unusual local container, or current third-party extractor stability. The contract is best-effort support with clear failure.
- Linux/Windows release parity in the first macOS Desktop delivery, unless the parent issue expands scope.
- Local sidecar subtitle discovery, translation, diarization, OCR, object tracking, or semantic scene understanding beyond what the selected frames and transcript let the model infer.

## Newly surfaced questions and fog

These are decision inputs, not reasons to copy upstream behavior blindly.

1. **Transcript-first cue rerun has a cache contradiction.** The contract recommends a transcript pass followed by cue timestamps against the downloaded local file, but a captioned URL in transcript mode intentionally downloads no video. Decide whether the second pass should reuse the URL, acquire the video into the same run, or have a first-pass option that retains media. [Transcript detail][skill-detail] [Cue workflow][skill-cues]
2. **`--no-whisper` documentation conflicts.** The implementation/contract use it to disable only Whisper; one README line describes “disable transcription entirely.” Native captions still remain active. The Codex contract should say “disable Whisper fallback” consistently. [Flag contract][skill-flags] [README flags][readme-flags]
3. **Cue frames bypass near-duplicate removal.** Published prose says dedup runs on every frame mode, while cue frames are independently extracted and merged after ordinary-frame dedup. Decide whether intentional pinned cues should always survive or identical cues should collapse. [Dedup behavior][readme-dedup] [Cue extraction][frames-cues]
4. **Range validation is incomplete at the observable boundary.** The release validates negative start, reversed bounded ranges, and start past duration, but does not clearly reject negative end-only values, end past duration, non-positive fps/resolution, negative cue times, or cues past media duration. Define fail-fast behavior and messages. [Runtime validation][watch-args] [Cue extraction][frames-cues]
5. **Focused extraction is under-tested.** Upstream tests cover cue-window filtering and parsing but do not assert ordinary frame extraction at start/end boundaries, transcript overlap edges, or end-past-duration reporting. Independent acceptance needs those fixtures. [Cue tests][test-timestamps] [Frame tests][test-frames]
6. **Keyless setup completion is split between script and agent.** The installer only marks setup complete when a key exists, while the skill tells the agent to write the marker after a deliberate keyless choice. Make one Codex-owned state transition authoritative and test it. [Setup preferences][skill-setup-preferences] [Installer behavior][setup-install]
7. **Secret handling needs a Codex policy.** Reading a project `.env` can unexpectedly select a provider key, and writing a key supplied in chat into a home file may not be acceptable. Decide environment/keychain/config precedence and whether per-provider audio-upload consent is required. [Provider selection][whisper-config] [Security disclosure][skill-security]
8. **English-only captions may surprise users.** The bounded request avoids hundreds of translated tracks, but no visible warning says other languages were skipped. Decide bounded locale negotiation and disclosure before broadening behavior. [Caption tests][test-download]
9. **Cleanup ownership is ambiguous on failure and follow-up.** The agent guesses whether follow-ups are likely, and blocking failures can occur after the directory is created but before the footer report. Define a run manifest/known path, failure cleanup, explicit retention, and safe expiry. [Runtime work directory][watch-workdir] [Cleanup contract][skill-cleanup]
10. **Warnings are contract-only in several paths.** The 71-test suite does not assert long-video warning boundaries, token-burner warning boundaries, user-answer acknowledgment, permission warnings, or login/region failure wording. Those need new independent tests rather than trust in prose.
11. **Third-party behavior drifts.** Setup installs current ffmpeg and yt-dlp, and no live provider test is in the upstream suite. Decide minimum versions, compatibility checks, and separately gated live smoke tests. [First run][readme-first-run] [Test scope][readme-tests]
12. **Release packaging contains a dev-only builder.** The official asset exactly matches `skills/watch/`, including `scripts/build-skill.sh`, even though scan-ignore metadata calls that script development-only. A Codex artifact should contain only what its selected install surface needs. [Build script][build-skill] [Skill scan ignore][skill-ignore]
13. **Untrusted metadata enters Markdown.** Source, title, uploader, captions, and provider errors are external data. The release prints them into a report without an explicit escaping/trust boundary. The Codex report should treat all of them as evidence, never instructions, and prevent Markdown/control-sequence spoofing. [Runtime report][watch-report]
14. **Partial Whisper success is not visibly labeled in the final report.** Failed chunks are noted on stderr, while the report only shows a segment count/provider. Decide whether the report and user answer must say “partial transcript” and name missing intervals. [Chunk behavior][whisper-chunks] [Failure contract][skill-failures]

## Independent acceptance-suite gate

The implementation ticket should not reuse upstream test code. It should author fresh fixtures and test only the observable contract above.

Minimum release gate:

1. **Offline contract suite:** independently synthesize cut-heavy, static, held-slide-with-small-change, portrait, long-duration metadata, silent, and audio clips. Mock yt-dlp and transcription HTTP at process/request boundaries. Cover every `IN`, `SET`, `TR`, `FR`, `FOC`, `CUE`, `REP`, `ERR`, `LIFE`, and `SEC` case.
2. **Clean-room audit:** reviewer confirms no upstream implementation/test source was copied, translated, or used as a scaffold; only this requirements inventory and first-party behavior links inform the implementation.
3. **Local Codex end-to-end smoke:** from the actual installed skill location, analyze a local synthetic video, inspect every emitted frame through the Codex image path, answer with timestamps, ask a follow-up without rerunning, then verify safe cleanup.
4. **Public caption smoke:** with explicit network approval, use a stable public captioned URL. Verify captions-first behavior, transcript detail without video download, provenance, and a focused visual rerun. Preserve raw acquisition evidence without claiming all yt-dlp sites work.
5. **Captionless/provider smoke:** separately opt in to Groq and/or OpenAI using disposable/restricted credentials. Verify audio-only upload disclosure, provider isolation, forced-provider behavior, and secret non-disclosure. A provider smoke is not required for frames-only local use, but it is required before claiming that provider works.
6. **Failure/approval smoke:** deny network, dependency install, home-config write, and provider upload in turn. Each denial must leave a truthful partial result or actionable stop, no secret leakage, and a safely identifiable work directory.
7. **Calibration gate:** record Codex-specific image cost/quality results before freezing resolution and frame caps. Any deviation from the v0.2.0 values must be an explicit parent decision, not an accidental implementation change.

## Source index

[build-skill]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/scripts/build-skill.sh#L1-L38
[changelog-security]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/CHANGELOG.md#L29-L45
[changelog-v020]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/CHANGELOG.md#L5-L27
[config-source]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/scripts/config.py#L17-L74
[download-captions]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/scripts/download.py#L44-L95
[download-local]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/scripts/download.py#L17-L41
[download-url]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/scripts/download.py#L115-L172
[frames-budgets]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/scripts/frames.py#L122-L159
[frames-cues]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/scripts/frames.py#L295-L390
[frames-time]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/scripts/frames.py#L42-L119
[readme-dedup]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/README.md#L67-L78
[readme-detail]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/README.md#L80-L96
[readme-first-run]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/README.md#L153-L173
[readme-flags]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/README.md#L191-L201
[readme-inputs]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/README.md#L31-L51
[readme-install]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/README.md#L98-L151
[readme-structure]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/README.md#L208-L242
[readme-tests]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/README.md#L228-L242
[readme-workflow]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/README.md#L43-L65
[release-workflow]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/.github/workflows/release.yml#L1-L30
[setup-config]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/scripts/setup.py#L35-L163
[setup-install]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/scripts/setup.py#L166-L350
[setup-status]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/scripts/setup.py#L217-L297
[skill-answer]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/SKILL.md#L183-L191
[skill-cleanup]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/SKILL.md#L183-L193
[skill-cues]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/SKILL.md#L207-L220
[skill-detail]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/SKILL.md#L195-L205
[skill-failures]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/SKILL.md#L232-L238
[skill-flags]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/SKILL.md#L132-L152
[skill-focus]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/SKILL.md#L154-L181
[skill-followups]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/SKILL.md#L240-L247
[skill-inputs]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/SKILL.md#L108-L140
[skill-limits]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/SKILL.md#L114-L130
[skill-overview]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/SKILL.md#L1-L16
[skill-security]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/SKILL.md#L249-L266
[skill-setup-preferences]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/SKILL.md#L78-L106
[skill-setup-structured]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/SKILL.md#L88-L106
[skill-setup]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/SKILL.md#L39-L86
[skill-transcription]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/SKILL.md#L221-L230
[skill-ignore]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/.skillignore#L1-L3
[test-config]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/tests/test_config.py#L7-L37
[test-dedup]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/tests/test_dedup.py#L42-L162
[test-download]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/tests/test_download.py#L1-L64
[test-frames]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/tests/test_frames.py#L9-L70
[test-setup]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/tests/test_setup.py#L39-L80
[test-timestamps]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/tests/test_timestamps.py#L11-L87
[test-watch]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/tests/test_watch.py#L25-L85
[test-whisper]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/tests/test_whisper.py#L16-L157
[transcribe-source]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/scripts/transcribe.py#L14-L89
[watch-args]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/scripts/watch.py#L25-L81
[watch-captions]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/scripts/watch.py#L90-L138
[watch-focus]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/scripts/watch.py#L140-L169
[watch-report-transcript]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/scripts/watch.py#L310-L383
[watch-report]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/scripts/watch.py#L268-L387
[watch-transcription]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/scripts/watch.py#L230-L267
[watch-warnings]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/scripts/watch.py#L319-L334
[watch-workdir]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/scripts/watch.py#L83-L95
[whisper-chunks]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/scripts/whisper.py#L350-L465
[whisper-config]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/scripts/whisper.py#L29-L112
[whisper-media]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/scripts/whisper.py#L115-L198
[whisper-request]: https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/skills/watch/scripts/whisper.py#L232-L329
