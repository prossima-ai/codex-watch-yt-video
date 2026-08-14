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
| Implementation commit | `PENDING — final local implementation commit has not yet been created` | Do not substitute a branch name, worktree HEAD, or an invented hash. Root records the intentional local commit only after final validation and reviews. |
| Documentation and code changes | `PENDING root final validation` | The final record must name the direct-caption receipt, URL policy, redirects, redaction, byte cap, typed outcomes, no-fallback path, and transcription-disablement changes actually present in the final diff. |
| Focused and complete validation | `PENDING root final validation` | Record exact commands, exit status, test count, static/package/skill checks, and any environment-limited checks after the final diff exists. |
| Standards review | `PENDING root final validation` | An independent review must inspect the complete diff from the pinned base and record every finding and resolution. |
| Spec review | `PENDING root final validation` | A separate independent review must inspect Decision #44, this specification, the prompt contract, and the complete diff. |
| Transcription disablement | `PENDING root final validation` | Final evidence must show the release-facing action surface cannot read provider credentials, invoke provider clients, or route direct-caption outcomes into transcription. |
| Live public-caption validation | `BLOCKED` | No separate explicit human approval has been granted for one named public-caption run. Hermetic tests cannot replace it. |
| Provider validation | `BLOCKED` | No human has selected one provider, no conservative effective complete-request-size limit has been accepted, and no separate provider approval has been granted. |
| Human release decision | `PENDING` | A human must review the completed evidence and record either the specifically defined approved scope or the exact blockers. No decision has been made here. |

No live caption retrieval, live caption validation, transcription, provider
credential read, provider request, provider validation, deployment, publication,
or release occurred while creating this record. A future live public-caption
approval applies only to the named one run; a future provider approval is a
separate gate and cannot be inferred from it.

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
