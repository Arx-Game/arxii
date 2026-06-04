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
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from core_management.permissions import is_staff_observer
from world.checks.services import perform_check
from world.missions.constants import AccessTier, MissionStatus
from world.missions.models import MissionInstance
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
from world.predicates.predicates import CharacterPredicateContext, evaluate

if TYPE_CHECKING:
    from typeclasses.characters import Character
    from world.scenes.models import Persona

logger = logging.getLogger(__name__)


class MissingPrimaryPersonaError(LookupError):
    """A played Character is missing a CharacterSheet or PRIMARY persona.

    Per ``character_sheets/CLAUDE.md`` every played character has a
    CharacterSheet with a PRIMARY persona — that's a load-bearing repo
    invariant. Hitting this exception means something upstream broke that
    invariant (character_creation didn't finalize, test scaffolding
    skipped sheet setup, etc.) and we fail loud rather than silently
    bypass gates that depend on the persona.
    """

    def __init__(self, character: Character) -> None:
        super().__init__(
            f"Character {character!r} has no PRIMARY persona — required invariant "
            "(see character_sheets/CLAUDE.md). Check character_creation finalize "
            "or test setup."
        )
        self.character = character


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


def persona_for_character(character: Character) -> Persona:
    """Return the PC's PRIMARY persona; raise loud on missing sheet/persona.

    A played character without a sheet or PRIMARY persona is a programmer
    error per ``character_sheets/CLAUDE.md``; we surface that loudly rather
    than silently bypassing any gate that needs the persona (cooldown,
    standing, item ownership, etc.).
    """
    sheet = getattr(character, "sheet_data", None)  # noqa: GETATTR_LITERAL
    if sheet is None:
        raise MissingPrimaryPersonaError(character)
    try:
        return sheet.primary_persona
    except Exception as exc:
        raise MissingPrimaryPersonaError(character) from exc


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
    sheet = getattr(character, "sheet_data", None)  # noqa: GETATTR_LITERAL
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


def _is_offer_eligible(  # noqa: PLR0913
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
       ``access_tier``, ``level_band``), and the AND-composed predicate
       ``template.availability_rule`` ∧ ``details.requirements_override``
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
    ctx = CharacterPredicateContext(character, presented_persona=persona)
    return evaluate(offer.eligibility_rule or {}, ctx)


def _mission_gates_pass(  # noqa: PLR0911
    *,
    offer: NPCServiceOffer,
    persona: Persona,
    character: Character,
    cache: _EligibilityCache,
) -> bool:
    """Apply the MISSION-only gates from ``_is_offer_eligible`` (#686).

    Ordered cheapest-first: cached PC/role gates → details lookup → template
    field gates → composed predicate. Template-side gates (``is_active``,
    ``access_tier``, ``level_band``, ``availability_rule``) are enforced
    here per spec — eligibility composes ``template.availability_rule`` ∧
    ``details.requirements_override`` ∧ ``offer.eligibility_rule``.
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
    if template.access_tier == AccessTier.STAFF_ONLY and not is_staff_observer(character):
        return False
    sheet = getattr(character, "sheet_data", None)  # noqa: GETATTR_LITERAL
    if sheet is None:
        # No sheet → no level → can't satisfy the level-band gate. Fail closed
        # consistently with the PC-cap gate above (cache.pc_at_npc_cap is True
        # when sheet is None, so we'd never reach here in practice, but make
        # the local-only path defensive in case the cache is bypassed).
        return False
    if not (template.level_band_min <= sheet.current_level <= template.level_band_max):
        return False
    ctx = CharacterPredicateContext(character, presented_persona=persona)
    if template.availability_rule and not evaluate(template.availability_rule, ctx):
        return False
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
    sampled down to at most ``pool_count`` via a weighted draw without
    replacement (``_draw_pool_offers``). The mission state machine passes
    ``pool_count`` derived from the placeholder
    ``random.randint(1, min(4, eligible_count))`` — see #726 for the
    standing-/level-/chain-driven policy that replaces the placeholder.
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
    """Weighted draw of up to ``count`` offers from ``offers`` without replacement.

    Weight source is kind-specific (see ``_weight_for_offer``). Per-slot
    arc-replace logic (``MissionTemplate.percent_replace`` against an
    active-Era arc pool) is deferred to **#726** along with the
    standing-/level-/chain-driven count policy — both are part of the
    same rich-policy follow-up.
    """
    from world.checks.outcome_utils import select_weighted  # noqa: PLC0415

    if count <= 0 or not offers:
        return []

    remaining = [_WeightedOffer(offer=o, weight=_weight_for_offer(o)) for o in offers]
    remaining = [w for w in remaining if w.weight > 0]
    if not remaining:
        return []

    drawn: list[NPCServiceOffer] = []
    while remaining and len(drawn) < count:
        pick = select_weighted(remaining)
        drawn.append(pick.offer)
        remaining.remove(pick)
    return drawn


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
