"""OrgAppeal lifecycle services (#3293) — appeals to organizations.

An appeal is a free-text IC ask lodged with an organization: any character may
lodge one (no membership required — the whole point is reaching a house without
knowing a member personally), members sign onto it to show support, and
leadership resolves it with a written answer. Mirrors the proven
``GroupStoryRequest`` shape (``world/stories/services/tables.py``), a sibling
lifecycle for a different target (GM pool vs. org), not a generalization of it.

Authorization for signon/resolve/withdraw is enforced here (mirrors
``promote_member``/``demote_member``/``expel_member`` in
``membership_services.py``, not the "service trusts pre-validated input"
convention used by pure state-machine services like ``GroupStoryRequest``) —
these three actions gate on standing (membership, the ``can_resolve_appeals``
rank, or staff, and petitioner identity), so the check belongs beside the
mutation it guards.

Lodging deliberately does NOT gate on ``persona.is_established_or_primary``
(unlike ``apply_to_organization``) — an appeal is not membership, and the user
stories are explicit that any character may ask a house for aid without prior
standing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.societies.constants import OrgAppealState
from world.societies.exceptions import (
    AppealNotOpenError,
    InvalidAppealVerdictError,
    NotAppealPetitionerError,
    NotAuthorizedToResolveAppealError,
    NotOrganizationMemberError,
)
from world.societies.models import OrgAppeal, OrgAppealSignon

if TYPE_CHECKING:
    from world.scenes.models import Persona
    from world.societies.models import Organization

_RESOLVED_VERDICTS = frozenset({OrgAppealState.GRANTED, OrgAppealState.DECLINED})


def can_resolve_org_appeals(persona: Persona, organization: Organization) -> bool:
    """Whether ``persona`` holds a ``can_resolve_appeals`` rank in the org.

    The active-membership gate mirrors ``OrganizationMembership``'s own truth —
    ``left_at`` and ``exiled_at`` both null — so a departed or exiled member
    never counts, mirroring ``houses.services.is_org_leader``.
    """
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    return OrganizationMembership.objects.filter(
        organization=organization,
        persona=persona,
        left_at__isnull=True,
        exiled_at__isnull=True,
        rank__can_resolve_appeals=True,
    ).exists()


def lodge_appeal(
    *,
    organization: Organization,
    petitioner_persona: Persona,
    title: str,
    body: str,
) -> OrgAppeal:
    """Lodge a free-text appeal with an organization.

    A DB-level partial unique constraint prevents a second OPEN appeal from
    the same petitioner to the same organization; ``IntegrityError`` will
    surface if violated — the service does not pre-check it (mirrors
    ``request_gm_for_covenant``).
    """
    return OrgAppeal.objects.create(
        organization=organization,
        petitioner_persona=petitioner_persona,
        title=title,
        body=body,
    )


def signon_appeal(
    *,
    appeal: OrgAppeal,
    member_persona: Persona,
    note: str = "",
) -> OrgAppealSignon:
    """A member signs onto an open appeal to show support.

    Raises:
        AppealNotOpenError: The appeal is no longer OPEN.
        NotOrganizationMemberError: ``member_persona`` has no active
            membership in the appeal's organization.
    """
    from world.societies.membership_services import active_membership_for_persona  # noqa: PLC0415

    if appeal.state != OrgAppealState.OPEN:
        raise AppealNotOpenError
    if active_membership_for_persona(appeal.organization, member_persona) is None:
        raise NotOrganizationMemberError

    return OrgAppealSignon.objects.get_or_create(
        appeal=appeal,
        member_persona=member_persona,
        defaults={"note": note},
    )[0]


@transaction.atomic
def resolve_appeal(
    *,
    appeal: OrgAppeal,
    verdict: str,
    resolution_text: str,
    resolver_persona: Persona | None,
    is_staff: bool = False,
) -> OrgAppeal:
    """Leadership grants or declines an open appeal with a written answer.

    ``is_staff`` bypasses the ``can_resolve_appeals`` rank check (mirrors the
    account.is_staff bypass pattern in ``actions/definitions/gm_stories.py``'s
    ``RequestGMForCovenantAction``); ``resolver_persona`` may be None only
    when ``is_staff`` is True (staff acting with no character present).

    Raises:
        AppealNotOpenError: The appeal is no longer OPEN.
        InvalidAppealVerdictError: ``verdict`` is neither GRANTED nor DECLINED.
        NotAuthorizedToResolveAppealError: Neither staff nor a
            ``can_resolve_appeals`` rank holder in the org.
    """
    if appeal.state != OrgAppealState.OPEN:
        raise AppealNotOpenError
    if verdict not in _RESOLVED_VERDICTS:
        raise InvalidAppealVerdictError
    if not is_staff:
        if resolver_persona is None or not can_resolve_org_appeals(
            resolver_persona, appeal.organization
        ):
            raise NotAuthorizedToResolveAppealError

    appeal.state = verdict
    appeal.resolution_text = resolution_text
    appeal.resolved_by_persona = resolver_persona
    appeal.resolved_at = timezone.now()
    appeal.save(update_fields=["state", "resolution_text", "resolved_by_persona", "resolved_at"])
    return appeal


def withdraw_appeal(*, appeal: OrgAppeal, petitioner_persona: Persona) -> OrgAppeal:
    """The petitioner rescinds their own open appeal.

    Raises:
        AppealNotOpenError: The appeal is no longer OPEN.
        NotAppealPetitionerError: ``petitioner_persona`` did not lodge it.
    """
    if appeal.state != OrgAppealState.OPEN:
        raise AppealNotOpenError
    if appeal.petitioner_persona_id != petitioner_persona.pk:
        raise NotAppealPetitionerError

    with transaction.atomic():
        appeal.state = OrgAppealState.WITHDRAWN
        appeal.resolved_at = timezone.now()
        appeal.save(update_fields=["state", "resolved_at"])
    return appeal
