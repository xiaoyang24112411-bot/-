"""NoneBot application entrypoint."""

from pathlib import Path

import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

from src.compat.pillow import apply_pillow_compatibility
from src.services.economy import get_economy_database


def main() -> None:
    apply_pillow_compatibility()
    nonebot.init()
    driver = nonebot.get_driver()
    driver.register_adapter(OneBotV11Adapter)
    if nonebot.load_plugin("nonebot_plugin_petpet") is None:
        raise RuntimeError("Failed to load nonebot_plugin_petpet")
    local_plugins = nonebot.load_plugins("src/plugins")
    expected = {
        path.stem for path in Path("src/plugins").glob("*.py")
        if not path.name.startswith("_")
    }
    missing = expected - {plugin.name for plugin in local_plugins}
    if missing:
        raise RuntimeError(f"Failed to load plugins: {', '.join(sorted(missing))}")
    driver.on_startup(get_economy_database().initialize)
    nonebot.run()


if __name__ == "__main__":
    main()
