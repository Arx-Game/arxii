"""Validators run on a declaration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat.constants import ActionCategory, SustainedKind
from world.combat.models import CombatEncounter, CombatOpponent, CombatParticipant, SustainedAction

if TYPE_CHECKING:
    from world.magic.models import Technique


def _validate_no_pending_sustained(
    participant: CombatParticipant, encounter: CombatEncounter
) -> None:
    """Raise if *participant* is still holding a SustainedAction together (#2705, D2).

    Sustaining occupies your action: you cannot hold a ritual together or wind
    up a technique and also declare something new. This is structural, not
    merely thematic — ``CombatRoundAction``'s ``unique_action_per_participant_
    per_round`` constraint means maturation (which clones the declaring action
    into the maturation round) would collide with a same-round declaration if
    this were allowed.

    Filters ``resolves_round__gte`` (not ``__gt``): the round lifecycle is
    DECLARING(R) *then* ``resolve_round(R)`` — a row maturing THIS round is
    NOT yet consumed while declaration is happening, because maturation only
    runs from ``resolve_round``, during RESOLVING. A ``__gt`` filter would
    therefore let a second action be declared for the maturing participant's
    own maturation round; ``update_or_create`` would create a
    ``CombatRoundAction(participant, round_number)`` row, and
    ``_mature_sustained_technique``'s bare ``.objects.create()`` for that same
    ``(participant, round_number)`` would then collide with
    ``unique_action_per_participant_per_round`` and raise an uncaught
    ``IntegrityError`` that aborts ``resolve_round`` for the entire encounter
    (#2705 adversarial review, Fix 1). ``__gte`` closes the gap: a row with
    ``resolves_round == round_number`` blocks declaration exactly like one
    still further out.

    Excludes a TECHNIQUE row with ``declared_round == round_number``: that row
    is THIS round's own in-progress commitment, not a prior one blocking a new
    declaration — a player amending their current round's declaration must
    still reach ``_sync_sustained_technique_declaration``'s delete-then-recreate
    idempotence, never this gate. A RITUAL row is never excluded this way even
    when ``declared_round == round_number``: a ritual is declared through
    ``try_declare_sustained_ritual`` (``PerformRitualAction``), a completely
    different seam from ``declare_action`` — there is no sync step here that
    will replace it, so a same-round ritual commitment must still block a
    combat declaration (Fix 2b; conducting a ritual and swinging a sword in the
    same round is not allowed, D2).
    """
    pending = (
        SustainedAction.objects.filter(
            participant=participant,
            resolves_round__gte=encounter.round_number,
        )
        .exclude(
            declared_round=encounter.round_number,
            sustained_kind=SustainedKind.TECHNIQUE,
        )
        .first()
    )
    if pending is not None:
        msg = f"Cannot declare an action: you are still holding {pending.subject_name} together."
        raise ValueError(msg)


def _validate_passive_slot(
    focused_category: str | None,
    *,
    physical_passive: Technique | None,
    social_passive: Technique | None,
    mental_passive: Technique | None,
) -> None:
    """Raise if the passive slot matching ``focused_category`` is occupied."""
    if focused_category is None:
        return
    passive_map = {
        ActionCategory.PHYSICAL: physical_passive,
        ActionCategory.SOCIAL: social_passive,
        ActionCategory.MENTAL: mental_passive,
    }
    if passive_map.get(focused_category) is not None:
        msg = (
            f"Cannot declare action: {focused_category} passive must be "
            f"None when focused_category is {focused_category}."
        )
        raise ValueError(msg)


def _supplied_target_kind(
    participant: CombatParticipant,
    focused_ally_target: CombatParticipant | None,
    focused_opponent_target: CombatOpponent | None,
) -> object | None:
    """Map the supplied target to its ConditionTargetKind, or None if no target."""
    from world.magic.models.techniques import ConditionTargetKind  # noqa: PLC0415

    if focused_ally_target is not None:
        if focused_ally_target == participant:
            return ConditionTargetKind.SELF
        return ConditionTargetKind.ALLY
    if focused_opponent_target is not None:
        return ConditionTargetKind.ENEMY
    return None


def _validate_target_kind_alignment(
    participant: CombatParticipant,
    focused_action: Technique,
    focused_ally_target: CombatParticipant | None,
    focused_opponent_target: CombatOpponent | None,
) -> None:
    """Raise if the supplied target's kind is not accepted by the technique."""
    from world.magic.models.techniques import ConditionTargetKind  # noqa: PLC0415

    rows = list(focused_action.condition_applications.all())
    has_base_power = focused_action.effect_type.base_power is not None

    if rows:
        kinds = {row.target_kind for row in rows}
        target_supplied_kind = _supplied_target_kind(
            participant, focused_ally_target, focused_opponent_target
        )
        # Accept SELF/ALLY interchangeably for ally-targets
        accepted = kinds.copy()
        if ConditionTargetKind.ALLY in accepted:
            accepted.add(ConditionTargetKind.SELF)
        if ConditionTargetKind.SELF in accepted:
            accepted.add(ConditionTargetKind.ALLY)
        if target_supplied_kind is not None and target_supplied_kind not in accepted:
            msg = (
                f"Technique target_kinds {sorted(kinds)} do not match supplied "
                f"target kind '{target_supplied_kind}'."
            )
            raise ValueError(msg)

    if has_base_power and not rows and focused_opponent_target is None:
        msg = "Damage technique requires focused_opponent_target."
        raise ValueError(msg)


def _validate_technique_reach(
    participant: CombatParticipant,
    focused_action: Technique,
    *,
    focused_opponent_target: CombatOpponent | None,
    focused_ally_target: CombatParticipant | None,
) -> None:
    """Raise ValueError if the technique's reach cannot cover the declared target.

    Resolves the target's ObjectDB from either ``focused_opponent_target.objectdb``
    (for NPC/opponent targets) or ``focused_ally_target.character_sheet.character``
    (for participant/ally targets). Delegates to ``technique_can_reach``, which is
    lenient when either combatant is unpositioned.

    Only runs when a target is actually provided; skips self/no-target declarations.
    """
    from world.combat.reach import technique_can_reach  # noqa: PLC0415

    attacker_objectdb = participant.character_sheet.character

    target_objectdb = None
    if focused_opponent_target is not None:
        target_objectdb = focused_opponent_target.objectdb
    elif focused_ally_target is not None and focused_ally_target != participant:
        target_objectdb = focused_ally_target.character_sheet.character

    if target_objectdb is None:
        # No external target (self-buff or no target) — reach is not constraining.
        return

    if not technique_can_reach(attacker_objectdb, focused_action, target_objectdb):
        from actions.errors import ActionDispatchError  # noqa: PLC0415

        raise ActionDispatchError(ActionDispatchError.TARGET_OUT_OF_REACH)


def _validate_strain_commitment(participant: CombatParticipant, strain_commitment: int) -> None:
    """Reject a strain overcommit beyond the participant's anima budget (#3446).

    The push-yourself lever is capped by the same budget the clash UI reads
    (mirrors ``_cap_strain_by_anima`` on the standalone cast serializer).
    Negative values are a caller bug, not a player choice.
    """
    if strain_commitment < 0:
        msg = "Strain commitment cannot be negative."
        raise ValueError(msg)
    if strain_commitment > participant.available_strain:
        msg = (
            f"Strain commitment ({strain_commitment}) exceeds available "
            f"anima ({participant.available_strain})."
        )
        raise ValueError(msg)
