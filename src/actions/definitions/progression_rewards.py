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
                success=False, message="Could not determine author for the specified target."
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


@dataclass
class ClaimRandomSceneAction(Action):
    """Claim a weekly random-scene target, awarding XP. Wraps ``claim_random_scene``."""

    key: str = "claim_random_scene"
    name: str = "Claim Random Scene"
    icon: str = "dice"
    category: str = "progression"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.progression.services.random_scene import claim_random_scene  # noqa: PLC0415
        from world.progression.types import ProgressionError  # noqa: PLC0415

        account = _resolve_account(actor)
        if account is None:
            return ActionResult(success=False, message=_NO_ACCOUNT)
        try:
            target = claim_random_scene(account=account, target_id=int(kwargs["target_id"]))
        except ProgressionError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True, message=f"Claimed random scene with {target.target_persona.name}."
        )


@dataclass
class RerollRandomSceneAction(Action):
    """Reroll a random-scene target slot (one per week). Wraps ``reroll_random_scene_target``."""

    key: str = "reroll_random_scene"
    name: str = "Reroll Random Scene"
    icon: str = "rotate"
    category: str = "progression"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415
        from world.progression.models import RandomSceneTarget  # noqa: PLC0415
        from world.progression.services.random_scene import (  # noqa: PLC0415
            reroll_random_scene_target,
        )
        from world.progression.types import ProgressionError  # noqa: PLC0415

        account = _resolve_account(actor)
        if account is None:
            return ActionResult(success=False, message=_NO_ACCOUNT)
        game_week = get_current_game_week()
        target = RandomSceneTarget.objects.filter(
            pk=kwargs.get("target_id"), account=account, game_week=game_week
        ).first()
        if target is None:
            return ActionResult(success=False, message=ProgressionError.RS_NOT_FOUND)
        try:
            updated = reroll_random_scene_target(
                account=account, slot_number=target.slot_number, game_week=game_week
            )
        except ProgressionError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message=f"Rerolled to {updated.target_persona.name}.")


@dataclass
class SetPathIntentAction(Action):
    """Declare the character's intended next path. Wraps ``set_path_intent``."""

    key: str = "set_path_intent"
    name: str = "Declare Path Intent"
    icon: str = "compass"
    category: str = "progression"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.classes.models import Path  # noqa: PLC0415
        from world.progression.services.path_intent import set_path_intent  # noqa: PLC0415

        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return ActionResult(success=False, message="No active character.")
        path = Path.objects.filter(pk=kwargs.get("path_id"), is_active=True).first()
        if path is None:
            return ActionResult(success=False, message="That is not a valid path.")
        set_path_intent(sheet, path)
        return ActionResult(success=True, message=f"You intend to walk the path of {path.name}.")


@dataclass
class ClearPathIntentAction(Action):
    """Clear the character's declared path intent. Wraps ``clear_path_intent``."""

    key: str = "clear_path_intent"
    name: str = "Clear Path Intent"
    icon: str = "compass"
    category: str = "progression"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.progression.services.path_intent import clear_path_intent  # noqa: PLC0415

        try:
            sheet = actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return ActionResult(success=False, message="No active character.")
        clear_path_intent(sheet)
        return ActionResult(success=True, message="Path intent cleared.")


@dataclass
class SelectPathAction(Action):
    """Late-selection recovery: pick a Path when CG never set one (#2121).

    For characters created via a CG-bypassing path (GM-finalize quickstart,
    NPCAsset -> PC promotion) with no ``CharacterPathHistory`` row at all —
    see ``select_initial_path``. Gated on
    ``current_path_for_character(actor) is None``; a character with a path
    already on record must use path advancement/crossing instead, not this
    recovery surface. Only the 5 CG-selectable PROSPECT paths are offered —
    this mirrors the initial CG choice, not a jump to an advanced stage.
    """

    key: str = "select_path"
    name: str = "Select Path"
    icon: str = "compass"
    category: str = "progression"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.classes.models import Path, PathStage  # noqa: PLC0415
        from world.progression.exceptions import PathAlreadySelectedError  # noqa: PLC0415
        from world.progression.services.advancement import select_initial_path  # noqa: PLC0415

        if getattr(actor, "sheet_data", None) is None:  # noqa: GETATTR_LITERAL
            return ActionResult(success=False, message="No active character.")
        path = Path.objects.filter(
            pk=kwargs.get("path_id"), is_active=True, stage=PathStage.PROSPECT
        ).first()
        if path is None:
            return ActionResult(success=False, message="That is not a valid starting path.")
        try:
            select_initial_path(actor, path)
        except PathAlreadySelectedError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message=f"You have chosen to walk {path.name}.")
