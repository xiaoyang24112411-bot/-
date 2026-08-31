"""Safe user-facing errors for batch-six services."""


class AIFeatureError(Exception):
    """A validation, provider, or empty-result error safe to show in QQ."""
