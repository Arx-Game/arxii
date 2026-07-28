"""Listener-post services — the standing informant loop (#2820 phase 3).

Post an agent in a room; a weekly game-clock sweep rolls their tradecraft and
accrues buzz from the room's mechanical residue (scenes held there, secrets
minted there — never prose). Crossing the threshold banks a harvest keyed to
a real caught record when one exists; the handler must physically visit the
room to collect, which grants an AUTOMATIC clue into the secret pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from world.tasking.constants import (
    LISTENER_BUZZ_BASE,
    LISTENER_BUZZ_PER_SCENE,
    LISTENER_BUZZ_PER_SECRET,
    LISTENER_BUZZ_THRESHOLD,
)
from world.tasking.exceptions import TaskingError
from world.tasking.models import ListenerHarvest, ListenerPost

if TYPE_CHECKING:
    from evennia_extensions.models import RoomProfile
    from world.assets.models import NPCAsset
    from world.checks.models import CheckType
    from world.clues.models import Clue
    from world.scenes.models import Persona


class ListenerPostError(TaskingError):
    user_message = "That listener post cannot be created."


class HarvestCollectionError(TaskingError):
    user_message = "There is nothing to collect here."


class NotPresentError(HarvestCollectionError):
    user_message = "You must go to your agent to collect what they hold."


def _handler_may_use_asset(handler: Persona, npc_asset: NPCAsset) -> bool:
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    if npc_asset.promoter_persona_id == handler.pk:
        return True
    if npc_asset.promoter_org_id is None:
        return False
    return OrganizationMembership.objects.filter(
        organization_id=npc_asset.promoter_org_id,
        persona=handler,
        left_at__isnull=True,
        exiled_at__isnull=True,
    ).exists()


@transaction.atomic
def create_listener_post(
    npc_asset: NPCAsset,
    room: RoomProfile,
    handler: Persona,
    *,
    check_type: CheckType | None = None,
    check_difficulty: int = 0,
) -> ListenerPost:
    """Post an agent as the room's listener (one active listener per room)."""
    from django.core.exceptions import ValidationError  # noqa: PLC0415
    from django.db import IntegrityError  # noqa: PLC0415

    from world.assets.constants import AssetStatus  # noqa: PLC0415
    from world.npc_services.models import (  # noqa: PLC0415
        AssignmentRole,
        NPCAssignment,
        NPCSourceType,
    )

    if npc_asset.status != AssetStatus.ACTIVE:
        raise ListenerPostError
    if not _handler_may_use_asset(handler, npc_asset):
        raise ListenerPostError
    try:
        assignment = NPCAssignment(
            source_type=NPCSourceType.NPC_ASSET,
            npc_asset=npc_asset,
            room=room,
            assignment_role=AssignmentRole.LISTENER,
            assigned_by=handler,
        )
        assignment.full_clean()
        assignment.save()
    except (IntegrityError, ValidationError) as exc:
        # The (room, role) partial-unique means the seat is taken — prime
        # posts are contested; flipping the sitting listener is the play.
        raise ListenerPostError from exc
    return ListenerPost.objects.create(
        assignment=assignment,
        handler=handler,
        check_type=check_type,
        check_difficulty=check_difficulty,
        threshold=LISTENER_BUZZ_THRESHOLD,
    )


def _room_residue(post: ListenerPost, since) -> tuple[int, list]:
    """Mechanical residue in the posted room since the last sweep.

    Returns (scene_count, new_scene_anchored_secrets). RoomProfile shares
    ObjectDB's pk, so Scene.location_id matches the assignment's room id
    directly. Prose is not an input anywhere here.
    """
    from world.scenes.models import Scene  # noqa: PLC0415
    from world.secrets.models import Secret  # noqa: PLC0415

    room_id = post.assignment.room_id
    scenes = Scene.objects.filter(location_id=room_id)
    secrets = Secret.objects.filter(scene__location_id=room_id)
    if since is not None:
        scenes = scenes.filter(date_started__gt=since)
        secrets = secrets.filter(created_date__gt=since)
    return scenes.count(), list(secrets)


def _uncaught_room_secret(post: ListenerPost):
    """The oldest room-minted secret this post hasn't already harvested."""
    from world.secrets.models import Secret  # noqa: PLC0415

    harvested_ids = post.harvests.filter(secret__isnull=False).values_list("secret_id", flat=True)
    return (
        Secret.objects.filter(scene__location_id=post.assignment.room_id)
        .exclude(pk__in=harvested_ids)
        .order_by("created_date")
        .first()
    )


def _sweep_post(post: ListenerPost, now) -> None:
    from world.assets.constants import AssetStatus  # noqa: PLC0415
    from world.checks.services import perform_check  # noqa: PLC0415

    asset = post.assignment.npc_asset
    if asset is None or asset.status != AssetStatus.ACTIVE:
        return

    # Suppressed (#2820 phase 4): the meter silently freezes. The handler
    # can't tell suppression from a run of failed tradecraft rolls.
    if post.suppressed_until is not None and post.suppressed_until > now:
        post.last_sweep_at = now
        post.save(update_fields=["last_sweep_at"])
        return

    scene_count, new_secrets = _room_residue(post, post.last_sweep_at)
    accrual = (
        LISTENER_BUZZ_BASE
        + LISTENER_BUZZ_PER_SCENE * scene_count
        + LISTENER_BUZZ_PER_SECRET * len(new_secrets)
    )
    if post.check_type_id is not None:
        agent_character = asset.asset_persona.character_sheet.character
        result = perform_check(agent_character, post.check_type, post.check_difficulty)
        if result.success_level <= 0:
            accrual = 0

    post.buzz += accrual
    if post.buzz >= post.threshold:
        post.buzz -= post.threshold
        if post.flipped_controller_id is not None:
            # Flipped (#2820 phase 4): the meter looks alive, but the true
            # handler decides what gets delivered — a queued red herring, or
            # nothing at all. Real catches stop.
            ListenerHarvest.objects.create(post=post, planted_clue=post.pending_plant)
            if post.pending_plant_id is not None:
                post.pending_plant = None
                post.save(update_fields=["pending_plant"])
        else:
            ListenerHarvest.objects.create(post=post, secret=_uncaught_room_secret(post))
    post.last_sweep_at = now
    post.save(update_fields=["buzz", "last_sweep_at"])


def listener_sweep() -> int:
    """Weekly cron: roll every active listener's accrual. Returns posts swept."""
    now = timezone.now()
    posts = ListenerPost.objects.filter(assignment__is_active=True).select_related(
        "assignment", "assignment__npc_asset"
    )
    count = 0
    for post in posts:
        _sweep_post(post, now)
        count += 1
    return count


@transaction.atomic
def collect_harvest(post: ListenerPost, collector: Persona) -> Clue | None:
    """Collect the oldest pending harvest — physically, in the posted room.

    A real catch mints (or reuses) an AUTOMATIC clue targeting the caught
    secret and grants it on the spot (clue -> secret knowledge). A quiet-week
    harvest collects to nothing — flavor, not currency. The visit itself is
    the exposure surface: anyone in the room sees the handler come to talk
    to their agent.
    """
    from world.clues.constants import ClueResolution, ClueTargetKind  # noqa: PLC0415
    from world.clues.models import Clue  # noqa: PLC0415
    from world.clues.services import acquire_clue, grant_clue_target  # noqa: PLC0415
    from world.roster.models import RosterEntry  # noqa: PLC0415

    if collector.pk != post.handler_id:
        raise HarvestCollectionError
    harvest = post.harvests.filter(collected_at__isnull=True).first()
    if harvest is None:
        raise HarvestCollectionError
    collector_character = collector.character_sheet.character
    if collector_character.db_location_id != post.assignment.room_id:
        raise NotPresentError

    harvest.collected_at = timezone.now()
    harvest.save(update_fields=["collected_at"])

    # A flipped post's planted red herring collects exactly like a real
    # catch — the handler cannot tell the difference (#2820 phase 4).
    if harvest.planted_clue_id is not None:
        clue = harvest.planted_clue
    elif harvest.secret_id is not None:
        clue, _ = Clue.objects.get_or_create(
            target_kind=ClueTargetKind.SECRET,
            target_secret=harvest.secret,
            defaults={
                "name": "An Agent's Whisper",
                "description": (
                    "PLACEHOLDER Your listener leans close: something happened here, "
                    "and they caught the shape of it."
                ),
                "resolution_mode": ClueResolution.AUTOMATIC,
            },
        )
    else:
        return None

    roster_entry = RosterEntry.objects.filter(character_sheet=collector.character_sheet).first()
    if roster_entry is not None:
        acquire_clue(roster_entry, clue)
        grant_clue_target(clue, roster_entry)
    return clue
