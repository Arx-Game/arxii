"""Trigger-based mission dispatch (#729 Phase 2).

When a character enters a ``ROOM_TRIGGER`` room or examines an
``ENVIRONMENTAL_DETAIL`` object, the giver bound to that object may hand the
character a mission drawn from its ``templates`` pool. Each template self-gates
via its own ``availability_rule`` (Option A), so dispatch just filters the pool
to what the character is eligible for and draws one at uniform weight.

Guards (the anti-nag layer): the giver must be active; the character must not
already hold an active trigger-sourced mission; and a per-(giver, character)
``MissionGiverCooldown`` blocks re-dispatch for a while after a grant.

Entry points are called directly from the movement / examine hooks (the
reactive Trigger-row system is anchored to ConditionInstances and doesn't fit a
room-bound giver), wrapped so a dispatch hiccup never breaks movement/look.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from django.db.models import Q
from django.utils import timezone

from world.checks.outcome_utils import select_weighted
from world.missions.constants import GiverKind, MissionStatus
from world.missions.models import MissionGiver, MissionGiverCooldown, MissionInstance
from world.narrative.constants import NarrativeCategory
from world.narrative.services import send_narrative_message
from world.predicates.predicates import CharacterPredicateContext, evaluate

if TYPE_CHECKING:
    from datetime import datetime

    from evennia.objects.models import ObjectDB

    from world.missions.models import MissionTemplate

# Default re-offer cooldown when a drawn template carries no cooldown of its own.
_DEFAULT_COOLDOWN = timezone.timedelta(hours=12)


def maybe_dispatch_on_enter(character: ObjectDB, room: ObjectDB) -> MissionInstance | None:
    """ROOM_TRIGGER entry point — call from ``Character.at_post_move``."""
    return _dispatch_for_target(character, room, GiverKind.ROOM_TRIGGER)


def maybe_dispatch_on_examine(character: ObjectDB, obj: ObjectDB) -> MissionInstance | None:
    """ENVIRONMENTAL_DETAIL entry point — call from the examine path."""
    return _dispatch_for_target(character, obj, GiverKind.ENVIRONMENTAL_DETAIL)


def _dispatch_for_target(
    character: ObjectDB, target: ObjectDB, giver_kind: str
) -> MissionInstance | None:
    """Fast path: is ``target`` an active giver of this kind? If so, dispatch."""
    if character is None or target is None:
        return None
    giver = (
        MissionGiver.objects.filter(target=target, giver_kind=giver_kind, is_active=True)
        .prefetch_related("templates")  # noqa: PREFETCH_STRING
        .first()
    )
    if giver is None:
        return None
    return _dispatch_from_giver(giver, character)


def _dispatch_from_giver(giver: MissionGiver, character: ObjectDB) -> MissionInstance | None:
    """Eligibility-filter the giver's pool, draw one, grant + announce.

    Returns the started ``MissionInstance``, or ``None`` when nothing is offered
    (cooldown active, already holding a trigger mission, or no eligible template).
    """
    now = timezone.now()
    if MissionGiverCooldown.objects.filter(
        giver=giver, character=character, available_at__gt=now
    ).exists():
        return None
    if _holds_active_trigger_mission(character):
        return None

    ctx = CharacterPredicateContext(character)
    eligible = [
        template
        for template in giver.templates.all()
        if template.is_active and evaluate(template.availability_rule or {}, ctx)
    ]
    if not eligible:
        return None

    # Uniform draw: MissionTemplate has no ``.weight`` attribute, so select_weighted
    # falls back to weight 1 for every entry. (Delegates the RNG to the codebase's
    # reviewed selection helper rather than a fresh random.* call.)
    template = select_weighted(eligible)
    instance = _grant(template, character)
    _write_cooldown(giver, character, template, now)
    _announce(character, template)
    return instance


def _holds_active_trigger_mission(character: ObjectDB) -> bool:
    """True if the character already holds a contract on an active trigger-sourced
    mission (source_offer is null = not NPC-mediated)."""
    return MissionInstance.objects.filter(
        Q(participants__character=character)
        & Q(participants__is_contract_holder=True)
        & Q(status=MissionStatus.ACTIVE)
        & Q(source_offer__isnull=True)
    ).exists()


def _grant(template: MissionTemplate, character: ObjectDB) -> MissionInstance:
    """Start the run via the canonical no-context primitive (no offer/persona)."""
    from world.missions.services.run import staff_assign_mission  # noqa: PLC0415

    return staff_assign_mission(template, character)


def _write_cooldown(
    giver: MissionGiver, character: ObjectDB, template: MissionTemplate, now: datetime
) -> None:
    available_at = now + (template.cooldown or _DEFAULT_COOLDOWN)
    MissionGiverCooldown.objects.update_or_create(
        giver=giver, character=character, defaults={"available_at": available_at}
    )


def _announce(character: ObjectDB, template: MissionTemplate) -> None:
    """Tell the player a mission hook found them (best-effort; never fatal)."""
    with contextlib.suppress(Exception):
        send_narrative_message(
            recipients=[character.sheet_data],
            body=f"Something here pulls you toward a task — {template.name}.",
            category=NarrativeCategory.HAPPENSTANCE,
            ooc_note=f"Surfaced by a trigger giver (template #{template.pk}).",
        )
