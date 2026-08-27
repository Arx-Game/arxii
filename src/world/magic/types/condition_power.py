"""Standalone condition combat-power evaluator types (#3390).

Shared shapes for ``world.magic.services.condition_power_eval`` — the panel-driving
evaluator that prices a bare ``ConditionTemplate`` at a chosen severity/duration into DE
(damage-equivalent), independent of any technique that happens to apply it. Mirrors
``world.magic.types.technique_power.TechniquePowerReport``'s shape; reuses
``PayloadValuation``/``ValuationProvenance`` from that module directly rather than
minting parallel types.
"""

from __future__ import annotations

from dataclasses import dataclass

from world.magic.types.technique_power import PayloadValuation


@dataclass(frozen=True, slots=True)
class ConditionPowerReport:
    """Full combat-power report for one condition template at one severity/duration (#3390)."""

    template_id: int
    name: str
    at_severity: int
    duration_rounds: int
    total_de: float
    #: Priced payload lines (DoT / generic-modifier / mitigation / capability-effect /
    #: gap-flag UNPRICEABLE rows).
    valuations: tuple[PayloadValuation, ...]
    #: e.g. "team_lane_excluded", "stage_dot_excluded".
    flags: tuple[str, ...]
