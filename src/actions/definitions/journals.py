"""Journal authoring actions — create, respond, edit (#1350).

Thin REGISTRY Actions over the existing ``world.journals.services`` write
functions, so both the web ViewSet and the telnet ``CmdJournal`` converge on
``action.run()`` (ADR-0001).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ObjectDoesNotExist

from actions.base import Action
from actions.prerequisites import Prerequisite
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext


@dataclass
class _HasCharacterSheetPrerequisite(Prerequisite):
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
class _BaseJournalAction(Action):
    """Shared base: sheet resolution + sheet-required prerequisite."""

    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [_HasCharacterSheetPrerequisite()]

    @staticmethod
    def _sheet(actor: ObjectDB) -> Any:
        try:
            return actor.sheet_data
        except (AttributeError, ObjectDoesNotExist):
            return None


@dataclass
class CreateJournalEntryAction(_BaseJournalAction):
    """Write a new journal entry (optionally public, with tags)."""

    key: str = "create_journal_entry"
    name: str = "Write Journal Entry"
    icon: str = "feather"
    category: str = "journals"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.journals.services import create_journal_entry  # noqa: PLC0415

        sheet = self._sheet(actor)
        if sheet is None:
            return ActionResult(success=False, message="No active character.")

        entry = create_journal_entry(
            author=sheet,
            title=kwargs.get("title", ""),
            body=kwargs.get("body", ""),
            is_public=bool(kwargs.get("is_public", False)),
            tags=kwargs.get("tags"),
        )
        return ActionResult(
            success=True,
            message=f"You write a new journal entry: {entry.title}.",
            data={"entry_id": entry.pk},
        )


@dataclass
class RespondToJournalAction(_BaseJournalAction):
    """Praise or retort another character's public journal entry."""

    key: str = "respond_to_journal"
    name: str = "Respond to Journal"
    icon: str = "message-circle"
    category: str = "journals"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.journals.constants import ResponseType  # noqa: PLC0415
        from world.journals.models import JournalEntry  # noqa: PLC0415
        from world.journals.services import create_journal_response  # noqa: PLC0415
        from world.journals.types import JournalError  # noqa: PLC0415

        sheet = self._sheet(actor)
        if sheet is None:
            return ActionResult(success=False, message="No active character.")

        parent = kwargs.get("parent")
        parent_id = kwargs.get("parent_id")
        response_type = kwargs.get("response_type")
        if isinstance(parent, JournalEntry):
            pass
        elif parent_id is not None:
            try:
                parent = JournalEntry.objects.get(pk=parent_id)
            except JournalEntry.DoesNotExist:
                return ActionResult(success=False, message="That journal entry was not found.")
        else:
            return ActionResult(success=False, message="No journal entry selected.")
        if response_type not in ResponseType.values:
            return ActionResult(
                success=False,
                message="response_type must be praise or retort.",
            )

        try:
            response_entry = create_journal_response(
                author=sheet,
                parent=parent,
                response_type=response_type,
                title=kwargs.get("title", ""),
                body=kwargs.get("body", ""),
            )
        except JournalError as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=f"You respond to '{parent.title}' with {response_type}.",
            data={"entry_id": response_entry.pk},
        )


@dataclass
class EditJournalEntryAction(_BaseJournalAction):
    """Edit the title and/or body of one of the actor's own entries."""

    key: str = "edit_journal_entry"
    name: str = "Edit Journal Entry"
    icon: str = "edit-3"
    category: str = "journals"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.journals.models import JournalEntry  # noqa: PLC0415
        from world.journals.services import edit_journal_entry  # noqa: PLC0415
        from world.journals.types import JournalError  # noqa: PLC0415

        sheet = self._sheet(actor)
        if sheet is None:
            return ActionResult(success=False, message="No active character.")

        entry = kwargs.get("entry")
        entry_id = kwargs.get("entry_id")
        if isinstance(entry, JournalEntry):
            if entry.author_id != sheet.pk:
                return ActionResult(success=False, message="That journal entry was not found.")
        elif entry_id is not None:
            try:
                entry = JournalEntry.objects.get(pk=entry_id, author_id=sheet.pk)
            except JournalEntry.DoesNotExist:
                return ActionResult(success=False, message="That journal entry was not found.")
        else:
            return ActionResult(success=False, message="No journal entry selected.")

        try:
            updated = edit_journal_entry(
                entry=entry,
                title=kwargs.get("title"),
                body=kwargs.get("body"),
            )
        except JournalError as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=f"You revise '{updated.title}'.",
            data={"entry_id": updated.pk},
        )
