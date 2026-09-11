from django.db import IntegrityError
from django.test import TestCase

from world.scenes.factories import PersonaFactory
from world.scenes.models import PoseSubmission


class PoseSubmissionModelTests(TestCase):
    def test_unique_constraint_blocks_duplicate_request_id_for_same_persona(self):
        persona = PersonaFactory()
        request_id = "11111111-1111-1111-1111-111111111111"
        PoseSubmission.objects.create(persona=persona, client_request_id=request_id)
        with self.assertRaises(IntegrityError):
            PoseSubmission.objects.create(persona=persona, client_request_id=request_id)

    def test_same_request_id_allowed_for_different_personas(self):
        persona_a = PersonaFactory()
        persona_b = PersonaFactory()
        request_id = "22222222-2222-2222-2222-222222222222"
        PoseSubmission.objects.create(persona=persona_a, client_request_id=request_id)
        PoseSubmission.objects.create(persona=persona_b, client_request_id=request_id)
        self.assertEqual(PoseSubmission.objects.count(), 2)
