"""Servant pampering ambience: meal + bath prep (#2989).

Same delay+departure/arrival-echo shape as ``servant_fetch.py`` — the core
feel is PAMPERING (ratified amendment 2): a servant is called, departs,
returns, and the character feels attended. Meal prep is pure ambience — no
mechanical payoff (the "appetites"/"catering" tie-ins the original issue
named don't verify against code: ``world.species.appetites`` is the
vampire/Vulpi/Vesperi blood hunger anchor, unrelated to ordinary meals, and
``world.events`` catering is Event-scoped and PC-driven, not an ambient
household mechanic — see the #2989 spec's anti-reinvention ledger). Bath
prep carries one small gated positive effect: a flat fatigue recovery
through the existing ``recover_fatigue`` partial-recovery seam (#2852, "the
seam food and drink restore through") — a genuine one-line hook, so it ships
rather than staying prop-only.

Eligibility mirrors ``can_servant_fetch``: owner/tenant standing at the
actor's location + an active SERVANT ``NPCAssignment`` in reach.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from evennia.utils import delay

from world.npc_services.servant_fetch import find_servant

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

#: Default delay (seconds) before meal/bath prep completes.
DEFAULT_AMBIENCE_DELAY_SECONDS: float = 5.0

#: Flat physical-fatigue recovery from a bath (#2852 partial-recovery seam).
#: PLACEHOLDER magnitude — small and gated, per the ratified amendment; not
#: meant to rival a full rest.
BATH_FATIGUE_RECOVERY: int = 10

# Authored pose text, module constants so a future content pass can vary
# them without touching the delay/echo plumbing.
MEAL_DEPARTURE_TEXT = "{servant} bows and departs to prepare a meal for {actor}."
MEAL_ARRIVAL_TEXT = "{servant} returns bearing a meal, laid out for {actor}."
BATH_DEPARTURE_TEXT = "{servant} bows and departs to draw a bath for {actor}."
BATH_ARRIVAL_TEXT = "{servant} returns to announce the bath is ready for {actor}."


def can_servant_pamper(*, actor: ObjectDB) -> bool:
    """Eligibility: may a servant prepare a meal/bath for this actor?

    True only when the actor has an active persona with owner or tenant
    standing at their current location AND an active SERVANT ``NPCAssignment``
    exists in reach (mirrors ``servant_fetch.can_servant_fetch``'s standing
    check, minus the item-reachability legs that don't apply here).
    """
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    from world.locations.services import is_owner, is_tenant  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    try:
        sheet = actor.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return False
    persona = active_persona_for_sheet(sheet)
    if persona is None:
        return False

    if actor.location is None:
        return False
    if not (is_owner(persona, actor.location) or is_tenant(persona, actor.location)):
        return False

    return find_servant(actor.location) is not None


def prepare_meal(actor: ObjectDB, delay_seconds: float = DEFAULT_AMBIENCE_DELAY_SECONDS) -> bool:
    """Queue a delayed meal-prep with room echoes. Pure ambience, no payoff.

    Returns True if the prep was queued (does not itself check eligibility —
    callers gate via ``can_servant_pamper``).
    """
    return _queue_pamper(
        actor,
        delay_seconds=delay_seconds,
        departure_text=MEAL_DEPARTURE_TEXT,
        arrival_text=MEAL_ARRIVAL_TEXT,
        on_complete=None,
    )


def prepare_bath(actor: ObjectDB, delay_seconds: float = DEFAULT_AMBIENCE_DELAY_SECONDS) -> bool:
    """Queue a delayed bath-prep with room echoes + a flat fatigue recovery.

    Returns True if the prep was queued (does not itself check eligibility —
    callers gate via ``can_servant_pamper``).
    """
    return _queue_pamper(
        actor,
        delay_seconds=delay_seconds,
        departure_text=BATH_DEPARTURE_TEXT,
        arrival_text=BATH_ARRIVAL_TEXT,
        on_complete=_recover_bath_fatigue,
    )


def _queue_pamper(
    actor: ObjectDB,
    *,
    delay_seconds: float,
    departure_text: str,
    arrival_text: str,
    on_complete: Callable[[ObjectDB], None] | None,
) -> bool:
    """Shared delay+echo plumbing for ``prepare_meal``/``prepare_bath``.

    Simpler than ``servant_fetch.servant_fetch_item``'s token/cancellation
    dance — ambience has no state to roll back on cancellation (nothing
    moves), so there's no ``actor.ndb.active_fetch_token`` to register: a
    departed character simply never sees the arrival echo (the pending
    ``delay()`` callback still fires but checks ``actor.location`` against
    the room it was queued in before messaging or applying any effect).
    """
    from flows.scene_data_manager import SceneDataManager  # noqa: PLC0415
    from flows.service_functions.communication import message_location  # noqa: PLC0415

    servant = find_servant(actor.location)
    servant_name = servant.get_active_target_name() if servant else "A servant"

    sdm = SceneDataManager()
    actor_state = sdm.initialize_state_for_object(actor)
    origin_room = actor.location
    message_location(
        actor_state,
        departure_text.format(servant=servant_name, actor="$You()"),
    )

    delay(
        delay_seconds,
        _complete_pamper,
        actor,
        origin_room,
        servant_name,
        arrival_text,
        on_complete,
    )
    return True


def _complete_pamper(
    actor: ObjectDB,
    origin_room: ObjectDB,
    servant_name: str,
    arrival_text: str,
    on_complete: Callable[[ObjectDB], None] | None,
) -> None:
    """Delayed completion: arrival echo, plus an optional mechanical payoff.

    No-ops if the actor left the room the prep was queued in.
    """
    if actor.location != origin_room:
        return

    from flows.scene_data_manager import SceneDataManager  # noqa: PLC0415
    from flows.service_functions.communication import message_location  # noqa: PLC0415

    sdm = SceneDataManager()
    actor_state = sdm.initialize_state_for_object(actor)
    message_location(
        actor_state,
        arrival_text.format(servant=servant_name, actor="$You()"),
    )

    if on_complete is not None:
        on_complete(actor)


def _recover_bath_fatigue(actor: ObjectDB) -> None:
    """Bath's gated positive effect: a flat physical-fatigue recovery (#2852)."""
    from actions.constants import ActionCategory  # noqa: PLC0415
    from world.fatigue.services import recover_fatigue  # noqa: PLC0415

    sheet = actor.character_sheet
    if sheet is None:
        return
    recover_fatigue(sheet, ActionCategory.PHYSICAL, BATH_FATIGUE_RECOVERY)
