"""Species-gift provisioning (#1580, ADR-0050). Called from CG finalize."""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.conditions.services import (
    apply_condition,
    has_condition,
    remove_condition,
)
from world.game_clock.constants import TimePhase
from world.game_clock.services import get_ic_phase
from world.scenes.round_services import ensure_round_for_acute_condition
from world.species.models import SpeciesGiftGrant

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models.gifts import CharacterGift


def reconcile_sunlight_exposure(character, room) -> None:
    """Apply or remove the Sunlight Exposure condition based on outdoor + day-phase + shelter
    (#1588, #1744).

    A character whose species grant wires a Sunlight-Exposure drawback takes radiant
    DoT while outdoors during a daylight phase; indoors, sheltered (location-shelter
    cascade covers radiant), or at night the condition is removed. When applied, ensures
    a danger scene round (the plummet pattern) so the existing round-tick processes the
    DoT through the peril pipeline — AFK-safety (ADR-0004/ADR-0049) holds unchanged: an
    unconscious victim flows into ``abandonment_environmental``, never a raw death.

    No-op for characters without a sheet or whose species has no sunlight drawback.

    Args:
        character: the ObjectDB character whose exposure to reconcile.
        room: the room the character is in (may be None — treated as indoor).
    """
    from world.species.factories import ensure_sunlight_exposure_content  # noqa: PLC0415

    template = ensure_sunlight_exposure_content()
    sheet = character.character_sheet
    if sheet is None or not _has_sunlight_drawback(sheet):
        return
    outdoor = _room_is_outdoor(room) and not _character_shelters_radiant(character, room)
    phase = get_ic_phase()
    should_expose = outdoor and phase in {
        TimePhase.DAY,
        TimePhase.DAWN,
        TimePhase.DUSK,
    }
    active = has_condition(character, template)
    if should_expose and not active:
        apply_condition(character, template)
        ensure_round_for_acute_condition(sheet)
    elif not should_expose and active:
        remove_condition(character, template)


def _character_shelters_radiant(character, room) -> bool:
    """Whether *character* in *room* is sheltered against radiant damage (#1744, #1756).

    Composes room-level cascade shelter with position-level shelter (a tent,
    table, or alcove the character occupies).
    """
    if room is None:
        return False
    from world.conditions.factories import ensure_radiant_damage_type  # noqa: PLC0415
    from world.locations.services import hazard_is_covered_for  # noqa: PLC0415

    return hazard_is_covered_for(character, room, ensure_radiant_damage_type())


def _has_sunlight_drawback(sheet) -> bool:
    """Whether the sheet's species (or an ancestor) grants a Sunlight-Exposure drawback."""
    from world.species.factories import SUNLIGHT_EXPOSURE_NAME  # noqa: PLC0415

    if sheet.species_id is None:
        return False
    species_pks = [s.pk for s in _species_and_ancestors(sheet.species)]
    return SpeciesGiftGrant.objects.filter(
        species_id__in=species_pks,
        drawback_condition__name=SUNLIGHT_EXPOSURE_NAME,
    ).exists()


def _room_is_outdoor(room) -> bool:
    """Whether the room is outdoors. Missing RoomProfile -> treated as indoor (safe default)."""
    if room is None:
        return False
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    try:
        return room.room_profile.is_outdoor
    except ObjectDoesNotExist:
        return False
    except AttributeError:
        return False


def _species_and_ancestors(species):
    """Return [species, parent, grandparent, ...] walking the parent chain.

    Assumes an acyclic parent chain (data-hygiene invariant); the while is bounded.
    """
    chain, node = [], species
    while node is not None:
        chain.append(node)
        node = node.parent
    return chain


def _apply_permanent_condition_once(character, condition) -> None:
    """Apply *condition* to *character* once, idempotently (drawback/benefit conditions)."""
    from world.conditions.models import ConditionInstance  # noqa: PLC0415
    from world.conditions.services import apply_condition  # noqa: PLC0415

    already_applied = ConditionInstance.objects.filter(
        target=character,
        condition=condition,
        resolved_at__isnull=True,
    ).exists()
    if not already_applied:
        apply_condition(character, condition)


def provision_species_gifts(sheet: CharacterSheet, *, resonance=None) -> list[CharacterGift]:
    """Mint the species' Minor Gift(s) + latent GIFT thread + any drawback. Idempotent.

    ``resonance`` is the player's CG-chosen gift resonance (the same value the Major-gift
    block resolves). When None, falls back to each gift's first supported resonance.

    Called from finalize_magic_data after the Major-gift cantrip block so the species
    gift thread anchors to the same resonance as the player's Major-gift thread.
    """
    from world.magic.specialization.services import grant_gift_to_character  # noqa: PLC0415

    if sheet.species_id is None:
        return []

    species_pks = [s.pk for s in _species_and_ancestors(sheet.species)]
    grants = SpeciesGiftGrant.objects.filter(species_id__in=species_pks).select_related(
        "gift", "drawback_condition", "benefit_condition"
    )
    minted: list[CharacterGift] = []
    for grant in grants:
        res = resonance or grant.gift.resonances.first()
        cg, _ = grant_gift_to_character(sheet, grant.gift, resonance=res)
        minted.append(cg)
        if grant.drawback_condition_id is not None:
            _apply_permanent_condition_once(sheet.character, grant.drawback_condition)
        if grant.benefit_condition_id is not None:
            _apply_permanent_condition_once(sheet.character, grant.benefit_condition)
    return minted
