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
    from world.scenes.types import CastResult


# The keys a combat cast's declaration reads from its kwargs (#5231). The declaration and the
# Soulfray pending cast both build from these, so a confirmed cast keeps every choice.
_COMBAT_DECLARATION_KEYS: tuple[str, ...] = (
    "focused_opponent_target_id",
    "focused_ally_target_id",
    "confirm_soulfray_risk",
    "strain_commitment",
    "fury_commitment_id",
    "fury_resonance_id",
    "position_params",
    "preferred_resonance_id",
)
# The keys that declare the cast's thread pull: telnet's built ``cast_pull`` and the web's raw
# ids. They are read at the combat door, never stored on the round's action.
_COMBAT_PULL_KEYS: tuple[str, ...] = (
    "cast_pull",
    "pull_tier",
    "pull_thread_ids",
    "pull_burn",
    "pull_burn_resonance_id",
    "pull_payers",
)


def _combat_declaration_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """The declaration kwargs of a combat cast: the effort level and each key it set."""
    declared: dict[str, Any] = {"effort_level": kwargs.get("effort_level", "medium")}
    for key in _COMBAT_DECLARATION_KEYS:
        value = kwargs.get(key)
        # An unset key, a False flag, a zero strain and an empty positions dict add nothing.
        if value is not None and value is not False and value not in (0, {}):
            declared[key] = value
    return declared


def _resolved_message(cast: CastResult) -> str:
    """The actor's own line for a cast that resolved now.

    Adds what her resonance check made the cast's pull and kindled power worth (#5308), and
    that an embattled ally's fight drew her in. The scene's outcome pose is read by everyone
    and carries neither.
    """
    from world.magic.services.resonance_checks import worth_clause  # noqa: PLC0415

    message = "Your technique resolves."
    technique_result = cast.result.technique_result if cast.result is not None else None
    worth = worth_clause(technique_result.worth_by_affinity) if technique_result else ""
    if worth:
        message = f"{message} {worth}"
    if cast.combat_seated:
        message = f"{message}\nYour cast reaches an embattled ally — you are drawn into the fight."
    return message


@dataclass
class CastTechniqueAction(Action):
    """Standalone technique cast — resolves immediately or gates on soulfray consent.

    kwargs:
        technique_id: PK of the ``Technique`` to cast (required).
        target_persona_id: PK of the target ``Persona``, or ``None`` for self / room.
        confirm_soulfray_risk: When ``True`` the cast proceeds even if the caster has
            an active Soulfray stage. Defaults ``False`` so the first cast of a
            soulfray-afflicted character halts and prompts for consent.
        cast_openly: One-way waiver of the caster's style-imposed cast concealment
            for this cast (#2710) — never adds concealment to an overt style.
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
        use_base_form: bool = False,
        position_params: dict[str, int] | None = None,
        preferred_resonance_id: int | None = None,
        cast_openly: bool = False,
        strain_commitment: int = 0,
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

        # deliberately includes battle-backed scenes: a standalone cast made while
        # standing in a staged/active battle should log against the battle's own
        # scene, not silently miss it and fall through to some other room scene (#2010
        # review).
        scene = Scene.objects.filter(location_id=actor.db_location_id, is_active=True).first()
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

        # #1619: Resolve the preferred resonance for multi-resonance variant
        # selection. When the character holds multiple GIFT threads at different
        # resonances, this lets the player choose which variant to manifest.
        preferred_resonance = None
        if preferred_resonance_id is not None:
            from world.magic.models import Resonance  # noqa: PLC0415

            try:
                preferred_resonance = Resonance.objects.get(pk=preferred_resonance_id)
            except Resonance.DoesNotExist:
                return ActionResult(success=False, message="Resonance not found.")

        from world.magic.exceptions import MagicError  # noqa: PLC0415

        try:
            cast = request_technique_cast(
                scene=scene,
                initiator_persona=initiator,
                target_persona=target,
                technique=technique,
                confirm_soulfray_risk=confirm_soulfray_risk,
                cast_pull=cast_pull,
                use_base_form=use_base_form,
                position_params=position_params,
                preferred_resonance=preferred_resonance,
                cast_openly=cast_openly,
                strain_commitment=strain_commitment,
            )
        except MagicError as exc:
            # Surface magic-layer failures (e.g. invalid/inert pull
            # declarations) as clean failure results; anything else propagates
            # so programming errors stay visible. user_message, never str(exc)
            # (exception detail must not reach players).
            return ActionResult(success=False, message=exc.user_message)

        if cast.soulfray_warning is not None and not confirm_soulfray_risk:
            from commands.pending_actions import PendingCast, register_pending  # noqa: PLC0415

            register_pending(
                actor.sheet_data.pk,  # type: ignore[union-attr]
                PendingCast(
                    technique_id=technique_id,
                    target_persona_id=target_persona_id,
                    # Every choice the player made rides along: a confirmed cast is the
                    # cast she asked for, in the resonance and form she named.
                    kwargs={
                        "position_params": position_params,
                        "preferred_resonance_id": preferred_resonance_id,
                        "use_base_form": use_base_form,
                        "cast_openly": cast_openly,
                        "strain_commitment": strain_commitment,
                        # A pull declared with the cast was not charged (the cast stopped
                        # before it); the confirmed cast carries it, as the combat
                        # path's replay carries the pull's own kwargs.
                        **({"cast_pull": cast_pull} if cast_pull is not None else {}),
                        **kwargs,
                    },
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

        message = _resolved_message(cast)
        return ActionResult(success=True, message=message)

    def round_declaration(
        self,
        ctx: Any,
        *,
        technique_id: int | None = None,
        **kwargs: Any,
    ) -> tuple[Any, dict[str, Any]] | ActionResult | None:
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

        **Soulfray gate:** when the caster has an active Soulfray stage and
        ``confirm_soulfray_risk`` is falsy, a ``PendingCast`` carrying all the combat
        declaration kwargs is registered and an ``ActionResult(success=False)`` is
        returned so the dispatcher short-circuits without recording a declaration or
        charging the pull.  Accepting the offer re-dispatches with
        ``confirm_soulfray_risk=True``, which skips this gate and proceeds normally.
        """
        from actions.constants import ActionBackend, CombatActionSlot  # noqa: PLC0415
        from actions.types import ActionRef, PlayerAction  # noqa: PLC0415
        from world.combat.round_context import CombatRoundContext  # noqa: PLC0415

        if not isinstance(ctx, CombatRoundContext) or technique_id is None:
            return None

        # A named resonance the Gift's thread lacks is refused first: nothing is recorded,
        # charged or offered for a cast that cannot be declared (#5231). Then the Soulfray
        # gate, BEFORE committing the cast pull so no resonance/anima is charged for a
        # declaration the player then declines.
        gate = self._combat_resonance_refusal(
            ctx, technique_id, kwargs
        ) or self._combat_soulfray_gate(ctx, technique_id, kwargs)
        if gate is not None:
            return gate
        fury_refusal = self._combat_fury_cap_refusal(ctx, kwargs)
        if fury_refusal is not None:
            return fury_refusal

        # Commit an optional thread pull at declaration time.
        # resolve_pull_from_kwargs normalises both the telnet path (pre-built
        # CastPullDeclaration in kwargs["cast_pull"]) and the web path (raw IDs:
        # pull_tier / pull_thread_ids, of any resonances) into one optional declaration.
        from world.combat.pull_helpers import resolve_pull_from_kwargs  # noqa: PLC0415

        sheet = ctx.participant.character_sheet
        cast_pull = resolve_pull_from_kwargs(sheet, kwargs)
        if cast_pull is not None:
            self._commit_combat_pull(cast_pull, ctx, technique_id, kwargs)

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
        decl_kwargs = _combat_declaration_kwargs(kwargs)
        # cast_pull is deliberately excluded from decl_kwargs: the CombatPull read-path
        # supplies the bonus during resolution; forwarding it here would double-charge.
        return pa, decl_kwargs

    @staticmethod
    def _combat_resonance_refusal(
        ctx: Any, technique_id: int, kwargs: dict[str, Any]
    ) -> ActionResult | None:
        """Refuse a named cast resonance the Gift's thread holds no row for (#5231).

        The focused cast only: a passive names no resonance. Runs before the cast pull is
        committed and before the Soulfray gate, so a refused choice is never charged.
        """
        from actions.constants import CombatActionSlot  # noqa: PLC0415

        preferred_resonance_id = kwargs.get("preferred_resonance_id")
        if preferred_resonance_id is None:
            return None
        if kwargs.get("action_slot", CombatActionSlot.FOCUSED) != CombatActionSlot.FOCUSED:
            return None
        from world.combat.services.declarations.declaration_validation import (  # noqa: PLC0415
            DeclarationRefusedError,
        )
        from world.combat.services.declarations.declare_action import (  # noqa: PLC0415
            refuse_resonance_off_thread,
        )
        from world.magic.models import Resonance, Technique  # noqa: PLC0415

        try:
            resonance = Resonance.objects.get(pk=int(preferred_resonance_id))
        except (TypeError, ValueError, Resonance.DoesNotExist):
            return ActionResult(success=False, message="Resonance not found.")
        # The declaration's own refusal, run here so it comes before the pull is charged.
        try:
            refuse_resonance_off_thread(
                ctx.participant, Technique.objects.filter(pk=technique_id).first(), resonance
            )
        except DeclarationRefusedError as exc:
            # A fixed player-facing line (ResonanceNotOnGiftThread.user_message), never detail.
            return ActionResult(success=False, message=str(exc))
        return None

    @staticmethod
    def _combat_fury_cap_refusal(ctx: Any, kwargs: dict[str, Any]) -> ActionResult | None:
        """Refuse giving in to an unkindled resonance or deeper than its strength allows (#5124).

        Mirrors the scene serializer's ``_cap_fury_by_provocation`` with the same message,
        so the player learns it at declaration instead of finding a shallower tier (and
        no Berserk) at resolution. Nothing is recorded or charged.
        """
        fury_commitment_id = kwargs.get("fury_commitment_id")
        if fury_commitment_id is None:
            return None
        from world.magic.models import FuryTier, Resonance  # noqa: PLC0415
        from world.magic.services.fury import give_in_refusal  # noqa: PLC0415

        tier = FuryTier.objects.filter(pk=fury_commitment_id).first()
        if tier is None:
            return ActionResult(success=False, message="Unknown Fury tier.")
        fury_resonance_id = kwargs.get("fury_resonance_id")
        resonance = (
            Resonance.objects.filter(pk=fury_resonance_id).first()
            if fury_resonance_id is not None
            else None
        )
        refusal = give_in_refusal(ctx.participant.character_sheet, resonance, tier)
        if refusal is not None:
            return ActionResult(success=False, message=refusal)
        return None

    @staticmethod
    def _combat_soulfray_gate(
        ctx: Any,
        technique_id: int,
        kwargs: dict[str, Any],
    ) -> ActionResult | None:
        """Return an ActionResult (prompt) and register a PendingCast when the soulfray gate fires.

        Returns ``None`` when the gate does not fire (no warning, or already confirmed).
        Must be called BEFORE committing any cast pull so no currency is charged for a
        declaration the player then declines.
        """
        if kwargs.get("confirm_soulfray_risk"):
            return None

        from world.magic.services.soulfray import get_soulfray_warning  # noqa: PLC0415

        character = ctx.participant.character_sheet.character
        warning = get_soulfray_warning(character)
        if warning is None:
            return None

        from commands.pending_actions import PendingCast, register_pending  # noqa: PLC0415

        # The same keys the declaration reads, so a confirmed combat cast keeps its strain, its
        # positions, its resonance and its pull; they cannot drift apart (#5231).
        pending_kwargs = _combat_declaration_kwargs(kwargs)
        for _key in ("action_slot", *_COMBAT_PULL_KEYS):
            _value = kwargs.get(_key)
            if _value is not None:
                pending_kwargs[_key] = _value

        register_pending(
            ctx.participant.character_sheet.pk,
            PendingCast(
                technique_id=technique_id,
                target_persona_id=None,  # combat uses focused_*_target_id
                kwargs=pending_kwargs,
            ),
        )
        return ActionResult(
            success=False,
            message=(
                f"{warning.stage_description} "
                "Use |waccept soulfray|n to proceed or |wdecline soulfray|n to abort."
            ),
        )

    @staticmethod
    def _commit_combat_pull(
        cast_pull: CastPullDeclaration,
        ctx: Any,
        technique_id: int,
        kwargs: dict[str, Any],
    ) -> None:
        """Commit a thread pull as a ``CombatPull`` row at declaration time.

        Delegates to ``world.combat.pull_helpers.commit_combat_pull`` so the
        commit logic is shared with the clash-contribution path and is not
        duplicated here.

        Resolves the live focused target (opponent, else ally) from *kwargs* via
        ``resolve_focused_target_objectdb`` (#1831) and passes it through so
        ``court_regard_modulation`` can fire for COVENANT_ROLE pulls.

        Raises:
            ActionDispatchError(PULL_ALREADY_COMMITTED): When the unique constraint fires
                (duplicate pull in the same round).
            ActionDispatchError(PULL_INVALID): When ``spend_resonance_for_pull`` raises a
                ``MagicError`` (invalid pull declaration — e.g. thread not in action,
                insufficient balance).
        """
        from world.combat.constants import PullBurnAction  # noqa: PLC0415
        from world.combat.pull_helpers import commit_combat_pull  # noqa: PLC0415
        from world.combat.round_context import resolve_focused_target_objectdb  # noqa: PLC0415
        from world.magic.models import Technique  # noqa: PLC0415
        from world.magic.services.magic_skills import resolve_cast_check  # noqa: PLC0415

        participant = ctx.participant
        encounter = participant.encounter
        target = resolve_focused_target_objectdb(encounter, kwargs)
        commit_combat_pull(
            cast_pull=cast_pull,
            participant=participant,
            encounter=encounter,
            technique_id=technique_id,
            burned_for=PullBurnAction.CAST,
            target=target,
            cast_check=resolve_cast_check(
                participant.character_sheet.character, Technique.objects.get(pk=technique_id)
            ),
        )
