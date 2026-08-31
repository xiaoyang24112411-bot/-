"""Random user singing audio from the open-source 60s API."""

from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from .errors import AIFeatureError


@dataclass(frozen=True)
class SingingClip:
    song_name: str
    singer: str
    performer: str
    detail_url: str
    audio: bytes


async def fetch_random_singing(
    base_url: str,
    *,
    fallback_urls: tuple[str, ...] = (),
    timeout: float = 30,
    max_bytes: int = 12 * 1024 * 1024,
    client: httpx.AsyncClient | None = None,
) -> SingingClip:
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=True)
    try:
        payload = None
        last_error: Exception | None = None
        for provider_url in (base_url, *fallback_urls):
            try:
                response = await http_client.get(f"{provider_url.rstrip('/')}/changya")
                response.raise_for_status()
                candidate = response.json()
                if isinstance(candidate, dict) and candidate.get("code") == 200:
                    payload = candidate
                    break
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                last_error = exc
        if payload is None:
            raise AIFeatureError("随机唱歌服务没有返回有效数据。") from last_error
        data = payload.get("data") or {}
        audio_data = data.get("audio") or {}
        audio_url = str(audio_data.get("url") or "")
        parsed_audio_url = urlparse(audio_url)
        if (
            parsed_audio_url.scheme not in {"http", "https"}
            or parsed_audio_url.hostname != "audio-cdn.api.singduck.cn"
        ):
            raise AIFeatureError("随机唱歌音频地址无效。")
        if parsed_audio_url.scheme == "http":
            audio_url = "https://" + audio_url.removeprefix("http://")
        audio_response = await http_client.get(audio_url)
        audio_response.raise_for_status()
        audio = audio_response.content
        if not audio or len(audio) > max_bytes:
            raise AIFeatureError("随机唱歌音频为空或超过 12 MB。")
        song = data.get("song") or {}
        user = data.get("user") or {}
        return SingingClip(
            song_name=str(song.get("name") or "未知歌曲"),
            singer=str(song.get("singer") or "未知原唱"),
            performer=str(user.get("nickname") or "匿名用户"),
            detail_url=str(audio_data.get("link") or ""),
            audio=audio,
        )
    except AIFeatureError:
        raise
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise AIFeatureError("随机唱歌服务暂时不可用，请稍后再试。") from exc
    finally:
        if owns_client:
            await http_client.aclose()
