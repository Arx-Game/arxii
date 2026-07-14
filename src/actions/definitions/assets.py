"""REGISTRY Actions for NPCAsset management (#2295)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext


@dataclass
class IntroduceAssetAction(Action):
    """Introduce an owned asset to a co-present ally, creating co-ownership (#2295).

    The introducer (actor) owns an ACTIVE NPCAsset. The ally persona must
    be co-present in the introducer's room. On success, creates a new
    NPCAsset row for the ally pointing at the same asset_persona.
    """

    key: str = "introduce_asset"
    name: str = "Introduce Asset"
    icon: str = "handshake"
    category: str = "social"
    target_type: TargetType = TargetType.SINGLE

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.assets.models import NPCAsset  # noqa: PLC0415
        from world.assets.services import IntroductionError, introduce_asset  # noqa: PLC0415
        from world.scenes.models import Persona  # noqa: PLC0415
        from world.scenes.services import (  # noqa: PLC0415
            MissingPrimaryPersonaError,
            persona_for_character,
        )

        asset_id = kwargs.get("asset_id")
        ally_persona_id = kwargs.get("ally_persona_id")

        if asset_id is None or ally_persona_id is None:
            return ActionResult(
                success=False,
                message="You must specify both an asset and an ally.",
            )

        asset = NPCAsset.objects.filter(pk=asset_id).first()
        if asset is None:
            return ActionResult(success=False, message="That asset was not found.")

        ally_persona = Persona.objects.filter(pk=ally_persona_id).first()
        if ally_persona is None:
            return ActionResult(success=False, message="That person was not found.")

        try:
            introducer_persona = persona_for_character(actor)
        except MissingPrimaryPersonaError:
            return ActionResult(success=False, message="No active character sheet.")

        try:
            new_asset = introduce_asset(
                introducer_persona=introducer_persona,
                ally_persona=ally_persona,
                asset=asset,
            )
        except IntroductionError as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=f"You introduce {asset.asset_persona.name} to {ally_persona.name}.",
            data={"new_asset_pk": new_asset.pk},
        )


# Module-level singleton registered in actions.registry._ALL_ACTIONS.
introduce_asset_action = IntroduceAssetAction()
