"""Tests for the required-content sentinel registry and collector (#3444)."""

from __future__ import annotations

from contextlib import contextmanager
from unittest import mock

from django.test import TestCase

from web.admin.tuning import required_content as rc
from world.conditions.factories import ConditionTemplateFactory


def _dep(key: str, probe: rc.ContentProbe, tier: rc.DependencyTier) -> rc.ContentDependency:
    return rc.ContentDependency(
        key=key,
        label=f"label for {key}",
        tier=tier,
        consumer="world/example.py:1 example()",
        consequence="Example breaks.",
        probe=probe,
    )


class TestBuildRegistry(TestCase):
    def test_duplicate_key_rejected(self) -> None:
        probe = rc.AnyRowProbe(label="ConditionTemplate")
        deps = [
            _dep("dup", probe, rc.DependencyTier.REQUIRED),
            _dep("dup", probe, rc.DependencyTier.REQUIRED),
        ]
        with self.assertRaises(ValueError):
            rc.build_registry(deps)

    def test_distinct_keys_accepted(self) -> None:
        probe = rc.AnyRowProbe(label="ConditionTemplate")
        deps = [
            _dep("a", probe, rc.DependencyTier.REQUIRED),
            _dep("b", probe, rc.DependencyTier.TUNING),
        ]
        self.assertEqual(len(rc.build_registry(deps)), 2)


class TestNamedRowsProbe(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        ConditionTemplateFactory(name="Mounted")

    def test_present_when_row_exists(self) -> None:
        probe = rc.NamedRowsProbe(label="ConditionTemplate", names=("Mounted",))
        result = probe.resolve(frozenset({"mounted"}))
        self.assertTrue(result.present)
        self.assertEqual(result.missing, ())

    def test_missing_names_reported(self) -> None:
        probe = rc.NamedRowsProbe(label="ConditionTemplate", names=("Mounted", "Unhorsed"))
        result = probe.resolve(frozenset({"mounted"}))
        self.assertFalse(result.present)
        self.assertEqual(result.missing, ("Unhorsed",))

    def test_matching_is_case_insensitive(self) -> None:
        probe = rc.NamedRowsProbe(label="ConditionTemplate", names=("MOUNTED",))
        self.assertTrue(probe.resolve(frozenset({"mounted"})).present)


class TestCustomProbe(TestCase):
    def test_delegates_to_callable(self) -> None:
        probe = rc.CustomProbe(fn=lambda: rc.ProbeResult(present=False, detail="nope"))
        result = probe.resolve(None)
        self.assertFalse(result.present)
        self.assertEqual(result.detail, "nope")


class TestModelLabel(TestCase):
    """`model_label()` and `participates_in_name_batch()` on each probe kind.

    `collect_required_content` routes its batching grouping through these two
    methods rather than through `isinstance` + direct attribute access, so a
    regression in either would silently break batching with no other test
    catching it.
    """

    def test_named_rows_probe_reports_its_label_and_batches(self) -> None:
        probe = rc.NamedRowsProbe(label="ConditionTemplate", names=("Mounted",))
        self.assertEqual(probe.model_label(), "ConditionTemplate")
        self.assertTrue(probe.participates_in_name_batch())

    def test_any_row_probe_reports_its_label_but_does_not_batch(self) -> None:
        probe = rc.AnyRowProbe(label="LevelPowerConfig")
        self.assertEqual(probe.model_label(), "LevelPowerConfig")
        self.assertFalse(probe.participates_in_name_batch())

    def test_custom_probe_reports_no_label_and_does_not_batch(self) -> None:
        probe = rc.CustomProbe(fn=lambda: rc.ProbeResult(present=True))
        self.assertIsNone(probe.model_label())
        self.assertFalse(probe.participates_in_name_batch())


class DeclarationPatchMixin:
    @contextmanager
    def patch_declarations(self, deps):
        with mock.patch.object(rc, "_declarations", return_value=deps):
            yield


class TestCollector(DeclarationPatchMixin, TestCase):
    """The collector must batch per model, not per declaration."""

    @classmethod
    def setUpTestData(cls) -> None:
        ConditionTemplateFactory(name="Mounted")

    def test_snapshot_separates_tiers_and_presence(self) -> None:
        deps = (
            _dep(
                "present-required",
                rc.NamedRowsProbe(label="ConditionTemplate", names=("Mounted",)),
                rc.DependencyTier.REQUIRED,
            ),
            _dep(
                "missing-required",
                rc.NamedRowsProbe(label="ConditionTemplate", names=("Nonexistent",)),
                rc.DependencyTier.REQUIRED,
            ),
            _dep(
                "missing-tuning",
                rc.AnyRowProbe(label="LevelPowerConfig"),
                rc.DependencyTier.TUNING,
            ),
        )
        with self.patch_declarations(deps):
            snapshot = rc.collect_required_content()
        self.assertEqual(
            [r.dependency.key for r in snapshot.missing_required], ["missing-required"]
        )
        self.assertEqual(
            [r.dependency.key for r in snapshot.present_required], ["present-required"]
        )
        self.assertEqual([r.dependency.key for r in snapshot.missing_tuning], ["missing-tuning"])

    def test_named_probes_batch_to_one_query_per_model(self) -> None:
        deps = tuple(
            _dep(
                f"cond-{index}",
                rc.NamedRowsProbe(label="ConditionTemplate", names=(f"Name {index}",)),
                rc.DependencyTier.REQUIRED,
            )
            for index in range(6)
        )
        with self.patch_declarations(deps):
            # One SELECT for the single distinct model label, regardless of
            # how many declarations name it.
            with self.assertNumQueries(1):
                rc.collect_required_content()


class TestRealDeclarations(TestCase):
    """The shipped declaration table is well-formed and probes resolve."""

    def test_keys_are_unique(self) -> None:
        # build_registry raises on a duplicate key.
        registry = rc.build_registry(rc._declarations())
        self.assertEqual(len(registry), len(rc._declarations()))

    def test_every_declaration_is_populated(self) -> None:
        for dep in rc._declarations():
            with self.subTest(key=dep.key):
                self.assertTrue(dep.key)
                self.assertTrue(dep.label)
                self.assertTrue(dep.consumer)
                self.assertTrue(dep.consequence)
                self.assertIn(dep.tier, (rc.DependencyTier.REQUIRED, rc.DependencyTier.TUNING))

    def test_both_tiers_are_represented(self) -> None:
        tiers = {dep.tier for dep in rc._declarations()}
        self.assertEqual(tiers, {rc.DependencyTier.REQUIRED, rc.DependencyTier.TUNING})

    def test_collector_runs_against_the_real_table(self) -> None:
        snapshot = rc.collect_required_content()
        total = (
            len(snapshot.missing_required)
            + len(snapshot.present_required)
            + len(snapshot.missing_tuning)
            + len(snapshot.present_tuning)
        )
        self.assertEqual(total, len(rc._declarations()))


class TestSoulfrayStagePoolProbe(TestCase):
    """Both directions: a stage without a pool must flip the probe."""

    def test_missing_when_a_stage_has_no_pool(self) -> None:
        from world.conditions.factories import ConditionStageFactory
        from world.magic.audere import SOULFRAY_CONDITION_NAME

        template = ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME)
        ConditionStageFactory(condition=template, stage_order=1, consequence_pool=None)
        result = rc._probe_soulfray_stage_pools()
        self.assertFalse(result.present)

    def test_present_when_every_stage_has_a_pool(self) -> None:
        from actions.factories import ConsequencePoolFactory
        from world.conditions.factories import ConditionStageFactory
        from world.magic.audere import SOULFRAY_CONDITION_NAME

        template = ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME)
        ConditionStageFactory(
            condition=template, stage_order=1, consequence_pool=ConsequencePoolFactory()
        )
        result = rc._probe_soulfray_stage_pools()
        self.assertTrue(result.present)


class TestEscalationCurveProbe(TestCase):
    def test_missing_with_no_rows(self) -> None:
        self.assertFalse(rc._probe_escalation_curves().present)

    def test_present_when_a_row_has_a_default_curve(self) -> None:
        from world.combat.constants import StakesLevel
        from world.combat.factories import EscalationCurveFactory
        from world.combat.models import StakesEscalationModifier

        curve = EscalationCurveFactory()
        StakesEscalationModifier.objects.create(stakes_level=StakesLevel.LOCAL, default_curve=curve)
        result = rc._probe_escalation_curves()
        self.assertTrue(result.present)


class TestAudereMajoraThresholdsProbe(TestCase):
    """Both directions: any boundary level missing must flip the probe."""

    def test_missing_when_a_boundary_level_is_absent(self) -> None:
        from world.magic.factories import ensure_audere_majora_threshold

        ensure_audere_majora_threshold(boundary_level=5)
        ensure_audere_majora_threshold(boundary_level=10)
        ensure_audere_majora_threshold(boundary_level=15)
        # boundary_level=20 deliberately left absent.
        result = rc._probe_audere_majora_thresholds()
        self.assertFalse(result.present)
        self.assertIn("20", result.missing)

    def test_present_when_all_four_boundary_levels_exist(self) -> None:
        from world.magic.factories import ensure_audere_majora_threshold

        for level in (5, 10, 15, 20):
            ensure_audere_majora_threshold(boundary_level=level)
        result = rc._probe_audere_majora_thresholds()
        self.assertTrue(result.present)
        self.assertEqual(result.missing, ())


class TestCapabilityBridgesProbe(TestCase):
    """Patches build_capability_power_panel per the brief - no real corpus needed."""

    def test_missing_when_the_zero_bucket_is_non_empty(self) -> None:
        panel = mock.Mock(zero_bucket=["Some Capability"])
        with mock.patch(
            "web.admin.tuning.capability_power_analytics.build_capability_power_panel",
            return_value=panel,
        ):
            result = rc._probe_capability_bridges()
        self.assertFalse(result.present)

    def test_present_when_the_zero_bucket_is_empty(self) -> None:
        panel = mock.Mock(zero_bucket=[])
        with mock.patch(
            "web.admin.tuning.capability_power_analytics.build_capability_power_panel",
            return_value=panel,
        ):
            result = rc._probe_capability_bridges()
        self.assertTrue(result.present)


class TestTravelSpeedModifierTargetProbe(TestCase):
    """A row named right but filed under the wrong category must report missing."""

    def test_missing_when_the_category_is_wrong(self) -> None:
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory

        wrong_category = ModifierCategoryFactory(name="combat")
        ModifierTargetFactory(name="travel_speed", category=wrong_category)
        result = rc._probe_travel_speed_modifier_target()
        self.assertFalse(result.present)

    def test_present_when_the_category_matches(self) -> None:
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory

        travel_category = ModifierCategoryFactory(name="travel")
        ModifierTargetFactory(name="travel_speed", category=travel_category)
        result = rc._probe_travel_speed_modifier_target()
        self.assertTrue(result.present)


class TestGossipCheckTypeProbe(TestCase):
    """A Gossip CheckType filed under the wrong category must report missing."""

    def test_missing_when_the_category_is_wrong(self) -> None:
        from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
        from world.secrets.constants import GOSSIP_CHECK_TYPE_NAME

        wrong_category = CheckCategoryFactory(name="Combat")
        CheckTypeFactory(name=GOSSIP_CHECK_TYPE_NAME, category=wrong_category)
        result = rc._probe_gossip_check_type()
        self.assertFalse(result.present)

    def test_present_when_the_category_matches(self) -> None:
        from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
        from world.secrets.constants import GOSSIP_CHECK_TYPE_NAME

        social_category = CheckCategoryFactory(name="Social")
        CheckTypeFactory(name=GOSSIP_CHECK_TYPE_NAME, category=social_category)
        result = rc._probe_gossip_check_type()
        self.assertTrue(result.present)


class TestGossipSpecializationProbe(TestCase):
    """A Gossip Specialization filed under the wrong parent skill must report missing."""

    def test_missing_when_the_parent_skill_trait_is_wrong(self) -> None:
        from world.skills.factories import SkillFactory, SpecializationFactory

        wrong_skill = SkillFactory(trait__name="Deception")
        SpecializationFactory(name="Gossip", parent_skill=wrong_skill)
        result = rc._probe_gossip_specialization()
        self.assertFalse(result.present)

    def test_present_when_the_parent_skill_trait_matches(self) -> None:
        from world.skills.factories import SkillFactory, SpecializationFactory

        persuasion_skill = SkillFactory(trait__name="Persuasion")
        SpecializationFactory(name="Gossip", parent_skill=persuasion_skill)
        result = rc._probe_gossip_specialization()
        self.assertTrue(result.present)


class TestWillpowerStatTraitProbe(TestCase):
    """A willpower Trait of the wrong trait_type must report missing."""

    def test_missing_when_the_trait_type_is_wrong(self) -> None:
        from world.traits.factories import TraitFactory
        from world.traits.models import TraitType

        TraitFactory(name="willpower", trait_type=TraitType.SKILL)
        result = rc._probe_willpower_stat_trait()
        self.assertFalse(result.present)

    def test_present_when_the_trait_type_matches(self) -> None:
        from world.traits.factories import TraitFactory
        from world.traits.models import TraitType

        TraitFactory(name="willpower", trait_type=TraitType.STAT)
        result = rc._probe_willpower_stat_trait()
        self.assertTrue(result.present)


class TestHostileSocialConsentCategoryProbe(TestCase):
    """A row named 'Hostile' under the wrong key must report missing (key, not name)."""

    def test_missing_when_the_key_is_wrong(self) -> None:
        from world.consent.factories import SocialConsentCategoryFactory

        SocialConsentCategoryFactory(key="antagonism", name="Hostile")
        result = rc._probe_hostile_social_consent_category()
        self.assertFalse(result.present)

    def test_present_when_the_key_matches(self) -> None:
        from world.consent.factories import SocialConsentCategoryFactory

        SocialConsentCategoryFactory(key="hostile", name="Hostile")
        result = rc._probe_hostile_social_consent_category()
        self.assertTrue(result.present)


class TestRequiredContentFragmentView(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        from evennia.accounts.models import AccountDB

        cls.super = AccountDB.objects.create_superuser("rcroot", "rcroot@example.com", "pw-123456")
        cls.staff = AccountDB.objects.create_user("rcstaff", "rcs@example.com", "pw-123456")
        cls.staff.is_staff = True
        cls.staff.save()

    def test_anonymous_redirected(self) -> None:
        from django.urls import reverse

        resp = self.client.get(reverse("admin_ops_required_content"))
        self.assertEqual(resp.status_code, 302)

    def test_staff_non_superuser_forbidden(self) -> None:
        from django.urls import reverse

        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin_ops_required_content"))
        self.assertEqual(resp.status_code, 403)

    def test_superuser_gets_panel(self) -> None:
        from django.urls import reverse

        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_ops_required_content"))
        self.assertEqual(resp.status_code, 200)

    def test_ops_dashboard_includes_the_panel_section(self) -> None:
        from django.urls import reverse

        self.client.force_login(self.super)
        resp = self.client.get(reverse("admin_ops"))
        self.assertIn('id="panel-ops-required-content"', resp.content.decode())
