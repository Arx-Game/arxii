"""Table sheet-update request actions (#2607).

Four actions drive the request lifecycle. Member-owned: submit, withdraw,
complete (the acting character's sheet must match the request's persona sheet).
GM-owned: sign-off (the actor must be the table's GM). Relational permission
checks depend on kwargs and so happen in ``execute``, not ``get_prerequisites``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from evennia.objects.models import ObjectDB

from actions.base import Action
from actions.constants import ActionCategory
from actions.prerequisites import Prerequisite
from actions.types import ActionContext, ActionResult, TargetType


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "approve"}


@dataclass
class TableRequestSubmitAction(Action):
    """A table member files a distinction add/remove request (#2607)."""

    key: str = "table_request_submit"
    name: str = "Submit Table Request"
    icon: str = "clipboard-plus"
    category: str = "gm"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return []

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.distinctions.models import Distinction  # noqa: PLC0415
        from world.distinctions.table_request_handlers import (  # noqa: PLC0415
            submit_distinction_request,
        )
        from world.gm.models import GMTableMembership  # noqa: PLC0415
        from world.gm.table_request_services import TableRequestStateError  # noqa: PLC0415

        sheet = actor.character_sheet
        if sheet is None:
            return ActionResult(success=False, message="That is not a character.")

        table_id = _coerce_int(kwargs.get("table_id"))
        distinction_slug = (kwargs.get("distinction_slug") or "").strip()
        removing = _truthy(kwargs.get("removing"))
        if table_id is None or not distinction_slug:
            return ActionResult(
                success=False,
                message=(
                    "Usage: table_request_submit table_id=<n> "
                    "distinction_slug=<slug> removing=<0|1>"
                ),
            )

        membership = GMTableMembership.objects.filter(
            table_id=table_id, persona__character_sheet=sheet, left_at__isnull=True
        ).first()
        if membership is None:
            return ActionResult(success=False, message="You are not a member of that table.")

        distinction = Distinction.objects.filter(
            slug__iexact=distinction_slug, is_active=True
        ).first()
        if distinction is None:
            return ActionResult(
                success=False, message=f"No active distinction '{distinction_slug}'."
            )

        try:
            request = submit_distinction_request(
                membership=membership,
                distinction=distinction,
                removing=removing,
                reasoning=(kwargs.get("reasoning") or "").strip(),
            )
        except TableRequestStateError as exc:
            return ActionResult(success=False, message=exc.user_message)

        verb = "remove" if removing else "gain"
        return ActionResult(
            success=True,
            message=f"Requested to {verb} '{distinction.name}' (request #{request.pk}).",
        )


def _load_owned_request(actor: ObjectDB, kwargs: dict[str, Any]):
    """Fetch a request the actor owns (their sheet == the request's persona sheet)."""
    from world.gm.models import TableUpdateRequest  # noqa: PLC0415

    sheet = actor.character_sheet
    if sheet is None:
        return None, ActionResult(success=False, message="That is not a character.")
    request_id = _coerce_int(kwargs.get("request_id"))
    if request_id is None:
        return None, ActionResult(success=False, message="Usage: request_id=<n>")
    request = TableUpdateRequest.objects.filter(pk=request_id).first()
    if request is None:
        return None, ActionResult(success=False, message="No such request.")
    if request.membership.persona.character_sheet_id != sheet.pk:
        return None, ActionResult(success=False, message="That is not your request.")
    return request, None


@dataclass
class TableRequestWithdrawAction(Action):
    """A member withdraws their still-pending request (#2607)."""

    key: str = "table_request_withdraw"
    name: str = "Withdraw Table Request"
    icon: str = "clipboard-x"
    category: str = "gm"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return []

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.gm.table_request_services import (  # noqa: PLC0415
            TableRequestStateError,
            withdraw_request,
        )

        request, error = _load_owned_request(actor, kwargs)
        if error is not None:
            return error
        try:
            withdraw_request(request)
        except TableRequestStateError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message="Request withdrawn.")


@dataclass
class TableRequestCompleteAction(Action):
    """A member completes their approved request (#2607)."""

    key: str = "table_request_complete"
    name: str = "Complete Table Request"
    icon: str = "clipboard-check"
    category: str = "gm"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return []

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.distinctions.table_request_handlers import XPInsufficient  # noqa: PLC0415
        from world.gm.table_request_services import (  # noqa: PLC0415
            TableRequestStateError,
            complete_request,
        )

        request, error = _load_owned_request(actor, kwargs)
        if error is not None:
            return error
        try:
            complete_request(request)
        except (TableRequestStateError, XPInsufficient) as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message="Request completed — your sheet is updated.")


@dataclass
class TableRequestSignoffAction(Action):
    """The table's GM approves or rejects a pending request (#2607)."""

    key: str = "table_request_signoff"
    name: str = "Sign Off Table Request"
    icon: str = "gavel"
    category: str = "gm"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return []

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.gm.models import TableUpdateRequest  # noqa: PLC0415
        from world.gm.table_request_services import (  # noqa: PLC0415
            TableRequestStateError,
            signoff_request,
        )

        account = actor.account
        if account is None:
            return ActionResult(success=False, message="You have no linked account.")
        request_id = _coerce_int(kwargs.get("request_id"))
        if request_id is None:
            return ActionResult(
                success=False, message="Usage: request_id=<n> approve=<0|1> [notes=...]"
            )
        request = TableUpdateRequest.objects.filter(pk=request_id).first()
        if request is None:
            return ActionResult(success=False, message="No such request.")
        if request.membership.table.gm.account_id != account.id:
            return ActionResult(success=False, message="You are not the GM of that table.")

        try:
            signoff_request(
                request,
                approve=_truthy(kwargs.get("approve")),
                gm_notes=(kwargs.get("notes") or "").strip(),
            )
        except TableRequestStateError as exc:
            return ActionResult(success=False, message=exc.user_message)
        verb = "approved" if _truthy(kwargs.get("approve")) else "rejected"
        return ActionResult(success=True, message=f"Request {verb}.")
