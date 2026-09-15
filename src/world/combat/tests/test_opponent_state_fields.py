"""GM-only boss state and public badges on the opponent payload (#3552)."""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from evennia_extensions.factories import AccountFactory
from world.combat.constants import OpponentTier
from world.combat.factories import (
    BossOpponentFactory,
    BossPhaseFactory,
    CombatEncounterFactory,
    CombatOpponentFactory,
)
from world.combat.serializers import OpponentSerializer

GM_ONLY_FIELDS = (
    "phase_count",
    "damage_multiplier",
    "break_bar_current",
    "break_bar_threshold",
    "vulnerability_rounds_remaining",
    "morale",
    "max_morale",
    "morale_state",
)


class OpponentStateFieldTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory()
        self.boss = BossOpponentFactory(
            encounter=self.encounter,
            current_phase=2,
            damage_multiplier=Decimal("1.50"),
            break_bar_threshold=12,
            break_bar_current=4,
            vulnerability_rounds_remaining=1,
            morale=40,
        )
        BossPhaseFactory(opponent=self.boss, phase_number=1)
        BossPhaseFactory(opponent=self.boss, phase_number=2)
        BossPhaseFactory(opponent=self.boss, phase_number=3)
        factory = APIRequestFactory()
        self.player_request = factory.get("/")
        self.player_request.user = AccountFactory(username="state_player")
        self.staff_request = factory.get("/")
        self.staff_request.user = AccountFactory(username="state_staff", is_staff=True)

    def test_player_sees_null_gm_fields_and_public_badges(self) -> None:
        data = OpponentSerializer(self.boss, context={"request": self.player_request}).data
        for field in GM_ONLY_FIELDS:
            self.assertIsNone(data[field], field)
        self.assertTrue(data["is_enraged"])
        self.assertTrue(data["is_wall_broken"])
        self.assertEqual(data["current_phase"], 2)

    def test_staff_sees_gm_fields(self) -> None:
        data = OpponentSerializer(self.boss, context={"request": self.staff_request}).data
        self.assertEqual(data["phase_count"], 3)
        self.assertEqual(data["damage_multiplier"], "1.50")
        self.assertEqual(data["break_bar_current"], 4)
        self.assertEqual(data["break_bar_threshold"], 12)
        self.assertEqual(data["vulnerability_rounds_remaining"], 1)
        self.assertEqual(data["morale"], 40)
        self.assertEqual(data["morale_state"], "falter")

    def test_scene_gm_context_flag_unlocks_gm_fields(self) -> None:
        data = OpponentSerializer(
            self.boss, context={"request": self.player_request, "is_gm": True}
        ).data
        self.assertEqual(data["phase_count"], 3)

    def test_phase_one_boss_shows_no_badges(self) -> None:
        calm = BossOpponentFactory(
            encounter=self.encounter, current_phase=1, damage_multiplier=Decimal("1.50")
        )
        data = OpponentSerializer(calm, context={"request": self.player_request}).data
        self.assertFalse(data["is_enraged"])
        self.assertFalse(data["is_wall_broken"])

    def test_non_boss_has_null_phase_count_for_gm(self) -> None:
        mook = CombatOpponentFactory(encounter=self.encounter, tier=OpponentTier.MOOK)
        data = OpponentSerializer(mook, context={"request": self.staff_request}).data
        self.assertIsNone(data["phase_count"])
        self.assertEqual(data["morale_state"], "steady")
