"""Tests for RitualSceneActionConfig sidecar model."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.magic.constants import RitualExecutionKind
from world.magic.factories import (
    RitualFactory,
    RitualSceneActionConfigFactory,
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


class RitualSceneActionConfigCreateTests(TestCase):
    """Tests for creating RitualSceneActionConfig records."""

    def test_create_config_for_scene_action_ritual(self):
        ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
            flow=None,
        )
        config = RitualSceneActionConfigFactory(ritual=ritual)
        self.assertEqual(ritual.scene_action_config, config)

    def test_create_config_via_factory(self):
        config = RitualSceneActionConfigFactory()
        self.assertIsNotNone(config.pk)
        self.assertEqual(config.ritual.execution_kind, RitualExecutionKind.SCENE_ACTION)
        self.assertIsNotNone(config.stat)
        self.assertIsNotNone(config.skill)
        self.assertIsNotNone(config.check_type)
        self.assertEqual(config.target_difficulty, 3)

    def test_config_optional_fields_default_null(self):
        config = RitualSceneActionConfigFactory()
        self.assertIsNone(config.specialization)
        self.assertIsNone(config.resonance)

    def test_one_to_one_constraint(self):
        """A ritual can only have one scene action config."""
        ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
            flow=None,
        )
        RitualSceneActionConfigFactory(ritual=ritual)
        with self.assertRaises(IntegrityError):
            RitualSceneActionConfigFactory(ritual=ritual)

    def test_config_str(self):
        config = RitualSceneActionConfigFactory()
        self.assertIn(str(config.ritual_id), str(config))


class RitualSceneActionCleanTests(TestCase):
    """Tests for sidecar invariant in Ritual.clean()."""

    def test_scene_action_ritual_requires_sidecar(self):
        """SCENE_ACTION ritual without sidecar fails clean()."""
        ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
            flow=None,
        )
        # Ritual is saved but has no sidecar; clean() should fail.
        with self.assertRaises(ValidationError) as ctx:
            ritual.clean()
        self.assertIn("execution_kind", ctx.exception.message_dict)

    def test_service_ritual_must_not_have_sidecar(self):
        """SERVICE ritual with a sidecar fails clean()."""
        ritual = RitualFactory(execution_kind=RitualExecutionKind.SERVICE)
        RitualSceneActionConfigFactory(ritual=ritual)
        ritual.refresh_from_db()
        with self.assertRaises(ValidationError) as ctx:
            ritual.clean()
        self.assertIn("execution_kind", ctx.exception.message_dict)

    def test_scene_action_ritual_with_sidecar_passes_clean(self):
        """SCENE_ACTION ritual with sidecar passes clean()."""
        ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
            flow=None,
        )
        RitualSceneActionConfigFactory(ritual=ritual)
        ritual.refresh_from_db()
        ritual.clean()  # no raise

    def test_new_unsaved_ritual_skips_sidecar_check(self):
        """clean() on an unsaved ritual skips the sidecar DB check (no pk yet)."""
        ritual = Ritual(
            name="Unsaved Scene Action",
            description="test",
            narrative_prose="test",
            execution_kind=RitualExecutionKind.SCENE_ACTION,
        )
        # Should not raise; pk is None so sidecar check is skipped.
        ritual.clean()
