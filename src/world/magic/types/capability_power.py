"""Capability combat-power evaluator types (#3390).

Shared shapes for ``world.magic.services.capability_power_eval`` — the panel-driving
evaluator that prices a ``CapabilityType`` into DE-per-point via its authored
``CheckTypeCapabilityModifier`` bridge rows. Mirrors
``world.magic.types.technique_power.TechniquePowerReport``'s shape; reuses
``PayloadValuation``/``ValuationProvenance`` from that module directly rather than
minting parallel types.
"""

from __future__ import annotations

from dataclasses import dataclass

from world.magic.types.technique_power import PayloadValuation


@dataclass(frozen=True, slots=True)
class CapabilityPowerReport:
    """Full combat-power report for one capability type (#3390)."""

    capability_id: int
    name: str
    total_de: float
    #: One ``check_bridge`` row per authored ``CheckTypeCapabilityModifier``, or a
    #: single UNPRICEABLE row when none are authored (see ``flags``).
    valuations: tuple[PayloadValuation, ...]
    #: ``("no_authored_bridge",)`` when the capability has zero authored
    #: ``CheckTypeCapabilityModifier`` rows (Decision 5, #3390) — pricing 0 WITH this
    #: flag is correct behavior, not a gap.
    flags: tuple[str, ...]
