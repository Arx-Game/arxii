"""Tests for reference Corruption content factories (Scope #7 Phase 9).

Covers:
- CorruptionConditionTemplateFactory: 5 stages with HOLD_OVERFLOW resist params
- CorruptionTwistTemplateFactory: CORRUPTION_TWIST MagicalAlterationTemplate
- author_reference_corruption_content: idempotent seeding of Primal + Abyssal sets
"""

from django.test import TestCase

from world.magic.constants import AlterationKind
from world.magic.factories import (
    AffinityFactory,
    CorruptionConditionTemplateFactory,
    CorruptionTwistTemplateFactory,
    ResonanceFactory,
    author_reference_corruption_content,
)
from world.magic.models import MagicalAlterationTemplate


class TestCorruptionConditionTemplateFactory(TestCase):
    """CorruptionConditionTemplateFactory authors correct stage shape."""

    def test_creates_five_stages(self) -> None:
        affinity = AffinityFactory(name="Primal")
        resonance = ResonanceFactory(affinity=affinity)
        template = CorruptionConditionTemplateFactory(corruption_resonance=resonance)

        stages = list(template.stages.order_by("stage_order"))
        self.assertEqual(len(stages), 5)

    def test_stage_order_sequential(self) -> None:
        affinity = AffinityFactory(name="Primal")
        resonance = ResonanceFactory(affinity=affinity)
        template = CorruptionConditionTemplateFactory(corruption_resonance=resonance)

        orders = list(template.stages.order_by("stage_order").values_list("stage_order", flat=True))
        self.assertEqual(orders, [1, 2, 3, 4, 5])

    def test_severity_thresholds(self) -> None:
        affinity = AffinityFactory(name="Primal")
        resonance = ResonanceFactory(affinity=affinity)
        template = CorruptionConditionTemplateFactory(corruption_resonance=resonance)

        thresholds = list(
            template.stages.order_by("stage_order").values_list("severity_threshold", flat=True)
        )
        self.assertEqual(thresholds, [50, 200, 500, 1000, 1500])

    def test_primal_resist_difficulties(self) -> None:
        affinity = AffinityFactory(name="Primal")
        resonance = ResonanceFactory(affinity=affinity)
        template = CorruptionConditionTemplateFactory(corruption_resonance=resonance)

        dcs = list(
            template.stages.order_by("stage_order").values_list("resist_difficulty", flat=True)
        )
        self.assertEqual(dcs, [8, 12, 18, 22, 28])

    def test_abyssal_resist_difficulties_harder(self) -> None:
        affinity = AffinityFactory(name="Abyssal")
        resonance = ResonanceFactory(affinity=affinity)
        template = CorruptionConditionTemplateFactory(corruption_resonance=resonance)

        dcs = list(
            template.stages.order_by("stage_order").values_list("resist_difficulty", flat=True)
        )
        self.assertEqual(dcs, [12, 18, 25, 30, 35])

    def test_all_stages_hold_overflow(self) -> None:
        from world.conditions.types import AdvancementResistFailureKind

        affinity = AffinityFactory(name="Primal")
        resonance = ResonanceFactory(affinity=affinity)
        template = CorruptionConditionTemplateFactory(corruption_resonance=resonance)

        kinds = list(
            template.stages.order_by("stage_order").values_list(
                "advancement_resist_failure_kind", flat=True
            )
        )
        self.assertEqual(
            kinds,
            [AdvancementResistFailureKind.HOLD_OVERFLOW] * 5,
        )

    def test_resist_check_type_set(self) -> None:
        affinity = AffinityFactory(name="Primal")
        resonance = ResonanceFactory(affinity=affinity)
        template = CorruptionConditionTemplateFactory(corruption_resonance=resonance)

        # All stages should have a resist_check_type
        for stage in template.stages.select_related("resist_check_type").order_by("stage_order"):
            self.assertIsNotNone(stage.resist_check_type, f"Stage {stage.stage_order} missing")
            self.assertEqual(stage.resist_check_type.name, "Magical Endurance")

    def test_passive_decay_max_severity_set_to_stage_2_threshold(self) -> None:
        affinity = AffinityFactory(name="Primal")
        resonance = ResonanceFactory(affinity=affinity)
        template = CorruptionConditionTemplateFactory(corruption_resonance=resonance)

        # Stage 2 threshold = 200; decay max should match
        self.assertEqual(template.passive_decay_max_severity, 200)

    def test_has_progression_flag_set(self) -> None:
        affinity = AffinityFactory(name="Primal")
        resonance = ResonanceFactory(affinity=affinity)
        template = CorruptionConditionTemplateFactory(corruption_resonance=resonance)

        self.assertTrue(template.has_progression)

    def test_idempotent_via_get_or_create(self) -> None:
        from world.conditions.models import ConditionTemplate

        affinity = AffinityFactory(name="Primal")
        resonance = ResonanceFactory(affinity=affinity)
        CorruptionConditionTemplateFactory(corruption_resonance=resonance)
        CorruptionConditionTemplateFactory(corruption_resonance=resonance)

        count = ConditionTemplate.objects.filter(corruption_resonance=resonance).count()
        self.assertEqual(count, 1)


class TestCorruptionTwistTemplateFactory(TestCase):
    """CorruptionTwistTemplateFactory produces valid CORRUPTION_TWIST rows."""

    def test_kind_is_corruption_twist(self) -> None:
        affinity = AffinityFactory(name="Primal")
        resonance = ResonanceFactory(affinity=affinity)
        twist = CorruptionTwistTemplateFactory(
            origin_resonance=resonance,
            resonance=resonance,
            origin_affinity=affinity,
            stage_threshold=2,
            kind=AlterationKind.CORRUPTION_TWIST,
        )
        self.assertEqual(twist.kind, AlterationKind.CORRUPTION_TWIST)

    def test_stage_threshold_stored(self) -> None:
        affinity = AffinityFactory(name="Abyssal")
        resonance = ResonanceFactory(affinity=affinity)
        twist = CorruptionTwistTemplateFactory(
            origin_resonance=resonance,
            resonance=resonance,
            origin_affinity=affinity,
            stage_threshold=3,
            kind=AlterationKind.CORRUPTION_TWIST,
        )
        self.assertEqual(twist.stage_threshold, 3)

    def test_resonance_fk_set(self) -> None:
        affinity = AffinityFactory(name="Primal")
        resonance = ResonanceFactory(affinity=affinity)
        twist = CorruptionTwistTemplateFactory(
            origin_resonance=resonance,
            resonance=resonance,
            origin_affinity=affinity,
            stage_threshold=2,
            kind=AlterationKind.CORRUPTION_TWIST,
        )
        self.assertEqual(twist.resonance_id, resonance.pk)


class TestAuthorReferenceCorruptionContent(TestCase):
    """author_reference_corruption_content seeds Primal + Abyssal sets correctly."""

    def test_both_resonances_get_condition_templates(self) -> None:
        from world.conditions.models import ConditionTemplate

        author_reference_corruption_content()

        self.assertTrue(
            ConditionTemplate.objects.filter(corruption_resonance__name="Wild Hunt").exists()
        )
        self.assertTrue(
            ConditionTemplate.objects.filter(corruption_resonance__name="Web of Spiders").exists()
        )

    def test_primal_has_six_or_more_twist_templates(self) -> None:
        author_reference_corruption_content()

        count = MagicalAlterationTemplate.objects.filter(
            kind=AlterationKind.CORRUPTION_TWIST,
            resonance__name="Wild Hunt",
        ).count()
        # 3 stages × 2 templates each = 6
        self.assertGreaterEqual(count, 6)

    def test_abyssal_has_six_or_more_twist_templates(self) -> None:
        author_reference_corruption_content()

        count = MagicalAlterationTemplate.objects.filter(
            kind=AlterationKind.CORRUPTION_TWIST,
            resonance__name="Web of Spiders",
        ).count()
        self.assertGreaterEqual(count, 6)

    def test_idempotent_does_not_double_create_condition_template(self) -> None:
        from world.conditions.models import ConditionTemplate

        author_reference_corruption_content()
        author_reference_corruption_content()

        self.assertEqual(
            ConditionTemplate.objects.filter(corruption_resonance__name="Wild Hunt").count(), 1
        )
        self.assertEqual(
            ConditionTemplate.objects.filter(corruption_resonance__name="Web of Spiders").count(),
            1,
        )

    def test_idempotent_does_not_exceed_twist_count(self) -> None:
        author_reference_corruption_content()
        count_before = MagicalAlterationTemplate.objects.filter(
            kind=AlterationKind.CORRUPTION_TWIST,
            resonance__name="Wild Hunt",
        ).count()

        author_reference_corruption_content()
        count_after = MagicalAlterationTemplate.objects.filter(
            kind=AlterationKind.CORRUPTION_TWIST,
            resonance__name="Wild Hunt",
        ).count()

        self.assertEqual(count_before, count_after)

    def test_wild_hunt_is_primal_affinity(self) -> None:
        from world.magic.models.affinity import Resonance

        author_reference_corruption_content()

        resonance = Resonance.objects.select_related("affinity").get(name="Wild Hunt")
        self.assertEqual(resonance.affinity.name, "Primal")

    def test_web_of_spiders_is_abyssal_affinity(self) -> None:
        from world.magic.models.affinity import Resonance

        author_reference_corruption_content()

        resonance = Resonance.objects.select_related("affinity").get(name="Web of Spiders")
        self.assertEqual(resonance.affinity.name, "Abyssal")

    def test_primal_condition_template_has_five_stages(self) -> None:
        from world.conditions.models import ConditionTemplate

        author_reference_corruption_content()

        template = ConditionTemplate.objects.get(corruption_resonance__name="Wild Hunt")
        self.assertEqual(template.stages.count(), 5)

    def test_abyssal_condition_template_has_harder_dcs(self) -> None:
        from world.conditions.models import ConditionTemplate

        author_reference_corruption_content()

        abyssal_template = ConditionTemplate.objects.get(
            corruption_resonance__name="Web of Spiders"
        )
        dcs = list(
            abyssal_template.stages.order_by("stage_order").values_list(
                "resist_difficulty", flat=True
            )
        )
        self.assertEqual(dcs, [12, 18, 25, 30, 35])
