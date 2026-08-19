"""Integrity checks for Issue #31 Desktop-authority evidence.

This module validates the shape and internal consistency of a sanitized record.
It deliberately cannot prove that Codex Desktop discovered a skill, applied an
approval decision, inspected a frame, or avoided an external side effect.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping


ROW_IDS = ("D-01", "D-02", "D-03", "D-04")
ALLOWED_OUTCOMES = frozenset({"PASS", "FAIL", "BLOCKED", "UNVERIFIED"})
PINNED_BASE_REVISION = "ebcd7f30e49505bd2b94367f495b03fde789de8f"
SPECIFICATION_REVISION = "9d9eea698b4eda09a435f1b198c606e7058033a6"

_REVISION = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_UTC_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_QUERY_URL = re.compile(r"https?://[^\s\"']*\?[^\s\"']+", re.IGNORECASE)
_RAW_URL = re.compile(r"(?:https?:)?//[^\s\"']+", re.IGNORECASE)
_URL_USERINFO = re.compile(r"https?://[^/\s\"']+@", re.IGNORECASE)
_ENCODED_URL = re.compile(r"(?:https?%3a%2f%2f|%2f%2f)[^\s\"']+", re.IGNORECASE)
_AUTHORIZATION = re.compile(
    r"\b(?:authorization|cookie|set-cookie)\s*[:=]\s*\S+", re.IGNORECASE
)
_SECRET = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{12,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,})\b"
)
_ENV_SECRET = re.compile(
    r"\b(?:[A-Za-z][A-Za-z0-9]*[_-])*(?:api[_-]?key|access[_-]?token|session[_-]?token|cookie|jwt|token|secret|password|credential|private[_-]?key)\s*=\s*\S+",
    re.IGNORECASE,
)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{3,}\.[A-Za-z0-9_-]{3,}\b")
_BEARER_CREDENTIAL = re.compile(
    r"\b(?:basic|bearer)\s+[A-Za-z0-9._~+/-]{8,}\b", re.IGNORECASE
)
_CREDENTIAL_HEADER = re.compile(
    r"\b(?:[A-Za-z][A-Za-z0-9]*[-_])*(?:api[-_]?key|access[-_]?token|session[-_]?token|token|secret|password|credential|private[-_]?key)\s*:\s*\S+",
    re.IGNORECASE,
)
_FORBIDDEN_RAW_FIELDS = frozenset(
    {
        "raw_task_transcript",
        "raw_transcript",
        "unredacted_screenshot",
        "screenshot_bytes",
        "environment_dump",
        "raw_environment",
        "approval_receipt",
        "caption_receipt",
        "credential_read",
        "receipt",
        "cookie",
        "cookies",
        "set_cookie",
        "session_cookie",
        "env",
        "dotenv",
        "raw_env",
    }
)
_RESERVED_NETWORK_DENIAL_SOURCE = "https://video.example/issue31-network-denial"
_UNPROVEN = frozenset(
    {
        "public media",
        "caption networking",
        "providers",
        "credentials",
        "uploads",
        "live cleanup",
        "in-task refresh",
        "release readiness",
    }
)
_SIDE_EFFECT_FIELDS = (
    "public_media_contact",
    "source_host_dns_http_request",
    "native_caption_request",
    "provider_contact",
    "credential_read",
    "audio_upload",
    "outside_workspace_write_succeeded",
    "unrelated_user_file_mutation",
)
_TASK_FIELDS = frozenset(
    {
        "id",
        "title",
        "primary_folder",
        "fresh_target_macos_desktop",
        "inventory_path",
        "displayed_alias",
        "selected_skill_path",
        "script_path",
        "sanitized_prompt",
        "command_trace",
    }
)


def validate_evidence_record(
    value: object,
    *,
    implementation_revision_exists: Callable[[str], bool] | None = None,
) -> tuple[str, ...]:
    """Return record-integrity errors without interpreting them as live proof."""

    if not isinstance(value, Mapping):
        return ("record must be an object",)

    errors: list[str] = []
    _validate_identity(value, errors, implementation_revision_exists)
    package = _validate_package(value.get("package"), errors)
    _validate_environment(value.get("environment"), errors)
    personal = _validate_paths(value.get("paths"), errors)
    _validate_task_plan(value.get("task_plan"), errors)
    tasks = _validate_tasks(value.get("tasks"), errors)
    _validate_supporting_checks(value.get("supporting_checks"), errors)
    _validate_side_effect_assertions(value.get("side_effect_assertions"), errors)
    _validate_reviews(value.get("reviews"), errors)
    _validate_unproven(value.get("unproven"), errors)
    _validate_sensitive_material(value, errors)

    rows = value.get("rows")
    if not isinstance(rows, Mapping):
        return tuple([*errors, "rows must be an object"])

    outcomes: list[str] = []
    for row_id in ROW_IDS:
        row = rows.get(row_id)
        if row is None:
            errors.append(f"missing row {row_id}")
            continue
        outcome = _validate_row_common(row_id, row, errors)
        if outcome is None or not isinstance(row, Mapping):
            continue
        outcomes.append(outcome)
        if outcome in {"PASS", "FAIL"}:
            _validate_actual_row(row_id, outcome, row, tasks, errors)
            _validate_result_prerequisites(row_id, outcome, value, errors)
        elif outcome == "BLOCKED":
            blocker = row.get("blocker")
            if not _is_text(blocker):
                errors.append(f"row {row_id} BLOCKED has no blocker")

        if row_id == "D-01" and outcome in {"PASS", "FAIL"}:
            _validate_d01(row, value.get("paths"), errors)
        if row_id == "D-02" and outcome in {"PASS", "FAIL"}:
            _validate_d02(
                row,
                package,
                personal,
                value.get("implementation_revision"),
                value.get("paths"),
                tasks,
                errors,
            )
        if row_id == "D-03" and outcome in {"PASS", "FAIL"}:
            _validate_d03(row, tasks, value.get("paths"), errors)
        if row_id == "D-04" and outcome in {"PASS", "FAIL"}:
            _validate_d04(row, errors)

    for index, row_id in enumerate(rows):
        if row_id not in ROW_IDS:
            errors.append(f"unknown row at index {index}")

    if any(outcome in {"PASS", "FAIL"} for outcome in outcomes):
        _validate_fixture(value.get("fixture"), errors)
    return tuple(errors)


def _validate_identity(
    value: Mapping[object, object],
    errors: list[str],
    implementation_revision_exists: Callable[[str], bool] | None,
) -> None:
    if value.get("schema_version") != "issue31-evidence-v1":
        errors.append("unexpected schema_version")
    if value.get("issue") != 31:
        errors.append("unexpected issue")
    timestamp = value.get("recorded_at_utc")
    if not isinstance(timestamp, str) or not _UTC_TIMESTAMP.fullmatch(timestamp):
        errors.append("invalid recorded_at_utc")
    for field in ("base_revision", "implementation_revision", "specification_revision"):
        revision = value.get(field)
        if not isinstance(revision, str) or not _REVISION.fullmatch(revision):
            errors.append(f"invalid {field}")
    if value.get("base_revision") != PINNED_BASE_REVISION:
        errors.append("unexpected base_revision")
    if value.get("specification_revision") != SPECIFICATION_REVISION:
        errors.append("unexpected specification_revision")
    implementation_revision = value.get("implementation_revision")
    if (
        implementation_revision_exists is not None
        and isinstance(implementation_revision, str)
        and _REVISION.fullmatch(implementation_revision)
        and not implementation_revision_exists(implementation_revision)
    ):
        errors.append("unknown implementation_revision")


def _validate_package(value: object, errors: list[str]) -> Mapping[object, object] | None:
    if not isinstance(value, Mapping):
        errors.append("package must be an object")
        return None
    tree = value.get("tree")
    if not isinstance(tree, str) or not _REVISION.fullmatch(tree):
        errors.append("package has invalid tree")
    key_hashes = value.get("key_file_sha256")
    _validate_key_hashes(key_hashes, "package key_file_sha256", errors)
    return value


def _validate_environment(value: object, errors: list[str]) -> None:
    if not isinstance(value, Mapping):
        errors.append("environment must be an object")
        return
    host = value.get("host")
    if not isinstance(host, Mapping):
        errors.append("environment has invalid host")
    else:
        for field in ("os", "architecture"):
            if not _is_text(host.get(field)):
                errors.append(f"environment host has invalid {field}")
    desktop = value.get("desktop")
    if not isinstance(desktop, Mapping) or not isinstance(desktop.get("observed"), bool):
        errors.append("environment has invalid desktop")
    elif desktop["observed"] and (
        not _is_text(desktop.get("version")) or not _is_text(desktop.get("bundle"))
    ):
        errors.append("environment observed desktop is incomplete")
    tools = value.get("tools")
    if not isinstance(tools, Mapping):
        errors.append("environment has invalid tools")
    else:
        for field in ("codex_cli", "python", "yt_dlp", "ffmpeg", "ffprobe"):
            if not _is_version_observation(tools.get(field)):
                errors.append(f"environment tools has invalid {field}")


def _validate_paths(value: object, errors: list[str]) -> Mapping[object, object] | None:
    if not isinstance(value, Mapping):
        errors.append("paths must be an object")
        return None
    repository = value.get("repository")
    if not _is_text(repository):
        errors.append("paths has invalid repository")
    elif not _is_observed_path(repository):
        errors.append("paths has a placeholder repository")
    personal = value.get("personal")
    if not isinstance(personal, Mapping):
        errors.append("paths has invalid personal")
        return None
    for field in ("literal", "resolved", "revision", "tree"):
        item = personal.get(field)
        if field in {"revision", "tree"}:
            if not isinstance(item, str) or not _REVISION.fullmatch(item):
                errors.append(f"personal has invalid {field}")
        elif not _is_text(item):
            errors.append(f"personal has invalid {field}")
        elif not _is_observed_path(item):
            errors.append(f"personal has a placeholder {field}")
    _validate_key_hashes(personal.get("key_file_sha256"), "personal key_file_sha256", errors)
    return personal


def _validate_task_plan(value: object, errors: list[str]) -> None:
    if not isinstance(value, list) or not value:
        errors.append("task_plan must be a non-empty list")
        return
    for index, task in enumerate(value):
        if not isinstance(task, Mapping):
            errors.append(f"task_plan {index} must be an object")
            continue
        for field in (
            "title",
            "primary_folder",
            "sanitized_prompt",
            "expected_writes",
            "intended_evidence",
        ):
            if not _is_text(task.get(field)):
                errors.append(f"task_plan {index} has invalid {field}")


def _validate_tasks(value: object, errors: list[str]) -> dict[str, Mapping[object, object]]:
    if not isinstance(value, list):
        errors.append("tasks must be a list")
        return {}
    tasks: dict[str, Mapping[object, object]] = {}
    for index, task in enumerate(value):
        if not isinstance(task, Mapping):
            errors.append(f"task {index} must be an object")
            continue
        task_label = f"task {index}"
        task_id = task.get("id")
        if not _is_text(task_id):
            errors.append(f"task {index} has invalid id")
            continue
        if task_id in tasks:
            errors.append(f"duplicate task id at index {index}")
            continue
        tasks[task_id] = task
        if set(task).difference(_TASK_FIELDS):
            errors.append(f"{task_label} has unsupported fields")
        for field in ("title", "primary_folder", "sanitized_prompt", "command_trace"):
            if not _is_text(task.get(field)):
                errors.append(f"{task_label} has invalid {field}")
        if _is_text(task.get("primary_folder")) and not _is_observed_path(
            task["primary_folder"]
        ):
            errors.append(f"{task_label} has a placeholder primary_folder")
        if task.get("fresh_target_macos_desktop") is not True:
            errors.append(f"{task_label} is not a fresh target-macOS Desktop task")
        selected = task.get("selected_skill_path")
        inventory = task.get("inventory_path")
        alias = task.get("displayed_alias")
        script = task.get("script_path")
        if selected is None:
            if any(item is not None for item in (inventory, alias, script)):
                errors.append(f"{task_label} has inconsistent unselected skill fields")
        elif not all(_is_text(item) for item in (selected, inventory, alias, script)):
            errors.append(f"{task_label} has invalid selected skill fields")
        elif not all(_is_observed_path(item) for item in (selected, inventory, script)):
            errors.append(f"{task_label} has placeholder selected skill fields")
        elif not selected.endswith("/SKILL.md"):
            errors.append(f"{task_label} has an invalid selected_skill_path")
        else:
            if inventory != selected:
                errors.append(
                    f"{task_label} inventory_path does not match selected_skill_path"
                )
            if alias != "watch":
                errors.append(f"{task_label} has an invalid displayed_alias")
            expected_script = f"{selected.rsplit('/SKILL.md', 1)[0]}/scripts/prepare_visual.py"
            if script != expected_script:
                errors.append(f"{task_label} script_path is not a bundled script")
    return tasks


def _validate_supporting_checks(value: object, errors: list[str]) -> None:
    if not isinstance(value, list) or not value:
        errors.append("supporting_checks must be a non-empty list")
        return
    for index, check in enumerate(value):
        if not isinstance(check, Mapping):
            errors.append(f"supporting_check {index} must be an object")
            continue
        if check.get("scope") != "static_integrity_only":
            errors.append(f"supporting_check {index} has invalid scope")
        if check.get("outcome") not in ALLOWED_OUTCOMES:
            errors.append(f"supporting_check {index} has invalid outcome")
        for field in ("name", "command", "count", "trace"):
            if not _is_text(check.get(field)):
                errors.append(f"supporting_check {index} has invalid {field}")
        exit_code = check.get("exit_code")
        if isinstance(exit_code, bool) or not isinstance(exit_code, int) or exit_code < 0:
            errors.append(f"supporting_check {index} has invalid exit_code")
        limitations = check.get("limitations")
        if (
            not isinstance(limitations, list)
            or not limitations
            or any(not _is_text(item) for item in limitations)
        ):
            errors.append(f"supporting_check {index} has invalid limitations")


def _validate_side_effect_assertions(value: object, errors: list[str]) -> None:
    if not isinstance(value, Mapping):
        errors.append("side_effect_assertions must be an object")
        return
    if not isinstance(value.get("host_audit_available"), bool):
        errors.append("side_effect_assertions has invalid host_audit_available")
    for field in _SIDE_EFFECT_FIELDS:
        if not isinstance(value.get(field), bool):
            errors.append(f"side_effect_assertions has invalid {field}")
        elif value[field] is not False:
            errors.append(f"side_effect_assertions must keep {field} false")


def _validate_reviews(value: object, errors: list[str]) -> None:
    if not isinstance(value, Mapping):
        errors.append("reviews must be an object")
        return
    for axis in ("standards", "spec"):
        if value.get(axis) not in ALLOWED_OUTCOMES:
            errors.append(f"reviews has invalid {axis} outcome")


def _validate_unproven(value: object, errors: list[str]) -> None:
    if not isinstance(value, list) or any(not _is_text(item) for item in value):
        errors.append("unproven must be a text list")
        return
    missing = _UNPROVEN.difference(value)
    if missing:
        errors.append("unproven is missing required boundaries")


def _validate_sensitive_material(value: object, errors: list[str]) -> None:
    def visit(item: object, path: str, context: str) -> None:
        if isinstance(item, Mapping):
            for key, nested in item.items():
                if isinstance(key, str):
                    key_path = f"{path}.field"
                    if _is_forbidden_raw_field(key) and not _is_scoped_safe_sensitive_field(
                        context, key, nested
                    ):
                        errors.append(f"forbidden raw evidence field at {key_path}")
                    if _contains_sensitive_text(key):
                        errors.append(f"sensitive mapping key at {key_path}")
                else:
                    key_path = f"{path}.non_text_key"
                visit(nested, key_path, _next_sensitive_context(context, key))
        elif isinstance(item, list):
            for index, nested in enumerate(item):
                visit(nested, f"{path}[{index}]", "other")
        elif isinstance(item, str) and _contains_sensitive_text(item):
            errors.append(f"sensitive value at {path}")

    visit(value, "record", "root")


def _validate_row_common(
    row_id: str, value: object, errors: list[str]
) -> str | None:
    if not isinstance(value, Mapping):
        errors.append(f"row {row_id} must be an object")
        return None
    outcome = value.get("outcome")
    if outcome not in ALLOWED_OUTCOMES:
        errors.append(f"row {row_id} has invalid outcome")
        return None
    if not _is_text(value.get("normative_meaning")):
        errors.append(f"row {row_id} has no normative_meaning")
    if value.get("proof_scope") != "target_macos_desktop":
        errors.append(f"row {row_id} has invalid proof_scope")
    if not _is_text(value.get("sanitized_stimulus")):
        errors.append(f"row {row_id} has invalid sanitized_stimulus")
    if not _is_text(value.get("trace")):
        errors.append(f"row {row_id} has no trace")
    decisions = value.get("approval_decisions")
    if not isinstance(decisions, list) or not decisions:
        errors.append(f"row {row_id} has no approval_decisions")
    else:
        for index, decision in enumerate(decisions):
            if not isinstance(decision, Mapping) or not all(
                _is_text(decision.get(field))
                for field in ("category", "decision", "pre_check", "post_check")
            ):
                errors.append(f"row {row_id} has invalid approval_decision {index}")
    checks = value.get("side_effect_checks")
    if not isinstance(checks, Mapping) or not checks:
        errors.append(f"row {row_id} has invalid side_effect_checks")
    _validate_artifacts(row_id, value.get("artifacts"), errors)
    limits = value.get("limitations")
    if not isinstance(limits, list) or not limits or any(not _is_text(item) for item in limits):
        errors.append(f"row {row_id} has invalid limitations")
    basis = value.get("qualification_basis")
    if not isinstance(basis, list) or not basis or any(not _is_text(item) for item in basis):
        errors.append(f"row {row_id} has invalid qualification_basis")
    return outcome if isinstance(outcome, str) else None


def _validate_artifacts(row_id: str, value: object, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append(f"row {row_id} has invalid artifacts")
        return
    for index, artifact in enumerate(value):
        if not isinstance(artifact, Mapping):
            errors.append(f"row {row_id} has a non-object artifact at index {index}")
            continue
        if not _is_text(artifact.get("id")):
            errors.append(f"row {row_id} has an artifact with invalid id")
        digest = artifact.get("sha256")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            errors.append(f"row {row_id} artifact {index} has invalid sha256")


def _validate_actual_row(
    row_id: str,
    outcome: str,
    row: Mapping[object, object],
    tasks: Mapping[str, Mapping[object, object]],
    errors: list[str],
) -> None:
    refs = row.get("task_refs")
    if not isinstance(refs, list) or not refs or any(not _is_text(ref) for ref in refs):
        errors.append(f"row {row_id} needs actual task_refs for PASS or FAIL")
    else:
        for index, task_id in enumerate(refs):
            if task_id not in tasks:
                errors.append(f"row {row_id} references an unknown task at index {index}")
    selected_paths = row.get("selected_skill_paths")
    if (
        not isinstance(selected_paths, list)
        or not selected_paths
        or any(not _is_text(path) for path in selected_paths)
    ):
        errors.append(f"row {row_id} needs selected_skill_paths for PASS or FAIL")
    basis = row.get("qualification_basis")
    if not isinstance(basis, list) or "actual_target_macos_desktop_task" not in basis:
        errors.append(f"row {row_id} {outcome} has no actual Desktop qualification basis")
    if isinstance(refs, list) and isinstance(selected_paths, list):
        observed_paths = {
            task.get("selected_skill_path")
            for task_id in refs
            if isinstance(task_id, str)
            for task in (tasks.get(task_id),)
            if isinstance(task, Mapping) and _is_text(task.get("selected_skill_path"))
        }
        if any(path not in observed_paths for path in selected_paths):
            errors.append(f"row {row_id} selected_skill_paths do not match its tasks")
    checks = row.get("side_effect_checks")
    if isinstance(checks, Mapping):
        for field in _SIDE_EFFECT_FIELDS:
            if checks.get(field) is not False:
                errors.append(f"row {row_id} has invalid {field} side-effect check")


def _validate_d01(
    row: Mapping[object, object], paths: object, errors: list[str]
) -> None:
    if not isinstance(paths, Mapping) or not _is_text(paths.get("repository")):
        return
    expected = f"{paths['repository']}/SKILL.md"
    selected = row.get("selected_skill_paths")
    if isinstance(selected, list) and expected not in selected:
        errors.append("row D-01 did not select the repository SKILL.md")


def _validate_d02(
    row: Mapping[object, object],
    package: Mapping[object, object] | None,
    personal: Mapping[object, object] | None,
    implementation_revision: object,
    paths: object,
    tasks: Mapping[str, Mapping[object, object]],
    errors: list[str],
) -> None:
    if package is not None and personal is not None:
        if personal.get("revision") != implementation_revision:
            errors.append("personal package revision does not match implementation_revision")
        if package.get("tree") != personal.get("tree"):
            errors.append("personal package tree does not match package")
        if package.get("key_file_sha256") != personal.get("key_file_sha256"):
            errors.append("personal package key_file_sha256 does not match package")
        selected = row.get("selected_skill_paths")
        expected = f"{personal['literal']}/SKILL.md"
        if isinstance(selected, list) and expected not in selected:
            errors.append("row D-02 did not select the personal SKILL.md")
    if isinstance(paths, Mapping) and _is_text(paths.get("repository")):
        repository_root = str(paths["repository"]).split("/.agents/", 1)[0]
        refs = row.get("task_refs")
        if isinstance(refs, list):
            for task_id in refs:
                task = tasks.get(task_id) if isinstance(task_id, str) else None
                if isinstance(task, Mapping) and task.get("primary_folder") == repository_root:
                    errors.append("row D-02 did not use a neutral primary folder")
    refusal = row.get("existing_target_refusal")
    if not isinstance(refusal, Mapping):
        errors.append("row D-02 has invalid existing_target_refusal")
        return
    for field in (
        "target_identity_before",
        "target_identity_after",
        "target_sha256_before",
        "target_sha256_after",
    ):
        item = refusal.get(field)
        if not isinstance(item, str) or not _SHA256.fullmatch(item):
            errors.append(f"row D-02 has invalid {field}")
    if (
        refusal.get("target_identity_before") != refusal.get("target_identity_after")
        or refusal.get("target_sha256_before") != refusal.get("target_sha256_after")
        or refusal.get("refused") is not True
    ):
        errors.append("row D-02 existing target was not preserved and refused")


def _validate_d03(
    row: Mapping[object, object],
    tasks: Mapping[str, Mapping[object, object]],
    paths: object,
    errors: list[str],
) -> None:
    controls = row.get("trigger_controls")
    if not isinstance(controls, Mapping):
        errors.append("row D-03 has invalid trigger_controls")
    else:
        expected = {
            "explicit": True,
            "implicit": True,
            "near_miss": False,
            "negative": False,
        }
        for name, selected_watch in expected.items():
            control = controls.get(name)
            if not isinstance(control, Mapping):
                errors.append(f"row D-03 has invalid {name} control")
                continue
            if control.get("selected_watch") is not selected_watch:
                errors.append(f"row D-03 has invalid {name} selection")
            task_ref = control.get("task_ref")
            if not _is_text(task_ref) or task_ref not in tasks:
                errors.append(f"row D-03 has invalid {name} task_ref")
            elif tasks[task_ref].get("selected_skill_path") is None and selected_watch:
                errors.append(f"row D-03 {name} control did not select watch")
            elif tasks[task_ref].get("selected_skill_path") is not None and not selected_watch:
                errors.append(f"row D-03 {name} control selected watch")
            if name in {"near_miss", "negative"}:
                if control.get("watch_script_started") is not False:
                    errors.append(f"row D-03 {name} control started watch")
                if control.get("network_activity") is not False:
                    errors.append(f"row D-03 {name} control has network activity")
                if control.get("media_process_started") is not False:
                    errors.append(f"row D-03 {name} control started a media process")
                if control.get("long_running_work") is not False:
                    errors.append(f"row D-03 {name} control started long-running work")

    duplicate_paths = row.get("duplicate_paths")
    if not isinstance(duplicate_paths, Mapping):
        errors.append("row D-03 has invalid duplicate_paths")
    elif (
        not _is_text(duplicate_paths.get("repository"))
        or not _is_text(duplicate_paths.get("personal"))
        or duplicate_paths.get("repository") == duplicate_paths.get("personal")
        or duplicate_paths.get("path_isolated") is not True
    ):
        errors.append("row D-03 did not establish duplicate-path isolation")
    elif isinstance(paths, Mapping) and isinstance(paths.get("personal"), Mapping):
        expected_repository = f"{paths.get('repository')}/SKILL.md"
        expected_personal = f"{paths['personal'].get('literal')}/SKILL.md"
        if (
            duplicate_paths.get("repository") != expected_repository
            or duplicate_paths.get("personal") != expected_personal
        ):
            errors.append("row D-03 has unexpected duplicate paths")

    reload = row.get("reload")
    if not isinstance(reload, Mapping):
        errors.append("row D-03 has invalid reload")
        return
    if reload.get("in_task_refresh_proved") is not False:
        errors.append("row D-03 claims in-task refresh")
    restart_count = reload.get("restart_count")
    if isinstance(restart_count, bool) or not isinstance(restart_count, int) or restart_count < 0:
        errors.append("row D-03 has invalid restart_count")
    elif restart_count > 1:
        errors.append("row D-03 has more than one restart")
    for field in ("original_sha256", "probe_sha256", "restored_sha256", "patch_sha256"):
        item = reload.get(field)
        if not isinstance(item, str) or not _SHA256.fullmatch(item):
            errors.append(f"row D-03 has invalid {field}")
    if reload.get("original_sha256") != reload.get("restored_sha256"):
        errors.append("row D-03 metadata probe was not restored")
    task_ref = reload.get("new_task_ref")
    if not _is_text(task_ref) or task_ref not in tasks:
        errors.append("row D-03 has invalid new_task_ref")
    disclaimer = reload.get("disclaimer")
    if not _is_text(disclaimer) or "does not prove refresh inside an already-open task" not in disclaimer:
        errors.append("row D-03 has no fresh-task limitation")


def _validate_d04(row: Mapping[object, object], errors: list[str]) -> None:
    checks = row.get("authority_checks")
    if not isinstance(checks, Mapping):
        errors.append("row D-04 has invalid authority_checks")
        return
    offline = checks.get("offline")
    if not isinstance(offline, Mapping) or offline.get("bundled_runtime") is not True:
        errors.append("row D-04 did not use the bundled runtime")
    elif (
        isinstance(offline.get("inspected_frame_count"), bool)
        or not isinstance(offline.get("inspected_frame_count"), int)
        or offline.get("inspected_frame_count", 0) < 1
    ):
        errors.append("row D-04 has no host-inspected frame")

    network = checks.get("network_denial")
    if not isinstance(network, Mapping):
        errors.append("row D-04 has invalid network_denial")
    else:
        required = {
            "source_network_approved": False,
            "state": "stopped",
            "stage": "metadata",
            "category": "network_approval_required",
        }
        if any(network.get(field) != expected for field, expected in required.items()):
            errors.append("row D-04 has invalid network denial state")
        if network.get("attempt_count") != 0 or network.get("dns_http_activity") is not False:
            errors.append("row D-04 network denial has outbound activity")
        if network.get("source") != _RESERVED_NETWORK_DENIAL_SOURCE:
            errors.append("row D-04 has an unexpected network denial source")

    denied_write = checks.get("outside_workspace_write_denial")
    if not isinstance(denied_write, Mapping):
        errors.append("row D-04 has invalid outside_workspace_write_denial")
    else:
        if not _is_text(denied_write.get("sentinel_path")):
            errors.append("row D-04 has no denied write sentinel")
        elif not _is_observed_path(denied_write["sentinel_path"]):
            errors.append("row D-04 has a placeholder denied write sentinel")
        if (
            denied_write.get("target_existed_before") is not False
            or denied_write.get("target_exists_after") is not False
            or denied_write.get("fallback_target_exists") is not False
        ):
            errors.append("row D-04 denied write created a target")
        if denied_write.get("parent_unchanged") is not True:
            errors.append("row D-04 denied write changed its parent")

    fallback = checks.get("local_frame_fallback")
    if not isinstance(fallback, Mapping):
        errors.append("row D-04 has invalid local_frame_fallback")
        return
    if (
        fallback.get("successful_inspection_before") is not True
        or fallback.get("failure_induced") is not True
    ):
        errors.append("row D-04 has invalid local-frame fallback stimulus")
    if (
        fallback.get("visual_observation_created") is not False
        or fallback.get("visual_claim_made") is not False
    ):
        errors.append("row D-04 fallback made a visual claim")
    for field in ("original_sha256", "restored_sha256"):
        item = fallback.get(field)
        if not isinstance(item, str) or not _SHA256.fullmatch(item):
            errors.append(f"row D-04 has invalid fallback {field}")
    if fallback.get("original_sha256") != fallback.get("restored_sha256"):
        errors.append("row D-04 frame fixture was not restored")
    if not _is_text(fallback.get("fixture_path")):
        errors.append("row D-04 has no fallback fixture path")
    elif not _is_observed_path(fallback["fixture_path"]):
        errors.append("row D-04 has a placeholder fallback fixture path")
    if (
        not _is_text(fallback.get("original_mode"))
        or fallback.get("original_mode") != fallback.get("restored_mode")
    ):
        errors.append("row D-04 frame fixture mode was not restored")


def _validate_result_prerequisites(
    row_id: str,
    outcome: str,
    value: Mapping[object, object],
    errors: list[str],
) -> None:
    environment = value.get("environment")
    desktop = environment.get("desktop") if isinstance(environment, Mapping) else None
    if not isinstance(desktop, Mapping) or desktop.get("observed") is not True:
        errors.append(f"{outcome} rows require observed Desktop version and bundle")
    if outcome == "PASS":
        reviews = value.get("reviews")
        if not isinstance(reviews, Mapping) or any(
            reviews.get(axis) != "PASS" for axis in ("standards", "spec")
        ):
            errors.append("PASS rows require passing independent reviews")
    if row_id == "D-04" and outcome == "PASS":
        assertions = value.get("side_effect_assertions")
        if (
            not isinstance(assertions, Mapping)
            or assertions.get("host_audit_available") is not True
        ):
            errors.append("PASS rows require host-audited side-effect checks")


def _validate_fixture(value: object, errors: list[str]) -> None:
    if not isinstance(value, Mapping):
        errors.append("actual Desktop rows require a fixture")
        return
    if value.get("kind") != "synthetic_local":
        errors.append("fixture has invalid kind")
    if not _is_text(value.get("generation_command")):
        errors.append("fixture has invalid generation_command")
    for field in ("mp4_sha256", "jpeg_sha256"):
        digest = value.get(field)
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            errors.append(f"fixture has invalid {field}")


def _validate_key_hashes(value: object, label: str, errors: list[str]) -> None:
    if not isinstance(value, Mapping):
        errors.append(f"{label} must be an object")
        return
    for path in ("SKILL.md", "agents/openai.yaml"):
        digest = value.get(path)
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            errors.append(f"{label} has invalid {path}")


def _is_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_observed_path(value: object) -> bool:
    return (
        _is_text(value)
        and value.startswith("/")
        and "$" not in value
        and "<" not in value
        and ">" not in value
    )


def _is_version_observation(value: object) -> bool:
    if _is_text(value):
        return True
    return (
        isinstance(value, Mapping)
        and value.get("observed") is False
        and value.get("value") is None
        and _is_text(value.get("limitation"))
    )


def _contains_sensitive_text(value: str) -> bool:
    raw_urls = _RAW_URL.findall(value)
    return bool(
        _QUERY_URL.search(value)
        or _URL_USERINFO.search(value)
        or _ENCODED_URL.search(value)
        or _AUTHORIZATION.search(value)
        or _SECRET.search(value)
        or _JWT.search(value)
        or _ENV_SECRET.search(value)
        or _BEARER_CREDENTIAL.search(value)
        or _CREDENTIAL_HEADER.search(value)
        or any(url != _RESERVED_NETWORK_DENIAL_SOURCE for url in raw_urls)
    )


def _is_forbidden_raw_field(value: str) -> bool:
    normalized = _normalized_field_name(value)
    compact = normalized.replace("_", "")
    forbidden_names = _FORBIDDEN_RAW_FIELDS.union(
        {
            "api_key",
            "apikey",
            "authorization",
            "credential",
            "credentials",
            "password",
            "private_key",
            "secret",
            "secret_key",
            "secretkey",
            "token",
        }
    )
    forbidden_compact = {name.replace("_", "") for name in forbidden_names}
    if (
        normalized in forbidden_names
        or compact in forbidden_compact
        or compact.endswith(
            (
                "apikey",
                "captionurl",
                "credential",
                "credentials",
                "privatekey",
                "secret",
                "secretkey",
                "token",
            )
        )
        or normalized.endswith(
        (
            "_api_key",
            "_credential",
            "_credentials",
            "_receipt",
            "_secret",
            "_token",
            "_url",
        )
        )
    ):
        return True
    parts = set(normalized.split("_"))
    if {
        "authorization",
        "cookie",
        "credential",
        "credentials",
        "dotenv",
        "env",
        "password",
        "receipt",
        "url",
    }.intersection(parts):
        return True
    return "environment" in parts and "dump" in parts


def _next_sensitive_context(context: str, key: object) -> str:
    if not isinstance(key, str):
        return "other"
    if context == "root":
        if key == "side_effect_assertions":
            return "side_effect_assertions"
        if key == "rows":
            return "rows"
    elif context == "rows" and key in ROW_IDS:
        return "row"
    elif context == "row" and key == "side_effect_checks":
        return "row_side_effect_checks"
    return "other"


def _is_scoped_safe_sensitive_field(context: str, key: str, value: object) -> bool:
    return (
        key == "credential_read"
        and value is False
        and context in {"side_effect_assertions", "row_side_effect_checks"}
    )


def _normalized_field_name(value: str) -> str:
    with_camel_boundaries = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value)
    return re.sub(r"[^a-zA-Z0-9]+", "_", with_camel_boundaries).lower().strip("_")
