"""Shared narration helpers for magic outcomes.

Public functions here are consumed by both the combat narration pipeline and the
standalone scene-cast narration path.  Keep this module free of Django model
imports so it can be called from any service layer without triggering ORM setup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.magic.types.power_ledger import PowerLedger


def render_cast_outcome_narration(  # noqa: PLR0913 - stable caller signature
    *,
    actor_label: str,
    technique_name: str,
    target_label: str | None,
    outcome_label: str,
    success_level: int,  # noqa: ARG001  (reserved for future verb tuning)
    power_ledger: PowerLedger | None = None,
    fizzle_note: str | None = None,
    signature_snippet: str | None = None,
) -> str:
    """One-line deterministic narration for a standalone scene cast. Pure."""
    clause = power_outcome_clause(power_ledger)
    sig = signature_clause(signature_snippet)
    target_part = f" at {target_label}" if target_label else ""
    head = f"{actor_label} casts {technique_name}{target_part}: {outcome_label}"
    suffix_parts = [c for c in (clause, sig) if c]
    base = f"{head} {' '.join(suffix_parts)}." if suffix_parts else f"{head}."
    return f"{base} {fizzle_note}" if fizzle_note else base


def render_unattributed_cast_narration(target_label: str | None) -> str:
    """What a concealed scene cast looked like to someone who cannot attribute it (#2734).

    The scene-path sibling of ``render_unattributed_action_narration``. Concealment
    hides attribution, not the event — an observer who fails detection still sees
    something take hold, they just cannot say who worked it or what it was.

    Carries no caster, no technique name and no outcome label: the outcome label is
    check vocabulary that only makes sense once you know a check was rolled, which is
    exactly the knowledge this tier lacks.

    Returns ``""`` for a target-less cast; callers must skip emitting on empty.
    """
    if not target_label:
        return ""
    return f"Something takes hold of {target_label}."


def render_vague_cast_narration(effect_line: str = "") -> str:
    """The line a marginally-detecting observer gets for a concealed cast (#2710/#2734).

    This tier knows a *working* happened — the thing the effect-only tier below it
    cannot tell — but still cannot name the caster or the technique. When the cast had
    a perceptible effect, that effect is folded in so this observer is never told
    strictly less than someone who rolled worse; with nothing to see, it degrades to
    the bare sensing line.

    Naming either party here would collapse this tier into the full one.
    """
    if effect_line:
        return f"{effect_line.rstrip('.')} — a working, though you cannot tell by whom."
    return "Something is being worked here — you cannot tell by whom."


def signature_clause(snippet: str | None) -> str:
    """Build a cosmetic em-dash clause from an already-resolved signature snippet.

    Returns ``""`` when ``snippet`` is falsy. The snippet is pre-resolved by the
    caller (``create_cast_outcome_pose``) so this function stays pure / ORM-free.

    Examples::

        signature_clause("spectral webs shimmer")
        # → "— spectral webs shimmer"

        signature_clause("")   # → ""
        signature_clause(None) # → ""
    """
    if not snippet:
        return ""
    return f"— {snippet}"


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

    return _penetration_clause(power_ledger) or _environment_clause(power_ledger)


def _penetration_clause(power_ledger: PowerLedger) -> str:
    """Return the PENETRATION-stage clause (bounce / partial / tear-through), or ``""``."""
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
    return ""


def _environment_clause(power_ledger: PowerLedger) -> str:
    """Return the ENVIRONMENT-amplification clause (ADD with positive amount), or ``""``."""
    from world.magic.constants import LedgerOp, PowerStage  # noqa: PLC0415

    for entry in power_ledger.entries:
        if entry.stage == PowerStage.ENVIRONMENT and entry.op == LedgerOp.ADD and entry.amount > 0:
            return "— the place's resonance swells the working"
    return ""
