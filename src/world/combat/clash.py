"""Clash service layer — strain conversion, clash-commit, per-round resolution, and related logic.

This module is the single entry point for all Clash mechanic operations.  It is
intentionally kept free of Django model writes and HTTP/Evennia I/O so that
each function is unit-testable in isolation.  Higher-level orchestration
(views, commands, flow steps) calls into this module rather than implementing
Clash logic themselves.

Current scope (Tasks 2.1–2.2):
  - ``strain_to_modifier``: converts anima committed past the strain floor into
    a diminishing-returns check modifier, driven entirely by ``StrainConfig``
    tuning knobs.
  - ``outcome_to_delta``: maps a ``CheckOutcome`` tier to a per-round progress
    delta, driven by the six ``ClashConfig.delta_*`` tuning knobs.

Future tasks will add clash-commit, round-resolution, and outcome helpers here.
"""

from world.combat.models import ClashConfig, StrainConfig
from world.traits.models import CheckOutcome


def strain_to_modifier(*, anima_committed: int, config: StrainConfig) -> int:
    """Convert a strain commitment (anima poured in past the floor) to a check modifier.

    Diminishing-returns curve: the first points convert efficiently, deep strain
    converts poorly.  Knobs come from ``StrainConfig``:

    - ``conversion_base``: the per-anima conversion at the start of the curve
    - ``diminishing_step``: every ``diminishing_step`` anima reduces the per-anima
      conversion by 1
    - ``diminishing_floor``: the conversion never drops below this per-anima value

    ``anima_committed`` is treated as ``0`` when negative (defensive guard).
    Returns exactly ``0`` when ``anima_committed`` is ``0``.
    """
    remaining = max(anima_committed, 0)
    mod = 0
    rate = config.conversion_base
    while remaining > 0:
        take = min(remaining, config.diminishing_step)
        mod += take * rate
        remaining -= take
        rate = max(rate - 1, config.diminishing_floor)
    return mod


def outcome_to_delta(*, check_outcome: CheckOutcome, config: ClashConfig) -> int:
    """Map a CheckOutcome tier to a clash progress delta.

    Banding (by CheckOutcome.success_level):
      >= 3  → critical success → config.delta_critical_success
      == 2  → great success    → config.delta_great_success
      == 1  → success          → config.delta_success
      == 0  → partial          → config.delta_partial
      == -1 → failure          → config.delta_failure
      <= -2 → botch            → config.delta_botch

    Values outside the authored range are clamped to the nearest band.
    Pure function — no DB writes, no I/O.
    """
    level = check_outcome.success_level
    if level >= 3:  # noqa: PLR2004 — tier breakpoints are design constants, not magic values
        return config.delta_critical_success
    if level == 2:  # noqa: PLR2004 — tier breakpoints are design constants, not magic values
        return config.delta_great_success
    if level == 1:
        return config.delta_success
    if level == 0:
        return config.delta_partial
    if level == -1:
        return config.delta_failure
    return config.delta_botch
