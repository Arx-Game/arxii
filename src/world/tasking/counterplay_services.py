"""Spy-vs-spy counterplay (#2820 phase 4).

Four verbs against a room's sitting listener, plus the consent boundary:

- **suppress**: intimidate the agent into silence — the meter freezes, and
  the handler is told nothing (a suppressed post and an unlucky one look
  identical on the board).
- **flip**: seduce the agent into a double allegiance. The original row
  still shows active; the flipper decides what actually gets delivered —
  including planted red herrings (accusation-provenance secrets, whose
  credibility is contested through the existing AccusationRebuttal loop).
- **detect**: a perception sweep that reveals listener posts in the room.
  Consentless — defending yourself against surveillance is always open
  (the Tom/Bob/Fred rule).
- **clear**: room authority expels listener assignments. Consentless.

Offensive moves (suppress/flip/plant) against a PC-run network route through
the antagonism-consent register via the ``espionage`` category; staff-authored
NPC networks have no PC owners and are always-on targets — the safe tier.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.tasking.exceptions import TaskingError
from world.tasking.models import ListenerPost

if TYPE_CHECKING:
    from evennia_extensions.models import RoomProfile
    from world.clues.models import Clue
    from world.scenes.models import Persona

SUPPRESS_CHECK_NAME = "Intimidation"
FLIP_CHECK_NAME = "Seduction"
DETECT_CHECK_NAMES = ("Perception", "Search", "Investigation")
ESPIONAGE_CONSENT_CATEGORY = "espionage"

# PLACEHOLDER tuning (#2820 phase 4).
SUPPRESS_BASE_DIFFICULTY = 10
FLIP_BASE_DIFFICULTY = 20
DETECT_BASE_DIFFICULTY = 10
SUPPRESS_DURATION = timedelta(days=14)


class CounterplayError(TaskingError):
    user_message = "That move is not possible here."


class ConsentBlockedError(CounterplayError):
    user_message = "They are not open to that kind of play."


class NotColocatedError(CounterplayError):
    user_message = "You must be in the room with the agent."


class NoCheckSeededError(CounterplayError):
    user_message = "PLACEHOLDER: the needed check type is not seeded on this shard."


def _tenure_for(persona: Persona):
    from world.roster.models import RosterTenure  # noqa: PLC0415

    return RosterTenure.objects.filter(
        roster_entry__character_sheet_id=persona.character_sheet_id,
        end_date__isnull=True,
    ).first()


def _owner_tenures(post: ListenerPost) -> list:
    """The PC tenures whose consent gates moves against this post's agent.

    Persona-held agent: the holding persona. Org-held: the org's active
    leadership. A staff-authored NPC network has no PC tenures — empty list
    means nothing gates (always-on target).
    """
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    asset = post.assignment.npc_asset
    if asset is None:
        return []
    if asset.promoter_persona_id is not None:
        tenure = _tenure_for(asset.promoter_persona)
        return [tenure] if tenure else []
    leaders = OrganizationMembership.objects.filter(
        organization_id=asset.promoter_org_id,
        left_at__isnull=True,
        exiled_at__isnull=True,
        rank__can_manage_ranks=True,
    ).select_related("persona")
    tenures = [_tenure_for(m.persona) for m in leaders]
    return [t for t in tenures if t is not None]


def _assert_consent(actor: Persona, post: ListenerPost) -> None:
    from world.consent.models import SocialConsentCategory  # noqa: PLC0415
    from world.consent.services import consent_blocks_targeting  # noqa: PLC0415

    category = SocialConsentCategory.objects.filter(key=ESPIONAGE_CONSENT_CATEGORY).first()
    actor_tenure = _tenure_for(actor)
    for owner_tenure in _owner_tenures(post):
        if consent_blocks_targeting(
            owner_tenure=owner_tenure,
            category=category,
            actor_tenure=actor_tenure,
        ):
            raise ConsentBlockedError


def _assert_colocated(actor: Persona, post: ListenerPost) -> None:
    character = actor.character_sheet.character
    if character.db_location_id != post.assignment.room_id:
        raise NotColocatedError


def _check_type_or_raise(name: str):
    from world.checks.models import CheckType  # noqa: PLC0415

    check_type = CheckType.objects.filter(name=name).first()
    if check_type is None:
        raise NoCheckSeededError
    return check_type


def _roll(actor: Persona, check_name: str, difficulty: int, *, target_persona=None):
    """The actor's counterplay roll — eased/hardened by the target NPC's
    personality (#2827 phase 4): a venal listener is easier to buy."""
    from world.checks.services import perform_check_with_modifiers  # noqa: PLC0415
    from world.npc_services.personality import preference_modifier  # noqa: PLC0415

    character = actor.character_sheet.character
    check_type = _check_type_or_raise(check_name)
    return perform_check_with_modifiers(
        character,
        check_type,
        target_difficulty=difficulty,
        extra_modifiers=preference_modifier(target_persona, check_type),
    )


@transaction.atomic
def suppress_listener(actor: Persona, post: ListenerPost) -> bool:
    """Intimidate the sitting listener into silence. Returns success.

    On success the meter silently freezes for SUPPRESS_DURATION. The handler
    learns nothing either way — paranoia is the feature.
    """
    if actor.pk == post.handler_id:
        raise CounterplayError
    _assert_colocated(actor, post)
    _assert_consent(actor, post)
    target = post.assignment.npc_asset.asset_persona if post.assignment.npc_asset else None
    result = _roll(
        actor,
        SUPPRESS_CHECK_NAME,
        SUPPRESS_BASE_DIFFICULTY + post.check_difficulty,
        target_persona=target,
    )
    if result.success_level <= 0:
        return False
    post.suppressed_until = timezone.now() + SUPPRESS_DURATION
    post.save(update_fields=["suppressed_until"])
    return True


@transaction.atomic
def flip_listener(actor: Persona, post: ListenerPost) -> bool:
    """Turn the sitting listener into a double agent. Returns success.

    On success the actor gains their own co-owner row on the asset persona
    (the #2295 pattern — CHARM acquisition) and hidden control of the post:
    real catches stop; planted red herrings flow instead.
    """
    from world.assets.constants import AssetAcquisitionSource, AssetStatus  # noqa: PLC0415
    from world.assets.models import NPCAsset  # noqa: PLC0415

    if actor.pk == post.handler_id:
        raise CounterplayError
    _assert_colocated(actor, post)
    _assert_consent(actor, post)
    target = post.assignment.npc_asset.asset_persona if post.assignment.npc_asset else None
    result = _roll(
        actor,
        FLIP_CHECK_NAME,
        FLIP_BASE_DIFFICULTY + post.check_difficulty,
        target_persona=target,
    )
    if result.success_level <= 0:
        return False

    asset = post.assignment.npc_asset
    already_owns = NPCAsset.objects.filter(
        promoter_persona=actor,
        asset_persona=asset.asset_persona,
        status=AssetStatus.ACTIVE,
    ).exists()
    if not already_owns:
        NPCAsset.objects.create(
            promoter_persona=actor,
            asset_persona=asset.asset_persona,
            role_context=asset.role_context,
            acquisition_source=AssetAcquisitionSource.CHARM,
        )
    post.flipped_controller = actor
    post.save(update_fields=["flipped_controller"])
    return True


@transaction.atomic
def plant_red_herring(
    controller: Persona,
    post: ListenerPost,
    *,
    subject_sheet,
    content: str,
) -> Clue:
    """Queue a false catch on a flipped post (#2820 phase 4).

    Mints an ACCUSATION-provenance secret (the flip controller is its hidden
    author) and a clue targeting it; the post's next harvest delivers the
    clue as if it were real. The lie is contestable later through the
    existing AccusationRebuttal loop — espionage disinformation and the
    renown fake-accusation game are one mechanic.
    """
    from world.clues.constants import ClueResolution, ClueTargetKind  # noqa: PLC0415
    from world.clues.models import Clue  # noqa: PLC0415
    from world.secrets.services import mint_accusation  # noqa: PLC0415

    if post.flipped_controller_id != controller.pk:
        raise CounterplayError
    secret = mint_accusation(
        accuser_persona=controller,
        subject_sheet=subject_sheet,
        content=content,
    )
    clue, _ = Clue.objects.get_or_create(
        target_kind=ClueTargetKind.SECRET,
        target_secret=secret,
        defaults={
            "name": "An Agent's Whisper",
            "description": (
                "PLACEHOLDER Your listener leans close: something happened here, "
                "and they caught the shape of it."
            ),
            "resolution_mode": ClueResolution.AUTOMATIC,
        },
    )
    post.pending_plant = clue
    post.save(update_fields=["pending_plant"])
    return clue


def detect_listeners(actor: Persona, room: RoomProfile) -> list[dict]:
    """Sweep the room for informants. Consentless (defensive).

    One perception-family roll; each active listener whose difficulty the
    roll clears is revealed (agent name only — the handler stays unknown;
    finding out WHO they report to is its own investigation).
    """
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.checks.services import perform_check_with_modifiers  # noqa: PLC0415

    character = actor.character_sheet.character
    if character.db_location_id != room.pk:
        raise NotColocatedError
    check_type = CheckType.objects.filter(name__in=DETECT_CHECK_NAMES).first()
    if check_type is None:
        raise NoCheckSeededError

    revealed: list[dict] = []
    posts = ListenerPost.objects.filter(
        assignment__room_id=room.pk,
        assignment__is_active=True,
    ).select_related("assignment__npc_asset")
    for post in posts:
        result = perform_check_with_modifiers(
            character,
            check_type,
            target_difficulty=DETECT_BASE_DIFFICULTY + post.check_difficulty,
        )
        if result.success_level > 0:
            asset = post.assignment.npc_asset
            revealed.append(
                {
                    "post_id": post.pk,
                    "agent_name": str(asset.asset_persona) if asset else "",
                }
            )
    return revealed


@transaction.atomic
def clear_room_listeners(actor: Persona, room: RoomProfile) -> int:
    """Room authority expels listener assignments. Consentless (defensive).

    Gated on the same owner/tenant standing room features use. Returns the
    number of assignments retired.
    """
    from world.npc_services.models import AssignmentRole, NPCAssignment  # noqa: PLC0415
    from world.room_features.services import can_modify_room_features  # noqa: PLC0415

    if not can_modify_room_features(actor, room.objectdb):
        raise CounterplayError
    now = timezone.now()
    assignments = NPCAssignment.objects.filter(
        room=room,
        assignment_role=AssignmentRole.LISTENER,
        is_active=True,
    )
    count = 0
    for assignment in assignments:
        assignment.is_active = False
        assignment.ended_at = now
        assignment.save(update_fields=["is_active", "ended_at"])
        count += 1
    return count
