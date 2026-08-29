"""GM story-NPC on-ramp (#3426) — mint a playable Story NPC bound to a GM's own account.

A JUNIOR+ GM stands up a Story NPC before a session and immediately gets a
playable character: the persona picker and telnet ``@ic`` key off
``RosterTenure``, and ``mint_story_npc`` (``world.roster.services.staff_characters``)
grants one to the requesting GM's account in the same mint that used to be
staff-only (``mint_staff_character``). ``category="gm"``, gated by
``MinimumGMLevelPrerequisite(GMLevel.JUNIOR)`` (staff bypass built in); the
per-level cap (``GMLevelCap.max_story_npcs``) and the finer "missing GM
profile"/"below JUNIOR" messaging are enforced inside the service itself, not
re-derived here.

An optional ``preset`` kwarg (#3427) names a curated ``NPCStatlinePreset`` by
natural key -- resolved here (not in the service, which takes the instance)
so both telnet and web pass a plain string; an unknown name is refused with
a player-safe message rather than silently minting with no statline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.constants import ActionCategory
from actions.prerequisites import MinimumGMLevelPrerequisite, Prerequisite
from actions.types import ActionResult, TargetType
from world.gm.constants import GMLevel

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext


@dataclass
class MintStoryNPCAction(Action):
    """Mint a Story NPC and bind it to the caller's account.

    Kwargs: ``name``, ``description``, optional ``preset`` (an
    ``NPCStatlinePreset`` natural-key name, #3427).
    """

    key: str = "mint_story_npc"
    name: str = "Mint Story NPC"
    icon: str = "user-plus"
    category: str = "gm"
    action_category: ActionCategory = ActionCategory.PHYSICAL
    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [MinimumGMLevelPrerequisite(GMLevel.JUNIOR)]

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.roster.models import NPCStatlinePreset  # noqa: PLC0415
        from world.roster.services.staff_characters import (  # noqa: PLC0415
            StaffMintError,
            mint_story_npc,
        )

        try:
            gm_account = actor.active_account
        except AttributeError:
            gm_account = None
        if gm_account is None:
            return ActionResult(success=False, message="GM trust required.")

        npc_name = (kwargs.get("name") or "").strip()
        if not npc_name:
            return ActionResult(success=False, message="Name the NPC.")

        preset = None
        preset_name = (kwargs.get("preset") or "").strip()
        if preset_name:
            try:
                preset = NPCStatlinePreset.objects.get_by_natural_key(preset_name)
            except NPCStatlinePreset.DoesNotExist:
                return ActionResult(
                    success=False,
                    message=f"No statline preset named '{preset_name}'.",
                )

        try:
            character = mint_story_npc(
                gm_account=gm_account,
                name=npc_name,
                description=kwargs.get("description") or "",
                preset=preset,
            )
        except StaffMintError as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=f"{character.key} minted as a Story NPC (#{character.pk}).",
        )
