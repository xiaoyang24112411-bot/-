"""Safe local category-based image and video libraries."""

import random
import re
from pathlib import Path

from src.services.economy.errors import EconomyError

CATEGORY_PATTERN = re.compile(r"^[\w\u4e00-\u9fff-]{1,40}$")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}


def list_categories(root: Path, media_type: str) -> tuple[str, ...]:
    base = root / media_type
    if not base.exists():
        return ()
    return tuple(sorted(path.name for path in base.iterdir() if path.is_dir()))


def random_media(
    root: Path,
    media_type: str,
    category: str,
    rng: random.Random | None = None,
) -> Path:
    category = category.strip() or "默认"
    if not CATEGORY_PATTERN.fullmatch(category):
        raise EconomyError("分类名称只能包含中文、字母、数字、下划线或短横线。")
    base = (root / media_type).resolve()
    target = (base / category).resolve()
    if target.parent != base:
        raise EconomyError("媒体分类路径无效。")
    extensions = IMAGE_EXTENSIONS if media_type == "images" else VIDEO_EXTENSIONS
    files = (
        tuple(
            path
            for path in target.iterdir()
            if path.is_file() and path.suffix.lower() in extensions
        )
        if target.exists()
        else ()
    )
    if not files:
        kind = "图片" if media_type == "images" else "视频"
        raise EconomyError(f"分类“{category}”中暂时没有{kind}。")
    return (rng or random.SystemRandom()).choice(files)
