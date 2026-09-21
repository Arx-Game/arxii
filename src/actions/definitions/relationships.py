"""Tie actions (#3957): declare, shift, end, reveal, AP, advance, summary.

Seven Actions converging on ``world.relationships.services`` — the one seam
telnet and the web share (``action.run()``). Plus ``RelationshipBumpAction``,
the ambient +/-1 nudge (#1699), unchanged apart from the service it calls.
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
    from world.relationships.exceptions import TieError


@dataclass
class BaseRelationshipAction(Action):
    """Shared base for tie-building verbs."""

    target_type: TargetType = TargetType.SINGLE

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCharacterSheetPrerequisite()]

    def _sheet(self, actor: ObjectDB) -> Any:
        return resolve_actor_sheet(actor)

    def _relationship(self, source: Any, target: Any, target_companion: Any = None) -> Any:
        from world.relationships.services import get_or_create_side  # noqa: PLC0415

        return get_or_create_side(source=source, target=target, target_companion=target_companion)

    def _target_name(self, target_sheet: Any, target_companion: Any = None) -> str | None:
        if target_companion is not None:
            return target_companion.name
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

    def _preflight_error(
        self, sheet: Any, target_sheet: Any, target_companion: Any = None, **required: Any
    ) -> str:
        """Return the first preflight error for a tie verb, else "".

        Consolidates the no-sheet / missing-required-kwarg / self-target / companion-
        ownership checks into a single message so each ``execute()`` needs one early
        return (keeps PLR0911 under the limit). ``required`` maps kwarg label to value;
        the first ``None`` value yields a "No <label> selected." message. A companion
        target (#3575) swaps the self-target check for ``companion_target_error``
        (owner-only, not released).
        """
        if sheet is None:
            return "No active character."
        for label, value in required.items():
            if value is None:
                return f"No {label} selected."
        if target_companion is not None:
            from world.relationships.services import companion_target_error  # noqa: PLC0415

            return companion_target_error(sheet, target_companion)
        return self._self_target_error(sheet, target_sheet)


def _tenure_for(sheet: Any) -> Any:
    """The sheet's current roster tenure, or None (consent reads it later)."""
    entry = sheet.roster_entry_or_none
    return entry.current_tenure if entry is not None else None


def _tie_error(exc: TieError) -> ActionResult:
    return ActionResult(success=False, message=exc.user_message)


@dataclass
class DeclareLabelAction(BaseRelationshipAction):
    """Name a type on your side of a tie; Private unless told otherwise (#3957)."""

    key: str = "declare_label"
    name: str = "Declare"
    icon: str = "tag"
    category: str = "relationships"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.relationships.constants import LabelAwareness  # noqa: PLC0415
        from world.relationships.exceptions import TieError  # noqa: PLC0415
        from world.relationships.services import declare_label  # noqa: PLC0415

        sheet = self._sheet(actor)
        target_sheet = kwargs.get("target_sheet")
        target_companion = kwargs.get("target_companion")
        label_type = kwargs.get("type")
        err = self._preflight_error(
            sheet,
            target_sheet,
            target_companion,
            target=target_sheet if target_sheet is not None else target_companion,
            type=label_type,
        )
        if err:
            return ActionResult(success=False, message=err)
        side = self._relationship(sheet, target_sheet, target_companion)
        try:
            label = declare_label(
                side=side,
                type=label_type,
                awareness=kwargs.get("awareness", LabelAwareness.PRIVATE),
                tenure=_tenure_for(sheet),
            )
        except TieError as exc:
            return _tie_error(exc)
        return ActionResult(
            success=True,
            message=f"{label_type.name} declared toward {side.target_name}.",
            data={"relationship_id": side.pk, "label_id": label.pk},
        )


@dataclass
class _LabelRowAction(BaseRelationshipAction):
    """Shared: resolve ``label`` and refuse one the actor does not own."""

    def _own_label(self, actor: ObjectDB, kwargs: dict[str, Any]) -> tuple[Any, Any, str]:
        sheet = self._sheet(actor)
        label = kwargs.get("label")
        if sheet is None:
            return None, None, "No active character."
        if label is None:
            return None, None, "No label selected."
        if label.relationship.source_id != sheet.pk:
            return None, None, "That is not your relationship."
        return sheet, label, ""


@dataclass
class ShiftLabelAction(_LabelRowAction):
    """Change one label into another; the old row ends, the new one remembers it (#3957)."""

    key: str = "shift_label"
    name: str = "Relationship Shift"
    icon: str = "shuffle"
    category: str = "relationships"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.relationships.exceptions import TieError  # noqa: PLC0415
        from world.relationships.services import shift_label  # noqa: PLC0415

        _sheet, label, err = self._own_label(actor, kwargs)
        new_type = kwargs.get("new_type")
        if not err and new_type is None:
            err = "No type selected."
        if err:
            return ActionResult(success=False, message=err)
        try:
            new = shift_label(label=label, new_type=new_type, note=kwargs.get("note", ""))
        except TieError as exc:
            return _tie_error(exc)
        return ActionResult(
            success=True,
            message=f"{label.type.name} becomes {new_type.name}.",
            data={"relationship_id": label.relationship_id, "label_id": new.pk},
        )


@dataclass
class EndLabelAction(_LabelRowAction):
    """End an open label; it shows as former from then on (#3957)."""

    key: str = "end_label"
    name: str = "End"
    icon: str = "minus"
    category: str = "relationships"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.relationships.exceptions import TieError  # noqa: PLC0415
        from world.relationships.services import end_label  # noqa: PLC0415

        _sheet, label, err = self._own_label(actor, kwargs)
        if err:
            return ActionResult(success=False, message=err)
        try:
            end_label(label=label)
        except TieError as exc:
            return _tie_error(exc)
        return ActionResult(
            success=True,
            message=f"{label.type.name} ended.",
            data={"relationship_id": label.relationship_id, "label_id": label.pk},
        )


@dataclass
class AdvanceLabelAwarenessAction(_LabelRowAction):
    """Move a label's awareness forward — never backward (#3957)."""

    key: str = "advance_label_awareness"
    name: str = "Make known"
    icon: str = "eye"
    category: str = "relationships"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.relationships.exceptions import TieError  # noqa: PLC0415
        from world.relationships.services import advance_awareness  # noqa: PLC0415

        _sheet, label, err = self._own_label(actor, kwargs)
        if err:
            return ActionResult(success=False, message=err)
        try:
            advance_awareness(label=label, to=kwargs.get("awareness", ""))
        except TieError as exc:
            return _tie_error(exc)
        return ActionResult(
            success=True,
            message=f"{label.type.name} is now {label.awareness}.",
            data={"relationship_id": label.relationship_id, "label_id": label.pk},
        )


@dataclass
class SetTieAllocationAction(BaseRelationshipAction):
    """Set this week's AP toward one side of a tie (#3957)."""

    key: str = "set_tie_allocation"
    name: str = "AP this week"
    icon: str = "clock"
    category: str = "relationships"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.relationships.exceptions import TieError  # noqa: PLC0415
        from world.relationships.services import set_allocation  # noqa: PLC0415

        sheet = self._sheet(actor)
        target_sheet = kwargs.get("target_sheet")
        target_companion = kwargs.get("target_companion")
        err = self._preflight_error(
            sheet,
            target_sheet,
            target_companion,
            target=target_sheet if target_sheet is not None else target_companion,
        )
        if err:
            return ActionResult(success=False, message=err)
        try:
            ap_amount = int(kwargs.get("ap_amount", 0))
        except (TypeError, ValueError):
            return ActionResult(success=False, message="Invalid AP value.")
        side = self._relationship(sheet, target_sheet, target_companion)
        try:
            set_allocation(side=side, ap_amount=ap_amount)
        except TieError as exc:
            return _tie_error(exc)
        return ActionResult(
            success=True,
            message=f"{ap_amount} AP this week toward {side.target_name}.",
            data={"relationship_id": side.pk},
        )


@dataclass
class AdvanceRelationshipTierAction(BaseRelationshipAction):
    """Claim the next tier with a capstone journal entry and XP (#3957)."""

    key: str = "advance_relationship_tier"
    name: str = "Advance Relationship Tier"
    icon: str = "crown"
    category: str = "relationships"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.progression.exceptions import InsufficientXPError  # noqa: PLC0415
        from world.relationships.exceptions import TieError  # noqa: PLC0415
        from world.relationships.services import advance_tier  # noqa: PLC0415

        sheet = self._sheet(actor)
        target_sheet = kwargs.get("target_sheet")
        entry = kwargs.get("journal_entry")
        err = self._preflight_error(
            sheet, target_sheet, None, target=target_sheet, journal_entry=entry
        )
        if err:
            return ActionResult(success=False, message=err)
        side = self._relationship(sheet, target_sheet, None)
        try:
            receipt = advance_tier(side=side, journal_entry=entry)
        except TieError as exc:
            return _tie_error(exc)
        except InsufficientXPError as exc:
            return ActionResult(
                success=False,
                message=f"Not enough XP: {exc.required} needed, {exc.available} available.",
            )
        return ActionResult(
            success=True,
            message=f"Tier {receipt.tier_claimed} with {side.target_name}.",
            data={
                "relationship_id": side.pk,
                "capstone_id": receipt.pk,
                "tier": receipt.tier_claimed,
            },
        )


@dataclass
class SetTieSummaryAction(BaseRelationshipAction):
    """Set the player's own paragraph on one side of a tie (#3957)."""

    key: str = "set_tie_summary"
    name: str = "Summary"
    icon: str = "pen"
    category: str = "relationships"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.relationships.services import set_summary  # noqa: PLC0415

        sheet = self._sheet(actor)
        target_sheet = kwargs.get("target_sheet")
        target_companion = kwargs.get("target_companion")
        err = self._preflight_error(
            sheet,
            target_sheet,
            target_companion,
            target=target_sheet if target_sheet is not None else target_companion,
        )
        if err:
            return ActionResult(success=False, message=err)
        side = self._relationship(sheet, target_sheet, target_companion)
        set_summary(side=side, summary=str(kwargs.get("summary", "")))
        return ActionResult(
            success=True, message="Summary saved.", data={"relationship_id": side.pk}
        )


@dataclass
class RelationshipBumpAction(BaseRelationshipAction):
    """Ambient one-keystroke regard nudge, anchored to a specific pose (#1699).

    Telnet passes no ``interaction`` — the action backfill-anchors to the
    target's most recent visible pose in the active scene lacking a bump from
    this relationship. The web door passes the reacted-to ``interaction``
    explicitly. Not consent-gated: a bump is a private write to the actor's
    own relationship data (ADR-0024).
    """

    key: str = "relationship_bump"
    name: str = "Relationship Bump"
    icon: str = "thumbs-up"
    category: str = "relationships"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.relationships.exceptions import RelationshipBumpError  # noqa: PLC0415
        from world.relationships.services import apply_relationship_bump  # noqa: PLC0415

        sheet = self._sheet(actor)
        target_sheet = kwargs.get("target_sheet")
        err = self._preflight_error(sheet, target_sheet, target=target_sheet)
        if not err:
            err = self._self_target_error(sheet, target_sheet)
        if err:
            return ActionResult(success=False, message=err)

        try:
            valence = 1 if int(kwargs.get("valence", 0)) > 0 else -1
        except (TypeError, ValueError):
            return ActionResult(success=False, message="Invalid valence value.")

        interaction = kwargs.get("interaction")
        if interaction is None:
            interaction = self._backfill_anchor(actor, sheet, target_sheet)
            if interaction is None:
                return ActionResult(
                    success=False,
                    message="You've already acknowledged everything they've done this scene.",
                )

        try:
            apply_relationship_bump(
                source=sheet,
                target=target_sheet,
                interaction=interaction,
                valence=valence,
                source_emoji=kwargs.get("source_emoji"),
            )
        except RelationshipBumpError as exc:
            return ActionResult(success=False, message=exc.user_message)
        except ValidationError as exc:
            return ActionResult(success=False, message=str(exc))

        target_name = self._target_name(target_sheet)
        direction = "warms" if valence > 0 else "cools"
        return ActionResult(
            success=True,
            message=(
                f"Your regard for {target_name} {direction}."
                if target_name
                else f"Your regard {direction}."
            ),
        )

    def _backfill_anchor(self, actor: ObjectDB, sheet: Any, target_sheet: Any) -> Any:
        """The target's most recent visible pose in the active scene without a bump from us."""
        from world.magic.services.gain import get_endorseable_poses_in_scene  # noqa: PLC0415
        from world.relationships.models import (  # noqa: PLC0415
            CharacterRelationship,
            RelationshipBump,
        )
        from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

        location = actor.location
        scene = get_active_scene(location) if location is not None else None
        if scene is None:
            return None
        poses = get_endorseable_poses_in_scene(sheet, target_sheet, scene)
        if not poses:
            return None
        relationship = CharacterRelationship.objects.filter(
            source=sheet, target=target_sheet
        ).first()
        bumped_ids: set[int] = set()
        if relationship is not None:
            bumped_ids = set(
                RelationshipBump.objects.filter(
                    relationship=relationship,
                    interaction_id__in=[interaction.pk for _, interaction in poses],
                ).values_list("interaction_id", flat=True)
            )
        for _, interaction in reversed(poses):
            if interaction.pk not in bumped_ids:
                return interaction
        return None
