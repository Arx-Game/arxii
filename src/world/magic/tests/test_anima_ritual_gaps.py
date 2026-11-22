"""Tests for three backend gaps in the Anima Ritual UI feature.

Gap 1: anima_recovery field in EnhancedSceneActionResultSerializer
Gap 2: author_account_id + check_config in RitualSerializer
Gap 3: PATCH support on RitualViewSet
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from actions.constants import ResolutionPhase
from actions.factories import ActionTemplateFactory
from actions.types import PendingActionResolution, StepResult
from evennia_extensions.factories import AccountFactory
from world.checks.factories import CheckTypeFactory
from world.checks.types import CheckResult
from world.conditions.factories import SoulfrayTemplateFactory
from world.magic.constants import RitualExecutionKind
from world.magic.factories import (
    CharacterAnimaFactory,
    RitualCheckConfigFactory,
    RitualFactory,
    SoulfrayConfigFactory,
    teach_ritual,
)
from world.magic.models.soulfray import AnimaRitualBudgetAward
from world.magic.serializers import RitualSerializer
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.roster.models import RosterEntry
from world.roster.services.selection import set_selected_entry
from world.scenes.action_constants import ActionRequestStatus, ConsentDecision
from world.scenes.action_serializers import EnhancedSceneActionResultSerializer
from world.scenes.action_services import respond_to_action_request
from world.scenes.factories import PersonaFactory, SceneActionRequestFactory, SceneFactory
from world.scenes.types import EnhancedSceneActionResult
from world.traits.factories import CheckOutcomeFactory

_PERFORM_CHECK_PATCH = "world.scenes.action_services.start_action_resolution"
_ACCRUE_PATCH = "world.scenes.action_services.accrue"


def _make_pending_resolution(outcome_row: object) -> PendingActionResolution:
    """Build a PendingActionResolution wrapping a real CheckOutcome row."""
    check_type = CheckTypeFactory()
    check_result = CheckResult(
        check_type=check_type,
        outcome=outcome_row,  # type: ignore[arg-type]
        chart=None,
        roller_rank=None,
        target_rank=None,
        rank_difference=0,
        trait_points=0,
        aspect_bonus=0,
        total_points=0,
    )
    main_result = StepResult(
        step_label="main",
        check_result=check_result,
        consequence_id=None,
    )
    return PendingActionResolution(
        template_id=1,
        character_id=1,
        target_difficulty=15,
        resolution_context_data={"character_id": 1, "challenge_instance_id": None},
        current_phase=ResolutionPhase.COMPLETE,
        main_result=main_result,
    )


def _make_scene_action_ritual():
    """Create a SCENE_ACTION Ritual + RitualCheckConfig."""
    ritual = RitualFactory(
        execution_kind=RitualExecutionKind.SCENE_ACTION,
        service_function_path="",
        flow=None,
    )
    RitualCheckConfigFactory(ritual=ritual)
    return ritual


# =============================================================================
# Gap 1: anima_recovery field in EnhancedSceneActionResultSerializer
# =============================================================================


class AnimaRecoverySerializerFieldTests(TestCase):
    """Gap 1: anima_recovery is populated for initiator only on anima_ritual accept."""

    def setUp(self) -> None:
        from world.magic.services import anima_ritual_action  # noqa: F401

        self.accrue_patcher = patch(_ACCRUE_PATCH)
        self.accrue_patcher.start()

    def tearDown(self) -> None:
        self.accrue_patcher.stop()

    @staticmethod
    def _give_a_player(action_request):
        """The account holding the initiator's roster tenure (she is not puppeted)."""
        sheet = action_request.initiator_persona.character_sheet
        account = AccountFactory()
        entry = RosterEntry.objects.filter(character_sheet=sheet).first()
        if entry is None:
            entry = RosterEntryFactory(character_sheet=sheet)
        RosterTenureFactory(player_data=account.player_data, roster_entry=entry, end_date=None)
        return account

    def _setup(self, success_level: int = 1) -> tuple:
        """Create a full ritual+scene setup and return (action_request, outcome)."""
        persona = PersonaFactory()
        sheet = persona.character_sheet
        target_persona = PersonaFactory()

        ritual = _make_scene_action_ritual()
        CharacterAnimaFactory(character=sheet, current=2, maximum=10)
        SoulfrayTemplateFactory()
        SoulfrayConfigFactory(
            ritual_severity_cost_per_point=1,
        )
        scene = SceneFactory(is_active=True)
        outcome = CheckOutcomeFactory(
            name=f"GapOutcome_sl{success_level}_{id(object())}",
            success_level=success_level,
        )
        # Budget keyed to the same outcome tier this helper mints, mirroring the
        # old ritual_budget_critical_success/_success/_partial/_failure values.
        AnimaRitualBudgetAward.objects.create(
            outcome_tier=outcome,
            budget={2: 10, 1: 6, 0: 3}.get(success_level, 1),
        )
        action_template = ActionTemplateFactory()
        action_request = SceneActionRequestFactory(
            scene=scene,
            initiator_persona=persona,
            target_persona=target_persona,
            action_key="anima_ritual",
            status=ActionRequestStatus.PENDING,
        )
        action_request.action_template = action_template
        action_request.snapshot_ritual = ritual
        action_request.save(update_fields=["action_template", "snapshot_ritual"])
        return action_request, outcome

    def test_resolver_attaches_anima_recovery_payload_to_action_request(self) -> None:
        """After accept, the resolver attaches _anima_recovery_payload to action_request."""
        action_request, outcome = self._setup(success_level=1)

        with patch(_PERFORM_CHECK_PATCH, return_value=_make_pending_resolution(outcome)):
            result = respond_to_action_request(
                action_request=action_request, decision=ConsentDecision.ACCEPT
            )

        self.assertIsNotNone(result)
        # Suppression justified: asserts the transient side-channel stash exists.
        payload = getattr(action_request, "_anima_recovery_payload", None)  # noqa: GETATTR_LITERAL
        self.assertIsNotNone(payload)
        # success budget=6, anima goes from 2 to 8
        self.assertEqual(payload["recovered"], 6)
        self.assertEqual(payload["soulfray_reduced"], 0)
        self.assertEqual(payload["new_pool"], 8)

    def test_serializer_returns_recovery_when_user_matches_initiator(self) -> None:
        """Serializer returns anima_recovery when request.user is initiator_account."""
        action_request, outcome = self._setup(success_level=1)

        with patch(_PERFORM_CHECK_PATCH, return_value=_make_pending_resolution(outcome)):
            result = respond_to_action_request(
                action_request=action_request, decision=ConsentDecision.ACCEPT
            )

        self.assertIsNotNone(result)
        # The initiator's player is whoever holds her roster tenure.
        initiator_account = self._give_a_player(action_request)

        mock_request = MagicMock()
        mock_request.user = initiator_account
        data = EnhancedSceneActionResultSerializer(
            result,
            context={"request": mock_request, "action_request": action_request},
        ).data

        self.assertIn("anima_recovery", data)
        recovery = data["anima_recovery"]
        self.assertIsNotNone(recovery)
        self.assertEqual(recovery["recovered"], 6)
        self.assertEqual(recovery["soulfray_reduced"], 0)
        self.assertEqual(recovery["new_pool"], 8)

    @tag("regression")
    def test_an_initiator_nobody_is_logged_in_as_still_sees_her_recovery(self) -> None:
        """Regression for #5280. Her recovery is shown to the player who holds her tenure, even
        when Evennia has cleared the account off the character because she is not puppeted."""
        action_request, outcome = self._setup(success_level=1)

        with patch(_PERFORM_CHECK_PATCH, return_value=_make_pending_resolution(outcome)):
            result = respond_to_action_request(
                action_request=action_request, decision=ConsentDecision.ACCEPT
            )

        initiator_account = self._give_a_player(action_request)
        character = action_request.initiator_persona.character_sheet.character
        self.assertIsNone(character.db_account)
        mock_request = MagicMock()
        mock_request.user = initiator_account
        data = EnhancedSceneActionResultSerializer(
            result,
            context={"request": mock_request, "action_request": action_request},
        ).data

        self.assertEqual(data["anima_recovery"]["recovered"], 6)

    def test_target_does_not_see_anima_recovery(self) -> None:
        """Non-initiator account does not see anima_recovery (disguise)."""
        action_request, outcome = self._setup(success_level=1)

        with patch(_PERFORM_CHECK_PATCH, return_value=_make_pending_resolution(outcome)):
            result = respond_to_action_request(
                action_request=action_request, decision=ConsentDecision.ACCEPT
            )

        self.assertIsNotNone(result)
        # Give the initiator a player, but pass a different account as request.user.
        self._give_a_player(action_request)
        other_account = AccountFactory()

        mock_request = MagicMock()
        mock_request.user = other_account  # NOT the initiator
        data = EnhancedSceneActionResultSerializer(
            result,
            context={"request": mock_request, "action_request": action_request},
        ).data

        self.assertIsNone(data["anima_recovery"])

    def test_non_anima_action_key_returns_null_recovery(self) -> None:
        """Non-anima action_key requests return null anima_recovery."""
        action_request, _outcome = self._setup(success_level=1)
        initiator_account = action_request.initiator_persona.character_sheet.character.db_account

        # Build a result with a different action_key
        mock_action_resolution = MagicMock()
        result = EnhancedSceneActionResult(
            action_resolution=mock_action_resolution,
            action_key="persuade",
        )
        mock_request = MagicMock()
        mock_request.user = initiator_account
        data = EnhancedSceneActionResultSerializer(
            result,
            context={"request": mock_request, "action_request": action_request},
        ).data
        self.assertIsNone(data["anima_recovery"])

    def test_anima_recovery_absent_without_context(self) -> None:
        """Without request/action_request context, anima_recovery is None."""
        mock_action_resolution = MagicMock()
        result = EnhancedSceneActionResult(
            action_resolution=mock_action_resolution,
            action_key="anima_ritual",
        )
        data = EnhancedSceneActionResultSerializer(result).data
        self.assertIsNone(data["anima_recovery"])


# =============================================================================
# Gap 2: author_account_id + check_config in RitualSerializer
# =============================================================================


class RitualSerializerFieldTests(TestCase):
    """Gap 2: author_account_id and check_config exposed in RitualSerializer."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.service_ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SERVICE,
            service_function_path="world.magic.services.spend_resonance_for_imbuing",
            author_account=cls.account,
        )
        cls.scene_action_ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
            flow=None,
            author_account=cls.account,
        )
        cls.config = RitualCheckConfigFactory(ritual=cls.scene_action_ritual)
        cls.staff_ritual = RitualFactory(
            author_account=None,  # staff-authored
        )

    def test_service_ritual_has_null_check_config(self) -> None:
        """SERVICE rituals without a config return null for check_config."""
        data = RitualSerializer(self.service_ritual).data
        self.assertIsNone(data["check_config"])

    def test_scene_action_ritual_has_nested_config(self) -> None:
        """SCENE_ACTION rituals return a nested check_config object."""
        data = RitualSerializer(self.scene_action_ritual).data
        config = data["check_config"]
        self.assertIsNotNone(config)
        self.assertIn("id", config)
        self.assertIn("stat", config)
        self.assertIn("stat_name", config)
        self.assertIn("skill", config)
        self.assertIn("skill_name", config)
        self.assertIn("target_difficulty_level", config)

    def test_author_account_id_is_returned(self) -> None:
        """author_account_id is the FK PK of the author account."""
        data = RitualSerializer(self.scene_action_ritual).data
        self.assertEqual(data["author_account_id"], self.account.pk)

    def test_staff_authored_ritual_has_null_author_account_id(self) -> None:
        """Staff-authored rituals return null for author_account_id."""
        data = RitualSerializer(self.staff_ritual).data
        self.assertIsNone(data["author_account_id"])


# =============================================================================
# Gap 3: PATCH support on RitualViewSet
# =============================================================================


class RitualViewSetPatchTests(APITestCase):
    """Gap 3: Author can PATCH their ritual; non-author/non-staff 403."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.author_account = AccountFactory()
        cls.other_account = AccountFactory()
        cls.staff_account = AccountFactory(is_staff=True)

        cls.ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SERVICE,
            service_function_path="world.magic.services.spend_resonance_for_imbuing",
            author_account=cls.author_account,
            hedge_accessible=True,
            name="Authored Ritual",
        )
        cls.staff_ritual = RitualFactory(
            author_account=None,  # staff-authored
            name="Staff Ritual",
        )

        # SCENE_ACTION ritual for nested config patch tests
        cls.scene_ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
            flow=None,
            author_account=cls.author_account,
            hedge_accessible=True,
            name="Scene Ritual",
        )
        cls.scene_config = RitualCheckConfigFactory(ritual=cls.scene_ritual)
        # The anima ritual is the character's (#5280): its author plays the character who
        # knows it, which is what lets them edit it.
        cls.knower_tenure = RosterTenureFactory(
            player_data=cls.author_account.player_data, end_date=None
        )
        teach_ritual(cls.scene_ritual, cls.knower_tenure.roster_entry.character_sheet)
        set_selected_entry(cls.author_account.player_data, cls.knower_tenure.roster_entry)

    def _patch_url(self, pk: int) -> str:
        return reverse("magic:ritual-detail", kwargs={"pk": pk})

    def test_author_can_patch_name(self) -> None:
        """Ritual author can PATCH name."""
        self.client.force_authenticate(user=self.author_account)
        resp = self.client.patch(
            self._patch_url(self.ritual.pk),
            {"name": "Updated Name"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.ritual.refresh_from_db()
        self.assertEqual(self.ritual.name, "Updated Name")

    def test_non_author_cannot_patch(self) -> None:
        """Non-author account receives 403 on PATCH."""
        self.client.force_authenticate(user=self.other_account)
        resp = self.client.patch(
            self._patch_url(self.ritual.pk),
            {"name": "Stolen Name"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_patch_any_ritual(self) -> None:
        """Staff account can PATCH any ritual regardless of author."""
        self.client.force_authenticate(user=self.staff_account)
        resp = self.client.patch(
            self._patch_url(self.ritual.pk),
            {"description": "Staff update"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_staff_authored_ritual_non_staff_cannot_patch(self) -> None:
        """Staff-authored (author_account=None) ritual cannot be PATCHed by non-staff."""
        self.client.force_authenticate(user=self.other_account)
        resp = self.client.patch(
            self._patch_url(self.staff_ritual.pk),
            {"name": "Hacked"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_nested_check_config_target_difficulty(self) -> None:
        """Author can PATCH the nested check_config target_difficulty_level."""
        self.client.force_authenticate(user=self.author_account)
        resp = self.client.patch(
            self._patch_url(self.scene_ritual.pk),
            {"check_config": {"target_difficulty_level": 2}},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.json())
        self.scene_config.refresh_from_db()
        self.assertEqual(self.scene_config.target_difficulty_level, 2)

    @tag("regression")
    def test_only_the_player_of_the_character_who_knows_it_can_patch_an_anima_ritual(
        self,
    ) -> None:
        """Regression for #5280. The anima ritual is in character, so it belongs to the
        character who knows it: once its author no longer plays that character they cannot
        see or edit it, and the player who now plays the character can."""
        self.knower_tenure.end_date = timezone.now()
        self.knower_tenure.save(update_fields=["end_date"])
        RosterTenureFactory(
            roster_entry=self.knower_tenure.roster_entry,
            player_data=self.other_account.player_data,
            end_date=None,
        )
        set_selected_entry(self.other_account.player_data, self.knower_tenure.roster_entry)

        self.client.force_authenticate(user=self.author_account)
        resp = self.client.patch(
            self._patch_url(self.scene_ritual.pk),
            {"description": "From another character"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        self.client.force_authenticate(user=self.other_account)
        resp = self.client.patch(
            self._patch_url(self.scene_ritual.pk),
            {"description": "From the character who knows it"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.json())

    def test_patch_without_config_preserves_top_level_update(self) -> None:
        """A missing check config does not prevent the ritual update."""
        self.client.force_authenticate(user=self.author_account)
        resp = self.client.patch(
            self._patch_url(self.ritual.pk),
            {"name": "Updated without config", "check_config": {"target_difficulty_level": 2}},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.json())
        self.ritual.refresh_from_db()
        self.assertEqual(self.ritual.name, "Updated without config")
        self.assertIsNone(self.ritual.check_config_or_none)

    def test_get_returns_author_account_id_and_config(self) -> None:
        """GET on a SCENE_ACTION ritual includes author_account_id and check_config."""
        self.client.force_authenticate(user=self.author_account)
        resp = self.client.get(self._patch_url(self.scene_ritual.pk))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["author_account_id"], self.author_account.pk)
        self.assertIsNotNone(data["check_config"])

    def test_delete_not_allowed(self) -> None:
        """DELETE is not allowed (http_method_names excludes delete)."""
        self.client.force_authenticate(user=self.author_account)
        resp = self.client.delete(self._patch_url(self.ritual.pk))
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


# =============================================================================
# Who can see an anima ritual (#5280)
# =============================================================================


@tag("regression")
class AnimaRitualVisibilityTests(APITestCase):
    """The anima ritual is in character: a player sees the ones her characters know."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.mara = AccountFactory()
        cls.tobin = AccountFactory()
        cls.staff = AccountFactory(is_staff=True)
        cls.mara_ritual = cls._anima_ritual(cls.mara, "Mara's Breathing")
        cls.tobin_ritual = cls._anima_ritual(cls.tobin, "Tobin's Vigil")
        cls.shared = RitualFactory(
            name="The Shared Rite",
            execution_kind=RitualExecutionKind.SERVICE,
            author_account=None,
            hedge_accessible=True,
        )

    @staticmethod
    def _anima_ritual(account, name: str):
        ritual = RitualFactory(
            name=name,
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
            flow=None,
            author_account=account,
            hedge_accessible=True,
        )
        RitualCheckConfigFactory(ritual=ritual)
        tenure = RosterTenureFactory(player_data=account.player_data, end_date=None)
        teach_ritual(ritual, tenure.roster_entry.character_sheet)
        set_selected_entry(account.player_data, tenure.roster_entry)
        return ritual

    def _listed(self, account) -> dict[str, dict]:
        self.client.force_authenticate(user=account)
        response = self.client.get(reverse("magic:ritual-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return {row["name"]: row for row in response.data["results"]}

    def test_a_player_lists_her_own_anima_ritual_and_the_shared_catalog_only(self) -> None:
        """Regression for #5280. Mara lists her ritual and the shared rite, never Tobin's."""
        self.assertEqual(set(self._listed(self.mara)), {"Mara's Breathing", "The Shared Rite"})

    def test_a_player_cannot_read_another_players_anima_ritual(self) -> None:
        """Regression for #5280. Tobin asking for Mara's ritual by id is told it is not there."""
        self.client.force_authenticate(user=self.tobin)
        url = reverse("magic:ritual-detail", args=[self.mara_ritual.pk])
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
        own = reverse("magic:ritual-detail", args=[self.tobin_ritual.pk])
        self.assertEqual(self.client.get(own).status_code, status.HTTP_200_OK)

    def test_the_edit_control_is_offered_only_for_the_ritual_a_played_character_knows(
        self,
    ) -> None:
        """Regression for #5280. Mara may edit her ritual and not the shared rite."""
        listed = self._listed(self.mara)
        self.assertTrue(listed["Mara's Breathing"]["viewer_can_edit"])
        self.assertFalse(listed["The Shared Rite"]["viewer_can_edit"])

    def test_staff_see_every_ritual(self) -> None:
        """Staff browse the whole catalog, both players' anima rituals included."""
        self.assertEqual(
            set(self._listed(self.staff)),
            {"Mara's Breathing", "Tobin's Vigil", "The Shared Rite"},
        )


@tag("regression")
class AnimaRitualOfTheActingCharacterTests(APITestCase):
    """One account plays two characters: browsing as one never shows or edits the other's."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory()
        cls.tenure_a = RosterTenureFactory(player_data=cls.account.player_data, end_date=None)
        cls.tenure_b = RosterTenureFactory(player_data=cls.account.player_data, end_date=None)
        cls.ritual_a = cls._anima_ritual(cls.tenure_a, "Ash's Breathing")
        cls.ritual_b = cls._anima_ritual(cls.tenure_b, "Birch's Breathing")

    @staticmethod
    def _anima_ritual(tenure, name: str):
        ritual = RitualFactory(
            name=name,
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
            flow=None,
            author_account=tenure.player_data.account,
            hedge_accessible=True,
        )
        RitualCheckConfigFactory(ritual=ritual)
        teach_ritual(ritual, tenure.roster_entry.character_sheet)
        return ritual

    def _browse_as(self, tenure) -> None:
        set_selected_entry(self.account.player_data, tenure.roster_entry)
        self.client.force_authenticate(user=self.account)

    def test_the_list_shows_only_the_selected_characters_ritual(self) -> None:
        """Regression for #5280. Browsing as the second character lists only her ritual."""
        self._browse_as(self.tenure_b)
        response = self.client.get(reverse("magic:ritual-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        listed = {row["name"]: row for row in response.data["results"]}
        self.assertEqual(set(listed), {"Birch's Breathing"})
        self.assertTrue(listed["Birch's Breathing"]["viewer_can_edit"])

    def test_the_other_characters_ritual_cannot_be_read_or_edited(self) -> None:
        """Regression for #5280. Browsing as the second character, the first's ritual is a 404."""
        self._browse_as(self.tenure_b)
        url = reverse("magic:ritual-detail", args=[self.ritual_a.pk])
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)
        response = self.client.patch(url, {"description": "Not mine"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.ritual_a.refresh_from_db()
        self.assertNotEqual(self.ritual_a.description, "Not mine")

    def test_the_selected_character_edits_her_own_ritual(self) -> None:
        """Browsing as the first character, her own ritual patches and the second's does not."""
        self._browse_as(self.tenure_a)
        own = reverse("magic:ritual-detail", args=[self.ritual_a.pk])
        response = self.client.patch(own, {"description": "Mine"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.json())
        other = reverse("magic:ritual-detail", args=[self.ritual_b.pk])
        self.assertEqual(
            self.client.patch(other, {"description": "Not mine"}, format="json").status_code,
            status.HTTP_404_NOT_FOUND,
        )
