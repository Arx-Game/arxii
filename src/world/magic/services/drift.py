"""Drift holdings and the conversion offer a deed opens (#4733, slice 4 of #4672).

Drift is resonance a character holds that sits off their own aura: any
``CharacterResonance`` with a positive balance whose affinity differs from the aura's
dominant affinity. Converting it needs no threshold. A deed (a grant from a ``DEED_GAIN_SOURCES``
source) that grows a resonance of the character's own affinity, made in a live scene by a
character who has convertible drift, opens a ``DriftConversionOffer`` for that scene and
adds to the cap of converting drift toward the resonance the deed grew. The offer lapses
when the scene finishes.

Carried drift (#4732) is the weighted pull of those holdings against the acting aura.
``drift_for`` measures it against the acting aura's dominant affinity;
``check_resonance_focus`` runs once per cast, before the cast's modifiers are gathered,
and on a failed focus roll applies (or deepens) the authored conflict condition, whose
own check modifier then reaches the same cast's roll. Its numbers live in ``DriftConfig``.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from world.magic.constants import DEED_GAIN_SOURCES, ComponentMode
from world.magic.exceptions import ConversionMappingError
from world.magic.models.aura import CharacterResonance
from world.magic.models.drift import (
    DriftConfig,
    DriftConversionCap,
    DriftConversionOffer,
    DriftCorrectionConfig,
)
from world.magic.models.motifs import MotifResonanceAssociation
from world.magic.services.conversion import conversion_pair
from world.magic.types.drift import DriftReading, FocusOutcome, QualifyingComponent

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance
    from world.magic.models import Technique
    from world.magic.models.affinity import Affinity, Resonance
    from world.magic.models.gain import ResonanceGrant
    from world.scenes.models import Scene


# A pair with no authored AffinityInteraction row counts at full weight.
_UNAUTHORED_PAIR_WEIGHT = Decimal(1)


def get_drift_config() -> DriftConfig:
    """Get-or-create the drift config singleton (pk=1)."""
    cfg = DriftConfig.objects.cached_singleton()
    if cfg is None:
        cfg, _ = DriftConfig.objects.get_or_create(pk=1)
    return cfg


def drift_for(sheet: CharacterSheet) -> DriftReading:
    """The off-aura drift ``sheet``'s character carries against the aura she acts with.

    The dominant affinity is the acting aura's (an active alternate self's affinity
    while one is worn). Her balances in that affinity are her main balance; every
    other balance counts as drift, weighted by the authored
    ``AffinityInteraction.conflict_weight`` of (its affinity, the dominant one). The
    threshold is ``max(threshold_floor, threshold_percent of the main balance)``;
    drift strictly past it is one step, plus one per further ``severity_step``.
    A character with no aura to measure against reads zero.
    """
    from world.magic.models import AffinityInteraction  # noqa: PLC0415
    from world.magic.services.acting_aura import acting_aura  # noqa: PLC0415

    aura = acting_aura(sheet)
    dominant = aura.dominant_affinity if aura is not None else None
    if dominant is None:
        return DriftReading(drift=0, threshold=0, steps_past=0, dominant_affinity=None)

    cfg = get_drift_config()
    main = 0
    weighted_drift = Decimal(0)
    for row in sheet.character.resonances.all():
        affinity = row.resonance.affinity
        if affinity.pk == dominant.pk:
            main += row.balance
            continue
        interaction = AffinityInteraction.objects.interaction_for(affinity, dominant)
        weight = interaction.conflict_weight if interaction is not None else _UNAUTHORED_PAIR_WEIGHT
        weighted_drift += row.balance * weight

    drift = int(weighted_drift)
    threshold = max(cfg.threshold_floor, main * cfg.threshold_percent // 100)
    steps_past = 0
    if drift > threshold:
        steps_past = 1 + (drift - threshold - 1) // cfg.severity_step
    return DriftReading(
        drift=drift, threshold=threshold, steps_past=steps_past, dominant_affinity=dominant
    )


def check_resonance_focus(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM - rolls, conditions and messages take the character
    technique: Technique,
    *,
    pulled_resonance: Resonance | None = None,
) -> FocusOutcome | None:
    """Roll the caster's focus against her carried drift, once per cast.

    ``use_technique`` calls it for every cast, after anima is deducted and before
    ``resolve_fn`` gathers the cast's check modifiers, so a condition applied here
    reaches the same cast's roll. A pull is part of its cast, not a roll of its own:
    ``pulled_resonance`` is the resonance this cast pulls, which the caller names
    (the declared cast pull's, or the combat round's committed pull); None means
    the cast pulls nothing. Working it outside her dominant affinity adds
    ``off_aura_pull_steps``.

    Returns None, rolling nothing, when the config's focus check type or conflict
    condition is unset (the Required content dashboard lists both) or when there are
    no steps. On a failed roll (success level below 1) the conflict condition is
    applied at ``steps + (1 - success_level)`` severity, so a worse roll never costs
    less; if she already holds it, its severity advances by one instead.
    """
    from world.checks.services import perform_check_with_modifiers  # noqa: PLC0415
    from world.conditions.services import (  # noqa: PLC0415
        advance_condition_severity,
        apply_condition,
        get_condition_instance,
    )
    from world.magic.constants import MagicActivity  # noqa: PLC0415
    from world.magic.services.magic_skills import activity_skill_terms  # noqa: PLC0415

    cfg = get_drift_config()
    if cfg.focus_check_type_id is None or cfg.conflict_condition_id is None:
        return None
    try:
        sheet = character.sheet_data
    except ObjectDoesNotExist:
        return None
    reading = drift_for(sheet)
    if reading.dominant_affinity is None:
        return None
    steps = reading.steps_past
    if (
        pulled_resonance is not None
        and pulled_resonance.affinity_id != reading.dominant_affinity.pk
    ):
        steps += cfg.off_aura_pull_steps
    if steps <= 0:
        return None

    difficulty = cfg.focus_base_difficulty + steps * cfg.focus_difficulty_per_step
    character.msg(
        f"Focus check: you are carrying drift past your threshold against your "
        f"{reading.dominant_affinity.name} aura."
    )
    result = perform_check_with_modifiers(
        character,
        cfg.focus_check_type,
        difficulty,
        extra_traits=activity_skill_terms(MagicActivity.KEEPING_FOCUS),
    )
    success_level = result.success_level
    if success_level >= 1:
        return FocusOutcome(success_level=success_level, steps=steps, applied_severity=0)

    condition = cfg.conflict_condition
    existing = get_condition_instance(character, condition)
    if existing is not None:
        applied = 1
        advance_condition_severity(existing, applied)
    else:
        applied = steps + (1 - success_level)
        apply_condition(
            character,
            condition,
            severity=applied,
            source_technique=technique,
        )
    character.msg(f"You lose your focus as you work {technique.name}: {condition.name}.")
    return FocusOutcome(success_level=success_level, steps=steps, applied_severity=applied)


def get_drift_correction_config() -> DriftCorrectionConfig:
    """Lazy-create the DriftCorrectionConfig singleton at pk=1."""
    config = DriftCorrectionConfig.objects.cached_singleton()
    if config is None:
        config, _ = DriftCorrectionConfig.objects.get_or_create(pk=1)
    return config


def own_affinity(sheet: CharacterSheet) -> Affinity | None:
    """The affinity the character's aura is mostly made of, or None.

    None when the sheet has no aura yet or the aura holds no shares. Never raises.
    """
    aura = sheet.aura_or_none
    if aura is None or not aura.cached_shares:
        return None
    return aura.dominant_affinity


def drift_holdings(sheet: CharacterSheet) -> list[CharacterResonance]:
    """Resonance held off the aura: positive balance, affinity other than the aura's own.

    Largest balance first. Empty when the character has no own affinity.
    """
    own = own_affinity(sheet)
    if own is None:
        return []
    return list(
        CharacterResonance.objects.filter(character_sheet=sheet, balance__gt=0)
        .exclude(resonance__affinity=own)
        .select_related("resonance__affinity")
        .order_by("-balance")
    )


def _has_conversion(source: Affinity, target: Affinity) -> bool:
    try:
        conversion_pair(source, target)
    except ConversionMappingError:
        return False
    return True


def convertible_drift(sheet: CharacterSheet, target: Resonance) -> list[CharacterResonance]:
    """``drift_holdings`` narrowed to rows with an authored conversion into target's affinity."""
    return [
        row
        for row in drift_holdings(sheet)
        if _has_conversion(row.resonance.affinity, target.affinity)
    ]


_OFFER_OPENED_TEXT = (
    "You carry resonance that does not fit you. Use |wdrift|n to see what you can correct."
)
_OFFER_LAPSED_TEXT = "The chance to correct drift passes with the scene."


def _tell_non_web(character: ObjectDB, text: str) -> None:
    """Send ``text`` to the character's telnet sessions only.

    Web players learn of an offer from the polled pending endpoint, so a bare ``msg``
    would show them the line twice.
    """
    from world.scenes.interaction_services import send_text_to_non_web  # noqa: PLC0415

    send_text_to_non_web(character, text)


def open_or_extend_conversion_offer(grant: ResonanceGrant) -> DriftConversionOffer | None:
    """Open (or extend) the character's conversion offer for the scene a deed grant happened in.

    Returns None, changing nothing, unless all of these hold: the grant is a deed; it grew a
    resonance of the character's own affinity; the configured ``cap_percent`` is above 0;
    the character has convertible drift toward that resonance; and the character stands in
    a live scene. A deed made outside a live scene opens no offer and is not an error.

    The cap toward the granted resonance grows by ``floor(grant.amount x cap_percent / 100)``,
    and the grant is linked to that cap. Only the grant that creates the cap row is floored
    at 1, so a first small deed still opens a usable cap; a later small deed can add 0. A
    cap therefore never exceeds ``cap_percent / 100`` of the deed points linked to it, plus
    that one floored point.

    A NEW offer or a NEW cap row (a new target resonance) tells the character, once the
    surrounding transaction commits (``grant_resonance`` is atomic); bumping an existing cap
    says nothing.
    """
    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

    if grant.source not in DEED_GAIN_SOURCES:
        return None
    sheet = grant.character_sheet
    own = own_affinity(sheet)
    if own is None or grant.resonance.affinity_id != own.pk:
        return None
    percent = get_drift_correction_config().cap_percent
    if percent == 0:
        return None
    # The scene lookup is cached on the room, so a character outside a scene costs no
    # query; the drift query below only runs for someone who could hold an offer.
    scene = get_active_scene(sheet.character.location)
    # The room's cached scene can outlive the scene's end; a finished scene is no scene.
    if scene is None or not scene.is_active or scene.is_finished:
        return None
    if not convertible_drift(sheet, grant.resonance):
        return None
    # A decline or a lapse can delete the offer between get_or_create and the lock; one
    # retry then opens a fresh offer instead of writing a cap onto a vanished row.
    for _attempt in range(2):
        with transaction.atomic():
            offer, offer_created = DriftConversionOffer.objects.get_or_create(
                character_sheet=sheet, scene=scene
            )
            # Lock the offer row so concurrent grants for it serialize. A filter, not
            # get(): the identity map would answer get() without the database or the lock.
            if not list(DriftConversionOffer.objects.select_for_update().filter(pk=offer.pk)):
                continue
            _extend_cap(offer, grant, percent, announce=offer_created)
            return offer
    return None


def _extend_cap(
    offer: DriftConversionOffer, grant: ResonanceGrant, percent: int, *, announce: bool
) -> None:
    """Add ``grant`` to the offer's cap toward its resonance, under the offer's row lock."""
    cap, cap_created = DriftConversionCap.objects.get_or_create(
        offer=offer, target_resonance=grant.resonance, defaults={"cap": 0}
    )
    if cap.grants.filter(pk=grant.pk).exists():
        return
    # Read the stored cap, not the cached one: a rolled-back outer transaction can leave
    # the shared instance holding a cap the table never kept.
    stored = DriftConversionCap.objects.filter(pk=cap.pk).values_list("cap", flat=True).get()
    increment = grant.amount * percent // 100
    if cap_created:
        increment = max(1, increment)
    cap.cap = stored + increment
    cap.save(update_fields=["cap"])
    cap.grants.add(grant)
    if announce or cap_created:
        character = offer.character_sheet.character
        transaction.on_commit(lambda: _tell_non_web(character, _OFFER_OPENED_TEXT))


def lapse_conversion_offers(scene: Scene) -> int:
    """Delete every conversion offer the scene opened (their caps go with them).

    Returns how many offers lapsed.
    """
    offers = DriftConversionOffer.objects.filter(scene=scene)
    characters = [
        offer.character_sheet.character
        for offer in offers.select_related("character_sheet__character")
    ]
    lapsed = offers.count()
    offers.delete()
    for character in characters:
        transaction.on_commit(
            lambda character=character: _tell_non_web(character, _OFFER_LAPSED_TEXT)
        )
    return lapsed


def qualifying_components(
    sheet: CharacterSheet,
    target: Resonance,
    items: Iterable[ItemInstance],
    *,
    min_item_meaning: int | None = None,
) -> list[QualifyingComponent]:
    """The items that count toward a target-resonance offering, each under its first route.

    Three routes, tried in this order: ``MATERIAL`` (the item's template is tied to
    ``target``), ``FACET`` (it carries a live facet that the performer's own motif ties to
    ``target``), and ``KEEPSAKE`` (it means at least ``min_item_meaning`` points to the
    performer; the route is off when that is None). An item qualifies at most once. The list
    is ordered by route (material, facet, keepsake), then as given, so an offering that is
    spent in order burns a plain material before a keepsake. A destroyed or empty item never
    qualifies. One target of ``qualifying_components_by_target``.
    """
    return qualifying_components_by_target(
        sheet, [target], items, min_item_meaning=min_item_meaning
    )[target.pk]


def qualifying_components_by_target(
    sheet: CharacterSheet,
    targets: Iterable[Resonance],
    items: Iterable[ItemInstance],
    *,
    min_item_meaning: int | None = None,
) -> dict[int, list[QualifyingComponent]]:
    """``qualifying_components`` for several targets at once, keyed by resonance pk.

    The query count does not grow with the number of targets: one motif-facet query, one
    item-facet query, and (with a keepsake bar) one meaning reading per carried item, read
    once and shared by every target.
    """
    from world.items.models import ItemFacet  # noqa: PLC0415
    from world.items.services.meaning import item_meaning  # noqa: PLC0415
    from world.worship.invocation_services import get_devotion_config  # noqa: PLC0415

    target_list = list(targets)
    live = [item for item in items if item.destroyed_at is None and item.quantity > 0]
    facets_by_target: dict[int, set[int]] = {target.pk: set() for target in target_list}
    for resonance_id, facet_id in MotifResonanceAssociation.objects.filter(
        motif_resonance__motif__character=sheet,
        motif_resonance__resonance_id__in=list(facets_by_target),
    ).values_list("motif_resonance__resonance_id", "facet_id"):
        facets_by_target[resonance_id].add(facet_id)
    all_facet_ids = set().union(*facets_by_target.values())
    facets_by_item: dict[int, set[int]] = {}
    if all_facet_ids and live:
        for item_id, facet_id in ItemFacet.objects.filter(
            item_instance__in=live, facet_id__in=all_facet_ids, removed_at__isnull=True
        ).values_list("item_instance_id", "facet_id"):
            facets_by_item.setdefault(item_id, set()).add(facet_id)
    keepsake_ids: set[int] = set()
    if min_item_meaning is not None:
        config = get_devotion_config()
        keepsake_ids = {
            item.pk
            for item in live
            if item_meaning(item, sheet, config=config).points >= min_item_meaning
        }

    route_rank = {mode: rank for rank, mode in enumerate(ComponentMode)}
    result: dict[int, list[QualifyingComponent]] = {}
    for target in target_list:
        target_facets = facets_by_target[target.pk]
        qualifying: list[QualifyingComponent] = []
        for item in live:
            if item.template.tied_resonance_id == target.pk:
                mode = ComponentMode.MATERIAL
            elif facets_by_item.get(item.pk, set()) & target_facets:
                mode = ComponentMode.FACET
            elif item.pk in keepsake_ids:
                mode = ComponentMode.KEEPSAKE
            else:
                continue
            qualifying.append(QualifyingComponent(item=item, mode=mode))
        qualifying.sort(key=lambda component: route_rank[component.mode])
        result[target.pk] = qualifying
    return result
