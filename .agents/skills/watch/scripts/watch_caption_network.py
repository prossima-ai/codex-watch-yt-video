from __future__ import annotations

from dataclasses import dataclass
import hashlib
import http.client
import ipaddress
import os
import secrets
import socket
import ssl
from typing import Callable, Literal, Mapping, Protocol
from urllib import error as urllib_error
from urllib.parse import urljoin, urlsplit
from urllib import request as urllib_request


MAX_CAPTION_REDIRECTS = 3
CAPTION_RECEIPT_LIFETIME_SECONDS = 5 * 60


_SAFE_ERROR_MESSAGES = {
    "invalid_byte_cap": "The native-caption byte limit is invalid.",
    "unsafe_url": "The native-caption destination is not an approved public HTTPS URL.",
    "unsafe_destination": "The native-caption destination did not resolve only to public addresses.",
    "invalid_receipt": "The native-caption approval receipt is invalid or no longer usable.",
    "expired_receipt": "The native-caption approval receipt has expired.",
    "redirect_malformed": "The native-caption redirect is malformed.",
    "redirect_downgrade": "The native-caption redirect would downgrade HTTPS and was rejected.",
    "redirect_limit": "The native-caption redirect limit was reached.",
    "redirect_loop": "The native-caption redirect loop was rejected.",
    "redirect_approval_required": "A new public native-caption hostname needs separate approval.",
    "response_too_large": "The native-caption response exceeds the approved byte limit.",
    "unavailable": "The selected native caption is unavailable.",
    "http_failure": "The native-caption service returned an unsuccessful response.",
    "transport_failure": "The native-caption request could not be completed.",
}


class CaptionNetworkError(OSError):
    """A deliberately redacted direct-caption networking failure."""

    def __init__(self, code: str, *, redirect_count: int = 0) -> None:
        if (
            isinstance(redirect_count, bool)
            or not isinstance(redirect_count, int)
            or redirect_count < 0
        ):
            raise ValueError("Caption redirect count must be a non-negative integer.")
        self.code = code
        self.redirect_count = redirect_count
        super().__init__(_SAFE_ERROR_MESSAGES[code])


class CaptionApprovalReceiptError(CaptionNetworkError):
    pass


class CaptionRedirectApprovalRequired(CaptionNetworkError):
    def __init__(self, resource: CaptionResource, *, redirect_count: int = 0) -> None:
        self.resource = resource
        super().__init__("redirect_approval_required", redirect_count=redirect_count)


class CaptionResponseTooLarge(CaptionNetworkError):
    def __init__(self, *, redirect_count: int = 0) -> None:
        super().__init__("response_too_large", redirect_count=redirect_count)


class CaptionUnavailable(CaptionNetworkError):
    def __init__(self, *, redirect_count: int = 0) -> None:
        super().__init__("unavailable", redirect_count=redirect_count)


@dataclass(frozen=True)
class CaptionOrigin:
    hostname: str
    port: int = 443


class CaptionResource:
    """An opaque internal URL whose serializable surface omits sensitive data."""

    __slots__ = ("_url", "origin", "_request_target", "_identity")

    def __init__(
        self,
        url: str,
        origin: CaptionOrigin,
        request_target: str,
        identity: str,
    ) -> None:
        object.__setattr__(self, "_url", url)
        object.__setattr__(self, "origin", origin)
        object.__setattr__(self, "_request_target", request_target)
        object.__setattr__(self, "_identity", identity)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("CaptionResource is immutable.")

    def __repr__(self) -> str:
        return f"CaptionResource(origin={self.origin!r})"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, CaptionResource)
            and self._url == other._url
            and self.origin == other.origin
            and self._request_target == other._request_target
            and self._identity == other._identity
        )

    def __hash__(self) -> int:
        return hash((self._url, self.origin, self._request_target, self._identity))

    def __copy__(self) -> CaptionResource:
        return self

    def __deepcopy__(self, memo: dict[int, object]) -> CaptionResource:
        del memo
        return self

    @property
    def request_target(self) -> str:
        return self._request_target


def caption_resource(value: object) -> CaptionResource:
    """Parse only an exact public HTTPS caption destination, without DNS access."""

    if (
        not isinstance(value, str)
        or not value
        or any(ord(character) <= 0x20 for character in value)
        or _has_invalid_percent_escape(value)
    ):
        raise CaptionNetworkError("unsafe_url")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise CaptionNetworkError("unsafe_url") from None
    if (
        parsed.scheme.casefold() != "https"
        or parsed.username is not None
        or parsed.password is not None
        or not parsed.hostname
        or "%" in parsed.hostname
        or _has_empty_explicit_port(parsed.netloc)
    ):
        raise CaptionNetworkError("unsafe_url")
    hostname = _normalized_hostname(parsed.hostname)
    if hostname is None or _is_ip_literal_or_local_alias(hostname):
        raise CaptionNetworkError("unsafe_url")
    if port not in {None, 443}:
        raise CaptionNetworkError("unsafe_url")
    target = parsed.path or "/"
    if parsed.query:
        target += "?" + parsed.query
    identity = hashlib.sha256(
        (hostname + "\x00" + target).encode("utf-8", "surrogatepass")
    ).hexdigest()
    return CaptionResource(value, CaptionOrigin(hostname), target, identity)


def _has_empty_explicit_port(netloc: str) -> bool:
    authority = netloc.rsplit("@", 1)[-1]
    return authority.endswith(":")


def _has_invalid_percent_escape(value: str) -> bool:
    index = value.find("%")
    while index >= 0:
        escaped = value[index + 1 : index + 3]
        if len(escaped) != 2 or any(
            character not in "0123456789abcdefABCDEF" for character in escaped
        ):
            return True
        index = value.find("%", index + 3)
    return False


def _normalized_hostname(value: str) -> str | None:
    hostname = value.rstrip(".")
    if not hostname:
        return None
    try:
        return hostname.encode("idna").decode("ascii").casefold()
    except UnicodeError:
        return None


def _is_ip_literal_or_local_alias(hostname: str) -> bool:
    if hostname == "localhost" or hostname.endswith(
        (".localhost", ".local", ".internal")
    ):
        return True
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        try:
            socket.inet_aton(hostname)
        except OSError:
            return False
        return True
    return True


class CaptionResolver(Protocol):
    def resolve(self, hostname: str, port: int) -> tuple[str, ...]: ...


class CaptionResponse(Protocol):
    status: int
    headers: Mapping[str, str]

    def read(self, size: int) -> bytes: ...

    def close(self) -> None: ...


class CaptionTransport(Protocol):
    def open(
        self, resource: CaptionResource, addresses: tuple[str, ...]
    ) -> CaptionResponse: ...


class _CaptionUrllibHandler(Protocol):
    def https_open(self, request: urllib_request.Request) -> CaptionResponse: ...


class SystemCaptionResolver:
    def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        try:
            answers = socket.getaddrinfo(
                hostname,
                port,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
            )
        except OSError:
            raise CaptionNetworkError("unsafe_destination") from None
        addresses = tuple(dict.fromkeys(answer[4][0] for answer in answers))
        if not addresses:
            raise CaptionNetworkError("unsafe_destination")
        return addresses


class _PinnedHttpsConnection(http.client.HTTPSConnection):
    """HTTPS connection that dials only already-validated resolved addresses."""

    def __init__(
        self,
        hostname: str,
        port: int,
        addresses: tuple[str, ...],
        *,
        timeout: float,
        context: ssl.SSLContext,
    ) -> None:
        super().__init__(hostname, port=port, timeout=timeout, context=context)
        self._caption_addresses = addresses

    def connect(self) -> None:
        last_error: OSError | None = None
        raw_socket: socket.socket | None = None
        for address in self._caption_addresses:
            try:
                raw_socket = _dial_pinned_address(address, self.port, self.timeout)
                break
            except OSError as error:
                last_error = error
        if raw_socket is None:
            if last_error is None:
                raise OSError("No validated caption address was available.")
            raise last_error
        try:
            self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)
        except Exception:
            raw_socket.close()
            raise


def _dial_pinned_address(address: str, port: int, timeout: float) -> socket.socket:
    """Dial a numeric answer directly, without another hostname resolution."""

    parsed = ipaddress.ip_address(address)
    family = socket.AF_INET6 if parsed.version == 6 else socket.AF_INET
    target: tuple[object, ...]
    if family == socket.AF_INET6:
        target = (address, port, 0, 0)
    else:
        target = (address, port)
    raw_socket = socket.socket(family, socket.SOCK_STREAM)
    try:
        raw_socket.settimeout(timeout)
        raw_socket.connect(target)
        return raw_socket
    except Exception:
        raw_socket.close()
        raise


class _ChunkedCaptionReader:
    """A bounded, strict chunked-body decoder over urllib's raw response stream."""

    _MAX_LINE_BYTES = 8 * 1024
    _MAX_TRAILER_BYTES = 64 * 1024

    def __init__(self, stream: object) -> None:
        self._stream = stream
        self._remaining = 0
        self._complete = False

    def read(self, size: int) -> bytes:
        if not isinstance(size, int) or size <= 0:
            return b""
        output = bytearray()
        while len(output) < size:
            if self._complete:
                # The direct action requires a definitive end of body.  The
                # request explicitly uses Connection: close, so waiting here
                # either sees EOF, detects surplus bytes, or fails closed on
                # a transport timeout.
                if self._read_raw(1):
                    raise OSError("Unexpected bytes after chunked caption body.")
                return bytes(output)
            if self._remaining == 0:
                self._begin_chunk()
                continue
            wanted = min(size - len(output), self._remaining)
            chunk = self._read_raw(wanted)
            if not chunk:
                raise OSError("Truncated chunked caption body.")
            output.extend(chunk)
            self._remaining -= len(chunk)
            if self._remaining == 0 and self._read_exact(2) != b"\r\n":
                raise OSError("Malformed chunked caption body.")
        return bytes(output)

    def _begin_chunk(self) -> None:
        line = self._read_line()
        if not line.endswith(b"\r\n"):
            raise OSError("Malformed chunked caption body.")
        encoded_size = line[:-2].split(b";", 1)[0]
        if not encoded_size or any(
            character not in b"0123456789abcdefABCDEF" for character in encoded_size
        ):
            raise OSError("Malformed chunked caption body.")
        chunk_size = int(encoded_size, 16)
        if chunk_size == 0:
            self._consume_trailers()
            self._complete = True
            return
        self._remaining = chunk_size

    def _consume_trailers(self) -> None:
        total = 0
        while True:
            line = self._read_line()
            total += len(line)
            if total > self._MAX_TRAILER_BYTES:
                raise OSError("Chunked caption trailers are too large.")
            if line == b"\r\n":
                return
            if not line.endswith(b"\r\n"):
                raise OSError("Malformed chunked caption trailers.")

    def _read_line(self) -> bytes:
        readline = getattr(self._stream, "readline", None)
        if not callable(readline):
            raise OSError("Caption response is not a readable stream.")
        value = readline(self._MAX_LINE_BYTES + 1)
        if not isinstance(value, bytes) or not value or len(value) > self._MAX_LINE_BYTES:
            raise OSError("Malformed chunked caption body.")
        return value

    def _read_exact(self, size: int) -> bytes:
        output = bytearray()
        while len(output) < size:
            value = self._read_raw(size - len(output))
            if not value:
                return b""
            output.extend(value)
        return bytes(output)

    def _read_raw(self, size: int) -> bytes:
        read = getattr(self._stream, "read", None)
        if not callable(read):
            raise OSError("Caption response is not a readable stream.")
        value = read(size)
        if not isinstance(value, bytes):
            raise OSError("Caption response is not bytes.")
        return value


class _UrllibCaptionResponse:
    """Raw urllib response reader that never trusts Content-Length framing."""

    def __init__(
        self, response: http.client.HTTPResponse, connection: http.client.HTTPConnection
    ) -> None:
        self.status = response.status
        self.headers = {name: value for name, value in response.getheaders()}
        self._response = response
        self._connection = connection
        header_values = response.headers.get_all("Content-Length")
        self.content_lengths = tuple(header_values or ())
        location_values = response.headers.get_all("Location")
        self.location_values = tuple(location_values or ())
        stream = response.fp
        self._chunked_reader = _ChunkedCaptionReader(stream) if response.chunked else None

    def read(self, size: int) -> bytes:
        if self._chunked_reader is not None:
            return self._chunked_reader.read(size)
        stream = self._response.fp
        if stream is None:
            return b""
        value = stream.read(size)
        if not isinstance(value, bytes):
            raise OSError("Caption response is not bytes.")
        return value

    def close(self) -> None:
        try:
            self._response.close()
        finally:
            self._connection.close()


class PinnedHttpsTransport:
    """Direct urllib HTTPS transport with pinned DNS and no redirect/proxy handlers."""

    def __init__(
        self,
        timeout_seconds: float = 15.0,
        *,
        handler_factory: Callable[
            [CaptionResource, tuple[str, ...], float], _CaptionUrllibHandler
        ]
        | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._handler_factory = handler_factory or _new_pinned_urllib_handler

    def open(
        self, resource: CaptionResource, addresses: tuple[str, ...]
    ) -> CaptionResponse:
        # Do not use urlopen() or an opener: either can inherit proxy,
        # redirect, auth, cookie, or audit-hook behavior.  This one direct
        # urllib HTTPS handler receives a request built only from the sealed
        # resource and returns 3xx responses to the explicit policy layer.
        request = urllib_request.Request(
            f"https://{resource.origin.hostname}{resource.request_target}",
            headers={
                "User-Agent": "codex-watch/1",
                "Accept": "text/vtt, application/ttml+xml",
            },
            method="GET",
        )
        request.timeout = self._timeout_seconds
        handler = self._handler_factory(resource, addresses, self._timeout_seconds)
        return handler.https_open(request)


def _new_pinned_urllib_handler(
    resource: CaptionResource, addresses: tuple[str, ...], timeout_seconds: float
) -> _CaptionUrllibHandler:
    return _PinnedUrllibHttpsHandler(
        resource,
        addresses,
        timeout_seconds=timeout_seconds,
    )


class _PinnedUrllibHttpsHandler(urllib_request.HTTPSHandler):
    """The sole urllib handler: pinned HTTPS, no redirect/proxy/auth surface."""

    def __init__(
        self,
        resource: CaptionResource,
        addresses: tuple[str, ...],
        *,
        timeout_seconds: float,
    ) -> None:
        # A global http.client debug level can print request targets.  Direct
        # caption URLs are sensitive internal data, so force it off here.
        super().__init__(debuglevel=0, context=ssl.create_default_context())
        self._resource = resource
        self._addresses = addresses
        self._timeout_seconds = timeout_seconds

    def https_open(self, request: urllib_request.Request) -> CaptionResponse:
        if (
            request.type != "https"
            or request.host != self._resource.origin.hostname
            or request.get_method() != "GET"
            or request.selector != self._resource.request_target
            or request.data is not None
        ):
            raise urllib_error.URLError("Unexpected caption request.")
        connection = self._connection_factory(request.host, request.timeout)
        try:
            # This mirrors urllib's HTTPS handler request operation but does
            # not call AbstractHTTPHandler.do_open(): that inherited method
            # closes h.sock immediately after getresponse(), which would make
            # an exact-cap check unable to wait for the definitive body EOF.
            # No caller-provided headers are copied, so authorization, cookie,
            # proxy, or other ambient state cannot move to this destination.
            connection.set_debuglevel(0)
            connection.request(
                "GET",
                request.selector,
                None,
                {
                    "User-Agent": "codex-watch/1",
                    "Accept": "text/vtt, application/ttml+xml",
                    "Connection": "close",
                },
            )
            response = connection.getresponse()
            return _UrllibCaptionResponse(response, connection)
        except (OSError, http.client.HTTPException):
            connection.close()
            raise urllib_error.URLError("Caption transport failed.") from None
        except Exception:
            connection.close()
            raise

    def _connection_factory(
        self, host: str, timeout: object, **_kwargs: object
    ) -> _PinnedHttpsConnection:
        if host != self._resource.origin.hostname or timeout != self._timeout_seconds:
            raise urllib_error.URLError("Unexpected caption request.")
        return _PinnedHttpsConnection(
            self._resource.origin.hostname,
            self._resource.origin.port,
            self._addresses,
            timeout=self._timeout_seconds,
            context=self._context,
        )


@dataclass(frozen=True)
class CaptionFetchResult:
    bytes_read: int
    redirect_count: int


class BoundedCaptionFetcher:
    """Resolve, pin, redirect-check, and bound one approved native-caption fetch."""

    def __init__(
        self,
        *,
        resolver: CaptionResolver | None = None,
        transport: CaptionTransport | None = None,
    ) -> None:
        self._resolver = resolver or SystemCaptionResolver()
        self._transport = transport or PinnedHttpsTransport()

    def fetch(
        self, resource: CaptionResource, output_fd: int, *, max_bytes: int
    ) -> CaptionFetchResult:
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
            raise CaptionNetworkError("invalid_byte_cap")
        # The generic fetch seam deliberately accepts only the sealed internal
        # resource, never a raw signed URL from an arbitrary caller.  Reparse
        # it to reject a forged dataclass with inconsistent safe metadata.
        if not isinstance(resource, CaptionResource):
            raise CaptionNetworkError("unsafe_url")
        approved_resource = caption_resource(resource._url)
        if approved_resource != resource:
            raise CaptionNetworkError("unsafe_url")
        current = approved_resource
        seen = {current._identity}
        redirects = 0
        while True:
            try:
                addresses = self._resolve_public_addresses(current)
            except CaptionNetworkError as error:
                error.redirect_count = redirects
                raise
            try:
                response = self._transport.open(current, addresses)
            except CaptionNetworkError as error:
                error.redirect_count = redirects
                raise
            except Exception:
                # A transport exception can embed a full request target.  The
                # public error must remain independently safe to render.
                raise CaptionNetworkError(
                    "transport_failure", redirect_count=redirects
                ) from None
            try:
                if response.status in {301, 302, 303, 307, 308}:
                    if redirects >= MAX_CAPTION_REDIRECTS:
                        raise CaptionNetworkError(
                            "redirect_limit", redirect_count=redirects
                        )
                    redirected = _redirect_resource(
                        current,
                        _redirect_location(response, redirect_count=redirects),
                        redirect_count=redirects,
                    )
                    if redirected.origin != approved_resource.origin:
                        try:
                            self._resolve_public_addresses(redirected)
                        except CaptionNetworkError as error:
                            error.redirect_count = redirects
                            raise
                        raise CaptionRedirectApprovalRequired(
                            redirected, redirect_count=redirects
                        )
                    if redirected._identity in seen:
                        raise CaptionNetworkError(
                            "redirect_loop", redirect_count=redirects
                        )
                    seen.add(redirected._identity)
                    redirects += 1
                    next_resource = redirected
                    result = None
                elif response.status in {404, 410}:
                    raise CaptionUnavailable()
                elif response.status < 200 or response.status >= 300:
                    raise CaptionNetworkError("http_failure")
                else:
                    next_resource = None
                    result = CaptionFetchResult(
                        _copy_bounded_body(response, output_fd, max_bytes), redirects
                    )
            except CaptionNetworkError as error:
                error.redirect_count = redirects
                self._close_after_failure(response)
                raise
            except Exception:
                self._close_after_failure(response)
                raise CaptionNetworkError(
                    "transport_failure", redirect_count=redirects
                ) from None
            try:
                response.close()
            except Exception:
                raise CaptionNetworkError(
                    "transport_failure", redirect_count=redirects
                ) from None
            if next_resource is not None:
                current = next_resource
                continue
            assert result is not None
            return result

    def _resolve_public_addresses(self, resource: CaptionResource) -> tuple[str, ...]:
        try:
            answers = self._resolver.resolve(resource.origin.hostname, resource.origin.port)
            return _public_addresses(answers)
        except CaptionNetworkError:
            raise
        except Exception:
            raise CaptionNetworkError("unsafe_destination") from None

    @staticmethod
    def _close_after_failure(response: CaptionResponse) -> None:
        try:
            response.close()
        except Exception:
            # A close error is never allowed to replace the already-safe
            # primary result or leak request-target material through chaining.
            pass


def _public_addresses(values: object) -> tuple[str, ...]:
    if not isinstance(values, tuple) or not values:
        raise CaptionNetworkError("unsafe_destination")
    validated: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise CaptionNetworkError("unsafe_destination")
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            raise CaptionNetworkError("unsafe_destination") from None
        if (
            not address.is_global
            or address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_unspecified
            or address.is_reserved
        ):
            raise CaptionNetworkError("unsafe_destination")
        validated.append(str(address))
    return tuple(dict.fromkeys(validated))


def _header(headers: Mapping[str, str], name: str) -> str | None:
    for header_name, value in headers.items():
        if header_name.casefold() == name:
            return value
    return None


def _redirect_location(
    response: CaptionResponse, *, redirect_count: int = 0
) -> str | None:
    values = getattr(response, "location_values", None)
    if values is None:
        return _header(response.headers, "location")
    if (
        not isinstance(values, tuple)
        or len(values) != 1
        or not isinstance(values[0], str)
    ):
        raise CaptionNetworkError("redirect_malformed", redirect_count=redirect_count)
    return values[0]


def _redirect_resource(
    current: CaptionResource, location: str | None, *, redirect_count: int = 0
) -> CaptionResource:
    if (
        not isinstance(location, str)
        or not location
        or any(ord(character) <= 0x20 for character in location)
        or _has_invalid_percent_escape(location)
    ):
        raise CaptionNetworkError("redirect_malformed", redirect_count=redirect_count)
    redirected_url = urljoin(current._url, location)
    try:
        parsed = urlsplit(redirected_url)
    except ValueError:
        raise CaptionNetworkError(
            "redirect_malformed", redirect_count=redirect_count
        ) from None
    if parsed.scheme.casefold() == "http":
        raise CaptionNetworkError("redirect_downgrade", redirect_count=redirect_count)
    try:
        return caption_resource(redirected_url)
    except CaptionNetworkError as error:
        raise CaptionNetworkError(
            error.code, redirect_count=redirect_count
        ) from None


def _copy_bounded_body(response: CaptionResponse, output_fd: int, max_bytes: int) -> int:
    declared_length = _validate_declared_content_lengths(response, max_bytes)
    total = 0
    while True:
        # At the exact boundary read one byte more. This catches a body whose
        # missing or misleading Content-Length claimed that it was complete.
        chunk = response.read(min(64 * 1024, max_bytes - total if total < max_bytes else 1))
        if not chunk:
            if declared_length is not None and total != declared_length:
                raise CaptionNetworkError("transport_failure")
            return total
        if not isinstance(chunk, bytes):
            raise CaptionNetworkError("transport_failure")
        if total + len(chunk) > max_bytes:
            raise CaptionResponseTooLarge()
        _write_all_bytes(output_fd, chunk)
        total += len(chunk)


def _validate_declared_content_lengths(
    response: CaptionResponse, max_bytes: int
) -> int | None:
    values = getattr(response, "content_lengths", None)
    if values is None:
        content_length = _header(response.headers, "content-length")
        values = () if content_length is None else (content_length,)
    if not isinstance(values, tuple) or any(not isinstance(value, str) for value in values):
        raise CaptionNetworkError("transport_failure")
    parsed: list[int] = []
    for value in values:
        if not value.isascii() or not value.isdecimal():
            raise CaptionNetworkError("transport_failure")
        declared_length = int(value)
        if declared_length > max_bytes:
            raise CaptionResponseTooLarge()
        parsed.append(declared_length)
    if parsed and any(value != parsed[0] for value in parsed[1:]):
        raise CaptionNetworkError("transport_failure")
    return parsed[0] if parsed else None


def _write_all_bytes(file_descriptor: int, value: bytes) -> None:
    remaining = value
    while remaining:
        written = os.write(file_descriptor, remaining)
        if written <= 0:
            raise OSError("Could not write the bounded caption response.")
        remaining = remaining[written:]


@dataclass(frozen=True)
class CaptionApprovalDecision:
    """One untrusted decision payload; the registry validates its value."""

    receipt: str
    decision: str


@dataclass(frozen=True)
class CaptionNetworkBinding:
    action: str
    watch_request_id: str
    source_value: str
    session_id: str
    workspace_id: str
    selected_track_id: str
    selected_format: str
    byte_cap: int
    origin: CaptionOrigin


@dataclass(frozen=True)
class CaptionNetworkApproval:
    receipt: str
    hostname: str
    purpose: Literal["retrieve_selected_native_caption"]
    selected_track_id: str
    selected_format: str
    byte_cap: int


@dataclass
class _IssuedReceipt:
    binding: CaptionNetworkBinding
    issued_at: float
    consumed: bool = False


class CaptionApprovalRegistry:
    """Same-session, single-use direct-caption approval receipts only."""

    def __init__(
        self,
        *,
        clock: Callable[[], float],
        receipt_factory: Callable[[], str] = lambda: "caption_receipt_"
        + secrets.token_urlsafe(24),
    ) -> None:
        self._clock = clock
        self._receipt_factory = receipt_factory
        self._receipts: dict[str, _IssuedReceipt] = {}

    def issue(self, binding: CaptionNetworkBinding) -> CaptionNetworkApproval:
        if (
            binding.action != "native_caption_retrieval"
            or binding.selected_format not in {"vtt", "ttml"}
            or isinstance(binding.byte_cap, bool)
            or binding.byte_cap <= 0
            or binding.origin.port != 443
            or _normalized_hostname(binding.origin.hostname) != binding.origin.hostname
            or _is_ip_literal_or_local_alias(binding.origin.hostname)
        ):
            raise ValueError("Invalid internal native-caption receipt binding.")
        receipt = self._new_receipt()
        self._receipts[receipt] = _IssuedReceipt(binding, self._clock())
        return CaptionNetworkApproval(
            receipt=receipt,
            hostname=binding.origin.hostname,
            purpose="retrieve_selected_native_caption",
            selected_track_id=binding.selected_track_id,
            selected_format=binding.selected_format,
            byte_cap=binding.byte_cap,
        )

    def verify_and_consume(
        self, decision: object, expected_binding: CaptionNetworkBinding
    ) -> CaptionApprovalDecision:
        if (
            not isinstance(decision, CaptionApprovalDecision)
            or not isinstance(decision.receipt, str)
            or not decision.receipt
        ):
            raise CaptionApprovalReceiptError("invalid_receipt")
        issued = self._receipts.get(decision.receipt)
        if issued is None or issued.consumed:
            raise CaptionApprovalReceiptError("invalid_receipt")
        if decision.decision not in {"approved", "declined", "canceled"}:
            issued.consumed = True
            raise CaptionApprovalReceiptError("invalid_receipt")
        if self._clock() >= issued.issued_at + CAPTION_RECEIPT_LIFETIME_SECONDS:
            issued.consumed = True
            raise CaptionApprovalReceiptError("expired_receipt")
        if issued.binding != expected_binding:
            issued.consumed = True
            raise CaptionApprovalReceiptError("invalid_receipt")
        issued.consumed = True
        return decision

    def invalidate_all(self) -> None:
        for issued in self._receipts.values():
            issued.consumed = True

    def invalidate_receipt(self, receipt: object) -> None:
        if isinstance(receipt, str):
            issued = self._receipts.get(receipt)
            if issued is not None:
                issued.consumed = True

    def invalidate_workspace(self, workspace_id: str) -> None:
        for issued in self._receipts.values():
            if issued.binding.workspace_id == workspace_id:
                issued.consumed = True

    def _new_receipt(self) -> str:
        candidate = self._receipt_factory()
        if not isinstance(candidate, str) or not candidate:
            raise ValueError("The caption receipt factory returned no opaque receipt.")
        receipt = candidate
        suffix = 1
        while receipt in self._receipts:
            receipt = f"{candidate}_{suffix}"
            suffix += 1
        return receipt
