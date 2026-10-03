"""Tests for the required-content sentinel registry and collector (#3444)."""

from __future__ import annotations

from contextlib import contextmanager
from unittest import mock

from django.test import TestCase

from web.admin.tuning import required_content as rc
from world.conditions.factories import ConditionTemplateFactory
from world.game_clock.factories import GameClockFactory
from world.magic.constants import GiftKind


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


class TestDependencyAdminUrl(TestCase):
    """Each panel row links to the admin page where its rows are authored (#3831)."""

    @staticmethod
    def _row(probe: rc.ContentProbe, admin_model: str | None = None) -> rc.DependencyRow:
        dependency = rc.ContentDependency(
            key="linked",
            label="linked dependency",
            tier=rc.DependencyTier.TUNING,
            consumer="world/example.py:1 example()",
            consequence="Example breaks.",
            probe=probe,
            admin_model=admin_model,
        )
        return rc.DependencyRow(dependency=dependency, result=rc.ProbeResult(present=False))

    def test_links_the_probed_models_changelist(self) -> None:
        row = self._row(rc.AnyRowProbe(label="LevelPowerConfig"))
        self.assertEqual(row.admin_url, "/admin/arxii/levelpowerconfig/")

    def test_admin_model_names_the_page_for_a_custom_probe(self) -> None:
        probe = rc.CustomProbe(fn=lambda: rc.ProbeResult(present=True))
        row = self._row(probe, admin_model="LevelPowerConfig")
        self.assertEqual(row.admin_url, "/admin/arxii/levelpowerconfig/")

    def test_no_link_when_the_probe_names_no_model(self) -> None:
        row = self._row(rc.CustomProbe(fn=lambda: rc.ProbeResult(present=True)))
        self.assertIsNone(row.admin_url)

    def test_no_link_for_an_unknown_model(self) -> None:
        row = self._row(rc.AnyRowProbe(label="NoSuchModel"))
        self.assertIsNone(row.admin_url)


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

    def test_a_repointed_row_with_no_cmdset_is_still_reported(self) -> None:
        """The old hand repair (#3596) fixed the typeclass path and nothing else: the row
        passed this probe while having zero commands (#3812). Both symptoms are flagged,
        and the detail names the heal rather than the ``.update()`` that caused it."""
        from django.conf import settings
        from evennia.accounts.models import AccountDB

        dep = next(d for d in rc._declarations() if d.key == "typeclassed-accounts")
        AccountDB.objects.create_superuser("rc_repointed", "rcrep@example.com", "pw-123456")
        AccountDB.objects.filter(username="rc_repointed").update(
            db_typeclass_path=settings.BASE_ACCOUNT_TYPECLASS
        )
        AccountDB.flush_instance_cache()

        result = dep.probe.resolve(None)

        self.assertFalse(result.present)
        self.assertIn("rc_repointed", result.detail)
        self.assertIn("heal_account_setup", result.detail)
        self.assertNotIn(".update(", result.detail)

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

    def test_legend_level_calibration_is_a_required_dependency(self) -> None:
        """An empty calibration table 500s the Rite of Honors (#3480, #3466)."""
        from world.societies.factories import LegendLevelCalibrationFactory

        dep = next(d for d in rc._declarations() if d.key == "legend-level-calibration")
        self.assertEqual(dep.tier, rc.DependencyTier.REQUIRED)
        self.assertIsInstance(dep.probe, rc.AnyRowProbe)
        self.assertEqual(dep.probe.model_label(), "LegendLevelCalibration")
        self.assertFalse(dep.probe.resolve(None).present)
        LegendLevelCalibrationFactory()
        self.assertTrue(dep.probe.resolve(None).present)

    def test_active_beginning_without_upbringing_is_reported(self) -> None:
        """A Beginning with no active Upbringing strands a player in Lineage (#3617)."""
        from world.character_creation.factories import BeginningsFactory, OriginTemplateFactory

        lonely = BeginningsFactory(name="Lonely")
        key = "character_creation.beginnings_have_upbringing"
        dep = next(d for d in rc._declarations() if d.key == key)
        result = dep.probe.resolve(None)
        self.assertFalse(result.present)
        self.assertIn("Lonely", result.missing)

        OriginTemplateFactory(beginning=lonely)
        result = dep.probe.resolve(None)
        self.assertNotIn("Lonely", result.missing)

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
    """A stage counts as missing with no pool OR a pool that draws nothing (#4089)."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.conditions.factories import ConditionStageFactory
        from world.magic.audere import SOULFRAY_CONDITION_NAME

        cls.template = ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME, has_progression=True)
        cls.stage = ConditionStageFactory(
            condition=cls.template, stage_order=1, name="Fraying", severity_threshold=1
        )

    def test_missing_when_a_stage_has_no_pool(self) -> None:
        result = rc._probe_soulfray_stage_pools()
        self.assertFalse(result.present)
        self.assertEqual(result.missing, ("Fraying",))

    def test_missing_when_a_stages_pool_is_empty(self) -> None:
        from actions.factories import ConsequencePoolFactory

        self.stage.consequence_pool = ConsequencePoolFactory()
        self.stage.save(update_fields=["consequence_pool"])
        result = rc._probe_soulfray_stage_pools()
        self.assertFalse(result.present)
        self.assertIn("a pool with no consequences in it", result.detail)

    def test_missing_when_the_child_excludes_every_parent_row(self) -> None:
        from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory

        parent = ConsequencePoolFactory()
        entry = ConsequencePoolEntryFactory(pool=parent)
        child = ConsequencePoolFactory(parent=parent)
        ConsequencePoolEntryFactory(pool=child, consequence=entry.consequence, is_excluded=True)
        self.stage.consequence_pool = child
        self.stage.save(update_fields=["consequence_pool"])
        self.assertFalse(rc._probe_soulfray_stage_pools().present)

    def test_present_when_every_stage_draws_something(self) -> None:
        from actions.factories import ConsequencePoolEntryFactory

        entry = ConsequencePoolEntryFactory()
        self.stage.consequence_pool = entry.pool
        self.stage.save(update_fields=["consequence_pool"])
        self.assertTrue(rc._probe_soulfray_stage_pools().present)

    def test_missing_when_soulfray_has_no_stages(self) -> None:
        from world.conditions.models import ConditionStage

        ConditionStage.objects.filter(pk=self.stage.pk).delete()
        self.assertFalse(rc._probe_soulfray_stage_pools().present)


class TestSoulfrayDeathRiskProbe(TestCase):
    """Some Soulfray stage's effective pool holds a character_loss row (#4089)."""

    @classmethod
    def setUpTestData(cls) -> None:
        from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
        from world.conditions.factories import ConditionStageFactory
        from world.magic.audere import SOULFRAY_CONDITION_NAME

        template = ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME, has_progression=True)
        cls.parent = ConsequencePoolFactory(name="Soulfray - common")
        cls.pool = ConsequencePoolFactory(name="Soulfray - Unravelling", parent=cls.parent)
        ConsequencePoolEntryFactory(pool=cls.pool)
        ConditionStageFactory(
            condition=template,
            stage_order=5,
            name="Unravelling",
            severity_threshold=66,
            consequence_pool=cls.pool,
        )

    def test_missing_when_no_row_can_kill(self) -> None:
        result = rc._probe_soulfray_death_risk()
        self.assertFalse(result.present)
        self.assertIn("Can kill", result.detail)

    def test_present_when_a_stage_pool_holds_a_lethal_row(self) -> None:
        from actions.factories import ConsequencePoolEntryFactory
        from world.checks.factories import ConsequenceFactory

        ConsequencePoolEntryFactory(
            pool=self.pool, consequence=ConsequenceFactory(character_loss=True)
        )
        self.assertTrue(rc._probe_soulfray_death_risk().present)

    def test_present_when_the_lethal_row_comes_from_the_parent_pool(self) -> None:
        from actions.factories import ConsequencePoolEntryFactory
        from world.checks.factories import ConsequenceFactory

        ConsequencePoolEntryFactory(
            pool=self.parent, consequence=ConsequenceFactory(character_loss=True)
        )
        self.assertTrue(rc._probe_soulfray_death_risk().present)

    def test_declared_as_required(self) -> None:
        dependency = next(d for d in rc._declarations() if d.key == "soulfray-death-risk")
        self.assertEqual(dependency.tier, rc.DependencyTier.REQUIRED)
        self.assertEqual(dependency.label, "Some Soulfray stage can kill")


class TestSoulfrayRowsLinkToTheBuilder(TestCase):
    """Both Soulfray rows link into the Soulfray Stage Builder (#4089)."""

    @classmethod
    def setUpTestData(cls) -> None:
        from web.admin.tests.soulfray_ladder import build_ladder

        cls.ladder = build_ladder()

    @staticmethod
    def _row(key: str) -> rc.DependencyRow:
        dependency = next(d for d in rc._declarations() if d.key == key)
        return rc.DependencyRow(dependency=dependency, result=dependency.probe.resolve(None))

    def test_pools_row_opens_the_first_stage_missing_a_pool(self) -> None:
        from django.urls import reverse

        self.assertEqual(
            self._row("soulfray-stage-pools").admin_url,
            reverse("admin_soulfray_builder", args=[self.ladder.stages[0].pk]),
        )

    def test_death_risk_row_opens_the_builder(self) -> None:
        from django.urls import reverse

        self.assertEqual(
            self._row("soulfray-death-risk").admin_url, reverse("admin_soulfray_builder_index")
        )


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

    def test_the_present_summary_counts_both_tiers(self) -> None:
        """The summary once read "0 dependencies present" whatever was present: a
        filter chain cannot add two lengths in one expression."""
        from django.urls import reverse

        present = rc.CustomProbe(fn=lambda: rc.ProbeResult(present=True))
        required = self._dependency(present, "count-required")
        tuning = rc.ContentDependency(
            key="count-tuning",
            label="Tuning sentinel",
            tier=rc.DependencyTier.TUNING,
            consumer=self.CONSUMER,
            consequence=self.CONSEQUENCE,
            probe=present,
        )

        self.client.force_login(self.super)
        with self.patch_declarations((required, tuning)):
            resp = self.client.get(reverse("admin_ops_required_content"))

        body = " ".join(resp.content.decode().split())
        self.assertIn("2 dependencies present", body)


class TestTraditionStandardLinesProbes(TestCase):
    """Both standard-line tables (#3675): missing rows AND blank text both report.

    The tradition slate page's own GET no longer ``get_or_create``s these rows
    (#3675 demo-fidelity ruling - that write was a guard by another name), so
    this sentinel is the only thing that notices an entirely-empty database or
    a row an author left blank.
    """

    def test_missing_when_no_rows_exist(self) -> None:
        state_result = rc._probe_tradition_state_lines()
        self.assertFalse(state_result.present)
        self.assertEqual(
            set(state_result.missing), {"self_taught", "teachers_gone", "living_masters"}
        )

        schooling_result = rc._probe_schooling_lines()
        self.assertFalse(schooling_result.present)
        self.assertEqual(set(schooling_result.missing), {"0", "1", "2"})

    def test_blank_entry_line_or_name_reports_missing_too(self) -> None:
        from world.character_creation.constants import TraditionState
        from world.character_creation.factories import (
            SchoolingLineFactory,
            TraditionStateLineFactory,
        )

        for state in TraditionState.values:
            TraditionStateLineFactory(state=state, entry_line="")
        for rank in range(3):
            SchoolingLineFactory(rank=rank, name="")

        state_result = rc._probe_tradition_state_lines()
        self.assertFalse(state_result.present)
        self.assertEqual(
            set(state_result.missing), {"self_taught", "teachers_gone", "living_masters"}
        )

        schooling_result = rc._probe_schooling_lines()
        self.assertFalse(schooling_result.present)
        self.assertEqual(set(schooling_result.missing), {"0", "1", "2"})

    def test_present_when_every_row_exists_with_text(self) -> None:
        from world.character_creation.constants import TraditionState
        from world.character_creation.factories import (
            SchoolingLineFactory,
            TraditionStateLineFactory,
        )

        for state in TraditionState.values:
            TraditionStateLineFactory(state=state, entry_line=f"{state} line")
        for rank in range(3):
            SchoolingLineFactory(rank=rank, name=f"Schooling {rank}")

        self.assertTrue(rc._probe_tradition_state_lines().present)
        self.assertTrue(rc._probe_schooling_lines().present)

    def test_declared_as_required_dependencies(self) -> None:
        for key in (
            "character_creation.tradition_state_lines",
            "character_creation.tradition_schooling_lines",
        ):
            dep = next(d for d in rc._declarations() if d.key == key)
            self.assertEqual(dep.tier, rc.DependencyTier.REQUIRED)
            self.assertIsInstance(dep.probe, rc.CustomProbe)


class TestSavagedConditionDeclaration(TestCase):
    """`savaged-condition` (#3652): `_apply_savaged()` resolves via `get_by_name`,
    case-insensitively, so the probe matches that."""

    def test_missing_on_an_empty_database(self) -> None:
        probe = _probe_for("savaged-condition")
        result = probe.resolve(frozenset())
        self.assertFalse(result.present)

    def test_present_once_the_condition_exists(self) -> None:
        from world.companions.defeat_content import SAVAGED_CONDITION_NAME

        probe = _probe_for("savaged-condition")
        ConditionTemplateFactory(name=SAVAGED_CONDITION_NAME)
        result = probe.resolve(frozenset({SAVAGED_CONDITION_NAME}))
        self.assertTrue(result.present)


class TestCompanionDefeatPoolProbe(TestCase):
    """`companion-defeat-pool` (#3652): a `CustomProbe`, not a name-only probe,
    because `resolve_companion_defeat` treats an entry-less pool as absent
    (`if not consequences: return False`) - the exact false-green shape the
    `Surrounded` composite probe above exists to avoid."""

    def test_missing_on_an_empty_database(self) -> None:
        result = rc._probe_companion_defeat_pool()
        self.assertFalse(result.present)
        self.assertTrue(any("ConsequencePool" in m for m in result.missing))

    def test_missing_when_the_pool_exists_but_has_no_entries(self) -> None:
        """A bare pool row with no ConsequencePoolEntry is a silent no-op, not a
        working pool - a name-only probe would report this present."""
        from actions.factories import ConsequencePoolFactory
        from world.companions.factories_combat import COMPANION_DEFEAT_POOL_NAME

        ConsequencePoolFactory(name=COMPANION_DEFEAT_POOL_NAME)
        result = rc._probe_companion_defeat_pool()
        self.assertFalse(result.present)
        self.assertTrue(any("ConsequencePoolEntry" in m for m in result.missing))

    def test_missing_when_every_entry_is_excluded(self) -> None:
        from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
        from world.companions.factories_combat import COMPANION_DEFEAT_POOL_NAME

        pool = ConsequencePoolFactory(name=COMPANION_DEFEAT_POOL_NAME)
        ConsequencePoolEntryFactory(pool=pool, is_excluded=True)
        result = rc._probe_companion_defeat_pool()
        self.assertFalse(result.present)

    def test_present_once_the_seeded_pool_exists(self) -> None:
        from world.companions.factories_combat import create_companion_defeat_pool

        create_companion_defeat_pool()
        result = rc._probe_companion_defeat_pool()
        self.assertTrue(result.present)
        self.assertEqual(result.missing, ())


class TestRiskCalibrationsProbe(TestCase):
    """`risk-calibrations` (#3831): `risk` is unique on `RiskCalibration`, so
    partial coverage must report exactly the uncovered levels, not "present" for
    having at least one row - the same partial-coverage shape
    `TestEscalationCurveProbe` above guards against."""

    def test_missing_every_level_with_no_rows(self) -> None:
        from world.societies.constants import RenownRisk

        result = rc._probe_risk_calibrations()
        self.assertFalse(result.present)
        self.assertEqual(
            set(result.missing),
            {RenownRisk.LOW, RenownRisk.MODERATE, RenownRisk.HIGH, RenownRisk.EXTREME},
        )

    def test_present_when_all_four_levels_are_covered(self) -> None:
        from world.societies.constants import RenownRisk
        from world.stories.factories import RiskCalibrationFactory

        for risk in (RenownRisk.LOW, RenownRisk.MODERATE, RenownRisk.HIGH, RenownRisk.EXTREME):
            RiskCalibrationFactory(risk=risk)
        result = rc._probe_risk_calibrations()
        self.assertTrue(result.present)
        self.assertEqual(result.missing, ())

    def test_missing_reports_only_the_uncovered_level(self) -> None:
        from world.societies.constants import RenownRisk
        from world.stories.factories import RiskCalibrationFactory

        RiskCalibrationFactory(risk=RenownRisk.LOW)
        RiskCalibrationFactory(risk=RenownRisk.MODERATE)
        RiskCalibrationFactory(risk=RenownRisk.HIGH)
        # RenownRisk.EXTREME deliberately left uncovered.
        result = rc._probe_risk_calibrations()
        self.assertFalse(result.present)
        self.assertEqual(result.missing, (RenownRisk.EXTREME,))


class TestPathMajorGiftUltimatesProbe(TestCase):
    def test_major_gift_grant_without_ultimate_is_missing(self) -> None:
        from web.admin.tuning.required_content import _probe_path_major_gift_ultimates
        from world.magic.factories import GiftFactory, PathGiftGrantFactory

        grant = PathGiftGrantFactory(gift=GiftFactory(kind=GiftKind.MAJOR))
        result = _probe_path_major_gift_ultimates()
        self.assertFalse(result.present)
        self.assertIn(f"{grant.path.name} / {grant.gift.name}", result.missing)

    def test_minor_gift_grant_never_flagged(self) -> None:
        from web.admin.tuning.required_content import _probe_path_major_gift_ultimates
        from world.magic.factories import GiftFactory, PathGiftGrantFactory

        PathGiftGrantFactory(gift=GiftFactory(kind=GiftKind.MINOR))
        self.assertTrue(_probe_path_major_gift_ultimates().present)

    def test_stocked_grant_present(self) -> None:
        from web.admin.tuning.required_content import _probe_path_major_gift_ultimates
        from world.magic.factories import PathGiftGrantFactory, UltimateTechniqueFactory

        grant = PathGiftGrantFactory()
        grant.ultimate_techniques.add(UltimateTechniqueFactory(gift=grant.gift))
        self.assertTrue(_probe_path_major_gift_ultimates().present)


class TestAudereConditionShapeProbe(TestCase):
    """#4098 final review item 2: duration-shape + death_deferred, not just presence."""

    def _well_formed_template(self, name: str) -> rc.ContentProbe:
        from world.conditions.constants import DurationType
        from world.mechanics.factories import DeathDeferredPropertyFactory

        template = ConditionTemplateFactory(
            name=name, default_duration_type=DurationType.UNTIL_END_OF_COMBAT
        )
        template.properties.add(DeathDeferredPropertyFactory())
        return template

    def test_missing_both_templates_is_reported(self) -> None:
        from web.admin.tuning.required_content import _probe_audere_condition_shape
        from world.magic.audere import AUDERE_CONDITION_NAME, AUDERE_MAJORA_CONDITION_NAME

        result = _probe_audere_condition_shape()
        self.assertFalse(result.present)
        self.assertTrue(any(AUDERE_CONDITION_NAME in m for m in result.missing))
        self.assertTrue(any(AUDERE_MAJORA_CONDITION_NAME in m for m in result.missing))

    def test_round_limited_duration_is_reported(self) -> None:
        from web.admin.tuning.required_content import _probe_audere_condition_shape
        from world.conditions.constants import DurationType
        from world.magic.audere import AUDERE_CONDITION_NAME, AUDERE_MAJORA_CONDITION_NAME
        from world.mechanics.factories import DeathDeferredPropertyFactory

        for name in (AUDERE_CONDITION_NAME, AUDERE_MAJORA_CONDITION_NAME):
            template = ConditionTemplateFactory(
                name=name, default_duration_type=DurationType.ROUNDS
            )
            template.properties.add(DeathDeferredPropertyFactory())
        result = _probe_audere_condition_shape()
        self.assertFalse(result.present)
        self.assertTrue(any("round-limited" in m for m in result.missing))

    def test_missing_death_deferred_property_is_reported(self) -> None:
        from web.admin.tuning.required_content import _probe_audere_condition_shape
        from world.conditions.constants import DurationType
        from world.magic.audere import AUDERE_CONDITION_NAME, AUDERE_MAJORA_CONDITION_NAME

        for name in (AUDERE_CONDITION_NAME, AUDERE_MAJORA_CONDITION_NAME):
            ConditionTemplateFactory(name=name, default_duration_type=DurationType.PERMANENT)
        result = _probe_audere_condition_shape()
        self.assertFalse(result.present)
        self.assertTrue(any("death_deferred" in m for m in result.missing))

    def test_well_formed_templates_are_present(self) -> None:
        from web.admin.tuning.required_content import _probe_audere_condition_shape
        from world.magic.audere import AUDERE_CONDITION_NAME, AUDERE_MAJORA_CONDITION_NAME

        self._well_formed_template(AUDERE_CONDITION_NAME)
        self._well_formed_template(AUDERE_MAJORA_CONDITION_NAME)
        result = _probe_audere_condition_shape()
        self.assertTrue(result.present)
        self.assertEqual(result.missing, ())


class TestUltimatesHaveActionTemplateProbe(TestCase):
    """#4098 final review item 4: an ultimate with no action_template is pickable
    through Audere and never castable - a sentinel, not a runtime guard."""

    def test_ultimate_with_no_action_template_is_missing(self) -> None:
        from web.admin.tuning.required_content import _probe_ultimates_have_action_template
        from world.magic.factories import UltimateTechniqueFactory

        ultimate = UltimateTechniqueFactory(name="Test Castless Ultimate")
        result = _probe_ultimates_have_action_template()
        self.assertFalse(result.present)
        self.assertIn(ultimate.name, result.missing)

    def test_ordinary_technique_with_no_action_template_never_flagged(self) -> None:
        from web.admin.tuning.required_content import _probe_ultimates_have_action_template
        from world.magic.factories import TechniqueFactory

        TechniqueFactory(name="Test Ordinary No Template")
        result = _probe_ultimates_have_action_template()
        self.assertTrue(result.present)

    def test_ultimate_with_an_action_template_is_present(self) -> None:
        from actions.factories import ActionTemplateFactory
        from web.admin.tuning.required_content import _probe_ultimates_have_action_template
        from world.magic.factories import UltimateTechniqueFactory

        UltimateTechniqueFactory(
            name="Test Castable Ultimate", action_template=ActionTemplateFactory()
        )
        result = _probe_ultimates_have_action_template()
        self.assertTrue(result.present)
        self.assertEqual(result.missing, ())


class TestAudereUltimateCopyProbe(TestCase):
    def test_placeholder_copy_reported(self) -> None:
        from web.admin.tuning.required_content import _probe_audere_ultimate_copy
        from world.magic.factories import AudereThresholdFactory

        AudereThresholdFactory()
        result = _probe_audere_ultimate_copy()
        self.assertFalse(result.present)
        self.assertIn("sword_reveal_label", result.missing)

    def test_fully_authored_copy_is_present(self) -> None:
        from web.admin.tuning.required_content import _probe_audere_ultimate_copy
        from world.magic.factories import AudereThresholdFactory

        AudereThresholdFactory(
            reveal_framing_text="The threads of fate pull taut.",
            deferred_death_text="Death waits at the edge of the circle.",
            sword_reveal_label="The Sword",
            shield_reveal_label="The Shield",
            crown_reveal_label="The Crown",
        )
        result = _probe_audere_ultimate_copy()
        self.assertTrue(result.present)
        self.assertEqual(result.missing, ())

    def test_missing_singleton_is_present_not_crashed(self) -> None:
        """A missing `AudereThreshold` is the REQUIRED `audere-threshold` row's failure
        state (fix round 1) - this probe must not double-report it, and must not crash
        reading fields off a `None` singleton."""
        from web.admin.tuning.required_content import _probe_audere_ultimate_copy

        result = _probe_audere_ultimate_copy()
        self.assertTrue(result.present)


class TestPersonalizationRows(TestCase):
    """The three TUNING rows gating the Gift stage's personalization catalogs (#4099)."""

    def test_no_price_offered_in_creation_is_reported(self) -> None:
        from world.magic.factories import RestrictionFactory

        RestrictionFactory()  # a DESIGN restriction never counts
        self.assertFalse(_probe_for("creation-prices").resolve(None).present)

    def test_an_offered_price_is_present(self) -> None:
        from world.magic.factories import PriceFactory

        PriceFactory(creation_point_cost=1)
        self.assertTrue(_probe_for("creation-prices").resolve(None).present)

    def test_offered_flourish_and_form_are_present(self) -> None:
        from world.magic.factories import SignatureMotifBonusFactory, TechniqueVariantFactory

        SignatureMotifBonusFactory(creation_point_cost=2)
        TechniqueVariantFactory(unlock_thread_level=1, creation_point_cost=3)
        self.assertTrue(_probe_for("creation-flourishes").resolve(None).present)
        self.assertTrue(_probe_for("creation-forms").resolve(None).present)


class TestPriceComponentsActiveProbe(TestCase):
    """The TUNING row for prices whose consumed item can no longer be made (#4099)."""

    def test_no_component_is_present(self) -> None:
        self.assertTrue(_probe_for("price-components-active").resolve(None).present)

    def test_a_component_from_an_inactive_template_is_reported(self) -> None:
        from world.items.factories import ItemTemplateFactory
        from world.magic.factories import PriceFactory
        from world.magic.models import PriceComponentRequirement

        price = PriceFactory(name="Ash and bone")
        PriceComponentRequirement.objects.create(
            restriction=price, item_template=ItemTemplateFactory(name="Old bone", is_active=False)
        )
        PriceComponentRequirement.objects.create(
            restriction=price, item_template=ItemTemplateFactory(name="Fresh ash")
        )
        result = _probe_for("price-components-active").resolve(None)
        self.assertFalse(result.present)
        self.assertEqual(result.missing, ("Ash and bone: Old bone",))


class TestPersonalizationCopyProbe(TestCase):
    """The TUNING row for the Gift stage's make-it-yours panel copy (#4099)."""

    def test_seeded_placeholder_copy_is_reported(self) -> None:
        from web.admin.tuning.required_content import _probe_personalization_copy

        result = _probe_personalization_copy()
        self.assertFalse(result.present)
        self.assertIn("personalize_heading", result.missing)

    def test_authored_copy_is_present(self) -> None:
        from web.admin.tuning.required_content import _probe_personalization_copy
        from world.character_creation.constants import PERSONALIZATION_COPY_KEYS
        from world.character_creation.models import CGExplanation

        for key in PERSONALIZATION_COPY_KEYS:
            CGExplanation.objects.update_or_create(key=key, defaults={"text": f"Authored {key}"})
        self.assertTrue(_probe_personalization_copy().present)


class TestCharacterCreationGapProbes(TestCase):
    """The six probes the first roster PC stock-take asked for (#4104): each names the
    rows a realm still lacks so a staff member filling it never has to walk a draft
    into the gap to find it."""

    def test_beginnings_without_species_and_traditions_are_named(self) -> None:
        from world.character_creation.factories import (
            BeginningsFactory,
            BeginningTraditionFactory,
        )
        from world.species.factories import SpeciesFactory

        bare = BeginningsFactory(name="Nobility")
        full = BeginningsFactory(name="Caretaker")
        full.allowed_species.add(SpeciesFactory(name="Human"))
        BeginningTraditionFactory(beginning=full)
        BeginningsFactory(name="Retired", is_active=False)

        species = rc._beginnings_without_species()
        self.assertFalse(species.present)
        self.assertEqual(species.missing, ("Nobility",))
        traditions = rc._beginnings_without_traditions()
        self.assertFalse(traditions.present)
        self.assertEqual(traditions.missing, ("Nobility",))

        bare.allowed_species.add(SpeciesFactory(name="Elf"))
        BeginningTraditionFactory(beginning=bare)
        self.assertTrue(rc._beginnings_without_species().present)
        self.assertTrue(rc._beginnings_without_traditions().present)

    def test_realm_with_nobility_but_no_particles_is_named(self) -> None:
        from world.character_creation.factories import RealmFactory
        from world.roster.constants import NOBLE_KIND_NAME
        from world.roster.factories import FamilyKindFactory
        from world.societies.houses.models import NobiliaryParticle

        umbros = RealmFactory(name="Umbros", theme="umbros")
        # Arx has no nobility by ruling and is not in the canon table, so it never lists.
        RealmFactory(name="Arx", theme="arx")

        result = rc._realms_without_nobiliary_particles()
        self.assertFalse(result.present)
        self.assertEqual(result.missing, ("Umbros",))

        noble = FamilyKindFactory(name=NOBLE_KIND_NAME)
        NobiliaryParticle.objects.create(realm=umbros, kind=noble, particle="arn")
        self.assertTrue(rc._realms_without_nobiliary_particles().present)

    def test_feature_rows_must_all_exist_and_be_active(self) -> None:
        from world.distinctions.factories import DistinctionFactory
        from world.seeds.distinctive_features import FEATURE_ROW_NAMES

        self.assertEqual(set(rc._probe_feature_distinctions().missing), set(FEATURE_ROW_NAMES))
        for name in FEATURE_ROW_NAMES[:-1]:
            DistinctionFactory(name=name)
        DistinctionFactory(name=FEATURE_ROW_NAMES[-1], is_active=False)
        result = rc._probe_feature_distinctions()
        self.assertFalse(result.present)
        self.assertEqual(result.missing, (FEATURE_ROW_NAMES[-1],))

    def test_the_six_are_registered_with_admin_links(self) -> None:
        keys = {dep.key: dep for dep in rc.build_registry(rc._declarations())}
        for key in (
            "character_creation.beginnings_allow_species",
            "character_creation.beginnings_have_traditions",
            "societies.realm_nobiliary_particles",
            "character_creation.appearance_sections",
            "distinctions.feature_rows",
            "character_sheets.enemy_reasons",
        ):
            self.assertIn(key, keys)
            self.assertEqual(keys[key].tier, rc.DependencyTier.REQUIRED)
            self.assertTrue(keys[key].admin_model)
