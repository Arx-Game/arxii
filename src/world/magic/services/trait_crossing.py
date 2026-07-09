"""Service for resolving TRAIT thread crossing offers (#1989)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction

if TYPE_CHECKING:
    from world.magic.models import Thread
    from world.magic.models.trait_crossing import (
        PendingTraitCrossingOffer,
        TraitCrossingOption,
    )


@dataclass(frozen=True)
class TraitCrossingResult:
    """Result of resolving a trait crossing offer."""

    option_name: str
    effect_kind: str
    crossing_level: int


def resolve_trait_crossing_offer(
    offer: PendingTraitCrossingOffer,
    *,
    option: TraitCrossingOption,
) -> TraitCrossingResult:
    """Two-phase resolve: staleness check outside txn; locked grant inside.

    Phase 1 (outside transaction): validate option belongs to the offer's
    resonance + crossing_level. If not -> delete offer + raise StaleError.

    Phase 2 (inside transaction.atomic with select_for_update): re-fetch offer,
    create TraitCrossingChoice, delete offer, fire ceremony beat #2
    (achievement/codex if authored on the option), invalidate thread cache.
    """
    from world.magic.crossing.ceremony import (  # noqa: PLC0415
        CeremonyNarrative,
        execute_ceremony_beat,
    )
    from world.magic.exceptions import (  # noqa: PLC0415
        TraitCrossingOfferNotFoundError,
        TraitCrossingOfferStaleError,
    )
    from world.magic.models.trait_crossing import (  # noqa: PLC0415
        PendingTraitCrossingOffer,
        TraitCrossingChoice,
    )

    thread: Thread = offer.thread

    # Phase 1: staleness check
    if option.resonance_id != thread.resonance_id or option.crossing_level != offer.crossing_level:
        offer.delete()
        raise TraitCrossingOfferStaleError

    with transaction.atomic():
        locked = PendingTraitCrossingOffer.objects.select_for_update().filter(pk=offer.pk).first()
        if locked is None:
            raise TraitCrossingOfferNotFoundError

        TraitCrossingChoice.objects.create(
            thread=thread,
            crossing_level=offer.crossing_level,
            option=option,
        )
        locked.delete()

    # Fire ceremony beat #2 — achievement/codex discovery
    execute_ceremony_beat(
        sheet=thread.owner,
        narrative=CeremonyNarrative(
            personal_body=option.narrative_snippet or f"Your {option.name} takes hold.",
        ),
        achievement=option.discovery_achievement,
        codex_entry=option.codex_entry,
    )

    # Invalidate the thread cache so passive read paths pick up the new choice
    character = thread.owner.character
    if hasattr(character, "threads"):  # noqa: GETATTR_LITERAL
        character.threads.invalidate()

    return TraitCrossingResult(
        option_name=option.name,
        effect_kind=option.effect_kind,
        crossing_level=offer.crossing_level,
    )
