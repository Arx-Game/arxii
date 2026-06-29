"""Deed-scene Actions — spread a tale and save a written deed account (#1503).

Both actions are `SCENE_ADAPTIVE` and return `None` from `round_declaration`, so they resolve
immediately while still participating in anti-spam gating and pose-order tracking.
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
class SpreadTaleAction(Action):
    """Spread a tale about a deed the actor's persona knows.

    kwargs:
        persona_id: PK of the ``Persona`` performing the spread (must belong to the actor).
        scene_id: PK of the ``Scene`` where the tale is told.
        deed_id: PK of the ``LegendEntry`` being spread.
        effort_level: "low" / "medium" / "high" — defaults to "medium".
        specialization_id: Optional PK of a Performance specialization.
        pose_text: Optional in-character pose text (blank if omitted).
    """

    key: str = "spread_tale"
    name: str = "Spread a Tale"
    icon: str = "megaphone"
    category: str = "social"
    target_type: TargetType = TargetType.SELF

    @staticmethod
    def _resolve_account(actor: ObjectDB, scene: Any, kwargs: dict[str, Any]) -> Any:
        """Resolve the requesting account, or None if it isn't a scene participant."""
        account = actor.account
        if account is None:
            requester_id = kwargs.get("requester_account_id")
            if requester_id is not None:
                from evennia.accounts.models import AccountDB  # noqa: PLC0415

                account = AccountDB.objects.filter(pk=requester_id).first()
        if account is None or not scene.participants.filter(pk=account.pk).exists():
            return None
        return account

    @staticmethod
    def _resolve_specialization(kwargs: dict[str, Any]) -> tuple[Any, str]:
        """Return (specialization, error_message); specialization is None when not chosen."""
        specialization_id = kwargs.get("specialization_id")
        if specialization_id is None:
            return None, ""

        from world.skills.models import Specialization  # noqa: PLC0415
        from world.societies.spread_services import (  # noqa: PLC0415
            get_spread_specializations,
        )

        valid_ids = set(get_spread_specializations().values_list("pk", flat=True))
        if specialization_id not in valid_ids:
            return None, "That form cannot be used to spread a tale."
        return Specialization.objects.get(pk=specialization_id), ""

    def execute(  # noqa: PLR0911
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.core.exceptions import ValidationError  # noqa: PLC0415
        from django.shortcuts import get_object_or_404  # noqa: PLC0415

        from world.locations.activity_services import room_activity_band  # noqa: PLC0415
        from world.scenes.action_services import create_and_resolve_area_action  # noqa: PLC0415
        from world.scenes.models import Scene  # noqa: PLC0415
        from world.societies.models import LegendEntry  # noqa: PLC0415
        from world.societies.spread_services import (  # noqa: PLC0415
            SPREAD_TALE_ACTION_KEY,
            get_or_create_spread_a_tale_template,
            get_spreadable_deeds,
            spread_check_modifiers,
        )

        sheet = actor.sheet_data
        persona_id = kwargs.get("persona_id")
        if persona_id is None:
            return ActionResult(success=False, message="You must choose a persona.")

        from world.scenes.models import Persona  # noqa: PLC0415

        persona = Persona.objects.filter(pk=persona_id, character_sheet=sheet).first()
        if persona is None:
            return ActionResult(success=False, message="You do not control that persona.")

        scene_id = kwargs.get("scene_id")
        if scene_id is None:
            return ActionResult(success=False, message="You must be in a scene.")
        scene = get_object_or_404(Scene, pk=scene_id)
        account = self._resolve_account(actor, scene, kwargs)
        if account is None:
            return ActionResult(success=False, message="You are not a participant in that scene.")

        deed_id = kwargs.get("deed_id")
        if deed_id is None:
            return ActionResult(success=False, message="You must choose a deed to spread.")
        deed = get_object_or_404(LegendEntry, pk=deed_id)
        if not get_spreadable_deeds(persona).filter(pk=deed.pk).exists():
            return ActionResult(
                success=False,
                message="This persona is not aware of that deed.",
            )

        specialization, spec_error = self._resolve_specialization(kwargs)
        if spec_error:
            return ActionResult(success=False, message=spec_error)

        extra_modifiers = spread_check_modifiers(sheet.character, specialization)
        template = get_or_create_spread_a_tale_template()

        try:
            result = create_and_resolve_area_action(
                scene=scene,
                initiator_persona=persona,
                action_template=template,
                action_key=SPREAD_TALE_ACTION_KEY,
                pose_text=kwargs.get("pose_text", ""),
                effort_level=kwargs.get("effort_level", "medium"),
                spread_deed_target=deed,
                extra_modifiers=extra_modifiers,
            )
        except ValidationError as exc:
            return ActionResult(success=False, message=exc.messages[0])
        except ValueError:
            return ActionResult(
                success=False,
                message="The tale could not be spread right now.",
            )

        main = result.action_resolution.main_result
        outcome = main.check_result.outcome_name if main and main.check_result else "Unknown"
        band = room_activity_band(scene.location).label
        return ActionResult(
            success=True,
            message=f"You spread the tale of {deed.title}.",
            data={"resolved": True, "outcome": outcome, "band": band},
        )

    def round_declaration(self, ctx: Any, **kwargs: Any) -> tuple[Any, dict[str, Any]] | None:
        """Immediate resolution only."""
        return None


@dataclass
class SaveDeedStoryAction(Action):
    """Save (or replace) this persona's written account of a deed.

    kwargs:
        persona_id: PK of the ``Persona`` authoring the story.
        deed_id: PK of the ``LegendEntry`` being written about.
        text: The written account.
    """

    key: str = "save_deed_story"
    name: str = "Save Deed Story"
    icon: str = "quill"
    category: str = "social"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from django.shortcuts import get_object_or_404  # noqa: PLC0415

        from world.scenes.models import Persona  # noqa: PLC0415
        from world.societies.models import LegendEntry  # noqa: PLC0415
        from world.societies.spread_services import (  # noqa: PLC0415
            get_spreadable_deeds,
            save_deed_story,
        )

        sheet = actor.sheet_data
        persona_id = kwargs.get("persona_id")
        if persona_id is None:
            return ActionResult(success=False, message="You must choose a persona.")

        persona = Persona.objects.filter(pk=persona_id, character_sheet=sheet).first()
        if persona is None:
            return ActionResult(success=False, message="You do not control that persona.")

        deed_id = kwargs.get("deed_id")
        if deed_id is None:
            return ActionResult(success=False, message="You must choose a deed.")
        deed = get_object_or_404(LegendEntry, pk=deed_id)
        if not get_spreadable_deeds(persona).filter(pk=deed.pk).exists():
            return ActionResult(
                success=False,
                message="This persona is not aware of that deed.",
            )

        text = kwargs.get("text", "").strip()
        if not text:
            return ActionResult(success=False, message="You must write something.")

        story = save_deed_story(author_persona=persona, deed=deed, text=text)
        return ActionResult(
            success=True,
            message="You record your account of the deed.",
            data={"story_id": story.pk, "author_name": persona.name, "text": story.text},
        )

    def round_declaration(self, ctx: Any, **kwargs: Any) -> tuple[Any, dict[str, Any]] | None:
        """Immediate resolution only."""
        return None
