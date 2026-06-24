"""CastTechniqueAction — SCENE_ADAPTIVE action for standalone technique casts.

Both telnet (``commands.magic.CmdAttempt``) and the web dispatch path converge
here for standalone technique casts. The action:

1. Resolves the active scene, initiator persona, technique, and optional target.
2. Calls ``request_technique_cast``.
3. When ``get_soulfray_warning`` is non-None and ``confirm_soulfray_risk=False``,
   registers a ``PendingCast`` and returns a ``success=False`` result so the
   dispatcher does NOT record anti-spam or advance the pose-order quorum. The actor
   is prompted to ``accept soulfray`` or ``decline soulfray``.
4. On a resolved cast returns ``success=True``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext


@dataclass
class CastTechniqueAction(Action):
    """Standalone technique cast — resolves immediately or gates on soulfray consent.

    kwargs:
        technique_id: PK of the ``Technique`` to cast (required).
        target_persona_id: PK of the target ``Persona``, or ``None`` for self / room.
        confirm_soulfray_risk: When ``True`` the cast proceeds even if the caster has
            an active Soulfray stage. Defaults ``False`` so the first cast of a
            soulfray-afflicted character halts and prompts for consent.
        **kwargs: Forwarded into ``PendingCast.kwargs`` for re-dispatch on accept.
    """

    key: str = "cast_technique"
    name: str = "Cast Technique"
    icon: str = "sparkles"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        *,
        technique_id: int,
        target_persona_id: int | None = None,
        confirm_soulfray_risk: bool = False,
        **kwargs: Any,
    ) -> ActionResult:
        """Resolve or gate the cast.

        Returns:
            ``success=False`` when the soulfray gate fires (pending consent).
            ``success=True`` when the cast resolves (or is on a PENDING benign/hostile path).
        """
        from world.magic.models import Technique  # noqa: PLC0415
        from world.scenes.cast_services import request_technique_cast  # noqa: PLC0415
        from world.scenes.models import Persona, Scene  # noqa: PLC0415
        from world.scenes.services import persona_for_character  # noqa: PLC0415

        scene = Scene.objects.filter(location=actor.location, is_active=True).first()
        if scene is None:
            return ActionResult(success=False, message="There is no active scene here.")

        initiator = persona_for_character(actor)

        try:
            technique = Technique.objects.get(pk=technique_id)
        except Technique.DoesNotExist:
            return ActionResult(success=False, message="Technique not found.")

        target: Persona | None = None
        if target_persona_id is not None:
            try:
                target = Persona.objects.get(pk=target_persona_id)
            except Persona.DoesNotExist:
                return ActionResult(success=False, message="Target persona not found.")

        cast = request_technique_cast(
            scene=scene,
            initiator_persona=initiator,
            target_persona=target,
            technique=technique,
            confirm_soulfray_risk=confirm_soulfray_risk,
        )

        if cast.soulfray_warning is not None and not confirm_soulfray_risk:
            from commands.pending_actions import PendingCast, register_pending  # noqa: PLC0415

            register_pending(
                actor.sheet_data.pk,  # type: ignore[union-attr]
                PendingCast(
                    technique_id=technique_id,
                    target_persona_id=target_persona_id,
                    kwargs=kwargs,
                ),
            )
            warning = cast.soulfray_warning
            return ActionResult(
                success=False,
                message=(
                    f"{warning.stage_description} "
                    "Use |waccept soulfray|n to proceed or |wdecline soulfray|n to abort."
                ),
            )

        return ActionResult(success=True, message="Your technique resolves.")

    def round_declaration(
        self,
        ctx: Any,
        *,
        technique_id: int | None = None,
        **kwargs: Any,
    ) -> tuple[Any, dict[str, Any]] | None:
        """Declare into a COMBAT round when inside a CombatRoundContext, else None."""
        from actions.constants import ActionBackend, CombatActionSlot  # noqa: PLC0415
        from actions.types import ActionRef, PlayerAction  # noqa: PLC0415
        from world.combat.round_context import CombatRoundContext  # noqa: PLC0415

        if not isinstance(ctx, CombatRoundContext) or technique_id is None:
            return None

        ref = ActionRef(
            backend=ActionBackend.COMBAT,
            technique_id=technique_id,
            action_slot=kwargs.get("action_slot", CombatActionSlot.FOCUSED),
        )
        pa = PlayerAction(
            backend=ActionBackend.COMBAT,
            display_name="Cast",
            ref=ref,
        )
        decl_kwargs: dict[str, Any] = {
            "effort_level": kwargs.get("effort_level", "medium"),
        }
        focused_opponent_id = kwargs.get("focused_opponent_target_id")
        if focused_opponent_id is not None:
            decl_kwargs["focused_opponent_target_id"] = focused_opponent_id
        return pa, decl_kwargs
