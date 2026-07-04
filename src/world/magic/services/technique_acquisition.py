"""Non-teaching technique acquisition service (#1732).

learn_technique is the shared commit seam: it runs the path gate,
gift-owned check, cap check, AP/XP spend, mints CharacterTechnique,
and announces. Called by item on-use and ritual SERVICE dispatch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.achievements.constants import AccessChangeSource
from world.achievements.discovery import announce_access_change
from world.action_points.models import ActionPointPool
from world.magic.exceptions import (
    GiftNotOwned,
    TechniqueCapExceeded,
    TechniqueStyleForbidden,
)
from world.magic.services.gift_acquisition import (
    can_learn_technique,
    count_techniques_for_gift,
    get_technique_cap_for_gift,
)

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import CharacterTechnique, Technique


@transaction.atomic
def learn_technique(  # noqa: PLR0913
    learner: CharacterSheet,
    technique: Technique,
    *,
    source: AccessChangeSource,
    ap_cost: int = 0,
    xp_cost: int = 0,
    location: object | None = None,
) -> CharacterTechnique:
    """Learn a technique from an owned gift (non-teaching path).

    Runs: gift-owned check -> path gate -> cap check -> AP/XP spend ->
    mint -> announce. Never implicitly acquires the gift — that is the
    teaching path's job.

    Args:
        learner: The character learning the technique.
        technique: The technique to learn.
        source: The AccessChangeSource for the announce message.
        ap_cost: AP to spend (0 = free).
        xp_cost: XP to spend (0 = free; not yet implemented — deferred).
        location: Optional room object the learner is in. When provided,
            an active Training Room feature in that room discounts the AP
            cost (#675).

    Returns:
        The new CharacterTechnique.

    Raises:
        GiftNotOwned: Learner doesn't own the technique's gift.
        TechniqueStyleForbidden: Learner's path doesn't permit the style.
        TechniqueCapExceeded: At the cap for this gift at current thread level.
        ValueError: Learner already knows this technique.
    """
    from world.magic.models import CharacterGift, CharacterTechnique  # noqa: PLC0415

    # 1. Gift-owned precondition.
    if not CharacterGift.objects.filter(character=learner, gift=technique.gift).exists():
        raise GiftNotOwned

    # 2. Path-style gate.
    if not can_learn_technique(learner, technique):
        raise TechniqueStyleForbidden

    # 3. Duplicate check.
    if CharacterTechnique.objects.filter(character=learner, technique=technique).exists():
        msg = f"{learner} already knows {technique.name}."
        raise ValueError(msg)

    # 4. Cap check.
    current_count = count_techniques_for_gift(learner, technique.gift)
    cap = get_technique_cap_for_gift(learner, technique.gift)
    if current_count >= cap:
        raise TechniqueCapExceeded

    # 5. AP spend.
    if ap_cost > 0:
        from world.magic.exceptions import MagicError  # noqa: PLC0415

        effective_ap_cost = ap_cost
        if location is not None:
            from evennia_extensions.models import RoomProfile  # noqa: PLC0415
            from world.room_features.constants import (  # noqa: PLC0415
                TRAINING_ROOM_AP_DISCOUNT_PER_LEVEL,
            )
            from world.room_features.services import (  # noqa: PLC0415
                active_training_room_in,
            )

            room_profile = RoomProfile.objects.filter(objectdb=location).first()
            if room_profile is not None:
                training_room = active_training_room_in(room_profile)
                if training_room is not None:
                    effective_ap_cost = max(
                        0,
                        ap_cost - training_room.level * TRAINING_ROOM_AP_DISCOUNT_PER_LEVEL,
                    )

        pool = ActionPointPool.get_or_create_for_character(learner.character)
        if not pool.can_afford(effective_ap_cost):
            msg = f"Insufficient action points (need {effective_ap_cost}, have {pool.current})."
            raise MagicError(msg)
        pool.spend(effective_ap_cost)

    # TODO(#1732-deferred): XP spend when xp_cost > 0 — needs XPTransaction wiring.
    _ = xp_cost

    # 6. Mint.
    ct = CharacterTechnique.objects.create(character=learner, technique=technique)

    # 7. Announce.
    announce_access_change(
        learner,
        gained=[technique],
        lost=[],
        source=source,
    )

    return ct


def learn_technique_from_ritual(*, character_sheet, ritual, **_kwargs):
    """SERVICE-dispatch adapter: learn a technique via a ritual TechniqueGrant.

    Called by PerformRitualAction._dispatch_service when a ritual with
    execution_kind=SERVICE has service_function_path pointing here. The
    Ritual instance is forwarded by the dispatch (contract fix in Task 6).

    Args:
        character_sheet: The CharacterSheet of the ritual performer.
        ritual: The Ritual being performed (forwarded by _dispatch_service).

    Returns:
        The new CharacterTechnique.
    """
    from world.magic.models import TechniqueGrant  # noqa: PLC0415

    grant = TechniqueGrant.objects.select_related("technique").get(ritual=ritual)
    return learn_technique(
        character_sheet,
        grant.technique,
        source=AccessChangeSource.TECHNIQUE_GRANT,
        ap_cost=grant.acquisition_ap_cost,
        xp_cost=grant.acquisition_xp_cost,
        location=character_sheet.character.location,
    )
