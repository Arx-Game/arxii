"""CastTechniqueAction — SCENE_ADAPTIVE action for standalone technique casts.

Reached by the **telnet** ``cast``/``declare`` command (``commands.combat.CmdDeclareTechnique``)
via ``dispatch_player_action(SCENE_ADAPTIVE)``. The **web** standalone-cast endpoint
(``world.scenes.action_views.SceneActionRequestViewSet.cast``) does NOT route through this
action — it calls ``request_technique_cast`` directly. So telnet and web converge at the
``request_technique_cast`` **service**, not at ``action.run()``; this action's anti-spam,
pose-order, and soulfray-pending machinery is telnet-only today. The action:

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
    from world.magic.types.pull import CastPullDeclaration


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

    def execute(  # noqa: PLR0913
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        *,
        technique_id: int,
        target_persona_id: int | None = None,
        confirm_soulfray_risk: bool = False,
        cast_pull: CastPullDeclaration | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        """Resolve or gate the cast.

        Args:
            cast_pull: An optional ``CastPullDeclaration`` resolved by the
                telnet command (or passed directly).  When provided it is
                forwarded into ``request_technique_cast`` so the pull is
                charged and applied as part of the cast.  Rejected on hostile
                techniques (``request_technique_cast`` raises; we surface a
                clean failure).

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

        try:
            cast = request_technique_cast(
                scene=scene,
                initiator_persona=initiator,
                target_persona=target,
                technique=technique,
                confirm_soulfray_risk=confirm_soulfray_risk,
                cast_pull=cast_pull,
            )
        except Exception as exc:
            # Surface magic-layer exceptions (e.g. MagicError subclasses for
            # invalid/inert pull declarations) as clean failure results rather
            # than propagating as crashes.  Re-raise anything that is not a
            # MagicError so programming errors are still visible.
            from world.magic.exceptions import MagicError  # noqa: PLC0415

            if not isinstance(exc, MagicError):
                raise
            return ActionResult(success=False, message=str(exc))

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
        """Declare into a COMBAT round when inside a CombatRoundContext, else None.

        When a ``cast_pull`` (a ``CastPullDeclaration``) is present and the context is
        a ``CombatRoundContext``, the pull is committed immediately at declaration time
        via ``spend_resonance_for_pull`` so the combat read-path
        (``_sum_active_flat_bonuses`` / ``_sum_intensity_bump_pulls``) can apply the
        bonus during round resolution.

        The one-pull-per-round cap is enforced by the ``(participant, round_number)``
        unique constraint on ``CombatPull``.  A duplicate attempt raises
        ``ActionDispatchError(PULL_ALREADY_COMMITTED)`` so the dispatcher surfaces a
        clean "already pulled" message rather than propagating an ``IntegrityError``.

        ``cast_pull`` is intentionally NOT forwarded into ``decl_kwargs`` — combat pulls
        come from the ``CombatPull`` read-path, not from the declaration kwargs, to avoid
        double-charging.
        """
        from actions.constants import ActionBackend, CombatActionSlot  # noqa: PLC0415
        from actions.types import ActionRef, PlayerAction  # noqa: PLC0415
        from world.combat.round_context import CombatRoundContext  # noqa: PLC0415

        if not isinstance(ctx, CombatRoundContext) or technique_id is None:
            return None

        # Commit an optional thread pull at declaration time.
        # resolve_pull_from_kwargs normalises both the telnet path (pre-built
        # CastPullDeclaration in kwargs["cast_pull"]) and the web path (raw IDs:
        # pull_resonance_id / pull_tier / pull_thread_ids) into one optional declaration.
        from world.combat.pull_helpers import resolve_pull_from_kwargs  # noqa: PLC0415

        sheet = ctx.participant.character_sheet
        cast_pull = resolve_pull_from_kwargs(sheet, kwargs)
        if cast_pull is not None:
            self._commit_combat_pull(cast_pull, ctx, technique_id)

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
        focused_ally_id = kwargs.get("focused_ally_target_id")
        if focused_ally_id is not None:
            decl_kwargs["focused_ally_target_id"] = focused_ally_id
        # cast_pull is deliberately excluded from decl_kwargs: the CombatPull read-path
        # supplies the bonus during resolution; forwarding it here would double-charge.
        return pa, decl_kwargs

    @staticmethod
    def _commit_combat_pull(
        cast_pull: CastPullDeclaration,
        ctx: Any,
        technique_id: int,
    ) -> None:
        """Commit a thread pull as a ``CombatPull`` row at declaration time.

        Delegates to ``world.combat.pull_helpers.commit_combat_pull`` so the
        commit logic is shared with the clash-contribution path and is not
        duplicated here.

        Raises:
            ActionDispatchError(PULL_ALREADY_COMMITTED): When the unique constraint fires
                (duplicate pull in the same round).
            ActionDispatchError(PULL_INVALID): When ``spend_resonance_for_pull`` raises a
                ``MagicError`` (invalid pull declaration — e.g. thread not in action,
                insufficient balance).
        """
        from world.combat.pull_helpers import commit_combat_pull  # noqa: PLC0415

        participant = ctx.participant
        encounter = participant.encounter
        commit_combat_pull(
            cast_pull=cast_pull,
            participant=participant,
            encounter=encounter,
            technique_id=technique_id,
        )
