"""Hero Killer tier (#875): unbeatable, victory-blocked, escape-only."""

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import EncounterOutcome, OpponentStatus, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    HeroKillerOpponentFactory,
)
from world.combat.services import _classify_encounter_outcome, apply_damage_to_opponent
from world.roster.factories import RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory


class HeroKillerDamageTests(TestCase):
    def test_damage_never_defeats_hero_killer(self):
        hk = HeroKillerOpponentFactory(health=10, max_health=9999, soak_value=0)
        result = apply_damage_to_opponent(hk, 1_000_000)
        hk.refresh_from_db()
        self.assertFalse(result.defeated)
        self.assertEqual(hk.status, OpponentStatus.ACTIVE)


class HeroKillerOutcomeTests(TestCase):
    def test_victory_blocked_while_hero_killer_present(self):
        encounter = CombatEncounterFactory()
        # Even an (artificially) non-active Hero Killer blocks victory: the
        # fight was never winnable.
        HeroKillerOpponentFactory(encounter=encounter, status=OpponentStatus.DEFEATED)
        self.assertNotEqual(_classify_encounter_outcome(encounter), EncounterOutcome.VICTORY)


class ForcedEscapeFlagTests(TestCase):
    def test_forced_escape_true_with_active_hero_killer(self):
        encounter = CombatEncounterFactory()
        hk = HeroKillerOpponentFactory(encounter=encounter)
        self.assertTrue(encounter.forced_escape)
        hk.status = OpponentStatus.FLED  # no longer on the field
        hk.save(update_fields=["status"])
        self.assertFalse(encounter.forced_escape)


class HeroKillerEscapeArcTests(TestCase):
    """End-to-end escape arc: Hero Killer survives all damage; all-fled PCs → FLED (#875)."""

    def test_all_pcs_flee_yields_fled_not_victory(self):
        encounter = CombatEncounterFactory()
        HeroKillerOpponentFactory(encounter=encounter)
        CombatParticipantFactory(encounter=encounter, status=ParticipantStatus.FLED)
        self.assertEqual(_classify_encounter_outcome(encounter), EncounterOutcome.FLED)
        self.assertTrue(encounter.forced_escape)


class ForcedEscapeSerializerTests(TestCase):
    """EncounterDetailSerializer emits forced_escape in the API payload (#983).

    The model property is covered by ForcedEscapeFlagTests; this asserts the
    serializer contract — that the detail endpoint actually surfaces the flag,
    so the frontend's ForcedEscapeBanner has live state to react to.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="forced_escape_player")
        cls.character = CharacterFactory(db_key="forcedescapechar")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        cls.tenure = RosterTenureFactory(
            roster_entry__character_sheet__character=cls.character,
            player_data__account=cls.account,
        )
        cls.scene = SceneFactory()
        SceneParticipationFactory(scene=cls.scene, account=cls.account, is_gm=False)

    def setUp(self) -> None:
        # Fresh encounter per test — the SharedMemoryModel identity map would
        # otherwise leak cached prefetch attrs across tests.
        self.encounter = CombatEncounterFactory(scene=self.scene)
        CombatParticipantFactory(encounter=self.encounter, character_sheet=self.sheet)
        self.client = APIClient()
        self.client.force_authenticate(user=self.account)

    def _get_detail(self) -> dict:
        response = self.client.get(f"/api/combat/{self.encounter.pk}/")
        self.assertEqual(response.status_code, 200)
        return response.data  # type: ignore[return-value]

    def test_forced_escape_true_with_active_hero_killer(self) -> None:
        HeroKillerOpponentFactory(encounter=self.encounter)

        data = self._get_detail()

        self.assertIn("forced_escape", data)
        self.assertTrue(data["forced_escape"])

    def test_forced_escape_false_without_hero_killer(self) -> None:
        data = self._get_detail()

        self.assertIn("forced_escape", data)
        self.assertFalse(data["forced_escape"])
