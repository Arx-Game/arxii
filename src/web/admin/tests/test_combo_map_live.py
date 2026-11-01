"""The combo map's reads (#4891, slice 3 of #4843).

Indulgence is carried by Tipsy and Smitten on the template and by Charmed on its second
stage only. Tipsy is landed by a technique and a vow effect, Charmed by a standoff
approach, and nothing lands Smitten. Readers: a perk situation, a prerequisite and a
modifier target read the property; a modifier target and a condition interaction name
Tipsy itself.
"""

from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from web.admin.combo_map import live
from world.conditions.factories import (
    ConditionConditionInteractionFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.covenants.factories import (
    CovenantRoleFactory,
    VowAddedEffectAppliedConditionFactory,
    VowAddedEffectFactory,
    VowSituationalPerkSituationFactory,
)
from world.covenants.perks.constants import Situation
from world.magic.factories import TechniqueAppliedConditionFactory, TechniqueFactory
from world.mechanics.constants import EffectKind
from world.mechanics.factories import ModifierTargetFactory, PrerequisiteFactory, PropertyFactory
from world.standoffs.factories import StandoffApproachFactory


class ComboMapLiveCase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.indulgence = PropertyFactory(name="Indulgence")
        cls.lonely = PropertyFactory(name="Lonely")
        cls.tipsy = ConditionTemplateFactory(name="Tipsy")
        cls.tipsy.properties.add(cls.indulgence)
        cls.smitten = ConditionTemplateFactory(name="Smitten")
        cls.smitten.properties.add(cls.indulgence)
        cls.charmed = ConditionTemplateFactory(name="Charmed", has_progression=True)
        ConditionStageFactory(condition=cls.charmed, stage_order=1, name="Warm")
        stage_two = ConditionStageFactory(condition=cls.charmed, stage_order=2, name="Smitten")
        stage_two.properties.add(cls.indulgence)
        cls.signed = ConditionTemplateFactory(name="Signed")

        cls.unbound = TechniqueFactory(name="Unbound")
        cls.unbound_label = f"Unbound ({cls.unbound.gift.name})"
        TechniqueAppliedConditionFactory(
            technique=cls.unbound, condition=cls.tipsy, target_kind="self"
        )
        cls.role = CovenantRoleFactory(name="Sage")
        cls.effect = VowAddedEffectFactory(covenant_role=cls.role)
        VowAddedEffectAppliedConditionFactory(effect=cls.effect, condition=cls.tipsy)
        cls.approach = StandoffApproachFactory(
            name="Keep the drinks coming", target_condition=cls.charmed
        )

        cls.situation = VowSituationalPerkSituationFactory(
            situation=Situation.TARGET_HAS_CONDITION_PROPERTY,
            condition_property=cls.indulgence,
            perk__covenant_role=cls.role,
            perk__name="Give Them What They Want",
        )
        cls.prerequisite = PrerequisiteFactory(name="Must be indulgent", property=cls.indulgence)
        cls.scoped = ModifierTargetFactory(
            name="Against the indulgent",
            scope_effect_kind=EffectKind.DAMAGE,
            scope_opponent_property=cls.indulgence,
        )
        cls.against_tipsy = ModifierTargetFactory(
            name="Against the tipsy",
            scope_effect_kind=EffectKind.DAMAGE,
            scope_opponent_condition=cls.tipsy,
        )
        ConditionConditionInteractionFactory(condition=cls.tipsy, other_condition=cls.signed)


class ConditionsCarryingTest(ComboMapLiveCase):
    def test_template_carriers_and_stage_only_carriers(self) -> None:
        rows = live.conditions_carrying(self.indulgence)
        self.assertEqual(
            [(r.name, r.stage_note) for r in rows],
            [("Charmed", "(stage 2 only)"), ("Smitten", ""), ("Tipsy", "")],
        )

    def test_properties_a_condition_carries(self) -> None:
        self.assertEqual(
            [(r.name, r.stage_note) for r in live.properties_carried(self.charmed)],
            [("Indulgence", "(stage 2 only)")],
        )


class SettersTest(ComboMapLiveCase):
    def test_each_setter_kind_lands_its_condition(self) -> None:
        rows = live.setters_for_conditions([self.tipsy, self.charmed])
        self.assertEqual(
            [(r.source.label, r.kind, r.lands) for r in rows],
            [
                ("Keep the drinks coming", "standoff approach", "Charmed on the pressed group"),
                (self.unbound_label, "technique", "Tipsy on self"),
                ("Hold / Lock (Sage base vow)", "vow effect", "Tipsy on the target"),
            ],
        )

    def test_each_setter_links_to_its_owner_change_page(self) -> None:
        rows = {r.source.label: r.source.url for r in live.setters_for_conditions([self.tipsy])}
        technique_url = reverse("admin:arxii_technique_change", args=[self.unbound.pk])
        effect_url = reverse("admin:arxii_vowaddedeffect_change", args=[self.effect.pk])
        self.assertEqual(rows[self.unbound_label], technique_url)
        self.assertEqual(rows["Hold / Lock (Sage base vow)"], effect_url)


class ReadersTest(ComboMapLiveCase):
    def test_property_readers(self) -> None:
        rows = live.readers_for_property(self.indulgence)
        self.assertEqual(
            [(r.source.label, r.kind) for r in rows],
            [
                ("Against the indulgent", "modifier target"),
                ("Sage: Give Them What They Want", "perk situation"),
                ("Must be indulgent", "prerequisite"),
            ],
        )

    def test_condition_readers(self) -> None:
        rows = live.readers_for_condition(self.tipsy)
        self.assertEqual(
            [(r.source.label, r.kind) for r in rows],
            [
                ("Tipsy and Signed", "condition interaction"),
                ("Against the tipsy", "modifier target"),
            ],
        )


class MapsTest(ComboMapLiveCase):
    def test_property_map_marks_the_condition_nothing_sets(self) -> None:
        combo = live.property_map(self.indulgence.pk)
        self.assertFalse(combo.set_by_nothing)
        self.assertFalse(combo.read_by_nothing)
        self.assertEqual(
            [line.unset_condition for line in combo.set_by if not line.setter], ["Smitten"]
        )

    def test_an_untouched_property_is_set_and_read_by_nothing(self) -> None:
        combo = live.property_map(self.lonely.pk)
        self.assertTrue(combo.set_by_nothing)
        self.assertTrue(combo.read_by_nothing)

    def test_condition_map_groups_readers_by_itself_then_each_property(self) -> None:
        combo = live.condition_map(self.tipsy.pk)
        self.assertEqual(
            [(g.heading, len(g.readers)) for g in combo.reader_groups],
            [("Tipsy", 2), ("Indulgence", 3)],
        )

    def test_a_condition_nothing_sets_or_reads(self) -> None:
        combo = live.condition_map(self.smitten.pk)
        self.assertTrue(combo.set_by_nothing)
        self.assertFalse(combo.read_by_nothing)  # its property is read
        unread = live.condition_map(ConditionTemplateFactory(name="Bored").pk)
        self.assertTrue(unread.read_by_nothing)

    def test_unknown_pk_is_none(self) -> None:
        self.assertIsNone(live.property_map(0))
        self.assertIsNone(live.condition_map(0))
