"""The missive arrival sweep (#3289).

Units only for what a journey cannot reach: the sweep's timing (it runs from the game-clock
scheduler, not from a player's action) and the block re-check at arrival.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerData
from world.items.factories import ItemInstanceFactory
from world.messengers.factories import MissiveFactory, TransmissionMethodFactory
from world.messengers.models import MissiveAttachment
from world.messengers.services import (
    deliver_due_missives,
    read_missive,
    send_missive,
    unread_count_for,
    visible_missives_for,
)
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.block_services import create_block


def _played_sheet():
    account = AccountFactory()
    player_data, _ = PlayerData.objects.get_or_create(account=account)
    entry = RosterEntryFactory()
    RosterTenureFactory(player_data=player_data, roster_entry=entry)
    return account, entry.character_sheet


def _arrival_pushes(msg_mock) -> list[dict]:
    return [c.kwargs["missive_arrived"][1] for c in msg_mock.call_args_list if c.kwargs]


class DeliverDueMissivesTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sender_account, cls.sender_sheet = _played_sheet()
        cls.recipient_account, cls.recipient_sheet = _played_sheet()
        cls.sender = cls.sender_sheet.primary_persona
        cls.recipient = cls.recipient_sheet.primary_persona
        cls.method = TransmissionMethodFactory()

    def _sweep(self, *, now) -> int:
        with self.captureOnCommitCallbacks(execute=True):
            return deliver_due_missives(now=now)

    def test_a_due_missive_is_announced_once_and_a_later_one_not_yet(self) -> None:
        now = timezone.now()
        due = MissiveFactory(
            sender_persona=self.sender,
            recipient_persona=self.recipient,
            method=self.method,
            available_at=now - timedelta(minutes=1),
        )
        later = MissiveFactory(
            sender_persona=self.sender,
            recipient_persona=self.recipient,
            method=self.method,
            available_at=now + timedelta(hours=1),
        )
        character_class = type(self.recipient_sheet.character)
        with patch.object(character_class, "msg") as msg_mock:
            self.assertEqual(self._sweep(now=now), 1)
            self.assertEqual(self._sweep(now=now), 0)

        pushes = _arrival_pushes(msg_mock)
        self.assertEqual(
            pushes,
            [
                {
                    "missive_id": due.pk,
                    "recipient_persona_name": self.recipient.name,
                    "sender_display": self.sender.name,
                }
            ],
        )
        due.refresh_from_db()
        later.refresh_from_db()
        self.assertEqual(due.arrival_notified_at, now)
        self.assertIsNone(later.arrival_notified_at)

    def _send_arriving_at(self, available_at):
        missive = send_missive(
            sender_persona=self.sender,
            recipient_persona=self.recipient,
            body="Meet me at the docks.",
            method=self.method,
        )
        self.assertFalse(missive.undeliverable)
        missive.available_at = available_at
        missive.save(update_fields=["available_at"])
        return missive

    def test_a_block_placed_in_transit_suppresses_the_missive(self) -> None:
        now = timezone.now()
        # One letter has arrived before any sweep runs; the other arrives later, at a sweep.
        arrived_unswept = self._send_arriving_at(now - timedelta(minutes=1))
        arrives_at_sweep = self._send_arriving_at(now + timedelta(minutes=10))
        create_block(
            blocker_account=self.recipient_account,
            blocker_persona=self.recipient,
            blocked_persona=self.sender,
            reason="They keep writing.",
        )

        # Lazy availability: with no sweep yet, the recipient already cannot see it.
        self.assertNotIn(arrived_unswept, visible_missives_for(self.recipient_sheet, now=now))
        self.assertEqual(unread_count_for(self.recipient_sheet), 0)
        arrived_unswept.refresh_from_db()
        self.assertTrue(arrived_unswept.undeliverable)

        later = now + timedelta(minutes=11)
        character_class = type(self.recipient_sheet.character)
        with patch.object(character_class, "msg") as msg_mock:
            self.assertEqual(self._sweep(now=later), 0)

        self.assertEqual(_arrival_pushes(msg_mock), [])
        arrives_at_sweep.refresh_from_db()
        self.assertTrue(arrives_at_sweep.undeliverable)
        self.assertIsNone(arrives_at_sweep.arrival_notified_at)
        recipient_view = visible_missives_for(self.recipient_sheet, now=later)
        self.assertNotIn(arrived_unswept, recipient_view)
        self.assertNotIn(arrives_at_sweep, recipient_view)
        # Write-then-suppress: the sender still sees the letters they sent.
        sender_view = visible_missives_for(self.sender_sheet, now=later)
        self.assertIn(arrived_unswept, sender_view)
        self.assertIn(arrives_at_sweep, sender_view)

    def test_a_letter_read_before_the_sweep_is_never_announced_or_withdrawn(self) -> None:
        now = timezone.now()
        letter = self._send_arriving_at(now - timedelta(minutes=1))
        read_missive(sheet=self.recipient_sheet, missive=letter)
        create_block(
            blocker_account=self.recipient_account,
            blocker_persona=self.recipient,
            blocked_persona=self.sender,
            reason="After reading it.",
        )

        character_class = type(self.recipient_sheet.character)
        with patch.object(character_class, "msg") as msg_mock:
            self.assertEqual(self._sweep(now=now), 0)

        self.assertEqual(_arrival_pushes(msg_mock), [])
        letter.refresh_from_db()
        self.assertFalse(letter.undeliverable)
        self.assertIn(letter, visible_missives_for(self.recipient_sheet, now=now))

    def test_the_same_item_twice_rides_once(self) -> None:
        item = ItemInstanceFactory(holder_character_sheet=self.sender_sheet)
        missive = send_missive(
            sender_persona=self.sender,
            recipient_persona=self.recipient,
            body="Twice over.",
            method=self.method,
            items=[item, item],
        )
        self.assertEqual(
            list(MissiveAttachment.objects.filter(missive=missive).values_list("item_id")),
            [(item.pk,)],
        )


class ArrivalLineArticleTests(TestCase):
    def test_the_article_follows_the_way_it_came(self) -> None:
        from world.messengers.notifications import _with_article

        self.assertEqual(_with_article("courier"), "A courier")
        self.assertEqual(_with_article("owl"), "An owl")
