"""Independently authored offline qualification for Issue #30 H-01 through H-10.

All command, clock, caption-DNS, and caption-HTTP seams below are injected.
No test uses a real URL, DNS lookup, credential, provider, or user workspace.
"""

from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from issue30_support import ROW_IDS
from skill_package_contract import route_watch_invocation


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIRECTORY = REPOSITORY_ROOT / ".agents" / "skills" / "watch" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIRECTORY))

from watch_answer import compose_watch_answer  # noqa: E402
from watch_caption_network import (  # noqa: E402
    BoundedCaptionFetcher,
    CaptionApprovalDecision,
    CaptionApprovalReceiptError,
    CaptionFetchResult,
    CaptionApprovalRegistry,
    CaptionNetworkBinding,
    CaptionNetworkError,
    CaptionOrigin,
    CaptionRedirectApprovalRequired,
    CaptionResponseTooLarge,
    caption_resource,
)
from watch_evidence import CommandResult, WatchEvidenceRuntime  # noqa: E402
from watch_transcription import (  # noqa: E402
    AudioChunkUpload,
    ProviderChunkResult,
    ProviderDescriptor,
)


class OfflineCommandRunner:
    """A deliberately small typed command seam with independent metadata inputs."""

    def __init__(self, *, caption_tracks: int = 0) -> None:
        self.caption_tracks = caption_tracks
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def run(
        self,
        executable: str,
        arguments: object,
        *,
        input_fd: int | None = None,
        output_fd: int | None = None,
    ) -> CommandResult:
        del input_fd, output_fd
        args = tuple(arguments)  # type: ignore[arg-type]
        self.calls.append((executable, args))
        if "-version" in args or "--version" in args:
            return CommandResult(0, f"{Path(executable).name} fixture 1.0\n", "")
        if "--verbose" in args:
            return CommandResult(0, "", "[debug] JS runtimes: none\n")
        if "-show_format" in args:
            return CommandResult(0, json.dumps(_local_metadata()), "")
        if "--dump-single-json" in args:
            return CommandResult(0, json.dumps(_url_metadata(self.caption_tracks)), "")
        raise AssertionError(f"Unexpected offline command: {executable} {args!r}")


class NeverCaptionFetcher:
    def __init__(self) -> None:
        self.calls = 0

    def fetch(self, *_args: object, **_kwargs: object) -> object:
        self.calls += 1
        raise AssertionError("A hermetic test attempted a caption network fetch.")


class MutableClock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


class StaticResolver:
    def __init__(self, addresses: tuple[str, ...]) -> None:
        self.addresses = addresses
        self.calls: list[tuple[str, int]] = []

    def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        self.calls.append((hostname, port))
        return self.addresses


class FixedResponse:
    def __init__(self, status: int, body: bytes, headers: dict[str, str] | None = None) -> None:
        self.status = status
        self.headers = headers or {"Content-Length": str(len(body))}
        self._body = body
        self.closed = False

    def read(self, size: int) -> bytes:
        result, self._body = self._body[:size], self._body[size:]
        return result

    def close(self) -> None:
        self.closed = True


class RecordingTransport:
    def __init__(self, response: FixedResponse) -> None:
        self.response = response
        self.calls: list[tuple[object, tuple[str, ...]]] = []

    def open(self, resource: object, addresses: tuple[str, ...]) -> FixedResponse:
        self.calls.append((resource, addresses))
        return self.response


class SequencedTransport:
    """Controlled HTTP responses with no system transport fallback."""

    def __init__(self, responses: list[FixedResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[object, tuple[str, ...]]] = []

    def open(self, resource: object, addresses: tuple[str, ...]) -> FixedResponse:
        self.calls.append((resource, addresses))
        if not self.responses:
            raise AssertionError("No controlled caption response remained.")
        return self.responses.pop(0)


class WritingCaptionFetcher:
    """A local caption seam that produces deliberately malformed bytes."""

    def __init__(self, body: bytes) -> None:
        self.body = body
        self.calls = 0

    def fetch(self, _resource: object, output_fd: int, *, max_bytes: int) -> CaptionFetchResult:
        self.calls += 1
        if len(self.body) > max_bytes:
            raise AssertionError("The controlled malformed caption exceeded its own bound.")
        os.write(output_fd, self.body)
        return CaptionFetchResult(bytes_read=len(self.body), redirect_count=0)


class ProviderMustNotRun:
    """A future-provider sentinel; caption failure must not reach it."""

    descriptor = ProviderDescriptor(
        provider="openai",
        model="offline-sentinel",
        destination="https://provider.example.test/transcribe",
        privacy_url="https://provider.example.test/privacy",
        max_chunk_bytes=1024,
        max_encoded_request_bytes=2048,
    )

    def __init__(self) -> None:
        self.calls = 0

    def transcribe_chunk(self, _upload: AudioChunkUpload) -> ProviderChunkResult:
        self.calls += 1
        raise AssertionError("A native-caption failure attempted provider fallback.")


def _local_metadata() -> dict[str, object]:
    return {
        "format": {"duration": "12", "format_name": "mov,mp4"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1024,
                "height": 576,
                "sample_aspect_ratio": "1:1",
                "display_aspect_ratio": "16:9",
            }
        ],
    }


def _url_metadata(caption_tracks: int) -> dict[str, object]:
    subtitles = {
        "en": [
            {
                "ext": "vtt",
                "url": "https://captions.example.test/en.vtt?signature=offline-secret",
            }
        ]
    }
    if caption_tracks == 2:
        subtitles["fr"] = [
            {
                "ext": "vtt",
                "url": "https://captions.example.test/fr.vtt?signature=offline-secret",
            }
        ]
    return {
        "_type": "video",
        "duration": 12,
        "title": "Offline fixture",
        "uploader": "fixture",
        "vcodec": "h264",
        "acodec": "aac",
        "width": 1024,
        "height": 576,
        "is_live": False,
        "subtitles": subtitles,
    }


def _offline_tools(name: str) -> str | None:
    return f"/offline/{name}" if name in {"yt-dlp", "ffmpeg", "ffprobe"} else None


def _binding() -> CaptionNetworkBinding:
    return CaptionNetworkBinding(
        action="native_caption_retrieval",
        watch_request_id="request-30",
        source_value="https://video.example.test/watch?id=30",
        session_id="session-30",
        workspace_id="workspace-30",
        selected_track_id="caption-30",
        selected_format="vtt",
        byte_cap=1024,
        origin=CaptionOrigin("captions.example.test"),
    )


class Issue30HermeticQualificationTests(unittest.TestCase):
    def test_h01_input_and_trigger_refusal_stops_before_runtime_side_effects(self) -> None:
        self.assertEqual(ROW_IDS[:2], ("H-01", "H-02"))
        self.assertEqual(
            route_watch_invocation("$watch https://video.example.test/a", source_count=1).route,
            "explicit",
        )
        self.assertEqual(
            route_watch_invocation(
                "Please summarize this video", source_count=1
            ).route,
            "implicit",
        )
        for request, count, state in (
            ("download this video", 1, "supported"),
            ("summarize the videos", 2, "supported"),
            ("summarize this private video", 1, "unsupported"),
        ):
            self.assertEqual(
                route_watch_invocation(request, source_count=count, source_state=state).route,
                "none",
            )

        runner = OfflineCommandRunner()
        runtime = WatchEvidenceRuntime(
            command_runner=runner,
            find_executable=_offline_tools,
            visual_enabled=False,
        )
        try:
            for sources in ([], ["one.mp4", "two.mp4"]):
                outcome = runtime.prepare({"sources": sources})
                self.assertEqual(outcome.state, "stopped")
                self.assertEqual(outcome.failure.category, "source_count")  # type: ignore[union-attr]
            credentialed = runtime.prepare(
                {"sources": ["https://user:pass@video.example.test/a"]}
            )
        finally:
            runtime.close()
        self.assertEqual(credentialed.failure.category, "unsupported_access")  # type: ignore[union-attr]
        self.assertEqual(runner.calls, [])

    def test_h02_adapter_arguments_keep_hostile_sources_as_one_data_value(self) -> None:
        runner = OfflineCommandRunner()
        fetcher = NeverCaptionFetcher()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "-local source $(not-a-command).mp4"
            source.write_bytes(b"local fixture")
            runtime = WatchEvidenceRuntime(
                command_runner=runner,
                caption_fetcher=fetcher,
                find_executable=_offline_tools,
                visual_enabled=False,
                artifact_root=Path(directory) / "runtime",
            )
            try:
                local_outcome = runtime.prepare(
                    {"sources": [str(source)], "detail": "transcript"}
                )
                url = "https://video.example.test/watch?q=one%20value&literal=$(nope)"
                url_outcome = runtime.prepare(
                    {
                        "sources": [url],
                        "detail": "transcript",
                        "source_network_approved": True,
                    }
                )
            finally:
                runtime.close()

        self.assertEqual(local_outcome.state, "partial")
        self.assertEqual(url_outcome.state, "decision_required")
        local_call = next(args for executable, args in runner.calls if executable.endswith("ffprobe") and "-show_format" in args)
        self.assertEqual(local_call[-1], str(source.resolve()))
        url_call = next(args for executable, args in runner.calls if executable.endswith("yt-dlp") and "--dump-single-json" in args)
        self.assertEqual(url_call[url_call.index("--") + 1], url)
        self.assertEqual(url_call.count(url), 1)
        self.assertEqual(fetcher.calls, 0)

    def test_h03_missing_tool_has_typed_guidance_without_an_installer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "fixture.mp4"
            source.write_bytes(b"fixture")
            runner = OfflineCommandRunner()
            runtime = WatchEvidenceRuntime(
                command_runner=runner,
                find_executable=lambda _name: None,
                visual_enabled=False,
            )
            try:
                outcome = runtime.prepare({"sources": [str(source)]})
            finally:
                runtime.close()
        self.assertEqual(outcome.state, "failed")
        self.assertEqual(outcome.failure.category, "missing_dependency")  # type: ignore[union-attr]
        self.assertIn("Install it deliberately", outcome.failure.message)  # type: ignore[union-attr]
        self.assertEqual(runner.calls, [])

    def test_h04_controls_reject_before_io_and_transcript_selects_zero_ordinary_frames(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "fixture.mp4"
            source.write_bytes(b"fixture")
            runner = OfflineCommandRunner()
            runtime = WatchEvidenceRuntime(
                command_runner=runner,
                find_executable=_offline_tools,
                artifact_root=Path(directory) / "runtime",
            )
            try:
                invalid = runtime.prepare(
                    {"sources": [str(source)], "detail": "unbounded"}
                )
                invalid_calls = tuple(runner.calls)
                transcript = runtime.prepare(
                    {"sources": [str(source)], "detail": "transcript"}
                )
            finally:
                runtime.close()
        self.assertEqual(invalid.state, "stopped")
        self.assertEqual(invalid.failure.category, "invalid_detail")  # type: ignore[union-attr]
        self.assertEqual(invalid_calls, ())
        visual = transcript.evidence.visual  # type: ignore[union-attr]
        self.assertEqual(visual.ordinary_frame_cap, 0)
        self.assertEqual(visual.frames, ())

    def test_h05_opaque_track_choice_requires_one_valid_same_task_selection(self) -> None:
        runner = OfflineCommandRunner(caption_tracks=2)
        fetcher = NeverCaptionFetcher()
        runtime = WatchEvidenceRuntime(
            command_runner=runner,
            caption_fetcher=fetcher,
            find_executable=_offline_tools,
            visual_enabled=False,
        )
        request = {
            "sources": ["https://video.example.test/watch?id=30"],
            "detail": "transcript",
            "source_network_approved": True,
        }
        try:
            choice = runtime.prepare(request)
            calls_before_invalid = tuple(runner.calls)
            invalid = runtime.prepare(
                {**request, "caption_track": "unknown-choice"}, prior_evidence=choice
            )
            selected = runtime.prepare(
                {**request, "caption_track": choice.choices[0].id}, prior_evidence=choice
            )
        finally:
            runtime.close()
        self.assertEqual(choice.state, "decision_required")
        self.assertEqual(choice.choice_kind, "caption_track")
        self.assertEqual(len(choice.choices), 2)
        self.assertEqual(invalid.state, "stopped")
        self.assertEqual(invalid.failure.category, "invalid_selection")  # type: ignore[union-attr]
        self.assertEqual(tuple(runner.calls[: len(calls_before_invalid)]), calls_before_invalid)
        self.assertEqual(selected.state, "decision_required")
        self.assertEqual(selected.choice_kind, "caption_network")
        self.assertEqual(fetcher.calls, 0)

    def test_h05_focus_and_cue_controls_are_normalized_or_refused_before_new_io(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "fixture.mp4"
            source.write_bytes(b"fixture")
            runner = OfflineCommandRunner()
            runtime = WatchEvidenceRuntime(
                command_runner=runner,
                find_executable=_offline_tools,
                visual_enabled=False,
                artifact_root=Path(directory) / "runtime",
            )
            try:
                accepted = runtime.prepare(
                    {
                        "sources": [str(source)],
                        "detail": "transcript",
                        "focus": ["00:01", "00:04"],
                        "cues": [3, "00:02", 3],
                    }
                )
                calls_before_refusals = tuple(runner.calls)
                invalid_focus = runtime.prepare(
                    {
                        "sources": [str(source)],
                        "detail": "transcript",
                        "focus": [5, 2],
                    }
                )
                invalid_cues = runtime.prepare(
                    {
                        "sources": [str(source)],
                        "detail": "transcript",
                        "cues": ["not-a-timestamp"],
                    }
                )
            finally:
                runtime.close()

        self.assertEqual(accepted.controls.focus_start_seconds, 1)  # type: ignore[union-attr]
        self.assertEqual(accepted.controls.focus_end_seconds, 4)  # type: ignore[union-attr]
        self.assertEqual(accepted.controls.cues_seconds, (2, 3))  # type: ignore[union-attr]
        self.assertEqual(invalid_focus.failure.category, "invalid_focus")  # type: ignore[union-attr]
        self.assertEqual(invalid_cues.failure.category, "invalid_cues")  # type: ignore[union-attr]
        self.assertEqual(tuple(runner.calls), calls_before_refusals)

    def test_h06_answer_compiler_keeps_conflicting_streams_and_derived_times_separate(self) -> None:
        outcome = {
            "state": "partial",
            "coverage": {
                "metadata": "complete",
                "transcript": "complete",
                "visual": "partial",
                "overall": "partial",
            },
            "evidence": {
                "metadata": {"title": "offline fixture"},
                "transcript": {
                    "provenance": "manual_captions",
                    "segments": [
                        {
                            "text": "The panel is green.",
                            "start_seconds": 10.0,
                            "end_seconds": 12.0,
                        }
                    ],
                },
                "visual": {
                    "frames": [
                        {
                            "timestamp_seconds": 11.0,
                            "chronological_position": 1,
                            "selection_reason": "scene",
                            "path": "/opaque/frame-001.jpg",
                            "format": "jpeg",
                            "width": 768,
                            "height": 432,
                            "inspected": True,
                            "resolution_reason": None,
                        }
                    ],
                    "inspection_state": "complete",
                },
            },
            "warnings": ["<untrusted>"],
        }
        answer = compose_watch_answer(
            {
                "outcome": outcome,
                "question": "Do the visible and spoken colors agree?",
                "answerability": "uncertain",
                "relevant_streams": ["transcript", "visual"],
                "visual_observations": [
                    {
                        "id": "seen-frame",
                        "frame_position": 1,
                        "description": "The visible panel is red.",
                    }
                ],
                "claims": [
                    {
                        "id": "spoken",
                        "text": "The transcript calls the panel green.",
                        "evidence": [{"stream": "transcript", "segment": 1}],
                    },
                    {
                        "id": "visible",
                        "text": "The visible panel is red.",
                        "evidence": [{"stream": "visual", "observation": "seen-frame"}],
                    },
                ],
                "conflicts": [{"left_claim": "spoken", "right_claim": "visible"}],
            }
        )
        self.assertEqual(answer.state, "answered")
        self.assertEqual(answer.answerability, "uncertain")
        self.assertEqual([citation.stream for citation in answer.citations], ["transcript", "visual"])
        self.assertIn("00:10–00:12", answer.markdown)
        self.assertIn("00:11", answer.markdown)
        self.assertNotIn("<untrusted>", answer.markdown)

    def test_h07_typed_cancellation_and_failure_do_not_emit_evidence_conclusions(self) -> None:
        runner = OfflineCommandRunner(caption_tracks=1)
        fetcher = NeverCaptionFetcher()
        runtime = WatchEvidenceRuntime(
            command_runner=runner,
            caption_fetcher=fetcher,
            find_executable=_offline_tools,
            visual_enabled=False,
        )
        request = {
            "sources": ["https://video.example.test/watch?id=30"],
            "detail": "transcript",
            "source_network_approved": True,
        }
        try:
            pending = runtime.prepare(request)
            calls_before_cancellation = tuple(runner.calls)
            outcome = runtime.prepare(
                {
                    **request,
                    "caption_network_approval": {
                        "receipt": pending.caption_network_approval.receipt,
                        "decision": "canceled",
                    },
                },
                prior_evidence=pending,
            )
        finally:
            runtime.close()
        self.assertEqual(outcome.state, "canceled")
        self.assertTrue(outcome.terminal)
        self.assertEqual(tuple(runner.calls), calls_before_cancellation)
        self.assertEqual(fetcher.calls, 0)
        withheld = compose_watch_answer(
            {
                "outcome": outcome.to_dict(),
                "answerability": "unsupported",
                "relevant_streams": [],
                "claims": [],
            }
        )
        self.assertEqual(withheld.state, "withheld")
        self.assertNotIn("The panel", withheld.markdown)

    def test_h08_opaque_reuse_skips_new_commands_and_invalid_cleanup_revokes_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "fixture.mp4"
            source.write_bytes(b"fixture")
            runner = OfflineCommandRunner()
            runtime = WatchEvidenceRuntime(
                command_runner=runner,
                find_executable=_offline_tools,
                visual_enabled=False,
                reuse_enabled=True,
                artifact_root=Path(directory) / "runtime",
            )
            try:
                first = runtime.prepare({"sources": [str(source)], "detail": "transcript"})
                calls_after_first = tuple(runner.calls)
                reused = runtime.prepare(
                    {"sources": [str(source)]},
                    prior_evidence={"evidence_handle": first.evidence_handle},
                )
                invalid_cleanup = runtime.cleanup("not-a-workspace-id")
            finally:
                runtime.close()
        self.assertEqual(reused.to_dict(), first.to_dict())
        self.assertEqual(tuple(runner.calls), calls_after_first)
        self.assertEqual(invalid_cleanup.state, "cleanup_refused")
        self.assertEqual(invalid_cleanup.disposition.reuse_state, "none")

    def test_h09_receipts_bind_all_fields_and_rejected_followups_do_zero_fetches(self) -> None:
        binding = _binding()
        substitutions = {
            "action": "different_action",
            "watch_request_id": "other-request",
            "source_value": "https://video.example.test/other",
            "session_id": "other-session",
            "workspace_id": "other-workspace",
            "selected_track_id": "other-track",
            "selected_format": "ttml",
            "byte_cap": 2048,
            "origin": CaptionOrigin("other-captions.example.test"),
        }
        for field, value in substitutions.items():
            with self.subTest(field=field):
                clock = MutableClock()
                registry = CaptionApprovalRegistry(
                    clock=clock, receipt_factory=lambda: "receipt-30"
                )
                approval = registry.issue(binding)
                decision = CaptionApprovalDecision(approval.receipt, "approved")
                with self.assertRaises(CaptionApprovalReceiptError) as rejected:
                    registry.verify_and_consume(decision, replace(binding, **{field: value}))
                self.assertEqual(rejected.exception.code, "invalid_receipt")
                with self.assertRaises(CaptionApprovalReceiptError):
                    registry.verify_and_consume(decision, binding)

        clock = MutableClock()
        registry = CaptionApprovalRegistry(clock=clock, receipt_factory=lambda: "expiry")
        expired = registry.issue(binding)
        clock.value += 300
        with self.assertRaises(CaptionApprovalReceiptError) as expired_error:
            registry.verify_and_consume(
                CaptionApprovalDecision(expired.receipt, "approved"), binding
            )
        self.assertEqual(expired_error.exception.code, "expired_receipt")

        invalidated = registry.issue(binding)
        registry.invalidate_workspace(binding.workspace_id)
        with self.assertRaises(CaptionApprovalReceiptError):
            registry.verify_and_consume(
                CaptionApprovalDecision(invalidated.receipt, "approved"), binding
            )

        runner = OfflineCommandRunner(caption_tracks=1)
        fetcher = NeverCaptionFetcher()
        runtime = WatchEvidenceRuntime(
            command_runner=runner,
            caption_fetcher=fetcher,
            find_executable=_offline_tools,
            visual_enabled=False,
        )
        request = {
            "sources": ["https://video.example.test/watch?id=30"],
            "detail": "transcript",
            "source_network_approved": True,
        }
        try:
            prompt = runtime.prepare(request)
            calls_before_rejection = tuple(runner.calls)
            rejected = runtime.prepare(
                {
                    **request,
                    "caption_network_approval": {
                        "receipt": "forged-receipt",
                        "decision": "approved",
                    },
                },
                prior_evidence=prompt,
            )
        finally:
            runtime.close()
        self.assertEqual(prompt.choice_kind, "caption_network")
        self.assertEqual(rejected.failure.category, "caption_approval_invalid")  # type: ignore[union-attr]
        self.assertEqual(fetcher.calls, 0)
        self.assertEqual(tuple(runner.calls), calls_before_rejection)

    def test_h09_fake_public_resolver_pins_answers_and_rejects_nonpublic_answers(self) -> None:
        resolver = StaticResolver(("8.8.8.8", "2606:4700:4700::1111"))
        transport = SequencedTransport([FixedResponse(200, b"WEBVTT\n")])
        fetcher = BoundedCaptionFetcher(resolver=resolver, transport=transport)
        with tempfile.TemporaryFile() as output:
            result = fetcher.fetch(
                caption_resource("https://captions.example.test/a.vtt?signature=private"),
                output.fileno(),
                max_bytes=1024,
            )
        self.assertEqual(result.bytes_read, len(b"WEBVTT\n"))
        self.assertEqual(resolver.calls, [("captions.example.test", 443)])
        self.assertEqual(transport.calls[0][1], ("8.8.8.8", "2606:4700:4700::1111"))
        self.assertNotIn("signature=private", repr(transport.calls[0][0]))
        with self.assertRaises(CaptionNetworkError) as unsafe_url:
            caption_resource("http://127.0.0.1/private.vtt?signature=private")
        self.assertEqual(unsafe_url.exception.code, "unsafe_url")
        self.assertNotIn("signature=private", str(unsafe_url.exception))

        for addresses in (("10.0.0.1",), ("8.8.8.8", "10.0.0.1")):
            with self.subTest(addresses=addresses):
                blocked_transport = SequencedTransport([])
                blocked_fetcher = BoundedCaptionFetcher(
                    resolver=StaticResolver(addresses), transport=blocked_transport
                )
                with tempfile.TemporaryFile() as output:
                    with self.assertRaises(CaptionNetworkError) as unsafe:
                        blocked_fetcher.fetch(
                            caption_resource("https://captions.example.test/blocked.vtt"),
                            output.fileno(),
                            max_bytes=1024,
                        )
                self.assertEqual(unsafe.exception.code, "unsafe_destination")
                self.assertEqual(blocked_transport.calls, [])

    def test_h09_redirects_reresolve_and_cross_origin_pauses_before_second_connect(self) -> None:
        resolver = StaticResolver(("8.8.8.8",))
        transport = SequencedTransport(
            [
                FixedResponse(302, b"", {"Location": "/next.vtt"}),
                FixedResponse(200, b"WEBVTT\n"),
            ]
        )
        fetcher = BoundedCaptionFetcher(resolver=resolver, transport=transport)
        with tempfile.TemporaryFile() as output:
            result = fetcher.fetch(
                caption_resource("https://captions.example.test/start.vtt"),
                output.fileno(),
                max_bytes=1024,
            )
        self.assertEqual(result.redirect_count, 1)
        self.assertEqual(resolver.calls, [("captions.example.test", 443)] * 2)
        self.assertEqual(len(transport.calls), 2)

        cross_origin_resolver = StaticResolver(("8.8.8.8",))
        cross_origin_transport = SequencedTransport(
            [
                FixedResponse(
                    302,
                    b"",
                    {"Location": "https://other-captions.example.test/next.vtt?secret=hidden"},
                )
            ]
        )
        cross_origin_fetcher = BoundedCaptionFetcher(
            resolver=cross_origin_resolver, transport=cross_origin_transport
        )
        with tempfile.TemporaryFile() as output:
            with self.assertRaises(CaptionRedirectApprovalRequired) as paused:
                cross_origin_fetcher.fetch(
                    caption_resource("https://captions.example.test/start.vtt"),
                    output.fileno(),
                    max_bytes=1024,
                )
        self.assertEqual(paused.exception.resource.origin.hostname, "other-captions.example.test")
        self.assertNotIn("secret=hidden", str(paused.exception))
        self.assertEqual(len(cross_origin_transport.calls), 1)
        self.assertEqual(
            cross_origin_resolver.calls,
            [("captions.example.test", 443), ("other-captions.example.test", 443)],
        )

    def test_h09_byte_eof_and_caption_format_failures_are_typed_without_provider_fallback(self) -> None:
        exact_fetcher = BoundedCaptionFetcher(
            resolver=StaticResolver(("8.8.8.8",)),
            transport=SequencedTransport([FixedResponse(200, b"12345678")]),
        )
        with tempfile.TemporaryFile() as output:
            result = exact_fetcher.fetch(
                caption_resource("https://captions.example.test/exact.vtt"),
                output.fileno(),
                max_bytes=8,
            )
            output.seek(0)
            self.assertEqual(output.read(), b"12345678")
        self.assertEqual(result.bytes_read, 8)

        for body, header, expected_error in (
            (b"123456789", "8", CaptionResponseTooLarge),
            (b"short", "8", CaptionNetworkError),
        ):
            with self.subTest(body=body):
                fetcher = BoundedCaptionFetcher(
                    resolver=StaticResolver(("8.8.8.8",)),
                    transport=SequencedTransport(
                        [FixedResponse(200, body, {"Content-Length": header})]
                    ),
                )
                with tempfile.TemporaryFile() as output:
                    with self.assertRaises(expected_error) as rejected:
                        fetcher.fetch(
                            caption_resource("https://captions.example.test/bounded.vtt"),
                            output.fileno(),
                            max_bytes=8,
                        )
                self.assertEqual(
                    rejected.exception.code,
                    "response_too_large" if expected_error is CaptionResponseTooLarge else "transport_failure",
                )

        provider = ProviderMustNotRun()
        malformed_fetcher = WritingCaptionFetcher(b"not a valid VTT payload")
        runtime = WatchEvidenceRuntime(
            command_runner=OfflineCommandRunner(caption_tracks=1),
            caption_fetcher=malformed_fetcher,
            find_executable=_offline_tools,
            visual_enabled=False,
            transcription_providers={"openai": provider},
        )
        request = {
            "sources": ["https://video.example.test/watch?id=30"],
            "detail": "transcript",
            "source_network_approved": True,
        }
        try:
            prompt = runtime.prepare(request)
            malformed = runtime.prepare(
                {
                    **request,
                    "caption_network_approval": {
                        "receipt": prompt.caption_network_approval.receipt,
                        "decision": "approved",
                    },
                },
                prior_evidence=prompt,
            )
        finally:
            runtime.close()
        self.assertEqual(malformed.state, "partial")
        self.assertEqual(malformed.failure.category, "caption_parse")  # type: ignore[union-attr]
        self.assertEqual(malformed.caption_network_audit.status, "parse_failed")  # type: ignore[union-attr]
        self.assertIsNone(malformed.choice_kind)
        self.assertEqual(malformed_fetcher.calls, 1)
        self.assertEqual(provider.calls, 0)
        self.assertNotIn("offline-secret", malformed.report_markdown)

    def test_h10_cleanup_refuses_untrusted_selector_and_preserves_caller_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "fixture.mp4"
            caller_output = root / "caller-output.txt"
            source.write_bytes(b"fixture")
            caller_output.write_text("must remain", encoding="utf-8")
            runtime = WatchEvidenceRuntime(
                command_runner=OfflineCommandRunner(),
                find_executable=_offline_tools,
                visual_enabled=False,
                reuse_enabled=True,
                artifact_root=root / "runtime",
            )
            try:
                outcome = runtime.prepare({"sources": [str(source)], "detail": "transcript"})
                refused = runtime.cleanup("../caller-output.txt")
                explicit = runtime.cleanup("current")
            finally:
                runtime.close()
            self.assertTrue(caller_output.exists())
            self.assertEqual(caller_output.read_text(encoding="utf-8"), "must remain")
        self.assertEqual(outcome.disposition.reuse_state, "same_task_evidence")
        self.assertEqual(refused.state, "cleanup_refused")
        self.assertEqual(explicit.state, "cleanup_incomplete")
        self.assertEqual(explicit.disposition.reuse_state, "revoked")

    def test_h10_invalid_selectors_refuse_without_touching_current_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "caller-source.mp4"
            caller_output = root / "caller-output.txt"
            source.write_bytes(b"caller source")
            caller_output.write_text("caller output", encoding="utf-8")
            runner = OfflineCommandRunner()
            runtime = WatchEvidenceRuntime(
                command_runner=runner,
                find_executable=_offline_tools,
                visual_enabled=False,
                reuse_enabled=True,
                artifact_root=root / "runtime",
            )
            try:
                initial = runtime.prepare({"sources": [str(source)], "detail": "transcript"})
                calls_before_cleanup = tuple(runner.calls)
                for selector in (
                    "../caller-output.txt",
                    str(caller_output),
                    object(),
                    "workspace_" + "a" * 24,
                ):
                    with self.subTest(selector=repr(selector)):
                        refused = runtime.cleanup(selector)
                        self.assertEqual(refused.state, "cleanup_refused")
                        self.assertEqual(tuple(runner.calls), calls_before_cleanup)
                        self.assertTrue(source.is_file())
                        self.assertEqual(
                            caller_output.read_text(encoding="utf-8"), "caller output"
                        )
                reused = runtime.prepare(
                    {"sources": [str(source)]},
                    prior_evidence={"evidence_handle": initial.evidence_handle},
                )
            finally:
                runtime.close()

        self.assertEqual(reused.to_dict(), initial.to_dict())
        self.assertEqual(tuple(runner.calls), calls_before_cleanup)

    def test_h10_control_and_leaf_tampering_refuses_and_revokes_reuse(self) -> None:
        mutators = {
            "marker_contents": lambda workspace, _source: (
                workspace / ".codex-watch-workspace.json"
            ).write_text('{"tampered": true}\n', encoding="utf-8"),
            "manifest_append": lambda workspace, _source: (
                workspace / ".codex-watch-manifest.jsonl"
            ).write_text(
                (workspace / ".codex-watch-manifest.jsonl").read_text(encoding="utf-8")
                + '{"tampered": true}\n',
                encoding="utf-8",
            ),
            "lock_contents": lambda workspace, _source: (
                workspace / ".codex-watch.lock"
            ).write_text("other-workspace\n", encoding="utf-8"),
            "unexpected_symlink": lambda workspace, source: (
                workspace / "untrusted-link"
            ).symlink_to(source),
            "marker_hardlink": lambda workspace, _source: os.link(
                workspace / ".codex-watch-workspace.json",
                workspace / "marker-hardlink",
            ),
        }
        for name, mutate in mutators.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / "caller-source.mp4"
                caller_output = root / "caller-output.txt"
                source.write_bytes(b"caller source")
                caller_output.write_text("caller output", encoding="utf-8")
                runner = OfflineCommandRunner()
                runtime = WatchEvidenceRuntime(
                    command_runner=runner,
                    find_executable=_offline_tools,
                    visual_enabled=False,
                    reuse_enabled=True,
                    artifact_root=root / "runtime",
                )
                try:
                    initial = runtime.prepare(
                        {"sources": [str(source)], "detail": "transcript"}
                    )
                    workspace = root / "runtime" / initial.workspace_id
                    calls_before_tamper = tuple(runner.calls)
                    mutate(workspace, source)
                    refused = runtime.cleanup("current")
                    stale = runtime.prepare(
                        {"sources": [str(source)]},
                        prior_evidence={"evidence_handle": initial.evidence_handle},
                    )
                finally:
                    runtime.close()

                self.assertEqual(refused.state, "cleanup_refused")
                self.assertTrue(workspace.exists())
                self.assertTrue(source.is_file())
                self.assertEqual(caller_output.read_text(encoding="utf-8"), "caller output")
                self.assertEqual(stale.failure.category, "evidence_disposed")  # type: ignore[union-attr]
                self.assertEqual(tuple(runner.calls), calls_before_tamper)

    def test_h10_identity_and_ancestor_replacements_refuse_without_deletion(self) -> None:
        scenarios = ("ordinary_replacement", "workspace_symlink", "ancestor_symlink")
        for scenario in scenarios:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / "caller-source.mp4"
                source.write_bytes(b"caller source")
                runtime = WatchEvidenceRuntime(
                    command_runner=OfflineCommandRunner(),
                    find_executable=_offline_tools,
                    visual_enabled=False,
                    artifact_root=root / "runtime",
                )
                try:
                    initial = runtime.prepare(
                        {"sources": [str(source)], "detail": "transcript"}
                    )
                    runtime_root = root / "runtime"
                    workspace = runtime_root / initial.workspace_id
                    moved_workspace = root / "moved-workspace"
                    user_directory = root / "user-directory"
                    user_directory.mkdir()
                    user_sentinel = user_directory / "do-not-delete.txt"
                    user_sentinel.write_text("caller owned", encoding="utf-8")
                    if scenario == "ordinary_replacement":
                        workspace.rename(moved_workspace)
                        workspace.mkdir()
                        replacement_sentinel = workspace / "replacement.txt"
                        replacement_sentinel.write_text("caller owned", encoding="utf-8")
                    elif scenario == "workspace_symlink":
                        workspace.rename(moved_workspace)
                        workspace.symlink_to(user_directory, target_is_directory=True)
                        replacement_sentinel = user_sentinel
                    else:
                        runtime_root.rename(root / "moved-runtime-root")
                        runtime_root.symlink_to(user_directory, target_is_directory=True)
                        moved_workspace = root / "moved-runtime-root" / initial.workspace_id
                        replacement_sentinel = user_sentinel
                    refused = runtime.cleanup("current")
                finally:
                    runtime.close()

                self.assertEqual(refused.state, "cleanup_refused")
                self.assertTrue(moved_workspace.is_dir())
                self.assertTrue(source.is_file())
                self.assertEqual(user_sentinel.read_text(encoding="utf-8"), "caller owned")
                self.assertEqual(
                    replacement_sentinel.read_text(encoding="utf-8"), "caller owned"
                )

    def test_h10_valid_owned_workspace_is_fail_closed_on_macos(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_source = root / "first-source.mp4"
            second_source = root / "second-source.mp4"
            caller_output = root / "caller-output.txt"
            first_source.write_bytes(b"first caller source")
            second_source.write_bytes(b"second caller source")
            caller_output.write_text("caller output", encoding="utf-8")
            runner = OfflineCommandRunner()
            runtime = WatchEvidenceRuntime(
                command_runner=runner,
                find_executable=_offline_tools,
                visual_enabled=False,
                reuse_enabled=True,
                artifact_root=root / "runtime",
            )
            try:
                first = runtime.prepare({"sources": [str(first_source)], "detail": "transcript"})
                second = runtime.prepare({"sources": [str(second_source)], "detail": "transcript"})
                first_workspace = root / "runtime" / first.workspace_id
                second_workspace = root / "runtime" / second.workspace_id
                calls_before_cleanup = tuple(runner.calls)
                result = runtime.cleanup(first.workspace_id)
                stale = runtime.prepare(
                    {"sources": [str(first_source)]},
                    prior_evidence={"evidence_handle": first.evidence_handle},
                )
            finally:
                runtime.close()

            self.assertEqual(result.state, "cleanup_incomplete")
            self.assertEqual(result.disposition.reuse_state, "revoked")
            self.assertTrue(first_workspace.is_dir())
            self.assertTrue(second_workspace.is_dir())
            self.assertTrue(first_source.is_file())
            self.assertTrue(second_source.is_file())
            self.assertEqual(caller_output.read_text(encoding="utf-8"), "caller output")
            self.assertEqual(stale.failure.category, "evidence_disposed")  # type: ignore[union-attr]
            self.assertEqual(tuple(runner.calls), calls_before_cleanup)


if __name__ == "__main__":
    unittest.main()
