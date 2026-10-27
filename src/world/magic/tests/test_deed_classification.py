"""Deed classification of GainSource (slice 4 of #4672)."""

from django.test import TestCase

from world.magic.constants import (
    DEED_GAIN_SOURCES,
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
            GainSource.PENANCE,
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
