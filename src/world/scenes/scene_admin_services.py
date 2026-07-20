"""Scene administration permission helpers.

Five public surfaces:
  - ``actor_can_administer_scene`` — permission gate for admin actions.
  - ``resolve_actor_account`` — controlling account for a character actor.
  - ``add_present_as_co_owners`` — co-ownership grant for all present PCs.
  - ``enroll_present_table_gms`` — auto is_gm grant for a present table-owning GM (#2113).
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


def enroll_present_table_gms(scene: Scene, room: ObjectDB) -> None:
    """Auto-flag ``is_gm=True`` for a present GM running their own table (#2113).

    Walks ``room.contents`` once (mirrors ``add_present_as_co_owners``'s object/account
    resolution) to build the present-accounts and present-personas sets, keyed by which
    account controls which persona. For each present account holding a ``GMProfile``,
    checks whether any of their ACTIVE ``GMTable`` rows has an active
    ``GMTableMembership`` (``left_at__isnull=True``) whose persona belongs to a
    *different* present character — bare table ownership is not enough: a GM merely
    passing through a stranger's room must not auto-become that scene's adjudicator.

    Called right after ``add_present_as_co_owners`` in ``StartSceneAction.execute`` and
    again from the mid-scene join branch, so a table-owning GM arriving after scene
    start still gets flagged. Idempotent (``update_or_create``); never flips ``is_gm``
    back to False — only ever grants.

    No query-in-loop concern: one combined ``GMTableMembership`` query per present-GM
    account, bounded by room occupancy (matches ``add_present_as_co_owners``'s cost
    profile).
    """
    from world.gm.constants import GMTableStatus  # noqa: PLC0415
    from world.gm.models import GMProfile, GMTableMembership  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    accounts_present: dict[int, AccountDB] = {}
    persona_account_ids: dict[int, int] = {}
    for obj in room.contents:
        try:
            sheet = obj.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            continue
        account = obj.active_account
        if account is None:
            continue
        accounts_present[account.id] = account
        persona = active_persona_for_sheet(sheet)
        persona_account_ids[persona.id] = account.id

    for account_id, account in accounts_present.items():
        try:
            profile = account.gm_profile
        except GMProfile.DoesNotExist:
            continue

        other_present_persona_ids = [
            persona_id
            for persona_id, owning_account_id in persona_account_ids.items()
            if owning_account_id != account_id
        ]
        if not other_present_persona_ids:
            continue

        member_present = GMTableMembership.objects.filter(
            table__gm=profile,
            table__status=GMTableStatus.ACTIVE,
            left_at__isnull=True,
            persona_id__in=other_present_persona_ids,
        ).exists()
        if not member_present:
            continue

        SceneParticipation.objects.update_or_create(
            scene=scene,
            account=account,
            defaults={"is_gm": True},
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

    # #2019/#2209: scene end tears down conjured obstacles and living-barrier
    # ramparts in the scene's room — both are cast-for-the-scene constructs with
    # no other teardown trigger (teardown_conjured_obstacles previously had no
    # production call site; this closes that gap alongside wiring ramparts).
    if scene.location is not None:
        from world.areas.positioning.services import (  # noqa: PLC0415
            teardown_conjured_obstacles,
            teardown_ramparts,
        )

        teardown_conjured_obstacles(scene.location)
        teardown_ramparts(scene.location)

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
            sheet = obj.character_sheet
            if sheet is None:
                continue
            roles = sheet.character.covenant_roles
            if not any(m.engaged for m in roles.active_memberships):
                continue
            revalidate_engagements(character_sheet=sheet, room=scene.location)

    # #2356: close any active speaker queue for this scene's room.
    if scene.location is not None:
        from world.scenes.speaker_queue_services import clear_queue_on_scene_finish  # noqa: PLC0415

        clear_queue_on_scene_finish(scene)

    # #2514: clear scene-scoped conditions (social moods, etc.) for all
    # participants. Mirrors the UNTIL_END_OF_COMBAT sweep in combat cleanup
    # (expire_end_of_combat_conditions). Participant resolution mirrors the
    # clear_very_attracted pattern in Scene.finish_scene.
    from world.conditions.services import expire_scene_scoped_conditions  # noqa: PLC0415

    participant_targets = [
        persona.character_sheet.character
        for persona in scene.persona_handler.active_participant_personas()
        if persona.character_sheet is not None and persona.character_sheet.character is not None
    ]
    expire_scene_scoped_conditions(participant_targets)

    broadcast_scene_message(scene, SceneAction.END)
