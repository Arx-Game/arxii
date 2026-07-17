"""DomainCrisis lifecycle services (#2238) — open, judge, resolve.

The crisis loop's read-and-resolve half. Creation routes through
``open_crisis`` (both system spawners and staff); the administrator's judgment
call routes through ``choose_crisis_option``; the weekly ``crisis_wait_tick``
rolls only crises whose *chosen* option is WAIT (the conscious-ignore rule —
an unjudged crisis never worsens, per the AFK-protection ruling).
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from django.utils import timezone

from world.societies.houses.constants import (
    CrisisOrigin,
    CrisisResolution,
    CrisisResolutionKind,
    DomainCrisisSeverity,
)
from world.societies.houses.models import (
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


def pick_crisis_type(origin: str, *, rng: random.Random | None = None) -> DomainCrisisType | None:
    """Weighted pick among automated types eligible for this origin's pool."""
    pool = _SPAWN_POOLS.get(origin, ())
    candidates = list(DomainCrisisType.objects.filter(automated=True, default_severity__in=pool))
    if not candidates:
        return None
    rng = rng or random
    weights = [c.spawn_weight for c in candidates]
    return rng.choices(candidates, weights=weights, k=1)[0]


def open_crisis(
    domain: Domain,
    *,
    origin: str,
    crisis_type: DomainCrisisType | None = None,
    description: str = "",
    rng: random.Random | None = None,
) -> DomainCrisis | None:
    """Open a crisis on ``domain``; the single creation seam for all origins.

    Automated origins pick an eligible type when none is given (a typeless
    automated crisis would offer no options — dead content). Auto-mint rule:
    an AUTOMATED-origin crisis whose type offers exactly one option, and it is
    MISSION, has no judgment to make — the mission path goes live at creation
    (``chosen_option`` pre-set; the run itself starts when a member accepts).
    STAFF-origin crises never auto-choose anything.
    """
    if domain.crises.filter(resolved_at__isnull=True).exists():
        return None
    if crisis_type is None and origin != CrisisOrigin.STAFF:
        crisis_type = pick_crisis_type(origin, rng=rng)
    severity = crisis_type.default_severity if crisis_type else DomainCrisisSeverity.TROUBLE
    crisis = DomainCrisis.objects.create(
        domain=domain,
        severity=severity,
        description=description or (crisis_type.description if crisis_type else ""),
        crisis_type=crisis_type,
        origin=origin,
    )
    if origin != CrisisOrigin.STAFF and crisis_type is not None:
        options = list(crisis_type.options.all())
        if len(options) == 1 and options[0].kind == CrisisResolutionKind.MISSION:
            crisis.chosen_option = options[0]
            crisis.chosen_at = timezone.now()
            crisis.save(update_fields=["chosen_option", "chosen_at"])
    return crisis


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


def _require_administrator(persona: Persona, domain: Domain) -> None:
    from world.societies.houses.services import can_administer_domain  # noqa: PLC0415

    if not can_administer_domain(persona, domain):
        msg = f"persona {persona.pk} may not administer domain {domain.pk}"
        raise CrisisServiceError(msg, user_message="You do not have authority over this domain.")


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
    _require_administrator(persona, crisis.domain)

    if option.kind == CrisisResolutionKind.PAY:
        _pay_off(crisis, persona, option)
        return crisis

    crisis.chosen_option = option
    crisis.chosen_at = timezone.now()
    crisis.save(update_fields=["chosen_option", "chosen_at"])
    return crisis


def _pay_off(crisis: DomainCrisis, persona: Persona, option: DomainCrisisTypeOption) -> None:
    from world.currency.services import (  # noqa: PLC0415
        can_spend_treasury,
        get_or_create_treasury,
    )

    org = crisis.domain.owner_org
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
    return crisis


def crisis_wait_tick(*, rng: random.Random | None = None) -> int:
    """Weekly roll for crises whose CHOSEN option is WAIT (conscious ignore only).

    Self-resolve wins the tie (help before harm). Worsening bumps severity one
    step on the same row; at CATASTROPHE there is no further step — the roll
    is a no-op (no fourth tier, per ruling).
    """
    rng = rng or random
    processed = 0
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
