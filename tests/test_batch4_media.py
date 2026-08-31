from io import BytesIO

import pytest
from PIL import Image

from src.services.economy.errors import EconomyError
from src.services.media.ascii_art import image_to_ascii
from src.services.media.local_library import list_categories, random_media
from src.services.media.saucenao import search_image_source
from src.services.media.web_tools import validate_public_url


def test_local_media_library_and_ascii_art(tmp_path):
    category = tmp_path / "images" / "风景"
    category.mkdir(parents=True)
    image_path = category / "sample.png"
    image = Image.new("RGB", (8, 4), "white")
    image.save(image_path)

    assert list_categories(tmp_path, "images") == ("风景",)
    assert random_media(tmp_path, "images", "风景") == image_path

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    art = image_to_ascii(buffer.getvalue(), width=8)
    assert art
    assert len(art.splitlines()) >= 1


def test_public_url_validation_blocks_local_networks():
    assert validate_public_url("https://example.com") == "https://example.com"
    with pytest.raises(EconomyError, match="内网"):
        validate_public_url("http://127.0.0.1/admin")
    with pytest.raises(EconomyError, match="完整"):
        validate_public_url("file:///etc/passwd")


@pytest.mark.asyncio
async def test_saucenao_requires_api_key():
    with pytest.raises(EconomyError, match="API Key"):
        await search_image_source("https://example.com/image.png", "")
