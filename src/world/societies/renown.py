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

from collections.abc import Sequence
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
    ORG_INFLOW_FRACTION,
    ORG_PRESTIGE_DECAY_FLAT,
    ORG_PRESTIGE_DECAY_PCT,
    PRINCIPLE_FIELD_NAMES,
    RANK_OUTFLOW_MULTIPLIERS,
    RISK_LEGEND_AWARDS,
    FameTier,
    RenownReach,
)
from world.societies.models import REPUTATION_MAX, REPUTATION_MIN, Organization

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
    Does NOT touch covenants' accumulated_legend. After decaying each org,
    recomputes ``prestige_from_orgs`` for every member persona whose outflow
    reads this org — the org's accumulated dropping changes everyone's
    rank-weighted readout.
    """
    from django.db.models import Q  # noqa: PLC0415

    touched = 0
    touched_org_ids: list[int] = []
    for org in Organization.objects.filter(
        Q(accumulated_prestige__gt=0) | Q(accumulated_fame__gt=0)
    ).iterator():
        apply_org_accumulated_decay(org)
        touched += 1
        touched_org_ids.append(org.pk)
    if touched_org_ids:
        recompute_members_prestige_from_orgs_for_orgs(touched_org_ids)
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
    # Phase C: org accumulated inflow + covenant-legend body-flow.
    org_inflow_org_ids: tuple[int, ...] = field(default_factory=tuple)
    covenant_legend_inflow_org_ids: tuple[int, ...] = field(default_factory=tuple)


def _bump_prestige_from_deeds(persona: Persona, delta: int) -> None:
    """Add ``delta`` to ``prestige_from_deeds`` + recompute the total denorm."""
    persona.prestige_from_deeds += delta
    persona.total_prestige = (
        persona.prestige_from_dwellings
        + persona.prestige_from_items
        + persona.prestige_from_orgs
        + persona.prestige_from_deeds
    )
    persona.save(update_fields=["prestige_from_deeds", "total_prestige"])


def _resolve_home_realm(origin_area):
    """Walk an Area's parent chain to find the first non-null ``realm`` FK.

    Returns the Realm instance or None if origin_area is None or no realm
    is set anywhere up the chain.
    """
    area = origin_area
    while area is not None:
        if area.realm is not None:
            return area.realm
        area = area.parent
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
        # CONTINENTAL = every Realm with territory under the home Realm's
        # CONTINENT-level Areas. Uses the AreaClosure materialized view
        # (transitive ancestor-descendant pairs) for a single-query
        # descendant scan rather than per-node BFS.
        from world.areas.models import AreaClosure  # noqa: PLC0415

        continent_ids = list(
            Area.objects.filter(realm=home_realm, level=AreaLevel.CONTINENT).values_list(
                "pk", flat=True
            )
        )
        if not continent_ids:
            logger.warning(
                "renown.continental_reach: home Realm %s has no CONTINENT-level "
                "Areas — falling back to LOCAL awareness. Author at least one "
                "Continent area on this Realm.",
                home_realm.pk if home_realm else None,
            )
            return [home_realm]
        realm_ids = set(
            AreaClosure.objects.filter(ancestor_id__in=continent_ids)
            .exclude(descendant__realm__isnull=True)
            .values_list("descendant__realm_id", flat=True)
            .distinct()
        )
        return list(Realm.objects.filter(pk__in=realm_ids))
    msg = f"unknown reach: {reach!r}"
    raise ValueError(msg)


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
def fire_renown_award(  # noqa: PLR0913, C901
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

    Composition: ``magnitude`` → fame + prestige_from_deeds; ``risk`` →
    legend (creates LegendEntry when > 0); ``archetypes`` → per-society
    reputation via dot product against principles; ``reach`` defaults
    from magnitude; ``society_overrides`` overrides computed per-society
    deltas. TEMPORARY personas skip reputation writes.
    """
    from world.societies.models import LegendEntry, Society, SocietyReputation  # noqa: PLC0415

    fame_awarded = MAGNITUDE_FAME_AWARDS.get(magnitude, 0) if magnitude else 0
    prestige_awarded = MAGNITUDE_PRESTIGE_AWARDS.get(magnitude, 0) if magnitude else 0
    legend_awarded = RISK_LEGEND_AWARDS.get(risk, 0) if risk else 0
    archetype_list = list(archetypes)
    overrides = society_overrides or {}

    fame_tier_changed = False
    if fame_awarded > 0:
        fame_tier_changed = set_persona_fame(persona, persona.fame_points + fame_awarded)
    if prestige_awarded != 0:
        _bump_prestige_from_deeds(persona, prestige_awarded)

    effective_reach = (
        reach
        or (MAGNITUDE_TO_DEFAULT_REACH.get(magnitude) if magnitude else None)
        or RenownReach.LOCAL.value
    )
    aware_realms = _resolve_aware_realms(_resolve_home_realm(origin_area), effective_reach)

    aware_society_ids: list[int] = []
    reputation_deltas: dict[int, int] = {}
    if archetype_list and persona.is_established_or_primary:
        aware_societies = list(Society.objects.filter(realm__in=[r.pk for r in aware_realms]))
        aware_society_ids = [s.pk for s in aware_societies]
        for society in aware_societies:
            rep_delta = (
                overrides[society]
                if society in overrides
                else _archetype_dot_product(archetype_list, society)
            )
            if rep_delta == 0:
                continue
            reputation, _ = SocietyReputation.objects.get_or_create(
                persona=persona, society=society, defaults={"value": 0}
            )
            reputation.value = max(
                REPUTATION_MIN, min(REPUTATION_MAX, reputation.value + rep_delta)
            )
            reputation.save(update_fields=["value"])
            reputation_deltas[society.pk] = rep_delta

    legend_entry_id: int | None = None
    if legend_awarded > 0:
        entry = LegendEntry.objects.create(persona=persona, title=title, base_value=legend_awarded)
        if aware_society_ids:
            entry.societies_aware.set(aware_society_ids)
        if archetype_list:
            entry.archetypes.set(archetype_list)
        legend_entry_id = entry.pk

    org_inflow_org_ids: tuple[int, ...] = ()
    covenant_legend_inflow_org_ids: tuple[int, ...] = ()
    if persona.is_established_or_primary:
        org_inflow_org_ids = apply_org_inflow_for_persona_deed(
            persona,
            prestige_delta=prestige_awarded,
            fame_delta=fame_awarded,
            legend_delta=legend_awarded,
        )
    elif legend_awarded > 0:
        covenant_legend_inflow_org_ids = apply_body_covenant_legend_inflow(
            persona, legend_delta=legend_awarded
        )

    return RenownAwardResult(
        persona_id=persona.pk,
        fame_awarded=fame_awarded,
        prestige_awarded=prestige_awarded,
        legend_awarded=legend_awarded,
        fame_tier_changed=fame_tier_changed,
        legend_entry_id=legend_entry_id,
        aware_society_ids=tuple(aware_society_ids),
        reputation_deltas=reputation_deltas,
        org_inflow_org_ids=org_inflow_org_ids,
        covenant_legend_inflow_org_ids=covenant_legend_inflow_org_ids,
    )


def _bump_society_reputation(persona: Persona, society, rep_delta: int) -> None:
    """Apply a clamped reputation delta to (persona, society). Used by spread-extension."""
    from world.societies.models import SocietyReputation  # noqa: PLC0415

    reputation, _ = SocietyReputation.objects.get_or_create(
        persona=persona, society=society, defaults={"value": 0}
    )
    reputation.value = max(REPUTATION_MIN, min(REPUTATION_MAX, reputation.value + rep_delta))
    reputation.save(update_fields=["value"])


# ---------------------------------------------------------------------------
# Phase C — Org inflow + persona outflow
#
# Loop-safe flow:
#
#   persona deed ──(flat 10% inflow)──▶ each membership's org accumulated
#                                              │
#                                              ▼
#                                       prestige_from_orgs(persona)
#                                       = sum over memberships of
#                                         (base + accum_prestige + accum_fame)
#                                         × rank_multiplier(rank)
#
# Outflow is a pure readout — it never feeds back into the org. The only
# write to an org's accumulated values is the inflow from a member's deed
# or the cron decay (in the opposite direction).
#
# Whenever an org's accumulated values change (deed inflow or cron decay),
# every member's prestige_from_orgs must be recomputed because the rank-
# weighted sum reads the latest org values.
# ---------------------------------------------------------------------------


def apply_org_inflow_for_persona_deed(
    persona: Persona,
    *,
    prestige_delta: int,
    fame_delta: int,
    legend_delta: int,
) -> tuple[int, ...]:
    """Apply flat-10% inflow from a persona's deed into each membership's org.

    Returns the tuple of org IDs touched. After inflow, recomputes the
    rank-weighted outflow for every member persona of every touched org
    (the org's accumulated values changed, so everyone's readout changed).

    Covenant-typed orgs additionally receive legend inflow (permanent, never
    decays). Non-covenant orgs ignore legend_delta.

    No-op for personas where ``is_established_or_primary`` is False.
    """
    if not persona.is_established_or_primary:
        return ()
    if prestige_delta <= 0 and fame_delta <= 0 and legend_delta <= 0:
        return ()

    memberships = list(persona.organization_memberships.select_related("organization"))
    if not memberships:
        return ()

    org_ids = [m.organization_id for m in memberships]
    covenant_org_ids = _covenant_org_ids(org_ids)

    inflow_prestige = int(prestige_delta * ORG_INFLOW_FRACTION)
    inflow_fame = int(fame_delta * ORG_INFLOW_FRACTION)
    inflow_legend = int(legend_delta * ORG_INFLOW_FRACTION)

    for membership in memberships:
        org = membership.organization
        update_fields: list[str] = []
        if inflow_prestige > 0:
            org.accumulated_prestige += inflow_prestige
            update_fields.append("accumulated_prestige")
        if inflow_fame > 0:
            org.accumulated_fame += inflow_fame
            update_fields.append("accumulated_fame")
        if inflow_legend > 0 and org.pk in covenant_org_ids:
            org.accumulated_legend += inflow_legend
            update_fields.append("accumulated_legend")
        if update_fields:
            org.save(update_fields=update_fields)

    recompute_members_prestige_from_orgs_for_orgs(org_ids)
    return tuple(org_ids)


def apply_body_covenant_legend_inflow(
    persona: Persona,
    *,
    legend_delta: int,
) -> tuple[int, ...]:
    """Apply rank-weighted body-flow covenant-legend inflow for a TEMPORARY persona.

    Legend follows the body, not the persona's social standing. So a
    TEMPORARY persona's deed routes its legend into the body's PRIMARY
    persona's covenant memberships, weighted by the primary's rank in each
    covenant (per the spec — distinct from the flat inflow path).

    Returns the tuple of covenant org IDs touched. No-op when the body has
    no PRIMARY persona or that primary has no covenant memberships.
    """
    if legend_delta <= 0:
        return ()
    from world.scenes.constants import PersonaType  # noqa: PLC0415
    from world.scenes.models import Persona as PersonaModel  # noqa: PLC0415

    # Spec: "Walk to the body's PRIMARY/ESTABLISHED persona's covenant
    # memberships." Prefer PRIMARY when present; fall back to any
    # ESTABLISHED on the same body so legend still flows for bodies
    # that only have an established alter-ego (no formal PRIMARY).
    body_persona = (
        PersonaModel.objects.filter(
            character_sheet=persona.character_sheet,
            persona_type__in=[PersonaType.PRIMARY, PersonaType.ESTABLISHED],
        )
        .order_by("persona_type")  # PRIMARY sorts before ESTABLISHED alphabetically.
        .first()
    )
    if body_persona is None:
        return ()

    memberships = list(body_persona.organization_memberships.select_related("organization"))
    if not memberships:
        return ()

    covenant_org_ids = _covenant_org_ids([m.organization_id for m in memberships])
    if not covenant_org_ids:
        return ()

    touched: list[int] = []
    for membership in memberships:
        if membership.organization_id not in covenant_org_ids:
            continue
        rank_mult = RANK_OUTFLOW_MULTIPLIERS.get(membership.rank, 0.0)
        inflow = int(legend_delta * ORG_INFLOW_FRACTION * rank_mult)
        if inflow <= 0:
            continue
        org = membership.organization
        org.accumulated_legend += inflow
        org.save(update_fields=["accumulated_legend"])
        touched.append(org.pk)
    return tuple(touched)


def recompute_persona_prestige_from_orgs(persona: Persona) -> int:
    """Rank-weighted readout of every membership's org standing into the persona.

    Writes the recomputed ``prestige_from_orgs`` (and the dependent
    ``total_prestige`` denorm) onto the persona. Returns the new
    ``prestige_from_orgs`` value.

    Loop-safe: this is a pure readout of org state. It never feeds back
    into the org.
    """
    if not persona.is_established_or_primary:
        # TEMPORARY personas have no memberships and cannot earn outflow.
        # Their fields default to 0 and stay there.
        return persona.prestige_from_orgs

    total = 0
    for membership in persona.organization_memberships.select_related("organization"):
        org = membership.organization
        org_standing = org.base_prestige + org.accumulated_prestige + org.accumulated_fame
        rank_mult = RANK_OUTFLOW_MULTIPLIERS.get(membership.rank, 0.0)
        total += int(org_standing * rank_mult)

    if total == persona.prestige_from_orgs:
        return total
    persona.prestige_from_orgs = total
    persona.total_prestige = (
        persona.prestige_from_dwellings
        + persona.prestige_from_items
        + persona.prestige_from_orgs
        + persona.prestige_from_deeds
    )
    persona.save(update_fields=["prestige_from_orgs", "total_prestige"])
    return total


def recompute_members_prestige_from_orgs_for_orgs(org_ids: Sequence[int]) -> int:
    """Recompute ``prestige_from_orgs`` for every persona with a membership in any of these orgs.

    Returns the count of personas recomputed. Called after a sweep of
    org inflow or org decay — any change to an org's accumulated values
    invalidates every member's rank-weighted readout.
    """
    if not org_ids:
        return 0
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    persona_ids = set(
        OrganizationMembership.objects.filter(organization_id__in=org_ids).values_list(
            "persona_id", flat=True
        )
    )
    if not persona_ids:
        return 0
    count = 0
    for persona in Persona.objects.filter(pk__in=persona_ids):
        recompute_persona_prestige_from_orgs(persona)
        count += 1
    return count


def extend_deed_awareness(
    deed,
    *,
    scene=None,
) -> tuple[list[int], dict[int, int]]:
    """#737 — Extend a deed's awareness to the spread-scene's Realm.

    Every Society in the scene's Realm enters ``deed.societies_aware``.
    Per-society reputation deltas (archetype dot product against
    ``deed.archetypes``) fire one-shot on newly-aware societies only.

    Returns ``(newly_aware_society_ids, applied_reputation_deltas)``.
    No-ops when the scene's Realm can't be resolved or no new societies
    become aware.
    """
    home_realm = _resolve_spread_realm(scene)
    if home_realm is None:
        return [], {}
    from world.societies.models import Society  # noqa: PLC0415

    realm_society_ids = set(Society.objects.filter(realm=home_realm).values_list("pk", flat=True))
    if not realm_society_ids:
        return [], {}
    already_aware_ids = set(deed.societies_aware.values_list("pk", flat=True))
    newly_aware_ids = realm_society_ids - already_aware_ids
    if not newly_aware_ids:
        return [], {}

    new_societies = list(Society.objects.filter(pk__in=newly_aware_ids))
    deed.societies_aware.add(*new_societies)

    archetype_list = list(deed.archetypes.all())
    if not archetype_list or not deed.persona.is_established_or_primary:
        return list(newly_aware_ids), {}

    applied: dict[int, int] = {}
    for society in new_societies:
        delta = _archetype_dot_product(archetype_list, society)
        if delta == 0:
            continue
        _bump_society_reputation(deed.persona, society, delta)
        applied[society.pk] = delta
    return list(newly_aware_ids), applied


def _resolve_spread_realm(scene) -> object | None:
    """Walk ``scene.location → RoomProfile.area → parent chain → Realm``.

    Returns None when the chain breaks at any step (no scene, no
    location, non-room location, no realm in the area's parent chain).
    """
    from evennia_extensions.models import RoomProfile  # noqa: PLC0415

    if scene is None or scene.location is None:
        return None
    try:
        room_profile = scene.location.room_profile
    except RoomProfile.DoesNotExist:
        return None
    return _resolve_home_realm(room_profile.area)


def apply_spread_fame_bump(
    deed,
    *,
    npc_audience: int = 0,
    success_level: int = 1,
) -> bool:
    """#676 Phase H — Bump the deed-subject's fame on a successful spread.

    Spec formula (§Legend Spread): ``fame_bump = 1 × npc_audience ×
    success_level``. The bump credits the deed subject (not the
    spreader). Default args yield 0 — the admin spread API hasn't been
    extended to carry NPC/check data yet, so this no-ops on every
    current caller. Returns True iff the fame tier changed.
    """
    bump = npc_audience * success_level
    if bump <= 0 or deed.persona_id is None:
        return False
    subject = deed.persona
    return set_persona_fame(subject, subject.fame_points + bump)


def _covenant_org_ids(org_ids: Sequence[int]) -> set[int]:
    """Return the subset of ``org_ids`` whose Organizations back a Covenant.

    Single query via the Covenant.organization OneToOneField reverse path.
    """
    if not org_ids:
        return set()
    from world.covenants.models import Covenant  # noqa: PLC0415

    return set(
        Covenant.objects.filter(organization_id__in=org_ids).values_list(
            "organization_id", flat=True
        )
    )
