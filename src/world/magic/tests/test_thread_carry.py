"""Threads carry through prerequisites (#4097).

Ratified spec: "a thread woven into a technique also empowers the techniques
it is a prerequisite for (including hidden ultimates)", and "a prerequisite's
thread carries at its full level." Covers the closure helper
(``prerequisite_technique_ids``) directly and its wiring into the cast path
via ``build_cast_applicable_threads`` / ``_anchor_in_action``.
"""

from __future__ import annotations

import itertools

from django.test import TestCase

from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterSheetFactory,
    ResonanceFactory,
    TechniqueFactory,
    ThreadFactory,
    ThreadPullEffectFactory,
)
from world.magic.services.cast_threads import build_cast_applicable_threads
from world.magic.services.power_terms import PowerTermContext, thread_power_term
from world.magic.services.technique_prerequisites import prerequisite_technique_ids
from world.progression.factories import TechniqueKnownRequirementFactory


class PrerequisiteTechniqueIdsTests(TestCase):
    def test_direct_prerequisite(self):
        a = TechniqueFactory()
        b = TechniqueFactory()
        TechniqueKnownRequirementFactory(technique=b, required_technique=a)

        self.assertEqual(prerequisite_technique_ids([b.pk]), frozenset({a.pk}))

    def test_transitive_prerequisite(self):
        a = TechniqueFactory()
        b = TechniqueFactory()
        c = TechniqueFactory()
        TechniqueKnownRequirementFactory(technique=b, required_technique=a)
        TechniqueKnownRequirementFactory(technique=c, required_technique=b)

        self.assertEqual(prerequisite_technique_ids([c.pk]), frozenset({a.pk, b.pk}))

    def test_cycle_terminates_and_excludes_the_input(self):
        a = TechniqueFactory()
        b = TechniqueFactory()
        TechniqueKnownRequirementFactory(technique=a, required_technique=b)
        TechniqueKnownRequirementFactory(technique=b, required_technique=a)

        self.assertEqual(prerequisite_technique_ids([a.pk]), frozenset({b.pk}))

    def test_inactive_requirement_does_not_contribute(self):
        a = TechniqueFactory()
        b = TechniqueFactory()
        TechniqueKnownRequirementFactory(technique=b, required_technique=a, is_active=False)

        self.assertEqual(prerequisite_technique_ids([b.pk]), frozenset())

    def test_no_requirements_is_empty(self):
        a = TechniqueFactory()

        self.assertEqual(prerequisite_technique_ids([a.pk]), frozenset())

    def test_pinned_query_count_per_chain_depth(self):
        """One batched query per BFS frontier level, never one per technique in the
        chain (#4097 fix round 2). A terminating query confirms the frontier is
        empty, so a chain of N hops costs N+1 queries."""
        techniques = [TechniqueFactory() for _ in range(4)]
        # techniques[0] requires [1] requires [2] requires [3] -- a 3-hop chain.
        for deeper, shallower in itertools.pairwise(techniques):
            TechniqueKnownRequirementFactory(technique=deeper, required_technique=shallower)

        chain_hops = 3
        with self.assertNumQueries(chain_hops + 1):
            result = prerequisite_technique_ids([techniques[0].pk])

        self.assertEqual(result, frozenset(t.pk for t in techniques[1:]))


class ThreadCarryThroughPrerequisitesTests(TestCase):
    """End-to-end: a thread on a prerequisite is in-scope for the dependent cast."""

    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.resonance = ResonanceFactory()

    def _technique_thread(self, technique):
        return ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=technique,
        )

    def test_direct_prerequisite_thread_carries_to_cast(self):
        a = TechniqueFactory()
        b = TechniqueFactory()
        TechniqueKnownRequirementFactory(technique=b, required_technique=a)
        thread = self._technique_thread(a)

        result = build_cast_applicable_threads(self.sheet, b)

        self.assertEqual([(t.thread.pk, t.pull_tier) for t in result], [(thread.pk, 0)])

    def test_transitive_prerequisite_threads_carry_to_cast(self):
        a = TechniqueFactory()
        b = TechniqueFactory()
        c = TechniqueFactory()
        TechniqueKnownRequirementFactory(technique=b, required_technique=a)
        TechniqueKnownRequirementFactory(technique=c, required_technique=b)
        thread_a = self._technique_thread(a)
        thread_b = self._technique_thread(b)

        result = build_cast_applicable_threads(self.sheet, c)

        self.assertEqual({t.thread.pk for t in result}, {thread_a.pk, thread_b.pk})

    def test_inactive_requirement_does_not_carry_to_cast(self):
        a = TechniqueFactory()
        b = TechniqueFactory()
        TechniqueKnownRequirementFactory(technique=b, required_technique=a, is_active=False)
        self._technique_thread(a)

        self.assertEqual(build_cast_applicable_threads(self.sheet, b), [])

    def test_unrelated_technique_thread_still_excluded(self):
        a = TechniqueFactory()
        b = TechniqueFactory()
        other = TechniqueFactory()
        TechniqueKnownRequirementFactory(technique=b, required_technique=a)
        self._technique_thread(other)

        self.assertEqual(build_cast_applicable_threads(self.sheet, b), [])

    def test_carried_thread_applies_at_full_level(self):
        """Full-level carry: casting B with only A's thread must yield the same
        thread_power_term as casting A directly with that thread (same thread
        row, same tier - the carry doesn't discount it)."""
        a = TechniqueFactory()
        b = TechniqueFactory()
        TechniqueKnownRequirementFactory(technique=b, required_technique=a)
        thread = self._technique_thread(a)
        ThreadPullEffectFactory(
            as_intensity_bump=True,
            target_kind=TargetKind.TECHNIQUE,
            resonance=self.resonance,
            tier=0,
            intensity_bump_amount=5,
        )

        threads_for_b = build_cast_applicable_threads(self.sheet, b)
        threads_for_a = build_cast_applicable_threads(self.sheet, a)

        term_for_b = thread_power_term(
            PowerTermContext(sheet=self.sheet, technique=b, applicable_threads=threads_for_b)
        )
        term_for_a = thread_power_term(
            PowerTermContext(sheet=self.sheet, technique=a, applicable_threads=threads_for_a)
        )

        self.assertEqual(term_for_b, term_for_a)
        self.assertEqual(term_for_b, 5)
        self.assertEqual(thread.pk, threads_for_b[0].thread.pk)
