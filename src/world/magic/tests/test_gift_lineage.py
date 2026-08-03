"""Gift lineage: holding a gift reaches its ancestors' techniques (#2891).

The invariant under test: a character granted a child gift holds ONE
``CharacterGift`` and threads ONE GIFT thread, and that one thread reaches the
child's own techniques *and* every ancestor gift's techniques — for learning, for
the technique cap, for cast-time resonance, and for variant specialization.

The shape exists so subspecies players don't pay the Rite of Imbuing twice: see
the issue for why two ``SpeciesGiftGrant`` rows was rejected.
"""

from django.test import TestCase

from world.achievements.constants import AccessChangeSource
from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import GiftKind, TargetKind
from world.magic.exceptions import GiftNotOwned, TechniqueCapExceeded
from world.magic.factories import (
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
    TechniqueVariantFactory,
)
from world.magic.models import CharacterGift, Thread
from world.magic.services.gift_acquisition import (
    charge_and_learn,
    count_techniques_for_gift,
    get_technique_cap_for_gift,
    resolve_owned_gift,
)
from world.magic.services.technique_acquisition import learn_technique
from world.magic.specialization.services import (
    gift_resonances_for,
    resolve_specialized_variant,
)


class GiftLineageModelTests(TestCase):
    """The derived walk itself — mirrors ``Species.lineage``'s contract."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.umbrella = GiftFactory(name="Khati", kind=GiftKind.MINOR)
        cls.kind = GiftFactory(name="Vulpi", kind=GiftKind.MINOR, parent=cls.umbrella)
        cls.umbrella_tech = TechniqueFactory(gift=cls.umbrella, name="Khati Senses")
        cls.kind_tech = TechniqueFactory(gift=cls.kind, name="Fox Cunning")

    def test_lineage_is_self_then_ancestors_nearest_first(self) -> None:
        self.assertEqual(
            [g.pk for g in self.kind.lineage],
            [self.kind.pk, self.umbrella.pk],
        )

    def test_lineage_of_a_parentless_gift_is_just_itself(self) -> None:
        self.assertEqual([g.pk for g in self.umbrella.lineage], [self.umbrella.pk])

    def test_lineage_ids_matches_lineage(self) -> None:
        self.assertEqual(self.kind.lineage_ids, frozenset({self.kind.pk, self.umbrella.pk}))

    def test_inherited_techniques_are_own_first_then_ancestors(self) -> None:
        self.assertEqual(
            [t.pk for t in self.kind.inherited_techniques],
            [self.kind_tech.pk, self.umbrella_tech.pk],
        )

    def test_inherited_techniques_of_a_parentless_gift_are_its_own(self) -> None:
        self.assertEqual(
            [t.pk for t in self.umbrella.inherited_techniques],
            [self.umbrella_tech.pk],
        )

    def test_cached_techniques_still_means_own_techniques_only(self) -> None:
        """``cached_techniques`` is the ``Prefetch(to_attr=)`` target — do not widen it."""
        self.assertEqual([t.pk for t in self.kind.cached_techniques], [self.kind_tech.pk])

    def test_a_parent_cycle_terminates(self) -> None:
        """A cycle is a data defect, not a modelled state; the walk must not hang."""
        self.umbrella.parent = self.kind
        self.umbrella.save()
        self.kind.refresh_from_db()
        self.assertEqual(
            {g.pk for g in self.kind.lineage},
            {self.kind.pk, self.umbrella.pk},
        )


class InheritedTechniqueAcquisitionTests(TestCase):
    """``learn_technique`` — the non-teaching acquisition path."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.resonance = ResonanceFactory()
        self.umbrella = GiftFactory(kind=GiftKind.MINOR)
        self.kind = GiftFactory(kind=GiftKind.MINOR, parent=self.umbrella)
        self.kind.resonances.add(self.resonance)
        # The character holds ONLY the kind gift, with ONE thread on it.
        CharacterGift.objects.create(character=self.sheet, gift=self.kind)
        Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.GIFT,
            target_gift=self.kind,
            level=0,
        )
        self.umbrella_tech = TechniqueFactory(gift=self.umbrella)
        self.kind_tech = TechniqueFactory(gift=self.kind)
        pool = ActionPointPool.get_or_create_for_character(self.sheet.character)
        pool.current = 200
        pool.save()

    def test_resolve_owned_gift_finds_the_held_descendant(self) -> None:
        self.assertEqual(resolve_owned_gift(self.sheet, self.umbrella), self.kind)

    def test_resolve_owned_gift_prefers_a_direct_hold(self) -> None:
        self.assertEqual(resolve_owned_gift(self.sheet, self.kind), self.kind)

    def test_resolve_owned_gift_returns_none_for_an_unreachable_gift(self) -> None:
        self.assertIsNone(resolve_owned_gift(self.sheet, GiftFactory(kind=GiftKind.MINOR)))

    def test_learn_technique_accepts_a_parent_gift_technique(self) -> None:
        """The crux: the learner holds the child, the technique belongs to the parent."""
        ct = learn_technique(
            self.sheet,
            self.umbrella_tech,
            source=AccessChangeSource.TECHNIQUE_GRANT,
        )
        self.assertEqual(ct.technique, self.umbrella_tech)

    def test_learn_technique_still_refuses_an_unrelated_gift(self) -> None:
        unrelated = TechniqueFactory(gift=GiftFactory(kind=GiftKind.MINOR))
        with self.assertRaises(GiftNotOwned):
            learn_technique(
                self.sheet,
                unrelated,
                source=AccessChangeSource.TECHNIQUE_GRANT,
            )

    def test_learn_technique_refuses_a_child_gift_technique_when_holding_the_parent(
        self,
    ) -> None:
        """Inheritance runs one way. Holding Khati does not grant the Vulpi kind's own."""
        other_sheet = CharacterSheetFactory()
        CharacterGift.objects.create(character=other_sheet, gift=self.umbrella)
        Thread.objects.create(
            owner=other_sheet,
            resonance=self.resonance,
            target_kind=TargetKind.GIFT,
            target_gift=self.umbrella,
            level=0,
        )
        with self.assertRaises(GiftNotOwned):
            learn_technique(
                other_sheet,
                self.kind_tech,
                source=AccessChangeSource.TECHNIQUE_GRANT,
            )

    def test_inherited_and_own_techniques_share_one_cap(self) -> None:
        """One thread, one cap — inherited techniques are not a second budget."""
        learn_technique(self.sheet, self.kind_tech, source=AccessChangeSource.TECHNIQUE_GRANT)
        self.assertEqual(count_techniques_for_gift(self.sheet, self.kind), 1)

        learn_technique(self.sheet, self.umbrella_tech, source=AccessChangeSource.TECHNIQUE_GRANT)
        self.assertEqual(count_techniques_for_gift(self.sheet, self.kind), 2)

    def test_cap_is_read_from_the_held_gifts_thread(self) -> None:
        """Asking about the parent must not report cap 0 for want of a parent thread."""
        cap = get_technique_cap_for_gift(self.sheet, self.kind)
        self.assertGreater(cap, 0)

    def test_cap_exceeded_counts_inherited_techniques(self) -> None:
        cap = get_technique_cap_for_gift(self.sheet, self.kind)
        for _ in range(cap):
            learn_technique(
                self.sheet,
                TechniqueFactory(gift=self.umbrella),
                source=AccessChangeSource.TECHNIQUE_GRANT,
            )
        with self.assertRaises(TechniqueCapExceeded):
            learn_technique(self.sheet, self.kind_tech, source=AccessChangeSource.TECHNIQUE_GRANT)


class InheritedTechniqueTeachingPathTests(TestCase):
    """``charge_and_learn`` — the teaching / Academy path.

    The highest-value assertion in this file: the whole point of ``Gift.parent``
    is that a subspecies character carries ONE gift and ONE thread. A path that
    implicitly mints a second of each on the first inherited technique would
    reintroduce the double AP+XP cost the design exists to remove.
    """

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.resonance = ResonanceFactory()
        self.umbrella = GiftFactory(kind=GiftKind.MINOR)
        self.kind = GiftFactory(kind=GiftKind.MINOR, parent=self.umbrella)
        self.umbrella.resonances.add(self.resonance)
        self.kind.resonances.add(self.resonance)
        CharacterGift.objects.create(character=self.sheet, gift=self.kind)
        Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.GIFT,
            target_gift=self.kind,
            level=0,
        )
        self.umbrella_tech = TechniqueFactory(gift=self.umbrella)

    def test_learning_an_inherited_technique_mints_no_second_gift_or_thread(self) -> None:
        charge_and_learn(
            self.sheet,
            self.umbrella_tech,
            base_ap_cost=10,
            source=AccessChangeSource.GIFT_ACQUISITION,
        )
        self.assertEqual(CharacterGift.objects.filter(character=self.sheet).count(), 1)
        self.assertEqual(
            Thread.objects.filter(owner=self.sheet, target_kind=TargetKind.GIFT).count(),
            1,
        )

    def test_inherited_technique_needs_no_gift_unlock_receipt(self) -> None:
        """The receipt gate is for acquiring a gift you don't have — this one is held."""
        progress = charge_and_learn(
            self.sheet,
            self.umbrella_tech,
            base_ap_cost=10,
            source=AccessChangeSource.GIFT_ACQUISITION,
        )
        self.assertEqual(progress.technique, self.umbrella_tech)


class InheritedTechniqueCastTests(TestCase):
    """Cast-time reads: the child's thread governs the parent's techniques."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.thread_resonance = ResonanceFactory()
        cls.umbrella_resonance = ResonanceFactory()
        cls.umbrella = GiftFactory(kind=GiftKind.MINOR)
        cls.umbrella.resonances.add(cls.umbrella_resonance)
        cls.kind = GiftFactory(kind=GiftKind.MINOR, parent=cls.umbrella)
        cls.kind.resonances.add(cls.thread_resonance)
        CharacterGift.objects.create(character=cls.sheet, gift=cls.kind)
        Thread.objects.create(
            owner=cls.sheet,
            resonance=cls.thread_resonance,
            target_kind=TargetKind.GIFT,
            target_gift=cls.kind,
            level=5,
        )
        cls.umbrella_tech = TechniqueFactory(gift=cls.umbrella)

    def test_inherited_technique_manifests_at_the_thread_resonance(self) -> None:
        """Not the parent gift's authored supported set — the character's own thread."""
        result = gift_resonances_for(self.sheet.character, self.umbrella)
        self.assertEqual([r.pk for r in result], [self.thread_resonance.pk])

    def test_inherited_technique_resolves_a_variant_from_the_child_thread(self) -> None:
        variant = TechniqueVariantFactory(
            parent_technique=self.umbrella_tech,
            resonance=self.thread_resonance,
            unlock_thread_level=3,
            name_override="Fox-Touched Sense",
        )
        resolved = resolve_specialized_variant(
            entity=self.umbrella_tech,
            character=self.sheet.character,
        )
        # Both a raw Technique and a _ResolvedTechnique expose ``name``; only the
        # resolved wrapper returns the variant's override.
        self.assertEqual(resolved.name, variant.name_override)


class ParentlessGiftUnchangedTests(TestCase):
    """A gift with no parent behaves exactly as it did before #2891."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.resonance = ResonanceFactory()
        self.gift = GiftFactory(kind=GiftKind.MINOR)
        self.gift.resonances.add(self.resonance)
        CharacterGift.objects.create(character=self.sheet, gift=self.gift)
        Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            level=0,
        )
        self.technique = TechniqueFactory(gift=self.gift)

    def test_learn_and_count_are_unchanged(self) -> None:
        learn_technique(self.sheet, self.technique, source=AccessChangeSource.TECHNIQUE_GRANT)
        self.assertEqual(count_techniques_for_gift(self.sheet, self.gift), 1)

    def test_resonance_read_is_unchanged(self) -> None:
        result = gift_resonances_for(self.sheet.character, self.gift)
        self.assertEqual([r.pk for r in result], [self.resonance.pk])
