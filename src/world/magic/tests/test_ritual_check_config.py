"""Tests for RitualCheckConfig model."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.magic.constants import RitualExecutionKind
from world.magic.factories import (
    RitualCheckConfigFactory,
    RitualFactory,
)
from world.magic.models import Ritual

# ExecutionKind values live on RitualExecutionKind in constants, not on Ritual.
_EXECUTION_KIND_VALUES = [c.value for c in RitualExecutionKind]


class RitualExecutionKindTests(TestCase):
    """Tests for the SCENE_ACTION addition to RitualExecutionKind."""

    def test_ritual_execution_kind_includes_scene_action(self):
        self.assertIn("SCENE_ACTION", _EXECUTION_KIND_VALUES)

    def test_ritual_execution_kind_has_all_three_values(self):
        self.assertIn("SERVICE", _EXECUTION_KIND_VALUES)
        self.assertIn("FLOW", _EXECUTION_KIND_VALUES)
        self.assertIn("SCENE_ACTION", _EXECUTION_KIND_VALUES)


class RitualAuthorAccountTests(TestCase):
    """Tests for the optional author_account FK on Ritual."""

    def test_ritual_author_account_optional(self):
        ritual = RitualFactory()
        self.assertIsNone(ritual.author_account)

    def test_ritual_author_account_can_be_set(self):
        user = AccountFactory()
        ritual = RitualFactory(author_account=user)
        self.assertEqual(ritual.author_account, user)

    def test_ritual_author_account_set_null_on_account_deletion(self):
        """Deleting the account sets author_account_id to NULL (SET_NULL)."""
        user = AccountFactory()
        ritual = RitualFactory(author_account=user)
        account_pk = user.pk
        user.delete()
        # Check the raw FK column via values() to bypass SharedMemoryModel identity map.
        from world.magic.models import Ritual as RitualModel

        author_id = RitualModel.objects.filter(pk=ritual.pk).values_list(
            "author_account_id", flat=True
        )[0]
        self.assertIsNone(author_id)
        self.assertNotEqual(account_pk, None)


class RitualCheckConfigCreateTests(TestCase):
    """Tests for creating RitualCheckConfig records."""

    def test_create_config_for_scene_action_ritual(self):
        ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
            flow=None,
        )
        config = RitualCheckConfigFactory(ritual=ritual)
        self.assertEqual(ritual.check_config, config)

    def test_create_config_via_factory(self):
        config = RitualCheckConfigFactory()
        self.assertIsNotNone(config.pk)
        self.assertEqual(config.ritual.execution_kind, RitualExecutionKind.SCENE_ACTION)
        self.assertIsNotNone(config.stat)
        self.assertIsNotNone(config.skill)
        self.assertIsNotNone(config.check_type)
        self.assertEqual(config.target_difficulty, 3)

    def test_config_optional_fields_default_null(self):
        config = RitualCheckConfigFactory()
        self.assertIsNone(config.specialization)
        self.assertIsNone(config.resonance)
        self.assertIsNone(config.non_founder_target_difficulty)

    def test_one_to_one_constraint(self):
        """A ritual can only have one check config."""
        ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
            flow=None,
        )
        RitualCheckConfigFactory(ritual=ritual)
        with self.assertRaises(IntegrityError):
            RitualCheckConfigFactory(ritual=ritual)

    def test_config_str(self):
        config = RitualCheckConfigFactory()
        self.assertIn(str(config.ritual_id), str(config))

    def test_non_founder_target_difficulty_can_be_set(self):
        """non_founder_target_difficulty is settable and stored."""
        config = RitualCheckConfigFactory(non_founder_target_difficulty=5)
        self.assertEqual(config.non_founder_target_difficulty, 5)

    def test_service_ritual_may_carry_config(self):
        """SERVICE rituals are now permitted to carry a RitualCheckConfig."""
        ritual = RitualFactory(execution_kind=RitualExecutionKind.SERVICE)
        config = RitualCheckConfigFactory(ritual=ritual)
        self.assertIsNotNone(config.pk)
        # clean() must not raise for a SERVICE ritual with a config.
        ritual.refresh_from_db()
        ritual.clean()  # no raise


class RitualCheckConfigCleanTests(TestCase):
    """Tests for config invariant in Ritual.clean()."""

    def test_scene_action_ritual_requires_config(self):
        """SCENE_ACTION ritual without config fails clean()."""
        ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
            flow=None,
        )
        # Ritual is saved but has no config; clean() should fail.
        with self.assertRaises(ValidationError) as ctx:
            ritual.clean()
        self.assertIn("execution_kind", ctx.exception.message_dict)

    def test_scene_action_ritual_with_config_passes_clean(self):
        """SCENE_ACTION ritual with config passes clean()."""
        ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
            flow=None,
        )
        RitualCheckConfigFactory(ritual=ritual)
        ritual.refresh_from_db()
        ritual.clean()  # no raise

    def test_new_unsaved_ritual_skips_config_check(self):
        """clean() on an unsaved ritual skips the config DB check (no pk yet)."""
        ritual = Ritual(
            name="Unsaved Scene Action",
            description="test",
            narrative_prose="test",
            execution_kind=RitualExecutionKind.SCENE_ACTION,
        )
        # Should not raise; pk is None so config check is skipped.
        ritual.clean()
