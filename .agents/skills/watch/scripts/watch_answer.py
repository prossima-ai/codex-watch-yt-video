from __future__ import annotations

from dataclasses import asdict, dataclass
import html
import json
import math
import re
from types import MappingProxyType
from typing import Any, Literal, Mapping, cast

from watch_evidence import Answerability, EvidenceCoverage, FrameSelectionReason


AnswerState = Literal["answered", "withheld", "invalid"]
EvidenceStream = Literal["metadata", "transcript", "visual"]


@dataclass(frozen=True)
class ResolvedCitation:
    claim_id: str
    stream: EvidenceStream
    label: str
    start_seconds: float | None = None
    end_seconds: float | None = None


@dataclass(frozen=True)
class AnswerProblem:
    code: str
    message: str


@dataclass(frozen=True)
class WatchAnswer:
    state: AnswerState
    answerability: Answerability
    coverage: EvidenceCoverage
    markdown: str
    citations: tuple[ResolvedCitation, ...] = ()
    limitations: tuple[str, ...] = ()
    problem: AnswerProblem | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _ResolvedClaim:
    id: str
    text: str
    citations: tuple[ResolvedCitation, ...]


@dataclass(frozen=True)
class _PreparedSelectedFrame:
    chronological_position: int
    timestamp_seconds: float | None


@dataclass(frozen=True)
class _PreparedVisualObservation:
    id: str
    description: str
    frame_position: int
    timestamp_seconds: float
    selection_reason: FrameSelectionReason


@dataclass(frozen=True)
class _PreparedVisualEvidence:
    coverage: EvidenceCoverage
    observations_by_id: Mapping[str, _PreparedVisualObservation]
    selected_frames: tuple[_PreparedSelectedFrame, ...]
    observed_positions: frozenset[int]


def compose_watch_answer(request: object) -> WatchAnswer:
    if not isinstance(request, Mapping):
        return _invalid_answer("invalid_request", "The answer request must be an object.")
    outcome = request.get("outcome")
    if not isinstance(outcome, Mapping):
        return _invalid_answer(
            "invalid_outcome", "The answer request must include one evidence outcome."
        )
    coverage = _parse_coverage(outcome.get("coverage"))
    if coverage is None:
        return _invalid_answer(
            "invalid_coverage", "The evidence outcome has invalid coverage."
        )
    outcome_state = outcome.get("state")
    if not isinstance(outcome_state, str):
        return _invalid_answer(
            "invalid_outcome_state", "The evidence outcome state is invalid.", coverage
        )
    if outcome_state not in {"ready", "partial"}:
        return _withheld_answer(outcome, coverage)
    allowed_request_fields = {
        "outcome",
        "question",
        "answerability",
        "claims",
        "visual_observations",
        "conflicts",
        "relevant_streams",
        "raw_transcript_requested",
    }
    if set(request) - allowed_request_fields:
        return _invalid_answer(
            "invalid_request_schema",
            "The answer request contains unsupported fields.",
            coverage,
        )
    question = request.get("question")
    if question is not None and not isinstance(question, str):
        return _invalid_answer(
            "invalid_question", "The optional question must be text.", coverage
        )
    answerability = request.get("answerability")
    if not isinstance(answerability, str) or answerability not in {
        "supported",
        "uncertain",
        "unsupported",
    }:
        return _invalid_answer(
            "invalid_answerability",
            "The answer plan needs a supported, uncertain, or unsupported answerability.",
            coverage,
        )
    claims = request.get("claims")
    if not isinstance(claims, list):
        return _invalid_answer(
            "invalid_claims", "The answer plan claims must be a list.", coverage
        )
    if answerability == "supported" and not claims:
        return _invalid_answer(
            "unsupported_plan",
            "A supported answer needs at least one grounded claim.",
            coverage,
        )
    visual_observations = request.get("visual_observations")
    prepared_visuals = _prepare_visual_observations(
        outcome, visual_observations, coverage
    )
    if isinstance(prepared_visuals, WatchAnswer):
        return prepared_visuals
    coverage = prepared_visuals.coverage

    resolved_claims: list[_ResolvedClaim] = []
    all_citations: list[ResolvedCitation] = []
    claim_ids: set[str] = set()
    for claim in claims:
        if not isinstance(claim, Mapping):
            return _invalid_answer("invalid_claim", "A claim must be an object.", coverage)
        if set(claim) != {"id", "text", "evidence"}:
            return _invalid_answer(
                "invalid_claim_schema",
                "A claim contains unsupported fields.",
                coverage,
            )
        claim_id = claim.get("id")
        claim_text = claim.get("text")
        references = claim.get("evidence")
        if (
            not isinstance(claim_id, str)
            or not claim_id.strip()
            or claim_id in claim_ids
            or not isinstance(claim_text, str)
            or not claim_text.strip()
            or not isinstance(references, list)
            or not references
        ):
            return _invalid_answer(
                "invalid_claim", "A claim is not a unique grounded material claim.", coverage
            )
        claim_ids.add(claim_id)
        claim_citations: list[ResolvedCitation] = []
        seen_references: set[str] = set()
        for reference in references:
            if not isinstance(reference, Mapping):
                return _invalid_answer(
                    "invalid_reference",
                    "A claim has an invalid evidence reference.",
                    coverage,
                )
            stream = reference.get("stream")
            reference_fields = {
                "metadata": {"stream", "field"},
                "transcript": {"stream", "segment"},
                "visual": {"stream", "observation"},
            }
            expected_fields = (
                reference_fields.get(stream) if isinstance(stream, str) else None
            )
            if expected_fields is None or set(reference) != expected_fields:
                return _invalid_answer(
                    "invalid_reference_schema",
                    "An evidence reference contains unsupported fields.",
                    coverage,
                )
            try:
                reference_key = json.dumps(
                    dict(reference), ensure_ascii=True, sort_keys=True, separators=(",", ":")
                )
            except (TypeError, ValueError):
                return _invalid_answer(
                    "invalid_reference",
                    "A claim has an invalid evidence reference.",
                    coverage,
                )
            if reference_key in seen_references:
                return _invalid_answer(
                    "duplicate_reference",
                    "A claim repeats the same evidence reference.",
                    coverage,
                )
            seen_references.add(reference_key)
            if stream == "transcript":
                resolved = _resolve_transcript_citation(
                    outcome, claim_id, reference, coverage
                )
            elif stream == "metadata":
                resolved = _resolve_metadata_citation(
                    outcome, claim_id, reference, coverage
                )
            elif stream == "visual":
                resolved = _resolve_visual_citation(
                    claim_id,
                    reference,
                    prepared_visuals,
                )
            else:
                resolved = _invalid_answer(
                    "invalid_reference",
                    "A claim has an invalid evidence reference.",
                    coverage,
                )
            if isinstance(resolved, WatchAnswer):
                return resolved
            citation, coverage = resolved
            claim_citations.append(citation)
            all_citations.append(citation)
        resolved_claims.append(
            _ResolvedClaim(claim_id, claim_text.strip(), tuple(claim_citations))
        )

    raw_transcript_requested = request.get("raw_transcript_requested", False)
    if not isinstance(raw_transcript_requested, bool):
        return _invalid_answer(
            "invalid_raw_transcript_request",
            "The Raw transcript request marker must be true or false.",
            coverage,
        )
    if not raw_transcript_requested and _contains_full_raw_transcript(
        outcome, resolved_claims
    ):
        return _invalid_answer(
            "raw_transcript_not_requested",
            "A normal answer must not reproduce the full Raw transcript.",
            coverage,
        )

    conflicts = request.get("conflicts", [])
    if not isinstance(conflicts, list):
        return _invalid_answer(
            "invalid_conflicts", "The answer conflicts must be a list.", coverage
        )
    resolved_by_id = {claim.id: claim for claim in resolved_claims}
    conflict_streams: list[tuple[EvidenceStream, ...]] = []
    seen_conflicts: set[frozenset[str]] = set()
    for conflict in conflicts:
        if not isinstance(conflict, Mapping):
            return _invalid_answer(
                "invalid_conflict", "A conflict must identify two claims.", coverage
            )
        left_id = conflict.get("left_claim")
        right_id = conflict.get("right_claim")
        if not isinstance(left_id, str) or not isinstance(right_id, str):
            return _invalid_answer(
                "invalid_conflict", "A conflict must identify two distinct claims.", coverage
            )
        pair = frozenset({left_id, right_id})
        if (
            left_id == right_id
            or left_id not in resolved_by_id
            or right_id not in resolved_by_id
            or len(pair) != 2
            or pair in seen_conflicts
        ):
            return _invalid_answer(
                "invalid_conflict", "A conflict must identify two distinct claims.", coverage
            )
        streams = tuple(
            dict.fromkeys(
                citation.stream
                for claim_id in (left_id, right_id)
                for citation in resolved_by_id[claim_id].citations
            )
        )
        if len(streams) < 2:
            return _invalid_answer(
                "invalid_conflict",
                "A cross-stream conflict needs evidence from distinct streams.",
                coverage,
            )
        seen_conflicts.add(pair)
        conflict_streams.append(streams)
    if conflicts and answerability != "uncertain":
        return _invalid_answer(
            "conflicting_answerability",
            "Conflicting evidence requires an uncertain answerability.",
            coverage,
        )

    requested_relevant_streams = request.get("relevant_streams")
    if (
        not isinstance(requested_relevant_streams, list)
        or not requested_relevant_streams
        or any(
            not isinstance(stream, str)
            or stream not in {"metadata", "transcript", "visual"}
            for stream in requested_relevant_streams
        )
        or len(set(requested_relevant_streams)) != len(requested_relevant_streams)
    ):
        return _invalid_answer(
            "invalid_relevant_streams",
            "Every answer must declare a nonempty unique list of relevant evidence streams.",
            coverage,
        )
    relevant_streams = set(requested_relevant_streams)
    cited_streams = {citation.stream for citation in all_citations}
    if not cited_streams.issubset(relevant_streams):
        return _invalid_answer(
            "undeclared_evidence_stream",
            "Every cited evidence stream must be declared relevant to the question.",
            coverage,
        )
    if answerability == "supported" and cited_streams != relevant_streams:
        return _invalid_answer(
            "missing_relevant_evidence",
            "A supported answer needs grounded evidence from every relevant stream.",
            coverage,
        )
    stream_coverage = {
        "metadata": coverage.metadata,
        "transcript": coverage.transcript,
        "visual": coverage.visual,
    }
    has_relevant_gap = any(
        stream_coverage[stream] != "complete" for stream in relevant_streams
    )
    if (
        answerability == "uncertain"
        and not resolved_claims
        and not conflict_streams
        and not has_relevant_gap
    ):
        return _invalid_answer(
            "unsupported_uncertainty",
            "An uncertain answer needs grounded evidence, a conflict, or a relevant coverage gap.",
            coverage,
        )

    lines = ["# Watch answer", ""]
    if answerability == "unsupported":
        lines.extend(
            ["The inspected evidence does not establish the requested conclusion.", ""]
        )
    elif answerability == "uncertain" and not conflict_streams:
        lines.extend(
            ["The inspected evidence does not establish one certain conclusion.", ""]
        )
    for claim in resolved_claims:
        labels = "; ".join(citation.label for citation in claim.citations)
        lines.append(f"- {_escape_markdown_text(claim.text)} — {labels}")
    if conflict_streams:
        if resolved_claims:
            lines.append("")
        for streams in conflict_streams:
            stream_names = " and ".join(streams)
            lines.append(f"The cited {stream_names} findings conflict.")
    if resolved_claims or conflict_streams:
        lines.append("")
    lines.extend(
        [
            f"Answerability: `{answerability}`.",
            "",
            "## Evidence coverage",
            "",
            f"- Metadata coverage: `{coverage.metadata}`",
            f"- Transcript coverage: `{coverage.transcript}`",
            f"- Visual coverage: `{coverage.visual}`",
            f"- Overall coverage: `{coverage.overall}`",
        ]
    )
    limitations = _collect_limitations(
        outcome,
        answerability,
        frozenset(relevant_streams),
        prepared_visuals,
    )
    if limitations:
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {_escape_markdown_text(limitation)}" for limitation in limitations)
    markdown = "\n".join(lines)
    return WatchAnswer(
        state="answered",
        answerability=answerability,
        coverage=coverage,
        markdown=markdown,
        citations=tuple(all_citations),
        limitations=limitations,
    )


def _contains_full_raw_transcript(
    outcome: Mapping[object, object], claims: list[_ResolvedClaim]
) -> bool:
    transcript = _transcript_from(outcome)
    segments = transcript.get("segments") if transcript is not None else None
    if not isinstance(segments, list) or not segments:
        return False
    segment_texts = [
        _normalize_prose(segment.get("text"))
        for segment in segments
        if isinstance(segment, Mapping) and isinstance(segment.get("text"), str)
    ]
    if len(segment_texts) != len(segments) or any(not text for text in segment_texts):
        return False
    answer_text = _normalize_prose(" ".join(claim.text for claim in claims))
    cursor = 0
    for segment_text in segment_texts:
        position = answer_text.find(segment_text, cursor)
        if position < 0:
            return False
        cursor = position + len(segment_text)
    return True


def _normalize_prose(value: str) -> str:
    return " ".join(value.split()).casefold()


def _withheld_answer(
    outcome: Mapping[object, object], coverage: EvidenceCoverage
) -> WatchAnswer:
    state = outcome.get("state")
    if not isinstance(state, str) or state not in {
        "decision_required",
        "consent_required",
        "stopped",
        "failed",
        "canceled",
    }:
        return _invalid_answer(
            "invalid_outcome_state", "The evidence outcome state is invalid.", coverage
        )
    lines = ["# Watch answer", ""]
    failure = outcome.get("failure")
    failure_stage = failure.get("stage") if isinstance(failure, Mapping) else None
    allowed_stages = {
        "validation",
        "preflight",
        "metadata",
        "workspace",
        "captions",
        "visual",
        "transcription_consent",
        "transcription",
        "reuse",
    }
    stage = failure_stage if failure_stage in allowed_stages else None
    if state == "canceled":
        stage_text = f" during `{stage}`" if stage is not None else ""
        lines.extend(
            [
                f"The watch request was canceled{stage_text}.",
                "No partial answer was produced.",
            ]
        )
    elif state == "decision_required":
        choice_kind = outcome.get("choice_kind")
        allowed_choices = {"caption_track", "audio_track", "transcription"}
        choice = (
            choice_kind
            if isinstance(choice_kind, str) and choice_kind in allowed_choices
            else "an evidence"
        )
        lines.append(
            f"An answer is waiting for `{choice}` selection; no conclusion was produced."
        )
    elif state == "consent_required":
        lines.append(
            "An answer is waiting for fresh transcription consent; no conclusion was produced."
        )
    else:
        stage_text = f" during `{stage}`" if stage is not None else ""
        lines.append(
            f"Evidence preparation {state}{stage_text}; no evidence conclusion was produced."
        )
        category = failure.get("category") if isinstance(failure, Mapping) else None
        attempts = failure.get("attempts") if isinstance(failure, Mapping) else None
        message = failure.get("message") if isinstance(failure, Mapping) else None
        if isinstance(category, str) and re.fullmatch(r"[a-z][a-z0-9_]*", category):
            lines.append(f"Failure category: `{category}`")
        if isinstance(attempts, int) and not isinstance(attempts, bool) and attempts >= 0:
            lines.append(f"Attempts: `{attempts}`")
        if isinstance(message, str) and message.strip():
            lines.append(f"Diagnostic: {_escape_markdown_text(message.strip())}")

    retained = outcome.get("retained_evidence") is True
    disposal_state = outcome.get("disposal_state")
    if not isinstance(disposal_state, str) or disposal_state not in {
        "not_created",
        "retained",
        "cleanup_succeeded",
        "cleanup_already_absent",
        "cleanup_deferred",
        "cleanup_refused",
        "cleanup_incomplete",
    }:
        disposal_state = "unknown"
    reuse_state = outcome.get("reuse_state")
    if not isinstance(reuse_state, str) or reuse_state not in {
        "none",
        "current_source_only",
        "same_task_evidence",
        "revoked",
    }:
        reuse_state = "unknown"
    lines.extend(
        [
            "",
            f"- Evidence retained: `{str(retained).lower()}`",
            f"- Disposal state: `{disposal_state}`",
            f"- Reuse state: `{reuse_state}`",
        ]
    )
    return WatchAnswer(
        state="withheld",
        answerability="unsupported",
        coverage=coverage,
        markdown="\n".join(lines),
    )


def _collect_limitations(
    outcome: Mapping[object, object],
    answerability: Answerability,
    relevant_streams: frozenset[EvidenceStream],
    prepared_visuals: _PreparedVisualEvidence,
) -> tuple[str, ...]:
    limitations: list[str] = []
    coverage = prepared_visuals.coverage
    transcript = _transcript_from(outcome)
    unavailable_ranges = (
        transcript.get("unavailable_ranges") if transcript is not None else None
    )
    if "transcript" in relevant_streams and isinstance(unavailable_ranges, list):
        for unavailable_range in unavailable_ranges:
            if not isinstance(unavailable_range, Mapping):
                continue
            start_seconds = _finite_seconds(unavailable_range.get("start_seconds"))
            end_seconds = _finite_seconds(unavailable_range.get("end_seconds"))
            if (
                start_seconds is not None
                and end_seconds is not None
                and end_seconds >= start_seconds
            ):
                limitations.append(
                    "Transcript evidence is unavailable at "
                    f"{_format_source_time(start_seconds)}–{_format_source_time(end_seconds)}."
                )
    if prepared_visuals.selected_frames and prepared_visuals.observed_positions:
        missing_frames = [
            frame
            for frame in prepared_visuals.selected_frames
            if frame.chronological_position not in prepared_visuals.observed_positions
        ]
        missing_times = [
            frame.timestamp_seconds
            for frame in missing_frames
            if frame.timestamp_seconds is not None
        ]
        if missing_frames:
            coverage_text = (
                "Visual observations cover "
                f"{len(prepared_visuals.observed_positions)} of "
                f"{len(prepared_visuals.selected_frames)} selected frames"
            )
            if len(missing_times) == len(missing_frames):
                time_label = "source time" if len(missing_times) == 1 else "source times"
                rendered_times = ", ".join(
                    _format_source_time(timestamp) for timestamp in missing_times
                )
                limitations.append(
                    f"{coverage_text}; unobserved selected {time_label}: {rendered_times}."
                )
            else:
                limitations.append(
                    f"{coverage_text}; one or more unobserved selected frames lack "
                    "a trustworthy source time."
                )
    if answerability in {"uncertain", "unsupported"}:
        if "transcript" in relevant_streams and coverage.transcript == "none":
            limitations.extend(
                [
                    "Transcript evidence coverage is none.",
                    "If speech is material, explicitly prepare a usable transcript before drawing a conclusion.",
                ]
            )
        if "visual" in relevant_streams and coverage.visual == "none":
            limitations.extend(
                [
                    "Visual evidence coverage is none.",
                    "If visible detail is material, explicitly prepare and inspect focused frames.",
                ]
            )
    warnings = outcome.get("warnings")
    if isinstance(warnings, list):
        limitations.extend(
            warning for warning in warnings if isinstance(warning, str) and warning.strip()
        )
    return tuple(dict.fromkeys(limitations))


def _resolve_metadata_citation(
    outcome: Mapping[object, object],
    claim_id: str,
    reference: Mapping[object, object],
    coverage: EvidenceCoverage,
) -> tuple[ResolvedCitation, EvidenceCoverage] | WatchAnswer:
    field_name = reference.get("field")
    allowed_fields = {
        "title",
        "uploader",
        "duration_seconds",
        "container",
        "size_bytes",
        "video_codec",
        "audio_codec",
        "width",
        "height",
        "is_live",
    }
    evidence = outcome.get("evidence")
    metadata = evidence.get("metadata") if isinstance(evidence, Mapping) else None
    if (
        not isinstance(field_name, str)
        or field_name not in allowed_fields
        or not isinstance(metadata, Mapping)
        or field_name not in metadata
        or metadata.get(field_name) is None
        or coverage.metadata == "none"
    ):
        return _invalid_answer(
            "invalid_metadata_reference",
            "The claim references unavailable source metadata.",
            coverage,
        )
    citation_label = (
        "source-wide (metadata; source time: not applicable; "
        f"field: {field_name})"
    )
    return (
        ResolvedCitation(
            claim_id=claim_id,
            stream="metadata",
            label=citation_label,
        ),
        coverage,
    )


def _resolve_transcript_citation(
    outcome: Mapping[object, object],
    claim_id: str,
    reference: Mapping[object, object],
    coverage: EvidenceCoverage,
) -> tuple[ResolvedCitation, EvidenceCoverage] | WatchAnswer:
    if coverage.transcript == "none":
        return _invalid_answer(
            "unavailable_transcript_stream",
            "The claim references a transcript stream with no usable coverage.",
            coverage,
        )
    segment_position = reference.get("segment")
    transcript = _transcript_from(outcome)
    segments = transcript.get("segments") if transcript is not None else None
    if (
        not isinstance(segment_position, int)
        or isinstance(segment_position, bool)
        or not isinstance(segments, list)
        or segment_position < 1
        or segment_position > len(segments)
    ):
        return _invalid_answer(
            "invalid_transcript_reference",
            "The claim references an unavailable transcript segment.",
            coverage,
        )
    segment = segments[segment_position - 1]
    if not isinstance(segment, Mapping):
        return _invalid_answer(
            "invalid_transcript_reference",
            "The claim references an unavailable transcript segment.",
            coverage,
        )
    start_seconds = _finite_seconds(segment.get("start_seconds"))
    end_seconds = _finite_seconds(segment.get("end_seconds"))
    if start_seconds is None or end_seconds is None or end_seconds < start_seconds:
        return _invalid_answer(
            "invalid_transcript_reference",
            "The claim references an invalid transcript segment.",
            coverage,
        )
    provenance = transcript.get("provenance") if transcript is not None else None
    provenance_label = (
        {
            "manual_captions": "manual captions",
            "automatic_captions": "automatic captions",
            "openai_whisper": "OpenAI Whisper",
            "groq_whisper": "Groq Whisper",
        }.get(provenance)
        if isinstance(provenance, str)
        else None
    )
    if provenance_label is None:
        return _invalid_answer(
            "invalid_transcript_provenance",
            "The transcript provenance is unavailable.",
            coverage,
        )
    citation_label = (
        f"{_format_source_time(start_seconds)}–{_format_source_time(end_seconds)} "
        f"(transcript; {provenance_label})"
    )
    return (
        ResolvedCitation(
            claim_id=claim_id,
            stream="transcript",
            label=citation_label,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
        ),
        coverage,
    )


def _resolve_visual_citation(
    claim_id: str,
    reference: Mapping[object, object],
    prepared_visuals: _PreparedVisualEvidence,
) -> tuple[ResolvedCitation, EvidenceCoverage] | WatchAnswer:
    observation_id = reference.get("observation")
    if not isinstance(observation_id, str) or not observation_id:
        return _invalid_answer(
            "invalid_visual_reference",
            "The claim references an unavailable visual observation.",
            prepared_visuals.coverage,
        )
    observation = prepared_visuals.observations_by_id.get(observation_id)
    if observation is None:
        return _invalid_answer(
            "invalid_visual_reference",
            "The claim references an unavailable visual observation.",
            prepared_visuals.coverage,
        )
    citation_label = (
        f"{_format_source_time(observation.timestamp_seconds)} "
        f"(visual; selection: {observation.selection_reason})"
    )
    return (
        ResolvedCitation(
            claim_id=claim_id,
            stream="visual",
            label=citation_label,
            start_seconds=observation.timestamp_seconds,
        ),
        prepared_visuals.coverage,
    )


def _prepare_visual_observations(
    outcome: Mapping[object, object],
    observations: object,
    coverage: EvidenceCoverage,
) -> _PreparedVisualEvidence | WatchAnswer:
    empty_observations: Mapping[str, _PreparedVisualObservation] = MappingProxyType(
        {}
    )
    if observations is None:
        return _PreparedVisualEvidence(
            coverage, empty_observations, (), frozenset()
        )
    if not isinstance(observations, list):
        return _invalid_answer(
            "invalid_visual_observations",
            "Visual observations must be a list.",
            coverage,
        )
    if not observations:
        return _PreparedVisualEvidence(
            coverage, empty_observations, (), frozenset()
        )

    visual = _visual_from(outcome)
    frames = visual.get("frames") if visual is not None else None
    inspection_state = visual.get("inspection_state") if visual is not None else None
    if not isinstance(frames, list) or not frames:
        return _invalid_answer(
            "invalid_visual_observation",
            "A Visual observation must identify one selected frame.",
            coverage,
        )

    frames_by_position: dict[int, Mapping[object, object]] = {}
    selected_frames: list[_PreparedSelectedFrame] = []
    for frame in frames:
        position = frame.get("chronological_position") if isinstance(frame, Mapping) else None
        if (
            not isinstance(position, int)
            or isinstance(position, bool)
            or position in frames_by_position
        ):
            return _invalid_answer(
                "invalid_visual_evidence",
                "The selected visual frames have invalid chronological positions.",
                coverage,
            )
        frames_by_position[position] = frame
        selected_frames.append(
            _PreparedSelectedFrame(
                chronological_position=position,
                timestamp_seconds=_finite_seconds(frame.get("timestamp_seconds")),
            )
        )

    prepared_observations: dict[str, _PreparedVisualObservation] = {}
    observed_positions: set[int] = set()
    for observation in observations:
        if not isinstance(observation, Mapping) or set(observation) != {
            "id",
            "frame_position",
            "description",
        }:
            return _invalid_answer(
                "invalid_visual_observation_schema",
                "A Visual observation contains unsupported fields.",
                coverage,
            )
        observation_id = observation.get("id")
        frame_position = observation.get("frame_position")
        description = observation.get("description")
        if (
            not isinstance(observation_id, str)
            or not observation_id.strip()
            or observation_id in prepared_observations
            or not isinstance(frame_position, int)
            or isinstance(frame_position, bool)
            or not isinstance(description, str)
            or not description.strip()
        ):
            return _invalid_answer(
                "invalid_visual_observation",
                "A Visual observation is invalid.",
                coverage,
            )
        frame = frames_by_position.get(frame_position)
        if frame is None:
            return _invalid_answer(
                "invalid_visual_observation",
                "A Visual observation references a frame that was not selected.",
                coverage,
            )
        runtime_inspected = frame.get("inspected") is True and inspection_state in {
            "complete",
            "partial",
        }
        if not runtime_inspected and inspection_state != "host_inspection_required":
            return _invalid_answer(
                "uninspected_visual_reference",
                "A Visual observation references a frame that was not inspected.",
                coverage,
            )
        timestamp_seconds = _finite_seconds(frame.get("timestamp_seconds"))
        selection_reason = frame.get("selection_reason")
        if (
            timestamp_seconds is None
            or not isinstance(selection_reason, str)
            or selection_reason
            not in {"first", "scene", "uniform", "keyframe", "transcript-cue"}
        ):
            return _invalid_answer(
                "invalid_visual_evidence",
                "The selected frame lacks trustworthy visual provenance.",
                coverage,
            )
        prepared_observations[observation_id] = _PreparedVisualObservation(
            id=observation_id,
            description=description.strip(),
            frame_position=frame_position,
            timestamp_seconds=timestamp_seconds,
            selection_reason=cast(FrameSelectionReason, selection_reason),
        )
        observed_positions.add(frame_position)

    answer_coverage = coverage
    if inspection_state == "host_inspection_required":
        if coverage.visual != "none":
            return _invalid_answer(
                "inconsistent_visual_coverage",
                "Pending visual inspection conflicts with its reported coverage.",
                coverage,
            )
        answer_coverage = EvidenceCoverage(
            coverage.metadata,
            coverage.transcript,
            "partial",
            "partial" if coverage.overall == "none" else coverage.overall,
        )
    elif coverage.visual == "none":
        return _invalid_answer(
            "inconsistent_visual_coverage",
            "Inspected visual evidence conflicts with its reported coverage.",
            coverage,
        )
    return _PreparedVisualEvidence(
        coverage=answer_coverage,
        observations_by_id=MappingProxyType(prepared_observations),
        selected_frames=tuple(selected_frames),
        observed_positions=frozenset(observed_positions),
    )


def _transcript_from(outcome: Mapping[object, object]) -> Mapping[object, object] | None:
    evidence = outcome.get("evidence")
    if not isinstance(evidence, Mapping):
        return None
    transcript = evidence.get("transcript")
    return transcript if isinstance(transcript, Mapping) else None


def _visual_from(outcome: Mapping[object, object]) -> Mapping[object, object] | None:
    evidence = outcome.get("evidence")
    if not isinstance(evidence, Mapping):
        return None
    visual = evidence.get("visual")
    return visual if isinstance(visual, Mapping) else None


def _parse_coverage(value: object) -> EvidenceCoverage | None:
    if not isinstance(value, Mapping):
        return None
    allowed = {"complete", "partial", "none"}
    fields = tuple(value.get(name) for name in ("metadata", "transcript", "visual", "overall"))
    if any(not isinstance(field, str) or field not in allowed for field in fields):
        return None
    return EvidenceCoverage(*fields)  # type: ignore[arg-type]


def _finite_seconds(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    seconds = float(value)
    return seconds if seconds >= 0 and math.isfinite(seconds) else None


def _format_source_time(seconds: float) -> str:
    milliseconds = int(round(seconds * 1000))
    whole_seconds, milliseconds = divmod(milliseconds, 1000)
    minutes, second = divmod(whole_seconds, 60)
    hours, minute = divmod(minutes, 60)
    prefix = f"{hours:02d}:{minute:02d}:{second:02d}" if hours else f"{minute:02d}:{second:02d}"
    return f"{prefix}.{milliseconds:03d}" if milliseconds else prefix


def _escape_markdown_text(value: str) -> str:
    escaped_controls = json.dumps(value, ensure_ascii=False)[1:-1]
    escaped_html = html.escape(escaped_controls, quote=True)
    for character in ("\\", "`", "*", "_", "[", "]", "(", ")", "#", ">", "|"):
        escaped_html = escaped_html.replace(character, f"&#{ord(character)};")
    return escaped_html


def _invalid_answer(
    code: str,
    message: str,
    coverage: EvidenceCoverage | None = None,
) -> WatchAnswer:
    safe_coverage = coverage or EvidenceCoverage("none", "none", "none", "none")
    return WatchAnswer(
        state="invalid",
        answerability="unsupported",
        coverage=safe_coverage,
        markdown=(
            "# Watch answer\n\n"
            "I could not produce an evidence-grounded answer because the answer plan was invalid."
        ),
        problem=AnswerProblem(code, message),
    )


def invalid_watch_answer(code: str, message: str) -> WatchAnswer:
    return _invalid_answer(code, message)
