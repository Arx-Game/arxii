"""Tests for flow_evaluate_resonance_environment adapter (RC3).

Verifies:
- Adapter returns the expected flat dict with all five keys.
- BaseState unwrap path: passing a BaseState-wrapped caster works identically to
  passing a raw ObjectDB.
- Inert case (no room resonances) returns empty strings and 0s.
- backfire_difficulty is precomputed correctly from config.
"""

from decimal import Decimal

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, RoomProfileFactory
from world.magic.constants import (
    AffinityInteractionAggressor,
    AffinityInteractionKind,
    ResonanceValence,
)
from world.magic.factories import (
    AffinityFactory,
    AffinityInteractionFactory,
    CharacterAuraFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
)
from world.magic.services.gain import tag_room_resonance
from world.magic.services.resonance_environment import get_resonance_environment_config


def _set_room_resonance_value(room_profile, resonance, value: int):
    """Tag the room with resonance and set modifier value."""
    mod = tag_room_resonance(room_profile, resonance)
    mod.value = value
    mod.save(update_fields=["value"])


class FlowEvaluateResonanceEnvironmentInertTest(TestCase):
    """Adapter returns all-zero/empty dict when no resonance data exists."""

    def test_inert_no_room_resonances(self) -> None:
        from flows.service_functions.resonance_environment import (
            flow_evaluate_resonance_environment,
        )

        caster_obj = CharacterFactory()
        # Room with no resonance tags: room_profile exists but no LocationValueModifier rows.
        RoomProfileFactory()
        # Place caster in a room that has no resonance.
        room_profile = RoomProfileFactory()
        caster_obj.location = room_profile.objectdb
        caster_obj.save()

        result = flow_evaluate_resonance_environment(caster=caster_obj, technique=None)

        self.assertIsInstance(result, dict)
        self.assertEqual(result["resonance_valence"], "")
        self.assertEqual(result["resonance_kind"], "")
        self.assertEqual(result["resonance_magnitude"], 0)
        self.assertEqual(result["resonance_backfire_difficulty"], 0)
        # direction may be empty or a default; just assert the key exists
        self.assertIn("resonance_direction", result)

    def test_inert_no_location(self) -> None:
        """Caster with no location returns inert dict (no crash)."""
        from flows.service_functions.resonance_environment import (
            flow_evaluate_resonance_environment,
        )

        caster_obj = CharacterFactory()
        caster_obj.location = None
        caster_obj.save()

        result = flow_evaluate_resonance_environment(caster=caster_obj, technique=None)

        self.assertEqual(result["resonance_valence"], "")
        self.assertEqual(result["resonance_magnitude"], 0)
        self.assertEqual(result["resonance_backfire_difficulty"], 0)


class FlowEvaluateResonanceEnvironmentAlignedTest(TestCase):
    """Adapter returns ALIGNED valence and correct backfire_difficulty (0 for ALIGNED)."""

    def setUp(self) -> None:
        # NOTE: setUp (not setUpTestData) — Evennia's DbHolder cannot be deepcopied,
        # which setUpTestData requires when it wraps class-level state in a transaction
        # savepoint. Use instance-level setUp instead.
        self.caster_obj = CharacterFactory()
        self.room_profile = RoomProfileFactory()
        self.caster_obj.location = self.room_profile.objectdb
        self.caster_obj.save()

        self.celestial = AffinityFactory(name="Celestial")
        self.resonance = ResonanceFactory(affinity=self.celestial)
        _set_room_resonance_value(self.room_profile, self.resonance, 40)

        AffinityInteractionFactory(
            source_affinity=self.celestial,
            environment_affinity=self.celestial,
            valence=ResonanceValence.ALIGNED,
            kind=AffinityInteractionKind.AMPLIFY,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("1.00"),
        )

        CharacterAuraFactory(
            character=self.caster_obj,
            celestial=Decimal("80.00"),
            primal=Decimal("10.00"),
            abyssal=Decimal("10.00"),
        )

        self.gift = GiftFactory()
        self.gift.resonances.add(self.resonance)
        self.technique = TechniqueFactory(gift=self.gift)

    def test_aligned_valence_returned(self) -> None:
        from flows.service_functions.resonance_environment import (
            flow_evaluate_resonance_environment,
        )

        result = flow_evaluate_resonance_environment(
            caster=self.caster_obj,
            technique=self.technique,
        )

        self.assertEqual(result["resonance_valence"], ResonanceValence.ALIGNED)
        self.assertEqual(result["resonance_kind"], AffinityInteractionKind.AMPLIFY)
        self.assertGreater(result["resonance_magnitude"], 0)
        # ALIGNED: backfire is for OPPOSED only — should be 0 since valence != opposed
        # (magnitude > 0 but valence is ALIGNED so backfire still gets computed from config;
        # the seed flow skips the perform_check branch for aligned)
        # The adapter always computes backfire_difficulty when magnitude > 0.
        cfg = get_resonance_environment_config()
        expected_backfire = cfg.backfire_base_difficulty + round(
            result["resonance_magnitude"] * float(cfg.backfire_difficulty_per_magnitude)
        )
        self.assertEqual(result["resonance_backfire_difficulty"], expected_backfire)

    def test_all_expected_keys_present(self) -> None:
        from flows.service_functions.resonance_environment import (
            flow_evaluate_resonance_environment,
        )

        result = flow_evaluate_resonance_environment(
            caster=self.caster_obj,
            technique=self.technique,
        )

        for key in (
            "resonance_valence",
            "resonance_kind",
            "resonance_magnitude",
            "resonance_direction",
            "resonance_backfire_difficulty",
        ):
            self.assertIn(key, result, f"Expected key '{key}' missing from adapter return dict")


class FlowEvaluateResonanceEnvironmentBaseStateUnwrapTest(TestCase):
    """Passing a BaseState-wrapped caster is handled identically to raw ObjectDB."""

    def setUp(self) -> None:
        # NOTE: setUp (not setUpTestData) — Evennia DbHolder deepcopy incompatibility.
        self.caster_obj = CharacterFactory()
        self.room_profile = RoomProfileFactory()
        self.caster_obj.location = self.room_profile.objectdb
        self.caster_obj.save()

        celestial = AffinityFactory(name="Celestial")
        resonance = ResonanceFactory(affinity=celestial)
        _set_room_resonance_value(self.room_profile, resonance, 40)

        AffinityInteractionFactory(
            source_affinity=celestial,
            environment_affinity=celestial,
            valence=ResonanceValence.ALIGNED,
            kind=AffinityInteractionKind.AMPLIFY,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("1.00"),
        )

        CharacterAuraFactory(
            character=self.caster_obj,
            celestial=Decimal("60.00"),
            primal=Decimal("20.00"),
            abyssal=Decimal("20.00"),
        )

    def test_basestate_unwrap_returns_same_result_as_raw_objectdb(self) -> None:
        """A mock BaseState wrapper (has .obj) should yield the same result as raw ObjectDB."""
        from flows.service_functions.resonance_environment import (
            flow_evaluate_resonance_environment,
        )

        class FakeBaseState:
            """Minimal BaseState mock exposing .obj."""

            def __init__(self, obj):
                self.obj = obj

        fake_state = FakeBaseState(self.caster_obj)

        result_raw = flow_evaluate_resonance_environment(
            caster=self.caster_obj,
            technique=None,
        )
        result_wrapped = flow_evaluate_resonance_environment(
            caster=fake_state,
            technique=None,
        )

        self.assertEqual(result_raw["resonance_valence"], result_wrapped["resonance_valence"])
        self.assertEqual(result_raw["resonance_kind"], result_wrapped["resonance_kind"])
        self.assertEqual(result_raw["resonance_magnitude"], result_wrapped["resonance_magnitude"])
        self.assertEqual(
            result_raw["resonance_backfire_difficulty"],
            result_wrapped["resonance_backfire_difficulty"],
        )
