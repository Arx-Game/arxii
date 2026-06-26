"""Tests for the treatment-candidate discovery endpoint (#1486).

Verifies ``GET /api/conditions/treatments/?target_persona_id=<id>`` resolves the
helper via the ``X-Character-ID`` header, resolves the active scene at the
helper's location, and delegates to ``get_treatment_candidates`` (the same
service the telnet ``treat`` command uses). The candidate-listing test mirrors
the telnet test's factory setup and patches the same scene/bond/engagement gates.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.constants import TARGET_EFFECT_CONDITION, TreatmentTargetKind
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionTemplateFactory,
    TreatmentTemplateFactory,
)
from world.conditions.views import TreatmentCandidateViewSet
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)
from world.scenes.factories import SceneFactory


def _give_account_character(account, character) -> None:
    """Wire ``account`` so ``get_available_characters()`` returns ``character``.

    Mirrors the helper in ``test_condition_instance_retrieve.py``: a PlayerData
    with a RosterTenure on a RosterEntry whose CharacterSheet points at the
    character, so the roster ownership check in ``CharacterContextMixin`` passes.
    """
    player_data = PlayerDataFactory(account=account)
    roster_entry = RosterEntryFactory(character_sheet__character=character)
    RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)


class TreatmentCandidateViewTests(TestCase):
    """Tests for the TreatmentCandidateViewSet discovery endpoint."""

    def setUp(self) -> None:
        # Evennia ObjectDB fixtures must be built in setUp, not setUpTestData:
        # the idmapper's DbHolder is un-deepcopyable, so the classmethod
        # snapshot machinery raises copy.Error (the DbHolder setUpTestData trap;
        # see test_consent_commands.py for the same note).
        self.room = ObjectDBFactory(
            db_key="Clinic",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.helper_char = CharacterFactory(location=self.room)
        self.target_char = CharacterFactory(location=self.room)
        self.helper_sheet = CharacterSheetFactory(character=self.helper_char)
        self.target_sheet = CharacterSheetFactory(character=self.target_char)

        self.user = AccountFactory()
        _give_account_character(self.user, self.helper_char)

        self.condition = ConditionTemplateFactory(name="Test Ailment")
        self.treatment = TreatmentTemplateFactory(
            target_condition=self.condition,
            target_kind=TreatmentTargetKind.PRIMARY,
            requires_bond=False,
            scene_required=True,
        )
        self.instance = ConditionInstanceFactory(
            target=self.target_char,
            condition=self.condition,
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _bust_scene_cache(self) -> None:
        """Clear the per-location active-scene cache the telnet test busts."""
        if hasattr(self.room, "_active_scene_cache"):
            del self.room._active_scene_cache

    def _get(
        self,
        *,
        character_header: str | None = "present",
        target_persona_id: str | None = "present",
    ) -> object:
        """Issue a GET with the X-Character-ID header and target_persona_id.

        ``character_header``/``target_persona_id`` of ``"present"`` mean "use the
        real fixture id"; pass ``None`` to omit that param/header.
        """
        headers: dict[str, str] = {}
        if character_header == "present":
            headers["HTTP_X_CHARACTER_ID"] = str(self.helper_char.id)
        elif character_header is not None:
            headers["HTTP_X_CHARACTER_ID"] = character_header

        query = ""
        if target_persona_id == "present":
            query = f"?target_persona_id={self.target_sheet.primary_persona.id}"
        elif target_persona_id is not None:
            query = f"?target_persona_id={target_persona_id}"

        return self.client.get(f"/api/conditions/treatments/{query}", **headers)

    def test_requires_target_persona_id(self) -> None:
        """No target_persona_id param -> 400 with the required-message."""
        response = self._get(target_persona_id=None)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["detail"] == "target_persona_id is required."

    def test_unknown_target_persona_returns_404(self) -> None:
        """Bogus target_persona_id -> 404 with 'Target persona not found.'"""
        response = self._get(target_persona_id="99999999")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["detail"] == "Target persona not found."

    def test_no_character_header_returns_404(self) -> None:
        """Missing X-Character-ID header -> 404 with 'No character found.'"""
        response = self._get(character_header=None)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["detail"] == "No character found."

    def test_no_active_scene_returns_400(self) -> None:
        """Helper + target exist but no active scene at the location -> 400."""
        self._bust_scene_cache()
        response = self._get()
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["detail"] == "You are not in an active scene."

    @patch("world.conditions.services._scene_participant", return_value=True)
    @patch(
        "world.mechanics.engagement.CharacterEngagement.objects.filter",
        return_value=MagicMock(exists=MagicMock(return_value=False)),
    )
    def test_list_returns_candidates(
        self,
        mock_engagement_filter: MagicMock,
        mock_scene_participant: MagicMock,
    ) -> None:
        """Helper & target in an active scene -> 200 with one condition candidate."""
        self._bust_scene_cache()
        SceneFactory(is_active=True, location=self.room)

        response = self._get()
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["scene_id"] is not None
        candidates = response.data["candidates"]
        assert len(candidates) == 1
        candidate = candidates[0]
        assert candidate["target_effect_type"] == TARGET_EFFECT_CONDITION
        assert candidate["treatment"]["name"] == self.treatment.name
        assert candidate["target_effect"]["id"] == self.instance.id
        assert candidate["bond_thread"] is None

    def test_viewset_class_shape(self) -> None:
        """The ViewSet matches the established read-only discovery pattern."""
        from rest_framework.permissions import IsAuthenticated

        from web.api.mixins import CharacterContextMixin

        assert issubclass(TreatmentCandidateViewSet, CharacterContextMixin)
        assert issubclass(TreatmentCandidateViewSet, object)
        assert IsAuthenticated in TreatmentCandidateViewSet.permission_classes
