"""Bounded public-web fetches with DNS checked at the actual TCP connection."""

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpcore
import httpx

from src.services.economy.errors import EconomyError


def is_public_address(value: str) -> bool:
    address = ipaddress.ip_address(value)
    if not address.is_global or address.is_multicast:
        return False
    if isinstance(address, ipaddress.IPv6Address):
        if address in ipaddress.ip_network("64:ff9b::/96"):
            # The well-known NAT64 prefix can translate to an internal IPv4 peer.
            return is_public_address(str(ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)))
        # These transition formats can otherwise conceal a private IPv4 peer.
        for embedded in (address.ipv4_mapped, address.sixtofour):
            if embedded is not None and not is_public_address(str(embedded)):
                return False
        if address.teredo is not None:
            return False
    return True


def validate_public_url(url: str) -> str:
    value = url.strip()
    try:
        parsed = urlparse(value)
        hostname = (parsed.hostname or "").casefold().rstrip(".")
        port = parsed.port
        httpx.URL(value)
    except (ValueError, httpx.InvalidURL) as exc:
        raise EconomyError("请输入有效的 http:// 或 https:// 网页地址。") from exc
    if parsed.scheme not in {"http", "https"} or not hostname or port == 0:
        raise EconomyError("请输入完整的 http:// 或 https:// 网页地址。")
    if parsed.username or parsed.password:
        raise EconomyError("网页地址不能包含登录凭据。")
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise EconomyError("不允许访问本机或内网地址。")
    try:
        public = is_public_address(hostname)
    except ValueError:
        # Hostnames (including alternative numeric spellings) are checked again
        # after resolution by PublicNetworkBackend before any TCP connection.
        return value
    if not public:
        raise EconomyError("不允许访问本机或内网地址。")
    return value


class PublicNetworkBackend(httpcore.AnyIOBackend):
    async def connect_tcp(
        self, host, port, timeout=None, local_address=None, socket_options=None
    ):
        async def connect():
            records = await asyncio.get_running_loop().getaddrinfo(
                host, port, type=socket.SOCK_STREAM
            )
            addresses = tuple(dict.fromkeys(record[4][0] for record in records))
            if not addresses or not all(is_public_address(address) for address in addresses):
                raise EconomyError("不允许访问本机或内网地址。")
            last_error = None
            for address in addresses:
                try:
                    # Connect to the validated numeric address, never the hostname:
                    # a second DNS lookup must not rebind it to an internal host.
                    return await super(PublicNetworkBackend, self).connect_tcp(
                        address, port, timeout, local_address, socket_options
                    )
                except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                    last_error = exc
            raise last_error or httpcore.ConnectError("No public address available")

        try:
            return await asyncio.wait_for(connect(), timeout=timeout or 10)
        except asyncio.TimeoutError as exc:
            raise httpcore.ConnectTimeout("Public host resolution/connection timed out") from exc
        except OSError as exc:
            raise httpcore.ConnectError("Public host resolution failed") from exc


@dataclass(frozen=True)
class PublicResource:
    url: str
    status: int
    headers: dict[str, str]
    body: bytes


class PublicHTTPClient:
    """Fetch only GET resources, with per-resource and per-screenshot budgets."""

    def __init__(self, *, max_bytes=8 * 1024 * 1024, total_bytes=32 * 1024 * 1024):
        self.max_bytes = max_bytes
        self.remaining_bytes = total_bytes
        self.remaining_requests = 128
        self.pool = httpcore.AsyncConnectionPool(
            network_backend=PublicNetworkBackend(), max_connections=4, retries=0
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.pool.aclose()

    async def fetch(self, url: str, headers: dict[str, str] | None = None) -> PublicResource:
        try:
            return await asyncio.wait_for(self._fetch(url, headers or {}), timeout=20)
        except (httpcore.NetworkError, httpcore.TimeoutException, httpcore.ProtocolError,
                asyncio.TimeoutError) as exc:
            raise EconomyError("网页资源获取失败或超时，请稍后再试。") from exc

    async def _fetch(self, url: str, headers: dict[str, str]) -> PublicResource:
        outgoing = {
            name.lower(): value for name, value in headers.items()
            if name.lower() in {"user-agent", "accept", "accept-language"}
        }
        # Read compressed bytes as-is only when identity was respected, preventing
        # a compressed payload from expanding past the memory budget in Chromium.
        outgoing["accept-encoding"] = "identity"
        for _ in range(6):
            target = httpx.URL(validate_public_url(url))
            if self.remaining_requests <= 0:
                raise EconomyError("网页资源请求过多，已停止加载。")
            self.remaining_requests -= 1
            async with self.pool.stream(
                "GET", str(target), headers=outgoing,
                extensions={"timeout": {"connect": 8, "read": 10, "write": 8, "pool": 10}},
            ) as response:
                response_headers = httpx.Headers(response.headers)
                if response.status in {301, 302, 303, 307, 308} and "location" in response_headers:
                    url = urljoin(str(target), response_headers["location"])
                    continue
                if response_headers.get("content-encoding", "identity").lower() != "identity":
                    raise EconomyError("网页使用了不支持的压缩响应。")
                limit = min(self.max_bytes, self.remaining_bytes)
                length = response_headers.get("content-length", "")
                if length.isdigit() and int(length) > limit:
                    raise EconomyError("网页资源过大，已停止加载。")
                body = bytearray()
                async for chunk in response.aiter_stream():
                    if len(body) + len(chunk) > self.max_bytes or len(chunk) > self.remaining_bytes:
                        raise EconomyError("网页资源过大，已停止加载。")
                    self.remaining_bytes -= len(chunk)
                    body.extend(chunk)
                # Chromium receives already bounded bytes, not an HTTP connection.
                safe_headers = {
                    name: value for name, value in response_headers.items()
                    if name not in {"content-length", "transfer-encoding", "connection",
                                    "content-encoding", "set-cookie", "alt-svc"}
                }
                return PublicResource(str(target), response.status, safe_headers, bytes(body))
        raise EconomyError("网页跳转次数过多，请使用最终网页链接。")
