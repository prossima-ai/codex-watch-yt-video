# Media and transcription constraints

- Ticket: [#3 — Research media dependencies and transcription constraints](https://github.com/killer-block-coder-95/codex-watch-yt-video/issues/3)
- Researched: 2026-08-09
- Scope: facts that constrain a future Codex Desktop skill for watching and analyzing YouTube videos. This report does not specify or implement the skill.
- Source policy: primary documentation from yt-dlp, FFmpeg, Homebrew, Groq, and OpenAI only. OpenAI claims use official OpenAI documentation only.

## Resolution summary

The portable baseline is a caption-first workflow with an audio-transcription fallback. A complete YouTube fallback path needs the `yt-dlp`, `ffmpeg`, and `ffprobe` executables; current yt-dlp also strongly recommends `yt-dlp-ejs` plus a supported JavaScript runtime for full YouTube support. Homebrew can install yt-dlp and FFmpeg on supported macOS, but package installation and all media/API network calls remain subject to the Codex sandbox and approval configuration.

The two candidate transcription providers are not interchangeable:

- OpenAI recommends `gpt-transcribe` for ordinary completed-file transcription, accepts only uploads up to 25 MB, and requires `whisper-1` when word or segment timestamps are required. Its current input-format list excludes FLAC and OGG.
- Groq exposes OpenAI-compatible transcription and translation endpoints with `whisper-large-v3` and `whisper-large-v3-turbo`. It accepts FLAC and OGG, exposes word and segment timestamps on both listed transcription models, and has plan-dependent file-size and audio-usage limits. Groq documents that only the first audio track in a multi-track file is transcribed.

No reviewed provider document states a universal maximum audio duration. Limits must therefore be enforced by measured bytes and the caller's current account limits, not by a guessed minute count. Long recordings need deterministic chunking and timestamp-offset reconciliation. Provider selection, timestamp precision, chunk policy, fallback consent, credential handling, and cleanup must be explicit specification decisions.

## Confirmed facts

### 1. Local media toolchain

#### yt-dlp runtime and installation

- When installed as Python software, yt-dlp supports CPython 3.10+ and PyPy 3.11+. Its official macOS standalone executable supports macOS 10.15+. Official release binaries and `pip` are first-party installation paths; Homebrew is listed as a third-party package-manager path and may lag upstream. ([yt-dlp README: release files and dependencies](https://github.com/yt-dlp/yt-dlp/blob/master/README.md#release-files), [yt-dlp installation wiki](https://github.com/yt-dlp/yt-dlp/wiki/Installation))
- yt-dlp says `ffmpeg`, `ffprobe`, `yt-dlp-ejs`, and a supported JavaScript runtime or engine are highly recommended. `ffmpeg` and `ffprobe` are required for merging separate audio/video streams and post-processing. `yt-dlp-ejs` is required for full YouTube support, and needs a runtime such as Deno (recommended), Node.js, Bun, or QuickJS. The required FFmpeg dependency is the executable, not the same-named Python package. ([yt-dlp dependencies](https://github.com/yt-dlp/yt-dlp/blob/master/README.md#dependencies))
- `-x`/`--extract-audio` requires both `ffmpeg` and `ffprobe`. yt-dlp can produce `aac`, `alac`, `flac`, `m4a`, `mp3`, `opus`, `vorbis`, or `wav` audio, or retain the best available format. `--ffmpeg-location` may identify an executable or its containing directory. ([yt-dlp post-processing options](https://github.com/yt-dlp/yt-dlp/blob/master/README.md#post-processing-options))
- yt-dlp's stable release can become stale when sites change. The project currently recommends its nightly channel to regular users and warns when a version is more than 90 days old. Update mechanics differ by install method: release binaries support `yt-dlp -U`; Homebrew installations use `brew upgrade yt-dlp`. ([yt-dlp update policy](https://github.com/yt-dlp/yt-dlp/blob/master/README.md#update), [installation wiki](https://github.com/yt-dlp/yt-dlp/wiki/Installation))
- yt-dlp loads user and system configuration files unless told otherwise. `--ignore-config` stops loading additional configuration files. Its maintainers warn integrations not to parse normal stdout, which may change; they recommend structured mechanisms such as `-J`, `--print`, and `--progress-template`. ([yt-dlp configuration](https://github.com/yt-dlp/yt-dlp/blob/master/README.md#configuration), [embedding guidance](https://github.com/yt-dlp/yt-dlp/blob/master/README.md#embedding-yt-dlp))

#### Captions and subtitle formats

- Manual captions and automatically generated captions are separate operations: `--write-subs` and `--write-auto-subs`. `--list-subs` lists available tracks without downloading the video unless simulation is overridden. Subtitle languages may be selected with exact tags or regular expressions. ([yt-dlp subtitle options](https://github.com/yt-dlp/yt-dlp/blob/master/README.md#subtitle-options))
- Subtitle format preferences can be expressed as a fallback sequence such as `ass/srt/best`. yt-dlp can convert downloaded subtitles to ASS, LRC, SRT, or WebVTT. ([yt-dlp subtitle and conversion options](https://github.com/yt-dlp/yt-dlp/blob/master/README.md#subtitle-options))
- yt-dlp treats live chat as a subtitle track. The documented exclusion is `--sub-langs all,-live_chat`. ([yt-dlp differences in default behavior](https://github.com/yt-dlp/yt-dlp/blob/master/README.md#differences-in-default-behavior))
- A caption track's existence, language tags, and format depend on the extractor result for the individual video. yt-dlp documents that some extracted metadata fields are not guaranteed to be present. ([yt-dlp output-template field caveat](https://github.com/yt-dlp/yt-dlp/blob/master/README.md#output-template))

#### FFmpeg and ffprobe

- `ffmpeg` is the converter/transcoder. It can explicitly select streams with `-map`, omit video with `-vn`, set an output sampling rate with `-ar`, and set channel count with `-ac`. ([FFmpeg command documentation](https://ffmpeg.org/ffmpeg.html))
- `ffprobe` reports container and stream information in machine-readable forms including JSON. It returns a positive exit code when an input cannot be opened or recognized as media. ([ffprobe documentation](https://ffmpeg.org/ffprobe.html))
- Supported containers and codecs vary with how FFmpeg was built and which external libraries were enabled. The authoritative runtime checks are the installed binary's `-formats` and `-codecs` output. ([FFmpeg general documentation](https://www.ffmpeg.org/general.html))

### 2. macOS and Homebrew

- Homebrew's supported-install requirements currently include Apple Silicon or 64-bit Intel, macOS Sonoma 14 or newer on officially supported hardware, and Xcode Command Line Tools or Xcode. Catalina 10.15 through Ventura 13 are described as unsupported but possibly functional; Mojave 10.14 and older cannot run current Homebrew. Default prefixes are `/opt/homebrew` on Apple Silicon and `/usr/local` on Intel macOS. ([Homebrew installation requirements](https://docs.brew.sh/Installation))
- The Homebrew formula commands are `brew install yt-dlp` and `brew install ffmpeg`. At the research date, the yt-dlp formula lists Deno and Python among its dependencies but does not list FFmpeg; Homebrew documents FFmpeg with its own install command. Bottle availability is OS/architecture-specific and should be checked on the current formula pages rather than copied into a permanent requirement. ([Homebrew yt-dlp formula](https://formulae.brew.sh/formula/yt-dlp), [Homebrew FFmpeg formula](https://formulae.brew.sh/formula/ffmpeg))
- Codex executes package managers and other spawned commands inside the active sandbox. In the usual `workspace-write`/`on-request` configuration, it asks before using the internet or writing outside the workspace; command network access is off by default unless enabled. ([OpenAI sandbox documentation](https://learn.chatgpt.com/docs/sandboxing), [OpenAI agent approvals and security](https://learn.chatgpt.com/docs/agent-approvals-security))

### 3. OpenAI file transcription

#### Endpoint, models, formats, and size

- The completed-file endpoint is `POST /v1/audio/transcriptions`. OpenAI currently recommends `gpt-transcribe` for ordinary transcription in the recording's original language. Specialized models are required for speaker labels, word timestamps, subtitle formats, or translation to English. ([OpenAI file-transcription guide](https://developers.openai.com/api/docs/guides/speech-to-text))
- Uploads are limited to 25 MB. Supported inputs are `mp3`, `mp4`, `mpeg`, `mpga`, `m4a`, `wav`, and `webm`; FLAC and OGG are not in the documented OpenAI list. For larger recordings, OpenAI says to compress or split into chunks of 25 MB or less and warns against splitting in the middle of a sentence because context and accuracy may be lost. ([OpenAI file-transcription guide: longer inputs](https://developers.openai.com/api/docs/guides/speech-to-text#longer-inputs))
- `gpt-transcribe` accepts free-form context plus keyword and multiple-language hints. Its current model page lists file and streamed-file transcription support, the `/v1/audio/transcriptions` endpoint, a price of $0.0045 per audio minute, no Free-tier support, and usage-tier-dependent request/token limits. These commercial and quota figures are current values, not stable interface guarantees. ([OpenAI GPT Transcribe model](https://developers.openai.com/api/docs/models/gpt-transcribe))

#### Timestamp, diarization, translation, and streaming constraints

- Word and segment timestamps through `timestamp_granularities[]` are currently supported only by `whisper-1`, with `response_format=verbose_json`. ([OpenAI file-transcription guide: timestamps](https://developers.openai.com/api/docs/guides/speech-to-text#timestamps))
- Speaker labeling uses `gpt-4o-transcribe-diarize` with `response_format=diarized_json`. Audio longer than 30 seconds requires `chunking_strategy=auto` or a voice-activity-detection configuration. Up to four known speakers can be supplied using 2–10 second reference clips. ([OpenAI file-transcription guide: speaker diarization](https://developers.openai.com/api/docs/guides/speech-to-text#speaker-diarization))
- Translation of a completed recording into English uses `/v1/audio/translations` with `whisper-1`. Ordinary transcription preserves the source language. ([OpenAI file-transcription guide: translations](https://developers.openai.com/api/docs/guides/speech-to-text#translations))
- File-result streaming is supported by `gpt-transcribe`, the existing GPT-4o transcription models, and the diarization model. `whisper-1` does not stream file transcription. This differs from Realtime transcription, which is intended for audio that is still arriving. ([OpenAI file-transcription guide: streaming](https://developers.openai.com/api/docs/guides/speech-to-text#streaming-transcriptions))

#### Credentials, rate failures, and data handling

- OpenAI API keys are bearer credentials and must be treated as secrets. OpenAI says to load them from a server-side environment variable or key-management service and not expose them in client-side code. ([OpenAI API authentication](https://developers.openai.com/api/reference/overview#authentication))
- Limits vary by model and organization/project usage tier. A temporary rate limit returns HTTP 429 and may include `Retry-After`; OpenAI recommends following that value or using bounded exponential backoff with jitter. Billing, spend, and quota 429 variants require user action and should not be retried as if temporary. ([OpenAI rate-limit guide](https://developers.openai.com/api/docs/guides/rate-limits), [OpenAI error codes](https://developers.openai.com/api/docs/guides/error-codes))
- OpenAI's current endpoint table says `/v1/audio/transcriptions` data is not used for training, has no abuse-monitoring retention, has no application-state retention, and is eligible for Zero Data Retention. This endpoint-specific row is more specific than the platform's general statement that many API endpoints retain abuse-monitoring logs for up to 30 days. ([OpenAI data controls](https://platform.openai.com/docs/models/default-usage-policies-by-endpoint))

### 4. Groq file transcription

#### Endpoint, models, formats, and size

- Groq exposes OpenAI-compatible endpoints at `https://api.groq.com/openai/v1/audio/transcriptions` and `https://api.groq.com/openai/v1/audio/translations`. The current speech-to-text models are `whisper-large-v3` and `whisper-large-v3-turbo`. Groq positions V3 for accuracy-sensitive multilingual work and Turbo for price/performance. ([Groq speech-to-text guide](https://console.groq.com/docs/speech-to-text))
- Groq documents an overall maximum file size of 25 MB on the Free tier and 100 MB on the Developer tier. A direct attachment is capped at 25 MB; the documented path for a larger file is the `url` parameter. Groq does not document a universal maximum duration on this page. ([Groq speech-to-text guide: audio limitations](https://console.groq.com/docs/speech-to-text#working-with-audio-files))
- Accepted file/URL types are `flac`, `mp3`, `mp4`, `mpeg`, `mpga`, `m4a`, `ogg`, `wav`, and `webm`. Only the first audio track in a multi-track file is transcribed. Response formats are `json`, `verbose_json`, and `text`; SRT and WebVTT are not listed as native response formats. ([Groq speech-to-text guide](https://console.groq.com/docs/speech-to-text))
- Both segment and word timestamp granularities are documented when `response_format=verbose_json`. The verbose response also includes fields such as average log probability, compression ratio, and no-speech probability that can assist diagnosis. ([Groq speech-to-text guide: request parameters](https://console.groq.com/docs/speech-to-text#using-the-api))
- Groq down-samples audio to 16 kHz mono before transcription. It recommends client-side 16 kHz mono conversion for very large inputs and FLAC for lossless size reduction. For files beyond the relevant limit, its guide recommends overlapping chunks and reconciliation of the overlap. ([Groq speech-to-text guide: preprocessing and larger files](https://console.groq.com/docs/speech-to-text#audio-preprocessing))
- The minimum accepted audio length is 0.01 seconds, but each request is billed for at least 10 seconds. ([Groq speech-to-text guide: audio limitations](https://console.groq.com/docs/speech-to-text#working-with-audio-files))

#### Credentials, rate failures, and data handling

- Groq's examples pass a bearer token from `GROQ_API_KEY`. Its key-management page says keys must be kept safe, and only team owners or users with the developer role can create or manage them. ([Groq API reference](https://console.groq.com/docs/api-reference), [Groq API keys](https://console.groq.com/keys))
- Groq rate limits apply at organization level. Audio models can be limited by requests per minute/day and audio seconds per hour/day; the exact current organization limits are available in the Console. Rate-limit responses use HTTP 429 and may include `retry-after`; request-too-large failures use HTTP 413. Server-side 500/502/503 responses are described as retryable after a wait, while 401/403 require credential or permission correction. ([Groq rate limits](https://console.groq.com/docs/rate-limits), [Groq error codes](https://console.groq.com/docs/errors))
- Groq says usage metadata is always retained but excludes customer inputs and outputs. Inference customer data is not retained by default, but inputs and outputs may be logged for reliability or abuse investigation for up to 30 days. All customers may enable Zero Data Retention; where customer data is retained, Groq says it is stored in US Google Cloud buckets. ([Groq data controls](https://console.groq.com/docs/your-data))
- Groq's current services agreement says Inputs and Outputs may not be used to train or fine-tune models unless the customer explicitly grants permission or instructs Groq to do so. ([Groq services agreement](https://console.groq.com/docs/legal/services-agreement))

## Specification implications

Everything in this section is an inference from the confirmed facts above, not a provider guarantee.

| Later specification decision | Evidence-bound implication |
| --- | --- |
| Dependency contract | Require executable preflight for `yt-dlp`, `ffmpeg`, and `ffprobe`; also surface whether yt-dlp reports a usable EJS/JavaScript runtime. Do not treat a Python package named `ffmpeg` as satisfying the dependency. |
| Installation behavior | Offer human-readable install guidance, but do not silently run Homebrew. Installation writes outside the repo and needs network access, so it can cross the default Codex boundary. Preserve a non-Homebrew yt-dlp path for macOS 10.15–13, where current Homebrew is unsupported. |
| Reproducible yt-dlp invocation | Use `--ignore-config` so a user's global yt-dlp flags cannot silently alter output, paths, authentication, or download behavior. Consume structured JSON/`--print` output rather than human stdout. Capture the executable version in diagnostics. |
| Caption precedence | Inspect available tracks first. Prefer an explicitly requested human caption language, then a documented automatic-caption fallback, then transcription. Exclude `live_chat`. Preserve whether text came from manual captions, automatic captions, or a provider transcript. |
| Caption normalization | Normalize caption cues to one internal structure with text, start/end time, language, and provenance. SRT or WebVTT are practical interchange formats because yt-dlp can convert to both, but the original track should be retained until parsing succeeds. |
| Audio-track selection | Select the intended audio language before upload and verify it with `ffprobe`; do not pass an arbitrary multi-track file to Groq because it will transcribe only the first track. The user-visible result should name the selected audio language or say it was unknown. |
| Provider-neutral upload artifact | A single fallback artifact cannot be FLAC or OGG if it must work unchanged with both providers. Use one of the shared documented formats (`mp3`, `mp4`, `mpeg`, `mpga`, `m4a`, `wav`, or `webm`) or transcode per provider. Measure the final file, not the source media, against the target limit. |
| Timestamp guarantee | Native caption cues are the least provider-dependent timestamp source. If captions are absent and word/segment timestamps are required, route OpenAI to `whisper-1` rather than the general `gpt-transcribe` model, or use Groq verbose JSON. A plain `gpt-transcribe` transcript cannot be advertised as word-timestamped. |
| Speaker labels | Keep diarization out of the default route. If requested, use OpenAI's diarization model with its chunking constraints and expose that speaker assignments are model output rather than verified identity. Groq's reviewed transcription guide documents timestamps, not speaker diarization. |
| Chunking | Preflight bytes and duration with `ffprobe`, then split before upload. Keep each OpenAI chunk at or below 25 MB; use the caller's actual Groq plan limit. Prefer boundaries near silence/sentence ends, preserve absolute offsets, and use small overlaps where the provider recommends them. De-duplicate overlap text without dropping timestamps. |
| Provider fallback | Do not silently send the recording to a second provider after a failure. The providers have different pricing, retention, geographic, and model behavior; fallback needs explicit configuration or user consent and must be visible in the report. |
| Remote URL uploads | Prefer direct upload. If Groq's URL path is supported later, require a trusted HTTPS source with bounded lifetime and document that it introduces another storage/access boundary. Do not expose local paths or long-lived credentials in a URL. |
| Credential handling | Read `OPENAI_API_KEY` or `GROQ_API_KEY` from the environment at call time. Never put secrets in skill text, command output, generated reports, filenames, URLs, or committed config. Missing/invalid credentials should produce setup guidance without probing other secrets. |
| Retry taxonomy | Retry boundedly only for temporary 429/5xx/network failures, following `Retry-After` where provided. Do not retry 401/403, oversized files, invalid formats, or quota/spend exhaustion unchanged. A partial chunk set must be reported as incomplete or discarded according to an explicit atomicity rule. |
| Temporary files and cleanup | Create per-run temporary storage, constrain filenames/paths, and delete downloaded media, converted audio, chunks, and cookie exports after success or failure unless the user explicitly asks to retain them. Retaining captions/transcripts for follow-up analysis is a separate product decision. |
| Output confidence | Never present provider text as an exact quote without traceable caption/transcript cues. Preserve caption type, language, provider/model, chunk coverage, warnings, and unavailable ranges so later summaries can distinguish evidence from model inference. |
| Release validation | Test against real current YouTube extraction because site changes can break a previously valid yt-dlp version. Forward-test provider schemas, file-size boundaries, timestamp offsets, rate-limit handling, and cleanup; documentation inspection alone does not prove runtime access or account entitlement. |

## Failure and validation matrix

| Condition to forward-test | Expected specification-level outcome |
| --- | --- |
| `yt-dlp` missing or too old for current YouTube | Stop before network work; name the missing/stale executable and give install/update guidance. |
| `ffmpeg` or `ffprobe` missing | Caption-only mode may proceed if it needs no post-processing; audio fallback must stop with precise dependency guidance. |
| No manual captions, automatic captions available | Use automatic captions only if the selected mode permits them; label provenance and language. |
| No usable caption track | Ask for or use the configured transcription provider; do not claim that captions were analyzed. |
| Private, age-restricted, geo-restricted, removed, or live input | Preserve yt-dlp's failure category where available. Never request or export browser cookies without an explicit authenticated-video workflow and approval boundary. |
| User yt-dlp config contains download or proxy flags | A skill invocation using `--ignore-config` should remain deterministic and confined to its run directory. |
| Multi-audio-track/dubbed source | Select and verify the intended track before upload; fail or warn when the language cannot be established. |
| OpenAI artifact is 25 MB or larger at the boundary | Verify whether “up to 25 MB” is inclusive in a live contract test; production logic should leave safety headroom rather than rely on exact decimal/binary boundary semantics. |
| Groq Free vs Developer account | Read/observe the caller's real entitlement; never infer a 100 MB allowance merely because the model page lists it. |
| Long audio crosses multiple chunks | The reconstructed transcript must have monotonic absolute timestamps, defined overlap de-duplication, full coverage accounting, and no duplicated report citations. |
| Temporary 429 | Respect `Retry-After` if present, apply bounded jittered backoff, and stop with an actionable rate-limit message when the retry budget is exhausted. |
| 401/403 or billing/quota failure | Do not retry; identify the provider and corrective user action without echoing the credential. |
| Provider 5xx or network interruption after some chunks | Apply bounded retry; then follow the specified partial-result atomicity rule and list uncovered time ranges. |
| Cleanup after success, failure, or cancellation | Temporary media and chunk files are removed; retained user-facing artifacts are explicitly listed. |

## Unknowns and fog

These questions are not resolved by the reviewed primary documentation and need an explicit decision or forward test:

1. **Maximum duration:** neither reviewed file-transcription guide states a provider-wide maximum duration. File bytes, plan limits, request limits, and practical transcription quality are known; a fixed maximum minute count is not.
2. **Exact size boundary:** “25 MB” is not defined as decimal vs binary units, nor is exact-boundary acceptance stated. Use headroom and test the real endpoint.
3. **Groq translation conflict:** Groq's model comparison says `whisper-large-v3-turbo` does not support translation, while the API reference lists both V3 and Turbo as available values for the translations endpoint. Treat Turbo translation as unsupported until Groq clarifies it or a forward test proves the current contract.
4. **OpenAI timestamp route vs quality route:** the recommended general model is `gpt-transcribe`, while timestamp granularities require `whisper-1`. The product must decide whether timestamps are mandatory, optional, or derived from chunk/caption boundaries.
5. **Caption language policy:** “best” language cannot be inferred safely for multilingual videos. The specification needs an explicit requested-language order and behavior when only auto-translated/automatic tracks exist.
6. **Audio language/dub selection:** the exact yt-dlp format-selection rule for YouTube dubbed audio should be tested on representative current videos; provider upload behavior alone cannot solve it.
7. **Cookie workflow:** browser-cookie access can unlock authenticated content but crosses a sensitive local-data boundary. Whether authenticated/private videos are in scope, and what approval/cleanup UX is required, remains undecided.
8. **Provider default and fallback consent:** cost, data location, retention controls, and account availability differ. The specification must choose no default, an explicit default, or per-run selection, and must define whether cross-provider fallback is ever allowed.
9. **Partial results:** the report needs an atomicity rule—fail the whole run, return clearly marked partial coverage, or allow resume from durable metadata.
10. **Temporary-artifact retention:** follow-up questions may benefit from keeping normalized captions/transcripts, but raw media and cookies raise privacy/storage risk. Retention duration and user control are not documented decisions yet.
11. **Supported platform floor:** the eventual skill may be macOS-first, cross-platform, or Homebrew-only. Current Homebrew supports macOS 14+, while yt-dlp's standalone macOS binary supports 10.15+; the project has not selected its minimum platform.
12. **Pinned versions and drift:** yt-dlp site compatibility, Homebrew formula versions, model aliases, prices, rate limits, and provider policies can change. The release process needs a freshness/forward-test cadence rather than copying the research-date values into permanent acceptance criteria.

## Primary source index

- [yt-dlp README](https://github.com/yt-dlp/yt-dlp/blob/master/README.md)
- [yt-dlp installation wiki](https://github.com/yt-dlp/yt-dlp/wiki/Installation)
- [FFmpeg command documentation](https://ffmpeg.org/ffmpeg.html)
- [ffprobe documentation](https://ffmpeg.org/ffprobe.html)
- [FFmpeg formats/codecs documentation](https://www.ffmpeg.org/general.html)
- [Homebrew installation requirements](https://docs.brew.sh/Installation)
- [Homebrew yt-dlp formula](https://formulae.brew.sh/formula/yt-dlp)
- [Homebrew FFmpeg formula](https://formulae.brew.sh/formula/ffmpeg)
- [OpenAI file-transcription guide](https://developers.openai.com/api/docs/guides/speech-to-text)
- [OpenAI GPT Transcribe model](https://developers.openai.com/api/docs/models/gpt-transcribe)
- [OpenAI API authentication](https://developers.openai.com/api/reference/overview#authentication)
- [OpenAI rate limits and errors](https://developers.openai.com/api/docs/guides/rate-limits)
- [OpenAI data controls](https://platform.openai.com/docs/models/default-usage-policies-by-endpoint)
- [OpenAI Codex sandbox](https://learn.chatgpt.com/docs/sandboxing)
- [OpenAI Codex approvals and security](https://learn.chatgpt.com/docs/agent-approvals-security)
- [Groq speech-to-text guide](https://console.groq.com/docs/speech-to-text)
- [Groq API reference](https://console.groq.com/docs/api-reference)
- [Groq rate limits](https://console.groq.com/docs/rate-limits)
- [Groq error codes](https://console.groq.com/docs/errors)
- [Groq data controls](https://console.groq.com/docs/your-data)
- [Groq services agreement](https://console.groq.com/docs/legal/services-agreement)
