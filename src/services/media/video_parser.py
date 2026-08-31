"""Authorized single-video download using embedded yt-dlp."""

import asyncio
import uuid
from dataclasses import dataclass
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from src.services.economy.errors import EconomyError
from src.services.media.web_tools import validate_public_url


@dataclass(frozen=True)
class ParsedVideo:
    title: str
    uploader: str
    path: Path


@dataclass(frozen=True)
class ParsedGallery:
    title: str
    image_urls: tuple[str, ...]


def _download(url: str, work_root: Path, max_bytes: int) -> ParsedVideo:
    task_dir = work_root / uuid.uuid4().hex
    task_dir.mkdir(parents=True, exist_ok=False)
    options = {
        "outtmpl": str(task_dir / "video.%(ext)s"),
        "format": "best[ext=mp4]/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "max_filesize": max_bytes,
        "socket_timeout": 20,
    }
    try:
        with YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=True)
            if not info:
                raise EconomyError("没有解析到可下载的视频。")
        files = tuple(path for path in task_dir.iterdir() if path.is_file())
        if not files:
            raise EconomyError("视频下载失败，可能需要登录 Cookie。")
        path = files[0]
        if path.stat().st_size > max_bytes:
            raise EconomyError("视频超过机器人允许的大小。")
        return ParsedVideo(
            str(info.get("title") or "未命名视频"),
            str(info.get("uploader") or ""),
            path,
        )
    except DownloadError as exc:
        raise EconomyError("该链接暂时无法解析，可能需要登录或更新解析器。") from exc


async def download_video(url: str, work_root: Path, max_bytes: int) -> ParsedVideo:
    target = validate_public_url(url)
    return await asyncio.to_thread(_download, target, work_root, max_bytes)


def _extract_gallery(url: str) -> ParsedGallery:
    options = {"quiet": True, "no_warnings": True, "skip_download": True}
    try:
        with YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=False)
    except DownloadError as exc:
        raise EconomyError("该图集暂时无法解析，可能需要登录 Cookie。") from exc
    if not info:
        raise EconomyError("没有解析到图集信息。")
    candidates = []
    entries = info.get("entries") or [info]
    for entry in entries:
        if not entry:
            continue
        direct_url = str(entry.get("url") or "")
        extension = str(entry.get("ext") or "").lower()
        if extension in {"jpg", "jpeg", "png", "webp"} and direct_url.startswith("http"):
            candidates.append(direct_url)
        thumbnails = entry.get("thumbnails") or []
        if thumbnails:
            thumbnail_url = str(thumbnails[-1].get("url") or "")
            if thumbnail_url.startswith("http"):
                candidates.append(thumbnail_url)
    unique = tuple(dict.fromkeys(candidates))[:9]
    if not unique:
        raise EconomyError("没有提取到可发送的图片；该平台可能暂不支持图集解析。")
    return ParsedGallery(str(info.get("title") or "未命名图集"), unique)


async def extract_gallery(url: str) -> ParsedGallery:
    target = validate_public_url(url)
    return await asyncio.to_thread(_extract_gallery, target)
