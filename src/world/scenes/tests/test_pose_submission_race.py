import threading
import uuid

from django.db import connection
from django.test import TransactionTestCase, tag

from world.scenes.factories import PersonaFactory
from world.scenes.interaction_services import idempotent_record_interaction
from world.scenes.models import InteractionMode, PoseSubmission


@tag("postgres")
class PoseSubmissionRaceTests(TransactionTestCase):
    """Two near-simultaneous submissions with the same request id must not both
    execute the underlying work - exactly one PoseSubmission/Interaction pair
    is created, matching the design's `IntegrityError`-on-race handling."""

    def test_concurrent_identical_submissions_produce_exactly_one_interaction(self):
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
        results: list = []

        def submit() -> None:
            results.append(idempotent_record_interaction(**kwargs))
            connection.close()

        threads = [threading.Thread(target=submit) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(
            PoseSubmission.objects.filter(persona=persona, client_request_id=request_id).count(), 1
        )
        interaction_pks = {
            result.interaction.pk for result in results if result.interaction is not None
        }
        self.assertEqual(len(interaction_pks), 1)
