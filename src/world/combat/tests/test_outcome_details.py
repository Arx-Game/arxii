"""Tests for GET /api/combat/action-outcome-details/

Phase 5 (combat-resolution-loop): outcome details are derived from existing
models (combo, conditions via correlation, target status) — no audit tables.
"""

from __future__ import annotations

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.combat.factories import ClashContributionFactory, ClashRoundFactory
from world.magic.types.power_ledger import PowerLedgerBuilder
from world.scenes.constants import InteractionMode
from world.scenes.factories import InteractionFactory
from world.scenes.power_ledger_services import persist_power_ledger


class ActionOutcomeDetailsViewTests(APITestCase):
    """GET /api/combat/action-outcome-details/ returns a list of outcome details."""

    def setUp(self) -> None:
        # Don't use setUpTestData — Evennia DbHolder isn't deepcopy-safe.
        self.account = AccountFactory()
        self.client.force_authenticate(user=self.account)

    def test_returns_empty_list_when_no_ids_given(self) -> None:
        url = reverse("combat:action-outcome-details")
        response = self.client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_returns_one_row_per_action_id(self) -> None:
        url = reverse("combat:action-outcome-details")
        response = self.client.get(url, {"action_interaction_ids": "10,20"})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2
        ids = {row["action_interaction_id"] for row in response.data}
        assert ids == {10, 20}

    def test_unknown_ids_return_empty_effects(self) -> None:
        url = reverse("combat:action-outcome-details")
        response = self.client.get(url, {"action_interaction_ids": "5"})
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        row = response.data[0]
        assert row["action_interaction_id"] == 5
        assert row["effects"] == []

    def test_rejects_non_integer_ids(self) -> None:
        url = reverse("combat:action-outcome-details")
        response = self.client.get(url, {"action_interaction_ids": "abc"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_requires_authentication(self) -> None:
        self.client.force_authenticate(user=None)
        url = reverse("combat:action-outcome-details")
        response = self.client.get(url, {"action_interaction_ids": "1"})
        assert response.status_code in {
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        }


class OutcomeDetailDataShapeTest(TestCase):
    """Unit tests for the _build_outcome_detail helper."""

    def test_returns_correct_shape_for_unknown_id(self) -> None:
        from world.combat.views_outcome_details import _build_outcome_detail

        # Build a minimal user object — for unknown ids the user isn't
        # consulted (no encounter to gate on). Pass a real account to
        # satisfy the function signature.
        account = AccountFactory()
        detail = _build_outcome_detail(42, account)
        assert detail.action_interaction_id == 42
        assert detail.effects == []


class DerivedOutcomeRowsTest(TestCase):
    """The view derives rows from existing models (combo, target status, conditions)."""

    def setUp(self) -> None:
        super().setUp()
        from world.combat.constants import OpponentStatus
        from world.combat.factories import (
            CombatEncounterFactory,
            CombatOpponentFactory,
            CombatParticipantFactory,
            CombatRoundActionFactory,
        )
        from world.scenes.constants import InteractionMode
        from world.scenes.factories import InteractionFactory, SceneFactory

        self.scene = SceneFactory()
        self.encounter = CombatEncounterFactory(scene=self.scene)
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        # Make the participant's character a known viewer.
        self.account = self.participant.character_sheet.character.account or AccountFactory()
        # Build a defeated opponent target.
        self.opponent = CombatOpponentFactory(
            encounter=self.encounter, name="Pyromancer", status=OpponentStatus.DEFEATED
        )
        # Action linked to an ACTION-mode Interaction.
        self.interaction = InteractionFactory(
            scene=self.scene,
            persona=self.participant.character_sheet.primary_persona,
            mode=InteractionMode.ACTION,
            content="Frost Bolt at Pyromancer",
        )
        self.action = CombatRoundActionFactory(
            participant=self.participant,
            focused_opponent_target=self.opponent,
            interaction=self.interaction,
            interaction_timestamp=self.interaction.timestamp,
        )

    def test_defeated_target_emits_status_row(self) -> None:
        from world.combat.views_outcome_details import _build_outcome_detail

        # Make the account a participant of the scene so _viewer_can_see passes.
        # In v1 this test exercises staff-bypass for simplicity.
        self.account.is_staff = True
        self.account.save()

        detail = _build_outcome_detail(self.interaction.pk, self.account)
        kinds = {row.kind for row in detail.effects}
        labels = " | ".join(row.label for row in detail.effects)
        assert "status" in kinds, f"expected a 'status' row in: {labels}"
        assert "Pyromancer" in labels

    def test_non_participant_sees_empty_effects(self) -> None:
        from world.combat.views_outcome_details import _build_outcome_detail

        outsider = AccountFactory()
        detail = _build_outcome_detail(self.interaction.pk, outsider)
        assert detail.effects == []

    def test_caster_sees_power_ledger(self) -> None:
        from world.combat.views_outcome_details import _build_outcome_detail
        from world.magic.types.power_ledger import PowerLedgerBuilder
        from world.scenes.power_ledger_services import persist_power_ledger

        persist_power_ledger(
            interaction=self.interaction, ledger=PowerLedgerBuilder(base=5).build()
        )
        self.account.is_staff = True
        self.account.save()
        detail = _build_outcome_detail(self.interaction.pk, self.account)
        assert detail.power_ledger is not None
        assert detail.power_ledger.total == 5

    def test_outsider_gets_null_ledger(self) -> None:
        from world.combat.views_outcome_details import _build_outcome_detail
        from world.magic.types.power_ledger import PowerLedgerBuilder
        from world.scenes.power_ledger_services import persist_power_ledger

        persist_power_ledger(
            interaction=self.interaction, ledger=PowerLedgerBuilder(base=5).build()
        )
        outsider = AccountFactory()
        detail = _build_outcome_detail(self.interaction.pk, outsider)
        assert detail.power_ledger is None

    def test_non_caster_participant_sees_effects_but_null_ledger(self) -> None:
        """The ledger gate is strictly tighter than effect visibility.

        A second encounter participant (not the caster, not staff) can see the
        action's effects — they're in the fight — but must NOT see the caster's
        power ledger. This proves the ledger is gated on
        ``interaction.persona.character_sheet_id`` (the caster), separately from
        ``_viewer_can_see`` (any encounter participant).
        """
        from evennia_extensions.factories import CharacterFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.combat.factories import CombatParticipantFactory
        from world.combat.views_outcome_details import _build_outcome_detail
        from world.magic.types.power_ledger import PowerLedgerBuilder
        from world.roster.factories import RosterTenureFactory
        from world.scenes.power_ledger_services import persist_power_ledger

        persist_power_ledger(
            interaction=self.interaction, ledger=PowerLedgerBuilder(base=5).build()
        )

        # A second, different character/account who is ALSO in this encounter.
        other_account = AccountFactory()
        other_char = CharacterFactory()
        other_sheet = CharacterSheetFactory(character=other_char)
        RosterTenureFactory(
            roster_entry__character_sheet__character=other_char,
            player_data__account=other_account,
        )
        CombatParticipantFactory(encounter=self.encounter, character_sheet=other_sheet)

        detail = _build_outcome_detail(self.interaction.pk, other_account)

        # Gate denies the ledger — they are not the caster.
        assert detail.power_ledger is None
        # But they CAN see effects, because they are an encounter participant.
        assert detail.effects, "second participant should see the action's effects"
        kinds = {row.kind for row in detail.effects}
        assert "status" in kinds


# ---------------------------------------------------------------------------
# Clash contribution detail — strain→power fields (Task 7)
# ---------------------------------------------------------------------------


class ClashContributionDetailStrainPowerTest(TestCase):
    """_build_outcome_detail populates strain_committed, power, progress_delta for clashes."""

    def setUp(self) -> None:
        super().setUp()
        # Build a ClashContribution linked to an ACTION Interaction with a ledger.
        self.interaction = InteractionFactory(mode=InteractionMode.ACTION)
        self.clash_round = ClashRoundFactory()
        self.contribution = ClashContributionFactory(
            clash_round=self.clash_round,
            anima_committed=5,
            progress_delta=3,
            interaction=self.interaction,
            interaction_timestamp=self.interaction.timestamp,
        )
        # Persist a power ledger onto the interaction (total = 12).
        persist_power_ledger(
            interaction=self.interaction,
            ledger=PowerLedgerBuilder(base=12).build(),
        )
        # Staff account — passes both _viewer_can_see and viewer_can_see_ledger.
        self.staff_account = AccountFactory()
        self.staff_account.is_staff = True
        self.staff_account.save()

    def test_strain_committed_and_progress_delta_in_detail(self) -> None:
        from world.combat.views_outcome_details import _build_outcome_detail

        detail = _build_outcome_detail(self.interaction.pk, self.staff_account)
        assert detail.strain_committed == 5
        assert detail.progress_delta == 3

    def test_power_derived_from_ledger_for_privileged_viewer(self) -> None:
        from world.combat.views_outcome_details import _build_outcome_detail

        detail = _build_outcome_detail(self.interaction.pk, self.staff_account)
        assert detail.power is not None
        assert detail.power == 12

    def test_power_withheld_from_non_privileged_viewer(self) -> None:
        """Non-staff, non-caster viewers see no power but still get strain/progress."""
        from world.combat.views_outcome_details import _build_outcome_detail

        outsider = AccountFactory()
        # outsider is not staff and does not play the contribution's character;
        # they also are not in the encounter — so _viewer_can_see returns False,
        # meaning effects are empty as well.  The important thing: power is None.
        detail = _build_outcome_detail(self.interaction.pk, outsider)
        assert detail.power is None

    def test_new_fields_absent_from_non_clash_details(self) -> None:
        """Non-clash interaction IDs must not break existing path (None defaults)."""
        from world.combat.views_outcome_details import _build_outcome_detail

        # Unknown ID → falls through to the bare ActionOutcomeDetail with defaults.
        detail = _build_outcome_detail(99999, self.staff_account)
        assert detail.strain_committed is None
        assert detail.power is None
        assert detail.progress_delta is None

    def test_clash_detail_json_contains_new_keys(self) -> None:
        """The endpoint returns the new fields in the JSON response body."""
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self.staff_account)
        url = reverse("combat:action-outcome-details")
        resp = client.get(url, {"action_interaction_ids": str(self.interaction.pk)})
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert len(data) == 1
        detail = data[0]
        assert "strain_committed" in detail, f"missing strain_committed in {list(detail)}"
        assert "power" in detail, f"missing power in {list(detail)}"
        assert "progress_delta" in detail, f"missing progress_delta in {list(detail)}"
        assert detail["strain_committed"] == 5
        assert detail["progress_delta"] == 3
        assert detail["power"] == 12
