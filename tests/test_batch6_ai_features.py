from datetime import UTC, datetime

import httpx
import pytest
import respx

from src.services.ai_features import AIFeatureError
from src.services.ai_features.music import API_URL, search_songs
from src.services.ai_features.personas import clear_persona, get_persona, set_persona
from src.services.ai_features.singing import fetch_random_singing
from src.services.ai_features.speech import synthesize_speech
from src.services.ai_features.wordclouds import (
    clear_wordcloud_messages,
    generate_wordcloud,
    get_wordcloud_messages,
    record_wordcloud_message,
    resolve_wordcloud_font,
    set_wordcloud_enabled,
)
from src.services.economy.database import EconomyDatabase


@pytest.mark.asyncio
async def test_persona_and_opt_in_wordcloud_storage(tmp_path):
    database = EconomyDatabase(tmp_path / "batch6.sqlite3")
    assert await get_persona(database, 1, 10) is None
    assert await set_persona(database, 1, 10, "用侦探口吻简洁回答") == "用侦探口吻简洁回答"
    assert await get_persona(database, 1, 10) == "用侦探口吻简洁回答"
    assert await clear_persona(database, 1, 10) is True

    now = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)
    assert not await record_wordcloud_message(database, 1, 10, "尚未开启", now=now)
    await set_wordcloud_enabled(database, 1, True, 99, 30)
    messages = (
        "机器人开发真的很有意思",
        "今天继续开发机器人功能",
        "群聊词云可以展示热门话题",
        "Python 开发效率很高",
    )
    for user_id, message in enumerate(messages, start=10):
        assert await record_wordcloud_message(database, 1, user_id, message, now=now)
    stored = await get_wordcloud_messages(database, 1, 7, now=now)
    assert len(stored) == 4
    font = resolve_wordcloud_font()
    image = generate_wordcloud(stored, font)
    assert image.startswith(b"\x89PNG")
    assert await clear_wordcloud_messages(database, 1) == 4


@pytest.mark.asyncio
async def test_music_and_random_singing_clients():
    song_payload = {
        "resultCount": 1,
        "results": [
            {
                "trackName": "稻香",
                "artistName": "周杰伦",
                "collectionName": "魔杰座",
                "trackTimeMillis": 223000,
                "trackViewUrl": "https://music.apple.com/cn/song/example",
            }
        ],
    }
    singing_payload = {
        "code": 200,
        "data": {
            "user": {"nickname": "测试歌手"},
            "song": {"name": "测试歌曲", "singer": "原唱"},
            "audio": {
                "url": "https://audio-cdn.api.singduck.cn/clip.wav",
                "link": "https://sing.test/work/1",
            },
        },
    }
    with respx.mock(assert_all_called=True) as router:
        router.get(API_URL).mock(return_value=httpx.Response(200, json=song_payload))
        router.get("https://info.test/v2/changya").mock(
            return_value=httpx.Response(200, json=singing_payload)
        )
        router.get("https://audio-cdn.api.singduck.cn/clip.wav").mock(
            return_value=httpx.Response(200, content=b"RIFF-audio")
        )
        async with httpx.AsyncClient() as client:
            songs = await search_songs("稻香", client=client)
            clip = await fetch_random_singing("https://info.test/v2", client=client)
    assert songs[0].artist == "周杰伦"
    assert songs[0].duration_seconds == 223
    assert clip.performer == "测试歌手"
    assert clip.audio == b"RIFF-audio"


@pytest.mark.asyncio
async def test_tts_input_validation():
    with pytest.raises(AIFeatureError, match="请输入"):
        await synthesize_speech("")
    with pytest.raises(AIFeatureError, match="可用语音角色"):
        await synthesize_speech("你好", "不存在")
    with pytest.raises(AIFeatureError, match="不能超过"):
        await synthesize_speech("太长了", max_characters=2)
