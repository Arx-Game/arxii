import uuid

from django.test import TestCase

from world.scenes.factories import PersonaFactory
from world.scenes.interaction_services import idempotent_record_interaction
from world.scenes.models import InteractionMode, PoseSubmission


class IdempotentRecordInteractionTests(TestCase):
    def test_first_call_creates_interaction_and_ledger_row(self):
        persona = PersonaFactory()
        request_id = uuid.uuid4()
        result = idempotent_record_interaction(
            persona=persona,
            client_request_id=request_id,
            comparison_fields={"content": "Silas nods."},
            character=persona.character_sheet.character,
            content="Silas nods.",
            mode=InteractionMode.POSE,
        )
        self.assertFalse(result.replayed)
        self.assertFalse(result.conflict)
        self.assertIsNotNone(result.interaction)
        self.assertEqual(
            PoseSubmission.objects.get(persona=persona, client_request_id=request_id).interaction,
            result.interaction,
        )

    def test_retry_with_same_payload_replays_without_creating_a_second_interaction(self):
        persona = PersonaFactory()
        request_id = uuid.uuid4()
        kwargs = {
            "persona": persona,
            "client_request_id": request_id,
            "comparison_fields": {"content": "Silas nods."},
            "character": persona.character_sheet.character,
            "content": "Silas nods.",
            "mode": InteractionMode.POSE,
        }
        first = idempotent_record_interaction(**kwargs)
        second = idempotent_record_interaction(**kwargs)
        self.assertFalse(second.conflict)
        self.assertTrue(second.replayed)
        self.assertEqual(first.interaction.pk, second.interaction.pk)
        submissions = PoseSubmission.objects.filter(persona=persona, client_request_id=request_id)
        self.assertEqual(submissions.count(), 1)

    def test_retry_with_different_payload_is_a_conflict(self):
        persona = PersonaFactory()
        request_id = uuid.uuid4()
        idempotent_record_interaction(
            persona=persona,
            client_request_id=request_id,
            comparison_fields={"content": "Silas nods."},
            character=persona.character_sheet.character,
            content="Silas nods.",
            mode=InteractionMode.POSE,
        )
        result = idempotent_record_interaction(
            persona=persona,
            client_request_id=request_id,
            comparison_fields={"content": "Silas waves."},
            character=persona.character_sheet.character,
            content="Silas waves.",
            mode=InteractionMode.POSE,
        )
        self.assertTrue(result.conflict)
        self.assertIsNone(result.interaction)
