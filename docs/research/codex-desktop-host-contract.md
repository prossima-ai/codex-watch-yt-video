# Codex Desktop host contract for a `watch` skill

**Research ticket:** [#7 — Establish the Codex Desktop host contract](https://github.com/killer-block-coder-95/codex-watch-yt-video/issues/7)

**Resolved:** 2026-08-09

**Active build examined:** ChatGPT desktop app `26.803.41515` (bundle `6321`) on macOS 26.6 arm64, with bundled `codex-cli 0.147.0-alpha.6.5`

## Resolution

The supported authoring contract for this project is:

- Put the repository-owned skill at `$REPO_ROOT/.agents/skills/watch/`.
- Put a personal, cross-repository installation at `$HOME/.agents/skills/watch/`.
- Require `SKILL.md` with YAML front matter containing `name` and `description`; keep scripts, references, and assets beside it.
- Treat `agents/openai.yaml` as optional host metadata, not as the discovery file. Use it for Desktop presentation, invocation policy, and declared tool dependencies. Set `policy.allow_implicit_invocation: true` explicitly if implicit matching is an intended product behavior.
- Treat `$watch` as an explicit invocation and a matching natural-language request as a possible implicit invocation. Neither route elevates filesystem or network authority.
- Run bundled scripts under the active sandbox and approval policy. Network access, writes outside writable roots, protected-path changes, and any skill-script approval remain independent gates.
- Use the active build's `view_image` tool for an already-local thumbnail or frame when available, but feature-detect it: the public image-input contract is stable, while the exact tool name and `detail` options are build-level behavior.
- Do not require a fresh task as the normative reload mechanism. OpenAI documents automatic skill-change detection with restart as the fallback, and the app-server contract supports change notifications and forced re-scan. A fresh task is nevertheless the clean release test because it reconstructs the model-visible skill inventory.

This resolution has one material qualification: **repository discovery is documented but was not reproduced by the bundled CLI diagnostic on the examined build.** A valid temporary `$REPO_ROOT/.agents/skills/host-contract-probe` did not appear in a fresh `codex debug prompt-input` inventory, even with an ephemeral trusted-project override. The probe and all generated evidence fixtures were removed. The `watch` implementation must therefore remain behind the repository-discovery acceptance gate below; this report does not claim that gate passed.

## Evidence labels

- **Documented** — stated by current official OpenAI documentation.
- **Verified** — reproduced against the active local Desktop/CLI build during this research.
- **Inference** — a conservative consequence of documented and verified facts, not a separately stated guarantee.
- **Unknown** — not established without implementing `watch`, mutating a global skill location, or granting a broader side effect solely for a probe.

## Contract matrix

| Area | Current contract | Evidence | Consequence for `watch` |
| --- | --- | --- | --- |
| Desktop availability | Standalone skills are supported in the ChatGPT desktop app's Codex surface; Desktop exposes a Skills sidebar. | **Documented:** [Build skills](https://learn.chatgpt.com/docs/build-skills) | A standalone repository or personal skill is an appropriate packaging unit; a plugin is not required for v0.1. |
| Repository discovery | Codex scans `.agents/skills` from the current working directory upward through the repository root. | **Documented:** [Build skills — Where Codex loads local skills](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills). **Not reproduced** by the local probe. | Canonical path is `.agents/skills/watch`, but release is blocked until Desktop lists that exact path in a fresh task. |
| Personal discovery | The portable personal authoring location is `$HOME/.agents/skills`. | **Documented:** [Build skills — Where Codex loads local skills](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills). **Verified:** existing skills from this path appeared in the active build's generated prompt inventory. | Install the personal copy at `$HOME/.agents/skills/watch`; installation or updates are writes outside the project and need explicit authority. |
| Alternate personal path | This build also discovered many skills from `$HOME/.codex/skills`, and the app-server documentation uses that path in examples. It is absent from the authoring guide's discovery table. | **Verified** locally; **documented only in lower-level examples:** [Codex App Server — Skills](https://learn.chatgpt.com/docs/app-server). | Treat `$HOME/.codex/skills` as a current implementation/compatibility path, not the portable target for this project. |
| Duplicate names | Skills with the same `name` are not merged; both may appear. | **Documented:** [Build skills](https://learn.chatgpt.com/docs/build-skills). **Verified:** duplicate `excalidraw-diagram` entries from `.agents` and `.codex` appeared locally. | Do not test repo and personal copies named `watch` in the same task unless the selector visibly identifies the intended absolute path. No precedence guarantee was found. |
| `SKILL.md` | A skill directory requires `SKILL.md`; `name` and `description` are required. Scripts, references, assets, and `agents/openai.yaml` are optional. Codex initially exposes name, description, and path, then reads the full instructions after selection. | **Documented:** [Build skills](https://learn.chatgpt.com/docs/build-skills). | Keep discovery metadata short and precise. Put procedure and safety logic in the body, and link supporting files explicitly. |
| `agents/openai.yaml` | Optional metadata supplies `interface`, `policy.allow_implicit_invocation`, and tool dependencies. The implicit flag defaults to `true`; `false` blocks implicit selection but preserves explicit `$skill`. | **Documented:** [Build skills — Optional metadata](https://learn.chatgpt.com/docs/build-skills#optional-metadata). **Verified:** sampled current OpenAI-bundled skills use `agents/openai.yaml`. | Include it for auditable Desktop metadata and invocation intent, but never depend on it for discovery. |
| Explicit invocation | `$<skill-name>` is a Codex skill marker. App-server clients should also attach the resolved skill path so full instructions are injected deterministically; otherwise the model attempts name resolution. | **Documented:** [Codex App Server — Skills](https://learn.chatgpt.com/docs/app-server). | `$watch` is the explicit test phrase. Verify that the selected entry resolves to the expected repo or personal `SKILL.md`. |
| Implicit invocation | Codex may select a skill when the task matches its `description`, unless implicit invocation is disabled. | **Documented:** [Build skills — How ChatGPT and Codex use skills](https://learn.chatgpt.com/docs/build-skills#how-chatgpt-and-codex-use-skills). | Test positive, near-miss, and negative prompts. A broad description is a routing bug, not a convenience. |
| Bundled scripts | `scripts/` is an optional skill resource for deterministic computation or external tooling. Merely bundling a script does not grant execution, network, or write authority. | **Documented:** [Build skills](https://learn.chatgpt.com/docs/build-skills) and [Agent approvals & security](https://learn.chatgpt.com/docs/agent-approvals-security). **Verified:** a script from an installed OpenAI skill executed from outside the workspace; its network operation still required escalation. | `SKILL.md` must say exactly when and how to run each script. Keep outputs in the workspace or temp by default and fail closed when permissions are denied. |
| Local images | Desktop can be asked to inspect an image on the local system; PNG and JPEG are documented common formats. | **Documented:** [Image inputs](https://learn.chatgpt.com/docs/image-inputs). **Verified:** `view_image` loaded an absolute PNG outside the workspace at `detail=original` under this session's read policy. | Download or generate a frame first, then inspect the local path. Reading succeeds only where the active profile permits it. Provide a path/attachment fallback if `view_image` is unavailable. |
| Sandbox | Local Desktop commands run in a constrained sandbox; macOS uses Seatbelt. `workspace-write` allows routine workspace work, while approvals govern boundary crossings. | **Documented:** [Sandbox](https://learn.chatgpt.com/docs/sandboxing). | Invocation of `watch` never bypasses the host sandbox. |
| Protected project paths | `.git`, `.agents`, and `.codex` inside writable roots remain recursively read-only in the default workspace-write policy. | **Documented:** [Agent approvals & security — Protected paths](https://learn.chatgpt.com/docs/agent-approvals-security#protected-paths-in-writable-roots). | Creating or updating the repo skill itself can require approval even though it is inside the repository. Runtime scripts must not self-modify the skill. |
| Outside-workspace writes | Auto/workspace-write asks before editing outside the workspace. Additional writable roots can be configured without disabling the whole sandbox. | **Documented:** [Sandbox](https://learn.chatgpt.com/docs/sandboxing) and [Agent approvals & security](https://learn.chatgpt.com/docs/agent-approvals-security). | A personal install, cache in an arbitrary home directory, or export beside the source video is not silently authorized. Prefer workspace/temp outputs; request the narrow target when another location is required. |
| Command network | Network is off by default for local workspace-write commands. Web search, plugins, and the browser have separate controls and do not grant a spawned script internet access. | **Documented:** [Agent approvals & security — Network access](https://learn.chatgpt.com/docs/agent-approvals-security#network-access) and [Sandbox](https://learn.chatgpt.com/docs/sandboxing). **Verified:** a bundled Node helper failed DNS in-sandbox, then succeeded after a scoped network escalation. | A downloader or YouTube request must expect denial or approval. Never infer that web-search availability means `yt-dlp`, `curl`, Node, or Python has network access. |
| Reload | Codex documents automatic detection; restart is the fallback. App-server has `skills/changed` and `skills/list` with `forceReload`. | **Documented:** [Build skills](https://learn.chatgpt.com/docs/build-skills) and [Codex App Server — Skills](https://learn.chatgpt.com/docs/app-server). **Verified:** the bundled protocol schema contains both mechanisms. | Use a fresh task for clean QA, then restart only if the skill still does not appear. Do not claim that a fresh task itself is the documented cache invalidator. |

## Discovery and metadata details

### Canonical paths

The current authoring guide defines four scopes: repository, user, admin, and OpenAI-bundled system skills. Repository scanning walks `.agents/skills` from `$CWD` through `$REPO_ROOT`; user skills live under `$HOME/.agents/skills`; admin skills live at `/etc/codex/skills`. Symlinked skill directories are supported. Duplicate names are retained rather than merged. [OpenAI's Build skills guide](https://learn.chatgpt.com/docs/build-skills) is the controlling source for a standalone skill authored by this project.

That means the two intended layouts are:

```text
$REPO_ROOT/.agents/skills/watch/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── scripts/          # optional
├── references/       # optional
└── assets/           # optional

$HOME/.agents/skills/watch/
└── ...same authored skill tree...
```

The active build also listed standalone skills from `$HOME/.codex/skills` and plugin skills from versioned cache directories under `$HOME/.codex/plugins/cache`. The lower-level [Codex App Server documentation](https://learn.chatgpt.com/docs/app-server) likewise shows `.codex/skills` paths and says normalized `interface` and `dependencies` can come from `SKILL.json`, while the standalone authoring guide specifies `agents/openai.yaml`. The three sampled current OpenAI-bundled skills on this machine contain `agents/openai.yaml` and no `SKILL.json`. The safest interpretation is:

1. Author this standalone skill to the `Build skills` contract (`.agents/skills` plus `agents/openai.yaml`).
2. Regard `.codex/skills` and `SKILL.json` as app-server/compatibility surface details unless OpenAI consolidates the documentation.
3. Test Desktop presentation and discovery rather than assuming file-precedence behavior that no source states.

### Local repository probe

A temporary probe was created twice: first under a nested temporary repository and then at the assigned worktree's exact repository root. It had a valid `SKILL.md` with `name` and `description`, plus an `agents/openai.yaml` with `allow_implicit_invocation: false`. A fresh bundled CLI process rendered its model-visible prompt using the repository as `cwd` and an ephemeral trusted-project override. The probe did not appear; existing personal, system, and plugin skills did. No omission warning appeared in the rendered skills block.

This negative result does **not** overturn the official path contract. The diagnostic may differ from the live Desktop app-server's project-root plumbing, or the examined alpha build may have a discovery defect. A direct live `skills/list` query was not completed because starting the local app-server attempted an external ChatGPT backend websocket and automatic review rejected that unneeded network side effect. No global skill/config location was changed just to force a result.

## Invocation and reload details

OpenAI documents progressive disclosure: the initial prompt receives compact skill metadata, and full `SKILL.md` instructions load after the skill is chosen. The initial skill list is budgeted, so very large installations can shorten descriptions or omit entries with a warning. Descriptions therefore need the trigger and boundary words early. [Build skills](https://learn.chatgpt.com/docs/build-skills) also defines explicit and implicit routes.

For current Codex protocol clients, [App Server](https://learn.chatgpt.com/docs/app-server) explicitly recognizes `$<skill-name>` and recommends resolving the matching name and path into a structured `skill` input item. Thus `$watch` is the correct explicit acceptance phrase for this Codex surface. The report does not claim an end-to-end `$watch` run because implementing the skill was deliberately out of scope.

Implicit routing is description-based and defaults on. For deterministic policy and reviewer clarity, the authored metadata should state the intended value rather than relying silently on the default:

```yaml
policy:
  allow_implicit_invocation: true
```

If the project later decides that watching a video is too costly or surprising to launch from natural language alone, set it to `false`; `$watch` remains available.

Reload has three distinct layers:

1. The host watches local skill files and can invalidate/re-scan metadata (`skills/changed`, `skills/list.forceReload`).
2. A task's already-constructed model prompt may still contain the inventory captured when that task began.
3. Restart is the documented fallback when an update is not visible.

Therefore a fresh task is the best clean test after installation, but it is an operational QA step, not the official primary reload contract.

## Script, image, and permission details

Skill selection supplies instructions; it grants no ambient authority. A bundled script is still a spawned local command. The [sandbox documentation](https://learn.chatgpt.com/docs/sandboxing) says spawned commands inherit the same filesystem and network boundaries, and [Agent approvals & security](https://learn.chatgpt.com/docs/agent-approvals-security) exposes skill-script approvals as a separate granular approval category.

The active session verified this composition. It read and executed `fetch-codex-manual.mjs` from an installed OpenAI skill outside the workspace. The script could write its cache under the permitted temp directory. Its initial network request failed with DNS blocked; the same command succeeded only after a scoped network escalation. This is the closest safe analogue to a future downloader script without implementing or invoking `watch`.

The host's built-in local-image tool is similarly distinct from shell networking. On this build, `view_image` accepted an absolute path plus `detail: "original"` and successfully loaded a PNG from the ChatGPT app bundle outside the workspace because the active profile allowed root reads. Public documentation guarantees the higher-level ability to inspect an image on the system and common PNG/JPEG inputs, not the `view_image` tool name or its detail enum. A robust skill should therefore:

1. Produce or download the frame into the workspace or an allowed temp directory.
2. Use `view_image` when the tool exists.
3. Fall back to reporting the absolute local path and asking the user to attach/open it if the tool is absent or read access is denied.

## Acceptance gates for the future `watch` implementation

Run these gates on the target Desktop build and record the app/CLI versions. Use harmless fixtures first; do not broaden global access to make a test pass.

1. **Repository discovery — blocking.** With only the repo copy present, start a new Codex task whose primary folder is the repository root. Confirm the Skills UI or model-visible inventory lists `watch` at `$REPO_ROOT/.agents/skills/watch/SKILL.md`. If absent, restart once and retry. Do not release on documentation alone.
2. **Personal discovery — blocking for global install.** In a separate task/repository without the repo copy, install the same tree at `$HOME/.agents/skills/watch`. Confirm the selector reports that exact path. Installation is an explicit outside-workspace write; do not make it from a runtime script.
3. **Duplicate isolation.** When both copies exist, confirm the intended path is visibly selected. If the UI cannot disambiguate, test one copy at a time and document that operational constraint.
4. **Metadata.** Verify display name, short description, icons if any, and default prompt. Confirm `allow_implicit_invocation` matches the intended product decision.
5. **Explicit invocation.** Invoke `$watch` with an offline local fixture. Confirm the host loads the correct `SKILL.md`, follows its script path, and reports real outputs rather than simulating execution.
6. **Implicit invocation.** Test at least one direct natural-language match, one near miss, and one negative control. A near miss must not start network or long-running work unexpectedly.
7. **Bundled-script execution.** Run an offline/deterministic script fixture from the skill directory. Confirm it can read bundled resources and writes only under the workspace or temp by default.
8. **Network denial and approval.** With command network disabled, confirm a network-dependent step fails closed and explains what permission is needed. Then approve only the required command/destination and confirm the real request succeeds. Web search or browser availability is not evidence for this gate.
9. **Outside-workspace write.** Request an output path outside writable roots. Confirm no file is created before approval; after a narrowly scoped approval, confirm only the named target is written.
10. **Local-image view.** Create a PNG/JPEG frame in an allowed location, inspect it with `view_image` when available, and verify a denied/unavailable path produces a useful fallback rather than a fabricated visual conclusion.
11. **Reload.** Modify only benign description text, wait for host detection, and inspect from a new task. If it does not update, restart Codex and retry. Record which mechanism was actually required.
12. **Clean-state audit.** Confirm no probe, credentials, downloaded media, or cache files remain in `.agents`, the global skill directories, or the Git diff except the intended implementation.

## Remaining fog and follow-up questions

1. Why did `codex debug prompt-input` in `0.147.0-alpha.6.5` omit a valid repo-root `.agents/skills` probe despite the official contract and a trusted-project override? The live Desktop `skills/list` result remains the decisive follow-up.
2. Which metadata file is the long-term app-server source of truth: the authoring guide's `agents/openai.yaml`, the app-server page's `SKILL.json`, or a compatibility merge? The active OpenAI-bundled skills support the first, but the docs currently describe both.
3. What selection precedence, if any, does Desktop apply when repo and personal skills share `name: watch`? Official documentation promises coexistence, not precedence.
4. Which executions receive a dedicated skill-script approval rather than only ordinary command/sandbox/network approval? The configuration exposes the category but does not state a complete trigger algorithm.
5. Is `view_image` a stable user-authored skill API, or only the current Desktop host's built-in implementation detail? The higher-level local-image capability is documented; the exact tool contract is not.
6. Does a `skills/changed` event update only Desktop selector metadata, or also the model-visible skill inventory of an already-running task? Use a new task until that distinction is documented or reproduced.

## Local evidence log

No global skill or config location was mutated. Temporary repository probes and generated schema directories were removed before the report was written.

| Check | Observation |
| --- | --- |
| `plutil` on `/Applications/ChatGPT.app/Contents/Info.plist` | App `26.803.41515`, bundle `6321`. |
| Bundled `codex --version` | `codex-cli 0.147.0-alpha.6.5`. |
| `codex debug prompt-input` in the assigned worktree | Listed skills from `$HOME/.agents/skills`, `$HOME/.codex/skills`, OpenAI system roots, and plugin caches; did not list the temporary repo probe. |
| Generated app-server JSON schema | Included `skills/list.forceReload`, `skills/changed`, normalized `SkillMetadata`, and scopes `repo`, `user`, `system`, and `admin`. |
| OpenAI-bundled skill inspection | `openai-docs`, `imagegen`, and `skill-creator` used `agents/openai.yaml`; no `SKILL.json` was present in those sampled skill roots. |
| Bundled skill script | Ran from an installed skill outside the workspace; temp write succeeded, command network failed first and succeeded after scoped escalation. |
| `view_image` | Loaded `/Applications/ChatGPT.app/Contents/Resources/icon-codex-light.png` at original detail. |
| Cleanup | Worktree returned clean before adding this report; no probe or schema fixture remained. |
