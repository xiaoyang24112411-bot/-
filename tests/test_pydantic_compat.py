from dataclasses import dataclass
from importlib import import_module

from pydantic import TypeAdapter

from src.compat.pillow import apply_pillow_compatibility
from src.compat.pydantic import apply_build_image_schema_compatibility


def test_build_image_can_be_used_inside_a_pydantic_dataclass_schema() -> None:
    apply_pillow_compatibility()
    build_image = import_module("nonebot_plugin_imageutils").BuildImage

    @dataclass
    class ImageHolder:
        image: build_image

    apply_build_image_schema_compatibility()
    adapter = TypeAdapter(ImageHolder)
    assert adapter.core_schema["type"] == "dataclass"

