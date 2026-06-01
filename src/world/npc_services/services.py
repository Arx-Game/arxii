"""Service functions for the unified NPC service framework.

- Persona resolution helpers bridge legacy ObjectDB-keyed call paths
  (mission ``accept_mission``) to the new persona-keyed NPCStanding.
- ``upsert_standing_cooldown`` is the shared cooldown-upsert mission code
  uses.
- ``start_interaction`` / ``resolve_offer`` / ``end_interaction`` make up
  the in-memory interaction state machine. State is ephemeral — lives in
  the dataclass instance for the duration of one interaction and is never
  persisted. Durable side effects go to ``NPCStanding`` on close and to
  the effect handler's downstream object on each final-action grant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.missions.predicates import CharacterPredicateContext, evaluate
from world.npc_services.constants import DrawMode
from world.npc_services.effects import EffectResult, dispatch_offer_effect
from world.npc_services.models import NPCRole, NPCServiceOffer, NPCStanding

if TYPE_CHECKING:
    from datetime import timedelta

    from evennia.objects.models import ObjectDB

    from world.missions.models import MissionGiver
    from world.scenes.models import Persona


def resolve_npc_persona_for_giver(giver: MissionGiver) -> Persona | None:
    """Return the NPC persona for a mission giver, or None if not resolvable.

    Only ``NPC``-kind givers can have a persona — ``ROOM_TRIGGER`` and
    ``ENVIRONMENTAL_DETAIL`` givers point at non-Character ObjectDBs and so
    have no persona. Returns None in those cases plus any case where the
    target ObjectDB is missing, has no character sheet, or has no PRIMARY
    persona row.
    """
    from world.missions.constants import GiverKind  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415

    if giver.giver_kind != GiverKind.NPC or giver.target_id is None:
        return None
    sheet = getattr(giver.target, "sheet_data", None)  # noqa: GETATTR_LITERAL — reverse OneToOne absent on non-Character objects
    if sheet is None:
        return None
    try:
        return sheet.primary_persona
    except Persona.DoesNotExist:
        return None


def resolve_persona_for_character(character: ObjectDB) -> Persona | None:
    """Return the PC's primary persona for an Evennia Character ObjectDB.

    Returns None for non-Character objects (no ``sheet_data`` reverse FK) or
    Character objects without a CharacterSheet or PRIMARY persona row.

    NPCStanding is keyed on personas, not Evennia ObjectDB rows. This helper
    bridges legacy ObjectDB-keyed call paths (mission ``accept_mission``,
    etc.) until they migrate to passing personas directly.
    """
    from world.scenes.models import Persona  # noqa: PLC0415

    sheet = getattr(character, "sheet_data", None)  # noqa: GETATTR_LITERAL — reverse OneToOne absent on non-Character objects
    if sheet is None:
        return None
    try:
        return sheet.primary_persona
    except Persona.DoesNotExist:
        return None


@transaction.atomic
def upsert_standing_cooldown(
    *,
    persona: Persona,
    npc_persona: Persona,
    cooldown: timedelta,
) -> NPCStanding:
    """Upsert an NPCStanding row, setting ``available_at = now + cooldown``.

    Affection is left untouched (defaults to 0 on first creation; preserved
    on subsequent upserts). Used by mission ``accept_mission`` to throttle
    re-acceptance from the same NPC by the same PC persona.
    """
    standing, _created = NPCStanding.objects.update_or_create(
        persona=persona,
        npc_persona=npc_persona,
        defaults={"available_at": timezone.now() + cooldown},
    )
    return standing


# ---------------------------------------------------------------------------
# Interaction state machine — ephemeral per-interaction state.
#
# Lives in the player's session for the duration of one interaction. NOT
# persisted. Carries: starting rapport (role default + standing affection for
# class 2-4 NPCs), the offers currently surfaced, optional pending-check
# state. On end_interaction the standing row is updated for class 2-4 NPCs
# (the persistent affection movement) and the session is discarded.
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
    ``end_interaction``. Never persisted — survives only as long as the
    caller holds a reference. The downstream side effects (effect handler
    output, NPCStanding update) are persistent.
    """

    role: NPCRole
    persona: Persona
    npc_persona: Persona | None
    """The NPC's persona, or None for class-1 nameless functionaries."""
    character: ObjectDB
    """The PC's Evennia Character — needed to construct the predicate context."""
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


def available_offers(session: InteractionSession) -> list[NPCServiceOffer]:
    """Return offers the PC can currently see/select, in stable order.

    Filtered by:
      * ``rapport_requirement <= session.current_rapport``
      * ``eligibility_rule`` evaluates True against a PredicateContext
        built from ``session.character`` + ``session.persona``

    Draw mode is honoured at the data layer — MENU offers are always
    listed when eligible; POOL offers (future mission migration; #686)
    will sample from the matching pool. Plan 2 only exercises MENU.
    """
    if session.closed:
        return []
    ctx = CharacterPredicateContext(session.character, presented_persona=session.persona)
    queryset = NPCServiceOffer.objects.filter(role=session.role).order_by("pk")
    eligible: list[NPCServiceOffer] = []
    for offer in queryset:
        if offer.rapport_requirement > session.current_rapport:
            continue
        if offer.draw_mode != DrawMode.MENU:
            # POOL handling is deferred to #686; for Plan 2 we don't surface
            # POOL offers from a MENU-mode interaction. Leaving the offer
            # out is the conservative default.
            continue
        if not evaluate(offer.eligibility_rule or {}, ctx):
            continue
        eligible.append(offer)
    return eligible


@transaction.atomic
def resolve_offer(
    session: InteractionSession,
    offer: NPCServiceOffer,
) -> EffectResult:
    """Grant ``offer`` in ``session`` — dispatch its effect, update rapport.

    For final offers (``is_final=True``) the session closes after the
    effect is dispatched; subsequent ``available_offers`` returns []. For
    non-final offers the rapport adjusts by ``rapport_delta_success`` and
    the session stays open for the next interaction step.

    Re-checks eligibility at grant time so a stale UI can't grant an
    offer the PC no longer qualifies for. Raises ``ValueError`` if the
    offer isn't currently eligible (the UI should never present an
    ineligible offer — surfacing the error catches authoring or
    client-side bugs loudly).
    """
    if session.closed:
        msg = "Cannot resolve an offer on a closed interaction session."
        raise ValueError(msg)
    if offer.role_id != session.role.pk:
        msg = (
            f"Offer {offer.pk} belongs to role {offer.role_id}, not session role {session.role.pk}."
        )
        raise ValueError(msg)
    if offer not in available_offers(session):
        msg = f"Offer {offer.pk} ({offer.label!r}) is not currently eligible for this session."
        raise ValueError(msg)
    result = dispatch_offer_effect(offer, session.persona)
    session.results.append(result)
    if offer.is_final:
        session.current_rapport += offer.rapport_delta_success
        end_interaction(session)
    else:
        session.current_rapport += offer.rapport_delta_success
    return result


def end_interaction(session: InteractionSession) -> None:
    """Close the session and persist final affection for class 2-4 NPCs.

    ``start_interaction`` seeded ``current_rapport`` with
    ``role.default_rapport_starting_value + existing_affection``. The new
    durable affection is therefore ``current_rapport - role default`` — we
    overwrite ``NPCStanding.affection`` with that value (not accumulate).
    No-op for class-1 (``npc_persona is None``).
    """
    if session.closed:
        return
    session.closed = True
    if session.npc_persona is None:
        return
    new_affection = session.current_rapport - session.role.default_rapport_starting_value
    standing, _ = NPCStanding.objects.get_or_create(
        persona=session.persona,
        npc_persona=session.npc_persona,
        defaults={"affection": new_affection},
    )
    if standing.affection != new_affection:
        standing.affection = new_affection
        standing.save(update_fields=["affection", "last_changed_at"])
