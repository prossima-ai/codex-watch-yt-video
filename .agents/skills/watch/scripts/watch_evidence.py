from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import html
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
from typing import Any, Callable, Literal, Mapping, Protocol, Sequence, TypeGuard
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET


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
ChoiceKind = Literal["caption_track", "audio_track", "transcription"]
CaptionType = Literal["manual", "automatic"]
TranscriptProvenance = Literal["manual_captions", "automatic_captions"]
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
FrameSelectionReason = Literal[
    "first", "scene", "uniform", "keyframe", "transcript-cue"
]
FrameInspectionState = Literal[
    "not_applicable",
    "host_inspection_required",
    "complete",
    "partial",
    "unavailable",
]
DeduplicationState = Literal["applied", "disabled", "unavailable", "not_needed"]
VisualFallback = Literal["none", "uniform", "keyframe", "scene"]


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
    caption_track: str | None


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
class VisualFrame:
    timestamp_seconds: float
    chronological_position: int
    selection_reason: FrameSelectionReason
    path: str
    format: Literal["jpeg"]
    width: int
    height: int
    inspected: bool
    resolution_reason: str | None = None


@dataclass(frozen=True)
class VisualEvidence:
    frames: tuple[VisualFrame, ...]
    candidate_count: int
    ordinary_candidate_count: int
    cap: int | None
    ordinary_frame_cap: int | None
    deduplication: DeduplicationState
    fallback: VisualFallback
    cue_requested_count: int
    cue_selected_count: int
    cue_dropped_by_cap_count: int
    cue_dropped_by_rate_count: int
    inspection_state: FrameInspectionState
    inspection_batches: tuple[tuple[VisualFrame, ...], ...]


@dataclass(frozen=True)
class _VideoGeometry:
    codec_name: str
    width: int
    height: int
    sample_aspect_ratio: float | None
    display_aspect_ratio: float | None


@dataclass(frozen=True)
class CaptionChoice:
    id: str
    kind: Literal["caption_track"]
    language: str
    caption_type: CaptionType
    format: str


@dataclass(frozen=True)
class CaptionInventoryItem:
    id: str
    kind: Literal["caption_track"]
    language: str
    caption_type: CaptionType
    format: str
    usable: bool


@dataclass(frozen=True)
class TranscriptSegment:
    text: str
    start_seconds: float
    end_seconds: float


@dataclass(frozen=True)
class TimeRange:
    start_seconds: float
    end_seconds: float


@dataclass(frozen=True)
class TranscriptEvidence:
    provenance: TranscriptProvenance
    language: str
    selected_track: CaptionChoice
    segments: tuple[TranscriptSegment, ...]
    available_ranges: tuple[TimeRange, ...]
    unavailable_ranges: tuple[TimeRange, ...]
    source_count: int


@dataclass(frozen=True)
class EvidenceBundle:
    metadata: MetadataEvidence
    transcript: TranscriptEvidence | None = None
    visual: VisualEvidence | None = None


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
    choice_kind: ChoiceKind | None = None
    choices: tuple[CaptionChoice, ...] = ()
    caption_inventory: tuple[CaptionInventoryItem, ...] = ()
    decision_handle: str | None = None

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
MAX_CAPTION_BYTES = 4 * 1024 * 1024
SUPPORTED_CAPTION_FORMATS = frozenset({"ttml", "vtt"})
CAPTION_FORMAT_PREFERENCE = ("vtt", "ttml")


@dataclass(frozen=True)
class _CaptionCandidate:
    language: str
    caption_type: CaptionType
    format: str
    usable: bool


@dataclass(frozen=True)
class _SourceProbe:
    metadata: MetadataEvidence
    caption_candidates: tuple[_CaptionCandidate, ...]


@dataclass(frozen=True)
class _CaptionSelection:
    source_value: str
    decision_handle: str
    choice: CaptionChoice
    metadata_probe: _SourceProbe


@dataclass(frozen=True)
class _TranscriptScope:
    start_seconds: float
    end_seconds: float | None


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(self, executable: str, arguments: Sequence[str]) -> CommandResult: ...


@dataclass(frozen=True)
class FrameEscalation:
    frame_path: str
    reason: str


@dataclass(frozen=True)
class FrameInspection:
    state: Literal["complete", "partial", "unavailable"]
    inspected_paths: tuple[str, ...]
    message: str | None = None
    escalations: tuple[FrameEscalation, ...] = ()


class FrameInspector(Protocol):
    def inspect(
        self, batches: tuple[tuple[VisualFrame, ...], ...]
    ) -> FrameInspection: ...


@dataclass(frozen=True)
class _FrameCandidate:
    timestamp_seconds: float
    selection_reason: FrameSelectionReason


@dataclass(frozen=True)
class _VisualPlan:
    candidates: tuple[_FrameCandidate, ...]
    ordinary_candidate_count: int
    cap: int | None
    ordinary_frame_cap: int | None
    deduplication: DeduplicationState
    fallback: VisualFallback
    cue_requested_count: int
    cue_selected_count: int
    cue_dropped_by_cap_count: int
    cue_dropped_by_rate_count: int


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
        frame_inspector: FrameInspector | None = None,
        artifact_root: Path | None = None,
        visual_enabled: bool = True,
    ) -> None:
        self._command_runner = command_runner or SubprocessCommandRunner()
        self._find_executable = find_executable
        self._frame_inspector = frame_inspector
        self._artifact_root = artifact_root
        self._visual_enabled = visual_enabled
        self._caption_selections: dict[str, _CaptionSelection] = {}

    def prepare(
        self,
        watch_request: object,
        prior_evidence: object | None = None,
    ) -> EvidenceOutcome:
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

        caption_selection, selection_failure = self._selected_caption(
            source, controls, prior_evidence
        )
        if selection_failure is not None:
            return self._failure_outcome(
                state="stopped",
                source=source,
                controls=controls,
                failure=selection_failure,
            )
        selected_caption = (
            caption_selection.choice if caption_selection is not None else None
        )

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
        assert required_path is not None

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
            if caption_selection is not None:
                metadata_result = caption_selection.metadata_probe
            elif source.kind == "local":
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
            controls, metadata_result.metadata.duration_seconds
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

        if source.kind == "url":
            caption_outcome = self._url_caption_outcome(
                source=source,
                controls=controls,
                metadata_probe=metadata_result,
                selected_caption=selected_caption,
                yt_dlp=required_path,
                warnings=warnings,
                tools=tools,
                javascript_support=javascript_support,
            )
            return self._with_visual_evidence(
                caption_outcome,
                source=source,
                metadata=metadata_result.metadata,
                controls=controls,
                executable_paths=executable_paths,
                question=watch_request.get("question"),
            )

        if self._visual_enabled:
            visual, visual_warnings = self._prepare_visual_evidence(
                source=source,
                metadata=metadata_result.metadata,
                controls=controls,
                executable_paths=executable_paths,
                question=watch_request.get("question"),
            )
        else:
            visual, visual_warnings = None, ()
        if self._visual_enabled and controls.output_dir is not None:
            visual_warnings += (
                "The supplied output_dir was not used for visual artifacts in this "
                "preparation; it did not grant filesystem write authority.",
            )
        all_warnings = warnings + visual_warnings
        visual_coverage: EvidenceCoverageValue = (
            "partial"
            if visual is not None
            and visual.inspection_state in {"complete", "partial"}
            and any(frame.inspected for frame in visual.frames)
            else "none"
        )
        evidence = EvidenceBundle(metadata=metadata_result.metadata, visual=visual)
        coverage = EvidenceCoverage("complete", "none", visual_coverage, "partial")
        report = _render_report(
            state="partial",
            source=source,
            metadata=metadata_result.metadata,
            coverage=coverage,
            answerability="uncertain",
            warnings=all_warnings,
            tools=tools,
            javascript_support=javascript_support,
            controls=controls,
            visual=visual,
        )
        return EvidenceOutcome(
            state="partial",
            terminal=True,
            source=source,
            coverage=coverage,
            answerability="uncertain",
            warnings=all_warnings,
            failure=None,
            evidence=evidence,
            tools=tools,
            javascript_support=javascript_support,
            controls=controls,
            report_markdown=report,
        )

    def _selected_caption(
        self,
        source: Source,
        controls: WatchControls,
        prior_evidence: object | None,
    ) -> tuple[_CaptionSelection | None, Failure | None]:
        selection_id = controls.caption_track
        if selection_id is None:
            return None, None
        selection = self._caption_selections.get(selection_id)
        if (
            selection is None
            or selection.source_value != source.value
            or (
                prior_evidence is not None
                and not _prior_evidence_matches_selection(
                    prior_evidence, source, selection
                )
            )
        ):
            return None, _validation_failure(
                "invalid_selection",
                "caption_track is unknown, stale, wrong-kind, or does not match the "
                "same-task selection outcome.",
            )
        return selection, None

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

        caption_track = watch_request.get("caption_track")
        if caption_track is not None and (
            not isinstance(caption_track, str) or not caption_track.strip()
        ):
            return None, _validation_failure(
                "invalid_selection",
                "caption_track must be one non-empty run-scoped choice ID.",
            )
        audio_track = watch_request.get("audio_track")
        if audio_track is not None:
            return None, _validation_failure(
                "invalid_selection",
                "audio_track has no matching run-scoped choice in this caption stage.",
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
                caption_track=caption_track,
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

    def _local_metadata(self, ffprobe: str, source: str) -> _SourceProbe | Failure:
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
        return _SourceProbe(_metadata_from_ffprobe(payload), ())

    def _url_metadata(self, yt_dlp: str, source: str) -> _SourceProbe | Failure:
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
        return _SourceProbe(
            metadata=_metadata_from_ytdlp(payload),
            caption_candidates=_caption_candidates_from_ytdlp(payload),
        )

    def _url_caption_outcome(
        self,
        *,
        source: Source,
        controls: WatchControls,
        metadata_probe: _SourceProbe,
        selected_caption: CaptionChoice | None,
        yt_dlp: str,
        warnings: tuple[str, ...],
        tools: tuple[ToolStatus, ...],
        javascript_support: JavaScriptSupport,
    ) -> EvidenceOutcome:
        caption_inventory = self._caption_inventory(
            source, metadata_probe.caption_candidates, selected_caption
        )
        caption_choices = tuple(
            _caption_choice_from_inventory(item)
            for item in caption_inventory
            if item.usable
        )
        if not caption_choices:
            missing_caption_warnings = warnings + (
                "No usable native caption tracks are available; transcript evidence is unavailable.",
            )
            if controls.detail == "transcript" and not controls.cues_seconds:
                missing_caption_warnings += (
                    "No visual fallback exists for transcript detail without usable captions or cues.",
                )
            return self._completed_outcome(
                state="partial",
                source=source,
                controls=controls,
                metadata=metadata_probe.metadata,
                coverage=EvidenceCoverage("complete", "none", "none", "partial"),
                warnings=missing_caption_warnings,
                tools=tools,
                javascript_support=javascript_support,
                caption_inventory=caption_inventory,
            )

        if selected_caption is None:
            if len(caption_choices) > 1:
                if self._visual_only_route(controls):
                    return self._completed_outcome(
                        state="partial",
                        source=source,
                        controls=controls,
                        metadata=metadata_probe.metadata,
                        coverage=EvidenceCoverage("complete", "none", "none", "partial"),
                        warnings=warnings
                        + (
                            "Multiple native caption tracks are available; visual evidence "
                            "will proceed without selecting transcript evidence.",
                        ),
                        tools=tools,
                        javascript_support=javascript_support,
                        caption_inventory=caption_inventory,
                    )
                decision_handle = _new_decision_handle()
                self._register_caption_selections(
                    source, decision_handle, caption_choices, metadata_probe
                )
                coverage = EvidenceCoverage("complete", "none", "none", "partial")
                report = _render_report(
                    state="decision_required",
                    source=source,
                    metadata=metadata_probe.metadata,
                    coverage=coverage,
                    answerability="uncertain",
                    warnings=warnings,
                    tools=tools,
                    javascript_support=javascript_support,
                    controls=controls,
                    choice_kind="caption_track",
                    choices=caption_choices,
                    decision_handle=decision_handle,
                )
                return EvidenceOutcome(
                    state="decision_required",
                    terminal=False,
                    source=source,
                    coverage=coverage,
                    answerability="uncertain",
                    warnings=warnings,
                    failure=None,
                    evidence=EvidenceBundle(metadata=metadata_probe.metadata),
                    tools=tools,
                    javascript_support=javascript_support,
                    controls=controls,
                    report_markdown=report,
                    choice_kind="caption_track",
                    choices=caption_choices,
                    caption_inventory=caption_inventory,
                    decision_handle=decision_handle,
                )
            selected_caption = caption_choices[0]
        else:
            selected_caption = next(
                (
                    choice
                    for choice in caption_choices
                    if choice.id == selected_caption.id
                ),
                None,
            )
            if selected_caption is None:
                return self._completed_outcome(
                    state="partial",
                    source=source,
                    controls=controls,
                    metadata=metadata_probe.metadata,
                    coverage=EvidenceCoverage("complete", "none", "none", "partial"),
                    warnings=warnings
                    + (
                        "The selected native caption track is no longer available; no caption was downloaded.",
                    ),
                    tools=tools,
                    javascript_support=javascript_support,
                    caption_inventory=caption_inventory,
                )

        raw_segments, caption_warnings = self._download_caption(
            yt_dlp, source.value, selected_caption
        )
        if raw_segments is None:
            return self._completed_outcome(
                state="partial",
                source=source,
                controls=controls,
                metadata=metadata_probe.metadata,
                coverage=EvidenceCoverage("complete", "none", "none", "partial"),
                warnings=warnings + caption_warnings,
                tools=tools,
                javascript_support=javascript_support,
                caption_inventory=caption_inventory,
            )

        scope = _transcript_scope(controls, metadata_probe.metadata.duration_seconds)
        scoped_segments = _segments_overlapping_scope(raw_segments, scope)
        available_ranges = _merge_ranges(
            _ranges_for_segments(scoped_segments, scope)
        )
        unavailable_ranges = _unavailable_ranges(available_ranges, scope)
        if not scoped_segments:
            transcript_coverage: EvidenceCoverageValue = "none"
            caption_warnings += (
                "Native captions are available, but no caption lines overlap the requested focus.",
            )
        elif scope is None or scope.end_seconds is None or unavailable_ranges:
            transcript_coverage = "partial"
        else:
            transcript_coverage = "complete"

        transcript = TranscriptEvidence(
            provenance=(
                "manual_captions"
                if selected_caption.caption_type == "manual"
                else "automatic_captions"
            ),
            language=selected_caption.language,
            selected_track=selected_caption,
            segments=_collapse_rolling_segments(scoped_segments),
            available_ranges=available_ranges,
            unavailable_ranges=unavailable_ranges,
            source_count=1,
        )
        can_finish_transcript = (
            controls.detail == "transcript"
            and not controls.cues_seconds
            and transcript_coverage == "complete"
        )
        return self._completed_outcome(
            state="ready" if can_finish_transcript else "partial",
            source=source,
            controls=controls,
            metadata=metadata_probe.metadata,
            transcript=transcript,
            coverage=EvidenceCoverage(
                "complete",
                transcript_coverage,
                "none",
                "complete" if can_finish_transcript else "partial",
            ),
            warnings=warnings + caption_warnings,
            tools=tools,
            javascript_support=javascript_support,
            caption_inventory=caption_inventory,
        )

    def _caption_inventory(
        self,
        source: Source,
        candidates: tuple[_CaptionCandidate, ...],
        selected_caption: CaptionChoice | None,
    ) -> tuple[CaptionInventoryItem, ...]:
        inventory: list[CaptionInventoryItem] = []
        for candidate in candidates:
            if (
                candidate.usable
                and selected_caption is not None
                and _choice_matches_candidate(
                    selected_caption, candidate
                )
            ):
                track_id = selected_caption.id
            else:
                track_id = f"caption_{secrets.token_urlsafe(18)}"
            inventory.append(
                CaptionInventoryItem(
                    id=track_id,
                    kind="caption_track",
                    language=candidate.language,
                    caption_type=candidate.caption_type,
                    format=candidate.format,
                    usable=candidate.usable,
                )
            )
        return tuple(inventory)

    def _register_caption_selections(
        self,
        source: Source,
        decision_handle: str,
        choices: Sequence[CaptionChoice],
        metadata_probe: _SourceProbe,
    ) -> None:
        stale_ids = [
            choice_id
            for choice_id, selection in self._caption_selections.items()
            if selection.source_value == source.value
        ]
        for choice_id in stale_ids:
            del self._caption_selections[choice_id]
        for choice in choices:
            self._caption_selections[choice.id] = _CaptionSelection(
                source_value=source.value,
                decision_handle=decision_handle,
                choice=choice,
                metadata_probe=metadata_probe,
            )

    def _download_caption(
        self, yt_dlp: str, source: str, selected_caption: CaptionChoice
    ) -> tuple[tuple[TranscriptSegment, ...] | None, tuple[str, ...]]:
        write_flag = (
            "--write-subs"
            if selected_caption.caption_type == "manual"
            else "--write-auto-subs"
        )
        try:
            with tempfile.TemporaryDirectory(prefix="watch-caption-") as directory:
                output_template = str(Path(directory) / "caption.%(ext)s")
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
                        write_flag,
                        "--sub-langs",
                        selected_caption.language,
                        "--sub-format",
                        selected_caption.format,
                        "--output",
                        output_template,
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
                caption_files = sorted(
                    path
                    for path in Path(directory).iterdir()
                    if (
                        path.is_file()
                        and path.suffix.casefold()
                        == f".{selected_caption.format}"
                    )
                )
                if len(caption_files) != 1:
                    return None, (
                        "Native caption retrieval did not produce one usable caption file; transcript evidence is unavailable.",
                    )
                caption_path = caption_files[0]
                if caption_path.stat().st_size > MAX_CAPTION_BYTES:
                    return None, (
                        "The selected native caption exceeds the safe parsing limit; transcript evidence is unavailable.",
                    )
                try:
                    caption_bytes = caption_path.read_bytes()
                except OSError:
                    return None, (
                        "The selected native caption could not be read safely; transcript evidence is unavailable.",
                    )
        except (OSError, subprocess.SubprocessError):
            return None, (
                "Native caption retrieval could not run; transcript evidence is unavailable.",
            )

        segments = _parse_caption(selected_caption.format, caption_bytes)
        if segments is None:
            return None, (
                "The selected native caption could not be parsed; transcript evidence is unavailable.",
            )
        if result.returncode != 0:
            return segments, (
                "yt-dlp reported an error after writing the selected caption; parsed the available caption artifact.",
            )
        return segments, ()

    def _completed_outcome(
        self,
        *,
        state: Literal["ready", "partial"],
        source: Source,
        controls: WatchControls,
        metadata: MetadataEvidence,
        coverage: EvidenceCoverage,
        warnings: tuple[str, ...],
        tools: tuple[ToolStatus, ...],
        javascript_support: JavaScriptSupport,
        transcript: TranscriptEvidence | None = None,
        visual: VisualEvidence | None = None,
        caption_inventory: tuple[CaptionInventoryItem, ...] = (),
    ) -> EvidenceOutcome:
        report = _render_report(
            state=state,
            source=source,
            metadata=metadata,
            transcript=transcript,
            coverage=coverage,
            answerability="uncertain",
            warnings=warnings,
            tools=tools,
            javascript_support=javascript_support,
            controls=controls,
            visual=visual,
        )
        return EvidenceOutcome(
            state=state,
            terminal=True,
            source=source,
            coverage=coverage,
            answerability="uncertain",
            warnings=warnings,
            failure=None,
            evidence=EvidenceBundle(
                metadata=metadata, transcript=transcript, visual=visual
            ),
            tools=tools,
            javascript_support=javascript_support,
            controls=controls,
            report_markdown=report,
            caption_inventory=caption_inventory,
        )

    def _visual_route_requested(self, controls: WatchControls) -> bool:
        return self._visual_enabled and (
            controls.detail != "transcript" or bool(controls.cues_seconds)
        )

    def _visual_only_route(self, controls: WatchControls) -> bool:
        return self._visual_route_requested(controls) and controls.detail != "transcript"

    def _with_visual_evidence(
        self,
        outcome: EvidenceOutcome,
        *,
        source: Source,
        metadata: MetadataEvidence,
        controls: WatchControls,
        executable_paths: Mapping[str, str | None],
        question: object,
    ) -> EvidenceOutcome:
        if (
            not outcome.terminal
            or outcome.evidence is None
            or not self._visual_route_requested(controls)
        ):
            return outcome
        visual, visual_warnings = self._prepare_visual_evidence(
            source=source,
            metadata=metadata,
            controls=controls,
            executable_paths=executable_paths,
            question=question,
        )
        if controls.output_dir is not None:
            visual_warnings += (
                "The supplied output_dir was not used for visual artifacts in this "
                "preparation; it did not grant filesystem write authority.",
            )
        visual_coverage: EvidenceCoverageValue = (
            "partial"
            if visual is not None
            and visual.inspection_state in {"complete", "partial"}
            and any(frame.inspected for frame in visual.frames)
            else "none"
        )
        coverage = EvidenceCoverage(
            outcome.coverage.metadata,
            outcome.coverage.transcript,
            visual_coverage,
            "partial",
        )
        warnings = outcome.warnings + visual_warnings
        evidence = EvidenceBundle(
            metadata=metadata,
            transcript=outcome.evidence.transcript,
            visual=visual,
        )
        report = _render_report(
            state="partial",
            source=source,
            metadata=metadata,
            transcript=outcome.evidence.transcript,
            coverage=coverage,
            answerability=outcome.answerability,
            warnings=warnings,
            tools=outcome.tools,
            javascript_support=outcome.javascript_support,
            controls=controls,
            visual=visual,
        )
        return replace(
            outcome,
            state="partial",
            coverage=coverage,
            warnings=warnings,
            evidence=evidence,
            report_markdown=report,
        )

    def _prepare_visual_evidence(
        self,
        *,
        source: Source,
        metadata: MetadataEvidence,
        controls: WatchControls,
        executable_paths: Mapping[str, str | None],
        question: object,
    ) -> tuple[VisualEvidence | None, tuple[str, ...]]:
        if controls.detail == "transcript" and not controls.cues_seconds:
            return (
                _empty_visual_evidence(controls),
                (
                    "Transcript detail selected no cue frames, so no visual fallback "
                    "was prepared.",
                ),
            )
        if metadata.duration_seconds is None:
            return None, (
                "Visual evidence was not prepared because the source duration is unavailable.",
            )
        if metadata.video_codec is None:
            return None, (
                "Visual evidence was not prepared because the source has no usable video stream.",
            )
        ffmpeg = executable_paths.get("ffmpeg")
        ffprobe = executable_paths.get("ffprobe")
        if ffmpeg is None or ffprobe is None:
            missing = ", ".join(
                name
                for name, executable in (("ffmpeg", ffmpeg), ("ffprobe", ffprobe))
                if executable is None
            )
            return None, (
                f"Visual evidence was not prepared because required tool(s) are unavailable: {missing}.",
            )

        try:
            artifact_root = self._create_visual_artifact_root()
        except OSError as error:
            return None, (
                "Visual evidence was not prepared because a current-run artifact location "
                f"could not be created: {_escape_control_sequences(str(error))}",
            )

        try:
            media_path, acquisition_warning = self._visual_media_path(
                source=source,
                yt_dlp=executable_paths.get("yt-dlp"),
                artifact_root=artifact_root,
            )
            if media_path is None:
                return None, (acquisition_warning,)

            source_geometry = self._source_video_geometry(ffprobe, media_path)
            if source_geometry is None:
                return None, (
                    "Visual evidence was not prepared because source display geometry is "
                    "unavailable; aspect-correct JPEG frames cannot be verified.",
                )

            plan, planning_warnings = self._plan_visual_frames(
                media_path=media_path,
                metadata=metadata,
                controls=controls,
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
            )
            extracted_frames, extraction_warnings = self._extract_visual_frames(
                candidates=plan.candidates,
                media_path=media_path,
                artifact_root=artifact_root,
                source_geometry=source_geometry,
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
            )
            batches = _chronological_batches(extracted_frames)
            frames, inspection_state, inspection_warnings = self._inspect_visual_frames(
                frames=extracted_frames,
                batches=batches,
                media_path=media_path,
                artifact_root=artifact_root,
                source_geometry=source_geometry,
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                has_question=isinstance(question, str) and bool(question.strip()),
            )
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            return None, (
                "Visual preparation failed before a trustworthy frame was available. "
                f"Diagnostic: {_escape_control_sequences(str(error))}",
            )
        inspected_batches = _chronological_batches(frames)
        scale_warnings: tuple[str, ...] = ()
        if controls.detail == "token-burner" and len(frames) > 250:
            scale_warnings = (
                "More than 250 selected frames create high visual-context cost; narrow "
                "the focus interval or set max_frames for a smaller inspected set.",
            )
        visual = VisualEvidence(
            frames=frames,
            candidate_count=len(plan.candidates),
            ordinary_candidate_count=plan.ordinary_candidate_count,
            cap=plan.cap,
            ordinary_frame_cap=plan.ordinary_frame_cap,
            deduplication=plan.deduplication,
            fallback=plan.fallback,
            cue_requested_count=plan.cue_requested_count,
            cue_selected_count=plan.cue_selected_count,
            cue_dropped_by_cap_count=plan.cue_dropped_by_cap_count,
            cue_dropped_by_rate_count=plan.cue_dropped_by_rate_count,
            inspection_state=inspection_state,
            inspection_batches=inspected_batches,
        )
        return (
            visual,
            planning_warnings
            + extraction_warnings
            + inspection_warnings
            + scale_warnings,
        )

    def _create_visual_artifact_root(self) -> Path:
        base = self._artifact_root
        if base is None:
            return Path(tempfile.mkdtemp(prefix="codex-watch-visual-"))
        resolved_base = base.expanduser().resolve(strict=False)
        resolved_base.mkdir(parents=True, exist_ok=True)
        return Path(
            tempfile.mkdtemp(prefix="codex-watch-visual-", dir=str(resolved_base))
        )

    def _visual_media_path(
        self,
        *,
        source: Source,
        yt_dlp: str | None,
        artifact_root: Path,
    ) -> tuple[Path | None, str]:
        if source.kind == "local":
            return Path(source.value), ""
        if yt_dlp is None:
            return (
                None,
                "Visual evidence was not prepared because yt-dlp is unavailable for "
                "the approved public source.",
            )
        result = self._command_runner.run(
            yt_dlp,
            [
                "--ignore-config",
                "--no-plugin-dirs",
                "--no-playlist",
                "--no-cache-dir",
                "--no-update",
                "--no-remote-components",
                "--no-warnings",
                "--socket-timeout",
                "15",
                "--retries",
                "0",
                "--extractor-retries",
                "0",
                "--format",
                "bestvideo[height<=1080]/bestvideo/best",
                "--output",
                str(artifact_root / "source.%(ext)s"),
                "--print",
                "after_move:filepath",
                "--",
                source.value,
            ],
        )
        if result.returncode != 0:
            return (
                None,
                "Visual media acquisition failed after the approved source-host request. "
                f"Diagnostic: {_escape_control_sequences((result.stderr or result.stdout).strip())}",
            )
        output_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not output_lines:
            return None, "Visual media acquisition did not report a controlled output path."
        try:
            media_path = Path(output_lines[-1]).resolve(strict=True)
            media_path.relative_to(artifact_root.resolve())
        except (OSError, RuntimeError, ValueError):
            return None, "Visual media acquisition reported an unsafe or missing output path."
        if not media_path.is_file():
            return None, "Visual media acquisition did not produce a regular media file."
        return media_path, ""

    def _plan_visual_frames(
        self,
        *,
        media_path: Path,
        metadata: MetadataEvidence,
        controls: WatchControls,
        ffmpeg: str,
        ffprobe: str,
    ) -> tuple[_VisualPlan, tuple[str, ...]]:
        assert metadata.duration_seconds is not None
        scope_start, scope_end = _visual_scope(controls, metadata.duration_seconds)
        cap = _visual_cap(controls)
        requested_cues = tuple(
            _FrameCandidate(timestamp, "transcript-cue")
            for timestamp in controls.cues_seconds
        )
        capped_cues, cue_dropped_by_cap = _thin_candidates(requested_cues, cap)
        rate_limited_cues, cue_dropped_by_rate = _limit_sampling_rate(capped_cues)
        ordinary_capacity = None if cap is None else max(0, cap - len(rate_limited_cues))
        warnings: list[str] = []
        if (
            controls.detail in {"efficient", "balanced"}
            and controls.focus_start_seconds is None
            and controls.focus_end_seconds is None
            and metadata.duration_seconds > 600
        ):
            warnings.append(
                "Visual coverage is sparse for an unfocused source over 600 seconds; "
                "narrow the focus interval or use token-burner."
            )
        if cue_dropped_by_cap:
            warnings.append(
                f"{cue_dropped_by_cap} cue frame request(s) were dropped by the frame cap; "
                "the first and last requested cues were retained where possible."
            )
        if cue_dropped_by_rate:
            warnings.append(
                f"{cue_dropped_by_rate} cue frame request(s) were dropped to preserve the "
                "two-frames-per-second ceiling."
            )

        ordinary_candidates: tuple[_FrameCandidate, ...] = ()
        fallback: VisualFallback = "none"
        deduplication: DeduplicationState = "not_needed"
        if controls.detail != "transcript" and ordinary_capacity != 0:
            target = _ordinary_target(
                scope_start=scope_start,
                scope_end=scope_end,
                focused=controls.focus_start_seconds is not None
                or controls.focus_end_seconds is not None,
                cap=ordinary_capacity,
            )
            if controls.detail == "efficient":
                keyframes = self._keyframe_candidates(
                    ffprobe=ffprobe,
                    media_path=media_path,
                    scope_start=scope_start,
                    scope_end=scope_end,
                )
                (
                    useful_keyframes,
                    keyframe_deduplication,
                    keyframe_warnings,
                ) = self._prepare_ordinary_candidates(
                    candidates=keyframes,
                    media_path=media_path,
                    ffmpeg=ffmpeg,
                    keep_duplicates=controls.keep_duplicates,
                )
                if len(useful_keyframes) >= 4:
                    ordinary_candidates = useful_keyframes
                    deduplication = keyframe_deduplication
                    warnings.extend(keyframe_warnings)
                    fallback = "keyframe"
                else:
                    ordinary_candidates, deduplication, ordinary_warnings = (
                        self._prepare_ordinary_candidates(
                            candidates=_uniform_candidates(
                                scope_start, scope_end, target
                            ),
                            media_path=media_path,
                            ffmpeg=ffmpeg,
                            keep_duplicates=controls.keep_duplicates,
                        )
                    )
                    warnings.extend(ordinary_warnings)
                    fallback = "uniform"
            elif controls.detail == "balanced":
                scenes = self._scene_candidates(
                    ffmpeg=ffmpeg,
                    media_path=media_path,
                    scope_start=scope_start,
                    scope_end=scope_end,
                )
                (
                    useful_scenes,
                    scene_deduplication,
                    scene_warnings,
                ) = self._prepare_ordinary_candidates(
                    candidates=scenes,
                    media_path=media_path,
                    ffmpeg=ffmpeg,
                    keep_duplicates=controls.keep_duplicates,
                )
                if len(useful_scenes) >= 2:
                    ordinary_candidates = useful_scenes
                    deduplication = scene_deduplication
                    warnings.extend(scene_warnings)
                    fallback = "scene"
                else:
                    ordinary_candidates, deduplication, ordinary_warnings = (
                        self._prepare_ordinary_candidates(
                            candidates=_uniform_candidates(
                                scope_start, scope_end, target
                            ),
                            media_path=media_path,
                            ffmpeg=ffmpeg,
                            keep_duplicates=controls.keep_duplicates,
                        )
                    )
                    warnings.extend(ordinary_warnings)
                    fallback = "uniform"
            else:
                scenes = self._scene_candidates(
                    ffmpeg=ffmpeg,
                    media_path=media_path,
                    scope_start=scope_start,
                    scope_end=scope_end,
                )
                if scenes:
                    ordinary_candidates, deduplication, ordinary_warnings = (
                        self._prepare_ordinary_candidates(
                            candidates=scenes,
                            media_path=media_path,
                            ffmpeg=ffmpeg,
                            keep_duplicates=controls.keep_duplicates,
                        )
                    )
                    warnings.extend(ordinary_warnings)
                    fallback = "scene"
                else:
                    ordinary_candidates, deduplication, ordinary_warnings = (
                        self._prepare_ordinary_candidates(
                            candidates=_uniform_candidates(
                                scope_start, scope_end, target
                            ),
                            media_path=media_path,
                            ffmpeg=ffmpeg,
                            keep_duplicates=controls.keep_duplicates,
                        )
                    )
                    warnings.extend(ordinary_warnings)
                    fallback = "uniform"

            ordinary_candidates, cue_rate_dropped = _exclude_candidates_near_pins(
                ordinary_candidates, rate_limited_cues
            )
            if cue_rate_dropped:
                warnings.append(
                    f"{cue_rate_dropped} ordinary frame candidate(s) were dropped to "
                    "preserve the two-frames-per-second ceiling around pinned cues."
                )
            ordinary_candidates, ordinary_dropped_by_cap = _thin_candidates(
                ordinary_candidates, ordinary_capacity
            )
            if ordinary_dropped_by_cap:
                warnings.append(
                    f"{ordinary_dropped_by_cap} ordinary frame candidate(s) were thinned "
                    "across the requested interval by the frame cap."
                )

        merged_candidates = _merge_visual_candidates(
            rate_limited_cues, ordinary_candidates
        )
        return (
            _VisualPlan(
                candidates=merged_candidates,
                ordinary_candidate_count=len(ordinary_candidates),
                cap=cap,
                ordinary_frame_cap=_ordinary_frame_cap(controls),
                deduplication=deduplication,
                fallback=fallback,
                cue_requested_count=len(requested_cues),
                cue_selected_count=len(rate_limited_cues),
                cue_dropped_by_cap_count=cue_dropped_by_cap,
                cue_dropped_by_rate_count=cue_dropped_by_rate,
            ),
            tuple(warnings),
        )

    def _prepare_ordinary_candidates(
        self,
        *,
        candidates: tuple[_FrameCandidate, ...],
        media_path: Path,
        ffmpeg: str,
        keep_duplicates: bool,
    ) -> tuple[
        tuple[_FrameCandidate, ...], DeduplicationState, tuple[str, ...]
    ]:
        rate_limited, rate_dropped = _limit_sampling_rate(candidates)
        warnings: list[str] = []
        if rate_dropped:
            warnings.append(
                f"{rate_dropped} ordinary frame candidate(s) were dropped to preserve "
                "the two-frames-per-second ceiling."
            )
        if not rate_limited:
            return (), "not_needed", tuple(warnings)
        if keep_duplicates:
            return rate_limited, "disabled", tuple(warnings)
        deduplicated, state, dedupe_warning = self._deduplicate_ordinary_candidates(
            candidates=rate_limited,
            media_path=media_path,
            ffmpeg=ffmpeg,
        )
        if dedupe_warning is not None:
            warnings.append(dedupe_warning)
        return deduplicated, state, tuple(warnings)

    def _keyframe_candidates(
        self,
        *,
        ffprobe: str,
        media_path: Path,
        scope_start: float,
        scope_end: float,
    ) -> tuple[_FrameCandidate, ...]:
        result = self._command_runner.run(
            ffprobe,
            [
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-skip_frame",
                "nokey",
                "-read_intervals",
                f"{_format_seconds(scope_start)}%+{_format_seconds(scope_end - scope_start)}",
                "-show_entries",
                "frame=best_effort_timestamp_time",
                "-of",
                "json",
                str(media_path),
            ],
        )
        if result.returncode != 0:
            return ()
        try:
            payload = json.loads(result.stdout)
        except (json.JSONDecodeError, TypeError):
            return ()
        frames = payload.get("frames") if isinstance(payload, Mapping) else None
        if not isinstance(frames, list):
            return ()
        timestamps = [
            timestamp
            for frame in frames
            if isinstance(frame, Mapping)
            for timestamp in [_nonnegative_float(frame.get("best_effort_timestamp_time"))]
            if timestamp is not None and scope_start <= timestamp <= scope_end
        ]
        return _unique_candidates(timestamps, "keyframe")

    def _scene_candidates(
        self,
        *,
        ffmpeg: str,
        media_path: Path,
        scope_start: float,
        scope_end: float,
    ) -> tuple[_FrameCandidate, ...]:
        result = self._command_runner.run(
            ffmpeg,
            [
                "-nostdin",
                "-v",
                "info",
                "-ss",
                _format_seconds(scope_start),
                "-t",
                _format_seconds(scope_end - scope_start),
                "-copyts",
                "-i",
                str(media_path),
                "-map",
                "0:v:0",
                "-vf",
                "select='gt(scene,0.15)',showinfo",
                "-an",
                "-sn",
                "-dn",
                "-f",
                "null",
                "-",
            ],
        )
        if result.returncode != 0:
            return ()
        timestamps = [
            float(match.group(1))
            for match in re.finditer(
                r"pts_time:([0-9]+(?:\.[0-9]+)?)", f"{result.stdout}\n{result.stderr}"
            )
            if scope_start <= float(match.group(1)) <= scope_end
        ]
        return _unique_candidates(timestamps, "scene")

    def _deduplicate_ordinary_candidates(
        self,
        *,
        candidates: tuple[_FrameCandidate, ...],
        media_path: Path,
        ffmpeg: str,
    ) -> tuple[tuple[_FrameCandidate, ...], DeduplicationState, str | None]:
        fingerprints: set[str] = set()
        retained: list[_FrameCandidate] = []
        for candidate in candidates:
            fingerprint = self._frame_fingerprint(ffmpeg, media_path, candidate.timestamp_seconds)
            if fingerprint is None:
                return (
                    candidates,
                    "unavailable",
                    "Ordinary-frame deduplication was unavailable, so visually similar "
                    "samples were retained.",
                )
            if fingerprint not in fingerprints:
                fingerprints.add(fingerprint)
                retained.append(candidate)
        return tuple(retained), "applied", None

    def _frame_fingerprint(
        self, ffmpeg: str, media_path: Path, timestamp_seconds: float
    ) -> str | None:
        result = self._command_runner.run(
            ffmpeg,
            [
                "-nostdin",
                "-v",
                "error",
                "-ss",
                _format_seconds(timestamp_seconds),
                "-i",
                str(media_path),
                "-map",
                "0:v:0",
                "-frames:v",
                "1",
                "-an",
                "-sn",
                "-dn",
                "-vf",
                "scale=w=32:h=18:flags=area,format=gray",
                "-f",
                "framemd5",
                "-",
            ],
        )
        if result.returncode != 0:
            return None
        match = re.search(r"\b([0-9a-f]{32})\s*$", result.stdout, re.IGNORECASE | re.MULTILINE)
        return match.group(1).casefold() if match is not None else None

    def _extract_visual_frames(
        self,
        *,
        candidates: tuple[_FrameCandidate, ...],
        media_path: Path,
        artifact_root: Path,
        source_geometry: _VideoGeometry,
        ffmpeg: str,
        ffprobe: str,
    ) -> tuple[tuple[VisualFrame, ...], tuple[str, ...]]:
        frames: list[VisualFrame] = []
        warnings: list[str] = []
        for candidate in candidates:
            position = len(frames) + 1
            filename = (
                f"frame-{position:04d}-{int(round(candidate.timestamp_seconds * 1000)):012d}.jpg"
            )
            frame_path = artifact_root / filename
            result = self._command_runner.run(
                ffmpeg,
                [
                    "-nostdin",
                    "-v",
                    "error",
                    "-ss",
                    _format_seconds(candidate.timestamp_seconds),
                    "-i",
                    str(media_path),
                    "-map",
                    "0:v:0",
                    "-frames:v",
                    "1",
                    "-an",
                    "-sn",
                    "-dn",
                    "-vf",
                    _square_pixel_scale_filter(768),
                    "-q:v",
                    "2",
                    "-n",
                    str(frame_path),
                ],
            )
            if result.returncode != 0 or not frame_path.is_file():
                warnings.append(
                    "No visual frame was recorded for source time "
                    f"{_format_seconds(candidate.timestamp_seconds)} because frame extraction failed."
                )
                continue
            geometry = self._jpeg_geometry(ffprobe, frame_path)
            if geometry is None or not _valid_frame_geometry(
                geometry, source_geometry
            ):
                warnings.append(
                    "No visual frame was recorded for source time "
                    f"{_format_seconds(candidate.timestamp_seconds)} because the extracted "
                    "file was not an aspect-correct JPEG within the 768 px ordinary limit."
                )
                continue
            width, height = geometry.width, geometry.height
            frames.append(
                VisualFrame(
                    timestamp_seconds=candidate.timestamp_seconds,
                    chronological_position=position,
                    selection_reason=candidate.selection_reason,
                    path=str(frame_path),
                    format="jpeg",
                    width=width,
                    height=height,
                    inspected=False,
                )
            )
        return tuple(frames), tuple(warnings)

    def _source_video_geometry(
        self, ffprobe: str, media_path: Path
    ) -> _VideoGeometry | None:
        geometry = self._video_geometry(ffprobe, media_path)
        if geometry is None or geometry.display_aspect_ratio is None:
            return None
        return geometry

    def _jpeg_geometry(self, ffprobe: str, frame_path: Path) -> _VideoGeometry | None:
        geometry = self._video_geometry(ffprobe, frame_path)
        if geometry is None or geometry.codec_name not in {"mjpeg", "jpeg"}:
            return None
        return geometry

    def _video_geometry(
        self, ffprobe: str, media_path: Path
    ) -> _VideoGeometry | None:
        result = self._command_runner.run(
            ffprobe,
            [
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name,width,height,sample_aspect_ratio,display_aspect_ratio",
                "-of",
                "json",
                str(media_path),
            ],
        )
        if result.returncode != 0:
            return None
        try:
            payload = json.loads(result.stdout)
        except (json.JSONDecodeError, TypeError):
            return None
        streams = payload.get("streams") if isinstance(payload, Mapping) else None
        stream = streams[0] if isinstance(streams, list) and streams else None
        if not isinstance(stream, Mapping):
            return None
        codec_name = _optional_text(stream.get("codec_name"))
        if codec_name is None:
            return None
        width = _nonnegative_int(stream.get("width"))
        height = _nonnegative_int(stream.get("height"))
        if width is None or height is None or width == 0 or height == 0:
            return None
        sample_aspect_ratio = _positive_ratio(stream.get("sample_aspect_ratio"))
        display_aspect_ratio = _positive_ratio(stream.get("display_aspect_ratio"))
        if display_aspect_ratio is None and sample_aspect_ratio is not None:
            display_aspect_ratio = width / height * sample_aspect_ratio
        return _VideoGeometry(
            codec_name=codec_name,
            width=width,
            height=height,
            sample_aspect_ratio=sample_aspect_ratio,
            display_aspect_ratio=display_aspect_ratio,
        )

    def _inspect_visual_frames(
        self,
        *,
        frames: tuple[VisualFrame, ...],
        batches: tuple[tuple[VisualFrame, ...], ...],
        media_path: Path,
        artifact_root: Path,
        source_geometry: _VideoGeometry,
        ffmpeg: str,
        ffprobe: str,
        has_question: bool,
    ) -> tuple[tuple[VisualFrame, ...], FrameInspectionState, tuple[str, ...]]:
        if not frames:
            return (), "not_applicable", ()
        if self._frame_inspector is None:
            return (
                frames,
                "host_inspection_required",
                (
                    "Visual frames are prepared in chronological batches of at most eight; "
                    "the host must inspect every listed frame before making a visual claim.",
                ),
            )
        try:
            inspection = self._frame_inspector.inspect(batches)
        except (OSError, RuntimeError, ValueError) as error:
            return (
                frames,
                "unavailable",
                (
                    "The host local-image capability could not inspect the selected frames; "
                    f"no visual claim is available. Diagnostic: {_escape_control_sequences(str(error))}",
                ),
            )
        requested_paths = {frame.path for frame in frames}
        inspected_paths = set(inspection.inspected_paths) & requested_paths
        inspected_frames = tuple(
            replace(frame, inspected=frame.path in inspected_paths) for frame in frames
        )
        if inspection.state == "unavailable":
            message = inspection.message or "The host local-image capability is unavailable."
            return (
                inspected_frames,
                "unavailable",
                (f"{_escape_control_sequences(message)} No visual claim is available.",),
            )

        detailed_frames, escalation_warnings = self._extract_requested_detail_frames(
            frames=inspected_frames,
            escalations=inspection.escalations,
            media_path=media_path,
            artifact_root=artifact_root,
            source_geometry=source_geometry,
            ffmpeg=ffmpeg,
            ffprobe=ffprobe,
            has_question=has_question,
        )
        if detailed_frames:
            detail_batches = _chronological_batches(detailed_frames)
            try:
                detail_inspection = self._frame_inspector.inspect(detail_batches)
            except (OSError, RuntimeError, ValueError) as error:
                return (
                    _replace_frames(inspected_frames, detailed_frames),
                    "unavailable",
                    escalation_warnings
                    + (
                        "The host local-image capability could not inspect the requested "
                        "higher-resolution frame; no visual claim is available for it. "
                        f"Diagnostic: {_escape_control_sequences(str(error))}",
                    ),
                )
            detail_paths = {frame.path for frame in detailed_frames}
            inspected_detail_paths = set(detail_inspection.inspected_paths) & detail_paths
            inspected_details = tuple(
                replace(frame, inspected=frame.path in inspected_detail_paths)
                for frame in detailed_frames
            )
            inspected_frames = _replace_frames(inspected_frames, inspected_details)
            if detail_inspection.state == "unavailable":
                message = (
                    detail_inspection.message
                    or "The host local-image capability is unavailable for the higher-resolution frame."
                )
                return (
                    inspected_frames,
                    "unavailable",
                    escalation_warnings
                    + (f"{_escape_control_sequences(message)} No visual claim is available.",),
                )
            if (
                inspection.state == "complete"
                and inspected_paths == requested_paths
                and detail_inspection.state == "complete"
                and inspected_detail_paths == detail_paths
            ):
                return inspected_frames, "complete", escalation_warnings
            detail_message = (
                detail_inspection.message
                or "The host could not inspect every higher-resolution frame."
            )
            return (
                inspected_frames,
                "partial",
                escalation_warnings
                + (
                    f"{_escape_control_sequences(detail_message)} Visual conclusions must name the gap.",
                ),
            )

        if inspection.state == "complete" and inspected_paths == requested_paths:
            return inspected_frames, "complete", escalation_warnings
        message = inspection.message or "The host could not inspect every selected frame."
        return (
            inspected_frames,
            "partial",
            escalation_warnings
            + (f"{_escape_control_sequences(message)} Visual conclusions must name the gap.",),
        )

    def _extract_requested_detail_frames(
        self,
        *,
        frames: tuple[VisualFrame, ...],
        escalations: tuple[FrameEscalation, ...],
        media_path: Path,
        artifact_root: Path,
        source_geometry: _VideoGeometry,
        ffmpeg: str,
        ffprobe: str,
        has_question: bool,
    ) -> tuple[tuple[VisualFrame, ...], tuple[str, ...]]:
        if escalations and not has_question:
            return (
                (),
                (
                    "A higher-resolution request was refused because this watch request "
                    "has no question that could materially depend on it.",
                ),
            )
        by_path = {frame.path: frame for frame in frames}
        detail_frames: list[VisualFrame] = []
        warnings: list[str] = []
        requested_paths: set[str] = set()
        for escalation in escalations:
            frame = by_path.get(escalation.frame_path)
            reason = escalation.reason.strip() if isinstance(escalation.reason, str) else ""
            if frame is None or not reason:
                warnings.append(
                    "An invalid higher-resolution request was refused because it did not "
                    "name one selected frame and a material reason."
                )
                continue
            if frame.path in requested_paths:
                continue
            requested_paths.add(frame.path)
            detail_path = artifact_root / (
                f"frame-{frame.chronological_position:04d}-"
                f"{int(round(frame.timestamp_seconds * 1000)):012d}-detail.jpg"
            )
            result = self._command_runner.run(
                ffmpeg,
                [
                    "-nostdin",
                    "-v",
                    "error",
                    "-ss",
                    _format_seconds(frame.timestamp_seconds),
                    "-i",
                    str(media_path),
                    "-map",
                    "0:v:0",
                    "-frames:v",
                    "1",
                    "-an",
                    "-sn",
                    "-dn",
                    "-vf",
                    _square_pixel_scale_filter(1024),
                    "-q:v",
                    "2",
                    "-n",
                    str(detail_path),
                ],
            )
            geometry = self._jpeg_geometry(ffprobe, detail_path)
            if (
                result.returncode != 0
                or not detail_path.is_file()
                or geometry is None
                or not _valid_frame_geometry(
                    geometry, source_geometry, max_width=1024
                )
            ):
                warnings.append(
                    "The requested higher-resolution frame could not be extracted as an "
                    "aspect-correct JPEG within the 1024 px limit."
                )
                continue
            width, height = geometry.width, geometry.height
            detail_frames.append(
                replace(
                    frame,
                    path=str(detail_path),
                    width=width,
                    height=height,
                    inspected=False,
                    resolution_reason=_escape_control_sequences(reason),
                )
            )
        return tuple(detail_frames), tuple(warnings)

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


def _empty_visual_evidence(controls: WatchControls) -> VisualEvidence:
    return VisualEvidence(
        frames=(),
        candidate_count=0,
        ordinary_candidate_count=0,
        cap=_visual_cap(controls),
        ordinary_frame_cap=_ordinary_frame_cap(controls),
        deduplication="not_needed",
        fallback="none",
        cue_requested_count=len(controls.cues_seconds),
        cue_selected_count=0,
        cue_dropped_by_cap_count=0,
        cue_dropped_by_rate_count=0,
        inspection_state="not_applicable",
        inspection_batches=(),
    )


def _visual_cap(controls: WatchControls) -> int | None:
    if controls.max_frames is not None:
        return controls.max_frames
    if controls.detail == "transcript":
        # The zero ordinary-frame cap is reported separately. Transcript detail
        # does not create ordinary frames, so valid pinned cues stay cue-only evidence.
        return None
    return {
        "efficient": 50,
        "balanced": 100,
        "token-burner": None,
    }[controls.detail]


def _ordinary_frame_cap(controls: WatchControls) -> int | None:
    if controls.max_frames is not None:
        return controls.max_frames
    return {
        "transcript": 0,
        "efficient": 50,
        "balanced": 100,
        "token-burner": None,
    }[controls.detail]


def _visual_scope(controls: WatchControls, duration_seconds: float) -> tuple[float, float]:
    start = controls.focus_start_seconds if controls.focus_start_seconds is not None else 0.0
    requested_end = (
        controls.focus_end_seconds
        if controls.focus_end_seconds is not None
        else duration_seconds
    )
    return start, min(requested_end, duration_seconds)


def _ordinary_target(
    *, scope_start: float, scope_end: float, focused: bool, cap: int | None
) -> int:
    duration = max(0.0, scope_end - scope_start)
    if focused:
        if duration <= 5:
            target = 10
        elif duration <= 15:
            target = 30
        elif duration <= 30:
            target = 60
        elif duration <= 60:
            target = 80
        else:
            target = math.ceil(duration * 2)
    elif duration <= 30:
        target = min(30, max(12, math.ceil(duration)))
    elif duration <= 60:
        target = 40
    elif duration <= 180:
        target = 60
    elif duration <= 600:
        target = 80
    else:
        target = math.ceil(duration / 6)
    rate_limited_target = min(target, max(1, math.floor(duration * 2)))
    return min(rate_limited_target, cap) if cap is not None else rate_limited_target


def _uniform_candidates(
    scope_start: float, scope_end: float, count: int
) -> tuple[_FrameCandidate, ...]:
    if count <= 0:
        return ()
    if count == 1:
        return (_FrameCandidate(scope_start, "first"),)
    interval = (scope_end - scope_start) / (count - 1)
    return tuple(
        _FrameCandidate(
            scope_start + index * interval,
            "first" if index == 0 else "uniform",
        )
        for index in range(count)
    )


def _unique_candidates(
    timestamps: Sequence[float], reason: FrameSelectionReason
) -> tuple[_FrameCandidate, ...]:
    unique_timestamps = sorted({round(timestamp, 6) for timestamp in timestamps})
    return tuple(
        _FrameCandidate(timestamp, reason) for timestamp in unique_timestamps
    )


def _thin_candidates(
    candidates: Sequence[_FrameCandidate], cap: int | None
) -> tuple[tuple[_FrameCandidate, ...], int]:
    ordered = tuple(candidates)
    if cap is None or len(ordered) <= cap:
        return ordered, 0
    if cap == 1:
        return (ordered[0],), len(ordered) - 1
    indices = {
        math.floor(index * (len(ordered) - 1) / (cap - 1))
        for index in range(cap)
    }
    retained = tuple(candidate for index, candidate in enumerate(ordered) if index in indices)
    return retained, len(ordered) - len(retained)


def _limit_sampling_rate(
    candidates: Sequence[_FrameCandidate],
) -> tuple[tuple[_FrameCandidate, ...], int]:
    retained: list[_FrameCandidate] = []
    for candidate in sorted(candidates, key=lambda item: item.timestamp_seconds):
        if (
            not retained
            or candidate.timestamp_seconds - retained[-1].timestamp_seconds >= 0.5 - 1e-9
        ):
            retained.append(candidate)
    return tuple(retained), len(candidates) - len(retained)


def _exclude_candidates_near_pins(
    candidates: Sequence[_FrameCandidate], pins: Sequence[_FrameCandidate]
) -> tuple[tuple[_FrameCandidate, ...], int]:
    pin_times = tuple(pin.timestamp_seconds for pin in pins)
    retained = tuple(
        candidate
        for candidate in candidates
        if all(
            abs(candidate.timestamp_seconds - pin_time) >= 0.5 - 1e-9
            for pin_time in pin_times
        )
    )
    return retained, len(candidates) - len(retained)


def _merge_visual_candidates(
    cues: Sequence[_FrameCandidate], ordinary: Sequence[_FrameCandidate]
) -> tuple[_FrameCandidate, ...]:
    merged: dict[float, _FrameCandidate] = {
        round(candidate.timestamp_seconds, 6): candidate for candidate in ordinary
    }
    for cue in cues:
        merged[round(cue.timestamp_seconds, 6)] = cue
    return tuple(candidate for _, candidate in sorted(merged.items()))


def _chronological_batches(
    frames: Sequence[VisualFrame],
) -> tuple[tuple[VisualFrame, ...], ...]:
    return tuple(
        tuple(frames[start : start + 8]) for start in range(0, len(frames), 8)
    )


def _replace_frames(
    frames: Sequence[VisualFrame], replacements: Sequence[VisualFrame]
) -> tuple[VisualFrame, ...]:
    by_position = {frame.chronological_position: frame for frame in replacements}
    return tuple(
        by_position.get(frame.chronological_position, frame) for frame in frames
    )


def _square_pixel_scale_filter(max_width: int) -> str:
    return (
        f"scale=w='min({max_width},min(iw,iw*sar))':"
        "h='2*trunc((ow/dar+1)/2)',setsar=1"
    )


def _valid_frame_geometry(
    geometry: _VideoGeometry, source_geometry: _VideoGeometry, *, max_width: int = 768
) -> bool:
    width, height = geometry.width, geometry.height
    if width > max_width:
        return False
    if width > min(max_width, source_geometry.width):
        return False
    if (
        geometry.sample_aspect_ratio is None
        or not math.isclose(geometry.sample_aspect_ratio, 1.0, rel_tol=0.0, abs_tol=0.01)
        or source_geometry.display_aspect_ratio is None
    ):
        return False
    return math.isclose(
        width / height,
        source_geometry.display_aspect_ratio,
        rel_tol=0.02,
        abs_tol=0.02,
    )


def _format_seconds(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


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
    effective_focus_end = controls.focus_end_seconds
    if effective_focus_end is not None and duration_seconds is not None:
        effective_focus_end = min(effective_focus_end, duration_seconds)
    retained_cues = tuple(
        cue_seconds
        for cue_seconds in controls.cues_seconds
        if (
            controls.focus_start_seconds is None
            or cue_seconds >= controls.focus_start_seconds
        )
        and (
            effective_focus_end is None or cue_seconds <= effective_focus_end
        )
    )
    return (
        replace(
            controls,
            focus_end_seconds=effective_focus_end,
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


def _caption_candidates_from_ytdlp(
    data: Mapping[str, object],
) -> tuple[_CaptionCandidate, ...]:
    formats_by_track: dict[tuple[str, CaptionType], set[str]] = {}
    caption_catalogs: tuple[tuple[CaptionType, str], ...] = (
        ("manual", "subtitles"),
        ("automatic", "automatic_captions"),
    )
    for caption_type, field_name in caption_catalogs:
        catalog = data.get(field_name)
        if not isinstance(catalog, Mapping):
            continue
        for raw_language, raw_formats in catalog.items():
            language = _caption_language(raw_language)
            if language is None or language.casefold().startswith("live_chat"):
                continue
            if not isinstance(raw_formats, Sequence) or isinstance(
                raw_formats, (str, bytes)
            ):
                continue
            track_formats = formats_by_track.setdefault((language, caption_type), set())
            for raw_format in raw_formats:
                if not isinstance(raw_format, Mapping):
                    continue
                extension = _caption_format(raw_format.get("ext"))
                if extension is None:
                    continue
                track_formats.add(extension)
    candidates = {
        _CaptionCandidate(
            language=language,
            caption_type=caption_type,
            format=_preferred_caption_format(formats),
            usable=bool(formats & SUPPORTED_CAPTION_FORMATS),
        )
        for (language, caption_type), formats in formats_by_track.items()
        if formats
    }
    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                candidate.language.casefold(),
                0 if candidate.caption_type == "manual" else 1,
                candidate.format,
            ),
        )
    )


def _preferred_caption_format(formats: set[str]) -> str:
    for format_name in CAPTION_FORMAT_PREFERENCE:
        if format_name in formats:
            return format_name
    return min(formats)


def _caption_language(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    language = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", language):
        return None
    return language


def _caption_format(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    extension = value.strip().casefold()
    if not re.fullmatch(r"[a-z0-9]{1,16}", extension):
        return None
    return extension


def _caption_choice_from_inventory(item: CaptionInventoryItem) -> CaptionChoice:
    return CaptionChoice(
        id=item.id,
        kind=item.kind,
        language=item.language,
        caption_type=item.caption_type,
        format=item.format,
    )


def _new_decision_handle() -> str:
    return f"decision_{secrets.token_urlsafe(24)}"


def _prior_evidence_matches_selection(
    prior_evidence: object,
    source: Source,
    selection: _CaptionSelection,
) -> bool:
    if isinstance(prior_evidence, EvidenceOutcome):
        prior_payload: object = prior_evidence.to_dict()
    else:
        prior_payload = prior_evidence
    if not isinstance(prior_payload, Mapping):
        return False
    if (
        prior_payload.get("state") != "decision_required"
        or prior_payload.get("terminal") is not False
        or prior_payload.get("choice_kind") != "caption_track"
    ):
        return False
    prior_source = prior_payload.get("source")
    raw_choices = prior_payload.get("choices")
    decision_handle = prior_payload.get("decision_handle")
    if (
        not isinstance(prior_source, Mapping)
        or prior_source.get("kind") != source.kind
        or prior_source.get("value") != source.value
        or prior_source.get("current") is not True
        or not isinstance(raw_choices, Sequence)
        or isinstance(raw_choices, (str, bytes))
        or decision_handle != selection.decision_handle
    ):
        return False
    expected_choice = asdict(selection.choice)
    return any(
        isinstance(choice, Mapping) and dict(choice) == expected_choice
        for choice in raw_choices
    )


def _choice_matches_candidate(
    choice: CaptionChoice, candidate: _CaptionCandidate
) -> bool:
    return (
        candidate.usable
        and choice.kind == "caption_track"
        and choice.language == candidate.language
        and choice.caption_type == candidate.caption_type
        and choice.format == candidate.format
    )


_VTT_TIMING = re.compile(
    r"^\s*(?P<start>(?:(?:\d{2,}):)?\d{2}:\d{2}\.\d{3})"
    r"\s+-->\s+"
    r"(?P<end>(?:(?:\d{2,}):)?\d{2}:\d{2}\.\d{3})(?:\s+.*)?$"
)
_TTML_DISALLOWED_DECLARATION = re.compile(
    br"<!\s*(?:doctype|entity)\b", re.IGNORECASE
)
_TTML_FRAME_CLOCK = re.compile(
    r"^(?P<hours>\d+):(?P<minutes>\d{2}):(?P<seconds>\d{2}):"
    r"(?P<frames>\d{2})(?:\.(?P<subframes>\d+))?$"
)
_TTML_MEDIA_CLOCK = re.compile(
    r"^(?P<hours>\d+):(?P<minutes>\d{2}):(?P<seconds>\d{2})"
    r"(?:\.(?P<fraction>\d+))?$"
)
_TTML_OFFSET_TIME = re.compile(
    r"^(?P<number>(?:\d+(?:\.\d*)?|\.\d+))(?P<unit>h|m|ms|s|f|t)$"
)
_TTML_CONTENT_NAMESPACES = frozenset(
    {
        "",
        "http://www.w3.org/ns/ttml",
        "http://www.w3.org/2006/10/ttaf1",
    }
)
_TTML_PARAMETER_NAMESPACES = frozenset(
    {
        "",
        "http://www.w3.org/ns/ttml#parameter",
        "http://www.w3.org/2006/10/ttaf1#parameter",
    }
)
_TTML_TIMING_ATTRIBUTES = frozenset({"begin", "dur", "end", "timeContainer"})
_TTML_PARAMETER_ATTRIBUTES = frozenset(
    {"frameRate", "frameRateMultiplier", "subFrameRate", "tickRate", "timeBase"}
)


@dataclass(frozen=True)
class _TTMLTiming:
    frame_rate: float
    sub_frame_rate: int
    tick_rate: float


def _parse_caption(
    caption_format: str, value: bytes
) -> tuple[TranscriptSegment, ...] | None:
    if caption_format == "vtt":
        try:
            return _parse_webvtt(value.decode("utf-8-sig"))
        except UnicodeDecodeError:
            return None
    if caption_format == "ttml":
        return _parse_ttml(value)
    return None


def _parse_webvtt(value: str) -> tuple[TranscriptSegment, ...] | None:
    lines = value.splitlines()
    if not lines or not lines[0].lstrip().startswith("WEBVTT"):
        return None
    segments: list[TranscriptSegment] = []
    index = 1
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line.startswith(("NOTE", "STYLE", "REGION")):
            index += 1
            while index < len(lines) and lines[index].strip():
                index += 1
            continue
        timing = _VTT_TIMING.match(lines[index])
        if timing is None:
            index += 1
            continue
        start_seconds = _parse_webvtt_timestamp(timing.group("start"))
        end_seconds = _parse_webvtt_timestamp(timing.group("end"))
        index += 1
        text_lines: list[str] = []
        while index < len(lines) and lines[index].strip():
            text_lines.append(lines[index])
            index += 1
        text = _normalize_caption_text(text_lines)
        if (
            start_seconds is not None
            and end_seconds is not None
            and end_seconds > start_seconds
            and text is not None
        ):
            segments.append(TranscriptSegment(text, start_seconds, end_seconds))
    if not segments:
        return None
    return tuple(sorted(segments, key=lambda segment: (segment.start_seconds, segment.end_seconds)))


def _parse_webvtt_timestamp(value: str) -> float | None:
    parts = value.split(":")
    if len(parts) not in {2, 3}:
        return None
    try:
        numbers = [float(part) for part in parts]
    except ValueError:
        return None
    if any(not math.isfinite(number) or number < 0 for number in numbers):
        return None
    if len(numbers) == 3 and numbers[1] >= 60:
        return None
    if numbers[-1] >= 60:
        return None
    seconds = 0.0
    for number in numbers:
        seconds = seconds * 60 + number
    return seconds


def _parse_ttml(value: bytes) -> tuple[TranscriptSegment, ...] | None:
    if _TTML_DISALLOWED_DECLARATION.search(value.replace(b"\x00", b"")) is not None:
        return None
    try:
        root = ET.fromstring(value)
    except (ET.ParseError, UnicodeError, ValueError):
        return None
    if not _is_ttml_element(root, {"tt"}):
        return None
    time_base = _ttml_parameter_attribute(root, "timeBase")
    if time_base is not None and time_base.strip().casefold() != "media":
        return None
    timing = _ttml_timing(root)
    if timing is None:
        return None

    segments: list[TranscriptSegment] = []
    try:
        _collect_ttml_segments(
            root,
            parent_start_seconds=0.0,
            parent_end_seconds=None,
            timing=timing,
            segments=segments,
        )
    except RecursionError:
        return None
    if not segments:
        return None
    return tuple(
        sorted(segments, key=lambda segment: (segment.start_seconds, segment.end_seconds))
    )


def _xml_local_name(value: object) -> str:
    return _xml_namespace_and_local_name(value)[1]


def _xml_namespace_and_local_name(value: object) -> tuple[str, str]:
    if not isinstance(value, str):
        return "", ""
    if value.startswith("{"):
        namespace, separator, local_name = value[1:].partition("}")
        if separator:
            return namespace, local_name
    return "", value.rsplit(":", 1)[-1]


def _is_ttml_element(element: ET.Element, names: set[str]) -> bool:
    namespace, local_name = _xml_namespace_and_local_name(element.tag)
    return namespace in _TTML_CONTENT_NAMESPACES and local_name in names


def _ttml_attribute(
    element: ET.Element, name: str, allowed_namespaces: frozenset[str]
) -> str | None:
    for raw_name, value in element.attrib.items():
        namespace, local_name = _xml_namespace_and_local_name(raw_name)
        if local_name == name and namespace in allowed_namespaces:
            return value
    return None


def _ttml_timing_attribute(element: ET.Element, name: str) -> str | None:
    assert name in _TTML_TIMING_ATTRIBUTES
    return _ttml_attribute(element, name, frozenset({""}))


def _ttml_parameter_attribute(element: ET.Element, name: str) -> str | None:
    assert name in _TTML_PARAMETER_ATTRIBUTES
    return _ttml_attribute(element, name, _TTML_PARAMETER_NAMESPACES)


def _ttml_timing(root: ET.Element) -> _TTMLTiming | None:
    raw_frame_rate = _ttml_parameter_attribute(root, "frameRate")
    if raw_frame_rate is None:
        frame_rate = 30.0
    else:
        frame_rate = _positive_ttml_number(raw_frame_rate)
        if frame_rate is None:
            return None

    multiplier = _ttml_parameter_attribute(root, "frameRateMultiplier")
    if multiplier is not None:
        multiplier_parts = multiplier.split()
        if len(multiplier_parts) != 2:
            return None
        numerator = _positive_ttml_number(multiplier_parts[0])
        denominator = _positive_ttml_number(multiplier_parts[1])
        if numerator is None or denominator is None:
            return None
        frame_rate *= numerator / denominator
        if not math.isfinite(frame_rate) or frame_rate <= 0:
            return None

    raw_sub_frame_rate = _ttml_parameter_attribute(root, "subFrameRate")
    if raw_sub_frame_rate is None:
        sub_frame_rate = 1
    else:
        try:
            sub_frame_rate = int(raw_sub_frame_rate)
        except ValueError:
            return None
        if sub_frame_rate <= 0:
            return None

    raw_tick_rate = _ttml_parameter_attribute(root, "tickRate")
    if raw_tick_rate is None:
        tick_rate = frame_rate * sub_frame_rate
    else:
        tick_rate = _positive_ttml_number(raw_tick_rate)
        if tick_rate is None:
            return None
    if not math.isfinite(tick_rate) or tick_rate <= 0:
        return None
    return _TTMLTiming(frame_rate, sub_frame_rate, tick_rate)


def _positive_ttml_number(value: object) -> float | None:
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _parse_ttml_time(value: str, timing: _TTMLTiming) -> float | None:
    text = value.strip()
    frame_clock = _TTML_FRAME_CLOCK.fullmatch(text)
    if frame_clock is not None:
        try:
            hours = int(frame_clock.group("hours"))
            minutes = int(frame_clock.group("minutes"))
            seconds = int(frame_clock.group("seconds"))
            frames = int(frame_clock.group("frames"))
            subframes_text = frame_clock.group("subframes")
            subframes = int(subframes_text) if subframes_text is not None else 0
        except ValueError:
            return None
        if (
            minutes >= 60
            or seconds >= 60
            or frames >= math.ceil(timing.frame_rate)
            or subframes >= timing.sub_frame_rate
        ):
            return None
        return (
            hours * 3600
            + minutes * 60
            + seconds
            + (frames + subframes / timing.sub_frame_rate) / timing.frame_rate
        )

    media_clock = _TTML_MEDIA_CLOCK.fullmatch(text)
    if media_clock is not None:
        try:
            hours = int(media_clock.group("hours"))
            minutes = int(media_clock.group("minutes"))
            seconds = int(media_clock.group("seconds"))
            fraction_text = media_clock.group("fraction")
            fraction = (
                float(f"0.{fraction_text}") if fraction_text is not None else 0.0
            )
        except ValueError:
            return None
        if minutes >= 60 or seconds >= 60:
            return None
        return hours * 3600 + minutes * 60 + seconds + fraction

    offset = _TTML_OFFSET_TIME.fullmatch(text)
    if offset is None:
        return None
    try:
        number = float(offset.group("number"))
    except ValueError:
        return None
    if not math.isfinite(number) or number < 0:
        return None
    unit = offset.group("unit")
    multipliers = {
        "h": 3600.0,
        "m": 60.0,
        "s": 1.0,
        "ms": 0.001,
        "f": 1.0 / timing.frame_rate,
        "t": 1.0 / timing.tick_rate,
    }
    seconds = number * multipliers[unit]
    return seconds if math.isfinite(seconds) else None


def _ttml_interval(
    element: ET.Element,
    parent_start_seconds: float,
    parent_end_seconds: float | None,
    timing: _TTMLTiming,
) -> tuple[float, float | None] | None:
    begin_value = _ttml_timing_attribute(element, "begin")
    begin_offset = 0.0
    if begin_value is not None:
        begin_offset = _parse_ttml_time(begin_value, timing)
        if begin_offset is None:
            return None
    start_seconds = parent_start_seconds + begin_offset
    end_candidates: list[float] = []
    if parent_end_seconds is not None:
        end_candidates.append(parent_end_seconds)

    end_value = _ttml_timing_attribute(element, "end")
    if end_value is not None:
        end_offset = _parse_ttml_time(end_value, timing)
        if end_offset is None:
            return None
        end_candidates.append(parent_start_seconds + end_offset)

    duration_value = _ttml_timing_attribute(element, "dur")
    if duration_value is not None:
        duration_seconds = _parse_ttml_time(duration_value, timing)
        if duration_seconds is None:
            return None
        end_candidates.append(start_seconds + duration_seconds)

    end_seconds = min(end_candidates) if end_candidates else None
    if end_seconds is not None and end_seconds <= start_seconds:
        return None
    return start_seconds, end_seconds


def _collect_ttml_segments(
    element: ET.Element,
    *,
    parent_start_seconds: float,
    parent_end_seconds: float | None,
    timing: _TTMLTiming,
    segments: list[TranscriptSegment],
) -> float | None:
    interval = _ttml_interval(
        element, parent_start_seconds, parent_end_seconds, timing
    )
    if interval is None:
        return None
    start_seconds, end_seconds = interval
    element_name = _xml_local_name(element.tag)
    if element_name == "p":
        if end_seconds is None:
            return None
        if _has_timed_ttml_inline_content(element):
            return end_seconds
        text = _ttml_caption_text(element)
        if text is not None:
            segments.append(TranscriptSegment(text, start_seconds, end_seconds))
        return end_seconds

    time_container = (
        _ttml_timing_attribute(element, "timeContainer") or "par"
    ).strip().casefold()
    if time_container not in {"par", "seq"}:
        return None
    timed_children = tuple(
        child
        for child in element
        if _is_ttml_element(child, {"body", "div", "p"})
    )
    if time_container == "seq":
        cursor = start_seconds
        for child in timed_children:
            child_end_seconds = _collect_ttml_segments(
                child,
                parent_start_seconds=cursor,
                parent_end_seconds=end_seconds,
                timing=timing,
                segments=segments,
            )
            if child_end_seconds is None:
                return None
            cursor = child_end_seconds
        if end_seconds is None:
            return cursor if timed_children else None
    else:
        child_end_seconds: list[float] = []
        for child in timed_children:
            child_end = _collect_ttml_segments(
                child,
                parent_start_seconds=start_seconds,
                parent_end_seconds=end_seconds,
                timing=timing,
                segments=segments,
            )
            if child_end is not None:
                child_end_seconds.append(child_end)
        if end_seconds is None:
            return max(child_end_seconds, default=None)
    return end_seconds


def _has_timed_ttml_inline_content(element: ET.Element) -> bool:
    for descendant in element.iter():
        if descendant is element:
            continue
        if not _is_ttml_element(descendant, {"span", "br"}):
            continue
        if any(
            _ttml_timing_attribute(descendant, name) is not None
            for name in _TTML_TIMING_ATTRIBUTES
        ):
            return True
    return False


def _ttml_caption_text(element: ET.Element) -> str | None:
    parts: list[str] = []

    def visit(current: ET.Element) -> None:
        if current.text:
            parts.append(current.text)
        for child in current:
            if _is_ttml_element(child, {"br"}):
                parts.append(" ")
            else:
                visit(child)
            if child.tail:
                parts.append(child.tail)

    visit(element)
    return _normalize_caption_text(parts, strip_markup=False, unescape_html=False)


def _normalize_caption_text(
    lines: Sequence[str], *, strip_markup: bool = True, unescape_html: bool = True
) -> str | None:
    text = " ".join(lines)
    if strip_markup:
        text = re.sub(r"<[^>]*>", "", text)
    if unescape_html:
        text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    text = "".join(character for character in text if character.isprintable())
    if not text:
        return None
    return text


def _transcript_scope(
    controls: WatchControls, duration_seconds: float | None
) -> _TranscriptScope | None:
    start_seconds = controls.focus_start_seconds or 0.0
    end_seconds = controls.focus_end_seconds
    if end_seconds is None:
        end_seconds = duration_seconds
    if end_seconds is None and controls.focus_start_seconds is None:
        return None
    return _TranscriptScope(start_seconds, end_seconds)


def _segments_overlapping_scope(
    segments: Sequence[TranscriptSegment], scope: _TranscriptScope | None
) -> tuple[TranscriptSegment, ...]:
    if scope is None:
        return tuple(segments)
    return tuple(
        segment
        for segment in segments
        if segment.end_seconds > scope.start_seconds
        and (
            scope.end_seconds is None or segment.start_seconds < scope.end_seconds
        )
    )


def _ranges_for_segments(
    segments: Sequence[TranscriptSegment], scope: _TranscriptScope | None
) -> tuple[TimeRange, ...]:
    ranges: list[TimeRange] = []
    for segment in segments:
        start_seconds = segment.start_seconds
        end_seconds = segment.end_seconds
        if scope is not None:
            start_seconds = max(start_seconds, scope.start_seconds)
            if scope.end_seconds is not None:
                end_seconds = min(end_seconds, scope.end_seconds)
        if end_seconds > start_seconds:
            ranges.append(TimeRange(start_seconds, end_seconds))
    return tuple(ranges)


def _merge_ranges(ranges: Sequence[TimeRange]) -> tuple[TimeRange, ...]:
    merged: list[TimeRange] = []
    for current in sorted(ranges, key=lambda interval: (interval.start_seconds, interval.end_seconds)):
        if not merged or current.start_seconds > merged[-1].end_seconds:
            merged.append(current)
        else:
            previous = merged[-1]
            merged[-1] = TimeRange(
                previous.start_seconds,
                max(previous.end_seconds, current.end_seconds),
            )
    return tuple(merged)


def _unavailable_ranges(
    available_ranges: Sequence[TimeRange], scope: _TranscriptScope | None
) -> tuple[TimeRange, ...]:
    if scope is None or scope.end_seconds is None:
        return ()
    unavailable: list[TimeRange] = []
    cursor = scope.start_seconds
    for available in available_ranges:
        if available.start_seconds > cursor:
            unavailable.append(TimeRange(cursor, available.start_seconds))
        cursor = max(cursor, available.end_seconds)
    if cursor < scope.end_seconds:
        unavailable.append(TimeRange(cursor, scope.end_seconds))
    return tuple(unavailable)


def _collapse_rolling_segments(
    segments: Sequence[TranscriptSegment],
) -> tuple[TranscriptSegment, ...]:
    collapsed: list[TranscriptSegment] = []
    previous_raw: TranscriptSegment | None = None
    latest_text_index: int | None = None
    for segment in segments:
        if previous_raw is not None and segment.start_seconds <= previous_raw.end_seconds:
            if segment.text == previous_raw.text:
                if latest_text_index is not None:
                    collapsed[latest_text_index] = replace(
                        collapsed[latest_text_index],
                        end_seconds=max(
                            collapsed[latest_text_index].end_seconds,
                            segment.end_seconds,
                        ),
                    )
                previous_raw = segment
                continue
            if segment.text.startswith(previous_raw.text):
                extension = segment.text[len(previous_raw.text) :].strip()
                if extension:
                    collapsed.append(
                        TranscriptSegment(
                            extension, segment.start_seconds, segment.end_seconds
                        )
                    )
                    latest_text_index = len(collapsed) - 1
                previous_raw = segment
                continue
            if previous_raw.text.startswith(segment.text):
                collapsed.append(segment)
                latest_text_index = len(collapsed) - 1
                previous_raw = segment
                continue
        collapsed.append(segment)
        latest_text_index = len(collapsed) - 1
        previous_raw = segment
    return tuple(collapsed)


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


def _positive_ratio(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        ratio = float(value)
        return ratio if math.isfinite(ratio) and ratio > 0 else None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if ":" not in text:
        try:
            ratio = float(text)
        except ValueError:
            return None
        return ratio if math.isfinite(ratio) and ratio > 0 else None
    numerator_text, separator, denominator_text = text.partition(":")
    if not separator or ":" in denominator_text:
        return None
    try:
        numerator = float(numerator_text)
        denominator = float(denominator_text)
    except ValueError:
        return None
    if (
        not math.isfinite(numerator)
        or not math.isfinite(denominator)
        or numerator <= 0
        or denominator <= 0
    ):
        return None
    return numerator / denominator


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
    transcript: TranscriptEvidence | None = None,
    coverage: EvidenceCoverage,
    answerability: Answerability,
    warnings: tuple[str, ...],
    tools: tuple[ToolStatus, ...],
    javascript_support: JavaScriptSupport,
    controls: WatchControls,
    visual: VisualEvidence | None = None,
    choice_kind: ChoiceKind | None = None,
    choices: Sequence[CaptionChoice] = (),
    decision_handle: str | None = None,
) -> str:
    terminal_state = "nonterminal" if state in {"decision_required", "consent_required"} else "terminal"
    lines = [
        "# Watch evidence report",
        "",
        f"- State: `{state}` ({terminal_state})",
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
    if transcript is not None:
        lines.extend(
            [
                f"- Transcript provenance: `{transcript.provenance}`",
                f"- Transcript language: `{transcript.language}`",
                "- Selected caption track: "
                f"`{transcript.selected_track.id}`; "
                f"language `{transcript.selected_track.language}`, "
                f"type `{transcript.selected_track.caption_type}`, "
                f"format `{transcript.selected_track.format}`",
                f"- Transcript segment count: `{len(transcript.segments)}`",
                f"- Transcript source count: `{transcript.source_count}`",
            ]
        )
        if transcript.available_ranges:
            lines.append(
                "- Transcript available ranges: "
                + _render_time_ranges(transcript.available_ranges)
            )
        if transcript.unavailable_ranges:
            lines.append(
                "- Transcript unavailable ranges: "
                + _render_time_ranges(transcript.unavailable_ranges)
            )
    if visual is not None:
        lines.extend(["", "## Visual evidence"])
        cap = "none" if visual.cap is None else str(visual.cap)
        lines.extend(
            [
                f"- Selected frames: `{len(visual.frames)}`",
                f"- Candidate frames: `{visual.candidate_count}`",
                f"- Ordinary candidates: `{visual.ordinary_candidate_count}`",
                f"- Frame cap: `{cap}`",
                "- Ordinary-frame cap: `"
                + (
                    "none"
                    if visual.ordinary_frame_cap is None
                    else str(visual.ordinary_frame_cap)
                )
                + "`",
                f"- Frame selection: `{visual.fallback}`",
                f"- Ordinary deduplication: `{visual.deduplication}`",
                f"- Requested cue frames: `{visual.cue_requested_count}`",
                f"- Selected cue frames: `{visual.cue_selected_count}`",
                f"- Visual inspection: `{visual.inspection_state}`",
            ]
        )
        if visual.inspection_state in {"host_inspection_required", "unavailable"}:
            lines.append("- Visual claims: `none until host inspection`")
        elif visual.inspection_state == "partial":
            lines.append("- Visual claims: `only inspected frames; gaps must be stated`")
        elif visual.inspection_state == "complete":
            lines.append("- Visual claims: `only from the inspected frames below`")
        if visual.cue_dropped_by_cap_count:
            lines.append(
                f"- Cue frames dropped by cap: `{visual.cue_dropped_by_cap_count}`"
            )
        if visual.cue_dropped_by_rate_count:
            lines.append(
                f"- Cue frames dropped by sampling rate: `{visual.cue_dropped_by_rate_count}`"
            )
        if not visual.frames:
            lines.append("- Selected frame paths: `none`")
        else:
            lines.append("- Selected frame paths, in chronological order:")
            for frame in visual.frames:
                resolution = (
                    "; higher-resolution reason "
                    f"{_render_preescaped_markdown_code(frame.resolution_reason)}"
                    if frame.resolution_reason is not None
                    else ""
                )
                lines.append(
                    "  - "
                    f"`{_format_seconds(frame.timestamp_seconds)}` seconds; "
                    f"position `{frame.chronological_position}`; "
                    f"reason `{frame.selection_reason}`; "
                    f"size `{frame.width}x{frame.height}` JPEG{resolution}; "
                    f"inspected `{str(frame.inspected).lower()}`; "
                    f"path {_render_untrusted_markdown_code(frame.path)}"
                )
            lines.append("- Required host inspection batches, in chronological order:")
            for batch_index, batch in enumerate(visual.inspection_batches, start=1):
                positions = ", ".join(
                    str(frame.chronological_position) for frame in batch
                )
                lines.append(f"  - Batch `{batch_index}`: frame positions `{positions}`")
    if choice_kind is not None:
        lines.extend(["", "## Decision required"])
        lines.append(f"- Choice kind: `{choice_kind}`")
        if decision_handle is not None:
            lines.append(f"- Decision handle: `{decision_handle}`")
        for choice in choices:
            lines.append(
                "- Caption choice "
                f"`{choice.id}`: language `{choice.language}`, "
                f"type `{choice.caption_type}`, format `{choice.format}`"
            )
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


def _render_time_ranges(ranges: Sequence[TimeRange]) -> str:
    return ", ".join(
        f"`{interval.start_seconds}`–`{interval.end_seconds}`" for interval in ranges
    )


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
