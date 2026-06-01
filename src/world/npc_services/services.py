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

from world.checks.services import perform_check
from world.npc_services.constants import DrawMode
from world.npc_services.effects import EffectResult, dispatch_offer_effect
from world.npc_services.models import (
    NPCRole,
    NPCServiceOffer,
    NPCStanding,
    OfferCooldown,
)
from world.predicates.predicates import CharacterPredicateContext, evaluate

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

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

    def __init__(self, character: ObjectDB) -> None:
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


def persona_for_character(character: ObjectDB) -> Persona:
    """Return the PC's PRIMARY persona; raise loud on missing sheet/persona.

    A played character without a sheet or PRIMARY persona is a programmer
    error per ``character_sheets/CLAUDE.md``; we surface that loudly rather
    than silently bypassing any gate that needs the persona (cooldown,
    standing, item ownership, etc.).
    """
    sheet = getattr(character, "sheet_data", None)  # noqa: GETATTR_LITERAL — reverse OneToOne, may legitimately be absent on non-Character ObjectDB
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
    character: ObjectDB
    """The PC's Evennia Character — needed for the predicate context."""
    current_rapport: int
    closed: bool = False
    results: list[EffectResult] = field(default_factory=list)


def start_interaction(
    *,
    role: NPCRole,
    persona: Persona,
    character: ObjectDB,
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


def _is_offer_eligible(
    offer: NPCServiceOffer,
    *,
    persona: Persona,
    character: ObjectDB,
    current_rapport: int,
    now: object | None = None,
) -> bool:
    """Single-offer eligibility check.

    Drives both ``available_offers`` (filtering) and ``resolve_offer``
    (single-offer re-verify). Keeping the check here means there's one
    source of truth, and ``resolve_offer`` doesn't have to re-run the
    whole queryset to verify one offer.
    """
    if offer.rapport_requirement > current_rapport:
        return False
    if offer.draw_mode != DrawMode.MENU:
        # POOL is reserved for mission migration #686 — log so authors
        # who try to use it before then get a signal instead of silent
        # absence. Conservative skip for Plan 2.
        logger.warning(
            "NPCServiceOffer %s skipped: draw_mode=%s not yet handled (see #686).",
            offer.pk,
            offer.draw_mode,
        )
        return False
    now = now or timezone.now()
    if offer.cooldown is not None:
        if OfferCooldown.objects.filter(
            offer=offer, persona=persona, available_at__gt=now
        ).exists():
            return False
    ctx = CharacterPredicateContext(character, presented_persona=persona)
    return evaluate(offer.eligibility_rule or {}, ctx)


def available_offers(session: InteractionSession) -> list[NPCServiceOffer]:
    """Return offers the PC can currently see/select, in stable order.

    Filtered by ``_is_offer_eligible`` (rapport gate + draw_mode + active
    cooldown + eligibility predicate). ``select_related("role")`` so the
    role doesn't get re-fetched per row when callers walk the result.
    """
    if session.closed:
        return []
    now = timezone.now()
    queryset = (
        NPCServiceOffer.objects.select_related("role").filter(role=session.role).order_by("pk")
    )
    return [
        offer
        for offer in queryset
        if _is_offer_eligible(
            offer,
            persona=session.persona,
            character=session.character,
            current_rapport=session.current_rapport,
            now=now,
        )
    ]


def _apply_check(
    offer: NPCServiceOffer,
    *,
    character: ObjectDB,
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
