from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from toc.http import HttpError


_ALLOWED_SCHEMES = frozenset({"http", "https"})
DEFAULT_MAX_MEDIA_BYTES = 512 * 1024 * 1024
_SENSITIVE_REDIRECT_HEADERS = frozenset(
    {"authorization", "proxy-authorization", "cookie"}
)


def _public_ip_address(raw_address: str, *, url: str) -> None:
    address = raw_address.split("%", 1)[0]
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError as exc:
        raise ValueError(f"media URL resolved to an invalid IP address: {url}") from exc
    if (
        not parsed.is_global
        or parsed.is_private
        or parsed.is_loopback
        or parsed.is_link_local
        or parsed.is_reserved
        or parsed.is_multicast
        or parsed.is_unspecified
    ):
        raise ValueError(
            f"media URL host resolved to non-public address {parsed.compressed}: {url}"
        )
    if isinstance(parsed, ipaddress.IPv6Address):
        embedded_addresses = [parsed.ipv4_mapped, parsed.sixtofour]
        if parsed.teredo is not None:
            embedded_addresses.extend(parsed.teredo)
        for embedded in embedded_addresses:
            if embedded is not None:
                _public_ip_address(str(embedded), url=url)


def validate_media_url(url: str) -> str:
    """Reject URLs that could make a provider media download an SSRF request."""

    if not isinstance(url, str) or not url or url != url.strip():
        raise ValueError("media URL must be a non-empty string without surrounding whitespace")
    if any(
        character.isspace() or ord(character) < 32 or ord(character) == 127
        for character in url
    ):
        raise ValueError("media URL must not contain whitespace or control characters")

    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"media URL is malformed: {url}") from exc

    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise ValueError("media URL scheme must be http or https")
    if not host:
        raise ValueError("media URL must include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("media URL must not include embedded credentials")

    try:
        literal = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        literal = None

    if literal is not None:
        _public_ip_address(str(literal), url=url)
        return url

    resolved_port = (
        port if port is not None else (443 if parsed.scheme.lower() == "https" else 80)
    )
    try:
        addresses = socket.getaddrinfo(
            host,
            resolved_port,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise ValueError(f"media URL host could not be resolved: {host}") from exc
    if not addresses:
        raise ValueError(f"media URL host did not resolve to an address: {host}")

    for address in addresses:
        sockaddr = address[4]
        if not sockaddr:
            raise ValueError(f"media URL host returned an invalid DNS result: {host}")
        _public_ip_address(str(sockaddr[0]), url=url)
    return url


class _SafeMediaRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Validate each redirect target and prevent credential propagation."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        validated_url = validate_media_url(newurl)
        redirected = super().redirect_request(
            req,
            fp,
            code,
            msg,
            headers,
            validated_url,
        )
        if redirected is None:
            return None
        for header_map in (redirected.headers, redirected.unredirected_hdrs):
            for header_name in list(header_map):
                if header_name.lower() in _SENSITIVE_REDIRECT_HEADERS:
                    header_map.pop(header_name, None)
        return redirected


def request_public_media_bytes(
    *,
    url: str,
    timeout_seconds: float,
    max_bytes: int = DEFAULT_MAX_MEDIA_BYTES,
) -> bytes:
    """Download public HTTP(S) media without accepting provider credentials."""

    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ValueError("media download size limit must be a positive integer")

    validated_url = validate_media_url(url)
    request = urllib.request.Request(validated_url, method="GET")
    opener = urllib.request.build_opener(_SafeMediaRedirectHandler())
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            headers = getattr(response, "headers", {})
            raw_content_length = headers.get("Content-Length") if hasattr(headers, "get") else None
            if raw_content_length is not None:
                try:
                    content_length = int(str(raw_content_length).strip())
                except ValueError:
                    content_length = -1
                if content_length > max_bytes:
                    raise ValueError(
                        f"media download exceeds size limit of {max_bytes} bytes"
                    )
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise ValueError(
                    f"media download exceeds size limit of {max_bytes} bytes"
                )
            return body
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        raise HttpError(
            status=int(getattr(exc, "code", 0) or 0),
            reason=str(getattr(exc, "reason", "") or ""),
            body=body,
            url=url,
        ) from exc
