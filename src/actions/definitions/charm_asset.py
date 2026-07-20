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
from actions.types import TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext, ActionResult

# Same role contexts as coercion — charm-acquired assets serve the same roles.
_CHARMABLE_ROLE_CONTEXTS = frozenset({"informant", "contact", "personal_favor"})


@dataclass
class CharmAssetAction(Action):
    """Extract a charmed NPC as a charm-acquired asset (#2502)."""

    key: str = "charm_asset"
    name: str = "Charm into Asset"
    icon: str = "heart"
    category: str = "social"
    action_category: ActionCategory = ActionCategory.SOCIAL
    target_type: TargetType = TargetType.SINGLE

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
                message="They're being played — you can't charm them into service.",
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
