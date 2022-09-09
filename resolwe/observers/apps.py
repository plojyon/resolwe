"""Application configuration."""
from django.apps import AppConfig


import logging

logger = logging.getLogger(__name__)


class BaseConfig(AppConfig):
    """Application configuration."""

    name = "resolwe.observers"

    def ready(self):
        """Application initialization."""
        logger.warning("REGISTERING SIGNALS")
        # Register signals handlers.
        from . import signals  # noqa: F401
