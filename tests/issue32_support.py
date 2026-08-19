"""Integrity checks for the sanitized Issue #32 live-evidence record.

The validator proves only that the committed card is internally consistent. It
does not replay a network request, inspect a visual frame, or grant authority.
"""

from __future__ import annotations

import re
from collections.abc import Mapping


PINNED_BASE_REVISION = "59ec45e2ffa80946292ce234acfec1706d0f8316"
CAPTION_BYTE_CAP = 4 * 1024 * 1024
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REVISION = re.compile(r"^[0-9a-f]{40}$")
_FORBIDDEN_FIELDS = frozenset(
    {
        "approval_receipt",
        "caption_receipt",
        "raw_caption_url",
        "receipt",
        "cookie",
        "cookies",
        "credential",
        "raw_transcript",
    }
)


def validate_evidence_record(value: object) -> tuple[str, ...]:
    """Return integrity errors without elevating this card into live proof."""

    if not isinstance(value, Mapping):
        return ("record must be an object",)

    errors: list[str] = []
    if value.get("schema_version") != "issue32-live-public-evidence-v1":
        errors.append("unexpected schema_version")
    if value.get("issue") != 32:
        errors.append("unexpected issue")
    if value.get("base_revision") != PINNED_BASE_REVISION:
        errors.append("unexpected base_revision")
    for field in ("base_revision", "implementation_revision", "specification_revision"):
        item = value.get(field)
        if not isinstance(item, str) or not _REVISION.fullmatch(item):
            errors.append(f"invalid {field}")
    if not _is_text(value.get("test_id")):
        errors.append("missing test_id")
    if value.get("outcome") != "PASS":
        errors.append("outcome must be PASS")
    if value.get("coverage") != "partial":
        errors.append("coverage must be partial")
    _validate_environment(value.get("environment"), errors)
    _validate_source(value.get("source"), errors)
    trace = value.get("trace")
    if not isinstance(trace, list) or not trace:
        errors.append("trace must be a non-empty list")

    caption = value.get("caption_run")
    if not isinstance(caption, Mapping):
        errors.append("caption_run must be an object")
    else:
        _validate_caption_run(caption, errors)

    visual = value.get("visual_run")
    if not isinstance(visual, Mapping):
        errors.append("visual_run must be an object")
    else:
        _validate_visual_run(visual, errors)

    qualification = value.get("qualification")
    if not isinstance(qualification, Mapping):
        errors.append("qualification must be an object")
    else:
        if qualification.get("L-01") != "PASS":
            errors.append("qualification L-01 must be PASS")
        if qualification.get("focused_visual_evidence") != "BLOCKED":
            errors.append("qualification focused_visual_evidence must be BLOCKED")
        if qualification.get("release_readiness") != "BLOCKED":
            errors.append("qualification release_readiness must be BLOCKED")

    effects = value.get("side_effect_assertions")
    if not isinstance(effects, Mapping):
        errors.append("side_effect_assertions must be an object")
    else:
        for field in ("provider_contact", "audio_upload", "credential_read"):
            if effects.get(field) is not False:
                errors.append(f"side_effect_assertions {field} must be false")
        for field in ("source_host_request", "native_caption_request"):
            if effects.get(field) is not True:
                errors.append(f"side_effect_assertions {field} must be true")

    _find_forbidden_fields(value, errors)
    return tuple(errors)


def _validate_caption_run(caption: Mapping[object, object], errors: list[str]) -> None:
    if caption.get("source_host") != "www.youtube.com":
        errors.append("caption_run has unexpected source_host")
    if caption.get("source_network_approval") != "approved":
        errors.append("caption_run requires approved source_network_approval")
    if caption.get("caption_network_approval") != "approved_jit":
        errors.append("caption_run requires approved caption_network_approval")
    if caption.get("purpose") != "retrieve_selected_native_caption":
        errors.append("caption_run has invalid purpose")
    if caption.get("byte_cap") != CAPTION_BYTE_CAP:
        errors.append("caption_run has invalid byte_cap")
    if caption.get("coverage") != "partial":
        errors.append("caption_run must retain partial coverage")
    if caption.get("provenance") != "automatic_captions":
        errors.append("caption_run has invalid provenance")
    if caption.get("selected_track") != {
        "language": "en",
        "caption_type": "automatic",
        "format": "vtt",
    }:
        errors.append("caption_run has invalid selected_track")
    if caption.get("redirect_count") != 0:
        errors.append("caption_run has invalid redirect_count")
    if caption.get("segment_count") != 1998:
        errors.append("caption_run has invalid segment_count")
    if caption.get("available_range_seconds") != [1.51, 1835]:
        errors.append("caption_run has invalid available_range_seconds")
    if caption.get("unavailable_range_seconds") != [0, 1.51]:
        errors.append("caption_run has invalid unavailable_range_seconds")
    if caption.get("media_download_completed") is not False:
        errors.append("caption_run media_download_completed must be false")
    artifact = caption.get("artifact")
    if not isinstance(artifact, Mapping):
        errors.append("caption_run artifact must be an object")
        return
    size_bytes = artifact.get("size_bytes")
    if not isinstance(size_bytes, int) or size_bytes < 1:
        errors.append("caption_run artifact has invalid size_bytes")
    elif size_bytes > CAPTION_BYTE_CAP:
        errors.append("caption_run artifact exceeds caption byte cap")
    digest = artifact.get("sha256")
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        errors.append("caption_run artifact has invalid sha256")


def _validate_visual_run(visual: Mapping[object, object], errors: list[str]) -> None:
    if visual.get("focus_seconds") != [469, 479]:
        errors.append("visual_run has invalid focus_seconds")
    if visual.get("max_frames") != 10:
        errors.append("visual_run has invalid max_frames")
    if visual.get("media_acquisition") != "attempted":
        errors.append("visual_run must record attempted media_acquisition")
    if visual.get("http_status") != 403:
        errors.append("visual_run has invalid http_status")
    if visual.get("coverage") != "none":
        errors.append("visual_run 403 outcome must retain none coverage")
    if visual.get("provenance") != "none":
        errors.append("visual_run 403 outcome must retain none provenance")
    if visual.get("outcome") != "BLOCKED":
        errors.append("visual_run 403 outcome must remain BLOCKED")
    frames = visual.get("frames")
    if frames != []:
        errors.append("visual_run 403 outcome must not claim frames")
    claims = visual.get("claims")
    if not isinstance(claims, list):
        errors.append("visual_run claims must be a list")
    elif claims and not frames:
        errors.append("visual_run has claims without inspected frames")
    artifact = visual.get("artifact")
    if not isinstance(artifact, Mapping) or artifact.get("size_bytes") != 0:
        errors.append("visual_run 403 artifact must be recorded as zero bytes")
    elif artifact.get("sha256") != (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    ):
        errors.append("visual_run 403 artifact has unexpected sha256")


def _validate_environment(value: object, errors: list[str]) -> None:
    if not isinstance(value, Mapping):
        errors.append("environment must be an object")
        return
    host = value.get("host")
    if not isinstance(host, Mapping) or not _is_text(host.get("os")) or not _is_text(
        host.get("architecture")
    ):
        errors.append("environment has invalid host")
    desktop = value.get("desktop")
    if not isinstance(desktop, Mapping) or desktop.get("observed") is not False:
        errors.append("environment has invalid desktop")
    tools = value.get("tools")
    if not isinstance(tools, Mapping) or any(
        not _is_text(tools.get(name))
        for name in ("python", "yt_dlp", "ffmpeg", "ffprobe", "deno")
    ):
        errors.append("environment has invalid tools")


def _validate_source(value: object, errors: list[str]) -> None:
    if not isinstance(value, Mapping):
        errors.append("source must be an object")
        return
    if value.get("host") != "www.youtube.com":
        errors.append("source has invalid host")
    if value.get("video_id") != "5Qu2SkSQeBU":
        errors.append("source has invalid video_id")
    if value.get("is_live") is not False or value.get("duration_seconds") != 1835:
        errors.append("source has invalid observed metadata")


def _is_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _find_forbidden_fields(value: object, errors: list[str]) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in _FORBIDDEN_FIELDS:
                errors.append(f"record contains forbidden field {key}")
            _find_forbidden_fields(item, errors)
    elif isinstance(value, list):
        for item in value:
            _find_forbidden_fields(item, errors)
