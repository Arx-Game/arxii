from datetime import timedelta
import uuid

from django.test import TestCase
from django.utils import timezone

from world.scenes.factories import PersonaFactory
from world.scenes.models import PoseSubmission
from world.scenes.tasks import pose_submission_cleanup_task


class PoseSubmissionCleanupTests(TestCase):
    def test_prunes_rows_older_than_24h_keeps_recent(self):
        persona = PersonaFactory()
        old = PoseSubmission.objects.create(persona=persona, client_request_id=uuid.uuid4())
        PoseSubmission.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(hours=25)
        )
        recent = PoseSubmission.objects.create(persona=persona, client_request_id=uuid.uuid4())

        pose_submission_cleanup_task()

        self.assertFalse(PoseSubmission.objects.filter(pk=old.pk).exists())
        self.assertTrue(PoseSubmission.objects.filter(pk=recent.pk).exists())
