"""Renown system services (#676 Phases A + B).

Phase A: fame tier derivation, persona-fame decay, organization-prestige
decay primitives + cron sweep entry points.

Phase B: renown event firing — bundle authored content (Magnitude / Risk /
PhilosophicalArchetypes / Reach) into a single ``fire_renown_award`` call
that writes prestige_from_deeds, fame_points, legend, and per-society
reputation deltas through the existing infrastructure (LegendEntry +
SocietyReputation + the new Persona fields from Phase A).

Subsequent phases extend this module with: org-inflow + persona-outflow
plumbing (Phase C), source-prestige-recompute helpers for dwellings/items
(Phases D/F).

The cron-driven decay sweep lives in ``world.societies.tasks`` and calls
the per-row decay functions defined here.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
import logging

from django.db import transaction

from world.scenes.models import Persona
from world.societies.constants import (
    FAME_DECAY_FLAT,
    FAME_DECAY_PCT,
    FAME_TIER_MULTIPLIERS,
    FAME_TIER_ORDER,
    FAME_TIER_THRESHOLDS,
    MAGNITUDE_FAME_AWARDS,
    MAGNITUDE_PRESTIGE_AWARDS,
    MAGNITUDE_TO_DEFAULT_REACH,
    ORG_FAME_DECAY_FLAT,
    ORG_FAME_DECAY_PCT,
    ORG_PRESTIGE_DECAY_FLAT,
    ORG_PRESTIGE_DECAY_PCT,
    PRINCIPLE_FIELD_NAMES,
    RISK_LEGEND_AWARDS,
    FameTier,
    RenownReach,
)
from world.societies.models import Organization

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fame tier derivation
# ---------------------------------------------------------------------------


def derive_fame_tier(fame_points: int) -> str:
    """Return the highest fame-tier name whose threshold is ≤ ``fame_points``.

    Walks ``FAME_TIER_ORDER`` from highest threshold down; first match wins.
    Returns the bare string value (``FameTier.NORMAL.value`` etc.) so callers
    can assign directly to ``persona.fame_tier`` without wrapping.
    """
    for tier_name in reversed(FAME_TIER_ORDER):
        if fame_points >= FAME_TIER_THRESHOLDS[tier_name]:
            return tier_name
    return FameTier.NORMAL.value


def fame_multiplier_for(fame_tier: str) -> float:
    """Look up the prestige-display multiplier for a fame tier."""
    return FAME_TIER_MULTIPLIERS[fame_tier]


def set_persona_fame(persona: Persona, new_fame_points: int) -> bool:
    """Write a new ``fame_points`` value and recompute ``fame_tier``.

    Returns True iff ``fame_tier`` changed (callers can hook tier-change
    notifications). ``new_fame_points`` is floored at 0 — fame is a
    non-negative buffer; negative buzz is captured via Reputation, not Fame.
    """
    floored = max(0, new_fame_points)
    new_tier = derive_fame_tier(floored)
    tier_changed = new_tier != persona.fame_tier
    persona.fame_points = floored
    persona.fame_tier = new_tier
    persona.save(update_fields=["fame_points", "fame_tier"])
    return tier_changed


# ---------------------------------------------------------------------------
# Fame decay (per-row primitive)
#
# Formula: new = max(0, old - FLAT - PCT * old)
#
# Per IC day cadence (cron interval in tasks.py is 8 real hours, matching
# the canonical 3:1 IC:OOC time ratio). The percentage term dominates at
# high fame; the flat term drains the residue at low fame.
# ---------------------------------------------------------------------------


def apply_persona_fame_decay(persona: Persona) -> bool:
    """Apply one tick of fame decay to ``persona``. Returns True iff tier changed.

    No-op for personas at ``fame_points == 0``.
    """
    if persona.fame_points <= 0:
        return False
    decayed = persona.fame_points - FAME_DECAY_FLAT - int(persona.fame_points * FAME_DECAY_PCT)
    return set_persona_fame(persona, decayed)


# ---------------------------------------------------------------------------
# Org accumulated-value decay
#
# accumulated_prestige and accumulated_fame decay each tick. accumulated_legend
# on covenants is permanent — NEVER touched by this function.
# ---------------------------------------------------------------------------


def apply_org_accumulated_decay(org: Organization) -> tuple[int, int]:
    """Apply one tick of decay to org accumulated_prestige + accumulated_fame.

    Returns a tuple of (new_accumulated_prestige, new_accumulated_fame).
    Floors at 0. Does NOT touch ``base_prestige`` (permanent) or
    ``accumulated_legend`` (permanent, covenant-only).
    """
    update_fields: list[str] = []
    new_prestige = org.accumulated_prestige
    if new_prestige > 0:
        new_prestige = max(
            0,
            new_prestige - ORG_PRESTIGE_DECAY_FLAT - int(new_prestige * ORG_PRESTIGE_DECAY_PCT),
        )
        if new_prestige != org.accumulated_prestige:
            org.accumulated_prestige = new_prestige
            update_fields.append("accumulated_prestige")
    new_fame = org.accumulated_fame
    if new_fame > 0:
        new_fame = max(
            0,
            new_fame - ORG_FAME_DECAY_FLAT - int(new_fame * ORG_FAME_DECAY_PCT),
        )
        if new_fame != org.accumulated_fame:
            org.accumulated_fame = new_fame
            update_fields.append("accumulated_fame")
    if update_fields:
        org.save(update_fields=update_fields)
    return new_prestige, new_fame


# ---------------------------------------------------------------------------
# Cron sweep entrypoints (called by world.societies.tasks)
# ---------------------------------------------------------------------------


@transaction.atomic
def decay_all_persona_fame() -> int:
    """Apply fame decay to every persona with positive fame. Returns count touched.

    Single transaction so a mid-sweep failure doesn't half-apply. Iterates
    only personas with ``fame_points > 0`` — avoids the no-op walk for the
    vast majority of personas at default state.
    """
    touched = 0
    for persona in Persona.objects.filter(fame_points__gt=0).iterator():
        apply_persona_fame_decay(persona)
        touched += 1
    logger.info("renown.fame_decay: applied to %d personas", touched)
    return touched


@transaction.atomic
def decay_all_org_accumulated() -> int:
    """Apply accumulated-prestige + accumulated-fame decay to every org with positive accumulation.

    Single transaction. Iterates only orgs with either accumulated value > 0.
    Does NOT touch covenants' accumulated_legend.
    """
    from django.db.models import Q  # noqa: PLC0415

    touched = 0
    for org in Organization.objects.filter(
        Q(accumulated_prestige__gt=0) | Q(accumulated_fame__gt=0)
    ).iterator():
        apply_org_accumulated_decay(org)
        touched += 1
    logger.info("renown.org_accumulated_decay: applied to %d organizations", touched)
    return touched


# ---------------------------------------------------------------------------
# Phase B — renown event firing
#
# ``fire_renown_award`` bundles authored content (Magnitude / Risk /
# PhilosophicalArchetypes / Reach) into a single call that writes through
# every renown axis at once. Idempotency is NOT promised — each call
# applies its deltas once. Callers (mission terminal emission, ad-hoc
# staff actions) own deduplication.
#
# The function is split into small private helpers for testability; the
# public ``fire_renown_award`` orchestrates them.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RenownAwardResult:
    """Structured outcome of ``fire_renown_award`` — useful for tests + UI feedback.

    All deltas reflect what was actually applied (zeros where a scale was
    blank or had no effect).
    """

    persona_id: int
    fame_awarded: int = 0
    prestige_awarded: int = 0
    legend_awarded: int = 0
    fame_tier_changed: bool = False
    legend_entry_id: int | None = None
    aware_society_ids: tuple[int, ...] = field(default_factory=tuple)
    reputation_deltas: dict[int, int] = field(default_factory=dict)


def _set_persona_prestige_source(persona: Persona, source_field: str, delta: int) -> None:
    """Add ``delta`` to a persona's prestige source field + recompute total_prestige.

    Single write per call. ``source_field`` must be one of the four prestige
    source field names — guarded against typos at the call site.
    """
    if source_field not in (
        "prestige_from_dwellings",
        "prestige_from_items",
        "prestige_from_orgs",
        "prestige_from_deeds",
    ):
        msg = f"unknown prestige source field: {source_field!r}"
        raise ValueError(msg)
    current = getattr(persona, source_field)  # noqa: GETATTR_LITERAL
    setattr(persona, source_field, current + delta)
    persona.total_prestige = (
        persona.prestige_from_dwellings
        + persona.prestige_from_items
        + persona.prestige_from_orgs
        + persona.prestige_from_deeds
    )
    persona.save(update_fields=[source_field, "total_prestige"])


def _resolve_home_realm(origin_area: object | None) -> object | None:
    """Walk an Area's parent chain to find the first non-null ``realm`` FK.

    Returns the Realm instance or None if origin_area is None or no realm
    is set anywhere up the chain.
    """
    if origin_area is None:
        return None
    area: object | None = origin_area
    while area is not None:
        realm = getattr(area, "realm", None)  # noqa: GETATTR_LITERAL
        if realm is not None:
            return realm
        area = getattr(area, "parent", None)  # noqa: GETATTR_LITERAL
    return None


def _resolve_aware_realms(home_realm: object | None, reach: str) -> list:
    """Resolve the list of Realms that become aware of an event.

    Binary aware-or-not per the spec — no attenuation. LOCAL and REGIONAL
    are home realm only; CONTINENTAL walks the area hierarchy to find
    Realms with territory on the same continent; WORLD is every Realm.
    """
    from world.areas.constants import AreaLevel  # noqa: PLC0415
    from world.areas.models import Area  # noqa: PLC0415
    from world.realms.models import Realm  # noqa: PLC0415

    if reach == RenownReach.WORLD.value:
        return list(Realm.objects.all())
    if home_realm is None:
        # No origin → no propagation possible for the non-WORLD cases.
        return []
    if reach in (RenownReach.LOCAL.value, RenownReach.REGIONAL.value):
        return [home_realm]
    if reach == RenownReach.CONTINENTAL.value:
        # Find any Area on the home_realm at level CONTINENT, then collect
        # every Realm with at least one area whose ancestor is that
        # continent. The Area.parent chain is finite (PLANE > CONTINENT >
        # KINGDOM > REGION > CITY > WARD > NEIGHBORHOOD > BUILDING), so
        # walking it is bounded.
        continents = list(Area.objects.filter(realm=home_realm, level=AreaLevel.CONTINENT))
        if not continents:
            # No continent-tier areas authored for this realm — fall back to
            # home-realm-only awareness rather than zero out continental
            # reach. Authoring should usually catch this, but be defensive.
            return [home_realm]
        # For each continent, gather descendant areas, then unique realms.
        realm_ids: set[int] = set()
        for continent in continents:
            for descendant in _descendants_of(continent):
                if descendant.realm_id is not None:
                    realm_ids.add(descendant.realm_id)
        return list(Realm.objects.filter(pk__in=realm_ids))
    msg = f"unknown reach: {reach!r}"
    raise ValueError(msg)


def _descendants_of(area: object) -> Iterable:
    """Yield Area + all of its descendants (BFS via the parent reverse manager)."""
    queue: list = [area]
    while queue:
        current = queue.pop(0)
        yield current
        queue.extend(current.children.all())


def _archetype_dot_product(archetypes: Sequence, society: object) -> int:
    """Compute the principle dot product between an archetype vector + society.

    Walks the six PRINCIPLE_FIELD_NAMES; for each axis, multiplies the
    summed archetype delta by the society's principle value and accumulates.
    Returns the signed integer reputation delta.
    """
    delta = 0
    for principle in PRINCIPLE_FIELD_NAMES:
        archetype_axis_sum = sum(
            getattr(arch, f"{principle}_delta")  # noqa: GETATTR_LITERAL
            for arch in archetypes
        )
        society_value = getattr(society, principle)  # noqa: GETATTR_LITERAL
        delta += archetype_axis_sum * society_value
    return delta


@transaction.atomic
def fire_renown_award(  # noqa: PLR0913
    *,
    persona: Persona,
    magnitude: str | None = None,
    risk: str | None = None,
    archetypes: Sequence = (),
    origin_area: object | None = None,
    reach: str | None = None,
    society_overrides: dict | None = None,
    title: str = "Renown deed",
) -> RenownAwardResult:
    """Apply a Renown award bundle to ``persona``. Writes across every axis.

    Bundle composition (per the #676 spec):

    * ``magnitude`` → fame buffer bump + prestige_from_deeds permanent
      bump, per ``MAGNITUDE_FAME_AWARDS`` and ``MAGNITUDE_PRESTIGE_AWARDS``.
      Blank/None: no fame/prestige delta.
    * ``risk`` → legend value via ``RISK_LEGEND_AWARDS``. Blank/None or
      ``RenownRisk.NONE``: no legend awarded; no LegendEntry created.
    * ``archetypes`` → for each aware Society (per reach + origin_area),
      compute the principle dot product and update SocietyReputation. Empty
      archetypes: no reputation deltas fire.
    * ``reach`` override defaults from magnitude per
      ``MAGNITUDE_TO_DEFAULT_REACH`` when None; explicit value wins.
    * ``society_overrides`` (dict of ``Society → int``) overrides the
      computed reputation delta for those specific societies.

    Temporary personas earn fame + prestige_from_deeds + legend, but
    SocietyReputation writes are skipped (existing system rule that only
    PRIMARY/ESTABLISHED personas hold reputation).
    """
    from world.societies.models import LegendEntry, SocietyReputation  # noqa: PLC0415

    society_overrides = society_overrides or {}
    archetype_list: list = list(archetypes)

    fame_awarded = MAGNITUDE_FAME_AWARDS.get(magnitude, 0) if magnitude else 0
    prestige_awarded = MAGNITUDE_PRESTIGE_AWARDS.get(magnitude, 0) if magnitude else 0
    legend_awarded = RISK_LEGEND_AWARDS.get(risk, 0) if risk else 0

    # Persona-side writes (fame buffer + permanent prestige).
    fame_tier_changed = False
    if fame_awarded > 0:
        fame_tier_changed = set_persona_fame(persona, persona.fame_points + fame_awarded)
    if prestige_awarded != 0:
        _set_persona_prestige_source(persona, "prestige_from_deeds", prestige_awarded)

    # Propagation: determine which Realms hear about this event.
    effective_reach = (
        reach
        or (MAGNITUDE_TO_DEFAULT_REACH.get(magnitude) if magnitude else None)
        or RenownReach.LOCAL.value
    )
    home_realm = _resolve_home_realm(origin_area)
    aware_realms = _resolve_aware_realms(home_realm, effective_reach)

    # Reputation deltas to societies in aware realms (skipped for TEMPORARY
    # personas — existing system gate).
    aware_society_ids: list[int] = []
    reputation_deltas: dict[int, int] = {}
    if archetype_list and persona.is_established_or_primary:
        from world.societies.models import Society  # noqa: PLC0415

        aware_societies = Society.objects.filter(realm__in=[r.pk for r in aware_realms])
        for society in aware_societies:
            if society in society_overrides:
                rep_delta = society_overrides[society]
            else:
                rep_delta = _archetype_dot_product(archetype_list, society)
            aware_society_ids.append(society.pk)
            if rep_delta == 0:
                continue
            reputation, _created = SocietyReputation.objects.get_or_create(
                persona=persona,
                society=society,
                defaults={"value": 0},
            )
            reputation.value = max(-1000, min(1000, reputation.value + rep_delta))
            reputation.save(update_fields=["value"])
            reputation_deltas[society.pk] = rep_delta

    # Legend entry creation when Risk awards legend.
    legend_entry_id: int | None = None
    if legend_awarded > 0:
        entry = LegendEntry.objects.create(
            persona=persona,
            title=title,
            base_value=legend_awarded,
        )
        if aware_society_ids:
            entry.societies_aware.set(aware_society_ids)
        legend_entry_id = entry.pk

    return RenownAwardResult(
        persona_id=persona.pk,
        fame_awarded=fame_awarded,
        prestige_awarded=prestige_awarded,
        legend_awarded=legend_awarded,
        fame_tier_changed=fame_tier_changed,
        legend_entry_id=legend_entry_id,
        aware_society_ids=tuple(aware_society_ids),
        reputation_deltas=reputation_deltas,
    )
