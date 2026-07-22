"""Distinction-specific actions: GM award / rank-up (#2037)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.constants import ActionCategory
from actions.prerequisites import MinimumGMLevelPrerequisite, Prerequisite
from actions.types import ActionContext, ActionResult, TargetType
from world.gm.constants import GMLevel


def _coerce_positive_int(value: Any) -> int | None:
    """Return ``value`` as a positive int, or ``None`` if it isn't one.

    Fails loud (returns None -> caller refuses) rather than silently coercing a
    non-positive/garbage rank to something valid.
    """
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return None
    return coerced if coerced > 0 else None


def _coerce_nonneg_int(value: Any) -> int | None:
    """Return ``value`` as a non-negative int, or ``None`` if it isn't one.

    Zero is legitimate for ``xp_cost`` — story-reason changes are free (#2631) —
    so the xp_cost override uses this instead of ``_coerce_positive_int``.
    """
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return None
    return coerced if coerced >= 0 else None


@dataclass
class GMAwardDistinctionAction(Action):
    """JUNIOR-tier GM action: award or rank up a catalog Distinction (#2037 Decision 4).

    Ad-hoc narrative distinction grant -- for story-earned moments (or a staff
    manual-audit correction, folded into this same action per the spec's
    Decision 1b) where a GM hand-awards or ranks up a Distinction. Mirrors
    ``GrantItemAction`` (``actions/definitions/items.py``) field-for-field: same
    JUNIOR-tier gate, same target-search convention, same catalog-only lookup
    (never freehand). Wraps ``world.distinctions.services.grant_distinction`` --
    the single shared acquisition seam every in-play Distinction source calls.

    Dispatch convention
    -------------------
    REGISTRY ActionRef: ``registry_key="gm_award_distinction"``, ``target_name=<str>``,
    ``distinction_slug=<str>``, optional ``rank=<int>``. Resolution (target search +
    catalog lookup) happens in ``execute()``.

    Gated on ``MinimumGMLevelPrerequisite(GMLevel.JUNIOR)`` (staff bypass
    preserved). No per-scene cap -- a Distinction grant is a rarer, heavier
    action already gated on GM trust level, not a per-scene currency tap.

    Rank validation (#2037 Task 2 review fold-in): an explicit ``rank`` below 1
    or above the resolved distinction's ``max_rank`` is rejected outright (never
    silently clamped), naming ``max_rank`` in the failure message -- the same
    "fail loud rather than silently clamp" bar ``GMApplyConditionAction`` already
    holds for severity/duration overrides.
    """

    key: str = "gm_award_distinction"
    name: str = "Award Distinction"
    icon: str = "medal"
    category: str = "gm"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [MinimumGMLevelPrerequisite(GMLevel.JUNIOR)]

    def execute(  # noqa: PLR0911
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.distinctions.exceptions import DistinctionExclusionError  # noqa: PLC0415
        from world.distinctions.models import Distinction  # noqa: PLC0415
        from world.distinctions.services import grant_distinction  # noqa: PLC0415
        from world.distinctions.types import DistinctionOrigin  # noqa: PLC0415

        target_name = (kwargs.get("target_name") or "").strip()
        distinction_slug = (kwargs.get("distinction_slug") or "").strip()
        if not target_name or not distinction_slug:
            return ActionResult(
                success=False,
                message="Usage: gm_award_distinction <character>=<distinction slug>[,rank]",
            )

        rank: int | None = None
        rank_raw = kwargs.get("rank")
        if rank_raw is not None:
            rank = _coerce_positive_int(rank_raw)
            if rank is None:
                return ActionResult(success=False, message="rank must be a positive whole number.")

        target = actor.search(target_name, global_search=True)
        if target is None:
            # search() already messaged the actor with a not-found/ambiguous notice.
            return ActionResult(success=False)

        sheet = target.character_sheet
        if sheet is None:
            return ActionResult(success=False, message="That is not a character.")

        distinction = Distinction.objects.filter(
            slug__iexact=distinction_slug, is_active=True
        ).first()
        if distinction is None:
            return ActionResult(
                success=False,
                message=f"No active distinction found with slug '{distinction_slug}'.",
            )

        if rank is not None and rank > distinction.max_rank:
            return ActionResult(
                success=False,
                message=f"{distinction.name} has a maximum rank of {distinction.max_rank}.",
            )

        try:
            char_distinction = grant_distinction(
                sheet,
                distinction,
                origin=DistinctionOrigin.GM_AWARD,
                rank=rank,
                source_description=f"Awarded by {actor.key}.",
            )
        except DistinctionExclusionError as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=(
                f"Awarded '{distinction.name}' (rank {char_distinction.rank}) to {target.key}."
            ),
        )


@dataclass
class AuthorizeDistinctionChangeAction(Action):
    """GM action: authorize a distinction add or removal for a character.

    Creates a ``DistinctionChangeAuthorization`` row. The player then spends
    XP via ``AcceptDistinctionChangeAction`` to complete the change.

    Gated on ``MinimumGMLevelPrerequisite(GMLevel.JUNIOR)``.

    Dispatch convention
    -------------------
    REGISTRY ActionRef: ``registry_key="authorize_distinction_change"``,
    ``target_name=<str>``, ``action=<"add"|"remove">``,
    ``distinction_slug=<str>`` (for add) or
    ``character_distinction_id=<int>`` (for remove),
    optional ``xp_cost=<int>`` (defaults to computed cost),
    ``reason=<str>``.
    """

    key: str = "authorize_distinction_change"
    name: str = "Authorize Distinction Change"
    icon: str = "scroll"
    category: str = "gm"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [MinimumGMLevelPrerequisite(GMLevel.JUNIOR)]

    def execute(  # noqa: PLR0911, PLR0912, C901
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.distinctions.models import (  # noqa: PLC0415
            CharacterDistinction,
            Distinction,
        )
        from world.distinctions.services import (  # noqa: PLC0415
            create_distinction_change_authorization,
        )
        from world.distinctions.types import DistinctionChangeAction  # noqa: PLC0415

        target_name = (kwargs.get("target_name") or "").strip()
        action_str = (kwargs.get("action") or "").strip().lower()
        reason = (kwargs.get("reason") or "").strip()

        if not target_name or not action_str or not reason:
            usage = (
                "Usage: authorize_distinction_change <character>,action=<add|remove>,reason=<text>"
            )
            return ActionResult(success=False, message=usage)

        if action_str not in (DistinctionChangeAction.ADD, DistinctionChangeAction.REMOVE):
            return ActionResult(success=False, message="action must be 'add' or 'remove'.")

        target = actor.search(target_name, global_search=True)
        if target is None:
            return ActionResult(success=False)

        sheet = target.character_sheet
        if sheet is None:
            return ActionResult(success=False, message="That is not a character.")

        if action_str == DistinctionChangeAction.ADD:
            distinction_slug = (kwargs.get("distinction_slug") or "").strip()
            if not distinction_slug:
                return ActionResult(
                    success=False, message="distinction_slug required for add action."
                )

            distinction = Distinction.objects.filter(
                slug__iexact=distinction_slug, is_active=True
            ).first()
            if distinction is None:
                return ActionResult(
                    success=False,
                    message=f"No active distinction found with slug '{distinction_slug}'.",
                )

            existing = CharacterDistinction.objects.filter(
                character=sheet, distinction=distinction
            ).first()
            current_rank = existing.rank if existing else 0

            rank = kwargs.get("rank")
            rank_int = _coerce_positive_int(rank) if rank else current_rank + 1
            if rank_int is None:
                return ActionResult(success=False, message="rank must be a positive whole number.")

            if rank_int > distinction.max_rank:
                return ActionResult(
                    success=False,
                    message=f"{distinction.name} has a maximum rank of {distinction.max_rank}.",
                )
            if existing and rank_int <= current_rank:
                return ActionResult(
                    success=False,
                    message=(
                        f"{target.key} already has {distinction.name} at rank "
                        f"{current_rank}; a rank-up needs a higher target rank."
                    ),
                )

            xp_cost = kwargs.get("xp_cost")
            xp_cost_int: int | None = None
            if xp_cost is not None:
                xp_cost_int = _coerce_nonneg_int(xp_cost)
                if xp_cost_int is None:
                    return ActionResult(
                        success=False, message="xp_cost must be a non-negative whole number."
                    )

            auth = create_distinction_change_authorization(
                sheet,
                action=DistinctionChangeAction.ADD,
                distinction=distinction,
                authorized_by=actor.account,
                reason=reason,
                rank=rank_int,
                xp_cost=xp_cost_int,
            )
            verb = "ranking up" if existing else "adding"
            return ActionResult(
                success=True,
                message=(
                    f"Authorized {verb} {distinction.name} (rank {rank_int}) for "
                    f"{target.key} at {auth.xp_cost} XP (auth #{auth.pk})."
                ),
            )

        # REMOVE
        cd_id = kwargs.get("character_distinction_id")
        if cd_id is None:
            return ActionResult(
                success=False, message="character_distinction_id required for remove action."
            )

        try:
            cd_id_int = int(cd_id)
        except (TypeError, ValueError):
            return ActionResult(success=False, message="character_distinction_id must be a number.")

        char_distinction = CharacterDistinction.objects.filter(
            pk=cd_id_int, character=sheet
        ).first()
        if char_distinction is None:
            return ActionResult(
                success=False,
                message=f"CharacterDistinction #{cd_id_int} not found for {target.key}.",
            )

        xp_cost = kwargs.get("xp_cost")
        xp_cost_int: int | None = None
        if xp_cost is not None:
            xp_cost_int = _coerce_nonneg_int(xp_cost)
            if xp_cost_int is None:
                return ActionResult(
                    success=False, message="xp_cost must be a non-negative whole number."
                )

        auth = create_distinction_change_authorization(
            sheet,
            action=DistinctionChangeAction.REMOVE,
            character_distinction=char_distinction,
            authorized_by=actor.account,
            reason=reason,
            xp_cost=xp_cost_int,
        )
        return ActionResult(
            success=True,
            message=(
                f"Authorized removing {char_distinction.distinction.name}"
                f" from {target.key} for {auth.xp_cost} XP (auth #{auth.pk})."
            ),
        )


@dataclass
class AcceptDistinctionChangeAction(Action):
    """Player action: accept a distinction change by spending XP.

    Calls ``spend_xp_on_distinction_unlock`` to debit XP and fire the change.

    Dispatch convention
    -------------------
    REGISTRY ActionRef: ``registry_key="accept_distinction_change"``,
    ``authorization_id=<int>``.
    """

    key: str = "accept_distinction_change"
    name: str = "Accept Distinction Change"
    icon: str = "check"
    category: str = "distinctions"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def execute(  # noqa: PLR0911
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.distinctions.exceptions import (  # noqa: PLC0415
            DistinctionAuthorizationError,
            DistinctionExclusionError,
        )
        from world.distinctions.models import DistinctionChangeAuthorization  # noqa: PLC0415
        from world.distinctions.services import spend_xp_on_distinction_unlock  # noqa: PLC0415
        from world.distinctions.types import DistinctionChangeAction  # noqa: PLC0415

        sheet = actor.character_sheet
        if sheet is None:
            return ActionResult(success=False, message="You have no character sheet.")

        auth_id = kwargs.get("authorization_id")
        if auth_id is None:
            return ActionResult(
                success=False, message="Usage: accept_distinction_change <authorization_id>"
            )

        try:
            auth_id_int = int(auth_id)
        except (TypeError, ValueError):
            return ActionResult(success=False, message="authorization_id must be a number.")

        auth = DistinctionChangeAuthorization.objects.filter(
            pk=auth_id_int, character_sheet=sheet
        ).first()
        if auth is None:
            return ActionResult(
                success=False,
                message=f"Authorization #{auth_id_int} not found for your character.",
            )

        try:
            spend_xp_on_distinction_unlock(sheet, auth)
        except DistinctionAuthorizationError as exc:
            return ActionResult(success=False, message=exc.user_message)
        except DistinctionExclusionError as exc:
            return ActionResult(success=False, message=exc.user_message)

        from world.gm.services import (  # noqa: PLC0415
            mark_requests_completed_for_authorization,
        )

        mark_requests_completed_for_authorization(auth)

        action_word = "added" if auth.action == DistinctionChangeAction.ADD else "removed"
        return ActionResult(
            success=True,
            message=f"Distinction change complete: {action_word} for {auth.xp_cost} XP.",
        )
