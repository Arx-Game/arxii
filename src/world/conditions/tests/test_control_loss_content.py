"""Seeded Berserk compulsion, Lycan blood and the moon trigger (#4802)."""

from django.test import TestCase, override_settings

from world.conditions.berserk_content import ensure_berserk_content
from world.conditions.constants import (
    CompulsionForbidden,
    CompulsionResult,
    CompulsionWant,
    ControlLossFiresOn,
    DurationType,
)
from world.conditions.control_loss_bands import (
    validate_compulsion_bands,
    validate_control_loss_bands,
)
from world.conditions.models import ConditionTemplate
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
    def test_berserk_seed_carries_compulsion_with_forbidden_actions(self) -> None:
        ensure_berserk_content()
        ensure_berserk_content()  # idempotent
        compulsion = get_berserk_template().compulsion
        self.assertEqual(compulsion.wants, CompulsionWant.ATTACK_OPPONENT)
        self.assertEqual(compulsion.check_type.name, "compulsion_resist")
        weights = {row.trait.name: float(row.weight) for row in compulsion.check_type.traits.all()}
        self.assertEqual(weights, {"willpower": 1.0, "composure": 0.5})
        self.assertEqual((compulsion.base_difficulty, compulsion.difficulty_per_severity), (25, 2))
        self.assertEqual(
            {row.action: row.extra_difficulty for row in compulsion.forbidden.all()},
            {
                CompulsionForbidden.FLEE: 5,
                CompulsionForbidden.PARLEY: 5,
                CompulsionForbidden.LEAVE: 10,
                CompulsionForbidden.REVERT_FORM: 10,
            },
        )
        bands = list(compulsion.bands.select_related("outcome"))
        self.assertEqual(len(bands), 5)
        by_level = {band.outcome.success_level: band for band in bands}
        self.assertEqual(by_level[2].result, CompulsionResult.ACTS_FREELY)
        self.assertEqual(by_level[1].result, CompulsionResult.ACTS_FREELY)
        self.assertEqual(by_level[0].result, CompulsionResult.ACTS_STRAINED)
        self.assertEqual((by_level[0].action_penalty, by_level[0].control_change), (4, -2))
        self.assertEqual(by_level[-1].result, CompulsionResult.COMPULSION_ACTS)
        self.assertEqual(by_level[-1].control_change, -2)
        self.assertEqual(by_level[-2].result, CompulsionResult.COMPULSION_ACTS)
        self.assertEqual(by_level[-2].control_change, -4)
        self.assertEqual(validate_compulsion_bands(bands), [])


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
        self.assertEqual(trigger.check_type.name, "moon_control")
        self.assertEqual(trigger.min_moon_pull, 6)
        self.assertEqual(trigger.base_difficulty, 20)
        self.assertEqual(trigger.difficulty_per_pull, 5)
        self.assertEqual(trigger.relief_per_level, 10)
        self.assertEqual(trigger.relief_gift, self.gift)
        self.assertEqual(trigger.relief_per_thread_level, 5)
        self.assertEqual(trigger.relief_cap, 30)
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


class ControlLossContentMigrationTests(TestCase):
    """The data migration run against the live app registry (its logic, not the executor)."""

    @staticmethod
    def _run() -> None:
        from importlib import import_module

        from django.apps import apps

        import_module("world.migrations.0333_control_loss_content").seed_control_loss_content(
            apps, None
        )

    def test_noop_on_empty_database(self) -> None:
        from world.conditions.models import Compulsion, ControlLossTrigger

        self._run()
        self.assertFalse(Compulsion.objects.exists())
        self.assertFalse(ControlLossTrigger.objects.exists())
        self.assertFalse(ConditionTemplate.objects.filter(name="Lycan blood").exists())

    def _populated(self):
        """Berserk designated, a lycan grant with the gift, one moon-bound bearer."""
        from world.character_sheets.factories import CharacterSheetFactory
        from world.conditions.models import ConditionCategory
        from world.distinctions.factories import (
            CharacterDistinctionFactory,
            DistinctionFactory,
            DistinctionTagFactory,
        )
        from world.magic.models import FuryConfig

        berserk = ConditionTemplate.objects.create(
            name="Berserk",
            category=ConditionCategory.objects.create(name="Control", alters_behavior=True),
        )
        config, _ = FuryConfig.objects.get_or_create(pk=1)
        config.berserk_condition = berserk
        config.save(update_fields=["berserk_condition"])
        grant = SpeciesGiftGrantFactory(gift=GiftFactory(name=SEED_LYCAN_GIFT_NAME))
        bearer = CharacterSheetFactory()
        distinction = DistinctionFactory()
        distinction.tags.add(DistinctionTagFactory(slug="moon-bound"))
        CharacterDistinctionFactory(character=bearer, distinction=distinction)
        return berserk, grant, bearer

    def test_populated_database_gets_rows_once_and_moon_bearers_the_condition(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory
        from world.conditions.models import (
            Compulsion,
            ConditionInstance,
            ControlLossBand,
            ControlLossTrigger,
        )

        berserk, grant, bearer = self._populated()
        bystander = CharacterSheetFactory()

        self._run()
        self._run()

        compulsion = Compulsion.objects.get(condition=berserk)
        self.assertEqual(compulsion.forbidden.count(), 4)
        self.assertEqual(validate_compulsion_bands(list(compulsion.bands.all())), [])
        grant.refresh_from_db()
        blood = grant.drawback_condition
        self.assertEqual((blood.name, blood.description), ("Lycan blood", ""))
        self.assertEqual(ConditionInstance.objects.filter(condition=blood).count(), 1)
        self.assertTrue(ConditionInstance.objects.filter(condition=blood, target_id=bearer.pk))
        self.assertFalse(ConditionInstance.objects.filter(target_id=bystander.pk, condition=blood))
        trigger = ControlLossTrigger.objects.get(vulnerability=blood)
        self.assertEqual(trigger.relief_gift_id, grant.gift_id)
        self.assertEqual(ControlLossBand.objects.filter(trigger=trigger).count(), 5)
        self.assertEqual(Compulsion.objects.count(), 1)

    def test_staff_set_drawback_leaves_the_grant_entirely_alone(self) -> None:
        from world.conditions.models import ConditionInstance, ControlLossTrigger

        berserk, grant, _bearer = self._populated()
        staff_drawback = ConditionTemplate.objects.create(
            name="Moon curse", category=berserk.category
        )
        grant.drawback_condition = staff_drawback
        grant.save(update_fields=["drawback_condition"])

        self._run()

        grant.refresh_from_db()
        self.assertEqual(grant.drawback_condition, staff_drawback)
        self.assertFalse(ControlLossTrigger.objects.exists())
        self.assertFalse(ConditionInstance.objects.exists())
        self.assertFalse(ConditionTemplate.objects.filter(name="Lycan blood").exists())

    def test_existing_compulsion_and_moon_trigger_are_never_added_to(self) -> None:
        from world.conditions.factories import CompulsionFactory, ControlLossTriggerFactory
        from world.conditions.models import (
            ConditionInstance,
            ControlLossBand,
            ControlLossTrigger,
        )

        berserk, grant, _bearer = self._populated()
        compulsion = CompulsionFactory(condition=berserk)
        ControlLossTriggerFactory()  # an authored moon-pull trigger elsewhere

        self._run()

        self.assertFalse(compulsion.forbidden.exists())
        self.assertFalse(compulsion.bands.exists())
        self.assertEqual(ControlLossTrigger.objects.count(), 1)
        self.assertFalse(ControlLossBand.objects.exists())
        grant.refresh_from_db()
        self.assertIsNone(grant.drawback_condition)
        self.assertFalse(ConditionInstance.objects.exists())
