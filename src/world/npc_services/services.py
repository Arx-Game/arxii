"""Service functions for the unified NPC service framework.

- ``persona_for_character`` resolves a PC's primary persona — used by the
  HTTP wiring (start_interaction) to compute persona from the request's
  puppeted character.
- ``start_interaction`` / ``available_offers`` / ``resolve_offer`` /
  ``end_interaction`` make up the in-memory interaction state machine.
  State is ephemeral — lives in the dataclass instance for the duration
  of one interaction and is never persisted. Durable side effects:
  ``NPCStanding`` affection on close, ``OfferCooldown`` row on final
  grants whose offer carries a non-null cooldown, the effect handler's
  downstream object on each grant.

Standing (affection) and cooldown are deliberately orthogonal — cooldown
lives on :class:`OfferCooldown` (per-(offer, persona)) so it works for
every offer kind, not only NPC-rooted ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import random
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from world.checks.services import perform_check
from world.missions.constants import MissionStatus
from world.missions.models import MissionInstance
from world.missions.services.visibility import template_visible_to
from world.npc_services.constants import DrawMode, OfferKind
from world.npc_services.effects import EffectResult, dispatch_offer_effect
from world.npc_services.models import (
    MissionOfferDetails,
    NPCRole,
    NPCRoleCooldown,
    NPCServiceOffer,
    NPCStanding,
    OfferCooldown,
)
from world.npc_services.offer_policy import mission_pool_count
from world.npc_services.serializers import (
    InteractionOfferSerializer,
    InteractionStateSerializer,
)
from world.predicates.predicates import CharacterPredicateContext, evaluate

if TYPE_CHECKING:
    from typeclasses.characters import Character
    from world.npc_services.models import RecordedProfile
    from world.scenes.models import Persona

logger = logging.getLogger(__name__)


class ResolveOfferError(ValueError):
    """Base class for offer-grant failures.

    Carries a fixed ``user_message`` separate from the internal exception
    message so callers can surface a safe string to the client without
    leaking object IDs or eligibility reasoning. Per
    `feedback_codeql_exceptions`: never pass `str(exc)` to a response.
    """

    user_message: str = "Offer could not be granted."


class SessionClosedError(ResolveOfferError):
    user_message = "This interaction has already ended."


class OfferRoleMismatchError(ResolveOfferError):
    user_message = "That offer is not available from this NPC."


class OfferNotEligibleError(ResolveOfferError):
    user_message = "That offer is not currently available."


class InsufficientAPError(ResolveOfferError):
    user_message = "You don't have the action points for that right now."


# #684: ``persona_for_character`` + ``MissingPrimaryPersonaError`` moved to
# ``world.scenes.services`` — the resolver belongs in scenes (general use
# across NPCStanding, item ownership snapshots, mission flavor, ...) and
# importers should not depend on the npc_services app for it.


# ---------------------------------------------------------------------------
# Interaction state machine — ephemeral per-interaction state.
#
# Lives in the player's session for the duration of one interaction. NOT
# persisted. Carries: starting rapport (role default + standing affection
# for class 2-4 NPCs), the offers currently surfaced. On end_interaction
# the standing row is updated for class 2-4 NPCs (the persistent affection
# movement) and the session is discarded.
#
# Visibility and selectability collapse into one predicate (the offer's
# ``eligibility_rule``) — if the predicate fails, the offer isn't surfaced.
# Progressive disclosure happens through how staff author predicates, not
# through a separate visibility layer.
# ---------------------------------------------------------------------------


@dataclass
class InteractionSession:
    """Ephemeral state for one in-progress NPC interaction.

    Created by ``start_interaction``; mutated by ``resolve_offer`` and
    ``end_interaction``. Never persisted directly — the HTTP wiring
    serializes a tiny state dict to ``request.session`` and rehydrates
    per call.
    """

    role: NPCRole
    persona: Persona
    npc_persona: Persona | None
    """The NPC's persona, or None for class-1 nameless functionaries."""
    character: Character
    """The PC's Evennia Character — needed for the predicate context."""
    current_rapport: int
    closed: bool = False
    results: list[EffectResult] = field(default_factory=list)


def start_interaction(
    *,
    role: NPCRole,
    persona: Persona,
    character: Character,
    npc_persona: Persona | None = None,
) -> InteractionSession:
    """Begin an interaction with an NPC of ``role``.

    Initial rapport = ``role.default_rapport_starting_value`` + (existing
    NPCStanding.affection if both personas are known and a row exists).
    Class-1 nameless functionary interactions pass ``npc_persona=None`` —
    rapport starts at the role default and no NPCStanding row is read or
    written.
    """
    starting = role.default_rapport_starting_value
    if npc_persona is not None:
        standing = NPCStanding.objects.filter(
            persona=persona,
            npc_persona=npc_persona,
        ).first()
        if standing is not None:
            starting += standing.affection
    return InteractionSession(
        role=role,
        persona=persona,
        npc_persona=npc_persona,
        character=character,
        current_rapport=starting,
    )


@dataclass(frozen=True)
class _EligibilityCache:
    """Pre-computed role-/PC-scoped query results, hoisted out of the offer loop.

    The eligibility check is run once per offer in ``available_offers`` and
    again as a single-offer re-verify in ``resolve_offer``. Several gates
    (role-scope cooldown, PC active-NPC-mission cap, per-(persona × role)
    one-in-flight) read state that does NOT vary across offers in the same
    role × persona × character set. Hoisting them into this cache turns
    ``O(offers × 3)`` queries into ``O(3)``.
    """

    role_cooldown_active: bool
    pc_at_npc_cap: bool
    persona_on_role_active: bool


def _build_eligibility_cache(
    *,
    role: NPCRole,
    persona: Persona,
    character: Character,
    now: object,
) -> _EligibilityCache:
    """Compute the three hoisted gates once per session for ``role``.

    ``pc_at_npc_cap`` fails closed when the character has no CharacterSheet —
    the PC cap is a load-bearing gate and silently bypassing it (the old
    behaviour) would let an unfinished/seeded PC pile up unlimited NPC
    missions. ``persona_on_role_active`` keys on the new
    ``MissionInstance.accepted_as_persona`` FK so ESTABLISHED personas don't
    inherit PRIMARY's commitments to the same role (spec AD#8).
    """
    role_cooldown_active = NPCRoleCooldown.objects.filter(
        role_id=role.pk, persona=persona, available_at__gt=now
    ).exists()
    sheet = character.character_sheet
    if sheet is None:
        pc_at_npc_cap = True
    else:
        active_npc_count = MissionInstance.objects.filter(
            participants__character=character,
            participants__is_contract_holder=True,
            status=MissionStatus.ACTIVE,
            source_offer__isnull=False,
        ).count()
        pc_at_npc_cap = active_npc_count >= sheet.max_active_npc_missions
    persona_on_role_active = MissionInstance.objects.filter(
        accepted_as_persona=persona,
        status=MissionStatus.ACTIVE,
        source_offer__role_id=role.pk,
    ).exists()
    return _EligibilityCache(
        role_cooldown_active=role_cooldown_active,
        pc_at_npc_cap=pc_at_npc_cap,
        persona_on_role_active=persona_on_role_active,
    )


def _is_offer_eligible(  # noqa: PLR0911, PLR0913
    offer: NPCServiceOffer,
    *,
    persona: Persona,
    character: Character,
    current_rapport: int,
    cache: _EligibilityCache | None = None,
    now: object | None = None,
) -> bool:
    """Single-offer eligibility check.

    Drives both ``available_offers`` (filtering) and ``resolve_offer``
    (single-offer re-verify). Keeping the check here means there's one
    source of truth, and ``resolve_offer`` doesn't have to re-run the
    whole queryset to verify one offer.

    Gates layered (#686):
    1. Role-level: ``offer.role.is_active``.
    2. Rapport: ``offer.rapport_requirement <= current_rapport``.
    3. Role-level cooldown (cached): no active ``NPCRoleCooldown``.
    4. Offer-level cooldown: no active ``OfferCooldown`` for (offer, persona).
    5. For MISSION offers only: PC cap (cached), per-(persona × role)
       one-in-flight (cached), template-level gates (``is_active``,
       ``visibility``/``availability_rule`` via ``template_visible_to``,
       ``level_band``), AND-composed with ``details.requirements_override``
       (see ``_mission_gates_pass``).
    6. Offer's own ``eligibility_rule`` predicate.

    POOL draw_mode is now a first-class case: eligibility itself is
    draw-mode-agnostic; ``available_offers`` applies the POOL sampling
    on top of the eligible-offer set when ``count`` is provided.
    """
    if not offer.role.is_active:
        return False
    if offer.rapport_requirement > current_rapport:
        return False
    now = now or timezone.now()
    if cache is None:
        # Single-offer callers (e.g. `resolve_offer`, ad-hoc tests) skip the
        # ``available_offers`` cache plumbing; we lazy-build the per-call
        # cache so the eligibility logic stays in one place.
        cache = _build_eligibility_cache(
            role=offer.role, persona=persona, character=character, now=now
        )
    if cache.role_cooldown_active:
        return False
    if (
        offer.cooldown is not None
        and OfferCooldown.objects.filter(
            offer=offer, persona=persona, available_at__gt=now
        ).exists()
    ):
        return False
    if offer.kind == OfferKind.MISSION.value and not _mission_gates_pass(
        offer=offer, persona=persona, character=character, cache=cache
    ):
        return False
    if offer.kind == OfferKind.ASSET_TASK_INTEL.value and not _intel_pool_has_unheld_clues(
        offer=offer, persona=persona
    ):
        return False
    if offer.kind == OfferKind.ASSET_TASK_COLLECT.value and not _asset_has_collectable_income(
        persona=persona
    ):
        return False
    ctx = CharacterPredicateContext(character, presented_persona=persona)
    return evaluate(offer.eligibility_rule or {}, ctx)


def _intel_pool_has_unheld_clues(*, offer: NPCServiceOffer, persona: Persona) -> bool:
    """Check whether the offer's clue pool has at least one unheld clue (#2293).

    Returns False (offer ineligible) when the persona's roster entry already
    holds every clue in the pool — the intel source is exhausted. Also returns
    False on authoring errors (missing details row, missing roster entry) to
    fail closed, consistent with ``_mission_gates_pass``.
    """
    from world.assets.models import AssetTaskIntelDetails  # noqa: PLC0415
    from world.clues.models import CharacterClue  # noqa: PLC0415
    from world.roster.models import RosterEntry  # noqa: PLC0415

    try:
        details = offer.asset_task_intel_details
    except AssetTaskIntelDetails.DoesNotExist:
        return False
    roster_entry = RosterEntry.objects.filter(character_sheet=persona.character_sheet).first()
    if roster_entry is None:
        return False
    held_clue_ids = set(
        CharacterClue.objects.filter(roster_entry=roster_entry).values_list("clue_id", flat=True)
    )
    pool_clue_ids = set(details.clue_pool.entries.values_list("clue_id", flat=True))
    return bool(pool_clue_ids - held_clue_ids)


def _asset_has_collectable_income(*, persona: Persona) -> bool:
    """Check whether the promoter has an active asset with uncollected_pool > 0 (#2294).

    Returns False (offer ineligible) when no active asset exists or the pool
    is empty. Fails closed on missing data, consistent with
    ``_intel_pool_has_unheld_clues``.
    """
    from world.assets.constants import AssetStatus  # noqa: PLC0415
    from world.assets.models import NPCAsset  # noqa: PLC0415

    return NPCAsset.objects.filter(
        promoter_persona=persona,
        status=AssetStatus.ACTIVE,
        uncollected_pool__gt=0,
    ).exists()


def _mission_gates_pass(  # noqa: PLR0911
    *,
    offer: NPCServiceOffer,
    persona: Persona,
    character: Character,
    cache: _EligibilityCache,
) -> bool:
    """Apply the MISSION-only gates from ``_is_offer_eligible`` (#686).

    Ordered cheapest-first: cached PC/role gates → details lookup → template
    field gates → composed predicate. Template-side visibility (#870:
    ``visibility`` + ``availability_rule`` + staff bypass) is enforced via
    the single ``template_visible_to`` gate; eligibility then composes
    ``details.requirements_override`` ∧ ``offer.eligibility_rule`` (offer-
    specific, orthogonal to template visibility).
    """
    if cache.pc_at_npc_cap:
        return False
    if cache.persona_on_role_active:
        return False
    try:
        details: MissionOfferDetails = offer.mission_offer_details
    except MissionOfferDetails.DoesNotExist:
        # MISSION offer with no details row is an authoring error; fail closed.
        return False
    template = details.mission_template
    if not template.is_active:
        return False
    if not template_visible_to(template, character, persona=persona):
        return False
    sheet = character.character_sheet
    if sheet is None:
        # No sheet → no level → can't satisfy the level-band gate. Fail closed
        # consistently with the PC-cap gate above (cache.pc_at_npc_cap is True
        # when sheet is None, so we'd never reach here in practice, but make
        # the local-only path defensive in case the cache is bypassed).
        return False
    if not (template.level_band_min <= sheet.current_level <= template.level_band_max):
        return False
    ctx = CharacterPredicateContext(character, presented_persona=persona)
    if details.requirements_override and not evaluate(details.requirements_override, ctx):
        return False
    return True


def available_offers(
    session: InteractionSession,
    *,
    pool_count: int | None = None,
) -> list[NPCServiceOffer]:
    """Return offers the PC can currently see/select, in stable order.

    Filtered by ``_is_offer_eligible`` (every gate; see its docstring).
    ``select_related("role")`` so the role doesn't get re-fetched per row.
    Role-/PC-scoped gates (NPCRoleCooldown, PC cap, per-(persona × role)
    one-in-flight) are computed ONCE via ``_build_eligibility_cache`` and
    passed into every offer's eligibility check — avoids the per-offer
    N+1 storm flagged by the #686 review.

    POOL semantics (#686): when ``pool_count`` is ``None`` (the default),
    all eligible offers are returned regardless of ``draw_mode`` — matches
    the historical MENU-only behaviour. When ``pool_count`` is provided,
    every MENU offer is still returned in full, but POOL-mode offers are
    sampled down to at most ``pool_count`` via a priority-tiered weighted draw
    without replacement (``_draw_pool_offers``). The live HTTP caller
    (``views._serialize_state``) derives ``pool_count`` from the PC's standing
    via ``offer_policy.mission_pool_count`` (#726); ``None`` is retained for
    callers/tests that want the full eligible set.
    """
    if session.closed:
        return []
    now = timezone.now()
    cache = _build_eligibility_cache(
        role=session.role,
        persona=session.persona,
        character=session.character,
        now=now,
    )
    # select_related the PERMIT details + its building_kind so issue_permit
    # doesn't pay 2 extra queries per PERMIT offer (mixed-kind roles only
    # pay for unused reverse-OneToOne fetches on non-PERMIT offers, which
    # is acceptable given the small per-role offer count). Pre-fetch the
    # M2M default_approved_wards for the same reason.
    queryset = (
        NPCServiceOffer.objects.select_related(
            "role",
            "permit_offer_details__building_kind",
            "mission_offer_details__mission_template",
        )
        .prefetch_related(
            "permit_offer_details__default_approved_wards",  # noqa: PREFETCH_STRING
        )
        .filter(role=session.role)
        .order_by("pk")
    )
    eligible = [
        offer
        for offer in queryset
        if _is_offer_eligible(
            offer,
            persona=session.persona,
            character=session.character,
            current_rapport=session.current_rapport,
            cache=cache,
            now=now,
        )
    ]

    if pool_count is None:
        return eligible

    menu_offers = [o for o in eligible if o.draw_mode == DrawMode.MENU]
    pool_offers = [o for o in eligible if o.draw_mode == DrawMode.POOL]
    return menu_offers + _draw_pool_offers(pool_offers, pool_count)


@dataclass
class _WeightedOffer:
    """Adapter for ``select_weighted``: pairs an offer with its draw weight."""

    offer: NPCServiceOffer
    weight: int


def _draw_pool_offers(offers: list[NPCServiceOffer], count: int) -> list[NPCServiceOffer]:
    """Ordered, weighted draw of up to ``count`` offers, without replacement.

    Offers are drawn in ordered groups (see ``_ordered_draw_groups``): explicit
    ``draw_priority`` tiers (chains / high-stakes, #726) first with guaranteed
    inclusion, then active-Era arc-replace winners (#1020), then the general
    pool. Each group is drawn weighted-without-replacement on
    ``_weight_for_offer``; a group is only reached once the groups above it are
    exhausted or the count is filled. With no priority offers and no active Era
    this collapses to the historical single weighted draw. Zero-weight offers
    are excluded so a row never silently vanishes due to a null/zero weight.
    """
    from world.checks.outcome_utils import select_weighted  # noqa: PLC0415

    if count <= 0 or not offers:
        return []

    weighted: list[_WeightedOffer] = []
    for offer in offers:
        weight = _weight_for_offer(offer)
        if weight > 0:
            weighted.append(_WeightedOffer(offer=offer, weight=weight))
    if not weighted:
        return []

    drawn: list[NPCServiceOffer] = []
    for group in _ordered_draw_groups(weighted):
        remaining = list(group)
        while remaining and len(drawn) < count:
            pick = select_weighted(remaining)
            drawn.append(pick.offer)
            remaining.remove(pick)
        if len(drawn) >= count:
            break
    return drawn


def _ordered_draw_groups(weighted: list[_WeightedOffer]) -> list[list[_WeightedOffer]]:
    """Order the eligible POOL offers into draw groups (#726, #1020).

    1. Explicit ``draw_priority`` tiers (chains / high-stakes), highest first —
       guaranteed inclusion.
    2. Active-Era arc-replace winners — priority-0 offers whose
       ``percent_replace`` roll won this render (ambient seasonal lift).
    3. The remaining general (priority-0) pool.

    Ordering is deliberately chains > arc > general: authored chains are
    deliberate narrative wiring and must not be bumped by a season roll, while
    arc content outranks the generic pool. The split is data-light (see
    ``constants``) so the ordering can be retuned after playtesting.
    """
    priority_tiers: dict[int, list[_WeightedOffer]] = {}
    general: list[_WeightedOffer] = []
    for weighted_offer in weighted:
        tier = _draw_priority_for_offer(weighted_offer.offer)
        if tier > 0:
            priority_tiers.setdefault(tier, []).append(weighted_offer)
        else:
            general.append(weighted_offer)

    arc_winners, general_rest = _split_arc_winners(general)

    groups = [priority_tiers[tier] for tier in sorted(priority_tiers, reverse=True)]
    groups.append(arc_winners)
    groups.append(general_rest)
    return groups


def _split_arc_winners(
    general: list[_WeightedOffer],
) -> tuple[list[_WeightedOffer], list[_WeightedOffer]]:
    """Partition the general pool into active-Era arc winners and the rest (#1020).

    "Arc offers" are MISSION offers whose template's ``created_in_era`` is the
    single ACTIVE Era; each rolls its ``percent_replace`` once per render and,
    on a win, is promoted ahead of the general pool. No active Era → no winners
    (the #726 behaviour, at the cost of one ``Era.objects.get_active()`` probe).
    The arc check rides the ``mission_offer_details__mission_template``
    select_related in ``available_offers``, so it adds no per-offer query.
    """
    from world.stories.models import Era  # noqa: PLC0415

    active_era = Era.objects.get_active()
    if active_era is None:
        return [], general
    winners: list[_WeightedOffer] = []
    rest: list[_WeightedOffer] = []
    for weighted_offer in general:
        bucket = winners if _arc_offer_wins(weighted_offer.offer, active_era.pk) else rest
        bucket.append(weighted_offer)
    return winners, rest


def _arc_offer_wins(offer: NPCServiceOffer, active_era_pk: int) -> bool:
    """True if ``offer`` is an active-Era arc mission that won its replace roll (#1020).

    Non-MISSION offers, missing details, and templates not authored in the
    active Era never win. ``percent_replace`` is the 0–100 win chance:
    0 → never (``randint(1, 100) <= 0`` is always False), 100 → always.
    """
    if offer.kind != OfferKind.MISSION.value:
        return False
    try:
        template = offer.mission_offer_details.mission_template
    except MissionOfferDetails.DoesNotExist:
        return False
    if template.created_in_era_id != active_era_pk:
        return False
    return random.randint(1, 100) <= template.percent_replace  # noqa: S311


def _draw_priority_for_offer(offer: NPCServiceOffer) -> int:
    """POOL-draw priority tier for an offer (#726).

    MISSION offers carry it on ``MissionOfferDetails.draw_priority``; other
    kinds have no priority surface today and sit in the general (0) tier. The
    ``mission_offer_details`` row is ``select_related`` upstream in
    ``available_offers``, so this adds no query.
    """
    if offer.kind == OfferKind.MISSION.value:
        try:
            return offer.mission_offer_details.draw_priority
        except MissionOfferDetails.DoesNotExist:
            return 0
    return 0


def _weight_for_offer(offer: NPCServiceOffer) -> int:
    """Resolve the POOL-draw weight for an offer per its kind (#686).

    MISSION: ``MissionOfferDetails.weight`` falls back to
    ``MissionTemplate.base_weight``. Other kinds: 1 (no per-kind weight
    surface today). Always clamped to >= 1 so a row never silently
    disappears from the draw due to a zero/null weight.
    """
    if offer.kind == OfferKind.MISSION.value:
        try:
            details = offer.mission_offer_details
        except MissionOfferDetails.DoesNotExist:
            return 1
        if details.weight is not None and details.weight > 0:
            return details.weight
        return max(details.mission_template.base_weight, 1)
    return 1


def _charge_offer_ap(offer: NPCServiceOffer, *, character: Character) -> None:
    """Charge the offer's ``ap_cost`` before its effect dispatches (#930).

    Raises ``InsufficientAPError`` (transaction rolls back — nothing granted)
    when the character can't pay. Free offers (the default) skip the pool
    lookup entirely.
    """
    if offer.ap_cost <= 0:
        return
    from world.action_points.models import ActionPointPool  # noqa: PLC0415

    pool = ActionPointPool.get_or_create_for_character(character)
    if not pool.spend(offer.ap_cost):
        msg = f"Offer {offer.pk} costs {offer.ap_cost} AP; character {character.pk} cannot pay."
        raise InsufficientAPError(msg)


def _apply_check(
    offer: NPCServiceOffer,
    *,
    character: Character,
) -> tuple[int, bool]:
    """Roll the offer's check (if any) and return (delta, succeeded).

    Returns ``(rapport_delta_success, True)`` when no ``check_type`` is
    set (the action succeeds unconditionally) or when the check rolls
    a positive success level; ``(rapport_delta_failure, False)`` otherwise.
    """
    if offer.check_type_id is None:
        return offer.rapport_delta_success, True
    result = perform_check(
        character,
        offer.check_type,
        target_difficulty=offer.check_difficulty,
    )
    succeeded = bool(result.outcome and result.outcome.success_level > 0)
    delta = offer.rapport_delta_success if succeeded else offer.rapport_delta_failure
    return delta, succeeded


@transaction.atomic
def resolve_offer(
    session: InteractionSession,
    offer: NPCServiceOffer,
) -> EffectResult:
    """Grant ``offer`` in ``session`` — dispatch its effect, update rapport.

    Final actions (``is_final=True``) dispatch the effect handler, write an
    ``OfferCooldown`` row when the offer has a cooldown set, and close the
    session. The effect IS the payoff — rapport is not adjusted on final
    actions. Non-final actions roll the offer's ``check_type`` if set (or
    treat as auto-success otherwise) and apply ``rapport_delta_success`` /
    ``rapport_delta_failure`` accordingly; session stays open.

    Re-verifies eligibility at grant time so a stale UI can't grant an
    offer the PC no longer qualifies for. Raises a ``ResolveOfferError``
    subclass — callers surface ``exc.user_message`` to clients (never
    ``str(exc)`` — see ``feedback_codeql_exceptions``).
    """
    if session.closed:
        msg = "Cannot resolve an offer on a closed interaction session."
        raise SessionClosedError(msg)
    if offer.role_id != session.role.pk:
        msg = (
            f"Offer {offer.pk} belongs to role {offer.role_id}, not session role {session.role.pk}."
        )
        raise OfferRoleMismatchError(msg)
    if not _is_offer_eligible(
        offer,
        persona=session.persona,
        character=session.character,
        current_rapport=session.current_rapport,
    ):
        msg = f"Offer {offer.pk} ({offer.label!r}) is not currently eligible for this session."
        raise OfferNotEligibleError(msg)

    _charge_offer_ap(offer, character=session.character)

    if offer.is_final:
        result = dispatch_offer_effect(offer, session.persona)
        session.results.append(result)
        if offer.cooldown is not None:
            OfferCooldown.objects.update_or_create(
                offer=offer,
                persona=session.persona,
                defaults={"available_at": timezone.now() + offer.cooldown},
            )
        end_interaction(session)
        return result

    # Non-final: roll check (if configured), apply delta, leave session open.
    delta, _succeeded = _apply_check(offer, character=session.character)
    session.current_rapport += delta
    result = dispatch_offer_effect(offer, session.persona)
    session.results.append(result)
    return result


@transaction.atomic
def adjust_npc_affection(pc_persona, npc_persona, *, delta: int) -> int:
    """Apply a disposition ``delta`` to the (pc_persona, npc_persona) standing.

    Atomic accumulate: the increment runs as a single ``UPDATE ... SET
    affection = affection + delta`` via ``F()`` so concurrent calls cannot
    lose updates (ADR-0016: reuses the NPCStanding affection column, no fork).
    Creates the row at affection=0 if absent. Returns the new affection value.
    No-op-safe for delta=0 (still returns current affection).
    """
    standing, _ = NPCStanding.objects.get_or_create(
        persona=pc_persona,
        npc_persona=npc_persona,
        defaults={"affection": 0},
    )
    if delta != 0:
        NPCStanding.objects.filter(pk=standing.pk).update(affection=F("affection") + delta)
        # ``F()``-based UPDATE bypasses Evennia's SharedMemoryModel instance,
        # so the cached copy must be purged and reloaded for callers that
        # already hold the same idmapped object.
        standing.flush_from_cache(force=True)
        standing.refresh_from_db()
    return standing.affection


@transaction.atomic
def incur_npc_debt(
    standing: NPCStanding,
    amount: int,
    *,
    current_affection: int,
    current_missions_completed: int,
) -> NPCStanding:
    """Add ``amount`` to ``standing.debt`` and re-stamp the repayment baseline.

    Generic: any petition-style feature (not just Court grant negotiation) that
    lets a PC over-draw an NPC's goodwill can call this. Mirrors
    ``adjust_npc_affection``'s ``F()``-based update + idmapper cache flush.
    """
    NPCStanding.objects.filter(pk=standing.pk).update(
        debt=F("debt") + amount,
        debt_baseline_affection=current_affection,
        debt_baseline_missions_completed=current_missions_completed,
    )
    standing.flush_from_cache(force=True)
    standing.refresh_from_db()
    return standing


def outstanding_debt(
    standing: NPCStanding,
    *,
    current_affection: int,
    current_missions_completed: int,
    affection_divisor: int,
    mission_divisor: int,
) -> int:
    """Derive-on-read: net ``standing.debt`` against progress since the baseline.

    Pure function, no writes. ``current_affection``/``current_missions_completed``
    are passed in by the caller rather than re-derived here, so this stays
    domain-agnostic (the caller decides what "missions" means for their feature).
    """
    if standing.debt == 0:
        return 0
    affection_credit = max(0, current_affection - standing.debt_baseline_affection) // (
        affection_divisor or 1
    )
    mission_credit = max(
        0, current_missions_completed - standing.debt_baseline_missions_completed
    ) // (mission_divisor or 1)
    return max(0, standing.debt - affection_credit - mission_credit)


@transaction.atomic
def record_petition_outcome(
    standing: NPCStanding,
    *,
    succeeded: bool,
    escalation_threshold: int,
) -> bool:
    """Increment/reset ``consecutive_failed_petitions``; report threshold crossing.

    Mirrors ``Contract.consecutive_missed`` / ``_update_contract_status``
    (``world/currency/services.py``): a success resets the streak to 0; a
    failure increments it and, at ``escalation_threshold``, the caller should
    fire its own escalation consequence (this function only reports whether
    that threshold was crossed — it has no opinion on what "escalation" means).
    The crossing report is level-triggered (``>= escalation_threshold``), not
    edge-triggered — it returns ``True`` on every failure at or past the
    threshold, not just the first one that crosses it. This is intentional:
    the caller's escalation fires again on each subsequent failure.
    """
    if succeeded:
        if standing.consecutive_failed_petitions:
            standing.consecutive_failed_petitions = 0
            standing.save(update_fields=["consecutive_failed_petitions"])
        return False

    standing.consecutive_failed_petitions += 1
    standing.save(update_fields=["consecutive_failed_petitions"])
    return standing.consecutive_failed_petitions >= escalation_threshold


@transaction.atomic
def end_interaction(session: InteractionSession) -> None:
    """Close the session and persist final affection for class 2-4 NPCs.

    ``start_interaction`` seeded ``current_rapport`` with
    ``role.default_rapport_starting_value + existing_affection``. The new
    durable affection is therefore ``current_rapport - role default`` —
    overwritten on ``NPCStanding`` (not accumulated). No-op for class-1
    (``npc_persona is None``).

    Uses ``update_or_create`` inside the atomic so concurrent close paths
    can't race a stale row in.
    """
    if session.closed:
        return
    session.closed = True
    if session.npc_persona is None:
        return
    new_affection = session.current_rapport - session.role.default_rapport_starting_value
    NPCStanding.objects.update_or_create(
        persona=session.persona,
        npc_persona=session.npc_persona,
        defaults={"affection": new_affection},
    )


def _offer_risk_tier(offer: NPCServiceOffer) -> int | None:
    """The wrapped MissionTemplate's risk_tier for MISSION offers, else None (#1770 PR4)."""
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    try:
        details = offer.mission_offer_details
    except ObjectDoesNotExist:
        return None
    return details.mission_template.risk_tier


def serialize_npc_session_state(
    session: InteractionSession,
    *,
    last_result_message: str = "",
) -> dict:
    """Compose the response payload from a (live or freshly-closed) session.

    Public helper shared by the web viewset and the telnet ``hire`` command.
    """
    # #726: surface a standing-driven number of POOL offers (strangers see one
    # trial job, trusted contacts a full slate). MENU offers are unaffected —
    # ``available_offers`` always returns every eligible MENU option in full.
    offers = (
        available_offers(
            session,
            pool_count=mission_pool_count(
                role=session.role,
                persona=session.persona,
                npc_persona=session.npc_persona,
            ),
        )
        if not session.closed
        else []
    )
    serialized_offers = InteractionOfferSerializer(
        [
            {
                "id": o.pk,
                "label": o.label,
                "kind": o.kind,
                "is_final": o.is_final,
                "rapport_requirement": o.rapport_requirement,
                "risk_tier": _offer_risk_tier(o),
            }
            for o in offers
        ],
        many=True,
    ).data
    return InteractionStateSerializer(
        {
            "role_id": session.role.pk,
            "current_rapport": session.current_rapport,
            "closed": session.closed,
            "available_offers": serialized_offers,
            "last_result_message": last_result_message,
        }
    ).data


class RecordedProfileError(Exception):
    """A recorded-profile operation was invalid; ``user_message`` is safe to show."""

    def __init__(self, msg: str) -> None:
        super().__init__(msg)
        self.user_message = msg


def complete_recorded_profile(profile: RecordedProfile, text: str) -> RecordedProfile:
    """Finalize a COMMISSIONED sitting: the write-up arrives (#2632).

    Sets the character's physical description through the canonical
    ``set_physical_description`` seam, stamps IC datetime + active Era
    (mirroring ProfileTextVersion), and archives the text forever — recorded
    profiles are never edited or deleted afterwards.
    """
    from world.character_sheets.services import set_physical_description  # noqa: PLC0415
    from world.game_clock.models import GameClock  # noqa: PLC0415
    from world.npc_services.constants import RecordedProfileStatus  # noqa: PLC0415
    from world.stories.models import Era  # noqa: PLC0415

    if profile.status != RecordedProfileStatus.COMMISSIONED:
        msg = "This profile has already been recorded."
        raise RecordedProfileError(msg)
    if not text.strip():
        msg = "The profile text can't be empty."
        raise RecordedProfileError(msg)

    clock = GameClock.get_active()
    with transaction.atomic():
        profile.text = text
        profile.status = RecordedProfileStatus.RECORDED
        profile.recorded_at = timezone.now()
        profile.ic_date = clock.get_ic_now() if clock else None
        profile.era = Era.objects.get_active()
        profile.save(update_fields=["text", "status", "recorded_at", "ic_date", "era"])
        set_physical_description(profile.persona.character_sheet, text)
    return profile
