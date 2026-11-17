"""Harvesting Primum from a lair or a slain creature (#5125).

Harvestable Primum exists only where hostile monsters are: the stock a lair holds
(``PlacePrimum``) and the Primum a slain creature carries (``CreaturePrimum``). Never an
ordinary room condition and never a call-up. A character is offered Primum only where she
perceives it. She rolls the harvest check with the harvest skill added; a thread on a gift
whose substance this is adds a bonus. The rolled outcome picks what she takes and how many
Primum items she receives (``HarvestOutcome``). A slain creature is harvested once, by one
person; a lair gives up only what it holds, and refills slowly or never.

An unset check, skill or Primum item raises ``HarvestNotConfigured``; a rolled outcome with no
``HarvestOutcome`` row takes nothing and leaves the source untouched, so she may try again.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from evennia_extensions.models import RoomProfile
from world.checks.constants import ModifierSourceKind
from world.checks.services import perform_check_with_modifiers
from world.checks.types import ExtraTraitTerm, ModifierContribution
from world.combat.constants import OpponentStatus
from world.combat.models import CombatOpponent
from world.items.models import ItemTemplate
from world.items.services.primum_items import mint_primum_items
from world.magic.constants import TargetKind
from world.magic.exceptions import HarvestNotConfigured
from world.magic.models import CreaturePrimum, HarvestOutcome, PlacePrimum, Substance
from world.magic.services.primum import gift_substance, primum_steps, step_names_for
from world.magic.services.primum_perception import perceived_substance_ids
from world.magic.services.resonance_environment import get_resonance_environment_config
from world.magic.services.threads import thread_level_multiplier, thread_rung
from world.magic.types.primum import HarvestOffer, HarvestResult

if TYPE_CHECKING:
    from collections.abc import Sequence

    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.magic.models import PrimumStep, ResonanceEnvironmentConfig, Thread

SOURCE_PLACE = "place"
SOURCE_CREATURE = "creature"
NOTHING_LEFT_MESSAGE = "There is nothing left to extract."
EMPTY_HANDED_MESSAGE = "You draw out no Primum."
_SKILL_WEIGHT = Decimal("1.00")


def _room_and_profile(character: ObjectDB) -> tuple[ObjectDB, RoomProfile] | None:  # noqa: OBJECTDB_PARAM - a character
    room = character.location
    if room is None:
        return None
    try:
        return room, room.room_profile
    except RoomProfile.DoesNotExist:
        return None


def _place_offers(
    profile: RoomProfile, perceived: frozenset[int], steps: Sequence[PrimumStep] | None
) -> list[HarvestOffer]:
    rows = [
        (row, row.current_amount())
        for row in PlacePrimum.objects.filter(
            room_profile=profile, substance_id__in=perceived
        ).select_related("substance")
    ]
    rows = [(row, amount) for row, amount in rows if amount > 0]
    names = step_names_for([amount for _row, amount in rows], steps=steps)
    return [
        HarvestOffer(
            substance_id=row.substance_id,
            substance_name=row.substance.name,
            source=SOURCE_PLACE,
            opponent_id=None,
            opponent_name="",
            step_name=name,
        )
        for (row, _amount), name in zip(rows, names, strict=True)
    ]


def _creature_offers(
    room: ObjectDB, perceived: frozenset[int], steps: Sequence[PrimumStep] | None
) -> list[HarvestOffer]:
    foes = list(
        CombatOpponent.objects.filter(
            encounter__room=room,
            status=OpponentStatus.DEFEATED,
            primum_harvested_at__isnull=True,
            creature_template__isnull=False,
        ).order_by("pk")
    )
    if not foes:
        return []
    carried: dict[int, list[CreaturePrimum]] = {}
    for row in CreaturePrimum.objects.filter(
        creature_template_id__in={foe.creature_template_id for foe in foes},
        substance_id__in=perceived,
        amount__gt=0,
    ).select_related("substance"):
        carried.setdefault(row.creature_template_id, []).append(row)
    pairs = [(foe, row) for foe in foes for row in carried.get(foe.creature_template_id, [])]
    names = step_names_for([row.amount for _foe, row in pairs], steps=steps)
    return [
        HarvestOffer(
            substance_id=row.substance_id,
            substance_name=row.substance.name,
            source=SOURCE_CREATURE,
            opponent_id=foe.pk,
            opponent_name=foe.name,
            step_name=name,
        )
        for (foe, row), name in zip(pairs, names, strict=True)
    ]


def harvest_offers(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - a character
    *,
    perceived: frozenset[int] | None = None,
    steps: Sequence[PrimumStep] | None = None,
) -> list[HarvestOffer]:
    """The Primum ``character`` can extract where she stands, and only what she perceives.

    ``perceived`` and ``steps`` are reads the caller already made (``perceived_substance_ids``
    for her own room, ``primum_steps``); omitted, they are read here.

    A lair's stock that still holds some, and each slain creature in the room not yet
    harvested whose kind carries Primum. Never an ordinary room condition or a call-up.
    """
    located = _room_and_profile(character)
    if located is None:
        return []
    room, profile = located
    if perceived is None:
        perceived = perceived_substance_ids(character, room)
    if not perceived:
        return []
    if steps is None:
        steps = primum_steps()
    return _place_offers(profile, perceived, steps) + _creature_offers(room, perceived, steps)


def _gift_thread(character: ObjectDB, substance: Substance) -> Thread | None:  # noqa: OBJECTDB_PARAM - a character
    """Her deepest GIFT thread on a gift whose substance is ``substance``, or None."""
    matching = [
        thread
        for thread in character.threads.all()
        if thread.target_kind == TargetKind.GIFT
        and thread.target_gift_id is not None
        and (held := gift_substance(thread.target_gift)) is not None
        and held.pk == substance.pk
    ]
    return max(matching, key=lambda thread: thread.level, default=None)


def _thread_bonus(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - a character
    substance: Substance,
    config: ResonanceEnvironmentConfig,
) -> list[ModifierContribution]:
    thread = _gift_thread(character, substance)
    if thread is None:
        return []
    value = config.harvest_thread_bonus * thread_level_multiplier(max(thread_rung(thread.level), 1))
    if value <= 0:
        return []
    return [
        ModifierContribution(
            source_kind=ModifierSourceKind.CHARACTER,
            source_label=f"Your {thread.target_gift.name} thread",
            value=int(value),
        )
    ]


def _require_configured(config: ResonanceEnvironmentConfig, substance: Substance) -> ExtraTraitTerm:
    """The harvest skill as a roll term; raises ``HarvestNotConfigured`` for unset tuning."""
    skill = config.harvest_skill
    if config.harvest_check_type is None or skill is None or not skill.is_active:
        raise HarvestNotConfigured
    if not ItemTemplate.objects.filter(primum_substance=substance).exists():
        raise HarvestNotConfigured
    return ExtraTraitTerm(trait=skill, weight=_SKILL_WEIGHT)


def _scaled_quantity(outcome: HarvestOutcome, taken: int) -> int:
    """The items for ``taken`` Primum: scaled down when the source held less than the outcome."""
    if taken <= 0 or outcome.amount_taken <= 0:
        return 0
    return max(outcome.quantity * taken // outcome.amount_taken, 1)


def _take_from_place(
    sheet: CharacterSheet, profile: RoomProfile, substance: Substance, outcome: HarvestOutcome
) -> tuple[int, int] | None:
    """Lock the lair's row, take what it holds up to the outcome, mint. ``(taken, quantity)``.

    None when the lair holds nothing now (it was drained between the offer and the lock).
    """
    now = timezone.now()
    with transaction.atomic():
        # Read as values under the lock, never the identity-mapped instance.
        values = (
            PlacePrimum.objects.select_for_update()
            .filter(room_profile=profile, substance=substance)
            .values("pk", "stored_amount", "stamped_at", "refill_per_day", "capacity", "is_finite")
            .first()
        )
        if values is None:
            return None
        pk = values.pop("pk")
        held = PlacePrimum.amount_at(**values, now=now)
        if held <= 0:
            return None
        taken = min(outcome.amount_taken, held)
        quantity = _scaled_quantity(outcome, taken)
        if taken > 0:
            # Mint first: a failed mint rolls back and leaves the cached row untouched.
            mint_primum_items(sheet, substance, quantity, outcome.quality_tier)
            row = PlacePrimum.objects.get(pk=pk)
            row.stored_amount = held - taken
            row.stamped_at = now
            row.save(update_fields=["stored_amount", "stamped_at"])
    return taken, quantity


def _take_from_creature(
    sheet: CharacterSheet, foe: CombatOpponent, substance: Substance, outcome: HarvestOutcome
) -> tuple[int, int] | None:
    """Lock the slain foe, harvest it once, mint. None when it was already harvested."""
    with transaction.atomic():
        state = (
            CombatOpponent.objects.select_for_update()
            .filter(pk=foe.pk)
            .values_list("primum_harvested_at", "status")
            .first()
        )
        if state is None or state[0] is not None or state[1] != OpponentStatus.DEFEATED:
            return None
        held = (
            CreaturePrimum.objects.filter(
                creature_template_id=foe.creature_template_id, substance=substance
            )
            .values_list("amount", flat=True)
            .first()
        ) or 0
        taken = min(outcome.amount_taken, held)
        quantity = _scaled_quantity(outcome, taken)
        if taken > 0:
            # Mint first: a failed mint rolls back and leaves the cached row untouched.
            mint_primum_items(sheet, substance, quantity, outcome.quality_tier)
        row = CombatOpponent.objects.get(pk=foe.pk)
        row.primum_harvested_at = timezone.now()
        row.save(update_fields=["primum_harvested_at"])
    return taken, quantity


def _failure(substance: Substance, message: str, outcome_name: str = "") -> HarvestResult:
    return HarvestResult(
        harvested=False,
        substance_name=substance.name,
        amount_taken=0,
        quantity=0,
        outcome_name=outcome_name,
        message=message,
    )


def _find_offer(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - a character
    substance: Substance,
    opponent: CombatOpponent | None,
) -> HarvestOffer | None:
    for offer in harvest_offers(character):
        if offer.substance_id != substance.pk:
            continue
        if opponent is None and offer.source == SOURCE_PLACE:
            return offer
        if opponent is not None and offer.opponent_id == opponent.pk:
            return offer
    return None


def harvest(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - a character
    *,
    substance: Substance,
    opponent: CombatOpponent | None = None,
) -> HarvestResult:
    """Extract ``substance`` from the lair she stands in, or from the slain ``opponent``.

    The substance must be among her ``harvest_offers``; otherwise nothing is left to extract
    (the same words whether the source is dry, harvested, absent or unperceived). Raises
    ``HarvestNotConfigured`` for unset tuning.
    """
    sheet = character.character_sheet
    if sheet is None or _find_offer(character, substance, opponent) is None:
        return _failure(substance, NOTHING_LEFT_MESSAGE)
    config = get_resonance_environment_config()
    skill_term = _require_configured(config, substance)
    check_result = perform_check_with_modifiers(
        character,
        config.harvest_check_type,
        target_difficulty=0,
        extra_contributions=_thread_bonus(character, substance, config),
        extra_traits=[skill_term],
    )
    rolled = check_result.outcome
    outcome_name = rolled.name if rolled is not None else ""
    outcome = (
        HarvestOutcome.objects.filter(outcome_tier=rolled).select_related("quality_tier").first()
        if rolled is not None
        else None
    )
    if outcome is None:
        return _failure(substance, EMPTY_HANDED_MESSAGE, outcome_name)
    if opponent is None:
        profile = character.location.room_profile
        taken_quantity = _take_from_place(sheet, profile, substance, outcome)
    else:
        taken_quantity = _take_from_creature(sheet, opponent, substance, outcome)
    if taken_quantity is None:
        return _failure(substance, NOTHING_LEFT_MESSAGE, outcome_name)
    taken, quantity = taken_quantity
    if taken <= 0:
        return _failure(substance, EMPTY_HANDED_MESSAGE, outcome_name)
    return HarvestResult(
        harvested=True,
        substance_name=substance.name,
        amount_taken=taken,
        quantity=quantity,
        outcome_name=outcome_name,
        message=f"You extract {quantity} {substance.name} Primum.",
    )
