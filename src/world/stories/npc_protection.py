"""Story-critical NPC protection (#1874) — thin re-export shim (#2001).

The implementation moved to ``world.stories.services.custody`` (the single
custody-check service seam that every enforcement point funnels through).
This module is kept as an import-stable alias: ``world.combat.services`` and
``world.vitals.peril_resolution`` both import ``is_death_prevented_by_story``
from this path.
"""

from __future__ import annotations

from world.stories.services.custody import is_death_prevented_by_story

__all__ = ["is_death_prevented_by_story"]
