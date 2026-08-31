"""Public-URL validation and Playwright screenshots."""

import ipaddress
from urllib.parse import urlparse

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

from src.services.economy.errors import EconomyError


def validate_public_url(url: str) -> str:
    value = url.strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise EconomyError("请输入完整的 http:// 或 https:// 网页地址。")
    if parsed.username or parsed.password:
        raise EconomyError("网页地址不能包含登录凭据。")
    hostname = parsed.hostname.casefold()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        raise EconomyError("不允许访问本机或内网地址。")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return value
    if not address.is_global:
        raise EconomyError("不允许访问本机或内网地址。")
    return value


async def screenshot_page(url: str) -> bytes:
    target = validate_public_url(url)
    try:
        async with async_playwright() as playwright:
            try:
                browser = await playwright.chromium.launch(channel="msedge", headless=True)
            except PlaywrightError:
                browser = await playwright.chromium.launch(headless=True)
            try:
                page = await browser.new_page(viewport={"width": 1280, "height": 1600})
                await page.goto(target, wait_until="domcontentloaded", timeout=25_000)
                return await page.screenshot(type="png", full_page=False)
            finally:
                await browser.close()
    except PlaywrightError as exc:
        raise EconomyError("网页打开或截图失败，请检查地址后重试。") from exc
