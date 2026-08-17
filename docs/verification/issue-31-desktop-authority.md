# Issue #31 Desktop package and authority evidence

## Status

This record is deliberately incomplete. The repository-owned integrity contract
and task plan exist, but no D row is qualified. Each row remains `BLOCKED` until
it has actual target-macOS Codex Desktop evidence against the exact package
revision recorded in `issue-31-evidence.json`.

The validator and its tests prove only that the committed record is structured
and internally consistent. They do not prove package discovery, a selected skill
path, a host approval decision, a network absence, a write denial, frame
inspection, or a Desktop restart.

| Row | Outcome | Current blocker |
| --- | --- | --- |
| D-01 | `BLOCKED` | No human-observed fresh Desktop task with the isolated worktree as its proven primary folder. |
| D-02 | `BLOCKED` | The existing personal symlink targets a clean but stale durable source; changing that source needs separate explicit approval, then a fresh neutral Desktop task. |
| D-03 | `BLOCKED` | No API exposes Skills UI selection, duplicate entries, restart state, or fresh inventory proof. |
| D-04 | `BLOCKED` | No API exposes task-scoped approval, network, filesystem, or visual-inspection audit evidence. |

## Bound candidate

The intended candidate is canonical `origin/main` revision
`ebcd7f30e49505bd2b94367f495b03fde789de8f`. Its canonical skill tree is
`d678b0774e51f3f84aff349c90b201350e756e1e`; `SKILL.md` and
`agents/openai.yaml` are bound by SHA-256 in the machine-readable record. The
current specification revision is
`9d9eea698b4eda09a435f1b198c606e7058033a6`, not assumed to be the base.

The current personal symlink is retained without mutation. Its resolved durable
source has a different package tree and `SKILL.md` hash, so it cannot establish
D-02 for this candidate. It was not recreated, retargeted, repaired, or updated.

## Planned human-observed tasks

The machine-readable record contains the exact sanitized title, primary-folder
requirement, prompt, expected writes, and intended evidence for these fresh
tasks:

- `Issue31 D01 repository discovery`
- `Issue31 D02 personal discovery`
- `Issue31 D03 explicit trigger`
- `Issue31 D03 implicit trigger`
- `Issue31 D03 near-miss control`
- `Issue31 D03 negative control`
- `Issue31 D03 fresh-task reload`
- `Issue31 D04 offline authority and frame fallback`

The D-03 fresh-task check may make one transient, benign metadata edit and use
at most one Desktop restart. It must restore the metadata byte-for-byte and say
explicitly: fresh-task discovery/reload does not prove refresh inside an
already-open task or identify the host cache-invalidation mechanism.

## Required gates before any PASS

1. A human opens each required fresh task in Codex Desktop, with the stated
   primary folder visibly established, and records only sanitized task IDs and
   observations.
2. For D-02, a separate approval packet must first authorize only advancing the
   durable source from its recorded detached revision to the pinned candidate.
   The packet must include current/target SHAs, exact paths, expected changed
   files, cleanup status, verification, and rollback. The existing personal
   symlink itself remains untouched.
3. D-04 uses only a local, generated fixture. The human declines the reserved
   source-network action and the one exclusive harmless outside-workspace
   sentinel write. A real local-frame failure must leave that frame without a
   visual observation or claim, and restore the test fixture's original hash and
   mode.
4. No public media, caption endpoint, provider, credential, upload, browser
   state, cookie store, `.env` content, or unrelated user file is inspected or
   mutated.

This Issue #31 record does not establish public-media behavior, caption
networking, provider activity, credential handling, uploads, live cleanup,
in-task refresh, provenance, or release readiness.
