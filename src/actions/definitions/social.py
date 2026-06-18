"""Social action singletons — registry-backed dispatch for ActionTemplate social actions (#544).

Each singleton exposes ``target_kind = TargetKind.PERSONA`` so the frontend knows
to prompt for a persona target. The ``execute()`` path goes through
``start_action_resolution`` which resolves the linked ActionTemplate's check chain.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from actions.constants import ActionCategory, TargetKind
from actions.types import TargetFilters, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.base import ActionContext
    from actions.types import ActionResult


class _SocialTemplateAction:
    """Base for social ActionTemplate-driven actions.

    Subclasses MUST set ``key``, ``name``, ``description``, ``template_name``.
    Not a subclass of ``Action`` (which is a dataclass with required positional
    fields); instead it exposes the same interface as class attributes so the
    registry and player_interface can treat it identically to an ``Action``.
    """

    template_name: str = ""
    target_type: TargetType = TargetType.SINGLE
    target_kind: TargetKind = TargetKind.PERSONA
    target_filters: TargetFilters = TargetFilters(in_same_scene=True, exclude_self=True)
    action_category: ActionCategory = ActionCategory.SOCIAL
    costs_turn: bool = True
    intent_event: str | None = None
    result_event: str | None = None

    def execute(self, actor: ObjectDB, context: ActionContext, **kwargs) -> ActionResult:
        from actions.models import ActionTemplate  # noqa: PLC0415
        from actions.services import start_action_resolution  # noqa: PLC0415
        from world.checks.types import ResolutionContext  # noqa: PLC0415

        template = ActionTemplate.objects.get(name=self.template_name)
        resolution_ctx = ResolutionContext(action_context=context)
        return start_action_resolution(
            character=actor,
            template=template,
            target_difficulty=0,
            context=resolution_ctx,
        )


class IntimidateAction(_SocialTemplateAction):
    key = "intimidate"
    name = "Intimidate"
    description = "Coerce through force of presence, threats, or physical dominance."
    icon = "skull"
    template_name = "Intimidate"
    category = "social"


class PersuadeAction(_SocialTemplateAction):
    key = "persuade"
    name = "Persuade"
    description = "Convince through reasoned argument, charm, and social grace."
    icon = "handshake"
    template_name = "Persuade"
    category = "social"


class DeceiveAction(_SocialTemplateAction):
    key = "deceive"
    name = "Deceive"
    description = "Mislead through misdirection, half-truths, or outright lies."
    icon = "mask"
    template_name = "Deceive"
    category = "social"


class FlirtAction(_SocialTemplateAction):
    key = "flirt"
    name = "Flirt"
    description = "Beguile through charm, allure, and romantic suggestion."
    icon = "heart"
    template_name = "Flirt"
    category = "social"


class PerformAction(_SocialTemplateAction):
    key = "perform"
    name = "Perform"
    description = "Captivate an audience through music, oration, or storytelling."
    icon = "music"
    template_name = "Perform"
    category = "social"


class EntranceAction(_SocialTemplateAction):
    key = "entrance"
    name = "Entrance"
    description = "Command attention through sheer force of personality on entering."
    icon = "sparkles"
    template_name = "Entrance"
    category = "social"

    def execute(self, actor: ObjectDB, context: ActionContext, **kwargs) -> ActionResult:
        from actions.models import ActionTemplate  # noqa: PLC0415
        from actions.services import start_action_resolution  # noqa: PLC0415
        from world.checks.types import ResolutionContext  # noqa: PLC0415

        template = ActionTemplate.objects.get(name=self.template_name)
        resolution_ctx = ResolutionContext(action_context=context)
        result = start_action_resolution(
            character=actor,
            template=template,
            target_difficulty=0,
            context=resolution_ctx,
        )

        if template.grants_entry_flourish:
            resonance_id = kwargs.get("resonance_id")
            if resonance_id is not None:
                self._fire_entry_flourish(actor, resonance_id)

        return result

    @staticmethod
    def _fire_entry_flourish(actor: ObjectDB, resonance_id: int) -> None:
        """Fire the entry flourish resonance grant. Best-effort — exceptions are logged."""
        try:
            from world.character_sheets.models import CharacterSheet  # noqa: PLC0415
            from world.magic.models import Resonance  # noqa: PLC0415
            from world.magic.services.gain import create_entry_flourish  # noqa: PLC0415

            sheet = CharacterSheet.objects.filter(character=actor).first()
            if sheet is None:
                return
            resonance = Resonance.objects.get(pk=resonance_id)
            create_entry_flourish(sheet, resonance, scene=None)
        except Exception:  # noqa: BLE001
            import logging  # noqa: PLC0415

            logging.getLogger(__name__).warning(
                "Entry flourish failed for actor %s, resonance_id %s",
                actor.pk,
                resonance_id,
                exc_info=True,
            )


class RestoreSenseAction(_SocialTemplateAction):
    key = "restore_sense"
    name = "Restore to Sense"
    description = "Talk a berserk ally down through force of personality and connection."
    icon = "heart-pulse"
    template_name = "Restore to Sense"
    category = "social"

    def execute(self, actor: ObjectDB, context: ActionContext, **kwargs) -> ActionResult:
        from actions.effects.registry import apply_effects  # noqa: PLC0415
        from actions.models import ActionEnhancement, ActionTemplate  # noqa: PLC0415
        from actions.services import start_action_resolution  # noqa: PLC0415
        from actions.types import (  # noqa: PLC0415
            ActionContext as _ActionContext,
            ActionResult as _ActionResult,
        )
        from flows.scene_data_manager import SceneDataManager  # noqa: PLC0415
        from world.checks.types import ResolutionContext  # noqa: PLC0415

        # Build an ActionContext for the effect dispatch (RemoveConditionOnCheckConfig).
        sdm = SceneDataManager()
        sdm.initialize_state_for_object(actor)
        target = kwargs.get("target")
        effect_ctx = _ActionContext(
            action=self,  # type: ignore[arg-type]
            actor=actor,
            target=target,
            kwargs=kwargs,
            scene_data=sdm,
            result=_ActionResult(success=True),
        )

        # Dispatch all ActionEnhancements wired to "restore_sense".
        # The factory seeds a RemoveConditionOnCheckConfig on one of these enhancements;
        # apply_effects dispatches it to handle_remove_condition_on_check.
        for enh in ActionEnhancement.objects.filter(base_action_key="restore_sense"):
            apply_effects(enh, effect_ctx)

        # Run the standard social template resolution (check + consequence pool).
        template = ActionTemplate.objects.get(name=self.template_name)
        resolution_ctx = ResolutionContext(action_context=context)
        return start_action_resolution(
            character=actor,
            template=template,
            target_difficulty=0,
            context=resolution_ctx,
        )


# Module-level singletons — registered in actions/registry.py
intimidate = IntimidateAction()
persuade = PersuadeAction()
deceive = DeceiveAction()
flirt = FlirtAction()
perform = PerformAction()
entrance = EntranceAction()
restore_sense = RestoreSenseAction()
