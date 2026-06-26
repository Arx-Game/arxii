"""Relationship-building player actions.

Four Actions converging on the existing relationship services:
first impression, development, capstone, and point redistribution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ObjectDoesNotExist, ValidationError

from actions.base import Action
from actions.prerequisites import Prerequisite
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext


@dataclass
class HasCharacterSheetPrerequisite(Prerequisite):
    """Actor must have a CharacterSheet."""

    def is_met(
        self,
        actor: ObjectDB,
        target: ObjectDB | None = None,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        try:
            actor.sheet_data  # noqa: B018
        except (AttributeError, ObjectDoesNotExist):
            return False, "No active character."
        return True, ""


@dataclass
class BaseRelationshipAction(Action):
    """Shared base for relationship-building verbs."""

    target_type: TargetType = TargetType.SINGLE

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCharacterSheetPrerequisite()]

    def _sheet(self, actor: ObjectDB) -> Any:
        from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

        try:
            return actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return None

    def _resolve_target_sheet(self, actor: ObjectDB, target_name_or_id: str) -> Any:
        from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

        sheet = self._sheet(actor)
        if sheet is None:
            return None, "No active character."

        value = target_name_or_id.strip()
        qs = CharacterSheet.objects.select_related("character")
        if value.isdigit():
            target_sheet = qs.filter(pk=int(value)).first()
        else:
            target_sheet = qs.filter(character__db_key__iexact=value).first()
        if target_sheet is None:
            return None, f"Could not find '{value}'."
        if target_sheet == sheet:
            return None, "You cannot target yourself."
        return target_sheet, ""

    def _resolve_track(self, track_name_or_id: str) -> Any:
        from world.relationships.models import RelationshipTrack  # noqa: PLC0415

        value = track_name_or_id.strip()
        qs = RelationshipTrack.objects.all()
        if value.isdigit():
            return qs.filter(pk=int(value)).first()
        return qs.filter(name__iexact=value).first()

    def _active_scene_for(self, actor: ObjectDB, target_sheet: Any) -> Any:
        from world.scenes.models import Scene  # noqa: PLC0415

        if actor.location is None:
            return None
        if target_sheet.character.location_id != actor.location.id:
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
        if sheet is None:
            return ActionResult(success=False, message="No active character.")

        target_sheet = kwargs.get("target_sheet")
        track = kwargs.get("track")
        missing = (
            "No target selected."
            if target_sheet is None
            else "No track selected."
            if track is None
            else ""
        )
        if missing:
            return ActionResult(success=False, message=missing)

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

        return ActionResult(
            success=True,
            message=f"You record a first impression of {target_sheet.character.db_key}.",
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
        if sheet is None:
            return ActionResult(success=False, message="No active character.")

        target_sheet = kwargs.get("target_sheet")
        track = kwargs.get("track")
        missing = (
            "No target selected."
            if target_sheet is None
            else "No track selected."
            if track is None
            else ""
        )
        if missing:
            return ActionResult(success=False, message=missing)

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

        return ActionResult(
            success=True,
            message=(
                f"You develop your regard for {target_sheet.character.db_key} "
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
        if sheet is None:
            return ActionResult(success=False, message="No active character.")

        target_sheet = kwargs.get("target_sheet")
        track = kwargs.get("track")
        missing = (
            "No target selected."
            if target_sheet is None
            else "No track selected."
            if track is None
            else ""
        )
        if missing:
            return ActionResult(success=False, message=missing)

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

        return ActionResult(
            success=True,
            message=(
                f"You mark a capstone in your regard for "
                f"{target_sheet.character.db_key} ({track.name})."
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
        if sheet is None:
            return ActionResult(success=False, message="No active character.")

        target_sheet = kwargs.get("target_sheet")
        source_track = kwargs.get("source_track")
        target_track = kwargs.get("target_track")
        relationship = self._relationship(sheet, target_sheet)
        missing = (
            "No target selected."
            if target_sheet is None
            else "No source track selected."
            if source_track is None
            else "No target track selected."
            if target_track is None
            else ""
        )
        if missing:
            return ActionResult(success=False, message=missing)

        try:
            points = int(kwargs.get("points", 0))
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
        except (TypeError, ValueError):
            return ActionResult(success=False, message="Invalid points value.")
        except ValidationError as exc:
            return ActionResult(success=False, message=str(exc))

        return ActionResult(
            success=True,
            message=(
                f"You shift {change.points_moved} points from "
                f"{change.source_track.name} to {change.target_track.name} "
                f"regarding {target_sheet.character.db_key}."
            ),
            data={"change_id": change.pk},
        )
