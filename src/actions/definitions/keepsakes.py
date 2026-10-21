"""Keepsake actions (#4530): mark an item you hold as standing for something, and let go.

Thin: the rules live in ``world.items.services.keepsakes``. The web item panel dispatches
these with ids; the telnet ``keepsake`` command dispatches them with names.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from evennia.objects.models import ObjectDB

from actions.base import Action, ActionResult
from actions.types import ActionContext, TargetType
from world.items.constants import KeepsakeSubject


def _sheet_of(actor: ObjectDB):
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    try:
        return actor.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        return None


def _held_item(actor: ObjectDB, sheet, kwargs: dict[str, Any]):
    """(item, error): the item the actor holds, by ``item_id`` (web) or ``item_name``."""
    from world.items.models import ItemInstance  # noqa: PLC0415

    item = None
    if kwargs.get("item_id") not in (None, ""):
        try:
            item = ItemInstance.objects.in_play().filter(pk=int(kwargs["item_id"])).first()
        except (TypeError, ValueError):
            item = None
    elif name := (kwargs.get("item_name") or "").strip():
        found = actor.search(name, location=actor, quiet=True)
        obj = found[0] if found else None
        item = ItemInstance.objects.filter(game_object=obj).first() if obj else None
    else:
        return None, ActionResult(success=False, message="Which item?")
    if item is None or item.holder_character_sheet_id != sheet.pk:
        return None, ActionResult(success=False, message="You are not holding that.")
    return item, None


@dataclass
class DeclareKeepsakeAction(Action):
    """Keep an item you hold as a keepsake: it stands for a tie, one of your deeds, a being,
    an organization, a person or a place, in your own words (#4530).

    kwargs:
        item_id / item_name: the item.
        subject_kind: one of ``KeepsakeSubject``.
        subject_id (web) / subject_name (telnet): the tie, deed, being, organization or
            person it stands for; for a place, ``subject_label`` is its name.
        text: your words, one to three sentences. Never scored.
        shown_on_examine: whether examine shows them.
        treasured: also mark the item treasured for consent.
    """

    key: str = "keepsake_declare"
    name: str = "Keep as a keepsake"
    icon: str = "heart"
    category: str = "items"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.items.exceptions import KeepsakeRefused  # noqa: PLC0415
        from world.items.services.keepsakes import (  # noqa: PLC0415
            MSG_NO_SUCH_SUBJECT,
            KeepsakeSubjectRef,
            declare_keepsake,
            find_subject_by_name,
        )

        sheet = _sheet_of(actor)
        if sheet is None:
            return ActionResult(success=False, message="You have no character sheet.")
        item, error = _held_item(actor, sheet, kwargs)
        if error is not None:
            return error
        kind = str(kwargs.get("subject_kind") or "")
        try:
            if kwargs.get("subject_id") not in (None, ""):
                subject = KeepsakeSubjectRef(kind=kind, pk=int(kwargs["subject_id"]))
            elif kind != KeepsakeSubject.PLACE and (kwargs.get("subject_name") or "").strip():
                subject = find_subject_by_name(sheet, kind, str(kwargs["subject_name"]))
            else:
                subject = KeepsakeSubjectRef(
                    kind=kind,
                    label=str(kwargs.get("subject_label") or kwargs.get("subject_name") or ""),
                )
            keepsake = declare_keepsake(
                sheet,
                item,
                subject=subject,
                text=str(kwargs.get("text") or ""),
                shown_on_examine=bool(kwargs.get("shown_on_examine")),
                treasured=bool(kwargs.get("treasured")),
            )
        except KeepsakeRefused as exc:
            return ActionResult(success=False, message=exc.user_message)
        except ValueError:
            return ActionResult(success=False, message=MSG_NO_SUCH_SUBJECT)
        return ActionResult(
            success=True,
            message=f"You keep {item} as a keepsake of {keepsake.subject_name}.",
            data={"keepsake_id": keepsake.pk},
        )


@dataclass
class ReleaseKeepsakeAction(Action):
    """Stop keeping an item as a keepsake. Frees the slot; keeping it again later starts the
    wait over (#4530). kwargs: ``item_id`` or ``item_name``."""

    key: str = "keepsake_release"
    name: str = "Release keepsake"
    icon: str = "heart-off"
    category: str = "items"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        from world.items.exceptions import KeepsakeRefused  # noqa: PLC0415
        from world.items.services.keepsakes import release_keepsake  # noqa: PLC0415

        sheet = _sheet_of(actor)
        if sheet is None:
            return ActionResult(success=False, message="You have no character sheet.")
        item, error = _held_item(actor, sheet, kwargs)
        if error is not None:
            return error
        try:
            release_keepsake(sheet, item)
        except KeepsakeRefused as exc:
            return ActionResult(success=False, message=exc.user_message)
        return ActionResult(success=True, message=f"You no longer keep {item} as a keepsake.")
