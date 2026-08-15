"""Independent support for Issue #30 qualification tests and evidence records.

This module is intentionally outside the canonical watch skill.  It supplies
only test/evidence contracts; it never contacts media, caption, or provider
hosts and never deletes a caller workspace.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping


ROW_IDS = (
    "H-01",
    "H-02",
    "H-03",
    "H-04",
    "H-05",
    "H-06",
    "H-07",
    "H-08",
    "H-09",
    "H-10",
    "S-01",
    "S-02",
    "S-03",
    "S-04",
)

ALLOWED_OUTCOMES = frozenset({"PASS", "FAIL", "BLOCKED", "UNVERIFIED"})
PINNED_BASE_REVISION = "dcf58a30090c56a9ee04addf4d706a5a85815133"

_REVISION = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def validate_evidence_record(
    value: object,
    *,
    implementation_revision_exists: Callable[[str], bool] | None = None,
) -> tuple[str, ...]:
    """Return all schema errors without interpreting evidence as a live result."""

    if not isinstance(value, Mapping):
        return ("record must be an object",)

    errors: list[str] = []
    if value.get("schema_version") != "issue30-evidence-v1":
        errors.append("unexpected schema_version")
    if value.get("issue") != 30:
        errors.append("unexpected issue")
    for field in ("base_revision", "implementation_revision", "specification_revision"):
        revision = value.get(field)
        if not isinstance(revision, str) or not _REVISION.fullmatch(revision):
            errors.append(f"invalid {field}")
    if value.get("base_revision") != PINNED_BASE_REVISION:
        errors.append("unexpected base_revision")
    if value.get("specification_revision") != PINNED_BASE_REVISION:
        errors.append("unexpected specification_revision")
    implementation_revision = value.get("implementation_revision")
    if (
        implementation_revision_exists is not None
        and isinstance(implementation_revision, str)
        and _REVISION.fullmatch(implementation_revision)
        and not implementation_revision_exists(implementation_revision)
    ):
        errors.append("unknown implementation_revision")

    scope = value.get("scope")
    if not isinstance(scope, Mapping):
        errors.append("scope must be an object")
    else:
        if not isinstance(scope.get("classification"), str) or not scope[
            "classification"
        ].strip():
            errors.append("scope has no classification")
        if scope.get("live_activity") is not False:
            errors.append("scope must declare live_activity false")
        if scope.get("closure_rows") != list(ROW_IDS):
            errors.append("scope has unexpected closure_rows")

    environment = value.get("environment")
    if not isinstance(environment, Mapping):
        errors.append("environment must be an object")
    else:
        for field in ("os", "python", "yt_dlp", "ffmpeg", "ffprobe"):
            if not isinstance(environment.get(field), str) or not environment[field].strip():
                errors.append(f"environment has invalid {field}")

    commands = value.get("commands")
    if not isinstance(commands, list) or not commands:
        errors.append("commands must be a non-empty list")
    else:
        for index, command in enumerate(commands):
            if not isinstance(command, Mapping):
                errors.append(f"command {index} must be an object")
                continue
            for field in ("command", "result", "scope"):
                entry = command.get(field)
                if not isinstance(entry, str) or not entry.strip():
                    errors.append(f"command {index} has invalid {field}")
            result = command.get("result")
            if isinstance(result, str) and result.split(":", 1)[0] not in ALLOWED_OUTCOMES:
                errors.append(f"command {index} has invalid result outcome")

    reviews = value.get("reviews")
    if not isinstance(reviews, Mapping):
        errors.append("reviews must be an object")
    else:
        for axis in ("standards", "spec"):
            if reviews.get(axis) not in ALLOWED_OUTCOMES:
                errors.append(f"reviews has invalid {axis} outcome")

    rows = value.get("rows")
    if not isinstance(rows, Mapping):
        return tuple([*errors, "rows must be an object"])

    for row_id in ROW_IDS:
        row = rows.get(row_id)
        if row is None:
            errors.append(f"missing row {row_id}")
            continue
        if not isinstance(row, Mapping):
            errors.append(f"row {row_id} must be an object")
            continue
        if row.get("outcome") not in ALLOWED_OUTCOMES:
            errors.append(f"row {row_id} has invalid outcome")
        if not isinstance(row.get("normative_meaning"), str) or not row[
            "normative_meaning"
        ].strip():
            errors.append(f"row {row_id} has no normative_meaning")
        expected_scope = "hermetic" if row_id.startswith("H-") else "synthetic"
        if row.get("proof_scope") != expected_scope:
            errors.append(f"row {row_id} has invalid proof_scope")
        trace = row.get("trace")
        if not isinstance(trace, str) or not trace.strip():
            errors.append(f"row {row_id} has no trace")
        if row.get("approval_status") != "not_required_offline":
            errors.append(f"row {row_id} has invalid approval_status")
        tests = row.get("tests")
        if (
            not isinstance(tests, list)
            or not tests
            or any(not isinstance(test, str) or not test.strip() for test in tests)
        ):
            errors.append(f"row {row_id} has invalid tests")
        artifacts = row.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            errors.append(f"row {row_id} has invalid artifacts")
        else:
            for artifact in artifacts:
                if not isinstance(artifact, Mapping):
                    errors.append(f"row {row_id} has a non-object artifact")
                    continue
                identifier = artifact.get("id")
                if not isinstance(identifier, str) or not identifier.strip():
                    errors.append(f"row {row_id} has an artifact with invalid id")
                    identifier = "unknown"
                digest = artifact.get("sha256")
                if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
                    errors.append(
                        f"row {row_id} artifact {identifier} has invalid sha256"
                    )
        limits = row.get("limits")
        if (
            not isinstance(limits, list)
            or not limits
            or any(not isinstance(limit, str) or not limit.strip() for limit in limits)
        ):
            errors.append(f"row {row_id} has invalid limits")

    for row_id in rows:
        if row_id not in ROW_IDS:
            errors.append(f"unknown row {row_id}")
    return tuple(errors)
