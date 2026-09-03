"""Tests for the required-content sentinel registry and collector (#3444)."""

from __future__ import annotations

from contextlib import contextmanager
from unittest import mock

from django.test import TestCase

from web.admin.tuning import required_content as rc
from world.conditions.factories import ConditionTemplateFactory
from world.game_clock.factories import GameClockFactory


def _dep(key: str, probe: rc.ContentProbe, tier: rc.DependencyTier) -> rc.ContentDependency:
    return rc.ContentDependency(
        key=key,
        label=f"label for {key}",
        tier=tier,
        consumer="world/example.py:1 example()",
        consequence="Example breaks.",
        probe=probe,
    )


def _probe_for(key: str) -> rc.ContentProbe:
    """The real declaration's own probe, by key - so a probe test always
    exercises the exact object shipped in `_declarations()`, not a
    hand-copied duplicate of its filter values."""
    return next(dep.probe for dep in rc._declarations() if dep.key == key)


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
        result = probe.resolve(frozenset({"Mounted"}))
        self.assertTrue(result.present)
        self.assertEqual(result.missing, ())

    def test_missing_names_reported(self) -> None:
        probe = rc.NamedRowsProbe(label="ConditionTemplate", names=("Mounted", "Unhorsed"))
        result = probe.resolve(frozenset({"Mounted"}))
        self.assertFalse(result.present)
        self.assertEqual(result.missing, ("Unhorsed",))

    def test_default_matching_is_case_sensitive(self) -> None:
        """Every consumer except ConditionTemplate resolves case-sensitively
        (#3444 final review item 3) - a probe that matched case-insensitively
        by default would report present for a row those consumers still can't
        find."""
        probe = rc.NamedRowsProbe(label="CheckType", names=("Tax Collection",))
        self.assertFalse(probe.resolve(frozenset({"tax collection"})).present)
        self.assertTrue(probe.resolve(frozenset({"Tax Collection"})).present)

    def test_case_insensitive_opt_in_matches_regardless_of_case(self) -> None:
        probe = rc.NamedRowsProbe(
            label="ConditionTemplate", names=("MOUNTED",), case_insensitive=True
        )
        self.assertTrue(probe.resolve(frozenset({"Mounted"})).present)


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

    def test_filtered_row_probe_reports_its_label_but_does_not_batch(self) -> None:
        probe = rc.FilteredRowProbe(
            label="ModifierTarget", filters=(("name", "x"),), absent_detail="missing"
        )
        self.assertEqual(probe.model_label(), "ModifierTarget")
        self.assertFalse(probe.participates_in_name_batch())


class TestFilteredRowProbe(TestCase):
    def test_present_when_the_compound_filter_matches(self) -> None:
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory

        travel_category = ModifierCategoryFactory(name="travel")
        ModifierTargetFactory(name="travel_speed", category=travel_category)
        probe = rc.FilteredRowProbe(
            label="ModifierTarget",
            filters=(("name", "travel_speed"), ("category__name", "travel")),
            absent_detail="No ModifierTarget 'travel_speed' row under category 'travel'.",
        )
        result = probe.resolve(None)
        self.assertTrue(result.present)
        self.assertEqual(result.detail, "")

    def test_missing_reports_the_configured_absent_detail(self) -> None:
        probe = rc.FilteredRowProbe(
            label="ModifierTarget", filters=(("name", "nonexistent"),), absent_detail="gone"
        )
        result = probe.resolve(None)
        self.assertFalse(result.present)
        self.assertEqual(result.detail, "gone")


class DeclarationPatchMixin:
    @contextmanager
    def patch_declarations(self, deps: tuple[rc.ContentDependency, ...]):
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

    def test_label_names_the_dependency_not_its_model(self) -> None:
        """`label` is a human phrase, never equal to the probe's `model_label()`.

        The panel renders `dependency.label` as its only "Dependency" column
        (#3444 final review item 5) - a label that just repeats the model name
        is indistinguishable from every other declaration on the same model.
        """
        for dep in rc._declarations():
            with self.subTest(key=dep.key):
                self.assertNotEqual(dep.label, dep.probe.model_label())

    def test_base_model_account_rows_are_a_required_dependency(self) -> None:
        """An account whose typeclass path is the base AccountDB model 500s every persona-aware
        endpoint (Sentry ARX2-8). Django's ``create_superuser`` still makes them,
        so the ops panel has to say so rather than let the next one surface as a
        Sentry issue."""
        from evennia.accounts.models import AccountDB

        dep = next(d for d in rc._declarations() if d.key == "typeclassed-accounts")
        self.assertEqual(dep.tier, rc.DependencyTier.REQUIRED)
        self.assertTrue(dep.probe.resolve(None).present)
        AccountDB.objects.create_superuser("rc_base_root", "rcbase@example.com", "pw-123456")
        result = dep.probe.resolve(None)
        self.assertFalse(result.present)
        self.assertIn("rc_base_root", result.detail)

    def test_mfa_secrets_key_probe_reports_a_key_that_cannot_decrypt(self) -> None:
        """A rotated-without-re-encrypt key locks every 2FA user out (#3591, ADR-0267)."""
        from allauth.mfa.models import Authenticator
        from cryptography.fernet import Fernet
        from django.test import override_settings

        from evennia_extensions.factories import AccountFactory
        from evennia_extensions.mfa_adapter import ArxMFAAdapter

        dep = next(d for d in rc._declarations() if d.key == "mfa-secrets-key")
        self.assertEqual(dep.tier, rc.DependencyTier.REQUIRED)
        # No rows yet: a parseable key is enough.
        self.assertTrue(dep.probe.resolve(None).present)
        account = AccountFactory(username="rc_mfa_user")
        Authenticator.objects.create(
            user=account,
            type=Authenticator.Type.TOTP,
            data={"secret": ArxMFAAdapter().encrypt("JBSWY3DPEHPK3PXP")},
        )
        self.assertTrue(dep.probe.resolve(None).present)
        with override_settings(MFA_SECRETS_KEY=Fernet.generate_key().decode()):
            result = dep.probe.resolve(None)
        self.assertFalse(result.present)
        self.assertIn("MFA_SECRETS_KEY", result.detail)
        with override_settings(MFA_SECRETS_KEY="not-a-key"):
            self.assertFalse(dep.probe.resolve(None).present)

    def test_game_clock_singleton_is_a_required_dependency(self) -> None:
        """An unset clock 503s `GET /api/clock/` and blanks every IC-date reader.

        Seen on play.arx2.com 2026-09-02: the Hall's Time plate fell back to
        "frozen" and nothing on the ops dashboard said why.
        """
        dep = next(d for d in rc._declarations() if d.key == "game-clock")
        self.assertEqual(dep.tier, rc.DependencyTier.REQUIRED)
        self.assertIsInstance(dep.probe, rc.AnyRowProbe)
        self.assertEqual(dep.probe.model_label(), "GameClock")
        # Break the invariant and watch the probe say so, then seed and watch it clear.
        self.assertFalse(dep.probe.resolve(None).present)
        GameClockFactory()
        self.assertTrue(dep.probe.resolve(None).present)

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


class TestSurroundedConditionBundleProbe(TestCase):
    """All three rows are required - a name-only check on the template alone
    is the exact false green #3444 final review item 2 flagged."""

    def test_missing_when_only_the_template_exists(self) -> None:
        from world.conditions.constants import SURROUNDED_CONDITION_NAME

        ConditionTemplateFactory(name=SURROUNDED_CONDITION_NAME)
        result = rc._probe_surrounded_condition_bundle()
        self.assertFalse(result.present)
        self.assertTrue(any("ConsequencePool" in m for m in result.missing))
        self.assertTrue(any("ConditionStage" in m for m in result.missing))

    def test_missing_when_the_pool_is_absent(self) -> None:
        from world.conditions.constants import SURROUNDED_CONDITION_NAME
        from world.conditions.factories import ConditionStageFactory

        template = ConditionTemplateFactory(name=SURROUNDED_CONDITION_NAME)
        ConditionStageFactory(condition=template, stage_order=1)
        result = rc._probe_surrounded_condition_bundle()
        self.assertFalse(result.present)
        self.assertTrue(any("ConsequencePool" in m for m in result.missing))

    def test_missing_when_the_entry_stage_is_absent(self) -> None:
        from actions.factories import ConsequencePoolFactory
        from world.conditions.constants import SURROUNDED_CONDITION_NAME
        from world.vitals.constants import POOL_SURROUNDED_ENTRY

        ConditionTemplateFactory(name=SURROUNDED_CONDITION_NAME)
        ConsequencePoolFactory(name=POOL_SURROUNDED_ENTRY)
        result = rc._probe_surrounded_condition_bundle()
        self.assertFalse(result.present)
        self.assertTrue(any("ConditionStage" in m for m in result.missing))

    def test_missing_when_the_pool_name_is_wrong_case(self) -> None:
        """The call site compares `p.name == POOL_SURROUNDED_ENTRY` case-
        sensitively - a differently-cased pool name is a real miss, not a
        false red."""
        from actions.factories import ConsequencePoolFactory
        from world.conditions.constants import SURROUNDED_CONDITION_NAME
        from world.conditions.factories import ConditionStageFactory
        from world.vitals.constants import POOL_SURROUNDED_ENTRY

        template = ConditionTemplateFactory(name=SURROUNDED_CONDITION_NAME)
        ConditionStageFactory(condition=template, stage_order=1)
        ConsequencePoolFactory(name=POOL_SURROUNDED_ENTRY.title())
        result = rc._probe_surrounded_condition_bundle()
        self.assertFalse(result.present)

    def test_present_when_all_three_rows_exist(self) -> None:
        from actions.factories import ConsequencePoolFactory
        from world.conditions.constants import SURROUNDED_CONDITION_NAME
        from world.conditions.factories import ConditionStageFactory
        from world.vitals.constants import POOL_SURROUNDED_ENTRY

        template = ConditionTemplateFactory(name=SURROUNDED_CONDITION_NAME)
        ConditionStageFactory(condition=template, stage_order=1)
        ConsequencePoolFactory(name=POOL_SURROUNDED_ENTRY)
        result = rc._probe_surrounded_condition_bundle()
        self.assertTrue(result.present)
        self.assertEqual(result.missing, ())


class TestEscalationCurveProbe(TestCase):
    def test_missing_with_no_rows(self) -> None:
        self.assertFalse(rc._probe_escalation_curves().present)

    def test_missing_when_only_one_of_five_levels_is_covered(self) -> None:
        """The partial-coverage case: this is the direction #3444 final review
        item 1 flagged as a false green - one covered stakes level must not
        report present for the other four."""
        from world.combat.constants import StakesLevel
        from world.combat.factories import EscalationCurveFactory
        from world.combat.models import StakesEscalationModifier

        curve = EscalationCurveFactory()
        StakesEscalationModifier.objects.create(stakes_level=StakesLevel.LOCAL, default_curve=curve)
        result = rc._probe_escalation_curves()
        self.assertFalse(result.present)
        self.assertIn(StakesLevel.WORLD, result.missing)
        self.assertNotIn(StakesLevel.LOCAL, result.missing)

    def test_present_when_every_level_has_a_default_curve(self) -> None:
        from world.combat.constants import StakesLevel
        from world.combat.factories import EscalationCurveFactory
        from world.combat.models import StakesEscalationModifier

        for level in StakesLevel.values:
            StakesEscalationModifier.objects.create(
                stakes_level=level, default_curve=EscalationCurveFactory()
            )
        result = rc._probe_escalation_curves()
        self.assertTrue(result.present)
        self.assertEqual(result.missing, ())


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


class TestEncounterOutcomeMappingsProbe(TestCase):
    """Every EncounterOutcome x RiskLevel pair must have a mapping row (#3559, #3565).

    VICTORY/DEFEAT grade a story beat; FLED/ABANDONED grade a scenario
    ENCOUNTER option's route instead (#3565) - the probe covers all four
    values either way.
    """

    def test_missing_when_one_pair_is_absent(self) -> None:
        from world.combat.constants import EncounterOutcome, RiskLevel
        from world.combat.models import EncounterOutcomeMapping
        from world.traits.models import CheckOutcome

        tier = CheckOutcome.objects.create(name="Missing Pair Tier", success_level=1)
        for outcome in EncounterOutcome.values:
            for risk in RiskLevel.values:
                if outcome == EncounterOutcome.DEFEAT and risk == RiskLevel.LETHAL:
                    continue  # deliberately left absent
                EncounterOutcomeMapping.objects.create(
                    outcome=outcome, risk_level=risk, check_outcome=tier
                )
        result = rc._probe_encounter_outcome_mappings()
        self.assertFalse(result.present)
        self.assertIn("defeat/lethal", result.missing)

    def test_present_when_every_pair_is_covered(self) -> None:
        from world.combat.constants import EncounterOutcome, RiskLevel
        from world.combat.models import EncounterOutcomeMapping
        from world.traits.models import CheckOutcome

        tier = CheckOutcome.objects.create(name="Complete Pair Tier", success_level=1)
        for outcome in EncounterOutcome.values:
            for risk in RiskLevel.values:
                EncounterOutcomeMapping.objects.create(
                    outcome=outcome, risk_level=risk, check_outcome=tier
                )
        result = rc._probe_encounter_outcome_mappings()
        self.assertTrue(result.present)
        self.assertEqual(result.missing, ())


class TestBattleOutcomeMappingsProbe(TestCase):
    """Every BattleOutcome except UNRESOLVED must have a mapping row (#3559)."""

    def test_missing_when_one_outcome_is_absent(self) -> None:
        from world.battles.constants import BattleOutcome
        from world.battles.models import BattleOutcomeMapping
        from world.traits.models import CheckOutcome

        tier = CheckOutcome.objects.create(name="Missing Outcome Tier", success_level=1)
        for outcome in BattleOutcome.values:
            if outcome in (BattleOutcome.UNRESOLVED, BattleOutcome.DEFENDER_DECISIVE):
                continue  # UNRESOLVED is never graded; DEFENDER_DECISIVE deliberately absent
            BattleOutcomeMapping.objects.create(outcome=outcome, check_outcome=tier)
        result = rc._probe_battle_outcome_mappings()
        self.assertFalse(result.present)
        self.assertIn(BattleOutcome.DEFENDER_DECISIVE, result.missing)

    def test_present_when_every_resolved_outcome_is_covered(self) -> None:
        from world.battles.constants import BattleOutcome
        from world.battles.models import BattleOutcomeMapping
        from world.traits.models import CheckOutcome

        tier = CheckOutcome.objects.create(name="Complete Outcome Tier", success_level=1)
        for outcome in BattleOutcome.values:
            if outcome == BattleOutcome.UNRESOLVED:
                continue
            BattleOutcomeMapping.objects.create(outcome=outcome, check_outcome=tier)
        result = rc._probe_battle_outcome_mappings()
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
        result = _probe_for("travel-speed-modifier-target").resolve(None)
        self.assertFalse(result.present)

    def test_present_when_the_category_matches(self) -> None:
        from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory

        travel_category = ModifierCategoryFactory(name="travel")
        ModifierTargetFactory(name="travel_speed", category=travel_category)
        result = _probe_for("travel-speed-modifier-target").resolve(None)
        self.assertTrue(result.present)


class TestGossipCheckTypeProbe(TestCase):
    """A Gossip CheckType filed under the wrong category must report missing."""

    def test_missing_when_the_category_is_wrong(self) -> None:
        from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
        from world.secrets.constants import GOSSIP_CHECK_TYPE_NAME

        wrong_category = CheckCategoryFactory(name="Combat")
        CheckTypeFactory(name=GOSSIP_CHECK_TYPE_NAME, category=wrong_category)
        result = _probe_for("gossip-check-type").resolve(None)
        self.assertFalse(result.present)

    def test_present_when_the_category_matches(self) -> None:
        from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
        from world.secrets.constants import GOSSIP_CHECK_TYPE_NAME

        social_category = CheckCategoryFactory(name="Social")
        CheckTypeFactory(name=GOSSIP_CHECK_TYPE_NAME, category=social_category)
        result = _probe_for("gossip-check-type").resolve(None)
        self.assertTrue(result.present)


class TestGossipSpecializationProbe(TestCase):
    """A Gossip Specialization filed under the wrong parent skill must report missing."""

    def test_missing_when_the_parent_skill_trait_is_wrong(self) -> None:
        from world.skills.factories import SkillFactory, SpecializationFactory

        wrong_skill = SkillFactory(trait__name="Deception")
        SpecializationFactory(name="Gossip", parent_skill=wrong_skill)
        result = _probe_for("gossip-specialization").resolve(None)
        self.assertFalse(result.present)

    def test_present_when_the_parent_skill_trait_matches(self) -> None:
        from world.skills.factories import SkillFactory, SpecializationFactory

        persuasion_skill = SkillFactory(trait__name="Persuasion")
        SpecializationFactory(name="Gossip", parent_skill=persuasion_skill)
        result = _probe_for("gossip-specialization").resolve(None)
        self.assertTrue(result.present)


class TestWillpowerStatTraitProbe(TestCase):
    """A willpower Trait of the wrong trait_type must report missing."""

    def test_missing_when_the_trait_type_is_wrong(self) -> None:
        from world.traits.factories import TraitFactory
        from world.traits.models import TraitType

        TraitFactory(name="willpower", trait_type=TraitType.SKILL)
        result = _probe_for("willpower-stat-trait").resolve(None)
        self.assertFalse(result.present)

    def test_present_when_the_trait_type_matches(self) -> None:
        from world.traits.factories import TraitFactory
        from world.traits.models import TraitType

        TraitFactory(name="willpower", trait_type=TraitType.STAT)
        result = _probe_for("willpower-stat-trait").resolve(None)
        self.assertTrue(result.present)


class TestHostileSocialConsentCategoryProbe(TestCase):
    """A row named 'Hostile' under the wrong key must report missing (key, not name)."""

    def test_missing_when_the_key_is_wrong(self) -> None:
        from world.consent.factories import SocialConsentCategoryFactory

        SocialConsentCategoryFactory(key="antagonism", name="Hostile")
        result = _probe_for("hostile-social-consent-category").resolve(None)
        self.assertFalse(result.present)

    def test_present_when_the_key_matches(self) -> None:
        from world.consent.factories import SocialConsentCategoryFactory

        SocialConsentCategoryFactory(key="hostile", name="Hostile")
        result = _probe_for("hostile-social-consent-category").resolve(None)
        self.assertTrue(result.present)

    def test_present_when_the_key_differs_only_by_case(self) -> None:
        """`get_by_natural_key` casefolds text natural-key components
        (`core/natural_keys.py`) - an exact `key="hostile"` filter would be a
        false RED for a row the game's own lookup resolves fine (#3444 final
        review item 3)."""
        from world.consent.factories import SocialConsentCategoryFactory

        SocialConsentCategoryFactory(key="Hostile", name="Hostile")
        result = _probe_for("hostile-social-consent-category").resolve(None)
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


class TestRequiredContentPanelRendersDependencyDetail(DeclarationPatchMixin, TestCase):
    """The panel must render consequence/consumer/missing text, not just a label.

    A test that only checks the label would pass against a template that
    dropped every other column - see the delete-the-column experiment noted
    in the Task 3 fix report for #3444.
    """

    LABEL = "Distinctive Sentinel Label Zyzzyva"
    CONSUMER = "world/example_detail.py:99 distinctive_consumer_fn()"
    CONSEQUENCE = "Distinctive consequence text: the sentinel test breaks quietly."

    @classmethod
    def setUpTestData(cls) -> None:
        from evennia.accounts.models import AccountDB

        cls.super = AccountDB.objects.create_superuser(
            "rcdetailroot", "rcdetail@example.com", "pw-123456"
        )

    def _dependency(self, probe: rc.ContentProbe, key: str) -> rc.ContentDependency:
        return rc.ContentDependency(
            key=key,
            label=self.LABEL,
            tier=rc.DependencyTier.REQUIRED,
            consumer=self.CONSUMER,
            consequence=self.CONSEQUENCE,
            probe=probe,
        )

    def test_missing_dependency_detail_renders_in_the_panel(self) -> None:
        from django.urls import reverse

        probe = rc.CustomProbe(
            fn=lambda: rc.ProbeResult(
                present=False,
                missing=("Widget-Alpha",),
                detail="Widget-Alpha row is absent from this database.",
            )
        )
        dep = self._dependency(probe, "detail-render-missing")

        self.client.force_login(self.super)
        with self.patch_declarations((dep,)):
            resp = self.client.get(reverse("admin_ops_required_content"))

        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn(self.LABEL, body)
        self.assertIn(self.CONSUMER, body)
        self.assertIn(self.CONSEQUENCE, body)
        self.assertIn("Widget-Alpha", body)
        self.assertIn("Widget-Alpha row is absent from this database.", body)

    def test_all_present_renders_the_nothing_missing_state(self) -> None:
        from django.urls import reverse

        probe = rc.CustomProbe(fn=lambda: rc.ProbeResult(present=True))
        dep = self._dependency(probe, "detail-render-present")

        self.client.force_login(self.super)
        with self.patch_declarations((dep,)):
            resp = self.client.get(reverse("admin_ops_required_content"))

        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn(
            "Nothing missing. Every required content dependency resolved against this database.",
            body,
        )
