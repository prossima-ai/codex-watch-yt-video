# Provenance

This record identifies what was inspected for the documentation contract. It
does not turn static, hermetic, or documentation evidence into a claim of live
host, source, provider, approval, or cleanup behavior.

## Claim classification

All material provenance claims use these labels:

- `confirmed` — a named recorded evidence source exists, with its scope stated.
- `implementation requirement` — specified or implemented behavior not yet
  qualifyingly live-verified.
- `unsupported/out of scope` — intentionally excluded v0.1 behavior.

## Decision #44 implementation evidence record

**Classification: implementation requirement. Evidence:** the pinned
`origin/main` base, Decision #44's approved contract, and local worktree
inspection. This is a live-evidence and release-status record, not authorization
for a caption request, provider request, deployment, publication, or release.

| Record | Value | Boundary |
| --- | --- | --- |
| Governing decision | [Decision #44](https://github.com/prossima-ai/codex-watch-yt-video/issues/44) | It approves the fail-closed direct native-caption contract and release gates; it does not approve a live action. |
| Pinned implementation base | `35a0c29bc9e264f533837adf40424aa95e55dcc1` | Canonical `origin/main` base for this implementation workflow and the squash commit from PR #45. |
| Implementation commit | `af11d98c59c0b42046f70a277b63457719bedf14` | Intentional local-only implementation commit on `codex/issue-44-direct-native-captions`; no push, PR, issue comment, label, release, provider, or live-media action occurred. |
| Documentation and code changes | `recorded` | Adds the sealed receipt/network/fetch seams and hermetic coverage; updates the normative specification, public safety/setup/readme/notices, domain vocabulary, and release gates. The implementation binds receipts; validates public HTTPS and DNS; pins numeric addresses; fails closed on redirects and response caps; redacts sensitive caption URLs; retains typed outcomes; and removes release-facing transcription providers. |
| Focused and complete validation | `PASS` | Baseline before edits: `python3 -m unittest discover -s tests` — 192 tests, exit 0. Final focused caption suites: 51 tests, exit 0. Complete suite: `python3 -B -m unittest discover -s tests -p 'test_*.py' -q` — 227 tests, exit 0. See exact commands below. |
| Standards review | `PASS — no unresolved findings` | Independent complete-diff review against `AGENTS.md`, domain docs, architecture, safety, tests, documentation, and maintainability; every actionable finding below was resolved and re-reviewed. |
| Spec review | `PASS — no unresolved findings` | Independent complete-diff review against Decision #44, this specification, the implementation request, and authorization/release gates; every actionable finding below was resolved and re-reviewed. |
| Transcription disablement | `PASS — release surface disabled` | `prepare_metadata.py` and `prepare_visual.py` use `release_transcription_providers()`, which returns no providers; tests prove no release-facing transcription choice, credential read, provider client, or direct-caption fallback. The provider-effective-size gate remains unresolved. |
| Live public-caption validation | `BLOCKED` | No separate explicit human approval has been granted for one named public-caption run. Hermetic tests cannot replace it. |
| Provider validation | `BLOCKED` | No human has selected one provider, no conservative effective complete-request-size limit has been accepted, and no separate provider approval has been granted. |
| Release gate status | `BLOCKED` | Missing controls/evidence are: one separately approved live public-caption run with adequate sanitized evidence; conservative provider-specific complete-request-size limits; selected-provider validation under separate approval; and an explicit human release decision. |
| Human release decision | `PENDING` | No human decision has been requested or received. A human must review this evidence and explicitly record either `Approved for the specifically defined release scope` or `Blocked`, with exact missing evidence or controls. |

No live caption retrieval, live caption validation, transcription, provider
credential read, provider request, provider validation, deployment, publication,
or release occurred while creating this record. A future live public-caption
approval applies only to the named one run; a future provider approval is a
separate gate and cannot be inferred from it.

### Local validation commands and limits

All listed commands ran in the isolated Decision #44 worktree on 2026-08-15 and
exited `0`.

- Baseline before edits: `python3 -m unittest discover -s tests` — **192 tests**.
- Focused native-caption implementation: `python3 -B -m unittest tests.test_caption_network tests.test_caption_evidence -v` — **51 tests**.
- Complete required repository suite: `python3 -B -m unittest discover -s tests -p 'test_*.py' -q` — **227 tests**.
- Syntax/static package inputs: `python3 -B -m compileall -q .agents/skills/watch/scripts tests`.
- Whitespace/formatting guard: `git diff --check 35a0c29bc9e264f533837adf40424aa95e55dcc1`.
- Skill package/discovery validation: `python3 /Users/ashishpratapsingh/.codex/skills/.system/skill-creator/scripts/quick_validate.py .agents/skills/watch` — `Skill is valid!`.

Repository inspection found no project lint, formatter, type-check, package, or
CI manifest beyond these standard-library tests and the repository-owned skill
validator, so no absent tool was represented as having run. These are hermetic
or static checks: they do not prove live DNS, public-host behavior, redirect
behavior, media compatibility, Codex Desktop discovery, provider behavior, or a
release.

### Independent review findings and resolutions

Both reviews inspected the full diff from the pinned base independently. The
following findings were resolved with repository evidence before the final
re-reviews reported no unresolved findings.

- **Standards:** known receipts were not burned for malformed/mismatched follow-ups; the runtime now invalidates the known receipt before every rejected use and tests its replay refusal.
- **Standards and Spec:** unsafe native-caption routes could be treated as no captions and offer transcription; the runtime now returns a sanitized caption-policy outcome that blocks every transcription/provider path, with a never-called provider fixture.
- **Standards:** `CONTEXT.md` omitted the caption-network action/receipt and still described active transcription; the canonical vocabulary now names the action and release-disabled transcription.
- **Standards:** dataclass representations could expose signed caption URLs; candidates, probes, and selections now retain sealed `CaptionResource` objects with a redacted representation, and snapshot/repr tests cover them.
- **Standards:** redirect-failure audit records could falsely say zero redirects; the bounded fetch error now carries only a safe numeric count, including a runtime same-origin-loop regression.
- **Standards:** a shorter-than-declared response could parse as a caption; final EOF must now equal a valid declared length, and a valid-but-truncated VTT fails as typed transport failure.
- **Spec:** early receipt/control/workspace failures, direct-caption visual continuation, error-category distinctions, and receipt expiry/replay boundaries were incomplete; explicit lifecycle, typed-outcome, controllable-clock, and visual-resume tests now cover them.
- **Spec:** response read/close failures and nonzero `yt-dlp` metadata diagnostics could render sensitive URL material; response lifecycle errors map to safe transport failures and nonzero `yt-dlp` output is classified but never rendered.
- **Spec:** the original `http.client` response framing and inherited `urllib` opener path could miss delayed bytes or close before definitive EOF; the sealed `urllib.request` handler now issues only a fixed direct GET, retains the raw response for bounded EOF checks, rejects altered request shape, and never forwards caller credentials/cookies.

Final Standards and Spec reviews each reported `PASS — no unresolved findings`.

## Historical Issue #29 implementation and specification record

**Classification: confirmed. Evidence:** historical fresh canonical-main fetch
on 2026-08-14 and local `git rev-parse HEAD` in the dedicated Issue #29 worktree.
This section is retained as the #29 record, not as the Decision #44 starting
point; the Decision #44 table above is authoritative for this workflow.

| Record | Value | Boundary |
| --- | --- | --- |
| Inspected implementation base | `0f1f224e818f52853d4d9e8356abf7be14c172a1` | This is the pinned canonical-main revision inspected before documentation edits, not the future documentation commit. |
| Specification revision | `858b139873aeff3b22a7338acbd14511078f0b33` | Latest revision that changed `docs/spec/watch-skill.md` at the inspected base. |
| Approval record | [Issue #13](https://github.com/prossima-ai/codex-watch-yt-video/issues/13) | The approved implementation-ready specification. |
| Documentation/security decision | [Issue #9](https://github.com/prossima-ai/codex-watch-yt-video/issues/9#issuecomment-5249321562) | Required companion documents, claim classifications, notices, provenance, and disclosure boundary. |

## Parity and independent-reimplementation boundary

**Classification: confirmed. Evidence:** [upstream v0.2.0 release](https://github.com/bradautomates/claude-video/releases/tag/v0.2.0), [pinned reference tree](https://github.com/bradautomates/claude-video/tree/83da59fa78c3eee9e20f515fe75c438bb5166efd), Issue #9 resolution, and the repository's `CONTEXT.md` terminology.

The fixed parity snapshot is `bradautomates/claude-video` v0.2.0 at
`83da59fa78c3eee9e20f515fe75c438bb5166efd`. It is a behavioral-parity
reference, not an implementation source. Independent reimplementation means the
new implementation was written for the Codex host contract; no upstream
implementation, tests, or assets were copied. The upstream project is
MIT-licensed, but no upstream material is bundled or redistributed here.

## Available evidence runs and inspection environment

**Classification: confirmed. Evidence:** commands run in the Issue #29
documentation worktree on 2026-08-14, plus the named hermetic tests merged in
PRs #41–#43.

- `python3 --version` recorded Python 3.13.3.
- `ffmpeg -version` and `ffprobe -version` recorded FFmpeg/ffprobe 9.0 with
  `--enable-gpl` and `--enable-version3`; that observed build is GPL-3.0-or-later
  and is an inspection environment only, not a supported minimum.
- The #26–#28 hermetic evidence includes answerability/citation grounding,
  provider-consent/credential-isolation, and fail-closed manual-installation
  fixtures. It proves only those offline fixture/code paths.
- No live Desktop probe, personal installation, source acquisition, media run,
  provider request, provider-retention probe, sandbox approval probe, or cleanup
  probe was performed to create this record.

The full component source and license boundary is in
[third-party notices](../THIRD_PARTY_NOTICES.md). Static records above do not
prove a user's runtime, tool installation, provider account, or media result.

## Intentional deviations from the parity snapshot

**Classification: implementation requirement. Evidence:**
[watch specification sections 6–7](spec/watch-skill.md#6-deterministic-evidence-runtime)
and the canonical skill instructions.

- ordinary 768 px JPEG frames are the baseline visual evidence form;
- targeted 1024 px escalation is permitted only through the typed
  `FrameInspector` boundary when a material small-text or fine-detail question
  remains unresolved; and
- visual observations are read in chronological batches of at most eight.

These are specified implementation choices. This record does not claim a live
calibration or source-media exercise for them.

## Notices, license, and clean-room review status

**Classification: confirmed. Evidence:** [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md), Issue #9 resolution, and repository inspection at the pinned base.

v0.1 is private and unlicensed for redistribution. `THIRD_PARTY_NOTICES.md`
records non-bundled host tool/provider service terms and the upstream reference
boundary; it includes full license text only if a future distribution actually
requires it.

Clean-room review status: the independent-reimplementation boundary was checked
against the pinned parity reference, the approved specification, and the current
repository tree. The record finds no upstream implementation, tests, or assets
copied into this repository. This is a source-review statement, not an external
legal opinion or a claim about all future contributions.

## Remaining live/release gates

**Classification: implementation requirement. Evidence:** specification
[section 13](spec/watch-skill.md#13-verification-records-and-release-gate) and
the documented provider-size discrepancy.

The remaining live/release gates are:

- Desktop/package/authority checks on the target macOS Codex Desktop host;
- one separately approved public-caption run for the Decision #44 direct action,
  with sanitized host/redirect validation, bounded byte count, typed outcome, and
  proof that transcription/provider code did not run;
- a conservative provider-specific effective complete-request-size limit before
  any provider is offered for a release. It must include multipart/form-data
  boundaries, per-part headers, metadata, and all other request-body overhead,
  not merely nominal media-file size; then a human-selected provider, a separate
  validation plan, and separate explicit human approval immediately before that
  provider activity; and
- a release record that captures current provider documentation, source/tool
  versions, live outcomes, approval records, independent reviews, and immutable
  release revision, followed by an explicit human decision for the stated scope.

An unavailable authorization, source, provider, or evidence record is `BLOCKED`
or `UNVERIFIED`, never a pass. The unselected provider must not be marketed as
live-verified.

## Future immutable release record

**Classification: implementation requirement. Evidence:** specification
[sections 12–13](spec/watch-skill.md#12-required-companion-documentation-and-provenance).

This document records the pinned implementation revision inspected above. A
future immutable release commit does not exist yet and must be recorded only when
a release record exists; this document deliberately makes no self-referential
commit claim.

Neither the upstream project nor OpenAI, Groq, or other providers endorse or are affiliated with this project.
