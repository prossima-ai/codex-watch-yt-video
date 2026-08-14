# Setup and troubleshooting

## Claim classification

Every material user-facing or release claim in this document uses the same labels as the rest of the repository:

- `confirmed` — a named recorded evidence source exists, with its evidence boundary stated.
- `implementation requirement` — specified or implemented behavior without qualifying live verification.
- `unsupported/out of scope` — behavior v0.1 does not provide or claim to provide.

Static analysis, hermetic tests, mocks, documentation review, and a closed issue cannot prove live Desktop discovery, personal installation, source-host acquisition, sandbox approval behavior, provider behavior/retention, or live cleanup.

## Scope and safety boundary

**Classification: implementation requirement. Evidence:** [watch specification sections 3 and 11](spec/watch-skill.md#11-packaging-manual-installation-and-updates) and `tests/test_skill_package_contract.py`.

The canonical source is `$REPO_ROOT/.agents/skills/watch`. `SKILL.md` is its discovery file; `agents/openai.yaml` is optional display and invocation-policy metadata only. Selecting `$watch` or matching a narrow implicit request does not grant filesystem, network, credential, upload, installation, cleanup, or outside-workspace authority.

This document describes the only supported personal-installation route. It does not authorize Codex, the `watch` skill, its runtime, a test, or repository tooling to perform it. A person must first see the exact action and explicitly approve the outside-workspace mutation.

```text
$HOME/.agents/skills/watch -> $REPO_ROOT/.agents/skills/watch
```

Never copy the package to a personal location. Never self-install. Never self-update. Never overwrite, remove, repair, force, or assume ownership of a personal target. Do not mutate global configuration, and do not use `$HOME/.codex/skills` as an alternate installation route for this project.

## Manual personal installation

**Classification: implementation requirement. Evidence:** [specification section 11](spec/watch-skill.md#11-packaging-manual-installation-and-updates) and `tests/test_skill_package_contract.py::CanonicalSkillPackageTests.test_documented_manual_installation_is_fail_closed_and_truthful`.

Before any mutation, set `source` to the canonical path and `target` to the exact personal path. The following inspection is read-only:

```sh
source="$REPO_ROOT/.agents/skills/watch"
target="$HOME/.agents/skills/watch"
agents_parent="$HOME/.agents"
skills_parent="$agents_parent/skills"

if [ ! -f "$source/SKILL.md" ]; then
  printf '%s\n' "Refusing: canonical SKILL.md is not present at $source" >&2
  exit 1
fi

for parent in "$agents_parent" "$skills_parent"; do
  if [ ! -d "$parent" ] || [ -L "$parent" ]; then
    printf '%s\n' "Refusing: required personal parent is missing, not a directory, or a symlink: $parent" >&2
    exit 1
  fi
done

if [ -e "$target" ] || [ -L "$target" ]; then
  printf '%s\n' "Refusing: personal target already exists at $target" >&2
  exit 1
fi

printf '%s\n' "Proposed manual action: create only $target -> $source"
```

The `-L` check is required: a broken symlink is still an existing target. A file, directory, valid symlink, broken symlink, or hostile target all require the same response: stop. The required parents must already be real directories, never symlinks. Do not use `ln -f`, `rm`, `cp`, a repair command, or a replacement command.

Only after the read-only check succeeds, the target is still absent, and a human has explicitly approved the exact outside-workspace mutation, that human may create one symlink at the displayed target pointing to the displayed source. The exact mutation is:

```text
create one symbolic link at $HOME/.agents/skills/watch whose destination is $REPO_ROOT/.agents/skills/watch
```

Do not use a bare `ln -s`: a shell preflight cannot make a later link creation race-safe, and a target that becomes a directory can receive an unintended child link. This project intentionally publishes no executable installation command or installer. A human-controlled procedure must use an exclusive, no-follow link-creation operation appropriate to the host. If the target appears before the human performs the action, refuse it and do nothing. Do not create a child link inside an existing directory. If either parent is missing, not a directory, or a symlink, stop and obtain separate explicit approval for that distinct outside-workspace change; then repeat every read-only check.

Afterward, verify the personal symlink's displayed path and resolved destination independently. Updating means updating only `$REPO_ROOT/.agents/skills/watch`; it never means copying or self-updating a personal tree.

## Repository and personal discovery are separate checks

**Classification: implementation requirement. Evidence:** specification [section 3.2](spec/watch-skill.md#32-discovery-evidence-and-its-boundary) and hermetic discovery fixtures only.

Repository discovery checks `$REPO_ROOT/.agents/skills/watch/SKILL.md` in a task whose primary folder is the repository root. Personal discovery checks `$HOME/.agents/skills/watch/SKILL.md` in a separate task/repository where the repository copy is absent. Record the exact displayed selected path for each check.

When both locations expose `name: watch`, there is no duplicate-name precedence assumption. Require path isolation: identify and verify the repository and personal paths independently. If Desktop cannot visibly distinguish them, test one copy at a time rather than selecting a bare `watch` name.

## Metadata reload and live acceptance

**Classification: implementation requirement. Evidence:** specification [section 3.2](spec/watch-skill.md#32-discovery-evidence-and-its-boundary). The #28 implementation record has no qualifying live probe.

Use a new Desktop task to inspect a benign metadata edit; it reconstructs the task inventory. Do not claim that an already-open task refreshes its skill inventory. Host change detection may update metadata, but a fresh task is the clean discovery check. If a changed skill is still missing, restart once as the documented fallback, then record whether it appeared. Do not use repeated restarts, configuration changes, or global copies to force discovery.

Static or hermetic package checks do not prove live Desktop discovery, personal installation, in-task refresh, approvals, runtime script execution, media acquisition, or provider behavior. This repository has not used a live Desktop or outside-workspace probe for this ticket.

Before any future live Desktop or outside-workspace probe, show the exact path and command/action, expected mutation, restoration procedure, and evidence record to the human, then wait for explicit approval. A benign discovery probe must not acquire media, contact a provider, upload data, read credentials, or alter a global target without that approval.

## Troubleshooting

- If the canonical package is not listed, first verify `$REPO_ROOT/.agents/skills/watch/SKILL.md` and the task's repository root. Start a new Desktop task; only then use the one restart once fallback. Do not infer success from hermetic tests.
- If the personal target exists in any form, keep it untouched. Its owner must decide what to do; this project never replaces or repairs it.
- If two `watch` entries appear, verify their absolute paths separately. There is no duplicate-name precedence.
- If a request only mentions a video, asks to download/edit/code for it, has zero/multiple/ambiguous sources, or needs private/authenticated/live access, it is outside the narrow implicit route. `$watch` selection still does not grant any new authority.

## Preflight and approval flow

**Classification: implementation requirement. Evidence:** specification [sections 3, 4, and 8](spec/watch-skill.md#8-optional-transcription-consent-secrets-and-retries) and hermetic tests in `tests/test_prepare_metadata.py` and `tests/test_provider_transcription.py`.

1. Validate exactly one supported source before acquisition. For a public,
   unauthenticated yt-dlp-compatible HTTP(S) URL, show that `yt-dlp` would
   contact its named host and obtain separate source-host command-network
   approval first. A selected native-caption resource can then be retrieved
   directly under that same approved source-network action; this is a documented
   release/spec gate, not a separate approval this procedure can grant. A local
   file does not grant extra authority.
2. Let preflight report missing `yt-dlp`, FFmpeg/ffprobe, or runtime support with typed guidance. Do not install or update a dependency, change a package manager, or treat a selected skill as permission to run a command.
3. Prefer captions. If optional transcription could help, obtain a user provider choice and audio-track selection where needed; a credential does not choose a provider.
4. After a named provider and track are selected, show the destination, current privacy link, selected track, estimated bytes/duration, possible chunking, and audio-only boundary. Then obtain fresh provider-specific audio-upload consent.
5. Only after that consent succeeds, request separate provider-network approval. Source-host command-network approval, provider choice, fresh consent, and provider-network approval remain separate; denial at any gate stops before the relevant work.

Do not request secrets in chat, scan `.env`, or make a provider request to diagnose credentials. Read [security and privacy](security-and-privacy.md) for the data boundary, outcome vocabulary, and validated cleanup protocol.

## Outcome and cleanup troubleshooting

**Classification: implementation requirement. Evidence:** specification [sections 9–10](spec/watch-skill.md#10-workspace-retention-reuse-and-cleanup) and hermetic lifecycle tests only.

- `decision_required` and `consent_required` are nonterminal requests for a specific choice; do not guess a selection or send a request while waiting.
- `stopped`, `failed`, and `canceled` are terminal outcomes. A truthful `partial` outcome can retain named evidence but must disclose coverage, answerability, gaps, and disposal state.
- Evidence reuse is same-task-only. It does not authorize automatic reacquisition, more extraction, provider upload, or automatic deletion.
- Cleanup is explicit and fail closed. `cleanup_deferred`, `cleanup_refused`, `cleanup_incomplete`, `cleanup_succeeded`, and `cleanup_already_absent` have the meanings documented in [security and privacy](security-and-privacy.md#explicit-cleanup-only). On macOS, `cleanup_incomplete` preserves a validated workspace rather than risking an unsafe delete.

## Recorded #28 boundary

**Classification: confirmed. Evidence:** [PR #43](https://github.com/prossima-ai/codex-watch-yt-video/pull/43) / Issue #28 merged record.

No live Desktop probe, personal installation, media acquisition, or provider request was performed for #28. Its hermetic package-contract tests prove only disposable fixture behavior and repository artifacts; they do not prove host discovery, personal installation, command-network approval, media acquisition, provider behavior, or cleanup on a user machine.
