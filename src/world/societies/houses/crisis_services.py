"""DomainCrisis lifecycle services (#2238) — open, judge, resolve.

The crisis loop's read-and-resolve half. Creation routes through
``open_crisis`` (both system spawners and staff); the administrator's judgment
call routes through ``choose_crisis_option``; the weekly ``crisis_wait_tick``
rolls only crises whose *chosen* option is WAIT (the conscious-ignore rule —
an unjudged crisis never worsens, per the AFK-protection ruling).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
import random
from typing import TYPE_CHECKING

from django.db import models
from django.utils import timezone

from world.societies.houses.constants import (
    AMBIENT_DOMAIN_OPPORTUNITY_PCT,
    AMBIENT_DOMAIN_THREAT_PCT,
    AMBIENT_ORG_OPPORTUNITY_PCT,
    AMBIENT_ORG_THREAT_PCT,
    COVERT_WINDOW_DAYS,
    OPPORTUNITY_BOON_COPPERS,
    OPPORTUNITY_LIFETIME_DAYS,
    OPPORTUNITY_PROSPERITY_BOON,
    CrisisAudience,
    CrisisOrigin,
    CrisisResolution,
    CrisisResolutionKind,
    CrisisValence,
    DomainCrisisSeverity,
    StatureShiftCause,
)
from world.societies.houses.models import (
    CrisisIntel,
    Domain,
    DomainCrisis,
    DomainCrisisType,
    DomainCrisisTypeOption,
)

if TYPE_CHECKING:
    from world.scenes.models import Persona

# PAY cost scales with severity (PLACEHOLDER multipliers).
_PAY_SEVERITY_MULT: dict[str, int] = {
    DomainCrisisSeverity.TROUBLE: 1,
    DomainCrisisSeverity.CRISIS: 2,
    DomainCrisisSeverity.CATASTROPHE: 4,
}

# Which authored severities each spawner draws from (PLACEHOLDER pools).
_SPAWN_POOLS: dict[str, tuple[str, ...]] = {
    CrisisOrigin.IMPROVEMENT: (DomainCrisisSeverity.TROUBLE, DomainCrisisSeverity.CRISIS),
    CrisisOrigin.UNREST: (DomainCrisisSeverity.TROUBLE, DomainCrisisSeverity.CRISIS),
    CrisisOrigin.AMBIENT: (DomainCrisisSeverity.TROUBLE, DomainCrisisSeverity.CRISIS),
    # Predator raids draw the whole ladder — the band's stage sets the final
    # severity after open (#3093).
    CrisisOrigin.PREDATOR: (
        DomainCrisisSeverity.TROUBLE,
        DomainCrisisSeverity.CRISIS,
        DomainCrisisSeverity.CATASTROPHE,
    ),
}

_SEVERITY_ORDER: tuple[str, ...] = (
    DomainCrisisSeverity.TROUBLE,
    DomainCrisisSeverity.CRISIS,
    DomainCrisisSeverity.CATASTROPHE,
)


class CrisisServiceError(Exception):
    """A crisis lifecycle rule was violated. Carries a safe user message."""

    def __init__(self, msg: str, *, user_message: str) -> None:
        super().__init__(msg)
        self.user_message = user_message


def pick_crisis_type(
    origin: str,
    *,
    audiences: Sequence[str] = (CrisisAudience.DOMAIN,),
    valence: str = CrisisValence.THREAT,
    rng: random.Random | None = None,
) -> DomainCrisisType | None:
    """Weighted pick among automated types eligible for this origin's pool."""
    pool = _SPAWN_POOLS.get(origin, ())
    candidates = list(
        DomainCrisisType.objects.filter(
            automated=True,
            default_severity__in=pool,
            audience__in=audiences,
            valence=valence,
        )
    )
    if not candidates:
        return None
    rng = rng or random
    weights = [c.spawn_weight for c in candidates]
    return rng.choices(candidates, weights=weights, k=1)[0]


def open_crisis(  # noqa: PLR0913 — one target pair + the existing authoring knobs
    domain: Domain | None = None,
    *,
    org=None,
    origin: str,
    crisis_type: DomainCrisisType | None = None,
    description: str = "",
    rng: random.Random | None = None,
) -> DomainCrisis | None:
    """Open a crisis on ``domain`` OR ``org``; the single creation seam.

    Automated origins pick an eligible type when none is given (a typeless
    automated crisis would offer no options — dead content). Auto-mint rule:
    an AUTOMATED-origin crisis whose type offers exactly one option, and it is
    MISSION, has no judgment to make — the mission path goes live at creation
    (``chosen_option`` pre-set; the run itself starts when a member accepts).
    STAFF-origin crises never auto-choose anything.

    One open crisis per (target, valence) — a domain can nurse a threat and an
    opportunity at once, never two of a kind (#2837). Generated (non-staff)
    crises stay covert for ``COVERT_WINDOW_DAYS`` before surfacing.
    """
    if (domain is None) == (org is None):
        msg = "open_crisis takes exactly one of domain/org"
        raise CrisisServiceError(msg, user_message="Invalid crisis target.")
    if crisis_type is None and origin != CrisisOrigin.STAFF:
        audiences = [CrisisAudience.DOMAIN] if domain is not None else _org_audiences(org)
        crisis_type = pick_crisis_type(origin, audiences=audiences, rng=rng)
    valence = crisis_type.valence if crisis_type else CrisisValence.THREAT
    open_of_kind = DomainCrisis.objects.filter(
        domain=domain, org=org, resolved_at__isnull=True
    ).select_related("crisis_type")
    if any(c.valence == valence for c in open_of_kind):
        return None
    severity = crisis_type.default_severity if crisis_type else DomainCrisisSeverity.TROUBLE
    if origin == CrisisOrigin.STAFF:
        surfaces_at = None
    else:
        surfaces_at = timezone.now() + timedelta(days=COVERT_WINDOW_DAYS)
    crisis = DomainCrisis.objects.create(
        domain=domain,
        org=org,
        severity=severity,
        description=description or (crisis_type.description if crisis_type else ""),
        crisis_type=crisis_type,
        origin=origin,
        surfaces_at=surfaces_at,
    )
    _maybe_auto_mint_mission(crisis, origin, crisis_type)
    if crisis.valence == CrisisValence.THREAT:
        # #3091 — blood in the water: an open threat drags the target's true
        # stature now (perceived only once it is public; covert window holds).
        from world.societies.houses.stature_services import crisis_stature_shift  # noqa: PLC0415

        crisis_stature_shift(crisis, cause=StatureShiftCause.CRISIS_OPENED)
    return crisis


def _maybe_auto_mint_mission(
    crisis: DomainCrisis, origin: str, crisis_type: DomainCrisisType | None
) -> None:
    """Pre-set the single MISSION option on an automated crisis with no judgment to make.

    A STAFF-origin crisis never auto-chooses; neither does a typeless one, nor
    one whose type offers a real menu.
    """
    if origin == CrisisOrigin.STAFF or crisis_type is None:
        return
    options = list(crisis_type.options.all())
    if len(options) != 1 or options[0].kind != CrisisResolutionKind.MISSION:
        return
    crisis.chosen_option = options[0]
    crisis.chosen_at = timezone.now()
    crisis.save(update_fields=["chosen_option", "chosen_at"])


def pay_cost_for(crisis: DomainCrisis, option: DomainCrisisTypeOption) -> int:
    """Severity-scaled PAY cost in coppers."""
    return option.cost_coppers * _PAY_SEVERITY_MULT.get(crisis.severity, 1)


def crisis_options(crisis: DomainCrisis) -> list[dict]:
    """The judgment-call menu: options with computed costs, for serializers."""
    if crisis.crisis_type is None:
        return []
    return [
        {
            "id": option.pk,
            "kind": option.kind,
            "cost_coppers": (
                pay_cost_for(crisis, option) if option.kind == CrisisResolutionKind.PAY else 0
            ),
            "mission_template_id": option.mission_template_id,
            "self_resolve_pct": option.self_resolve_pct,
            "worsen_pct": option.worsen_pct,
        }
        for option in crisis.crisis_type.options.all()
    ]


def _org_audiences(org) -> list[str]:
    """Which type audiences an org-target draw includes (#2837)."""
    from world.currency.constants import IncomeStreamKind  # noqa: PLC0415

    criminal = bool(org.org_type_id is not None and org.org_type.is_covert) or (
        org.income_streams.filter(active=True, kind=IncomeStreamKind.CRIME_KICKUP).exists()
    )
    if criminal:
        return [CrisisAudience.ORG, CrisisAudience.CRIMINAL_ORG]
    return [CrisisAudience.ORG]


def _can_lead_org(persona: Persona, org) -> bool:
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    return OrganizationMembership.objects.filter(
        organization=org,
        persona=persona,
        left_at__isnull=True,
        exiled_at__isnull=True,
        rank__can_manage_ranks=True,
    ).exists()


def can_judge_crisis(persona: Persona, crisis: DomainCrisis) -> bool:
    """Boolean face of the judgment gate, for viewset persona resolution."""
    try:
        _require_administrator(persona, crisis)
    except CrisisServiceError:
        return False
    return True


def _require_administrator(persona: Persona, crisis: DomainCrisis) -> None:
    from world.societies.houses.services import can_administer_domain  # noqa: PLC0415

    if crisis.domain_id is not None:
        if can_administer_domain(persona, crisis.domain):
            return
        msg = f"persona {persona.pk} may not administer domain {crisis.domain_id}"
        raise CrisisServiceError(msg, user_message="You do not have authority over this domain.")
    if not _can_lead_org(persona, crisis.org):
        msg = f"persona {persona.pk} may not lead org {crisis.org_id}"
        raise CrisisServiceError(
            msg, user_message="You do not have authority over this organization."
        )


def choose_crisis_option(
    crisis: DomainCrisis, persona: Persona, option: DomainCrisisTypeOption
) -> DomainCrisis:
    """The administrator's judgment call — PAY resolves now, MISSION/WAIT commit."""
    if crisis.resolved_at is not None:
        msg = f"crisis {crisis.pk} is already resolved"
        raise CrisisServiceError(msg, user_message="That crisis is already resolved.")
    if crisis.chosen_option_id is not None:
        msg = f"crisis {crisis.pk} already has a chosen option"
        raise CrisisServiceError(
            msg, user_message="A course has already been chosen for that crisis."
        )
    if option.crisis_type_id != crisis.crisis_type_id:
        msg = f"option {option.pk} does not belong to crisis {crisis.pk}'s type"
        raise CrisisServiceError(msg, user_message="That option does not apply here.")
    _require_administrator(persona, crisis)

    if option.kind == CrisisResolutionKind.PAY:
        _pay_off(crisis, persona, option)
        return crisis

    crisis.chosen_option = option
    crisis.chosen_at = timezone.now()
    update_fields = ["chosen_option", "chosen_at"]
    if option.kind == CrisisResolutionKind.MISSION:
        # #2837: the MISSION path actually mints now (was BUILT, NOT WIRED —
        # `minted_mission` had no production writer, so
        # `resolve_crisis_for_mission` could never match).
        from world.missions.services.run import staff_assign_mission  # noqa: PLC0415

        instance = staff_assign_mission(
            option.mission_template,
            persona.character_sheet.character,
            persona=persona,
        )
        crisis.minted_mission = instance
        update_fields.append("minted_mission")
    crisis.save(update_fields=update_fields)
    return crisis


def _pay_off(crisis: DomainCrisis, persona: Persona, option: DomainCrisisTypeOption) -> None:
    from world.currency.services import (  # noqa: PLC0415
        can_spend_treasury,
        get_or_create_treasury,
    )

    org = crisis.target_org
    treasury = get_or_create_treasury(org)
    cost = pay_cost_for(crisis, option)
    if not can_spend_treasury(treasury, persona):
        msg = f"persona {persona.pk} may not spend treasury of org {org.pk}"
        raise CrisisServiceError(msg, user_message="You cannot spend this house's treasury.")
    if treasury.balance < cost:
        msg = f"treasury {treasury.pk} balance below crisis cost {cost}"
        raise CrisisServiceError(msg, user_message="The house treasury cannot cover that cost.")
    treasury.balance -= cost
    treasury.save(update_fields=["balance"])
    resolve_crisis(crisis, resolution=CrisisResolution.PAID)


def resolve_crisis(crisis: DomainCrisis, *, resolution: str) -> DomainCrisis:
    """Stamp a crisis resolved. Idempotent-hostile: raises on double-resolve."""
    if crisis.resolved_at is not None:
        msg = f"crisis {crisis.pk} is already resolved"
        raise CrisisServiceError(msg, user_message="That crisis is already resolved.")
    crisis.resolution = resolution
    crisis.resolved_at = timezone.now()
    crisis.save(update_fields=["resolution", "resolved_at"])
    if crisis.valence == CrisisValence.THREAT:
        # #3091 — the drag lifts the moment the threat is dealt with.
        from world.societies.houses.stature_services import crisis_stature_shift  # noqa: PLC0415

        crisis_stature_shift(crisis, cause=StatureShiftCause.CRISIS_RESOLVED)
    if crisis.aggressor_band_id is not None and resolution in (
        CrisisResolution.MISSION_COMPLETED,
        CrisisResolution.TASK_COMPLETED,
        CrisisResolution.PAID,
    ):
        # #3093 — answering a raid answers the BAND: strength burns, the
        # menace ladder falls back. (Waiting it out answers nothing.)
        from world.predators.services import strike_band  # noqa: PLC0415

        strike_band(crisis.aggressor_band)
    return crisis


def crisis_wait_tick(*, rng: random.Random | None = None) -> int:
    """Weekly roll for crises whose CHOSEN option is WAIT (conscious ignore only).

    Self-resolve wins the tie (help before harm). Worsening bumps severity one
    step on the same row; at CATASTROPHE there is no further step — the roll
    is a no-op (no fourth tier, per ruling).
    """
    rng = rng or random
    processed = 0
    # Opportunities are windows, not wounds: they close on schedule whether or
    # not anyone judged them (#2837) — the AFK-protection ruling covers harm,
    # and an expired windfall harms nobody.
    cutoff = timezone.now() - timedelta(days=OPPORTUNITY_LIFETIME_DAYS)
    stale = DomainCrisis.objects.filter(
        resolved_at__isnull=True,
        opened_at__lt=cutoff,
        crisis_type__valence=CrisisValence.OPPORTUNITY,
    )
    for opportunity in stale:
        resolve_crisis(opportunity, resolution=CrisisResolution.EXPIRED)
        processed += 1
    crises = DomainCrisis.objects.filter(
        resolved_at__isnull=True,
        chosen_option__kind=CrisisResolutionKind.WAIT,
    ).select_related("chosen_option")
    for crisis in crises:
        option = crisis.chosen_option
        roll = rng.random() * 100
        if roll < option.self_resolve_pct:
            resolve_crisis(crisis, resolution=CrisisResolution.SELF_RESOLVED)
        elif roll < option.self_resolve_pct + option.worsen_pct:
            idx = _SEVERITY_ORDER.index(crisis.severity)
            if idx + 1 < len(_SEVERITY_ORDER):
                crisis.severity = _SEVERITY_ORDER[idx + 1]
                crisis.save(update_fields=["severity"])
        processed += 1
    return processed


def resolve_crisis_for_mission(instance) -> DomainCrisis | None:
    """Mission-completion hook: a successful run resolves its source crisis."""
    crisis = (
        DomainCrisis.objects.filter(minted_mission=instance, resolved_at__isnull=True)
        .select_related("domain")
        .first()
    )
    if crisis is None:
        return None
    return resolve_crisis(crisis, resolution=CrisisResolution.MISSION_COMPLETED)


def crisis_generation_tick(*, rng: random.Random | None = None) -> int:
    """Weekly ambient spawner (#2837) — the loop's content pump.

    Rolls each domain for a threat and an opportunity, then each eligible
    org (one with active income streams, or a covert org type — the
    player-run enterprises worth scheming about). ``open_crisis`` enforces
    one-open-per-(target, valence), so a busy target just misses the roll.
    """
    from world.currency.models import OrgIncomeStream  # noqa: PLC0415
    from world.societies.models import Organization  # noqa: PLC0415

    rng = rng or random
    opened = 0
    for domain in Domain.objects.select_related("owner_org"):
        threat_pct = AMBIENT_DOMAIN_THREAT_PCT * _threat_multiplier(domain.owner_org)
        if rng.random() * 100 < threat_pct:
            opened += open_crisis(domain, origin=CrisisOrigin.AMBIENT, rng=rng) is not None
        if rng.random() * 100 < AMBIENT_DOMAIN_OPPORTUNITY_PCT:
            opened += (
                _open_generated(domain=domain, valence=CrisisValence.OPPORTUNITY, rng=rng)
                is not None
            )
    stream_org_ids = set(
        OrgIncomeStream.objects.filter(active=True).values_list("organization_id", flat=True)
    )
    orgs = Organization.objects.filter(
        models.Q(pk__in=stream_org_ids) | models.Q(org_type__is_covert=True)
    ).distinct()
    for org in orgs:
        if rng.random() * 100 < AMBIENT_ORG_THREAT_PCT * _threat_multiplier(org):
            opened += _open_generated(org=org, valence=CrisisValence.THREAT, rng=rng) is not None
        if rng.random() * 100 < AMBIENT_ORG_OPPORTUNITY_PCT:
            opened += (
                _open_generated(org=org, valence=CrisisValence.OPPORTUNITY, rng=rng) is not None
            )
    return opened


def _threat_multiplier(org) -> float:
    """Predators probe the weak (#3091): the target's band scales threat odds.

    No stature row or band yet means neutral 1.0 — the loop degrades to the
    flat ambient chances for unbanded orgs.
    """
    from world.societies.houses.models import HouseStature  # noqa: PLC0415

    if org is None:
        return 1.0
    stature = HouseStature.objects.filter(organization=org).select_related("band").first()
    if stature is None or stature.band is None:
        return 1.0
    return float(stature.band.threat_multiplier)


def _open_generated(
    *,
    domain: Domain | None = None,
    org=None,
    valence: str,
    rng: random.Random,
) -> DomainCrisis | None:
    """Ambient open with an explicit valence draw (open_crisis defaults to threat)."""
    audiences = [CrisisAudience.DOMAIN] if domain is not None else _org_audiences(org)
    crisis_type = pick_crisis_type(
        CrisisOrigin.AMBIENT, audiences=audiences, valence=valence, rng=rng
    )
    if crisis_type is None:
        return None
    return open_crisis(
        domain, org=org, origin=CrisisOrigin.AMBIENT, crisis_type=crisis_type, rng=rng
    )


def grant_crisis_intel(crisis: DomainCrisis, org, *, source: str) -> tuple[CrisisIntel, bool]:
    """An org learns of a crisis early (#2837). Idempotent per (crisis, org)."""
    return CrisisIntel.objects.get_or_create(crisis=crisis, org=org, defaults={"source": source})


def org_knows_of(crisis: DomainCrisis, org) -> bool:
    """Visibility rule: surfaced, yours, or sweated for (#2837)."""
    if crisis.is_surfaced:
        return True
    return CrisisIntel.objects.filter(crisis=crisis, org=org).exists()


def apply_crisis_boon(crisis: DomainCrisis, acting_org) -> str:
    """Pay whoever seized/exploited the event, by magnitude (#2837).

    The domain's own house seizing its own opportunity takes prosperity; any
    other seizure (rival exploit, org-target event) pays coppers into the
    acting org's treasury. PLACEHOLDER magnitudes.
    """
    from world.currency.services import get_or_create_treasury  # noqa: PLC0415

    if (
        crisis.domain_id is not None
        and crisis.valence == CrisisValence.OPPORTUNITY
        and acting_org.pk == crisis.domain.owner_org_id
    ):
        boon = OPPORTUNITY_PROSPERITY_BOON.get(crisis.severity, 0)
        crisis.domain.prosperity = min(100, crisis.domain.prosperity + boon)
        crisis.domain.save(update_fields=["prosperity"])
        return f"Prosperity blooms in {crisis.domain.name}."
    coppers = OPPORTUNITY_BOON_COPPERS.get(crisis.severity, 0)
    treasury = get_or_create_treasury(acting_org)
    treasury.balance += coppers
    treasury.save(update_fields=["balance"])
    return f"The venture pays {coppers} coppers into the coffers."


def org_crisis_income_factor(org) -> float:
    """The worst open, surfaced org-target threat's malus (#2837); 1.0 clean.

    Domain-target crises already bite through ``Domain.income_multiplier`` —
    this is the org-leg symmetry, applied at weekly stream accrual.
    """
    factors = [
        crisis.income_factor
        for crisis in DomainCrisis.objects.filter(org=org, resolved_at__isnull=True)
    ]
    return min(factors, default=1.0)
