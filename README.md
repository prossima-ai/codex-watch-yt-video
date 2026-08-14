# Codex-native `watch` skill

`watch` prepares evidence for exactly one public, unauthenticated video URL or one lawful local video. It is a repository-owned Codex Desktop skill; it is not a downloader, editor, installer, credential manager, provider client without separate consent, or media library.

## Canonical source and discovery

The canonical skill source is [`$REPO_ROOT/.agents/skills/watch`](.agents/skills/watch/SKILL.md). `SKILL.md` is the discovery file. Its optional `agents/openai.yaml` contains only visible display metadata, the `$watch` default prompt, and the narrow implicit-invocation policy.

Use `$watch` explicitly. Implicit matching is limited to a clear request to inspect, analyze, summarize, or answer a question from exactly one supplied video or the Current source. Mentioning video, editing, downloading, coding, zero/multiple/ambiguous sources, or private/authenticated/live/playlists are not implicit routes.

## Request examples

These are request syntax examples only; this documentation does not contact either source.

```text
$watch https://video.example/watch?v=one What is the speaker's conclusion?
$watch "/path/to/local video.mp4" Give a timestamped summary.
```

The only personal-installation route is the manual symlink:

```text
$HOME/.agents/skills/watch -> $REPO_ROOT/.agents/skills/watch
```

It is a human-controlled outside-workspace action. The skill, its runtime, tests, and repository tooling never create, copy, update, repair, or remove a personal skill target. See [setup and troubleshooting](docs/setup-and-troubleshooting.md) before considering that action.

## Verification boundary

The repository includes hermetic package-contract tests for paths, metadata, routing policy, symlink integrity, and refusal behavior. Those tests do not prove live Desktop discovery, an already-open task's inventory refresh, a personal installation, sandbox approvals, media acquisition, or provider behavior. No live media or provider request is part of package discovery validation.
