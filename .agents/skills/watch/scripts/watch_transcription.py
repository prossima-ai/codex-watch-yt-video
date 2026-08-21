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
from types import MappingProxyType
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


ProviderName = Literal["openai", "groq", "mistral"]
OPENAI_MAX_AUDIO_CHUNK_BYTES = 19_000_000
OPENAI_MAX_ENCODED_REQUEST_BYTES = 20_000_000
# Conservative local development bounds, not a claim about Mistral entitlement.
MISTRAL_MODEL = "voxtral-mini-2602"
MISTRAL_MAX_AUDIO_CHUNK_BYTES = 19_000_000
MISTRAL_MAX_ENCODED_REQUEST_BYTES = 20_000_000
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
    max_encoded_request_bytes: int | None = None


@dataclass(frozen=True)
class AudioChunkUpload:
    """Legacy adapter fixture shape retained for isolated adapter tests."""

    data: bytes
    filename: str
    content_type: Literal["audio/mpeg"]
    offset_seconds: float
    duration_seconds: float


@dataclass(frozen=True)
class PreparedAudioUpload:
    """The only audio facts the Watch runtime may pass to batch transcription."""

    data: bytes
    filename: str
    content_type: Literal["audio/mpeg"]


@dataclass(frozen=True)
class ProviderAudioUpload:
    """The deliberately timing-free object supplied to a provider adapter."""

    data: bytes
    filename: str
    content_type: Literal["audio/mpeg"]


@dataclass(frozen=True)
class ProviderSegment:
    text: str
    start_seconds: float
    end_seconds: float


@dataclass(frozen=True)
class ProviderChunkResult:
    language: str | None
    segments: tuple[ProviderSegment, ...]
    usage_seconds: float | None = None


class TranscriptionProvider(Protocol):
    @property
    def descriptor(self) -> ProviderDescriptor: ...

    def transcribe_chunk(self, upload: ProviderAudioUpload) -> ProviderChunkResult: ...


@dataclass(frozen=True)
class BatchTranscriptionSuccess:
    result: ProviderChunkResult


@dataclass(frozen=True)
class BatchTranscriptionFailure:
    category: ProviderFailureCategory
    retryable: bool
    safe_detail: str
    retry_after_seconds: float | None = None


BatchTranscriptionResult = BatchTranscriptionSuccess | BatchTranscriptionFailure


class BatchTranscriptionModule:
    """Provider-neutral boundary for one already-prepared audio upload.

    It deliberately owns neither source timing, selection, consent, retries,
    coverage, nor user-facing reporting.  Those remain Watch runtime authority.
    """

    def __init__(self, adapter: TranscriptionProvider) -> None:
        descriptor = getattr(adapter, "descriptor", None)
        if not isinstance(descriptor, ProviderDescriptor):
            raise ValueError("Batch transcription adapters require an immutable route.")
        self._adapter = adapter
        self._descriptor = descriptor

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    def transcribe(self, prepared: PreparedAudioUpload) -> BatchTranscriptionResult:
        try:
            configured_descriptor = getattr(self._adapter, "descriptor", None)
            route_is_unchanged = configured_descriptor == self._descriptor
        except Exception:
            route_is_unchanged = False
        if not route_is_unchanged:
            return BatchTranscriptionFailure(
                category="permanent",
                retryable=False,
                safe_detail=_normalized_failure_detail("permanent"),
            )
        try:
            _validate_prepared_upload(prepared, self._descriptor.max_chunk_bytes)
            result = self._adapter.transcribe_chunk(
                ProviderAudioUpload(
                    data=prepared.data,
                    filename=prepared.filename,
                    content_type=prepared.content_type,
                )
            )
            _validate_provider_chunk_result(result)
        except ProviderCallError as error:
            category = _normalized_failure_category(error.category)
            category_is_known = (
                isinstance(error.category, str) and error.category == category
            )
            return BatchTranscriptionFailure(
                category=category,
                retryable=error.retryable if category_is_known else False,
                safe_detail=_normalized_failure_detail(category),
                retry_after_seconds=error.retry_after_seconds
                if error.retryable and category_is_known
                else None,
            )
        except MissingProviderCredentialError:
            return BatchTranscriptionFailure(
                category="authentication",
                retryable=False,
                safe_detail=_normalized_failure_detail("authentication"),
            )
        except (OSError, TimeoutError):
            return BatchTranscriptionFailure(
                category="permanent",
                retryable=False,
                safe_detail=_normalized_failure_detail("permanent"),
            )
        except Exception:
            return BatchTranscriptionFailure(
                category="permanent",
                retryable=False,
                safe_detail=_normalized_failure_detail("permanent"),
            )
        return BatchTranscriptionSuccess(result)


class ProviderTransport(Protocol):
    def send(
        self,
        descriptor: ProviderDescriptor,
        credential: str,
        upload: ProviderAudioUpload,
    ) -> object: ...


class EncodedProviderTransport(Protocol):
    def send_encoded(
        self,
        descriptor: ProviderDescriptor,
        credential: str,
        *,
        body: bytes,
        content_type: str,
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
        upload: ProviderAudioUpload,
    ) -> object:
        _validate_upload(upload, descriptor.max_chunk_bytes)
        body, content_type = _multipart_request_body(descriptor, upload)
        return self.send_encoded(
            descriptor,
            credential,
            body=body,
            content_type=content_type,
        )

    def send_encoded(
        self,
        descriptor: ProviderDescriptor,
        credential: str,
        *,
        body: bytes,
        content_type: str,
    ) -> object:
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
        _validate_encoded_request_size(descriptor, body)
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
    __slots__ = ("_credential_reader", "_transport")

    descriptor = ProviderDescriptor(
        provider="openai",
        model="whisper-1",
        destination="https://api.openai.com/v1/audio/transcriptions",
        privacy_url="https://platform.openai.com/docs/models/default-usage-policies-by-endpoint",
        max_chunk_bytes=OPENAI_MAX_AUDIO_CHUNK_BYTES,
        max_encoded_request_bytes=OPENAI_MAX_ENCODED_REQUEST_BYTES,
    )

    def __init__(
        self,
        *,
        credential_reader: Callable[[str], str | None],
        transport: ProviderTransport,
    ) -> None:
        self._credential_reader = credential_reader
        self._transport = transport

    def transcribe_chunk(self, upload: ProviderAudioUpload) -> ProviderChunkResult:
        _validate_upload(upload, self.descriptor.max_chunk_bytes)
        request_body, _ = _multipart_request_body(self.descriptor, upload)
        _validate_encoded_request_size(self.descriptor, request_body)
        credential = self._credential_reader("OPENAI_API_KEY")
        if not isinstance(credential, str) or not credential:
            raise MissingProviderCredentialError(
                "OPENAI_API_KEY is unavailable from the permitted credential source."
            )
        response = self._transport.send(self.descriptor, credential, upload)
        return _parse_provider_result(response)


class GroqTranscriptionProvider:
    __slots__ = ("_credential_reader", "_transport")

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

    def transcribe_chunk(self, upload: ProviderAudioUpload) -> ProviderChunkResult:
        _validate_upload(upload, self.descriptor.max_chunk_bytes)
        credential = self._credential_reader("GROQ_API_KEY")
        if not isinstance(credential, str) or not credential:
            raise MissingProviderCredentialError(
                "GROQ_API_KEY is unavailable from the permitted credential source."
            )
        response = self._transport.send(self.descriptor, credential, upload)
        return _parse_provider_result(response)


class MistralTranscriptionProvider:
    """Pinned direct-upload adapter, available only through the development registry."""

    __slots__ = ("_credential_reader", "_transport")

    descriptor = ProviderDescriptor(
        provider="mistral",
        model=MISTRAL_MODEL,
        destination="https://api.mistral.ai/v1/audio/transcriptions",
        privacy_url="https://docs.mistral.ai/admin/monitor-comply/privacy-data-controls",
        max_chunk_bytes=MISTRAL_MAX_AUDIO_CHUNK_BYTES,
        max_encoded_request_bytes=MISTRAL_MAX_ENCODED_REQUEST_BYTES,
    )

    def __init__(
        self,
        *,
        credential_reader: Callable[[str], str | None],
        transport: EncodedProviderTransport,
    ) -> None:
        self._credential_reader = credential_reader
        self._transport = transport

    def transcribe_chunk(self, upload: ProviderAudioUpload) -> ProviderChunkResult:
        if not isinstance(upload, ProviderAudioUpload):
            raise ValueError("The provider input is not one bounded audio-only chunk.")
        _validate_upload(upload, self.descriptor.max_chunk_bytes)
        request_body, content_type = _multipart_request_body(
            self.descriptor,
            upload,
            response_format=None,
            timestamp_field="timestamp_granularities",
        )
        _validate_encoded_request_size(self.descriptor, request_body)
        credential = self._credential_reader("MISTRAL_API_KEY")
        if not isinstance(credential, str) or not credential:
            raise MissingProviderCredentialError(
                "MISTRAL_API_KEY is unavailable from the permitted credential source."
            )
        response = self._transport.send_encoded(
            self.descriptor,
            credential,
            body=request_body,
            content_type=content_type,
        )
        return _parse_mistral_provider_result(response)


def development_transcription_registry() -> Mapping[
    ProviderName, TranscriptionProvider
]:
    """Build test/development adapters without reading credentials or contacting providers."""

    return MappingProxyType({
        "openai": OpenAITranscriptionProvider(
            credential_reader=_environment_credential_reader,
            transport=UrllibProviderTransport(),
        ),
        "groq": GroqTranscriptionProvider(
            credential_reader=_environment_credential_reader,
            transport=UrllibProviderTransport(),
        ),
        "mistral": MistralTranscriptionProvider(
            credential_reader=_environment_credential_reader,
            transport=UrllibProviderTransport(),
        ),
    })


def default_transcription_providers() -> Mapping[ProviderName, TranscriptionProvider]:
    """Compatibility name for the isolated development/test registry."""

    return development_transcription_registry()


def release_transcription_registry() -> Mapping[ProviderName, TranscriptionProvider]:
    """Keep every release-facing action free of provider clients until the gate closes."""

    return MappingProxyType({})


def release_transcription_providers() -> Mapping[ProviderName, TranscriptionProvider]:
    """Compatibility name for the intentionally empty release registry."""

    return release_transcription_registry()


def _environment_credential_reader(name: str) -> str | None:
    if name not in {"OPENAI_API_KEY", "GROQ_API_KEY", "MISTRAL_API_KEY"}:
        return None
    return os.environ.get(name)


def _multipart_request_body(
    descriptor: ProviderDescriptor,
    upload: ProviderAudioUpload | AudioChunkUpload,
    *,
    response_format: str | None = "verbose_json",
    timestamp_field: str = "timestamp_granularities[]",
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

    response_format_field = (
        () if response_format is None else (text_field("response_format", response_format),)
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
            *response_format_field,
            text_field(timestamp_field, "segment"),
            ending,
        )
    )
    return body, f"multipart/form-data; boundary={boundary}"


def _validate_encoded_request_size(
    descriptor: ProviderDescriptor, body: bytes
) -> None:
    max_encoded_request_bytes = descriptor.max_encoded_request_bytes
    if (
        not isinstance(max_encoded_request_bytes, int)
        or isinstance(max_encoded_request_bytes, bool)
        or max_encoded_request_bytes <= 0
        or len(body) > max_encoded_request_bytes
    ):
        raise ProviderCallError(
            category="size_format",
            retryable=False,
            safe_detail=(
                "The selected provider request exceeds its verified complete "
                "request-size limit."
            ),
        )


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


def _validate_prepared_upload(
    upload: PreparedAudioUpload | ProviderAudioUpload | AudioChunkUpload,
    max_chunk_bytes: int,
) -> None:
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
    ):
        raise ValueError("The provider input is not one bounded audio-only chunk.")


def _validate_upload(
    upload: ProviderAudioUpload | AudioChunkUpload, max_chunk_bytes: int
) -> None:
    _validate_prepared_upload(upload, max_chunk_bytes)
    if isinstance(upload, AudioChunkUpload) and (
        not isinstance(upload.offset_seconds, (int, float))
        or isinstance(upload.offset_seconds, bool)
        or not math.isfinite(upload.offset_seconds)
        or upload.offset_seconds < 0
        or not isinstance(upload.duration_seconds, (int, float))
        or isinstance(upload.duration_seconds, bool)
        or not math.isfinite(upload.duration_seconds)
        or upload.duration_seconds <= 0
    ):
        raise ValueError("The provider input is not one bounded audio-only chunk.")


def _validate_provider_chunk_result(result: object) -> None:
    if not isinstance(result, ProviderChunkResult):
        raise ValueError("The provider returned an invalid transcription object.")
    if result.language is not None and not isinstance(result.language, str):
        raise ValueError("The provider returned an invalid transcription object.")
    if result.usage_seconds is not None and (
        not isinstance(result.usage_seconds, (int, float))
        or isinstance(result.usage_seconds, bool)
        or not math.isfinite(result.usage_seconds)
        or result.usage_seconds < 0
    ):
        raise ValueError("The provider returned an invalid transcription object.")
    for segment in result.segments:
        if (
            not isinstance(segment, ProviderSegment)
            or not isinstance(segment.text, str)
            or not isinstance(segment.start_seconds, (int, float))
            or isinstance(segment.start_seconds, bool)
            or not math.isfinite(segment.start_seconds)
            or not isinstance(segment.end_seconds, (int, float))
            or isinstance(segment.end_seconds, bool)
            or not math.isfinite(segment.end_seconds)
        ):
            raise ValueError("The provider returned an invalid transcription object.")


_NORMALIZED_FAILURE_DETAILS: Mapping[ProviderFailureCategory, str] = {
    "transient_network": "The selected provider request failed transiently.",
    "rate_limit": "The selected provider rate-limited the request.",
    "server_error": "The selected provider reported a transient server error.",
    "authentication": "The selected provider credential or authorization is unavailable.",
    "invalid_input": "The selected provider rejected the prepared audio input.",
    "size_format": "The prepared audio exceeded the selected provider safety limit.",
    "billing_quota": "The selected provider reported a billing or quota limit.",
    "permanent": "The selected provider request failed permanently.",
}


def _normalized_failure_category(category: object) -> ProviderFailureCategory:
    if isinstance(category, str):
        for known_category in _NORMALIZED_FAILURE_DETAILS:
            if category == known_category:
                return known_category
    return "permanent"


def _normalized_failure_detail(category: ProviderFailureCategory) -> str:
    return _NORMALIZED_FAILURE_DETAILS[category]


def _parse_provider_result(value: object) -> ProviderChunkResult:
    if not isinstance(value, Mapping):
        raise ValueError("The provider returned an invalid transcription object.")
    usage_value = value.get("duration")
    if usage_value is None:
        usage_seconds = None
    elif (
        isinstance(usage_value, (int, float))
        and not isinstance(usage_value, bool)
        and math.isfinite(usage_value)
        and usage_value >= 0
    ):
        usage_seconds = float(usage_value)
    else:
        raise ValueError("The provider returned invalid transcription usage.")
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
    return ProviderChunkResult(None, tuple(segments), usage_seconds)


def _parse_mistral_provider_result(value: object) -> ProviderChunkResult:
    if not isinstance(value, Mapping) or value.get("model") != MISTRAL_MODEL:
        raise ValueError("The selected provider returned an invalid transcription object.")
    usage = value.get("usage")
    if usage is None:
        usage_seconds = None
    elif (
        isinstance(usage, Mapping)
        and isinstance(usage.get("prompt_audio_seconds"), (int, float))
        and not isinstance(usage.get("prompt_audio_seconds"), bool)
        and math.isfinite(float(usage["prompt_audio_seconds"]))
        and float(usage["prompt_audio_seconds"]) >= 0
    ):
        usage_seconds = float(usage["prompt_audio_seconds"])
    else:
        raise ValueError("The provider returned invalid transcription usage.")
    return _parse_provider_result(
        {
            "language": value.get("language"),
            "duration": usage_seconds,
            "segments": value.get("segments"),
        }
    )
