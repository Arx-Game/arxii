from django.test import TestCase

from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterSheetFactory,
    GiftFactory,
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


class AmbientGiftThreadQueryCountTests(TestCase):
    """Regression for #2708 review Finding 1.

    ``_gift_in_action`` used to run a fresh ``Technique`` query on every call, and
    ``build_applicable_threads`` calls ``_anchor_ambiently_active`` once per thread in
    its loop — so a character with several owned GIFT threads fired one query per
    thread on every ambient evaluation. The query count must now stay flat as the
    number of GIFT threads grows.
    """

    def test_multi_gift_thread_character_query_count_bounded(self):
        from world.magic.services.cast_threads import build_applicable_threads
        from world.magic.types.pull import PullActionContext

        sheet = CharacterSheetFactory()
        gifts = [GiftFactory() for _ in range(4)]
        techniques = [TechniqueFactory(gift=gift) for gift in gifts]
        for gift in gifts:
            ThreadFactory(
                owner=sheet,
                target_kind=TargetKind.GIFT,
                target_gift=gift,
                target_trait=None,
            )
        ctx = PullActionContext(involved_techniques=(techniques[0].pk,))

        # Prime the FK cache for sheet.character so the query count below reflects only
        # the GIFT-arm predicate work, not an unrelated one-time relation fetch.
        _ = sheet.character

        with self.assertNumQueries(2):
            result = build_applicable_threads(sheet, ctx, ambient=True)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].thread.target_gift_id, gifts[0].pk)
