from datetime import UTC, datetime

import pytest

from src.services.deepseek_pricing import (
    BillingPeriod,
    deepseek_billing_period,
    should_suspend_autochat,
)


@pytest.mark.parametrize(
    ("hour", "expected"),
    [
        (0, BillingPeriod.OFF_PEAK),
        (1, BillingPeriod.PEAK),
        (3, BillingPeriod.PEAK),
        (4, BillingPeriod.OFF_PEAK),
        (6, BillingPeriod.PEAK),
        (9, BillingPeriod.PEAK),
        (10, BillingPeriod.OFF_PEAK),
    ],
)
def test_weekday_peak_boundaries(hour, expected):
    monday = datetime(2026, 9, 21, hour, 0, tzinfo=UTC)
    assert deepseek_billing_period(monday) is expected


def test_weekend_is_always_off_peak():
    saturday = datetime(2026, 9, 26, 8, 0, tzinfo=UTC)
    assert deepseek_billing_period(saturday) is BillingPeriod.OFF_PEAK
    assert not should_suspend_autochat(True, saturday)


def test_peak_suspension_can_be_explicitly_disabled():
    peak = datetime(2026, 9, 21, 2, 0, tzinfo=UTC)
    assert should_suspend_autochat(True, peak)
    assert not should_suspend_autochat(False, peak)
