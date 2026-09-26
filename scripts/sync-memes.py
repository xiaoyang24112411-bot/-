"""Synchronize and verify the official meme-generator-rs template resources.

Usage: python scripts/sync-memes.py [--verify-only]
The generator resource directory is selected by MEME_HOME, or data/meme-generator.
"""

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from io import BytesIO
from pathlib import Path, PurePosixPath

RESOURCE_MANIFEST_URL = (
    "https://raw.githubusercontent.com/MemeCrafters/"
    "meme-generator-rs/v0.2.3/resources/resources.json"
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_resource_path(root: Path, category: str, name: str) -> Path:
    relative = PurePosixPath(name)
    if relative.is_absolute() or "\\" in name or not relative.parts or any(
        part in ("", ".", "..") or ":" in part for part in relative.parts
    ):
        raise ValueError(f"Unsafe resource name: {name!r}")
    return root / "resources" / category / Path(*relative.parts)


def verify_resources(root: Path, manifest: dict) -> list[str]:
    failures: list[str] = []
    for category in ("fonts", "images"):
        for item in manifest[category]:
            name = item["file"]
            expected = item["hash"].lower()
            if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
                raise ValueError(f"Invalid SHA256 for {name!r}")
            path = expected_resource_path(root, category, name)
            if not path.is_file() or sha256_file(path) != expected:
                failures.append(f"{category}/{name}")
    return failures


def smoke_test() -> None:
    from meme_generator import Image, get_meme
    from PIL import Image as PillowImage

    avatar = BytesIO()
    PillowImage.new("RGB", (120, 120), "#4b92c8").save(avatar, format="PNG")
    result = get_meme("applaud").generate([Image("test", avatar.getvalue())], [], {})
    if not isinstance(result, bytes) or not result.startswith((b"GIF8", b"\x89PNG", b"RIFF")):
        raise RuntimeError(f"Template rendering failed: {result!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    root = Path(os.environ.get("MEME_HOME", PROJECT_ROOT / "data/meme-generator")).resolve()
    os.environ["MEME_HOME"] = str(root)
    if not args.verify_only:
        from meme_generator.resources import check_resources

        print(f"Synchronizing meme resources in {root} ...", flush=True)
        check_resources()

    request = urllib.request.Request(
        RESOURCE_MANIFEST_URL,
        headers={"User-Agent": "qq-nonebot-meme-resource-check/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        manifest = json.load(response)
    failures = verify_resources(root, manifest)
    if failures:
        print(f"Missing or corrupt resources: {len(failures)}", file=sys.stderr)
        for name in failures[:10]:
            print(f"  {name}", file=sys.stderr)
        return 1

    smoke_test()
    count = sum(len(manifest[category]) for category in ("fonts", "images"))
    print(f"Verified {count} resources and rendered a test GIF successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
