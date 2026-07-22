"""Distinction-specific actions: GM award + sheet-update requests (#2037, #2628)."""

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


def _reviewer_has_table_access(reviewer_account: Any, req: Any) -> bool:
    """The #2631 review-pool rule: staff, or a GM with table access.

    A GM may review a request iff the requesting character has an ACTIVE
    membership at one of that GM's tables. Shopping among known GMs is fine;
    a GM the player has never sat with must not see their sheet.
    """
    if reviewer_account is None or reviewer_account.is_staff:
        return True

    from world.gm.models import GMTableMembership  # noqa: PLC0415

    return GMTableMembership.objects.filter(
        persona__character_sheet=req.character_sheet,
        left_at__isnull=True,
        table__gm__account=reviewer_account,
    ).exists()


@dataclass
class GMAwardDistinctionAction(Action):
    """JUNIOR-tier GM action: add or remove a distinction via the request framework (#2628).

    Creates an auto-approved ``SheetUpdateRequest`` and immediately processes it.
    XP is charged on the sign-based model: beneficial distinctions cost XP to
    add (free to remove); detrimental distinctions are free to add (cost XP to
    remove). This ensures XP consistency — the same cost whether the player
    requested it or the GM set it directly.

    Wraps ``create_sheet_update_request`` + ``approve_sheet_update_request``.

    Dispatch convention
    -------------------
    REGISTRY ActionRef: ``registry_key="gm_award_distinction"``,
    ``target_name=<str>``, ``distinction_slug=<str>``,
    optional ``action="remove"`` (default is add),
    optional ``rank=<int>`` (for add).

    Gated on ``MinimumGMLevelPrerequisite(GMLevel.JUNIOR)`` (staff bypass
    preserved).
    """

    key: str = "gm_award_distinction"
    name: str = "Award Distinction"
    icon: str = "medal"
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
        from world.distinctions.exceptions import (  # noqa: PLC0415
            DistinctionExclusionError,
            SheetUpdateRequestError,
        )
        from world.distinctions.models import CharacterDistinction, Distinction  # noqa: PLC0415
        from world.distinctions.services import (  # noqa: PLC0415
            approve_sheet_update_request,
            create_sheet_update_request,
        )
        from world.distinctions.types import (  # noqa: PLC0415
            DistinctionOrigin,
            SheetUpdateRequestType,
        )

        target_name = (kwargs.get("target_name") or "").strip()
        distinction_slug = (kwargs.get("distinction_slug") or "").strip()
        action_str = (kwargs.get("action") or "add").strip().lower()

        if not target_name or not distinction_slug:
            if action_str == "remove":  # noqa: STRING_LITERAL
                return ActionResult(
                    success=False,
                    message="Usage: grant_distinction/remove <character>=<distinction slug>",
                )
            return ActionResult(
                success=False,
                message="Usage: grant_distinction <character>=<distinction slug>[,rank]",
            )

        target = actor.search(target_name, global_search=True)
        if target is None:
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

        gm_account = actor.account

        if action_str == "remove":  # noqa: STRING_LITERAL
            char_distinction = CharacterDistinction.objects.filter(
                character=sheet, distinction=distinction
            ).first()
            if char_distinction is None:
                return ActionResult(
                    success=False,
                    message=f"{target.key} does not have {distinction.name}.",
                )
            try:
                req = create_sheet_update_request(
                    sheet,
                    SheetUpdateRequestType.DISTINCTION_REMOVE,
                    justification=f"GM-direct removal by {actor.key}.",
                    target_character_distinction=char_distinction,
                    submitted_by=gm_account,
                    origin=DistinctionOrigin.GM_AWARD,
                )
                approve_sheet_update_request(req, gm_account)
            except SheetUpdateRequestError as exc:
                return ActionResult(success=False, message=exc.user_message)
            except DistinctionExclusionError as exc:
                return ActionResult(success=False, message=exc.user_message)

            return ActionResult(
                success=True,
                message=f"Removed {distinction.name} from {target.key}.",
            )

        # ADD (default)
        rank: int | None = None
        rank_raw = kwargs.get("rank")
        if rank_raw is not None:
            rank = _coerce_positive_int(rank_raw)
            if rank is None:
                return ActionResult(success=False, message="rank must be a positive whole number.")

        if rank is not None and rank > distinction.max_rank:
            return ActionResult(
                success=False,
                message=f"{distinction.name} has a maximum rank of {distinction.max_rank}.",
            )

        try:
            req = create_sheet_update_request(
                sheet,
                SheetUpdateRequestType.DISTINCTION_ADD,
                justification=f"GM-direct grant by {actor.key}.",
                target_distinction=distinction,
                submitted_by=gm_account,
                origin=DistinctionOrigin.GM_AWARD,
            )
            approve_sheet_update_request(req, gm_account)
        except SheetUpdateRequestError as exc:
            return ActionResult(success=False, message=exc.user_message)
        except DistinctionExclusionError as exc:
            return ActionResult(success=False, message=exc.user_message)

        cd = CharacterDistinction.objects.filter(character=sheet, distinction=distinction).first()
        actual_rank = cd.rank if cd else 1
        return ActionResult(
            success=True,
            message=f"Awarded '{distinction.name}' (rank {actual_rank}) to {target.key}.",
        )


@dataclass
class SubmitSheetUpdateRequestAction(Action):
    """Player action: submit a request to add or remove a distinction.

    Creates a PENDING ``SheetUpdateRequest``. The XP cost is computed and
    stamped at submission time. The player sees the cost in the result message.

    Dispatch convention
    -------------------
    REGISTRY ActionRef: ``registry_key="submit_sheet_update"``,
    ``request_type=<"distinction_add"|"distinction_remove">``,
    ``distinction_slug=<str>`` (for add) or
    ``character_distinction_id=<int>`` (for remove),
    optional ``rank=<int>`` (for add),
    ``justification=<str>``.
    """

    key: str = "submit_sheet_update"
    name: str = "Submit Sheet Update Request"
    icon: str = "scroll"
    category: str = "distinctions"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def execute(  # noqa: PLR0911, PLR0912, C901
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.distinctions.exceptions import (  # noqa: PLC0415
            DistinctionExclusionError,
            SheetUpdateRequestError,
        )
        from world.distinctions.models import CharacterDistinction, Distinction  # noqa: PLC0415
        from world.distinctions.services import create_sheet_update_request  # noqa: PLC0415
        from world.distinctions.types import (  # noqa: PLC0415
            DistinctionOrigin,
            SheetUpdateRequestType,
        )

        sheet = actor.character_sheet
        if sheet is None:
            return ActionResult(success=False, message="You have no character sheet.")

        request_type_str = (kwargs.get("request_type") or "").strip().lower()
        justification = (kwargs.get("justification") or "").strip()

        if not request_type_str or not justification:
            return ActionResult(
                success=False,
                message=(
                    "Usage: submit_sheet_update "
                    "request_type=<distinction_add|distinction_remove>,justification=<text>"
                ),
            )

        type_map = {
            "distinction_add": SheetUpdateRequestType.DISTINCTION_ADD,
            "distinction_remove": SheetUpdateRequestType.DISTINCTION_REMOVE,
        }
        request_type = type_map.get(request_type_str)
        if request_type is None:
            return ActionResult(
                success=False,
                message="request_type must be 'distinction_add' or 'distinction_remove'.",
            )

        account = actor.account

        if request_type == SheetUpdateRequestType.DISTINCTION_ADD:
            distinction_slug = (kwargs.get("distinction_slug") or "").strip()
            if not distinction_slug:
                return ActionResult(success=False, message="distinction_slug required for add.")
            distinction = Distinction.objects.filter(
                slug__iexact=distinction_slug, is_active=True
            ).first()
            if distinction is None:
                return ActionResult(
                    success=False,
                    message=f"No active distinction found with slug '{distinction_slug}'.",
                )
            try:
                req = create_sheet_update_request(
                    sheet,
                    request_type,
                    justification=justification,
                    target_distinction=distinction,
                    submitted_by=account,
                    origin=DistinctionOrigin.UNLOCK_PURCHASE,
                )
            except DistinctionExclusionError as exc:
                return ActionResult(success=False, message=exc.user_message)
            except SheetUpdateRequestError as exc:
                return ActionResult(success=False, message=exc.user_message)
        else:
            cd_id = kwargs.get("character_distinction_id")
            if cd_id is None:
                return ActionResult(
                    success=False,
                    message="character_distinction_id required for remove.",
                )
            try:
                cd_id_int = int(cd_id)
            except (TypeError, ValueError):
                return ActionResult(
                    success=False, message="character_distinction_id must be a number."
                )
            char_distinction = CharacterDistinction.objects.filter(
                pk=cd_id_int, character=sheet
            ).first()
            if char_distinction is None:
                return ActionResult(
                    success=False,
                    message=f"CharacterDistinction #{cd_id_int} not found for your character.",
                )
            try:
                req = create_sheet_update_request(
                    sheet,
                    request_type,
                    justification=justification,
                    target_character_distinction=char_distinction,
                    submitted_by=account,
                    origin=DistinctionOrigin.UNLOCK_PURCHASE,
                )
            except SheetUpdateRequestError as exc:
                return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=(
                f"Request #{req.pk} submitted ({req.get_request_type_display()}). "
                f"XP cost: {req.xp_cost}."
            ),
        )


@dataclass
class ReviewSheetUpdateRequestAction(Action):
    """GM action: approve or deny a pending SheetUpdateRequest.

    On approval: XP is auto-debited and the change fires immediately
    (atomic). On denial: request closes, no change.

    Gated on ``MinimumGMLevelPrerequisite(GMLevel.JUNIOR)``.

    Dispatch convention
    -------------------
    REGISTRY ActionRef: ``registry_key="review_sheet_update"``,
    ``request_id=<int>``, ``decision=<"approve"|"deny">``.
    """

    key: str = "review_sheet_update"
    name: str = "Review Sheet Update Request"
    icon: str = "check"
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
        from world.distinctions.exceptions import SheetUpdateRequestError  # noqa: PLC0415
        from world.distinctions.models import SheetUpdateRequest  # noqa: PLC0415
        from world.distinctions.services import (  # noqa: PLC0415
            approve_sheet_update_request,
            deny_sheet_update_request,
        )
        from world.distinctions.types import SheetUpdateRequestStatus  # noqa: PLC0415

        request_id = kwargs.get("request_id")
        decision = (kwargs.get("decision") or "").strip().lower()

        if request_id is None or not decision:
            return ActionResult(
                success=False,
                message="Usage: review_sheet_update request_id=<int>,decision=<approve|deny>",
            )

        try:
            request_id_int = int(request_id)
        except (TypeError, ValueError):
            return ActionResult(success=False, message="request_id must be a number.")

        if decision not in ("approve", "deny"):
            return ActionResult(success=False, message="decision must be 'approve' or 'deny'.")

        req = SheetUpdateRequest.objects.filter(pk=request_id_int).first()
        if req is None:
            return ActionResult(success=False, message=f"Request #{request_id_int} not found.")

        if not _reviewer_has_table_access(actor.account, req):
            return ActionResult(
                success=False,
                message="You may only review requests from characters at your own tables.",
            )

        if req.status != SheetUpdateRequestStatus.PENDING:
            return ActionResult(
                success=False,
                message=f"Request #{request_id_int} has already been processed.",
            )

        gm_account = actor.account

        if decision == "approve":  # noqa: STRING_LITERAL
            try:
                approve_sheet_update_request(req, gm_account)
            except SheetUpdateRequestError as exc:
                return ActionResult(success=False, message=exc.user_message)
            return ActionResult(
                success=True,
                message=f"Approved request #{request_id_int}. Change applied.",
            )
        try:
            deny_sheet_update_request(req, gm_account)
        except SheetUpdateRequestError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"Denied request #{request_id_int}.",
        )
