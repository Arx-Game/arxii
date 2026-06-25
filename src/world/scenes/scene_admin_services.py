"""Scene administration permission helpers.

Three public surfaces:
  - ``actor_can_administer_scene`` — permission gate for admin actions.
  - ``resolve_actor_account`` — controlling account for a character actor.
  - ``add_present_as_co_owners`` — co-ownership grant for all present PCs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

from world.scenes.models import Scene, SceneParticipation

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
