from src.services.information.commands import (
    parse_fuel_region,
    parse_hot_search_platform,
)


def test_fuel_price_accepts_canonical_and_compact_wording() -> None:
    assert parse_fuel_region("今日油价 怀化") == "怀化"
    assert parse_fuel_region("/每日油价 广东") == "广东"
    assert parse_fuel_region("今日怀化油价") == "怀化"
    assert parse_fuel_region("/每日深圳油价") == "深圳"


def test_fuel_price_rejects_unrelated_text() -> None:
    assert parse_fuel_region("怀化油价") is None
    assert parse_fuel_region("今天几号") is None


def test_hot_search_parses_platform_and_default() -> None:
    assert parse_hot_search_platform("热搜 微博") == "微博"
    assert parse_hot_search_platform("/热搜查询 抖音") == "抖音"
    assert parse_hot_search_platform("热搜") == ""
    assert parse_hot_search_platform("热搜平台") is None
