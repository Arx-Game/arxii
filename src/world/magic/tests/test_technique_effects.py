"""Tests for the shared technique effect summary (#2898)."""

from __future__ import annotations

from django.test import TestCase

from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
)
from world.magic.constants import TechniqueReach
from world.magic.factories import (
    BinaryEffectTypeFactory,
    TechniqueAppliedConditionFactory,
    TechniqueCapabilityGrantFactory,
    TechniqueDamageProfileFactory,
    TechniqueFactory,
    TechniqueRemovedConditionFactory,
)
from world.magic.models.techniques import ConditionTargetKind
from world.magic.services.targeting import derive_target_relationship
from world.magic.services.technique_effects import (
    invalidate_technique_payload_caches,
    summarize_technique_effects,
    technique_effect_authoring_gaps,
    technique_is_underspecified,
    technique_relationship_is_ambiguous,
)


def _bare_technique(**kwargs):
    """A technique with no auto-seeded damage profile, so payload rows are explicit."""
    return TechniqueFactory(
        effect_type=BinaryEffectTypeFactory(),
        damage_profile=False,
        **kwargs,
    )


class SummarizeTechniqueEffectsTests(TestCase):
    """summarize_technique_effects reads the four payload tables display never saw."""

    def test_ally_buff_reports_relationship_and_applied_condition(self):
        """An ALLY-targeted condition surfaces as relationship + an applies row."""
        technique = _bare_technique(anima_cost=5)
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=ConditionTemplateFactory(name="Guarded"),
            target_kind=ConditionTargetKind.ALLY,
        )

        summary = summarize_technique_effects(technique)

        self.assertEqual(summary["relationship"], ConditionTargetKind.ALLY.value)
        self.assertFalse(summary["hostile"])
        self.assertEqual([row["name"] for row in summary["applies"]], ["Guarded"])
        self.assertFalse(summary["is_underspecified"])

    def test_damage_profile_surfaces_type_and_hostility(self):
        """A typed damage profile reaches the payload — 62 rows previously reached nothing."""
        technique = _bare_technique()
        TechniqueDamageProfileFactory(
            technique=technique,
            damage_type=DamageTypeFactory(name="witchfire"),
            base_damage=7,
        )

        summary = summarize_technique_effects(technique)

        self.assertTrue(summary["hostile"])
        self.assertEqual(summary["relationship"], ConditionTargetKind.ENEMY.value)
        self.assertEqual(summary["damage"][0]["damage_type"], "witchfire")
        self.assertEqual(summary["damage"][0]["base_damage"], 7)

    def test_capability_grants_and_removals_reach_the_payload(self):
        """793 capability grants and 27 removal rows previously reached no surface."""
        technique = _bare_technique()
        TechniqueCapabilityGrantFactory(
            technique=technique,
            capability=CapabilityTypeFactory(name="flight"),
            base_value=3,
        )
        TechniqueRemovedConditionFactory(
            technique=technique,
            condition=ConditionTemplateFactory(name="Burning"),
            target_kind=ConditionTargetKind.ALLY,
        )

        summary = summarize_technique_effects(technique)

        self.assertEqual([row["name"] for row in summary["grants"]], ["flight"])
        self.assertEqual([row["name"] for row in summary["removes"]], ["Burning"])
        self.assertEqual(summary["relationship"], ConditionTargetKind.ALLY.value)

    def test_arena_and_reach_come_from_the_technique_row(self):
        """action_category reached no surface at all before #2898."""
        technique = _bare_technique(reach=TechniqueReach.SAME)
        TechniqueAppliedConditionFactory(
            technique=technique,
            target_kind=ConditionTargetKind.SELF,
        )

        summary = summarize_technique_effects(technique)

        self.assertEqual(summary["arena"], technique.action_category)
        self.assertEqual(summary["reach"], TechniqueReach.SAME.value)


class TechniqueEffectSentenceTests(TestCase):
    """The plain-words line names no fields."""

    def test_ally_buff_reads_as_a_sentence(self):
        technique = _bare_technique(anima_cost=5, reach=TechniqueReach.ANY)
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=ConditionTemplateFactory(name="Guarded"),
            target_kind=ConditionTargetKind.ALLY,
        )

        summary = summarize_technique_effects(technique)["summary"]

        self.assertIn("Cast on an ally, anywhere in the room", summary)
        self.assertIn("Costs 5 anima.", summary)
        self.assertIn("Applies Guarded.", summary)
        # Field names never leak into player-facing prose.
        self.assertNotIn("target_kind", summary)
        self.assertNotIn("action_category", summary)

    def test_damage_and_grants_read_as_sentences(self):
        technique = _bare_technique(anima_cost=0)
        TechniqueDamageProfileFactory(
            technique=technique,
            damage_type=DamageTypeFactory(name="shadow"),
            base_damage=4,
        )
        TechniqueCapabilityGrantFactory(
            technique=technique,
            capability=CapabilityTypeFactory(name="flight"),
        )

        summary = summarize_technique_effects(technique)["summary"]

        self.assertIn("Deals shadow damage.", summary)
        self.assertIn("Grants flight.", summary)
        # anima_cost of 0 is not worth a sentence.
        self.assertNotIn("anima", summary)

    def test_multiple_conditions_join_as_prose(self):
        technique = _bare_technique()
        for name in ("Burning", "Blinded", "Slowed"):
            TechniqueAppliedConditionFactory(
                technique=technique,
                condition=ConditionTemplateFactory(name=name),
                target_kind=ConditionTargetKind.ENEMY,
            )

        summary = summarize_technique_effects(technique)["summary"]

        self.assertIn("Applies Burning, Blinded and Slowed.", summary)


class TechniqueAuthoringGapTests(TestCase):
    """The two states where the derived effect can't be trusted are reported, not guessed."""

    def test_technique_with_no_payload_is_underspecified(self):
        """86 of 272 authored techniques were in this state when #2898 was written."""
        technique = _bare_technique()

        summary = summarize_technique_effects(technique)

        self.assertTrue(technique_is_underspecified(technique))
        self.assertTrue(summary["is_underspecified"])
        self.assertIn("Its effects are not yet catalogued.", summary["summary"])

    def test_authored_payload_is_not_underspecified(self):
        technique = _bare_technique()
        TechniqueAppliedConditionFactory(technique=technique)

        self.assertFalse(technique_is_underspecified(technique))

    def test_side_effect_condition_makes_the_relationship_ambiguous(self):
        """The #2764 failure mode: a self-buff whose side effect targets an enemy.

        A self-teleport that applies Flanked to an enemy derives as enemy-targeted,
        silently, and looks correct. Authored data carries no signal separating the
        point of a technique from a side effect, so the ambiguity is reported —
        and derive_target_relationship's own answer stays exactly as it was, since
        it gates live cast targeting.
        """
        technique = _bare_technique()
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=ConditionTemplateFactory(name="Displaced"),
            target_kind=ConditionTargetKind.SELF,
        )
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=ConditionTemplateFactory(name="Flanked"),
            target_kind=ConditionTargetKind.ENEMY,
        )

        self.assertTrue(technique_relationship_is_ambiguous(technique))
        self.assertEqual(derive_target_relationship(technique), ConditionTargetKind.ENEMY)

    def test_single_target_kind_is_not_ambiguous(self):
        technique = _bare_technique()
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=ConditionTemplateFactory(name="Displaced"),
            target_kind=ConditionTargetKind.SELF,
        )
        TechniqueRemovedConditionFactory(
            technique=technique,
            condition=ConditionTemplateFactory(name="Burning"),
            target_kind=ConditionTargetKind.SELF,
        )

        self.assertFalse(technique_relationship_is_ambiguous(technique))

    def test_audit_reports_both_gap_kinds_and_skips_clean_techniques(self):
        blank = _bare_technique(name="Blank Working")
        ambiguous = _bare_technique(name="Ambiguous Working")
        TechniqueAppliedConditionFactory(technique=ambiguous, target_kind=ConditionTargetKind.SELF)
        TechniqueAppliedConditionFactory(technique=ambiguous, target_kind=ConditionTargetKind.ENEMY)
        clean = _bare_technique(name="Clean Working")
        TechniqueAppliedConditionFactory(technique=clean, target_kind=ConditionTargetKind.ALLY)

        gaps = {gap.technique_id: gap for gap in technique_effect_authoring_gaps()}

        self.assertTrue(gaps[blank.pk].is_underspecified)
        self.assertFalse(gaps[blank.pk].relationship_is_ambiguous)
        self.assertTrue(gaps[ambiguous.pk].relationship_is_ambiguous)
        self.assertFalse(gaps[ambiguous.pk].is_underspecified)
        self.assertNotIn(clean.pk, gaps)


class TechniqueEffectCacheTests(TestCase):
    """The summary lives on the Technique row, so a pk fetch answers every surface."""

    def test_summary_is_built_once_per_instance(self):
        technique = _bare_technique()
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=ConditionTemplateFactory(name="Guarded"),
            target_kind=ConditionTargetKind.ALLY,
        )
        invalidate_technique_payload_caches(technique)

        with self.assertNumQueries(4):
            # One query per payload table on the first build.
            first = technique.cached_effect_summary
        with self.assertNumQueries(0):
            second = technique.cached_effect_summary

        self.assertIs(first, second)

    def test_hostility_and_relationship_ride_the_same_cached_lists(self):
        """The cast path calls is_technique_hostile up to six times per cast."""
        from world.magic.services.hostility import is_technique_hostile

        technique = _bare_technique()
        TechniqueDamageProfileFactory(technique=technique, base_damage=5)
        invalidate_technique_payload_caches(technique)

        # First call populates cached_damage_profiles; every later call is free.
        is_technique_hostile(technique)
        with self.assertNumQueries(0):
            for _ in range(6):
                self.assertTrue(is_technique_hostile(technique))
            self.assertEqual(derive_target_relationship(technique), ConditionTargetKind.ENEMY)

    def test_invalidation_rebuilds_after_a_payload_edit(self):
        """An authoring edit must not leave the identity map serving the old summary."""
        technique = _bare_technique()
        self.assertTrue(technique.cached_effect_summary["is_underspecified"])

        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=ConditionTemplateFactory(name="Guarded"),
            target_kind=ConditionTargetKind.ALLY,
        )
        invalidate_technique_payload_caches(technique)

        self.assertFalse(technique.cached_effect_summary["is_underspecified"])
        self.assertEqual(
            technique.cached_effect_summary["relationship"],
            ConditionTargetKind.ALLY.value,
        )
