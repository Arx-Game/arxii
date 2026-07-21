"""State-machine transitions for TableUpdateRequest (#2607).

Generic, kind-agnostic: submit is kind-specific and lives with each kind (the
distinction kind's ``submit_distinction_request`` is in
``world.distinctions.table_request_handlers``). These handle the shared
lifecycle: GM sign-off (approve/reject), member withdraw, and member complete.

    PENDING --approve--> APPROVED --complete--> COMPLETED
       |--reject--> REJECTED
       |--withdraw--> WITHDRAWN
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils import timezone

from world.gm.constants import TableRequestStatus
from world.gm.request_handlers import run_request_completion

if TYPE_CHECKING:
    from world.gm.models import TableUpdateRequest


class TableRequestStateError(Exception):
    """An illegal table-request transition, or an ineligible submit."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


def _notify_approved(request: TableUpdateRequest) -> None:
    """Prompt the member to complete their approved change (#2607)."""
    from world.narrative.constants import NarrativeCategory  # noqa: PLC0415
    from world.narrative.services import send_narrative_message  # noqa: PLC0415

    sheet = request.membership.persona.character_sheet
    send_narrative_message(
        recipients=[sheet],
        body=(
            "Your table request was approved. Complete it when you're ready — "
            "the change applies (and any XP is spent) at that point."
        ),
        category=NarrativeCategory.SYSTEM,
    )


def signoff_request(
    request: TableUpdateRequest, *, approve: bool, gm_notes: str = ""
) -> TableUpdateRequest:
    """GM sign-off: PENDING -> APPROVED or REJECTED."""
    if request.status != TableRequestStatus.PENDING:
        raise TableRequestStateError("This request is no longer pending sign-off.")
    request.status = TableRequestStatus.APPROVED if approve else TableRequestStatus.REJECTED
    request.gm_notes = gm_notes
    request.resolved_at = timezone.now()
    request.save(update_fields=["status", "gm_notes", "resolved_at"])
    if approve:
        _notify_approved(request)
    return request


def withdraw_request(request: TableUpdateRequest) -> TableUpdateRequest:
    """Member pulls a still-pending request: PENDING -> WITHDRAWN."""
    if request.status != TableRequestStatus.PENDING:
        raise TableRequestStateError("Only a pending request can be withdrawn.")
    request.status = TableRequestStatus.WITHDRAWN
    request.resolved_at = timezone.now()
    request.save(update_fields=["status", "resolved_at"])
    return request


def complete_request(request: TableUpdateRequest) -> TableUpdateRequest:
    """Member completes an approved request: APPROVED -> COMPLETED.

    Dispatches to the kind's completion handler (which spends XP and applies the
    change atomically). If the handler raises — e.g. the member cannot afford the
    XP — the exception propagates and the status stays APPROVED, so completion
    can be retried whenever the member can afford it. No deadline.
    """
    if request.status != TableRequestStatus.APPROVED:
        raise TableRequestStateError("Only an approved request can be completed.")
    run_request_completion(request)
    request.status = TableRequestStatus.COMPLETED
    request.completed_at = timezone.now()
    request.save(update_fields=["status", "completed_at"])
    return request
