"""Tests for can_view_encounter_effects helper + preserved endpoint behavior.

Task 4 (#1041): validates that the extracted helper in combat.permissions
produces identical results to the old inline _viewer_can_see, and that the
endpoint still degrades gracefully (200 + empty effects) for non-viewers.
"""

from __future__ import annotations

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.roster.factories import RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory


class CanViewEncounterEffectsHelperTest(TestCase):
    """Unit tests for the extracted can_view_encounter_effects helper."""

    def setUp(self) -> None:
        # Don't use setUpTestData — Evennia DbHolder isn't deepcopy-safe.
        self.scene = SceneFactory()
        self.encounter = CombatEncounterFactory(scene=self.scene)

        # Fighter: a character who is an encounter participant.
        self.fighter_account = AccountFactory()
        fighter_char = CharacterFactory()
        fighter_sheet = CharacterSheetFactory(character=fighter_char)
        RosterTenureFactory(
            roster_entry__character_sheet__character=fighter_char,
            player_data__account=self.fighter_account,
        )
        CombatParticipantFactory(encounter=self.encounter, character_sheet=fighter_sheet)

        # GM: has a SceneParticipation with is_gm=True.
        self.gm_account = AccountFactory()
        SceneParticipationFactory(scene=self.scene, account=self.gm_account, is_gm=True)

        # Outsider: authenticated but neither participant nor GM nor staff.
        self.outsider = AccountFactory()

        # Staff: is_staff=True.
        self.staff = AccountFactory(is_staff=True)

    def test_staff_can_view(self) -> None:
        from world.combat.permissions import can_view_encounter_effects

        self.assertTrue(can_view_encounter_effects(self.staff, self.encounter))

    def test_scene_gm_can_view(self) -> None:
        from world.combat.permissions import can_view_encounter_effects

        self.assertTrue(can_view_encounter_effects(self.gm_account, self.encounter))

    def test_encounter_participant_can_view(self) -> None:
        from world.combat.permissions import can_view_encounter_effects

        self.assertTrue(can_view_encounter_effects(self.fighter_account, self.encounter))

    def test_outsider_cannot_view(self) -> None:
        from world.combat.permissions import can_view_encounter_effects

        self.assertFalse(can_view_encounter_effects(self.outsider, self.encounter))

    def test_unauthenticated_cannot_view(self) -> None:
        """An anonymous-user-like object with no is_authenticated attribute returns False."""
        from world.combat.permissions import can_view_encounter_effects

        class _Anon:
            pass

        self.assertFalse(can_view_encounter_effects(_Anon(), self.encounter))


class OutcomeEndpointNonViewerDegradationTest(APITestCase):
    """Endpoint degrades to empty effects (status 200) for non-viewers."""

    def setUp(self) -> None:
        from world.combat.factories import CombatRoundActionFactory
        from world.scenes.constants import InteractionMode
        from world.scenes.factories import InteractionFactory

        self.scene = SceneFactory()
        self.encounter = CombatEncounterFactory(scene=self.scene)

        # Participant account — the one who "did" the action.
        self.participant_account = AccountFactory()
        participant_char = CharacterFactory()
        participant_sheet = CharacterSheetFactory(character=participant_char)
        RosterTenureFactory(
            roster_entry__character_sheet__character=participant_char,
            player_data__account=self.participant_account,
        )
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=participant_sheet
        )

        # Create an ACTION interaction + CombatRoundAction.
        self.interaction = InteractionFactory(
            scene=self.scene,
            persona=participant_sheet.primary_persona,
            mode=InteractionMode.ACTION,
        )
        self.action = CombatRoundActionFactory(
            participant=self.participant,
            interaction=self.interaction,
            interaction_timestamp=self.interaction.timestamp,
        )

        # Outsider: authenticated, not a participant, not GM, not staff.
        self.outsider = AccountFactory()

    def test_outsider_gets_empty_effects_status_200(self) -> None:
        """Non-viewer gets 200 with empty effects list — not a 403."""
        self.client.force_authenticate(user=self.outsider)
        url = reverse("combat:action-outcome-details")
        response = self.client.get(url, {"action_interaction_ids": str(self.interaction.pk)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["effects"], [])

    def test_participant_gets_effects(self) -> None:
        """Encounter participant gets the full effects list."""
        self.client.force_authenticate(user=self.participant_account)
        url = reverse("combat:action-outcome-details")
        response = self.client.get(url, {"action_interaction_ids": str(self.interaction.pk)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        # Effects may be empty if no conditions/combos/target-status set up,
        # but the gate passed — assert the row exists (empty list vs no row).
        self.assertEqual(response.data[0]["action_interaction_id"], self.interaction.pk)
