"""Application configuration."""
from django.apps import AppConfig


class BaseConfig(AppConfig):
    """Application configuration."""

    name = "resolwe.observers"

    def ready(self):
        pass  # from . import signals
