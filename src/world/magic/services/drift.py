"""Drift holdings and the conversion offer a deed opens (#4733, slice 4 of #4672).

Drift is resonance a character holds that sits off their own aura: any
``CharacterResonance`` with a positive balance whose affinity differs from the aura's
dominant affinity. There is no threshold. A deed (a grant from a ``DEED_GAIN_SOURCES``
source) that grows a resonance of the character's own affinity, made in a live scene by a
character who has convertible drift, opens a ``DriftConversionOffer`` for that scene and
adds to the cap of converting drift toward the resonance the deed grew. The offer lapses
when the scene finishes.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from django.db import transaction

from world.magic.constants import DEED_GAIN_SOURCES, ComponentMode
from world.magic.exceptions import ConversionMappingError
from world.magic.models.aura import CharacterResonance
from world.magic.models.drift import (
    DriftConversionCap,
    DriftConversionOffer,
    DriftCorrectionConfig,
)
from world.magic.models.motifs import MotifResonanceAssociation
from world.magic.services.conversion import conversion_pair
from world.magic.types.drift import QualifyingComponent

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance
    from world.magic.models.affinity import Affinity, Resonance
    from world.magic.models.gain import ResonanceGrant
    from world.scenes.models import Scene


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
    qualifies.
    """
    from world.items.models import ItemFacet  # noqa: PLC0415
    from world.items.services.meaning import item_meaning  # noqa: PLC0415
    from world.worship.invocation_services import get_devotion_config  # noqa: PLC0415

    live = [item for item in items if item.destroyed_at is None and item.quantity > 0]
    motif_facet_ids = set(
        MotifResonanceAssociation.objects.filter(
            motif_resonance__motif__character=sheet, motif_resonance__resonance=target
        ).values_list("facet_id", flat=True)
    )
    faceted_item_ids = (
        set(
            ItemFacet.objects.filter(
                item_instance__in=live, facet_id__in=motif_facet_ids, removed_at__isnull=True
            ).values_list("item_instance_id", flat=True)
        )
        if motif_facet_ids
        else set()
    )
    config = get_devotion_config() if min_item_meaning is not None else None

    qualifying: list[QualifyingComponent] = []
    for item in live:
        if item.template.tied_resonance_id == target.pk:
            mode = ComponentMode.MATERIAL
        elif item.pk in faceted_item_ids:
            mode = ComponentMode.FACET
        elif (
            config is not None
            and min_item_meaning is not None
            and item_meaning(item, sheet, config=config).points >= min_item_meaning
        ):
            mode = ComponentMode.KEEPSAKE
        else:
            continue
        qualifying.append(QualifyingComponent(item=item, mode=mode))
    route_rank = {mode: rank for rank, mode in enumerate(ComponentMode)}
    qualifying.sort(key=lambda component: route_rank[component.mode])
    return qualifying
