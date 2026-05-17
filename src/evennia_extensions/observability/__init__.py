"""
Observability exporter for Arx II.

Provides fail-safe metrics export and monitoring capabilities,
disabled by default.
"""

from evennia_extensions.observability.settings import observability_config

__all__ = ["observability_config"]
