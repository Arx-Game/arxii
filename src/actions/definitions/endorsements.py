"""Actions for resonance-gain endorsements (Spec C §2.2 / §2.3 / #1152, #1340)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ObjectDoesNotExist

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
      endorser can confirm they have the right one. No DB row is written. A pick on a pose
      that named no resonance (#5327) skips the preview: it only waits for the poser and is
      easy to change or withdraw.
    - ``confirm=True``: commit — creates the PoseEndorsement row.

    kwargs:
        interaction: Interaction — the pose to endorse
        resonance: Resonance — which resonance to award; optional when the pose's author
            reached for one (#5308), which is then the resonance awarded
        confirm: bool — False = preview, True = commit (default False)
        pose_number: int | None — the pose's number as ``poses`` lists it, for the reply line
        change_pick: bool — when True and the endorser already has a pick waiting for the poser
            on this pose, change it to ``resonance`` instead of refusing (telnet sets it)

    On a pose that named no resonance the pick waits for the poser to accept it (#5327), and
    the reply says it pays only if she does.
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
        reach = interaction.cached_resonance_reach
        if reach is not None:
            resonance = reach.resonance
        if resonance is None:
            return ActionResult(
                success=False,
                message="Which resonance? (endorse pose <char> resonance=<name>)",
            )

        # A pick on a pose that named no resonance only waits for the poser, and typing the
        # command again with another resonance changes it, so it commits without a preview.
        waits_for_poser = interaction.cached_resonance_reach is None
        if not confirm and not waits_for_poser:
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
        number = kwargs.get("pose_number")
        if kwargs.get("change_pick"):
            changed = self._change_waiting_pick(sheet, interaction, resonance, number)
            if changed is not None:
                return changed
        try:
            endorsement = create_pose_endorsement(sheet, interaction, resonance)
        except EndorsementValidationError as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=self._endorsed_line(endorsement, number),
            data={"endorsement": endorsement},
        )

    @staticmethod
    def _poser_name(interaction: Any) -> str:
        return interaction.persona.name if interaction.persona else "the poser"

    @staticmethod
    def _pose_words(who: str, number: int | None) -> str:
        """ "Brannoc's pose #1", or "Brannoc's pose" when no number is known."""
        return f"{who}'s pose" if number is None else f"{who}'s pose #{number}"

    def _endorsed_line(self, endorsement: Any, number: int | None) -> str:
        """What the endorser reads. A pick that waits for the poser says it pays only if she
        accepts; one on a pose that named its own resonance counts toward the weekly pot."""
        resonance = endorsement.resonance
        if not endorsement.awaiting_acceptance:
            return (
                f"You endorse the pose for {resonance.name}. It will count toward the weekly pot."
            )
        who = self._poser_name(endorsement.interaction)
        return (
            f"You endorse {self._pose_words(who, number)} with {resonance.name}. "
            f"It pays only if {who} accepts."
        )

    def _change_waiting_pick(
        self, sheet: Any, interaction: Any, resonance: Any, number: int | None
    ) -> ActionResult | None:
        """Change the pick this endorser already made on the pose, when one waits for the poser.

        Typing the endorse command again with another resonance swaps the pick. None when she
        has no waiting pick on the pose, so the caller endorses as usual (and a confirmed
        endorsement answers "Already endorsed this pose").
        """
        from world.magic.exceptions import EndorsementValidationError  # noqa: PLC0415
        from world.magic.models import PoseEndorsement  # noqa: PLC0415
        from world.magic.services.gain import (  # noqa: PLC0415
            change_pose_endorsement,
            player_of_sheet,
        )

        existing = PoseEndorsement.objects.filter(
            endorser_sheet=sheet,
            interaction=interaction,
            awaiting_acceptance=True,
            settled_at__isnull=True,
        ).first()
        if existing is None:
            return None
        before = existing.resonance
        who = self._poser_name(interaction)
        if before.pk == resonance.pk:
            return ActionResult(
                success=True,
                message=(
                    f"Your pick on {self._pose_words(who, number)} is already {resonance.name}. "
                    f"It pays only if {who} accepts."
                ),
                data={"endorsement": existing},
            )
        account = player_of_sheet(sheet)
        try:
            changed = change_pose_endorsement(existing, resonance, account)
        except EndorsementValidationError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=(
                f"You change your pick on {self._pose_words(who, number)} from {before.name} "
                f"to {resonance.name}. It pays only if {who} accepts."
            ),
            data={"endorsement": changed},
        )


@dataclass
class AnswerPoseProposalAction(Action):
    """Accept or decline the resonance a witness proposed on a pose (#5327).

    The poser, the scene's GM and staff may answer. Accepting lets the weekly settlement pay the
    pick; declining deletes it, and it pays nothing. Telnet reaches this through
    ``endorse accept`` and ``endorse decline``.

    kwargs:
        endorsement: PoseEndorsement -- the waiting pick
        accept: bool -- True to accept, False to decline
        pose_number: int | None -- the pose's number as ``poses`` lists it, for the reply line
    """

    key: str = "answer_pose_proposal"
    name: str = "Answer Pose Proposal"
    icon: str = "check"
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
            accept_pose_proposal,
            decline_pose_proposal,
            player_of_sheet,
        )
        from world.magic.services.kindling import shown_names  # noqa: PLC0415

        endorsement = kwargs.get("endorsement")
        if endorsement is None:
            return ActionResult(success=False, message="Which proposal? (endorse accept <char> #N)")
        sheet = actor.sheet_data
        account = player_of_sheet(sheet)
        if account is None:
            return ActionResult(success=False, message="You need a player to answer a proposal.")
        resonance = endorsement.resonance
        witness = shown_names(sheet, [endorsement.endorser_sheet_id]).get(
            endorsement.endorser_sheet_id, "Someone"
        )
        number = kwargs.get("pose_number")
        pose = "your pose" if number is None else f"your pose #{number}"
        try:
            if kwargs.get("accept"):
                answered = accept_pose_proposal(endorsement, account)
            else:
                decline_pose_proposal(endorsement, account)
                answered = None
        except EndorsementValidationError as exc:
            return ActionResult(success=False, message=exc.user_message)
        if answered is not None:
            return ActionResult(
                success=True,
                message=(
                    f"You accept {witness}'s {resonance.name} on {pose}. "
                    "It pays at the weekly settlement."
                ),
                data={"endorsement": answered},
            )
        return ActionResult(
            success=True,
            message=f"You decline {witness}'s {resonance.name} on {pose}. It pays nothing.",
        )


@dataclass
class WithdrawPoseEndorsementAction(Action):
    """Take back an endorsement of one's own pose pick before the weekly settlement pays it
    (#5327). Telnet reaches this through ``endorse withdraw``; the web uses DELETE on the
    endorsement.

    kwargs:
        endorsement: PoseEndorsement -- the endorsement to take back
        pose_number: int | None -- the pose's number as ``poses`` lists it, for the reply line
    """

    key: str = "withdraw_pose_endorsement"
    name: str = "Withdraw Pose Endorsement"
    icon: str = "undo"
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
            player_of_sheet,
            withdraw_pose_endorsement,
        )

        endorsement = kwargs.get("endorsement")
        if endorsement is None:
            return ActionResult(
                success=False, message="Which endorsement? (endorse withdraw <char> [#N])"
            )
        account = player_of_sheet(actor.sheet_data)
        if account is None:
            return ActionResult(success=False, message="You need a player to withdraw a pick.")
        interaction = endorsement.interaction
        who = interaction.persona.name if interaction.persona else "the poser"
        number = kwargs.get("pose_number")
        pose = f"{who}'s pose" if number is None else f"{who}'s pose #{number}"
        resonance = endorsement.resonance
        try:
            withdraw_pose_endorsement(endorsement, account)
        except EndorsementValidationError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=f"You withdraw your {resonance.name} endorsement of {pose}.",
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
        except ObjectDoesNotExist:
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
        except ObjectDoesNotExist:
            persona_name = str(endorsee_sheet)

        return ActionResult(
            success=True,
            message=(
                f"You endorse {persona_name}'s style presentation for {resonance.name}. "
                "The grant fires immediately."
            ),
            data={"endorsement": endorsement},
        )
