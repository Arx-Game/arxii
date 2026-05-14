"""Management command for the LocationValueModifier cleanup sweep.

Thin wrapper around ``world.locations.services.cleanup_decayed_modifiers``.
Run as: ``arx manage cleanup_decayed_modifiers``.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from world.locations.services import cleanup_decayed_modifiers


class Command(BaseCommand):
    help = "Delete LocationValueModifier rows whose current_value() has decayed to zero."

    def handle(self, *_args: Any, **_options: Any) -> None:
        deleted = cleanup_decayed_modifiers()
        self.stdout.write(f"Deleted {deleted} decayed LocationValueModifier row(s).")
