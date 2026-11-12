"""Journeys for IC missives (#3289): a letter written to a persona, carried by a messenger,
read, and what came with it accepted or refused.

Each types what a player types, sends what the web client dispatches, or reads the REST
list the missives page reads, and asserts what each player was told and shown. The
journeys send by a journey-local "Courier" that arrives the moment it is sent, so the
real clock is never patched; the arrival sweep (``deliver_due_missives``) is run by hand
where the scheduler would run it.
"""

from __future__ import annotations

from unittest.mock import patch

from evennia_extensions.factories import ObjectDBFactory
from integration_tests.harness import JourneyCase
from world.currency.services import get_or_create_purse, transfer
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemInstance
from world.messengers.factories import TransmissionMethodFactory
from world.messengers.models import Missive
from world.messengers.seeds import ensure_messenger_method
from world.messengers.services import deliver_due_missives
from world.scenes.block_services import create_block
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory

MISSIVES_URL = "/api/missives/"
UNREAD_URL = "/api/missives/unread-count/"


def sheet_of(character):
    return character.sheet_data


def face_of(character):
    return sheet_of(character).primary_persona


def give_coppers(character, amount: int) -> None:
    transfer(
        amount=amount, reason="journey seed", to_purse=get_or_create_purse(sheet_of(character))
    )


def purse_balance(character) -> int:
    purse = get_or_create_purse(sheet_of(character))
    purse.refresh_from_db()
    return purse.balance


def held_item(character, name: str) -> ItemInstance:
    """An item in *character*'s hands: a game object in their inventory and a row they hold."""
    return ItemInstanceFactory(
        template=ItemTemplateFactory(name=name),
        game_object=ObjectDBFactory(db_key=name, location=character),
        holder_character_sheet=sheet_of(character),
    )


def holder_of(item: ItemInstance) -> int | None:
    return ItemInstance.objects.filter(pk=item.pk).values_list("holder_character_sheet_id").get()[0]


def carries(character, item: ItemInstance) -> bool:
    character.carried_items.invalidate()
    return item.pk in {carried.pk for carried in character.carried_items.all()}


def arrival_frames(box) -> list[dict]:
    """The ``missive_arrived`` payloads pushed to one character's browser."""
    frame = "missive_arrived"
    return [kwargs[frame][1] for _args, kwargs in box.calls if frame in kwargs]


class MissiveJourneyCase(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self.study = self.make_room("Ysmay's Study")
        self.counting_house = self.make_room("The Counting House")
        self.ysmay = self.make_player("Ysmay", room=self.study)
        self.hobb = self.make_player("Hobb", room=self.counting_house)
        # Sorts before the seed "Messenger", so it is the default way to send.
        self.courier = TransmissionMethodFactory(name="Courier", ic_delay_minutes=0)

    def sweep(self) -> None:
        """The arrival sweep the scheduler runs, with its after-commit pushes."""
        with self.captureOnCommitCallbacks(execute=True):
            deliver_due_missives()

    def rows(self, character) -> list[dict]:
        response = self.api(self.account_of(character)).get(MISSIVES_URL)
        self.assertEqual(response.status_code, 200, response.content)
        return response.data["results"]

    def unread(self, character) -> int:
        response = self.api(self.account_of(character)).get(UNREAD_URL)
        self.assertEqual(response.status_code, 200, response.content)
        return response.data["count"]

    def only_missive(self) -> Missive:
        return Missive.objects.get()


class SendingAndAccepting(MissiveJourneyCase):
    """Ysmay sends Hobb a brooch and some coin by telnet; he reads and accepts it."""

    def test_a_letter_with_coin_and_a_brooch_reaches_hobb_and_he_keeps_them(self) -> None:
        give_coppers(self.ysmay, 100)
        brooch = held_item(self.ysmay, "Moth Brooch")
        self.connect_telnet(self.hobb)

        told = self.telnet(
            self.ysmay, "missive/send Hobb+coin 50+item Moth Brooch=Wear it to the masque."
        )
        self.assertIn("Your missive to Hobb is on its way.", told)
        self.assertEqual(purse_balance(self.ysmay), 50)
        self.assertFalse(carries(self.ysmay, brooch))
        letter = self.only_missive()

        self.sweep()
        self.assertEqual(
            arrival_frames(self.mailbox(self.hobb)),
            [
                {
                    "missive_id": letter.pk,
                    "recipient_persona_name": "Hobb",
                    "sender_display": "Ysmay",
                }
            ],
        )
        self.assertTold(
            self.hobb,
            f"A messenger brings you a missive from Ysmay. (missive/read {letter.pk})",
        )

        told = self.telnet(self.hobb, f"missive/read {letter.pk}")
        self.assertIn("From Ysmay to Hobb", told)
        self.assertIn("Wear it to the masque.", told)
        self.assertIn("50 coin (Waiting)", told)
        self.assertIn("Moth Brooch (Waiting)", told)

        told = self.telnet(self.hobb, f"missive/accept {letter.pk}")
        self.assertIn("You accept what came with the missive.", told)
        self.assertEqual(purse_balance(self.hobb), 50)
        self.assertEqual(holder_of(brooch), sheet_of(self.hobb).pk)
        self.assertTrue(carries(self.hobb, brooch))


class RefusingByTheWeb(MissiveJourneyCase):
    """Hobb refuses what came with a letter from the missives page; Ysmay gets it back."""

    def test_refused_coin_and_brooch_go_home_and_ysmay_hears_why(self) -> None:
        give_coppers(self.ysmay, 100)
        brooch = held_item(self.ysmay, "Moth Brooch")
        result = self.web(
            self.ysmay,
            "send_missive",
            recipient_persona_id=face_of(self.hobb).pk,
            body="A small token.",
            coin_amount=50,
            item_ids=[brooch.pk],
        )
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertIn("Your missive to Hobb is on its way.", result.detail.message)
        letter_id = result.detail.data["missive_id"]
        self.sweep()

        self.watch(self.ysmay)
        with (
            patch.object(self.ysmay.sessions, "count", return_value=1),
            self.captureOnCommitCallbacks(execute=True),
        ):
            result = self.web(self.hobb, "refuse_missive", missive_id=letter_id)
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertIn("You refuse it; the messenger takes it back.", result.detail.message)
        self.assertTold(self.ysmay, "Hobb refused what you sent; it has been returned to you.")
        self.assertEqual(purse_balance(self.ysmay), 100)
        self.assertEqual(holder_of(brooch), sheet_of(self.ysmay).pk)
        self.assertTrue(carries(self.ysmay, brooch))

        [row] = self.rows(self.ysmay)
        self.assertEqual(
            [(a["kind"], a["resolution"]) for a in row["attachments"]],
            [("coin", "refused"), ("item", "refused")],
        )


class WritingToAMask(MissiveJourneyCase):
    """Hobb writes to the Gray Fox; Ysmay answers as the Fox and never as herself."""

    def test_the_fox_answers_and_hobb_never_learns_who_it_is(self) -> None:
        fox = PersonaFactory(
            character_sheet=sheet_of(self.ysmay),
            name="the Gray Fox",
            persona_type=PersonaType.ESTABLISHED,
            is_fake_name=False,
        )
        told = self.telnet(self.hobb, "missive/send the Gray Fox=Who are you?")
        self.assertIn("Your missive to the Gray Fox is on its way.", told)
        question = self.only_missive()
        self.sweep()
        self.assertEqual(
            arrival_frames(self.mailbox(self.ysmay)),
            [
                {
                    "missive_id": question.pk,
                    "recipient_persona_name": "the Gray Fox",
                    "sender_display": "Hobb",
                }
            ],
        )

        told = self.telnet(self.ysmay, f"missive/reply {question.pk}=A friend of the docks.")
        self.assertIn("Your missive to Hobb is on its way.", told)
        answer = Missive.objects.exclude(pk=question.pk).get()
        self.assertEqual(answer.sender_persona, fox)
        self.sweep()

        told = self.telnet(self.hobb, f"missive/read {answer.pk}")
        self.assertIn("From the Gray Fox to Hobb", told)
        self.assertNotIn("Ysmay", told)

        rows = {row["id"]: row for row in self.rows(self.hobb)}
        self.assertEqual(rows[question.pk]["direction"], "sent")
        self.assertEqual(rows[question.pk]["counterpart_name"], "the Gray Fox")
        self.assertEqual(rows[answer.pk]["direction"], "received")
        self.assertEqual(rows[answer.pk]["counterpart_name"], "the Gray Fox")
        self.assertEqual(rows[answer.pk]["in_reply_to"], question.pk)
        for row in rows.values():
            self.assertEqual(row["own_persona_id"], face_of(self.hobb).pk)
            self.assertEqual(row["own_persona_name"], "Hobb")
            self.assertNotIn("Ysmay", str(row))


class ABlockedLetter(MissiveJourneyCase):
    """Hobb's player has blocked Ysmay's; her letter goes out like any other and never lands."""

    def test_the_sender_sees_a_normal_send_and_the_recipient_sees_nothing(self) -> None:
        told = self.telnet(self.ysmay, "missive/send Hobb=Before the quarrel.")
        self.assertIn("Your missive to Hobb is on its way.", told)
        before = self.only_missive()
        self.sweep()
        [before_row] = self.rows(self.ysmay)

        create_block(
            blocker_account=self.account_of(self.hobb),
            blocker_persona=face_of(self.hobb),
            blocked_persona=face_of(self.ysmay),
            reason="Too many letters.",
            account_level=True,
        )
        told = self.telnet(self.ysmay, "missive/send Hobb=Please, one more word.")
        self.assertIn("Your missive to Hobb is on its way.", told)
        after = Missive.objects.exclude(pk=before.pk).get()
        self.sweep()

        rows = {row["id"]: row for row in self.rows(self.ysmay)}
        varying = {"id", "body", "sent_at"}
        self.assertEqual(
            {k: v for k, v in rows[after.pk].items() if k not in varying},
            {k: v for k, v in before_row.items() if k not in varying},
        )
        self.assertEqual([row["id"] for row in self.rows(self.hobb)], [before.pk])
        self.assertEqual(self.unread(self.hobb), 1)
        self.assertEqual(
            [frame["missive_id"] for frame in arrival_frames(self.mailbox(self.hobb))],
            [before.pk],
        )
        self.assertNotIn("Please, one more word.", self.telnet(self.hobb, "missive"))


class WhoCanSeeALetter(MissiveJourneyCase):
    """Nobody but the two correspondents sees a letter, and the recipient only once it lands."""

    def test_a_stranger_sees_nothing_and_the_recipient_waits_for_the_messenger(self) -> None:
        tam = self.make_player("Tam", room=self.counting_house)
        result = self.web(
            self.ysmay,
            "send_missive",
            recipient_persona_id=face_of(self.hobb).pk,
            body="By the slow road.",
            method_id=ensure_messenger_method().pk,
        )
        self.assertTrue(result.detail.success, result.detail.message)
        letter_id = result.detail.data["missive_id"]
        self.sweep()

        self.assertEqual([row["id"] for row in self.rows(self.ysmay)], [letter_id])
        self.assertEqual(self.rows(self.hobb), [])
        self.assertEqual(self.unread(self.hobb), 0)
        self.assertEqual(arrival_frames(self.mailbox(self.hobb)), [])
        result = self.web(self.hobb, "read_missive", missive_id=letter_id)
        self.assertFalse(result.detail.success)
        self.assertIn("You have no such missive.", result.detail.message)

        self.assertEqual(self.rows(tam), [])
        self.assertEqual(self.unread(tam), 0)
        result = self.web(tam, "read_missive", missive_id=letter_id)
        self.assertFalse(result.detail.success)
        self.assertIn("You have no such missive.", result.detail.message)
