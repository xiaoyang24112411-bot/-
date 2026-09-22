"""DeepSeek's published peak/off-peak billing schedule."""

from datetime import date, datetime, timedelta, timezone
from enum import Enum

CHINA_TIMEZONE = timezone(timedelta(hours=8))

# Reviewed 2026-09-22. DeepSeek exempts Chinese public holidays and all weekends:
# https://api-docs.deepseek.com/quick_start/pricing/
# Full 2026 holiday breaks (including adjusted days off), State Council notice:
# https://www.gov.cn/zhengce/zhengceku/202511/content_7047091.htm
# Add each new year's published schedule here; unknown years deliberately keep
# weekday peak hours instead of guessing a holiday and incurring peak charges.
CHINESE_PUBLIC_HOLIDAYS = frozenset(
    date(2026, month, day)
    for month, first_day, last_day in (
        (1, 1, 3),      # New Year
        (2, 15, 23),    # Spring Festival
        (4, 4, 6),      # Qingming
        (5, 1, 5),      # Labour Day
        (6, 19, 21),    # Dragon Boat Festival
        (9, 25, 27),    # Mid-Autumn Festival
        (10, 1, 7),     # National Day
    )
    for day in range(first_day, last_day + 1)
)


class BillingPeriod(str, Enum):
    PEAK = "peak"
    OFF_PEAK = "off_peak"


def deepseek_billing_period(now: datetime | None = None) -> BillingPeriod:
    """Weekdays 01-04/06-10 UTC are peak, except known Chinese holiday dates.

    Naive input is UTC, matching the previous API contract. Holiday dates use
    Beijing time; weekends stay off-peak even when they are make-up workdays.
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    china_current = current.astimezone(CHINA_TIMEZONE)
    if china_current.weekday() >= 5 or china_current.date() in CHINESE_PUBLIC_HOLIDAYS:
        return BillingPeriod.OFF_PEAK
    hour = current.hour
    if 1 <= hour < 4 or 6 <= hour < 10:
        return BillingPeriod.PEAK
    return BillingPeriod.OFF_PEAK


def is_deepseek_peak(now: datetime | None = None) -> bool:
    return deepseek_billing_period(now) is BillingPeriod.PEAK


def should_suspend_autochat(suspend_during_peak: bool, now: datetime | None = None) -> bool:
    return suspend_during_peak and is_deepseek_peak(now)
