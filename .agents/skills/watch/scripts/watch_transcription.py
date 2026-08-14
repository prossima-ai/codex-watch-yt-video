from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from email.utils import parsedate_to_datetime
import errno
import json
import math
import os
import re
import secrets
import socket
import ssl
import time
from typing import Any, Callable, Literal, Mapping, Protocol, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    OpenerDirector,
    ProxyHandler,
    Request,
    build_opener,
)


ProviderName = Literal["openai", "groq"]
TRANSCRIPTION_RELEASE_ENABLED = False
TRANSCRIPTION_RELEASE_BLOCKER = (
    "Provider transcription is release-disabled until each selected provider has "
    "a conservative effective request-size limit that includes multipart/form-data "
    "boundaries, headers, metadata, and every other request-body overhead, not "
    "merely nominal media-file size."
)
ProviderFailureCategory = Literal[
    "transient_network",
    "rate_limit",
    "server_error",
    "authentication",
    "invalid_input",
    "size_format",
    "billing_quota",
    "permanent",
]


@dataclass(frozen=True)
class ProviderDescriptor:
    provider: ProviderName
    model: str
    destination: str
    privacy_url: str
    max_chunk_bytes: int


@dataclass(frozen=True)
class AudioChunkUpload:
    """Bounded audio-only provider input with no source or workspace path."""

    data: bytes
    filename: str
    content_type: Literal["audio/mpeg"]
    offset_seconds: float
    duration_seconds: float


@dataclass(frozen=True)
class ProviderSegment:
    text: str
    start_seconds: float
    end_seconds: float


@dataclass(frozen=True)
class ProviderChunkResult:
    language: str | None
    segments: tuple[ProviderSegment, ...]


class TranscriptionProvider(Protocol):
    descriptor: ProviderDescriptor

    def transcribe_chunk(self, upload: AudioChunkUpload) -> ProviderChunkResult: ...


class ProviderTransport(Protocol):
    def send(
        self,
        descriptor: ProviderDescriptor,
        credential: str,
        upload: AudioChunkUpload,
    ) -> object: ...


class RejectingProviderRedirectHandler(HTTPRedirectHandler):
    """Reject every provider redirect before an authorization header can move."""

    def redirect_request(
        self,
        request: Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> Request | None:
        del new_url
        raise HTTPError(
            request.full_url,
            code,
            "Provider redirects are not permitted.",
            headers,
            file_pointer,
        )


class MissingProviderCredentialError(RuntimeError):
    pass


class ProviderCallError(RuntimeError):
    def __init__(
        self,
        *,
        category: ProviderFailureCategory,
        retryable: bool,
        safe_detail: str,
        retry_after_seconds: float | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__("The selected transcription provider request failed.")
        self.category = category
        self.retryable = retryable
        self.safe_detail = safe_detail
        self.retry_after_seconds = retry_after_seconds
        self.status_code = status_code


class UrllibProviderTransport:
    """Small provider HTTP boundary that accepts audio bytes, never filesystem paths."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 60.0,
        response_limit_bytes: int = 8 * 1024 * 1024,
        opener: OpenerDirector | None = None,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        if timeout_seconds <= 0 or response_limit_bytes <= 0:
            raise ValueError("Provider transport bounds must be positive.")
        self._timeout_seconds = timeout_seconds
        self._response_limit_bytes = response_limit_bytes
        self._opener = opener or build_opener(
            ProxyHandler({}), RejectingProviderRedirectHandler()
        )
        self._wall_clock = wall_clock

    def send(
        self,
        descriptor: ProviderDescriptor,
        credential: str,
        upload: AudioChunkUpload,
    ) -> object:
        _validate_upload(upload, descriptor.max_chunk_bytes)
        parsed_destination = urlsplit(descriptor.destination)
        if (
            parsed_destination.scheme != "https"
            or parsed_destination.username is not None
            or parsed_destination.password is not None
            or not parsed_destination.hostname
        ):
            raise ProviderCallError(
                category="permanent",
                retryable=False,
                safe_detail="The selected provider destination is invalid.",
            )
        body, content_type = _multipart_request_body(descriptor, upload)
        request = Request(
            descriptor.destination,
            data=body,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {credential}",
                "Content-Type": content_type,
                "User-Agent": "codex-watch/1",
            },
            method="POST",
        )
        try:
            with self._opener.open(
                request, timeout=self._timeout_seconds
            ) as response:
                response_bytes = response.read(self._response_limit_bytes + 1)
        except HTTPError as error:
            try:
                classified_error = _classified_http_error(
                    error, now_epoch_seconds=self._wall_clock()
                )
            finally:
                error.close()
            raise classified_error from None
        except (URLError, TimeoutError, OSError, ValueError) as error:
            raise _classified_network_error(error) from None
        if len(response_bytes) > self._response_limit_bytes:
            raise ProviderCallError(
                category="permanent",
                retryable=False,
                safe_detail="The selected provider response exceeded the local safety limit.",
            )
        try:
            return json.loads(response_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ProviderCallError(
                category="permanent",
                retryable=False,
                safe_detail="The selected provider returned an invalid JSON response.",
            ) from None


class OpenAITranscriptionProvider:
    descriptor = ProviderDescriptor(
        provider="openai",
        model="whisper-1",
        destination="https://api.openai.com/v1/audio/transcriptions",
        privacy_url="https://platform.openai.com/docs/models/default-usage-policies-by-endpoint",
        max_chunk_bytes=24 * 1024 * 1024 - 1,
    )

    def __init__(
        self,
        *,
        credential_reader: Callable[[str], str | None],
        transport: ProviderTransport,
    ) -> None:
        self._credential_reader = credential_reader
        self._transport = transport

    def transcribe_chunk(self, upload: AudioChunkUpload) -> ProviderChunkResult:
        _validate_upload(upload, self.descriptor.max_chunk_bytes)
        credential = self._credential_reader("OPENAI_API_KEY")
        if not isinstance(credential, str) or not credential:
            raise MissingProviderCredentialError(
                "OPENAI_API_KEY is unavailable from the permitted credential source."
            )
        response = self._transport.send(self.descriptor, credential, upload)
        return _parse_provider_result(response)


class GroqTranscriptionProvider:
    descriptor = ProviderDescriptor(
        provider="groq",
        model="whisper-large-v3",
        destination="https://api.groq.com/openai/v1/audio/transcriptions",
        privacy_url="https://console.groq.com/docs/your-data",
        max_chunk_bytes=24 * 1024 * 1024 - 1,
    )

    def __init__(
        self,
        *,
        credential_reader: Callable[[str], str | None],
        transport: ProviderTransport,
    ) -> None:
        self._credential_reader = credential_reader
        self._transport = transport

    def transcribe_chunk(self, upload: AudioChunkUpload) -> ProviderChunkResult:
        _validate_upload(upload, self.descriptor.max_chunk_bytes)
        credential = self._credential_reader("GROQ_API_KEY")
        if not isinstance(credential, str) or not credential:
            raise MissingProviderCredentialError(
                "GROQ_API_KEY is unavailable from the permitted credential source."
            )
        response = self._transport.send(self.descriptor, credential, upload)
        return _parse_provider_result(response)


def default_transcription_providers() -> dict[ProviderName, TranscriptionProvider]:
    """Build isolated adapters without reading credentials or contacting providers."""

    return {
        "openai": OpenAITranscriptionProvider(
            credential_reader=_environment_credential_reader,
            transport=UrllibProviderTransport(),
        ),
        "groq": GroqTranscriptionProvider(
            credential_reader=_environment_credential_reader,
            transport=UrllibProviderTransport(),
        ),
    }


def release_transcription_providers() -> dict[ProviderName, TranscriptionProvider]:
    """Keep every release-facing action free of provider clients until the gate closes."""

    return {}


def _environment_credential_reader(name: str) -> str | None:
    if name not in {"OPENAI_API_KEY", "GROQ_API_KEY"}:
        return None
    return os.environ.get(name)


def _multipart_request_body(
    descriptor: ProviderDescriptor, upload: AudioChunkUpload
) -> tuple[bytes, str]:
    boundary = "codex-watch-" + secrets.token_hex(16)
    while boundary.encode("ascii") in upload.data:
        boundary = "codex-watch-" + secrets.token_hex(16)
    delimiter = f"--{boundary}\r\n".encode("ascii")
    ending = f"--{boundary}--\r\n".encode("ascii")

    def text_field(name: str, value: str) -> bytes:
        if any(character in value for character in "\r\n"):
            raise ValueError("Provider form values must be single-line strings.")
        return (
            delimiter
            + f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(
                "ascii"
            )
            + value.encode("utf-8")
            + b"\r\n"
        )

    body = b"".join(
        (
            delimiter,
            (
                'Content-Disposition: form-data; name="file"; '
                f'filename="{upload.filename}"\r\n'
            ).encode("ascii"),
            f"Content-Type: {upload.content_type}\r\n\r\n".encode("ascii"),
            upload.data,
            b"\r\n",
            text_field("model", descriptor.model),
            text_field("response_format", "verbose_json"),
            text_field("timestamp_granularities[]", "segment"),
            ending,
        )
    )
    return body, f"multipart/form-data; boundary={boundary}"


def _classified_http_error(
    error: HTTPError, *, now_epoch_seconds: float
) -> ProviderCallError:
    status = int(error.code)
    error_code = _provider_error_code(error)
    retry_after = _retry_after_seconds(
        error.headers.get("Retry-After"),
        now_epoch_seconds=now_epoch_seconds,
    )
    if status in {401, 403}:
        category: ProviderFailureCategory = "authentication"
        retryable = False
        detail = "The selected provider rejected its credential or authorization."
    elif status == 413:
        category = "size_format"
        retryable = False
        detail = "The selected provider rejected the bounded audio size or format."
    elif status == 429 and error_code in {
        "billing_hard_limit_reached",
        "billing_not_active",
        "insufficient_quota",
        "usage_limit_reached",
    }:
        category = "billing_quota"
        retryable = False
        detail = "The selected provider reported a billing or quota limit."
    elif status == 429:
        category = "rate_limit"
        retryable = True
        detail = "The selected provider rate-limited the request."
    elif status in {408, 425}:
        category = "transient_network"
        retryable = True
        detail = "The selected provider request failed transiently."
    elif 500 <= status <= 599:
        category = "server_error"
        retryable = True
        detail = "The selected provider reported a transient server error."
    elif status in {400, 404, 409, 415, 422}:
        category = "invalid_input"
        retryable = False
        detail = "The selected provider rejected the request input."
    else:
        category = "permanent"
        retryable = False
        detail = "The selected provider request failed permanently."
    return ProviderCallError(
        category=category,
        retryable=retryable,
        safe_detail=detail,
        retry_after_seconds=retry_after if retryable else None,
        status_code=status,
    )


def _provider_error_code(error: HTTPError) -> str | None:
    if error.fp is None:
        return None
    try:
        raw_body = error.read(64 * 1024)
        value = json.loads(raw_body.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, Mapping):
        return None
    error_value = value.get("error")
    if not isinstance(error_value, Mapping):
        return None
    for field in ("code", "type"):
        code = error_value.get(field)
        if isinstance(code, str):
            return code.lower()
    return None


def _classified_network_error(error: BaseException) -> ProviderCallError:
    reason = error.reason if isinstance(error, URLError) else error
    transient = _is_known_transient_network_error(reason)
    return ProviderCallError(
        category="transient_network" if transient else "permanent",
        retryable=transient,
        safe_detail=(
            "The selected provider network request failed transiently."
            if transient
            else "The selected provider request failed due to a permanent transport error."
        ),
    )


def _is_known_transient_network_error(error: object) -> bool:
    if isinstance(error, (ssl.SSLCertVerificationError, ssl.SSLError)):
        return False
    if isinstance(
        error,
        (
            TimeoutError,
            ConnectionResetError,
            ConnectionAbortedError,
            ConnectionRefusedError,
            BrokenPipeError,
        ),
    ):
        return True
    if isinstance(error, socket.gaierror):
        return error.errno == getattr(socket, "EAI_AGAIN", None)
    if isinstance(error, OSError):
        return error.errno in {
            errno.ECONNABORTED,
            errno.ECONNREFUSED,
            errno.ECONNRESET,
            errno.EHOSTUNREACH,
            errno.ENETDOWN,
            errno.ENETUNREACH,
            errno.EPIPE,
            errno.ETIMEDOUT,
        }
    return False


def _retry_after_seconds(
    value: str | None, *, now_epoch_seconds: float
) -> float | None:
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            seconds = retry_at.timestamp() - now_epoch_seconds
        except (TypeError, ValueError, OverflowError):
            return None
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return min(seconds, 60.0)


def _validate_upload(upload: AudioChunkUpload, max_chunk_bytes: int) -> None:
    filename_match = (
        re.fullmatch(
            r"audio-chunk-([0-9]{4}|10000)\.mp3",
            upload.filename,
            flags=re.ASCII,
        )
        if isinstance(upload.filename, str)
        else None
    )
    if (
        upload.content_type != "audio/mpeg"
        or filename_match is None
        or int(filename_match.group(1)) == 0
        or not isinstance(upload.data, bytes)
        or not upload.data
        or not isinstance(max_chunk_bytes, int)
        or isinstance(max_chunk_bytes, bool)
        or max_chunk_bytes <= 1
        or len(upload.data) >= max_chunk_bytes
        or not isinstance(upload.offset_seconds, (int, float))
        or isinstance(upload.offset_seconds, bool)
        or not math.isfinite(upload.offset_seconds)
        or upload.offset_seconds < 0
        or not isinstance(upload.duration_seconds, (int, float))
        or isinstance(upload.duration_seconds, bool)
        or not math.isfinite(upload.duration_seconds)
        or upload.duration_seconds <= 0
    ):
        raise ValueError("The provider input is not one bounded audio-only chunk.")


def _parse_provider_result(value: object) -> ProviderChunkResult:
    if not isinstance(value, Mapping):
        raise ValueError("The provider returned an invalid transcription object.")
    language_value = value.get("language")
    language = language_value if isinstance(language_value, str) and language_value else None
    raw_segments = value.get("segments")
    if not isinstance(raw_segments, Sequence) or isinstance(raw_segments, (str, bytes)):
        raise ValueError("The provider returned invalid transcript segments.")
    segments: list[ProviderSegment] = []
    for raw_segment in raw_segments:
        if not isinstance(raw_segment, Mapping):
            raise ValueError("The provider returned an invalid transcript segment.")
        text = raw_segment.get("text")
        start = raw_segment.get("start")
        end = raw_segment.get("end")
        if (
            not isinstance(text, str)
            or not isinstance(start, (int, float))
            or isinstance(start, bool)
            or not isinstance(end, (int, float))
            or isinstance(end, bool)
        ):
            raise ValueError("The provider returned an invalid transcript segment.")
        segments.append(ProviderSegment(text, float(start), float(end)))
    return ProviderChunkResult(language, tuple(segments))
