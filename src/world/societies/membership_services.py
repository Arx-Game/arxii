"""Services for organization membership lifecycle.

This module is the service layer behind the OrganizationMembership model and
its related rank-ladder / offer machinery. Service functions are kept thin and
stateless; model-level hooks delegate here so the business logic is testable
outside of Django model signals.
"""

from typing import TYPE_CHECKING

from world.societies.models import OrganizationRank

if TYPE_CHECKING:
    from world.societies.models import Organization


# Default capability grants for a freshly-created five-rank ladder.
# Tier 1 (highest) can invite; lower tiers cannot until configured by staff.
_DEFAULT_CAPABILITY_TIERS = {
    1: {"can_invite": True, "can_kick": True, "can_manage_ranks": True},
    2: {"can_invite": True, "can_kick": False, "can_manage_ranks": False},
    3: {"can_invite": False, "can_kick": False, "can_manage_ranks": False},
    4: {"can_invite": False, "can_kick": False, "can_manage_ranks": False},
    5: {"can_invite": False, "can_kick": False, "can_manage_ranks": False},
}


def ensure_default_rank_ladder(organization: "Organization") -> None:
    """Create the default five-tier rank ladder for an organization if absent.

    Covenants (``org_type.name == "covenant"``) are skipped because they use a
    separate membership model and should not receive the generic rank ladder.

    Args:
        organization: The organization to ensure ranks for.
    """
    if organization.ranks.exists():
        return
    if organization.org_type and organization.org_type.name == "covenant":  # noqa: STRING_LITERAL
        return

    for tier in range(1, 6):
        OrganizationRank.objects.create(
            organization=organization,
            name=organization.get_rank_title(tier),
            tier=tier,
            **_DEFAULT_CAPABILITY_TIERS[tier],
        )
