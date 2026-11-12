"""Missive services (#3289): send, read, accept, refuse, and the arrival sweep.

Every player-facing failure raises ``MissiveError`` whose ``user_message`` is plain play
copy. Callers (the actions, the telnet verbs, the REST views) never format their own.

Leak rules this module keeps (spec "Verified leak analysis"):

- A missive is addressed to a persona, never a character. Addressing refusals use the same
  wording whoever owns the persona.
- Blocks are write-then-suppress (decision 6): a blocked send is written like any other and
  marked ``undeliverable``; the recipient never sees it and the sender is never told.
- Notices to the sender name the recipient PERSONA the sender addressed, never its character.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from world.conditions.services import get_effective_capability_value
from world.currency.services import get_or_create_purse, transfer
from world.game_clock.services import get_ic_now, get_real_time_for_ic_date
from world.game_clock.types import ClockError
from world.items.constants import OwnershipEventType
from world.items.exceptions import NaturalWeaponNotRemovable
from world.items.models import ItemInstance, OwnershipEvent
from world.items.services.holding import set_item_holder
from world.items.services.materialize import materialize_item_game_object
from world.items.services.natural_weapons import is_natural_weapon
from world.items.services.usage import dematerialize_item_instance, release_item_for_custody
from world.messengers.constants import AttachmentResolution
from world.messengers.exceptions import MissiveError
from world.messengers.models import Missive, MissiveAttachment, TransmissionMethod
from world.scenes.block_services import (
    account_block_active,
    coded_block_active,
    persona_player,
)
from world.scenes.constants import PersonaType
from world.scenes.models import Persona

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet

_ADDRESSABLE_TYPES = (PersonaType.PRIMARY, PersonaType.ESTABLISHED)

NO_METHOD = "No messenger can carry a missive for you."
METHOD_NOT_YOURS = "You cannot send by that means."
NO_SUCH_PERSONA = "There is no one by that name to send to."
AMBIGUOUS_PERSONA = "More than one person goes by that name."
EMPTY_BODY = "Write something first."
NOT_HELD = "You can only send something you have."
NOT_ENOUGH_COIN = "You do not have that much coin."
NO_SUCH_MISSIVE = "You have no such missive."
NOT_YOURS = "That missive was not sent to you."
NOTHING_ATTACHED = "Nothing came with that missive."
ALREADY_ANSWERED = "You have already answered for what came with it."


# ---------------------------------------------------------------------------
# Methods and addressing
# ---------------------------------------------------------------------------


def available_methods_for(sheet: CharacterSheet) -> list[TransmissionMethod]:
    """The transmission methods this character may send with, ordered by name.

    A universal method is open to everyone; a capability-gated one needs the character's
    effective value of that capability above zero.
    """
    methods = TransmissionMethod.objects.select_related("required_capability")
    available: list[TransmissionMethod] = []
    for method in methods:
        gated_open = method.required_capability is not None and (
            get_effective_capability_value(sheet, method.required_capability) > 0
        )
        if method.is_universal or gated_open:
            available.append(method)
    return available


def default_method_for(sheet: CharacterSheet) -> TransmissionMethod:
    """The first available method by name; refuses when there is none."""
    methods = available_methods_for(sheet)
    if not methods:
        raise MissiveError(NO_METHOD)
    return methods[0]


def _addressable_personas() -> QuerySet[Persona]:
    return Persona.objects.filter(persona_type__in=_ADDRESSABLE_TYPES, is_system=False)


def find_addressable_persona(name: str) -> Persona:
    """The one primary or established persona going by ``name`` (any case).

    The refusal wording never depends on who owns the persona.
    """
    matches = list(_addressable_personas().filter(name__iexact=name.strip())[:2])
    if not matches:
        raise MissiveError(NO_SUCH_PERSONA)
    if len(matches) > 1:
        raise MissiveError(AMBIGUOUS_PERSONA)
    return matches[0]


def addressable_persona(persona_id: int) -> Persona:
    """The addressable persona with this pk, under the same rules as by name."""
    persona = _addressable_personas().filter(pk=persona_id).first()
    if persona is None:
        raise MissiveError(NO_SUCH_PERSONA)
    return persona


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------


def _blocked(a: Persona, b: Persona) -> bool:
    """Whether an active block sits between these two faces' players, either way.

    A persona whose character has no current player gives no PlayerData and is treated as
    not blocked (the block helpers are keyed on players).
    """
    player_a = persona_player(a)
    player_b = persona_player(b)
    if player_a is None or player_b is None:
        return False
    return coded_block_active(
        player_a=player_a, persona_a=a, player_b=player_b, persona_b=b
    ) or account_block_active(player_a=player_a, player_b=player_b)


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------


def _arrival_time(ic_sent_at: datetime | None, delay_minutes: int) -> datetime:
    """Real time the letter arrives: the IC delay through the clock, else real minutes."""
    delay = timedelta(minutes=delay_minutes)
    if ic_sent_at is not None:
        try:
            arrival = get_real_time_for_ic_date(ic_sent_at + delay)
        except ClockError:
            # Paused or zero-ratio clock: IC time cannot be converted, so fall back.
            arrival = None
        if arrival is not None:
            return arrival
    return timezone.now() + delay


def _lock_items_for_sending(
    items: Sequence[ItemInstance], sender_sheet: CharacterSheet
) -> list[ItemInstance]:
    locked: list[ItemInstance] = []
    for item in items:
        row = ItemInstance.objects.select_for_update().filter(pk=item.pk).first()
        if row is None or row.holder_character_sheet_id != sender_sheet.pk:
            raise MissiveError(NOT_HELD)
        if is_natural_weapon(row):
            raise MissiveError(NaturalWeaponNotRemovable.user_message)
        if MissiveAttachment.objects.filter(
            item=row, resolution=AttachmentResolution.PENDING
        ).exists():
            raise MissiveError(NOT_HELD)
        locked.append(row)
    return locked


def _take_into_transit(item: ItemInstance) -> None:
    """Row custody while the letter travels: off the body, no game object, no holder.

    The org vault's ``_take_into_custody`` shape (``items/services/org_vault.py``).
    """
    release_item_for_custody(item)
    dematerialize_item_instance(item)
    set_item_holder(item, None)
    item.save(update_fields=["contained_in"])


def _method_for_sending(
    sheet: CharacterSheet,
    method: TransmissionMethod | None,
    *,
    carries_coin: bool,
    carries_items: bool,
) -> TransmissionMethod:
    """The method this send uses: the one asked for if this character may use it, else the
    default; refused when it cannot carry what rides along."""
    available = available_methods_for(sheet)
    if method is None:
        if not available:
            raise MissiveError(NO_METHOD)
        method = available[0]
    elif method not in available:
        raise MissiveError(METHOD_NOT_YOURS)
    if carries_coin and not method.can_carry_coin:
        message = f"A {method.name} cannot carry coin."
        raise MissiveError(message)
    if carries_items and not method.can_carry_items:
        message = f"A {method.name} cannot carry items."
        raise MissiveError(message)
    return method


@transaction.atomic
def send_missive(  # noqa: PLR0913 - every argument is a distinct part of the letter
    *,
    sender_persona: Persona,
    recipient_persona: Persona,
    body: str,
    method: TransmissionMethod | None = None,
    coin_amount: int = 0,
    items: Sequence[ItemInstance] = (),
    in_reply_to: Missive | None = None,
) -> Missive:
    """Write and send a missive from one persona to another.

    Coin leaves the sender's purse now (a sink; the attachment row is the in-transit
    custody) and items go into row custody. A send between blocked players is written
    exactly like any other and marked ``undeliverable`` (write-then-suppress, decision 6):
    the recipient never sees it and the sender is never told. Its attachments stay PENDING
    for good; they are never auto-returned, because a return would tell the sender about
    the block.
    """
    text = body.strip()
    if not text:
        raise MissiveError(EMPTY_BODY)
    sender_sheet = sender_persona.character_sheet
    method = _method_for_sending(
        sender_sheet, method, carries_coin=coin_amount != 0, carries_items=bool(items)
    )
    if coin_amount < 0:
        raise MissiveError(NOT_ENOUGH_COIN)
    locked_items = _lock_items_for_sending(items, sender_sheet)
    purse = get_or_create_purse(sender_sheet) if coin_amount else None
    if purse is not None and purse.balance < coin_amount:
        raise MissiveError(NOT_ENOUGH_COIN)

    ic_sent_at = get_ic_now()
    missive = Missive.objects.create(
        sender_persona=sender_persona,
        recipient_persona=recipient_persona,
        method=method,
        body=text,
        ic_sent_at=ic_sent_at,
        available_at=_arrival_time(ic_sent_at, method.ic_delay_minutes),
        undeliverable=_blocked(sender_persona, recipient_persona),
        in_reply_to=in_reply_to,
    )
    if purse is not None:
        try:
            transfer(amount=coin_amount, reason=f"Missive {missive.pk} sent", from_purse=purse)
        except ValidationError as exc:
            # The amount is known positive and there is one source, so the only refusal
            # left is insufficient funds (the purse drained since the check above).
            raise MissiveError(NOT_ENOUGH_COIN) from exc
        MissiveAttachment.objects.create(missive=missive, coin_amount=coin_amount)
    for item in locked_items:
        _take_into_transit(item)
        MissiveAttachment.objects.create(missive=missive, item=item)
    return missive


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def _suppress_if_blocked(missive: Missive) -> bool:
    """Re-check a block at arrival; a blocked missive turns ``undeliverable`` silently."""
    if not _blocked(missive.sender_persona, missive.recipient_persona):
        return False
    missive.undeliverable = True
    missive.save(update_fields=["undeliverable"])
    return True


def _awaiting_arrival_check(missive: Missive, now: datetime) -> bool:
    return (
        missive.arrival_notified_at is None
        and not missive.undeliverable
        and missive.available_at <= now
    )


def _settle_arrivals_for(sheet: CharacterSheet, now: datetime) -> None:
    """Apply the arrival block re-check to this character's due, unannounced missives.

    Availability is lazy (it holds when the sweep is down), so the check a sweep would make
    is made here too, before anything is shown: a block placed in transit must never let the
    letter through in the window before the next sweep.
    """
    due = Missive.objects.filter(
        recipient_persona__character_sheet=sheet,
        available_at__lte=now,
        arrival_notified_at__isnull=True,
        undeliverable=False,
    ).select_related("sender_persona", "recipient_persona")
    for missive in due:
        _suppress_if_blocked(missive)


def _delivered_to(sheet: CharacterSheet, now: datetime) -> Q:
    return Q(
        recipient_persona__character_sheet=sheet,
        available_at__lte=now,
        undeliverable=False,
    )


def visible_missives_for(
    sheet: CharacterSheet, *, now: datetime | None = None
) -> QuerySet[Missive]:
    """Missives this character may see: everything any of its faces sent, and what any of
    its faces received once it has arrived and was not suppressed by a block."""
    now = now or timezone.now()
    _settle_arrivals_for(sheet, now)
    return (
        Missive.objects.filter(Q(sender_persona__character_sheet=sheet) | _delivered_to(sheet, now))
        # No attachments prefetch: a bare-string or plain to_attr prefetch onto these
        # identity-mapped rows would serve a stale list after accept/refuse (ADR-0263).
        .select_related("method", "sender_persona", "recipient_persona")
    )


def unread_count_for(sheet: CharacterSheet) -> int:
    """Arrived, unsuppressed, unread missives addressed to any of this character's faces."""
    now = timezone.now()
    _settle_arrivals_for(sheet, now)
    return Missive.objects.filter(_delivered_to(sheet, now), read_at__isnull=True).count()


def get_visible_missive(sheet: CharacterSheet, missive_id: int) -> Missive:
    """One missive this character may see, else the same refusal whatever the reason."""
    missive = visible_missives_for(sheet).filter(pk=missive_id).first()
    if missive is None:
        raise MissiveError(NO_SUCH_MISSIVE)
    return missive


def _is_delivered_to(sheet: CharacterSheet, missive: Missive) -> bool:
    """Whether this missive has reached this character, after the arrival block re-check."""
    now = timezone.now()
    if missive.recipient_persona.character_sheet_id != sheet.pk:
        return False
    if _awaiting_arrival_check(missive, now) and _suppress_if_blocked(missive):
        return False
    return not missive.undeliverable and missive.available_at <= now


def read_missive(*, sheet: CharacterSheet, missive: Missive) -> Missive:
    """Mark the missive read the first time its recipient reads it; a sender's read is a no-op."""
    if missive.read_at is None and _is_delivered_to(sheet, missive):
        missive.read_at = timezone.now()
        missive.save(update_fields=["read_at"])
    return missive


def sent_by(sheet: CharacterSheet, missive: Missive) -> bool:
    """Whether this character wrote the missive to someone else.

    A letter between two of one character's own faces counts as received, so its reply goes
    back to the face that wrote it.
    """
    return (
        missive.sender_persona.character_sheet_id == sheet.pk
        and missive.recipient_persona.character_sheet_id != sheet.pk
    )


def sent_by_q(sheet: CharacterSheet) -> Q:
    """``sent_by`` as a queryset filter: the same rule, for filtering a list in the database."""
    return Q(sender_persona__character_sheet=sheet) & ~Q(recipient_persona__character_sheet=sheet)


def reply_sender_for(missive: Missive) -> Persona:
    """The face a reply goes out under: the one that was written to (decision 3).

    Answering a letter sent to a mask must never unmask the writer.
    """
    return missive.recipient_persona


# ---------------------------------------------------------------------------
# Accepting and refusing what came with it
# ---------------------------------------------------------------------------


def _lock_pending_attachments(sheet: CharacterSheet, missive: Missive) -> list[MissiveAttachment]:
    if not _is_delivered_to(sheet, missive):
        # Visibility first: a missive this character cannot see gets the same copy as a
        # nonexistent one; only a letter it sent (and so sees) is "not sent to you".
        if missive.sender_persona.character_sheet_id == sheet.pk:
            raise MissiveError(NOT_YOURS)
        raise MissiveError(NO_SUCH_MISSIVE)
    pending = list(
        MissiveAttachment.objects.select_for_update()
        .filter(missive=missive, resolution=AttachmentResolution.PENDING)
        .order_by("pk")
    )
    if not pending:
        if MissiveAttachment.objects.filter(missive=missive).exists():
            raise MissiveError(ALREADY_ANSWERED)
        raise MissiveError(NOTHING_ATTACHED)
    return pending


def _hand_over(
    attachment: MissiveAttachment,
    *,
    missive: Missive,
    to_sheet: CharacterSheet,
    accepted: bool,
) -> None:
    """Move one attachment out of transit to ``to_sheet``."""
    if attachment.coin_amount:
        verb = "accepted" if accepted else "returned"
        transfer(
            amount=attachment.coin_amount,
            reason=f"Missive {missive.pk} {verb}",
            to_purse=get_or_create_purse(to_sheet),
        )
        return
    item = ItemInstance.objects.select_for_update().get(pk=attachment.item_id)
    event = None
    if accepted:
        event = OwnershipEvent.objects.create(
            item_instance=item,
            event_type=OwnershipEventType.GIVEN,
            from_character_sheet=missive.sender_persona.character_sheet,
            to_character_sheet=to_sheet,
            from_persona_display=missive.sender_persona,
            to_persona_display=missive.recipient_persona,
            notes=f"missive #{missive.pk}",
        )
    set_item_holder(item, to_sheet, event=event)
    materialize_item_game_object(item, to_sheet)


def _notify_sender(missive: Missive, text: str) -> None:
    """One line to the sender's character, only if someone is playing it right now."""
    character = missive.sender_persona.character_sheet.character
    if character is not None and character.sessions.count():
        character.msg(text)


def _resolve(*, sheet: CharacterSheet, missive: Missive, accepted: bool) -> list[MissiveAttachment]:
    pending = _lock_pending_attachments(sheet, missive)
    to_sheet = sheet if accepted else missive.sender_persona.character_sheet
    resolution = AttachmentResolution.ACCEPTED if accepted else AttachmentResolution.REFUSED
    now = timezone.now()
    for attachment in pending:
        _hand_over(attachment, missive=missive, to_sheet=to_sheet, accepted=accepted)
        attachment.resolution = resolution
        attachment.resolved_at = now
        attachment.save(update_fields=["resolution", "resolved_at"])
    name = missive.recipient_persona.name
    if accepted:
        text = f"{name} accepted what you sent with your missive."
    else:
        text = f"{name} refused what you sent; it has been returned to you."
    # robust: a failed notice is logged and never disturbs the committed hand-over.
    transaction.on_commit(lambda: _notify_sender(missive, text), robust=True)
    return pending


@transaction.atomic
def accept_missive(*, sheet: CharacterSheet, missive: Missive) -> list[MissiveAttachment]:
    """The recipient takes the coin and items that came with the missive.

    Items are recorded as a gift (an ``OwnershipEvent`` GIVEN, persona-voiced on both sides)
    and appear in the recipient's inventory; coin is credited to their purse.
    """
    return _resolve(sheet=sheet, missive=missive, accepted=True)


@transaction.atomic
def refuse_missive(*, sheet: CharacterSheet, missive: Missive) -> list[MissiveAttachment]:
    """The recipient sends the coin and items back to the sender's character."""
    return _resolve(sheet=sheet, missive=missive, accepted=False)


# ---------------------------------------------------------------------------
# Arrival sweep
# ---------------------------------------------------------------------------


def deliver_due_missives(*, now: datetime | None = None) -> int:
    """Announce every missive that has come due; returns how many were announced.

    A block placed while the letter travelled is checked again here: the missive turns
    ``undeliverable`` and nobody is told. Otherwise the arrival push goes out after commit
    and ``arrival_notified_at`` is stamped whether or not the recipient is online (the
    unread count carries it for an offline recipient).
    """
    from world.messengers.notifications import notify_missive_arrived  # noqa: PLC0415

    now = now or timezone.now()
    due = Missive.objects.filter(
        available_at__lte=now, arrival_notified_at__isnull=True, undeliverable=False
    ).select_related("sender_persona", "recipient_persona")
    announced = 0
    for candidate in due:
        with transaction.atomic():
            # Lock and re-read: an overlapping sweep holding this row skips it, and one that
            # already announced it no longer matches, so no letter is pushed twice.
            missive = (
                Missive.objects.select_for_update(skip_locked=True)
                .filter(pk=candidate.pk, arrival_notified_at__isnull=True, undeliverable=False)
                .select_related("sender_persona", "recipient_persona")
                .first()
            )
            if missive is None or _suppress_if_blocked(missive):
                continue
            missive.arrival_notified_at = now
            missive.save(update_fields=["arrival_notified_at"])
            # robust: one failed push is logged and never stops the others.
            transaction.on_commit(lambda m=missive: notify_missive_arrived(m), robust=True)
        announced += 1
    return announced
