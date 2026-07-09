"""Service for resolving thread crossing offers (generalized, #1990)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction

if TYPE_CHECKING:
    from typeclasses.characters import Character
    from world.magic.models import Thread
    from world.magic.models.crossing import (
        CrossingOption,
        PendingCrossingOffer,
    )


@dataclass(frozen=True)
class CrossingResult:
    """Result of resolving a crossing offer."""

    option_name: str
    crossing_level: int
    target_kind: str


@dataclass(frozen=True)
class CrossingEffectInfo:
    """Examinable info about an active crossing buff."""

    name: str
    description: str
    condition_template_id: int
    target_kind: str
    resonance_name: str
    crossing_level: int


def resolve_crossing_offer(
    offer: PendingCrossingOffer,
    *,
    option: CrossingOption,
) -> CrossingResult:
    """Two-phase resolve: staleness check outside txn; locked grant inside.

    Phase 1 (outside transaction): validate option matches the offer's
    target_kind + resonance + crossing_level. If not -> delete offer + raise
    StaleError.

    Phase 2 (inside transaction.atomic with select_for_update): re-fetch offer,
    create CrossingChoice, delete offer, fire ceremony beat #2
    (achievement/codex if authored on the option), invalidate thread cache.
    """
    from world.magic.crossing.ceremony import (  # noqa: PLC0415
        CeremonyNarrative,
        execute_ceremony_beat,
    )
    from world.magic.exceptions import (  # noqa: PLC0415
        CrossingOfferNotFoundError,
        CrossingOfferStaleError,
    )
    from world.magic.models.crossing import (  # noqa: PLC0415
        CrossingChoice,
        PendingCrossingOffer,
    )

    thread: Thread = offer.thread

    # Phase 1: staleness check
    if (
        option.target_kind != thread.target_kind
        or option.resonance_id != thread.resonance_id
        or option.crossing_level != offer.crossing_level
    ):
        offer.delete()
        raise CrossingOfferStaleError

    with transaction.atomic():
        locked = PendingCrossingOffer.objects.select_for_update().filter(pk=offer.pk).first()
        if locked is None:
            raise CrossingOfferNotFoundError

        CrossingChoice.objects.create(
            thread=thread,
            crossing_level=offer.crossing_level,
            option=option,
        )
        locked.delete()

    # Fire ceremony beat #2 — achievement/codex discovery
    execute_ceremony_beat(
        sheet=thread.owner,
        narrative=CeremonyNarrative(
            personal_body=option.description or f"Your {option.name} takes hold.",
        ),
        achievement=option.discovery_achievement,
        codex_entry=option.codex_entry,
    )

    # Invalidate the thread cache so passive read paths pick up the new choice
    character = thread.owner.character
    if hasattr(character, "threads"):  # noqa: GETATTR_LITERAL
        character.threads.invalidate()

    return CrossingResult(
        option_name=option.name,
        crossing_level=offer.crossing_level,
        target_kind=thread.target_kind,
    )


def active_crossing_effects(character: Character) -> list[CrossingEffectInfo]:
    """Return active crossing buffs for a character, filtered by wear-gating.

    For FACET-kind threads, only includes choices where the character is
    wearing an item with the anchor facet. Other kinds (TRAIT) are always-on.
    """
    from world.magic.constants import TargetKind  # noqa: PLC0415
    from world.magic.models.crossing import CrossingChoice  # noqa: PLC0415

    sheet = character.sheet_data
    choices = list(
        CrossingChoice.objects.filter(thread__owner=sheet).select_related(
            "option",
            "option__condition_template",
            "thread__resonance",
        )
    )

    result: list[CrossingEffectInfo] = []
    for choice in choices:
        thread = choice.thread
        if thread.target_kind == TargetKind.FACET:
            # Wear-gate: only active if wearing an item with the anchor facet
            if not hasattr(character, "equipped_items"):  # noqa: GETATTR_LITERAL
                continue
            matching = character.equipped_items.item_facets_for(thread.target_facet)
            if not matching:
                continue

        if thread.target_kind == TargetKind.SANCTUM:
            # Location-gate: only active if the character is in the sanctum's room
            sanctum = thread.target_sanctum_details
            if sanctum is None:
                continue
            sanctum_room = sanctum.feature_instance.room_profile.objectdb
            if character.location != sanctum_room:
                continue

        result.append(
            CrossingEffectInfo(
                name=choice.option.name,
                description=choice.option.description,
                condition_template_id=choice.option.condition_template_id,
                target_kind=thread.target_kind,
                resonance_name=thread.resonance.name if thread.resonance else "",
                crossing_level=choice.crossing_level,
            )
        )
    return result
