"""Combat encounter → story beat auto-wiring (#1746).

Wires the ENCOUNTER_COMPLETED reactive event to record_outcome_tier_completion:
when a CombatEncounter completes, classify_battle_outcome maps its
(EncounterOutcome, RiskLevel) to a designer-tunable CheckOutcome, and the
ENCOUNTER_COMPLETED subscriber resolves any linked OUTCOME_TIER beat via
record_outcome_tier_completion.

FLED/ABANDONED encounters (or any unmapped outcome×risk pair) resolve the beat
to PENDING_GM_REVIEW via force_outcome — a machine-detected non-success/failure
terminal outcome that needs a GM's adjudication rather than an immediate
pre-authored consequence.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.traits.models import CheckOutcome

if TYPE_CHECKING:
    from world.combat.models import CombatEncounter

ENCOUNTER_BEAT_TRIGGER_NAME = "encounter_completed_beat_wiring"


def classify_battle_outcome(encounter: CombatEncounter) -> CheckOutcome | None:
    """Map a completed encounter's (outcome, risk_level) to a CheckOutcome tier.

    Returns the designer-authored CheckOutcome for the encounter's outcome×risk,
    or None when no mapping row exists or the row's check_outcome is null
    (FLED/ABANDONED, or a pair the designers left unmapped). None signals the
    caller to resolve the beat to PENDING_GM_REVIEW rather than firing a
    consequence pool.

    Args:
        encounter: A completed CombatEncounter. Its ``outcome`` and
            ``risk_level`` drive the mapping lookup.

    Returns:
        The mapped CheckOutcome, or None.

    Raises:
        ValueError: if the encounter has no outcome set (programmer error — the
            ENCOUNTER_COMPLETED event only fires post-completion).
    """
    if not encounter.outcome:
        msg = (
            f"Encounter {encounter.pk} has no outcome; classify_battle_outcome "
            "should only be called on a completed encounter."
        )
        raise ValueError(msg)
    # Local import to avoid a circular dependency at module load: the factories
    # module imports ENCOUNTER_BEAT_TRIGGER_NAME from here (see Task 4).
    from world.combat.models import EncounterOutcomeMapping  # noqa: PLC0415

    mapping = EncounterOutcomeMapping.objects.filter(
        outcome=encounter.outcome,
        risk_level=encounter.risk_level,
    ).first()
    return mapping.check_outcome if mapping is not None else None
