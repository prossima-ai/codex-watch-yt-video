from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Sequence
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIRECTORY = REPOSITORY_ROOT / ".agents" / "skills" / "watch" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIRECTORY))

from watch_evidence import (  # noqa: E402
    CommandResult,
    TranscriptSegment,
    WatchEvidenceRuntime,
)


class CaptionRunner:
    def __init__(self, metadata: dict[str, object], caption_bodies: dict[str, str]) -> None:
        self.metadata = metadata
        self.caption_bodies = caption_bodies
        self.invocations: list[tuple[str, list[str]]] = []

    def run(self, executable: str, arguments: Sequence[str]) -> CommandResult:
        copied_arguments = list(arguments)
        self.invocations.append((executable, copied_arguments))
        if "--version" in copied_arguments or "-version" in copied_arguments:
            return CommandResult(0, "2026.08.12\n", "")
        if "--verbose" in copied_arguments:
            return CommandResult(1, "", "[debug] JS runtimes: node-24.10.0\n")
        if "--dump-single-json" in copied_arguments:
            return CommandResult(0, json.dumps(self.metadata), "")

        kind = (
            "manual"
            if "--write-subs" in copied_arguments
            else "automatic"
            if "--write-auto-subs" in copied_arguments
            else None
        )
        if kind is None:
            return CommandResult(1, "", "Unexpected command")
        language = copied_arguments[copied_arguments.index("--sub-langs") + 1]
        caption_format = copied_arguments[copied_arguments.index("--sub-format") + 1]
        output_template = copied_arguments[copied_arguments.index("--output") + 1]
        caption_path = Path(output_template.replace("%(ext)s", caption_format))
        caption_body = self.caption_bodies.get(f"{kind}:{language}:{caption_format}")
        if caption_body is None:
            caption_body = self.caption_bodies[f"{kind}:{language}"]
        caption_path.write_text(caption_body, encoding="utf-8")
        return CommandResult(0, "", "")

    def caption_invocations(self) -> list[list[str]]:
        return [
            arguments
            for _, arguments in self.invocations
            if "--write-subs" in arguments or "--write-auto-subs" in arguments
        ]


def fake_executable(name: str) -> str:
    return f"/fake/{name}"


def captioned_metadata(
    *,
    subtitles: dict[str, object] | None = None,
    automatic_captions: dict[str, object] | None = None,
    duration: float | None = 10.0,
) -> dict[str, object]:
    return {
        "_type": "video",
        "id": "captioned-example",
        "title": "Captioned example",
        "duration": duration,
        "ext": "webm",
        "vcodec": "vp9",
        "acodec": "opus",
        "is_live": False,
        "subtitles": subtitles or {},
        "automatic_captions": automatic_captions or {},
    }


class CaptionEvidenceTests(unittest.TestCase):
    source = "https://video.example/watch?v=captioned"

    def make_runtime(
        self, metadata: dict[str, object], caption_bodies: dict[str, str]
    ) -> tuple[WatchEvidenceRuntime, CaptionRunner]:
        runner = CaptionRunner(metadata, caption_bodies)
        return (
            WatchEvidenceRuntime(command_runner=runner, find_executable=fake_executable),
            runner,
        )

    def request(self, **controls: object) -> dict[str, object]:
        return {
            "sources": [self.source],
            "source_network_approved": True,
            "detail": "transcript",
            **controls,
        }

    def test_multiple_usable_tracks_pause_with_sanitized_choices_before_download(self) -> None:
        runtime, runner = self.make_runtime(
            captioned_metadata(
                subtitles={"en": [{"ext": "vtt", "url": "https://cdn.example/manual.vtt"}]},
                automatic_captions={
                    "fr": [{"ext": "vtt", "url": "https://cdn.example/automatic.vtt"}],
                    "live_chat": [{"ext": "json", "url": "https://cdn.example/chat"}],
                },
            ),
            {},
        )

        outcome = runtime.prepare(self.request())
        payload = json.loads(json.dumps(outcome.to_dict()))

        self.assertEqual(outcome.state, "decision_required")
        self.assertFalse(outcome.terminal)
        self.assertEqual(payload["choice_kind"], "caption_track")
        self.assertEqual(
            payload["choices"],
            [
                {
                    "id": payload["choices"][0]["id"],
                    "kind": "caption_track",
                    "language": "en",
                    "caption_type": "manual",
                    "format": "vtt",
                },
                {
                    "id": payload["choices"][1]["id"],
                    "kind": "caption_track",
                    "language": "fr",
                    "caption_type": "automatic",
                    "format": "vtt",
                },
            ],
        )
        self.assertNotEqual(payload["choices"][0]["id"], payload["choices"][1]["id"])
        self.assertNotIn("cdn.example", outcome.report_markdown)
        self.assertEqual(runner.caption_invocations(), [])

        tampered_prior = json.loads(json.dumps(payload))
        tampered_prior["choices"][0]["language"] = "de"
        runner.invocations.clear()
        rejected = runtime.prepare(
            self.request(caption_track=payload["choices"][0]["id"]),
            prior_evidence=tampered_prior,
        )
        self.assertEqual(rejected.state, "stopped")
        self.assertEqual(rejected.failure.category, "invalid_selection")
        self.assertEqual(runner.invocations, [])

    def test_explicit_prior_choice_downloads_only_manual_captions_and_normalizes_segments(self) -> None:
        runtime, runner = self.make_runtime(
            captioned_metadata(
                subtitles={"en": [{"ext": "vtt", "url": "https://cdn.example/manual.vtt"}]},
                automatic_captions={
                    "en": [{"ext": "vtt", "url": "https://cdn.example/automatic.vtt"}]
                },
            ),
            {
                "manual:en": """WEBVTT

00:00:00.000 --> 00:00:02.000
<c>Hello &amp; welcome</c>

00:00:01.000 --> 00:00:03.000
Hello &amp; welcome everyone

00:00:03.000 --> 00:00:04.000
Hello &amp; welcome everyone

00:00:05.000 --> 00:00:06.000
<i>Bye</i>
""",
                "automatic:en": "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nUnused\n",
            },
        )
        decision = runtime.prepare(self.request())
        manual_choice = next(
            choice for choice in decision.choices if choice.caption_type == "manual"
        )

        outcome = runtime.prepare(
            self.request(caption_track=manual_choice.id), prior_evidence=decision
        )
        payload = json.loads(json.dumps(outcome.to_dict()))

        self.assertEqual(outcome.state, "partial")
        self.assertTrue(outcome.terminal)
        self.assertEqual(payload["coverage"]["transcript"], "partial")
        transcript = payload["evidence"]["transcript"]
        self.assertEqual(transcript["provenance"], "manual_captions")
        self.assertEqual(transcript["language"], "en")
        self.assertEqual(
            transcript["available_ranges"],
            [
                {"start_seconds": 0.0, "end_seconds": 4.0},
                {"start_seconds": 5.0, "end_seconds": 6.0},
            ],
        )
        self.assertEqual(
            transcript["unavailable_ranges"],
            [
                {"start_seconds": 4.0, "end_seconds": 5.0},
                {"start_seconds": 6.0, "end_seconds": 10.0},
            ],
        )
        self.assertEqual(
            transcript["segments"],
            [
                {
                    "text": "Hello & welcome",
                    "start_seconds": 0.0,
                    "end_seconds": 2.0,
                },
                {"text": "everyone", "start_seconds": 1.0, "end_seconds": 4.0},
                {"text": "Bye", "start_seconds": 5.0, "end_seconds": 6.0},
            ],
        )
        self.assertNotIn("Hello &amp; welcome", outcome.report_markdown)
        self.assertNotIn("Hello & welcome", outcome.report_markdown)
        self.assertIn("Transcript provenance: `manual_captions`", outcome.report_markdown)
        self.assertIn(
            f"Selected caption track: `{manual_choice.id}`", outcome.report_markdown
        )
        self.assertIn("type `manual`, format `vtt`", outcome.report_markdown)
        self.assertEqual(
            sum(
                "--dump-single-json" in arguments
                for _, arguments in runner.invocations
            ),
            1,
        )
        caption_calls = runner.caption_invocations()
        self.assertEqual(len(caption_calls), 1)
        self.assertIn("--skip-download", caption_calls[0])
        self.assertIn("--write-subs", caption_calls[0])
        self.assertNotIn("--write-auto-subs", caption_calls[0])
        self.assertEqual(
            caption_calls[0][caption_calls[0].index("--sub-langs") + 1], "en"
        )
        self.assertEqual(
            caption_calls[0][caption_calls[0].index("--sub-format") + 1], "vtt"
        )

    def test_sole_automatic_track_finishes_transcript_detail_without_media_download(self) -> None:
        runtime, runner = self.make_runtime(
            captioned_metadata(
                automatic_captions={
                    "en": [{"ext": "vtt", "url": "https://cdn.example/automatic.vtt"}],
                    "live_chat": [{"ext": "json", "url": "https://cdn.example/chat"}],
                },
                duration=2.0,
            ),
            {
                "automatic:en": """WEBVTT

00:00:00.000 --> 00:00:02.000
Automatic caption text
"""
            },
        )

        outcome = runtime.prepare(self.request())
        payload = json.loads(json.dumps(outcome.to_dict()))

        self.assertEqual(outcome.state, "ready")
        self.assertTrue(outcome.terminal)
        self.assertEqual(payload["coverage"]["transcript"], "complete")
        self.assertEqual(payload["coverage"]["overall"], "complete")
        self.assertEqual(
            payload["evidence"]["transcript"]["provenance"], "automatic_captions"
        )
        self.assertNotIn("Automatic caption text", outcome.report_markdown)
        caption_calls = runner.caption_invocations()
        self.assertEqual(len(caption_calls), 1)
        self.assertIn("--skip-download", caption_calls[0])
        self.assertIn("--write-auto-subs", caption_calls[0])
        self.assertNotIn("--write-subs", caption_calls[0])

        runner.invocations.clear()
        reused_inventory_id = outcome.caption_inventory[0].id
        invalid_resume = runtime.prepare(
            self.request(caption_track=reused_inventory_id)
        )
        self.assertEqual(invalid_resume.state, "stopped")
        self.assertEqual(invalid_resume.failure.category, "invalid_selection")
        self.assertEqual(runner.invocations, [])

    def test_one_logical_track_with_vtt_and_ttml_selects_vtt_without_a_choice(self) -> None:
        runtime, runner = self.make_runtime(
            captioned_metadata(
                subtitles={
                    "en": [
                        {"ext": "ttml", "url": "https://cdn.example/manual.ttml"},
                        {"ext": "vtt", "url": "https://cdn.example/manual.vtt"},
                    ]
                },
                duration=1.0,
            ),
            {
                "manual:en:vtt": "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nCaption text\n"
            },
        )

        outcome = runtime.prepare(self.request())

        self.assertEqual(outcome.state, "ready")
        self.assertEqual(
            [
                (item.language, item.caption_type, item.format, item.usable)
                for item in outcome.caption_inventory
            ],
            [("en", "manual", "vtt", True)],
        )
        caption_calls = runner.caption_invocations()
        self.assertEqual(len(caption_calls), 1)
        self.assertEqual(
            caption_calls[0][caption_calls[0].index("--sub-format") + 1], "vtt"
        )

    def test_ttml_and_vtt_tracks_require_choice_and_selected_ttml_normalizes(self) -> None:
        runtime, runner = self.make_runtime(
            captioned_metadata(
                subtitles={"en": [{"ext": "ttml", "url": "https://cdn.example/manual.ttml"}]},
                automatic_captions={
                    "en": [{"ext": "vtt", "url": "https://cdn.example/automatic.vtt"}]
                },
                duration=1.0,
            ),
            {
                "manual:en:ttml": """<?xml version="1.0" encoding="UTF-8"?>
<tt xmlns="http://www.w3.org/ns/ttml"><body><div>
  <p begin="00:00:00.000" end="00:00:01.000">TTML text</p>
</div></body></tt>
""",
                "automatic:en:vtt": "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nUnused\n",
            },
        )

        decision = runtime.prepare(self.request())
        ttml_choice = next(choice for choice in decision.choices if choice.format == "ttml")
        self.assertEqual(decision.state, "decision_required")
        self.assertEqual(runner.caption_invocations(), [])
        outcome = runtime.prepare(
            self.request(caption_track=ttml_choice.id), prior_evidence=decision
        )
        payload = json.loads(json.dumps(outcome.to_dict()))

        self.assertEqual(outcome.state, "ready")
        self.assertEqual(
            [
                (item.caption_type, item.format, item.usable)
                for item in outcome.caption_inventory
            ],
            [("manual", "ttml", True), ("automatic", "vtt", True)],
        )
        self.assertEqual(payload["evidence"]["transcript"]["selected_track"]["format"], "ttml")
        self.assertEqual(
            payload["evidence"]["transcript"]["segments"],
            [{"text": "TTML text", "start_seconds": 0.0, "end_seconds": 1.0}],
        )
        self.assertNotIn("TTML text", outcome.report_markdown)
        self.assertIn("format `ttml`", outcome.report_markdown)
        caption_calls = runner.caption_invocations()
        self.assertEqual(len(caption_calls), 1)
        self.assertIn("--write-subs", caption_calls[0])
        self.assertIn("--skip-download", caption_calls[0])
        self.assertEqual(
            caption_calls[0][caption_calls[0].index("--sub-format") + 1], "ttml"
        )

    def test_ttml_normalizes_nested_text_and_inherited_media_timing(self) -> None:
        runtime, _ = self.make_runtime(
            captioned_metadata(
                subtitles={"en": [{"ext": "ttml", "url": "https://cdn.example/manual.ttml"}]},
                duration=5.0,
            ),
            {
                "manual:en:ttml": """<?xml version="1.0"?>
<tt xmlns="http://www.w3.org/ns/ttml" xmlns:ttp="http://www.w3.org/ns/ttml#parameter" ttp:timeBase="media">
  <body begin="1s"><div begin="500ms" dur="3s">
    <p begin="500ms" dur="1s">Hello <span>world</span><br/>Fish &amp;amp;</p>
  </div></body>
</tt>
"""
            },
        )

        outcome = runtime.prepare(self.request())
        payload = json.loads(json.dumps(outcome.to_dict()))

        self.assertEqual(outcome.state, "partial")
        self.assertEqual(
            payload["evidence"]["transcript"]["segments"],
            [
                {
                    "text": "Hello world Fish &amp;",
                    "start_seconds": 2.0,
                    "end_seconds": 3.0,
                }
            ],
        )
        self.assertEqual(
            payload["evidence"]["transcript"]["available_ranges"],
            [{"start_seconds": 2.0, "end_seconds": 3.0}],
        )
        self.assertNotIn("Hello world", outcome.report_markdown)

    def test_ttml_nested_sequence_advances_to_following_sibling(self) -> None:
        runtime, _ = self.make_runtime(
            captioned_metadata(
                subtitles={"en": [{"ext": "ttml", "url": "https://cdn.example/manual.ttml"}]},
                duration=3.0,
            ),
            {
                "manual:en:ttml": """<tt><body timeContainer="seq">
  <div timeContainer="seq"><p dur="1s">First</p><p dur="1s">Second</p></div>
  <p dur="1s">Third</p>
</body></tt>"""
            },
        )

        outcome = runtime.prepare(self.request())

        self.assertEqual(
            outcome.evidence.transcript.segments,
            (
                TranscriptSegment("First", 0.0, 1.0),
                TranscriptSegment("Second", 1.0, 2.0),
                TranscriptSegment("Third", 2.0, 3.0),
            ),
        )

    def test_ttml_rejects_foreign_timing_namespaces_and_elements(self) -> None:
        runtime, _ = self.make_runtime(
            captioned_metadata(
                subtitles={"en": [{"ext": "ttml", "url": "https://cdn.example/manual.ttml"}]},
                duration=1.0,
            ),
            {
                "manual:en:ttml": """<tt xmlns="http://www.w3.org/ns/ttml" xmlns:bad="urn:bad">
  <body><bad:p begin="0s" end="1s">Foreign cue</bad:p>
  <p bad:begin="9s" begin="0s" end="1s">Trusted cue</p></body>
</tt>"""
            },
        )

        outcome = runtime.prepare(self.request())

        self.assertEqual(
            outcome.evidence.transcript.segments,
            (TranscriptSegment("Trusted cue", 0.0, 1.0),),
        )
        self.assertNotIn("Foreign cue", outcome.report_markdown)

    def test_timed_ttml_span_is_omitted_instead_of_claimed_at_parent_time(self) -> None:
        runtime, _ = self.make_runtime(
            captioned_metadata(
                subtitles={"en": [{"ext": "ttml", "url": "https://cdn.example/manual.ttml"}]},
                duration=2.0,
            ),
            {
                "manual:en:ttml": """<tt><body><div>
  <p begin="0s" end="2s">Before <span begin="1s" end="2s">later words</span></p>
</div></body></tt>"""
            },
        )

        outcome = runtime.prepare(self.request())

        self.assertEqual(outcome.state, "partial")
        self.assertIsNone(outcome.evidence.transcript)
        self.assertEqual(outcome.coverage.transcript, "none")
        self.assertNotIn("later words", outcome.report_markdown)

    def test_sole_automatic_ttml_track_uses_automatic_provenance(self) -> None:
        runtime, runner = self.make_runtime(
            captioned_metadata(
                automatic_captions={
                    "fr": [{"ext": "ttml", "url": "https://cdn.example/automatic.ttml"}]
                },
                duration=1.0,
            ),
            {
                "automatic:fr:ttml": """<tt><body><div>
<p begin="0s" end="1s">Automatic TTML</p>
</div></body></tt>"""
            },
        )

        outcome = runtime.prepare(self.request())
        payload = json.loads(json.dumps(outcome.to_dict()))

        self.assertEqual(outcome.state, "ready")
        self.assertEqual(
            payload["evidence"]["transcript"]["provenance"], "automatic_captions"
        )
        self.assertEqual(
            payload["evidence"]["transcript"]["selected_track"]["format"], "ttml"
        )
        caption_calls = runner.caption_invocations()
        self.assertEqual(len(caption_calls), 1)
        self.assertIn("--write-auto-subs", caption_calls[0])
        self.assertEqual(
            caption_calls[0][caption_calls[0].index("--sub-format") + 1], "ttml"
        )

    def test_unsafe_ttml_is_a_truthful_partial_result(self) -> None:
        runtime, _ = self.make_runtime(
            captioned_metadata(
                subtitles={"en": [{"ext": "ttml", "url": "https://cdn.example/manual.ttml"}]}
            ),
            {
                "manual:en:ttml": """<!DOCTYPE tt [<!ENTITY hidden "not evidence">]>
<tt><body><div><p begin="0s" end="1s">&hidden;</p></div></body></tt>
"""
            },
        )

        outcome = runtime.prepare(self.request())

        self.assertEqual(outcome.state, "partial")
        self.assertIsNone(outcome.evidence.transcript)
        self.assertEqual(outcome.coverage.transcript, "none")
        self.assertIn("could not be parsed", outcome.report_markdown)
        self.assertNotIn("not evidence", outcome.report_markdown)

    def test_unknown_or_wrong_kind_caption_selection_stops_before_any_command(self) -> None:
        runtime, runner = self.make_runtime(
            captioned_metadata(),
            {},
        )

        unknown = runtime.prepare(self.request(caption_track="caption-not-issued"))
        wrong_kind = runtime.prepare(self.request(audio_track="audio-not-issued"))

        self.assertEqual(unknown.state, "stopped")
        self.assertEqual(unknown.failure.category, "invalid_selection")
        self.assertEqual(wrong_kind.state, "stopped")
        self.assertEqual(wrong_kind.failure.category, "invalid_selection")
        self.assertEqual(runner.invocations, [])

    def test_malformed_native_caption_is_a_truthful_partial_result(self) -> None:
        runtime, _ = self.make_runtime(
            captioned_metadata(
                subtitles={"en": [{"ext": "vtt", "url": "https://cdn.example/manual.vtt"}]}
            ),
            {"manual:en": "This is not WebVTT\n"},
        )

        outcome = runtime.prepare(self.request())

        self.assertEqual(outcome.state, "partial")
        self.assertTrue(outcome.terminal)
        self.assertIsNone(outcome.failure)
        self.assertIsNone(outcome.evidence.transcript)
        self.assertEqual(outcome.coverage.transcript, "none")
        self.assertIn("could not be parsed", outcome.report_markdown)
        self.assertNotIn("This is not WebVTT", outcome.report_markdown)

    def test_normalized_raw_transcript_preserves_printable_unicode_and_escapes_only_the_report(self) -> None:
        runtime, _ = self.make_runtime(
            captioned_metadata(
                subtitles={"hi": [{"ext": "vtt", "url": "https://cdn.example/manual.vtt"}]},
                duration=1.0,
            ),
            {
                "manual:hi": """WEBVTT

00:00:00.000 --> 00:00:01.000
<c>“नमस्ते” \\ captions</c>
"""
            },
        )

        outcome = runtime.prepare(self.request())
        payload = json.loads(json.dumps(outcome.to_dict()))

        self.assertEqual(
            payload["evidence"]["transcript"]["segments"][0]["text"],
            "“नमस्ते” \\ captions",
        )
        self.assertNotIn("नमस्ते", outcome.report_markdown)

    def test_exact_rolling_duplicate_retains_the_later_absolute_end_time(self) -> None:
        runtime, _ = self.make_runtime(
            captioned_metadata(
                subtitles={"en": [{"ext": "vtt", "url": "https://cdn.example/manual.vtt"}]},
                duration=2.0,
            ),
            {
                "manual:en": """WEBVTT

00:00:00.000 --> 00:00:01.000
Hello

00:00:01.000 --> 00:00:02.000
Hello
"""
            },
        )

        outcome = runtime.prepare(self.request())

        self.assertEqual(
            outcome.evidence.transcript.segments,
            (TranscriptSegment("Hello", 0.0, 2.0),),
        )

    def test_shorter_rolling_caption_retains_its_later_absolute_time(self) -> None:
        runtime, _ = self.make_runtime(
            captioned_metadata(
                subtitles={"en": [{"ext": "vtt", "url": "https://cdn.example/manual.vtt"}]},
                duration=2.0,
            ),
            {
                "manual:en": """WEBVTT

00:00:00.000 --> 00:00:01.000
Hello world

00:00:01.000 --> 00:00:02.000
Hello
"""
            },
        )

        outcome = runtime.prepare(self.request())

        self.assertEqual(
            outcome.evidence.transcript.segments,
            (
                TranscriptSegment("Hello world", 0.0, 1.0),
                TranscriptSegment("Hello", 1.0, 2.0),
            ),
        )

    def test_focus_without_overlapping_caption_lines_reports_none_not_unavailable_captions(self) -> None:
        runtime, _ = self.make_runtime(
            captioned_metadata(
                subtitles={"en": [{"ext": "vtt", "url": "https://cdn.example/manual.vtt"}]},
                duration=10.0,
            ),
            {
                "manual:en": """WEBVTT

00:00:00.000 --> 00:00:01.000
Outside the requested focus
"""
            },
        )

        outcome = runtime.prepare(self.request(focus=["00:00:05", "00:00:08"]))
        payload = json.loads(json.dumps(outcome.to_dict()))

        self.assertEqual(outcome.state, "partial")
        self.assertEqual(payload["coverage"]["transcript"], "none")
        self.assertEqual(payload["evidence"]["transcript"]["segments"], [])
        self.assertIn("no caption lines overlap the requested focus", outcome.report_markdown)
        self.assertNotIn("captions are unavailable", outcome.report_markdown)

    def test_start_only_focus_excludes_earlier_captions_when_duration_is_unknown(self) -> None:
        runtime, _ = self.make_runtime(
            captioned_metadata(
                subtitles={"en": [{"ext": "vtt", "url": "https://cdn.example/manual.vtt"}]},
                duration=None,
            ),
            {
                "manual:en": """WEBVTT

00:00:00.000 --> 00:00:01.000
Before focus

00:00:05.000 --> 00:00:06.000
Inside focus
"""
            },
        )

        outcome = runtime.prepare(self.request(focus=["00:00:05", None]))
        payload = json.loads(json.dumps(outcome.to_dict()))

        self.assertEqual(outcome.state, "partial")
        self.assertEqual(payload["coverage"]["transcript"], "partial")
        self.assertEqual(
            payload["evidence"]["transcript"]["segments"],
            [{"text": "Inside focus", "start_seconds": 5.0, "end_seconds": 6.0}],
        )
        self.assertEqual(
            payload["evidence"]["transcript"]["available_ranges"],
            [{"start_seconds": 5.0, "end_seconds": 6.0}],
        )
        self.assertEqual(payload["evidence"]["transcript"]["unavailable_ranges"], [])


if __name__ == "__main__":
    unittest.main()
