"""Pydantic compatibility for dataclasses used by the legacy petpet plugin."""

from typing import Any

from pydantic_core import core_schema

from src.compat.pillow import apply_pillow_compatibility


def apply_build_image_schema_compatibility() -> None:
    """Teach Pydantic 2.13 how to validate imageutils' arbitrary image type."""
    apply_pillow_compatibility()
    from nonebot_plugin_imageutils import BuildImage

    if "__get_pydantic_core_schema__" in BuildImage.__dict__:
        return

    def get_schema(
        cls: type[Any],
        source_type: Any,
        handler: Any,
    ) -> core_schema.CoreSchema:
        del source_type, handler
        return core_schema.is_instance_schema(cls)

    BuildImage.__get_pydantic_core_schema__ = classmethod(get_schema)  # type: ignore[attr-defined]
