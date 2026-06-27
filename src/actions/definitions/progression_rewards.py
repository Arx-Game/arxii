"""Progression-reward actions (#1348).

Thin ``action.run()`` wrappers around the existing progression service
functions, so telnet ``Cmd*`` commands and the web views converge on one seam
(ADR-0001). Account-level actions resolve the acting account from the actor via
``get_account_for_character``; character-level actions use ``actor.sheet_data``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext

_NO_ACCOUNT = "You have no active character on the roster."


def _resolve_account(actor: ObjectDB) -> AccountDB | None:
    from world.roster.selectors import get_account_for_character  # noqa: PLC0415

    return get_account_for_character(actor)


@dataclass
class ClaimKudosAction(Action):
    """Claim kudos and convert to account XP. Wraps ``claim_kudos_for_xp``."""

    key: str = "claim_kudos"
    name: str = "Claim Kudos"
    icon: str = "gift"
    category: str = "progression"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.progression.models import KudosClaimCategory  # noqa: PLC0415
        from world.progression.services.kudos import (  # noqa: PLC0415
            InsufficientKudosError,
            claim_kudos_for_xp,
        )

        account = _resolve_account(actor)
        if account is None:
            return ActionResult(success=False, message=_NO_ACCOUNT)
        category = KudosClaimCategory.objects.filter(
            pk=kwargs.get("claim_category_id"), is_active=True
        ).first()
        if category is None:
            return ActionResult(success=False, message="Invalid or inactive claim category.")
        try:
            result = claim_kudos_for_xp(
                account=account, amount=int(kwargs["amount"]), claim_category=category
            )
        except InsufficientKudosError:
            return ActionResult(success=False, message="Insufficient kudos for this conversion.")
        except (ValueError, TypeError):
            return ActionResult(success=False, message="Invalid amount for this conversion rate.")
        return ActionResult(
            success=True,
            message=f"Claimed {kwargs['amount']} kudos for {result.xp_awarded} XP.",
        )


@dataclass
class CastVoteAction(Action):
    """Cast a weekly vote on another player's content. Wraps ``cast_vote``."""

    key: str = "cast_vote"
    name: str = "Cast Vote"
    icon: str = "thumbs-up"
    category: str = "progression"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.progression.services.voting import (  # noqa: PLC0415
            cast_vote,
            get_author_account_for_target,
        )
        from world.progression.types import ProgressionError  # noqa: PLC0415

        account = _resolve_account(actor)
        if account is None:
            return ActionResult(success=False, message=_NO_ACCOUNT)
        target_type = kwargs["target_type"]
        target_id = int(kwargs["target_id"])
        author = get_author_account_for_target(target_type, target_id)
        if author is None:
            return ActionResult(
                success=False, message="Could not determine the author of that content."
            )
        try:
            cast_vote(
                voter_account=account,
                target_type=target_type,
                target_id=target_id,
                author_account=author,
            )
        except ProgressionError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message="Vote cast.")


@dataclass
class RemoveVoteAction(Action):
    """Remove an unprocessed weekly vote. Wraps ``remove_vote``."""

    key: str = "remove_vote"
    name: str = "Remove Vote"
    icon: str = "thumbs-down"
    category: str = "progression"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.progression.services.voting import remove_vote  # noqa: PLC0415
        from world.progression.types import ProgressionError  # noqa: PLC0415

        account = _resolve_account(actor)
        if account is None:
            return ActionResult(success=False, message=_NO_ACCOUNT)
        try:
            remove_vote(
                voter_account=account,
                target_type=kwargs["target_type"],
                target_id=int(kwargs["target_id"]),
            )
        except ProgressionError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message="Vote removed.")
