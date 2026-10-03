"""Charm-sourced NPCAsset acquisition action (#2502).

``CharmAssetAction`` (key ``charm_asset``) mirrors ``CoerceAssetAction``: a
charmed NPC is extracted as a CHARM ``NPCAsset`` of the charmer's chosen
role_context. Auto-succeeds against an un-played NPC; a PC or actively-piloted
NPC is never auto-acquired. The charm condition is NOT consumed — it is the
leverage gate, and the asset persists beyond the condition's duration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.constants import ActionCategory
from actions.prerequisites import Prerequisite
from actions.types import TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext, ActionResult

# Same role contexts as coercion — charm-acquired assets serve the same roles.
_CHARMABLE_ROLE_CONTEXTS = frozenset({"informant", "contact", "personal_favor"})

#: A player character can't be "taken into service" like an NPC (#4091 task 12).
#: Canonical PC/NPC test per ``is_player_character``
#: (``world/roster/services/activity.py``) -- an active ``RosterTenure`` OR a
#: live puppet; ``db_account`` alone reads None for an OFFLINE PC, since
#: Evennia's ``unpuppet_object`` clears it. Never matched on a name.
_NOT_AN_NPC_RETAIN_MESSAGE = "They have a will of their own; you cannot take them into service."


@dataclass
class CharmedByActorPrerequisite(Prerequisite):
    """The target carries a charm (ALLY_OF_CASTER) the actor applied and is
    present (#4091; presence check added task 12 fix round 1 ruling 1 — it was
    missing here, which is why ``retain`` could reach a target the digest's
    ``can_send_away`` flag would already call gone).

    Mirrors the gate ``charm_into_asset`` itself enforces — this exists so the
    persona menu can show a reason; the service call stays the authority.
    """

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        from world.conditions.constants import Allegiance  # noqa: PLC0415
        from world.npc_services.allegiance import actor_holds_sway_present  # noqa: PLC0415
        from world.roster.services.activity import is_player_character  # noqa: PLC0415
        from world.scenes.models import Persona  # noqa: PLC0415

        kwargs = (context or {}).get("kwargs", {})
        persona = (
            Persona.objects.filter(pk=kwargs.get("target_persona_id"))
            .select_related("character_sheet__character")
            .first()
        )
        body = persona.character_sheet.character if persona else None
        if (
            body is None
            or body.db_location_id is None
            or body.db_location_id != actor.db_location_id
        ):
            return False, "They are not here."
        if is_player_character(persona.character_sheet):
            return False, _NOT_AN_NPC_RETAIN_MESSAGE
        kinds = frozenset({Allegiance.ALLY_OF_CASTER})
        if not actor_holds_sway_present(actor, body, kinds=kinds):
            return False, "They are not charmed by you."
        return True, ""


@dataclass
class CharmAssetAction(Action):
    """Extract a charmed NPC as a charm-acquired asset (#2502)."""

    key: str = "charm_asset"
    name: str = "Charm into Asset"
    icon: str = "heart"
    category: str = "social"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SINGLE

    def get_prerequisites(self) -> list[Prerequisite]:
        return [CharmedByActorPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from actions.types import ActionResult as _ActionResult  # noqa: PLC0415
        from world.assets.services import CharmError, charm_into_asset  # noqa: PLC0415
        from world.scenes.models import Persona  # noqa: PLC0415
        from world.scenes.services import persona_for_character  # noqa: PLC0415

        role_context = kwargs.get("role_context")
        if role_context not in _CHARMABLE_ROLE_CONTEXTS:
            return _ActionResult(
                success=False,
                message="Acquire them as what? (informant / contact / personal-favor)",
            )
        target_persona = (
            Persona.objects.filter(pk=kwargs.get("target_persona_id"))
            .select_related("character_sheet__character")
            .first()
        )
        if target_persona is None:
            return _ActionResult(success=False, message="No such target.")

        target_character = target_persona.character_sheet.character
        if target_character is None:
            return _ActionResult(
                success=False,
                message="There's no one there to charm into service.",
            )
        # A played character (has an account) or an actively-piloted NPC is never
        # auto-acquired — they retain full agency (ADR-0024).
        if target_character.db_account is not None or target_character.sessions.count() > 0:
            return _ActionResult(
                success=False,
                message="They're being played; you can't charm them into service.",
            )

        try:
            asset = charm_into_asset(
                charmer_persona=persona_for_character(actor),
                target_persona=target_persona,
                role_context=role_context,
            )
        except CharmError as exc:
            return _ActionResult(success=False, message=exc.user_message)
        kind = asset.get_role_context_display().lower()
        return _ActionResult(
            success=True,
            message=f"You now hold {target_persona} as a charmed {kind}.",
        )


charm_asset = CharmAssetAction()
