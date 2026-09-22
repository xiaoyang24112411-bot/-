import asyncio
import socket
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock

import httpcore
import pytest
from PIL import Image
from playwright.async_api import async_playwright

from src.services.economy.errors import EconomyError
from src.services.media.public_http import (
    PublicHTTPClient,
    PublicNetworkBackend,
    PublicResource,
    validate_public_url,
)
from src.services.media.web_tools import screenshot_page


def resolved(*addresses):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443)) for address in addresses]


@pytest.mark.asyncio
@pytest.mark.parametrize("addresses", [
    ("127.0.0.1",), ("10.0.0.2",), ("169.254.169.254",),
    ("93.184.216.34", "192.168.0.1"), ("224.0.0.1",),
])
async def test_connection_rejects_every_internal_or_mixed_dns_answer(monkeypatch, addresses):
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", AsyncMock(
        return_value=resolved(*addresses)
    ))
    connector = AsyncMock()
    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", connector)
    with pytest.raises(EconomyError, match="内网"):
        await PublicNetworkBackend().connect_tcp("attacker.example", 443)
    connector.assert_not_called()


@pytest.mark.asyncio
async def test_connection_pins_numeric_ip_and_rechecks_rebinding(monkeypatch):
    lookup = AsyncMock(side_effect=[resolved("93.184.216.34"), resolved("127.0.0.1")])
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", lookup)
    connector = AsyncMock(return_value=httpcore.AsyncMockStream([]))
    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", connector)
    backend = PublicNetworkBackend()
    await backend.connect_tcp("rebind.example", 443)
    assert connector.call_args.args[0] == "93.184.216.34"
    with pytest.raises(EconomyError, match="内网"):
        await backend.connect_tcp("rebind.example", 443)
    assert connector.call_count == 1


@pytest.mark.asyncio
async def test_pinned_connection_preserves_host_and_tls_server_name(monkeypatch):
    class CaptureStream(httpcore.AsyncMockStream):
        def __init__(self):
            super().__init__([b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"])
            self.written = b""
            self.tls_host = None

        async def write(self, buffer, timeout=None):
            self.written += buffer

        async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            self.tls_host = server_hostname
            return self

    stream = CaptureStream()
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", AsyncMock(
        return_value=resolved("93.184.216.34")
    ))
    connector = AsyncMock(return_value=stream)
    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", connector)
    async with PublicHTTPClient() as client:
        resource = await client.fetch("https://public.example/page")
    assert resource.body == b"ok"
    assert connector.call_args.args[0] == "93.184.216.34"
    assert b"Host: public.example\r\n" in stream.written
    assert stream.tls_host == "public.example"


@pytest.mark.asyncio
async def test_redirect_to_rebound_domain_is_blocked_before_second_connection(monkeypatch):
    response = (
        b"HTTP/1.1 302 Found\r\nLocation: https://rebind.example/private\r\n"
        b"Connection: close\r\nContent-Length: 0\r\n\r\n"
    )
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", AsyncMock(
        side_effect=[resolved("93.184.216.34"), resolved("127.0.0.1")]
    ))
    connector = AsyncMock(return_value=httpcore.AsyncMockStream([response]))
    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", connector)
    async with PublicHTTPClient() as client:
        with pytest.raises(EconomyError, match="内网"):
            await client.fetch("https://rebind.example/")
    assert connector.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("headers,body", [
    (b"Content-Length: 99999\r\n", b""),
    (b"Connection: close\r\n", b"x" * 100),
    (b"Content-Encoding: gzip\r\nContent-Length: 0\r\n", b""),
])
async def test_resource_size_and_compression_limits(monkeypatch, headers, body):
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", AsyncMock(
        return_value=resolved("93.184.216.34")
    ))
    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", AsyncMock(
        return_value=httpcore.AsyncMockStream([b"HTTP/1.1 200 OK\r\n" + headers + b"\r\n" + body])
    ))
    async with PublicHTTPClient(max_bytes=20) as client:
        with pytest.raises(EconomyError, match="过大|压缩"):
            await client.fetch("https://public.example/")


@pytest.mark.parametrize("url", [
    "http://[::1]/", "http://[::ffff:127.0.0.1]/", "http://localhost./",
    "http://[64:ff9b::7f00:1]/", "http://[2002:7f00:1::]/",
    "http://224.0.0.1/", "http://example.com:99999/",
])
def test_malformed_and_nonpublic_urls(url):
    with pytest.raises(EconomyError):
        validate_public_url(url)


@pytest.mark.asyncio
async def test_offline_browser_renders_fulfilled_page_without_direct_network(monkeypatch):
    async with async_playwright() as playwright:
        if not (
            Path(playwright.chromium.executable_path).is_file()
            or Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe").is_file()
            or Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe").is_file()
        ):
            pytest.skip("No local Chromium/Edge for the browser isolation regression")

    connections = []

    async def local_server(reader, writer):
        connections.append(True)
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(local_server, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    html = (
        '<html><body style="margin:0;background:rgb(255,0,0)">'
        f'<img src="http://127.0.0.1:{port}/private">'
        f'<script>new WebSocket("ws://127.0.0.1:{port}/socket");</script>'
        '</body></html>'
    ).encode()

    async def fetch(self, url, headers=None):
        if url != "https://public.example/":
            raise EconomyError("不允许访问本机或内网地址。")
        return PublicResource(url, 200, {"content-type": "text/html"}, html)

    monkeypatch.setattr(PublicHTTPClient, "fetch", fetch)
    try:
        image = await screenshot_page("https://public.example/")
        with Image.open(BytesIO(image)) as rendered:
            assert rendered.convert("RGB").getpixel((500, 500)) == (255, 0, 0)
        assert connections == []
    finally:
        server.close()
        await server.wait_closed()
