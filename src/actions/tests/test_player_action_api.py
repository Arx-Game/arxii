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
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.mechanics.constants import DifficultyIndicator
from world.mechanics.factories import (
    ApplicationFactory,
    ChallengeApproachFactory,
    ChallengeTemplateConsequenceFactory,
    ChallengeTemplateFactory,
    PropertyFactory,
)
from world.mechanics.models import ChallengeInstance, CharacterChallengeRecord
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.traits.factories import CheckOutcomeFactory

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

    Also creates a CheckOutcome + Consequence attached to the template so that
    resolve_challenge() can select a consequence when perform_check is patched.

    Returns (challenge_instance, approach, capability, check_type, outcome, consequence).
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

    from world.mechanics.constants import ResolutionType

    outcome = CheckOutcomeFactory(success_level=1)
    consequence = ConsequenceFactory(outcome_tier=outcome, label="Test consequence")
    ChallengeTemplateConsequenceFactory(
        challenge_template=template,
        consequence=consequence,
        resolution_type=ResolutionType.PERSONAL,  # keep challenge active; avoids DESTROY
    )

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

    return challenge_instance, approach, capability, check_type, outcome, consequence


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

        cls.challenge_instance, cls.approach, cls.capability, cls.check_type, _, _ = (
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


# ---------------------------------------------------------------------------
# Dispatch endpoint tests — POST /api/actions/characters/<id>/dispatch/
# ---------------------------------------------------------------------------


class DispatchActionViewPermissionTests(TestCase):
    """Permission checks for the dispatch endpoint."""

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

        cls.room = ObjectDB.objects.create(db_key="DispatchPermRoom")
        cls.other_account = AccountFactory()
        cls.staff_account = AccountFactory(is_staff=True)

    def setUp(self) -> None:
        self.client = APIClient()
        self.character.db_location = self.room
        self.character.save()

    def _url(self, character_id: int | None = None) -> str:
        cid = character_id if character_id is not None else self.character.pk
        return f"/api/actions/characters/{cid}/dispatch/"

    def _valid_ref_payload(self) -> dict:
        return {
            "ref": {
                "backend": "challenge",
                "challenge_instance_id": 999,
                "approach_id": 999,
            },
            "kwargs": {},
        }

    def test_unauthenticated_returns_401_or_403(self) -> None:
        """Unauthenticated requests are rejected."""
        self.client.force_authenticate(user=None)
        response = self.client.post(self._url(), self._valid_ref_payload(), format="json")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_non_owner_returns_403(self) -> None:
        """Non-owners cannot dispatch actions for another character."""
        self.client.force_authenticate(user=self.other_account)
        response = self.client.post(self._url(), self._valid_ref_payload(), format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_nonexistent_character_returns_404(self) -> None:
        """Dispatching for a non-existent character returns 404."""
        self.client.force_authenticate(user=self.staff_account)
        response = self.client.post(
            self._url(character_id=999999), self._valid_ref_payload(), format="json"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


class DispatchActionViewChallengeTests(TestCase):
    """Owner dispatches a CHALLENGE action — immediate resolution, real side effect."""

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

        cls.room = ObjectDB.objects.create(db_key="DispatchChallengeRoom")

        (
            cls.challenge_instance,
            cls.approach,
            cls.capability,
            cls.check_type,
            cls.outcome,
            cls.consequence,
        ) = _make_challenge_setup(cls.sheet, cls.room)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner_account)
        self.character.db_location = self.room
        self.character.save()
        # SharedMemoryModel identity map doesn't invalidate on TestCase savepoint rollback.
        # Refresh challenge_instance so is_active reflects the DB-rolled-back state
        # (prevents "Challenge is not active" from prior test's DESTROY resolution).
        self.challenge_instance.refresh_from_db()
        from unittest.mock import patch as _patch

        from world.mechanics.constants import DifficultyIndicator

        self._difficulty_patch = _patch(
            "world.mechanics.services._get_difficulty_indicator_for_check",
            return_value=DifficultyIndicator.MODERATE,
        )
        self._difficulty_patch.start()

    def tearDown(self) -> None:
        self._difficulty_patch.stop()

    def _make_check_result(self) -> object:
        """Build a minimal CheckResult for patching perform_check."""
        from world.checks.types import CheckResult

        return CheckResult(
            check_type=self.check_type,
            outcome=self.outcome,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

    def _url(self) -> str:
        return f"/api/actions/characters/{self.character.pk}/dispatch/"

    def _challenge_payload(self) -> dict:
        return {
            "ref": {
                "backend": "challenge",
                "challenge_instance_id": self.challenge_instance.pk,
                "approach_id": self.approach.pk,
            },
            "kwargs": {},
        }

    @patch("world.mechanics.challenge_resolution.perform_check")
    def test_challenge_dispatch_returns_200(self, mock_check: object) -> None:
        """Owner POSTs a valid CHALLENGE ref → 200 with dispatch result."""
        mock_check.return_value = self._make_check_result()  # type: ignore[attr-defined]
        response = self.client.post(self._url(), self._challenge_payload(), format="json")
        assert response.status_code == status.HTTP_200_OK

    @patch("world.mechanics.challenge_resolution.perform_check")
    def test_challenge_dispatch_deferred_false(self, mock_check: object) -> None:
        """Outside a declaring round, CHALLENGE dispatch is immediate (deferred=False)."""
        mock_check.return_value = self._make_check_result()  # type: ignore[attr-defined]
        response = self.client.post(self._url(), self._challenge_payload(), format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["deferred"] is False

    @patch("world.mechanics.challenge_resolution.perform_check")
    def test_challenge_dispatch_backend_in_response(self, mock_check: object) -> None:
        """Response contains backend field matching the dispatch backend."""
        mock_check.return_value = self._make_check_result()  # type: ignore[attr-defined]
        response = self.client.post(self._url(), self._challenge_payload(), format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["backend"] == "challenge"

    @patch("world.mechanics.challenge_resolution.perform_check")
    def test_challenge_dispatch_real_side_effect(self, mock_check: object) -> None:
        """Dispatching a CHALLENGE routes through real resolve_challenge and creates a DB record.

        Patches perform_check (requires real trait/rank DB rows not in this test's scope)
        but asserts the real side effect: a CharacterChallengeRecord row is created, which
        confirms dispatch_player_action → resolve_challenge routing actually ran.
        """
        mock_check.return_value = self._make_check_result()  # type: ignore[attr-defined]

        record_count_before = CharacterChallengeRecord.objects.filter(
            character=self.character,
            challenge_instance=self.challenge_instance,
        ).count()

        response = self.client.post(self._url(), self._challenge_payload(), format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["deferred"] is False
        assert response.data["backend"] == "challenge"

        # Real side effect: CharacterChallengeRecord was created
        record_count_after = CharacterChallengeRecord.objects.filter(
            character=self.character,
            challenge_instance=self.challenge_instance,
        ).count()
        assert record_count_after == record_count_before + 1

    def test_invalid_ref_missing_challenge_instance_id_returns_400(self) -> None:
        """Ref with backend=challenge but no challenge_instance_id → 400 (serializer validates)."""
        payload = {
            "ref": {"backend": "challenge"},
            "kwargs": {},
        }
        response = self.client.post(self._url(), payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # Response should NOT contain raw exception text
        body = str(response.data)
        assert "Traceback" not in body
        assert "ValueError" not in body

    def test_invalid_ref_returns_safe_message(self) -> None:
        """Invalid ref response carries the ActionDispatchError safe message, not str(exc)."""
        from actions.errors import ActionDispatchError

        payload = {
            "ref": {"backend": "challenge"},
            "kwargs": {},
        }
        response = self.client.post(self._url(), payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        expected_msg = ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF).user_message
        body_str = str(response.data)
        assert expected_msg in body_str

    def test_stale_ref_unknown_ids_returns_400_with_safe_message(self) -> None:
        """Valid shape but non-existent ids → 400 with UNKNOWN_ACTION_REF safe message."""
        from actions.errors import ActionDispatchError

        payload = {
            "ref": {
                "backend": "challenge",
                "challenge_instance_id": 999999,
                "approach_id": 999999,
            },
            "kwargs": {},
        }
        response = self.client.post(self._url(), payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert (
            response.data["detail"]
            == ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF).user_message
        )


class DispatchActionViewCombatTests(TestCase):
    """Owner in a DECLARING round dispatches a COMBAT action — deferred, real DB row."""

    @classmethod
    def setUpTestData(cls) -> None:
        from actions.factories import ActionTemplateFactory
        from world.combat.constants import EncounterStatus, ParticipantStatus
        from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
        from world.magic.factories import (
            BinaryEffectTypeFactory,
            CharacterTechniqueFactory,
            TechniqueFactory,
        )

        cls.owner_account = AccountFactory()
        cls.owner_player_data = PlayerDataFactory(account=cls.owner_account)

        cls.encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        cls.participant = CombatParticipantFactory(
            encounter=cls.encounter,
            status=ParticipantStatus.ACTIVE,
        )
        cls.sheet = cls.participant.character_sheet
        cls.character = cls.sheet.character

        cls.roster_entry = RosterEntryFactory(character_sheet=cls.sheet)
        cls.tenure = RosterTenureFactory(
            player_data=cls.owner_player_data,
            roster_entry=cls.roster_entry,
            start_date=timezone.now(),
            end_date=None,
        )

        from world.vitals.models import CharacterVitals

        # CharacterVitals required by declare_action (status check)
        CharacterVitals.objects.get_or_create(
            character_sheet=cls.sheet,
            defaults={"health": 100, "max_health": 100},
        )

        cls.check_type = CheckTypeFactory()
        cls.action_template = ActionTemplateFactory(check_type=cls.check_type)
        # BinaryEffectTypeFactory (base_power=None) — avoid "damage technique requires
        # focused_opponent_target" validation in declare_action (line 863 services.py).
        cls.technique = TechniqueFactory(
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=cls.action_template,
        )
        CharacterTechniqueFactory(character=cls.sheet, technique=cls.technique)

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner_account)

    def _url(self) -> str:
        return f"/api/actions/characters/{self.character.pk}/dispatch/"

    def _combat_payload(self) -> dict:
        return {
            "ref": {
                "backend": "combat",
                "technique_id": self.technique.pk,
            },
            "kwargs": {"effort_level": 1},
        }

    def test_combat_dispatch_returns_200_deferred(self) -> None:
        """Owner in DECLARING round dispatches COMBAT → 200, deferred=True."""
        response = self.client.post(self._url(), self._combat_payload(), format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["deferred"] is True

    def test_combat_dispatch_creates_round_action_row(self) -> None:
        """Dispatching COMBAT creates a CombatRoundAction row for the participant+round."""
        from world.combat.models import CombatRoundAction

        initial_count = CombatRoundAction.objects.filter(
            participant=self.participant,
            round_number=self.encounter.round_number,
        ).count()

        response = self.client.post(self._url(), self._combat_payload(), format="json")
        assert response.status_code == status.HTTP_200_OK

        final_count = CombatRoundAction.objects.filter(
            participant=self.participant,
            round_number=self.encounter.round_number,
        ).count()
        assert final_count == initial_count + 1

    def test_combat_dispatch_backend_in_response(self) -> None:
        """Response backend matches the dispatched backend."""
        # Clear any prior declaration from test_combat_dispatch_creates_round_action_row
        from world.combat.models import CombatRoundAction

        CombatRoundAction.objects.filter(
            participant=self.participant,
            round_number=self.encounter.round_number,
        ).delete()

        response = self.client.post(self._url(), self._combat_payload(), format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["backend"] == "combat"
