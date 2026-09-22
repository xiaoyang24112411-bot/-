from datetime import datetime, timedelta, timezone

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
    monday = datetime(2026, 9, 21, hour, 0, tzinfo=timezone.utc)
    assert deepseek_billing_period(monday) is expected


def test_weekend_is_always_off_peak():
    saturday = datetime(2026, 9, 26, 8, 0, tzinfo=timezone.utc)
    assert deepseek_billing_period(saturday) is BillingPeriod.OFF_PEAK
    assert not should_suspend_autochat(True, saturday)


def test_peak_suspension_can_be_explicitly_disabled():
    peak = datetime(2026, 9, 21, 2, 0, tzinfo=timezone.utc)
    assert should_suspend_autochat(True, peak)
    assert not should_suspend_autochat(False, peak)


@pytest.mark.parametrize("month,day", [
    (1, 1), (1, 2), (1, 3),
    (2, 15), (2, 20), (2, 23),
    (4, 4), (4, 6),
    (5, 1), (5, 4), (5, 5),
    (6, 19), (6, 21),
    (9, 25), (9, 27),
    (10, 1), (10, 5), (10, 7),
])
def test_2026_announced_holiday_breaks_are_off_peak_all_day(month, day):
    # Both normally charged windows, plus both ends of the Beijing day.
    china = timezone(timedelta(hours=8))
    for hour, minute in ((0, 0), (9, 0), (11, 59), (14, 0), (17, 59), (23, 59)):
        moment = datetime(2026, month, day, hour, minute, tzinfo=china)
        assert deepseek_billing_period(moment) is BillingPeriod.OFF_PEAK
        previous_date_zone = moment.astimezone(timezone(timedelta(hours=-10)))
        assert deepseek_billing_period(previous_date_zone) is BillingPeriod.OFF_PEAK
        assert not should_suspend_autochat(True, moment)


@pytest.mark.parametrize("month,day", [(1, 4), (2, 14), (2, 28), (5, 9), (9, 20), (10, 10)])
def test_makeup_work_weekends_still_use_weekend_pricing(month, day):
    moment = datetime(2026, month, day, 2, 0, tzinfo=timezone.utc)
    assert deepseek_billing_period(moment) is BillingPeriod.OFF_PEAK


@pytest.mark.parametrize("month,day", [(2, 24), (4, 7), (5, 6), (6, 22), (9, 28), (10, 8)])
def test_normal_weekdays_after_holidays_resume_peak_pricing(month, day):
    moment = datetime(2026, month, day, 2, 0, tzinfo=timezone.utc)
    assert deepseek_billing_period(moment) is BillingPeriod.PEAK


@pytest.mark.parametrize("hour,minute,second,expected", [
    (8, 59, 59, BillingPeriod.OFF_PEAK),
    (9, 0, 0, BillingPeriod.PEAK),
    (11, 59, 59, BillingPeriod.PEAK),
    (12, 0, 0, BillingPeriod.OFF_PEAK),
    (13, 59, 59, BillingPeriod.OFF_PEAK),
    (14, 0, 0, BillingPeriod.PEAK),
    (17, 59, 59, BillingPeriod.PEAK),
    (18, 0, 0, BillingPeriod.OFF_PEAK),
])
def test_beijing_boundaries_are_independent_of_input_timezone(hour, minute, second, expected):
    china = timezone(timedelta(hours=8))
    moment = datetime(2026, 9, 22, hour, minute, second, tzinfo=china)
    assert deepseek_billing_period(moment) is expected
    assert deepseek_billing_period(moment.astimezone(timezone.utc)) is expected
    # UTC-10 falls on the previous date during the morning Beijing window.
    assert deepseek_billing_period(moment.astimezone(timezone(timedelta(hours=-10)))) is expected


def test_unknown_years_conservatively_keep_weekday_peak_hours():
    friday = datetime(2027, 1, 1, 2, tzinfo=timezone.utc)
    saturday = datetime(2027, 1, 2, 2, tzinfo=timezone.utc)
    assert deepseek_billing_period(friday) is BillingPeriod.PEAK
    assert deepseek_billing_period(saturday) is BillingPeriod.OFF_PEAK


def test_naive_datetimes_remain_utc():
    assert deepseek_billing_period(datetime(2026, 9, 22, 2)) is BillingPeriod.PEAK
    assert deepseek_billing_period(datetime(2026, 9, 25, 2)) is BillingPeriod.OFF_PEAK
