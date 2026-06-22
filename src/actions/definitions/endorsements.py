"""Actions for resonance-gain endorsements (Spec C §2.2 / §2.3 / #1152, #1340)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionContext, ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

_POSE_PREVIEW_MAX_CHARS = 200


@dataclass
class PoseEndorseAction(Action):
    """Endorse a peer's RP pose for resonance gain (settles at weekly pot).

    Two-phase to prevent targeting the wrong pose:
    - ``confirm=False`` (default): preview mode — returns the pose text so the
      endorser can confirm they have the right one. No DB row is written.
    - ``confirm=True``: commit — creates the PoseEndorsement row.

    kwargs:
        interaction: Interaction — the pose to endorse
        resonance: Resonance — which resonance to award
        confirm: bool — False = preview, True = commit (default False)
    """

    key: str = "endorse_pose"
    name: str = "Endorse Pose"
    icon: str = "heart"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.magic.exceptions import EndorsementValidationError  # noqa: PLC0415
        from world.magic.services.gain import create_pose_endorsement  # noqa: PLC0415

        interaction = kwargs.get("interaction")
        resonance = kwargs.get("resonance")
        confirm = kwargs.get("confirm", False)

        if interaction is None:
            return ActionResult(
                success=False,
                message="Which pose? (endorse pose <char> [#N] resonance=<name>)",
            )
        if resonance is None:
            return ActionResult(
                success=False,
                message="Which resonance? (endorse pose <char> resonance=<name>)",
            )

        if not confirm:
            author = interaction.persona.name if interaction.persona else "Unknown"
            content = interaction.content or ""
            preview = content[:_POSE_PREVIEW_MAX_CHARS] + (
                "..." if len(content) > _POSE_PREVIEW_MAX_CHARS else ""
            )
            return ActionResult(
                success=True,
                message=(
                    f"You are about to endorse this pose by {author} "
                    f"for {resonance.name}:\n\n"
                    f"  {preview}\n\n"
                    "Run the same command with 'confirm' at the end to commit."
                ),
                data={"preview": True},
            )

        sheet = actor.sheet_data
        try:
            endorsement = create_pose_endorsement(sheet, interaction, resonance)
        except EndorsementValidationError as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=(
                f"You endorse the pose for {resonance.name}. It will count toward the weekly pot."
            ),
            data={"endorsement": endorsement},
        )


@dataclass
class SceneEntryEndorseAction(Action):
    """Endorse a peer's scene-entry pose for an immediate flat resonance grant.

    kwargs:
        endorsee_sheet: CharacterSheet — whose entry to endorse
        scene: Scene — the scene containing the entry pose
        resonance: Resonance — which resonance to award
    """

    key: str = "endorse_scene_entry"
    name: str = "Endorse Scene Entry"
    icon: str = "door-open"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.magic.exceptions import EndorsementValidationError  # noqa: PLC0415
        from world.magic.services.gain import create_scene_entry_endorsement  # noqa: PLC0415

        endorsee_sheet = kwargs.get("endorsee_sheet")
        scene = kwargs.get("scene")
        resonance = kwargs.get("resonance")

        if endorsee_sheet is None:
            return ActionResult(success=False, message="Who are you endorsing?")
        if scene is None:
            return ActionResult(success=False, message="Which scene?")
        if resonance is None:
            return ActionResult(success=False, message="Which resonance?")

        sheet = actor.sheet_data
        try:
            endorsement = create_scene_entry_endorsement(sheet, endorsee_sheet, scene, resonance)
        except EndorsementValidationError as exc:
            return ActionResult(success=False, message=exc.user_message)

        try:
            persona_name = endorsee_sheet.primary_persona.name
        except Exception:  # noqa: BLE001
            persona_name = str(endorsee_sheet)

        return ActionResult(
            success=True,
            message=(
                f"You endorse {persona_name}'s scene entry for {resonance.name}. "
                "The grant fires immediately."
            ),
            data={"endorsement": endorsement},
        )


@dataclass
class StylePresentationEndorseAction(Action):
    """Endorse a peer's outfit / motif presentation for an immediate flat resonance grant.

    kwargs:
        endorsee_sheet: CharacterSheet — whose style to endorse
        scene: Scene — the scene context
        resonance: Resonance — which resonance to award
    """

    key: str = "endorse_style_presentation"
    name: str = "Endorse Style Presentation"
    icon: str = "star"
    category: str = "magic"
    target_type: TargetType = TargetType.SELF

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.magic.exceptions import EndorsementValidationError  # noqa: PLC0415
        from world.magic.services.gain import (  # noqa: PLC0415
            create_style_presentation_endorsement,
        )

        endorsee_sheet = kwargs.get("endorsee_sheet")
        scene = kwargs.get("scene")
        resonance = kwargs.get("resonance")

        if endorsee_sheet is None:
            return ActionResult(success=False, message="Who are you endorsing?")
        if scene is None:
            return ActionResult(success=False, message="Which scene?")
        if resonance is None:
            return ActionResult(success=False, message="Which resonance?")

        sheet = actor.sheet_data
        try:
            endorsement = create_style_presentation_endorsement(
                sheet, endorsee_sheet, scene, resonance
            )
        except EndorsementValidationError as exc:
            return ActionResult(success=False, message=exc.user_message)

        try:
            persona_name = endorsee_sheet.primary_persona.name
        except Exception:  # noqa: BLE001
            persona_name = str(endorsee_sheet)

        return ActionResult(
            success=True,
            message=(
                f"You endorse {persona_name}'s style presentation for {resonance.name}. "
                "The grant fires immediately."
            ),
            data={"endorsement": endorsement},
        )
