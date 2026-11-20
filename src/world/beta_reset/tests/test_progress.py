"""The per-character progress reset reverses play provenance and leaves the baseline (#3055)."""

from __future__ import annotations

from django.test import TestCase

from world.beta_reset.progress import plan_progress_reset, reset_character_progress
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
