"""Proclamations & domain edicts (#2842, ADR-0178).

A proclamation appeals to a philosophy MECHANICALLY: the stance archetype's
six-axis vector dot-products against each society's principles (the same
judgment engine renown/scandal use), and the oratory roll scales the
reception asymmetrically — aligned societies warm only on success; opposed
ones are provoked regardless, mitigated by success and amplified by botches.
The prose is display-only and never parsed.

Edicts ride proclamations: enacting a standing domain policy issues its
inherent stance (the social bill) and leaves a ``DomainEdict`` row the
weekly tick and stream accrual read (the mechanical bite).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

if TYPE_CHECKING:
    from world.scenes.models import Persona
    from world.societies.houses.models import Domain, DomainEdict, EdictKind
    from world.societies.models import Proclamation, StanceArchetype

# PLACEHOLDER calibration (#2842). Reception scaling per roll success level:
# aligned societies gain scaled by _SUPPORT_PCT (a failed roll wins nobody);
# opposed societies lose scaled by _PROVOKE_PCT (success mitigates, failure
# takes it in full, a botch amplifies).
_SUPPORT_PCT: dict[int, int] = {-2: 0, -1: 0, 0: 50, 1: 100, 2: 130, 3: 150}
_PROVOKE_PCT: dict[int, int] = {-2: 150, -1: 100, 0: 100, 1: 60, 2: 40, 3: 25}
_CHECK_PREFERENCE = ("Persuasion", "Diplomacy", "Oratory", "Etiquette")


class ProclamationError(Exception):
    """A proclamation rule was violated. Carries a safe user message."""

    def __init__(self, msg: str, *, user_message: str) -> None:
        super().__init__(msg)
        self.user_message = user_message


def _oratory_check_type():
    from world.checks.models import CheckType  # noqa: PLC0415

    for name in _CHECK_PREFERENCE:
        check_type = CheckType.objects.filter(name=name).first()
        if check_type is not None:
            return check_type
    return CheckType.objects.first()


def _scaled_reception(raw_delta: int, success_level: int) -> int:
    """Asymmetric roll scaling (#2842): support is earned, provocation is
    survived."""
    if raw_delta > 0:
        pct = _SUPPORT_PCT.get(min(max(success_level, -2), 3), 100)
    else:
        pct = _PROVOKE_PCT.get(min(max(success_level, -2), 3), 100)
    return (raw_delta * pct) // 100


def apply_stance_reception(
    persona: Persona, stance: StanceArchetype, success_level: int
) -> dict[int, int]:
    """Shift every society's view of the proclaimer by alignment × roll.

    Reuses the renown dot-product (the stance row exposes the same
    ``{axis}_delta`` fields). Returns ``{society_pk: applied_delta}``.
    """
    from world.societies.models import Society  # noqa: PLC0415
    from world.societies.renown import (  # noqa: PLC0415
        _archetype_dot_product,
        bump_society_reputation,
    )

    if not persona.is_established_or_primary:
        return {}
    applied: dict[int, int] = {}
    for society in Society.objects.all():
        raw = _archetype_dot_product([stance], society)
        if raw == 0:
            continue
        delta = _scaled_reception(raw, success_level)
        if delta == 0:
            continue
        bump_society_reputation(persona, society, delta)
        applied[society.pk] = delta
    return applied


def _require_org_leadership(persona: Persona, org) -> None:
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    is_leader = OrganizationMembership.objects.filter(
        organization=org,
        persona=persona,
        left_at__isnull=True,
        exiled_at__isnull=True,
        rank__can_manage_ranks=True,
    ).exists()
    if not is_leader:
        msg = f"persona {persona.pk} may not speak for org {org.pk}"
        raise ProclamationError(
            msg, user_message="Only the organization's leadership may speak for it."
        )


@transaction.atomic
def issue_proclamation(
    persona: Persona,
    stance: StanceArchetype,
    *,
    prose: str = "",
    org=None,
    difficulty: int = 0,
) -> Proclamation:
    """Stand up and take a public position (#2842).

    Rolls oratory (closest seeded check type), applies the asymmetric
    reception to every society, and records the act. The prose rides along
    for the feed — mechanics never read it.
    """

    if org is not None:
        _require_org_leadership(persona, org)
    return _issue(persona, stance, prose=prose, org=org, difficulty=difficulty)


def _issue(
    persona: Persona,
    stance: StanceArchetype,
    *,
    prose: str,
    org,
    difficulty: int,
) -> Proclamation:
    """Ungated core — callers have already authorized the speaker."""
    from world.checks.services import perform_check_with_modifiers  # noqa: PLC0415
    from world.societies.models import Proclamation  # noqa: PLC0415

    check_type = _oratory_check_type()
    if check_type is None:
        msg = "no check types seeded; cannot roll a proclamation"
        raise ProclamationError(msg, user_message="The rhetorical arts are not yet known here.")
    result = perform_check_with_modifiers(
        persona.character_sheet.character,
        check_type,
        target_difficulty=difficulty,
    )
    apply_stance_reception(persona, stance, result.success_level)
    return Proclamation.objects.create(
        issuer=persona,
        org=org,
        stance=stance,
        prose=prose,
        check_outcome=result.outcome,
    )


@transaction.atomic
def enact_edict(
    domain: Domain, kind: EdictKind, persona: Persona, *, prose: str = ""
) -> DomainEdict:
    """Enact a standing policy: the stance is proclaimed, the payload persists.

    Requires domain authority (leader rank or the domain-steward office).
    An existing active edict is revoked — policies swap, never stack.
    """
    from world.societies.houses.models import DomainEdict  # noqa: PLC0415
    from world.societies.houses.services import can_administer_domain  # noqa: PLC0415

    if not can_administer_domain(persona, domain):
        msg = f"persona {persona.pk} may not administer domain {domain.pk}"
        raise ProclamationError(msg, user_message="You do not have authority over this domain.")
    # Domain authority (incl. the steward office) suffices here — the edict
    # gate IS the authorization; no second org-speech gate.
    proclamation = _issue(persona, kind.stance, prose=prose, org=domain.owner_org, difficulty=0)
    now = timezone.now()
    # Per-row saves, not queryset .update() — idmapper instances must see the
    # revocation (SharedMemoryModel identity map).
    for row in DomainEdict.objects.filter(domain=domain, revoked_at__isnull=True):
        row.revoked_at = now
        row.save(update_fields=["revoked_at"])
    return DomainEdict.objects.create(
        domain=domain,
        kind=kind,
        proclamation=proclamation,
        enacted_by=persona,
    )


def revoke_edict(domain: Domain, persona: Persona) -> int:
    """Rescind the active policy. Returns rows revoked (0 or 1)."""
    from world.societies.houses.models import DomainEdict  # noqa: PLC0415
    from world.societies.houses.services import can_administer_domain  # noqa: PLC0415

    if not can_administer_domain(persona, domain):
        msg = f"persona {persona.pk} may not administer domain {domain.pk}"
        raise ProclamationError(msg, user_message="You do not have authority over this domain.")
    revoked = 0
    for row in DomainEdict.objects.filter(domain=domain, revoked_at__isnull=True):
        row.revoked_at = timezone.now()
        row.save(update_fields=["revoked_at"])
        revoked += 1
    return revoked


def active_edict(domain_id: int):
    """The domain's standing policy, or None — the read seam for accrual,
    ticks, and spy reports."""
    from world.societies.houses.models import DomainEdict  # noqa: PLC0415

    return (
        DomainEdict.objects.filter(domain_id=domain_id, revoked_at__isnull=True)
        .select_related("kind")
        .first()
    )


def edict_weekly_tick() -> int:
    """Weekly rollover processor (#2842): each active edict's unrest delta
    and treasury upkeep land. A treasury that cannot pay skips the upkeep —
    the policy visibly falters rather than driving balances negative
    (PLACEHOLDER rule; no debt spiral)."""
    from world.currency.services import get_or_create_treasury  # noqa: PLC0415
    from world.societies.houses.models import DomainEdict  # noqa: PLC0415

    processed = 0
    edicts = DomainEdict.objects.filter(revoked_at__isnull=True).select_related(
        "kind", "domain__owner_org"
    )
    for edict in edicts:
        kind = edict.kind
        domain = edict.domain
        if kind.weekly_unrest_delta:
            domain.unrest = max(0, min(100, domain.unrest + kind.weekly_unrest_delta))
            domain.save(update_fields=["unrest"])
        if kind.weekly_upkeep_coppers:
            treasury = get_or_create_treasury(domain.owner_org)
            if treasury.balance >= kind.weekly_upkeep_coppers:
                treasury.balance -= kind.weekly_upkeep_coppers
                treasury.save(update_fields=["balance"])
        processed += 1
    return processed
