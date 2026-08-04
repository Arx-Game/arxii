"""List BOSS-tier opponents with legend aftermath but no wall_breaker_combo (#2051).

One-time legacy audit — the #1997 Game Ops dashboard pattern. Run after deploy
to identify existing BOSS opponents that predate the save-time guard. Safe to
run repeatedly (read-only).

Run as: ``arx manage audit_boss_wall_breakers``
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from world.combat.constants import OpponentTier
from world.combat.models import CombatOpponent


class Command(BaseCommand):
    help = "List BOSS opponents missing wall_breaker_combo (#2051)."

    def handle(self, *_args: Any, **_options: Any) -> None:
        qs = CombatOpponent.objects.filter(
            tier=OpponentTier.BOSS,
            aftermath_pool__isnull=False,
            wall_breaker_combo__isnull=True,
        ).select_related("encounter")
        violations = [
            f"  Opponent {opp.pk} ('{opp.name}') — encounter {opp.encounter_id}"
            for opp in qs
            if opp._aftermath_pays_legend()  # noqa: SLF001
        ]
        if not violations:
            self.stdout.write("No boss wall-breaker violations found.")
        else:
            self.stdout.write(f"{len(violations)} violation(s):")
            for v in violations:
                self.stdout.write(v)
