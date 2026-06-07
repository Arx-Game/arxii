"""Tests for cast_services: derive_cast_difficulty and request_technique_cast."""

from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from evennia import create_object

from actions.factories import ActionTemplateFactory
from world.combat.constants import EncounterStatus
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    TechniqueFactory,
)
from world.scenes.action_constants import ActionRequestStatus
from world.scenes.cast_services import derive_cast_difficulty, request_technique_cast
from world.scenes.constants import InteractionMode
from world.scenes.factories import PersonaFactory, SceneFactory
from world.traits.factories import CheckSystemSetupFactory
from world.vitals.models import CharacterVitals


class TestDeriveCastDifficulty(TestCase):
    """derive_cast_difficulty maps technique intensity to the authored band scale (0-75)."""

    def test_low_intensity_lower_than_high_intensity(self) -> None:
        """A low-intensity technique must yield a lower difficulty than a high-intensity one."""
        low = TechniqueFactory(intensity=1, damage_profile=False)
        high = TechniqueFactory(intensity=9, damage_profile=False)
        assert derive_cast_difficulty(low) < derive_cast_difficulty(high)

    def test_result_in_expected_range(self) -> None:
        """The returned difficulty must be on the 0-100 scale (in practice a band value)."""
        for intensity in range(1, 10):
            technique = TechniqueFactory(intensity=intensity, damage_profile=False)
            difficulty = derive_cast_difficulty(technique)
            assert 0 <= difficulty <= 100, (
                f"difficulty={difficulty} out of range for intensity={intensity}"
            )

    def test_intensity_1_maps_to_band_15(self) -> None:
        """Intensity 1 should land in the first band (ceiling 2 → difficulty 15 = TRIVIAL)."""
        technique = TechniqueFactory(intensity=1, damage_profile=False)
        assert derive_cast_difficulty(technique) == 15

    def test_intensity_2_maps_to_band_15(self) -> None:
        """Intensity 2 is still ≤ ceiling 2, so difficulty is 15."""
        technique = TechniqueFactory(intensity=2, damage_profile=False)
        assert derive_cast_difficulty(technique) == 15

    def test_intensity_3_maps_to_band_30(self) -> None:
        """Intensity 3 is in the second band (ceiling 4 → difficulty 30 = EASY)."""
        technique = TechniqueFactory(intensity=3, damage_profile=False)
        assert derive_cast_difficulty(technique) == 30

    def test_intensity_5_maps_to_band_45(self) -> None:
        """Intensity 5 is in the third band (ceiling 6 → difficulty 45 = NORMAL)."""
        technique = TechniqueFactory(intensity=5, damage_profile=False)
        assert derive_cast_difficulty(technique) == 45

    def test_intensity_7_maps_to_band_60(self) -> None:
        """Intensity 7 is in the fourth band (ceiling 8 → difficulty 60 = HARD)."""
        technique = TechniqueFactory(intensity=7, damage_profile=False)
        assert derive_cast_difficulty(technique) == 60

    def test_intensity_9_maps_to_band_75(self) -> None:
        """Intensity 9 is in the final band (ceiling 9999 → difficulty 75 = DAUNTING)."""
        technique = TechniqueFactory(intensity=9, damage_profile=False)
        assert derive_cast_difficulty(technique) == 75

    def test_intensity_none_defaults_safely(self) -> None:
        """A technique with intensity=None (or 0) must not crash; treat as intensity 1."""
        technique = TechniqueFactory(intensity=1, damage_profile=False)
        # Force intensity to None to simulate a None value at runtime.
        technique.intensity = None
        assert derive_cast_difficulty(technique) == 15

    def test_intensity_zero_defaults_safely(self) -> None:
        """Intensity 0 must be treated as 1 (no negative/zero-difficulty exploits)."""
        technique = TechniqueFactory(intensity=1, damage_profile=False)
        technique.intensity = 0
        assert derive_cast_difficulty(technique) == 15


def _grant(persona, technique) -> None:
    """Grant a technique to the persona's CharacterSheet so the knows-check passes."""
    CharacterTechniqueFactory(character=persona.character_sheet, technique=technique)


def _benign_castable_technique() -> object:
    """A non-hostile, standalone-castable technique (no power, no damage, has template)."""
    return TechniqueFactory(
        effect_type=BinaryEffectTypeFactory(),
        damage_profile=False,
        action_template=ActionTemplateFactory(),
    )


def _hostile_castable_technique() -> object:
    """A hostile (damage) standalone-castable technique."""
    # Default EffectTypeFactory has base_power=10 → auto-seeds a damage profile →
    # is_technique_hostile() is True.
    return TechniqueFactory(action_template=ActionTemplateFactory())


class TestRequestTechniqueCastValidation(TestCase):
    """request_technique_cast guards: must know the technique and it must be castable."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()

    def test_unknown_technique_raises(self) -> None:
        technique = _benign_castable_technique()  # not granted to the initiator
        with self.assertRaises(ValidationError):
            request_technique_cast(
                scene=self.scene,
                initiator_persona=self.initiator,
                technique=technique,
            )

    def test_technique_without_action_template_raises(self) -> None:
        technique = TechniqueFactory(
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
        )
        _grant(self.initiator, technique)
        with self.assertRaises(ValidationError):
            request_technique_cast(
                scene=self.scene,
                initiator_persona=self.initiator,
                technique=technique,
            )


class TestRequestTechniqueCastRouting(TestCase):
    """request_technique_cast routes self / benign-other / hostile-other correctly."""

    @classmethod
    def setUpTestData(cls) -> None:
        CheckSystemSetupFactory.create()
        room = create_object("typeclasses.rooms.Room", key="Cast Room", nohome=True)
        cls.scene = SceneFactory(location=room)
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()
        # Anima + vitals so use_technique and combat seeding have real data.
        CharacterAnimaFactory(
            character=cls.initiator.character_sheet.character,
            current=20,
            maximum=30,
        )
        for persona in (cls.initiator, cls.target):
            CharacterVitals.objects.create(
                character_sheet=persona.character_sheet,
                health=50,
                max_health=50,
                base_max_health=50,
            )

    def setUp(self) -> None:
        self.award_kudos_patcher = patch("world.scenes.action_services.award_kudos")
        self.mock_award_kudos = self.award_kudos_patcher.start()

    def tearDown(self) -> None:
        self.award_kudos_patcher.stop()

    def test_self_cast_resolves_and_creates_outcome_pose(self) -> None:
        """No target → RESOLVED request with a Narrator OUTCOME pose."""
        technique = _benign_castable_technique()
        _grant(self.initiator, technique)

        cast = request_technique_cast(
            scene=self.scene,
            initiator_persona=self.initiator,
            technique=technique,
        )

        self.assertEqual(cast.request.status, ActionRequestStatus.RESOLVED)
        self.assertIsNotNone(cast.result)
        self.assertIsNone(cast.encounter)
        pose = cast.outcome_interaction
        self.assertIsNotNone(pose)
        self.assertEqual(pose.mode, InteractionMode.OUTCOME)
        self.assertTrue(pose.persona.is_system)
        self.assertEqual(cast.request.result_interaction, pose)

    def test_benign_cast_at_other_pc_is_pending(self) -> None:
        """Benign technique aimed at another PC → PENDING consent request."""
        technique = _benign_castable_technique()
        _grant(self.initiator, technique)

        cast = request_technique_cast(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            technique=technique,
        )

        self.assertEqual(cast.request.status, ActionRequestStatus.PENDING)
        self.assertIsNone(cast.result)
        self.assertIsNone(cast.encounter)

    def test_hostile_cast_at_other_pc_seeds_encounter(self) -> None:
        """Hostile technique aimed at another PC → combat encounter seeded (DECLARING)."""
        technique = _hostile_castable_technique()
        _grant(self.initiator, technique)

        cast = request_technique_cast(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            technique=technique,
        )

        self.assertIsNotNone(cast.encounter)
        cast.encounter.refresh_from_db()
        self.assertEqual(cast.encounter.status, EncounterStatus.DECLARING)
        self.assertEqual(cast.request.status, ActionRequestStatus.RESOLVED)
