"""IC missive REGISTRY actions (#3289): send, reply, read, accept and refuse.

Thin wrappers over ``world.messengers.services``; the rules (methods, blocks, custody of
coin and items) live there and every refusal is a ``MissiveError`` whose ``user_message``
is shown as-is. These actions own what the services leave to the caller: that the sending
face is one of the actor's own, that the recipient is addressable, and that every
``missive_id`` is one the actor may see. Kwargs arrive as JSON types from the web and as
strings from the telnet ``missive`` command, so every id and amount is parsed here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from actions.base import Action
from actions.types import ActionResult, TargetType

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from actions.types import ActionContext
    from world.character_sheets.models import CharacterSheet
    from world.items.models import ItemInstance
    from world.messengers.models import Missive, TransmissionMethod
    from world.scenes.models import Persona

NO_CHARACTER = "No active character."
NOT_YOUR_FACE = "That is not one of your faces."
WHICH_MISSIVE = "Which missive?"
WHO_FOR = "Who is the missive for?"
BAD_COIN = "Give the coin as a whole number."
ACCEPTED = "You accept what came with the missive."
REFUSED = "You refuse it; the messenger takes it back."
NO_FACE = "You have no face to send under."
UNDATED = "undated"
_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1


class _Refusal(Exception):
    """A parse failure inside this module, carried up to one ``ActionResult``."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def _sheet_of(actor: ObjectDB) -> CharacterSheet:
    from django.core.exceptions import ObjectDoesNotExist  # noqa: PLC0415

    try:
        sheet = actor.sheet_data
    except (AttributeError, ObjectDoesNotExist) as exc:
        raise _Refusal(NO_CHARACTER) from exc
    if sheet is None:
        raise _Refusal(NO_CHARACTER)
    return sheet


def _int_or_none(value: Any) -> int | None:
    """An int from a JSON int or a telnet string (``"#12"`` too); None when unparseable or
    outside the signed 64-bit range a database column can hold."""
    number: int | None = None
    if isinstance(value, bool):
        number = None
    elif isinstance(value, int):
        number = value
    elif isinstance(value, str):
        try:
            number = int(value.strip().lstrip("#"))
        except ValueError:
            number = None
    if number is None or not _INT64_MIN <= number <= _INT64_MAX:
        return None
    return number


def _missive_for(sheet: CharacterSheet, kwargs: dict[str, Any]) -> Missive:
    from world.messengers.services import get_visible_missive  # noqa: PLC0415

    missive_id = _int_or_none(kwargs.get("missive_id"))
    if missive_id is None:
        raise _Refusal(WHICH_MISSIVE)
    return get_visible_missive(sheet, missive_id)


def _own_persona(sheet: CharacterSheet, value: Any) -> Persona:
    """The actor's own non-system persona with this pk, else "not one of your faces"."""
    from world.scenes.models import Persona  # noqa: PLC0415

    persona_id = _int_or_none(value)
    persona = (
        Persona.objects.filter(pk=persona_id, character_sheet=sheet, is_system=False).first()
        if persona_id is not None
        else None
    )
    if persona is None:
        raise _Refusal(NOT_YOUR_FACE)
    return persona


def _recipient(kwargs: dict[str, Any]) -> Persona:
    from world.messengers.exceptions import MissiveError  # noqa: PLC0415
    from world.messengers.services import (  # noqa: PLC0415
        NO_SUCH_PERSONA,
        addressable_persona,
        find_addressable_persona,
    )

    raw_id = kwargs.get("recipient_persona_id")
    if raw_id not in (None, ""):
        persona_id = _int_or_none(raw_id)
        if persona_id is None:
            raise MissiveError(NO_SUCH_PERSONA)
        return addressable_persona(persona_id)
    name = str(kwargs.get("recipient_name") or "").strip()
    if not name:
        raise _Refusal(WHO_FOR)
    return find_addressable_persona(name)


def _coin(kwargs: dict[str, Any]) -> int:
    raw = kwargs.get("coin_amount")
    if raw in (None, ""):
        return 0
    amount = _int_or_none(raw)
    if amount is None:
        raise _Refusal(BAD_COIN)
    return amount


def _method(kwargs: dict[str, Any]) -> TransmissionMethod | None:
    from world.messengers.exceptions import MissiveError  # noqa: PLC0415
    from world.messengers.models import TransmissionMethod  # noqa: PLC0415
    from world.messengers.services import METHOD_NOT_YOURS  # noqa: PLC0415

    raw = kwargs.get("method_id")
    if raw in (None, ""):
        return None
    method_id = _int_or_none(raw)
    method = (
        TransmissionMethod.objects.filter(pk=method_id).first() if method_id is not None else None
    )
    if method is None:
        raise MissiveError(METHOD_NOT_YOURS)
    return method


def _item_by_name(actor: ObjectDB, name: str) -> ItemInstance:
    wanted = name.strip().lower()
    carried = actor.carried_items.all()
    exact = [item for item in carried if item.display_name.lower() == wanted]
    if exact:
        return exact[0]
    partial = [item for item in carried if wanted in item.display_name.lower()]
    if len(partial) == 1:
        return partial[0]
    if partial:
        message = f"You carry more than one '{name.strip()}'."
    else:
        message = f"You carry no '{name.strip()}'."
    raise _Refusal(message)


def _items(actor: ObjectDB, kwargs: dict[str, Any]) -> list[ItemInstance]:
    """``item_ids`` (web, ItemInstance pks) or ``item_names`` (telnet, from what the actor
    carries). Whether the actor still holds each one is the service's check."""
    from world.items.models import ItemInstance  # noqa: PLC0415
    from world.messengers.exceptions import MissiveError  # noqa: PLC0415
    from world.messengers.services import NOT_HELD  # noqa: PLC0415

    raw_ids = kwargs.get("item_ids") or []
    if isinstance(raw_ids, (str, int)):
        raw_ids = [raw_ids]
    if raw_ids:
        pks = [_int_or_none(raw) for raw in raw_ids]
        if any(pk is None for pk in pks):
            raise MissiveError(NOT_HELD)
        unique = list(dict.fromkeys(pks))
        found = {item.pk: item for item in ItemInstance.objects.filter(pk__in=unique)}
        if len(found) != len(unique):
            raise MissiveError(NOT_HELD)
        return [found[pk] for pk in unique]
    raw_names = kwargs.get("item_names") or []
    if isinstance(raw_names, (str, int)):
        raw_names = [raw_names]
    names: Sequence[str] = [str(name) for name in raw_names]
    items: list[ItemInstance] = []
    for name in names:
        if not name.strip():
            continue
        item = _item_by_name(actor, name)
        if item not in items:
            items.append(item)
    return items


def _send(
    actor: ObjectDB,
    *,
    sender: Persona,
    recipient: Persona,
    kwargs: dict[str, Any],
    in_reply_to: Missive | None = None,
) -> ActionResult:
    from world.messengers.display import shown_name  # noqa: PLC0415
    from world.messengers.services import send_missive  # noqa: PLC0415

    missive = send_missive(
        sender_persona=sender,
        recipient_persona=recipient,
        body=str(kwargs.get("body") or ""),
        method=_method(kwargs),
        coin_amount=_coin(kwargs),
        items=_items(actor, kwargs),
        in_reply_to=in_reply_to,
    )
    actor.carried_items.invalidate()
    # A fresh letter names the recipient as the writer typed it; a reply names the face it
    # answers through the writer's eyes, so a mask stays a mask.
    if in_reply_to is None:
        recipient_label = recipient.name
    else:
        recipient_label = shown_name(recipient, sender.character_sheet)
    # Identical whether or not a block suppresses it (write-then-suppress).
    return ActionResult(
        success=True,
        message=f"Your missive to {recipient_label} is on its way.",
        data={"missive_id": missive.pk},
    )


def _guarded(run: Any) -> ActionResult:
    """Run ``run()`` and turn a refusal into a failed ``ActionResult``."""
    from world.messengers.exceptions import MissiveError  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415

    try:
        return run()
    except _Refusal as exc:
        return ActionResult(success=False, message=exc.message)
    except MissiveError as exc:
        return ActionResult(success=False, message=exc.user_message)
    except Persona.DoesNotExist:
        # active_persona_for_sheet on a sheet whose PRIMARY persona is missing.
        return ActionResult(success=False, message=NO_FACE)


def render_missive(missive: Missive, sheet: CharacterSheet) -> str:
    """The letter as ``sheet``'s character reads it: header, body, and what came with it."""
    from world.currency.constants import format_coppers  # noqa: PLC0415
    from world.game_clock.services import format_ic_date  # noqa: PLC0415
    from world.messengers.display import missive_correspondents  # noqa: PLC0415
    from world.messengers.models import MissiveAttachment  # noqa: PLC0415

    when = format_ic_date(missive.ic_sent_at) if missive.ic_sent_at is not None else UNDATED
    from_name, to_name = missive_correspondents(sheet, missive)
    lines = [
        f"From {from_name} to {to_name}, {when}",
        "",
        missive.body,
    ]
    attachments = list(
        MissiveAttachment.objects.filter(missive=missive)
        .select_related("item__template")
        .order_by("pk")
    )
    if attachments:
        lines.append("")
        lines.append("With it:")
        for attachment in attachments:
            what = (
                format_coppers(attachment.coin_amount)
                if attachment.coin_amount
                else attachment.item.display_name
            )
            lines.append(f"  {what} ({attachment.get_resolution_display()})")
    return "\n".join(lines)


@dataclass
class SendMissiveAction(Action):
    """Write a missive to another persona (#3289).

    kwargs:
        body: the letter.
        recipient_persona_id (web) / recipient_name (telnet): who it is for; any primary or
            established persona that is not a system one.
        sender_persona_id: optional, one of the actor's own faces; default the active one.
        coin_amount: optional coin to send with it, in coppers (the telnet ``+coin 5s`` is
            parsed to coppers by the command).
        item_ids (web) / item_names (telnet): optional items to send with it.
        method_id: optional transmission method; default the first one open to the actor.
    """

    key: str = "send_missive"
    name: str = "Send a missive"
    icon: str = "mail"
    category: str = "social"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        def run() -> ActionResult:
            from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

            sheet = _sheet_of(actor)
            if kwargs.get("sender_persona_id") not in (None, ""):
                sender = _own_persona(sheet, kwargs["sender_persona_id"])
            else:
                sender = active_persona_for_sheet(sheet)
            recipient = _recipient(kwargs)
            return _send(
                actor,
                sender=sender,
                recipient=recipient,
                kwargs=kwargs,
            )

        return _guarded(run)


@dataclass
class ReplyMissiveAction(Action):
    """Answer a missive (#3289).

    kwargs:
        missive_id: the missive being answered.
        body: the reply.
        sender_persona_id: optional, one of the actor's own faces. Default: the face the
            original was written to when the actor received it, or the face it went out
            under when the actor sent it.
        coin_amount, item_ids / item_names, method_id: as for ``send_missive``.

    The reply goes to the original's sender when the actor received it, and to the
    original's recipient when the actor sent it.
    """

    key: str = "reply_missive"
    name: str = "Reply to a missive"
    icon: str = "reply"
    category: str = "social"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        def run() -> ActionResult:
            from world.messengers.services import reply_sender_for, sent_by  # noqa: PLC0415

            sheet = _sheet_of(actor)
            original = _missive_for(sheet, kwargs)
            if sent_by(sheet, original):
                recipient = original.recipient_persona
                default_sender = original.sender_persona
            else:
                recipient = original.sender_persona
                default_sender = reply_sender_for(original)
            if kwargs.get("sender_persona_id") not in (None, ""):
                sender = _own_persona(sheet, kwargs["sender_persona_id"])
            else:
                sender = default_sender
            return _send(
                actor,
                sender=sender,
                recipient=recipient,
                kwargs=kwargs,
                in_reply_to=original,
            )

        return _guarded(run)


@dataclass
class ReadMissiveAction(Action):
    """Read a missive; the first read by its recipient marks it read (#3289).

    kwargs:
        missive_id: the missive.
    """

    key: str = "read_missive"
    name: str = "Read a missive"
    icon: str = "mail-open"
    category: str = "social"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        def run() -> ActionResult:
            from world.messengers.services import read_missive  # noqa: PLC0415

            sheet = _sheet_of(actor)
            missive = read_missive(sheet=sheet, missive=_missive_for(sheet, kwargs))
            return ActionResult(
                success=True,
                message=render_missive(missive, sheet),
                data={"missive_id": missive.pk},
            )

        return _guarded(run)


@dataclass
class AcceptMissiveAction(Action):
    """Take the coin and items that came with a missive (#3289).

    kwargs:
        missive_id: the missive.
    """

    key: str = "accept_missive"
    name: str = "Accept what came with a missive"
    icon: str = "check"
    category: str = "social"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        def run() -> ActionResult:
            from world.messengers.services import accept_missive  # noqa: PLC0415

            sheet = _sheet_of(actor)
            missive = _missive_for(sheet, kwargs)
            accept_missive(sheet=sheet, missive=missive)
            actor.carried_items.invalidate()
            return ActionResult(success=True, message=ACCEPTED, data={"missive_id": missive.pk})

        return _guarded(run)


@dataclass
class RefuseMissiveAction(Action):
    """Send the coin and items that came with a missive back to its sender (#3289).

    kwargs:
        missive_id: the missive.
    """

    key: str = "refuse_missive"
    name: str = "Refuse what came with a missive"
    icon: str = "x"
    category: str = "social"
    target_type: TargetType = TargetType.SELF

    def execute(
        self, actor: ObjectDB, context: ActionContext | None = None, **kwargs: Any
    ) -> ActionResult:
        def run() -> ActionResult:
            from world.messengers.services import refuse_missive  # noqa: PLC0415

            sheet = _sheet_of(actor)
            missive = _missive_for(sheet, kwargs)
            refuse_missive(sheet=sheet, missive=missive)
            return ActionResult(success=True, message=REFUSED, data={"missive_id": missive.pk})

        return _guarded(run)
