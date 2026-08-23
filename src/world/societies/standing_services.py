"""Leader-declared org favor/disfavor service (#3290).

An org leader (an active membership whose ``OrganizationRank.can_declare_standing``
is set) can officially declare a persona favored or disfavored with the org. The
reputation delta itself always applies through the existing
``bump_organization_reputation`` writer (``renown.py``) — this module never writes
``OrganizationReputation`` directly; it only mints the ``StandingDeclaration`` audit
row alongside it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from world.societies.constants import (
    STANDING_DECLARATION_DISFAVOR_DELTA,
    STANDING_DECLARATION_FAVOR_DELTA,
    STANDING_DISFAVOR_CONSENT_CATEGORY_KEY,
    StandingDirection,
)
from world.societies.exceptions import (
    InvalidStandingTargetError,
    NotAuthorizedToDeclareStandingError,
    StandingConsentBlockedError,
    StandingRateLimitedError,
)
from world.societies.membership_services import active_membership_for_persona
from world.societies.renown import bump_organization_reputation

if TYPE_CHECKING:
    from world.roster.models import RosterTenure
    from world.scenes.models import Persona
    from world.societies.models import Organization, StandingDeclaration


def _active_tenure(persona: Persona) -> RosterTenure | None:
    from world.roster.models import RosterTenure  # noqa: PLC0415

    return RosterTenure.objects.filter(
        roster_entry__character_sheet=persona.character_sheet, end_date__isnull=True
    ).first()


def _consent_blocks_disfavor(*, target_persona: Persona, declarer_persona: Persona) -> bool:
    """Mirrors ``world.secrets.services.accusation_permitted``'s consent gate.

    A tenure-less target (NPC or no active tenure) is always antagonism-allowed,
    matching the steal/frame gates; a played target must have opened their
    ``hostile`` antagonism-consent category (#2170) to the declaring persona.
    """
    from world.consent.models import SocialConsentCategory  # noqa: PLC0415
    from world.consent.services import consent_blocks_targeting  # noqa: PLC0415

    target_tenure = _active_tenure(target_persona)
    if target_tenure is None:
        return False

    try:
        hostile = SocialConsentCategory.objects.get_by_natural_key(
            STANDING_DISFAVOR_CONSENT_CATEGORY_KEY
        )
    except SocialConsentCategory.DoesNotExist:
        return False  # category not seeded (bare test DB) — no gate to apply

    return consent_blocks_targeting(
        owner_tenure=target_tenure,
        category=hostile,
        actor_tenure=_active_tenure(declarer_persona),
    )


@transaction.atomic
def declare_standing(
    *,
    organization: Organization,
    target_persona: Persona,
    declared_by_persona: Persona,
    direction: str,
    citation: str,
) -> StandingDeclaration:
    """Officially declare *target_persona* favored or disfavored with *organization*.

    Gates (#3290 decisions 1-3, in order): the declaring persona's active
    membership rank must carry ``can_declare_standing``; the target must be able
    to hold organization reputation at all (established/primary persona); a
    DISFAVOR direction additionally requires the target's antagonism consent;
    at most one declaration per (organization, target_persona) per IC week.
    Raises a typed :class:`~world.societies.exceptions.StandingDeclarationError`
    subclass on any gate failure.
    """
    from world.game_clock.week_services import get_current_game_week  # noqa: PLC0415
    from world.societies.models import (  # noqa: PLC0415
        OrganizationReputation,
        StandingDeclaration,
    )

    if direction not in StandingDirection.values:
        msg = f"Invalid standing direction '{direction}'."
        raise ValueError(msg)

    actor_membership = active_membership_for_persona(organization, declared_by_persona)
    if actor_membership is None or not actor_membership.rank.can_declare_standing:
        raise NotAuthorizedToDeclareStandingError

    if not target_persona.is_established_or_primary:
        raise InvalidStandingTargetError

    if direction == StandingDirection.DISFAVOR and _consent_blocks_disfavor(
        target_persona=target_persona, declarer_persona=declared_by_persona
    ):
        raise StandingConsentBlockedError

    game_week = get_current_game_week()
    if StandingDeclaration.objects.filter(
        organization=organization, target_persona=target_persona, game_week=game_week
    ).exists():
        raise StandingRateLimitedError

    nominal_delta = (
        STANDING_DECLARATION_FAVOR_DELTA
        if direction == StandingDirection.FAVOR
        else STANDING_DECLARATION_DISFAVOR_DELTA
    )
    old_value = (
        OrganizationReputation.objects.filter(persona=target_persona, organization=organization)
        .values_list("value", flat=True)
        .first()
        or 0
    )
    new_value = bump_organization_reputation(target_persona, organization, nominal_delta)
    # is_established_or_primary was already checked above and nominal_delta is never
    # zero, so bump_organization_reputation's only no-op conditions can't apply here.
    applied = 0 if new_value is None else new_value - old_value

    return StandingDeclaration.objects.create(
        organization=organization,
        target_persona=target_persona,
        declared_by_persona=declared_by_persona,
        direction=direction,
        delta_applied=applied,
        citation=citation,
        game_week=game_week,
    )
