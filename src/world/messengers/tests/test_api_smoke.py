"""SQLite-tier proof of the missives REST API (#3289).

The journeys in ``integration_tests/test_missives_journeys.py`` drive the same endpoint on
the Postgres tier; this drives ``GET /api/missives/`` through the real URL with a signed-in
account whose durable selection is a played character, so ``character_for_request``
resolves exactly as it does for a browser.
"""

from __future__ import annotations

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.currency.services import get_or_create_purse, transfer
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.messengers.factories import TransmissionMethodFactory
from world.messengers.seeds import ensure_messenger_method
from world.messengers.services import deliver_due_missives, read_missive, send_missive
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.roster.services.selection import set_selected_entry
from world.scenes.block_services import create_block
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory

LIST_URL = "/api/missives/"
UNREAD_URL = "/api/missives/unread-count/"
ADDRESSEES_URL = "/api/missives/addressees/"
ROW_FIELDS = {
    "id",
    "direction",
    "counterpart_name",
    "own_persona_id",
    "own_persona_name",
    "method_name",
    "body",
    "ic_date",
    "sent_at",
    "is_read",
    "in_reply_to",
    "attachments",
}


def _player(name: str):
    """A played character whose account has it selected, as login leaves it."""
    character = CharacterFactory(db_key=name)
    CharacterSheetFactory(character=character)
    entry = RosterEntryFactory(character_sheet__character=character)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    set_selected_entry(tenure.player_data, entry)
    return character, tenure.player_data.account


class MissiveApiSmokeTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.ysmay, cls.ysmay_account = _player("Ysmay")
        cls.hobb, cls.hobb_account = _player("Hobb")
        cls.tam, cls.tam_account = _player("Tam")
        cls.ysmay_face = cls.ysmay.character_sheet.primary_persona
        cls.hobb_face = cls.hobb.character_sheet.primary_persona
        # Arrives the moment it is sent; the seed Messenger takes 30 game minutes.
        cls.runner = TransmissionMethodFactory(name="Quick Runner", ic_delay_minutes=0)

    def _get(self, account, url: str = LIST_URL, **params):
        client = APIClient()
        client.force_authenticate(user=account)
        response = client.get(url, params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.data

    def _rows(self, account, **params) -> list[dict]:
        return self._get(account, **params)["results"]

    def _send(self, sender, recipient, body: str, **kwargs):
        return send_missive(sender_persona=sender, recipient_persona=recipient, body=body, **kwargs)

    def test_each_side_sees_the_letter_from_where_it_stands(self) -> None:
        transfer(
            amount=100,
            reason="smoke seed",
            to_purse=get_or_create_purse(self.ysmay.character_sheet),
        )
        brooch = ItemInstanceFactory(
            template=ItemTemplateFactory(name="Moth Brooch"),
            game_object=ObjectDBFactory(db_key="Moth Brooch", location=self.ysmay),
            holder_character_sheet=self.ysmay.character_sheet,
        )
        letter = self._send(
            self.ysmay_face,
            self.hobb_face,
            "Wear it tonight.",
            method=self.runner,
            coin_amount=50,
            items=[brooch],
        )

        [sent] = self._rows(self.ysmay_account)
        self.assertEqual(set(sent), ROW_FIELDS)
        self.assertEqual(sent["id"], letter.pk)
        self.assertEqual(sent["direction"], "sent")
        self.assertEqual(sent["counterpart_name"], "Hobb")
        self.assertEqual(sent["own_persona_id"], self.ysmay_face.pk)
        self.assertEqual(sent["own_persona_name"], "Ysmay")
        self.assertEqual(sent["method_name"], "Quick Runner")
        self.assertEqual(sent["body"], "Wear it tonight.")
        self.assertEqual(sent["ic_date"], "")  # no game clock in this test
        self.assertTrue(sent["is_read"])
        self.assertIsNone(sent["in_reply_to"])
        self.assertEqual(
            [(a["kind"], a["label"], a["resolution"]) for a in sent["attachments"]],
            [("coin", "5s", "pending"), ("item", "Moth Brooch", "pending")],
        )

        [received] = self._rows(self.hobb_account)
        self.assertEqual(received["direction"], "received")
        self.assertEqual(received["counterpart_name"], "Ysmay")
        self.assertEqual(received["own_persona_id"], self.hobb_face.pk)
        self.assertEqual(received["own_persona_name"], "Hobb")
        self.assertFalse(received["is_read"])

        # The filters split the two sides by the reader's place in the letter.
        self.assertEqual(self._rows(self.ysmay_account, direction="received"), [])
        self.assertEqual(len(self._rows(self.ysmay_account, direction="sent")), 1)
        self.assertEqual(len(self._rows(self.hobb_account, unread="true")), 1)

        # A third player sees neither side.
        self.assertEqual(self._rows(self.tam_account), [])
        self.assertEqual(self._get(self.tam_account, UNREAD_URL), {"count": 0})

    def test_unread_count_follows_arrival_and_reading(self) -> None:
        letter = self._send(self.ysmay_face, self.hobb_face, "Come by.", method=self.runner)
        self.assertEqual(self._get(self.hobb_account, UNREAD_URL), {"count": 1})
        read_missive(sheet=self.hobb.character_sheet, missive=letter)
        self.assertEqual(self._get(self.hobb_account, UNREAD_URL), {"count": 0})
        self.assertEqual(self._rows(self.hobb_account, unread="true"), [])
        [row] = self._rows(self.hobb_account)
        self.assertTrue(row["is_read"])
        # The sender's unread count never counts what it sent.
        self.assertEqual(self._get(self.ysmay_account, UNREAD_URL), {"count": 0})

    def test_a_letter_still_on_the_road_is_not_shown_to_its_recipient(self) -> None:
        self._send(self.ysmay_face, self.hobb_face, "On its way.", method=ensure_messenger_method())
        self.assertEqual(self._rows(self.hobb_account), [])
        self.assertEqual(self._get(self.hobb_account, UNREAD_URL), {"count": 0})
        self.assertEqual(len(self._rows(self.ysmay_account)), 1)

    def test_a_blocked_send_reads_like_any_other_to_its_sender(self) -> None:
        normal = self._send(self.ysmay_face, self.hobb_face, "First.", method=self.runner)
        [normal_row] = self._rows(self.ysmay_account)
        # Announced before the block, so it stays delivered; a letter not yet announced
        # would be suppressed by the arrival re-check.
        deliver_due_missives()
        create_block(
            blocker_account=self.hobb_account,
            blocker_persona=self.hobb_face,
            blocked_persona=self.ysmay_face,
            reason="Enough.",
            account_level=True,
        )
        blocked = self._send(self.ysmay_face, self.hobb_face, "Second.", method=self.runner)

        rows = {row["id"]: row for row in self._rows(self.ysmay_account)}
        blocked_row = rows[blocked.pk]
        varying = {"id", "body", "sent_at"}
        self.assertEqual(
            {k: v for k, v in blocked_row.items() if k not in varying},
            {k: v for k, v in normal_row.items() if k not in varying},
        )
        # The recipient sees only the letter that arrived before the block.
        self.assertEqual([row["id"] for row in self._rows(self.hobb_account)], [normal.pk])
        self.assertEqual(self._get(self.hobb_account, UNREAD_URL), {"count": 1})

    def test_no_row_carries_the_other_side(self) -> None:
        # The only id fields are the row, its reply link, its attachments and the reader's
        # own face; nothing names the other side's persona, sheet, character or account.
        self._send(self.ysmay_face, self.hobb_face, "Hello.", method=self.runner)
        for account, own_face in (
            (self.ysmay_account, self.ysmay_face),
            (self.hobb_account, self.hobb_face),
        ):
            [row] = self._rows(account)
            self.assertEqual(set(row), ROW_FIELDS)
            self.assertEqual(row["own_persona_id"], own_face.pk)
            self.assertNotIn("undeliverable", row)
            self.assertNotIn("read_at", row)

    def test_masked_writers_cost_the_same_however_many_letters_they_send(self) -> None:
        masks = []
        for player, mask in (("Maud", "owl mask"), ("Pell", "fox mask")):
            character, _ = _player(player)
            masks.append(
                PersonaFactory(
                    character_sheet=character.character_sheet,
                    name=mask,
                    persona_type=PersonaType.TEMPORARY,
                    is_fake_name=True,
                )
            )

        def write_one_each() -> None:
            for mask in masks:
                self._send(mask, self.hobb_face, "From behind a mask.", method=self.runner)
            deliver_due_missives()  # the scheduler's sweep, so no row waits on a settle

        def page_queries() -> tuple[int, list[dict]]:
            with CaptureQueriesContext(connection) as queries:
                rows = self._rows(self.hobb_account)
            return len(queries), rows

        write_one_each()
        page_queries()  # warm the request's own lookups
        two_rows, rows = page_queries()
        self.assertEqual(len(rows), 2)
        write_one_each()
        write_one_each()
        six_rows, rows = page_queries()
        self.assertEqual(len(rows), 6)
        self.assertLessEqual(six_rows, two_rows)
        for row in rows:
            self.assertNotIn("Maud", row["counterpart_name"])
            self.assertNotIn("Pell", row["counterpart_name"])
        self.assertEqual(
            {row["counterpart_name"] for row in rows},
            {"a person wearing an owl mask", "a person wearing a fox mask"},
        )
        # One missive by id goes through the same rule.
        client = APIClient()
        client.force_authenticate(user=self.hobb_account)
        detail = client.get(f"{LIST_URL}{rows[0]['id']}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data, rows[0])
        self.assertEqual(client.get(f"{LIST_URL}nope/").status_code, 404)

    def test_the_to_picker_names_faces_and_nothing_about_who_plays_them(self) -> None:
        mask_owner, _ = _player("Hobbin")
        PersonaFactory(
            character_sheet=mask_owner.character_sheet,
            name="Hobgoblin mask",
            persona_type=PersonaType.TEMPORARY,
            is_fake_name=True,
        )
        rows = self._get(self.tam_account, ADDRESSEES_URL, search="hob")
        self.assertEqual(
            rows,
            [
                {"id": self.hobb_face.pk, "name": "Hobb"},
                {"id": mask_owner.character_sheet.primary_persona.pk, "name": "Hobbin"},
            ],
        )
        for row in rows:
            self.assertEqual(set(row), {"id", "name"})
        # Too short a search finds nobody.
        self.assertEqual(self._get(self.tam_account, ADDRESSEES_URL, search="h"), [])
