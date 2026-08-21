"""Download and verify the complete resource pack for every petpet command."""

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

RESOURCE_URL = (
    "https://raw.githubusercontent.com/noneplugin/"
    "nonebot-plugin-petpet/v0.3.x/resources"
)
OUTPUT = Path(__file__).resolve().parents[1] / "assets" / "petpet"
EXTRA_FILES = {
    "fonts/consola.ttf": "c6e6ce8119fdd47ec6a5449a08e2d2ad7f41ea03143aae193068ed9fa58eaebc",
}
TEMPLATE_NAMES = (
    "petpet",
    "kiss",
    "rub",
    "capoo_rub",
    "play",
    "pat",
    "throw_gif",
    "always_always",
    "turn",
    "windmill_turn",
    "roll",
    "worship",
    "eat",
    "klee_eat",
    "bite",
    "hutao_bite",
    "twist",
    "wallpaper",
    "shock",
    "listen_music",
    "funny_mirror",
    "love_you",
    "punch",
    "pound",
    "thump",
    "knock",
    "garbage",
    "jiujiu",
    "suck",
    "hammer",
    "tightly",
    "repeat",
    "walnut_zoom",
    "confuse",
    "hit_screen",
    "fencing",
    "hug_leg",
    "tankuku_holdsign",
    "wave",
    "rise_dead",
    "kirby_hammer",
    "wooden_fish",
    "kick_ball",
    "bocchi_draft",
    "scratch_head",
    "applaud",
    "chase_train",
    "printing",
    "beat_head",
)
def download(path: str) -> bytes:
    request = urllib.request.Request(
        f"{RESOURCE_URL}/{path}",
        headers={"User-Agent": "qq-nonebot-petpet-prefetch/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def main() -> int:
    resource_list_bytes = download("resource_list.json")
    resource_list = json.loads(resource_list_bytes.decode("utf-8"))
    selected = resource_list
    if not selected:
        print("No required petpet resources found", file=sys.stderr)
        return 1

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "resource_list.json").write_bytes(resource_list_bytes)

    for item in selected:
        relative = str(item["path"])
        expected = str(item["hash"])
        destination = OUTPUT / relative
        if destination.exists() and hashlib.md5(destination.read_bytes()).hexdigest() == expected:
            continue
        content = download(relative)
        if hashlib.md5(content).hexdigest() != expected:
            print(f"Hash mismatch for {relative}", file=sys.stderr)
            return 1
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)

    for relative, expected_sha256 in EXTRA_FILES.items():
        destination = OUTPUT / relative
        if (
            destination.exists()
            and hashlib.sha256(destination.read_bytes()).hexdigest() == expected_sha256
        ):
            continue
        content = download(relative)
        if hashlib.sha256(content).hexdigest() != expected_sha256:
            print(f"SHA256 mismatch for {relative}", file=sys.stderr)
            return 1
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)

    print(f"petpet_assets={len(selected) + len(EXTRA_FILES)} output={OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

