# Setup and troubleshooting

## Scope and safety boundary

The canonical source is `$REPO_ROOT/.agents/skills/watch`. `SKILL.md` is its discovery file; `agents/openai.yaml` is optional display and invocation-policy metadata only. Selecting `$watch` or matching a narrow implicit request does not grant filesystem, network, credential, upload, installation, cleanup, or outside-workspace authority.

This document describes the only supported personal-installation route. It does not authorize Codex, the `watch` skill, its runtime, a test, or repository tooling to perform it. A person must first see the exact action and explicitly approve the outside-workspace mutation.

```text
$HOME/.agents/skills/watch -> $REPO_ROOT/.agents/skills/watch
```

Never copy the package to a personal location. Never self-install. Never self-update. Never overwrite, remove, repair, force, or assume ownership of a personal target. Do not mutate global configuration, and do not use `$HOME/.codex/skills` as an alternate installation route for this project.

## Manual personal installation

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

Repository discovery checks `$REPO_ROOT/.agents/skills/watch/SKILL.md` in a task whose primary folder is the repository root. Personal discovery checks `$HOME/.agents/skills/watch/SKILL.md` in a separate task/repository where the repository copy is absent. Record the exact displayed selected path for each check.

When both locations expose `name: watch`, there is no duplicate-name precedence assumption. Require path isolation: identify and verify the repository and personal paths independently. If Desktop cannot visibly distinguish them, test one copy at a time rather than selecting a bare `watch` name.

## Metadata reload and live acceptance

Use a new Desktop task to inspect a benign metadata edit; it reconstructs the task inventory. Do not claim that an already-open task refreshes its skill inventory. Host change detection may update metadata, but a fresh task is the clean discovery check. If a changed skill is still missing, restart once as the documented fallback, then record whether it appeared. Do not use repeated restarts, configuration changes, or global copies to force discovery.

Static or hermetic package checks do not prove live Desktop discovery, personal installation, in-task refresh, approvals, runtime script execution, media acquisition, or provider behavior. This repository has not used a live Desktop or outside-workspace probe for this ticket.

Before any future live Desktop or outside-workspace probe, show the exact path and command/action, expected mutation, restoration procedure, and evidence record to the human, then wait for explicit approval. A benign discovery probe must not acquire media, contact a provider, upload data, read credentials, or alter a global target without that approval.

## Troubleshooting

- If the canonical package is not listed, first verify `$REPO_ROOT/.agents/skills/watch/SKILL.md` and the task's repository root. Start a new Desktop task; only then use the one restart once fallback. Do not infer success from hermetic tests.
- If the personal target exists in any form, keep it untouched. Its owner must decide what to do; this project never replaces or repairs it.
- If two `watch` entries appear, verify their absolute paths separately. There is no duplicate-name precedence.
- If a request only mentions a video, asks to download/edit/code for it, has zero/multiple/ambiguous sources, or needs private/authenticated/live access, it is outside the narrow implicit route. `$watch` selection still does not grant any new authority.
