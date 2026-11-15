"""Schema rules of the kindled-resonance models (#5124): the constraints the database holds."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.combat.factories import CombatEncounterFactory
from world.covenants.perks.constants import Situation
from world.magic.constants import GainSource
from world.magic.factories import (
    AffinityFactory,
    KindledStrengthTierFactory,
    KindlingFactory,
    KindlingSituationFactory,
    ReflectionFactory,
    ResonanceFactory,
    ResonanceGrantFactory,
    SettlingRiteFactory,
)
from world.magic.models import KindledStrengthTier, ResonanceGrant
from world.missions.factories import MissionThemeFactory
from world.scenes.factories import SceneFactory


class KindlingSituationTests(TestCase):
    def test_a_row_names_a_resonance_or_an_affinity_never_both_or_neither(self) -> None:
        resonance = ResonanceFactory()
        for resonance_arg, affinity_arg in [(None, None), (resonance, AffinityFactory())]:
            with self.subTest(resonance=resonance_arg), self.assertRaises(IntegrityError):
                with transaction.atomic():
                    KindlingSituationFactory(resonance=resonance_arg, for_affinity=affinity_arg)

    def test_an_affinity_wide_row_is_allowed(self) -> None:
        row = KindlingSituationFactory(resonance=None, for_affinity=AffinityFactory())
        self.assertIsNone(row.resonance_id)

    def test_clean_refuses_a_row_with_no_target(self) -> None:
        row = KindlingSituationFactory.build(resonance=None, for_affinity=None)
        with self.assertRaises(ValidationError):
            row.full_clean()

    def test_the_theme_and_enemies_columns_ride_the_params(self) -> None:
        theme = MissionThemeFactory()
        row = KindlingSituationFactory(resonance=ResonanceFactory(), mission_theme=theme)
        self.assertEqual(row.params.mission_theme, theme)
        self.assertFalse(row.params.enemies_only)

    def test_a_parameter_the_situation_does_not_read_is_refused(self) -> None:
        # IN_MELEE reads no parameters, so a theme or enemies_only on it is an authoring slip.
        for field, value in [("mission_theme", MissionThemeFactory()), ("enemies_only", True)]:
            with self.subTest(field=field):
                row = KindlingSituationFactory.build(
                    resonance=ResonanceFactory(), situation=Situation.IN_MELEE, **{field: value}
                )
                with self.assertRaises(ValidationError) as caught:
                    row.clean()
                self.assertIn(field, caught.exception.message_dict)


class KindledStrengthTierTests(TestCase):
    def test_rank_and_name_are_each_unique(self) -> None:
        KindledStrengthTierFactory(rank=1, name="Faint")
        for rank, name in [(1, "Other"), (2, "Faint")]:
            with self.subTest(rank=rank), self.assertRaises(IntegrityError):
                with transaction.atomic():
                    KindledStrengthTier.objects.create(rank=rank, name=name)

    def test_the_factory_lands_its_fields_on_a_row_that_already_exists(self) -> None:
        # Migration 0413 seeds ranks 1 to 3, so on the Postgres tier the row is already there.
        KindledStrengthTier.objects.create(rank=3, name="Seeded")
        row = KindledStrengthTierFactory(rank=3, give_in_max_depth=2)
        self.assertEqual(row.give_in_max_depth, 2)
        self.assertEqual(KindledStrengthTier.objects.filter(rank=3).count(), 1)


class KindlingTests(TestCase):
    def test_a_kindling_ends_with_its_fight(self) -> None:
        kindling = KindlingFactory()
        kindling.encounter.delete()
        self.assertFalse(type(kindling).objects.filter(pk=kindling.pk).exists())

    def test_a_kindling_belongs_to_one_fight_or_one_scene(self) -> None:
        for encounter, scene in [(None, None), (CombatEncounterFactory(), SceneFactory())]:
            with self.subTest(encounter=encounter), self.assertRaises(IntegrityError):
                with transaction.atomic():
                    KindlingFactory(encounter=encounter, scene=scene)


class ReflectionTests(TestCase):
    def test_a_reflection_names_a_deed_or_a_resonance_not_both_or_neither(self) -> None:
        grant = ResonanceGrantFactory()
        for grant_arg, resonance_arg in [(None, None), (grant, ResonanceFactory())]:
            with self.subTest(grant=grant_arg), self.assertRaises(IntegrityError):
                with transaction.atomic():
                    ReflectionFactory(grant=grant_arg, resonance=resonance_arg)

    def test_a_deed_is_reflected_on_once(self) -> None:
        grant = ResonanceGrantFactory()
        ReflectionFactory(grant=grant, resonance=None)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ReflectionFactory(grant=grant, resonance=None, character_sheet=grant.character_sheet)

    def test_a_reflection_survives_its_writing_being_deleted(self) -> None:
        reflection = ReflectionFactory()
        reflection.journal_entry.delete()
        reflection.refresh_from_db()
        self.assertIsNone(reflection.journal_entry_id)

    def test_a_reflection_with_no_rite_is_waiting(self) -> None:
        self.assertIsNone(ReflectionFactory().rite)


class ResonanceGrantSourceShapeTests(TestCase):
    def test_a_kindled_deed_needs_the_situation_that_held(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            ResonanceGrantFactory(source=GainSource.KINDLED_DEED)
        grant = ResonanceGrantFactory(
            source=GainSource.KINDLED_DEED, source_kindling_situation=KindlingSituationFactory()
        )
        self.assertIsNotNone(grant.pk)

    def test_an_embraced_deed_needs_the_rite_and_the_reflection(self) -> None:
        rite = SettlingRiteFactory()
        reflection = ReflectionFactory(character_sheet=rite.character_sheet)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ResonanceGrantFactory(source=GainSource.EMBRACED_DEED, source_settling_rite=rite)
        grant = ResonanceGrantFactory(
            source=GainSource.EMBRACED_DEED,
            source_settling_rite=rite,
            source_reflection=reflection,
        )
        self.assertIsNotNone(grant.pk)

    def test_another_source_may_not_carry_a_kindling_link(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            ResonanceGrantFactory(
                source=GainSource.STAFF_GRANT, source_kindling_situation=KindlingSituationFactory()
            )

    def test_a_used_situation_cannot_be_deleted(self) -> None:
        situation = KindlingSituationFactory()
        ResonanceGrantFactory(source=GainSource.KINDLED_DEED, source_kindling_situation=situation)
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            situation.delete()
        self.assertEqual(ResonanceGrant.objects.count(), 1)
