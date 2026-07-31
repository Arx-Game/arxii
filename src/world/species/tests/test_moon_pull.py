"""Moon pull + lycan control checks (#2845). SQLite tier — apply_condition is
PG-only, so consequence application is patched where the reconcile would reach it."""

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.models import CharacterDistinction
from world.game_clock.constants import TimePhase
from world.species.factories import ensure_moon_bound_distinction
from world.species.moon_constants import (
    MOON_EXEMPT_LEVEL,
    MOON_FORM_CLARITY_MAX_BONUS,
    MOON_PULL_CHECK_THRESHOLD,
)
from world.species.moon_pull import felt_moon_pull, moon_clarity_instance_value
from world.species.moon_sensitivity import reconcile_moon_pull


def _night_full_moon():
    return patch.multiple(
        "world.species.moon_pull",
        get_ic_phase=lambda: TimePhase.NIGHT,
        get_moon_illumination=lambda: 1.0,
    )


class FeltMoonPullTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.room = RoomProfileFactory(is_outdoor=True).objectdb

    def test_daytime_pulls_nothing(self):
        with patch("world.species.moon_pull.get_ic_phase", return_value=TimePhase.DAY):
            exposure = felt_moon_pull(self.sheet.character, self.room)
        self.assertEqual(exposure.pull, 0)

    def test_clear_full_moon_pulls_at_full_base(self):
        with _night_full_moon():
            exposure = felt_moon_pull(self.sheet.character, self.room)
        self.assertEqual(exposure.base, 10)
        self.assertEqual(exposure.pull, 10)
        self.assertGreaterEqual(exposure.pull, MOON_PULL_CHECK_THRESHOLD)

    def test_half_moon_stays_below_the_check_threshold(self):
        with patch.multiple(
            "world.species.moon_pull",
            get_ic_phase=lambda: TimePhase.NIGHT,
            get_moon_illumination=lambda: 0.5,
        ):
            exposure = felt_moon_pull(self.sheet.character, self.room)
        self.assertLess(exposure.pull, MOON_PULL_CHECK_THRESHOLD)

    def test_cloud_shade_dampens_the_pull(self):
        with (
            _night_full_moon(),
            patch("world.species.moon_pull._shade_value", return_value=3),
        ):
            exposure = felt_moon_pull(self.sheet.character, self.room)
        self.assertEqual(exposure.pull, 7)

    def test_indoors_pulls_nothing(self):
        indoor = RoomProfileFactory(is_outdoor=False).objectdb
        with _night_full_moon():
            exposure = felt_moon_pull(self.sheet.character, indoor)
        self.assertEqual(exposure.pull, 0)

    def test_clarity_multiplier_scales_with_pull(self):
        with _night_full_moon():
            clarity = moon_clarity_instance_value(self.sheet.character, self.room)
        self.assertAlmostEqual(clarity, 1.0 + MOON_FORM_CLARITY_MAX_BONUS)
        with patch("world.species.moon_pull.get_ic_phase", return_value=TimePhase.DAY):
            self.assertEqual(moon_clarity_instance_value(self.sheet.character, self.room), 1.0)


class MoonReconcileTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.distinction = ensure_moon_bound_distinction()

    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.room = RoomProfileFactory(is_outdoor=True).objectdb
        self.character.location = self.room

    def _bind(self):
        CharacterDistinction.objects.create(character=self.sheet, distinction=self.distinction)

    def test_unbound_character_never_checks(self):
        with (
            _night_full_moon(),
            patch("world.species.moon_sensitivity._control_holds") as check,
        ):
            reconcile_moon_pull(self.character)
        check.assert_not_called()

    def test_weak_pull_never_checks(self):
        self._bind()
        with (
            patch.multiple(
                "world.species.moon_pull",
                get_ic_phase=lambda: TimePhase.NIGHT,
                get_moon_illumination=lambda: 0.4,
            ),
            patch("world.species.moon_sensitivity._control_holds") as check,
        ):
            reconcile_moon_pull(self.character)
        check.assert_not_called()

    def test_failed_check_forces_shift_and_berserk(self):
        self._bind()
        with (
            _night_full_moon(),
            patch("world.species.moon_sensitivity._control_holds", return_value=False),
            patch("world.species.moon_sensitivity._force_battle_form_shift") as shift,
            patch("world.species.moon_sensitivity._apply_berserk") as berserk,
        ):
            reconcile_moon_pull(self.character)
        shift.assert_called_once()
        berserk.assert_called_once()

    def test_held_check_changes_nothing(self):
        self._bind()
        with (
            _night_full_moon(),
            patch("world.species.moon_sensitivity._control_holds", return_value=True),
            patch("world.species.moon_sensitivity._lose_control") as lost,
        ):
            reconcile_moon_pull(self.character)
        lost.assert_not_called()

    def test_high_tier_exempt_unless_impaired(self):
        self._bind()
        with (
            _night_full_moon(),
            patch.object(
                type(self.sheet),
                "current_level",
                new_callable=lambda: property(lambda _self: MOON_EXEMPT_LEVEL),
            ),
            patch("world.species.moon_sensitivity._is_impaired", return_value=False),
            patch("world.species.moon_sensitivity._control_holds") as check,
        ):
            reconcile_moon_pull(self.character)
        check.assert_not_called()
        with (
            _night_full_moon(),
            patch.object(
                type(self.sheet),
                "current_level",
                new_callable=lambda: property(lambda _self: MOON_EXEMPT_LEVEL),
            ),
            patch("world.species.moon_sensitivity._is_impaired", return_value=True),
            patch("world.species.moon_sensitivity._control_holds", return_value=True) as check,
        ):
            reconcile_moon_pull(self.character)
        check.assert_called_once()

    def test_already_berserk_skips_the_window(self):
        self._bind()
        with (
            _night_full_moon(),
            patch(
                "world.species.moon_sensitivity._active_berserk_instance",
                return_value=object(),
            ),
            patch("world.species.moon_sensitivity._control_holds") as check,
        ):
            reconcile_moon_pull(self.character)
        check.assert_not_called()


class BerserkContentTest(TestCase):
    def test_seed_creates_control_category_berserk(self):
        from world.conditions.berserk_content import ensure_berserk_content
        from world.conditions.models import ConditionTemplate

        ensure_berserk_content()
        template = ConditionTemplate.objects.get(name="Berserk")
        self.assertTrue(template.category.alters_behavior)
        self.assertTrue(template.has_progression)
        self.assertEqual(template.stages.count(), 1)

    def test_seed_heals_a_miscategorized_row(self):
        """A hand-loaded Berserk in a non-behavioral category gets re-anchored."""
        from world.conditions.berserk_content import ensure_berserk_content
        from world.conditions.models import ConditionCategory, ConditionTemplate

        wrong = ConditionCategory.objects.create(name="Emotional", alters_behavior=False)
        ConditionTemplate.objects.create(
            name="Berserk", category=wrong, description="fixture-shaped impostor"
        )
        ensure_berserk_content()
        template = ConditionTemplate.objects.get(name="Berserk")
        self.assertTrue(template.category.alters_behavior)
        self.assertEqual(template.category.name, "Control")
