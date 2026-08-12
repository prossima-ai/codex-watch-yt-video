# TestSprite AI Testing Report (MCP)

---

## 1️⃣ Document Metadata

- **Project Name:** codex-watch-yt-video
- **Date:** 2026-08-12
- **Prepared by:** TestSprite AI Team, with repository-contract analysis by Codex
- **Scope:** Issue #22 metadata preparation through a temporary test-only HTTP adapter
- **Executed Cases:** TC001-TC006 and TC009; TC007-TC008 were excluded because track selection belongs to later implementation tickets

---

## 2️⃣ Requirement Validation Summary

### Requirement: Single-source request validation

- **Description:** Accept exactly one supported source and stop invalid or unsupported requests before later evidence work.

#### Test TC001 postpreparemetadatawithvalidsinglesource

- **Test Code:** [TC001_postpreparemetadatawithvalidsinglesource.py](./TC001_postpreparemetadatawithvalidsinglesource.py)
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/5634f79f-d16d-4670-a749-735ed538841a/test/bc5c7747-cc39-4cfb-8750-7f87c6f18b15
- **Status:** ✅ Passed
- **Severity:** LOW
- **Analysis / Findings:** The adapter returned HTTP 200 with a typed `partial` outcome and established the single local source. No caption, visual, transcription, workspace, or cleanup stage ran.

---

#### Test TC002 postpreparemetadatawithinvalidmultiplesourcesorunsupportedinput

- **Test Code:** [TC002_postpreparemetadatawithinvalidmultiplesourcesorunsupportedinput.py](./TC002_postpreparemetadatawithinvalidmultiplesourcesorunsupportedinput.py)
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/5634f79f-d16d-4670-a749-735ed538841a/test/f6691ddb-efde-412e-98dd-c930a8805ca5
- **Status:** ✅ Passed
- **Severity:** LOW
- **Analysis / Findings:** The tested invalid source forms returned typed `stopped` or `failed` outcomes with failure details and no later evidence stages.

---

### Requirement: Metadata evidence and tool preflight

- **Description:** Return typed metadata, tool availability, coverage, warnings, and a safely rendered Markdown report; return typed guidance when a required tool is actually unavailable.

#### Test TC003 postpreparemetadatawithmetadatatoolpreflight

- **Test Code:** [TC003_postpreparemetadatawithmetadatatoolpreflight.py](./TC003_postpreparemetadatawithmetadatatoolpreflight.py)
- **Test Error:** `AssertionError` while requiring a top-level `tool_preflight` dictionary.
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/5634f79f-d16d-4670-a749-735ed538841a/test/4fd23eff-bf58-4afb-8720-3eda959eb0ab
- **Status:** ❌ Failed (generated-test mismatch)
- **Severity:** INFO
- **Analysis / Findings:** The response did contain successful metadata, coverage, warnings, JavaScript support, all three tool statuses, and the escaped Markdown report. The generated test asserted invented field names: the implemented schema uses `tools`, `javascript_support`, and `report_markdown`, not `tool_preflight` and `escaped_markdown_report`. This run does not identify a product defect.

---

#### Test TC004 postpreparemetadatawithmissingrequiredlocaltools

- **Test Code:** [TC004_postpreparemetadatawithmissingrequiredlocaltools.py](./TC004_postpreparemetadatawithmissingrequiredlocaltools.py)
- **Test Error:** `AssertionError: Expected missing-tool guidance in failure details`
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/5634f79f-d16d-4670-a749-735ed538841a/test/d0cfd281-2218-44ed-9b96-2303352139e7
- **Status:** ❌ Failed (precondition not established)
- **Severity:** INFO
- **Analysis / Findings:** The generated test did not remove, mock, or hide any required tool. `yt-dlp`, `ffmpeg`, and `ffprobe` were all available, so the runtime correctly returned metadata instead of a missing-dependency failure. The repository's hermetic unit test separately simulates an absent required tool and verifies typed `missing_dependency` guidance and retry/disposition state.

---

### Requirement: Control validation and normalization

- **Description:** Validate detail, focus, cues, frame limits, duplicate handling, and track IDs before acquisition.

#### Test TC005 postpreparemetadatawithvalidcontrols

- **Test Code:** [TC005_postpreparemetadatawithvalidcontrols.py](./TC005_postpreparemetadatawithvalidcontrols.py)
- **Test Error:** `AssertionError: 'cues' control should be a list`
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/5634f79f-d16d-4670-a749-735ed538841a/test/4dd53226-b707-4d2e-892b-ab5a5c683a2c
- **Status:** ❌ Failed (generated-test mismatch)
- **Severity:** INFO
- **Analysis / Findings:** The runtime accepted and normalized valid controls. The generated test expected input-shaped string fields named `focus` and `cues`; the response contract intentionally returns numeric `focus_start_seconds`, `focus_end_seconds`, and `cues_seconds`. It also searched metadata evidence for timestamps that only later visual/transcript stages could supply. This run does not identify a product defect.

---

#### Test TC006 postpreparemetadatawithinvalidcontrols

- **Test Code:** [TC006_postpreparemetadatawithinvalidcontrols.py](./TC006_postpreparemetadatawithinvalidcontrols.py)
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/5634f79f-d16d-4670-a749-735ed538841a/test/11a41416-9e4a-448f-a337-f34f59766d1a
- **Status:** ✅ Passed
- **Severity:** LOW
- **Analysis / Findings:** Invalid detail, timestamps, cue, frame cap, and stale track controls returned typed terminal outcomes with specific failure details and no guessed selection or later evidence.

---

### Requirement: Test-only adapter readiness

- **Description:** Confirm that the temporary compatibility adapter is reachable without treating it as production behavior.

#### Test TC009 gethealthadapterstatuscheck

- **Test Code:** [TC009_gethealthadapterstatuscheck.py](./TC009_gethealthadapterstatuscheck.py)
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/5634f79f-d16d-4670-a749-735ed538841a/test/9edb436e-c0b8-4fc0-b88e-9fdf649fe442
- **Status:** ✅ Passed
- **Severity:** LOW
- **Analysis / Findings:** The temporary localhost adapter reported ready. This proves only TestSprite reachability, not a production HTTP deployment.

---

## 3️⃣ Coverage & Matching Metrics

- **Raw TestSprite result:** 4 of 7 tests passed (57.14%).
- **Failure triage:** 3 generated-test/precondition mismatches; 0 confirmed product defects.
- **Planned but intentionally excluded:** 2 later-ticket cases (TC007 and TC008).

| Requirement | Total Tests | ✅ Passed | ❌ Raw Failed | Confirmed Product Defects |
|---|---:|---:|---:|---:|
| Single-source request validation | 2 | 2 | 0 | 0 |
| Metadata evidence and tool preflight | 2 | 0 | 2 | 0 |
| Control validation and normalization | 2 | 1 | 1 | 0 |
| Test-only adapter readiness | 1 | 1 | 0 | 0 |
| **Total** | **7** | **4** | **3** | **0** |

---

## 4️⃣ Key Gaps / Risks

> TestSprite's raw pass rate is 57.14%, but all three failures conflict with the implemented response schema or fail to establish their named precondition. They should not be treated as confirmed Issue #22 regressions.

- The repository is a Codex skill and JSON stdin/stdout command, not an HTTP service. A temporary localhost adapter was required, so this run qualifies only the mapped request/outcome boundary.
- The generated PRD described semantic response concepts without exact field names. TestSprite then invented `tool_preflight`, `escaped_markdown_report`, `focus`, and `cues` response fields. Future runs should supply an explicit JSON schema.
- TC004 needs an adapter-level dependency injection or a deliberately constrained test process to make `ffprobe` unavailable. The safety instruction for this run prohibited uninstalling tools or mutating the host environment.
- TC005 included focus timestamps beyond the one-second synthetic fixture and asserted later-stage evidence behavior. Future tests should keep intervals within fixture duration and test only metadata-stage normalization.
- Caption/audio-track selection (TC007-TC008), visual extraction, transcription, workspace lifecycle, cleanup, installation, public-host networking, and live provider behavior were not tested because they are outside the implemented Issue #22 metadata stage.
- Only a synthetic local MP4 was used. No external URL, credential, network acquisition, package installation, media upload, or provider request occurred.
