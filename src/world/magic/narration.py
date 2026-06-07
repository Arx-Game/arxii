"""Shared narration helpers for magic outcomes.

Public functions here are consumed by both the combat narration pipeline and the
standalone scene-cast narration path.  Keep this module free of Django model
imports so it can be called from any service layer without triggering ORM setup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.magic.types.power_ledger import PowerLedger


def power_outcome_clause(power_ledger: PowerLedger | None) -> str:
    """Return a short, dramatic prose clause describing the ledger's notable event.

    Inspects PENETRATION and ENVIRONMENT stages in priority order:

    1. Bounce (PENETRATION SET to 0) — the ward entirely turned the working aside.
    2. Partial bleed (PENETRATION MULTIPLY with a negative percent) — the ward
       absorbed much of the force but the working still landed.
    3. Clean penetration (PENETRATION SET to a positive value, label
       "ward (penetrated)") — the working tore cleanly through the ward.
    4. Environment amplification (ENVIRONMENT ADD with a positive amount) —
       a resonant node swelled the working's power.

    Returns ``""`` when none of these cases apply (plain unwarded, non-magic, or
    combo path). Only one clause is returned — priorities run top to bottom.
    """
    if power_ledger is None:
        return ""

    from world.magic.constants import LedgerOp, PowerStage  # noqa: PLC0415

    for entry in power_ledger.entries:
        if entry.stage != PowerStage.PENETRATION:
            continue
        # Bounce: SET to 0 (label "ward (bounced)")
        if entry.op == LedgerOp.SET and entry.amount == 0:
            return "— the ward turns it aside"
        # Partial: MULTIPLY with negative percent (ward reduced power)
        if entry.op == LedgerOp.MULTIPLY and entry.amount < 0:
            return "— the ward bleeds off much of its force"
        # Clean / over penetration: SET to positive value (label "ward (penetrated)")
        # or MULTIPLY with a positive pct (overpenetration amplified by the bounce factor).
        # Both are "tore through" — collapse into one condition.
        if entry.amount > 0:
            return "— it tears through the ward"

    # Environment amplification: ENVIRONMENT ADD with positive amount
    for entry in power_ledger.entries:
        if entry.stage == PowerStage.ENVIRONMENT and entry.op == LedgerOp.ADD and entry.amount > 0:
            return "— the place's resonance swells the working"

    return ""
