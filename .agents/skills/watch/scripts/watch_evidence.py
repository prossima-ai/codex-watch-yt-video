from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import fcntl
import hashlib
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
import stat
import subprocess
import tempfile
from typing import Any, Callable, Literal, Mapping, Protocol, Sequence, TextIO, TypeGuard
from urllib.parse import urlsplit
from urllib import error as urlerror
from urllib import request as urlrequest
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
EvidenceStage = Literal["validation", "preflight", "metadata", "workspace", "reuse"]
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
    "invalid_evidence_handle",
    "evidence_disposed",
    "reuse_requires_approval",
    "workspace_creation",
]
DisposalState = Literal[
    "not_created",
    "retained",
    "cleanup_succeeded",
    "cleanup_already_absent",
    "cleanup_deferred",
    "cleanup_refused",
    "cleanup_incomplete",
]
ReuseState = Literal["none", "current_source_only", "same_task_evidence", "revoked"]
CleanupState = Literal[
    "cleanup_succeeded",
    "cleanup_already_absent",
    "cleanup_deferred",
    "cleanup_refused",
    "cleanup_incomplete",
]
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
    workspace_id: str | None = None
    evidence_handle: str | None = None
    disposition: EvidenceDisposition = field(
        default_factory=lambda: EvidenceDisposition(False, "not_created", "none")
    )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        failure = payload.get("failure")
        if isinstance(failure, dict):
            disposition = failure.pop("disposition")
            failure.update(disposition)
        disposition = payload.pop("disposition")
        payload.update(disposition)
        return payload


@dataclass(frozen=True)
class CleanupOutcome:
    state: CleanupState
    workspace_id: str | None
    message: str
    disposition: EvidenceDisposition
    report_markdown: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        disposition = payload.pop("disposition")
        payload.update(disposition)
        return payload


NO_EVIDENCE_NO_WORKSPACE = EvidenceDisposition(False, "not_created", "none")
CURRENT_SOURCE_NO_WORKSPACE = EvidenceDisposition(
    False, "not_created", "current_source_only"
)
JAVASCRIPT_NOT_CHECKED = JavaScriptSupport("not_checked", None)
MAX_CAPTION_BYTES = 4 * 1024 * 1024
SUPPORTED_CAPTION_FORMATS = frozenset({"ttml", "vtt"})
CAPTION_FORMAT_PREFERENCE = ("vtt", "ttml")
WORKSPACE_SCHEMA = "codex-watch-workspace"
WORKSPACE_MANIFEST_VERSION = 1
WORKSPACE_MARKER_NAME = ".codex-watch-workspace.json"
WORKSPACE_MANIFEST_NAME = ".codex-watch-manifest.jsonl"
WORKSPACE_LOCK_NAME = ".codex-watch.lock"
RUNTIME_ROOT_DIRECTORY_NAME = "codex-watch-runtime"
RUNTIME_ROOT_SCHEMA = "codex-watch-runtime-root"
RUNTIME_ROOT_VERSION = 1
RUNTIME_ROOT_MARKER_NAME = ".codex-watch-runtime-root.json"
WORKSPACE_CONTROL_NAMES = frozenset(
    {WORKSPACE_MARKER_NAME, WORKSPACE_MANIFEST_NAME, WORKSPACE_LOCK_NAME}
)
WORKSPACE_ID_PATTERN = re.compile(r"^workspace_[A-Za-z0-9_-]{20,}$")
_NOFOLLOW_DIRECTORY_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_NOFOLLOW_FILE_FLAGS = (
    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
)


@dataclass(frozen=True)
class _CaptionCandidate:
    language: str
    caption_type: CaptionType
    format: str
    usable: bool
    caption_url: str | None


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
    workspace_id: str


@dataclass(frozen=True)
class _TranscriptScope:
    start_seconds: float
    end_seconds: float | None


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class _ManifestArtifact:
    path: str
    kind: str
    disposition: Literal["retained"]
    size_bytes: int
    sha256: str


@dataclass
class _WorkspaceRecord:
    workspace_id: str
    path: Path
    path_identity: tuple[int, int]
    directory_fd: int | None
    source: Source | None
    controls: WatchControls | None
    evidence_handle: str | None
    marker_identity: tuple[int, int]
    manifest_identity: tuple[int, int]
    marker_digest: str
    manifest_digest: str
    lock_digest: str
    lock_file: TextIO
    artifacts: dict[str, _ManifestArtifact]
    outcome: EvidenceOutcome | None = None
    reuse_eligible: bool = True
    cleanup_state: CleanupState | None = None
    deleted_artifacts: set[str] = field(default_factory=set)
    deleted_controls: set[str] = field(default_factory=set)
    cleanup_only: bool = False


@dataclass(frozen=True)
class _CleanupRecordLookup:
    """A resolved cleanup record or an observed competing recovery lock."""

    record: _WorkspaceRecord | None
    deferred_workspace_id: str | None = None


class CommandRunner(Protocol):
    def run(
        self,
        executable: str,
        arguments: Sequence[str],
        *,
        input_fd: int | None = None,
        output_fd: int | None = None,
    ) -> CommandResult: ...


class CaptionFetcher(Protocol):
    def fetch(self, url: str, output_fd: int, *, max_bytes: int) -> None: ...


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


@dataclass(frozen=True)
class _VisualMedia:
    """One visual input, optionally retained in a runtime workspace."""

    argument: str
    workspace: _WorkspaceRecord | None


class SubprocessCommandRunner:
    def run(
        self,
        executable: str,
        arguments: Sequence[str],
        *,
        input_fd: int | None = None,
        output_fd: int | None = None,
    ) -> CommandResult:
        run_kwargs: dict[str, object] = {}
        # ``stdout`` is duplicated to descriptor 1 by subprocess itself.  The
        # child needs only an explicit pass-through descriptor when it reads a
        # retained workspace artifact through ``/dev/fd/<n>``.
        inherited_fds = (input_fd,) if input_fd is not None else ()
        for file_descriptor in inherited_fds:
            os.fstat(file_descriptor)
        if inherited_fds:
            run_kwargs["pass_fds"] = inherited_fds
        if output_fd is None:
            run_kwargs["stdout"] = subprocess.PIPE
        else:
            run_kwargs["stdout"] = output_fd
        run_kwargs["stderr"] = subprocess.PIPE
        completed = subprocess.run(
            [executable, *arguments],
            stdin=subprocess.DEVNULL,
            text=False,
            check=False,
            shell=False,
            timeout=30,
            **run_kwargs,
        )
        return CommandResult(
            completed.returncode,
            _decode_command_output(completed.stdout),
            _decode_command_output(completed.stderr),
        )


class UrlCaptionFetcher:
    """Fetch a selected public caption directly into a caller-owned descriptor."""

    def fetch(self, url: str, output_fd: int, *, max_bytes: int) -> None:
        _validate_caption_resource_url(url)
        opener = urlrequest.build_opener(
            urlrequest.ProxyHandler({}), _CaptionRedirectHandler()
        )
        request = urlrequest.Request(url, headers={"User-Agent": "codex-watch/1"})
        try:
            with opener.open(request, timeout=15) as response:
                _validate_caption_resource_url(response.geturl())
                total_bytes = 0
                while True:
                    chunk = response.read(min(64 * 1024, max_bytes + 1 - total_bytes))
                    if not chunk:
                        return
                    total_bytes += len(chunk)
                    if total_bytes > max_bytes:
                        raise OSError("The selected native caption exceeds the safe parsing limit.")
                    _write_all_bytes(output_fd, chunk)
        except (urlerror.URLError, TimeoutError) as error:
            raise OSError("The selected native caption could not be fetched.") from error


class _CaptionRedirectHandler(urlrequest.HTTPRedirectHandler):
    def redirect_request(
        self,
        request: urlrequest.Request,
        file_pointer: object,
        code: int,
        message: str,
        headers: object,
        new_url: str,
    ) -> urlrequest.Request | None:
        _validate_caption_resource_url(new_url)
        return super().redirect_request(
            request, file_pointer, code, message, headers, new_url
        )


class WatchEvidenceRuntime:
    def __init__(
        self,
        command_runner: CommandRunner | None = None,
        caption_fetcher: CaptionFetcher | None = None,
        find_executable: Callable[[str], str | None] = shutil.which,
        frame_inspector: FrameInspector | None = None,
        artifact_root: Path | None = None,
        visual_enabled: bool = True,
        reuse_enabled: bool = True,
    ) -> None:
        self._command_runner = command_runner or SubprocessCommandRunner()
        self._caption_fetcher = caption_fetcher or UrlCaptionFetcher()
        self._find_executable = find_executable
        self._frame_inspector = frame_inspector
        self._artifact_root = artifact_root
        self._visual_enabled = visual_enabled
        self._reuse_enabled = reuse_enabled
        self._caption_selections: dict[str, _CaptionSelection] = {}
        self._workspace_root: Path | None = None
        self._workspace_root_identity: tuple[int, int] | None = None
        self._workspace_root_fd: int | None = None
        self._workspace_root_marker_identity: tuple[int, int] | None = None
        self._workspace_root_marker_digest: str | None = None
        self._workspace_root_is_fixed = False
        self._workspaces: dict[str, _WorkspaceRecord] = {}
        self._evidence_handles: dict[str, _WorkspaceRecord] = {}
        self._retired_evidence_handles: dict[str, _WorkspaceRecord] = {}
        self._current_workspace_id: str | None = None
        self._current_source: Source | None = None

    def close(self) -> None:
        """Release this runtime's workspace locks without deleting any workspace."""

        for record in self._workspaces.values():
            lock_file = record.lock_file
            if not lock_file.closed:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                except (OSError, ValueError):
                    pass
                try:
                    lock_file.close()
                except OSError:
                    pass
            directory_fd = record.directory_fd
            record.directory_fd = None
            if directory_fd is not None:
                try:
                    os.close(directory_fd)
                except OSError:
                    pass
        if self._workspace_root_fd is not None:
            try:
                os.close(self._workspace_root_fd)
            except OSError:
                pass
            self._workspace_root_fd = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            # Interpreter shutdown can clear module globals before finalizers run.
            pass

    def cleanup(self, selector: object) -> CleanupOutcome:
        """Remove one tracked Watch workspace after explicit selector validation."""

        lookup = self._cleanup_record_for_selector(selector)
        if lookup.deferred_workspace_id is not None:
            return self._cleanup_outcome(
                "cleanup_deferred",
                None,
                "The recovered workspace is currently locked by another runtime; no files were deleted.",
                EvidenceDisposition(False, "cleanup_deferred", "none"),
                workspace_id=lookup.deferred_workspace_id,
            )
        record = lookup.record
        if record is None:
            return self._cleanup_outcome(
                "cleanup_refused",
                None,
                "Cleanup accepts only current or one opaque workspace ID issued by this runtime.",
                EvidenceDisposition(False, "cleanup_refused", "none"),
            )

        if _has_symlink_component(record.path):
            self._revoke_workspace(record, "cleanup_refused")
            return self._cleanup_outcome(
                "cleanup_refused",
                record,
                "The workspace path is symlinked or has a symlinked ancestor; no files were deleted.",
                EvidenceDisposition(False, "cleanup_refused", "revoked"),
            )

        if record.cleanup_state == "cleanup_succeeded":
            if record.path.exists():
                return self._cleanup_outcome(
                    "cleanup_refused",
                    record,
                    "The previously removed workspace path unexpectedly exists and was not deleted.",
                    EvidenceDisposition(False, "cleanup_refused", "revoked"),
                )
            return self._cleanup_outcome(
                "cleanup_already_absent",
                record,
                "The validated workspace is already absent; same-task evidence remains revoked.",
                EvidenceDisposition(False, "cleanup_already_absent", "revoked"),
            )

        if not record.path.exists():
            try:
                directory_stat = (
                    os.fstat(record.directory_fd)
                    if record.directory_fd is not None
                    else None
                )
            except OSError:
                directory_stat = None
            if directory_stat is not None and directory_stat.st_nlink >= 2:
                self._revoke_workspace(record, "cleanup_refused")
                return self._cleanup_outcome(
                    "cleanup_refused",
                    record,
                    "The workspace path is absent but its validated directory still exists elsewhere; no files were deleted.",
                    EvidenceDisposition(False, "cleanup_refused", "revoked"),
                )
            self._revoke_workspace(record, "cleanup_already_absent")
            return self._cleanup_outcome(
                "cleanup_already_absent",
                record,
                "The validated workspace is already absent; same-task evidence remains revoked.",
                EvidenceDisposition(False, "cleanup_already_absent", "revoked"),
            )

        try:
            fcntl.flock(record.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return self._cleanup_outcome(
                "cleanup_deferred",
                record,
                "The validated workspace is currently locked by another runtime; no files were deleted.",
                (
                    EvidenceDisposition(False, "cleanup_deferred", "none")
                    if record.cleanup_only
                    else EvidenceDisposition(
                        True, "cleanup_deferred", "same_task_evidence"
                    )
                ),
            )
        except (OSError, ValueError):
            self._revoke_workspace(record, "cleanup_refused")
            return self._cleanup_outcome(
                "cleanup_refused",
                record,
                "The workspace lock could not be verified; no files were deleted.",
                EvidenceDisposition(False, "cleanup_refused", "revoked"),
            )

        validation_error = self._workspace_validation_error(record)
        if validation_error is not None:
            self._revoke_workspace(record, "cleanup_refused")
            return self._cleanup_outcome(
                "cleanup_refused",
                record,
                "Workspace validation failed; no files were deleted. " + validation_error,
                EvidenceDisposition(False, "cleanup_refused", "revoked"),
            )

        workspace_fd: int | None = None
        try:
            workspace_fd = self._open_workspace_cleanup_directory(record)
            validation_error = self._workspace_validation_error_at_fd(
                record, workspace_fd
            )
            if validation_error is not None:
                self._revoke_workspace(record, "cleanup_refused")
                return self._cleanup_outcome(
                    "cleanup_refused",
                    record,
                    "Workspace validation failed after its directory was anchored; no files were deleted. "
                    + validation_error,
                    EvidenceDisposition(False, "cleanup_refused", "revoked"),
                )

            # Darwin/POSIX exposes unlink and directory removal only through a
            # live leaf name, not through an identity-bound file or directory
            # descriptor.  A same-user process can replace a validated leaf
            # between the validation above and ``unlink(name, dir_fd=...)``.
            # That could delete a user file.  Do not trade the fail-closed
            # cleanup contract for best-effort removal: retaining this fully
            # validated workspace is truthful ``cleanup_incomplete`` and
            # preserves every user path.
            self._revoke_workspace(record, "cleanup_incomplete")
            return self._cleanup_outcome(
                "cleanup_incomplete",
                record,
                "The workspace was validated, but this runtime cannot remove named files without a leaf-rebinding race; no files were deleted.",
                EvidenceDisposition(False, "cleanup_incomplete", "revoked"),
            )
        except (OSError, ValueError):
            self._revoke_workspace(record, "cleanup_refused")
            return self._cleanup_outcome(
                "cleanup_refused",
                record,
                "The workspace directory could not be anchored without following paths; no files were deleted.",
                EvidenceDisposition(False, "cleanup_refused", "revoked"),
            )
        finally:
            if workspace_fd is not None:
                try:
                    os.close(workspace_fd)
                except OSError:
                    pass

    def _cleanup_record_for_selector(self, selector: object) -> _CleanupRecordLookup:
        if selector == "current":
            if self._current_workspace_id is None:
                return _CleanupRecordLookup(None)
            return _CleanupRecordLookup(
                self._workspaces.get(self._current_workspace_id)
            )
        if not isinstance(selector, str) or not WORKSPACE_ID_PATTERN.fullmatch(selector):
            return _CleanupRecordLookup(None)
        record = self._workspaces.get(selector)
        if record is not None:
            return _CleanupRecordLookup(record)
        return self._recover_cleanup_record(selector)

    def _recover_cleanup_record(self, workspace_id: str) -> _CleanupRecordLookup:
        """Reopen one fixed-root workspace as cleanup-only state.

        A recovered record deliberately has neither a source nor an evidence
        handle.  It can validate and retain the lock long enough for the
        existing explicit-cleanup flow, but cannot become Current evidence or
        authorize acquisition/reuse in this new task session.
        """

        if self._artifact_root is not None:
            return _CleanupRecordLookup(None)

        root_fd: int | None = None
        workspace_fd: int | None = None
        lock_fd: int | None = None
        lock_file: TextIO | None = None
        try:
            root = self._workspace_root_path(recovery=True)
            if self._workspace_root_fd is None:
                raise OSError("The fixed runtime workspace root is not anchored.")
            root_fd = os.dup(self._workspace_root_fd)
            workspace_fd = os.open(
                workspace_id,
                _NOFOLLOW_DIRECTORY_FLAGS,
                dir_fd=root_fd,
            )
            workspace_stat = os.fstat(workspace_fd)
            if not stat.S_ISDIR(workspace_stat.st_mode):
                raise OSError("The recovered workspace is not a directory.")
            path = root / workspace_id
            path_identity = _stat_identity(workspace_stat)
            if (
                _has_symlink_component(path)
                or not path.is_dir()
                or _path_identity(path) != path_identity
            ):
                raise OSError("The recovered workspace path cannot be verified.")

            lock_fd = os.open(
                WORKSPACE_LOCK_NAME,
                os.O_RDWR | _NOFOLLOW_FILE_FLAGS,
                dir_fd=workspace_fd,
            )
            lock_file = os.fdopen(lock_fd, "r+", encoding="utf-8")
            lock_fd = None
            lock_bytes, lock_stat = _read_nofollow_file_at(
                workspace_fd, WORKSPACE_LOCK_NAME
            )
            held_stat = os.fstat(lock_file.fileno())
            if (
                _stat_identity(lock_stat) != _stat_identity(held_stat)
                or lock_bytes != f"{workspace_id}\n".encode("utf-8")
            ):
                raise OSError("The recovered workspace lock is invalid.")

            # A held lock wins over every mutable workspace leaf: a live
            # runtime can be between writes while holding it, including midway
            # through one append-only manifest record.  Do not parse/cache
            # that snapshot; the next explicit recovery will reopen it fresh.
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return _CleanupRecordLookup(None, workspace_id)

            marker_bytes, marker_stat = _read_nofollow_file_at(
                workspace_fd, WORKSPACE_MARKER_NAME
            )
            try:
                marker = json.loads(marker_bytes.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as error:
                raise OSError("The recovered workspace marker is unreadable.") from error
            if marker != {
                "schema": WORKSPACE_SCHEMA,
                "version": WORKSPACE_MANIFEST_VERSION,
                "workspace_id": workspace_id,
            }:
                raise OSError("The recovered workspace marker is invalid.")

            manifest_bytes, manifest_stat = _read_nofollow_file_at(
                workspace_fd, WORKSPACE_MANIFEST_NAME
            )
            try:
                artifacts = _manifest_artifacts_text(
                    manifest_bytes.decode("utf-8"), workspace_id
                )
            except UnicodeError as error:
                raise OSError("The recovered workspace manifest is unreadable.") from error
            if artifacts is None:
                raise OSError("The recovered workspace manifest is invalid.")

            record = _WorkspaceRecord(
                workspace_id=workspace_id,
                path=path,
                path_identity=path_identity,
                directory_fd=workspace_fd,
                source=None,
                controls=None,
                evidence_handle=None,
                marker_identity=_stat_identity(marker_stat),
                manifest_identity=_stat_identity(manifest_stat),
                marker_digest=_bytes_digest(marker_bytes),
                manifest_digest=_bytes_digest(manifest_bytes),
                lock_digest=_bytes_digest(lock_bytes),
                lock_file=lock_file,
                artifacts=artifacts,
                reuse_eligible=False,
                cleanup_only=True,
            )

            if self._workspace_validation_error_at_fd(record, workspace_fd) is not None:
                raise OSError("The recovered workspace failed descriptor validation.")
            if self._workspace_validation_error(record) is not None:
                raise OSError("The recovered workspace failed lexical validation.")

            self._workspaces[workspace_id] = record
            workspace_fd = None
            lock_file = None
            return _CleanupRecordLookup(record)
        except (OSError, ValueError):
            return _CleanupRecordLookup(None)
        finally:
            if lock_file is not None:
                try:
                    lock_file.close()
                except OSError:
                    pass
            elif lock_fd is not None:
                try:
                    os.close(lock_fd)
                except OSError:
                    pass
            if workspace_fd is not None:
                try:
                    os.close(workspace_fd)
                except OSError:
                    pass
            if root_fd is not None:
                try:
                    os.close(root_fd)
                except OSError:
                    pass

    def _cleanup_outcome(
        self,
        state: CleanupState,
        record: _WorkspaceRecord | None,
        message: str,
        disposition: EvidenceDisposition,
        *,
        workspace_id: str | None = None,
    ) -> CleanupOutcome:
        workspace_id = record.workspace_id if record is not None else workspace_id
        lines = [
            "# Watch workspace cleanup",
            "",
            f"- State: `{state}`",
            f"- Workspace ID: `{workspace_id}`" if workspace_id else "- Workspace ID: `none`",
            f"- Disposal state: `{disposition.disposal_state}`",
            f"- Reuse state: `{disposition.reuse_state}`",
            f"- Message: {_render_preescaped_markdown_code(message)}",
        ]
        return CleanupOutcome(
            state=state,
            workspace_id=workspace_id,
            message=message,
            disposition=disposition,
            report_markdown="\n".join(lines) + "\n",
        )

    def _workspace_root_path(self, *, recovery: bool = False) -> Path:
        """Return the anchored workspace root for live work or recovery.

        ``artifact_root`` is an in-process composition seam for hermetic tests.
        It is never a cleanup-recovery authority: only the fixed marked runtime
        root below the canonical system temporary directory can be reopened by
        a fresh runtime.
        """

        if recovery and self._artifact_root is not None:
            raise OSError(
                "Cross-session cleanup is available only for the fixed runtime root."
            )
        if self._workspace_root is not None:
            root = self._workspace_root
            if (
                _has_symlink_component(root)
                or not root.is_dir()
                or self._workspace_root_identity is None
                or self._workspace_root_fd is None
                or _path_identity(root) != self._workspace_root_identity
            ):
                raise OSError("The runtime workspace root is no longer a regular directory.")
            if self._workspace_root_is_fixed:
                marker_identity = self._workspace_root_marker_identity
                marker_digest = self._workspace_root_marker_digest
                if (
                    marker_identity is None
                    or marker_digest is None
                    or _runtime_root_marker_validation_error_at_fd(
                        self._workspace_root_fd, marker_identity, marker_digest
                    )
                    is not None
                ):
                    raise OSError("The fixed runtime workspace root marker was altered.")
            return root
        if self._artifact_root is None:
            (
                root,
                root_fd,
                root_marker_identity,
                root_marker_digest,
            ) = _open_default_runtime_root(create=not recovery)
            root_is_fixed = True
        else:
            root = _canonicalize_system_path_alias(
                self._artifact_root.expanduser()
            )
            if not root.is_absolute():
                raise OSError("The runtime workspace root is not an absolute directory.")
            root_fd = _open_nofollow_directory_path(root, create=True)
            root_marker_identity = None
            root_marker_digest = None
            root_is_fixed = False
        try:
            root_identity = _stat_identity(os.fstat(root_fd))
            if _has_symlink_component(root) or not root.is_dir():
                raise OSError("The runtime workspace root is not a regular directory.")
            if root_identity != _path_identity(root):
                raise OSError("The runtime workspace root identity changed.")
            if root_is_fixed:
                assert root_marker_identity is not None
                assert root_marker_digest is not None
                if (
                    _runtime_root_marker_validation_error_at_fd(
                        root_fd, root_marker_identity, root_marker_digest
                    )
                    is not None
                ):
                    raise OSError("The fixed runtime workspace root marker was altered.")
        except (OSError, ValueError):
            os.close(root_fd)
            raise
        self._workspace_root = root
        self._workspace_root_identity = root_identity
        self._workspace_root_fd = root_fd
        self._workspace_root_marker_identity = root_marker_identity
        self._workspace_root_marker_digest = root_marker_digest
        self._workspace_root_is_fixed = root_is_fixed
        return root

    def _open_workspace_cleanup_directory(self, record: _WorkspaceRecord) -> int:
        """Duplicate the original workspace descriptor for descriptor-bound cleanup."""

        if record.directory_fd is None:
            raise OSError("The workspace directory is no longer held by this runtime.")
        workspace_fd = os.dup(record.directory_fd)
        try:
            if _stat_identity(os.fstat(workspace_fd)) != record.path_identity:
                raise OSError("The workspace directory identity changed.")
        except (OSError, ValueError):
            os.close(workspace_fd)
            raise
        return workspace_fd

    def _run_workspace_command(
        self,
        record: _WorkspaceRecord,
        executable: str,
        arguments: Sequence[str],
        *,
        input_fd: int | None = None,
        output_fd: int | None = None,
        pending_artifact: str | None = None,
    ) -> CommandResult:
        """Run a command only after validating its retained workspace inputs."""

        if not record.reuse_eligible:
            raise OSError("The workspace is no longer eligible for command output.")
        if pending_artifact is not None and not _is_runtime_artifact_name(
            pending_artifact
        ):
            raise OSError("The requested command output is not a runtime artifact name.")
        lexical_validation_error = self._workspace_validation_error(
            record, pending_artifact=pending_artifact
        )
        if lexical_validation_error is not None:
            raise OSError(
                "The workspace cannot be used for command output. "
                + lexical_validation_error
            )
        workspace_fd = self._open_workspace_cleanup_directory(record)
        try:
            descriptor_validation_error = self._workspace_validation_error_at_fd(
                record, workspace_fd, pending_artifact=pending_artifact
            )
            if descriptor_validation_error is not None:
                raise OSError(
                    "The workspace cannot be used for command output. "
                    + descriptor_validation_error
                )
            return self._command_runner.run(
                executable,
                arguments,
                input_fd=input_fd,
                output_fd=output_fd,
            )
        finally:
            os.close(workspace_fd)

    def _run_visual_media_command(
        self,
        media: _VisualMedia,
        executable: str,
        arguments: Sequence[str],
        *,
        workspace: _WorkspaceRecord | None = None,
        output_fd: int | None = None,
        pending_artifact: str | None = None,
    ) -> CommandResult:
        if media.workspace is None:
            if workspace is not None:
                return self._run_workspace_command(
                    workspace,
                    executable,
                    arguments,
                    output_fd=output_fd,
                    pending_artifact=pending_artifact,
                )
            return self._command_runner.run(
                executable, arguments, output_fd=output_fd
            )
        input_fd = self._open_verified_workspace_artifact_input(
            media.workspace, media.argument
        )
        try:
            input_argument = f"/dev/fd/{input_fd}"
            return self._run_workspace_command(
                media.workspace,
                executable,
                [
                    input_argument if argument == media.argument else argument
                    for argument in arguments
                ],
                input_fd=input_fd,
                output_fd=output_fd,
                pending_artifact=pending_artifact,
            )
        finally:
            os.close(input_fd)

    def _workspace_validation_error_at_fd(
        self,
        record: _WorkspaceRecord,
        workspace_fd: int,
        pending_artifact: str | None = None,
    ) -> str | None:
        """Validate a workspace from its anchored directory descriptor."""

        allow_incomplete = record.cleanup_state == "cleanup_incomplete"
        expected_names = set(record.artifacts) - record.deleted_artifacts
        if pending_artifact is not None:
            expected_names.add(pending_artifact)
        expected_controls = set(WORKSPACE_CONTROL_NAMES) - record.deleted_controls
        try:
            observed_names = set(os.listdir(workspace_fd))
        except OSError:
            return "The workspace contents cannot be enumerated safely."
        if observed_names != expected_names | expected_controls:
            return "The workspace has unknown, missing, or altered entries."
        if pending_artifact is not None:
            try:
                pending_stat = os.stat(
                    pending_artifact,
                    dir_fd=workspace_fd,
                    follow_symlinks=False,
                )
            except OSError:
                return "The pending runtime artifact is missing or symlinked."
            if not stat.S_ISREG(pending_stat.st_mode) or pending_stat.st_nlink != 1:
                return "The pending runtime artifact is not a regular file."

        if WORKSPACE_MARKER_NAME in expected_controls:
            try:
                marker_bytes, marker_stat = _read_nofollow_file_at(
                    workspace_fd, WORKSPACE_MARKER_NAME
                )
                marker = json.loads(marker_bytes.decode("utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                return "The workspace ownership marker cannot be validated."
            if marker != {
                "schema": WORKSPACE_SCHEMA,
                "version": WORKSPACE_MANIFEST_VERSION,
                "workspace_id": record.workspace_id,
            } or (
                _stat_identity(marker_stat) != record.marker_identity
                or _bytes_digest(marker_bytes) != record.marker_digest
                or marker_stat.st_nlink != 1
            ):
                return "The workspace ownership marker was altered."
        elif not allow_incomplete:
            return "The workspace ownership marker is missing."

        if WORKSPACE_MANIFEST_NAME in expected_controls:
            try:
                manifest_bytes, manifest_stat = _read_nofollow_file_at(
                    workspace_fd, WORKSPACE_MANIFEST_NAME
                )
                manifest_entries = _manifest_artifacts_text(
                    manifest_bytes.decode("utf-8"), record.workspace_id
                )
            except (OSError, UnicodeError):
                return "The append-only workspace manifest cannot be validated."
            if (
                _stat_identity(manifest_stat) != record.manifest_identity
                or _bytes_digest(manifest_bytes) != record.manifest_digest
                or manifest_entries != record.artifacts
                or manifest_stat.st_nlink != 1
            ):
                return "The append-only workspace manifest is invalid or unverified."
        elif not allow_incomplete:
            return "The workspace manifest is missing."

        if WORKSPACE_LOCK_NAME in expected_controls:
            if record.lock_file.closed:
                return "The workspace lock is not held by this runtime."
            try:
                lock_bytes, lock_stat = _read_nofollow_file_at(
                    workspace_fd, WORKSPACE_LOCK_NAME
                )
                held_stat = os.fstat(record.lock_file.fileno())
            except (OSError, ValueError):
                return "The workspace lock is not held by this runtime."
            if (
                _stat_identity(lock_stat) != _stat_identity(held_stat)
                or _bytes_digest(lock_bytes) != record.lock_digest
                or lock_bytes != f"{record.workspace_id}\n".encode("utf-8")
                or lock_stat.st_nlink != 1
            ):
                return "The workspace lock was altered or is not held."
        elif not allow_incomplete:
            return "The workspace lock is missing."

        for artifact_name, artifact in record.artifacts.items():
            if artifact_name in record.deleted_artifacts:
                continue
            try:
                artifact_digest, artifact_stat = _digest_nofollow_file_at(
                    workspace_fd, artifact_name
                )
            except OSError:
                return "A manifest-listed artifact is missing or symlinked."
            if (
                artifact_stat.st_size != artifact.size_bytes
                or artifact_digest != artifact.sha256
                or artifact_stat.st_nlink != 1
            ):
                return "A manifest-listed artifact was altered."
        return None

    def _create_workspace(
        self, source: Source, controls: WatchControls
    ) -> tuple[_WorkspaceRecord | None, Failure | None]:
        workspace_path: Path | None = None
        lock_file: TextIO | None = None
        lock_fd: int | None = None
        root_fd: int | None = None
        workspace_fd: int | None = None
        record: _WorkspaceRecord | None = None
        created_workspace_identity: tuple[int, int] | None = None
        try:
            root = self._workspace_root_path()
            if self._workspace_root_fd is None:
                raise OSError("The runtime workspace root is no longer held by this runtime.")
            root_fd = os.dup(self._workspace_root_fd)
            workspace_id = _new_workspace_id()
            for _ in range(8):
                workspace_path = root / workspace_id
                try:
                    os.mkdir(workspace_id, mode=0o700, dir_fd=root_fd)
                    created_workspace_identity = _stat_identity(
                        os.stat(workspace_id, dir_fd=root_fd, follow_symlinks=False)
                    )
                    break
                except FileExistsError:
                    workspace_id = _new_workspace_id()
            else:
                raise OSError("Could not allocate a unique runtime workspace ID.")

            assert workspace_path is not None
            assert created_workspace_identity is not None
            workspace_fd = os.open(
                workspace_id,
                _NOFOLLOW_DIRECTORY_FLAGS,
                dir_fd=root_fd,
            )
            workspace_identity = _stat_identity(os.fstat(workspace_fd))
            if workspace_identity != created_workspace_identity:
                raise OSError(
                    "The newly created runtime workspace changed before it could be anchored."
                )
            marker = {
                "schema": WORKSPACE_SCHEMA,
                "version": WORKSPACE_MANIFEST_VERSION,
                "workspace_id": workspace_id,
            }
            manifest_header = {
                "record": "header",
                "schema": WORKSPACE_SCHEMA,
                "version": WORKSPACE_MANIFEST_VERSION,
                "workspace_id": workspace_id,
            }
            marker_bytes = _json_line_bytes(marker)
            manifest_bytes = _json_line_bytes(manifest_header)
            lock_bytes = f"{workspace_id}\n".encode("utf-8")
            marker_stat = _write_new_bytes_at(
                workspace_fd, WORKSPACE_MARKER_NAME, marker_bytes
            )
            manifest_stat = _write_new_json_line_at(
                workspace_fd, WORKSPACE_MANIFEST_NAME, manifest_header
            )
            lock_stat = _write_new_bytes_at(
                workspace_fd, WORKSPACE_LOCK_NAME, lock_bytes
            )
            lock_fd = os.open(
                WORKSPACE_LOCK_NAME,
                os.O_RDWR | _NOFOLLOW_FILE_FLAGS,
                dir_fd=workspace_fd,
            )
            held_lock_stat = os.fstat(lock_fd)
            if _stat_identity(held_lock_stat) != _stat_identity(lock_stat):
                os.close(lock_fd)
                lock_fd = None
                raise OSError("The workspace lock changed during creation.")
            lock_file = os.fdopen(lock_fd, "r+", encoding="utf-8")
            lock_fd = None
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            record = _WorkspaceRecord(
                workspace_id=workspace_id,
                path=workspace_path,
                path_identity=workspace_identity,
                directory_fd=workspace_fd,
                source=source,
                controls=controls,
                evidence_handle=_new_evidence_handle(),
                marker_identity=_stat_identity(marker_stat),
                manifest_identity=_stat_identity(manifest_stat),
                marker_digest=_bytes_digest(marker_bytes),
                manifest_digest=_bytes_digest(manifest_bytes),
                lock_digest=_bytes_digest(lock_bytes),
                lock_file=lock_file,
                artifacts={},
            )
        except (OSError, RuntimeError, ValueError) as error:
            if lock_file is not None:
                try:
                    lock_file.close()
                except OSError:
                    pass
            elif lock_fd is not None:
                try:
                    os.close(lock_fd)
                except OSError:
                    pass
            return None, Failure(
                stage="workspace",
                category="workspace_creation",
                message=(
                    "A runtime-owned Watch workspace could not be created safely. "
                    f"Diagnostic: {_escape_control_sequences(str(error))}"
                ),
                attempts=1,
                disposition=CURRENT_SOURCE_NO_WORKSPACE,
            )
        finally:
            if workspace_fd is not None:
                if record is None:
                    try:
                        os.close(workspace_fd)
                    except OSError:
                        pass
                # The successful record owns this descriptor until close(); it
                # makes future cleanup independent of later name replacement.
                workspace_fd = None
            if root_fd is not None:
                try:
                    os.close(root_fd)
                except OSError:
                    pass

        self._workspaces[record.workspace_id] = record
        assert record.evidence_handle is not None
        self._evidence_handles[record.evidence_handle] = record
        self._current_workspace_id = record.workspace_id
        return record, None

    def _record_workspace_artifact(
        self, record: _WorkspaceRecord, artifact_path: Path, kind: str
    ) -> None:
        try:
            relative = artifact_path.relative_to(record.path)
        except ValueError as error:
            raise OSError("A runtime artifact was outside its workspace.") from error
        if len(relative.parts) != 1:
            raise OSError("A runtime artifact path is not a regular workspace file.")
        self._record_workspace_artifact_name(record, relative.name, kind)

    def _record_workspace_artifact_name(
        self, record: _WorkspaceRecord, artifact_name: str, kind: str
    ) -> None:
        if not _is_runtime_artifact_name(artifact_name):
            raise OSError("A runtime artifact path is not a regular workspace file.")
        workspace_fd = self._open_workspace_cleanup_directory(record)
        try:
            self._record_workspace_artifact_name_at_fd(
                record, artifact_name, kind, workspace_fd
            )
        finally:
            os.close(workspace_fd)

    def _create_workspace_artifact_output(
        self, record: _WorkspaceRecord, artifact_name: str
    ) -> int:
        """Reserve one no-follow output leaf before an adapter can write bytes."""

        if not _is_runtime_artifact_name(artifact_name):
            raise OSError("A runtime artifact path is not a regular workspace file.")
        if artifact_name in record.artifacts:
            raise OSError("A runtime artifact would overwrite an existing manifest entry.")
        lexical_validation_error = self._workspace_validation_error(record)
        if lexical_validation_error is not None:
            raise OSError("The workspace cannot create an artifact. " + lexical_validation_error)
        workspace_fd = self._open_workspace_cleanup_directory(record)
        try:
            descriptor_validation_error = self._workspace_validation_error_at_fd(
                record, workspace_fd
            )
            if descriptor_validation_error is not None:
                raise OSError(
                    "The workspace cannot create an artifact. "
                    + descriptor_validation_error
                )
            output_fd = os.open(
                artifact_name,
                os.O_RDWR
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                0o600,
                dir_fd=workspace_fd,
            )
            try:
                output_stat = os.fstat(output_fd)
                if not stat.S_ISREG(output_stat.st_mode) or output_stat.st_nlink != 1:
                    raise OSError("The runtime artifact output is not a regular file.")
                return output_fd
            except (OSError, ValueError):
                os.close(output_fd)
                raise
        finally:
            os.close(workspace_fd)

    def _finalize_workspace_artifact_output(
        self,
        record: _WorkspaceRecord,
        artifact_name: str,
        kind: str,
        output_fd: int,
    ) -> None:
        """Append a manifest entry only for the still-bound preopened output.

        The producer receives an already-open descriptor, so it cannot select a
        workspace leaf by pathname.  Before accepting those bytes as evidence,
        re-open the leaf without following links and require it to be the same
        inode as the original descriptor.  Any replacement makes the workspace
        unverified rather than silently accepting attacker-controlled bytes.
        """

        if not _is_runtime_artifact_name(artifact_name):
            raise OSError("A runtime artifact path is not a regular workspace file.")
        if artifact_name in record.artifacts:
            raise OSError("A runtime artifact would overwrite an existing manifest entry.")
        try:
            os.fsync(output_fd)
            output_stat = os.fstat(output_fd)
            if not stat.S_ISREG(output_stat.st_mode) or output_stat.st_nlink != 1:
                raise OSError("The runtime artifact output is not a regular file.")
            output_digest = _digest_open_file_descriptor(output_fd)
        except (OSError, ValueError):
            raise OSError("The runtime artifact output could not be verified.") from None

        entry = _ManifestArtifact(
            path=artifact_name,
            kind=kind,
            disposition="retained",
            size_bytes=output_stat.st_size,
            sha256=output_digest,
        )
        workspace_fd = self._open_workspace_cleanup_directory(record)
        try:
            validation_error = self._workspace_validation_error_at_fd(
                record, workspace_fd, pending_artifact=artifact_name
            )
            if validation_error is not None:
                raise OSError(
                    "The workspace changed before its artifact could be recorded. "
                    + validation_error
                )
            live_fd = os.open(
                artifact_name, _NOFOLLOW_FILE_FLAGS, dir_fd=workspace_fd
            )
            try:
                live_stat = os.fstat(live_fd)
                if (
                    not stat.S_ISREG(live_stat.st_mode)
                    or live_stat.st_nlink != 1
                    or _stat_identity(live_stat) != _stat_identity(output_stat)
                    or _digest_open_file_descriptor(live_fd) != output_digest
                ):
                    raise OSError("The preopened runtime artifact was replaced.")
            finally:
                os.close(live_fd)
            self._append_workspace_artifact_entry_at_fd(
                record, entry, workspace_fd, pending_artifact=artifact_name
            )
            validation_error = self._workspace_validation_error_at_fd(
                record, workspace_fd
            )
            if validation_error is not None:
                raise OSError(
                    "The workspace changed after its artifact was recorded. "
                    + validation_error
                )
            lexical_validation_error = self._workspace_validation_error(record)
            if lexical_validation_error is not None:
                raise OSError(
                    "The workspace changed after its artifact was recorded. "
                    + lexical_validation_error
                )
        finally:
            os.close(workspace_fd)

    def _retain_failed_workspace_artifact_output(
        self,
        record: _WorkspaceRecord,
        artifact_name: str,
        kind: str,
        output_fd: int | None,
    ) -> None:
        """Make a safely reserved failed producer output an explicit manifest leaf.

        A command can fail after the runtime has reserved its output file.  It
        is still runtime-owned only if its descriptor and directory can be
        verified, so retain it for explicit cleanup rather than deleting a
        name that may have changed.  A verification failure is deliberately
        left for the caller's normal fail-closed workspace revocation.
        """

        if output_fd is None or artifact_name in record.artifacts:
            return
        try:
            self._finalize_workspace_artifact_output(
                record, artifact_name, kind, output_fd
            )
        except (OSError, ValueError):
            return

    def _open_verified_workspace_artifact_input(
        self, record: _WorkspaceRecord, artifact_name: str
    ) -> int:
        """Open a manifest artifact by descriptor, pinning its verified bytes."""

        artifact = record.artifacts.get(artifact_name)
        if artifact is None or artifact_name in record.deleted_artifacts:
            raise OSError("The requested workspace input was not retained as evidence.")
        workspace_fd = self._open_workspace_cleanup_directory(record)
        try:
            input_fd = os.open(
                artifact_name, _NOFOLLOW_FILE_FLAGS, dir_fd=workspace_fd
            )
            try:
                input_stat = os.fstat(input_fd)
                if not stat.S_ISREG(input_stat.st_mode):
                    raise OSError("The requested workspace input is not a regular file.")
                if input_stat.st_nlink != 1:
                    raise OSError("The requested workspace input has unexpected links.")
                input_digest = _digest_open_file_descriptor(input_fd)
                if (
                    input_stat.st_size != artifact.size_bytes
                    or input_digest != artifact.sha256
                ):
                    raise OSError("The requested workspace input was altered.")
                os.lseek(input_fd, 0, os.SEEK_SET)
                return input_fd
            except (OSError, ValueError):
                os.close(input_fd)
                raise
        finally:
            os.close(workspace_fd)

    def _record_workspace_artifact_name_at_fd(
        self,
        record: _WorkspaceRecord,
        artifact_name: str,
        kind: str,
        workspace_fd: int,
    ) -> None:
        if not _is_runtime_artifact_name(artifact_name):
            raise OSError("A runtime artifact path is not a regular workspace file.")
        try:
            artifact_digest, artifact_stat = _digest_nofollow_file_at(
                workspace_fd, artifact_name
            )
        except OSError as error:
            raise OSError("A runtime artifact is missing or symlinked.") from error
        entry = _ManifestArtifact(
            path=artifact_name,
            kind=kind,
            disposition="retained",
            size_bytes=artifact_stat.st_size,
            sha256=artifact_digest,
        )
        self._append_workspace_artifact_entry_at_fd(
            record, entry, workspace_fd, pending_artifact=artifact_name
        )

    def _append_workspace_artifact_entry_at_fd(
        self,
        record: _WorkspaceRecord,
        entry: _ManifestArtifact,
        workspace_fd: int,
        *,
        pending_artifact: str,
    ) -> None:
        existing = record.artifacts.get(entry.path)
        if existing is not None:
            if existing != entry:
                raise OSError("A runtime artifact would overwrite an existing manifest entry.")
            return
        if (
            self._workspace_validation_error_at_fd(
                record, workspace_fd, pending_artifact=pending_artifact
            )
            is not None
        ):
            raise OSError("The workspace changed before its artifact could be recorded.")
        payload = {
            "record": "artifact",
            "path": entry.path,
            "kind": entry.kind,
            "disposition": entry.disposition,
            "size_bytes": entry.size_bytes,
            "sha256": entry.sha256,
        }
        manifest_stat, manifest_digest = _append_json_line_at(
            workspace_fd, WORKSPACE_MANIFEST_NAME, payload
        )
        record.artifacts[entry.path] = entry
        record.manifest_identity = _stat_identity(manifest_stat)
        record.manifest_digest = manifest_digest

    def _read_verified_workspace_artifact(
        self, record: _WorkspaceRecord, artifact_name: str
    ) -> bytes:
        """Read one manifest-recorded artifact through the held workspace FD."""

        artifact = record.artifacts.get(artifact_name)
        if artifact is None:
            raise OSError("The runtime artifact was not recorded in the workspace manifest.")
        workspace_fd = self._open_workspace_cleanup_directory(record)
        try:
            artifact_bytes, artifact_stat = _read_nofollow_file_at(
                workspace_fd, artifact_name
            )
            if (
                artifact_stat.st_size != artifact.size_bytes
                or _bytes_digest(artifact_bytes) != artifact.sha256
            ):
                raise OSError("The runtime artifact changed after it was recorded.")
            validation_error = self._workspace_validation_error_at_fd(record, workspace_fd)
            if validation_error is not None:
                raise OSError("The workspace changed after command output. " + validation_error)
            return artifact_bytes
        finally:
            os.close(workspace_fd)

    def _workspace_artifact_display_path(
        self, record: _WorkspaceRecord, artifact_name: str
    ) -> Path:
        """Return a host-facing path only while the lexical workspace is intact."""

        if not _is_runtime_artifact_name(artifact_name):
            raise OSError("The runtime artifact name is unsafe for host inspection.")
        validation_error = self._workspace_validation_error(record)
        if validation_error is not None:
            raise OSError(
                "The workspace cannot be exposed for host inspection. "
                + validation_error
            )
        artifact_path = record.path / artifact_name
        if not _is_regular_nonsymlink_file(artifact_path):
            raise OSError("The runtime artifact is not a regular file for host inspection.")
        return artifact_path

    def _workspace_validation_error(
        self, record: _WorkspaceRecord, pending_artifact: str | None = None
    ) -> str | None:
        path = record.path
        if _has_symlink_component(path) or not path.is_dir():
            return "The workspace is missing, symlinked, or not a directory."
        try:
            root = self._workspace_root_path()
        except OSError:
            return "The runtime workspace root can no longer be verified."
        try:
            path_identity = _path_identity(path)
        except OSError:
            return "The workspace identity cannot be verified."
        if (
            path.parent != root
            or not WORKSPACE_ID_PATTERN.fullmatch(record.workspace_id)
            or path_identity != record.path_identity
        ):
            return "The workspace is not a direct child with an opaque runtime ID."

        allow_incomplete = record.cleanup_state == "cleanup_incomplete"
        expected_names = set(record.artifacts) - record.deleted_artifacts
        if pending_artifact is not None:
            expected_names.add(pending_artifact)
        expected_controls = set(WORKSPACE_CONTROL_NAMES) - record.deleted_controls
        try:
            observed_names = {entry.name for entry in path.iterdir()}
        except OSError:
            return "The workspace contents cannot be enumerated safely."
        if observed_names != expected_names | expected_controls:
            return "The workspace has unknown, missing, or altered entries."
        if pending_artifact is not None:
            pending_path = path / pending_artifact
            if (
                not _is_regular_nonsymlink_file(pending_path)
                or pending_path.stat().st_nlink != 1
            ):
                return "The pending runtime artifact is missing or symlinked."

        marker_path = path / WORKSPACE_MARKER_NAME
        manifest_path = path / WORKSPACE_MANIFEST_NAME
        lock_path = path / WORKSPACE_LOCK_NAME
        if WORKSPACE_MARKER_NAME in expected_controls:
            if not _is_regular_nonsymlink_file(marker_path):
                return "The workspace ownership marker is not a regular file."
            try:
                marker = json.loads(marker_path.read_text(encoding="utf-8"))
                marker_digest = _file_digest(marker_path)
                marker_identity = _path_identity(marker_path)
            except (OSError, UnicodeError, json.JSONDecodeError):
                return "The workspace ownership marker cannot be validated."
            if marker != {
                "schema": WORKSPACE_SCHEMA,
                "version": WORKSPACE_MANIFEST_VERSION,
                "workspace_id": record.workspace_id,
            } or (
                marker_identity != record.marker_identity
                or marker_digest != record.marker_digest
                or marker_path.stat().st_nlink != 1
            ):
                return "The workspace ownership marker was altered."
        elif not allow_incomplete:
            return "The workspace ownership marker is missing."

        if WORKSPACE_MANIFEST_NAME in expected_controls:
            if not _is_regular_nonsymlink_file(manifest_path):
                return "The workspace manifest is not a regular file."
            try:
                manifest_digest = _file_digest(manifest_path)
                manifest_identity = _path_identity(manifest_path)
            except OSError:
                return "The append-only workspace manifest cannot be validated."
            if (
                manifest_identity != record.manifest_identity
                or manifest_digest != record.manifest_digest
                or manifest_path.stat().st_nlink != 1
            ):
                return "The append-only workspace manifest was altered."
            entries = _manifest_artifacts(
                manifest_path, record.workspace_id
            )
            if entries is None or entries != record.artifacts:
                return "The append-only workspace manifest is invalid or unverified."
        elif not allow_incomplete:
            return "The workspace manifest is missing."

        if WORKSPACE_LOCK_NAME in expected_controls:
            if not _is_regular_nonsymlink_file(lock_path):
                return "The workspace lock is not a regular file."
            try:
                lock_stat = lock_path.stat()
                held_stat = os.fstat(record.lock_file.fileno())
                lock_digest = _file_digest(lock_path)
                lock_contents = lock_path.read_text(encoding="utf-8")
            except (OSError, ValueError):
                return "The workspace lock is not held by this runtime."
            if (
                record.lock_file.closed
                or lock_stat.st_ino != held_stat.st_ino
                or lock_stat.st_dev != held_stat.st_dev
                or lock_digest != record.lock_digest
                or lock_contents != f"{record.workspace_id}\n"
                or lock_stat.st_nlink != 1
            ):
                return "The workspace lock was altered or is not held."
        elif not allow_incomplete:
            return "The workspace lock is missing."

        for artifact_name, artifact in record.artifacts.items():
            if artifact_name in record.deleted_artifacts:
                continue
            artifact_path = path / artifact_name
            if not _is_regular_nonsymlink_file(artifact_path):
                return "A manifest-listed artifact is missing or symlinked."
            try:
                size_bytes = artifact_path.stat().st_size
                digest = _file_digest(artifact_path)
            except OSError:
                return "A manifest-listed artifact cannot be verified."
            if (
                size_bytes != artifact.size_bytes
                or digest != artifact.sha256
                or artifact_path.stat().st_nlink != 1
            ):
                return "A manifest-listed artifact was altered."
        return None

    def _attach_workspace_outcome(
        self,
        record: _WorkspaceRecord,
        outcome: EvidenceOutcome,
        *,
        store: bool,
    ) -> EvidenceOutcome:
        validation_error = self._workspace_validation_error(record)
        if validation_error is None:
            if (
                self._reuse_enabled
                and not record.cleanup_only
                and record.evidence_handle is not None
            ):
                disposition = EvidenceDisposition(
                    True, "retained", "same_task_evidence"
                )
                evidence_handle = record.evidence_handle
                integrity_line: tuple[str, ...] = ()
            else:
                disposition = EvidenceDisposition(False, "retained", "none")
                evidence_handle = None
                integrity_line = (
                    "- Workspace reuse: `unavailable after this one-shot runtime exits`",
                )
        else:
            self._revoke_workspace(record, "cleanup_refused")
            disposition = EvidenceDisposition(False, "cleanup_refused", "revoked")
            evidence_handle = None
            integrity_line = (
                "- Workspace integrity: `unverified; same-task reuse is unavailable`",
            )
        report = outcome.report_markdown.rstrip("\n") + "\n\n" + "\n".join(
            (
                "## Workspace retention",
                f"- Workspace ID: `{record.workspace_id}`",
                f"- Disposal state: `{disposition.disposal_state}`",
                f"- Reuse state: `{disposition.reuse_state}`",
                *integrity_line,
            )
        ) + "\n"
        retained = replace(
            outcome,
            report_markdown=report,
            workspace_id=record.workspace_id,
            evidence_handle=evidence_handle,
            disposition=disposition,
        )
        if store:
            record.outcome = retained
            if retained.controls is not None:
                record.controls = retained.controls
        return retained

    def _revoke_workspace(self, record: _WorkspaceRecord, state: CleanupState) -> None:
        record.reuse_eligible = False
        record.cleanup_state = state
        if record.evidence_handle is not None:
            self._evidence_handles.pop(record.evidence_handle, None)
            self._retired_evidence_handles[record.evidence_handle] = record
        if self._current_workspace_id == record.workspace_id:
            self._current_workspace_id = None

    def _reuse_outcome(
        self,
        source: Source,
        controls: WatchControls,
        watch_request: Mapping[str, object],
        prior_evidence: object | None,
    ) -> tuple[EvidenceOutcome | None, Failure | None, _WorkspaceRecord | None]:
        has_handle, handle = _evidence_handle_from_prior(prior_evidence)
        if not has_handle:
            return None, None, None
        if not self._reuse_enabled:
            return (
                None,
                _reuse_failure(
                    "invalid_evidence_handle",
                    "This one-shot runtime does not retain a same-task evidence handle.",
                    NO_EVIDENCE_NO_WORKSPACE,
                ),
                None,
            )
        if handle is None:
            return (
                None,
                _reuse_failure(
                    "invalid_evidence_handle",
                    "The supplied evidence handle is not a valid same-task opaque handle.",
                    NO_EVIDENCE_NO_WORKSPACE,
                ),
                None,
            )
        record = self._evidence_handles.get(handle)
        if record is None:
            retired = self._retired_evidence_handles.get(handle)
            if retired is not None:
                return (
                    None,
                    _reuse_failure(
                        "evidence_disposed",
                        "The prior same-task evidence was disposed or made ineligible and cannot be reused.",
                        EvidenceDisposition(
                            False,
                            retired.cleanup_state or "cleanup_refused",
                            "revoked",
                        ),
                    ),
                    retired,
                )
            return (
                None,
                _reuse_failure(
                    "invalid_evidence_handle",
                    "The supplied evidence handle is unknown, stale, or belongs to another task.",
                    NO_EVIDENCE_NO_WORKSPACE,
                ),
                None,
            )
        if (
            record.cleanup_only
            or record.source is None
            or record.controls is None
            or record.evidence_handle is None
        ):
            self._revoke_workspace(record, "cleanup_refused")
            return (
                None,
                _reuse_failure(
                    "invalid_evidence_handle",
                    "The supplied evidence handle is not eligible for same-task reuse.",
                    EvidenceDisposition(False, "cleanup_refused", "revoked"),
                ),
                record,
            )
        if record.source.kind != source.kind or record.source.value != source.value:
            return (
                None,
                _reuse_failure(
                    "invalid_evidence_handle",
                    "The supplied evidence handle does not match this Current source.",
                    EvidenceDisposition(True, "retained", "same_task_evidence"),
                ),
                record,
            )
        if not _reuse_controls_match(record.controls, controls, watch_request):
            return (
                None,
                _reuse_failure(
                    "reuse_requires_approval",
                    "This follow-up requests evidence outside the retained same-task scope. Start a new explicit preparation instead; no media was reacquired.",
                    EvidenceDisposition(True, "retained", "same_task_evidence"),
                ),
                record,
            )
        if not record.reuse_eligible or self._workspace_validation_error(record) is not None:
            self._revoke_workspace(record, "cleanup_refused")
            return (
                None,
                _reuse_failure(
                    "evidence_disposed",
                    "The prior same-task evidence is no longer eligible for reuse; no media was reacquired.",
                    EvidenceDisposition(False, "cleanup_refused", "revoked"),
                ),
                record,
            )
        if record.outcome is None:
            self._revoke_workspace(record, "cleanup_refused")
            return (
                None,
                _reuse_failure(
                    "invalid_evidence_handle",
                    "The supplied evidence handle has no immutable same-task outcome.",
                    EvidenceDisposition(False, "cleanup_refused", "revoked"),
                ),
                record,
            )
        self._current_workspace_id = record.workspace_id
        self._current_source = record.source
        return record.outcome, None, record

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

        previous_current_source = self._current_source
        source = Source(source.kind, source.value, True)
        self._current_source = source
        same_current_source = (
            previous_current_source is not None
            and previous_current_source.kind == source.kind
            and previous_current_source.value == source.value
        )
        if not same_current_source:
            self._current_workspace_id = None

        if controls.caption_track is None:
            has_handle, _ = _evidence_handle_from_prior(prior_evidence)
            current_record = (
                self._workspaces.get(self._current_workspace_id)
                if self._current_workspace_id is not None
                else None
            )
            if same_current_source and not has_handle:
                disposition = (
                    EvidenceDisposition(True, "retained", "same_task_evidence")
                    if current_record is not None
                    and current_record.reuse_eligible
                    and not current_record.cleanup_only
                    and current_record.source is not None
                    and current_record.source.kind == source.kind
                    and current_record.source.value == source.value
                    else CURRENT_SOURCE_NO_WORKSPACE
                )
                return self._failure_outcome(
                    state="stopped",
                    source=source,
                    controls=controls,
                    failure=_reuse_failure(
                        "reuse_requires_approval",
                        "This same-task follow-up must supply its opaque evidence handle before any new acquisition; no media was reacquired.",
                        disposition,
                    ),
                    workspace=current_record,
                )

            reused_outcome, reuse_failure, reuse_record = self._reuse_outcome(
                source, controls, watch_request, prior_evidence
            )
            if reused_outcome is not None:
                return reused_outcome
            if reuse_failure is not None:
                return self._failure_outcome(
                    state="stopped",
                    source=source,
                    controls=controls,
                    failure=reuse_failure,
                    workspace=reuse_record,
                )

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
        workspace: _WorkspaceRecord | None = None
        if caption_selection is not None:
            workspace = self._workspaces.get(caption_selection.workspace_id)
            if (
                workspace is None
                or not workspace.reuse_eligible
                or self._workspace_validation_error(workspace) is not None
            ):
                if workspace is not None:
                    self._revoke_workspace(workspace, "cleanup_refused")
                return self._failure_outcome(
                    state="stopped",
                    source=source,
                    controls=controls,
                    failure=_reuse_failure(
                        "evidence_disposed",
                        "The caption-selection workspace is no longer eligible; no caption was downloaded.",
                        EvidenceDisposition(False, "cleanup_refused", "revoked"),
                    ),
                    workspace=workspace,
                )
            if workspace.outcome is not None and workspace.outcome.terminal:
                if not _reuse_controls_match(workspace.controls, controls, watch_request):
                    return self._failure_outcome(
                        state="stopped",
                        source=source,
                        controls=controls,
                        failure=_reuse_failure(
                            "reuse_requires_approval",
                            "This completed caption selection requests evidence outside its retained same-task scope. Start a new explicit preparation instead; no media was reacquired.",
                            EvidenceDisposition(
                                True, "retained", "same_task_evidence"
                            ),
                        ),
                        workspace=workspace,
                    )
                self._current_workspace_id = workspace.workspace_id
                self._current_source = workspace.source
                return workspace.outcome

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

        if workspace is None:
            workspace, workspace_failure = self._create_workspace(source, controls)
            if workspace_failure is not None:
                return self._failure_outcome(
                    state="failed",
                    source=source,
                    warnings=warnings,
                    tools=tools,
                    javascript_support=javascript_support,
                    controls=controls,
                    failure=workspace_failure,
                )
        assert workspace is not None

        if source.kind == "url":
            caption_outcome = self._url_caption_outcome(
                source=source,
                controls=controls,
                metadata_probe=metadata_result,
                selected_caption=selected_caption,
                warnings=warnings,
                tools=tools,
                javascript_support=javascript_support,
                workspace=workspace,
            )
            outcome = self._with_visual_evidence(
                caption_outcome,
                source=source,
                metadata=metadata_result.metadata,
                controls=controls,
                executable_paths=executable_paths,
                question=watch_request.get("question"),
                workspace=workspace,
            )
            return self._attach_workspace_outcome(workspace, outcome, store=True)

        if self._visual_enabled:
            visual, visual_warnings = self._prepare_visual_evidence(
                source=source,
                metadata=metadata_result.metadata,
                controls=controls,
                executable_paths=executable_paths,
                question=watch_request.get("question"),
                workspace=workspace,
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
        outcome = EvidenceOutcome(
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
        return self._attach_workspace_outcome(workspace, outcome, store=True)

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
        warnings: tuple[str, ...],
        tools: tuple[ToolStatus, ...],
        javascript_support: JavaScriptSupport,
        workspace: _WorkspaceRecord,
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
                    source,
                    decision_handle,
                    caption_choices,
                    metadata_probe,
                    workspace.workspace_id,
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

        selected_candidate = next(
            (
                candidate
                for candidate in metadata_probe.caption_candidates
                if _choice_matches_candidate(selected_caption, candidate)
            ),
            None,
        )
        if selected_candidate is None or selected_candidate.caption_url is None:
            raw_segments, caption_warnings = None, (
                "The selected native caption no longer has a verified retrieval route; transcript evidence is unavailable.",
            )
        else:
            raw_segments, caption_warnings = self._download_caption(
                selected_caption, selected_candidate.caption_url, workspace
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
        workspace_id: str,
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
                workspace_id=workspace_id,
            )

    def _download_caption(
        self,
        selected_caption: CaptionChoice,
        caption_url: str,
        workspace: _WorkspaceRecord,
    ) -> tuple[tuple[TranscriptSegment, ...] | None, tuple[str, ...]]:
        caption_name = f"caption.{selected_caption.format}"
        output_fd: int | None = None
        artifact_finalized = False
        try:
            output_fd = self._create_workspace_artifact_output(workspace, caption_name)
            self._caption_fetcher.fetch(
                caption_url, output_fd, max_bytes=MAX_CAPTION_BYTES
            )
            self._finalize_workspace_artifact_output(
                workspace, caption_name, "caption", output_fd
            )
            artifact_finalized = True
            caption_bytes = self._read_verified_workspace_artifact(
                workspace, caption_name
            )
            if len(caption_bytes) > MAX_CAPTION_BYTES:
                return None, (
                    "The selected native caption exceeds the safe parsing limit; transcript evidence is unavailable.",
                )
        except (OSError, subprocess.SubprocessError):
            if not artifact_finalized:
                self._retain_failed_workspace_artifact_output(
                    workspace, caption_name, "caption", output_fd
                )
            return None, (
                "Native caption retrieval did not produce one verified caption file; transcript evidence is unavailable.",
            )
        finally:
            if output_fd is not None:
                try:
                    os.close(output_fd)
                except OSError:
                    pass

        segments = _parse_caption(selected_caption.format, caption_bytes)
        if segments is None:
            return None, (
                "The selected native caption could not be parsed; transcript evidence is unavailable.",
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
        workspace: _WorkspaceRecord,
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
            workspace=workspace,
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
        workspace: _WorkspaceRecord,
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
            media, acquisition_warning = self._visual_media_path(
                source=source,
                yt_dlp=executable_paths.get("yt-dlp"),
                workspace=workspace,
            )
            if media is None:
                return None, (acquisition_warning,)

            source_geometry = self._source_video_geometry(ffprobe, media)
            if source_geometry is None:
                return None, (
                    "Visual evidence was not prepared because source display geometry is "
                    "unavailable; aspect-correct JPEG frames cannot be verified.",
                )

            plan, planning_warnings = self._plan_visual_frames(
                media=media,
                metadata=metadata,
                controls=controls,
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
            )
            extracted_frames, extraction_warnings = self._extract_visual_frames(
                candidates=plan.candidates,
                media=media,
                workspace=workspace,
                source_geometry=source_geometry,
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
            )
            batches = _chronological_batches(extracted_frames)
            frames, inspection_state, inspection_warnings = self._inspect_visual_frames(
                frames=extracted_frames,
                batches=batches,
                media=media,
                workspace=workspace,
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

    def _visual_media_path(
        self,
        *,
        source: Source,
        yt_dlp: str | None,
        workspace: _WorkspaceRecord,
    ) -> tuple[_VisualMedia | None, str]:
        if source.kind == "local":
            return _VisualMedia(source.value, None), ""
        if yt_dlp is None:
            return (
                None,
                "Visual evidence was not prepared because yt-dlp is unavailable for "
                "the approved public source.",
            )
        media_name = "source.media"
        output_fd: int | None = None
        artifact_finalized = False
        try:
            output_fd = self._create_workspace_artifact_output(workspace, media_name)
            result = self._run_workspace_command(
                workspace,
                yt_dlp,
                [
                    "--ignore-config",
                    "--no-plugin-dirs",
                    "--no-playlist",
                    "--no-cache-dir",
                    "--no-update",
                    "--no-remote-components",
                    "--no-warnings",
                    "--quiet",
                    "--no-progress",
                    "--no-part",
                    "--socket-timeout",
                    "15",
                    "--retries",
                    "0",
                    "--extractor-retries",
                    "0",
                    "--format",
                    "bestvideo[height<=1080]/bestvideo/best",
                    "--output",
                    "-",
                    "--",
                    source.value,
                ],
                output_fd=output_fd,
                pending_artifact=media_name,
            )
            self._finalize_workspace_artifact_output(
                workspace, media_name, "media", output_fd
            )
            artifact_finalized = True
        except (OSError, subprocess.SubprocessError):
            if not artifact_finalized:
                self._retain_failed_workspace_artifact_output(
                    workspace, media_name, "media", output_fd
                )
            return None, "Visual media acquisition produced an unverified workspace artifact."
        finally:
            if output_fd is not None:
                try:
                    os.close(output_fd)
                except OSError:
                    pass
        if result.returncode != 0:
            return (
                None,
                "Visual media acquisition failed after the approved source-host request. "
                f"Diagnostic: {_escape_control_sequences((result.stderr or result.stdout).strip())}",
            )
        return _VisualMedia(media_name, workspace), ""

    def _plan_visual_frames(
        self,
        *,
        media: _VisualMedia,
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
                    media=media,
                    scope_start=scope_start,
                    scope_end=scope_end,
                )
                (
                    useful_keyframes,
                    keyframe_deduplication,
                    keyframe_warnings,
                ) = self._prepare_ordinary_candidates(
                    candidates=keyframes,
                    media=media,
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
                            media=media,
                            ffmpeg=ffmpeg,
                            keep_duplicates=controls.keep_duplicates,
                        )
                    )
                    warnings.extend(ordinary_warnings)
                    fallback = "uniform"
            elif controls.detail == "balanced":
                scenes = self._scene_candidates(
                    ffmpeg=ffmpeg,
                    media=media,
                    scope_start=scope_start,
                    scope_end=scope_end,
                )
                (
                    useful_scenes,
                    scene_deduplication,
                    scene_warnings,
                ) = self._prepare_ordinary_candidates(
                    candidates=scenes,
                    media=media,
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
                            media=media,
                            ffmpeg=ffmpeg,
                            keep_duplicates=controls.keep_duplicates,
                        )
                    )
                    warnings.extend(ordinary_warnings)
                    fallback = "uniform"
            else:
                scenes = self._scene_candidates(
                    ffmpeg=ffmpeg,
                    media=media,
                    scope_start=scope_start,
                    scope_end=scope_end,
                )
                if scenes:
                    ordinary_candidates, deduplication, ordinary_warnings = (
                        self._prepare_ordinary_candidates(
                            candidates=scenes,
                            media=media,
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
                            media=media,
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
        media: _VisualMedia,
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
            media=media,
            ffmpeg=ffmpeg,
        )
        if dedupe_warning is not None:
            warnings.append(dedupe_warning)
        return deduplicated, state, tuple(warnings)

    def _keyframe_candidates(
        self,
        *,
        ffprobe: str,
        media: _VisualMedia,
        scope_start: float,
        scope_end: float,
    ) -> tuple[_FrameCandidate, ...]:
        result = self._run_visual_media_command(
            media,
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
                media.argument,
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
        media: _VisualMedia,
        scope_start: float,
        scope_end: float,
    ) -> tuple[_FrameCandidate, ...]:
        result = self._run_visual_media_command(
            media,
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
                media.argument,
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
        media: _VisualMedia,
        ffmpeg: str,
    ) -> tuple[tuple[_FrameCandidate, ...], DeduplicationState, str | None]:
        fingerprints: set[str] = set()
        retained: list[_FrameCandidate] = []
        for candidate in candidates:
            fingerprint = self._frame_fingerprint(ffmpeg, media, candidate.timestamp_seconds)
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
        self, ffmpeg: str, media: _VisualMedia, timestamp_seconds: float
    ) -> str | None:
        result = self._run_visual_media_command(
            media,
            ffmpeg,
            [
                "-nostdin",
                "-v",
                "error",
                "-ss",
                _format_seconds(timestamp_seconds),
                "-i",
                media.argument,
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
        media: _VisualMedia,
        workspace: _WorkspaceRecord,
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
            output_fd: int | None = None
            artifact_finalized = False
            try:
                output_fd = self._create_workspace_artifact_output(workspace, filename)
                result = self._run_visual_media_command(
                    media,
                    ffmpeg,
                    [
                        "-nostdin",
                        "-v",
                        "error",
                        "-ss",
                        _format_seconds(candidate.timestamp_seconds),
                        "-i",
                        media.argument,
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
                        "-f",
                        "image2pipe",
                        "-c:v",
                        "mjpeg",
                        "pipe:1",
                    ],
                    workspace=workspace,
                    output_fd=output_fd,
                    pending_artifact=filename,
                )
                self._finalize_workspace_artifact_output(
                    workspace, filename, "frame", output_fd
                )
                artifact_finalized = True
            except (OSError, subprocess.SubprocessError):
                if not artifact_finalized:
                    self._retain_failed_workspace_artifact_output(
                        workspace, filename, "frame", output_fd
                    )
                warnings.append(
                    "No visual frame was recorded because its workspace artifact could not be verified."
                )
                continue
            finally:
                if output_fd is not None:
                    try:
                        os.close(output_fd)
                    except OSError:
                        pass
            if result.returncode != 0:
                warnings.append(
                    "No visual frame was recorded for source time "
                    f"{_format_seconds(candidate.timestamp_seconds)} because frame extraction failed."
                )
                continue
            geometry = self._jpeg_geometry(ffprobe, filename, workspace)
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
            frame_path = self._workspace_artifact_display_path(workspace, filename)
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
        self, ffprobe: str, media: _VisualMedia
    ) -> _VideoGeometry | None:
        geometry = self._video_geometry(ffprobe, media)
        if geometry is None or geometry.display_aspect_ratio is None:
            return None
        return geometry

    def _jpeg_geometry(
        self, ffprobe: str, frame_name: str, workspace: _WorkspaceRecord
    ) -> _VideoGeometry | None:
        geometry = self._video_geometry(
            ffprobe, _VisualMedia(frame_name, workspace)
        )
        if geometry is None or geometry.codec_name not in {"mjpeg", "jpeg"}:
            return None
        return geometry

    def _video_geometry(
        self, ffprobe: str, media: _VisualMedia
    ) -> _VideoGeometry | None:
        result = self._run_visual_media_command(
            media,
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
                media.argument,
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
        media: _VisualMedia,
        workspace: _WorkspaceRecord,
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
            media=media,
            workspace=workspace,
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
        media: _VisualMedia,
        workspace: _WorkspaceRecord,
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
            detail_name = (
                f"frame-{frame.chronological_position:04d}-"
                f"{int(round(frame.timestamp_seconds * 1000)):012d}-detail.jpg"
            )
            output_fd: int | None = None
            artifact_finalized = False
            try:
                output_fd = self._create_workspace_artifact_output(workspace, detail_name)
                result = self._run_visual_media_command(
                    media,
                    ffmpeg,
                    [
                        "-nostdin",
                        "-v",
                        "error",
                        "-ss",
                        _format_seconds(frame.timestamp_seconds),
                        "-i",
                        media.argument,
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
                        "-f",
                        "image2pipe",
                        "-c:v",
                        "mjpeg",
                        "pipe:1",
                    ],
                    workspace=workspace,
                    output_fd=output_fd,
                    pending_artifact=detail_name,
                )
                self._finalize_workspace_artifact_output(
                    workspace, detail_name, "detail_frame", output_fd
                )
                artifact_finalized = True
            except (OSError, subprocess.SubprocessError):
                if not artifact_finalized:
                    self._retain_failed_workspace_artifact_output(
                        workspace, detail_name, "detail_frame", output_fd
                    )
                warnings.append(
                    "The requested higher-resolution frame could not be verified as a workspace artifact."
                )
                continue
            finally:
                if output_fd is not None:
                    try:
                        os.close(output_fd)
                    except OSError:
                        pass
            geometry = self._jpeg_geometry(ffprobe, detail_name, workspace)
            if (
                result.returncode != 0
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
            detail_path = self._workspace_artifact_display_path(workspace, detail_name)
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
        workspace: _WorkspaceRecord | None = None,
    ) -> EvidenceOutcome:
        coverage = EvidenceCoverage("none", "none", "none", "none")
        retained_handle = (
            workspace.evidence_handle
            if workspace is not None
            and failure.disposition.reuse_state == "same_task_evidence"
            and workspace.reuse_eligible
            else None
        )
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
                state,
                source,
                failure,
                warnings,
                javascript_support,
                workspace_id=workspace.workspace_id if workspace is not None else None,
            ),
            workspace_id=workspace.workspace_id if workspace is not None else None,
            evidence_handle=retained_handle,
            disposition=failure.disposition,
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
    formats_by_track: dict[tuple[str, CaptionType], dict[str, set[str]]] = {}
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
            track_formats = formats_by_track.setdefault((language, caption_type), {})
            for raw_format in raw_formats:
                if not isinstance(raw_format, Mapping):
                    continue
                extension = _caption_format(raw_format.get("ext"))
                caption_url = _caption_resource_url(raw_format.get("url"))
                if extension is None or caption_url is None:
                    continue
                track_formats.setdefault(extension, set()).add(caption_url)
    candidates: list[_CaptionCandidate] = []
    for (language, caption_type), formats in formats_by_track.items():
        if not formats:
            continue
        # A metadata response can contain several retrieval endpoints for the
        # same logical track and format.  Treating the first one as authority
        # would silently make an ambiguous network request.  Prefer a supported
        # format only when it has exactly one validated endpoint.
        retrievable_formats = {
            extension
            for extension, urls in formats.items()
            if len(urls) == 1 and extension in SUPPORTED_CAPTION_FORMATS
        }
        if retrievable_formats:
            selected_format = _preferred_caption_format(retrievable_formats)
            caption_url = next(iter(formats[selected_format]))
            usable = True
        else:
            selected_format = _preferred_caption_format(set(formats))
            caption_url = None
            usable = False
        candidates.append(
            _CaptionCandidate(
                language=language,
                caption_type=caption_type,
                format=selected_format,
                usable=usable,
                caption_url=caption_url,
            )
        )
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


def _new_workspace_id() -> str:
    return f"workspace_{secrets.token_urlsafe(24)}"


def _new_evidence_handle() -> str:
    return f"evidence_{secrets.token_urlsafe(24)}"


def _json_line_bytes(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _write_new_bytes_at(
    directory_fd: int, name: str, value: bytes
) -> os.stat_result:
    """Create one runtime control file through an anchored directory FD."""

    file_fd = os.open(
        name,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        0o600,
        dir_fd=directory_fd,
    )
    try:
        offset = 0
        while offset < len(value):
            offset += os.write(file_fd, value[offset:])
        os.fsync(file_fd)
        file_stat = os.fstat(file_fd)
        if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_nlink != 1:
            raise OSError("Expected one unlinked runtime control file.")
        return file_stat
    finally:
        os.close(file_fd)


def _write_all_bytes(file_descriptor: int, value: bytes) -> None:
    offset = 0
    while offset < len(value):
        offset += os.write(file_descriptor, value[offset:])


def _decode_command_output(value: bytes | str | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def _write_new_json_line_at(
    directory_fd: int, name: str, value: Mapping[str, object]
) -> os.stat_result:
    return _write_new_bytes_at(directory_fd, name, _json_line_bytes(value))


def _append_json_line_at(
    directory_fd: int, name: str, value: Mapping[str, object]
) -> tuple[os.stat_result, str]:
    """Append one manifest record through its validated workspace descriptor."""

    file_fd = os.open(
        name,
        os.O_RDWR | os.O_APPEND | _NOFOLLOW_FILE_FLAGS,
        dir_fd=directory_fd,
    )
    try:
        file_stat = os.fstat(file_fd)
        if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_nlink != 1:
            raise OSError("Expected a regular manifest file.")
        payload = _json_line_bytes(value)
        _write_all_bytes(file_fd, payload)
        os.fsync(file_fd)
        os.lseek(file_fd, 0, os.SEEK_SET)
        digest = hashlib.sha256()
        while True:
            chunk = os.read(file_fd, 1024 * 1024)
            if not chunk:
                return file_stat, digest.hexdigest()
            digest.update(chunk)
    finally:
        os.close(file_fd)


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        while True:
            chunk = input_file.read(1024 * 1024)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)


def _bytes_digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _stat_identity(path_stat: os.stat_result) -> tuple[int, int]:
    return path_stat.st_dev, path_stat.st_ino


def _path_identity(path: Path) -> tuple[int, int]:
    return _stat_identity(path.stat())


def _read_nofollow_file_at(directory_fd: int, name: str) -> tuple[bytes, os.stat_result]:
    """Read one regular file through a directory descriptor without links."""

    file_fd = os.open(name, _NOFOLLOW_FILE_FLAGS, dir_fd=directory_fd)
    try:
        file_stat = os.fstat(file_fd)
        if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_nlink != 1:
            raise OSError("Expected a regular file.")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(file_fd, 1024 * 1024)
            if not chunk:
                return b"".join(chunks), file_stat
            chunks.append(chunk)
    finally:
        os.close(file_fd)


def _digest_nofollow_file_at(directory_fd: int, name: str) -> tuple[str, os.stat_result]:
    """Digest one regular file through a directory descriptor without links."""

    file_fd = os.open(name, _NOFOLLOW_FILE_FLAGS, dir_fd=directory_fd)
    try:
        file_stat = os.fstat(file_fd)
        if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_nlink != 1:
            raise OSError("Expected a regular file.")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(file_fd, 1024 * 1024)
            if not chunk:
                return digest.hexdigest(), file_stat
            digest.update(chunk)
    finally:
        os.close(file_fd)


def _digest_open_file_descriptor(file_descriptor: int) -> str:
    """Digest a pinned regular file and restore its position to the beginning."""

    file_stat = os.fstat(file_descriptor)
    if not stat.S_ISREG(file_stat.st_mode):
        raise OSError("Expected a regular file.")
    os.lseek(file_descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    while True:
        chunk = os.read(file_descriptor, 1024 * 1024)
        if not chunk:
            os.lseek(file_descriptor, 0, os.SEEK_SET)
            return digest.hexdigest()
        digest.update(chunk)


def _is_runtime_artifact_name(name: str) -> bool:
    """Accept one non-control direct-child filename generated by this runtime."""

    return (
        bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,255}", name))
        and name not in WORKSPACE_CONTROL_NAMES
    )


def _canonicalize_system_path_alias(path: Path) -> Path:
    """Preserve strict checks below macOS's stable /tmp and /var aliases."""

    lexical = Path(os.path.abspath(os.fspath(path)))
    for alias_text in ("/tmp", "/var"):
        alias = Path(alias_text)
        try:
            target = Path(os.path.realpath(alias))
            is_system_alias = alias.is_symlink() and target != alias
        except OSError:
            continue
        if not is_system_alias:
            continue
        try:
            relative = lexical.relative_to(alias)
        except ValueError:
            continue
        return target / relative
    return lexical


def _runtime_root_marker_bytes() -> bytes:
    return _json_line_bytes(
        {"schema": RUNTIME_ROOT_SCHEMA, "version": RUNTIME_ROOT_VERSION}
    )


def _read_runtime_root_marker_at(
    root_fd: int,
) -> tuple[os.stat_result, str]:
    marker_bytes, marker_stat = _read_nofollow_file_at(
        root_fd, RUNTIME_ROOT_MARKER_NAME
    )
    if marker_bytes != _runtime_root_marker_bytes():
        raise OSError("The fixed runtime workspace root marker is invalid.")
    return marker_stat, _bytes_digest(marker_bytes)


def _runtime_root_marker_validation_error_at_fd(
    root_fd: int,
    marker_identity: tuple[int, int],
    marker_digest: str,
) -> str | None:
    try:
        marker_stat, observed_digest = _read_runtime_root_marker_at(root_fd)
    except OSError:
        return "The fixed runtime workspace root marker cannot be validated."
    if (
        _stat_identity(marker_stat) != marker_identity
        or observed_digest != marker_digest
        or marker_stat.st_nlink != 1
    ):
        return "The fixed runtime workspace root marker was altered."
    return None


def _open_default_runtime_root(
    *, create: bool
) -> tuple[Path, int, tuple[int, int], str]:
    """Open the one fixed, marked runtime root through no-follow descriptors.

    The fixed location gives explicit ``cleanup <workspace-id>`` a narrowly
    scoped cross-session lookup authority.  It is not a user-selected path:
    an absent or unmarked existing root is refused for recovery, and every
    workspace remains a direct child selected only by its opaque ID.
    """

    temp_root = _canonicalize_system_path_alias(Path(tempfile.gettempdir()))
    if not temp_root.is_absolute():
        raise OSError("The system temporary directory is not absolute.")
    parent_fd = _open_nofollow_directory_path(temp_root, create=False)
    root_fd: int | None = None
    try:
        created_identity: tuple[int, int] | None = None
        try:
            root_fd = os.open(
                RUNTIME_ROOT_DIRECTORY_NAME,
                _NOFOLLOW_DIRECTORY_FLAGS,
                dir_fd=parent_fd,
            )
        except FileNotFoundError:
            if not create:
                raise
            os.mkdir(RUNTIME_ROOT_DIRECTORY_NAME, mode=0o700, dir_fd=parent_fd)
            created_stat = os.stat(
                RUNTIME_ROOT_DIRECTORY_NAME,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
            if not stat.S_ISDIR(created_stat.st_mode):
                raise OSError("Created runtime workspace root is not a directory.")
            created_identity = _stat_identity(created_stat)
            root_fd = os.open(
                RUNTIME_ROOT_DIRECTORY_NAME,
                _NOFOLLOW_DIRECTORY_FLAGS,
                dir_fd=parent_fd,
            )

        root_stat = os.fstat(root_fd)
        if (
            not stat.S_ISDIR(root_stat.st_mode)
            or (
                created_identity is not None
                and _stat_identity(root_stat) != created_identity
            )
        ):
            raise OSError(
                "The fixed runtime workspace root changed before it could be anchored."
            )
        if created_identity is not None:
            marker_stat = _write_new_bytes_at(
                root_fd, RUNTIME_ROOT_MARKER_NAME, _runtime_root_marker_bytes()
            )
            marker_digest = _bytes_digest(_runtime_root_marker_bytes())
        else:
            marker_stat, marker_digest = _read_runtime_root_marker_at(root_fd)
        return (
            temp_root / RUNTIME_ROOT_DIRECTORY_NAME,
            root_fd,
            _stat_identity(marker_stat),
            marker_digest,
        )
    except (OSError, ValueError):
        if root_fd is not None:
            try:
                os.close(root_fd)
            except OSError:
                pass
        raise
    finally:
        os.close(parent_fd)


def _open_nofollow_directory_path(path: Path, *, create: bool) -> int:
    """Anchor an absolute directory by descriptor without resolving path links.

    A lexical ``Path.resolve()`` is unsafe for a workspace root: a same-user
    process can replace a checked directory with a symlink between the check
    and resolution.  Walk every component from an open descriptor for ``/``;
    each child is opened with ``O_NOFOLLOW`` relative to its already anchored
    parent.  Optional creation uses that same parent descriptor, never a
    multi-component pathname operation, and captures the new entry identity
    before opening it.  POSIX has no atomic mkdir-and-open-by-descriptor
    primitive; this detects swaps across the observable creation/binding
    boundary and later lifecycle validation remains fail-closed.
    """

    if not path.is_absolute():
        raise OSError("Expected an absolute runtime workspace root.")
    directory_fd = os.open("/", _NOFOLLOW_DIRECTORY_FLAGS)
    try:
        for component in path.parts[1:]:
            created_identity: tuple[int, int] | None = None
            try:
                child_fd = os.open(
                    component, _NOFOLLOW_DIRECTORY_FLAGS, dir_fd=directory_fd
                )
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(component, mode=0o700, dir_fd=directory_fd)
                created_stat = os.stat(
                    component, dir_fd=directory_fd, follow_symlinks=False
                )
                if not stat.S_ISDIR(created_stat.st_mode):
                    raise OSError("Created runtime workspace component is not a directory.")
                created_identity = _stat_identity(created_stat)
                child_fd = os.open(
                    component, _NOFOLLOW_DIRECTORY_FLAGS, dir_fd=directory_fd
                )
            try:
                child_stat = os.fstat(child_fd)
                if not stat.S_ISDIR(child_stat.st_mode):
                    raise OSError("Expected a regular runtime workspace directory.")
                if (
                    created_identity is not None
                    and _stat_identity(child_stat) != created_identity
                ):
                    raise OSError(
                        "A newly created runtime workspace directory changed before it could be anchored."
                    )
            except (OSError, ValueError):
                os.close(child_fd)
                raise
            os.close(directory_fd)
            directory_fd = child_fd
        return directory_fd
    except (OSError, ValueError):
        try:
            os.close(directory_fd)
        except OSError:
            pass
        raise


def _has_symlink_component(path: Path) -> bool:
    """Reject a lexical path if any existing component is a symlink.

    ``Path.resolve()`` is intentionally not used here: it would hide an ancestor
    replacement that redirects a once-owned workspace through a symlink.
    """

    lexical = Path(os.path.abspath(os.fspath(path)))
    current = Path(lexical.anchor)
    for part in lexical.parts[1:]:
        current /= part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            return False
        except OSError:
            return True
        if stat.S_ISLNK(mode):
            return True
    return False


def _is_regular_nonsymlink_file(path: Path) -> bool:
    return not path.is_symlink() and path.is_file()


def _manifest_artifacts(
    manifest_path: Path, workspace_id: str
) -> dict[str, _ManifestArtifact] | None:
    try:
        value = manifest_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    return _manifest_artifacts_text(value, workspace_id)


def _manifest_artifacts_text(
    value: str, workspace_id: str
) -> dict[str, _ManifestArtifact] | None:
    lines = value.splitlines()
    if not lines:
        return None
    try:
        header = json.loads(lines[0])
    except json.JSONDecodeError:
        return None
    if header != {
        "record": "header",
        "schema": WORKSPACE_SCHEMA,
        "version": WORKSPACE_MANIFEST_VERSION,
        "workspace_id": workspace_id,
    }:
        return None
    artifacts: dict[str, _ManifestArtifact] = {}
    for raw_line in lines[1:]:
        try:
            item = json.loads(raw_line)
        except json.JSONDecodeError:
            return None
        if not isinstance(item, Mapping) or set(item) != {
            "record",
            "path",
            "kind",
            "disposition",
            "size_bytes",
            "sha256",
        }:
            return None
        path = item.get("path")
        kind = item.get("kind")
        disposition = item.get("disposition")
        size_bytes = item.get("size_bytes")
        digest = item.get("sha256")
        if (
            item.get("record") != "artifact"
            or not isinstance(path, str)
            or not isinstance(kind, str)
            or not kind
            or disposition != "retained"
            or isinstance(size_bytes, bool)
            or not isinstance(size_bytes, int)
            or size_bytes < 0
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or Path(path).name != path
            or "/" in path
            or "\\" in path
            or path in {".", ".."}
            or path in WORKSPACE_CONTROL_NAMES
            or path in artifacts
        ):
            return None
        artifacts[path] = _ManifestArtifact(
            path, kind, "retained", size_bytes, digest
        )
    return artifacts


def _evidence_handle_from_prior(prior_evidence: object | None) -> tuple[bool, str | None]:
    if isinstance(prior_evidence, EvidenceOutcome):
        return (
            prior_evidence.evidence_handle is not None,
            prior_evidence.evidence_handle,
        )
    if isinstance(prior_evidence, Mapping):
        if "evidence_handle" not in prior_evidence:
            return False, None
        value = prior_evidence.get("evidence_handle")
    elif isinstance(prior_evidence, str):
        value = prior_evidence
    else:
        return False, None
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"evidence_[A-Za-z0-9_-]{20,}", value)
    ):
        return True, None
    return True, value


def _reuse_controls_match(
    retained: WatchControls,
    requested: WatchControls,
    raw_request: Mapping[str, object],
) -> bool:
    for request_name, attribute in (
        ("detail", "detail"),
        ("focus", "focus_start_seconds"),
        ("cues", "cues_seconds"),
        ("max_frames", "max_frames"),
        ("keep_duplicates", "keep_duplicates"),
        ("output_dir", "output_dir"),
        ("caption_track", "caption_track"),
    ):
        if request_name in raw_request and getattr(retained, attribute) != getattr(
            requested, attribute
        ):
            return False
    if "focus" in raw_request and retained.focus_end_seconds != requested.focus_end_seconds:
        return False
    return True


def _reuse_failure(
    category: FailureCategory, message: str, disposition: EvidenceDisposition
) -> Failure:
    return Failure(
        stage="reuse",
        category=category,
        message=message,
        attempts=0,
        disposition=disposition,
    )


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


def _caption_resource_url(value: object) -> str | None:
    if (
        not isinstance(value, str)
        or not value
        or any(ord(character) <= 0x20 for character in value)
    ):
        return None
    try:
        parsed = urlsplit(value)
        # Accessing ``port`` validates malformed numeric port syntax.
        _ = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.username
        or parsed.password
        or not parsed.hostname
        or _is_non_public_host(parsed.hostname)
    ):
        return None
    return value


def _validate_caption_resource_url(value: str) -> None:
    if _caption_resource_url(value) is None:
        raise OSError("The selected native caption URL is not a public HTTP(S) resource.")


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
    *,
    workspace_id: str | None = None,
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
    if workspace_id is not None:
        lines.append(f"- Workspace ID: `{workspace_id}`")
    if source is not None:
        lines.append(f"- Source: {_render_untrusted_markdown_code(source.value)}")
    if warnings:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {_render_untrusted_markdown_code(warning)}" for warning in warnings)
    return "\n".join(lines) + "\n"
