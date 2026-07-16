from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import ObjectDBFactory
from world.conditions.constants import (
    ConditionInteractionOutcome,
    ConditionInteractionTrigger,
)
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionConditionInteractionFactory,
    ConditionDamageInteractionFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
)
from world.conditions.services import (
    advance_condition_severity,
    apply_condition,
    bulk_apply_conditions,
    clear_all_conditions,
    decay_condition_severity,
    process_damage_interactions,
    process_round_end,
    remove_condition,
    remove_conditions_by_category,
    suppress_condition,
)
from world.conditions.types import BulkConditionApplication
from world.roster.factories import RosterEntryFactory
from world.scenes.factories import SceneFactory
from world.scenes.services import has_unseen_observers


def _create_room(key: str = "TestRoom") -> ObjectDB:
    return ObjectDBFactory(
        db_key=key,
        db_typeclass_path="typeclasses.rooms.Room",
    )


class ConcealmentOOCWiringTests(TestCase):
    def setUp(self) -> None:
        roster = RosterEntryFactory()
        self.sheet = roster.character_sheet
        self.character = self.sheet.character
        # CharacterFactory creates with nohome=True (location=None); a real room is
        # required for get_active_scene to resolve anything (mirrors test_can_perceive.py).
        self.character.location = _create_room()
        self.scene = SceneFactory(location=self.character.location, is_active=True)
        cat = ConditionCategoryFactory(conceals_from_perception=True)
        self.template = ConditionTemplateFactory(category=cat)

    def test_apply_registers_unseen_observer(self) -> None:
        apply_condition(target=self.character, condition=self.template)
        self.assertTrue(has_unseen_observers(self.scene))

    def test_remove_clears_unseen_observer(self) -> None:
        apply_condition(target=self.character, condition=self.template)
        remove_condition(self.character, self.template)
        self.assertFalse(has_unseen_observers(self.scene))

    def test_suppress_clears_unseen_observer(self) -> None:
        apply_condition(target=self.character, condition=self.template)
        suppress_condition(self.character, self.template)
        self.assertFalse(has_unseen_observers(self.scene))

    def test_non_concealing_condition_does_not_register(self) -> None:
        plain_template = ConditionTemplateFactory()
        apply_condition(target=self.character, condition=plain_template)
        self.assertFalse(has_unseen_observers(self.scene))

    def test_remove_one_of_two_concealments_keeps_banner_up(self) -> None:
        """Two independently-applied concealing conditions on the same target;
        removing one must not drop the OOC banner while the other remains active
        (#1225 review fix)."""
        other_cat = ConditionCategoryFactory(conceals_from_perception=True)
        other_template = ConditionTemplateFactory(category=other_cat)

        apply_condition(target=self.character, condition=self.template)
        apply_condition(target=self.character, condition=other_template)
        self.assertTrue(has_unseen_observers(self.scene))

        remove_condition(self.character, self.template)

        self.assertTrue(has_unseen_observers(self.scene))

    def test_bulk_apply_registers_unseen_observer(self) -> None:
        """bulk_apply_conditions (the magic/combat/covenant apply path, #1225 review
        gap) must trigger the same OOC hook as the single-condition apply_condition
        path."""
        bulk_apply_conditions(
            [BulkConditionApplication(target=self.character, template=self.template)]
        )
        self.assertTrue(has_unseen_observers(self.scene))

    def test_remove_conditions_by_category_clears_unseen_observer(self) -> None:
        """remove_conditions_by_category (final-review gap) previously bypassed the
        per-instance teardown via a raw queryset ``.delete()`` — it must clear the
        OOC banner when it removes the last concealing condition on target."""
        apply_condition(target=self.character, condition=self.template)
        self.assertTrue(has_unseen_observers(self.scene))

        remove_conditions_by_category(self.character, self.template.category)

        self.assertFalse(has_unseen_observers(self.scene))

    def test_remove_conditions_by_category_keeps_banner_if_other_concealment_remains(
        self,
    ) -> None:
        """Mirrors test_remove_one_of_two_concealments_keeps_banner_up for the bulk
        category-clear path: clearing one category must not drop the banner while an
        independently-applied concealment in another category is still active."""
        other_cat = ConditionCategoryFactory(conceals_from_perception=True)
        other_template = ConditionTemplateFactory(category=other_cat)

        apply_condition(target=self.character, condition=self.template)
        apply_condition(target=self.character, condition=other_template)
        self.assertTrue(has_unseen_observers(self.scene))

        remove_conditions_by_category(self.character, self.template.category)

        self.assertTrue(has_unseen_observers(self.scene))

    def test_clear_all_conditions_clears_unseen_observer(self) -> None:
        """clear_all_conditions (final-review gap) previously bypassed the
        per-instance teardown via a raw queryset ``.delete()`` — it must clear the
        OOC banner when it removes the last concealing condition on target."""
        apply_condition(target=self.character, condition=self.template)
        self.assertTrue(has_unseen_observers(self.scene))

        clear_all_conditions(self.character)

        self.assertFalse(has_unseen_observers(self.scene))

    def test_decay_to_zero_severity_clears_unseen_observer(self) -> None:
        """Natural severity decay to zero (final-review gap, #1225) — a concealing
        condition that expires via ``decay_condition_severity`` must clear the OOC
        banner exactly like ``remove_condition`` does. Currently inert in production
        (the seeded ``Concealed`` template has no ``passive_decay_per_day``, so
        ``decay_all_conditions_tick`` never reaches this path today) but ADR-0083
        promises the hook for any future duration/decay-based concealment producer.

        Uses ``apply_condition`` (not a raw ``ConditionInstanceFactory`` row) so the
        register hook actually fires before decay — a bare factory-created instance
        was never registered in the first place, which would make the opening
        assertion pass for the wrong reason (or fail outright)."""
        instance = apply_condition(
            target=self.character, condition=self.template, severity=1
        ).instance
        self.assertTrue(has_unseen_observers(self.scene))

        decay_condition_severity(instance, amount=1)

        self.assertEqual(instance.severity, 0)
        self.assertIsNotNone(instance.resolved_at)
        self.assertFalse(has_unseen_observers(self.scene))

    def test_decay_that_holds_above_zero_does_not_clear_banner(self) -> None:
        """A partial decay that leaves severity above zero must NOT clear the OOC
        banner — only a full decay-to-zero (natural expiry) does."""
        instance = apply_condition(
            target=self.character, condition=self.template, severity=3
        ).instance
        self.assertTrue(has_unseen_observers(self.scene))

        decay_condition_severity(instance, amount=1)

        self.assertEqual(instance.severity, 2)
        self.assertIsNone(instance.resolved_at)
        self.assertTrue(has_unseen_observers(self.scene))

    def test_advance_from_zero_reregisters_unseen_observer(self) -> None:
        """Inverse of the decay-to-zero case — a resolved concealing condition
        re-advancing from zero severity must re-register the OOC banner (#1225)."""
        instance = apply_condition(
            target=self.character, condition=self.template, severity=1
        ).instance
        self.assertTrue(has_unseen_observers(self.scene))
        decay_condition_severity(instance, amount=1)
        self.assertFalse(has_unseen_observers(self.scene))

        advance_condition_severity(instance, amount=1)

        self.assertEqual(instance.severity, 1)
        self.assertIsNone(instance.resolved_at)
        self.assertTrue(has_unseen_observers(self.scene))

    def test_condition_condition_interaction_removal_clears_unseen_observer(
        self,
    ) -> None:
        """bulk_apply_conditions's condition-condition interaction removal path
        (final-review gap) previously deleted the losing instance via a raw
        ``existing_instance.delete()`` inside ``_process_interactions_from_context``,
        bypassing the OOC clear hook entirely. Applying an incoming condition that
        removes the concealing one via interaction must clear the banner."""
        incoming = ConditionTemplateFactory()
        ConditionConditionInteractionFactory(
            condition=self.template,
            other_condition=incoming,
            trigger=ConditionInteractionTrigger.ON_OTHER_APPLIED,
            outcome=ConditionInteractionOutcome.REMOVE_SELF,
        )

        apply_condition(target=self.character, condition=self.template)
        self.assertTrue(has_unseen_observers(self.scene))

        bulk_apply_conditions([BulkConditionApplication(target=self.character, template=incoming)])

        self.assertFalse(has_unseen_observers(self.scene))

    def test_damage_interaction_removal_clears_unseen_observer(self) -> None:
        """process_damage_interactions (final-review gap) previously deleted a
        ``removes_condition=True`` instance directly, bypassing the OOC clear
        hook. This is reachable today through the existing, already-shipped
        ConditionDamageInteraction admin form — not hypothetical."""
        force = DamageTypeFactory()
        ConditionDamageInteractionFactory(
            condition=self.template,
            damage_type=force,
            removes_condition=True,
        )

        apply_condition(target=self.character, condition=self.template)
        self.assertTrue(has_unseen_observers(self.scene))

        process_damage_interactions(self.character, force)

        self.assertFalse(has_unseen_observers(self.scene))

    def test_rounds_duration_expiry_clears_unseen_observer(self) -> None:
        """_process_duration_and_progression's ROUNDS-duration countdown-to-zero
        expiry path (final-review gap) previously deleted the instance directly,
        bypassing the OOC clear hook. Currently inert in production (the seeded
        ``Concealed`` template is PERMANENT-duration) but mirrors the
        decay/advance fix — the same producer class round 4 pre-emptively closed
        for natural severity decay was missed for natural ROUNDS expiry."""
        apply_condition(target=self.character, condition=self.template, duration_rounds=1)
        self.assertTrue(has_unseen_observers(self.scene))

        process_round_end(self.character)

        self.assertFalse(has_unseen_observers(self.scene))
