"""Small allow-listed Edge online text-to-speech wrapper."""

import asyncio

import edge_tts

from .errors import AIFeatureError

VOICES = {
    "晓晓": "zh-CN-XiaoxiaoNeural",
    "云希": "zh-CN-YunxiNeural",
    "晓伊": "zh-CN-XiaoyiNeural",
    "云扬": "zh-CN-YunyangNeural",
}


async def synthesize_speech(
    text: str,
    role: str = "晓晓",
    *,
    max_characters: int = 300,
    timeout: float = 45,
) -> bytes:
    content = text.strip()
    if not content:
        raise AIFeatureError("请输入要合成的文字。")
    if len(content) > max_characters:
        raise AIFeatureError(f"语音文字不能超过 {max_characters} 个字符。")
    voice = VOICES.get(role)
    if voice is None:
        raise AIFeatureError("可用语音角色：" + "、".join(VOICES))

    async def collect_audio() -> bytes:
        chunks: list[bytes] = []
        communicate = edge_tts.Communicate(content, voice)
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio" and chunk.get("data"):
                chunks.append(bytes(chunk["data"]))
        return b"".join(chunks)

    try:
        audio = await asyncio.wait_for(collect_audio(), timeout=timeout)
    except (asyncio.TimeoutError, edge_tts.exceptions.EdgeTTSException) as exc:
        raise AIFeatureError("在线语音合成暂时不可用，请稍后再试。") from exc
    if not audio:
        raise AIFeatureError("在线语音服务没有返回音频。")
    if len(audio) > 8 * 1024 * 1024:
        raise AIFeatureError("合成音频超过 8 MB，请缩短文字。")
    return audio
