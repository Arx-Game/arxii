"""Journal authoring actions — create, respond, edit (#1350).

Thin REGISTRY Actions over the existing ``world.journals.services`` write
functions, so both the web ViewSet and the telnet ``CmdJournal`` converge on
``action.run()`` (ADR-0001).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.db import transaction

from actions.base import Action
from actions.prerequisites import HasCharacterSheetPrerequisite, Prerequisite, resolve_actor_sheet
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext
    from world.character_sheets.models import CharacterSheet
    from world.journals.models import JournalEntry
    from world.magic.types.marking import PendingMark


_MSG_NO_ACTIVE_CHARACTER = "No active character."
_MSG_ENTRY_NOT_FOUND = "That journal entry was not found."
_MSG_INVALID_DISPOSITION = "disposition must be reveal or seal."
_MSG_INVALID_OVERRIDE = "override must be inherit, reveal, or seal."
_MSG_ABOUT_NOT_FOUND = "That character was not found."
_MSG_INVALID_CONSENT = "consent must be rivals or anyone."
_MSG_MARK_NEEDS_ACT = (
    "A journal entry marks an act. Choose the act this entry is about, or leave the resonance out."
)


def _resolve_about(about_id: Any) -> tuple[Any, str | None]:
    """Resolve an ``about_id`` kwarg to a CharacterSheet, or an error message."""
    from world.character_sheets.models import CharacterSheet  # noqa: PLC0415

    if about_id is None:
        return None, None
    try:
        return CharacterSheet.objects.get(pk=int(about_id)), None
    except (CharacterSheet.DoesNotExist, TypeError, ValueError):
        return None, _MSG_ABOUT_NOT_FOUND


@dataclass
class _BaseJournalAction(Action):
    """Shared base: sheet resolution + sheet-required prerequisite."""

    target_type: TargetType = TargetType.SELF

    def get_prerequisites(self) -> list[Prerequisite]:
        return [HasCharacterSheetPrerequisite()]

    @staticmethod
    def _sheet(actor: ObjectDB) -> Any:
        return resolve_actor_sheet(actor)


def _record_journal_mark(
    sheet: CharacterSheet, pending_mark: PendingMark, entry: JournalEntry
) -> tuple[str, bool]:
    """Pay the mark a journal entry carries, as ``(line, paid)``.

    A mark refused late (the week's table at 0 percent, a worn payer) is not an error for the
    entry: its refusal line comes back with ``paid`` false and the act stays pointable.
    """
    from world.magic.exceptions import MarkError  # noqa: PLC0415
    from world.magic.services.marking import record_pending_mark  # noqa: PLC0415

    try:
        result = record_pending_mark(sheet, pending_mark, journal_entry=entry)
    except MarkError as exc:
        return exc.user_message, False
    return result.line, result.paid


@dataclass
class CreateJournalEntryAction(_BaseJournalAction):
    """Write a new journal entry (optionally public, with tags).

    A reflection (#5124) rides with it: ``reflect_choice`` and one target. A mark (#5327) rides
    with it too: ``reach_act_id`` (one of the writer's recorded acts) and ``reach_resonance_id``,
    both needed, since a journal entry marks an act and has no bare reach. Both are checked
    before the entry is written and recorded in the same transaction as it. A reflection that
    fails late takes the entry back with it; a mark that is refused late does not: the entry
    stays, the act stays pointable and the refusal comes back in ``mark_line`` with
    ``mark_recorded`` false.
    """

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
        from world.journals.constants import PosthumousOverride  # noqa: PLC0415
        from world.journals.services import create_journal_entry  # noqa: PLC0415
        from world.magic.exceptions import MarkError, ReflectionError  # noqa: PLC0415
        from world.magic.services.marking import pending_mark_from  # noqa: PLC0415
        from world.magic.services.reflection import (  # noqa: PLC0415
            pending_reflection_from,
            record_pending_reflection,
            recorded_line,
        )

        sheet = self._sheet(actor)
        if sheet is None:
            return ActionResult(success=False, message=_MSG_NO_ACTIVE_CHARACTER)

        posthumous_override = kwargs.get("posthumous_override", PosthumousOverride.INHERIT)
        if posthumous_override not in PosthumousOverride.values:
            return ActionResult(success=False, message=_MSG_INVALID_OVERRIDE)

        about, error = _resolve_about(kwargs.get("about_id"))
        if error is not None:
            return ActionResult(success=False, message=error)

        # A reflection (#5124) is checked before the entry is written, so a refused one costs
        # the writer nothing.
        try:
            pending = pending_reflection_from(sheet, kwargs)
        except ReflectionError as exc:
            return ActionResult(success=False, message=exc.user_message)

        # A mark (#5327) is checked the same way. A journal entry marks an act, so a resonance
        # with no act is refused here.
        if kwargs.get("reach_act_id") is None and kwargs.get("reach_resonance_id") is not None:
            return ActionResult(success=False, message=_MSG_MARK_NEEDS_ACT)
        try:
            pending_mark = pending_mark_from(sheet, kwargs)
        except MarkError as exc:
            return ActionResult(success=False, message=exc.user_message)

        # Entry and reflection are one transaction: a reflection that fails late (a race on the
        # same deed) takes the entry back with it, and the writer is told why. A mark that is
        # refused late (the week's table at 0 percent, a worn payer) does not: the entry stays,
        # the act stays pointable and the writer reads the refusal beside the entry. Catching
        # it inside the block keeps the entry's other writes (counters, cached rows) true.
        mark_line = ""
        mark_paid = False
        try:
            with transaction.atomic():
                entry = create_journal_entry(
                    author=sheet,
                    title=kwargs.get("title", ""),
                    body=kwargs.get("body", ""),
                    is_public=bool(kwargs.get("is_public", False)),
                    tags=kwargs.get("tags"),
                    posthumous_override=posthumous_override,
                    about=about,
                )
                reflection = (
                    record_pending_reflection(sheet, pending, writing=entry)
                    if pending is not None
                    else None
                )
                if pending_mark is not None:
                    mark_line, mark_paid = _record_journal_mark(sheet, pending_mark, entry)
        except ReflectionError as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(
            success=True,
            message=(
                f"You write a new journal entry: {entry.title}."
                + (f" {recorded_line(reflection)}" if reflection is not None else "")
                + (f" {mark_line}" if mark_line else "")
            ),
            data={"entry_id": entry.pk}
            | ({"reflection_line": recorded_line(reflection)} if reflection is not None else {})
            | ({"mark_line": mark_line, "mark_recorded": mark_paid} if mark_line else {}),
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
            return ActionResult(success=False, message=_MSG_NO_ACTIVE_CHARACTER)

        parent = kwargs.get("parent")
        parent_id = kwargs.get("parent_id")
        response_type = kwargs.get("response_type")
        if isinstance(parent, JournalEntry):
            pass
        elif parent_id is not None:
            try:
                parent = JournalEntry.objects.get(pk=parent_id)
            except JournalEntry.DoesNotExist:
                return ActionResult(success=False, message=_MSG_ENTRY_NOT_FOUND)
        else:
            return ActionResult(success=False, message="No journal entry selected.")
        if response_type not in ResponseType.values:
            return ActionResult(
                success=False,
                message="response_type must be praise, retort, or condemn.",
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
        from world.journals.constants import PosthumousOverride  # noqa: PLC0415
        from world.journals.models import JournalEntry  # noqa: PLC0415
        from world.journals.services import edit_journal_entry  # noqa: PLC0415
        from world.journals.types import JournalError  # noqa: PLC0415

        sheet = self._sheet(actor)
        if sheet is None:
            return ActionResult(success=False, message=_MSG_NO_ACTIVE_CHARACTER)

        entry = kwargs.get("entry")
        entry_id = kwargs.get("entry_id")
        if isinstance(entry, JournalEntry):
            if entry.author_id != sheet.pk:
                return ActionResult(success=False, message=_MSG_ENTRY_NOT_FOUND)
        elif entry_id is not None:
            try:
                entry = JournalEntry.objects.get(pk=entry_id, author_id=sheet.pk)
            except JournalEntry.DoesNotExist:
                return ActionResult(success=False, message=_MSG_ENTRY_NOT_FOUND)
        else:
            return ActionResult(success=False, message="No journal entry selected.")

        posthumous_override = kwargs.get("posthumous_override")
        if posthumous_override is not None and posthumous_override not in PosthumousOverride.values:
            return ActionResult(success=False, message=_MSG_INVALID_OVERRIDE)

        about, error = _resolve_about(kwargs.get("about_id"))
        if error is not None:
            return ActionResult(success=False, message=error)

        try:
            updated = edit_journal_entry(
                entry=entry,
                title=kwargs.get("title"),
                body=kwargs.get("body"),
                posthumous_override=posthumous_override,
                about=about,
                clear_about=bool(kwargs.get("clear_about", False)),
            )
        except JournalError as exc:
            return ActionResult(success=False, message=exc.user_message)

        return ActionResult(
            success=True,
            message=f"You revise '{updated.title}'.",
            data={"entry_id": updated.pk},
        )


@dataclass
class SetJournalDispositionAction(_BaseJournalAction):
    """Set the actor's sheet-level default posthumous journal disposition (#3287)."""

    key: str = "set_journal_disposition"
    name: str = "Set Posthumous Journal Disposition"
    icon: str = "shield"
    category: str = "journals"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.character_sheets.types import PosthumousJournalDisposition  # noqa: PLC0415
        from world.journals.services import set_sheet_posthumous_disposition  # noqa: PLC0415

        sheet = self._sheet(actor)
        if sheet is None:
            return ActionResult(success=False, message=_MSG_NO_ACTIVE_CHARACTER)

        disposition = kwargs.get("disposition")
        if disposition not in PosthumousJournalDisposition.values:
            return ActionResult(success=False, message=_MSG_INVALID_DISPOSITION)

        set_sheet_posthumous_disposition(sheet=sheet, disposition=disposition)
        return ActionResult(
            success=True,
            message=f"Your private journals will {disposition} after death by default.",
            data={"disposition": disposition},
        )


@dataclass
class SetRetortConsentAction(_BaseJournalAction):
    """Set who may Retort or Condemn the actor's entries (#3941, ADR-0307)."""

    key: str = "set_retort_consent"
    name: str = "Set Retort Consent"
    icon: str = "shield"
    category: str = "journals"

    def execute(
        self,
        actor: ObjectDB,
        context: ActionContext | None = None,
        **kwargs: Any,
    ) -> ActionResult:
        from world.character_sheets.types import RetortConsent  # noqa: PLC0415
        from world.journals.services import set_retort_consent  # noqa: PLC0415

        sheet = self._sheet(actor)
        if sheet is None:
            return ActionResult(success=False, message=_MSG_NO_ACTIVE_CHARACTER)
        consent = kwargs.get("consent")
        if consent not in RetortConsent.values:
            return ActionResult(success=False, message=_MSG_INVALID_CONSENT)
        set_retort_consent(sheet=sheet, consent=consent)
        who = "anyone" if consent == RetortConsent.ANYONE else "rivals only"
        return ActionResult(
            success=True,
            message=f"Retorts and condemnation of your journals: {who}.",
            data={"consent": consent},
        )
