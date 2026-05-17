"""Tests for evaluate_resonance_environment primitive (RA4).

All tests build rows via AffinityInteractionFactory, rooms via tag_room_resonance
(then adjusting the LocationValueModifier.value for different intensities),
caster aura via CharacterAuraFactory, and technique via existing magic factories.

Room-resonance enumeration: the primitive queries LocationValueModifier rows with
key_type=RESONANCE for the room's cascade (profile + ancestor areas). Tests use
tag_room_resonance which creates room-level modifiers, then adjust .value in-place.

Note on aura field lookup: CharacterAura has exactly three fields (celestial, primal,
abyssal). For cast-time, the working affinity's name is lowercased to index into
the aura. Tests that check magnitude must use canonical affinity names matching
these fields.

Cache isolation: every test class uses ResonanceCacheIsolationMixin so
AffinityInteractionManager's process-lived cache is cleared between tests.
This prevents negative-cached entries from poisoning subsequent test classes.
"""

from decimal import Decimal

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, RoomProfileFactory
from world.magic.constants import (
    AffinityInteractionAggressor,
    AffinityInteractionKind,
    ResonanceDirection,
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
from world.magic.services.resonance_environment import (
    ResonanceEnvironmentEffect,
    evaluate_resonance_environment,
    get_resonance_environment_config,
)
from world.magic.tests._cache_isolation import ResonanceCacheIsolationMixin


def _set_room_resonance_value(room_profile, resonance, value: int) -> None:
    """Tag the room with resonance and set the modifier value to ``value``.

    Uses instance .save() rather than queryset .update() so the SharedMemoryModel
    identity-map cache is kept consistent with the database.
    """
    mod = tag_room_resonance(room_profile, resonance)
    mod.value = value
    mod.save(update_fields=["value"])


class AlignedPairTest(ResonanceCacheIsolationMixin, TestCase):
    """ALIGNED pair → valence ALIGNED, kind AMPLIFY, direction ENVIRONMENT_DOMINANT, magnitude>0."""

    def test_aligned_pair(self) -> None:
        caster_obj = CharacterFactory()
        room_profile = RoomProfileFactory()
        room = room_profile.objectdb

        celestial = AffinityFactory(name="Celestial")
        resonance = ResonanceFactory(affinity=celestial)
        _set_room_resonance_value(room_profile, resonance, 40)

        AffinityInteractionFactory(
            source_affinity=celestial,
            environment_affinity=celestial,
            valence=ResonanceValence.ALIGNED,
            kind=AffinityInteractionKind.AMPLIFY,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("1.00"),
        )

        CharacterAuraFactory(
            character=caster_obj,
            celestial=Decimal("80.00"),
            primal=Decimal("10.00"),
            abyssal=Decimal("10.00"),
        )

        gift = GiftFactory()
        gift.resonances.add(resonance)
        technique = TechniqueFactory(gift=gift)

        cfg = get_resonance_environment_config()
        result = evaluate_resonance_environment(caster=caster_obj, room=room, technique=technique)

        self.assertIsInstance(result, ResonanceEnvironmentEffect)
        self.assertEqual(result.valence, ResonanceValence.ALIGNED)
        self.assertEqual(result.kind, AffinityInteractionKind.AMPLIFY)
        self.assertEqual(result.direction, ResonanceDirection.ENVIRONMENT_DOMINANT)
        self.assertGreater(result.magnitude, 0)
        # Verify formula: raw = 40 * (80/100) * 1.00 * 1.000 = 32 → round = 32
        expected = round(40 * Decimal("0.80") * Decimal("1.00") * cfg.base_coefficient)
        self.assertEqual(result.magnitude, expected)
        self.assertEqual(result.source_affinity, celestial)
        self.assertEqual(result.environment_affinity, celestial)
        # T4: interaction is the resolved AffinityInteraction; ALIGNED → backfire_difficulty=0
        self.assertIsNotNone(result.interaction)
        self.assertEqual(result.interaction.valence, ResonanceValence.ALIGNED)
        self.assertEqual(result.backfire_difficulty, 0)


class OpposedRejectTest(ResonanceCacheIsolationMixin, TestCase):
    """Abyssal-caster / Celestial-place REJECT: OPPOSED, ENVIRONMENT_DOMINANT."""

    def test_opposed_reject(self) -> None:
        caster_obj = CharacterFactory()
        room_profile = RoomProfileFactory()
        room = room_profile.objectdb

        abyssal = AffinityFactory(name="Abyssal")
        celestial = AffinityFactory(name="Celestial")
        celestial_res = ResonanceFactory(affinity=celestial)
        _set_room_resonance_value(room_profile, celestial_res, 50)

        AffinityInteractionFactory(
            source_affinity=abyssal,
            environment_affinity=celestial,
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REJECT,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("1.00"),
        )

        # Abyssal-dominant caster
        CharacterAuraFactory(
            character=caster_obj,
            celestial=Decimal("10.00"),
            primal=Decimal("20.00"),
            abyssal=Decimal("70.00"),
        )

        abyssal_res = ResonanceFactory(affinity=abyssal)
        gift = GiftFactory()
        gift.resonances.add(abyssal_res)
        technique = TechniqueFactory(gift=gift)

        cfg = get_resonance_environment_config()
        result = evaluate_resonance_environment(caster=caster_obj, room=room, technique=technique)

        self.assertEqual(result.valence, ResonanceValence.OPPOSED)
        self.assertEqual(result.kind, AffinityInteractionKind.REJECT)
        self.assertEqual(result.direction, ResonanceDirection.ENVIRONMENT_DOMINANT)
        # place_magnitude=50, caster_alignment=70/100=0.70, severity=1.00, coeff=1.000
        expected = round(50 * Decimal("0.70") * Decimal("1.00") * cfg.base_coefficient)
        self.assertEqual(result.magnitude, expected)
        self.assertEqual(result.source_affinity, abyssal)
        self.assertEqual(result.environment_affinity, celestial)
        # T4: interaction is the resolved AffinityInteraction; OPPOSED → backfire_difficulty>0
        self.assertIsNotNone(result.interaction)
        self.assertEqual(result.interaction.kind, AffinityInteractionKind.REJECT)
        expected_backfire = cfg.backfire_base_difficulty + round(
            result.magnitude * float(cfg.backfire_difficulty_per_magnitude)
        )
        self.assertEqual(result.backfire_difficulty, expected_backfire)


class SmallerSeverityTest(ResonanceCacheIsolationMixin, TestCase):
    """REPEL (severity 0.3) → smaller magnitude than REJECT (severity 1.0) at equal inputs."""

    def test_repel_smaller_than_reject(self) -> None:
        # Place: primal affinity (for repel) and celestial affinity (for reject)
        # Caster: celestial for repel, abyssal for reject
        # Both at 80% alignment, same place_magnitude=50
        caster_repel = CharacterFactory()
        caster_reject = CharacterFactory()
        room_profile_repel = RoomProfileFactory()
        room_profile_reject = RoomProfileFactory()
        room_repel = room_profile_repel.objectdb
        room_reject = room_profile_reject.objectdb

        celestial = AffinityFactory(name="Celestial")
        primal = AffinityFactory(name="Primal")
        abyssal = AffinityFactory(name="Abyssal")

        primal_res = ResonanceFactory(affinity=primal, name="PrimalResRepel")
        celestial_res = ResonanceFactory(affinity=celestial, name="CelestialResReject")

        # REPEL: celestial-caster / primal-place, severity=0.3
        _set_room_resonance_value(room_profile_repel, primal_res, 50)
        AffinityInteractionFactory(
            source_affinity=celestial,
            environment_affinity=primal,
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REPEL,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("0.30"),
        )
        CharacterAuraFactory(
            character=caster_repel,
            celestial=Decimal("80.00"),
            primal=Decimal("10.00"),
            abyssal=Decimal("10.00"),
        )
        celestial_gift_res = ResonanceFactory(affinity=celestial, name="CelestialGiftRepel")
        gift_repel = GiftFactory(name="GiftRepel")
        gift_repel.resonances.add(celestial_gift_res)
        technique_repel = TechniqueFactory(gift=gift_repel)

        # REJECT: abyssal-caster / celestial-place, severity=1.0
        _set_room_resonance_value(room_profile_reject, celestial_res, 50)
        AffinityInteractionFactory(
            source_affinity=abyssal,
            environment_affinity=celestial,
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REJECT,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("1.00"),
        )
        CharacterAuraFactory(
            character=caster_reject,
            celestial=Decimal("10.00"),
            primal=Decimal("10.00"),
            abyssal=Decimal("80.00"),
        )
        abyssal_gift_res = ResonanceFactory(affinity=abyssal, name="AbyssalGiftReject")
        gift_reject = GiftFactory(name="GiftReject")
        gift_reject.resonances.add(abyssal_gift_res)
        technique_reject = TechniqueFactory(gift=gift_reject)

        result_repel = evaluate_resonance_environment(
            caster=caster_repel, room=room_repel, technique=technique_repel
        )
        result_reject = evaluate_resonance_environment(
            caster=caster_reject, room=room_reject, technique=technique_reject
        )

        # REPEL severity=0.3 vs REJECT severity=1.0 at equal inputs → repel magnitude < reject
        self.assertLess(result_repel.magnitude, result_reject.magnitude)
        self.assertEqual(result_repel.kind, AffinityInteractionKind.REPEL)
        self.assertEqual(result_reject.kind, AffinityInteractionKind.REJECT)


class CorruptDirectionTest(ResonanceCacheIsolationMixin, TestCase):
    """CORRUPT pair direction test: caster vs place strength comparison."""

    def _make_corrupt_setup(self):
        """Create shared objects for corrupt direction tests.

        Abyssal caster / Primal place = CORRUPT. Returns (abyssal_aff, primal_aff,
        primal_res, abyssal_res, interaction).
        """
        abyssal = AffinityFactory(name="Abyssal")
        primal = AffinityFactory(name="Primal")
        primal_res = ResonanceFactory(affinity=primal, name="PrimalResCorrupt")
        abyssal_res = ResonanceFactory(affinity=abyssal, name="AbyssalResCorrupt")

        interaction = AffinityInteractionFactory(
            source_affinity=abyssal,
            environment_affinity=primal,
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.CORRUPT,
            aggressor=AffinityInteractionAggressor.CASTER,
            severity_multiplier=Decimal("1.00"),
        )
        return abyssal, primal, primal_res, abyssal_res, interaction

    def test_corrupt_strong_caster_vs_weak_place_is_caster_dominant(self) -> None:
        """Strong abyssal caster (80% aura, strength 40) vs weak place (mag=10): CASTER_DOMINANT."""
        _, _, primal_res, abyssal_res, _ = self._make_corrupt_setup()
        cfg = get_resonance_environment_config()

        caster_obj = CharacterFactory()
        room_profile = RoomProfileFactory()
        room = room_profile.objectdb
        _set_room_resonance_value(room_profile, primal_res, 10)

        CharacterAuraFactory(
            character=caster_obj,
            celestial=Decimal("10.00"),
            primal=Decimal("10.00"),
            abyssal=Decimal("80.00"),
        )

        gift = GiftFactory()
        gift.resonances.add(abyssal_res)
        technique = TechniqueFactory(gift=gift)

        result = evaluate_resonance_environment(caster=caster_obj, room=room, technique=technique)

        # caster_strength = 80 * 0.500 = 40; place_magnitude = 10
        # caster_strength - place_magnitude = 30 > balanced_band(10) → CASTER_DOMINANT
        caster_strength = float(Decimal("80.00") * cfg.caster_power_scalar)
        self.assertGreater(caster_strength - 10, cfg.balanced_band)
        self.assertEqual(result.direction, ResonanceDirection.CASTER_DOMINANT)
        self.assertEqual(result.kind, AffinityInteractionKind.CORRUPT)
        self.assertGreater(result.magnitude, 0)
        # T4: CORRUPT is OPPOSED valence → backfire_difficulty > 0; interaction is resolved
        self.assertIsNotNone(result.interaction)
        self.assertEqual(result.interaction.kind, AffinityInteractionKind.CORRUPT)
        expected_backfire = cfg.backfire_base_difficulty + round(
            result.magnitude * float(cfg.backfire_difficulty_per_magnitude)
        )
        self.assertEqual(result.backfire_difficulty, expected_backfire)

    def test_corrupt_weak_caster_vs_strong_place_is_environment_dominant(self) -> None:
        """Weak abyssal caster (strength 15) vs strong primal place (80): ENVIRONMENT_DOMINANT."""
        _, _, primal_res, abyssal_res, _ = self._make_corrupt_setup()
        cfg = get_resonance_environment_config()

        caster_obj = CharacterFactory()
        room_profile = RoomProfileFactory()
        room = room_profile.objectdb
        _set_room_resonance_value(room_profile, primal_res, 80)

        CharacterAuraFactory(
            character=caster_obj,
            celestial=Decimal("40.00"),
            primal=Decimal("30.00"),
            abyssal=Decimal("30.00"),
        )

        gift = GiftFactory()
        gift.resonances.add(abyssal_res)
        technique = TechniqueFactory(gift=gift)

        result = evaluate_resonance_environment(caster=caster_obj, room=room, technique=technique)

        # caster_strength = 30 * 0.500 = 15; place_magnitude = 80
        # place_magnitude - caster_strength = 65 > balanced_band(10) → ENVIRONMENT_DOMINANT
        caster_strength = float(Decimal("30.00") * cfg.caster_power_scalar)
        self.assertGreater(80 - caster_strength, cfg.balanced_band)
        self.assertEqual(result.direction, ResonanceDirection.ENVIRONMENT_DOMINANT)
        self.assertEqual(result.kind, AffinityInteractionKind.CORRUPT)
        self.assertGreater(result.magnitude, 0)
        # T4: CORRUPT is OPPOSED valence → backfire_difficulty > 0; interaction is resolved
        self.assertIsNotNone(result.interaction)
        expected_backfire = cfg.backfire_base_difficulty + round(
            result.magnitude * float(cfg.backfire_difficulty_per_magnitude)
        )
        self.assertEqual(result.backfire_difficulty, expected_backfire)

    def test_corrupt_within_balanced_band_is_balanced(self) -> None:
        """Within balanced_band → BALANCED direction.

        balanced_band=10. caster abyssal=42% → strength = 42 * 0.500 = 21.
        place_magnitude=25. |21 - 25| = 4, within band of 10 → BALANCED.
        """
        _, _, primal_res, abyssal_res, _ = self._make_corrupt_setup()
        cfg = get_resonance_environment_config()

        caster_obj = CharacterFactory()
        room_profile = RoomProfileFactory()
        room = room_profile.objectdb
        _set_room_resonance_value(room_profile, primal_res, 25)

        CharacterAuraFactory(
            character=caster_obj,
            celestial=Decimal("20.00"),
            primal=Decimal("38.00"),
            abyssal=Decimal("42.00"),
        )

        gift = GiftFactory()
        gift.resonances.add(abyssal_res)
        technique = TechniqueFactory(gift=gift)

        result = evaluate_resonance_environment(caster=caster_obj, room=room, technique=technique)

        # caster_strength = 42 * 0.500 = 21; place_magnitude = 25
        # |21 - 25| = 4 ≤ 10 → BALANCED
        caster_strength = float(Decimal("42.00") * cfg.caster_power_scalar)
        self.assertLessEqual(abs(caster_strength - 25), cfg.balanced_band)
        self.assertEqual(result.direction, ResonanceDirection.BALANCED)
        self.assertEqual(result.kind, AffinityInteractionKind.CORRUPT)
        self.assertGreater(result.magnitude, 0)
        # T4: CORRUPT is OPPOSED valence → backfire_difficulty > 0; interaction is resolved
        self.assertIsNotNone(result.interaction)
        expected_backfire = cfg.backfire_base_difficulty + round(
            result.magnitude * float(cfg.backfire_difficulty_per_magnitude)
        )
        self.assertEqual(result.backfire_difficulty, expected_backfire)


class MissingAuraTest(ResonanceCacheIsolationMixin, TestCase):
    """Missing CharacterAura → inert effect (valence="", magnitude=0)."""

    def test_missing_aura_returns_inert_cast_time(self) -> None:
        caster_obj = CharacterFactory()
        room_profile = RoomProfileFactory()
        room = room_profile.objectdb

        celestial = AffinityFactory(name="Celestial")
        celestial_res = ResonanceFactory(affinity=celestial)
        _set_room_resonance_value(room_profile, celestial_res, 50)

        abyssal = AffinityFactory(name="Abyssal")
        AffinityInteractionFactory(
            source_affinity=abyssal,
            environment_affinity=celestial,
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REJECT,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("1.00"),
        )

        abyssal_res = ResonanceFactory(affinity=abyssal)
        gift = GiftFactory()
        gift.resonances.add(abyssal_res)
        technique = TechniqueFactory(gift=gift)

        # No CharacterAura created → should be inert
        result = evaluate_resonance_environment(caster=caster_obj, room=room, technique=technique)

        self.assertEqual(result.valence, "")
        self.assertEqual(result.kind, "")
        self.assertEqual(result.magnitude, 0)
        self.assertIsNone(result.source_affinity)
        self.assertIsNone(result.environment_affinity)
        # T4: inert result → interaction=None, backfire_difficulty=0
        self.assertIsNone(result.interaction)
        self.assertEqual(result.backfire_difficulty, 0)


class MultiAffinityGiftTest(ResonanceCacheIsolationMixin, TestCase):
    """Multi-affinity gift: highest severity_multiplier wins; tiebreak by Affinity.name."""

    def test_highest_severity_chosen(self) -> None:
        """2 resonances, 2 affinities, 2 different-severity interactions → highest chosen."""
        caster_obj = CharacterFactory()
        room_profile = RoomProfileFactory()
        room = room_profile.objectdb

        # Place: celestial affinity
        celestial = AffinityFactory(name="Celestial")
        primal = AffinityFactory(name="Primal")
        abyssal = AffinityFactory(name="Abyssal")
        celestial_res = ResonanceFactory(affinity=celestial, name="CelestialR1")
        _set_room_resonance_value(room_profile, celestial_res, 30)

        # Gift has two resonances: one abyssal, one primal
        # abyssal vs celestial = REJECT severity=1.0
        # primal vs celestial = REJECT severity=0.3
        abyssal_gift_res = ResonanceFactory(affinity=abyssal, name="AbyssalGR")
        primal_gift_res = ResonanceFactory(affinity=primal, name="PrimalGR")

        AffinityInteractionFactory(
            source_affinity=abyssal,
            environment_affinity=celestial,
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REJECT,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("1.00"),
        )
        AffinityInteractionFactory(
            source_affinity=primal,
            environment_affinity=celestial,
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REJECT,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("0.30"),
        )

        CharacterAuraFactory(
            character=caster_obj,
            celestial=Decimal("10.00"),
            primal=Decimal("20.00"),
            abyssal=Decimal("70.00"),
        )

        gift = GiftFactory()
        gift.resonances.add(abyssal_gift_res)
        gift.resonances.add(primal_gift_res)
        technique = TechniqueFactory(gift=gift)

        result = evaluate_resonance_environment(caster=caster_obj, room=room, technique=technique)

        # Should choose abyssal (severity 1.0 > 0.3)
        self.assertEqual(result.source_affinity, abyssal)
        self.assertEqual(result.kind, AffinityInteractionKind.REJECT)
        # magnitude based on abyssal alignment (70%)
        cfg = get_resonance_environment_config()
        expected = round(30 * Decimal("0.70") * Decimal("1.00") * cfg.base_coefficient)
        self.assertEqual(result.magnitude, expected)
        # T4: OPPOSED REJECT → interaction is resolved; backfire_difficulty > 0
        self.assertIsNotNone(result.interaction)
        self.assertEqual(result.interaction.kind, AffinityInteractionKind.REJECT)
        expected_backfire = cfg.backfire_base_difficulty + round(
            result.magnitude * float(cfg.backfire_difficulty_per_magnitude)
        )
        self.assertEqual(result.backfire_difficulty, expected_backfire)

    def test_equal_severity_tiebreak_by_affinity_name(self) -> None:
        """Equal severity_multiplier → tiebreak by Affinity.name ascending.

        Use canonical affinity names so the aura field lookup works:
        "Abyssal" < "Celestial" alphabetically → Abyssal chosen.
        """
        caster_obj = CharacterFactory()
        room_profile = RoomProfileFactory()
        room = room_profile.objectdb

        # Place: primal affinity
        primal_aff = AffinityFactory(name="Primal")
        abyssal_aff = AffinityFactory(name="Abyssal")
        celestial_aff = AffinityFactory(name="Celestial")

        primal_res = ResonanceFactory(affinity=primal_aff, name="PrimalRTiebreak")
        _set_room_resonance_value(room_profile, primal_res, 20)

        abyssal_res = ResonanceFactory(affinity=abyssal_aff, name="AbyssalRTiebreak")
        celestial_res = ResonanceFactory(affinity=celestial_aff, name="CelestialRTiebreak")

        # Both interactions have same severity
        AffinityInteractionFactory(
            source_affinity=abyssal_aff,
            environment_affinity=primal_aff,
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REPEL,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("0.50"),
        )
        AffinityInteractionFactory(
            source_affinity=celestial_aff,
            environment_affinity=primal_aff,
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REPEL,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("0.50"),
        )

        # caster has both celestial and abyssal
        CharacterAuraFactory(
            character=caster_obj,
            celestial=Decimal("30.00"),
            primal=Decimal("10.00"),
            abyssal=Decimal("60.00"),
        )

        gift = GiftFactory()
        gift.resonances.add(abyssal_res)
        gift.resonances.add(celestial_res)
        technique = TechniqueFactory(gift=gift)

        result = evaluate_resonance_environment(caster=caster_obj, room=room, technique=technique)

        # Tiebreak: "Abyssal" < "Celestial" → abyssal_aff chosen
        self.assertEqual(result.source_affinity, abyssal_aff)


class PlaceDominantAffinityTiebreakTest(ResonanceCacheIsolationMixin, TestCase):
    """Equal summed effective_value → place affinity by Affinity.name ascending."""

    def test_place_affinity_tiebreak_by_name(self) -> None:
        """Equal-valued place resonances → affinity with alphabetically lower name is dominant.

        Place has both Celestial and Primal resonances at equal magnitude.
        "Celestial" < "Primal" alphabetically → Celestial is dominant.
        Working affinity is Abyssal (caster), so interactions are:
        Abyssal→Celestial (REJECT) and Abyssal→Primal (REPEL).
        The test verifies that environment_affinity == celestial.
        """
        caster_obj = CharacterFactory()
        room_profile = RoomProfileFactory()
        room = room_profile.objectdb

        # "Celestial" < "Primal" alphabetically
        celestial_aff = AffinityFactory(name="Celestial")
        primal_aff = AffinityFactory(name="Primal")
        abyssal_aff = AffinityFactory(name="Abyssal")

        celestial_place_res = ResonanceFactory(affinity=celestial_aff, name="CelestialPlace")
        primal_place_res = ResonanceFactory(affinity=primal_aff, name="PrimalPlace")
        abyssal_gift_res = ResonanceFactory(affinity=abyssal_aff, name="AbyssalGift")

        # Equal magnitude for both place affinities
        _set_room_resonance_value(room_profile, celestial_place_res, 30)
        _set_room_resonance_value(room_profile, primal_place_res, 30)

        AffinityInteractionFactory(
            source_affinity=abyssal_aff,
            environment_affinity=celestial_aff,
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REJECT,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("1.00"),
        )
        AffinityInteractionFactory(
            source_affinity=abyssal_aff,
            environment_affinity=primal_aff,
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REPEL,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("1.00"),
        )

        CharacterAuraFactory(
            character=caster_obj,
            celestial=Decimal("10.00"),
            primal=Decimal("10.00"),
            abyssal=Decimal("80.00"),
        )

        gift = GiftFactory()
        gift.resonances.add(abyssal_gift_res)
        technique = TechniqueFactory(gift=gift)

        result = evaluate_resonance_environment(caster=caster_obj, room=room, technique=technique)

        # "Celestial" < "Primal" → environment_affinity should be celestial_aff
        self.assertEqual(result.environment_affinity, celestial_aff)
        self.assertEqual(result.kind, AffinityInteractionKind.REJECT)


class InertCasesTest(ResonanceCacheIsolationMixin, TestCase):
    """No resonances or no AffinityInteraction row → inert effect."""

    def test_no_cascade_resonances_returns_inert(self) -> None:
        """Room with no cascade resonance → inert."""
        caster_obj = CharacterFactory()
        room_profile = RoomProfileFactory()
        room = room_profile.objectdb

        abyssal = AffinityFactory(name="Abyssal")
        abyssal_res = ResonanceFactory(affinity=abyssal)

        CharacterAuraFactory(
            character=caster_obj,
            celestial=Decimal("10.00"),
            primal=Decimal("10.00"),
            abyssal=Decimal("80.00"),
        )

        gift = GiftFactory()
        gift.resonances.add(abyssal_res)
        technique = TechniqueFactory(gift=gift)

        # No tag_room_resonance called → room has no resonance modifiers
        result = evaluate_resonance_environment(caster=caster_obj, room=room, technique=technique)

        self.assertEqual(result.valence, "")
        self.assertEqual(result.magnitude, 0)
        # T4: inert → interaction=None, backfire_difficulty=0
        self.assertIsNone(result.interaction)
        self.assertEqual(result.backfire_difficulty, 0)

    def test_no_affinity_interaction_row_returns_inert(self) -> None:
        """Room has resonance but no AffinityInteraction row authored → inert."""
        caster_obj = CharacterFactory()
        room_profile = RoomProfileFactory()
        room = room_profile.objectdb

        abyssal = AffinityFactory(name="Abyssal")
        celestial = AffinityFactory(name="Celestial")
        celestial_res = ResonanceFactory(affinity=celestial)
        _set_room_resonance_value(room_profile, celestial_res, 50)

        # No AffinityInteractionFactory created for (abyssal, celestial) pair
        abyssal_res = ResonanceFactory(affinity=abyssal)

        CharacterAuraFactory(
            character=caster_obj,
            celestial=Decimal("10.00"),
            primal=Decimal("10.00"),
            abyssal=Decimal("80.00"),
        )

        gift = GiftFactory()
        gift.resonances.add(abyssal_res)
        technique = TechniqueFactory(gift=gift)

        result = evaluate_resonance_environment(caster=caster_obj, room=room, technique=technique)

        self.assertEqual(result.valence, "")
        self.assertEqual(result.magnitude, 0)
        # T4: inert → interaction=None, backfire_difficulty=0
        self.assertIsNone(result.interaction)
        self.assertEqual(result.backfire_difficulty, 0)

    def test_zero_magnitude_result_is_inert(self) -> None:
        """round(raw) == 0 → inert (valence="")."""
        caster_obj = CharacterFactory()
        room_profile = RoomProfileFactory()
        room = room_profile.objectdb

        abyssal = AffinityFactory(name="Abyssal")
        celestial = AffinityFactory(name="Celestial")
        celestial_res = ResonanceFactory(affinity=celestial)
        _set_room_resonance_value(room_profile, celestial_res, 1)  # tiny magnitude

        AffinityInteractionFactory(
            source_affinity=abyssal,
            environment_affinity=celestial,
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REPEL,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("0.30"),
        )

        # Very low abyssal alignment (1%)
        CharacterAuraFactory(
            character=caster_obj,
            celestial=Decimal("10.00"),
            primal=Decimal("89.00"),
            abyssal=Decimal("1.00"),
        )

        abyssal_res = ResonanceFactory(affinity=abyssal)
        gift = GiftFactory()
        gift.resonances.add(abyssal_res)
        technique = TechniqueFactory(gift=gift)

        result = evaluate_resonance_environment(caster=caster_obj, room=room, technique=technique)

        # raw = 1 * 0.01 * 0.30 * 1.000 = 0.003 → round = 0 → inert
        self.assertEqual(result.magnitude, 0)
        self.assertEqual(result.valence, "")
        # T4: zero-magnitude inert → interaction=None, backfire_difficulty=0
        self.assertIsNone(result.interaction)
        self.assertEqual(result.backfire_difficulty, 0)


class PresenceTimeTest(ResonanceCacheIsolationMixin, TestCase):
    """Presence-time (technique=None) → caster aura dominant affinity used, no gift."""

    def test_presence_time_uses_aura_dominant_affinity(self) -> None:
        caster_obj = CharacterFactory()
        room_profile = RoomProfileFactory()
        room = room_profile.objectdb

        celestial = AffinityFactory(name="Celestial")
        abyssal = AffinityFactory(name="Abyssal")
        celestial_res = ResonanceFactory(affinity=celestial)
        _set_room_resonance_value(room_profile, celestial_res, 40)

        AffinityInteractionFactory(
            source_affinity=abyssal,
            environment_affinity=celestial,
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REJECT,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("1.00"),
        )

        # Abyssal-dominant caster
        CharacterAuraFactory(
            character=caster_obj,
            celestial=Decimal("10.00"),
            primal=Decimal("20.00"),
            abyssal=Decimal("70.00"),
        )

        # technique=None → presence-time evaluation
        result = evaluate_resonance_environment(caster=caster_obj, room=room, technique=None)

        cfg = get_resonance_environment_config()
        self.assertEqual(result.valence, ResonanceValence.OPPOSED)
        self.assertEqual(result.source_affinity, abyssal)
        self.assertEqual(result.environment_affinity, celestial)
        expected = round(40 * Decimal("0.70") * Decimal("1.00") * cfg.base_coefficient)
        self.assertEqual(result.magnitude, expected)
        # T4: OPPOSED → interaction is resolved; backfire_difficulty uses formula
        self.assertIsNotNone(result.interaction)
        self.assertEqual(result.interaction.kind, AffinityInteractionKind.REJECT)
        expected_backfire = cfg.backfire_base_difficulty + round(
            result.magnitude * float(cfg.backfire_difficulty_per_magnitude)
        )
        self.assertEqual(result.backfire_difficulty, expected_backfire)

    def test_presence_time_missing_aura_returns_inert(self) -> None:
        """technique=None + no CharacterAura → inert."""
        caster_obj = CharacterFactory()
        room_profile = RoomProfileFactory()
        room = room_profile.objectdb

        celestial = AffinityFactory(name="Celestial")
        celestial_res = ResonanceFactory(affinity=celestial)
        _set_room_resonance_value(room_profile, celestial_res, 40)

        abyssal = AffinityFactory(name="Abyssal")
        AffinityInteractionFactory(
            source_affinity=abyssal,
            environment_affinity=celestial,
            valence=ResonanceValence.OPPOSED,
            kind=AffinityInteractionKind.REJECT,
            aggressor=AffinityInteractionAggressor.ENVIRONMENT,
            severity_multiplier=Decimal("1.00"),
        )

        # No CharacterAura created
        result = evaluate_resonance_environment(caster=caster_obj, room=room, technique=None)

        self.assertEqual(result.valence, "")
        self.assertEqual(result.magnitude, 0)
        # T4: inert → interaction=None, backfire_difficulty=0
        self.assertIsNone(result.interaction)
        self.assertEqual(result.backfire_difficulty, 0)
