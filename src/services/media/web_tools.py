"""Public-URL validation and Playwright screenshots."""

import asyncio

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

from src.services.economy.errors import EconomyError
from src.services.media.public_http import PublicHTTPClient
from src.services.media.public_http import validate_public_url as validate_public_url

_screenshot_lock = asyncio.Lock()


async def _screenshot_public_page(target: str) -> bytes:
    async with PublicHTTPClient() as client:
        document = await client.fetch(target)
        async with async_playwright() as playwright:
            try:
                browser = await playwright.chromium.launch(channel="msedge", headless=True)
            except PlaywrightError:
                browser = await playwright.chromium.launch(headless=True)
            try:
                # The browser itself is offline. Even an unhandled redirect or a
                # browser feature bypassing routing cannot reach a local service.
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 1600},
                    offline=True, service_workers="block", accept_downloads=False,
                )

                async def route_request(route):
                    request = route.request
                    if request.method != "GET":
                        await route.abort()
                        return
                    try:
                        resource = (
                            document if request.url == document.url
                            else await client.fetch(request.url, request.headers)
                        )
                    except EconomyError:
                        await route.abort()
                        return
                    await route.fulfill(
                        status=resource.status, headers=resource.headers, body=resource.body
                    )

                async def close_websocket(socket):
                    await socket.close()

                await context.route("**/*", route_request)
                await context.route_web_socket("**/*", close_websocket)
                page = await context.new_page()
                await page.goto(document.url, wait_until="domcontentloaded", timeout=25_000)
                return await page.screenshot(type="png", full_page=False)
            finally:
                await browser.close()


async def screenshot_page(url: str) -> bytes:
    target = validate_public_url(url)
    if _screenshot_lock.locked():
        raise EconomyError("当前有网页正在截图，请稍后再试。")
    try:
        async with _screenshot_lock:
            return await asyncio.wait_for(_screenshot_public_page(target), timeout=45)
    except (PlaywrightError, asyncio.TimeoutError) as exc:
        raise EconomyError("网页打开或截图失败，请检查地址后重试。") from exc
