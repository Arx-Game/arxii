"""Tests for cast_services: derive_cast_difficulty and request_technique_cast."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from evennia import create_object

from actions.factories import ActionTemplateFactory
from evennia_extensions.factories import RoomProfileFactory
from world.combat.constants import EncounterStatus
from world.magic.constants import (
    AffinityInteractionAggressor,
    AffinityInteractionKind,
    LedgerOp,
    PowerStage,
    ResonanceValence,
)
from world.magic.factories import (
    AffinityFactory,
    AffinityInteractionFactory,
    BinaryEffectTypeFactory,
    CharacterAnimaFactory,
    CharacterAuraFactory,
    CharacterTechniqueFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
)
from world.magic.models import Technique
from world.magic.services.gain import tag_room_resonance
from world.magic.tests._cache_isolation import ResonanceCacheIsolationMixin
from world.magic.types.power_ledger import PowerLedgerBuilder
from world.scenes.action_constants import ActionRequestStatus
from world.scenes.cast_services import (
    create_cast_outcome_pose,
    derive_cast_difficulty,
    request_technique_cast,
)
from world.scenes.constants import InteractionMode
from world.scenes.factories import PersonaFactory, SceneFactory
from world.scenes.models import Persona
from world.scenes.types import EnhancedSceneActionResult
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


def _grant(persona: Persona, technique: Technique) -> None:
    """Grant a technique to the persona's CharacterSheet so the knows-check passes."""
    CharacterTechniqueFactory(character=persona.character_sheet, technique=technique)


def _benign_castable_technique() -> Technique:
    """A non-hostile, standalone-castable technique (no power, no damage, has template)."""
    return TechniqueFactory(
        effect_type=BinaryEffectTypeFactory(),
        damage_profile=False,
        action_template=ActionTemplateFactory(),
    )


def _hostile_castable_technique() -> Technique:
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

    def test_self_cast_persists_strain_commitment(self) -> None:
        """strain_commitment forwarded on the immediate path is stored on the request."""
        technique = _benign_castable_technique()
        _grant(self.initiator, technique)

        cast = request_technique_cast(
            scene=self.scene,
            initiator_persona=self.initiator,
            technique=technique,
            strain_commitment=3,
        )

        self.assertEqual(cast.request.status, ActionRequestStatus.RESOLVED)
        self.assertEqual(cast.request.strain_commitment, 3)

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


class TestImmediateCastSurfacesEnvironmentLedger(ResonanceCacheIsolationMixin, TestCase):
    """A self-cast in an amplifying resonant room surfaces the environment clause.

    Real integration: the caster's character stands in a room tagged with a
    Celestial resonance whose AffinityInteraction with the working affinity is
    AMPLIFY. ``use_technique`` evaluates the resonance environment, the
    ENVIRONMENT power-shift stage adds a positive entry to the cast-level
    ``PowerLedger``, and ``_route_immediate_cast`` threads that ledger into the
    OUTCOME pose narration — so the pose ends with the environment clause.
    """

    def test_self_cast_outcome_pose_has_environment_clause(self) -> None:
        CheckSystemSetupFactory.create()

        # Amplifying place: a room tagged with a Celestial resonance whose
        # self-interaction (Celestial × Celestial) is ALIGNED / AMPLIFY.
        room_profile = RoomProfileFactory()
        room = room_profile.objectdb
        celestial = AffinityFactory(name="Celestial")
        resonance = ResonanceFactory(affinity=celestial)
        mod = tag_room_resonance(room_profile, resonance)
        mod.value = 40
        mod.save(update_fields=["value"])
        AffinityInteractionFactory(
            source_affinity=celestial,
            environment_affinity=celestial,
            valence=ResonanceValence.ALIGNED,
            kind=AffinityInteractionKind.AMPLIFY,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("1.00"),
        )

        # Caster: a persona whose character is highly Celestial-aligned and is
        # physically standing in the resonant room.
        initiator = PersonaFactory()
        caster_char = initiator.character_sheet.character
        caster_char.location = room
        CharacterAuraFactory(
            character=caster_char,
            celestial=Decimal("80.00"),
            primal=Decimal("10.00"),
            abyssal=Decimal("10.00"),
        )
        CharacterAnimaFactory(character=caster_char, current=20, maximum=30)

        # Benign, standalone-castable technique whose gift channels the resonance
        # so the cast-time working affinity resolves to Celestial.
        gift = GiftFactory()
        gift.resonances.add(resonance)
        technique = TechniqueFactory(
            gift=gift,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=ActionTemplateFactory(),
        )
        CharacterTechniqueFactory(character=initiator.character_sheet, technique=technique)

        scene = SceneFactory(location=room)

        with patch("world.scenes.action_services.award_kudos"):
            cast = request_technique_cast(
                scene=scene,
                initiator_persona=initiator,
                technique=technique,
            )

        self.assertEqual(cast.request.status, ActionRequestStatus.RESOLVED)
        pose = cast.outcome_interaction
        self.assertIsNotNone(pose)
        self.assertTrue(
            pose.content.endswith("— the place's resonance swells the working."),
            f"OUTCOME pose missing environment clause: {pose.content!r}",
        )


class TestCreateCastOutcomePoseLedgerClause(TestCase):
    """Direct unit test: a hand-built amplification ledger yields the env clause.

    Narrower companion to the integration test above. It bypasses the magic
    pipeline and feeds ``create_cast_outcome_pose`` a PowerLedger with a positive
    ENVIRONMENT ADD entry, proving the param is threaded into the narration.
    """

    def test_environment_add_ledger_appends_clause(self) -> None:
        scene = SceneFactory()
        caster = PersonaFactory()
        technique = TechniqueFactory(intensity=1, damage_profile=False)

        ledger = (
            PowerLedgerBuilder(base=5)
            .add(PowerStage.ENVIRONMENT, "resonance environment", 7)
            .build()
        )
        # Sanity: the builder produced the entry the clause logic looks for.
        self.assertTrue(
            any(
                e.stage == PowerStage.ENVIRONMENT and e.op == LedgerOp.ADD and e.amount > 0
                for e in ledger.entries
            )
        )

        # Minimal stub for the outcome-label extraction (main_result is None →
        # outcome defaults to "Unknown"); the clause comes solely from the ledger.
        action_resolution = SimpleNamespace(main_result=None)
        result = EnhancedSceneActionResult(
            action_resolution=action_resolution,  # type: ignore[arg-type]
            action_key="cast",
            technique_result=None,
        )

        pose = create_cast_outcome_pose(
            scene=scene,
            caster_persona=caster,
            target_persona=None,
            technique=technique,
            result=result,
            power_ledger=ledger,
        )
        self.assertTrue(
            pose.content.endswith("— the place's resonance swells the working."),
            f"OUTCOME pose missing environment clause: {pose.content!r}",
        )
