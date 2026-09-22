"""Docker healthcheck client: python -m src.services.healthcheck."""

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener


def main() -> int:
    try:
        port = int(os.environ.get("PORT", "8080"))
        if not 1 <= port <= 65535:
            raise ValueError("invalid port")
        opener = build_opener(ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{port}/healthz", timeout=7) as response:
            report = json.load(response)
        print(json.dumps(report))
        return 0 if report.get("status") == "ok" else 1
    except HTTPError as exc:
        print(f"Health endpoint returned HTTP {exc.code}")
    except (URLError, TimeoutError, OSError, ValueError):
        print("Health endpoint is unavailable")
    return 1


if __name__ == "__main__":
    sys.exit(main())
