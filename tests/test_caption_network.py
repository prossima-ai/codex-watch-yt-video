from __future__ import annotations

from dataclasses import replace
import http.client
import io
import os
from pathlib import Path
import sys
import tempfile
import traceback
import unittest
from unittest import mock
from urllib import request as urllib_request


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIRECTORY = REPOSITORY_ROOT / ".agents" / "skills" / "watch" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIRECTORY))

from watch_caption_network import (  # noqa: E402
    BoundedCaptionFetcher,
    CaptionApprovalDecision,
    CaptionApprovalReceiptError,
    CaptionApprovalRegistry,
    CaptionNetworkError,
    CaptionNetworkBinding,
    CaptionRedirectApprovalRequired,
    CaptionResponseTooLarge,
    CaptionUnavailable,
    _UrllibCaptionResponse,
    _PinnedUrllibHttpsHandler,
    _dial_pinned_address,
    caption_resource,
    PinnedHttpsTransport,
)


class MutableClock:
    def __init__(self, now: float = 100.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class StaticResolver:
    def __init__(self, answers: dict[str, tuple[str, ...]]) -> None:
        self.answers = answers
        self.requests: list[tuple[str, int]] = []

    def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        self.requests.append((hostname, port))
        return self.answers[hostname]


class SequencedResolver:
    def __init__(self, answers: tuple[tuple[str, ...], ...]) -> None:
        self.answers = list(answers)
        self.requests: list[tuple[str, int]] = []

    def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        self.requests.append((hostname, port))
        if not self.answers:
            raise AssertionError("Unexpected DNS resolution")
        return self.answers.pop(0)


class FakeResponse:
    def __init__(
        self,
        status: int,
        *,
        headers: dict[str, str] | None = None,
        chunks: tuple[bytes, ...] = (),
    ) -> None:
        self.status = status
        self.headers = headers or {}
        self._chunks = list(chunks)
        self.read_calls = 0
        self.closed = False

    def read(self, size: int) -> bytes:
        self.read_calls += 1
        if not self._chunks:
            return b""
        value = self._chunks.pop(0)
        if len(value) <= size:
            return value
        self._chunks.insert(0, value[size:])
        return value[:size]

    def close(self) -> None:
        self.closed = True


class RecordingTransport:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def open(self, resource: object, addresses: tuple[str, ...]) -> FakeResponse:
        self.calls.append((resource.origin.hostname, addresses))
        if not self.responses:
            raise AssertionError("Unexpected outbound caption HTTP attempt")
        return self.responses.pop(0)


class SecretFailingTransport:
    def __init__(self) -> None:
        self.calls = 0

    def open(self, resource: object, addresses: tuple[str, ...]) -> FakeResponse:
        del resource, addresses
        self.calls += 1
        raise OSError("https://captions.example/private.vtt?token=never-expose")


class SecretReadFailingResponse(FakeResponse):
    def read(self, size: int) -> bytes:
        del size
        raise OSError("https://captions.example/private.vtt?token=read-never-expose")


class SecretCloseFailingResponse(FakeResponse):
    def close(self) -> None:
        raise OSError("https://captions.example/private.vtt?token=close-never-expose")


class RawHttpSocket:
    def __init__(self, stream: object) -> None:
        self._stream = stream

    def makefile(self, mode: str, buffering: int | None = None) -> object:
        del mode, buffering
        return self._stream


class CloseRecorder:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class DelayedBodyStream:
    """A read seam that produces a surplus byte only after the cap is reached."""

    def __init__(
        self,
        header: bytes,
        body_reads: tuple[bytes, ...],
        *,
        line_reads: tuple[bytes, ...] = (),
        terminal_error: Exception | None = None,
    ) -> None:
        self._headers = io.BytesIO(header)
        self._body_reads = list(body_reads)
        self._line_reads = list(line_reads)
        self._terminal_error = terminal_error
        self.closed = False

    def readline(self, size: int = -1) -> bytes:
        value = self._headers.readline(size)
        if value:
            return value
        if not self._line_reads:
            return b""
        value = self._line_reads.pop(0)
        if size < 0 or len(value) <= size:
            return value
        self._line_reads.insert(0, value[size:])
        return value[:size]

    def read(self, size: int = -1) -> bytes:
        if not self._body_reads:
            if self._terminal_error is not None:
                raise self._terminal_error
            return b""
        value = self._body_reads.pop(0)
        if size < 0 or len(value) <= size:
            return value
        self._body_reads.insert(0, value[size:])
        return value[:size]

    def close(self) -> None:
        self.closed = True

    def flush(self) -> None:
        pass


class RecordingUrllibHandler:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.requests: list[object] = []

    def https_open(self, request: object) -> FakeResponse:
        self.requests.append(request)
        return self.response


class RecordingUrllibHandlerFactory:
    def __init__(self, handler: RecordingUrllibHandler) -> None:
        self.handler = handler
        self.calls: list[tuple[object, tuple[str, ...], float]] = []

    def __call__(
        self, resource: object, addresses: tuple[str, ...], timeout_seconds: float
    ) -> RecordingUrllibHandler:
        self.calls.append((resource, addresses, timeout_seconds))
        return self.handler


class RecordingDialSocket:
    def __init__(self) -> None:
        self.timeout: float | None = None
        self.connected: tuple[object, ...] | None = None
        self.closed = False

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def connect(self, target: tuple[object, ...]) -> None:
        self.connected = target

    def close(self) -> None:
        self.closed = True


class RecordingPinnedConnection:
    def __init__(self, response: http.client.HTTPResponse) -> None:
        self.response = response
        self.debuglevel: int | None = None
        self.request_call: tuple[object, ...] | None = None
        self.closed = False

    def set_debuglevel(self, level: int) -> None:
        self.debuglevel = level

    def request(
        self,
        method: str,
        selector: str,
        body: object,
        headers: dict[str, str],
    ) -> None:
        self.request_call = (method, selector, body, dict(headers))

    def getresponse(self) -> http.client.HTTPResponse:
        return self.response

    def close(self) -> None:
        self.closed = True


class CaptionReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = MutableClock()
        self.registry = CaptionApprovalRegistry(
            clock=self.clock,
            receipt_factory=lambda: "caption_receipt_test",
        )
        self.binding = CaptionNetworkBinding(
            action="native_caption_retrieval",
            watch_request_id="watch-request-1",
            source_value="https://video.example/watch?v=one",
            session_id="session-1",
            workspace_id="workspace-1",
            selected_track_id="caption-en",
            selected_format="vtt",
            byte_cap=8,
            origin=caption_resource("https://captions.example/one.vtt?token=secret").origin,
        )

    def issue(self) -> CaptionApprovalDecision:
        prompt = self.registry.issue(self.binding)
        self.assertEqual(prompt.hostname, "captions.example")
        self.assertEqual(prompt.purpose, "retrieve_selected_native_caption")
        self.assertEqual(prompt.selected_track_id, "caption-en")
        self.assertEqual(prompt.selected_format, "vtt")
        self.assertEqual(prompt.byte_cap, 8)
        self.assertNotIn("token", repr(prompt))
        return CaptionApprovalDecision(prompt.receipt, "approved")

    def test_valid_correctly_bound_unexpired_receipt_is_consumed_once(self) -> None:
        decision = self.issue()

        verified = self.registry.verify_and_consume(decision, self.binding)

        self.assertEqual(verified.decision, "approved")
        with self.assertRaises(CaptionApprovalReceiptError) as replayed:
            self.registry.verify_and_consume(decision, self.binding)
        self.assertEqual(replayed.exception.code, "invalid_receipt")

    def test_missing_malformed_and_tampered_receipts_fail_closed(self) -> None:
        valid = self.issue()
        attempts: tuple[object, ...] = (
            None,
            {},
            CaptionApprovalDecision("caption_receipt_unknown", "approved"),
            CaptionApprovalDecision(valid.receipt, "tampered"),
        )

        for attempted in attempts:
            with self.subTest(attempted=type(attempted).__name__):
                with self.assertRaises(CaptionApprovalReceiptError) as rejected:
                    self.registry.verify_and_consume(attempted, self.binding)
                self.assertEqual(rejected.exception.code, "invalid_receipt")

        with self.assertRaises(CaptionApprovalReceiptError) as replayed:
            self.registry.verify_and_consume(valid, self.binding)
        self.assertEqual(replayed.exception.code, "invalid_receipt")

    def test_receipt_cannot_move_between_action_source_session_destination_or_bindings(self) -> None:
        substitutions = (
            replace(self.binding, action="different_action"),
            replace(self.binding, watch_request_id="watch-request-2"),
            replace(self.binding, source_value="https://video.example/watch?v=two"),
            replace(self.binding, session_id="session-2"),
            replace(self.binding, workspace_id="workspace-2"),
            replace(self.binding, selected_track_id="caption-fr"),
            replace(self.binding, selected_format="ttml"),
            replace(self.binding, byte_cap=9),
            replace(
                self.binding,
                origin=caption_resource("https://other-captions.example/one.vtt").origin,
            ),
        )

        for substituted in substitutions:
            with self.subTest(substituted=substituted):
                registry = CaptionApprovalRegistry(
                    clock=self.clock,
                    receipt_factory=lambda: "caption_receipt_test",
                )
                prompt = registry.issue(self.binding)
                with self.assertRaises(CaptionApprovalReceiptError) as rejected:
                    registry.verify_and_consume(
                        CaptionApprovalDecision(prompt.receipt, "approved"), substituted
                    )
                self.assertEqual(rejected.exception.code, "invalid_receipt")

    def test_expiry_has_a_deterministic_fail_closed_boundary(self) -> None:
        decision = self.issue()
        self.clock.now += 299.999
        self.assertEqual(
            self.registry.verify_and_consume(decision, self.binding).decision, "approved"
        )

        expired_registry = CaptionApprovalRegistry(
            clock=self.clock,
            receipt_factory=lambda: "caption_receipt_expiry",
        )
        prompt = expired_registry.issue(self.binding)
        self.clock.now += 300
        with self.assertRaises(CaptionApprovalReceiptError) as expired:
            expired_registry.verify_and_consume(
                CaptionApprovalDecision(prompt.receipt, "approved"), self.binding
            )
        self.assertEqual(expired.exception.code, "expired_receipt")

    def test_denial_cancellation_and_request_end_invalidate_receipts(self) -> None:
        denied = self.issue()
        self.assertEqual(
            self.registry.verify_and_consume(
                CaptionApprovalDecision(denied.receipt, "declined"), self.binding
            ).decision,
            "declined",
        )
        with self.assertRaises(CaptionApprovalReceiptError):
            self.registry.verify_and_consume(denied, self.binding)

        canceled_prompt = self.registry.issue(replace(self.binding, workspace_id="workspace-2"))
        self.assertEqual(
            self.registry.verify_and_consume(
                CaptionApprovalDecision(canceled_prompt.receipt, "canceled"),
                replace(self.binding, workspace_id="workspace-2"),
            ).decision,
            "canceled",
        )
        ended_prompt = self.registry.issue(replace(self.binding, workspace_id="workspace-3"))
        self.registry.invalidate_workspace("workspace-3")
        with self.assertRaises(CaptionApprovalReceiptError):
            self.registry.verify_and_consume(
                CaptionApprovalDecision(ended_prompt.receipt, "approved"),
                replace(self.binding, workspace_id="workspace-3"),
            )
        all_prompt = self.registry.issue(replace(self.binding, workspace_id="workspace-4"))
        self.registry.invalidate_all()
        with self.assertRaises(CaptionApprovalReceiptError):
            self.registry.verify_and_consume(
                CaptionApprovalDecision(all_prompt.receipt, "approved"),
                replace(self.binding, workspace_id="workspace-4"),
            )


class BoundedCaptionFetcherTests(unittest.TestCase):
    def fetch(
        self,
        url: str,
        *,
        answers: dict[str, tuple[str, ...]],
        responses: list[FakeResponse],
        max_bytes: int = 8,
    ) -> tuple[bytes, StaticResolver, RecordingTransport]:
        resolver = StaticResolver(answers)
        transport = RecordingTransport(responses)
        fetcher = BoundedCaptionFetcher(resolver=resolver, transport=transport)
        with tempfile.TemporaryFile() as output:
            fetcher.fetch(caption_resource(url), output.fileno(), max_bytes=max_bytes)
            output.seek(0)
            body = output.read()
        return body, resolver, transport

    def test_public_https_accepts_public_ipv4_and_ipv6_and_pins_transport_addresses(self) -> None:
        body, resolver, transport = self.fetch(
            "https://captions.example/one.vtt?signature=secret",
            answers={"captions.example": ("8.8.8.8", "2606:4700:4700::1111")},
            responses=[FakeResponse(200, chunks=(b"caption",))],
        )

        self.assertEqual(body, b"caption")
        self.assertEqual(resolver.requests, [("captions.example", 443)])
        self.assertEqual(
            transport.calls,
            [("captions.example", ("8.8.8.8", "2606:4700:4700::1111"))],
        )

    def test_malformed_credentialed_non_https_and_nonpublic_urls_make_zero_transport_calls(self) -> None:
        invalid_urls = (
            "not a url",
            "http://captions.example/one.vtt",
            "ftp://captions.example/one.vtt",
            "https://user:pass@captions.example/one.vtt",
            "https://captions.example:444/one.vtt",
            "https://captions.example/%ZZ",
            "https://8.8.8.8/one.vtt",
            "https://[2606:4700:4700::1111]/one.vtt",
            "https://127.0.0.1/one.vtt",
            "https://10.0.0.1/one.vtt",
            "https://169.254.1.1/one.vtt",
            "https://[::1]/one.vtt",
            "https://localhost/one.vtt",
            "https://captions%2eexample/one.vtt",
            "https://%31%32%37.0.0.1/one.vtt",
        )
        for url in invalid_urls:
            with self.subTest(url=url):
                resolver = StaticResolver({})
                transport = RecordingTransport([])
                fetcher = BoundedCaptionFetcher(resolver=resolver, transport=transport)
                with tempfile.TemporaryFile() as output:
                    with self.assertRaises(CaptionNetworkError) as rejected:
                        fetcher.fetch(
                            caption_resource(url), output.fileno(), max_bytes=8
                        )
                self.assertEqual(rejected.exception.code, "unsafe_url")
                self.assertEqual(resolver.requests, [])
                self.assertEqual(transport.calls, [])

        resolver = StaticResolver({})
        transport = RecordingTransport([])
        fetcher = BoundedCaptionFetcher(resolver=resolver, transport=transport)
        with tempfile.TemporaryFile() as output:
            with self.assertRaises(CaptionNetworkError) as raw_url:
                fetcher.fetch(
                    "https://captions.example/one.vtt?token=never-pass-raw",
                    output.fileno(),
                    max_bytes=8,
                )
        self.assertEqual(raw_url.exception.code, "unsafe_url")
        self.assertEqual(resolver.requests, [])
        self.assertEqual(transport.calls, [])

    def test_private_link_local_multicast_unspecified_reserved_and_malformed_dns_answers_fail_before_http(self) -> None:
        forbidden = (
            "127.0.0.1",
            "10.0.0.1",
            "169.254.1.1",
            "224.0.0.1",
            "0.0.0.0",
            "100.64.0.1",
            "192.0.2.1",
            "255.255.255.255",
            "::1",
            "fc00::1",
            "fe80::1",
            "ff02::1",
            "::",
            "2001:db8::1",
            "not-an-address",
        )
        for address in forbidden:
            with self.subTest(address=address):
                resolver = StaticResolver({"captions.example": (address,)})
                transport = RecordingTransport([])
                fetcher = BoundedCaptionFetcher(resolver=resolver, transport=transport)
                with tempfile.TemporaryFile() as output:
                    with self.assertRaises(CaptionNetworkError) as rejected:
                        fetcher.fetch(
                            caption_resource("https://captions.example/one.vtt"),
                            output.fileno(),
                            max_bytes=8,
                        )
                self.assertEqual(rejected.exception.code, "unsafe_destination")
                self.assertEqual(transport.calls, [])

        resolver = StaticResolver({"captions.example": ("8.8.8.8", "10.0.0.1")})
        transport = RecordingTransport([])
        fetcher = BoundedCaptionFetcher(resolver=resolver, transport=transport)
        with tempfile.TemporaryFile() as output:
            with self.assertRaises(CaptionNetworkError) as mixed:
                fetcher.fetch(
                    caption_resource("https://captions.example/one.vtt"),
                    output.fileno(),
                    max_bytes=8,
                )
        self.assertEqual(mixed.exception.code, "unsafe_destination")
        self.assertEqual(transport.calls, [])

    def test_redirects_are_revalidated_limited_loop_checked_and_never_downgrade(self) -> None:
        body, resolver, transport = self.fetch(
            "https://captions.example/start.vtt",
            answers={"captions.example": ("8.8.8.8",)},
            responses=[
                FakeResponse(302, headers={"Location": "/next.vtt"}),
                FakeResponse(200, chunks=(b"caption",)),
            ],
        )
        self.assertEqual(body, b"caption")
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(resolver.requests, [("captions.example", 443)] * 2)

        resolver = SequencedResolver((("8.8.8.8",), ("10.0.0.1",)))
        transport = RecordingTransport([FakeResponse(302, headers={"Location": "/next.vtt"})])
        fetcher = BoundedCaptionFetcher(resolver=resolver, transport=transport)
        with tempfile.TemporaryFile() as output:
            with self.assertRaises(CaptionNetworkError) as rebind:
                fetcher.fetch(
                    caption_resource("https://captions.example/start.vtt"),
                    output.fileno(),
                    max_bytes=8,
                )
        self.assertEqual(rebind.exception.code, "unsafe_destination")
        self.assertEqual(resolver.requests, [("captions.example", 443)] * 2)
        self.assertEqual(len(transport.calls), 1)

        for location, expected_code in (
            (None, "redirect_malformed"),
            ("/next%ZZ.vtt", "redirect_malformed"),
            ("http://captions.example/downgrade.vtt", "redirect_downgrade"),
            ("https://127.0.0.1/private.vtt", "unsafe_url"),
        ):
            with self.subTest(location=location):
                resolver = StaticResolver({"captions.example": ("8.8.8.8",)})
                transport = RecordingTransport([FakeResponse(302, headers={} if location is None else {"Location": location})])
                fetcher = BoundedCaptionFetcher(resolver=resolver, transport=transport)
                with tempfile.TemporaryFile() as output:
                    with self.assertRaises(CaptionNetworkError) as rejected:
                        fetcher.fetch(
                            caption_resource("https://captions.example/start.vtt"),
                            output.fileno(),
                            max_bytes=8,
                        )
                self.assertEqual(rejected.exception.code, expected_code)

        duplicate_location = FakeResponse(302)
        duplicate_location.location_values = ("/one.vtt", "/two.vtt")
        resolver = StaticResolver({"captions.example": ("8.8.8.8",)})
        transport = RecordingTransport([duplicate_location])
        fetcher = BoundedCaptionFetcher(resolver=resolver, transport=transport)
        with tempfile.TemporaryFile() as output:
            with self.assertRaises(CaptionNetworkError) as duplicate:
                fetcher.fetch(
                    caption_resource("https://captions.example/start.vtt"),
                    output.fileno(),
                    max_bytes=8,
                )
        self.assertEqual(duplicate.exception.code, "redirect_malformed")
        self.assertEqual(len(transport.calls), 1)

        resolver = StaticResolver({"captions.example": ("8.8.8.8",)})
        transport = RecordingTransport(
            [
                FakeResponse(302, headers={"Location": "/one"}),
                FakeResponse(302, headers={"Location": "/two"}),
                FakeResponse(302, headers={"Location": "/three"}),
                FakeResponse(302, headers={"Location": "/four"}),
            ]
        )
        fetcher = BoundedCaptionFetcher(resolver=resolver, transport=transport)
        with tempfile.TemporaryFile() as output:
            with self.assertRaises(CaptionNetworkError) as exceeded:
                fetcher.fetch(
                    caption_resource("https://captions.example/start"),
                    output.fileno(),
                    max_bytes=8,
                )
        self.assertEqual(exceeded.exception.code, "redirect_limit")
        self.assertEqual(exceeded.exception.redirect_count, 3)
        self.assertEqual(len(transport.calls), 4)

        resolver = StaticResolver({"captions.example": ("8.8.8.8",)})
        transport = RecordingTransport(
            [
                FakeResponse(302, headers={"Location": "/one"}),
                FakeResponse(302, headers={"Location": "/start"}),
            ]
        )
        fetcher = BoundedCaptionFetcher(resolver=resolver, transport=transport)
        with tempfile.TemporaryFile() as output:
            with self.assertRaises(CaptionNetworkError) as looped:
                fetcher.fetch(
                    caption_resource("https://captions.example/start"),
                    output.fileno(),
                    max_bytes=8,
                )
        self.assertEqual(looped.exception.code, "redirect_loop")
        self.assertEqual(looped.exception.redirect_count, 1)

    def test_public_cross_origin_redirect_requires_a_new_approval_and_private_cross_origin_fails(self) -> None:
        resolver = StaticResolver(
            {
                "captions.example": ("8.8.8.8",),
                "other-captions.example": ("1.1.1.1",),
            }
        )
        transport = RecordingTransport(
            [FakeResponse(302, headers={"Location": "https://other-captions.example/one.vtt?secret=1"})]
        )
        fetcher = BoundedCaptionFetcher(resolver=resolver, transport=transport)
        with tempfile.TemporaryFile() as output:
            with self.assertRaises(CaptionRedirectApprovalRequired) as redirected:
                fetcher.fetch(
                    caption_resource("https://captions.example/start.vtt"),
                    output.fileno(),
                    max_bytes=8,
                )
        self.assertEqual(redirected.exception.resource.origin.hostname, "other-captions.example")
        self.assertNotIn("secret", str(redirected.exception))
        self.assertEqual(resolver.requests, [("captions.example", 443), ("other-captions.example", 443)])
        self.assertEqual(len(transport.calls), 1)

        resolver = StaticResolver({"captions.example": ("8.8.8.8",), "private.example": ("10.0.0.1",)})
        transport = RecordingTransport([FakeResponse(302, headers={"Location": "https://private.example/one.vtt"})])
        fetcher = BoundedCaptionFetcher(resolver=resolver, transport=transport)
        with tempfile.TemporaryFile() as output:
            with self.assertRaises(CaptionNetworkError) as rejected:
                fetcher.fetch(
                    caption_resource("https://captions.example/start.vtt"),
                    output.fileno(),
                    max_bytes=8,
                )
        self.assertEqual(rejected.exception.code, "unsafe_destination")
        self.assertEqual(len(transport.calls), 1)

    def test_declared_and_streamed_byte_caps_are_strict_and_never_return_partial_success(self) -> None:
        too_large_response = FakeResponse(200, headers={"Content-Length": "9"}, chunks=(b"ignored",))
        resolver = StaticResolver({"captions.example": ("8.8.8.8",)})
        transport = RecordingTransport([too_large_response])
        fetcher = BoundedCaptionFetcher(resolver=resolver, transport=transport)
        with tempfile.TemporaryFile() as output:
            with self.assertRaises(CaptionResponseTooLarge):
                fetcher.fetch(
                    caption_resource("https://captions.example/one.vtt"),
                    output.fileno(),
                    max_bytes=8,
                )
            output.seek(0)
            self.assertEqual(output.read(), b"")
        self.assertEqual(too_large_response.read_calls, 0)

        conflicting_lengths = FakeResponse(200, chunks=(b"ignored",))
        conflicting_lengths.content_lengths = ("7", "8")
        resolver = StaticResolver({"captions.example": ("8.8.8.8",)})
        transport = RecordingTransport([conflicting_lengths])
        fetcher = BoundedCaptionFetcher(resolver=resolver, transport=transport)
        with tempfile.TemporaryFile() as output:
            with self.assertRaises(CaptionNetworkError) as conflicting:
                fetcher.fetch(
                    caption_resource("https://captions.example/conflicting.vtt"),
                    output.fileno(),
                    max_bytes=8,
                )
        self.assertEqual(conflicting.exception.code, "transport_failure")
        self.assertEqual(conflicting_lengths.read_calls, 0)

        exact, _, _ = self.fetch(
            "https://captions.example/exact.vtt",
            answers={"captions.example": ("8.8.8.8",)},
            responses=[FakeResponse(200, chunks=(b"1234", b"5678"))],
        )
        self.assertEqual(exact, b"12345678")

        resolver = StaticResolver({"captions.example": ("8.8.8.8",)})
        transport = RecordingTransport([FakeResponse(200, headers={"Content-Length": "8"}, chunks=(b"1234", b"56789"))])
        fetcher = BoundedCaptionFetcher(resolver=resolver, transport=transport)
        with tempfile.TemporaryFile() as output:
            with self.assertRaises(CaptionResponseTooLarge):
                fetcher.fetch(
                    caption_resource("https://captions.example/stream.vtt"),
                    output.fileno(),
                    max_bytes=8,
                )
            output.seek(0)
            self.assertEqual(output.read(), b"12345678")

    def test_urllib_response_adapter_waits_for_eof_and_detects_a_delayed_byte_beyond_an_underreported_content_length(self) -> None:
        stream = DelayedBodyStream(
            b"HTTP/1.1 200 OK\r\nContent-Length: 8\r\n\r\n",
            (b"12345678", b"9"),
        )
        raw_response = http.client.HTTPResponse(
            RawHttpSocket(stream)
        )
        raw_response.begin()
        connection = CloseRecorder()
        response = _UrllibCaptionResponse(raw_response, connection)
        resolver = StaticResolver({"captions.example": ("8.8.8.8",)})
        transport = RecordingTransport([response])
        fetcher = BoundedCaptionFetcher(resolver=resolver, transport=transport)

        with tempfile.TemporaryFile() as output:
            with self.assertRaises(CaptionResponseTooLarge):
                fetcher.fetch(
                    caption_resource("https://captions.example/underreported.vtt"),
                    output.fileno(),
                    max_bytes=8,
                )
            output.seek(0)
            self.assertEqual(output.read(), b"12345678")
        self.assertTrue(connection.closed)

    def test_truncated_declared_caption_body_fails_instead_of_returning_parseable_partial_data(
        self,
    ) -> None:
        valid_but_short_vtt = b"WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHi\n"
        resolver = StaticResolver({"captions.example": ("8.8.8.8",)})
        transport = RecordingTransport(
            [
                FakeResponse(
                    200,
                    headers={"Content-Length": str(len(valid_but_short_vtt) + 10)},
                    chunks=(valid_but_short_vtt,),
                )
            ]
        )
        fetcher = BoundedCaptionFetcher(resolver=resolver, transport=transport)

        with tempfile.TemporaryFile() as output:
            with self.assertRaises(CaptionNetworkError) as truncated:
                fetcher.fetch(
                    caption_resource("https://captions.example/one.vtt"),
                    output.fileno(),
                    max_bytes=1024,
                )

        self.assertEqual(truncated.exception.code, "transport_failure")
        self.assertEqual(len(transport.calls), 1)

    def test_urllib_response_adapter_handles_exact_boundary_chunked_body_and_timeout_fail_closed(self) -> None:
        def fetch_response(response: object) -> tuple[bytes, CaptionNetworkError | None]:
            resolver = StaticResolver({"captions.example": ("8.8.8.8",)})
            transport = RecordingTransport([response])
            fetcher = BoundedCaptionFetcher(resolver=resolver, transport=transport)
            with tempfile.TemporaryFile() as output:
                try:
                    fetcher.fetch(
                        caption_resource("https://captions.example/body.vtt"),
                        output.fileno(),
                        max_bytes=8,
                    )
                except CaptionNetworkError as error:
                    failure = error
                else:
                    failure = None
                output.seek(0)
                return output.read(), failure

        exact_raw = http.client.HTTPResponse(
            RawHttpSocket(
                DelayedBodyStream(
                    b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n",
                    (b"12345678", b"\r\n", b""),
                    line_reads=(b"8\r\n", b"0\r\n", b"\r\n"),
                )
            )
        )
        exact_raw.begin()
        exact_response = _UrllibCaptionResponse(exact_raw, CloseRecorder())
        exact, exact_failure = fetch_response(exact_response)
        self.assertEqual(exact, b"12345678")
        self.assertIsNone(exact_failure)

        timed_out_raw = http.client.HTTPResponse(
            RawHttpSocket(
                DelayedBodyStream(
                    b"HTTP/1.1 200 OK\r\nContent-Length: 8\r\n\r\n",
                    (b"12345678",),
                    terminal_error=TimeoutError("delayed body never ended"),
                )
            )
        )
        timed_out_raw.begin()
        timed_out, timeout_failure = fetch_response(
            _UrllibCaptionResponse(timed_out_raw, CloseRecorder())
        )
        self.assertEqual(timed_out, b"12345678")
        self.assertIsNotNone(timeout_failure)
        self.assertEqual(timeout_failure.code, "transport_failure")

    def test_pinned_urllib_transport_uses_only_the_sealed_get_request_and_numeric_dials(self) -> None:
        handler = RecordingUrllibHandler(FakeResponse(200))
        factory = RecordingUrllibHandlerFactory(handler)
        resource = caption_resource(
            "https://Captions.example/one.vtt?token=never-display"
        )

        opened = PinnedHttpsTransport(
            timeout_seconds=7.0,
            handler_factory=factory,
        ).open(resource, ("8.8.8.8", "2606:4700:4700::1111"))

        self.assertIs(opened, handler.response)
        self.assertEqual(len(factory.calls), 1)
        request = handler.requests[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(
            request.get_full_url(),
            "https://captions.example/one.vtt?token=never-display",
        )
        headers = {name.casefold(): value for name, value in request.header_items()}
        self.assertEqual(headers["user-agent"], "codex-watch/1")
        self.assertEqual(headers["accept"], "text/vtt, application/ttml+xml")
        self.assertNotIn("authorization", headers)
        self.assertNotIn("proxy-authorization", headers)
        self.assertNotIn("cookie", headers)

        for address, expected_target in (
            ("8.8.8.8", ("8.8.8.8", 443)),
            ("2606:4700:4700::1111", ("2606:4700:4700::1111", 443, 0, 0)),
        ):
            with self.subTest(address=address):
                dial_socket = RecordingDialSocket()
                with mock.patch(
                    "watch_caption_network.socket.socket", return_value=dial_socket
                ) as socket_constructor:
                    returned = _dial_pinned_address(address, 443, 7.0)
                self.assertIs(returned, dial_socket)
                self.assertEqual(dial_socket.timeout, 7.0)
                self.assertEqual(dial_socket.connected, expected_target)
                self.assertFalse(dial_socket.closed)
                self.assertEqual(socket_constructor.call_count, 1)

    def test_pinned_urllib_handler_keeps_its_raw_response_open_and_ignores_request_credentials(
        self,
    ) -> None:
        raw_response = http.client.HTTPResponse(
            RawHttpSocket(
                DelayedBodyStream(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n", ())
            )
        )
        raw_response.begin()
        connection = RecordingPinnedConnection(raw_response)
        resource = caption_resource("https://captions.example/one.vtt?token=sealed")
        handler = _PinnedUrllibHttpsHandler(
            resource, ("8.8.8.8",), timeout_seconds=7.0
        )
        handler._connection_factory = lambda host, timeout: connection
        request = urllib_request.Request(
            "https://captions.example/one.vtt?token=sealed",
            headers={
                "Authorization": "Bearer must-not-forward",
                "Cookie": "session=must-not-forward",
                "User-Agent": "caller-must-not-control",
            },
            method="GET",
        )
        request.timeout = 7.0

        with mock.patch.object(
            urllib_request.AbstractHTTPHandler,
            "do_open",
            side_effect=AssertionError("Inherited urllib open path must not run."),
        ):
            response = handler.https_open(request)

        self.assertEqual(connection.debuglevel, 0)
        self.assertEqual(
            connection.request_call,
            (
                "GET",
                "/one.vtt?token=sealed",
                None,
                {
                    "User-Agent": "codex-watch/1",
                    "Accept": "text/vtt, application/ttml+xml",
                    "Connection": "close",
                },
            ),
        )
        response.close()
        self.assertTrue(connection.closed)

    def test_http_transport_and_unavailable_failures_are_typed_and_redacted(self) -> None:
        resolver = StaticResolver({"captions.example": ("8.8.8.8",)})
        transport = RecordingTransport([FakeResponse(404)])
        fetcher = BoundedCaptionFetcher(resolver=resolver, transport=transport)
        with tempfile.TemporaryFile() as output:
            with self.assertRaises(CaptionUnavailable) as unavailable:
                fetcher.fetch(
                    caption_resource("https://captions.example/one.vtt?token=secret"),
                    output.fileno(),
                    max_bytes=8,
                )
        self.assertEqual(unavailable.exception.code, "unavailable")
        self.assertNotIn("secret", str(unavailable.exception))

        resolver = StaticResolver({"captions.example": ("8.8.8.8",)})
        transport = RecordingTransport([FakeResponse(500)])
        fetcher = BoundedCaptionFetcher(resolver=resolver, transport=transport)
        with tempfile.TemporaryFile() as output:
            with self.assertRaises(CaptionNetworkError) as failure:
                fetcher.fetch(
                    caption_resource("https://captions.example/one.vtt?token=secret"),
                    output.fileno(),
                    max_bytes=8,
                )
        self.assertEqual(failure.exception.code, "http_failure")
        self.assertNotIn("secret", str(failure.exception))

    def test_transport_exception_and_internal_resource_repr_never_expose_a_signed_url(self) -> None:
        resource = caption_resource(
            "https://captions.example/one.vtt?token=never-expose"
        )
        self.assertNotIn("never-expose", repr(resource))

        resolver = StaticResolver({"captions.example": ("8.8.8.8",)})
        transport = SecretFailingTransport()
        fetcher = BoundedCaptionFetcher(resolver=resolver, transport=transport)
        with tempfile.TemporaryFile() as output:
            with self.assertRaises(CaptionNetworkError) as rejected:
                fetcher.fetch(resource, output.fileno(), max_bytes=8)
        rendered_exception = "".join(traceback.format_exception(rejected.exception))
        self.assertEqual(rejected.exception.code, "transport_failure")
        self.assertNotIn("never-expose", rendered_exception)
        self.assertIsNone(rejected.exception.__cause__)
        self.assertEqual(transport.calls, 1)

    def test_response_read_and_close_failures_are_redacted_without_overriding_safe_errors(self) -> None:
        for response, secret in (
            (SecretReadFailingResponse(200), "read-never-expose"),
            (
                SecretCloseFailingResponse(200, chunks=(b"caption",)),
                "close-never-expose",
            ),
        ):
            with self.subTest(response=type(response).__name__):
                resolver = StaticResolver({"captions.example": ("8.8.8.8",)})
                transport = RecordingTransport([response])
                fetcher = BoundedCaptionFetcher(resolver=resolver, transport=transport)
                with tempfile.TemporaryFile() as output:
                    with self.assertRaises(CaptionNetworkError) as rejected:
                        fetcher.fetch(
                            caption_resource(
                                "https://captions.example/one.vtt?token=never-expose"
                            ),
                            output.fileno(),
                            max_bytes=8,
                        )
                rendered_exception = "".join(traceback.format_exception(rejected.exception))
                self.assertEqual(rejected.exception.code, "transport_failure")
                self.assertNotIn(secret, rendered_exception)
                self.assertNotIn("never-expose", rendered_exception)
                self.assertIsNone(rejected.exception.__cause__)


if __name__ == "__main__":
    unittest.main()
