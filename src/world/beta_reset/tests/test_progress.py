"""The per-character progress reset reverses play provenance and leaves the baseline (#3055)."""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.beta_reset.exceptions import (
    BetaResetDisabledError,
    IncompleteLedgerError,
    ReleaseLatchedError,
)
from world.beta_reset.models import ReleaseLatch
from world.beta_reset.progress import (
    ledger_problems,
    plan_progress_reset,
    reset_character_progress,
)
from world.beta_reset.services import (
    CG_AUTHORING_ACQUISITION_ORIGINS,
    CG_AUTHORING_DISTINCTION_ORIGINS,
    CG_AUTHORING_TRAIT_CHANGE_SOURCES,
    PLAY_TIME_ACQUISITION_ORIGINS,
    PLAY_TIME_DISTINCTION_ORIGINS,
    PLAY_TIME_TRAIT_CHANGE_SOURCES,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.distinctions.models import CharacterDistinction
from world.distinctions.types import DistinctionOrigin
from world.magic.constants import AcquisitionOrigin
from world.magic.factories import (
    CharacterGiftFactory,
    CharacterTechniqueFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.magic.models import CharacterGift, CharacterTechnique
from world.progression.models import ClassLevelAdvancement, LevelStatPointSpend
from world.traits.factories import CharacterTraitValueFactory, SkillTraitFactory, StatTraitFactory
from world.traits.models import CharacterTraitChange, CharacterTraitValue, TraitChangeSource
from world.vitals.factories import CharacterVitalsFactory


def _change(sheet, trait, old, new, source):
    return CharacterTraitChange.objects.create(
        character_sheet=sheet, trait=trait, old_value=old, new_value=new, source=source
    )


class ProvenanceSetsCoverEveryEnumMemberTests(TestCase):
    """A new origin or source cannot be added without choosing play or baseline."""

    def test_every_member_is_on_exactly_one_side(self) -> None:
        for enum, play, baseline in (
            (AcquisitionOrigin, PLAY_TIME_ACQUISITION_ORIGINS, CG_AUTHORING_ACQUISITION_ORIGINS),
            (TraitChangeSource, PLAY_TIME_TRAIT_CHANGE_SOURCES, CG_AUTHORING_TRAIT_CHANGE_SOURCES),
            (DistinctionOrigin, PLAY_TIME_DISTINCTION_ORIGINS, CG_AUTHORING_DISTINCTION_ORIGINS),
        ):
            with self.subTest(enum=enum.__name__):
                self.assertEqual(play & baseline, set())
                self.assertEqual(play | baseline, set(enum))


class ResetCharacterProgressTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.stat = StatTraitFactory(name="beta_reset_strength")
        cls.skill = SkillTraitFactory(name="beta_reset_swordplay")
        cls.language = SkillTraitFactory(name="beta_reset_language")

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.klass = CharacterClassFactory()

    def _value(self, trait) -> int:
        return CharacterTraitValue.objects.get(character=self.sheet, trait=trait).value

    def _seed_progress(self) -> None:
        # Stat: authored at 3, raised to 5 in play by a level-up and a GM award.
        CharacterTraitValueFactory(character=self.sheet, trait=self.stat, value=5)
        _change(self.sheet, self.stat, 0, 3, TraitChangeSource.CHARACTER_CREATION)
        _change(self.sheet, self.stat, 3, 4, TraitChangeSource.DEVELOPMENT_LEVEL_UP)
        _change(self.sheet, self.stat, 4, 5, TraitChangeSource.GM_GRANT)
        # Skill first learned in play: the row itself goes.
        CharacterTraitValueFactory(character=self.sheet, trait=self.skill, value=20)
        _change(self.sheet, self.skill, 0, 20, TraitChangeSource.DEVELOPMENT_LEVEL_UP)
        # Language raised by an XP breakthrough over its authored value.
        CharacterTraitValueFactory(character=self.sheet, trait=self.language, value=40)
        _change(self.sheet, self.language, 0, 30, TraitChangeSource.CHARACTER_CREATION)
        _change(self.sheet, self.language, 30, 40, TraitChangeSource.XP_BREAKTHROUGH)

        self.cg_technique = CharacterTechniqueFactory(
            character=self.sheet,
            technique=TechniqueFactory(),
            origin=AcquisitionOrigin.CHARACTER_CREATION,
        )
        self.play_technique = CharacterTechniqueFactory(
            character=self.sheet, technique=TechniqueFactory(), origin=AcquisitionOrigin.TRAINED
        )
        self.cg_gift = CharacterGiftFactory(
            character=self.sheet, gift=GiftFactory(), origin=AcquisitionOrigin.CHARACTER_CREATION
        )
        self.play_gift = CharacterGiftFactory(
            character=self.sheet, gift=GiftFactory(), origin=AcquisitionOrigin.PATH_GRANT
        )
        self.cg_distinction = CharacterDistinctionFactory(
            character=self.sheet,
            distinction=DistinctionFactory(),
            origin=DistinctionOrigin.CHARACTER_CREATION,
        )
        self.play_distinction = CharacterDistinctionFactory(
            character=self.sheet,
            distinction=DistinctionFactory(),
            origin=DistinctionOrigin.GM_AWARD,
        )
        self.level = CharacterClassLevelFactory(
            character=self.sheet, character_class=self.klass, level=4, is_primary=True
        )
        for before in (1, 2, 3):
            ClassLevelAdvancement.objects.create(
                character_sheet=self.sheet,
                character_class=self.klass,
                level_before=before,
                level_after=before + 1,
            )
        LevelStatPointSpend.objects.create(
            character_sheet=self.sheet, trait=self.stat, level_granted=2
        )

    def test_play_progress_is_reversed_and_the_baseline_stays(self) -> None:
        self._seed_progress()

        reset_character_progress(self.sheet)

        self.assertEqual(self._value(self.stat), 3)
        self.assertEqual(self._value(self.language), 30)
        self.assertFalse(
            CharacterTraitValue.objects.filter(character=self.sheet, trait=self.skill).exists()
        )
        self.assertEqual(
            CharacterTraitChange.objects.filter(
                character_sheet=self.sheet, source=TraitChangeSource.CHARACTER_CREATION
            ).count(),
            2,
        )
        self.assertFalse(
            CharacterTraitChange.objects.filter(
                character_sheet=self.sheet, source__in=PLAY_TIME_TRAIT_CHANGE_SOURCES
            ).exists()
        )
        self.assertTrue(CharacterTechnique.objects.filter(pk=self.cg_technique.pk).exists())
        self.assertFalse(CharacterTechnique.objects.filter(pk=self.play_technique.pk).exists())
        self.assertTrue(CharacterGift.objects.filter(pk=self.cg_gift.pk).exists())
        self.assertFalse(CharacterGift.objects.filter(pk=self.play_gift.pk).exists())
        self.assertTrue(CharacterDistinction.objects.filter(pk=self.cg_distinction.pk).exists())
        self.assertFalse(CharacterDistinction.objects.filter(pk=self.play_distinction.pk).exists())
        self.assertFalse(LevelStatPointSpend.objects.filter(character_sheet=self.sheet).exists())
        self.level.refresh_from_db()
        self.assertEqual(self.level.level, 1)

    def test_a_second_run_changes_nothing(self) -> None:
        self._seed_progress()
        reset_character_progress(self.sheet)

        second = plan_progress_reset(self.sheet)

        self.assertFalse(second.changes_anything)
        reset_character_progress(self.sheet)
        self.assertEqual(self._value(self.stat), 3)

    def test_the_plan_describes_the_reset_without_touching_anything(self) -> None:
        self._seed_progress()

        plan = plan_progress_reset(self.sheet)

        self.assertEqual(
            {r.trait_name for r in plan.trait_reverts},
            {
                self.stat.name,
                self.skill.name,
                self.language.name,
            },
        )
        self.assertEqual((plan.level_now, plan.level_baseline), (4, 1))
        self.assertEqual((plan.techniques, plan.gifts, plan.distinctions), (1, 1, 1))
        self.assertTrue(CharacterTechnique.objects.filter(pk=self.play_technique.pk).exists())
        self.assertEqual(self._value(self.stat), 5)

    def test_a_character_with_no_play_progress_is_left_alone(self) -> None:
        CharacterTraitValueFactory(character=self.sheet, trait=self.stat, value=3)
        _change(self.sheet, self.stat, 0, 3, TraitChangeSource.CHARACTER_CREATION)

        plan = reset_character_progress(self.sheet)

        self.assertFalse(plan.changes_anything)
        self.assertEqual(self._value(self.stat), 3)


class ResetGuardTests(TestCase):
    """No direct call runs once the constant is off or the latch is written."""

    def test_the_disabled_constant_refuses_and_nothing_changes(self) -> None:
        sheet = CharacterSheetFactory()
        technique = CharacterTechniqueFactory(
            character=sheet, technique=TechniqueFactory(), origin=AcquisitionOrigin.TRAINED
        )

        with (
            mock.patch("world.beta_reset.services.BETA_RESET_ENABLED", False),
            self.assertRaises(BetaResetDisabledError),
        ):
            reset_character_progress(sheet)

        self.assertTrue(CharacterTechnique.objects.filter(pk=technique.pk).exists())

    def test_the_release_latch_refuses_and_nothing_changes(self) -> None:
        sheet = CharacterSheetFactory()
        technique = CharacterTechniqueFactory(
            character=sheet, technique=TechniqueFactory(), origin=AcquisitionOrigin.TRAINED
        )
        ReleaseLatch.objects.create(released_by=AccountFactory())

        with self.assertRaises(ReleaseLatchedError):
            reset_character_progress(sheet)

        self.assertTrue(CharacterTechnique.objects.filter(pk=technique.pk).exists())


class IncompleteLedgerTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.stat = StatTraitFactory(name="ledger_strength")

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()

    def _stat_with_chain(self, rows, value) -> None:
        CharacterTraitValueFactory(character=self.sheet, trait=self.stat, value=value)
        for old, new, source in rows:
            _change(self.sheet, self.stat, old, new, source)

    def test_a_whole_ledger_has_no_problems(self) -> None:
        self._stat_with_chain(
            [
                (0, 3, TraitChangeSource.CHARACTER_CREATION),
                (3, 5, TraitChangeSource.DEVELOPMENT_LEVEL_UP),
            ],
            5,
        )

        self.assertEqual(ledger_problems(self.sheet), ())

    def test_a_broken_chain_is_reported(self) -> None:
        self._stat_with_chain(
            [
                (0, 3, TraitChangeSource.CHARACTER_CREATION),
                (4, 5, TraitChangeSource.DEVELOPMENT_LEVEL_UP),
            ],
            5,
        )

        (problem,) = ledger_problems(self.sheet)
        self.assertIn("ledger_strength: the ledger breaks", problem)

    def test_a_ledger_that_ends_short_of_the_value_is_reported(self) -> None:
        self._stat_with_chain(
            [
                (0, 3, TraitChangeSource.CHARACTER_CREATION),
                (3, 4, TraitChangeSource.DEVELOPMENT_LEVEL_UP),
            ],
            6,
        )

        (problem,) = ledger_problems(self.sheet)
        self.assertIn("ends at 4 but the value is 6", problem)

    def test_a_ledger_row_whose_value_row_is_gone_is_reported(self) -> None:
        _change(self.sheet, self.stat, 0, 4, TraitChangeSource.DEVELOPMENT_LEVEL_UP)

        (problem,) = ledger_problems(self.sheet)
        self.assertIn("trait value row is gone", problem)

    def test_a_level_above_its_receipts_is_reported(self) -> None:
        klass = CharacterClassFactory()
        CharacterClassLevelFactory(
            character=self.sheet, character_class=klass, level=5, is_primary=True
        )
        ClassLevelAdvancement.objects.create(
            character_sheet=self.sheet, character_class=klass, level_before=1, level_after=2
        )

        (problem,) = ledger_problems(self.sheet)
        self.assertIn("a rise with no advancement receipt", problem)

    def test_execute_refuses_by_default_names_the_trait_and_changes_nothing(self) -> None:
        self._stat_with_chain([(4, 5, TraitChangeSource.DEVELOPMENT_LEVEL_UP)], 9)

        with self.assertRaises(IncompleteLedgerError) as raised:
            reset_character_progress(self.sheet)

        self.assertIn("ledger_strength", str(raised.exception))
        self.assertEqual(
            CharacterTraitValue.objects.get(character=self.sheet, trait=self.stat).value, 9
        )

    def test_the_flag_proceeds_past_an_incomplete_ledger(self) -> None:
        self._stat_with_chain([(4, 5, TraitChangeSource.DEVELOPMENT_LEVEL_UP)], 9)

        reset_character_progress(self.sheet, allow_incomplete_ledger=True)

        self.assertEqual(
            CharacterTraitValue.objects.get(character=self.sheet, trait=self.stat).value, 8
        )


class ResetKeepsTheProcessHonestTests(TestCase):
    """Caches and side effects a reset must get right in the same process."""

    def test_techniques_handler_and_max_health_are_right_straight_after(self) -> None:
        sheet = CharacterSheetFactory()
        vitals = CharacterVitalsFactory(
            character_sheet=sheet, base_max_health=50, max_health=999, health=10
        )
        kept = CharacterTechniqueFactory(
            character=sheet,
            technique=TechniqueFactory(),
            origin=AcquisitionOrigin.CHARACTER_CREATION,
        )
        gone = CharacterTechniqueFactory(
            character=sheet, technique=TechniqueFactory(), origin=AcquisitionOrigin.TRAINED
        )
        self.assertEqual(
            {t.pk for t in sheet.character.techniques.all()},
            {kept.technique_id, gone.technique_id},
        )

        reset_character_progress(sheet)

        self.assertEqual([t.pk for t in sheet.character.techniques.all()], [kept.technique_id])
        vitals.refresh_from_db()
        self.assertEqual(vitals.max_health, 50)

    def test_lowering_the_level_runs_no_story_reactivity(self) -> None:
        sheet = CharacterSheetFactory()
        klass = CharacterClassFactory()
        row = CharacterClassLevelFactory(
            character=sheet, character_class=klass, level=3, is_primary=True
        )
        for before in (1, 2):
            ClassLevelAdvancement.objects.create(
                character_sheet=sheet,
                character_class=klass,
                level_before=before,
                level_after=before + 1,
            )

        with mock.patch(
            "world.stories.services.reactivity.on_character_state_changed"
        ) as reactivity:
            reset_character_progress(sheet)

        reactivity.assert_not_called()
        row.refresh_from_db()
        self.assertEqual(row.level, 1)
