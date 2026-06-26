"""Organization membership lifecycle services (#1511).

All state mutations for generic (non-covenant) organization membership live
here. Actions are thin wrappers that call these functions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.scenes.block_services import org_join_blocked
from world.societies.exceptions import (
    AlreadyOrganizationMemberError,
    CannotDemoteError,
    CannotPromoteError,
    CrossOrganizationRankError,
    InvalidOrganizationPersonaError,
    NoPendingInvitationError,  # noqa: F401
    NotAuthorizedToInviteError,
    NotAuthorizedToKickError,
    NotAuthorizedToManageOrganizationError,
    NotAuthorizedToManageRanksError,
    NotOrganizationMemberError,
    OrganizationMemberBlockError,
    OrganizationOfferNotForYouError,
    OrganizationOfferPendingError,
    OrganizationOfferResolvedError,
)

if TYPE_CHECKING:
    from world.scenes.models import Persona
    from world.societies.models import (
        Organization,
        OrganizationMembership,
        OrganizationMembershipOffer,
        OrganizationRank,
    )

# Organization type name used to detect covenant-style organizations.
_COVENANT_TYPE_NAME = "covenant"


def ensure_default_rank_ladder(organization: Organization) -> list[OrganizationRank]:
    """Create the default five-rank ladder for a generic organization if absent.

    Covenants are skipped — their rank ladder lives in the covenants app.
    """
    if organization.ranks.exists():
        return list(organization.ranks.order_by("tier"))

    if organization.org_type and organization.org_type.name == _COVENANT_TYPE_NAME:
        return []

    ranks = []
    for tier in range(1, 6):
        title = organization.get_rank_title(tier)
        is_top = tier == 1
        ranks.append(
            organization.ranks.create(
                name=title,
                tier=tier,
                can_invite=is_top,
                can_kick=is_top,
                can_manage_ranks=is_top,
            )
        )
    return ranks


def base_rank_for_organization(organization: Organization) -> OrganizationRank:
    """Return the lowest (tier 5) rank for an organization, creating the ladder if needed."""
    ensure_default_rank_ladder(organization)
    return organization.ranks.order_by("-tier").first()


def active_membership_for_persona(
    organization: Organization,
    persona: Persona,
) -> OrganizationMembership | None:
    """Return the active membership for a persona in an organization, or None."""
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    return (
        OrganizationMembership.objects.filter(
            organization=organization,
            persona=persona,
            left_at__isnull=True,
            exiled_at__isnull=True,
        )
        .select_related("rank")
        .first()
    )


def _assert_higher_rank(
    actor_membership: OrganizationMembership,
    target_membership: OrganizationMembership,
) -> None:
    if actor_membership.rank.tier >= target_membership.rank.tier:
        raise NotAuthorizedToManageOrganizationError


@transaction.atomic
def join_organization(
    organization: Organization,
    persona: Persona,
) -> OrganizationMembership:
    """Create a new active membership at the base rank for an organization."""
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    if active_membership_for_persona(organization, persona) is not None:
        raise AlreadyOrganizationMemberError

    if not persona.is_established_or_primary:
        raise InvalidOrganizationPersonaError

    joining_sheet = persona.character_sheet
    member_sheets = [
        m.persona.character_sheet
        for m in OrganizationMembership.objects.filter(
            organization=organization,
            left_at__isnull=True,
            exiled_at__isnull=True,
        ).select_related("persona__character_sheet")
    ]
    if org_join_blocked(joining_sheet=joining_sheet, member_sheets=member_sheets):
        raise OrganizationMemberBlockError

    rank = base_rank_for_organization(organization)
    return OrganizationMembership.objects.create(
        organization=organization,
        persona=persona,
        rank=rank,
    )


@transaction.atomic
def leave_organization(membership: OrganizationMembership) -> None:
    """Record a voluntary departure from an organization."""
    if membership.left_at is not None:
        return
    membership.left_at = timezone.now()
    membership.save(update_fields=["left_at"])


@transaction.atomic
def invite_to_organization(
    organization: Organization,
    from_persona: Persona,
    to_persona: Persona,
) -> OrganizationMembershipOffer:
    """Create an INVITE offer from one member to another persona."""
    from world.societies.models import OrganizationMembershipOffer  # noqa: PLC0415

    actor_membership = active_membership_for_persona(organization, from_persona)
    if actor_membership is None or not actor_membership.rank.can_invite:
        raise NotAuthorizedToInviteError

    if not to_persona.is_established_or_primary:
        raise InvalidOrganizationPersonaError

    if active_membership_for_persona(organization, to_persona) is not None:
        raise AlreadyOrganizationMemberError

    if OrganizationMembershipOffer.objects.filter(
        organization=organization,
        to_persona=to_persona,
        kind=OrganizationMembershipOffer.Kind.INVITE,
        status=OrganizationMembershipOffer.Status.PENDING,
    ).exists():
        raise OrganizationOfferPendingError

    return OrganizationMembershipOffer.objects.create(
        organization=organization,
        from_persona=from_persona,
        to_persona=to_persona,
        kind=OrganizationMembershipOffer.Kind.INVITE,
    )


@transaction.atomic
def apply_to_organization(
    organization: Organization,
    from_persona: Persona,
) -> OrganizationMembershipOffer:
    """Create an APPLICATION offer from a persona to an organization."""
    from world.societies.models import OrganizationMembershipOffer  # noqa: PLC0415

    if not from_persona.is_established_or_primary:
        raise InvalidOrganizationPersonaError

    if active_membership_for_persona(organization, from_persona) is not None:
        raise AlreadyOrganizationMemberError

    if OrganizationMembershipOffer.objects.filter(
        organization=organization,
        from_persona=from_persona,
        kind=OrganizationMembershipOffer.Kind.APPLICATION,
        status=OrganizationMembershipOffer.Status.PENDING,
    ).exists():
        raise OrganizationOfferPendingError

    return OrganizationMembershipOffer.objects.create(
        organization=organization,
        from_persona=from_persona,
        kind=OrganizationMembershipOffer.Kind.APPLICATION,
    )


@transaction.atomic
def accept_invitation(
    offer: OrganizationMembershipOffer,
    as_persona: Persona,
) -> OrganizationMembership:
    """Accept an INVITE offer and create a membership."""
    if offer.status != offer.Status.PENDING:
        raise OrganizationOfferResolvedError
    if offer.kind != offer.Kind.INVITE:
        raise OrganizationOfferResolvedError
    if offer.to_persona_id != as_persona.pk:
        raise OrganizationOfferNotForYouError

    membership = join_organization(offer.organization, as_persona)
    offer.status = offer.Status.ACCEPTED
    offer.resolved_at = timezone.now()
    offer.save(update_fields=["status", "resolved_at"])
    return membership


@transaction.atomic
def decline_invitation(
    offer: OrganizationMembershipOffer,
    as_persona: Persona,
) -> None:
    """Decline an INVITE offer."""
    if offer.status != offer.Status.PENDING:
        raise OrganizationOfferResolvedError
    if offer.to_persona_id != as_persona.pk:
        raise OrganizationOfferNotForYouError

    offer.status = offer.Status.DECLINED
    offer.resolved_at = timezone.now()
    offer.save(update_fields=["status", "resolved_at"])


@transaction.atomic
def accept_application(
    offer: OrganizationMembershipOffer,
    actor_persona: Persona,
) -> OrganizationMembership:
    """Accept an APPLICATION offer on behalf of the organization."""
    if offer.status != offer.Status.PENDING or offer.kind != offer.Kind.APPLICATION:
        raise OrganizationOfferResolvedError

    actor_membership = active_membership_for_persona(offer.organization, actor_persona)
    if actor_membership is None or not actor_membership.rank.can_invite:
        raise NotAuthorizedToInviteError

    membership = join_organization(offer.organization, offer.from_persona)
    offer.status = offer.Status.ACCEPTED
    offer.resolved_at = timezone.now()
    offer.save(update_fields=["status", "resolved_at"])
    return membership


@transaction.atomic
def decline_application(
    offer: OrganizationMembershipOffer,
    actor_persona: Persona,
) -> None:
    """Decline an APPLICATION offer on behalf of the organization."""
    if offer.status != offer.Status.PENDING or offer.kind != offer.Kind.APPLICATION:
        raise OrganizationOfferResolvedError

    actor_membership = active_membership_for_persona(offer.organization, actor_persona)
    if actor_membership is None or not actor_membership.rank.can_invite:
        raise NotAuthorizedToInviteError

    offer.status = offer.Status.DECLINED
    offer.resolved_at = timezone.now()
    offer.save(update_fields=["status", "resolved_at"])


@transaction.atomic
def promote_member(
    target_membership: OrganizationMembership,
    actor_membership: OrganizationMembership,
) -> OrganizationMembership:
    """Move a member one tier higher (lower tier number)."""
    if actor_membership.left_at is not None or not actor_membership.rank.can_manage_ranks:
        raise NotAuthorizedToManageRanksError

    if target_membership.organization_id != actor_membership.organization_id:
        raise CrossOrganizationRankError

    if target_membership.left_at is not None or target_membership.exiled_at is not None:
        raise NotOrganizationMemberError

    _assert_higher_rank(actor_membership, target_membership)

    current_tier = target_membership.rank.tier
    if current_tier <= 1:
        raise CannotPromoteError

    new_rank = actor_membership.organization.ranks.filter(tier=current_tier - 1).first()
    if new_rank is None:
        raise CannotPromoteError

    target_membership.rank = new_rank
    target_membership.save(update_fields=["rank"])
    return target_membership


@transaction.atomic
def demote_member(
    target_membership: OrganizationMembership,
    actor_membership: OrganizationMembership,
) -> OrganizationMembership:
    """Move a member one tier lower (higher tier number)."""
    if actor_membership.left_at is not None or not actor_membership.rank.can_manage_ranks:
        raise NotAuthorizedToManageRanksError

    if target_membership.organization_id != actor_membership.organization_id:
        raise CrossOrganizationRankError

    if target_membership.left_at is not None or target_membership.exiled_at is not None:
        raise NotOrganizationMemberError

    _assert_higher_rank(actor_membership, target_membership)

    current_tier = target_membership.rank.tier
    if current_tier >= 5:  # noqa: PLR2004
        raise CannotDemoteError

    new_rank = actor_membership.organization.ranks.filter(tier=current_tier + 1).first()
    if new_rank is None:
        raise CannotDemoteError

    target_membership.rank = new_rank
    target_membership.save(update_fields=["rank"])
    return target_membership


@transaction.atomic
def expel_member(
    target_membership: OrganizationMembership,
    actor_membership: OrganizationMembership,
) -> None:
    """Forcibly remove a member from an organization."""
    if actor_membership.left_at is not None or not actor_membership.rank.can_kick:
        raise NotAuthorizedToKickError

    if target_membership.organization_id != actor_membership.organization_id:
        raise CrossOrganizationRankError

    if target_membership.left_at is not None or target_membership.exiled_at is not None:
        return

    _assert_higher_rank(actor_membership, target_membership)

    target_membership.exiled_at = timezone.now()
    target_membership.left_at = timezone.now()
    target_membership.save(update_fields=["exiled_at", "left_at"])
