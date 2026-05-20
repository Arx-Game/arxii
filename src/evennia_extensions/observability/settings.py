"""
Observability configuration settings.

Provides a fail-safe configuration object for the observability exporter.
All features are disabled by default.
"""

from dataclasses import dataclass

from django.conf import settings


@dataclass(frozen=True)
class ObservabilityConfig:
    """Configuration for the observability exporter.

    Attributes:
        enabled: Whether the observability exporter is enabled.
        port: Port number for the metrics endpoint.
    """

    enabled: bool
    port: int


def observability_config() -> ObservabilityConfig:
    """Load observability configuration from Django settings.

    Returns:
        ObservabilityConfig: Configuration object with values from Django settings
            or safe defaults (disabled, port 9109).
    """
    return ObservabilityConfig(
        enabled=bool(getattr(settings, "OBSERVABILITY_ENABLED", False)),  # noqa: GETATTR_LITERAL
        port=int(getattr(settings, "OBSERVABILITY_PORT", 9109)),  # noqa: GETATTR_LITERAL
    )
