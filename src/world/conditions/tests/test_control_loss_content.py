"""Seeded Berserk compulsion, Lycan blood and the moon trigger (#4802)."""

from decimal import Decimal

from django.test import TestCase, override_settings

from world.conditions.berserk_content import ensure_berserk_content
from world.conditions.constants import (
    ControlLossFiresOn,
    DurationType,
)
from world.conditions.control_loss_bands import (
    validate_compulsion_bands,
    validate_control_loss_bands,
)
from world.conditions.models import Compulsion, ConditionTemplate
from world.magic.factories import GiftFactory
from world.magic.services.fury import get_berserk_template
from world.species.factories import SpeciesFactory, SpeciesGiftGrantFactory
from world.species.moon_provisioning import (
    SEED_LYCAN_GIFT_NAME,
    SEED_LYCAN_SPECIES_NAME,
    ensure_lycan_blood_condition,
    ensure_moon_control_loss_trigger,
)


class BerserkCompulsionSeedTests(TestCase):
    def test_seeded_stage_multiplier_is_a_decimal_straight_after_seeding(self) -> None:
        """A string here is multiplied into a repeated string by effective_severity."""
        ensure_berserk_content()
        stage = get_berserk_template().stages.get()
        self.assertIsInstance(stage.severity_multiplier, Decimal)

    def test_berserk_seed_is_idempotent_and_its_bands_validate(self) -> None:
        """A second seeding adds no rows, and the seeded bands pass the admin's order rule.

        The seeded numbers themselves are proven by the losing-control journeys, which roll
        against them (``_CompelledMira``).
        """
        ensure_berserk_content()
        compulsion = get_berserk_template().compulsion
        before = (compulsion.forbidden.count(), compulsion.bands.count())
        ensure_berserk_content()
        self.assertEqual(Compulsion.objects.filter(condition=compulsion.condition).count(), 1)
        self.assertEqual((compulsion.forbidden.count(), compulsion.bands.count()), before)
        self.assertEqual(validate_compulsion_bands(list(compulsion.bands.all())), [])


@override_settings(SEED_SAMPLE_CONTENT=True)
class MoonTriggerSeedTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        ensure_berserk_content()
        cls.species = SpeciesFactory(name=SEED_LYCAN_SPECIES_NAME)
        cls.gift = GiftFactory(name=SEED_LYCAN_GIFT_NAME)
        cls.grant = SpeciesGiftGrantFactory(species=cls.species, gift=cls.gift)

    def _give_lycan_blood(self) -> None:
        self.grant.drawback_condition = ensure_lycan_blood_condition()
        self.grant.save(update_fields=["drawback_condition"])

    def test_moon_trigger_seeded_with_todays_values(self) -> None:
        self._give_lycan_blood()
        trigger = ensure_moon_control_loss_trigger()
        self.assertIsNotNone(trigger)
        self.assertEqual(ensure_moon_control_loss_trigger(), trigger)  # idempotent
        self.assertEqual(trigger.fires_on, ControlLossFiresOn.MOON_PULL)
        self.assertEqual(trigger.vulnerability.name, "Lycan blood")
        self.assertEqual(trigger.check_type.name, "Hold against the moon")
        self.assertEqual(trigger.min_moon_pull, 6)
        self.assertEqual(trigger.base_difficulty_level, 1)
        self.assertEqual(trigger.difficulty_per_pull_tenths, 10)
        self.assertEqual(trigger.relief_per_level_tenths, 20)
        self.assertEqual(trigger.relief_gift, self.gift)
        self.assertEqual(trigger.relief_per_thread_level_tenths, 10)
        self.assertEqual(trigger.relief_cap_tenths, 60)
        self.assertEqual(trigger.exempt_from_level, 6)
        self.assertEqual(trigger.impaired_willpower_drop, 10)
        bands = list(trigger.bands.select_related("outcome"))
        self.assertEqual(len(bands), 5)
        berserk = get_berserk_template()
        for band in bands:
            if band.outcome.success_level >= 0:
                self.assertIsNone(band.applies)
                self.assertFalse(band.forces_form)
            else:
                self.assertEqual(band.applies, berserk)
                self.assertEqual((band.severity, band.duration_rounds), (3, 3))
                self.assertTrue(band.forces_form)
        self.assertEqual(validate_control_loss_bands(bands), [])

    def test_lycan_blood_is_permanent_and_does_not_alter_behavior(self) -> None:
        self._give_lycan_blood()
        blood = ensure_moon_control_loss_trigger().vulnerability
        self.assertEqual(blood.default_duration_type, DurationType.PERMANENT)
        self.assertFalse(blood.category.alters_behavior)
        self.assertEqual(blood.description, "")

    def test_lycan_grant_carries_lycan_blood(self) -> None:
        from world.seeds.character_creation import _seed_moon_content

        _seed_moon_content()
        self.grant.refresh_from_db()
        self.assertEqual(self.grant.drawback_condition.name, "Lycan blood")
        self.assertTrue(
            ConditionTemplate.objects.get(name="Lycan blood").control_loss_triggers.exists()
        )

    def test_no_trigger_while_the_grant_has_no_drawback(self) -> None:
        self.assertIsNone(ensure_moon_control_loss_trigger())

    def test_no_trigger_without_a_berserk_designation(self) -> None:
        self._give_lycan_blood()
        from world.magic.models import FuryConfig

        config = FuryConfig.objects.get(pk=1)
        config.berserk_condition = None
        config.save(update_fields=["berserk_condition"])
        self.assertIsNone(ensure_moon_control_loss_trigger())

    def test_an_existing_moon_control_check_is_reused_never_doubled(self) -> None:
        """An earlier seed's "moon_control" row rolls the trigger; no second check is made."""
        from world.checks.factories import CheckTypeFactory
        from world.checks.models import CheckType

        legacy = CheckTypeFactory(name="moon_control")
        self._give_lycan_blood()

        trigger = ensure_moon_control_loss_trigger()

        self.assertEqual(trigger.check_type, legacy)
        self.assertEqual(CheckType.objects.get(pk=legacy.pk).name, "moon_control")
        self.assertFalse(CheckType.objects.filter(name="Hold against the moon").exists())

    def test_without_moon_control_the_check_is_made_under_its_player_name(self) -> None:
        from world.checks.models import CheckType

        self._give_lycan_blood()

        trigger = ensure_moon_control_loss_trigger()

        self.assertEqual(trigger.check_type.name, "Hold against the moon")
        self.assertFalse(CheckType.objects.filter(name="moon_control").exists())
