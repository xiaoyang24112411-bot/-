"""DeepSeek's published peak/off-peak billing schedule."""

from datetime import UTC, datetime
from enum import StrEnum


class BillingPeriod(StrEnum):
    PEAK = "peak"
    OFF_PEAK = "off_peak"


def deepseek_billing_period(now: datetime | None = None) -> BillingPeriod:
    """Return the official period: weekdays 01-04 and 06-10 UTC are peak."""
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    current = current.astimezone(UTC)
    if current.weekday() >= 5:
        return BillingPeriod.OFF_PEAK
    hour = current.hour
    if 1 <= hour < 4 or 6 <= hour < 10:
        return BillingPeriod.PEAK
    return BillingPeriod.OFF_PEAK


def is_deepseek_peak(now: datetime | None = None) -> bool:
    return deepseek_billing_period(now) is BillingPeriod.PEAK


def should_suspend_autochat(suspend_during_peak: bool, now: datetime | None = None) -> bool:
    return suspend_during_peak and is_deepseek_peak(now)
