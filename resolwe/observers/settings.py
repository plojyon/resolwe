from django.conf import settings


def get_queryobserver_settings():
    """Query observer connection configuration."""
    defaults = {
        # Throttle evaluation (in seconds). If a new update comes earlier than
        # given rate value, the evaluation will be delayed (and batched).
        # A higher value introduces more latency.
        "throttle_rate": 2,
    }
    defaults.update(getattr(settings, "OBSERVERS", {}))
    return defaults
