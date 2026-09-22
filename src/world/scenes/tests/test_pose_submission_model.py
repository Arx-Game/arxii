from django.db import IntegrityError, connection
from django.test import TestCase

from world.scenes.factories import InteractionFactory, PersonaFactory
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

    def test_durable_submission_carries_interaction_timestamp(self):
        persona = PersonaFactory()
        interaction = InteractionFactory(persona=persona)
        submission = PoseSubmission.objects.create(
            persona=persona,
            client_request_id="33333333-3333-3333-3333-333333333333",
            interaction_id=interaction.pk,
            timestamp=interaction.timestamp,
        )
        self.assertEqual(submission.timestamp, interaction.timestamp)
        self.assertEqual(submission.resolve_interaction(), interaction)

    def test_interaction_and_timestamp_must_be_set_together(self):
        persona = PersonaFactory()
        interaction = InteractionFactory(persona=persona)
        with self.assertRaises(IntegrityError):
            PoseSubmission.objects.create(
                persona=persona,
                client_request_id="44444444-4444-4444-4444-444444444444",
                interaction_id=interaction.pk,
            )

    def test_composite_relation_assignment_and_pair_filter(self):
        persona = PersonaFactory()
        interaction = InteractionFactory(persona=persona)
        submission = PoseSubmission(
            persona=persona,
            client_request_id="55555555-5555-5555-5555-555555555555",
            interaction=interaction,
        )
        self.assertEqual(submission.interaction_id, interaction.pk)
        self.assertEqual(submission.timestamp, interaction.timestamp)
        submission.save()
        loaded = PoseSubmission.objects.filter(pk=submission.pk).get()
        self.assertEqual(loaded.interaction.pk, interaction.pk)
        self.assertEqual(loaded.interaction.timestamp, interaction.timestamp)
        self.assertEqual(
            PoseSubmission.objects.filter(interaction=interaction).get().pk, submission.pk
        )

    def test_parent_delete_cascades_durable_submission(self):
        if connection.vendor != "postgresql":
            self.skipTest("composite database cascade is PostgreSQL-only")
        persona = PersonaFactory()
        interaction = InteractionFactory(persona=persona)
        submission = PoseSubmission.objects.create(
            persona=persona,
            client_request_id="66666666-6666-6666-6666-666666666666",
            interaction=interaction,
        )
        interaction.delete()
        self.assertFalse(PoseSubmission.objects.filter(pk=submission.pk).exists())
