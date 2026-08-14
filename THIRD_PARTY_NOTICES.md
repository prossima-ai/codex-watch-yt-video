# Third-party notices

This notice inventories only external tools and service references present in the
current Codex-native `watch` implementation. It does not grant permission to
download, install, redistribute, enable a provider, or use any listed component.

## Claim classification

Each material notice uses the repository-wide labels:

- `confirmed` — a named recorded source, code inspection, or dated official
  documentation observation exists; its boundary is part of the claim.
- `implementation requirement` — specified or implemented behavior not proven
  through a qualifying live verification.
- `unsupported/out of scope` — behavior not supplied or claimed by v0.1.

## Distribution boundary

**Classification: confirmed. Evidence:** historical Issue #29 inspection of the
pinned implementation base `0f1f224e818f52853d4d9e8356abf7be14c172a1` and the
repository tree on 2026-08-14. The Decision #44 implementation base is recorded
separately in [provenance](docs/provenance.md#decision-44-implementation-evidence-record).

This repository invokes host-provided tools and contains future-only external
provider service references; no third-party code, binary, or license text is bundled.
It therefore does not reproduce full upstream license texts. If a future release distributes a tool,
binary, package, source excerpt, asset, or other third-party material, that
release must determine and carry the required notices/license text before
distribution.

## Host tools and runtime

**Classification: implementation requirement. Evidence:** the runtime source
uses command names and Python standard-library imports; availability in another
host is not established by this record.

| Component | Direct role | Source and effective license boundary | Version / evidence boundary |
| --- | --- | --- | --- |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Contacts an approved public source host for metadata, subtitle inventory, and media work. The runtime directly retrieves a selected native-caption resource separately; see [security and privacy](docs/security-and-privacy.md#sources-and-local-processing). | The [source license](https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE) is Unlicense. The [upstream licensing note](https://github.com/yt-dlp/yt-dlp/blob/master/README.md#licensing) says some executable packaging forms add third-party terms, including GPLv3+ or ISC/MIT components. An end user's executable must be evaluated by its actual distribution form; this project does not claim every `yt-dlp` executable is solely Unlicense. | No `yt-dlp` executable version was captured for this documentation run; no supported minimum is asserted. |
| [FFmpeg](https://ffmpeg.org/) / `ffprobe` | Probes local/media streams and produces frames. Selected-track audio extraction is future-only and release-disabled with transcription. | [FFmpeg's license record](https://github.com/FFmpeg/FFmpeg/blob/master/LICENSE.md) describes a default LGPL-2.1-or-later source position; enabled GPL components can make a build GPL. The actual build configuration controls the effective license. | **Classification: confirmed. Evidence:** 2026-08-14 `ffmpeg -version` and `ffprobe -version` recorded version 9.0 with `--enable-gpl` and `--enable-version3`; that inspection build is GPL-3.0-or-later. It is an inspection environment only, not a supported minimum or a claim about any other FFmpeg build. |
| [Python](https://www.python.org/) standard library | The scripts directly import Python standard-library modules, including the bounded direct native-caption network implementation; no third-party Python package, requirement file, or lockfile is used by the current implementation. The direct action is separately receipt-gated and release-disabled pending live validation; see [security and privacy](docs/security-and-privacy.md#direct-native-caption-networking). | [Python's license](https://docs.python.org/3/license.html) is PSF-2.0 for Python software. A host Python distribution can include additional components outside this notice. | **Classification: confirmed. Evidence:** `python3 --version` on 2026-08-14 reported Python 3.13.3. This is an inspection environment only, not a supported minimum. |
| macOS Codex Desktop | Required host context for the private v0.1 skill. | Host product and operating-system terms are outside this repository; no host component is bundled. | **Classification: implementation requirement. Evidence:** [watch specification section 2](docs/spec/watch-skill.md#2-scope-and-explicit-non-goals). No host version was captured here. |

The FFmpeg observation is intentionally narrow: `--enable-gpl` and
`--enable-version3` appeared in the recorded 9.0 configuration. It is not a
universal FFmpeg licensing statement, nor proof that the tool works for a user
or that a media operation was performed.

## Provider services: future-only adapter targets and documentation observations

**Classification: confirmed. Evidence:** official provider documentation was
checked on 2026-08-14. Checked: 2026-08-14 is a date-bound documentation
observation, not a live transcription request, account-entitlement check,
provider-retention probe, provider enablement, or release authorization.

| Service | Future-only adapter target | Official documentation observation | Service/license boundary |
| --- | --- | --- | --- |
| OpenAI `whisper-1` | `https://api.openai.com/v1/audio/transcriptions` | The [model page](https://developers.openai.com/api/docs/models/whisper-1) and [speech-to-text guide](https://developers.openai.com/api/docs/guides/speech-to-text) list `whisper-1` for transcription, `verbose_json`, and timestamp granularities. The [data-controls table](https://developers.openai.com/api/docs/guides/your-data#default-usage-policies-by-endpoint) is the current endpoint-specific privacy/retention disclosure. | This is a hosted service governed by the [OpenAI Services Agreement](https://openai.com/policies/services-agreement/), not an open-source dependency distributed by this repository. |
| Groq `whisper-large-v3` | `https://api.groq.com/openai/v1/audio/transcriptions` | The [speech-to-text guide](https://console.groq.com/docs/speech-to-text) and [model page](https://console.groq.com/docs/model/whisper-large-v3) list the model and OpenAI-compatible endpoint. The [Your Data disclosure](https://console.groq.com/docs/your-data) says inference customer data is not retained by default but allows temporary reliability/abuse logs (up to 30 days unless ZDR) and records usage metadata; it is not accurate to say Groq never retains data. | This is a hosted service governed by the [Groq Services Agreement](https://console.groq.com/docs/legal/services-agreement), not an open-source dependency distributed by this repository. |

**Classification: implementation requirement. Evidence:** implementation
inspection of `.agents/skills/watch/scripts/watch_transcription.py` at the
pinned base and [the future provider gate](docs/spec/watch-skill.md#82-required-future-provider-gate).

The historical adapters configure a maximum audio chunk payload of 25,165,823
bytes (`24 * 1024 * 1024 - 1`) before multipart overhead. Current OpenAI
documentation states a 25 MB upload limit, and current Groq documentation states
25 MB for the free tier and 100 MB for the developer tier. This code has no
account-tier limit discovery, so it cannot truthfully promise that its ceiling is
below a 25,000,000-byte provider/account limit.

Transcription is release-disabled. Any future provider limit must be a
conservative provider-specific effective limit for the complete encoded request,
not merely nominal media-file size. It must include multipart/form-data
boundaries, per-part headers, field names, metadata, and every other request-body
overhead. A generic file-size cap is not provider-safety evidence. Before any
provider validation or enablement, a human must select exactly one provider,
review a provider-specific validation plan, and grant separate explicit human
approval immediately before that activity. This is an unresolved release gate,
not a verified provider capability; no provider validation, credential use, or
provider request occurred for this work.

Provider selection, fresh provider-specific audio-upload consent, and separate
provider-network approval remain future implementation requirements. Neither the
documentation check nor hermetic tests prove real endpoint acceptance, account
availability, provider behavior, retention, or audio upload.

## Behavioral-parity reference

**Classification: confirmed. Evidence:** [upstream v0.2.0 release](https://github.com/bradautomates/claude-video/releases/tag/v0.2.0), [pinned tree](https://github.com/bradautomates/claude-video/tree/83da59fa78c3eee9e20f515fe75c438bb5166efd), and [MIT license](https://github.com/bradautomates/claude-video/blob/83da59fa78c3eee9e20f515fe75c438bb5166efd/LICENSE).

`bradautomates/claude-video` v0.2.0 at
`83da59fa78c3eee9e20f515fe75c438bb5166efd` is an MIT-licensed behavioral-parity
reference only. This independent reimplementation does not bundle, copy, or
redistribute its code, tests, assets, or license text. Neither that upstream
project nor OpenAI, Groq, or any other provider endorses or is affiliated with
this project.

## Release record

**Classification: implementation requirement. Evidence:** [watch specification
section 13](docs/spec/watch-skill.md#13-verification-records-and-release-gate).

See [provenance](docs/provenance.md) for the pinned implementation revision,
recorded evidence, intentional deviations, and the remaining live/release gates.
Direct-caption retrieval and transcription are both release-disabled until their
separate hermetic, live-validation, and human-decision gates close.
