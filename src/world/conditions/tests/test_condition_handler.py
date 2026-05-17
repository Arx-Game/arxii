"""Tests for ConditionHandler — ObjectParent.conditions cached handler.

Validates:
- First access to active() issues exactly 1 query on a non-Character ObjectDB
  (base ConditionHandler, no extra prefetch).
- Subsequent access (and filter methods) issue ZERO queries.
- Query count does NOT scale with condition or template count.
- apply_condition / remove_condition invalidation is reflected immediately.
- "active" semantics match get_active_conditions for suppressed conditions.
- Works for non-Character ObjectDB targets (Room typeclass).
- Characters continue to expose CharacterConditionHandler (subclass with
  resistance_modifier) via their own cached_property override.
"""

from evennia import create_object
from evennia.utils.test_resources import EvenniaTestCase

from world.conditions.factories import (
    ConditionTemplateFactory,
)
from world.conditions.services import apply_condition, get_active_conditions, remove_condition


class ConditionHandlerFirstAccessQueryTest(EvenniaTestCase):
    """First call to active() on a Room issues 1 query; repeats issue 0.

    Rooms use the base ConditionHandler (installed via ObjectParent).
    Characters have their own CharacterConditionHandler override.
    """

    def test_first_active_call_issues_one_query_on_room(self) -> None:
        room = create_object("typeclasses.rooms.Room", key="Q1Room", nohome=True)
        t1 = ConditionTemplateFactory(name="BurningR")
        t2 = ConditionTemplateFactory(name="ChilledR")
        t3 = ConditionTemplateFactory(name="StunnedR")
        apply_condition(room, t1)
        apply_condition(room, t2)
        apply_condition(room, t3)
        # Invalidate so we start from a cold cache
        room.conditions.invalidate()

        with self.assertNumQueries(1):
            result = room.conditions.active()

        self.assertEqual(len(result), 3)

    def test_second_active_call_issues_zero_queries(self) -> None:
        room = create_object("typeclasses.rooms.Room", key="Q2Room", nohome=True)
        t1 = ConditionTemplateFactory(name="BurningB")
        t2 = ConditionTemplateFactory(name="ChilledB")
        apply_condition(room, t1)
        apply_condition(room, t2)
        room.conditions.invalidate()
        # Warm the cache
        room.conditions.active()

        with self.assertNumQueries(0):
            room.conditions.active()
            room.conditions.active()

    def test_query_count_constant_regardless_of_condition_count(self) -> None:
        """Loading 5 active conditions on a Room still costs exactly 1 query."""
        room = create_object("typeclasses.rooms.Room", key="Q3Room", nohome=True)
        templates = [ConditionTemplateFactory() for _ in range(5)]
        for t in templates:
            apply_condition(room, t)
        room.conditions.invalidate()

        with self.assertNumQueries(1):
            result = room.conditions.active()

        self.assertEqual(len(result), 5)

    def test_instances_for_templates_zero_queries_after_warmup(self) -> None:
        room = create_object("typeclasses.rooms.Room", key="Q4Room", nohome=True)
        t1 = ConditionTemplateFactory(name="ColdC")
        t2 = ConditionTemplateFactory(name="WetC")
        t3 = ConditionTemplateFactory(name="BurnC")
        apply_condition(room, t1)
        apply_condition(room, t2)
        apply_condition(room, t3)
        # Warm cache
        room.conditions.active()

        with self.assertNumQueries(0):
            matches = room.conditions.instances_for_templates({t1, t3})

        self.assertEqual(len(matches), 2)
        template_pks = {i.condition_id for i in matches}
        self.assertIn(t1.pk, template_pks)
        self.assertIn(t3.pk, template_pks)
        self.assertNotIn(t2.pk, template_pks)

    def test_has_template_zero_queries_after_warmup(self) -> None:
        room = create_object("typeclasses.rooms.Room", key="Q5Room", nohome=True)
        t1 = ConditionTemplateFactory(name="ColdD")
        t2 = ConditionTemplateFactory(name="WetD")
        apply_condition(room, t1)
        # Warm cache
        room.conditions.active()

        with self.assertNumQueries(0):
            self.assertTrue(room.conditions.has_template(t1))
            self.assertFalse(room.conditions.has_template(t2))

    def test_query_count_constant_regardless_of_template_count(self) -> None:
        """instances_for_templates with many templates still costs 0 queries post-warmup."""
        room = create_object("typeclasses.rooms.Room", key="Q6Room", nohome=True)
        templates = [ConditionTemplateFactory() for _ in range(8)]
        for t in templates[:4]:
            apply_condition(room, t)
        room.conditions.active()  # warm

        with self.assertNumQueries(0):
            matches = room.conditions.instances_for_templates(set(templates))

        # Only the first 4 were applied
        self.assertEqual(len(matches), 4)

    def test_character_conditions_still_zero_queries_on_repeat(self) -> None:
        """Characters also get 0 queries on repeat (CharacterConditionHandler subclass)."""
        char = create_object("typeclasses.characters.Character", key="Q7Char", nohome=True)
        t1 = ConditionTemplateFactory(name="ColdE")
        apply_condition(char, t1)
        # Warm the character's cache (may be >1 query on first access due to prefetch)
        char.conditions.active()

        with self.assertNumQueries(0):
            char.conditions.active()
            char.conditions.active()


class ConditionHandlerInvalidationTest(EvenniaTestCase):
    """apply_condition / remove_condition reflect changes via invalidation."""

    def test_apply_condition_reflected_after_invalidation(self) -> None:
        room = create_object("typeclasses.rooms.Room", key="I1Room", nohome=True)
        t1 = ConditionTemplateFactory(name="ColdE")
        # Prime empty cache
        initial = room.conditions.active()
        self.assertEqual(len(initial), 0)

        apply_condition(room, t1)
        # apply_condition must have invalidated — next read reflects new state
        result = room.conditions.active()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].condition_id, t1.pk)

    def test_apply_condition_reflected_on_character(self) -> None:
        char = create_object("typeclasses.characters.Character", key="I2Char", nohome=True)
        t1 = ConditionTemplateFactory(name="ColdF")
        initial = char.conditions.active()
        self.assertEqual(len(initial), 0)

        apply_condition(char, t1)
        result = char.conditions.active()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].condition_id, t1.pk)

    def test_remove_condition_reflected_after_invalidation(self) -> None:
        room = create_object("typeclasses.rooms.Room", key="I3Room", nohome=True)
        t1 = ConditionTemplateFactory(name="ColdG")
        apply_condition(room, t1)
        self.assertEqual(len(room.conditions.active()), 1)

        remove_condition(room, t1)
        result = room.conditions.active()
        self.assertEqual(len(result), 0)

    def test_remove_condition_reflected_on_character(self) -> None:
        char = create_object("typeclasses.characters.Character", key="I4Char", nohome=True)
        t1 = ConditionTemplateFactory(name="ColdH")
        apply_condition(char, t1)
        self.assertEqual(len(char.conditions.active()), 1)

        remove_condition(char, t1)
        result = char.conditions.active()
        self.assertEqual(len(result), 0)

    def test_manual_invalidate_drops_internal_cache(self) -> None:
        room = create_object("typeclasses.rooms.Room", key="I5Room", nohome=True)
        t1 = ConditionTemplateFactory(name="ColdI")
        apply_condition(room, t1)
        # Prime cache
        room.conditions.active()
        # Manually invalidate — forces re-query
        room.conditions.invalidate()
        with self.assertNumQueries(1):
            room.conditions.active()


class ConditionHandlerActiveSemanticParityTest(EvenniaTestCase):
    """active() semantics must match get_active_conditions() exactly."""

    def test_suppressed_condition_excluded_by_default(self) -> None:
        from world.conditions.models import ConditionInstance

        room = create_object("typeclasses.rooms.Room", key="S1Room", nohome=True)
        t1 = ConditionTemplateFactory(name="ColdJ")
        apply_condition(room, t1)
        instance = ConditionInstance.objects.get(target=room, condition=t1)
        instance.is_suppressed = True
        instance.save(update_fields=["is_suppressed"])
        room.conditions.invalidate()

        handler_result = room.conditions.active()
        service_result = list(get_active_conditions(room))

        self.assertEqual(len(handler_result), 0)
        self.assertEqual(len(service_result), 0)
        self.assertEqual(
            {i.pk for i in handler_result},
            {i.pk for i in service_result},
        )

    def test_suppressed_until_expired_condition_is_active(self) -> None:
        """A condition whose suppressed_until is in the past is active (suppression lifted)."""
        from django.utils import timezone

        from world.conditions.models import ConditionInstance

        room = create_object("typeclasses.rooms.Room", key="S2Room", nohome=True)
        t1 = ConditionTemplateFactory(name="ColdK")
        apply_condition(room, t1)
        instance = ConditionInstance.objects.get(target=room, condition=t1)
        # Suppressed but suppressed_until is in the past → suppression has expired
        instance.is_suppressed = False
        instance.suppressed_until = timezone.now() - timezone.timedelta(hours=1)
        instance.save(update_fields=["is_suppressed", "suppressed_until"])
        room.conditions.invalidate()

        handler_result = room.conditions.active()
        service_result = list(get_active_conditions(room))

        # Both should include the condition (suppression expired)
        self.assertEqual(
            {i.pk for i in handler_result},
            {i.pk for i in service_result},
        )
        self.assertEqual(len(handler_result), 1)

    def test_parity_across_multiple_conditions_mixed_suppression(self) -> None:
        from world.conditions.models import ConditionInstance

        room = create_object("typeclasses.rooms.Room", key="S3Room", nohome=True)
        t1 = ConditionTemplateFactory(name="ColdL")
        t2 = ConditionTemplateFactory(name="WetL")
        t3 = ConditionTemplateFactory(name="BurnL")
        apply_condition(room, t1)
        apply_condition(room, t2)
        apply_condition(room, t3)
        # Suppress t2
        inst2 = ConditionInstance.objects.get(target=room, condition=t2)
        inst2.is_suppressed = True
        inst2.save(update_fields=["is_suppressed"])
        room.conditions.invalidate()

        handler_pks = {i.pk for i in room.conditions.active()}
        service_pks = {i.pk for i in get_active_conditions(room)}
        self.assertEqual(handler_pks, service_pks)


class ConditionHandlerNonCharacterTest(EvenniaTestCase):
    """handler works for Room typeclass — conditions is on ObjectParent, not just Character."""

    def test_room_has_conditions_handler(self) -> None:
        room = create_object("typeclasses.rooms.Room", key="TestRoom1", nohome=True)
        self.assertTrue(hasattr(room, "conditions"))
        self.assertTrue(callable(room.conditions.active))
        self.assertTrue(callable(room.conditions.invalidate))
        self.assertTrue(callable(room.conditions.instances_for_templates))
        self.assertTrue(callable(room.conditions.has_template))

    def test_room_active_returns_empty_with_no_conditions(self) -> None:
        room = create_object("typeclasses.rooms.Room", key="TestRoom2", nohome=True)
        with self.assertNumQueries(1):
            result = room.conditions.active()
        self.assertEqual(result, [])

    def test_apply_and_read_condition_on_room(self) -> None:
        room = create_object("typeclasses.rooms.Room", key="TestRoom3", nohome=True)
        t1 = ConditionTemplateFactory(name="Dark")
        apply_condition(room, t1)

        result = room.conditions.active()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].condition_id, t1.pk)

    def test_room_second_active_call_zero_queries(self) -> None:
        room = create_object("typeclasses.rooms.Room", key="TestRoom4", nohome=True)
        t1 = ConditionTemplateFactory(name="Foggy")
        apply_condition(room, t1)
        room.conditions.active()  # warm

        with self.assertNumQueries(0):
            room.conditions.active()

    def test_character_conditions_is_subclass_of_condition_handler(self) -> None:
        """Characters return CharacterConditionHandler which is a ConditionHandler subclass."""
        from world.conditions.handlers import CharacterConditionHandler, ConditionHandler

        char = create_object("typeclasses.characters.Character", key="TestChar1", nohome=True)
        self.assertIsInstance(char.conditions, ConditionHandler)
        self.assertIsInstance(char.conditions, CharacterConditionHandler)


class CharacterConditionHandlerParityTest(EvenniaTestCase):
    """character.conditions.active() must return exactly the same set as get_active_conditions().

    Parity tests covering all four cases across the canonical active filter boundary.
    Each subtest asserts `character.conditions.active()` == `get_active_conditions(character)`.
    After cache warmup, all repeated reads must be 0 queries.
    """

    def test_plain_active_condition_included_by_both(self) -> None:
        """A plain active (not suppressed, not resolved) condition appears in both."""
        char = create_object("typeclasses.characters.Character", key="ParityChar1", nohome=True)
        t1 = ConditionTemplateFactory(name="ParityActive")
        apply_condition(char, t1)
        char.conditions.invalidate()

        handler_pks = {i.pk for i in char.conditions.active()}
        service_pks = {i.pk for i in get_active_conditions(char)}
        self.assertEqual(handler_pks, service_pks)
        self.assertEqual(len(handler_pks), 1)

    def test_suppressed_condition_excluded_by_both(self) -> None:
        """is_suppressed=True means the condition is absent from both."""
        from world.conditions.models import ConditionInstance

        char = create_object("typeclasses.characters.Character", key="ParityChar2", nohome=True)
        t1 = ConditionTemplateFactory(name="ParitySuppressed")
        apply_condition(char, t1)
        instance = ConditionInstance.objects.get(target=char, condition=t1)
        instance.is_suppressed = True
        instance.save(update_fields=["is_suppressed"])
        char.conditions.invalidate()

        handler_pks = {i.pk for i in char.conditions.active()}
        service_pks = {i.pk for i in get_active_conditions(char)}
        self.assertEqual(handler_pks, service_pks)
        self.assertEqual(len(handler_pks), 0)

    def test_suppressed_until_expired_included_by_both(self) -> None:
        """suppressed_until in the past means suppression lifted — both include it.

        This is the first previously-divergent case: the old CharacterConditionHandler
        used is_suppressed=False only, missing the suppressed_until expiry branch.
        """
        from django.utils import timezone

        from world.conditions.models import ConditionInstance

        char = create_object("typeclasses.characters.Character", key="ParityChar3", nohome=True)
        t1 = ConditionTemplateFactory(name="ParityExpired")
        apply_condition(char, t1)
        instance = ConditionInstance.objects.get(target=char, condition=t1)
        instance.is_suppressed = False
        instance.suppressed_until = timezone.now() - timezone.timedelta(hours=1)
        instance.save(update_fields=["is_suppressed", "suppressed_until"])
        char.conditions.invalidate()

        handler_pks = {i.pk for i in char.conditions.active()}
        service_pks = {i.pk for i in get_active_conditions(char)}
        self.assertEqual(handler_pks, service_pks)
        self.assertEqual(len(handler_pks), 1)

    def test_resolved_at_condition_included_by_both(self) -> None:
        """resolved_at-set condition is NOT filtered out — both return it.

        This is the second previously-divergent case: the old CharacterConditionHandler
        applied resolved_at__isnull=True which excluded resolved conditions,
        diverging from get_active_conditions which has no resolved_at gate.
        """
        from django.utils import timezone

        from world.conditions.models import ConditionInstance

        char = create_object("typeclasses.characters.Character", key="ParityChar4", nohome=True)
        t1 = ConditionTemplateFactory(name="ParityResolved")
        apply_condition(char, t1)
        instance = ConditionInstance.objects.get(target=char, condition=t1)
        instance.resolved_at = timezone.now()
        instance.save(update_fields=["resolved_at"])
        char.conditions.invalidate()

        handler_pks = {i.pk for i in char.conditions.active()}
        service_pks = {i.pk for i in get_active_conditions(char)}
        self.assertEqual(handler_pks, service_pks)
        self.assertEqual(len(handler_pks), 1)

    def test_zero_queries_on_repeat_for_character(self) -> None:
        """After cache warmup, character.conditions.active() costs 0 queries."""
        char = create_object("typeclasses.characters.Character", key="ParityChar5", nohome=True)
        t1 = ConditionTemplateFactory(name="ParityCache")
        apply_condition(char, t1)
        # Warm the cache
        char.conditions.active()

        with self.assertNumQueries(0):
            char.conditions.active()
            char.conditions.active()
