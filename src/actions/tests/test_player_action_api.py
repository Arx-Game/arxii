"""Tests for GET /api/actions/characters/<id>/available/ endpoint.

Covers:
- (a) Character owner GETs endpoint → 200 with paginated merged list.
- (b) Active challenge in character's room → response contains a serialized
  action with backend == "challenge", non-null check_type (id+name), correct ref.
- (c) Non-owner → 403 (IsCharacterOwner enforced).
- (d) Unauthenticated → 401/403.
- (e) Pagination envelope present.
- (f) Nonexistent character → 404.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from evennia.objects.models import ObjectDB
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.checks.factories import CheckTypeFactory
from world.mechanics.constants import DifficultyIndicator
from world.mechanics.factories import (
    ApplicationFactory,
    ChallengeApproachFactory,
    ChallengeTemplateFactory,
    PropertyFactory,
)
from world.mechanics.models import ChallengeInstance
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory

_MODERATE_DIFFICULTY_PATCH = patch(
    "world.mechanics.services._get_difficulty_indicator_for_check",
    return_value=DifficultyIndicator.MODERATE,
)


def _set_character_location(character: ObjectDB, room: ObjectDB) -> ObjectDB:
    """Set character location via raw DB update and patch the Python instance."""
    ObjectDB.objects.filter(pk=character.pk).update(db_location=room)
    character.db_location = room
    return character


def _make_challenge_setup(sheet: object, room: ObjectDB) -> tuple:
    """Wire capability + challenge + approach + technique grant so the character can act.

    Returns (challenge_instance, approach, capability, check_type).
    """
    from world.conditions.factories import CapabilityTypeFactory
    from world.magic.factories import (
        CharacterTechniqueFactory,
        TechniqueCapabilityGrantFactory,
        TechniqueFactory,
    )

    check_type = CheckTypeFactory()
    capability = CapabilityTypeFactory()
    prop = PropertyFactory()

    app = ApplicationFactory(capability=capability, target_property=prop)
    template = ChallengeTemplateFactory()
    template.properties.add(prop)

    approach = ChallengeApproachFactory(
        challenge_template=template,
        application=app,
        check_type=check_type,
        action_template=None,
    )
    challenge_instance = ChallengeInstance.objects.create(
        template=template,
        location=room,
        target_object=room,
        is_active=True,
        is_revealed=True,
    )

    technique = TechniqueFactory(damage_profile=False)
    TechniqueCapabilityGrantFactory(technique=technique, capability=capability, base_value=5)
    CharacterTechniqueFactory(character=sheet, technique=technique)

    return challenge_instance, approach, capability, check_type


class AvailableActionsViewOwnerTests(TestCase):
    """Character owner can GET available actions; basic permission and shape checks."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner_account = AccountFactory()
        cls.owner_player_data = PlayerDataFactory(account=cls.owner_account)

        cls.roster_entry = RosterEntryFactory()
        cls.character = cls.roster_entry.character_sheet.character

        cls.tenure = RosterTenureFactory(
            player_data=cls.owner_player_data,
            roster_entry=cls.roster_entry,
            start_date=timezone.now(),
            end_date=None,
        )

        cls.room = ObjectDB.objects.create(db_key="AvailActionsRoom")
        cls.other_account = AccountFactory()
        cls.staff_account = AccountFactory(is_staff=True)

    def setUp(self) -> None:
        self.client = APIClient()
        self.character.db_location = self.room
        self.character.save()

    def _url(self, character_id: int | None = None) -> str:
        cid = character_id if character_id is not None else self.character.pk
        return f"/api/actions/characters/{cid}/available/"

    def test_unauthenticated_returns_401_or_403(self) -> None:
        """Unauthenticated requests are rejected."""
        self.client.force_authenticate(user=None)
        response = self.client.get(self._url())
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_non_owner_returns_403(self) -> None:
        """Non-owners cannot access another character's available actions."""
        self.client.force_authenticate(user=self.other_account)
        response = self.client.get(self._url())
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_owner_gets_200_with_pagination_envelope(self) -> None:
        """Character owner gets a paginated 200 response."""
        self.client.force_authenticate(user=self.owner_account)
        with patch("actions.views.get_player_actions", return_value=[]):
            response = self.client.get(self._url())
        assert response.status_code == status.HTTP_200_OK
        assert "results" in response.data
        assert "count" in response.data

    def test_staff_can_access_any_character(self) -> None:
        """Staff accounts bypass IsCharacterOwner."""
        self.client.force_authenticate(user=self.staff_account)
        with patch("actions.views.get_player_actions", return_value=[]):
            response = self.client.get(self._url())
        assert response.status_code == status.HTTP_200_OK

    def test_nonexistent_character_returns_404(self) -> None:
        """Requesting actions for a non-existent character returns 404."""
        self.client.force_authenticate(user=self.staff_account)
        response = self.client.get(self._url(character_id=999999))
        assert response.status_code == status.HTTP_404_NOT_FOUND


class AvailableActionsViewChallengeShapeTests(TestCase):
    """Endpoint returns correctly-shaped serialized CHALLENGE actions.

    Verifies that active challenges with matching capability produce a
    serialized PlayerAction with the expected wire shape.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner_account = AccountFactory()
        cls.owner_player_data = PlayerDataFactory(account=cls.owner_account)

        cls.roster_entry = RosterEntryFactory()
        cls.sheet = cls.roster_entry.character_sheet
        cls.character = cls.sheet.character

        cls.tenure = RosterTenureFactory(
            player_data=cls.owner_player_data,
            roster_entry=cls.roster_entry,
            start_date=timezone.now(),
            end_date=None,
        )

        cls.room = ObjectDB.objects.create(db_key="ChallengeShapeRoom")

        cls.challenge_instance, cls.approach, cls.capability, cls.check_type = (
            _make_challenge_setup(cls.sheet, cls.room)
        )

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner_account)
        # Persist character location via save() to match how mechanics tests set location.
        self.character.db_location = self.room
        self.character.save()
        self._difficulty_patch = _MODERATE_DIFFICULTY_PATCH
        self._difficulty_patch.start()

    def tearDown(self) -> None:
        self._difficulty_patch.stop()

    def _url(self) -> str:
        return f"/api/actions/characters/{self.character.pk}/available/"

    def test_response_contains_challenge_action(self) -> None:
        """Response contains at least one action with backend == 'challenge'."""
        response = self.client.get(self._url())
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        backends = [r["backend"] for r in results]
        assert "challenge" in backends, f"Expected 'challenge' backend in {backends}"

    def test_challenge_action_has_check_type_id_and_name(self) -> None:
        """Serialized CHALLENGE action has check_type with id and name."""
        response = self.client.get(self._url())
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        challenge_results = [r for r in results if r["backend"] == "challenge"]
        assert len(challenge_results) >= 1
        action = challenge_results[0]
        assert "check_type" in action
        check_type_data = action["check_type"]
        assert "id" in check_type_data
        assert "name" in check_type_data
        assert check_type_data["id"] == self.check_type.pk

    def test_challenge_action_ref_has_expected_fields(self) -> None:
        """Serialized CHALLENGE action has ref with backend, challenge_instance_id, approach_id."""
        response = self.client.get(self._url())
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        challenge_results = [r for r in results if r["backend"] == "challenge"]
        assert len(challenge_results) >= 1
        action = challenge_results[0]
        assert "ref" in action
        ref = action["ref"]
        assert ref["backend"] == "challenge"
        assert ref["challenge_instance_id"] == self.challenge_instance.pk
        assert ref["approach_id"] == self.approach.pk

    def test_challenge_action_null_action_template(self) -> None:
        """Plain approach produces null action_template in the response."""
        response = self.client.get(self._url())
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        challenge_results = [r for r in results if r["backend"] == "challenge"]
        assert len(challenge_results) >= 1
        action = challenge_results[0]
        assert action["action_template"] is None

    def test_challenge_action_prerequisite_met_true(self) -> None:
        """prerequisite_met is True (character has the capability)."""
        response = self.client.get(self._url())
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        challenge_results = [r for r in results if r["backend"] == "challenge"]
        assert len(challenge_results) >= 1
        action = challenge_results[0]
        assert "prerequisite_met" in action
        assert action["prerequisite_met"] is True

    def test_response_has_display_name_and_description(self) -> None:
        """Serialized action has display_name and description fields."""
        response = self.client.get(self._url())
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        challenge_results = [r for r in results if r["backend"] == "challenge"]
        assert len(challenge_results) >= 1
        action = challenge_results[0]
        assert "display_name" in action
        assert "description" in action
        assert "prerequisite_reasons" in action
