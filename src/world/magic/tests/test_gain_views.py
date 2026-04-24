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


class SceneEntryEndorsementViewTests(APITestCase):
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

    def _scenario(self):
        """Build endorser + endorsee + scene + entry interaction + claimed resonance."""
        from world.magic.services.gain import account_for_sheet
        from world.scenes.constants import PoseKind

        endorser_tenure = self.RosterTenureFactory()
        endorser_sheet = endorser_tenure.roster_entry.character_sheet
        endorsee_tenure = self.RosterTenureFactory()
        endorsee_sheet = endorsee_tenure.roster_entry.character_sheet

        scene = self.SceneFactory()
        endorser_account = account_for_sheet(endorser_sheet)
        self.SceneParticipationFactory(scene=scene, account=endorser_account)

        resonance = self.ResonanceFactory()
        self.CharacterResonanceFactory(character_sheet=endorsee_sheet, resonance=resonance)

        self.InteractionFactory(
            scene=scene,
            persona=endorsee_sheet.primary_persona,
            pose_kind=PoseKind.ENTRY,
        )

        return endorser_sheet, endorsee_sheet, scene, resonance, endorser_account

    def test_create_happy_path(self) -> None:
        from world.magic.models import SceneEntryEndorsement

        _, endorsee, scene, resonance, account = self._scenario()
        self.client.force_authenticate(user=account)

        response = self.client.post(
            "/api/magic/scene-entry-endorsements/",
            data={
                "endorsee_sheet": endorsee.pk,
                "scene": scene.pk,
                "resonance": resonance.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(SceneEntryEndorsement.objects.count(), 1)

    def test_create_missing_entry_pose_returns_400(self) -> None:
        from world.scenes.models import Interaction

        _, endorsee, scene, resonance, account = self._scenario()
        # Nuke the entry pose
        Interaction.objects.filter(scene=scene).delete()
        self.client.force_authenticate(user=account)

        response = self.client.post(
            "/api/magic/scene-entry-endorsements/",
            data={
                "endorsee_sheet": endorsee.pk,
                "scene": scene.pk,
                "resonance": resonance.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_delete_not_supported(self) -> None:
        """Scene entry endorsements are immutable — DELETE deferred."""
        from world.magic.services.gain import create_scene_entry_endorsement

        endorser, endorsee, scene, resonance, account = self._scenario()
        endorsement = create_scene_entry_endorsement(endorser, endorsee, scene, resonance)
        self.client.force_authenticate(user=account)

        response = self.client.delete(f"/api/magic/scene-entry-endorsements/{endorsement.pk}/")
        # Create-only viewset — DELETE returns 405 Method Not Allowed
        self.assertEqual(response.status_code, 405)


class ResonanceGrantListTests(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.magic.factories import ResonanceFactory
        from world.roster.factories import RosterTenureFactory

        cls.CharacterSheetFactory = CharacterSheetFactory
        cls.RosterTenureFactory = RosterTenureFactory
        cls.ResonanceFactory = ResonanceFactory

    def _account_with_grant(self):
        """Build account + sheet with one staff-grant row."""
        from world.magic.constants import GainSource
        from world.magic.services.gain import account_for_sheet
        from world.magic.services.resonance import grant_resonance

        tenure = self.RosterTenureFactory()
        sheet = tenure.roster_entry.character_sheet
        account = account_for_sheet(sheet)
        resonance = self.ResonanceFactory()
        grant_resonance(sheet, resonance, 5, source=GainSource.STAFF_GRANT)
        return account, sheet, resonance

    def test_user_sees_own_grants(self) -> None:
        account, _, _ = self._account_with_grant()
        self.client.force_authenticate(user=account)

        response = self.client.get("/api/magic/resonance-grants/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Paginated: either {results: [...]} or a list
        results = data["results"] if isinstance(data, dict) and "results" in data else data
        self.assertEqual(len(results), 1)

    def test_user_does_not_see_others_grants(self) -> None:
        # Set up two accounts, each with a grant
        alice_account, _, _ = self._account_with_grant()
        bob_account, _, _ = self._account_with_grant()

        # Alice's view
        self.client.force_authenticate(user=alice_account)
        response = self.client.get("/api/magic/resonance-grants/")
        data = response.json()
        results = data["results"] if isinstance(data, dict) and "results" in data else data
        self.assertEqual(len(results), 1)
        # Bob's view
        self.client.force_authenticate(user=bob_account)
        response = self.client.get("/api/magic/resonance-grants/")
        data = response.json()
        results = data["results"] if isinstance(data, dict) and "results" in data else data
        self.assertEqual(len(results), 1)

    def test_filter_by_source(self) -> None:
        from world.magic.constants import GainSource
        from world.magic.factories import RoomAuraProfileFactory
        from world.magic.services.resonance import grant_resonance

        account, sheet, resonance = self._account_with_grant()
        # Add a second grant of a different source
        aura = RoomAuraProfileFactory()
        grant_resonance(
            sheet,
            resonance,
            1,
            source=GainSource.ROOM_RESIDENCE,
            room_aura_profile=aura,
        )

        self.client.force_authenticate(user=account)
        response = self.client.get("/api/magic/resonance-grants/?source=STAFF_GRANT")
        data = response.json()
        results = data["results"] if isinstance(data, dict) and "results" in data else data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "STAFF_GRANT")

    def test_staff_sees_all(self) -> None:
        self._account_with_grant()  # Alice's grant
        self._account_with_grant()  # Bob's grant

        from evennia.accounts.models import AccountDB

        staff = AccountDB.objects.create_superuser(
            "specc_staff_admin", "staff@example.com", "password"
        )
        self.client.force_authenticate(user=staff)

        response = self.client.get("/api/magic/resonance-grants/")
        data = response.json()
        results = data["results"] if isinstance(data, dict) and "results" in data else data
        self.assertEqual(len(results), 2)

    def test_delete_not_supported(self) -> None:
        account, _, _ = self._account_with_grant()
        self.client.force_authenticate(user=account)

        response = self.client.get("/api/magic/resonance-grants/")
        data = response.json()
        results = data["results"] if isinstance(data, dict) and "results" in data else data
        grant_pk = results[0]["id"]

        response = self.client.delete(f"/api/magic/resonance-grants/{grant_pk}/")
        self.assertEqual(response.status_code, 405)
