"""Botch-immunity targets on ModifierTarget (#4386): scope rules and the cached lookup."""

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.mechanics.admin import ModifierTargetAdmin
from world.mechanics.constants import BOTCH_IMMUNITY_CATEGORY_NAME
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.mechanics.models import ModifierTarget


class BotchImmunityTargetTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.botch = ModifierCategoryFactory(name=BOTCH_IMMUNITY_CATEGORY_NAME)
        cls.other_category = ModifierCategoryFactory(name="botch_test_other")
        cls.check_category = CheckCategoryFactory(name="Botch Test Wilderness")
        cls.other_check_category = CheckCategoryFactory(name="Botch Test Court")
        cls.riding = CheckTypeFactory(name="Botch Test Riding", category=cls.check_category)
        cls.tracking = CheckTypeFactory(name="Botch Test Tracking", category=cls.check_category)
        cls.etiquette = CheckTypeFactory(
            name="Botch Test Etiquette", category=cls.other_check_category
        )

    def setUp(self) -> None:
        ModifierTarget.clear_trait_cache()

    def tearDown(self) -> None:
        ModifierTarget.clear_trait_cache()

    def _target(self, **kwargs: object) -> ModifierTarget:
        kwargs.setdefault("category", self.botch)
        return ModifierTargetFactory(**kwargs)

    def test_clean_refuses_both_scopes(self) -> None:
        target = ModifierTarget(
            name="both",
            category=self.botch,
            target_check_category=self.check_category,
            target_scope_check_type=self.riding,
        )
        with self.assertRaises(ValidationError) as ctx:
            target.clean()
        self.assertIn("target_scope_check_type", ctx.exception.message_dict)

    def test_clean_refuses_neither_scope(self) -> None:
        target = ModifierTarget(name="neither", category=self.botch)
        with self.assertRaises(ValidationError) as ctx:
            target.clean()
        self.assertIn("target_check_category", ctx.exception.message_dict)

    def test_clean_refuses_scope_outside_category(self) -> None:
        by_category = ModifierTarget(
            name="stray", category=self.other_category, target_check_category=self.check_category
        )
        with self.assertRaises(ValidationError) as ctx:
            by_category.clean()
        self.assertIn("target_check_category", ctx.exception.message_dict)
        by_type = ModifierTarget(
            name="stray", category=self.other_category, target_scope_check_type=self.riding
        )
        with self.assertRaises(ValidationError) as ctx:
            by_type.clean()
        self.assertIn("target_scope_check_type", ctx.exception.message_dict)

    def test_clean_accepts_one_scope(self) -> None:
        ModifierTarget(name="ok", category=self.botch, target_scope_check_type=self.riding).clean()

    def test_one_target_per_scope(self) -> None:
        self._target(name="riding one", target_scope_check_type=self.riding)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            self._target(name="riding two", target_scope_check_type=self.riding)
        self._target(name="wild one", target_check_category=self.check_category)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            self._target(name="wild two", target_check_category=self.check_category)

    def test_both_scopes_refused_by_database(self) -> None:
        with transaction.atomic(), self.assertRaises(IntegrityError):
            self._target(
                name="both",
                target_check_category=self.check_category,
                target_scope_check_type=self.riding,
            )

    def test_targets_for_check_type_and_its_category(self) -> None:
        by_type = self._target(name="riding", target_scope_check_type=self.riding)
        by_category = self._target(name="wild", target_check_category=self.check_category)
        self._target(name="court", target_check_category=self.other_check_category)
        self._target(name="tracking", target_scope_check_type=self.tracking, is_active=False)

        self.assertEqual(
            ModifierTarget.botch_immunity_targets_for(self.riding), [by_type, by_category]
        )
        self.assertEqual(ModifierTarget.botch_immunity_targets_for(self.tracking), [by_category])

    def test_ignores_other_categories(self) -> None:
        # Written past clean() on purpose: the lookup must not trust it.
        ModifierTarget.objects.create(
            name="stray", category=self.other_category, target_scope_check_type=self.riding
        )
        self.assertEqual(ModifierTarget.botch_immunity_targets_for(self.riding), [])

    def test_lookup_runs_no_query_once_built(self) -> None:
        ModifierTarget.botch_immunity_targets_for(self.riding)
        with self.assertNumQueries(0):
            self.assertEqual(ModifierTarget.botch_immunity_targets_for(self.etiquette), [])

    def test_cache_invalidates_on_save_and_delete(self) -> None:
        self.assertEqual(ModifierTarget.botch_immunity_targets_for(self.riding), [])
        target = self._target(name="riding", target_scope_check_type=self.riding)
        self.assertEqual(ModifierTarget.botch_immunity_targets_for(self.riding), [target])

        target.is_active = False
        target.save()
        self.assertEqual(ModifierTarget.botch_immunity_targets_for(self.riding), [])

        target.is_active = True
        target.save()
        self.assertEqual(ModifierTarget.botch_immunity_targets_for(self.riding), [target])

        target.delete()
        self.assertEqual(ModifierTarget.botch_immunity_targets_for(self.riding), [])


class GrantedByAdminTests(TestCase):
    """The ModifierTarget change form's read-only "Granted by" field (#4386)."""

    def setUp(self) -> None:
        ModifierTarget.clear_trait_cache()
        self.model_admin = ModifierTargetAdmin(ModifierTarget, admin.site)

    def tearDown(self) -> None:
        ModifierTarget.clear_trait_cache()

    def test_names_the_granting_distinction(self) -> None:
        target = ModifierTargetFactory(
            category=ModifierCategoryFactory(name=BOTCH_IMMUNITY_CATEGORY_NAME),
            name="sure in the saddle",
            target_scope_check_type=CheckTypeFactory(name="Granted By Riding"),
        )
        DistinctionEffectFactory(distinction=DistinctionFactory(name="Born Rider"), target=target)
        shown = str(self.model_admin.granted_by(target))
        self.assertIn("Distinction: Born Rider: sure in the saddle", shown)

    def test_empty_message_when_nothing_grants(self) -> None:
        target = ModifierTargetFactory(name="ungranted")
        self.assertEqual(self.model_admin.granted_by(target), "Nothing grants this target yet.")
