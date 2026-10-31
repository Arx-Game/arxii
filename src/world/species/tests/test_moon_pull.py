"""Moon pull + lycan control checks (#2845). SQLite tier — apply_condition is
PG-only, so consequence application is patched where the reconcile would reach it."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.constants import ControlLossFiresOn
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionTemplateFactory,
    ControlLossTriggerFactory,
)
from world.game_clock.constants import TimePhase
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.species.moon_constants import MOON_FORM_CLARITY_MAX_BONUS
from world.species.moon_pull import felt_moon_pull, moon_clarity_instance_value
from world.species.moon_sensitivity import is_moon_bound, reconcile_moon_pull

# What the seeded moon trigger authors (moon_provisioning): the pull that rolls, the tier
# at which the roll stops unless impaired.
TRIGGER_MIN_PULL = 6
TRIGGER_EXEMPT_LEVEL = 6


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
        self.assertGreaterEqual(exposure.pull, TRIGGER_MIN_PULL)

    def test_half_moon_stays_below_the_check_threshold(self):
        with patch.multiple(
            "world.species.moon_pull",
            get_ic_phase=lambda: TimePhase.NIGHT,
            get_moon_illumination=lambda: 0.5,
        ):
            exposure = felt_moon_pull(self.sheet.character, self.room)
        self.assertLess(exposure.pull, TRIGGER_MIN_PULL)

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
    """The moon window fires the character's MOON_PULL trigger; the engine decides."""

    @classmethod
    def setUpTestData(cls):
        cls.trigger = ControlLossTriggerFactory(
            fires_on=ControlLossFiresOn.MOON_PULL,
            min_moon_pull=TRIGGER_MIN_PULL,
            exempt_from_level=TRIGGER_EXEMPT_LEVEL,
            impaired_willpower_drop=10,
        )

    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.room = RoomProfileFactory(is_outdoor=True).objectdb
        self.character.location = self.room

    def _bind(self):
        ConditionInstanceFactory(target=self.character, condition=self.trigger.vulnerability)
        tenure = RosterTenureFactory(
            roster_entry=RosterEntryFactory(character_sheet=self.sheet), end_date=None
        )
        self.character.db_account = tenure.player_data.account

    def _level(self, level):
        return patch.object(
            type(self.sheet),
            "current_level",
            new_callable=lambda: property(lambda _self: level),
        )

    def test_unbound_character_never_checks(self):
        self.assertFalse(is_moon_bound(self.sheet))
        with (
            _night_full_moon(),
            patch("world.checks.services.perform_check_with_modifiers") as check,
        ):
            reconcile_moon_pull(self.character)
        check.assert_not_called()

    def test_a_carrier_of_a_moon_trigger_condition_is_moon_bound(self):
        self._bind()
        self.assertTrue(is_moon_bound(self.sheet))
        other = ConditionInstanceFactory(
            target=CharacterSheetFactory().character, condition=ConditionTemplateFactory()
        )
        self.assertFalse(is_moon_bound(other.target.character_sheet))

    def test_weak_pull_never_checks(self):
        self._bind()
        with (
            patch.multiple(
                "world.species.moon_pull",
                get_ic_phase=lambda: TimePhase.NIGHT,
                get_moon_illumination=lambda: 0.4,
            ),
            patch("world.checks.services.perform_check_with_modifiers") as check,
        ):
            reconcile_moon_pull(self.character)
        check.assert_not_called()

    def test_full_moon_rolls_the_trigger(self):
        self._bind()
        with (
            _night_full_moon(),
            self._level(1),
            patch(
                "world.checks.services.perform_check_with_modifiers",
                return_value=MagicMock(outcome=None),
            ) as check,
        ):
            reconcile_moon_pull(self.character)
        check.assert_called_once()
        self.assertEqual(check.call_args.args[1], self.trigger.check_type)

    def test_high_tier_exempt_unless_impaired(self):
        self._bind()
        with (
            _night_full_moon(),
            self._level(TRIGGER_EXEMPT_LEVEL),
            patch("world.conditions.control_loss._is_impaired", return_value=False),
            patch("world.checks.services.perform_check_with_modifiers") as check,
        ):
            reconcile_moon_pull(self.character)
        check.assert_not_called()
        with (
            _night_full_moon(),
            self._level(TRIGGER_EXEMPT_LEVEL),
            patch("world.conditions.control_loss._is_impaired", return_value=True),
            patch(
                "world.checks.services.perform_check_with_modifiers",
                return_value=MagicMock(outcome=None),
            ) as check,
        ):
            reconcile_moon_pull(self.character)
        check.assert_called_once()

    def test_already_compelled_gets_the_rampage_window_not_a_roll(self):
        self._bind()
        with (
            _night_full_moon(),
            patch("world.conditions.control_loss.has_compulsion", return_value=True),
            patch("world.combat.berserk_compulsion.berserk_rampage_window") as rampage,
            patch("world.checks.services.perform_check_with_modifiers") as check,
        ):
            reconcile_moon_pull(self.character)
        rampage.assert_called_once_with(self.character)
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


class RenamedBerserkTest(TestCase):
    """A renamed Berserk still compels, because the compulsion row is what counts (#4739)."""

    def test_the_renamed_berserk_is_a_compulsion_on_the_character(self):
        from world.conditions.berserk_content import ensure_berserk_content
        from world.conditions.control_loss import active_compulsion, has_compulsion
        from world.magic.services.fury import get_berserk_template

        ensure_berserk_content()
        berserk = get_berserk_template()
        berserk.name = "Red Haze"
        berserk.save(update_fields=["name"])
        character = CharacterSheetFactory().character
        self.assertFalse(has_compulsion(character))
        instance = ConditionInstanceFactory(target=character, condition=berserk)
        character.conditions.invalidate()
        self.assertTrue(has_compulsion(character))
        self.assertEqual(active_compulsion(character)[1], instance)


class LycanBattleFormProvisioningTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        from world.species.moon_provisioning import BATTLE_FORM_STAT_SUITE
        from world.traits.factories import TraitFactory
        from world.traits.models import TraitType

        for trait_name, _value in BATTLE_FORM_STAT_SUITE:
            TraitFactory(name=trait_name, trait_type=TraitType.STAT)

    def test_provisions_form_profile_effects_and_alt_idempotently(self):
        from world.forms.models import AlternateSelf, FormCombatProfileEffect
        from world.species.moon_provisioning import (
            BATTLE_FORM_STAT_SUITE,
            TUNING_BASELINE,
            ensure_lycan_battle_form,
        )

        sheet = CharacterSheetFactory()
        alt = ensure_lycan_battle_form(sheet)
        again = ensure_lycan_battle_form(sheet)
        self.assertEqual(alt.pk, again.pk)
        self.assertEqual(AlternateSelf.objects.filter(character=sheet).count(), 1)
        self.assertIsNotNone(alt.combat_profile)
        self.assertEqual(
            FormCombatProfileEffect.objects.filter(profile=alt.combat_profile).count(),
            len(BATTLE_FORM_STAT_SUITE),
        )
        self.assertEqual(alt.tuning_value, TUNING_BASELINE)

    def test_thread_level_feeds_tuning(self):
        from world.species.moon_provisioning import (
            TUNING_BASELINE,
            ensure_lycan_battle_form,
        )

        sheet = CharacterSheetFactory()
        with patch("world.species.moon_provisioning._gift_thread_level", return_value=3):
            alt = ensure_lycan_battle_form(sheet)
        self.assertEqual(alt.tuning_value, TUNING_BASELINE + 3)


class CaniUneaseTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        from world.species.factories import SpeciesFactory

        cls.cani = SpeciesFactory(name="Cani")

    def setUp(self):
        self.sheet = CharacterSheetFactory(species=self.cani)
        self.character = self.sheet.character
        self.room = RoomProfileFactory(is_outdoor=True).objectdb
        self.character.location = self.room

    def test_moonlit_cani_gains_unease_with_message(self):
        from world.species.moon_sensitivity import reconcile_cani_unease

        with (
            _night_full_moon(),
            patch("world.conditions.services.apply_condition") as apply,
            patch("world.conditions.services.get_active_conditions", return_value=[]),
            patch.object(self.character, "msg") as msg,
        ):
            reconcile_cani_unease(self.character)
        apply.assert_called_once()
        msg.assert_called_once()

    def test_non_cani_never_gains_unease(self):
        from world.species.moon_sensitivity import reconcile_cani_unease

        other = CharacterSheetFactory()
        other.character.location = self.room
        with (
            _night_full_moon(),
            patch("world.conditions.services.apply_condition") as apply,
        ):
            reconcile_cani_unease(other.character)
        apply.assert_not_called()

    def test_unease_clears_out_of_the_moonlight(self):
        from world.species.factories import ensure_moonlit_unease_condition
        from world.species.moon_sensitivity import reconcile_cani_unease

        template = ensure_moonlit_unease_condition()
        instance = MagicMock()
        instance.condition = template
        with (
            patch("world.species.moon_pull.get_ic_phase", return_value=TimePhase.DAY),
            patch(
                "world.conditions.services.get_active_conditions",
                return_value=[instance],
            ),
            patch("world.conditions.services.remove_condition") as remove,
        ):
            reconcile_cani_unease(self.character)
        remove.assert_called_once()


class RestoreToSenseContentTest(TestCase):
    def test_seed_creates_enhancement_and_removal_config(self):
        from actions.models import ActionEnhancement
        from actions.models.effect_configs import RemoveConditionOnCheckConfig
        from world.checks.models import CheckCategory, CheckType
        from world.conditions.berserk_content import ensure_berserk_content

        category, _ = CheckCategory.objects.get_or_create(name="Social")
        CheckType.objects.get_or_create(name="Persuasion", defaults={"category": category})
        ensure_berserk_content()
        enhancement = ActionEnhancement.objects.get(base_action_key="restore_sense")
        config = RemoveConditionOnCheckConfig.objects.get(enhancement=enhancement)
        self.assertEqual(config.condition.name, "Berserk")
        self.assertEqual(config.check_type.name, "Persuasion")


class VoluntaryShiftMoonScalingTest(TestCase):
    def test_unbound_shifter_gets_baseline(self):
        from actions.definitions.forms import ShiftFormAction

        sheet = CharacterSheetFactory()
        value = ShiftFormAction._moon_instance_value(sheet.character, sheet)
        self.assertEqual(value, 1.0)

    def test_moon_bound_shifter_drinks_the_moonlight(self):
        from actions.definitions.forms import ShiftFormAction

        sheet = CharacterSheetFactory()
        ConditionInstanceFactory(
            target=sheet.character,
            condition=ControlLossTriggerFactory(
                fires_on=ControlLossFiresOn.MOON_PULL
            ).vulnerability,
        )
        room = RoomProfileFactory(is_outdoor=True).objectdb
        sheet.character.location = room
        with _night_full_moon():
            value = ShiftFormAction._moon_instance_value(sheet.character, sheet)
        self.assertAlmostEqual(value, 1.0 + MOON_FORM_CLARITY_MAX_BONUS)
