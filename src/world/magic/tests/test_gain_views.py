"""API view tests for Spec C pose endorsement."""

from rest_framework.test import APITestCase


class PoseEndorsementViewTests(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import (
            CharacterResonanceFactory,
            ResonanceFactory,
        )
        from world.roster.factories import RosterTenureFactory
        from world.scenes.factories import (
            InteractionFactory,
            SceneFactory,
            SceneParticipationFactory,
        )

        cls.CharacterSheetFactory = CharacterSheetFactory
        cls.CharacterResonanceFactory = CharacterResonanceFactory
        cls.ResonanceFactory = ResonanceFactory
        cls.RosterTenureFactory = RosterTenureFactory
        cls.InteractionFactory = InteractionFactory
        cls.SceneFactory = SceneFactory
        cls.SceneParticipationFactory = SceneParticipationFactory

    def _endorser_scenario(self):
        """Build endorser (with tenure/account) + endorsee + interaction + scene."""
        from world.magic.services.gain import account_for_sheet

        endorser_tenure = self.RosterTenureFactory()
        endorser_sheet = endorser_tenure.roster_entry.character_sheet
        endorsee_tenure = self.RosterTenureFactory()
        endorsee_sheet = endorsee_tenure.roster_entry.character_sheet

        scene = self.SceneFactory()
        endorser_account = account_for_sheet(endorser_sheet)
        self.SceneParticipationFactory(scene=scene, account=endorser_account)

        resonance = self.ResonanceFactory()
        self.CharacterResonanceFactory(character_sheet=endorsee_sheet, resonance=resonance)
        interaction = self.InteractionFactory(scene=scene, persona=endorsee_sheet.primary_persona)
        return endorser_sheet, endorsee_sheet, scene, interaction, resonance, endorser_account

    def test_create_happy_path(self) -> None:
        from world.magic.models import PoseEndorsement

        _, _, _, interaction, resonance, account = self._endorser_scenario()
        self.client.force_authenticate(user=account)

        response = self.client.post(
            "/api/magic/pose-endorsements/",
            data={
                "interaction": interaction.pk,
                "resonance": resonance.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(PoseEndorsement.objects.count(), 1)

    def test_create_validation_error_returns_400(self) -> None:
        """Whisper interaction should return 400 with user_message."""
        from world.scenes.constants import InteractionMode

        _, _, _, interaction, resonance, account = self._endorser_scenario()
        interaction.mode = InteractionMode.WHISPER
        interaction.save(update_fields=["mode"])
        self.client.force_authenticate(user=account)

        response = self.client.post(
            "/api/magic/pose-endorsements/",
            data={
                "interaction": interaction.pk,
                "resonance": resonance.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_delete_unsettled_returns_204(self) -> None:
        from world.magic.services.gain import create_pose_endorsement

        endorser, _, _, interaction, resonance, account = self._endorser_scenario()
        endorsement = create_pose_endorsement(endorser, interaction, resonance)
        self.client.force_authenticate(user=account)

        response = self.client.delete(f"/api/magic/pose-endorsements/{endorsement.pk}/")
        self.assertEqual(response.status_code, 204)

    def test_delete_settled_returns_404(self) -> None:
        from django.utils import timezone

        from world.magic.services.gain import create_pose_endorsement

        endorser, _, _, interaction, resonance, account = self._endorser_scenario()
        endorsement = create_pose_endorsement(endorser, interaction, resonance)
        endorsement.settled_at = timezone.now()
        endorsement.granted_amount = 4
        endorsement.save(update_fields=["settled_at", "granted_amount"])
        self.client.force_authenticate(user=account)

        response = self.client.delete(f"/api/magic/pose-endorsements/{endorsement.pk}/")
        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_returns_401_or_403(self) -> None:
        _, _, _, interaction, resonance, _ = self._endorser_scenario()

        response = self.client.post(
            "/api/magic/pose-endorsements/",
            data={"interaction": interaction.pk, "resonance": resonance.pk},
            format="json",
        )
        self.assertIn(response.status_code, (401, 403))
