"""Tests for CombatOpponent.level (#2707 Task 5).

Covers the three-way resolution order in ``add_opponent``:
- Auto-scaling mode (no ``max_health``) defaults ``level`` to the encounter's
  average party level, already resolved onto ``OpponentStatBlock.level``.
- An explicit ``level=`` kwarg always wins over the auto-scaled default.
- Manual mode (``max_health`` passed) still gets a real level (falls back to 1).

Plus the PvP mirror path (``_opponent_kwargs_from_sheet`` takes the mirrored
character's bond-aware ``effective_combat_level``) and that ``level`` is
public (ungated) in ``OpponentSerializer``.
"""

from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassLevelFactory
from world.combat.cast_seed import _opponent_kwargs_from_sheet
from world.combat.constants import OpponentTier, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    seed_scaling_defaults,
)
from world.combat.serializers import OpponentSerializer
from world.combat.services import add_opponent


class AutoScaledOpponentLevelTest(TestCase):
    """Auto-scaling mode (no max_health) defaults level to the party average."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_scaling_defaults()
        cls.encounter = CombatEncounterFactory()
        # Two ACTIVE participants at levels 4 and 6 -> average 5.
        for level in (4, 6):
            participant = CombatParticipantFactory(
                encounter=cls.encounter,
                status=ParticipantStatus.ACTIVE,
            )
            CharacterClassLevelFactory(
                character=participant.character_sheet,
                level=level,
                is_primary=True,
            )

    def test_auto_scaled_opponent_defaults_to_party_average_level(self) -> None:
        opp = add_opponent(self.encounter, name="Brute", tier=OpponentTier.MOOK, threat_pool=None)
        self.assertEqual(opp.level, 5)


class ExplicitLevelWinsTest(TestCase):
    """A deliberately under-levelled boss is how an upset victory gets authored."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_scaling_defaults()
        cls.encounter = CombatEncounterFactory()

    def test_explicit_level_wins_over_the_default(self) -> None:
        opp = add_opponent(
            self.encounter,
            name="Faded Tyrant",
            tier=OpponentTier.BOSS,
            threat_pool=None,
            level=2,
        )
        self.assertEqual(opp.level, 2)


class ManualModeOpponentLevelTest(TestCase):
    """max_health passed = manual mode; level must not come out 0."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_scaling_defaults()
        cls.encounter = CombatEncounterFactory()

    def test_manual_mode_opponent_still_gets_a_level(self) -> None:
        opp = add_opponent(
            self.encounter,
            name="Handmade",
            tier=OpponentTier.MOOK,
            threat_pool=None,
            max_health=40,
        )
        self.assertGreaterEqual(opp.level, 1)


class PvpMirrorOpponentLevelTest(TestCase):
    """PvP mirrors take the mirrored character's bond-aware combat level."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.level_seven_sheet = CharacterSheetFactory()
        CharacterClassLevelFactory(
            character=cls.level_seven_sheet,
            level=7,
            is_primary=True,
        )

    def test_pvp_mirror_takes_the_mirrored_characters_combat_level(self) -> None:
        kwargs = _opponent_kwargs_from_sheet(self.level_seven_sheet)
        self.assertEqual(kwargs["level"], 7)


class OpponentLevelSerializerTest(TestCase):
    """Threat assessment is the point -- unlike soak and probing threshold."""

    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory()
        self.opponent = CombatOpponentFactory(encounter=self.encounter)
        factory = APIRequestFactory()
        self.request = factory.get("/")
        self.request.user = AccountFactory()

    def test_level_is_public_in_the_opponent_payload(self) -> None:
        data = OpponentSerializer(self.opponent, context={"request": self.request}).data
        self.assertEqual(data["level"], self.opponent.level)
