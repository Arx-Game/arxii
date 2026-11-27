"""Deed classification of GainSource (slice 4 of #4672)."""

from django.test import TestCase

from world.magic.constants import (
    ACCELERATED_GAIN_SOURCES,
    AFFINITY_RATE_EXEMPT_SOURCES,
    AFFINITY_RATE_SCALED_SOURCES,
    DEED_GAIN_SOURCES,
    GAIN_BONUS_CALLER_ROLLED_SOURCES,
    GAIN_BONUS_EXEMPT_SOURCES,
    GAIN_BONUS_ROLLED_SOURCES,
    NON_ACCELERATED_GAIN_SOURCES,
    NON_DEED_GAIN_SOURCES,
    GainSource,
)


class DeedClassificationTests(TestCase):
    def test_every_gain_source_is_in_exactly_one_deed_set(self) -> None:
        deeds = {GainSource(v) for v in DEED_GAIN_SOURCES}
        non_deeds = {GainSource(v) for v in NON_DEED_GAIN_SOURCES}
        self.assertEqual(set(GainSource), deeds | non_deeds)
        self.assertEqual(deeds & non_deeds, set())

    def test_casting_and_conversions_are_not_deeds(self) -> None:
        for source in (
            GainSource.FALL_CONVERSION,
            GainSource.DRIFT_CORRECTION,
            GainSource.COMPROMISE,
            GainSource.STAFF_GRANT,
            GainSource.DISTINCTION,
            GainSource.ROOM_RESIDENCE,
            GainSource.OUTFIT_TRICKLE,
            GainSource.SANCTUM_WEAVING,
        ):
            with self.subTest(source=source):
                self.assertIn(source, NON_DEED_GAIN_SOURCES)

    def test_scene_and_mission_gains_are_deeds(self) -> None:
        for source in (
            GainSource.POSE_ENDORSEMENT,
            GainSource.SCENE_ENTRY,
            GainSource.MISSION_REWARD,
            GainSource.WORSHIP_RITE,
        ):
            with self.subTest(source=source):
                self.assertIn(source, DEED_GAIN_SOURCES)

    def test_drift_correction_is_never_accelerated(self) -> None:
        self.assertIn(GainSource.DRIFT_CORRECTION, NON_ACCELERATED_GAIN_SOURCES)


class AffinityRateClassificationTests(TestCase):
    def test_every_gain_source_is_either_exempt_from_the_earn_rate_or_scaled_by_it(self) -> None:
        exempt = {GainSource(v) for v in AFFINITY_RATE_EXEMPT_SOURCES}
        scaled = {GainSource(v) for v in AFFINITY_RATE_SCALED_SOURCES}
        self.assertEqual(set(GainSource), exempt | scaled)
        self.assertEqual(exempt & scaled, set())

    def test_distinction_is_exempt_because_it_reconciles_against_its_ledger_rows(self) -> None:
        self.assertIn(GainSource.DISTINCTION, AFFINITY_RATE_EXEMPT_SOURCES)


class GainBonusClassificationTests(TestCase):
    def test_every_gain_source_meets_the_bonus_check_in_exactly_one_way(self) -> None:
        exempt = {GainSource(v) for v in GAIN_BONUS_EXEMPT_SOURCES}
        caller_rolled = {GainSource(v) for v in GAIN_BONUS_CALLER_ROLLED_SOURCES}
        rolled = {GainSource(v) for v in GAIN_BONUS_ROLLED_SOURCES}
        self.assertEqual(set(GainSource), exempt | caller_rolled | rolled)
        self.assertEqual(exempt & caller_rolled, set())
        self.assertEqual(exempt & rolled, set())
        self.assertEqual(caller_rolled & rolled, set())

    def test_trickle_harvest_is_accelerated_rate_scaled_and_not_a_deed(self) -> None:
        self.assertIn(GainSource.TRICKLE_HARVEST, ACCELERATED_GAIN_SOURCES)
        self.assertIn(GainSource.TRICKLE_HARVEST, AFFINITY_RATE_SCALED_SOURCES)
        self.assertIn(GainSource.TRICKLE_HARVEST, NON_DEED_GAIN_SOURCES)
