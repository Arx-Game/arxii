"""Relationship-building player actions.

Four Actions converging on the existing relationship services:
first impression, development, capstone, and point redistribution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ObjectDoesNotExist, ValidationError

from actions.base import Action
from actions.prerequisites import HasCharacterSheetPrerequisite, Prerequisite, resolve_actor_sheet
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext


@dataclass
class BaseRelationshipAction(Action):
    """Shared base for relationship-building verbs."""

    target_type: TargetType = TargetType.SINGLE

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCharacterSheetPrerequisite()]

    def _sheet(self, actor: ObjectDB) -> Any:
        return resolve_actor_sheet(actor)

    def _active_scene_for(self, actor: ObjectDB, target_sheet: Any) -> Any:
        from world.scenes.models import Scene  # noqa: PLC0415

        if actor.location is None:
            return None
        try:
            character = target_sheet.character
        except (AttributeError, ObjectDoesNotExist):
            return None
        if character is None or character.location_id != actor.location.id:
            return None
        return Scene.objects.filter(location=actor.location, is_active=True).first()

    def _relationship(self, source: Any, target: Any) -> Any:
        from world.relationships.models import CharacterRelationship  # noqa: PLC0415

        relationship, _ = CharacterRelationship.objects.get_or_create(
            source=source,
            target=target,
            defaults={"is_pending": True},
        )
        return relationship

    def _target_name(self, target_sheet: Any) -> str | None:
        try:
            return target_sheet.character.db_key
        except (AttributeError, ObjectDoesNotExist):
            return None

    def _self_target_error(self, sheet: Any, target_sheet: Any) -> str:
        """Return an error message if the actor targets themselves, else "".

        Mirrors the DB-level ``relationship_source_not_target`` CheckConstraint
        so players get a friendly failure rather than a 500/IntegrityError. The
        verbs describe regard for *another* character — a self-relationship is
        nonsensical and would self-award both author + target XP (#1485).
        """
        if target_sheet is not None and sheet is not None and target_sheet.pk == sheet.pk:
            return "You cannot record a relationship with yourself."
        return ""

    def _resolve_writeup(self, writeup_type: str | None, writeup_id: int | None) -> Any:
        """Resolve a writeup instance from type and id kwargs.

        ``writeup_type`` must be one of ``"update"``, ``"development"``, or ``"capstone"``.
        Raises ``WriteupFeedbackError`` (with a ``user_message``) for unknown types or
        missing rows so callers can convert it to a clean ``ActionResult`` failure.
        """
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        from world.relationships.exceptions import WriteupFeedbackError  # noqa: PLC0415
        from world.relationships.models import (  # noqa: PLC0415
            RelationshipCapstone,
            RelationshipDevelopment,
            RelationshipUpdate,
        )

        _TYPE_MAP: dict[str, Any] = {
            "update": RelationshipUpdate,
            "development": RelationshipDevelopment,
            "capstone": RelationshipCapstone,
        }

        if writeup_type not in _TYPE_MAP:
            msg = "Invalid writeup type."
            raise WriteupFeedbackError(msg)

        model = _TYPE_MAP[writeup_type]
        try:
            return model.objects.get(pk=writeup_id)
        except (ObjectDoesNotExist, model.DoesNotExist, ValueError, TypeError):
            msg = "Writeup not found."
            raise WriteupFeedbackError(msg) from None

    def _preflight_error(self, sheet: Any, target_sheet: Any, **required: Any) -> str:
        """Return the first preflight error for a relationship verb, else "".

        Consolidates the no-sheet / missing-required-kwarg / self-target checks
        into a single message so each ``execute()`` needs one early return
        (keeps PLR0911 under the limit). ``required`` maps kwarg label → value;
        the first ``None`` value yields a "No <label> selected." message.
        """
        if sheet is None:
            return "No active character."
        for label, value in required.items():
            if value is None:
                return f"No {label} selected."
        return self._self_target_error(sheet, target_sheet)


@dataclass
class CreateFirstImpressionAction(BaseRelationshipAction):
    """Record a first impression toward another character."""

    key: str = "create_first_impression"
    name: str = "First Impression"
    icon: str = "sparkles"
    category: str = "relationships"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.relationships.constants import (  # noqa: PLC0415
            FirstImpressionColoring,
            UpdateVisibility,
        )
        from world.relationships.services import create_first_impression  # noqa: PLC0415

        sheet = self._sheet(actor)
        target_sheet = kwargs.get("target_sheet")
        track = kwargs.get("track")
        err = self._preflight_error(sheet, target_sheet, target=target_sheet, track=track)
        if err:
            return ActionResult(success=False, message=err)

        try:
            points = int(kwargs.get("points", 0))
            relationship = create_first_impression(
                source=sheet,
                target=target_sheet,
                title=kwargs.get("title", ""),
                writeup=kwargs.get("writeup", ""),
                track=track,
                points=points,
                coloring=kwargs.get("coloring", FirstImpressionColoring.NEUTRAL),
                visibility=kwargs.get("visibility", UpdateVisibility.PRIVATE),
                linked_scene=self._active_scene_for(actor, target_sheet),
            )
        except (TypeError, ValueError):
            return ActionResult(success=False, message="Invalid points value.")
        except ValidationError as exc:
            return ActionResult(success=False, message=str(exc))

        target_name = self._target_name(target_sheet)
        return ActionResult(
            success=True,
            message=(
                f"You record a first impression of {target_name}."
                if target_name
                else "You record a first impression."
            ),
            data={"relationship_id": relationship.pk},
        )


@dataclass
class CreateDevelopmentAction(BaseRelationshipAction):
    """Solidify temporary points into permanent developed points."""

    key: str = "create_development"
    name: str = "Develop Relationship"
    icon: str = "trending-up"
    category: str = "relationships"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.relationships.constants import UpdateVisibility  # noqa: PLC0415
        from world.relationships.services import create_development  # noqa: PLC0415

        sheet = self._sheet(actor)
        target_sheet = kwargs.get("target_sheet")
        track = kwargs.get("track")
        err = self._preflight_error(sheet, target_sheet, target=target_sheet, track=track)
        if err:
            return ActionResult(success=False, message=err)

        relationship = self._relationship(sheet, target_sheet)

        try:
            points = int(kwargs.get("points", 0))
        except (TypeError, ValueError):
            return ActionResult(success=False, message="Invalid points value.")

        try:
            xp_awarded = int(kwargs.get("xp_awarded", 0))
        except (TypeError, ValueError):
            return ActionResult(success=False, message="Invalid xp value.")

        try:
            development = create_development(
                relationship=relationship,
                author=sheet,
                title=kwargs.get("title", ""),
                writeup=kwargs.get("writeup", ""),
                track=track,
                points=points,
                xp_awarded=xp_awarded,
                visibility=kwargs.get("visibility", UpdateVisibility.PRIVATE),
                linked_scene=self._active_scene_for(actor, target_sheet),
            )
        except ValidationError as exc:
            return ActionResult(success=False, message=str(exc))

        target_name = self._target_name(target_sheet)
        return ActionResult(
            success=True,
            message=(
                f"You develop your regard for {target_name} "
                f"({development.points_earned} points on {track.name})."
                if target_name
                else f"You develop your regard "
                f"({development.points_earned} points on {track.name})."
            ),
            data={"development_id": development.pk},
        )


@dataclass
class CreateCapstoneAction(BaseRelationshipAction):
    """Record a monumental relationship capstone."""

    key: str = "create_capstone"
    name: str = "Relationship Capstone"
    icon: str = "crown"
    category: str = "relationships"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.relationships.constants import UpdateVisibility  # noqa: PLC0415
        from world.relationships.services import create_capstone  # noqa: PLC0415

        sheet = self._sheet(actor)
        target_sheet = kwargs.get("target_sheet")
        track = kwargs.get("track")
        err = self._preflight_error(sheet, target_sheet, target=target_sheet, track=track)
        if err:
            return ActionResult(success=False, message=err)

        relationship = self._relationship(sheet, target_sheet)

        try:
            points = int(kwargs.get("points", 0))
        except (TypeError, ValueError):
            return ActionResult(success=False, message="Invalid points value.")

        try:
            capstone = create_capstone(
                relationship=relationship,
                author=sheet,
                title=kwargs.get("title", ""),
                writeup=kwargs.get("writeup", ""),
                track=track,
                points=points,
                visibility=kwargs.get("visibility", UpdateVisibility.SHARED),
                linked_scene=self._active_scene_for(actor, target_sheet),
            )
        except ValidationError as exc:
            return ActionResult(success=False, message=str(exc))

        target_name = self._target_name(target_sheet)
        return ActionResult(
            success=True,
            message=(
                f"You mark a capstone in your regard for {target_name} ({track.name})."
                if target_name
                else f"You mark a capstone in your regard ({track.name})."
            ),
            data={"capstone_id": capstone.pk},
        )


@dataclass
class RedistributePointsAction(BaseRelationshipAction):
    """Move developed points between tracks in an existing relationship."""

    key: str = "redistribute_points"
    name: str = "Redistribute Relationship Points"
    icon: str = "shuffle"
    category: str = "relationships"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.relationships.constants import UpdateVisibility  # noqa: PLC0415
        from world.relationships.services import redistribute_points  # noqa: PLC0415

        sheet = self._sheet(actor)
        target_sheet = kwargs.get("target_sheet")
        source_track = kwargs.get("source_track")
        target_track = kwargs.get("target_track")
        err = self._preflight_error(
            sheet,
            target_sheet,
            target=target_sheet,
            **{"source track": source_track, "target track": target_track},
        )
        if err:
            return ActionResult(success=False, message=err)

        relationship = self._relationship(sheet, target_sheet)

        try:
            points = int(kwargs.get("points", 0))
        except (TypeError, ValueError):
            return ActionResult(success=False, message="Invalid points value.")

        try:
            change = redistribute_points(
                relationship=relationship,
                author=sheet,
                title=kwargs.get("title", ""),
                writeup=kwargs.get("writeup", ""),
                source_track=source_track,
                target_track=target_track,
                points=points,
                visibility=kwargs.get("visibility", UpdateVisibility.PRIVATE),
            )
        except ValidationError as exc:
            return ActionResult(success=False, message=str(exc))

        target_name = self._target_name(target_sheet)
        return ActionResult(
            success=True,
            message=(
                f"You shift {change.points_moved} points from "
                f"{change.source_track.name} to {change.target_track.name} "
                f"regarding {target_name}."
                if target_name
                else f"You shift {change.points_moved} points from "
                f"{change.source_track.name} to {change.target_track.name}."
            ),
            data={"change_id": change.pk},
        )


@dataclass
class GiveWriteupKudosAction(BaseRelationshipAction):
    """Commend a shared/public relationship writeup on behalf of its subject."""

    key: str = "give_writeup_kudos"
    name: str = "Commend Writeup"
    icon: str = "heart"
    category: str = "relationships"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.relationships.exceptions import WriteupFeedbackError  # noqa: PLC0415
        from world.relationships.services import give_writeup_kudos  # noqa: PLC0415
        from world.roster.selectors import get_account_for_character  # noqa: PLC0415

        writeup_type = kwargs.get("writeup_type")
        writeup_id = kwargs.get("writeup_id")

        if not writeup_type or writeup_id is None:
            return ActionResult(success=False, message="No writeup selected.")

        try:
            writeup = self._resolve_writeup(writeup_type, writeup_id)
        except WriteupFeedbackError as exc:
            return ActionResult(success=False, message=exc.user_message)

        giver_account = get_account_for_character(actor)
        if giver_account is None:
            return ActionResult(success=False, message="No account found for your character.")

        try:
            kudos = give_writeup_kudos(giver_account=giver_account, writeup=writeup)
        except WriteupFeedbackError as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message="You commend the writeup.",
            data={"kudos_id": kudos.pk},
        )


@dataclass
class FileWriteupComplaintAction(BaseRelationshipAction):
    """File a bad-faith-RP complaint against a relationship writeup for staff triage."""

    key: str = "file_writeup_complaint"
    name: str = "File Writeup Complaint"
    icon: str = "flag"
    category: str = "relationships"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.relationships.exceptions import WriteupFeedbackError  # noqa: PLC0415
        from world.relationships.services import file_writeup_complaint  # noqa: PLC0415
        from world.roster.selectors import get_account_for_character  # noqa: PLC0415

        writeup_type = kwargs.get("writeup_type")
        writeup_id = kwargs.get("writeup_id")
        reason = kwargs.get("reason") or ""

        if not reason:
            return ActionResult(success=False, message="No reason provided.")

        if not writeup_type or writeup_id is None:
            return ActionResult(success=False, message="No writeup selected.")

        try:
            writeup = self._resolve_writeup(writeup_type, writeup_id)
        except WriteupFeedbackError as exc:
            return ActionResult(success=False, message=exc.user_message)

        complainant_account = get_account_for_character(actor)
        if complainant_account is None:
            return ActionResult(success=False, message="No account found for your character.")

        try:
            complaint = file_writeup_complaint(
                complainant_account=complainant_account,
                writeup=writeup,
                reason=reason,
            )
        except WriteupFeedbackError as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message="Your complaint has been filed for staff review.",
            data={"complaint_id": complaint.pk},
        )
