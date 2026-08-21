"""NoneBot application entrypoint."""

import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

from src.compat.pillow import apply_pillow_compatibility


def main() -> None:
    apply_pillow_compatibility()
    nonebot.init()
    driver = nonebot.get_driver()
    driver.register_adapter(OneBotV11Adapter)
    if nonebot.load_plugin("nonebot_plugin_petpet") is None:
        raise RuntimeError("Failed to load nonebot_plugin_petpet")
    local_plugins = nonebot.load_plugins("src/plugins")
    if "petpet_compat" not in {plugin.name for plugin in local_plugins}:
        raise RuntimeError("Failed to load petpet compatibility plugin")
    nonebot.run()


if __name__ == "__main__":
    main()

