"""Reactive upkeep: payment, lapses and drains."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.combat import services as _svc
from world.combat.constants import ParticipantStatus
from world.combat.models import CombatEncounter, CombatParticipant
from world.combat.services.encounter.anima import _get_anima
from world.magic.models.soulfray import SoulfrayConfig
from world.magic.services.anima import deduct_anima

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.conditions.models import ConditionInstance
    from world.magic.models.anima import CharacterAnima


def _narrate_upkeep_lapse(inst: ConditionInstance, encounter: CombatEncounter) -> None:
    """Tell the payer, the bearer (when different) and the room that a ward lapsed (#3574).

    Called immediately before the lapse ``inst.delete()`` so the names are
    still resolvable. The payer rule is ``drain_reactive_upkeep``'s own:
    ``source_character`` when set, else the bearer. Room line carries no
    numbers; the private lines say only that the fee could not be met.
    """
    from world.scenes.interaction_services import narrate_privately  # noqa: PLC0415

    bearer = inst.target
    payer = inst.source_character or bearer
    ward = inst.condition.name
    if payer.pk == bearer.pk:
        narrate_privately(payer, f"You cannot sustain {ward}; it lapses.")
    else:
        narrate_privately(payer, f"You cannot sustain {ward} on {bearer}; it lapses.")
        narrate_privately(bearer, f"{payer}'s {ward} over you lapses.")
    _svc._broadcast_commitment_line(encounter, f"The {ward} over {bearer} gutters out.")  # noqa: SLF001 (test patch seam)


def _debit_ally_paid_upkeep(
    inst: ConditionInstance, cost: int, *, encounter: CombatEncounter
) -> None:
    """Debit a condition's upkeep from its ally ``source_character`` payer.

    The payer is the condition's ``source_character`` — distinct from the
    bearer. If the payer cannot pay in full and hasn't consented, the
    condition lapses (its ``ConditionInstance`` row is deleted and any
    ``Trigger`` rows on it cascade). A consented payer instead runs into
    deficit and accrues Soulfray (#3573) via ``_pay_upkeep``.
    """
    payer = inst.source_character
    payer_anima = _get_anima(payer)
    if payer_anima is None:
        _narrate_upkeep_lapse(inst, encounter)
        inst.delete()  # lapse — Trigger rows cascade via source_condition FK
        return
    if payer_anima.current < cost and not inst.soulfray_consented:
        _narrate_upkeep_lapse(inst, encounter)
        inst.delete()  # lapse - Trigger rows cascade via source_condition FK
        return
    _pay_upkeep(payer, payer_anima, cost, inst, encounter)


def _pay_upkeep(
    payer: ObjectDB,  # noqa: OBJECTDB_PARAM
    anima: CharacterAnima,
    cost: int,
    inst: ConditionInstance,
    encounter: CombatEncounter,
) -> None:
    """Debit one round of upkeep; a consented payer runs into deficit and accrues (#3573).

    Shared by the ally-paid and self-paid upkeep branches of
    ``drain_reactive_upkeep`` so the debit-then-accrue sequencing lives in one
    place. Unconsented callers must not reach here already-unaffordable - the
    caller lapses the condition instead.
    """
    deficit = deduct_anima(payer, cost, lethal=encounter.is_lethal)
    if not inst.soulfray_consented:
        return
    _svc.accumulate_soulfray(
        character=payer,
        anima=anima,
        deficit=deficit,
        soulfray_config=SoulfrayConfig.objects.cached_singleton(),
        check_result=None,
        lethal=encounter.is_lethal,
    )
    if deficit > 0:
        _svc._broadcast_commitment_line(  # noqa: SLF001 (test patch seam)
            encounter, f"{payer} bleeds soul to keep the ward on {inst.target}."
        )


def _drain_participant_upkeep(
    part: CombatParticipant, anima: CharacterAnima, encounter: CombatEncounter
) -> None:
    """Debit one participant's sustained conditions for this round.

    Anima is written at most once (after the loop) so that N self-sustained
    conditions produce a single UPDATE rather than N; ally-sourced conditions
    debit their payer's pool immediately, since that payer is not necessarily
    among the participants being iterated. A consented instance that runs
    unaffordable (#3573) is the rare exception: it flushes the accumulated
    ``remaining`` first, then pays into deficit through ``_pay_upkeep`` rather
    than lapsing.
    """
    from world.conditions.models import ConditionInstance  # noqa: PLC0415

    char = part.character_sheet.character
    instances = ConditionInstance.objects.filter(
        target=char,
        is_suppressed=False,
        resolved_at__isnull=True,
        condition__upkeep_anima_per_round__gt=0,
    ).select_related("condition")
    remaining = anima.current
    for inst in instances:
        cost = inst.condition.upkeep_anima_per_round
        if inst.source_character_id and inst.source_character_id != char.id:
            _debit_ally_paid_upkeep(inst, cost, encounter=encounter)
            continue
        if remaining >= cost:
            remaining -= cost
        elif inst.soulfray_consented:
            anima.current = remaining
            anima.save(update_fields=["current"])
            _pay_upkeep(char, anima, cost, inst, encounter)
            # deduct_anima (inside _pay_upkeep) re-fetches CharacterAnima by
            # pk under select_for_update; SharedMemoryModel identity-maps by
            # pk so that call returns this same instance and its glut-first
            # spend already landed on anima.current - carry that forward
            # instead of clobbering it back to 0 (#3573 review fix).
            remaining = anima.current
        else:
            _narrate_upkeep_lapse(inst, encounter)
            inst.delete()  # lapse — Trigger rows cascade via source_condition FK
    if remaining != anima.current:
        anima.current = remaining
        anima.save(update_fields=["current"])


def drain_reactive_upkeep(encounter: CombatEncounter) -> None:
    """Debit per-round upkeep from each active participant's sustained conditions.

    For each ACTIVE participant, for each active (not suppressed, not resolved)
    condition with ``upkeep_anima_per_round > 0``: spend that anima from the
    condition's payer's ``CharacterAnima`` pool. If the payer cannot pay in
    full, the condition lapses — its ``ConditionInstance`` row is deleted and
    any ``Trigger`` rows on it cascade. The lapse is narrated to the payer, the
    bearer and the room (#3574, ``_narrate_upkeep_lapse``).

    Payer rule (#2208): ``source_character`` pays when set — an ally ward
    strains its caster, never its bearer. Self-cast wards are unchanged
    (source == bearer). Only looking up a separate ``CharacterAnima`` when
    ``source_character_id`` differs from the bearer's keeps the common
    self-ward path on the single-query-per-participant code path below.

    Participants without a ``CharacterAnima`` row are skipped entirely — including
    any caster-paid wards they bear (ADR-0118 edge: an anima-less bearer's ally
    ward gets free upkeep; acceptable because player characters always have an
    anima row).

    Anima is written at most once per participant (after the inner loop) so that
    a round with N self-sustained conditions produces a single UPDATE rather
    than N; ally-sourced conditions debit their payer's pool immediately since
    that payer is not necessarily among the participants being iterated. A
    consented instance that runs unaffordable (#3573) is the rare exception: it
    flushes the accumulated ``remaining`` immediately, then pays through
    ``_pay_upkeep`` into deficit rather than lapsing.
    """
    parts = CombatParticipant.objects.filter(
        encounter=encounter, status=ParticipantStatus.ACTIVE
    ).select_related("character_sheet__character")
    for part in parts:
        anima = _get_anima(part.character_sheet.character)
        if anima is None:
            continue
        _drain_participant_upkeep(part, anima, encounter)
