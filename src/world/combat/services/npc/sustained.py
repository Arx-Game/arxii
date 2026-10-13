"""Sustained actions: maturation and erosion riders."""

from __future__ import annotations

from world.combat.constants import SUSTAINED_HIT_DOWNGRADE, ParticipantStatus, SustainedKind
from world.combat.models import (
    CombatEncounter,
    CombatParticipant,
    CombatRoundAction,
    CombatRoundActionTarget,
    SustainedAction,
)
from world.combat.services.npc.sustained_narration import (
    _broadcast_sustained_broken,
    _broadcast_sustained_erosion,
    _broadcast_sustained_held,
)


def _mature_sustained_technique(sustained: SustainedAction, round_number: int) -> None:
    """Clone the declaring ``CombatRoundAction`` into the maturation round (#2705).

    ``declared_action`` is null only in a data-integrity gap — it must always be
    set at TECHNIQUE declaration time (see ``_sync_sustained_technique_declaration``)
    — treated as a broken commitment rather than silently dropped.

    Resets the per-round/resolution fields that would otherwise carry stale state
    forward from the DECLARING round: ``is_ready`` (flips True so the matured
    action behaves like a normal ready declaration), ``interaction`` /
    ``interaction_timestamp`` (the ACTION-mode Interaction, if any, belongs to
    the declaring round's resolution — a stale FK here would misattribute this
    round's narration to that one), ``combo_upgrade`` (a combo detected against
    the DECLARING round's board has no bearing on the maturation round's board),
    ``succor_resolution`` (a cached Succor outcome is round-scoped), ``from_
    entrance`` (a windup declared as a dramatic technique entrance must not
    spuriously re-fire ``_maybe_suggest_entrance_dramatic_moment`` N rounds
    later — ``_resolve_pc_action`` fires that suggestion whenever
    ``action.from_entrance`` is true, #2705 adversarial review, Fix 4), and
    ``maneuver`` / ``item_instance`` (a maneuver and the item it uses belong to
    the DECLARING round's action shape — a sustained commitment is never itself
    a maneuver — not to the matured cast).

    **Deliberately PRESERVED, not reset:** ``confirm_soulfray_risk`` (the
    player's consent for THIS specific cast — it does not expire at maturation,
    it IS what the player is committing to) and the cast geometry FKs
    (``cast_destination``, ``cast_position_a``, ``cast_position_b``,
    ``redirect_opponent_target``, ``redirect_object_target``) — these describe
    the declared cast itself, not per-round resolution bookkeeping, so they
    carry forward unchanged into the maturation round.

    Does **not** delete a pre-existing same-round row to make room: decision D2
    (enforced by ``_validate_no_pending_sustained``) means one cannot exist while
    this commitment is pending — an ``IntegrityError`` here would mean D2's
    invariant broke elsewhere, and surfacing that beats silently discarding a
    player's declaration.

    **Deliberate deviation from the plan's literal ``clone.pk = None`` recipe**
    (verified with a scratch repro during implementation — a real bug, not a
    style preference): ``CombatRoundAction`` is a ``SharedMemoryModel``
    (idmapper identity map). Nulling ``pk``/``id`` on the fetched ``original``
    instance and re-``save()``-ing it reassigns a NEW pk to that SAME cached
    Python object, but the idmapper's cache entry for the ORIGINAL pk is never
    updated — it keeps pointing at this now-mutated object. Any later
    ``CombatRoundAction.objects.get(pk=<declaring round's pk>)`` in the same
    process (audit views, admin, a future round's queries) would silently
    return the MATURATION round's data instead of the true declaring-round
    row, for the remaining life of the process. Building a plain field dict
    and calling ``.objects.create()`` instead sidesteps this entirely — the
    fetched ``original`` instance and its cache entry are never touched, and a
    genuinely new instance/row is created for the new pk. The field dict is
    built from ``original._meta.concrete_fields`` rather than a hardcoded
    list so a future field addition to ``CombatRoundAction`` is copied
    automatically instead of silently dropped.
    """
    if sustained.declared_action_id is None:
        _broadcast_sustained_broken(sustained, reason="comes to nothing")
        sustained.delete()
        return

    original = sustained.declared_action
    extra_target_opponent_ids = list(original.extra_targets.values_list("opponent_id", flat=True))

    fields = {
        field.attname: getattr(original, field.attname)
        for field in original._meta.concrete_fields  # noqa: SLF001
        if not field.primary_key
    }
    fields["round_number"] = round_number
    fields["is_ready"] = True
    fields["interaction_id"] = None
    fields["interaction_timestamp"] = None
    fields["combo_upgrade_id"] = None
    fields["succor_resolution"] = None
    fields["from_entrance"] = False
    fields["maneuver"] = None
    fields["item_instance_id"] = None
    clone = CombatRoundAction.objects.create(**fields)

    if extra_target_opponent_ids:
        CombatRoundActionTarget.objects.bulk_create(
            [
                CombatRoundActionTarget(action=clone, opponent_id=opponent_id)
                for opponent_id in extra_target_opponent_ids
            ]
        )

    _broadcast_sustained_held(sustained)
    sustained.delete()


def _mature_sustained_ritual(sustained: SustainedAction) -> None:
    """Dispatch the held ritual at maturation, or break on a content-surface error (#2705).

    The RITUAL sibling of ``_mature_sustained_technique``. Components were
    already validated and consumed at declaration
    (``PerformRitualAction._validate_components``, before
    ``try_declare_sustained_ritual`` ever creates this row) — so a caught
    failure here still deletes the row with no refund, the same "the cost
    stands" ruling ``_mature_one_sustained_action`` applies to the
    downgrades-exceeded break one level up.

    Catches only the same ritual-surface exceptions ``PerformRitualAction``
    itself catches (``RitualComponentError`` / ``ResonanceInsufficient`` /
    ``AnchorCapExceeded`` / ``InvalidImbueAmount`` / ``XPInsufficient`` /
    ``GhostTutorError``) — a content-authoring gap in ONE participant's
    ritual must not abort round resolution for every other combatant.
    Deliberately does NOT catch bare ``Exception`` (no defensive
    error-papering, CLAUDE.md) — an unexpected crash here should surface
    loudly, not be swallowed into a generic broken-ritual line.
    """
    from world.magic.exceptions import (  # noqa: PLC0415
        AnchorCapExceeded,
        GhostTutorError,
        InvalidImbueAmount,
        ResonanceInsufficient,
        RitualComponentError,
        XPInsufficient,
    )
    from world.magic.services.ritual_dispatch import dispatch_ritual  # noqa: PLC0415

    try:
        dispatch_ritual(
            ritual=sustained.ritual,
            performer_sheet=sustained.participant.character_sheet,
        )
    except (
        RitualComponentError,
        ResonanceInsufficient,
        AnchorCapExceeded,
        InvalidImbueAmount,
        XPInsufficient,
        GhostTutorError,
    ):
        _broadcast_sustained_broken(sustained, reason="fizzles")
        sustained.delete()
        return

    _broadcast_sustained_held(sustained)
    sustained.delete()


def _mature_one_sustained_action(sustained: SustainedAction, round_number: int) -> None:
    """Resolve a single matured ``SustainedAction``: break, lose-holder, or hold (#2705).

    Mirrors ``_mature_one_pending_attack``'s three-way branch shape. Unlike the
    NPC side there is no damage ramp (D1, ADR-0188) — a held commitment resolves
    at full effect or not at all.

    1. ``downgrades > 0 and downgrades >= absorption_budget`` -> broken. **The
       cost stands — nothing is refunded.** Components/anima were charged at
       declaration (rituals, Task 5); the spec's ruling is that a broken
       sustain is simply spent, which is what makes committing to one real
       stakes rather than a free retry. Requires ``downgrades > 0``, not just
       ``>=``, so that a Critical-Failure budget of 0 breaks on the participant's
       FIRST LANDING HIT (``_apply_sustained_erosion_rider`` takes it to
       ``downgrades=1``, already ``>= 0``) rather than at maturation regardless
       of whether the participant was ever touched — ``0 >= 0`` alone would
       fizzle an untouched commitment in total safety, which the approved spec
       never intended (#2705 adversarial review, Fix 5).
    2. The holder can no longer hold it together (left the encounter or died) ->
       broken, distinct "comes to nothing" narration.
    3. ``SustainedKind.TECHNIQUE`` -> clone the declaring action into this round.
    4. ``SustainedKind.RITUAL`` -> dispatch the ritual's authored execution
       payload (Task 5's ``_mature_sustained_ritual``); a caught content-surface
       exception breaks the commitment instead of raising through round
       resolution.
    """
    from world.vitals.services import is_dead  # noqa: PLC0415

    if sustained.downgrades > 0 and sustained.downgrades >= sustained.absorption_budget:
        _broadcast_sustained_broken(sustained)
        sustained.delete()
        return

    participant = sustained.participant
    if participant.status != ParticipantStatus.ACTIVE or is_dead(participant.character_sheet):
        _broadcast_sustained_broken(sustained, reason="comes to nothing")
        sustained.delete()
        return

    if sustained.sustained_kind == SustainedKind.TECHNIQUE:
        _mature_sustained_technique(sustained, round_number)
        return

    _mature_sustained_ritual(sustained)


def _mature_sustained_actions(encounter: CombatEncounter, round_number: int) -> None:
    """Mature every PC ``SustainedAction`` whose commitment resolves this round (#2705).

    The PC-side sibling of ``_mature_pending_opponent_attacks`` — called from
    ``resolve_round`` immediately after it, in the same pass, BEFORE the
    round's ``CombatRoundAction`` rows are queried into ``pc_actions``, so a
    held technique's cloned row is picked up by the normal PC pipeline
    unmodified in the same pass.
    """
    rows = list(
        SustainedAction.objects.filter(
            encounter=encounter,
            resolves_round=round_number,
        ).select_related(
            "participant__character_sheet__character",
            "ritual",
            "technique",
            "declared_action",
        )
    )
    for sustained in rows:
        _mature_one_sustained_action(sustained, round_number)


def _apply_sustained_erosion_rider(participant: CombatParticipant, damage_dealt: int) -> None:
    """A landing hit on a sustaining PC adds a downgrade to their commitment (#2705).

    The PC-side sibling of ``_apply_windup_interception_rider``. Only fires on
    ``damage_dealt > 0`` — a fully-mitigated hit does not erode anything.
    Matches a NOT-YET-MATURED row (``resolves_round__gte`` the current round)
    for the same reason the windup rider does: a ``SustainedAction`` maturing
    THIS round is already resolved and deleted by ``_mature_sustained_actions``
    before PC damage resolves this round, so this can only ever reach a future
    one.

    Unlike the NPC side there is no ``called_out``/blind split: a PC's
    sustained action is telegraphed publicly the moment it is declared (see
    ``_broadcast_sustained_telegraph``), so there is nothing to "call out" —
    every landing hit erodes by the same flat ``SUSTAINED_HIT_DOWNGRADE``.
    """
    if damage_dealt <= 0:
        return

    sustained = SustainedAction.objects.filter(
        participant=participant,
        resolves_round__gte=participant.encounter.round_number,
    ).first()
    if sustained is None:
        return

    sustained.downgrades += SUSTAINED_HIT_DOWNGRADE
    sustained.save(update_fields=["downgrades"])
    _broadcast_sustained_erosion(sustained)
