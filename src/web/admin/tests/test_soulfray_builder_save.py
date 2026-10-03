"""The Soulfray Stage Builder save: one POST writes the whole stage (#4089)."""

from __future__ import annotations

from unittest import mock

from django.urls import reverse

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from actions.models import ConsequencePool, ConsequencePoolEntry
from evennia_extensions.models import PlayerData
from web.admin.authoring.credit import stamp_reviewed
from web.admin.soulfray_builder.forms import (
    TABLE_CHANGED_ERROR,
    BaseEffectFormSet,
    stage_pool_choices,
)
from web.admin.soulfray_builder.save import NEW_POOL_NAME_REQUIRED
from web.admin.tests.soulfray_ladder import (
    SoulfrayBuilderTestCase,
    form_values,
    make_superuser,
    shared_pool,
    stock,
)
from web.admin.tuning import required_content as rc
from world.checks.constants import EffectType
from world.checks.factories import (
    CheckTypeFactory,
    ConsequenceEffectFactory,
    ConsequenceFactory,
)
from world.checks.models import Consequence, ConsequenceEffect
from world.conditions.factories import (
    ConditionCheckModifierFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import ConditionCheckModifier, ConditionStage, ConditionStageOnEntry
from world.contributors.factories import ContentContributorFactory
from world.magic.factories import SoulfrayConfigFactory, TechniqueFactory
from world.mechanics.factories import PropertyFactory


class SaveTestCase(SoulfrayBuilderTestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.writer = ContentContributorFactory(name="Soulfray Saver")
        PlayerData.objects.create(account=cls.author, contributor=cls.writer)
        cls.unlinked = make_superuser("sfsaverunlinked")
        cls.config = SoulfrayConfigFactory(
            resilience_check_type=CheckTypeFactory(name="Magical Endurance")
        )
        cls.common = shared_pool(cls.ladder, ("Partial Success", "Success"))
        cls.fraying = cls.ladder.stage("Fraying")
        cls.tearing = cls.ladder.stage("Tearing")
        cls.fraying_pool = stock(
            cls.fraying, cls.ladder, tiers=("Critical Failure", "Failure"), parent=cls.common
        )
        cls.ripping = cls.ladder.stage("Ripping")
        cls.ripping_pool = stock(cls.ripping, cls.ladder, tiers=("Failure",))
        cls.fraying_failure = Consequence.objects.get(label="Fraying Failure")
        cls.shaken = ConditionTemplateFactory(name="Shaken")
        ConsequenceEffectFactory(
            consequence=cls.fraying_failure,
            effect_type=EffectType.APPLY_CONDITION,
            condition_template=cls.shaken,
            condition_severity=1,
        )
        cls.loose = ConsequencePoolFactory(name="Loose shared pool")
        cls.penalty = ConditionCheckModifierFactory(
            condition=None,
            stage=cls.ripping,
            check_type=cls.config.resilience_check_type,
            modifier_value=-3,
        )
        cls.blocks = PropertyFactory(name="blocks_anima_regen")
        cls.numb = ConditionStageFactory(
            condition=ConditionTemplateFactory(name="Poison test", has_progression=True),
            stage_order=1,
            name="Numb",
        )

    def _url(self, stage) -> str:
        return reverse("admin_soulfray_builder", args=[stage.pk])

    def _values(self, stage, query: str = "") -> dict[str, list[str]]:
        self.client.force_login(self.author)
        resp = self.client.get(self._url(stage) + query)
        self.assertEqual(resp.status_code, 200)
        return form_values(resp.content.decode())

    def _post(self, stage, data, user=None):
        self.client.force_login(user or self.author)
        return self.client.post(self._url(stage), data)

    @staticmethod
    def _add_row(data: dict[str, list[str]], **fields: object) -> int:
        index = int(data["rows-TOTAL_FORMS"][0])
        data["rows-TOTAL_FORMS"] = [str(index + 1)]
        for name, value in {"consequence": "", "copy_of": "", "weight": "1", **fields}.items():
            data[f"rows-{index}-{name}"] = [str(value)]
        return index

    @staticmethod
    def _add_new_row_effects(
        data: dict[str, list[str]], index: int, effects: list[dict[str, object]]
    ) -> None:
        """The ``new<index>`` effect formset the page's "Add an effect" posts."""
        prefix = f"new{index}"
        data[f"{prefix}-TOTAL_FORMS"] = [str(len(effects))]
        data[f"{prefix}-INITIAL_FORMS"] = ["0"]
        for number, effect in enumerate(effects):
            fields = {"id": "", "target": "self", "execution_order": "1", **effect}
            for name, value in fields.items():
                data[f"{prefix}-{number}-{name}"] = [str(value)]

    @staticmethod
    def _row_index(data: dict[str, list[str]], label: str) -> int:
        """The row form index of the table row labelled ``label``. Matched on its
        posted consequence id: a shared row renders its label as text, not an input."""
        labelled = Consequence.objects.filter(label=label).values_list("pk", flat=True)
        pks = {str(pk) for pk in labelled}
        key = next(k for k, v in data.items() if k.endswith("-consequence") and set(v) & pks)
        return int(key.split("-")[1])


class OneSaveWritesTheStageTest(SaveTestCase):
    def test_one_save_writes_stage_penalty_pool_rows_effects_and_credit(self) -> None:
        data = self._values(self.tearing)
        data["stage-description"] = ["PLACEHOLDER warning"]
        data["stage-properties"] = [str(self.blocks.pk)]
        data["onentry-0-condition"] = [str(self.shaken.pk)]
        data["onentry-0-severity"] = ["2"]
        data["penalty-modifier_value"] = ["-5"]
        data["pool-pool"] = [""]
        data["pool-new_name"] = ["Soulfray - Tearing"]
        data["pool-parent"] = [str(self.common.pk)]
        index = self._add_row(
            data,
            outcome_tier=self.ladder.outcomes["Critical Failure"].pk,
            label="PLACEHOLDER backlash wound",
            weight=2,
            theater="on",
        )
        self._add_new_row_effects(
            data,
            index,
            [
                {
                    "effect_type": EffectType.APPLY_CONDITION,
                    "condition_template": self.shaken.pk,
                    "condition_severity": 2,
                },
                {
                    "effect_type": EffectType.ADD_PROPERTY,
                    "property": self.blocks.pk,
                    "execution_order": 2,
                },
            ],
        )
        resp = self._post(self.tearing, data)
        self.assertEqual(resp.status_code, 302)
        stage = ConditionStage.objects.get(pk=self.tearing.pk)
        pool = ConsequencePool.objects.get(pk=stage.consequence_pool_id)
        self.assertEqual((pool.name, pool.parent_id), ("Soulfray - Tearing", self.common.pk))
        self.assertEqual(stage.description, "PLACEHOLDER warning")
        self.assertEqual(list(stage.properties.all()), [self.blocks])
        self.assertEqual(ConditionStageOnEntry.objects.get(stage=stage).severity, 2)
        modifier = ConditionCheckModifier.objects.get(
            stage=stage, check_type=self.config.resilience_check_type
        )
        self.assertEqual(modifier.modifier_value, -5)
        row = Consequence.objects.get(label="PLACEHOLDER backlash wound")
        self.assertEqual((row.weight, row.theater, row.character_loss), (2, True, False))
        self.assertTrue(ConsequencePoolEntry.objects.filter(pool=pool, consequence=row).exists())
        effects = list(
            ConsequenceEffect.objects.filter(consequence=row).order_by("execution_order")
        )
        self.assertEqual(
            [(e.effect_type, e.condition_template_id, e.property_id) for e in effects],
            [
                (EffectType.APPLY_CONDITION, self.shaken.pk, None),
                (EffectType.ADD_PROPERTY, None, self.blocks.pk),
            ],
        )
        for credited in (stage, pool, row, *effects):
            self.assertEqual(credited.written_by, self.writer)

    def test_page_and_panel_after_save_show_the_new_state(self) -> None:
        data = self._values(self.tearing)
        data["pool-parent"] = [str(self.common.pk)]
        self._add_row(
            data, outcome_tier=self.ladder.outcomes["Failure"].pk, label="PLACEHOLDER slip"
        )
        self.assertEqual(self._post(self.tearing, data).status_code, 302)
        body = self.client.get(self._url(self.tearing)).content.decode()
        self.assertIn("3 consequences reachable here", body)
        self.assertNotIn("Tearing", rc._probe_soulfray_stage_pools().missing)

    def test_save_next_opens_the_next_stage(self) -> None:
        data = self._values(self.tearing)
        data["save_next"] = ["Save and open Ripping"]
        resp = self._post(self.tearing, data)
        self.assertEqual(resp["Location"], self._url(self.ladder.stage("Ripping")))


class RowEditsTest(SaveTestCase):
    def test_reweight_and_drop_shared_rows_write_child_entries(self) -> None:
        data = self._values(self.fraying)
        data[f"rows-{self._row_index(data, 'common Success')}-weight"] = ["5"]
        data[f"rows-{self._row_index(data, 'common Partial Success')}-remove"] = ["on"]
        self.assertEqual(self._post(self.fraying, data).status_code, 302)
        success = Consequence.objects.get(label="common Success")
        partial = Consequence.objects.get(label="common Partial Success")
        reweight = ConsequencePoolEntry.objects.get(pool=self.fraying_pool, consequence=success)
        self.assertEqual((reweight.weight_override, reweight.is_excluded), (5, False))
        drop = ConsequencePoolEntry.objects.get(pool=self.fraying_pool, consequence=partial)
        self.assertTrue(drop.is_excluded)

    def test_removing_an_own_row_keeps_the_consequence(self) -> None:
        data = self._values(self.fraying)
        data[f"rows-{self._row_index(data, 'Fraying Critical Failure')}-remove"] = ["on"]
        self.assertEqual(self._post(self.fraying, data).status_code, 302)
        consequence = Consequence.objects.get(label="Fraying Critical Failure")
        self.assertFalse(
            ConsequencePoolEntry.objects.filter(
                pool=self.fraying_pool, consequence=consequence
            ).exists()
        )

    def test_effect_added_on_an_existing_row_is_saved_and_credited(self) -> None:
        data = self._values(self.fraying)
        prefix = f"e{self.fraying_failure.pk}"
        index = int(data[f"{prefix}-TOTAL_FORMS"][0])
        data[f"{prefix}-TOTAL_FORMS"] = [str(index + 1)]
        data.update(
            {
                f"{prefix}-{index}-id": [""],
                f"{prefix}-{index}-consequence": [str(self.fraying_failure.pk)],
                f"{prefix}-{index}-effect_type": [EffectType.APPLY_CONDITION],
                f"{prefix}-{index}-target": ["self"],
                f"{prefix}-{index}-execution_order": ["1"],
                f"{prefix}-{index}-condition_template": [str(self.shaken.pk)],
                f"{prefix}-{index}-condition_severity": ["3"],
            }
        )
        self.assertEqual(self._post(self.fraying, data).status_code, 302)
        effect = ConsequenceEffect.objects.get(
            consequence=self.fraying_failure, condition_severity=3
        )
        self.assertEqual(effect.written_by, self.writer)

    def test_untouched_added_row_is_ignored(self) -> None:
        before = Consequence.objects.count()
        data = self._values(self.fraying)
        self._add_row(data)
        self.assertEqual(self._post(self.fraying, data).status_code, 302)
        self.assertEqual(Consequence.objects.count(), before)

    def test_half_filled_effects_on_skipped_new_rows_do_not_block_the_save(self) -> None:
        before = (Consequence.objects.count(), ConsequenceEffect.objects.count())
        data = self._values(self.fraying)
        half_filled = [{"effect_type": EffectType.APPLY_CONDITION}]
        blank = self._add_row(data)
        self._add_new_row_effects(data, blank, half_filled)
        removed = self._add_row(
            data,
            outcome_tier=self.ladder.outcomes["Failure"].pk,
            label="PLACEHOLDER removed before saving",
            remove="on",
        )
        self._add_new_row_effects(data, removed, half_filled)
        data["stage-description"] = ["PLACEHOLDER still saved"]
        self.assertEqual(self._post(self.fraying, data).status_code, 302)
        self.assertEqual((Consequence.objects.count(), ConsequenceEffect.objects.count()), before)
        stage = ConditionStage.objects.get(pk=self.fraying.pk)
        self.assertEqual(stage.description, "PLACEHOLDER still saved")

    def test_a_shared_rows_text_and_effects_are_never_written_here(self) -> None:
        """Ruling RF-1: a shared row is drop/reweight only, whatever the POST carries."""
        shared = Consequence.objects.get(label="common Success")
        before = Consequence.objects.filter(pk=shared.pk).values(
            "label", "character_loss", "theater", "outcome_tier_id", "written_by_id"
        )[0]
        data = self._values(self.fraying)
        index = self._row_index(data, "common Success")
        self.assertNotIn(f"e{shared.pk}-TOTAL_FORMS", data)
        data[f"rows-{index}-label"] = ["PLACEHOLDER shared"]
        data[f"rows-{index}-character_loss"] = ["on"]
        data[f"rows-{index}-theater"] = ["on"]
        data[f"rows-{index}-outcome_tier"] = [str(self.ladder.outcomes["Failure"].pk)]
        prefix = f"e{shared.pk}"
        data.update(
            {
                f"{prefix}-TOTAL_FORMS": ["1"],
                f"{prefix}-INITIAL_FORMS": ["0"],
                f"{prefix}-0-id": [""],
                f"{prefix}-0-consequence": [str(shared.pk)],
                f"{prefix}-0-effect_type": [EffectType.APPLY_CONDITION],
                f"{prefix}-0-target": ["self"],
                f"{prefix}-0-execution_order": ["1"],
                f"{prefix}-0-condition_template": [str(self.shaken.pk)],
                f"{prefix}-0-condition_severity": ["2"],
            }
        )
        data["stage-description"] = ["PLACEHOLDER saved beside it"]
        self.assertEqual(self._post(self.fraying, data).status_code, 302)
        after = Consequence.objects.filter(pk=shared.pk).values(
            "label", "character_loss", "theater", "outcome_tier_id", "written_by_id"
        )[0]
        self.assertEqual(after, before)
        self.assertFalse(ConsequenceEffect.objects.filter(consequence=shared).exists())
        self.assertFalse(
            ConsequencePoolEntry.objects.filter(pool=self.fraying_pool, consequence=shared).exists()
        )
        self.assertEqual(ConditionStage.objects.get(pk=self.fraying.pk).written_by, self.writer)

    def test_a_shared_row_still_drops_and_reweights_beside_a_text_edit(self) -> None:
        data = self._values(self.fraying)
        success = self._row_index(data, "common Success")
        partial = self._row_index(data, "common Partial Success")
        data[f"rows-{success}-weight"] = ["4"]
        data[f"rows-{success}-label"] = ["PLACEHOLDER ignored"]
        data[f"rows-{partial}-remove"] = ["on"]
        self.assertEqual(self._post(self.fraying, data).status_code, 302)
        entries = dict(
            ConsequencePoolEntry.objects.filter(pool=self.fraying_pool).values_list(
                "consequence__label", "weight_override"
            )
        )
        self.assertEqual(entries["common Success"], 4)
        self.assertIn("common Partial Success", entries)
        self.assertTrue(Consequence.objects.filter(label="common Success").exists())

    def test_copy_rows_clone_their_effects(self) -> None:
        data = self._values(self.tearing, f"?copy_from={self.fraying.pk}")
        self.assertEqual(self._post(self.tearing, data).status_code, 302)
        pool = ConditionStage.objects.get(pk=self.tearing.pk).consequence_pool
        copied = Consequence.objects.get(label="Fraying Failure", pool_entries__pool=pool)
        self.assertNotEqual(copied.pk, self.fraying_failure.pk)
        effect = ConsequenceEffect.objects.get(consequence=copied)
        self.assertEqual(
            (effect.effect_type, effect.condition_template_id, effect.written_by),
            (EffectType.APPLY_CONDITION, self.shaken.pk, self.writer),
        )


class RefusalsTest(SaveTestCase):
    def test_unlinked_operator_saves_nothing(self) -> None:
        data = self._values(self.tearing)
        self._add_row(
            data, outcome_tier=self.ladder.outcomes["Failure"].pk, label="PLACEHOLDER slip"
        )
        resp = self._post(self.tearing, data, user=self.unlinked)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("link a contributor", resp.content.decode().lower())
        self.assertIsNone(ConditionStage.objects.get(pk=self.tearing.pk).consequence_pool_id)

    def test_a_parent_that_itself_inherits_is_refused(self) -> None:
        data = self._values(self.tearing)
        data["pool-parent"] = [str(self.fraying_pool.pk)]
        resp = self._post(self.tearing, data)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("inheritance is one level deep", resp.content.decode())
        self.assertIsNone(ConditionStage.objects.get(pk=self.tearing.pk).consequence_pool_id)

    def test_a_stage_pool_cannot_be_another_stages_parent(self) -> None:
        data = self._values(self.tearing)
        data["pool-parent"] = [str(self.ripping_pool.pk)]
        resp = self._post(self.tearing, data)
        self.assertEqual(resp.status_code, 200)
        errors = resp.context["forms"].pool.errors["parent"]
        self.assertIn("Soulfray - Ripping is a Soulfray stage's own pool", errors[0])
        self.assertIsNone(ConditionStage.objects.get(pk=self.tearing.pk).consequence_pool_id)

    def test_another_stages_parent_cannot_be_picked_as_a_stage_pool(self) -> None:
        data = self._values(self.tearing)
        data["pool-pool"] = [str(self.common.pk)]
        resp = self._post(self.tearing, data)
        self.assertEqual(resp.status_code, 200)
        errors = resp.context["forms"].pool.errors["pool"]
        self.assertIn("Soulfray - common is another Soulfray stage's shared parent", errors[0])
        self.assertIsNone(ConditionStage.objects.get(pk=self.tearing.pk).consequence_pool_id)

    def test_new_rows_with_no_pool_name_are_refused(self) -> None:
        data = self._values(self.tearing)
        data["pool-new_name"] = [""]
        self._add_row(
            data, outcome_tier=self.ladder.outcomes["Failure"].pk, label="PLACEHOLDER homeless"
        )
        resp = self._post(self.tearing, data)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["forms"].pool.errors["new_name"], [NEW_POOL_NAME_REQUIRED])
        self.assertIsNone(ConditionStage.objects.get(pk=self.tearing.pk).consequence_pool_id)
        self.assertFalse(Consequence.objects.filter(label="PLACEHOLDER homeless").exists())

    def test_a_table_that_changed_since_the_page_loaded_is_refused(self) -> None:
        data = self._values(self.fraying)
        data[f"rows-{self._row_index(data, 'Fraying Failure')}-label"] = ["PLACEHOLDER edited"]
        # Someone adds a row to the shared parent pool between this page's GET and its POST.
        ConsequencePoolEntryFactory(
            pool=self.common,
            consequence=ConsequenceFactory(
                outcome_tier=self.ladder.outcomes["Critical Failure"], label="Arrived late"
            ),
        )
        resp = self._post(self.fraying, data)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["forms"].rows.non_form_errors(), [TABLE_CHANGED_ERROR])
        self.assertTrue(Consequence.objects.filter(label="Fraying Failure").exists())
        self.assertFalse(Consequence.objects.filter(label="PLACEHOLDER edited").exists())

    def test_a_table_that_shrank_since_the_page_loaded_is_refused(self) -> None:
        data = self._values(self.fraying)
        data[f"rows-{self._row_index(data, 'Fraying Failure')}-label"] = ["PLACEHOLDER edited"]
        # The shared pool stops offering a row between this page's GET and its POST, so
        # every posted row past it now names the wrong table row. Saved through the
        # instance (a queryset update would leave the identity-mapped entry stale), and
        # put back by a cleanup so the cached instance never outlives this test's rollback.
        entry = ConsequencePoolEntry.objects.get(
            pool=self.common, consequence__label="common Partial Success"
        )
        entry.is_excluded = True
        entry.save(update_fields=["is_excluded"])

        def _restore() -> None:
            entry.is_excluded = False
            entry.save(update_fields=["is_excluded"])

        self.addCleanup(_restore)
        resp = self._post(self.fraying, data)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["forms"].rows.non_form_errors(), [TABLE_CHANGED_ERROR])
        self.assertFalse(Consequence.objects.filter(label="PLACEHOLDER edited").exists())

    def test_a_bad_row_re_renders_with_errors(self) -> None:
        data = self._values(self.tearing)
        self._add_row(data, outcome_tier=self.ladder.outcomes["Failure"].pk, label="")
        resp = self._post(self.tearing, data)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("This field is required", resp.content.decode())
        self.assertIsNone(ConditionStage.objects.get(pk=self.tearing.pk).consequence_pool_id)

    def test_pool_change_with_row_edits_is_refused(self) -> None:
        data = self._values(self.fraying)
        data["pool-parent"] = [str(self.loose.pk)]
        data[f"rows-{self._row_index(data, 'Fraying Failure')}-label"] = ["PLACEHOLDER edited"]
        resp = self._post(self.fraying, data)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Nothing was saved", resp.content.decode())
        self.assertEqual(
            ConsequencePool.objects.get(pk=self.fraying_pool.pk).parent_id, self.common.pk
        )
        self.assertTrue(Consequence.objects.filter(label="Fraying Failure").exists())

    def test_a_stage_from_another_condition_is_404(self) -> None:
        self.client.force_login(self.author)
        self.assertEqual(self.client.post(self._url(self.numb), {}).status_code, 404)


class PoolPickTest(SaveTestCase):
    """The pool select offers Soulfray stage pools and pools nothing else uses (I1)."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.clash_pool = ConsequencePoolFactory(name="Clash pool")
        TechniqueFactory(clash_resolution_pool=cls.clash_pool)
        cls.numb_pool = ConsequencePoolFactory(name="Numb pool")
        cls.numb.consequence_pool = cls.numb_pool
        cls.numb.save(update_fields=["consequence_pool"])
        # A parentless pool a non-Soulfray pool inherits from (a trap pool's shared base).
        cls.trap_base = ConsequencePoolFactory(name="Trap base pool")
        ConsequencePoolFactory(name="Trap pool", parent=cls.trap_base)

    @staticmethod
    def _parent_id(pool: ConsequencePool) -> int | None:
        return ConsequencePool.objects.filter(pk=pool.pk).values_list("parent_id", flat=True)[0]

    def test_the_pool_select_offers_stage_pools_and_unused_pools_only(self) -> None:
        self.client.force_login(self.author)
        resp = self.client.get(self._url(self.tearing))
        offered = set(resp.context["forms"].pool.fields["pool"].queryset)
        self.assertTrue({self.fraying_pool, self.ripping_pool, self.loose} <= offered)
        self.assertNotIn(self.clash_pool, offered)
        self.assertNotIn(self.numb_pool, offered)
        self.assertNotIn(self.trap_base, offered)
        # common is a Soulfray stage pool's parent, which is not a consumer: still offered
        # (and refused by clean as another stage's shared parent).
        self.assertIn(self.common, offered)

    def test_the_pool_list_is_one_query_however_many_pools_and_consumers(self) -> None:
        with self.assertNumQueries(1):
            first = list(stage_pool_choices())
        for index in range(5):
            held = ConsequencePoolFactory(name=f"Held pool {index}")
            TechniqueFactory(clash_resolution_pool=held)
            ConsequencePoolFactory(name=f"Child pool {index}", parent=held)
            ConsequencePoolFactory(name=f"Free pool {index}")
        with self.assertNumQueries(1):
            second = list(stage_pool_choices())
        added = {pool.name for pool in second} - {pool.name for pool in first}
        # A held pool stays out; a free pool, or a child pool nothing else holds, is offered.
        self.assertEqual(
            added,
            {f"Free pool {index}" for index in range(5)}
            | {f"Child pool {index}" for index in range(5)},
        )

    def test_a_pool_another_consumer_holds_is_refused(self) -> None:
        for held in (self.clash_pool, self.numb_pool, self.trap_base):
            with self.subTest(pool=held.name):
                data = self._values(self.tearing)
                data["pool-pool"] = [str(held.pk)]
                data["pool-parent"] = [str(self.loose.pk)]
                resp = self._post(self.tearing, data)
                self.assertEqual(resp.status_code, 200)
                self.assertIn("pool", resp.context["forms"].pool.errors)
                self.assertIsNone(
                    ConditionStage.objects.filter(pk=self.tearing.pk).values_list(
                        "consequence_pool_id", flat=True
                    )[0]
                )
                self.assertIsNone(self._parent_id(held))

    def test_a_pool_a_non_soulfray_pool_inherits_from_is_refused(self) -> None:
        """Taking it as this stage's own pool would let this page edit rows the trap
        pool inherits, so the pick is refused even with the parent select left alone."""
        data = self._values(self.tearing)
        data["pool-pool"] = [str(self.trap_base.pk)]
        resp = self._post(self.tearing, data)
        self.assertEqual(resp.status_code, 200)
        errors = resp.context["forms"].pool.errors["pool"]
        self.assertIn("Pick a Soulfray stage's pool or a pool nothing else uses", errors[0])
        self.assertIsNone(
            ConditionStage.objects.filter(pk=self.tearing.pk).values_list(
                "consequence_pool_id", flat=True
            )[0]
        )

    def test_another_stages_pool_cannot_be_re_parented_from_here(self) -> None:
        data = self._values(self.tearing)
        data["pool-pool"] = [str(self.ripping_pool.pk)]
        data["pool-parent"] = [str(self.loose.pk)]
        resp = self._post(self.tearing, data)
        self.assertEqual(resp.status_code, 200)
        errors = resp.context["forms"].pool.errors["parent"]
        self.assertIn("Soulfray - Ripping is also used elsewhere", errors[0])
        self.assertIsNone(self._parent_id(self.ripping_pool))

    def test_switching_to_a_pool_keeps_its_parent_when_the_select_is_left_alone(self) -> None:
        data = self._values(self.fraying)
        self.assertEqual(data["pool-parent"], [str(self.common.pk)])
        data["pool-pool"] = [str(self.loose.pk)]
        self.assertEqual(self._post(self.fraying, data).status_code, 302)
        self.assertIsNone(self._parent_id(self.loose))
        self.assertEqual(
            ConditionStage.objects.filter(pk=self.fraying.pk).values_list(
                "consequence_pool_id", flat=True
            )[0],
            self.loose.pk,
        )

    def test_switching_to_a_pool_and_changing_the_select_re_parents_it(self) -> None:
        data = self._values(self.ripping)
        self.assertEqual(data["pool-parent"], [""])
        data["pool-pool"] = [str(self.loose.pk)]
        data["pool-parent"] = [str(self.common.pk)]
        self.assertEqual(self._post(self.ripping, data).status_code, 302)
        self.assertEqual(self._parent_id(self.loose), self.common.pk)

    def test_the_parent_select_never_offers_the_stages_own_pool(self) -> None:
        self.client.force_login(self.author)
        resp = self.client.get(self._url(self.ripping))
        self.assertNotIn(
            self.ripping_pool, set(resp.context["forms"].pool.fields["parent"].queryset)
        )
        self.assertIn('id="sf-pool-parents"', resp.content.decode())


class CacheSafetyTest(SaveTestCase):
    """A save that does not commit leaves the identity-mapped rows as they were.

    Every read here is the ordinary cached ``get(pk=...)``, never a flush: the live
    game reads the same instances, so the cache itself is what is asserted on.
    """

    def _edit_stage(self, data: dict[str, list[str]]) -> None:
        data["stage-name"] = ["PLACEHOLDER renamed"]
        data["stage-severity_threshold"] = ["99"]

    def _assert_stage_untouched(self, stage: ConditionStage, name: str, threshold: int) -> None:
        cached = ConditionStage.objects.get(pk=stage.pk)
        self.assertEqual((cached.name, cached.severity_threshold), (name, threshold))

    def test_a_refused_save_with_no_pool_name_leaves_the_cached_stage_alone(self) -> None:
        data = self._values(self.tearing)
        self._edit_stage(data)
        data["pool-new_name"] = [""]
        self._add_row(
            data, outcome_tier=self.ladder.outcomes["Failure"].pk, label="PLACEHOLDER homeless"
        )
        self.assertEqual(self._post(self.tearing, data).status_code, 200)
        self._assert_stage_untouched(self.tearing, "Tearing", 6)

    def test_a_refused_pool_switch_leaves_the_cached_stage_and_effects_alone(self) -> None:
        data = self._values(self.fraying)
        self._edit_stage(data)
        data["pool-parent"] = [str(self.loose.pk)]
        data[f"rows-{self._row_index(data, 'Fraying Failure')}-label"] = ["PLACEHOLDER edited"]
        data[f"e{self.fraying_failure.pk}-0-condition_severity"] = ["4"]
        resp = self._post(self.fraying, data)
        self.assertIn("Nothing was saved", resp.content.decode())
        self._assert_stage_untouched(self.fraying, "Fraying", 1)
        effect = ConsequenceEffect.objects.get(consequence=self.fraying_failure)
        self.assertEqual(ConsequenceEffect.objects.get(pk=effect.pk).condition_severity, 1)

    def test_a_failure_inside_the_save_leaves_the_cached_stage_pool_alone(self) -> None:
        data = self._values(self.tearing)
        self._edit_stage(data)
        data["pool-parent"] = [str(self.common.pk)]
        self._add_row(
            data, outcome_tier=self.ladder.outcomes["Failure"].pk, label="PLACEHOLDER lost"
        )
        with (
            mock.patch.object(BaseEffectFormSet, "save", side_effect=RuntimeError("injected")),
            self.assertRaises(RuntimeError),
        ):
            self._post(self.tearing, data)
        stage = ConditionStage.objects.get(pk=self.tearing.pk)
        self.assertIsNone(stage.consequence_pool_id)
        self.assertIsNone(stage.consequence_pool)
        self._assert_stage_untouched(self.tearing, "Tearing", 6)

    def test_a_failure_inside_the_save_leaves_the_cached_pool_parent_alone(self) -> None:
        data = self._values(self.fraying)
        data["pool-parent"] = [str(self.loose.pk)]
        with (
            mock.patch.object(BaseEffectFormSet, "save", side_effect=RuntimeError("injected")),
            self.assertRaises(RuntimeError),
        ):
            self._post(self.fraying, data)
        pool = ConsequencePool.objects.get(pk=self.fraying_pool.pk)
        self.assertEqual(pool.parent_id, self.common.pk)
        self.assertEqual(pool.parent, self.common)

    def test_a_failure_inside_the_save_leaves_the_penalty_alone(self) -> None:
        # ConditionCheckModifier is not identity-mapped today, so this pins the
        # rollback; it would also catch the model joining the identity map unguarded.
        data = self._values(self.ripping)
        data["penalty-modifier_value"] = ["-7"]
        with (
            mock.patch.object(BaseEffectFormSet, "save", side_effect=RuntimeError("injected")),
            self.assertRaises(RuntimeError),
        ):
            self._post(self.ripping, data)
        self.assertEqual(ConditionCheckModifier.objects.get(pk=self.penalty.pk).modifier_value, -3)

    def test_a_failure_inside_the_save_evicts_the_rows_it_created(self) -> None:
        data = self._values(self.tearing)
        data["pool-parent"] = [str(self.common.pk)]
        self._add_row(
            data, outcome_tier=self.ladder.outcomes["Failure"].pk, label="PLACEHOLDER lost"
        )
        with (
            mock.patch.object(BaseEffectFormSet, "save", side_effect=RuntimeError("injected")),
            self.assertRaises(RuntimeError),
        ):
            self._post(self.tearing, data)
        cached_pools = {pool.name for pool in ConsequencePool.get_all_cached_instances()}
        self.assertNotIn("Soulfray - Tearing", cached_pools)
        cached_rows = {row.label for row in Consequence.get_all_cached_instances()}
        self.assertNotIn("PLACEHOLDER lost", cached_rows)


class ReviewTest(SaveTestCase):
    def test_mark_reviewed_stamps_review_only(self) -> None:
        self.client.force_login(self.author)
        resp = self.client.post(reverse("admin_soulfray_builder_review", args=[self.fraying.pk]))
        self.assertEqual(resp.status_code, 302)
        stage = ConditionStage.objects.get(pk=self.fraying.pk)
        self.assertEqual((stage.reviewed_by, stage.written_by), (self.writer, None))
        pool = ConsequencePool.objects.get(pk=self.fraying_pool.pk)
        self.assertEqual(pool.reviewed_by, self.writer)
        consequence = Consequence.objects.get(pk=self.fraying_failure.pk)
        self.assertEqual(consequence.reviewed_by, self.writer)
        effect = ConsequenceEffect.objects.get(consequence=self.fraying_failure)
        self.assertEqual(effect.reviewed_by, self.writer)
        shared = Consequence.objects.get(label="common Success")
        self.assertIsNone(shared.reviewed_by)

    def test_the_rail_carries_the_mark_reviewed_form(self) -> None:
        self.client.force_login(self.author)
        body = self.client.get(self._url(self.fraying)).content.decode()
        self.assertIn(reverse("admin_soulfray_builder_review", args=[self.fraying.pk]), body)
        self.assertIn('value="Mark reviewed"', body)

    def test_a_failure_part_way_leaves_the_cached_rows_unreviewed(self) -> None:
        calls = {"n": 0}

        def _stamp(row, contributor) -> None:
            calls["n"] += 1
            if calls["n"] == 3:
                message = "injected"
                raise RuntimeError(message)
            stamp_reviewed(row, contributor)

        self.client.force_login(self.author)
        with (
            mock.patch("web.admin.soulfray_builder.views.stamp_reviewed", side_effect=_stamp),
            self.assertRaises(RuntimeError),
        ):
            self.client.post(reverse("admin_soulfray_builder_review", args=[self.fraying.pk]))
        self.assertIsNone(ConditionStage.objects.get(pk=self.fraying.pk).reviewed_by)
        self.assertIsNone(ConsequencePool.objects.get(pk=self.fraying_pool.pk).reviewed_by)

    def test_review_is_post_only_and_needs_a_contributor(self) -> None:
        url = reverse("admin_soulfray_builder_review", args=[self.fraying.pk])
        self.client.force_login(self.author)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.force_login(self.unlinked)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertIsNone(ConditionStage.objects.get(pk=self.fraying.pk).reviewed_by)


class NoConfigSaveTest(SoulfrayBuilderTestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        PlayerData.objects.create(
            account=cls.author, contributor=ContentContributorFactory(name="No Config Saver")
        )

    def test_save_works_and_writes_no_penalty(self) -> None:
        stage = self.ladder.stage("Tearing")
        url = reverse("admin_soulfray_builder", args=[stage.pk])
        self.client.force_login(self.author)
        data = form_values(self.client.get(url).content.decode())
        data["stage-description"] = ["PLACEHOLDER no config"]
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertFalse(ConditionCheckModifier.objects.filter(stage_id=stage.pk).exists())
