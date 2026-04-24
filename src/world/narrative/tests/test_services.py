from unittest import mock

from django.test import TestCase
from django.utils import timezone

from world.character_sheets.factories import CharacterSheetFactory
from world.narrative.constants import NarrativeCategory
from world.narrative.factories import NarrativeMessageDeliveryFactory
from world.narrative.services import deliver_queued_messages, send_narrative_message


class SendNarrativeMessageTests(TestCase):
    def test_creates_message_with_delivery_per_recipient(self) -> None:
        sheet_a = CharacterSheetFactory()
        sheet_b = CharacterSheetFactory()

        msg = send_narrative_message(
            recipients=[sheet_a, sheet_b],
            body="Dark clouds gather over the city.",
            category=NarrativeCategory.ATMOSPHERE,
        )

        self.assertIsNotNone(msg.pk)
        self.assertEqual(msg.deliveries.count(), 2)
        recipients = {d.recipient_character_sheet for d in msg.deliveries.all()}
        self.assertEqual(recipients, {sheet_a, sheet_b})

    def test_offline_recipient_delivery_remains_queued(self) -> None:
        sheet = CharacterSheetFactory()  # factory does not puppet the character
        msg = send_narrative_message(
            recipients=[sheet],
            body="A whisper on the wind.",
            category=NarrativeCategory.VISIONS,
        )
        delivery = msg.deliveries.get(recipient_character_sheet=sheet)
        self.assertIsNone(delivery.delivered_at)

    def test_empty_recipients_creates_message_with_no_deliveries(self) -> None:
        msg = send_narrative_message(
            recipients=[],
            body="System-level notice without recipients (edge case).",
            category=NarrativeCategory.SYSTEM,
        )
        self.assertEqual(msg.deliveries.count(), 0)

    def test_stores_ooc_note_and_sender_fields(self) -> None:
        sheet = CharacterSheetFactory()
        msg = send_narrative_message(
            recipients=[sheet],
            body="A beat resolved.",
            category=NarrativeCategory.STORY,
            ooc_note="Internal staff note about this beat.",
        )
        self.assertEqual(msg.category, NarrativeCategory.STORY)
        self.assertEqual(msg.ooc_note, "Internal staff note about this beat.")
        self.assertIsNone(msg.related_story)


class OnlinePushTests(TestCase):
    def test_online_recipient_is_pushed_and_marked_delivered(self) -> None:
        sheet = CharacterSheetFactory()
        fake_session = mock.Mock()
        character = sheet.character
        with (
            mock.patch.object(character.sessions, "all", return_value=[fake_session]),
            mock.patch.object(character, "msg") as msg_mock,
        ):
            msg = send_narrative_message(
                recipients=[sheet],
                body="A whisper reaches your ears.",
                category=NarrativeCategory.VISIONS,
            )
        delivery = msg.deliveries.get(recipient_character_sheet=sheet)
        self.assertIsNotNone(delivery.delivered_at)
        msg_mock.assert_called_once()
        body_arg = msg_mock.call_args.args[0]
        self.assertIn("A whisper reaches your ears.", body_arg)
        self.assertEqual(msg_mock.call_args.kwargs.get("type"), "narrative")


class DeliverQueuedMessagesTests(TestCase):
    def test_pushes_only_queued_messages_and_marks_delivered(self) -> None:
        sheet = CharacterSheetFactory()
        already = NarrativeMessageDeliveryFactory(
            recipient_character_sheet=sheet,
            delivered_at=timezone.now(),
        )
        queued_one = NarrativeMessageDeliveryFactory(
            recipient_character_sheet=sheet,
            delivered_at=None,
        )
        queued_two = NarrativeMessageDeliveryFactory(
            recipient_character_sheet=sheet,
            delivered_at=None,
        )
        fake_session = mock.Mock()
        character = sheet.character
        with (
            mock.patch.object(character.sessions, "all", return_value=[fake_session]),
            mock.patch.object(character, "msg") as msg_mock,
        ):
            count = deliver_queued_messages(sheet)

        self.assertEqual(count, 2)
        self.assertEqual(msg_mock.call_count, 2)
        queued_one.refresh_from_db()
        queued_two.refresh_from_db()
        already.refresh_from_db()
        self.assertIsNotNone(queued_one.delivered_at)
        self.assertIsNotNone(queued_two.delivered_at)
        # Already-delivered message's delivered_at should be unchanged.
        self.assertIsNotNone(already.delivered_at)

    def test_returns_zero_when_no_queued_messages(self) -> None:
        sheet = CharacterSheetFactory()
        count = deliver_queued_messages(sheet)
        self.assertEqual(count, 0)
