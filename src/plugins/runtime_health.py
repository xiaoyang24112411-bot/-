"""An internal HTTP health endpoint for Docker; sends no chat messages."""

import json

import nonebot
from nonebot.drivers import HTTPServerSetup, Request, Response, ReverseDriver
from yarl import URL

from src.services.economy import get_economy_database
from src.services.runtime_health import runtime_health


async def handle_health(request: Request) -> Response:
    report = await runtime_health(get_economy_database(), dict(nonebot.get_bots()))
    return Response(
        200 if report["status"] == "ok" else 503,
        headers={"Content-Type": "application/json", "Cache-Control": "no-store"},
        content=json.dumps(report),
    )


driver = nonebot.get_driver()
if not isinstance(driver, ReverseDriver):
    raise RuntimeError("Runtime health requires a reverse HTTP driver (e.g. fastapi)")
driver.setup_http_server(HTTPServerSetup(URL("/healthz"), "GET", "qqbot-health", handle_health))
