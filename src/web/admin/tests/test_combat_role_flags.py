"""The missing combat content flags (#4906, slice 4 of #4843).

Vows: Warden has no picks; Fulmination has picks, and its sub-role Static Choir chooses
from them; Lifeward is a sub-role of Warden, so it has nothing to choose either.

Holders, with a budget of 4: Corvin chose Arcing Charge (3) and Kneel (value 4, one
half-time limit: 2) at level 1, 5 of 4. Mira chose one pick worth exactly 4. A
secondary membership and a left one are both over and never read.

Conditions: Indulgence is read by a perk situation, Lonely by nothing. Signed carries
Lonely and one vow effect lands it; Brooding carries Lonely and two effects land it;
Hushed carries Lonely only on its second stage and is landed; Unfelt carries nothing and
is landed; Named carries Lonely, is landed, and a modifier target names it. Smitten
carries Indulgence and nothing lands it; Charmed carries it on its second stage only and
nothing lands it either; Tipsy carries it and is landed.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from web.admin.tuning import combat_role_flags as flags, required_content as rc
from world.conditions.factories import ConditionStageFactory, ConditionTemplateFactory
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CharacterVowFocusPickFactory,
    CovenantRoleFactory,
    SubroleCovenantRoleFactory,
    VowAddedEffectAppliedConditionFactory,
    VowAddedEffectFactory,
    VowFocusPickConfigFactory,
    VowFocusPickFactory,
    VowFocusPickLimitFactory,
    VowSituationalPerkSituationFactory,
    VowStatScalingFactory,
)
from world.covenants.perks.constants import Situation
from world.mechanics.constants import EffectKind
from world.mechanics.factories import ModifierTargetFactory, PropertyFactory


def _texts(result: rc.ProbeResult) -> list[str]:
    return [row.text for row in result.flagged]


def _url_for(result: rc.ProbeResult, text: str) -> str | None:
    return next(row.url for row in result.flagged if row.text == text)


class CombatRoleFlagsCase(TestCase):
    _effects_made = 0

    @classmethod
    def setUpTestData(cls) -> None:
        VowFocusPickConfigFactory(budget_per_level=4)
        cls.warden = CovenantRoleFactory(name="Warden")
        cls.lifeward = SubroleCovenantRoleFactory(name="Lifeward", parent_role=cls.warden)
        cls.fulmination = CovenantRoleFactory(name="Fulmination")
        cls.choir = SubroleCovenantRoleFactory(name="Static Choir", parent_role=cls.fulmination)

        cls.arcing = VowFocusPickFactory(covenant_role=cls.fulmination, name="Arcing", value=3)
        cls.kneel = VowFocusPickFactory(covenant_role=cls.fulmination, name="Kneel", value=4)
        VowFocusPickLimitFactory(pick=cls.kneel, frequency_tenths=5)
        cls.open_sky = VowFocusPickFactory(
            covenant_role=cls.fulmination, name="Under Open Sky", value=4
        )
        for pick in (cls.arcing, cls.kneel):
            VowStatScalingFactory(covenant_role=cls.fulmination, focus_pick=pick)

        cls.corvin = cls._holder(cls.arcing, cls.kneel)
        cls.mira = cls._holder(cls.open_sky)
        cls.secondary = cls._holder(cls.arcing, cls.kneel, is_secondary=True)
        cls.left = cls._holder(cls.arcing, cls.kneel, left_at=timezone.now())

        cls.indulgence = PropertyFactory(name="Indulgence")
        cls.lonely = PropertyFactory(name="Lonely")
        VowSituationalPerkSituationFactory(
            situation=Situation.TARGET_HAS_CONDITION_PROPERTY,
            condition_property=cls.indulgence,
            perk__covenant_role=cls.fulmination,
            perk__name="Give Them What They Want",
        )
        cls.signed = cls._condition("Signed", cls.lonely, setters=1)
        cls.brooding = cls._condition("Brooding", cls.lonely, setters=2)
        cls.unfelt = cls._condition("Unfelt", None, setters=1)
        cls.named = cls._condition("Named", cls.lonely, setters=1)
        ModifierTargetFactory(
            name="Against the named",
            scope_effect_kind=EffectKind.DAMAGE,
            scope_opponent_condition=cls.named,
        )
        cls.hushed = cls._staged("Hushed", cls.lonely, setters=1)
        cls.smitten = cls._condition("Smitten", cls.indulgence, setters=0)
        cls.charmed = cls._staged("Charmed", cls.indulgence, setters=0)
        cls.tipsy = cls._condition("Tipsy", cls.indulgence, setters=1)

    @classmethod
    def _holder(cls, *picks, **membership):
        role = CharacterCovenantRoleFactory(covenant_role=picks[0].covenant_role, **membership)
        for pick in picks:
            CharacterVowFocusPickFactory(character_role=role, pick=pick)
        return role

    @classmethod
    def _land(cls, template, setters: int) -> None:
        for _ in range(setters):
            # A distinct unlock level per effect: Postgres treats the scope key's nulls as
            # equal, so two otherwise identical effects on one vow collide.
            cls._effects_made += 1
            effect = VowAddedEffectFactory(
                covenant_role=cls.warden, unlock_thread_level=cls._effects_made
            )
            VowAddedEffectAppliedConditionFactory(effect=effect, condition=template)

    @classmethod
    def _condition(cls, name: str, prop, *, setters: int):
        template = ConditionTemplateFactory(name=name)
        if prop is not None:
            template.properties.add(prop)
        cls._land(template, setters)
        return template

    @classmethod
    def _staged(cls, name: str, prop, *, setters: int):
        template = ConditionTemplateFactory(name=name, has_progression=True)
        ConditionStageFactory(condition=template, stage_order=1, name=f"{name} one")
        ConditionStageFactory(condition=template, stage_order=2, name=f"{name} two").properties.add(
            prop
        )
        cls._land(template, setters)
        return template


class VowNoPicksTest(CombatRoleFlagsCase):
    def test_a_vow_and_a_sub_role_with_nothing_to_choose_are_flagged(self) -> None:
        result = flags._probe_vow_no_picks()
        self.assertFalse(result.present)
        self.assertIn("Warden", _texts(result))
        self.assertIn("Lifeward", _texts(result))
        self.assertEqual(result.missing, tuple(_texts(result)))

    def test_a_vow_with_picks_and_its_sub_role_are_not_flagged(self) -> None:
        texts = _texts(flags._probe_vow_no_picks())
        self.assertNotIn("Fulmination", texts)
        self.assertNotIn("Static Choir", texts)

    def test_each_row_links_to_its_vow_page(self) -> None:
        result = flags._probe_vow_no_picks()
        self.assertEqual(
            _url_for(result, "Lifeward"), reverse("admin_vow_builder", args=[self.lifeward.pk])
        )


class HolderOverBudgetTest(CombatRoleFlagsCase):
    def test_a_holder_over_budget_is_flagged_with_the_total(self) -> None:
        name = self.corvin.character_sheet.character.db_key
        result = flags._probe_holder_over_budget()
        self.assertEqual(_texts(result), [f"{name}, Fulmination level 1 (5 of 4)"])

    def test_the_row_links_to_the_holders_picks(self) -> None:
        name = self.corvin.character_sheet.character.db_key
        url = flags._probe_holder_over_budget().flagged[0].url
        changelist = reverse("admin:arxii_charactervowfocuspick_changelist")
        self.assertEqual(url, f"{changelist}?{urlencode({'q': name})}")

    def test_exactly_at_budget_secondary_and_left_are_not_flagged(self) -> None:
        texts = " ".join(_texts(flags._probe_holder_over_budget()))
        for membership in (self.mira, self.secondary, self.left):
            self.assertNotIn(membership.character_sheet.character.db_key, texts)


class ConditionNeverReadTest(CombatRoleFlagsCase):
    def test_a_landed_condition_whose_properties_nothing_reads_is_flagged(self) -> None:
        texts = _texts(flags._probe_condition_never_read())
        self.assertIn("Signed (set by Hold / Lock (Warden base vow))", texts)
        self.assertIn("Brooding (set by Hold / Lock (Warden base vow) and 1 more)", texts)

    def test_a_stage_only_carrier_counts(self) -> None:
        texts = _texts(flags._probe_condition_never_read())
        self.assertIn("Hushed (set by Hold / Lock (Warden base vow))", texts)

    def test_no_property_named_read_or_unlanded_are_not_flagged(self) -> None:
        texts = " ".join(_texts(flags._probe_condition_never_read()))
        for name in ("Unfelt", "Named", "Tipsy", "Smitten", "Charmed"):
            self.assertNotIn(name, texts)

    def test_the_row_links_to_the_conditions_combo_map(self) -> None:
        result = flags._probe_condition_never_read()
        self.assertEqual(
            _url_for(result, "Signed (set by Hold / Lock (Warden base vow))"),
            reverse("admin_combo_map_condition", args=[self.signed.pk]),
        )


class ConditionSetByNothingTest(CombatRoleFlagsCase):
    def test_an_unlanded_carrier_of_a_read_property_is_flagged(self) -> None:
        texts = _texts(flags._probe_condition_set_by_nothing())
        self.assertIn("Smitten (Indulgence)", texts)
        self.assertIn("Charmed (Indulgence)", texts)

    def test_a_landed_carrier_and_a_carrier_of_an_unread_property_are_not_flagged(self) -> None:
        texts = " ".join(_texts(flags._probe_condition_set_by_nothing()))
        for name in ("Tipsy", "Signed", "Brooding", "Hushed", "Unfelt"):
            self.assertNotIn(name, texts)

    def test_the_row_links_to_the_conditions_combo_map(self) -> None:
        result = flags._probe_condition_set_by_nothing()
        self.assertEqual(
            _url_for(result, "Smitten (Indulgence)"),
            reverse("admin_combo_map_condition", args=[self.smitten.pk]),
        )


class PickBlankPayloadTest(CombatRoleFlagsCase):
    def test_a_pick_with_no_payload_is_flagged_and_links_to_its_vow(self) -> None:
        result = flags._probe_pick_blank_payload()
        self.assertEqual(_texts(result), ["Under Open Sky (Fulmination)"])
        self.assertEqual(
            result.flagged[0].url, reverse("admin_vow_builder", args=[self.fulmination.pk])
        )

    def test_a_pick_with_a_payload_row_is_not_flagged(self) -> None:
        texts = " ".join(_texts(flags._probe_pick_blank_payload()))
        self.assertNotIn("Arcing", texts)
        self.assertNotIn("Kneel", texts)


class RegistryTest(CombatRoleFlagsCase):
    def test_the_five_flags_are_tuning_rows_of_the_required_content_registry(self) -> None:
        keys = {dep.key: dep.tier for dep in rc._declarations() if dep.key.startswith("combat_")}
        self.assertEqual(
            keys,
            dict.fromkeys(
                (
                    "combat_vow_no_picks",
                    "combat_holder_over_budget",
                    "combat_condition_never_read",
                    "combat_condition_set_by_nothing",
                    "combat_pick_blank_payload",
                ),
                rc.DependencyTier.TUNING,
            ),
        )


#: The five probes' queries together, however many vows, picks, holders and conditions.
FLAG_QUERIES = 116


class QueryCountTest(CombatRoleFlagsCase):
    def _run_all(self) -> int:
        with CaptureQueriesContext(connection) as queries:
            for dependency in flags.combat_role_declarations():
                dependency.probe.resolve(None)
        return len(queries)

    def test_the_query_count_does_not_grow_with_the_rows(self) -> None:
        self._run_all()
        before = self._run_all()
        for index in range(5):
            role = CovenantRoleFactory(name=f"Extra vow {index}")
            pick = VowFocusPickFactory(covenant_role=role, name=f"Extra pick {index}", value=9)
            self._holder(pick)
            self._condition(f"Extra set {index}", self.lonely, setters=1)
            self._condition(f"Extra unset {index}", self.indulgence, setters=0)
        self._run_all()
        after = self._run_all()
        self.assertEqual(before, after)
        self.assertEqual(after, FLAG_QUERIES)
