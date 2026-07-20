"""Per-vow situational perks (#2536, Layer 4 of the vow-power model).

Machinery lives here in ``world/covenants/perks/`` (slice 1: ``constants.py``
only); the authoring models themselves stay in ``world.covenants.models``
alongside the rest of the covenants migration graph — a new app is an
antipattern per the ratified spec decision (migration-graph overhead).
"""

from __future__ import annotations
