from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
from typing import Sequence
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIRECTORY = REPOSITORY_ROOT / ".agents" / "skills" / "watch" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIRECTORY))

from watch_evidence import (  # noqa: E402
    CommandResult,
    MetadataEvidence,
    TranscriptSegment,
    WatchEvidenceRuntime,
    _SourceProbe,
    _caption_candidates_from_ytdlp,
)
from watch_caption_network import (  # noqa: E402
    BoundedCaptionFetcher,
    CaptionNetworkError,
    CaptionRedirectApprovalRequired,
    CaptionResource,
    CaptionResponseTooLarge,
    CaptionUnavailable,
    caption_resource,
)
from watch_transcription import ProviderDescriptor  # noqa: E402


class CaptionRunner:
    def __init__(self, metadata: dict[str, object], caption_bodies: dict[str, str]) -> None:
        self.metadata = metadata
        self.caption_bodies = caption_bodies
        self.invocations: list[tuple[str, list[str]]] = []
        self.caption_fetches: list[str] = []
        self.caption_resource_reprs: list[str] = []

    def run(
        self,
        executable: str,
        arguments: Sequence[str],
        *,
        input_fd: int | None = None,
        output_fd: int | None = None,
    ) -> CommandResult:
        del input_fd, output_fd
        copied_arguments = list(arguments)
        self.invocations.append((executable, copied_arguments))
        if "--version" in copied_arguments or "-version" in copied_arguments:
            return CommandResult(0, "2026.08.12\n", "")
        if "--verbose" in copied_arguments:
            return CommandResult(1, "", "[debug] JS runtimes: node-24.10.0\n")
        if "--dump-single-json" in copied_arguments:
            return CommandResult(0, json.dumps(self.metadata), "")

        return CommandResult(1, "", "Unexpected command")

    def fetch(self, resource: CaptionResource, output_fd: int, *, max_bytes: int) -> None:
        self.caption_resource_reprs.append(repr(resource))
        url = resource._url
        catalogues = (
            ("manual", self.metadata.get("subtitles")),
            ("automatic", self.metadata.get("automatic_captions")),
        )
        for caption_type, catalogue in catalogues:
            if not isinstance(catalogue, dict):
                continue
            for language, entries in catalogue.items():
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if not isinstance(entry, dict) or entry.get("url") != url:
                        continue
                    caption_format = entry["ext"]
                    caption_body = self.caption_bodies.get(
                        f"{caption_type}:{language}:{caption_format}"
                    )
                    if caption_body is None:
                        caption_body = self.caption_bodies[f"{caption_type}:{language}"]
                    payload = caption_body.encode("utf-8")
                    if len(payload) > max_bytes:
                        raise OSError("Fixture caption exceeds the safe limit.")
                    while payload:
                        written = os.write(output_fd, payload)
                        payload = payload[written:]
                    self.caption_fetches.append(url)
                    return
        raise OSError("Unexpected caption URL")

    def caption_invocations(self) -> list[str]:
        return self.caption_fetches


class MetadataFailureRunner(CaptionRunner):
    def __init__(self, diagnostic: str) -> None:
        super().__init__(captioned_metadata(), {})
        self.diagnostic = diagnostic

    def run(
        self,
        executable: str,
        arguments: Sequence[str],
        *,
        input_fd: int | None = None,
        output_fd: int | None = None,
    ) -> CommandResult:
        if "--dump-single-json" in arguments:
            self.invocations.append((executable, list(arguments)))
            return CommandResult(1, "", self.diagnostic)
        return super().run(
            executable, arguments, input_fd=input_fd, output_fd=output_fd
        )


class CaptionVisualRunner(CaptionRunner):
    """Hermetic source-media and frame fixture for caption-resume visual tests."""

    def run(
        self,
        executable: str,
        arguments: Sequence[str],
        *,
        input_fd: int | None = None,
        output_fd: int | None = None,
    ) -> CommandResult:
        copied_arguments = list(arguments)
        if (
            "--version" in copied_arguments
            or "-version" in copied_arguments
            or "--verbose" in copied_arguments
            or "--dump-single-json" in copied_arguments
        ):
            return super().run(
                executable,
                copied_arguments,
                input_fd=input_fd,
                output_fd=output_fd,
            )
        self.invocations.append((executable, copied_arguments))
        if "--format" in copied_arguments and "--output" in copied_arguments:
            assert output_fd is not None
            os.write(output_fd, b"synthetic-media")
            return CommandResult(0, "", "")
        if "-show_entries" in copied_arguments:
            is_frame = (
                input_fd is not None
                and os.pread(input_fd, 1024, 0).startswith(b"synthetic-jpeg")
            )
            return CommandResult(
                0,
                json.dumps(
                    {
                        "streams": [
                            {
                                "codec_name": "mjpeg" if is_frame else "h264",
                                "width": 768 if is_frame else 1920,
                                "height": 432 if is_frame else 1080,
                                "sample_aspect_ratio": "1:1",
                                "display_aspect_ratio": "16:9",
                            }
                        ]
                    }
                ),
                "",
            )
        if "-frames:v" in copied_arguments:
            assert output_fd is not None
            os.write(output_fd, b"synthetic-jpeg")
            return CommandResult(0, "", "")
        return CommandResult(1, "", "Unexpected visual command")


class MutableClock:
    def __init__(self, now: float = 10.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class FailingCaptionRunner(CaptionRunner):
    def fetch(self, resource: CaptionResource, output_fd: int, *, max_bytes: int) -> None:
        del output_fd, max_bytes
        self.caption_resource_reprs.append(repr(resource))
        url = resource._url
        self.caption_fetches.append(url)
        raise OSError("signed-caption-url?secret=never-render")


class RaisingCaptionRunner(CaptionRunner):
    def __init__(
        self,
        metadata: dict[str, object],
        error: Exception,
    ) -> None:
        super().__init__(metadata, {})
        self.error = error

    def fetch(self, resource: CaptionResource, output_fd: int, *, max_bytes: int) -> None:
        del output_fd, max_bytes
        self.caption_resource_reprs.append(repr(resource))
        url = resource._url
        self.caption_fetches.append(url)
        raise self.error


class _RedirectResponse:
    def __init__(self, location: str) -> None:
        self.status = 302
        self.headers = {"Location": location}

    def read(self, size: int) -> bytes:
        del size
        raise AssertionError("A redirect response body must not be read.")

    def close(self) -> None:
        pass


class SameOriginRedirectLoopCaptionFetcher:
    """Hermetic real bounded-fetch seam: one safe hop then a safe loop."""

    def __init__(self) -> None:
        self.transport_resource_reprs: list[str] = []
        self._responses = [
            _RedirectResponse("/loop.vtt"),
            _RedirectResponse("/manual.vtt?token=caption-secret"),
        ]
        self._fetcher = BoundedCaptionFetcher(resolver=self, transport=self)

    def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        if hostname != "cdn.example" or port != 443:
            raise AssertionError("Unexpected redirected caption destination")
        return ("8.8.8.8",)

    def open(
        self, resource: CaptionResource, addresses: tuple[str, ...]
    ) -> _RedirectResponse:
        if addresses != ("8.8.8.8",) or not self._responses:
            raise AssertionError("Unexpected caption HTTP attempt")
        self.transport_resource_reprs.append(repr(resource))
        return self._responses.pop(0)

    def fetch(self, resource: CaptionResource, output_fd: int, *, max_bytes: int) -> object:
        return self._fetcher.fetch(resource, output_fd, max_bytes=max_bytes)


class RedirectingCaptionRunner(CaptionRunner):
    def __init__(self, metadata: dict[str, object], caption_bodies: dict[str, str]) -> None:
        super().__init__(metadata, caption_bodies)
        self.redirected = False

    def fetch(self, resource: CaptionResource, output_fd: int, *, max_bytes: int) -> None:
        self.caption_resource_reprs.append(repr(resource))
        url = resource._url
        if not self.redirected:
            self.redirected = True
            self.caption_fetches.append(url)
            raise CaptionRedirectApprovalRequired(
                caption_resource("https://other-captions.example/next.vtt?token=redirect-secret")
            )
        payload = self.caption_bodies["manual:en"].encode("utf-8")
        if len(payload) > max_bytes:
            raise OSError("Fixture caption exceeds the safe limit.")
        while payload:
            written = os.write(output_fd, payload)
            payload = payload[written:]
        self.caption_fetches.append(url)


class NeverCalledProvider:
    descriptor = ProviderDescriptor(
        provider="openai",
        model="whisper-1",
        destination="https://api.openai.example/v1/audio/transcriptions",
        privacy_url="https://api.openai.example/privacy",
        max_chunk_bytes=8,
    )

    def __init__(self) -> None:
        self.calls = 0

    def transcribe_chunk(self, upload: object) -> object:
        del upload
        self.calls += 1
        raise AssertionError("Direct caption retrieval must not call a provider")


class AutoApprovingCaptionRuntime:
    """Test harness for parser-focused tests after the explicit approval boundary."""

    def __init__(self, runtime: WatchEvidenceRuntime) -> None:
        self._runtime = runtime

    def prepare(
        self, request: dict[str, object], prior_evidence: object | None = None
    ) -> object:
        outcome = self._runtime.prepare(request, prior_evidence=prior_evidence)
        if outcome.choice_kind != "caption_network":
            return outcome
        assert outcome.caption_network_approval is not None
        approved_request = dict(request)
        approved_request.pop("caption_track", None)
        approved_request["caption_network_approval"] = {
            "receipt": outcome.caption_network_approval.receipt,
            "decision": "approved",
        }
        return self._runtime.prepare(approved_request, prior_evidence=outcome)


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
    ) -> tuple[AutoApprovingCaptionRuntime, CaptionRunner]:
        runner = CaptionRunner(metadata, caption_bodies)
        return (
            AutoApprovingCaptionRuntime(
                WatchEvidenceRuntime(
                    command_runner=runner,
                    caption_fetcher=runner,
                    find_executable=fake_executable,
                )
            ),
            runner,
        )

    def request(self, **controls: object) -> dict[str, object]:
        return {
            "sources": [self.source],
            "source_network_approved": True,
            "detail": "transcript",
            **controls,
        }

    def test_direct_caption_network_action_requires_a_fresh_opaque_receipt_before_fetch(self) -> None:
        clock = MutableClock()
        runtime, runner = self.make_runtime(
            captioned_metadata(
                subtitles={"en": [{"ext": "vtt", "url": "https://cdn.example/manual.vtt?token=secret"}]},
                duration=1.0,
            ),
            {"manual:en": "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nCaption\n"},
        )
        runtime = WatchEvidenceRuntime(
            command_runner=runner,
            caption_fetcher=runner,
            find_executable=fake_executable,
            clock=clock,
        )

        approval = runtime.prepare(self.request())
        serialized_approval = json.dumps(approval.to_dict(), sort_keys=True)

        self.assertEqual(approval.state, "decision_required")
        self.assertEqual(approval.choice_kind, "caption_network")
        self.assertFalse(approval.terminal)
        self.assertIsNotNone(approval.caption_network_approval)
        self.assertIsNone(approval.decision_handle)
        self.assertEqual(runner.caption_fetches, [])
        self.assertIn("cdn.example", serialized_approval)
        self.assertNotIn("token=secret", serialized_approval)
        self.assertNotIn("expires_in_seconds", serialized_approval)

        completed = runtime.prepare(
            self.request(
                caption_network_approval={
                    "receipt": approval.caption_network_approval.receipt,
                    "decision": "approved",
                }
            ),
            prior_evidence=approval,
        )

        self.assertEqual(completed.state, "ready")
        self.assertEqual(runner.caption_fetches, ["https://cdn.example/manual.vtt?token=secret"])
        self.assertEqual(
            runner.caption_resource_reprs,
            ["CaptionResource(origin=CaptionOrigin(hostname='cdn.example', port=443))"],
        )
        self.assertNotIn("token=secret", json.dumps(completed.to_dict(), sort_keys=True))

    def test_invalid_or_expired_caption_receipts_make_zero_fetch_attempts(self) -> None:
        clock = MutableClock()
        runner = CaptionRunner(
            captioned_metadata(
                subtitles={"en": [{"ext": "vtt", "url": "https://cdn.example/manual.vtt"}]}
            ),
            {"manual:en": "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nCaption\n"},
        )
        runtime = WatchEvidenceRuntime(
            command_runner=runner,
            caption_fetcher=runner,
            find_executable=fake_executable,
            clock=clock,
        )
        approval = runtime.prepare(self.request())

        malformed = runtime.prepare(
            self.request(
                caption_network_approval={"receipt": "caption_receipt_tampered", "decision": "approved"}
            ),
            prior_evidence=approval,
        )
        self.assertEqual(malformed.state, "stopped")
        self.assertEqual(malformed.failure.category, "caption_approval_invalid")
        self.assertEqual(runner.caption_fetches, [])

        clock.now += 300
        expired = runtime.prepare(
            self.request(
                caption_network_approval={
                    "receipt": approval.caption_network_approval.receipt,
                    "decision": "approved",
                }
            ),
            prior_evidence=approval,
        )
        self.assertEqual(expired.state, "stopped")
        self.assertEqual(expired.failure.category, "caption_approval_expired")
        self.assertEqual(runner.caption_fetches, [])

        malformed_runner = CaptionRunner(
            captioned_metadata(
                subtitles={"en": [{"ext": "vtt", "url": "https://cdn.example/manual.vtt"}]}
            ),
            {"manual:en": "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nCaption\n"},
        )
        malformed_runtime = WatchEvidenceRuntime(
            command_runner=malformed_runner,
            caption_fetcher=malformed_runner,
            find_executable=fake_executable,
        )
        malformed_approval = malformed_runtime.prepare(self.request())
        tampered = malformed_runtime.prepare(
            self.request(
                caption_network_approval={
                    "receipt": malformed_approval.caption_network_approval.receipt,
                    "decision": "tampered",
                }
            ),
            prior_evidence=malformed_approval,
        )
        replayed = malformed_runtime.prepare(
            self.request(
                caption_network_approval={
                    "receipt": malformed_approval.caption_network_approval.receipt,
                    "decision": "approved",
                }
            ),
            prior_evidence=malformed_approval,
        )
        self.assertEqual(tampered.state, "stopped")
        self.assertEqual(replayed.state, "stopped")
        self.assertEqual(malformed_runner.caption_fetches, [])

        ended_runner = CaptionRunner(
            captioned_metadata(
                subtitles={"en": [{"ext": "vtt", "url": "https://cdn.example/manual.vtt"}]}
            ),
            {"manual:en": "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nCaption\n"},
        )
        ended_runtime = WatchEvidenceRuntime(
            command_runner=ended_runner,
            caption_fetcher=ended_runner,
            find_executable=fake_executable,
        )
        ended_approval = ended_runtime.prepare(self.request())
        ended_runtime.close()
        ended = ended_runtime.prepare(
            self.request(
                caption_network_approval={
                    "receipt": ended_approval.caption_network_approval.receipt,
                    "decision": "approved",
                }
            ),
            prior_evidence=ended_approval,
        )
        self.assertEqual(ended.state, "stopped")
        self.assertEqual(ended_runner.caption_fetches, [])

    def test_rejected_caption_network_followups_burn_a_known_receipt_before_fetch(self) -> None:
        metadata = captioned_metadata(
            subtitles={"en": [{"ext": "vtt", "url": "https://cdn.example/manual.vtt"}]}
        )
        body = {"manual:en": "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nCaption\n"}

        malformed_runner = CaptionRunner(metadata, body)
        malformed_runtime = WatchEvidenceRuntime(
            command_runner=malformed_runner,
            caption_fetcher=malformed_runner,
            find_executable=fake_executable,
        )
        malformed_approval = malformed_runtime.prepare(self.request())
        malformed = malformed_runtime.prepare(
            self.request(
                caption_network_approval={
                    "receipt": malformed_approval.caption_network_approval.receipt,
                    "decision": ["approved"],
                }
            ),
            prior_evidence=malformed_approval,
        )
        malformed_replay = malformed_runtime.prepare(
            self.request(
                caption_network_approval={
                    "receipt": malformed_approval.caption_network_approval.receipt,
                    "decision": "approved",
                }
            ),
            prior_evidence=malformed_approval,
        )
        self.assertEqual(malformed.state, "stopped")
        self.assertEqual(malformed_replay.state, "stopped")
        self.assertEqual(malformed_runner.caption_fetches, [])

        prior_runner = CaptionRunner(metadata, body)
        prior_runtime = WatchEvidenceRuntime(
            command_runner=prior_runner,
            caption_fetcher=prior_runner,
            find_executable=fake_executable,
        )
        prior_approval = prior_runtime.prepare(self.request())
        altered_prior = prior_approval.to_dict()
        altered_prior["caption_network_approval"]["byte_cap"] = 1
        rejected_prior = prior_runtime.prepare(
            self.request(
                caption_network_approval={
                    "receipt": prior_approval.caption_network_approval.receipt,
                    "decision": "approved",
                }
            ),
            prior_evidence=altered_prior,
        )
        prior_replay = prior_runtime.prepare(
            self.request(
                caption_network_approval={
                    "receipt": prior_approval.caption_network_approval.receipt,
                    "decision": "approved",
                }
            ),
            prior_evidence=prior_approval,
        )
        self.assertEqual(rejected_prior.state, "stopped")
        self.assertEqual(prior_replay.state, "stopped")
        self.assertEqual(prior_runner.caption_fetches, [])

    def test_caption_denial_is_terminal_and_direct_caption_failure_never_offers_or_calls_transcription(self) -> None:
        runner = FailingCaptionRunner(
            captioned_metadata(
                subtitles={"en": [{"ext": "vtt", "url": "https://cdn.example/manual.vtt?token=secret"}]}
            ),
            {},
        )
        provider = NeverCalledProvider()
        runtime = WatchEvidenceRuntime(
            command_runner=runner,
            caption_fetcher=runner,
            find_executable=fake_executable,
            transcription_providers={"openai": provider},
        )
        approval = runtime.prepare(self.request())

        denied = runtime.prepare(
            self.request(
                caption_network_approval={
                    "receipt": approval.caption_network_approval.receipt,
                    "decision": "declined",
                }
            ),
            prior_evidence=approval,
        )
        self.assertEqual(denied.state, "stopped")
        self.assertEqual(denied.failure.category, "caption_approval_declined")
        self.assertEqual(runner.caption_fetches, [])

        retry_runtime = WatchEvidenceRuntime(
            command_runner=runner,
            caption_fetcher=runner,
            find_executable=fake_executable,
            transcription_providers={"openai": provider},
        )
        retry_approval = retry_runtime.prepare(self.request())
        failed = retry_runtime.prepare(
            self.request(
                caption_network_approval={
                    "receipt": retry_approval.caption_network_approval.receipt,
                    "decision": "approved",
                }
            ),
            prior_evidence=retry_approval,
        )
        serialized_failure = json.dumps(failed.to_dict(), sort_keys=True)
        self.assertEqual(failed.state, "partial")
        self.assertIsNone(failed.choice_kind)
        self.assertEqual(provider.calls, 0)
        self.assertNotIn("token=secret", serialized_failure)

    def test_unsafe_caption_route_is_a_typed_partial_and_never_offers_transcription(self) -> None:
        provider = NeverCalledProvider()
        runner = CaptionRunner(
            captioned_metadata(
                subtitles={
                    "en": [
                        {
                            "ext": "vtt",
                            "url": "https://127.0.0.1/private.vtt?token=never-render",
                        }
                    ]
                }
            ),
            {},
        )
        runtime = WatchEvidenceRuntime(
            command_runner=runner,
            caption_fetcher=runner,
            find_executable=fake_executable,
            transcription_providers={"openai": provider},
        )

        outcome = runtime.prepare(self.request())
        payload = json.dumps(outcome.to_dict(), sort_keys=True)

        self.assertEqual(outcome.state, "partial")
        self.assertIsNone(outcome.choice_kind)
        self.assertIsNotNone(outcome.failure)
        self.assertEqual(outcome.failure.category, "caption_url_policy")
        self.assertEqual(provider.calls, 0)
        self.assertEqual(runner.caption_fetches, [])
        self.assertNotIn("127.0.0.1", payload)
        self.assertNotIn("never-render", payload)

    def test_caption_network_failure_categories_are_typed_and_sanitized(self) -> None:
        metadata = captioned_metadata(
            subtitles={"en": [{"ext": "vtt", "url": "https://cdn.example/manual.vtt?token=secret"}]}
        )
        cases: tuple[tuple[Exception, str, str, int], ...] = (
            (CaptionUnavailable(), "unavailable", "caption_unavailable", 0),
            (CaptionResponseTooLarge(), "response_too_large", "caption_response_too_large", 0),
            (CaptionNetworkError("http_failure"), "http_failed", "caption_http", 0),
            (CaptionNetworkError("transport_failure"), "transport_failed", "caption_transport", 0),
            (CaptionNetworkError("unsafe_destination"), "url_policy_failed", "caption_url_policy", 0),
            (
                CaptionNetworkError("redirect_loop", redirect_count=1),
                "redirect_failed",
                "caption_redirect",
                1,
            ),
            (OSError("https://cdn.example/manual.vtt?token=secret"), "transport_failed", "caption_transport", 0),
        )
        for error, expected_status, expected_category, expected_redirect_count in cases:
            with self.subTest(error=type(error).__name__):
                runner = RaisingCaptionRunner(metadata, error)
                runtime = WatchEvidenceRuntime(
                    command_runner=runner,
                    caption_fetcher=runner,
                    find_executable=fake_executable,
                )
                approval = runtime.prepare(self.request())
                outcome = runtime.prepare(
                    self.request(
                        caption_network_approval={
                            "receipt": approval.caption_network_approval.receipt,
                            "decision": "approved",
                        }
                    ),
                    prior_evidence=approval,
                )
                payload = json.dumps(outcome.to_dict(), sort_keys=True)
                self.assertEqual(outcome.state, "partial")
                self.assertEqual(outcome.caption_network_audit.status, expected_status)
                self.assertEqual(
                    outcome.caption_network_audit.redirect_count, expected_redirect_count
                )
                self.assertEqual(outcome.failure.category, expected_category)
                self.assertNotIn("token=secret", payload)

    def test_same_origin_redirect_loop_keeps_a_truthful_sanitized_redirect_audit(self) -> None:
        caption_url = "https://cdn.example/manual.vtt?token=caption-secret"
        command_runner = CaptionRunner(
            captioned_metadata(subtitles={"en": [{"ext": "vtt", "url": caption_url}]}),
            {},
        )
        caption_fetcher = SameOriginRedirectLoopCaptionFetcher()
        runtime = WatchEvidenceRuntime(
            command_runner=command_runner,
            caption_fetcher=caption_fetcher,
            find_executable=fake_executable,
        )
        approval = runtime.prepare(self.request())

        outcome = runtime.prepare(
            self.request(
                caption_network_approval={
                    "receipt": approval.caption_network_approval.receipt,
                    "decision": "approved",
                }
            ),
            prior_evidence=approval,
        )
        observable = json.dumps(outcome.to_dict(), sort_keys=True) + outcome.report_markdown

        self.assertEqual(outcome.state, "partial")
        self.assertEqual(outcome.failure.category, "caption_redirect")
        self.assertEqual(outcome.caption_network_audit.status, "redirect_failed")
        self.assertEqual(outcome.caption_network_audit.redirect_count, 1)
        self.assertEqual(len(caption_fetcher.transport_resource_reprs), 2)
        self.assertNotIn("manual.vtt", observable)
        self.assertNotIn("loop.vtt", observable)
        self.assertNotIn("caption-secret", observable)
        self.assertTrue(
            all("caption-secret" not in value for value in caption_fetcher.transport_resource_reprs)
        )

    def test_caption_network_resume_preserves_visual_evidence_after_approval_and_denial(self) -> None:
        metadata = captioned_metadata(
            subtitles={"en": [{"ext": "vtt", "url": "https://cdn.example/manual.vtt"}]},
            duration=1.0,
        )
        body = {"manual:en": "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nCaption\n"}

        approved_runner = CaptionVisualRunner(metadata, body)
        approved_runtime = WatchEvidenceRuntime(
            command_runner=approved_runner,
            caption_fetcher=approved_runner,
            find_executable=fake_executable,
        )
        approved_prompt = approved_runtime.prepare(
            self.request(detail="transcript", cues=[0])
        )
        approved = approved_runtime.prepare(
            self.request(
                detail="transcript",
                cues=[0],
                caption_network_approval={
                    "receipt": approved_prompt.caption_network_approval.receipt,
                    "decision": "approved",
                },
            ),
            prior_evidence=approved_prompt,
        )
        self.assertEqual(approved.state, "partial")
        self.assertIsNotNone(approved.evidence.visual)
        self.assertEqual(len(approved.evidence.visual.frames), 1)

        denied_runner = CaptionVisualRunner(metadata, body)
        denied_runtime = WatchEvidenceRuntime(
            command_runner=denied_runner,
            caption_fetcher=denied_runner,
            find_executable=fake_executable,
        )
        denied_prompt = denied_runtime.prepare(self.request(detail="transcript", cues=[0]))
        denied = denied_runtime.prepare(
            self.request(
                detail="transcript",
                cues=[0],
                caption_network_approval={
                    "receipt": denied_prompt.caption_network_approval.receipt,
                    "decision": "declined",
                },
            ),
            prior_evidence=denied_prompt,
        )
        self.assertEqual(denied.state, "stopped")
        self.assertEqual(denied.failure.category, "caption_approval_declined")
        self.assertIsNotNone(denied.evidence.visual)
        self.assertEqual(len(denied_runner.caption_fetches), 0)

    def test_canceled_caption_network_action_stops_before_caption_or_visual_acquisition(self) -> None:
        metadata = captioned_metadata(
            subtitles={"en": [{"ext": "vtt", "url": "https://cdn.example/manual.vtt"}]},
            duration=1.0,
        )
        runner = CaptionVisualRunner(
            metadata,
            {"manual:en": "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nCaption\n"},
        )
        runtime = WatchEvidenceRuntime(
            command_runner=runner,
            caption_fetcher=runner,
            find_executable=fake_executable,
        )
        prompt = runtime.prepare(self.request(detail="transcript", cues=[0]))

        canceled = runtime.prepare(
            self.request(
                detail="transcript",
                cues=[0],
                caption_network_approval={
                    "receipt": prompt.caption_network_approval.receipt,
                    "decision": "canceled",
                },
            ),
            prior_evidence=prompt,
        )

        self.assertEqual(canceled.state, "canceled")
        self.assertEqual(canceled.failure.category, "user_cancellation")
        self.assertEqual(runner.caption_fetches, [])
        self.assertFalse(any("--format" in arguments for _, arguments in runner.invocations))

    def test_cross_origin_redirect_returns_a_new_caption_approval_without_following_it(self) -> None:
        metadata = captioned_metadata(
            subtitles={"en": [{"ext": "vtt", "url": "https://cdn.example/manual.vtt?token=first"}]},
            duration=1.0,
        )
        runner = RedirectingCaptionRunner(
            metadata,
            {"manual:en": "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nCaption\n"},
        )
        runtime = WatchEvidenceRuntime(
            command_runner=runner,
            caption_fetcher=runner,
            find_executable=fake_executable,
        )
        first = runtime.prepare(self.request())
        second = runtime.prepare(
            self.request(
                caption_network_approval={
                    "receipt": first.caption_network_approval.receipt,
                    "decision": "approved",
                }
            ),
            prior_evidence=first,
        )
        serialized_second = json.dumps(second.to_dict(), sort_keys=True)

        self.assertEqual(second.state, "decision_required")
        self.assertEqual(second.choice_kind, "caption_network")
        self.assertEqual(second.caption_network_approval.hostname, "other-captions.example")
        self.assertEqual(len(runner.caption_fetches), 1)
        self.assertNotIn("redirect-secret", serialized_second)

        completed = runtime.prepare(
            self.request(
                caption_network_approval={
                    "receipt": second.caption_network_approval.receipt,
                    "decision": "approved",
                }
            ),
            prior_evidence=second,
        )
        self.assertEqual(completed.state, "ready")
        self.assertEqual(len(runner.caption_fetches), 2)

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
        self.assertEqual(caption_calls, ["https://cdn.example/manual.vtt"])
        self.assertNotIn("cdn.example", outcome.report_markdown)

    def test_replaying_a_completed_caption_choice_reuses_its_terminal_evidence(self) -> None:
        runtime, runner = self.make_runtime(
            captioned_metadata(
                subtitles={"en": [{"ext": "vtt", "url": "https://cdn.example/manual.vtt"}]},
                automatic_captions={
                    "fr": [{"ext": "vtt", "url": "https://cdn.example/automatic.vtt"}]
                },
            ),
            {
                "manual:en": "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nManual caption\n",
                "automatic:fr": "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nAutomatic caption\n",
            },
        )
        decision = runtime.prepare(self.request())
        choice = next(choice for choice in decision.choices if choice.caption_type == "manual")
        completed = runtime.prepare(
            self.request(caption_track=choice.id), prior_evidence=decision
        )
        invocations_before_replay = list(runner.invocations)
        fetches_before_replay = list(runner.caption_fetches)

        replayed = runtime.prepare(
            self.request(question="What did the retained transcript establish?"),
            prior_evidence={"evidence_handle": completed.evidence_handle},
        )

        self.assertEqual(replayed, completed)
        self.assertEqual(runner.invocations, invocations_before_replay)
        self.assertEqual(runner.caption_fetches, fetches_before_replay)

    def test_caption_retrieval_urls_remain_internal_to_the_runtime(self) -> None:
        caption_url = "https://cdn.example/private.vtt?signature=caption-secret"
        runtime, runner = self.make_runtime(
            captioned_metadata(
                subtitles={"en": [{"ext": "vtt", "url": caption_url}]},
                duration=1.0,
            ),
            {"manual:en": "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nCaption\n"},
        )

        outcome = runtime.prepare(self.request())
        serialized_outcome = json.dumps(outcome.to_dict(), sort_keys=True)

        self.assertEqual(runner.caption_fetches, [caption_url])
        self.assertIn("cdn.example", serialized_outcome)
        self.assertNotIn("private.vtt", serialized_outcome)
        self.assertNotIn("caption-secret", serialized_outcome)
        self.assertNotIn("cdn.example", outcome.report_markdown)

        candidates = _caption_candidates_from_ytdlp(
            captioned_metadata(
                subtitles={"en": [{"ext": "vtt", "url": caption_url}]}
            )
        )
        self.assertNotIn("private.vtt", repr(candidates))
        self.assertNotIn("caption-secret", repr(candidates))
        probe_snapshot = repr(
            asdict(
                _SourceProbe(
                    MetadataEvidence(
                        None, None, None, None, None, None, None, None, None, False
                    ),
                    candidates,
                    (),
                )
            )
        )
        self.assertNotIn("private.vtt", probe_snapshot)
        self.assertNotIn("caption-secret", probe_snapshot)

        pending_runner = CaptionRunner(
            captioned_metadata(
                subtitles={"en": [{"ext": "vtt", "url": caption_url}]}
            ),
            {},
        )
        pending_runtime = WatchEvidenceRuntime(
            command_runner=pending_runner,
            caption_fetcher=pending_runner,
            find_executable=fake_executable,
        )
        try:
            pending = pending_runtime.prepare(self.request())
            receipt = pending.caption_network_approval.receipt
            selection = pending_runtime._caption_network_selections[receipt]
            self.assertNotIn("private.vtt", repr(selection))
            self.assertNotIn("caption-secret", repr(selection))
        finally:
            pending_runtime.close()

    def test_yt_dlp_metadata_failure_never_renders_a_signed_caption_url(self) -> None:
        caption_url = "https://caption-host.example/private.vtt?token=caption-secret"
        runner = MetadataFailureRunner(f"upstream failure: {caption_url}")
        runtime = WatchEvidenceRuntime(
            command_runner=runner,
            caption_fetcher=runner,
            find_executable=fake_executable,
        )

        outcome = runtime.prepare(self.request())
        observable = json.dumps(outcome.to_dict(), sort_keys=True) + outcome.report_markdown

        self.assertEqual(outcome.state, "failed")
        self.assertEqual(outcome.failure.category, "metadata_probe")
        self.assertNotIn("caption-host.example", observable)
        self.assertNotIn("private.vtt", observable)
        self.assertNotIn("caption-secret", observable)

    def test_ambiguous_same_format_caption_urls_are_not_silently_fetched(self) -> None:
        runtime, runner = self.make_runtime(
            captioned_metadata(
                subtitles={
                    "en": [
                        {"ext": "vtt", "url": "https://cdn.example/one.vtt"},
                        {"ext": "vtt", "url": "https://cdn.example/two.vtt"},
                    ]
                }
            ),
            {},
        )

        outcome = runtime.prepare(self.request())
        serialized_outcome = json.dumps(outcome.to_dict(), sort_keys=True)

        self.assertEqual(outcome.state, "partial")
        self.assertTrue(outcome.terminal)
        self.assertEqual(runner.caption_fetches, [])
        self.assertEqual(outcome.choices, ())
        self.assertEqual(len(outcome.caption_inventory), 1)
        self.assertFalse(outcome.caption_inventory[0].usable)
        self.assertNotIn("cdn.example", serialized_outcome)

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
        self.assertEqual(caption_calls, ["https://cdn.example/automatic.vtt"])

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
        self.assertEqual(caption_calls, ["https://cdn.example/manual.vtt"])

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
        self.assertEqual(caption_calls, ["https://cdn.example/manual.ttml"])

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
        self.assertEqual(caption_calls, ["https://cdn.example/automatic.ttml"])

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
        self.assertEqual(outcome.failure.category, "caption_parse")
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
