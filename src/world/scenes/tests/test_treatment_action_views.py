"""Tests for the treat-condition web execution endpoint (#1486 Task 6).

Verifies ``POST /api/action-requests/`` with ``action_key="treat_condition"``
creates a pending ``SceneActionRequest`` with the treatment FKs set, the
submitted candidate pair is validated against ``get_treatment_candidates`` (so a
fabricated pair is rejected), and the treatment fields are only valid for the
``treat_condition`` action key. Mirrors the telnet + Task 5 test factory setup
and patches the same scene/bond/engagement gates.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.constants import TreatmentTargetKind
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionTemplateFactory,
    TreatmentTemplateFactory,
)
from world.magic.factories import PendingAlterationFactory, ThreadFactory
from world.roster.factories import (
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)
from world.scenes.action_constants import ActionRequestStatus
from world.scenes.action_models import SceneActionRequest
from world.scenes.factories import SceneFactory


def _field_messages(value) -> list[str]:
    """Normalize a DRF ValidationError field value to a list of strings.

    A single message string is wrapped; a list of messages is passed through.
    """
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value]


def _give_account_character(account, character) -> None:
    """Wire ``account`` so ``get_account_personas`` returns the character's persona.

    Mirrors the helper in test_treatment_views.py: a PlayerData with a RosterTenure
    on a RosterEntry whose CharacterSheet points at the character.
    """
    player_data = PlayerDataFactory(account=account)
    roster_entry = RosterEntryFactory(character_sheet__character=character)
    RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)


class TreatConditionActionViewTests(TestCase):
    """Tests for POST /api/action-requests/ with action_key=treat_condition."""

    def setUp(self) -> None:
        # Evennia ObjectDB fixtures must be built in setUp, not setUpTestData:
        # the idmapper's DbHolder is un-deepcopyable, so the classmethod
        # snapshot machinery raises copy.Error (the DbHolder setUpTestData trap;
        # see test_treatment_views.py for the same note).
        self.room = ObjectDBFactory(
            db_key="Clinic",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.helper_char = CharacterFactory(location=self.room)
        self.target_char = CharacterFactory(location=self.room)
        self.helper_sheet = CharacterSheetFactory(character=self.helper_char)
        self.target_sheet = CharacterSheetFactory(character=self.target_char)

        self.account = AccountFactory()
        _give_account_character(self.account, self.helper_char)

        self.scene = SceneFactory(is_active=True, location=self.room)
        # Bust the per-location active-scene cache.
        if hasattr(self.room, "_active_scene_cache"):
            del self.room._active_scene_cache

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
        self.client.force_authenticate(user=self.account)
        self.url = reverse("sceneactionrequest-list")

    def _treat_payload(self, **overrides) -> dict:
        """Build a minimal treat_condition POST payload."""
        payload: dict = {
            "scene": self.scene.pk,
            "initiator_persona": self.helper_sheet.primary_persona.pk,
            "target_persona": self.target_sheet.primary_persona.pk,
            "action_key": "treat_condition",
            "treatment_id": self.treatment.pk,
            "target_condition_instance_id": self.instance.pk,
        }
        payload.update(overrides)
        return payload

    @patch("world.conditions.services._scene_participant", return_value=True)
    @patch(
        "world.mechanics.engagement.CharacterEngagement.objects.filter",
        return_value=MagicMock(exists=MagicMock(return_value=False)),
    )
    def test_create_treatment_request_sets_fks(
        self,
        mock_engagement_filter: MagicMock,
        mock_scene_participant: MagicMock,
    ) -> None:
        """POST a valid candidate -> 201 with treatment FKs set, status PENDING."""
        response = self.client.post(self.url, self._treat_payload(), format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data

        request = SceneActionRequest.objects.get(pk=response.data["id"])
        assert request.action_key == "treat_condition"
        assert request.status == ActionRequestStatus.PENDING
        assert request.treatment_id == self.treatment.pk
        assert request.target_condition_instance_id == self.instance.pk
        assert request.target_pending_alteration_id is None
        # requires_bond=False -> no bond thread selected by the candidate query.
        assert request.thread_used_id is None

    @patch("world.conditions.services._scene_participant", return_value=True)
    @patch(
        "world.mechanics.engagement.CharacterEngagement.objects.filter",
        return_value=MagicMock(exists=MagicMock(return_value=False)),
    )
    def test_rejects_fabricated_treatment_pair(
        self,
        mock_engagement_filter: MagicMock,
        mock_scene_participant: MagicMock,
    ) -> None:
        """POST a treatment_id + instance that is NOT a valid candidate -> 400.

        A TreatmentTemplate whose target_condition doesn't match the instance's
        condition means get_treatment_candidates returns no match for that pair.
        This is the security gate test — it MUST fail without candidate validation.
        """
        other_condition = ConditionTemplateFactory(name="Unrelated Ailment")
        # A treatment that targets a DIFFERENT condition than the instance has.
        other_treatment = TreatmentTemplateFactory(
            target_condition=other_condition,
            target_kind=TreatmentTargetKind.PRIMARY,
            requires_bond=False,
            scene_required=True,
        )
        payload = self._treat_payload(treatment_id=other_treatment.pk)
        response = self.client.post(self.url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "treatment" in response.data
        treatment_msg = _field_messages(response.data["treatment"])
        assert any("not available for this target" in m for m in treatment_msg), treatment_msg

    @patch("world.conditions.services._scene_participant", return_value=True)
    @patch(
        "world.mechanics.engagement.CharacterEngagement.objects.filter",
        return_value=MagicMock(exists=MagicMock(return_value=False)),
    )
    def test_non_treat_action_with_treatment_fields_rejected(
        self,
        mock_engagement_filter: MagicMock,
        mock_scene_participant: MagicMock,
    ) -> None:
        """POST a non-treat action carrying ANY treatment field -> 400.

        All four treatment fields (treatment_id, target_condition_instance_id,
        target_pending_alteration_id, bond_thread_id) are only meaningful for
        treat_condition. The base payload already carries treatment_id +
        target_condition_instance_id, so this one POST exercises the folded guard.
        """
        payload = self._treat_payload(action_key="intimidate")
        response = self.client.post(self.url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "treatment_fields" in response.data
        msgs = _field_messages(response.data["treatment_fields"])
        assert any("only valid for treat_condition" in m for m in msgs), msgs

    @patch("world.conditions.services._scene_participant", return_value=True)
    @patch(
        "world.mechanics.engagement.CharacterEngagement.objects.filter",
        return_value=MagicMock(exists=MagicMock(return_value=False)),
    )
    def test_treat_requires_exactly_one_target_effect(
        self,
        mock_engagement_filter: MagicMock,
        mock_scene_participant: MagicMock,
    ) -> None:
        """POST treat_condition + treatment_id but NEITHER target effect id -> 400."""
        payload = self._treat_payload()
        del payload["target_condition_instance_id"]
        response = self.client.post(self.url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "target_effect" in response.data

    @patch("world.conditions.services._scene_participant", return_value=True)
    @patch(
        "world.mechanics.engagement.CharacterEngagement.objects.filter",
        return_value=MagicMock(exists=MagicMock(return_value=False)),
    )
    def test_treat_with_both_target_effect_ids_rejected(
        self,
        mock_engagement_filter: MagicMock,
        mock_scene_participant: MagicMock,
    ) -> None:
        """POST treat_condition + treatment_id + BOTH target effect ids -> 400."""
        payload = self._treat_payload(target_pending_alteration_id=999)
        response = self.client.post(self.url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "target_effect" in response.data

    @patch("world.conditions.services._scene_participant", return_value=True)
    @patch(
        "world.mechanics.engagement.CharacterEngagement.objects.filter",
        return_value=MagicMock(exists=MagicMock(return_value=False)),
    )
    def test_treat_without_treatment_id_rejected(
        self,
        mock_engagement_filter: MagicMock,
        mock_scene_participant: MagicMock,
    ) -> None:
        """POST treat_condition with no treatment_id -> 400."""
        payload = self._treat_payload()
        del payload["treatment_id"]
        response = self.client.post(self.url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "treatment_id" in response.data
        tid_msg = _field_messages(response.data["treatment_id"])
        assert any("requires a treatment_id" in m for m in tid_msg), tid_msg

    @patch("world.conditions.services._scene_participant", return_value=True)
    @patch(
        "world.mechanics.engagement.CharacterEngagement.objects.filter",
        return_value=MagicMock(exists=MagicMock(return_value=False)),
    )
    def test_treat_without_target_persona_rejected(
        self,
        mock_engagement_filter: MagicMock,
        mock_scene_participant: MagicMock,
    ) -> None:
        """POST treat_condition with no target_persona -> 400 (heal-another requires a target)."""
        payload = self._treat_payload()
        del payload["target_persona"]
        response = self.client.post(self.url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "target_persona" in response.data

    @patch("world.conditions.services._scene_participant", return_value=True)
    @patch("world.conditions.services._thread_anchors_to_character", return_value=True)
    @patch(
        "world.mechanics.engagement.CharacterEngagement.objects.filter",
        return_value=MagicMock(exists=MagicMock(return_value=False)),
    )
    def test_thread_used_from_matched_candidate_not_client_bond(
        self,
        mock_engagement_filter: MagicMock,
        mock_thread_anchors: MagicMock,
        mock_scene_participant: MagicMock,
    ) -> None:
        """requires_bond=True -> thread_used comes from the matched candidate.

        Builds a treatment requiring a bond and a Thread owned by the helper.
        get_treatment_candidates anchors the thread to the target via
        _thread_anchors_to_character (patched True), so the candidate carries a
        real bond_thread. The POST body sends a DIFFERENT bond_thread_id — the
        client-supplied id MUST be ignored; the request uses the candidate's
        thread, proving provenance cannot be forged.
        """
        bond_treatment = TreatmentTemplateFactory(
            target_condition=self.condition,
            target_kind=TreatmentTargetKind.PRIMARY,
            requires_bond=True,
            scene_required=True,
        )
        matched_thread = ThreadFactory(owner=self.helper_sheet)

        # A different thread's id in the POST body; the view must ignore it.
        decoy_thread = ThreadFactory(owner=self.helper_sheet)
        payload = self._treat_payload(
            treatment_id=bond_treatment.pk,
            bond_thread_id=decoy_thread.pk,
        )
        response = self.client.post(self.url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data

        request = SceneActionRequest.objects.get(pk=response.data["id"])
        assert request.treatment_id == bond_treatment.pk
        assert request.target_condition_instance_id == self.instance.pk
        # The matched candidate's thread, NOT the client-supplied decoy.
        assert request.thread_used_id == matched_thread.pk
        assert request.thread_used_id != decoy_thread.pk

    @patch("world.conditions.services._scene_participant", return_value=True)
    @patch(
        "world.mechanics.engagement.CharacterEngagement.objects.filter",
        return_value=MagicMock(exists=MagicMock(return_value=False)),
    )
    def test_treat_targets_pending_alteration_branch(
        self,
        mock_engagement_filter: MagicMock,
        mock_scene_participant: MagicMock,
    ) -> None:
        """target_kind=PENDING_ALTERATION -> target_pending_alteration FK set.

        Builds a PendingAlteration (status OPEN) on the target's sheet and a
        treatment whose target_kind is PENDING_ALTERATION, then POSTs
        treatment_id + target_pending_alteration_id. The candidate query
        returns this pair (alterations are matched on character + OPEN status,
        not on target_condition); the created request carries the alteration FK
        and leaves target_condition_instance None.
        """
        alteration = PendingAlterationFactory(character=self.target_sheet)
        alteration_treatment = TreatmentTemplateFactory(
            target_kind=TreatmentTargetKind.PENDING_ALTERATION,
            requires_bond=False,
            scene_required=True,
        )
        payload = self._treat_payload(
            treatment_id=alteration_treatment.pk,
            target_pending_alteration_id=alteration.pk,
        )
        # The base payload carries target_condition_instance_id; the alteration
        # branch requires the alteration id alone, so drop the condition id.
        del payload["target_condition_instance_id"]
        response = self.client.post(self.url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data

        request = SceneActionRequest.objects.get(pk=response.data["id"])
        assert request.treatment_id == alteration_treatment.pk
        assert request.target_pending_alteration_id == alteration.pk
        assert request.target_condition_instance_id is None
        assert request.thread_used_id is None
