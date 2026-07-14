"""Tests for the food collection mini-game event flow (#2218).

Tests the pre/post event emission, cancellation, difficulty modification,
and pool-size difficulty scaling.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.agriculture.types import FoodCollectionResult


def _make_field(pool=100, name="Field"):
    """Helper: create a Field instance with a crop and uncollected pool."""
    from world.agriculture.models import CropType, FieldDetails
    from world.room_features.constants import (
        RoomFeatureInstallMechanism,
        RoomFeatureServiceStrategy,
    )
    from world.room_features.factories import RoomFeatureInstanceFactory
    from world.room_features.models import RoomFeatureKind

    kind = RoomFeatureKind.objects.create(
        name=name,
        max_level=5,
        service_strategy=RoomFeatureServiceStrategy.FIELD,
        install_mechanism=RoomFeatureInstallMechanism.PROJECT,
    )
    crop = CropType.objects.create(name=f"{name}Crop", base_production=10)
    instance = RoomFeatureInstanceFactory(feature_kind=kind)
    FieldDetails.objects.create(feature_instance=instance, crop_type=crop, uncollected_pool=pool)
    return instance


def _mock_location():
    """A mock location with no triggers so emit_event returns an uncancelled stack."""
    room = MagicMock()
    room.contents = []
    room.trigger_handler = None
    return room


def _seed_check_type():
    """Create the Food Collection CheckType so perform_check is actually called."""
    from world.checks.factories import CheckTypeFactory

    return CheckTypeFactory(name="Food Collection")


def _uncancelled_stack(*args, **kwargs):
    """Return a FlowStack that was not cancelled (the normal case)."""
    from flows.flow_stack import FlowStack

    return FlowStack(owner=None)


def _cancelled_stack(*args, **kwargs):
    """Return a FlowStack that was cancelled."""
    from flows.flow_stack import FlowStack

    stack = FlowStack(owner=None)
    stack.mark_cancelled()
    return stack


class PoolDifficultyBonusTests(TestCase):
    """The pool-size difficulty scaling helper (#2218)."""

    def test_small_pool_no_bonus(self):
        """Pool at or below the threshold produces zero bonus."""
        from world.agriculture.services.collection import _pool_difficulty_bonus

        instance = _make_field(pool=50, name="SmallPool")
        bonus = _pool_difficulty_bonus(instance, MagicMock())
        self.assertEqual(bonus, 0)

    def test_pool_above_threshold_gives_bonus(self):
        """Pool above the threshold produces a stepped bonus."""
        from world.agriculture.services.collection import _pool_difficulty_bonus

        # threshold=50, step=50: pool=150 → excess=100 → bonus=2
        instance = _make_field(pool=150, name="LargePool")
        bonus = _pool_difficulty_bonus(instance, MagicMock())
        self.assertEqual(bonus, 2)

    def test_bonus_is_capped(self):
        """Pool far above the threshold is capped at max_bonus."""
        from world.agriculture.services.collection import _pool_difficulty_bonus

        # threshold=50, step=50, max_bonus=30: pool=5000 → excess=4950 → 99, capped at 30
        instance = _make_field(pool=5000, name="HugePool")
        bonus = _pool_difficulty_bonus(instance, MagicMock())
        self.assertEqual(bonus, 30)


class FoodPreCollectEventTests(TestCase):
    """The FOOD_PRE_COLLECT event is emitted before the pool is zeroed."""

    def test_pre_collect_event_emitted(self):
        """The FOOD_PRE_COLLECT event fires before the pool is zeroed."""
        from world.agriculture.services import collect_field_food

        instance = _make_field(pool=100, name="PreCollect")
        actor = MagicMock(location=_mock_location())

        with patch("flows.emit.emit_event", side_effect=_uncancelled_stack) as mock_emit:
            collect_field_food(actor, instance)

            # emit_event should have been called with food_pre_collect
            self.assertTrue(mock_emit.called)
            first_call = mock_emit.call_args_list[0]
            self.assertEqual(first_call.args[0], "food_pre_collect")

    def test_cancellation_preserves_pool(self):
        """A cancelled pre-collect event leaves the pool intact."""
        from world.agriculture.models import FieldDetails
        from world.agriculture.services import collect_field_food

        instance = _make_field(pool=100, name="Cancelled")
        actor = MagicMock(location=_mock_location())

        with patch("flows.emit.emit_event", side_effect=_cancelled_stack):
            result = collect_field_food(actor, instance)

            self.assertTrue(result.cancelled)
            self.assertEqual(result.gathered, 100)
            self.assertEqual(result.landed, 0)

            # Pool was NOT zeroed
            details = FieldDetails.objects.get(feature_instance=instance)
            self.assertEqual(details.uncollected_pool, 100)

    def test_difficulty_modifier_carried_into_check(self):
        """A reactive flow that mutates difficulty_modifier affects the check difficulty."""
        from world.agriculture.services import collect_field_food

        _seed_check_type()
        instance = _make_field(pool=100, name="ModDifficulty")
        actor = MagicMock(location=_mock_location())

        def emit_side_effect(event_name, payload, location, **kwargs):
            if event_name == "food_pre_collect":
                payload.difficulty_modifier = 10
            from flows.flow_stack import FlowStack

            return FlowStack(owner=None)

        with (
            patch("flows.emit.emit_event", side_effect=emit_side_effect),
            patch("world.checks.services.perform_check") as mock_check,
        ):
            mock_check.return_value = MagicMock(success_level=0)

            collect_field_food(actor, instance)

            # The check should have been called with the modified difficulty
            check_call = mock_check.call_args
            # Base NORMAL=45 + pool_bonus(1 for pool=100: (100-50)/50=1) + modifier(10) = 56
            self.assertEqual(check_call.kwargs["target_difficulty"], 56)


class FoodCollectedEventTests(TestCase):
    """The FOOD_COLLECTED event is emitted after the outcome is resolved."""

    def test_post_collect_event_emitted(self):
        """The FOOD_COLLECTED event fires after collection completes."""
        from world.agriculture.services import collect_field_food

        instance = _make_field(pool=100, name="PostCollect")
        actor = MagicMock(location=_mock_location())

        with patch("flows.emit.emit_event", side_effect=_uncancelled_stack) as mock_emit:
            collect_field_food(actor, instance)

            # Two emit calls: pre-collect and post-collect
            self.assertEqual(mock_emit.call_count, 2)
            post_call = mock_emit.call_args_list[1]
            self.assertEqual(post_call.args[0], "food_collected")

    def test_catastrophe_emits_post_event(self):
        """A catastrophe still emits the post-collect event with catastrophe=True."""
        from world.agriculture.services import collect_field_food

        _seed_check_type()
        instance = _make_field(pool=100, name="Catastrophe")
        actor = MagicMock(location=_mock_location())

        with (
            patch("flows.emit.emit_event", side_effect=_uncancelled_stack) as mock_emit,
            patch("world.checks.services.perform_check") as mock_check,
        ):
            # success_level=-2 → below the last band floor (-1) → catastrophe
            mock_check.return_value = MagicMock(success_level=-2)

            result = collect_field_food(actor, instance)

            self.assertTrue(result.catastrophe)
            # Post-collect event was still emitted
            self.assertEqual(mock_emit.call_count, 2)
            post_call = mock_emit.call_args_list[1]
            self.assertEqual(post_call.args[0], "food_collected")
            # The payload should have catastrophe=True
            payload = post_call.args[1]
            self.assertTrue(payload.catastrophe)


class FoodCollectionResultCancelledTests(TestCase):
    """The FoodCollectionResult.cancelled field (#2218)."""

    def test_cancelled_result_has_cancelled_flag(self):
        """A cancelled result has cancelled=True and zeroes for landed/overflow."""
        result = FoodCollectionResult(
            gathered=100,
            landed=0,
            overflow=0,
            success_level=0,
            cancelled=True,
        )
        self.assertTrue(result.cancelled)
        self.assertFalse(result.catastrophe)

    def test_normal_result_cancelled_defaults_false(self):
        """A normal result has cancelled=False by default."""
        result = FoodCollectionResult(
            gathered=100,
            landed=85,
            overflow=0,
            success_level=0,
        )
        self.assertFalse(result.cancelled)
