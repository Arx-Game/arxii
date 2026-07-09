"""Scene administration permission helpers.

Four public surfaces:
  - ``actor_can_administer_scene`` — permission gate for admin actions.
  - ``resolve_actor_account`` — controlling account for a character actor.
  - ``add_present_as_co_owners`` — co-ownership grant for all present PCs.
  - ``finish_scene_full`` — full scene-finish orchestration (finish, rewards, fatigue, broadcast).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

from world.fatigue.tasks import process_deferred_fatigue_resets
from world.progression.services.scene_rewards import on_scene_finished
from world.scenes.constants import SceneAction
from world.scenes.models import Scene, SceneParticipation
from world.scenes.services import broadcast_scene_message

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB


def resolve_actor_account(actor: ObjectDB) -> AccountDB | None:
    """Return the controlling account for ``actor`` (PC tenure path).

    Returns None for GM/Staff/NPC characters that have no roster tenure
    linking them to a player account.
    """
    return actor.active_account


def actor_can_administer_scene(actor: ObjectDB, scene: Scene) -> bool:
    """Return True if ``actor`` may administer ``scene``.

    Authorization tiers (first match wins):
    1. ``actor.is_story_runner`` — GM/Staff characters gate as True with no
       account lookup.
    2. The actor's controlling account is a staff user.
    3. The actor's controlling account is a scene co-owner (``is_owner=True``
       on their ``SceneParticipation`` row).
    """
    if actor.is_story_runner:
        return True
    account = resolve_actor_account(actor)
    if account is None:
        return False
    if account.is_staff:
        return True
    return scene.is_owner(account)


def add_present_as_co_owners(scene: Scene, room: ObjectDB) -> None:
    """Mark every present character with a controlling account as a scene co-owner.

    Walks ``room.contents`` for objects with a ``sheet_data`` attribute (i.e.
    characters with a CharacterSheet), resolves their controlling account via
    ``character.active_account``, and ``update_or_create``s a
    ``SceneParticipation`` row with ``is_owner=True``.  Objects without a
    sheet (NPCs, props, etc.) and characters without a controlling account
    (GM/Staff characters, bare NPCs) are silently skipped.
    """
    for obj in room.contents:
        try:
            obj.sheet_data  # noqa: B018 — attribute access guards NPC/prop skip
        except (AttributeError, ObjectDoesNotExist):
            continue
        account = obj.active_account
        if account is None:
            continue
        SceneParticipation.objects.update_or_create(
            scene=scene,
            account=account,
            defaults={"is_owner": True},
        )


def finish_scene_full(scene: Scene, by_account: AccountDB | None = None) -> None:  # noqa: ARG001
    """Run the full scene-finish orchestration.

    Idempotent: returns immediately if the scene is already finished
    (``scene.is_finished`` is True), so calling twice is safe.

    Steps (in order):
    1. ``scene.finish_scene()`` — sets ``date_finished`` + ``is_active=False``.
    2. ``on_scene_finished(scene)`` — awards scene-completion progression rewards.
    3. ``process_deferred_fatigue_resets`` — drains any pending fatigue-reset
       tasks for all participant accounts.
    4. ``broadcast_scene_message(scene, SceneAction.END)`` — pushes the END
       event over the scene's WebSocket channel.

    ``by_account`` is accepted for call-site symmetry (so both the web viewset
    and the upcoming ``FinishSceneAction`` can pass their actor without branching)
    but the existing orchestration did not use the requesting account, so it is
    not forwarded to any of the above.
    """
    if scene.is_finished:
        return

    scene.finish_scene()
    on_scene_finished(scene)
    participant_account_ids = set(scene.participations.values_list("account_id", flat=True))
    process_deferred_fatigue_resets(participant_account_ids)

    # #2051: when a scene ends, Durance vows tied to co-presence in that
    # scene's room may dim — can_engage_membership checks for an active scene,
    # which is now gone. Revalidate remaining occupants' engaged covenant roles.
    # COURT vows re-validate by their own arm (master's business), so only
    # Durance vows are affected. Hot-path short-circuit: skip occupants with no
    # engaged covenant role (cached handler — no DB query for the common case).
    if scene.location is not None:
        from world.covenants.services import revalidate_engagements  # noqa: PLC0415
        from world.scenes.interaction_services import (  # noqa: PLC0415
            invalidate_active_scene_cache,
        )

        # finish_scene() set is_active=False but the room's in-memory
        # _active_scene_cache still holds this scene — bust it so
        # can_engage_membership sees no active scene.
        invalidate_active_scene_cache(scene.location)

        for obj in scene.location.contents:
            sheet = getattr(obj, "sheet_data", None)  # noqa: GETATTR_LITERAL
            if sheet is None:
                continue
            roles = sheet.character.covenant_roles
            if not any(m.engaged for m in roles.active_memberships):
                continue
            revalidate_engagements(character_sheet=sheet, room=scene.location)

    broadcast_scene_message(scene, SceneAction.END)
