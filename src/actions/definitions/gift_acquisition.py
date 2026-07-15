"""Gift/technique/thread-weaving acquisition Actions — the action.run() seam (#2116).

Three thin REGISTRY Actions wrapping the existing, already-tested acquisition
services (`world.magic.services.gift_acquisition`, `world.magic.services.threads`)
that had zero non-test callers before this issue. Mirrors the `sanctum.py` shape:
each Action resolves its own kwargs, delegates to the service, and translates the
service's typed exceptions into a failure ``ActionResult`` — no business logic here.
Shared by telnet `CmdLearn` (`commands/gift_learning.py`) and the web magic endpoints.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType
from world.magic.exceptions import MagicError, ProtagonismLockedError
from world.magic.types.alterations import AlterationGateError

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext

_MSG_NO_CHARACTER_SHEET = "You have no character sheet."

# Exceptions the gift/technique/thread-weaving acquisition services raise:
# MagicError covers XPInsufficient / GiftUnlockMissing / TechniqueCapExceeded /
# TechniqueStyleForbidden / WeavingUnlockMissing (all subclass it);
# AlterationGateError is the Mage Scar advancement gate; ProtagonismLockedError
# is the protagonism-lock gate (enforce_advancement_gate checks it first);
# ValueError is raised for "already knows this technique".
_ACQUISITION_EXC = (MagicError, AlterationGateError, ProtagonismLockedError, ValueError)

# The three typed members carry a safe user_message; bare ValueError (the
# "already knows this technique" path) has only its str(). Explicit dispatch —
# getattr-with-default here would silently swallow a genuine attribute bug.
_USER_MESSAGE_EXC = (MagicError, AlterationGateError, ProtagonismLockedError)


def _acquisition_error_message(exc: Exception) -> str:
    if isinstance(exc, _USER_MESSAGE_EXC):
        return exc.user_message
    return str(exc)


def _actor_sheet(actor: ObjectDB) -> Any:  # noqa: OBJECTDB_PARAM
    """Return actor.sheet_data, or None when the actor has no CharacterSheet."""
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    try:
        return actor.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return None


@dataclass
class PurchaseGiftUnlockAction(Action):
    """Spend XP to purchase a GiftUnlock receipt — the XP gate (ADR-0053).

    Does not acquire the gift; acceptance of a TechniqueTeachingOffer
    (``AcceptTechniqueOfferAction``) is the separate acquisition step.
    """

    key: str = "purchase_gift_unlock"
    name: str = "Purchase Gift Unlock"
    icon: str = "lock-open"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF
    ap_cost: int = 0

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.magic.models import GiftUnlock  # noqa: PLC0415
        from world.magic.services.gift_acquisition import spend_xp_on_gift_unlock  # noqa: PLC0415
        from world.roster.models import RosterTenure  # noqa: PLC0415

        sheet = _actor_sheet(actor)
        if sheet is None:
            return ActionResult(success=False, message=_MSG_NO_CHARACTER_SHEET)

        gift_unlock_id = kwargs.get("gift_unlock_id")
        if gift_unlock_id is None:
            return ActionResult(success=False, message="gift_unlock_id is required.")

        teacher = None
        teacher_tenure_id = kwargs.get("teacher_tenure_id")
        if teacher_tenure_id is not None:
            try:
                teacher = RosterTenure.objects.get(pk=teacher_tenure_id)
            except RosterTenure.DoesNotExist:
                return ActionResult(success=False, message="Unknown teacher_tenure_id.")

        try:
            unlock = GiftUnlock.objects.get(pk=gift_unlock_id)
        except GiftUnlock.DoesNotExist:
            return ActionResult(success=False, message="Unknown gift_unlock_id.")

        try:
            receipt = spend_xp_on_gift_unlock(sheet, unlock, teacher=teacher)
        except _ACQUISITION_EXC as exc:
            return ActionResult(success=False, message=_acquisition_error_message(exc))

        return ActionResult(
            success=True,
            message=f"Unlocked {unlock.gift.name} for {receipt.xp_spent} XP.",
            data={"gift_unlock_id": unlock.pk, "receipt_id": receipt.pk},
        )


@dataclass
class AcceptTechniqueOfferAction(Action):
    """Accept a TechniqueTeachingOffer — the acquisition step (#1587, #2116).

    Implicitly acquires the technique's gift on the first technique learned
    from it (requires the ``CharacterGiftUnlock`` receipt purchased via
    ``PurchaseGiftUnlockAction``).
    """

    key: str = "accept_technique_offer"
    name: str = "Accept Technique Offer"
    icon: str = "graduation-cap"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF
    ap_cost: int = 0

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.magic.models import TechniqueTeachingOffer  # noqa: PLC0415
        from world.magic.services.gift_acquisition import (  # noqa: PLC0415
            accept_technique_offer as accept_technique_offer_service,
        )

        sheet = _actor_sheet(actor)
        if sheet is None:
            return ActionResult(success=False, message=_MSG_NO_CHARACTER_SHEET)

        offer_id = kwargs.get("offer_id")
        if offer_id is None:
            return ActionResult(success=False, message="offer_id is required.")

        try:
            offer = TechniqueTeachingOffer.objects.select_related("technique__gift").get(
                pk=offer_id
            )
        except TechniqueTeachingOffer.DoesNotExist:
            return ActionResult(success=False, message="Unknown offer_id.")

        try:
            character_technique = accept_technique_offer_service(sheet, offer)
        except _ACQUISITION_EXC as exc:
            return ActionResult(success=False, message=_acquisition_error_message(exc))

        return ActionResult(
            success=True,
            message=f"You learn {offer.technique.name}.",
            data={
                "offer_id": offer.pk,
                "character_technique_id": character_technique.pk,
                "technique_id": offer.technique_id,
            },
        )


@dataclass
class AcceptThreadWeavingOfferAction(Action):
    """Accept a ThreadWeavingTeachingOffer — telnet parity with the web (#2116).

    Wraps the existing ``accept_thread_weaving_unlock`` service, the same seam
    the web ``AcceptTeachingOfferSerializer`` now dispatches through.
    """

    key: str = "accept_thread_weaving_offer"
    name: str = "Accept Thread-Weaving Offer"
    icon: str = "graduation-cap"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF
    ap_cost: int = 0

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.magic.models import ThreadWeavingTeachingOffer  # noqa: PLC0415
        from world.magic.services.threads import accept_thread_weaving_unlock  # noqa: PLC0415

        sheet = _actor_sheet(actor)
        if sheet is None:
            return ActionResult(success=False, message=_MSG_NO_CHARACTER_SHEET)

        offer_id = kwargs.get("offer_id")
        if offer_id is None:
            return ActionResult(success=False, message="offer_id is required.")

        try:
            offer = ThreadWeavingTeachingOffer.objects.select_related("unlock").get(pk=offer_id)
        except ThreadWeavingTeachingOffer.DoesNotExist:
            return ActionResult(success=False, message="Unknown offer_id.")

        try:
            purchase = accept_thread_weaving_unlock(sheet, offer)
        except _ACQUISITION_EXC as exc:
            return ActionResult(success=False, message=_acquisition_error_message(exc))

        return ActionResult(
            success=True,
            message=f"Learned to weave {offer.unlock} for {purchase.xp_spent} XP.",
            data={"offer_id": offer.pk, "purchase_id": purchase.pk},
        )
