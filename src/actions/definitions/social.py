"""Social action singletons — registry-backed dispatch for ActionTemplate social actions (#544).

Each singleton exposes ``target_kind = TargetKind.PERSONA`` so the frontend knows
to prompt for a persona target. The ``execute()`` path goes through
``start_action_resolution`` which resolves the linked ActionTemplate's check chain.

These are real ``Action`` subclasses (#1172): the registry dispatch path and the
scene consent path both rely on the ``Action`` interface (``run()`` / ``execute()`` /
``dispatch_effects()``). Inherent target effects (e.g. RestoreSense removing a
Berserk condition) live in ``dispatch_effects`` so they fire exactly once whether
the action is driven through ``run()`` or through the scene consent resolution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.constants import ActionCategory, TargetKind
from actions.types import TargetFilters, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.models import ActionTemplate
    from actions.prerequisites import Prerequisite
    from actions.types import ActionContext, ActionResult, PendingActionResolution
    from flows.scene_data_manager import SceneDataManager
    from world.character_sheets.models import CharacterSheet
    from world.magic.models import Technique
    from world.magic.types import SoulfrayWarning
    from world.scenes.models import Interaction, Persona, Scene
    from world.scenes.types import CastResult


def _maybe_fire_decisive_for_direct_action(
    actor: ObjectDB,
    resolution: PendingActionResolution,
) -> None:
    """Fire any pending DecisiveCheckMarker after a direct social check (#1748)."""
    from world.scenes.decisive_check_services import maybe_fire_decisive_check  # noqa: PLC0415
    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

    main = resolution.main_result
    if main is None:
        return
    if actor.location is None:
        return
    scene = get_active_scene(actor.location)
    if scene is None:
        return
    try:
        sheet = actor.sheet_data
    except AttributeError:
        return
    maybe_fire_decisive_check(
        scene=scene,
        check_outcome=main.check_result.outcome,
        initiator_sheet=sheet,
    )


@dataclass
class _SocialTemplateAction(Action):
    """Base for social ActionTemplate-driven actions.

    Subclasses set ``key``, ``name``, ``icon``, and ``template_name``. The
    common social defaults (PERSONA single target, social category, turn cost)
    are supplied here so concrete classes only declare what differs.
    """

    category: str = "social"
    target_type: TargetType = TargetType.SINGLE
    target_kind: TargetKind | None = TargetKind.PERSONA
    target_filters: TargetFilters | None = field(
        default_factory=lambda: TargetFilters(in_same_scene=True, exclude_self=True)
    )
    action_category: ActionCategory | None = ActionCategory.SOCIAL
    costs_turn: bool = True

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        _template, result = self._resolve_template(actor, context, **kwargs)
        return result

    def _resolve_template(
        self,
        actor: ObjectDB,
        context: ActionContext | None,
        **kwargs: Any,
    ) -> tuple[ActionTemplate, ActionResult]:
        """Resolve this action's ActionTemplate and wrap the outcome into an ``ActionResult``.

        Shared by the base ``execute()`` and ``EntranceAction.execute()`` (which needs the
        ``ActionTemplate`` afterward to decide the entry-flourish offer). Dispatches inherent
        target effects first (no-op for plain social actions; RestoreSense removes Berserk).
        On this path a single dispatch only runs through ``execute()``, never the consent
        path too.
        """
        from actions.models import ActionTemplate  # noqa: PLC0415
        from actions.services import start_action_resolution  # noqa: PLC0415
        from world.checks.types import ResolutionContext  # noqa: PLC0415

        scene_data = context.scene_data if context is not None else None
        self.dispatch_effects(actor, kwargs.get("target"), scene_data)

        template = ActionTemplate.objects.get(name=self.template_name)
        resolution_ctx = ResolutionContext(character=actor, action_context=context)
        resolution = start_action_resolution(
            character=actor,
            template=template,
            target_difficulty=0,
            context=resolution_ctx,
        )
        result = self._result_from_resolution(resolution)
        # Disposition delta is a side effect of the resolution completing, like
        # ``dispatch_effects`` above — kept in this shared path so every social
        # template action (Persuade/Intimidate/Entrance/…) moves NPC affection
        # (#1591). The raw ``resolution`` carries the success tier (ADR-0019).
        self._apply_disposition_delta(actor, kwargs.get("target_persona_id"), resolution)
        # #1748: fire any pending decisive-check marker after a direct social check.
        _maybe_fire_decisive_for_direct_action(actor, resolution)
        return template, result

    @staticmethod
    def _result_from_resolution(
        resolution: PendingActionResolution, message: str | None = None
    ) -> ActionResult:
        """Wrap a ``PendingActionResolution`` into the ``ActionResult`` its consumers expect.

        ``execute()``'s only live consumers are REGISTRY ones — the telnet command
        (reads ``.message``) and the web dispatcher (stuffs the result into
        ``DispatchResult.detail``, typed ``ActionResult``). The rich pending-resolution
        object is consumed elsewhere by direct callers of ``start_action_resolution``
        (scene consent, cast), never through here — so returning an ``ActionResult`` is
        both honest and what these consumers actually read (#1245). Success is the one
        canonical expression every resolution consumer uses
        (``main_result.check_result.success_level``); ``main_result is None`` is a
        *paused* resolution whose main step hasn't rolled, so it cannot have succeeded.
        The full resolution rides ``data`` so nothing is lost.
        """
        from actions.types import ActionResult as _ActionResult  # noqa: PLC0415

        main = resolution.main_result
        succeeded = main is not None and main.check_result.success_level > 0
        return _ActionResult(success=succeeded, message=message, data={"resolution": resolution})

    def _apply_disposition_delta(self, actor, target_persona_id, resolution):
        """Move NPC disposition by the social check's success tier (#1591).

        ``resolution`` is the raw ``PendingActionResolution`` whose
        ``main_result.check_result.success_level`` grades the delta (ADR-0019).
        """
        from world.npc_services.social_disposition import (  # noqa: PLC0415
            apply_social_disposition_delta,
        )

        apply_social_disposition_delta(actor, target_persona_id, resolution)


@dataclass
class IntimidateAction(_SocialTemplateAction):
    key: str = "intimidate"
    name: str = "Intimidate"
    icon: str = "skull"
    template_name: str = "Intimidate"
    description: str = "Coerce through force of presence, threats, or physical dominance."


@dataclass
class PersuadeAction(_SocialTemplateAction):
    key: str = "persuade"
    name: str = "Persuade"
    icon: str = "handshake"
    template_name: str = "Persuade"
    description: str = "Convince through reasoned argument, charm, and social grace."


@dataclass
class DeceiveAction(_SocialTemplateAction):
    key: str = "deceive"
    name: str = "Deceive"
    icon: str = "mask"
    template_name: str = "Deceive"
    description: str = "Mislead through misdirection, half-truths, or outright lies."


@dataclass
class FlirtAction(_SocialTemplateAction):
    key: str = "flirt"
    name: str = "Flirt"
    icon: str = "heart"
    template_name: str = "Flirt"
    description: str = "Beguile through charm, allure, and romantic suggestion."


@dataclass
class SeduceAction(_SocialTemplateAction):
    key: str = "seduce"
    name: str = "Seduce"
    icon: str = "flame"
    template_name: str = "Seduce"
    description: str = (
        "Press an attraction further — a harder roll than a flirt, with a deeper hold."
    )


@dataclass
class BlackmailAction(_SocialTemplateAction):
    key: str = "blackmail"
    name: str = "Blackmail"
    icon: str = "lock"
    template_name: str = "Blackmail"
    description: str = "Press a secret you hold over them — comply, or see it exposed."

    def get_prerequisites(self) -> list[Prerequisite]:
        from actions.prerequisites import BlackmailAmmoPrerequisite  # noqa: PLC0415

        return [*super().get_prerequisites(), BlackmailAmmoPrerequisite()]

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        _template, result = self._resolve_template(actor, context, **kwargs)
        # On a SUCCESSFUL press, mint standing Leverage founded on the pressed secret. The
        # ammo prereq already validated (secret known + about the target) before execute, so
        # the resolves here can't fail; the guard is belt-and-suspenders.
        if result.success:
            from actions.prerequisites import resolve_actor_sheet  # noqa: PLC0415
            from world.secrets.models import Secret  # noqa: PLC0415
            from world.secrets.services import mint_leverage  # noqa: PLC0415

            secret = Secret.objects.filter(pk=kwargs.get("secret_id")).first()
            target = kwargs.get("target")
            actor_sheet = resolve_actor_sheet(actor)
            target_sheet = resolve_actor_sheet(target) if target is not None else None
            if secret is not None and actor_sheet is not None and target_sheet is not None:
                mint_leverage(
                    holder_sheet=actor_sheet, subject_sheet=target_sheet, founded_on=secret
                )
        return result


@dataclass
class BoonAction(_SocialTemplateAction):
    key: str = "boon"
    name: str = "Boon"
    icon: str = "gift"
    template_name: str = "Boon"
    description: str = (
        "Press someone to grant you a boon — money, an item, or a deed, named up front."
    )
    # Fulfillment does NOT live in execute(): the consent paths never call it (the
    # Blackmail mint asymmetry). The `boon` resolver registered by
    # world.scenes.boon_services fires on both the NPC auto-accept and the piloted
    # accept paths, fulfilling the ask and charging the per-Boon affection cost.


@dataclass
class PerformAction(_SocialTemplateAction):
    key: str = "perform"
    name: str = "Perform"
    icon: str = "music"
    template_name: str = "Perform"
    description: str = "Captivate an audience through music, oration, or storytelling."


def run_entrance_success_hooks(  # noqa: PLR0913 - cohesive entrance-hook params; shared w/ Task 5
    actor: ObjectDB,
    scene: Scene | None,
    *,
    success_level: int | None,
    target_persona_id: int | None,  # noqa: ARG001 - reserved: Task 5's combat-resolution reuse
    technique: Technique,  # noqa: ARG001 - reserved: Task 5's combat-resolution reuse
    interaction: Interaction | None = None,
) -> str | None:
    """Flourish offer + dramatic-moment suggestion for an entrance (#2183).

    Shared by ``EntranceAction`` (both the bare ActionTemplate path and the
    technique-driven ``_execute_technique_entrance`` path) and Task 5's deferred
    combat-resolution hook — keep this signature stable.

    Disposition is deliberately NOT here: it needs the raw
    ``PendingActionResolution`` (not just an int success level), which only the
    resolved-inline branch of ``_execute_technique_entrance`` has in hand — that
    caller applies it directly.

    - Flourish offer: gated on the "Entrance" ``ActionTemplate.grants_entry_flourish``
      (fetched by name, independent of *technique*'s own action_template — a technique
      cast has no ActionTemplate of its own tied to "Entrance").
    - Suggestion: only when ``success_level`` is not None — the hostile-seeded branch
      defers this to Task 5's combat-resolution hook, where the real success level
      becomes known once the declared cast resolves.

    Returns the flourish prompt string (or None if no offer was created) so the
    caller can fold it into its own result message.
    """
    from actions.models import ActionTemplate  # noqa: PLC0415
    from actions.prerequisites import resolve_actor_sheet  # noqa: PLC0415

    prompt: str | None = None
    template = ActionTemplate.objects.filter(name="Entrance").first()
    if template is not None and template.grants_entry_flourish:
        from world.magic.entry_flourish import (  # noqa: PLC0415
            maybe_create_entry_flourish_offer,
        )

        offer = maybe_create_entry_flourish_offer(actor, scene)
        if offer is not None:
            prompt = "Use |wflourish <resonance>|n to declare your entrance."

    if success_level is not None:
        actor_sheet = resolve_actor_sheet(actor)
        if actor_sheet is not None:
            from world.magic.services.gain import maybe_suggest_dramatic_moments  # noqa: PLC0415

            maybe_suggest_dramatic_moments(
                character_sheet=actor_sheet,
                scene=scene,
                success_level=success_level,
                interaction=interaction,
            )

    return prompt


@dataclass
class EntranceAction(_SocialTemplateAction):
    key: str = "entrance"
    name: str = "Entrance"
    icon: str = "sparkles"
    template_name: str = "Entrance"
    description: str = "Command attention through sheer force of personality on entering."

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        technique_id = kwargs.pop("technique_id", None)
        if technique_id is not None:
            return self._execute_technique_entrance(
                actor, context, technique_id=technique_id, **kwargs
            )

        template, result = self._resolve_template(actor, context, **kwargs)

        # On a SUCCESSFUL entrance, open the entry-flourish offer (actor self-grant)
        # and prompt the actor toward declaring it. The prompt rides the result
        # ``message`` like every other action — the command surfaces it via
        # ``self.msg(result.message)`` and the web dispatcher via ``detail.message`` (#1245).
        if template.grants_entry_flourish and result.success:
            from world.magic.entry_flourish import (  # noqa: PLC0415
                maybe_create_entry_flourish_offer,
            )

            loc = actor.location
            scene = loc.active_scene if loc is not None and hasattr(loc, "active_scene") else None
            offer = maybe_create_entry_flourish_offer(actor, scene)
            if offer is not None:
                prompt = "Use |wflourish <resonance>|n to declare your entrance."
                result.message = f"{result.message}\n{prompt}" if result.message else prompt

        return result

    def _execute_technique_entrance(  # noqa: PLR0913 - mirrors CastTechniqueAction.execute
        self,
        actor: ObjectDB,
        context: ActionContext | None,
        *,
        technique_id: int,
        target_persona_id: int | None = None,
        confirm_soulfray_risk: bool = False,
        entry_interaction_id: int | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        """Technique-driven combat entrance (#2183) — the ``enter <technique>`` path.

        Mirrors ``CastTechniqueAction.execute`` (scene/persona/technique/target
        resolution, soulfray ``PendingCast`` gating) but routes the outcome through
        the deferral matrix instead of a flat success/failure — see
        ``_dispatch_entrance_cast`` for the branch-by-branch breakdown.
        """
        from actions.prerequisites import resolve_actor_sheet  # noqa: PLC0415
        from actions.types import ActionResult as _ActionResult  # noqa: PLC0415
        from world.combat.cast_seed import _feedable_encounter  # noqa: PLC0415
        from world.combat.constants import OpponentStatus, ParticipantStatus  # noqa: PLC0415
        from world.combat.models import CombatOpponent, CombatParticipant  # noqa: PLC0415
        from world.magic.models import Technique  # noqa: PLC0415
        from world.scenes.models import Persona, Scene  # noqa: PLC0415
        from world.scenes.services import persona_for_character  # noqa: PLC0415

        scene = Scene.objects.filter(location=actor.location, is_active=True).first()
        if scene is None:
            return _ActionResult(success=False, message="There is no active scene here.")

        actor_sheet = resolve_actor_sheet(actor)
        if actor_sheet is not None:
            feedable = _feedable_encounter(scene)
            if feedable is not None:
                already_participant = CombatParticipant.objects.filter(
                    encounter=feedable,
                    character_sheet=actor_sheet,
                    status=ParticipantStatus.ACTIVE,
                ).exists()
                already_opponent = CombatOpponent.objects.filter(
                    encounter=feedable,
                    objectdb=actor,
                    status=OpponentStatus.ACTIVE,
                ).exists()
                if already_participant or already_opponent:
                    return _ActionResult(success=False, message="You're already in the fight.")

        initiator = persona_for_character(actor)

        try:
            technique = Technique.objects.get(pk=technique_id)
        except Technique.DoesNotExist:
            return _ActionResult(success=False, message="Technique not found.")

        target: Persona | None = None
        if target_persona_id is not None:
            try:
                target = Persona.objects.get(pk=target_persona_id)
            except Persona.DoesNotExist:
                return _ActionResult(success=False, message="Target persona not found.")

        battle_context = self._resolve_battle_context(actor_sheet, scene)

        return self._dispatch_entrance_cast(
            actor,
            scene,
            actor_sheet,
            initiator,
            technique,
            target,
            technique_id=technique_id,
            target_persona_id=target_persona_id,
            confirm_soulfray_risk=confirm_soulfray_risk,
            entry_interaction_id=entry_interaction_id,
            entrance_kwargs=kwargs,
            battle_context=battle_context,
        )

    def _dispatch_entrance_cast(  # noqa: PLR0913 - cohesive entrance-cast dispatch params
        self,
        actor: ObjectDB,
        scene: Scene,
        actor_sheet: CharacterSheet | None,
        initiator: Persona,
        technique: Technique,
        target: Persona | None,
        *,
        technique_id: int,
        target_persona_id: int | None,
        confirm_soulfray_risk: bool,
        entry_interaction_id: int | None,
        entrance_kwargs: dict[str, Any],
        battle_context: tuple[Any, Any] | None = None,
    ) -> ActionResult:
        """Call ``request_technique_cast`` and route the outcome per the #2183 deferral matrix.

        - soulfray gate not confirmed → register a ``PendingCast`` (mirrors cast.py).
        - PENDING (benign consent-gated, or hostile risk-gated) → no hooks now;
          Task 5 wires them at accept-time resolution.
        - hostile, seeded straight into combat → flourish only (the success level
          isn't known until the declared cast resolves — Task 5's combat hook fires
          the suggestion then).
        - resolved inline → full hooks when the success level clears 0, plus a
          benign-intervention combat join when the target is another sheet's
          ACTIVE combatant.
        """
        from actions.types import ActionResult as _ActionResult  # noqa: PLC0415
        from world.magic.exceptions import MagicError  # noqa: PLC0415
        from world.scenes.cast_services import request_technique_cast  # noqa: PLC0415
        from world.scenes.models import Interaction  # noqa: PLC0415

        try:
            cast = request_technique_cast(
                scene=scene,
                initiator_persona=initiator,
                target_persona=target,
                technique=technique,
                confirm_soulfray_risk=confirm_soulfray_risk,
                originated_as_entrance=True,
            )
        except MagicError as exc:
            # user_message, never str(exc) — exception detail must not reach players.
            return _ActionResult(success=False, message=exc.user_message)

        if cast.soulfray_warning is not None and not confirm_soulfray_risk:
            return self._register_entrance_soulfray_pending(
                actor_sheet,
                cast.soulfray_warning,
                technique_id=technique_id,
                target_persona_id=target_persona_id,
                entry_interaction_id=entry_interaction_id,
                entrance_kwargs=entrance_kwargs,
            )

        entry_interaction: Interaction | None = None
        if entry_interaction_id is not None:
            entry_interaction = Interaction.objects.filter(pk=entry_interaction_id).first()

        if cast.result is None and cast.encounter is None:
            # PENDING — benign consent-gated, or hostile risk-gated (#777). Task 5
            # fires the deferred hooks when the request resolves on accept.
            return _ActionResult(success=True, message="Your entrance hangs on their consent.")

        if cast.encounter is not None:
            self._maybe_bind_battle_encounter(cast.encounter, battle_context)
            return self._resolve_hostile_entrance_result(
                actor, scene, technique, target_persona_id, entry_interaction
            )

        return self._resolve_inline_entrance_result(
            actor, scene, actor_sheet, technique, target, target_persona_id, entry_interaction, cast
        )

    @staticmethod
    def _register_entrance_soulfray_pending(  # noqa: PLR0913 - cohesive pending-cast registration
        actor_sheet: CharacterSheet | None,
        warning: SoulfrayWarning,
        *,
        technique_id: int,
        target_persona_id: int | None,
        entry_interaction_id: int | None,
        entrance_kwargs: dict[str, Any],
    ) -> ActionResult:
        """Register a ``PendingCast`` for the soulfray consent gate, mirroring ``cast.py``.

        Stores an ``"entrance": True`` marker in the pending kwargs so a future
        re-dispatch can be routed back to the entrance path (not yet wired here —
        the generic ``SoulfrayPendingHandler`` always re-dispatches to
        ``cast_technique`` today).
        """
        from actions.types import ActionResult as _ActionResult  # noqa: PLC0415

        sheet_pk = actor_sheet.pk if actor_sheet is not None else None
        if sheet_pk is not None:
            from commands.pending_actions import PendingCast, register_pending  # noqa: PLC0415

            register_pending(
                sheet_pk,
                PendingCast(
                    technique_id=technique_id,
                    target_persona_id=target_persona_id,
                    kwargs={
                        "entrance": True,
                        "entry_interaction_id": entry_interaction_id,
                        **entrance_kwargs,
                    },
                ),
            )
        return _ActionResult(
            success=False,
            message=(
                f"{warning.stage_description} "  # type: ignore[attr-defined]
                "Use |waccept soulfray|n to proceed or |wdecline soulfray|n to abort."
            ),
        )

    @staticmethod
    def _resolve_hostile_entrance_result(
        actor: ObjectDB,
        scene: Scene,
        technique: Technique,
        target_persona_id: int | None,
        entry_interaction: Interaction | None,
    ) -> ActionResult:
        """Hostile technique erupted straight into open combat — flourish only.

        The declared cast hasn't resolved yet, so the success level (and thus the
        dramatic-moment suggestion) isn't known; Task 5's combat-resolution hook
        fires the suggestion once the round resolves.
        """
        from actions.types import ActionResult as _ActionResult  # noqa: PLC0415

        prompt = run_entrance_success_hooks(
            actor,
            scene,
            success_level=None,
            target_persona_id=target_persona_id,
            technique=technique,
            interaction=entry_interaction,
        )
        message = "Your entrance erupts into open combat!"
        if prompt:
            message = f"{message}\n{prompt}"
        return _ActionResult(success=True, message=message)

    @staticmethod
    def _resolve_inline_entrance_result(  # noqa: PLR0913 - cohesive resolved-inline outcome params
        actor: ObjectDB,
        scene: Scene,
        _actor_sheet: CharacterSheet | None,  # #2226: was used for seating, now generalized
        technique: Technique,
        _target: Persona | None,  # #2226: was used for seating, now generalized
        target_persona_id: int | None,
        entry_interaction: Interaction | None,
        cast: CastResult,
    ) -> ActionResult:
        """Self/room/no-target cast, or a benign no-consent cast aimed at another PC.

        (``request_technique_cast`` routes the latter through the immediate path too —
        only a hostile or consent-requiring technique detours through the
        combat-seed/PENDING branches in ``_dispatch_entrance_cast``.)
        """
        from actions.types import ActionResult as _ActionResult  # noqa: PLC0415
        from world.magic.services.hostility import is_technique_hostile  # noqa: PLC0415
        from world.npc_services.social_disposition import (  # noqa: PLC0415
            apply_social_disposition_delta,
        )

        main = cast.result.action_resolution.main_result if cast.result is not None else None  # type: ignore[attr-defined]
        success_level = main.check_result.success_level if main is not None else 0

        if not is_technique_hostile(technique) and target_persona_id is not None:
            apply_social_disposition_delta(
                actor,
                target_persona_id,
                cast.result.action_resolution,  # type: ignore[attr-defined]
            )

        if success_level <= 0:
            return _ActionResult(success=False, message="Your entrance fails to draw notice.")

        prompt = run_entrance_success_hooks(
            actor,
            scene,
            success_level=success_level,
            target_persona_id=target_persona_id,
            technique=technique,
            interaction=entry_interaction,
        )
        message = "Your entrance commands the room."
        if prompt:
            message = f"{message}\n{prompt}"

        # #2226: combat seating for benign casts is now handled by
        # _route_immediate_cast's generalized seating call — no need to
        # duplicate it here.
        return _ActionResult(success=True, message=message)

    @staticmethod
    def _resolve_battle_context(
        actor_sheet: CharacterSheet | None,
        scene: Scene,
    ) -> tuple[Any, Any] | None:
        """Detect whether the actor is a stationed battle participant at this scene (#2225).

        Returns ``(BattleParticipant, BattlePlace)`` when the actor is an active
        ``BattleParticipant`` stationed at a ``BattlePlace`` whose battle's scene
        matches *scene*. Returns None otherwise (not in a battle, not stationed,
        or scene co-location mismatch — all fall through to the normal entrance flow).

        The stationing check stays in the action layer (ADR-0010): ``world.combat``
        never imports from ``world.battles``.
        """
        if actor_sheet is None:
            return None

        from world.battles.constants import BattleParticipantStatus  # noqa: PLC0415
        from world.battles.models import BattleParticipant  # noqa: PLC0415

        participant = (
            BattleParticipant.objects.select_related(
                "place__battle__scene",
            )
            .filter(
                character_sheet=actor_sheet,
                status=BattleParticipantStatus.ACTIVE,
            )
            .first()
        )
        if participant is None or participant.place is None:
            return None

        battle_place = participant.place
        if battle_place.battle.scene_id != scene.pk:
            return None

        return participant, battle_place

    @staticmethod
    def _maybe_bind_battle_encounter(
        encounter: Any,
        battle_context: tuple[Any, Any] | None,
    ) -> None:
        """Bind a hostile-seeded encounter to the actor's BattlePlace (#2225).

        Called inside ``_dispatch_entrance_cast`` on the hostile-seeded branch,
        where ``cast.encounter`` is in scope. When the actor's ``BattlePlace``
        has no open encounter (FK is None or points at a COMPLETED encounter),
        binds the new encounter to the place and installs the place-encounter
        outcome trigger. When the place already has an open encounter, no-ops
        (the cast fed it via ``_feedable_encounter``; it's already bound).

        The ``BattlePlace.combat_encounter`` FK persists after completion
        (``complete_encounter`` only sets ``status=COMPLETED``, never nulls the
        FK), so the "open" check uses status filtering, not raw FK presence.
        """
        if battle_context is None:
            return

        from world.battles.place_encounter_wiring import (  # noqa: PLC0415
            install_place_encounter_trigger,
        )
        from world.scenes.constants import RoundStatus  # noqa: PLC0415

        _participant, battle_place = battle_context

        existing = battle_place.combat_encounter
        if existing is not None and existing.status in (
            RoundStatus.DECLARING,
            RoundStatus.BETWEEN_ROUNDS,
        ):
            return

        battle_place.combat_encounter = encounter
        battle_place.save(update_fields=["combat_encounter"])
        install_place_encounter_trigger(encounter)


@dataclass
class RestoreSenseAction(_SocialTemplateAction):
    key: str = "restore_sense"
    name: str = "Restore to Sense"
    icon: str = "heart-pulse"
    template_name: str = "Restore to Sense"
    description: str = "Talk a berserk ally down through force of personality and connection."

    def dispatch_effects(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        scene_data: SceneDataManager | None = None,
    ) -> None:
        """Dispatch the RemoveConditionOnCheckConfig wired to ``restore_sense``.

        The factory seeds a ``RemoveConditionOnCheckConfig`` on an
        ``ActionEnhancement`` keyed ``base_action_key="restore_sense"``;
        ``apply_effects`` dispatches it to ``handle_remove_condition_on_check``,
        which rolls a check against *target* and removes the Berserk condition on
        success. Called by ``execute()`` (registry/``run()`` path) and by the
        scene consent resolution.
        """
        from actions.effects.registry import apply_effects  # noqa: PLC0415
        from actions.models import ActionEnhancement  # noqa: PLC0415
        from actions.types import (  # noqa: PLC0415
            ActionContext as _ActionContext,
            ActionResult as _ActionResult,
        )
        from flows.scene_data_manager import SceneDataManager  # noqa: PLC0415

        sdm = scene_data
        if sdm is None:
            sdm = SceneDataManager()
            sdm.initialize_state_for_object(actor)

        effect_ctx = _ActionContext(
            action=self,
            actor=actor,
            target=target,
            kwargs={},
            scene_data=sdm,
            result=_ActionResult(success=True),
        )

        for enh in ActionEnhancement.objects.filter(base_action_key=self.key):
            apply_effects(enh, effect_ctx)


@dataclass
class ResolveFlourishOfferAction(Action):
    """Resolve a pending entry-flourish offer by declaring a resonance."""

    key: str = "resolve_entry_flourish"
    name: str = "Declare Flourish"
    icon: str = "sparkles"
    category: str = "social"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        *,
        offer: object,
        resonance: object,
        **kwargs: Any,
    ) -> ActionResult:
        from actions.types import ActionResult as _ActionResult  # noqa: PLC0415
        from world.magic.entry_flourish import resolve_entry_flourish_offer  # noqa: PLC0415
        from world.magic.exceptions import (  # noqa: PLC0415
            EntryFlourishOfferNotFoundError,
            EntryFlourishOfferStaleError,
        )

        try:
            entry_result = resolve_entry_flourish_offer(offer, resonance=resonance)
        except EntryFlourishOfferNotFoundError:
            return _ActionResult(success=False, message="You have no pending flourish offer.")
        except EntryFlourishOfferStaleError:
            return _ActionResult(
                success=False,
                message="That resonance is no longer yours to broadcast.",
            )
        return _ActionResult(
            success=True,
            message=(
                f"Your {entry_result.resonance_name} fills the room as you announce your arrival."
            ),
            data={"entry_flourish_result": entry_result},
        )


# Module-level singletons — registered in actions/registry.py
intimidate = IntimidateAction()
persuade = PersuadeAction()
deceive = DeceiveAction()
flirt = FlirtAction()
seduce = SeduceAction()
blackmail = BlackmailAction()
boon = BoonAction()
perform = PerformAction()
entrance = EntranceAction()
restore_sense = RestoreSenseAction()
resolve_entry_flourish = ResolveFlourishOfferAction()
