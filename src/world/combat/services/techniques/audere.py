"""Audere offers: crossings, withheld offers, and deletion."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from django.db.models import QuerySet

from actions.errors import ActionDispatchError
from world.combat.constants import ParticipantStatus
from world.combat.models import CombatEncounter

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.magic.audere import PendingAudereOffer
    from world.magic.audere_majora import PendingAudereMajoraOffer


def _end_audere_kind_and_delete_offers(
    condition_id: int | None,
    end_fn: Callable[[ObjectDB], None],
    pending_offer_model: type[PendingAudereOffer | PendingAudereMajoraOffer],
    participant_targets: list[ObjectDB],
) -> None:
    """Revert one Audere-family condition for its holders and clear its pending offers.

    Extracted out of ``cleanup_completed_encounter`` (one call per kind) to keep
    that function's own branching simple -- this is Audere/Audere Majora's own
    per-kind unit of work, including the #4101 fix round 1 withheld-manifestation
    release for the Majora kind specifically. ``condition_id`` is the kind's designated
    template (#4739); when unset nobody holds it, but pending offers are still cleared.
    """
    from world.conditions.models import ConditionInstance  # noqa: PLC0415
    from world.magic.audere_majora import PendingAudereMajoraOffer  # noqa: PLC0415

    target_ids: set[int] = set()
    if condition_id is not None:
        target_ids = set(
            ConditionInstance.objects.filter(
                target__in=participant_targets,
                condition_id=condition_id,
            ).values_list("target_id", flat=True)
        )
    for target in participant_targets:
        if target.pk in target_ids:
            end_fn(target)
    offers = pending_offer_model.objects.filter(character_sheet__character__in=participant_targets)
    if pending_offer_model is PendingAudereMajoraOffer:
        _release_and_delete_withheld_majora_offers(offers)
        offers.filter(manifestation_withheld=False).delete()
    else:
        offers.delete()


def _release_and_delete_withheld_majora_offers(offers: QuerySet[PendingAudereMajoraOffer]) -> None:
    """Lock, release, and delete each withheld-manifestation Majora offer, one row at a time.

    The gate opened with a GM present, promising a Crossing prompt that will now
    never exist (the encounter is ending unresolved) -- the held line must not
    be silently lost (#4101 fix round 1, I1). Goes through
    ``release_and_delete_withheld_offer`` (#4101 fix round 2, should-fix 4) --
    per-row ``select_for_update`` guards against a concurrent accept/decline
    already having consumed the same offer between this sweep's query and its
    own delete. ``offers`` is bounded to this encounter's own participants, so
    a per-row lock+release+delete is cheap. The non-withheld remainder is
    still bulk-deleted by the caller afterward -- only the withheld rows need
    this one-at-a-time treatment.
    """
    from world.magic.audere_majora import release_and_delete_withheld_offer  # noqa: PLC0415

    for offer_id in offers.filter(manifestation_withheld=True).values_list("pk", flat=True):
        release_and_delete_withheld_offer(offer_id)


def _block_if_participant_mid_audere_majora_crossing(encounter: CombatEncounter) -> None:
    """Hard, unconditional block (#1899): a round must never resolve while an
    active participant is mid-Audere-Majora-crossing, regardless of
    ``encounter.is_paused`` — that flag is a separate, softer disconnect-pause
    concern. Extracted to keep ``resolve_round`` under the statement-count lint.
    """
    from world.magic.audere_majora import (  # noqa: PLC0415
        any_character_mid_audere_majora_crossing,
    )

    active_sheets = [
        p.character_sheet
        for p in encounter.participants.filter(status=ParticipantStatus.ACTIVE).select_related(
            "character_sheet"
        )
    ]
    if any_character_mid_audere_majora_crossing(active_sheets):
        raise ActionDispatchError(ActionDispatchError.PARTICIPANT_MID_CROSSING)
