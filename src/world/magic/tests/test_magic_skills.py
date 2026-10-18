"""Magic-layer skill term resolution (#4450): activity rows and the technique skill."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from evennia.accounts.models import AccountDB

from actions.factories import ActionTemplateFactory
from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.types import ExtraTraitTerm
from world.classes.factories import PathFactory
from world.magic.constants import GiftKind, MagicActivity, RitualExecutionKind
from world.magic.factories import (
    GiftFactory,
    MagicActivitySkillFactory,
    RitualCheckConfigFactory,
    TechniqueFactory,
)
from world.magic.models.rituals import Ritual
from world.magic.services.magic_skills import (
    activity_skill_terms,
    involved_trait_ids,
    resolve_cast_check,
    technique_skill_term,
)
from world.magic.types.magic_skills import CastCheck
from world.progression.factories import CharacterPathHistoryFactory
from world.progression.models import CharacterPathHistory
from world.skills.factories import SkillFactory
from world.traits.factories import StatTraitFactory


class ActivitySkillTermsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.skill_a = SkillFactory()
        cls.skill_b = SkillFactory()

    def test_activity_terms_from_rows(self):
        MagicActivitySkillFactory(
            activity=MagicActivity.DISPELLING, skill=self.skill_a, weight=Decimal("1.00")
        )
        MagicActivitySkillFactory(
            activity=MagicActivity.DISPELLING, skill=self.skill_b, weight=Decimal("0.50")
        )
        MagicActivitySkillFactory(activity=MagicActivity.ANIMA_RITUAL, skill=self.skill_a)

        terms = activity_skill_terms(MagicActivity.DISPELLING)

        self.assertEqual(
            {(t.trait, t.weight) for t in terms},
            {
                (self.skill_a.trait, Decimal("1.00")),
                (self.skill_b.trait, Decimal("0.50")),
            },
        )
        self.assertTrue(all(isinstance(t, ExtraTraitTerm) for t in terms))

    def test_activity_terms_skip_inactive_skill(self):
        inactive = SkillFactory(is_active=False)
        MagicActivitySkillFactory(activity=MagicActivity.RITUAL_WORKING, skill=inactive)
        MagicActivitySkillFactory(activity=MagicActivity.RITUAL_WORKING, skill=self.skill_a)

        terms = activity_skill_terms(MagicActivity.RITUAL_WORKING)

        self.assertEqual([t.trait for t in terms], [self.skill_a.trait])

    def test_activity_terms_empty_when_unmapped(self):
        self.assertEqual(activity_skill_terms(MagicActivity.SOUL_TETHER_RESCUE), ())


class TechniqueSkillTermTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.override_skill = SkillFactory()
        cls.path_skill = SkillFactory()
        cls.new_path_skill = SkillFactory()
        cls.gift_skill = SkillFactory()
        cls.sheet = CharacterSheetFactory()
        cls.path = PathFactory(technique_skill=cls.path_skill)
        cls.major_gift = GiftFactory(kind=GiftKind.MAJOR)
        cls.minor_gift = GiftFactory(kind=GiftKind.MINOR, technique_skill=cls.gift_skill)

    def _term(self, technique):
        return technique_skill_term(self.sheet.character, technique)

    def test_technique_override_wins(self):
        CharacterPathHistoryFactory(character=self.sheet, path=self.path)
        technique = TechniqueFactory(gift=self.major_gift, skill=self.override_skill)

        term = self._term(technique)

        self.assertEqual(term, ExtraTraitTerm(self.override_skill.trait, Decimal("1.00")))

    def test_inactive_override_gives_no_term(self):
        inactive = SkillFactory(is_active=False)
        technique = TechniqueFactory(gift=self.major_gift, skill=inactive)

        self.assertIsNone(self._term(technique))

    def test_major_gift_uses_current_path_skill(self):
        CharacterPathHistoryFactory(character=self.sheet, path=self.path)
        technique = TechniqueFactory(gift=self.major_gift)

        term = self._term(technique)

        self.assertEqual(term, ExtraTraitTerm(self.path_skill.trait, Decimal("1.00")))

    def test_major_gift_after_path_change_uses_new_path(self):
        new_path = PathFactory(technique_skill=self.new_path_skill)
        old = CharacterPathHistoryFactory(character=self.sheet, path=self.path)
        # selected_at is auto_now_add, so backdate the first row with a queryset update.
        CharacterPathHistory.objects.filter(pk=old.pk).update(
            selected_at=timezone.now() - timedelta(days=2)
        )
        CharacterPathHistoryFactory(character=self.sheet, path=new_path)
        technique = TechniqueFactory(gift=self.major_gift)

        term = self._term(technique)

        self.assertEqual(term.trait, self.new_path_skill.trait)

    def test_minor_gift_uses_gift_skill(self):
        CharacterPathHistoryFactory(character=self.sheet, path=self.path)
        technique = TechniqueFactory(gift=self.minor_gift)

        term = self._term(technique)

        self.assertEqual(term, ExtraTraitTerm(self.gift_skill.trait, Decimal("1.00")))

    def test_inactive_path_skill_gives_no_term(self):
        inactive = SkillFactory(is_active=False)
        path = PathFactory(technique_skill=inactive)
        CharacterPathHistoryFactory(character=self.sheet, path=path)
        technique = TechniqueFactory(gift=self.major_gift)

        self.assertIsNone(self._term(technique))

    def test_no_path_no_term(self):
        technique = TechniqueFactory(gift=self.major_gift)

        self.assertIsNone(self._term(technique))

    def test_no_sheet_no_term(self):
        bare = ObjectDBFactory()
        technique = TechniqueFactory(gift=self.major_gift)

        self.assertIsNone(technique_skill_term(bare, technique))


class ResolveCastCheckTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.template = ActionTemplateFactory()
        cls.skill = SkillFactory()
        cls.path = PathFactory(technique_skill=cls.skill)
        CharacterPathHistoryFactory(character=cls.sheet, path=cls.path)
        cls.gift = GiftFactory(kind=GiftKind.MAJOR)

    def test_resolve_cast_check_personal_wins_and_adds_term(self):
        account = AccountDB.objects.create(username="magic_skills_personal")
        ritual = Ritual.objects.create(
            name="magic_skills_personal_ritual",
            author_account=account,
            execution_kind=RitualExecutionKind.SCENE_ACTION,
        )
        config = RitualCheckConfigFactory(ritual=ritual)
        self.sheet.character.db_account = account
        self.sheet.character.save(update_fields=["db_account"])
        technique = TechniqueFactory(gift=self.gift, action_template=self.template)

        cast = resolve_cast_check(self.sheet.character, technique)

        self.assertEqual(
            cast,
            CastCheck(
                check_type=config.check_type,
                extra_traits=(ExtraTraitTerm(self.skill.trait, Decimal("1.00")),),
            ),
        )

    def test_resolve_cast_check_falls_back_to_template_check(self):
        technique = TechniqueFactory(gift=self.gift, action_template=self.template)

        cast = resolve_cast_check(self.sheet.character, technique)

        self.assertEqual(cast.check_type, self.template.check_type)

    def test_resolve_cast_check_none_when_unprovisioned_and_no_template(self):
        technique = TechniqueFactory(gift=self.gift, action_template=None)

        self.assertIsNone(resolve_cast_check(self.sheet.character, technique))


class InvolvedTraitIdsTests(TestCase):
    def test_involved_trait_ids_union(self):
        stat = StatTraitFactory()
        skill = SkillFactory()
        check_type = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=check_type, trait=stat)
        terms = (
            ExtraTraitTerm(skill.trait, Decimal("1.00")),
            ExtraTraitTerm(stat, Decimal("0.50")),
        )

        ids = involved_trait_ids(check_type, terms)

        self.assertEqual(ids, (stat.pk, skill.trait.pk))
