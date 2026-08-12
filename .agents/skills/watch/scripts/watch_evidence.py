from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import html
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
from typing import Any, Callable, Literal, Mapping, Protocol, Sequence, TypeGuard
from urllib.parse import urlsplit


EvidenceCoverageValue = Literal["complete", "partial", "none"]
Answerability = Literal["supported", "uncertain", "unsupported"]
OutcomeState = Literal[
    "ready",
    "partial",
    "decision_required",
    "consent_required",
    "stopped",
    "failed",
    "canceled",
]
SourceKind = Literal["local", "url"]
EvidenceStage = Literal["validation", "preflight", "metadata"]
FailureCategory = Literal[
    "source_count",
    "ambiguous_source",
    "invalid_source",
    "unsupported_access",
    "non_public_url",
    "unsupported_scheme",
    "invalid_local_path",
    "invalid_request",
    "invalid_json",
    "invalid_control",
    "invalid_question",
    "invalid_detail",
    "invalid_max_frames",
    "invalid_keep_duplicates",
    "invalid_focus",
    "invalid_cues",
    "invalid_output_dir",
    "invalid_selection",
    "missing_dependency",
    "network_approval_required",
    "tool_execution",
    "metadata_probe",
    "unsupported_playlist",
    "unsupported_live_source",
]
DisposalState = Literal["not_created"]
ReuseState = Literal["none", "current_source_only"]
JavaScriptSupportStatus = Literal["available", "unavailable", "unknown", "not_checked"]
DetailMode = Literal["transcript", "efficient", "balanced", "token-burner"]


@dataclass(frozen=True)
class EvidenceCoverage:
    metadata: EvidenceCoverageValue
    transcript: EvidenceCoverageValue
    visual: EvidenceCoverageValue
    overall: EvidenceCoverageValue


@dataclass(frozen=True)
class EvidenceDisposition:
    retained_evidence: bool
    disposal_state: DisposalState
    reuse_state: ReuseState


@dataclass(frozen=True)
class Failure:
    stage: EvidenceStage
    category: FailureCategory
    message: str
    attempts: int
    disposition: EvidenceDisposition


@dataclass(frozen=True)
class Source:
    kind: SourceKind
    value: str
    current: bool


@dataclass(frozen=True)
class ToolStatus:
    name: str
    available: bool
    required_for_metadata: bool
    version: str | None


@dataclass(frozen=True)
class JavaScriptSupport:
    status: JavaScriptSupportStatus
    runtime: str | None


@dataclass(frozen=True)
class WatchControls:
    detail: DetailMode
    focus_start_seconds: float | None
    focus_end_seconds: float | None
    cues_seconds: tuple[float, ...]
    dropped_cues_count: int
    max_frames: int | None
    keep_duplicates: bool
    output_dir: str | None


@dataclass(frozen=True)
class MetadataEvidence:
    title: str | None
    uploader: str | None
    duration_seconds: float | None
    container: str | None
    size_bytes: int | None
    video_codec: str | None
    audio_codec: str | None
    width: int | None
    height: int | None
    is_live: bool


@dataclass(frozen=True)
class EvidenceBundle:
    metadata: MetadataEvidence
    transcript: None = None
    visual: None = None


@dataclass(frozen=True)
class EvidenceOutcome:
    state: OutcomeState
    terminal: bool
    source: Source | None
    coverage: EvidenceCoverage
    answerability: Answerability
    warnings: tuple[str, ...]
    failure: Failure | None
    evidence: EvidenceBundle | None
    tools: tuple[ToolStatus, ...]
    javascript_support: JavaScriptSupport
    controls: WatchControls | None
    report_markdown: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        failure = payload.get("failure")
        if isinstance(failure, dict):
            disposition = failure.pop("disposition")
            failure.update(disposition)
        return payload


NO_EVIDENCE_NO_WORKSPACE = EvidenceDisposition(False, "not_created", "none")
CURRENT_SOURCE_NO_WORKSPACE = EvidenceDisposition(
    False, "not_created", "current_source_only"
)
JAVASCRIPT_NOT_CHECKED = JavaScriptSupport("not_checked", None)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(self, executable: str, arguments: Sequence[str]) -> CommandResult: ...


class SubprocessCommandRunner:
    def run(self, executable: str, arguments: Sequence[str]) -> CommandResult:
        completed = subprocess.run(
            [executable, *arguments],
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            check=False,
            shell=False,
            timeout=30,
        )
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)


class WatchEvidenceRuntime:
    def __init__(
        self,
        command_runner: CommandRunner | None = None,
        find_executable: Callable[[str], str | None] = shutil.which,
    ) -> None:
        self._command_runner = command_runner or SubprocessCommandRunner()
        self._find_executable = find_executable

    def prepare(
        self,
        watch_request: object,
        prior_evidence: object | None = None,
    ) -> EvidenceOutcome:
        del prior_evidence
        if not isinstance(watch_request, Mapping):
            return self.invalid_input(
                "invalid_request", "The watch request must be one JSON object."
            )
        source, validation_failure = self._validate_source(watch_request)
        if validation_failure is not None:
            return self._failure_outcome(
                state="stopped",
                source=source,
                failure=validation_failure,
            )
        assert source is not None

        controls, validation_failure = self._validate_controls(watch_request)
        if validation_failure is not None:
            return self._failure_outcome(
                state="stopped", source=source, failure=validation_failure
            )
        assert controls is not None

        source = Source(source.kind, source.value, True)
        tools, executable_paths, javascript_support = self._preflight(source.kind)
        required_name = "ffprobe" if source.kind == "local" else "yt-dlp"
        required_path = executable_paths[required_name]
        warnings = tuple(
            f"{tool.name} is unavailable; later evidence stages that require it cannot run."
            for tool in tools
            if not tool.available and not tool.required_for_metadata
        )
        if required_path is None:
            return self._failure_outcome(
                state="failed",
                source=source,
                warnings=warnings,
                tools=tools,
                javascript_support=javascript_support,
                controls=controls,
                failure=Failure(
                    stage="preflight",
                    category="missing_dependency",
                    message=(
                        f"Required metadata tool '{required_name}' is unavailable. "
                        "Install it deliberately, then retry; the runtime will not install it."
                    ),
                    attempts=0,
                    disposition=CURRENT_SOURCE_NO_WORKSPACE,
                ),
            )

        if source.kind == "url" and watch_request.get("source_network_approved") is not True:
            return self._failure_outcome(
                state="stopped",
                source=source,
                warnings=warnings,
                tools=tools,
                javascript_support=javascript_support,
                controls=controls,
                failure=Failure(
                    stage="metadata",
                    category="network_approval_required",
                    message=(
                        "Source-host command-network approval is required before yt-dlp "
                        "contacts the public URL host."
                    ),
                    attempts=0,
                    disposition=CURRENT_SOURCE_NO_WORKSPACE,
                ),
            )

        try:
            if source.kind == "local":
                metadata_result = self._local_metadata(required_path, source.value)
            else:
                metadata_result = self._url_metadata(required_path, source.value)
        except (OSError, subprocess.SubprocessError) as error:
            return self._failure_outcome(
                state="failed",
                source=source,
                warnings=warnings,
                tools=tools,
                javascript_support=javascript_support,
                controls=controls,
                failure=Failure(
                    stage="metadata",
                    category="tool_execution",
                    message=_escape_control_sequences(str(error)),
                    attempts=1,
                    disposition=CURRENT_SOURCE_NO_WORKSPACE,
                ),
            )

        if isinstance(metadata_result, Failure):
            outcome_source = (
                Source(source.kind, source.value, False)
                if metadata_result.category == "unsupported_playlist"
                else source
            )
            return self._failure_outcome(
                state=(
                    "stopped"
                    if metadata_result.category.startswith("unsupported_")
                    else "failed"
                ),
                source=outcome_source,
                warnings=warnings,
                tools=tools,
                javascript_support=javascript_support,
                controls=controls,
                failure=metadata_result,
            )

        controls, known_duration_failure = _normalize_controls_after_metadata(
            controls, metadata_result.duration_seconds
        )
        if known_duration_failure is not None:
            return self._failure_outcome(
                state="stopped",
                source=source,
                warnings=warnings,
                tools=tools,
                javascript_support=javascript_support,
                controls=controls,
                failure=known_duration_failure,
            )

        evidence = EvidenceBundle(metadata=metadata_result)
        coverage = EvidenceCoverage("complete", "none", "none", "partial")
        report = _render_report(
            state="partial",
            source=source,
            metadata=metadata_result,
            coverage=coverage,
            answerability="uncertain",
            warnings=warnings,
            tools=tools,
            javascript_support=javascript_support,
            controls=controls,
        )
        return EvidenceOutcome(
            state="partial",
            terminal=True,
            source=source,
            coverage=coverage,
            answerability="uncertain",
            warnings=warnings,
            failure=None,
            evidence=evidence,
            tools=tools,
            javascript_support=javascript_support,
            controls=controls,
            report_markdown=report,
        )

    def invalid_input(
        self, category: FailureCategory, message: str
    ) -> EvidenceOutcome:
        return self._failure_outcome(
            state="stopped",
            source=None,
            failure=_validation_failure(category, message),
        )

    def _validate_source(
        self, watch_request: Mapping[str, object]
    ) -> tuple[Source | None, Failure | None]:
        sources = watch_request.get("sources")
        if not isinstance(sources, Sequence) or isinstance(sources, (str, bytes)):
            source_count = 0
            validated_sources: Sequence[object] | None = None
        else:
            source_count = len(sources)
            validated_sources = sources

        if source_count != 1:
            return None, _validation_failure(
                "source_count",
                "Provide exactly one public HTTP(S) URL or one local video path.",
            )

        assert validated_sources is not None
        source_value = validated_sources[0]
        if not isinstance(source_value, str) or not source_value.strip():
            return None, _validation_failure(
                "ambiguous_source",
                "The source must be one non-empty URL or local video path.",
            )

        try:
            parsed_url = urlsplit(source_value)
        except ValueError:
            return None, _validation_failure(
                "invalid_source", "The source is not a valid public URL or local path."
            )

        if parsed_url.scheme in {"http", "https"}:
            source = Source("url", source_value, False)
            if parsed_url.username or parsed_url.password:
                return None, _validation_failure(
                    "unsupported_access",
                    "Use one public unauthenticated HTTP(S) video URL without credentials.",
                )
            if not parsed_url.hostname:
                return source, _validation_failure(
                    "unsupported_access",
                    "Use one public unauthenticated HTTP(S) video URL without credentials.",
                )
            if _is_non_public_host(parsed_url.hostname):
                return source, _validation_failure(
                    "non_public_url",
                    "Use a public video URL; local and private-network hosts are unsupported.",
                )
            return source, None

        if parsed_url.scheme:
            return None, _validation_failure(
                "unsupported_scheme",
                "Only public HTTP(S) URLs and local video paths are supported.",
            )

        try:
            attempted_path = Path(source_value).expanduser().resolve(strict=False)
        except (OSError, RuntimeError, ValueError):
            return None, _validation_failure(
                "invalid_local_path", "The local video path cannot be resolved safely."
            )
        attempted_source = Source("local", str(attempted_path), False)
        if not attempted_path.is_file() or not os.access(attempted_path, os.R_OK):
            return attempted_source, _validation_failure(
                "invalid_local_path",
                "Local video is missing, unreadable, or not a file: "
                f"{_escape_control_sequences(str(attempted_path))}",
            )
        return attempted_source, None

    def _validate_controls(
        self, watch_request: Mapping[str, object]
    ) -> tuple[WatchControls | None, Failure | None]:
        supported_fields = {
            "sources",
            "question",
            "detail",
            "focus",
            "cues",
            "max_frames",
            "keep_duplicates",
            "output_dir",
            "caption_track",
            "audio_track",
            "source_network_approved",
        }
        unknown_fields = sorted(
            _escape_control_sequences(str(field))
            for field in watch_request
            if field not in supported_fields
        )
        if unknown_fields:
            return None, _validation_failure(
                "invalid_control",
                "Unsupported watch request field(s): " + ", ".join(unknown_fields),
            )

        question = watch_request.get("question")
        if question is not None and not isinstance(question, str):
            return None, _validation_failure(
                "invalid_question", "The optional question must be text."
            )

        detail = watch_request.get("detail", "balanced")
        if not _is_detail_mode(detail):
            return None, _validation_failure(
                "invalid_detail",
                "detail must be transcript, efficient, balanced, or token-burner.",
            )
        max_frames = watch_request.get("max_frames")
        if max_frames is not None and (
            isinstance(max_frames, bool)
            or not isinstance(max_frames, int)
            or max_frames <= 0
        ):
            return None, _validation_failure(
                "invalid_max_frames", "max_frames must be a positive integer."
            )

        keep_duplicates = watch_request.get("keep_duplicates", False)
        if not isinstance(keep_duplicates, bool):
            return None, _validation_failure(
                "invalid_keep_duplicates", "keep_duplicates must be true or false."
            )

        focus_start, focus_end, focus_failure = _validate_focus(
            watch_request.get("focus")
        )
        if focus_failure is not None:
            return None, focus_failure

        cues, cue_failure = _validate_cues(watch_request.get("cues"))
        if cue_failure is not None:
            return None, cue_failure

        output_dir_value = watch_request.get("output_dir")
        output_dir: str | None = None
        if output_dir_value is not None:
            if not isinstance(output_dir_value, str) or not output_dir_value.strip():
                return None, _validation_failure(
                    "invalid_output_dir", "output_dir must be one non-empty path."
                )
            try:
                output_dir = str(
                    Path(output_dir_value).expanduser().resolve(strict=False)
                )
            except (OSError, RuntimeError, ValueError):
                return None, _validation_failure(
                    "invalid_output_dir", "output_dir cannot be resolved safely."
                )

        for selection_name in ("caption_track", "audio_track"):
            selection = watch_request.get(selection_name)
            if selection is not None:
                return None, _validation_failure(
                    "invalid_selection",
                    f"{selection_name} has no matching run-scoped choice in this metadata pass.",
                )

        return (
            WatchControls(
                detail=detail,
                focus_start_seconds=focus_start,
                focus_end_seconds=focus_end,
                cues_seconds=cues,
                dropped_cues_count=0,
                max_frames=max_frames,
                keep_duplicates=keep_duplicates,
                output_dir=output_dir,
            ),
            None,
        )

    def _preflight(
        self, source_kind: SourceKind
    ) -> tuple[
        tuple[ToolStatus, ...], dict[str, str | None], JavaScriptSupport
    ]:
        required_name = "ffprobe" if source_kind == "local" else "yt-dlp"
        executable_paths = {
            name: self._find_executable(name) for name in ("yt-dlp", "ffmpeg", "ffprobe")
        }
        statuses: list[ToolStatus] = []
        for name, executable in executable_paths.items():
            statuses.append(
                ToolStatus(
                    name=name,
                    available=executable is not None,
                    required_for_metadata=name == required_name,
                    version=self._tool_version(name, executable),
                )
            )
        javascript_support = self._javascript_support(executable_paths["yt-dlp"])
        return tuple(statuses), executable_paths, javascript_support

    def _tool_version(self, name: str, executable: str | None) -> str | None:
        if executable is None:
            return None
        argument = "--version" if name == "yt-dlp" else "-version"
        arguments = (
            ["--ignore-config", "--no-plugin-dirs", "--no-update", argument]
            if name == "yt-dlp"
            else [argument]
        )
        try:
            result = self._command_runner.run(executable, arguments)
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        first_line = result.stdout.splitlines()[0] if result.stdout.splitlines() else ""
        return _escape_control_sequences(first_line) or None

    def _javascript_support(self, yt_dlp: str | None) -> JavaScriptSupport:
        if yt_dlp is None:
            return JavaScriptSupport("unavailable", None)
        try:
            result = self._command_runner.run(
                yt_dlp,
                [
                    "--ignore-config",
                    "--no-plugin-dirs",
                    "--no-cache-dir",
                    "--no-update",
                    "--no-remote-components",
                    "--retries",
                    "0",
                    "--extractor-retries",
                    "0",
                    "--verbose",
                    "--simulate",
                    "--no-warnings",
                    "watch-preflight:",
                ],
            )
        except (OSError, subprocess.SubprocessError):
            return JavaScriptSupport("unknown", None)
        diagnostic = f"{result.stdout}\n{result.stderr}"
        match = re.search(r"^\[debug\] JS runtimes:\s*(.+)$", diagnostic, re.MULTILINE)
        if match is None:
            return JavaScriptSupport("unknown", None)
        runtime = _escape_control_sequences(match.group(1).strip())
        if runtime.casefold() == "none":
            return JavaScriptSupport("unavailable", None)
        return JavaScriptSupport("available", runtime)

    def _local_metadata(self, ffprobe: str, source: str) -> MetadataEvidence | Failure:
        result = self._command_runner.run(
            ffprobe,
            [
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                source,
            ],
        )
        if result.returncode != 0:
            return _metadata_failure("ffprobe", result.stderr)
        try:
            payload = json.loads(result.stdout)
        except (json.JSONDecodeError, TypeError):
            return _metadata_failure("ffprobe", "The tool returned invalid JSON.")
        return _metadata_from_ffprobe(payload)

    def _url_metadata(self, yt_dlp: str, source: str) -> MetadataEvidence | Failure:
        result = self._command_runner.run(
            yt_dlp,
            [
                "--ignore-config",
                "--no-plugin-dirs",
                "--no-playlist",
                "--skip-download",
                "--no-cache-dir",
                "--no-update",
                "--no-remote-components",
                "--dump-single-json",
                "--no-warnings",
                "--socket-timeout",
                "15",
                "--retries",
                "0",
                "--extractor-retries",
                "0",
                "--",
                source,
            ],
        )
        if result.returncode != 0:
            diagnostic = result.stderr or result.stdout
            if _looks_like_unsupported_access(diagnostic):
                return Failure(
                    stage="metadata",
                    category="unsupported_access",
                    message=(
                        "The source appears private, authenticated, unavailable, "
                        "region-limited, age-gated, DRM-protected, or live. No bypass "
                        "will be attempted. Diagnostic: "
                        f"{_escape_control_sequences(diagnostic.strip())}"
                    ),
                    attempts=1,
                    disposition=CURRENT_SOURCE_NO_WORKSPACE,
                )
            return _metadata_failure("yt-dlp", diagnostic)
        try:
            payload = json.loads(result.stdout)
        except (json.JSONDecodeError, TypeError):
            return _metadata_failure("yt-dlp", "The tool returned invalid JSON.")
        if not isinstance(payload, Mapping):
            return _metadata_failure("yt-dlp", "The tool returned an invalid metadata object.")
        if payload.get("_type") in {"playlist", "multi_video"} or isinstance(
            payload.get("entries"), list
        ):
            return Failure(
                stage="metadata",
                category="unsupported_playlist",
                message="Playlists and multi-video sources are unsupported; provide one video URL.",
                attempts=1,
                disposition=CURRENT_SOURCE_NO_WORKSPACE,
            )
        if payload.get("is_live") is True or payload.get("live_status") in {
            "is_live",
            "is_upcoming",
            "post_live",
        }:
            return Failure(
                stage="metadata",
                category="unsupported_live_source",
                message="Live and upcoming video sources are unsupported.",
                attempts=1,
                disposition=CURRENT_SOURCE_NO_WORKSPACE,
            )
        return _metadata_from_ytdlp(payload)

    def _failure_outcome(
        self,
        *,
        state: Literal["stopped", "failed"],
        source: Source | None,
        failure: Failure,
        warnings: tuple[str, ...] = (),
        tools: tuple[ToolStatus, ...] = (),
        javascript_support: JavaScriptSupport = JAVASCRIPT_NOT_CHECKED,
        controls: WatchControls | None = None,
    ) -> EvidenceOutcome:
        coverage = EvidenceCoverage("none", "none", "none", "none")
        return EvidenceOutcome(
            state=state,
            terminal=True,
            source=source,
            coverage=coverage,
            answerability="unsupported",
            warnings=warnings,
            failure=failure,
            evidence=None,
            tools=tools,
            javascript_support=javascript_support,
            controls=controls,
            report_markdown=_render_failure_report(
                state, source, failure, warnings, javascript_support
            ),
        )


def _validation_failure(category: FailureCategory, message: str) -> Failure:
    return Failure(
        stage="validation",
        category=category,
        message=message,
        attempts=0,
        disposition=NO_EVIDENCE_NO_WORKSPACE,
    )


def _is_detail_mode(value: object) -> TypeGuard[DetailMode]:
    return isinstance(value, str) and value in {
        "transcript",
        "efficient",
        "balanced",
        "token-burner",
    }


def _validate_focus(
    value: object,
) -> tuple[float | None, float | None, Failure | None]:
    if value is None:
        return None, None, None
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) != 2
    ):
        return None, None, _validation_failure(
            "invalid_focus", "focus must contain [start, end], with either endpoint optional."
        )
    start_value, end_value = value
    start = _parse_timestamp(start_value) if start_value is not None else None
    end = _parse_timestamp(end_value) if end_value is not None else None
    if (start_value is not None and start is None) or (
        end_value is not None and end is None
    ):
        return None, None, _validation_failure(
            "invalid_focus",
            "focus endpoints must be non-negative seconds, MM:SS, or HH:MM:SS.",
        )
    if start is None and end is None:
        return None, None, _validation_failure(
            "invalid_focus", "focus must provide at least one endpoint."
        )
    if start is not None and end is not None and end <= start:
        return None, None, _validation_failure(
            "invalid_focus", "focus end must be greater than focus start."
        )
    return start, end, None


def _validate_cues(value: object) -> tuple[tuple[float, ...], Failure | None]:
    if value is None:
        return (), None
    if isinstance(value, str):
        raw_values: Sequence[object] = value.split(",")
    elif isinstance(value, Sequence) and not isinstance(value, bytes):
        raw_values = value
    else:
        return (), _validation_failure(
            "invalid_cues", "cues must be comma-separated timestamps or a timestamp list."
        )
    parsed_values: list[float] = []
    for raw_value in raw_values:
        if isinstance(raw_value, str) and not raw_value.strip():
            continue
        timestamp = _parse_timestamp(raw_value)
        if timestamp is None:
            return (), _validation_failure(
                "invalid_cues",
                "Every cue must be non-negative seconds, MM:SS, or HH:MM:SS.",
            )
        parsed_values.append(timestamp)
    return tuple(sorted(set(parsed_values))), None


def _parse_timestamp(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    parts = text.split(":")
    if len(parts) > 3:
        return None
    try:
        numbers = [float(part) for part in parts]
    except ValueError:
        return None
    if any(not math.isfinite(number) or number < 0 for number in numbers):
        return None
    if len(numbers) > 1 and any(number >= 60 for number in numbers[1:]):
        return None
    seconds = 0.0
    for number in numbers:
        seconds = seconds * 60 + number
    return seconds


def _metadata_failure(tool: str, diagnostic: str) -> Failure:
    safe_diagnostic = _escape_control_sequences(diagnostic.strip())
    message = f"{tool} could not read safe source metadata."
    if safe_diagnostic:
        message = f"{message} Diagnostic: {safe_diagnostic}"
    return Failure(
        stage="metadata",
        category="metadata_probe",
        message=message,
        attempts=1,
        disposition=CURRENT_SOURCE_NO_WORKSPACE,
    )


def _normalize_controls_after_metadata(
    controls: WatchControls, duration_seconds: float | None
) -> tuple[WatchControls, Failure | None]:
    if (
        duration_seconds is not None
        and controls.focus_start_seconds is not None
        and controls.focus_start_seconds >= duration_seconds
    ):
        return (
            controls,
            Failure(
                stage="metadata",
                category="invalid_focus",
                message=(
                    "focus start must be before the known source duration "
                    f"({duration_seconds} seconds)."
                ),
                attempts=1,
                disposition=CURRENT_SOURCE_NO_WORKSPACE,
            ),
        )
    if duration_seconds is not None and any(
        cue_seconds > duration_seconds for cue_seconds in controls.cues_seconds
    ):
        return (
            controls,
            Failure(
                stage="metadata",
                category="invalid_cues",
                message=(
                    "Every cue must be at or before the known source duration "
                    f"({duration_seconds} seconds)."
                ),
                attempts=1,
                disposition=CURRENT_SOURCE_NO_WORKSPACE,
            ),
        )
    retained_cues = tuple(
        cue_seconds
        for cue_seconds in controls.cues_seconds
        if (
            controls.focus_start_seconds is None
            or cue_seconds >= controls.focus_start_seconds
        )
        and (
            controls.focus_end_seconds is None
            or cue_seconds <= controls.focus_end_seconds
        )
    )
    return (
        replace(
            controls,
            cues_seconds=retained_cues,
            dropped_cues_count=len(controls.cues_seconds) - len(retained_cues),
        ),
        None,
    )


def _metadata_from_ffprobe(payload: object) -> MetadataEvidence:
    data: Mapping[str, object] = payload if isinstance(payload, Mapping) else {}
    format_value = data.get("format")
    format_data: Mapping[str, object] = (
        format_value if isinstance(format_value, Mapping) else {}
    )
    streams_value = data.get("streams")
    streams: list[object] = streams_value if isinstance(streams_value, list) else []
    video: Mapping[str, object] = next(
        (
            item
            for item in streams
            if isinstance(item, Mapping) and item.get("codec_type") == "video"
        ),
        {},
    )
    audio: Mapping[str, object] = next(
        (
            item
            for item in streams
            if isinstance(item, Mapping) and item.get("codec_type") == "audio"
        ),
        {},
    )
    tags_value = format_data.get("tags")
    tags: Mapping[str, object] = tags_value if isinstance(tags_value, Mapping) else {}
    return MetadataEvidence(
        title=_optional_text(tags.get("title")),
        uploader=_optional_text(tags.get("artist")),
        duration_seconds=_nonnegative_float(format_data.get("duration")),
        container=_optional_text(format_data.get("format_name")),
        size_bytes=_nonnegative_int(format_data.get("size")),
        video_codec=_optional_text(video.get("codec_name")),
        audio_codec=_optional_text(audio.get("codec_name")),
        width=_nonnegative_int(video.get("width")),
        height=_nonnegative_int(video.get("height")),
        is_live=False,
    )


def _metadata_from_ytdlp(data: Mapping[str, object]) -> MetadataEvidence:
    return MetadataEvidence(
        title=_optional_text(data.get("title")),
        uploader=_optional_text(data.get("uploader")),
        duration_seconds=_nonnegative_float(data.get("duration")),
        container=_optional_text(data.get("ext")),
        size_bytes=_nonnegative_int(data.get("filesize") or data.get("filesize_approx")),
        video_codec=_optional_text(data.get("vcodec")),
        audio_codec=_optional_text(data.get("acodec")),
        width=_nonnegative_int(data.get("width")),
        height=_nonnegative_int(data.get("height")),
        is_live=False,
    )


def _looks_like_unsupported_access(diagnostic: str) -> bool:
    normalized = diagnostic.casefold()
    return any(
        marker in normalized
        for marker in (
            "private video",
            "sign in",
            "login required",
            "log in",
            "age-restricted",
            "members-only",
            "drm",
            "not available in your country",
            "region",
            "live event",
            "livestream",
            "video unavailable",
            "removed",
        )
    )


def _is_non_public_host(hostname: str) -> bool:
    normalized = hostname.rstrip(".").casefold()
    if normalized == "localhost" or normalized.endswith(
        (".localhost", ".local", ".internal")
    ):
        return True
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        try:
            packed_address = socket.inet_aton(normalized)
        except OSError:
            return False
        address = ipaddress.ip_address(packed_address)
    return not address.is_global


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = _escape_control_sequences(str(value)).strip()
    return text or None


def _nonnegative_float(value: object) -> float | None:
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _nonnegative_int(value: object) -> int | None:
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _escape_control_sequences(value: str) -> str:
    encoded = json.dumps(value, ensure_ascii=True)
    return encoded[1:-1]


def _render_untrusted_markdown_code(value: object) -> str:
    escaped_value = _escape_control_sequences(str(value))
    return f"<code>{html.escape(escaped_value, quote=True)}</code>"


def _render_preescaped_markdown_code(value: object) -> str:
    return f"<code>{html.escape(str(value), quote=True)}</code>"


def _render_report(
    *,
    state: OutcomeState,
    source: Source,
    metadata: MetadataEvidence,
    coverage: EvidenceCoverage,
    answerability: Answerability,
    warnings: tuple[str, ...],
    tools: tuple[ToolStatus, ...],
    javascript_support: JavaScriptSupport,
    controls: WatchControls,
) -> str:
    lines = [
        "# Watch evidence report",
        "",
        f"- State: `{state}` (terminal)",
        f"- Source kind: `{source.kind}`",
        f"- Source: {_render_untrusted_markdown_code(source.value)}",
        f"- Detail: `{controls.detail}`",
        f"- Metadata coverage: `{coverage.metadata}`",
        f"- Transcript coverage: `{coverage.transcript}`",
        f"- Visual coverage: `{coverage.visual}`",
        f"- Overall coverage: `{coverage.overall}`",
        f"- Answerability: `{answerability}`",
    ]
    if controls.focus_start_seconds is not None or controls.focus_end_seconds is not None:
        lines.append(
            "- Focus seconds: "
            f"`{controls.focus_start_seconds}` to `{controls.focus_end_seconds}`"
        )
    if controls.cues_seconds:
        lines.append(
            "- Cues seconds: "
            + ", ".join(f"`{timestamp}`" for timestamp in controls.cues_seconds)
        )
    if controls.dropped_cues_count:
        lines.append(
            f"- Cues dropped outside focus: `{controls.dropped_cues_count}`"
        )
    if controls.max_frames is not None:
        lines.append(f"- Maximum frames: `{controls.max_frames}`")
    lines.append(f"- Keep duplicates: `{str(controls.keep_duplicates).lower()}`")
    if controls.output_dir is not None:
        lines.append(
            f"- Output directory: {_render_untrusted_markdown_code(controls.output_dir)}"
        )
    for label, value in (
        ("Title", metadata.title),
        ("Uploader", metadata.uploader),
        ("Duration seconds", metadata.duration_seconds),
        ("Container", metadata.container),
        ("Video codec", metadata.video_codec),
        ("Audio codec", metadata.audio_codec),
    ):
        if value is not None:
            lines.append(f"- {label}: {_render_preescaped_markdown_code(value)}")
    lines.extend(["", "## Tool preflight"])
    for tool in tools:
        availability = "available" if tool.available else "unavailable"
        version = (
            f"; version {_render_preescaped_markdown_code(tool.version)}"
            if tool.version
            else ""
        )
        lines.append(f"- `{tool.name}`: {availability}{version}")
    runtime = (
        f"; runtime {_render_preescaped_markdown_code(javascript_support.runtime)}"
        if javascript_support.runtime
        else ""
    )
    lines.append(f"- JavaScript support: `{javascript_support.status}`{runtime}")
    if warnings:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {_render_untrusted_markdown_code(warning)}" for warning in warnings)
    return "\n".join(lines) + "\n"


def _render_failure_report(
    state: OutcomeState,
    source: Source | None,
    failure: Failure,
    warnings: tuple[str, ...],
    javascript_support: JavaScriptSupport,
) -> str:
    lines = [
        "# Watch evidence report",
        "",
        f"- State: `{state}` (terminal)",
        f"- Stage: `{failure.stage}`",
        f"- Category: `{failure.category}`",
        f"- Message: {_render_preescaped_markdown_code(failure.message)}",
        f"- Disposal state: `{failure.disposition.disposal_state}`",
        f"- Reuse state: `{failure.disposition.reuse_state}`",
        f"- JavaScript support: `{javascript_support.status}`",
    ]
    if source is not None:
        lines.append(f"- Source: {_render_untrusted_markdown_code(source.value)}")
    if warnings:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {_render_untrusted_markdown_code(warning)}" for warning in warnings)
    return "\n".join(lines) + "\n"
