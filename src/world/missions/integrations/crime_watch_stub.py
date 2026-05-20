"""Crime-watch propagation stub (Phase 5b.1 — DESIGN §13.3 sealed).

The crime-watch system does not exist yet. Authoring a mission that emits
a PROPAGATION/CRIME_WATCH line MUST fail loudly during
``apply_deed_rewards`` so the author hears about it immediately, rather
than silently dropping the emission and surprising the player downstream.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.missions.models import MissionDeedRewardLine


_DESIGN_MESSAGE = (
    "DESIGN §13.3 — crime-watch propagation deferred to Phase 6+ "
    "(see docs/plans/2026-05-18-missions-design.md)."
)


def flag_crime(line: MissionDeedRewardLine) -> None:
    """Raise NotImplementedError — crime-watch system is Phase 6+.

    ``line`` is unused today because the stub raises before doing anything,
    but the parameter is the seam contract Phase 6+ will need (the real
    implementation will dispatch on ``line.recipient`` / ``line.ref``).
    """
    del line  # placate ARG001 until the real impl uses it
    raise NotImplementedError(_DESIGN_MESSAGE)
