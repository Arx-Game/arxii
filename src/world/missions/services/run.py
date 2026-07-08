"""Mission-run lifecycle services — share + staff-assign.

The NPC-mediated accept flow now lives on the unified offer framework:
``world.missions.services.offer_handler.issue_mission`` is the MISSION
effect handler dispatched by ``world.npc_services.services.resolve_offer``
once the player selects a MISSION-kind ``NPCServiceOffer``. Per #686.

This module retains ``staff_assign_mission`` (staff-power drop without a
giver context — used by the Phase-D staff-assign action) and
``share_mission`` (the non-contract-holder participant add).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from evennia_extensions.models import RoomProfile
from world.missions.models import (
    MissionInstance,
    MissionNode,
    MissionParticipant,
)
from world.missions.services.resolution import enter_node

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.missions.models import MissionInvite, MissionTemplate
    from world.projects.models import Project
    from world.scenes.models import Persona


def _entry_node(template: MissionTemplate) -> MissionNode:
    """Return the template's unique entry node.

    The single-entry-node invariant is enforced by ``MissionNode.clean()``,
    so this is a safe ``.get()``. Missing entry node is an authoring error
    and surfaces here as ``MissionNode.DoesNotExist`` — loud, not silent.
    """
    return MissionNode.objects.get(template=template, is_entry=True)


def _template_has_project_lines(template: MissionTemplate) -> bool:
    """True if any route-parented reward template on this template uses sink=PROJECT (#2045).

    Candidate-parented PROJECT lines are rejected by clean(), so only route-parented
    lines can exist. Used by the issue-time refusal gate: a template carrying PROJECT
    reward lines must not issue an instance with no bound project.
    """
    from world.missions.constants import DeedRewardSink  # noqa: PLC0415
    from world.missions.models import MissionOptionRouteReward  # noqa: PLC0415

    return MissionOptionRouteReward.objects.filter(
        sink=DeedRewardSink.PROJECT,
        route__isnull=False,
        route__option__node__template=template,
    ).exists()


def anchor_room_for(character: ObjectDB) -> RoomProfile | None:
    """The grant-time anchor: the RoomProfile of the character's location (#885).

    Uniform across all three grant paths — the trigger grant happens while
    standing in the trigger room, the NPC offer in the NPC's room, the
    staff assign wherever the character is. ``None`` (no location, or a
    location with no profile — non-room containers) means a placeless
    grant: ANCHOR-mode options simply never fire for that run.
    """
    location = character.location
    if location is None:
        return None
    try:
        return location.room_profile
    except RoomProfile.DoesNotExist:
        return None


@transaction.atomic
def staff_assign_mission(
    template: MissionTemplate,
    character: ObjectDB,
    *,
    project: Project | None = None,
) -> MissionInstance:
    """Staff-power: drop a mission on a character without a giver context.

    Bypasses all availability filters (predicate / cooldown / level band /
    access tier). Used by the staff-assign action so operators can hand-
    place missions for testing, narrative reasons, or recovery scenarios.

    ``project`` optionally binds the run to a live Project (#2045) — mirrors
    how MissionOfferDetails.target_project binds offer-issued runs. The GM
    assignment path (#2048's ``gm_assign_mission``) will take the same kwarg;
    coordinated in whichever PR lands second.

    Wrapped in ``@transaction.atomic`` so a failure in ``enter_node`` rolls
    back the half-created MissionInstance + MissionParticipant.
    """
    if project is None and _template_has_project_lines(template):
        msg = (
            f"Template '{template.name}' has PROJECT reward lines but no project "
            "is bound — refusing to issue an unbound instance (#2045)."
        )
        raise ValueError(msg)
    instance = MissionInstance.objects.create(
        template=template,
        anchor_room=anchor_room_for(character),
        target_project=project,
    )
    MissionParticipant.objects.create(
        instance=instance,
        character=character,
        is_contract_holder=True,
    )
    enter_node(instance, _entry_node(template))
    return instance


@transaction.atomic
def grant_rescue_mission(
    template: MissionTemplate,
    character: ObjectDB,
    rescue_target: CharacterSheet,
) -> MissionInstance:
    """Grant a rescue run targeting a captive (#931 Phase 4 rescue).

    Mirrors :func:`staff_assign_mission` but stamps ``rescue_target`` so the run
    knows whom it frees — its success route resolves the captive's captivity. The
    caller (a capture-site / captive-room trigger, or an explicit ally grant)
    supplies the authored rescue template.
    """
    instance = MissionInstance.objects.create(
        template=template,
        anchor_room=anchor_room_for(character),
        rescue_target=rescue_target,
    )
    MissionParticipant.objects.create(
        instance=instance,
        character=character,
        is_contract_holder=True,
    )
    enter_node(instance, _entry_node(template))
    return instance


@transaction.atomic
def grant_captive_mission(template: MissionTemplate, character: ObjectDB) -> MissionInstance:
    """Grant a captive their own loop on capture (#931 Phase 4 captive agency).

    Mirrors :func:`staff_assign_mission` — no ``rescue_target`` (the captive frees
    themselves, they don't rescue another). The grant happens after the captive is
    moved into the cell, so ``anchor_room_for`` anchors the run to the cell: the
    escape + get-word-out options are the captive's agency from inside it. The
    caller supplies the authored (override-then-default) captive template.
    """
    instance = MissionInstance.objects.create(
        template=template,
        anchor_room=anchor_room_for(character),
    )
    MissionParticipant.objects.create(
        instance=instance,
        character=character,
        is_contract_holder=True,
    )
    enter_node(instance, _entry_node(template))
    return instance


def share_mission(
    instance: MissionInstance,
    other_character: ObjectDB,
) -> MissionParticipant:
    """Add ``other_character`` as a non-holder participant to ``instance``.

    Design §10: sharees are full participants but never bear the
    contractual consequence — no cooldown row, no giver linkage.
    """
    return MissionParticipant.objects.create(
        instance=instance,
        character=other_character,
        is_contract_holder=False,
    )


class InviteError(Exception):
    """A typed error from the mission invite services (#887).

    Carries a user-safe message (never an internal str()).
    """

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


_ERR_NOT_ACTIVE = "That mission is not active."
_ERR_NOT_HOLDER = "Only the contract holder may invite others."
_ERR_ALREADY_PARTICIPANT = "They are already part of that mission."
_ERR_ALREADY_RESPONDED = "You have already responded to that invitation."
_ERR_RUN_NOT_ACTIVE = "That mission is no longer active."


def invite_to_mission(
    instance: MissionInstance,
    holder_persona: Persona,
    invitee_persona: Persona,
) -> MissionInvite:
    """Create a PENDING invite for ``invitee_persona`` to join ``instance``.

    Validates the inviter is the instance's contract holder and the run is
    ACTIVE; rejects if the invitee is already a participant. Consent is opt-in
    participation (ADR-0024 — not a behavior-altering effect), mirroring
    ``EventInvitation``'s RSVP rather than the ``SceneActionRequest`` flow.
    """
    from world.missions.constants import MissionStatus  # noqa: PLC0415
    from world.missions.models import MissionInvite, MissionParticipant  # noqa: PLC0415
    from world.missions.services.multiplayer import contract_holder  # noqa: PLC0415

    if instance.status != MissionStatus.ACTIVE:
        raise InviteError(_ERR_NOT_ACTIVE)
    holder = contract_holder(instance)
    if holder.character.sheet_data.primary_persona.pk != holder_persona.pk:
        raise InviteError(_ERR_NOT_HOLDER)
    if MissionParticipant.objects.filter(
        instance=instance, character_id=invitee_persona.character_sheet.character_id
    ).exists():
        raise InviteError(_ERR_ALREADY_PARTICIPANT)
    return MissionInvite.objects.create(
        instance=instance,
        target_persona=invitee_persona,
        invited_by=holder_persona,
    )


def respond_to_mission_invite(
    invite: MissionInvite,
    decision: MissionInvite.Response,
) -> MissionParticipant | None:
    """Resolve a PENDING invite. On ACCEPT, calls ``share_mission``.

    Raises ``InviteError`` if the run is no longer active or the invite was
    already responded to. Returns the new ``MissionParticipant`` on accept;
    ``None`` on decline.
    """
    from django.utils import timezone  # noqa: PLC0415

    from world.missions.constants import MissionStatus  # noqa: PLC0415
    from world.missions.models import MissionInvite  # noqa: PLC0415

    if invite.response != MissionInvite.Response.PENDING:
        raise InviteError(_ERR_ALREADY_RESPONDED)
    if invite.instance.status != MissionStatus.ACTIVE:
        raise InviteError(_ERR_RUN_NOT_ACTIVE)
    invite.response = decision
    invite.responded_at = timezone.now()
    invite.save(update_fields=["response", "responded_at"])
    if decision != MissionInvite.Response.ACCEPTED:
        return None
    invitee_character = invite.target_persona.character_sheet.character
    return share_mission(invite.instance, invitee_character)
