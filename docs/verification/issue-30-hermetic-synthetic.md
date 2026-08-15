# Issue #30 hermetic and synthetic qualification

This is a hash-only local evidence record for Issue #30. It qualifies the
offline H-01 through H-10 and local-synthetic S-01 through S-04 rows named in
the implementation guide. It does not claim Desktop discovery, host approval,
live media acquisition, DNS, a caption request, a provider request, a
credential read, live cleanup, owned-artifact deletion, or a release decision.

## Revisions and environment

| Item | Value |
| --- | --- |
| Pinned canonical base and specification | `dcf58a30090c56a9ee04addf4d706a5a85815133` |
| Local implementation commit | `fb3ee3c18684c366ba0609997b1beb1e1d7c3883` |
| Host | macOS 26.6 (25G72), Python 3.13.3 |
| Local fixture tools | yt-dlp 2026.07.04, FFmpeg/ffprobe 9.0 |
| Machine-readable record | `docs/verification/issue-30-evidence.json` |

## Qualification results

| Rows | Result | Evidence boundary |
| --- | --- | --- |
| H-01 to H-08 | PASS | Independently authored offline runners, task state, and answer/citation fixtures. |
| H-09 | PASS | Fake resolver, transport, clock, and caption fetcher only; no DNS, URL, redirect, caption, provider, or credential activity. |
| H-10 | PASS | Disposable hostile-workspace fixtures only; validated macOS cleanup is intentionally `cleanup_incomplete` with no deletion and reuse revocation. |
| S-01 | PASS | Versioned, deterministic, temporary local media corpus and track metadata. |
| S-02 | PASS | Local FFmpeg 768/1024 JPEG extraction plus the bounded inspector escalation seam. |
| S-03 | PASS | Generated 340-second, 1fps scale fixture proves 0/50/100/at-least-251 chronological selection behavior. |
| S-04 | PASS | A fresh blinded reviewer inspected the multi-track contradiction frame and supported the visible claim; [the hash-only review record](issue-30-s04-review.json) captures its method, input/frame/output hashes, and limits. |

The precise test names, artifact hashes, limits, and run commands are in the
machine-readable record. Source media and review packets are regenerated only
inside temporary directories and are not committed.

## Current H-09 / H-11 scope

The current specification is authoritative: H-09 means direct native-caption
opaque-receipt binding and network safety, not the historical provider-consent
interpretation. H-11 release-facing transcription disablement and the future
complete-request-size gate remain non-regression evidence only; they are not an
Issue #30 closure row.

## Validation and review boundary

The focused Issue #30 suite passed **29 tests in 61.455s**. The mapped caption
and workspace regressions passed **51 tests in 0.232s** and **23 tests in
0.127s**. The full repository suite passed **262 tests in 114.343s**. Syntax,
package/discovery, and skill-package validation also passed; exact commands are
retained in the JSON record. Independent Standards and Spec reviews passed with
no findings. No push, pull request, issue mutation, or live validation is
authorized by this record.
