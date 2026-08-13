from __future__ import annotations

from pathlib import Path
import copy
import json
import re
import subprocess
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIRECTORY = REPOSITORY_ROOT / ".agents" / "skills" / "watch" / "scripts"
ANSWER_WATCH = SCRIPTS_DIRECTORY / "answer_watch.py"
SKILL = REPOSITORY_ROOT / ".agents" / "skills" / "watch" / "SKILL.md"
ANSWER_REFERENCE = (
    REPOSITORY_ROOT
    / ".agents"
    / "skills"
    / "watch"
    / "references"
    / "answer-layer.md"
)
sys.path.insert(0, str(SCRIPTS_DIRECTORY))

from watch_answer import compose_watch_answer  # noqa: E402


def evidence_outcome(
    *,
    state: str = "ready",
    transcript: dict[str, object] | None = None,
    visual: dict[str, object] | None = None,
) -> dict[str, object]:
    transcript_coverage = "complete" if transcript is not None else "none"
    return {
        "state": state,
        "terminal": True,
        "source": {
            "kind": "url",
            "value": "https://video.example/watch?v=answer",
            "current": True,
        },
        "coverage": {
            "metadata": "complete",
            "transcript": transcript_coverage,
            "visual": "none",
            "overall": "complete" if transcript is not None and visual is None else "partial",
        },
        "answerability": "uncertain",
        "warnings": [],
        "failure": None,
        "evidence": {
            "metadata": {
                "title": "Launch update",
                "uploader": "Example channel",
                "duration_seconds": 90.0,
                "container": "webm",
                "size_bytes": None,
                "video_codec": "vp9",
                "audio_codec": "opus",
                "width": 1920,
                "height": 1080,
                "is_live": False,
            },
            "transcript": transcript,
            "visual": visual,
        },
        "tools": [],
        "javascript_support": {"status": "not_checked", "runtime": None},
        "controls": None,
        "report_markdown": "",
        "choice_kind": None,
        "choices": [],
        "caption_inventory": [],
        "decision_handle": None,
        "workspace_id": None,
        "evidence_handle": None,
        "retained_evidence": False,
        "disposal_state": "not_created",
        "reuse_state": "none",
    }


def transcript_evidence() -> dict[str, object]:
    return {
        "provenance": "manual_captions",
        "language": "en",
        "selected_track": {
            "id": "caption_opaque",
            "kind": "caption_track",
            "language": "en",
            "caption_type": "manual",
            "format": "vtt",
        },
        "segments": [
            {
                "text": "The launch is scheduled for Friday.",
                "start_seconds": 31.25,
                "end_seconds": 34.5,
            }
        ],
        "available_ranges": [{"start_seconds": 31.25, "end_seconds": 34.5}],
        "unavailable_ranges": [],
        "source_count": 1,
    }


def visual_evidence(*, inspection_state: str = "host_inspection_required") -> dict[str, object]:
    return {
        "frames": [
            {
                "timestamp_seconds": 36.0,
                "chronological_position": 1,
                "selection_reason": "scene",
                "path": "/runtime/workspace/frame-0001.jpg",
                "format": "jpeg",
                "width": 768,
                "height": 432,
                "inspected": inspection_state == "complete",
                "resolution_reason": None,
            }
        ],
        "candidate_count": 1,
        "ordinary_candidate_count": 1,
        "cap": 100,
        "ordinary_frame_cap": 100,
        "deduplication": "applied",
        "fallback": "scene",
        "cue_requested_count": 0,
        "cue_selected_count": 0,
        "cue_dropped_by_cap_count": 0,
        "cue_dropped_by_rate_count": 0,
        "inspection_state": inspection_state,
        "inspection_batches": [],
    }


class WatchAnswerLayerTests(unittest.TestCase):
    def test_transcript_claim_uses_absolute_time_and_manual_caption_provenance(self) -> None:
        answer = compose_watch_answer(
            {
                "outcome": evidence_outcome(transcript=transcript_evidence()),
                "question": "When is launch?",
                "answerability": "supported",
                "relevant_streams": ["transcript"],
                "claims": [
                    {
                        "id": "launch-date",
                        "text": "The speaker schedules the launch for Friday.",
                        "evidence": [{"stream": "transcript", "segment": 1}],
                    }
                ],
            }
        )

        self.assertEqual(answer.state, "answered")
        self.assertEqual(answer.answerability, "supported")
        self.assertIn("00:31.250–00:34.500 (transcript; manual captions)", answer.markdown)
        self.assertEqual(answer.citations[0].stream, "transcript")
        self.assertEqual(answer.citations[0].start_seconds, 31.25)
        self.assertEqual(answer.citations[0].end_seconds, 34.5)

    def test_transcript_claim_preserves_automatic_caption_provenance(self) -> None:
        transcript = transcript_evidence()
        transcript["provenance"] = "automatic_captions"

        answer = compose_watch_answer(
            {
                "outcome": evidence_outcome(transcript=transcript),
                "question": "When is launch?",
                "answerability": "supported",
                "relevant_streams": ["transcript"],
                "claims": [
                    {
                        "id": "launch-date",
                        "text": "The speaker schedules the launch for Friday.",
                        "evidence": [{"stream": "transcript", "segment": 1}],
                    }
                ],
            }
        )

        self.assertEqual(answer.state, "answered")
        self.assertIn(
            "00:31.250–00:34.500 (transcript; automatic captions)",
            answer.markdown,
        )

    def test_visual_observation_turns_one_selected_frame_into_visual_evidence(self) -> None:
        answer = compose_watch_answer(
            {
                "outcome": evidence_outcome(visual=visual_evidence()),
                "question": "What does the status badge show?",
                "answerability": "supported",
                "relevant_streams": ["visual"],
                "visual_observations": [
                    {
                        "id": "status-frame",
                        "frame_position": 1,
                        "description": "The status badge reads READY.",
                    }
                ],
                "claims": [
                    {
                        "id": "status",
                        "text": "The status badge reads READY.",
                        "evidence": [
                            {"stream": "visual", "observation": "status-frame"}
                        ],
                    }
                ],
            }
        )

        self.assertEqual(answer.state, "answered")
        self.assertEqual(answer.answerability, "supported")
        self.assertEqual(answer.coverage.visual, "partial")
        self.assertIn("00:36 (visual; selection: scene)", answer.markdown)
        self.assertEqual(answer.citations[0].stream, "visual")
        self.assertEqual(answer.citations[0].start_seconds, 36.0)
        self.assertIsNone(answer.citations[0].end_seconds)

    def test_visual_reference_resolves_the_indexed_second_observation(self) -> None:
        visual = visual_evidence()
        second_frame = dict(visual["frames"][0])  # type: ignore[index]
        second_frame.update(
            {
                "timestamp_seconds": 40.0,
                "chronological_position": 2,
                "path": "/runtime/workspace/frame-0002.jpg",
            }
        )
        visual["frames"].append(second_frame)  # type: ignore[union-attr]

        answer = compose_watch_answer(
            {
                "outcome": evidence_outcome(visual=visual),
                "question": "What does the later frame show?",
                "answerability": "supported",
                "relevant_streams": ["visual"],
                "visual_observations": [
                    {
                        "id": "earlier-status",
                        "frame_position": 1,
                        "description": "The earlier frame reads READY.",
                    },
                    {
                        "id": "later-status",
                        "frame_position": 2,
                        "description": "The later frame reads DONE.",
                    },
                ],
                "claims": [
                    {
                        "id": "later-status",
                        "text": "The later selected frame reads DONE.",
                        "evidence": [
                            {"stream": "visual", "observation": "later-status"}
                        ],
                    }
                ],
            }
        )

        self.assertEqual(answer.state, "answered")
        self.assertEqual(answer.citations[0].start_seconds, 40.0)
        self.assertIn("00:40 (visual; selection: scene)", answer.markdown)
        self.assertNotIn("unobserved selected", answer.markdown)

    def test_cross_stream_conflict_keeps_both_citations_and_is_uncertain(self) -> None:
        transcript = transcript_evidence()
        transcript["segments"] = [
            {
                "text": "The status is green.",
                "start_seconds": 10.0,
                "end_seconds": 12.0,
            }
        ]
        visual = visual_evidence()
        visual["frames"][0]["timestamp_seconds"] = 11.0  # type: ignore[index]

        answer = compose_watch_answer(
            {
                "outcome": evidence_outcome(transcript=transcript, visual=visual),
                "question": "Did the displayed status match what the speaker said?",
                "answerability": "uncertain",
                "relevant_streams": ["transcript", "visual"],
                "visual_observations": [
                    {
                        "id": "visible-status",
                        "frame_position": 1,
                        "description": "The displayed status is red.",
                    }
                ],
                "claims": [
                    {
                        "id": "spoken-status",
                        "text": "The speaker calls the status green.",
                        "evidence": [{"stream": "transcript", "segment": 1}],
                    },
                    {
                        "id": "visible-status",
                        "text": "The displayed status is red.",
                        "evidence": [
                            {"stream": "visual", "observation": "visible-status"}
                        ],
                    },
                ],
                "conflicts": [
                    {"left_claim": "spoken-status", "right_claim": "visible-status"}
                ],
            }
        )

        self.assertEqual(answer.state, "answered")
        self.assertEqual(answer.answerability, "uncertain")
        self.assertIn("00:10–00:12 (transcript; manual captions)", answer.markdown)
        self.assertIn("00:11 (visual; selection: scene)", answer.markdown)
        self.assertIn("The cited transcript and visual findings conflict.", answer.markdown)
        self.assertEqual([citation.stream for citation in answer.citations], ["transcript", "visual"])

    def test_supported_cross_stream_claim_cites_each_relevant_stream(self) -> None:
        transcript = transcript_evidence()
        transcript["segments"] = [
            {
                "text": "The status is READY.",
                "start_seconds": 10.0,
                "end_seconds": 12.0,
            }
        ]
        visual = visual_evidence()
        visual["frames"][0]["timestamp_seconds"] = 11.0  # type: ignore[index]

        answer = compose_watch_answer(
            {
                "outcome": evidence_outcome(transcript=transcript, visual=visual),
                "question": "Did the display match the speaker?",
                "answerability": "supported",
                "relevant_streams": ["transcript", "visual"],
                "visual_observations": [
                    {
                        "id": "visible-status",
                        "frame_position": 1,
                        "description": "The displayed status is READY.",
                    }
                ],
                "claims": [
                    {
                        "id": "matching-status",
                        "text": "The displayed READY status agrees with the spoken READY status.",
                        "evidence": [
                            {"stream": "transcript", "segment": 1},
                            {"stream": "visual", "observation": "visible-status"},
                        ],
                    }
                ],
            }
        )

        self.assertEqual(answer.state, "answered")
        self.assertEqual(answer.answerability, "supported")
        self.assertEqual(
            [citation.stream for citation in answer.citations],
            ["transcript", "visual"],
        )
        self.assertIn("00:10–00:12 (transcript; manual captions)", answer.markdown)
        self.assertIn("00:11 (visual; selection: scene)", answer.markdown)

    def test_partial_transcript_can_support_a_claim_while_naming_its_gap(self) -> None:
        transcript = transcript_evidence()
        transcript["unavailable_ranges"] = [
            {"start_seconds": 40.0, "end_seconds": 50.0}
        ]
        outcome = evidence_outcome(transcript=transcript)
        outcome["coverage"]["transcript"] = "partial"  # type: ignore[index]
        outcome["coverage"]["overall"] = "partial"  # type: ignore[index]

        answer = compose_watch_answer(
            {
                "outcome": outcome,
                "question": "When is launch?",
                "answerability": "supported",
                "relevant_streams": ["transcript"],
                "claims": [
                    {
                        "id": "launch-date",
                        "text": "The speaker schedules launch for Friday.",
                        "evidence": [{"stream": "transcript", "segment": 1}],
                    }
                ],
            }
        )

        self.assertEqual(answer.state, "answered")
        self.assertEqual(answer.coverage.transcript, "partial")
        self.assertEqual(answer.answerability, "supported")
        self.assertIn(
            "Transcript evidence is unavailable at 00:40–00:50.",
            answer.limitations,
        )
        self.assertIn("## Limitations", answer.markdown)
        self.assertIn("Transcript coverage: `partial`", answer.markdown)

    def test_metadata_claim_is_source_wide_and_never_given_a_fake_timestamp(self) -> None:
        answer = compose_watch_answer(
            {
                "outcome": evidence_outcome(),
                "question": "Who uploaded this source?",
                "answerability": "supported",
                "relevant_streams": ["metadata"],
                "claims": [
                    {
                        "id": "uploader",
                        "text": "The source uploader is Example channel.",
                        "evidence": [{"stream": "metadata", "field": "uploader"}],
                    }
                ],
            }
        )

        self.assertEqual(answer.state, "answered")
        self.assertEqual(answer.answerability, "supported")
        self.assertIn(
            "source-wide (metadata; source time: not applicable; field: uploader)",
            answer.markdown,
        )
        self.assertNotIn("00:00 (metadata", answer.markdown)
        self.assertEqual(answer.citations[0].stream, "metadata")
        self.assertIsNone(answer.citations[0].start_seconds)

    def test_cancellation_with_retained_evidence_suppresses_the_answer_plan(self) -> None:
        outcome = evidence_outcome(state="canceled", transcript=transcript_evidence())
        outcome["failure"] = {
            "stage": "visual",
            "category": "user_cancellation",
            "message": "The user canceled visual inspection.",
            "attempts": 1,
            "retained_evidence": True,
            "disposal_state": "retained",
            "reuse_state": "same_task_evidence",
        }
        outcome["retained_evidence"] = True
        outcome["disposal_state"] = "retained"
        outcome["reuse_state"] = "same_task_evidence"

        answer = compose_watch_answer(
            {
                "outcome": outcome,
                "question": "When is launch?",
                "answerability": "supported",
                "relevant_streams": ["transcript"],
                "claims": [
                    {
                        "id": "must-not-render",
                        "text": "THIS PARTIAL ANSWER MUST NOT APPEAR",
                        "evidence": [{"stream": "transcript", "segment": 1}],
                    }
                ],
            }
        )

        self.assertEqual(answer.state, "withheld")
        self.assertEqual(answer.answerability, "unsupported")
        self.assertIn("canceled during `visual`", answer.markdown)
        self.assertIn("Evidence retained: `true`", answer.markdown)
        self.assertIn("Disposal state: `retained`", answer.markdown)
        self.assertIn("Reuse state: `same_task_evidence`", answer.markdown)
        self.assertNotIn("THIS PARTIAL ANSWER MUST NOT APPEAR", answer.markdown)
        self.assertEqual(answer.citations, ())

    def test_complete_transcript_does_not_support_an_unseen_visual_conclusion(self) -> None:
        answer = compose_watch_answer(
            {
                "outcome": evidence_outcome(transcript=transcript_evidence()),
                "question": "What color was the displayed status?",
                "answerability": "unsupported",
                "relevant_streams": ["visual"],
                "claims": [],
            }
        )

        self.assertEqual(answer.state, "answered")
        self.assertEqual(answer.answerability, "unsupported")
        self.assertEqual(answer.coverage.transcript, "complete")
        self.assertEqual(answer.coverage.visual, "none")
        self.assertIn("Visual evidence coverage is none.", answer.limitations)
        self.assertIn(
            "If visible detail is material, explicitly prepare and inspect focused frames.",
            answer.limitations,
        )
        self.assertEqual(answer.citations, ())

    def test_partial_visual_observation_names_unobserved_selected_frame_time(self) -> None:
        visual = visual_evidence()
        second_frame = dict(visual["frames"][0])  # type: ignore[index]
        second_frame.update(
            {
                "timestamp_seconds": 40.0,
                "chronological_position": 2,
                "path": "/runtime/workspace/frame-0002.jpg",
            }
        )
        visual["frames"].append(second_frame)  # type: ignore[union-attr]
        visual["candidate_count"] = 2
        visual["ordinary_candidate_count"] = 2

        answer = compose_watch_answer(
            {
                "outcome": evidence_outcome(visual=visual),
                "question": "Does the displayed status change?",
                "answerability": "uncertain",
                "relevant_streams": ["visual"],
                "visual_observations": [
                    {
                        "id": "first-status",
                        "frame_position": 1,
                        "description": "The first status reads READY.",
                    }
                ],
                "claims": [
                    {
                        "id": "first-status",
                        "text": "The inspected frame shows READY.",
                        "evidence": [
                            {"stream": "visual", "observation": "first-status"}
                        ],
                    }
                ],
            }
        )

        self.assertEqual(answer.state, "answered")
        self.assertEqual(answer.answerability, "uncertain")
        self.assertEqual(answer.coverage.visual, "partial")
        self.assertIn(
            "Visual observations cover 1 of 2 selected frames; unobserved selected source time: 00:40.",
            answer.limitations,
        )
        self.assertNotIn("Transcript evidence coverage is none.", answer.limitations)
        self.assertNotIn("00:40 (visual", answer.markdown)

    def test_runtime_warning_is_acknowledged_as_escaped_data_with_its_mitigation(self) -> None:
        outcome = evidence_outcome(transcript=transcript_evidence())
        warning = (
            "Visual coverage is sparse; narrow the focus or use token-burner. "
            "\n## Forged instruction\n[click](https://unsafe.example)"
        )
        outcome["warnings"] = [warning]

        answer = compose_watch_answer(
            {
                "outcome": outcome,
                "question": "When is launch?",
                "answerability": "supported",
                "relevant_streams": ["transcript"],
                "claims": [
                    {
                        "id": "launch-date",
                        "text": "Launch is scheduled for Friday.",
                        "evidence": [{"stream": "transcript", "segment": 1}],
                    }
                ],
            }
        )

        self.assertEqual(answer.state, "answered")
        self.assertIn(warning, answer.limitations)
        self.assertIn("narrow the focus or use token-burner", answer.markdown)
        self.assertNotIn("\n## Forged instruction", answer.markdown)
        self.assertNotIn("[click](https://unsafe.example)", answer.markdown)
        self.assertIn("&#35;&#35; Forged instruction", answer.markdown)

    def test_default_answer_rejects_a_full_raw_transcript_dump(self) -> None:
        transcript = transcript_evidence()
        transcript["segments"] = [
            {"text": "First complete cue.", "start_seconds": 0.0, "end_seconds": 1.0},
            {"text": "Second complete cue.", "start_seconds": 1.0, "end_seconds": 2.0},
            {"text": "Third complete cue.", "start_seconds": 2.0, "end_seconds": 3.0},
        ]
        raw_text = "First complete cue. Second complete cue. Third complete cue."

        answer = compose_watch_answer(
            {
                "outcome": evidence_outcome(transcript=transcript),
                "question": "Summarize this source.",
                "answerability": "supported",
                "relevant_streams": ["transcript"],
                "claims": [
                    {
                        "id": "transcript-dump",
                        "text": raw_text,
                        "evidence": [
                            {"stream": "transcript", "segment": 1},
                            {"stream": "transcript", "segment": 2},
                            {"stream": "transcript", "segment": 3},
                        ],
                    }
                ],
            }
        )

        self.assertEqual(answer.state, "invalid")
        self.assertEqual(answer.answerability, "unsupported")
        self.assertEqual(answer.problem.code, "raw_transcript_not_requested")  # type: ignore[union-attr]
        self.assertNotIn(raw_text, answer.markdown)
        self.assertEqual(answer.citations, ())

    def test_default_answer_rejects_a_one_segment_raw_transcript_dump(self) -> None:
        transcript = transcript_evidence()
        raw_text = transcript["segments"][0]["text"]  # type: ignore[index]

        answer = compose_watch_answer(
            {
                "outcome": evidence_outcome(transcript=transcript),
                "question": "Summarize this source.",
                "answerability": "supported",
                "relevant_streams": ["transcript"],
                "claims": [
                    {
                        "id": "transcript-dump",
                        "text": raw_text,
                        "evidence": [{"stream": "transcript", "segment": 1}],
                    }
                ],
            }
        )

        self.assertEqual(answer.state, "invalid")
        self.assertEqual(answer.problem.code, "raw_transcript_not_requested")  # type: ignore[union-attr]
        self.assertNotIn(raw_text, answer.markdown)

    def test_uncited_free_form_reason_cannot_bypass_grounded_claims(self) -> None:
        forged_conclusion = "The video proves success at 00:42."

        answer = compose_watch_answer(
            {
                "outcome": evidence_outcome(),
                "question": "Did it succeed?",
                "answerability": "unsupported",
                "reason": forged_conclusion,
                "relevant_streams": ["visual"],
                "claims": [],
            }
        )

        self.assertEqual(answer.state, "invalid")
        self.assertNotIn(forged_conclusion, answer.markdown)
        self.assertEqual(answer.citations, ())

    def test_supported_answer_requires_evidence_from_every_relevant_stream(self) -> None:
        answer = compose_watch_answer(
            {
                "outcome": evidence_outcome(transcript=transcript_evidence()),
                "question": "Did the display match the speaker?",
                "answerability": "supported",
                "relevant_streams": ["transcript", "visual"],
                "claims": [
                    {
                        "id": "cross-stream-conclusion",
                        "text": "The display matched the speaker.",
                        "evidence": [{"stream": "transcript", "segment": 1}],
                    }
                ],
            }
        )

        self.assertEqual(answer.state, "invalid")
        self.assertNotIn("The display matched the speaker.", answer.markdown)
        self.assertEqual(answer.citations, ())

    def test_runtime_complete_visual_coverage_is_not_downgraded(self) -> None:
        visual = visual_evidence(inspection_state="complete")
        outcome = evidence_outcome(visual=visual)
        outcome["coverage"]["visual"] = "complete"  # type: ignore[index]
        outcome["coverage"]["overall"] = "complete"  # type: ignore[index]

        answer = compose_watch_answer(
            {
                "outcome": outcome,
                "question": "What does the status badge show?",
                "answerability": "supported",
                "relevant_streams": ["visual"],
                "visual_observations": [
                    {
                        "id": "status-frame",
                        "frame_position": 1,
                        "description": "The status badge reads READY.",
                    }
                ],
                "claims": [
                    {
                        "id": "status",
                        "text": "The status badge reads READY.",
                        "evidence": [
                            {"stream": "visual", "observation": "status-frame"}
                        ],
                    }
                ],
            }
        )

        self.assertEqual(answer.state, "answered")
        self.assertEqual(answer.coverage.visual, "complete")
        self.assertEqual(answer.coverage.overall, "complete")

    def test_visual_claim_cannot_use_an_uninspected_selected_frame(self) -> None:
        visual = visual_evidence(inspection_state="partial")
        outcome = evidence_outcome(visual=visual)
        outcome["coverage"]["visual"] = "partial"  # type: ignore[index]

        answer = compose_watch_answer(
            {
                "outcome": outcome,
                "question": "What does the status badge show?",
                "answerability": "supported",
                "relevant_streams": ["visual"],
                "visual_observations": [
                    {
                        "id": "unseen-status",
                        "frame_position": 1,
                        "description": "A description must not make this frame inspected.",
                    }
                ],
                "claims": [
                    {
                        "id": "unseen-status",
                        "text": "UNSEEN VISUAL CLAIM",
                        "evidence": [
                            {"stream": "visual", "observation": "unseen-status"}
                        ],
                    }
                ],
            }
        )

        self.assertEqual(answer.state, "invalid")
        self.assertEqual(answer.problem.code, "uninspected_visual_reference")  # type: ignore[union-attr]
        self.assertNotIn("UNSEEN VISUAL CLAIM", answer.markdown)
        self.assertEqual(answer.citations, ())

    def test_visual_observation_updates_coverage_even_without_a_visual_claim(self) -> None:
        answer = compose_watch_answer(
            {
                "outcome": evidence_outcome(visual=visual_evidence()),
                "question": "Does the frame prove that the launch completed?",
                "answerability": "unsupported",
                "relevant_streams": ["visual"],
                "visual_observations": [
                    {
                        "id": "status-frame",
                        "frame_position": 1,
                        "description": "The frame shows a READY status, not completion.",
                    }
                ],
                "claims": [],
            }
        )

        self.assertEqual(answer.state, "answered")
        self.assertEqual(answer.answerability, "unsupported")
        self.assertEqual(answer.coverage.visual, "partial")
        self.assertNotIn("Visual evidence coverage is none.", answer.limitations)

    def test_unreferenced_visual_observation_still_fails_closed(self) -> None:
        answer = compose_watch_answer(
            {
                "outcome": evidence_outcome(),
                "question": "What is the source title?",
                "answerability": "supported",
                "relevant_streams": ["metadata"],
                "visual_observations": [
                    {
                        "id": "forged-frame",
                        "frame_position": 99,
                        "description": "FORGED UNSELECTED OBSERVATION",
                    }
                ],
                "claims": [
                    {
                        "id": "source-title",
                        "text": "The source title is Launch update.",
                        "evidence": [{"stream": "metadata", "field": "title"}],
                    }
                ],
            }
        )

        self.assertEqual(answer.state, "invalid")
        self.assertNotIn("FORGED UNSELECTED OBSERVATION", answer.markdown)
        self.assertEqual(answer.citations, ())

    def test_cli_compiles_one_json_answer_request(self) -> None:
        request = {
            "outcome": evidence_outcome(transcript=transcript_evidence()),
            "question": "When is launch?",
            "answerability": "supported",
            "relevant_streams": ["transcript"],
            "claims": [
                {
                    "id": "launch-date",
                    "text": "Launch is scheduled for Friday.",
                    "evidence": [{"stream": "transcript", "segment": 1}],
                }
            ],
        }

        completed = subprocess.run(
            [sys.executable, "-B", str(ANSWER_WATCH)],
            input=json.dumps(request),
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["state"], "answered")
        self.assertEqual(payload["answerability"], "supported")
        self.assertIn(
            "00:31.250–00:34.500 (transcript; manual captions)",
            payload["markdown"],
        )
        self.assertEqual(payload["citations"][0]["stream"], "transcript")

    def test_failed_outcome_reports_typed_failure_without_an_evidence_conclusion(self) -> None:
        outcome = evidence_outcome(state="failed", transcript=transcript_evidence())
        outcome["failure"] = {
            "stage": "captions",
            "category": "caption_parse",
            "message": "Caption parser rejected <unsafe>\n## forged state",
            "attempts": 2,
            "retained_evidence": True,
            "disposal_state": "retained",
            "reuse_state": "same_task_evidence",
        }
        outcome["retained_evidence"] = True
        outcome["disposal_state"] = "retained"
        outcome["reuse_state"] = "same_task_evidence"

        answer = compose_watch_answer(
            {
                "outcome": outcome,
                "question": "When is launch?",
                "answerability": "supported",
                "relevant_streams": ["transcript"],
                "claims": [
                    {
                        "id": "must-not-render",
                        "text": "A conclusion that must stay suppressed.",
                        "evidence": [{"stream": "transcript", "segment": 1}],
                    }
                ],
            }
        )

        self.assertEqual(answer.state, "withheld")
        self.assertIn("failed during `captions`", answer.markdown)
        self.assertIn("Failure category: `caption_parse`", answer.markdown)
        self.assertIn("Attempts: `2`", answer.markdown)
        self.assertIn("Caption parser rejected &lt;unsafe&gt;", answer.markdown)
        self.assertNotIn("\n## forged state", answer.markdown)
        self.assertNotIn("A conclusion that must stay suppressed.", answer.markdown)

    def test_malformed_evidence_reference_fails_closed_without_rendering_claim_text(self) -> None:
        answer = compose_watch_answer(
            {
                "outcome": evidence_outcome(transcript=transcript_evidence()),
                "question": "When is launch?",
                "answerability": "supported",
                "relevant_streams": ["transcript"],
                "claims": [
                    {
                        "id": "malformed",
                        "text": "UNVALIDATED CLAIM TEXT",
                        "evidence": [{"stream": "transcript", "segment": []}],
                    }
                ],
            }
        )

        self.assertEqual(answer.state, "invalid")
        self.assertEqual(answer.answerability, "unsupported")
        self.assertNotIn("UNVALIDATED CLAIM TEXT", answer.markdown)
        self.assertEqual(answer.citations, ())

    def test_non_scalar_state_answerability_and_coverage_values_fail_closed(self) -> None:
        valid_request = {
            "outcome": evidence_outcome(transcript=transcript_evidence()),
            "question": "When is launch?",
            "answerability": "supported",
            "relevant_streams": ["transcript"],
            "claims": [
                {
                    "id": "launch-date",
                    "text": "Launch is scheduled for Friday.",
                    "evidence": [{"stream": "transcript", "segment": 1}],
                }
            ],
        }
        malformed_requests: list[dict[str, object]] = []
        malformed_answerability = copy.deepcopy(valid_request)
        malformed_answerability["answerability"] = []
        malformed_requests.append(malformed_answerability)
        malformed_state = copy.deepcopy(valid_request)
        malformed_state["outcome"]["state"] = []  # type: ignore[index]
        malformed_requests.append(malformed_state)
        malformed_coverage = copy.deepcopy(valid_request)
        malformed_coverage["outcome"]["coverage"]["visual"] = []  # type: ignore[index]
        malformed_requests.append(malformed_coverage)

        for malformed_request in malformed_requests:
            with self.subTest(request=malformed_request):
                answer = compose_watch_answer(malformed_request)
                self.assertEqual(answer.state, "invalid")
                self.assertEqual(answer.answerability, "unsupported")
                self.assertEqual(answer.citations, ())

    def test_non_scalar_provenance_selection_reason_and_conflict_ids_fail_closed(self) -> None:
        bad_transcript = transcript_evidence()
        bad_transcript["provenance"] = []
        transcript_request = {
            "outcome": evidence_outcome(transcript=bad_transcript),
            "question": "When is launch?",
            "answerability": "supported",
            "relevant_streams": ["transcript"],
            "claims": [
                {
                    "id": "launch-date",
                    "text": "Launch is scheduled for Friday.",
                    "evidence": [{"stream": "transcript", "segment": 1}],
                }
            ],
        }

        bad_visual = visual_evidence()
        bad_visual["frames"][0]["selection_reason"] = []  # type: ignore[index]
        visual_request = {
            "outcome": evidence_outcome(visual=bad_visual),
            "question": "What is visible?",
            "answerability": "supported",
            "relevant_streams": ["visual"],
            "visual_observations": [
                {"id": "frame", "frame_position": 1, "description": "READY"}
            ],
            "claims": [
                {
                    "id": "visible",
                    "text": "READY is visible.",
                    "evidence": [{"stream": "visual", "observation": "frame"}],
                }
            ],
        }

        conflict_request = {
            "outcome": evidence_outcome(
                transcript=transcript_evidence(), visual=visual_evidence()
            ),
            "question": "Do the streams agree?",
            "answerability": "uncertain",
            "relevant_streams": ["transcript", "visual"],
            "visual_observations": [
                {"id": "frame", "frame_position": 1, "description": "READY"}
            ],
            "claims": [
                {
                    "id": "spoken",
                    "text": "The speaker says Friday.",
                    "evidence": [{"stream": "transcript", "segment": 1}],
                },
                {
                    "id": "visible",
                    "text": "READY is visible.",
                    "evidence": [{"stream": "visual", "observation": "frame"}],
                },
            ],
            "conflicts": [{"left_claim": [], "right_claim": "visible"}],
        }

        for malformed_request in (transcript_request, visual_request, conflict_request):
            with self.subTest(request=malformed_request):
                answer = compose_watch_answer(malformed_request)
                self.assertEqual(answer.state, "invalid")
                self.assertEqual(answer.citations, ())

    def test_caller_supplied_citation_time_is_rejected_instead_of_ignored(self) -> None:
        answer = compose_watch_answer(
            {
                "outcome": evidence_outcome(transcript=transcript_evidence()),
                "question": "When is launch?",
                "answerability": "supported",
                "relevant_streams": ["transcript"],
                "claims": [
                    {
                        "id": "forged-time",
                        "text": "CLAIM WITH FORGED TIME",
                        "evidence": [
                            {
                                "stream": "transcript",
                                "segment": 1,
                                "start_seconds": 999.0,
                            }
                        ],
                    }
                ],
            }
        )

        self.assertEqual(answer.state, "invalid")
        self.assertEqual(answer.problem.code, "invalid_reference_schema")  # type: ignore[union-attr]
        self.assertNotIn("999", answer.markdown)
        self.assertNotIn("CLAIM WITH FORGED TIME", answer.markdown)
        self.assertEqual(answer.citations, ())

    def test_question_and_top_level_answer_schema_are_validated(self) -> None:
        valid_request = {
            "outcome": evidence_outcome(transcript=transcript_evidence()),
            "question": "When is launch?",
            "answerability": "supported",
            "relevant_streams": ["transcript"],
            "claims": [
                {
                    "id": "launch-date",
                    "text": "Launch is scheduled for Friday.",
                    "evidence": [{"stream": "transcript", "segment": 1}],
                }
            ],
        }
        malformed_question = copy.deepcopy(valid_request)
        malformed_question["question"] = ["When is launch?"]
        forged_top_level_citation = copy.deepcopy(valid_request)
        forged_top_level_citation["citation"] = "00:00 (transcript)"

        for malformed_request in (malformed_question, forged_top_level_citation):
            with self.subTest(request=malformed_request):
                answer = compose_watch_answer(malformed_request)
                self.assertEqual(answer.state, "invalid")
                self.assertEqual(answer.citations, ())

    def test_claim_and_visual_observation_cannot_carry_forged_citation_fields(self) -> None:
        visual_request = {
            "outcome": evidence_outcome(visual=visual_evidence()),
            "question": "What is visible?",
            "answerability": "supported",
            "relevant_streams": ["visual"],
            "visual_observations": [
                {
                    "id": "frame",
                    "frame_position": 1,
                    "description": "READY",
                    "timestamp_seconds": 999.0,
                }
            ],
            "claims": [
                {
                    "id": "visible",
                    "text": "READY is visible.",
                    "evidence": [{"stream": "visual", "observation": "frame"}],
                }
            ],
        }
        claim_request = {
            "outcome": evidence_outcome(transcript=transcript_evidence()),
            "question": "When is launch?",
            "answerability": "supported",
            "relevant_streams": ["transcript"],
            "claims": [
                {
                    "id": "launch-date",
                    "text": "Launch is scheduled for Friday.",
                    "evidence": [{"stream": "transcript", "segment": 1}],
                    "citation": "00:00 (transcript)",
                }
            ],
        }

        for malformed_request in (visual_request, claim_request):
            with self.subTest(request=malformed_request):
                answer = compose_watch_answer(malformed_request)
                self.assertEqual(answer.state, "invalid")
                self.assertNotIn("999", answer.markdown)
                self.assertNotIn("00:00 (transcript)", answer.markdown)
                self.assertEqual(answer.citations, ())

    def test_explicit_raw_transcript_request_may_return_the_complete_grounded_text(self) -> None:
        transcript = transcript_evidence()
        transcript["segments"] = [
            {"text": "First complete cue.", "start_seconds": 0.0, "end_seconds": 1.0},
            {"text": "Second complete cue.", "start_seconds": 1.0, "end_seconds": 2.0},
        ]
        raw_text = "First complete cue. Second complete cue."

        answer = compose_watch_answer(
            {
                "outcome": evidence_outcome(transcript=transcript),
                "question": "Give me the full Raw transcript.",
                "raw_transcript_requested": True,
                "answerability": "supported",
                "relevant_streams": ["transcript"],
                "claims": [
                    {
                        "id": "raw-transcript",
                        "text": raw_text,
                        "evidence": [
                            {"stream": "transcript", "segment": 1},
                            {"stream": "transcript", "segment": 2},
                        ],
                    }
                ],
            }
        )

        self.assertEqual(answer.state, "answered")
        self.assertEqual(answer.answerability, "supported")
        self.assertIn(raw_text, answer.markdown)
        self.assertEqual(len(answer.citations), 2)

    def test_cli_malformed_json_returns_typed_invalid_answer(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-B", str(ANSWER_WATCH)],
            input="{not-json",
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["state"], "invalid")
        self.assertEqual(payload["answerability"], "unsupported")
        self.assertEqual(payload["problem"]["code"], "invalid_json")

    def test_transcript_claim_is_rejected_when_stream_coverage_is_none(self) -> None:
        outcome = evidence_outcome(transcript=transcript_evidence())
        outcome["coverage"]["transcript"] = "none"  # type: ignore[index]

        answer = compose_watch_answer(
            {
                "outcome": outcome,
                "question": "When is launch?",
                "answerability": "supported",
                "relevant_streams": ["transcript"],
                "claims": [
                    {
                        "id": "inconsistent-transcript",
                        "text": "INCONSISTENT TRANSCRIPT CLAIM",
                        "evidence": [{"stream": "transcript", "segment": 1}],
                    }
                ],
            }
        )

        self.assertEqual(answer.state, "invalid")
        self.assertEqual(answer.problem.code, "unavailable_transcript_stream")  # type: ignore[union-attr]
        self.assertNotIn("INCONSISTENT TRANSCRIPT CLAIM", answer.markdown)
        self.assertEqual(answer.citations, ())

    def test_no_question_produces_a_grounded_timestamped_summary(self) -> None:
        answer = compose_watch_answer(
            {
                "outcome": evidence_outcome(transcript=transcript_evidence()),
                "question": None,
                "answerability": "supported",
                "relevant_streams": ["transcript"],
                "claims": [
                    {
                        "id": "summary",
                        "text": "The source announces a Friday launch.",
                        "evidence": [{"stream": "transcript", "segment": 1}],
                    }
                ],
            }
        )

        self.assertEqual(answer.state, "answered")
        self.assertEqual(answer.answerability, "supported")
        self.assertIn("The source announces a Friday launch.", answer.markdown)
        self.assertIn(
            "00:31.250–00:34.500 (transcript; manual captions)", answer.markdown
        )

    def test_skill_routes_user_facing_answers_through_the_grounding_reference(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        answer_reference = ANSWER_REFERENCE.read_text(encoding="utf-8")

        self.assertIn("references/answer-layer.md", skill)
        self.assertIn("scripts/answer_watch.py", skill)
        self.assertIn("visual_observations", answer_reference)
        self.assertIn("chronological_position", answer_reference)
        self.assertIn("transcript segment positions are 1-based", answer_reference)
        self.assertIn("Caller-written citation times are invalid", answer_reference)
        self.assertIn("state: `invalid`", answer_reference)
        self.assertIn('"answerability"', answer_reference)
        self.assertNotIn('"verdict"', answer_reference)
        self.assertNotIn("host observation", answer_reference.casefold())

        example = re.search(r"```json\n(.*?)\n```", answer_reference, re.DOTALL)
        self.assertIsNotNone(example)
        example_request = json.loads(example.group(1))  # type: ignore[union-attr]
        example_answer = compose_watch_answer(example_request)
        self.assertEqual(example_answer.state, "answered")


if __name__ == "__main__":
    unittest.main()
