from django.test import TestCase

from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterSheetFactory,
    ResonanceFactory,
    TechniqueFactory,
    ThreadFactory,
)


class BuildCastApplicableThreadsTests(TestCase):
    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.resonance = ResonanceFactory()
        self.technique = TechniqueFactory()

    def _technique_thread(self, technique):
        # Build a TECHNIQUE-kind thread anchored to `technique` (always deterministic
        # for _anchor_in_action when involved_techniques contains technique.id).
        return ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=technique,
        )

    def test_passive_technique_anchored_thread_in_scope(self):
        from world.magic.services.cast_threads import build_cast_applicable_threads

        thread = self._technique_thread(self.technique)
        result = build_cast_applicable_threads(self.sheet, self.technique)
        self.assertEqual([(a.thread.pk, a.pull_tier) for a in result], [(thread.pk, 0)])

    def test_thread_anchored_to_other_technique_excluded(self):
        from world.magic.services.cast_threads import build_cast_applicable_threads

        other = TechniqueFactory()
        self._technique_thread(other)
        self.assertEqual(build_cast_applicable_threads(self.sheet, self.technique), [])

    def test_declared_pull_overrides_passive_tier(self):
        from world.magic.services.cast_threads import build_cast_applicable_threads
        from world.magic.types.pull import CastPullDeclaration

        thread = self._technique_thread(self.technique)
        pull = CastPullDeclaration(resonance=self.resonance, tier=2, threads=(thread,))
        result = build_cast_applicable_threads(self.sheet, self.technique, cast_pull=pull)
        self.assertEqual([(a.thread.pk, a.pull_tier) for a in result], [(thread.pk, 2)])
