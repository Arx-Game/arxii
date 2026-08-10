"""Org pacts & betrothal services (#2999): diplomacy with teeth.

OrgPact is the signed-paper instrument (proposed by one leadership, ratified
by the other, terms as levers); betrayal is a stamped world event with a
permanent prestige cost, never untracked prose. Betrothal is the promised
union — a fraction of the eventual alliance's weight now, the wedding rite
as the payoff (union + marriage pact + tier prestige in one stroke).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models, transaction
from django.utils import timezone

from world.societies.houses.constants import (
    BETROTHAL_BREAK_PRESTIGE_PENALTY,
    SCANDAL_PRESTIGE_PENALTY,
    OrgPactDissolutionReason,
    PactDissolutionReason,
    StatureShiftCause,
)
from world.societies.houses.models import Betrothal, BetrothalTerm, OrgPact, PactKind
from world.societies.houses.services import (
    CommitmentSpec,
    HousesServiceError,
    is_org_leader,
    sign_marriage_pact,
)

if TYPE_CHECKING:
    from world.roster.models import Kinsperson
    from world.scenes.models import Persona
    from world.societies.models import Organization


def _require_leader(persona: Persona, org: Organization, action: str) -> None:
    if not is_org_leader(persona, org):
        msg = f"{persona} may not {action} for org {org.pk}"
        raise HousesServiceError(msg, user_message="Only the org's leadership may do that.")


def _reprice(orgs, *, cause: str) -> None:
    """Both parties reprice immediately: diplomacy is news."""
    from world.societies.houses.models import HouseStature  # noqa: PLC0415
    from world.societies.houses.stature_services import (  # noqa: PLC0415
        recompute_stature,
        record_shift,
    )

    for org in orgs:
        stature = HouseStature.objects.filter(organization=org).first()
        before = stature.true_total if stature is not None else 0
        stature = recompute_stature(org)
        delta = stature.true_total - before
        stature.perceived_total = max(0, stature.perceived_total + delta)
        stature.save(update_fields=["perceived_total", "updated_at"])
        record_shift(org, cause=cause, delta_true=delta, delta_perceived=delta)


def propose_org_pact(
    *, kind: PactKind, proposer: Persona, party_a: Organization, party_b: Organization
) -> OrgPact:
    """One leadership offers terms; nothing binds until the other ratifies."""
    if party_a.pk == party_b.pk:
        msg = "a pact needs two orgs"
        raise HousesServiceError(msg, user_message="An org cannot ally with itself.")
    _require_leader(proposer, party_a, "propose a pact")
    if OrgPact.objects.filter(
        models.Q(party_a=party_a, party_b=party_b) | models.Q(party_a=party_b, party_b=party_a),
        kind=kind,
        dissolved_at__isnull=True,
    ).exists():
        msg = f"pact of kind {kind.pk} already live between {party_a.pk}/{party_b.pk}"
        raise HousesServiceError(
            msg, user_message="Such a pact already stands (or awaits an answer)."
        )
    return OrgPact.objects.create(kind=kind, party_a=party_a, party_b=party_b, proposed_by=proposer)


@transaction.atomic
def ratify_org_pact(pact: OrgPact, *, ratifier: Persona) -> OrgPact:
    """The counterparty's leadership signs: levers arm, both houses reprice."""
    if pact.ratified_at is not None or pact.dissolved_at is not None:
        msg = f"pact {pact.pk} is not awaiting ratification"
        raise HousesServiceError(msg, user_message="That pact is not awaiting an answer.")
    _require_leader(ratifier, pact.party_b, "ratify a pact")
    pact.ratified_at = timezone.now()
    if pact.kind.income_share_pct:
        from world.currency.models import OrgObligation  # noqa: PLC0415

        pact.obligation = OrgObligation.objects.create(
            from_organization=pact.party_a,
            to_organization=pact.party_b,
            name=f"{pact.kind.name}: {pact.party_a.name} to {pact.party_b.name}",
            percent=pact.kind.income_share_pct,
        )
    pact.save(update_fields=["ratified_at", "obligation"])
    _reprice((pact.party_a, pact.party_b), cause=StatureShiftCause.PACT_SIGNED)
    return pact


@transaction.atomic
def dissolve_org_pact(
    pact: OrgPact, *, reason: str, betrayer: Organization | None = None
) -> OrgPact:
    """End the pact. BETRAYAL costs the betrayer standing, permanently."""
    if pact.dissolved_at is not None:
        return pact
    pact.dissolved_at = timezone.now()
    pact.dissolution_reason = reason
    pact.save(update_fields=["dissolved_at", "dissolution_reason"])
    if pact.obligation is not None and pact.obligation.active:
        pact.obligation.active = False
        pact.obligation.save(update_fields=["active"])
    if reason == OrgPactDissolutionReason.BETRAYAL and betrayer is not None:
        betrayer.accumulated_prestige -= SCANDAL_PRESTIGE_PENALTY
        betrayer.save(update_fields=["accumulated_prestige"])
    _reprice((pact.party_a, pact.party_b), cause=StatureShiftCause.PACT_DISSOLVED)
    return pact


def flag_betrayal_between(attacker: Organization, victim: Organization) -> int:
    """A hostile act between pact partners stamps BETRAYAL on every live pact.

    Called from offensive spy-task resolution; future war declarations use
    the same seam. Returns how many pacts were betrayed.
    """
    pacts = OrgPact.objects.filter(
        models.Q(party_a=attacker, party_b=victim) | models.Q(party_a=victim, party_b=attacker),
        ratified_at__isnull=False,
        dissolved_at__isnull=True,
    )
    count = 0
    for pact in pacts:
        dissolve_org_pact(pact, reason=OrgPactDissolutionReason.BETRAYAL, betrayer=attacker)
        count += 1
    return count


def standing_org_pacts(org: Organization):
    return OrgPact.objects.filter(
        models.Q(party_a=org) | models.Q(party_b=org),
        ratified_at__isnull=False,
        dissolved_at__isnull=True,
    ).select_related("kind", "party_a", "party_b")


# ---------------------------------------------------------------------------
# Betrothal → wedding
# ---------------------------------------------------------------------------


def propose_betrothal(  # noqa: PLR0913 — two people, two houses, a proposer, terms
    *,
    proposer: Persona,
    kinsperson_a: Kinsperson,
    kinsperson_b: Kinsperson,
    senior_house: Organization,
    junior_house: Organization,
    terms: list[CommitmentSpec] | None = None,
    expires_at=None,
) -> Betrothal:
    """Record the promised union with its negotiated terms held in draft."""
    _require_leader(proposer, senior_house, "propose a betrothal")
    if kinsperson_a.pk == kinsperson_b.pk:
        msg = "a betrothal needs two people"
        raise HousesServiceError(msg, user_message="A betrothal needs two people.")
    for kin in (kinsperson_a, kinsperson_b):
        if kin.is_deceased:
            msg = f"kinsperson {kin.pk} is deceased"
            raise HousesServiceError(msg, user_message="The dead are past betrothal.")
        if Betrothal.objects.filter(
            models.Q(kinsperson_a=kin) | models.Q(kinsperson_b=kin),
            broken_at__isnull=True,
            wed_at__isnull=True,
        ).exists():
            msg = f"kinsperson {kin.pk} is already promised"
            raise HousesServiceError(msg, user_message="One of them is already promised.")
    betrothal = Betrothal.objects.create(
        kinsperson_a=kinsperson_a,
        kinsperson_b=kinsperson_b,
        senior_house=senior_house,
        junior_house=junior_house,
        expires_at=expires_at,
    )
    for spec in terms or []:
        BetrothalTerm.objects.create(
            betrothal=betrothal,
            kind=spec.kind,
            owed_by_senior=spec.owed_by_senior,
            committed_person=spec.committed_person,
            amount=spec.amount,
            percent=spec.percent,
            notes=spec.notes,
        )
    _reprice((betrothal.senior_house, betrothal.junior_house), cause=StatureShiftCause.PACT_SIGNED)
    return betrothal


def break_betrothal(betrothal: Betrothal, *, breaking_house: Organization) -> Betrothal:
    """A broken promise is a scandal: flat permanent standing cost."""
    if not betrothal.is_active:
        msg = f"betrothal {betrothal.pk} is not active"
        raise HousesServiceError(msg, user_message="That promise no longer stands.")
    betrothal.broken_at = timezone.now()
    betrothal.save(update_fields=["broken_at"])
    breaking_house.accumulated_prestige -= BETROTHAL_BREAK_PRESTIGE_PENALTY
    breaking_house.save(update_fields=["accumulated_prestige"])
    _reprice(
        (betrothal.senior_house, betrothal.junior_house), cause=StatureShiftCause.PACT_DISSOLVED
    )
    return betrothal


@transaction.atomic
def solemnize_wedding(betrothal: Betrothal):
    """The rite lands everything at once (#2999): union, pact, tier prestige.

    First in-play caller of ``record_union``; the negotiated BetrothalTerms
    become real, executing PactCommitments through ``sign_marriage_pact``.
    """
    from world.roster.models import UnionKind  # noqa: PLC0415
    from world.roster.services.kinship import record_union  # noqa: PLC0415
    from world.societies.houses.stature_services import (  # noqa: PLC0415
        award_marriage_tier_prestige,
    )

    if not betrothal.is_active:
        msg = f"betrothal {betrothal.pk} is not active"
        raise HousesServiceError(msg, user_message="That promise no longer stands.")
    marriage_kind = (
        UnionKind.objects.filter(confers_wedlock=True, realm__isnull=True).first()
        or UnionKind.objects.filter(confers_wedlock=True).first()
    )
    if marriage_kind is None:
        msg = "no wedlock-conferring UnionKind exists"
        raise HousesServiceError(msg, user_message="No law of marriage exists to wed under.")
    union = record_union(
        kind=marriage_kind,
        members=[betrothal.kinsperson_a, betrothal.kinsperson_b],
        started_at=timezone.now(),
    )
    specs = [
        CommitmentSpec(
            kind=term.kind,
            owed_by_senior=term.owed_by_senior,
            committed_person=term.committed_person,
            amount=term.amount,
            percent=term.percent,
            notes=term.notes,
        )
        for term in betrothal.terms.all()
    ]
    pact = sign_marriage_pact(
        union=union,
        senior_house=betrothal.senior_house,
        junior_house=betrothal.junior_house,
        commitments=specs,
    )
    award_marriage_tier_prestige(
        union, senior_house=betrothal.senior_house, junior_house=betrothal.junior_house
    )
    betrothal.wed_at = timezone.now()
    betrothal.save(update_fields=["wed_at"])
    return pact


__all__ = [
    "PactDissolutionReason",
    "break_betrothal",
    "dissolve_org_pact",
    "flag_betrayal_between",
    "propose_betrothal",
    "propose_org_pact",
    "ratify_org_pact",
    "solemnize_wedding",
    "standing_org_pacts",
]
