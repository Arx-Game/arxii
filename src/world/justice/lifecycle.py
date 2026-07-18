"""Heat lifecycle services (#1826) — lie low, bribe, pardon, wanted visibility.

The two ratified halves beyond passive decay: active clearing (each costing
something real, per the asymmetry rule) and public visibility (upper-tier heat
becomes wanted status others can see — ending display.py's self-only rule for
those tiers, and only those).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils import timezone

from world.justice.constants import (
    BRIBE_BOTCH_LEVEL,
    BRIBE_CHECK_TYPE_NAME,
    BRIBE_CLEAR_PCT,
    BRIBE_COST_PER_HEAT,
    BRIBE_PARTIAL_CLEAR_PCT,
    BRIBERY_CRIME_SCALE,
    BRIBERY_CRIME_SLUG,
    MAGISTRATE_OFFICE,
    WANTED_VALUE_FLOOR,
    tier_for_value,
)
from world.justice.models import CrimeKind, LieLowState, PardonGrant, PersonaHeat
from world.justice.services import enforcing_society_for

if TYPE_CHECKING:
    from world.areas.models import Area
    from world.scenes.models import Persona


class HeatLifecycleError(Exception):
    """A lifecycle rule was violated. Carries a safe user message."""

    def __init__(self, msg: str, *, user_message: str) -> None:
        super().__init__(msg)
        self.user_message = user_message


# ---------------------------------------------------------------------------
# Lie low
# ---------------------------------------------------------------------------


def active_lie_low(persona: Persona, area: Area) -> LieLowState | None:
    return LieLowState.objects.filter(persona=persona, area=area, ended_at__isnull=True).first()


def declare_lie_low(persona: Persona, area: Area) -> LieLowState:
    """Go to ground in ``area`` — a conscious choice, never automatic."""
    if active_lie_low(persona, area) is not None:
        msg = f"persona {persona.pk} already lying low in area {area.pk}"
        raise HeatLifecycleError(msg, user_message="You are already lying low there.")
    return LieLowState.objects.create(persona=persona, area=area)


def end_lie_low(persona: Persona, area: Area) -> LieLowState | None:
    """Voluntarily surface. Returns the ended state, or None if none active."""
    state = active_lie_low(persona, area)
    if state is None:
        return None
    state.ended_at = timezone.now()
    state.save(update_fields=["ended_at"])
    return state


def break_lie_low_for_ic_action(persona: Persona, area: Area | None) -> None:
    """IC action in the area surfaces the persona — the state breaks.

    Called from the interaction-recording seam and from heat accrual. Cheap
    no-op when nothing is active (the overwhelmingly common case).
    """
    if area is None:
        return
    state = active_lie_low(persona, area)
    if state is not None:
        state.ended_at = timezone.now()
        state.save(update_fields=["ended_at"])


def lie_low_extra_decay(*, base_decay: int, multiplier: int) -> int:
    """Extra decay applied on top of the daily base for active lie-low rows."""
    return max(0, (multiplier - 1) * base_decay)


def crime_collection_malus_applies(organization, area: Area | None) -> bool:
    """Whether a CRIME_KICKUP stream in ``area`` misses a lying-low member.

    True when any active member persona of ``organization`` is currently lying
    low in that area — their rackets run short-handed (#1826).
    """
    if area is None:
        return False
    return LieLowState.objects.filter(
        area=area,
        ended_at__isnull=True,
        persona__organization_memberships__organization=organization,
        persona__organization_memberships__left_at__isnull=True,
        persona__organization_memberships__exiled_at__isnull=True,
    ).exists()


# ---------------------------------------------------------------------------
# Bribe
# ---------------------------------------------------------------------------


def bribe_cost_for(persona: Persona, area: Area) -> int:
    """Coin cost of a bribe approach: scales with current heat there."""
    total = sum(row.value for row in PersonaHeat.objects.filter(persona=persona, area=area))
    return max(BRIBE_COST_PER_HEAT, total * BRIBE_COST_PER_HEAT)


def attempt_bribe(persona: Persona, area: Area) -> dict:
    """Bribe the hunters: coin sink + check; the botch band mints a crime.

    Bands (PLACEHOLDER percentages): success clears ``BRIBE_CLEAR_PCT``% of
    each heat row there; partial (success_level == 0) clears
    ``BRIBE_PARTIAL_CLEAR_PCT``%; failure clears nothing (half the coin is
    spent anyway — the approach cost); the botch band additionally mints a
    ``bribery`` crime with its own heat.
    """
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.checks.services import perform_check  # noqa: PLC0415
    from world.currency.services import get_or_create_purse  # noqa: PLC0415
    from world.justice.services import accrue_heat  # noqa: PLC0415

    rows = list(PersonaHeat.objects.filter(persona=persona, area=area, value__gt=0))
    if not rows:
        msg = f"persona {persona.pk} has no heat in area {area.pk}"
        raise HeatLifecycleError(msg, user_message="No one is hunting you there.")

    sheet = persona.character_sheet
    character = sheet.character if sheet is not None else None
    if character is None:
        msg = f"persona {persona.pk} has no character for the bribe check"
        raise HeatLifecycleError(msg, user_message="You cannot attempt that now.")

    check_type = CheckType.objects.filter(name=BRIBE_CHECK_TYPE_NAME).first()
    if check_type is None:
        msg = f"check type '{BRIBE_CHECK_TYPE_NAME}' is not seeded"
        raise HeatLifecycleError(msg, user_message="The hunters cannot be approached yet.")

    cost = bribe_cost_for(persona, area)
    purse = get_or_create_purse(persona.character_sheet)
    if purse.balance < cost:
        msg = f"purse {purse.pk} below bribe cost {cost}"
        raise HeatLifecycleError(msg, user_message="You cannot afford that bribe.")

    result = perform_check(character, check_type)
    level = result.outcome.success_level if result.outcome else 0

    if level > 0:
        clear_pct, spent = BRIBE_CLEAR_PCT, cost
    elif level == 0:
        clear_pct, spent = BRIBE_PARTIAL_CLEAR_PCT, cost
    else:
        clear_pct, spent = 0, cost // 2

    purse.balance -= spent
    purse.save(update_fields=["balance"])

    for row in rows:
        row.value = max(0, row.value - (row.value * clear_pct) // 100)
        row.save(update_fields=["value"])
    PersonaHeat.objects.filter(persona=persona, area=area, value=0).delete()

    crime_minted = False
    if level <= BRIBE_BOTCH_LEVEL:
        kind, _ = CrimeKind.objects.get_or_create(
            slug=BRIBERY_CRIME_SLUG, defaults={"name": "Bribery"}
        )
        accrue_heat(persona=persona, crime_kind=kind, area=area, scale=BRIBERY_CRIME_SCALE)
        crime_minted = True

    return {
        "success_level": level,
        "cleared_pct": clear_pct,
        "coin_spent": spent,
        "crime_minted": crime_minted,
    }


# ---------------------------------------------------------------------------
# Pardon
# ---------------------------------------------------------------------------


def can_pardon(granter: Persona, area: Area) -> bool:
    """Pardon power: the enforcing society's magistrate office or org leadership."""
    from world.societies.houses.services import is_org_leader  # noqa: PLC0415
    from world.societies.models import Organization  # noqa: PLC0415
    from world.societies.office_services import holds_office  # noqa: PLC0415

    society = enforcing_society_for(area)
    if society is None:
        return False
    orgs = Organization.objects.filter(society=society)
    return any(
        holds_office(granter, org, MAGISTRATE_OFFICE) or is_org_leader(granter, org) for org in orgs
    )


def pardon_persona(granter: Persona, target: Persona, area: Area) -> PardonGrant:
    """A lord's grant: zero the target's warrant with the enforcing society."""
    society = enforcing_society_for(area)
    if society is None:
        msg = f"area {area.pk} has no enforcing society"
        raise HeatLifecycleError(msg, user_message="No power enforces law there.")
    if not can_pardon(granter, area):
        msg = f"persona {granter.pk} lacks pardon power in area {area.pk}"
        raise HeatLifecycleError(msg, user_message="You do not hold the power of pardon there.")
    rows = PersonaHeat.objects.filter(persona=target, area=area, society=society)
    cleared = sum(row.value for row in rows)
    rows.delete()
    return PardonGrant.objects.create(
        granter_persona=granter,
        target_persona=target,
        area=area,
        society=society,
        heat_cleared=cleared,
    )


# ---------------------------------------------------------------------------
# Wanted visibility
# ---------------------------------------------------------------------------


def wanted_rows_for_area(area: Area) -> list[dict]:
    """Publicly visible warrants in ``area`` — tier + presented name, never numbers.

    Only rows at/above ``WANTED_VALUE_FLOOR`` flip public (the deliberate end
    of self-only visibility for the top tiers). Crime kinds come from the
    warrant's sourced deeds where tagged.
    """
    rows = (
        PersonaHeat.objects.filter(area=area, value__gte=WANTED_VALUE_FLOOR)
        .select_related("persona", "society")
        .order_by("-value")
    )
    out = []
    for row in rows:
        crime_names = list(
            CrimeKind.objects.filter(deed_tags__deed__heat_sources__heat=row)
            .values_list("name", flat=True)
            .distinct()
        )
        out.append(
            {
                "persona_name": row.persona.name,
                "tier": tier_for_value(row.value),
                "society_name": row.society.name,
                "crimes": crime_names,
            }
        )
    return out
