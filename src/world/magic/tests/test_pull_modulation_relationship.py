"""Tests for RELATIONSHIP_TRACK pull modulation (#1849, #3957).

Mirrors world/magic/tests/test_pull_modulation_passthrough.py's structure and
world/magic/services/pull_modulation_court.py's shape, but this rule has no
polarity gate (Decisions 3/4 in the #1849 spec) and reads CharacterRelationship
instead of NpcRegard.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import EffectKind, TargetKind
from world.magic.factories import ThreadFactory, ThreadPullEffectFactory
from world.magic.models import RelationshipBondPullTuning
from world.magic.services.pull_modulation_relationship import (
    get_relationship_bond_pull_tuning,
    relationship_bond_modulation,
)
from world.magic.services.resonance import resolve_pull_effects
from world.relationships.factories import CharacterRelationshipFactory


def _relationship_track_thread(*, owner, threaded_sheet, invested_depth: int = 0):
    """Build a RELATIONSHIP_TRACK thread owned by `owner`, anchored to `owner`'s
    own side of a tie toward `threaded_sheet`, with the given invested_depth."""
    relationship = CharacterRelationshipFactory(source=owner, target=threaded_sheet, is_active=True)
    if invested_depth:
        relationship.invested_depth = invested_depth
        relationship.save()
    return ThreadFactory(
        owner=owner,
        target_kind=TargetKind.RELATIONSHIP_TRACK,
        target_relationship=relationship,
        target_trait=None,
        level=10,
    )


def _bond_with_affection_conflict(*, owner, threaded_sheet, affection: int = 0, conflict: int = 0):
    """Build a RELATIONSHIP_TRACK thread anchored on an owner->threaded_sheet bond
    carrying `affection`/`conflict` gauges -- pair_depth() (the base term) is set to
    affection+conflict (mirroring the old developed_absolute_value = pos+neg split);
    min(affection, conflict) is what the fraught term keys on."""
    thread = _relationship_track_thread(
        owner=owner, threaded_sheet=threaded_sheet, invested_depth=affection + conflict
    )
    bond = owner.relationships_as_source.get(target=threaded_sheet)
    bond.affection = affection
    bond.conflict = conflict
    bond.save()
    return thread


class RelationshipBondModulationDirectTriggerTests(TestCase):
    """Live target IS the threaded person Y."""

    def test_direct_target_empowers_pull_by_saturating_curve(self) -> None:
        owner = CharacterSheetFactory()
        threaded_sheet = CharacterSheetFactory()
        thread = _relationship_track_thread(
            owner=owner, threaded_sheet=threaded_sheet, invested_depth=30
        )
        RelationshipBondPullTuning.objects.create(pk=1, coefficient=1, cap=20, half_saturation=30)
        ThreadPullEffectFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            resonance=thread.resonance,
            tier=1,
            min_thread_level=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=4,
        )

        resolved = resolve_pull_effects(
            [thread], tier=1, in_combat=True, target=threaded_sheet.character
        )

        flat_rows = [r for r in resolved if r.kind == EffectKind.FLAT_BONUS]
        self.assertEqual(len(flat_rows), 1)
        # level=10 -> multiplier=1; base_scaled = 4*1 = 4.
        # S = 1*30 = 30 (pair_depth, no reverse side); bonus = round(20*30/60) = 10.
        # scaled_value = 4 + 10 = 14.
        self.assertEqual(flat_rows[0].scaled_value, 14)

    def test_no_owner_to_threaded_person_relationship_leaves_unchanged(self) -> None:
        owner = CharacterSheetFactory()
        threaded_sheet = CharacterSheetFactory()
        # thread anchors owner's own side, but that side has no invested_depth
        # beyond the default 0.
        thread = _relationship_track_thread(
            owner=owner, threaded_sheet=threaded_sheet, invested_depth=0
        )
        RelationshipBondPullTuning.objects.create(pk=1, coefficient=1, cap=20, half_saturation=30)
        ThreadPullEffectFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            resonance=thread.resonance,
            tier=1,
            min_thread_level=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=4,
        )

        resolved = resolve_pull_effects(
            [thread], tier=1, in_combat=True, target=threaded_sheet.character
        )

        flat_rows = [r for r in resolved if r.kind == EffectKind.FLAT_BONUS]
        # pair_depth=0 -> S=0 -> _soft_cap returns 0 -> bonus 0 -> unchanged.
        self.assertEqual(flat_rows[0].scaled_value, 4)


class RelationshipBondModulationIndirectTriggerTests(TestCase):
    """Live target is a third party X hostile toward the threaded person Y."""

    def test_hostile_third_party_target_empowers_via_owner_bond(self) -> None:
        owner = CharacterSheetFactory()
        threaded_sheet = CharacterSheetFactory()
        thread = _relationship_track_thread(
            owner=owner, threaded_sheet=threaded_sheet, invested_depth=30
        )
        RelationshipBondPullTuning.objects.create(pk=1, coefficient=1, cap=20, half_saturation=30)
        # X (a third party) is hostile toward Y: conflict > affection.
        x_sheet = CharacterSheetFactory()
        hostile_relationship = CharacterRelationshipFactory(
            source=x_sheet, target=threaded_sheet, is_active=True
        )
        hostile_relationship.conflict = 10
        hostile_relationship.save()
        ThreadPullEffectFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            resonance=thread.resonance,
            tier=1,
            min_thread_level=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=4,
        )

        resolved = resolve_pull_effects([thread], tier=1, in_combat=True, target=x_sheet.character)

        flat_rows = [r for r in resolved if r.kind == EffectKind.FLAT_BONUS]
        # Same magnitude as the direct-trigger test: scale is ALWAYS the owner's
        # bond to Y (30 depth), never X's conflict magnitude (10).
        self.assertEqual(flat_rows[0].scaled_value, 14)

    def test_indirect_trigger_magnitude_unaffected_by_x_hostility_size(self) -> None:
        """Changing X's hostility magnitude doesn't change the bonus size, only
        whether it fires — the scale is always the owner's own bond to Y."""
        owner = CharacterSheetFactory()
        threaded_sheet = CharacterSheetFactory()
        thread = _relationship_track_thread(
            owner=owner, threaded_sheet=threaded_sheet, invested_depth=30
        )
        RelationshipBondPullTuning.objects.create(pk=1, coefficient=1, cap=20, half_saturation=30)
        x_sheet = CharacterSheetFactory()
        hostile_relationship = CharacterRelationshipFactory(
            source=x_sheet, target=threaded_sheet, is_active=True
        )
        # Very high hostility magnitude -- bonus must still be 14.
        hostile_relationship.conflict = 1000
        hostile_relationship.save()
        ThreadPullEffectFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            resonance=thread.resonance,
            tier=1,
            min_thread_level=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=4,
        )

        resolved = resolve_pull_effects([thread], tier=1, in_combat=True, target=x_sheet.character)

        flat_rows = [r for r in resolved if r.kind == EffectKind.FLAT_BONUS]
        self.assertEqual(flat_rows[0].scaled_value, 14)

    def test_non_hostile_third_party_leaves_pull_unchanged(self) -> None:
        """X exists, has no relationship (or a non-hostile one) toward Y, and isn't
        Y: neither trigger condition holds -> no-op."""
        owner = CharacterSheetFactory()
        threaded_sheet = CharacterSheetFactory()
        thread = _relationship_track_thread(
            owner=owner, threaded_sheet=threaded_sheet, invested_depth=30
        )
        RelationshipBondPullTuning.objects.create(pk=1, coefficient=1, cap=20, half_saturation=30)
        x_sheet = CharacterSheetFactory()  # no relationship to threaded_sheet at all
        ThreadPullEffectFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            resonance=thread.resonance,
            tier=1,
            min_thread_level=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=4,
        )

        resolved = resolve_pull_effects([thread], tier=1, in_combat=True, target=x_sheet.character)

        flat_rows = [r for r in resolved if r.kind == EffectKind.FLAT_BONUS]
        self.assertEqual(flat_rows[0].scaled_value, 4)


class RelationshipBondModulationInactiveBondTests(TestCase):
    """A frozen (is_active=False) side earns/triggers no reward (#3957 — replaces
    the old never-consented "pending" gate; ties have no consent concept anymore)."""

    def test_inactive_owner_to_y_relationship_does_not_reward(self) -> None:
        owner = CharacterSheetFactory()
        threaded_sheet = CharacterSheetFactory()
        thread = _relationship_track_thread(
            owner=owner, threaded_sheet=threaded_sheet, invested_depth=0
        )
        RelationshipBondPullTuning.objects.create(pk=1, coefficient=1, cap=20, half_saturation=30)
        # Owner->Y relationship is the anchor _relationship_track_thread already
        # created (unique_relationship_pair forbids a second row for this pair) --
        # freeze it and add depth; a frozen side earns no reward.
        inactive_relationship = owner.relationships_as_source.get(target=threaded_sheet)
        inactive_relationship.is_active = False
        inactive_relationship.invested_depth = 30
        inactive_relationship.save()
        ThreadPullEffectFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            resonance=thread.resonance,
            tier=1,
            min_thread_level=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=4,
        )

        resolved = resolve_pull_effects(
            [thread], tier=1, in_combat=True, target=threaded_sheet.character
        )

        flat_rows = [r for r in resolved if r.kind == EffectKind.FLAT_BONUS]
        self.assertEqual(flat_rows[0].scaled_value, 4)

    def test_inactive_indirect_hostility_does_not_trigger(self) -> None:
        owner = CharacterSheetFactory()
        threaded_sheet = CharacterSheetFactory()
        thread = _relationship_track_thread(
            owner=owner, threaded_sheet=threaded_sheet, invested_depth=30
        )
        RelationshipBondPullTuning.objects.create(pk=1, coefficient=1, cap=20, half_saturation=30)
        x_sheet = CharacterSheetFactory()

        # X->Y relationship is hostile but INACTIVE (broken off) -- must not trigger.
        broken_off_relationship = CharacterRelationshipFactory(
            source=x_sheet, target=threaded_sheet, is_active=False
        )
        broken_off_relationship.conflict = 10
        broken_off_relationship.save()
        ThreadPullEffectFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            resonance=thread.resonance,
            tier=1,
            min_thread_level=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=4,
        )

        resolved = resolve_pull_effects([thread], tier=1, in_combat=True, target=x_sheet.character)

        flat_rows = [r for r in resolved if r.kind == EffectKind.FLAT_BONUS]
        self.assertEqual(flat_rows[0].scaled_value, 4)


class RelationshipBondModulationNoResolutionPrivacyGateTests(TestCase):
    """Resolution-time modulation has NO can_perceive gate, deliberately — mirrors
    court_regard_modulation (also ungated at resolution). The privacy protection for
    this rule lives entirely in the picker (Task 3's RELATIONSHIP_NO_STAKE tests):
    a live, already-resolved cast target is a real commitment, not a free-probe
    vector, so gating resolution too would be redundant. This test documents that
    the bonus applies regardless of location/perception at resolution time, so a
    future reader doesn't mistake the absence of a gate here for an oversight."""

    def test_indirect_trigger_applies_even_when_owner_cannot_perceive_x(self) -> None:
        owner = CharacterSheetFactory()
        threaded_sheet = CharacterSheetFactory()
        thread = _relationship_track_thread(
            owner=owner, threaded_sheet=threaded_sheet, invested_depth=30
        )
        RelationshipBondPullTuning.objects.create(pk=1, coefficient=1, cap=20, half_saturation=30)
        x_sheet = CharacterSheetFactory()
        hostile_relationship = CharacterRelationshipFactory(
            source=x_sheet, target=threaded_sheet, is_active=True
        )
        hostile_relationship.conflict = 10
        hostile_relationship.save()
        ThreadPullEffectFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            resonance=thread.resonance,
            tier=1,
            min_thread_level=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=4,
        )
        # Put owner's character and X's character in different, unconnected rooms.
        # If resolution were gated on can_perceive, this would leave scaled_value=4;
        # since it isn't, the bonus applies exactly as in the perceivable case.
        owner_room = ObjectDBFactory(db_key="OwnerRoom", db_typeclass_path="typeclasses.rooms.Room")
        x_room = ObjectDBFactory(db_key="XRoom", db_typeclass_path="typeclasses.rooms.Room")
        owner.character.location = owner_room
        x_sheet.character.location = x_room

        resolved = resolve_pull_effects([thread], tier=1, in_combat=True, target=x_sheet.character)

        flat_rows = [r for r in resolved if r.kind == EffectKind.FLAT_BONUS]
        # Same bonus (14) as the perceivable indirect-trigger test -- no gate here.
        self.assertEqual(flat_rows[0].scaled_value, 14)


class RelationshipTrackPassthroughTests(TestCase):
    """target=None passthrough for RELATIONSHIP_TRACK pulls (#1831 Task 2 guarantee,
    extended to this target_kind)."""

    def test_relationship_track_pull_with_no_target_is_unchanged(self) -> None:
        owner = CharacterSheetFactory()
        threaded_sheet = CharacterSheetFactory()
        thread = _relationship_track_thread(
            owner=owner, threaded_sheet=threaded_sheet, invested_depth=30
        )
        RelationshipBondPullTuning.objects.create(pk=1, coefficient=1, cap=20, half_saturation=30)
        ThreadPullEffectFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            resonance=thread.resonance,
            tier=1,
            min_thread_level=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=4,
        )

        resolved = resolve_pull_effects([thread], tier=1, in_combat=True, target=None)

        flat_rows = [r for r in resolved if r.kind == EffectKind.FLAT_BONUS]
        self.assertEqual(flat_rows[0].scaled_value, 4)


class RelationshipBondModulationFraughtDevotionTests(TestCase):
    """Acceptance matrix for the fraught + devotion differential terms (#2034, #3957).

    All cases call ``relationship_bond_modulation`` directly (rather than through
    ``resolve_pull_effects``) so the assertions isolate the bond-investment math
    from the pull-tier/level-multiplier machinery -- ``effect_row`` is unused by
    the function (kept only for call-site parity, see its ``# noqa: ARG001``) so
    tests pass ``None``. Every case uses tuning defaults
    (coefficient=1/cap=20/half=30; fraught_coefficient=1/cap=10/half=30;
    devotion_threshold=60/coefficient=1/cap=10/half=30).
    """

    def test_mixed_valence_out_earns_single_valence_same_total(self) -> None:
        """Same pair_depth (80) split two ways: bond A mixes 40 affection + 40
        conflict (fraught term fires); bond B is pure 80 affection (fraught term
        is 0). Base + devotion terms are identical for both -- only the mixed
        bond's fraught bonus tips the total."""
        RelationshipBondPullTuning.objects.create(pk=1)
        owner_a = CharacterSheetFactory()
        target_a = CharacterSheetFactory()
        thread_a = _bond_with_affection_conflict(
            owner=owner_a, threaded_sheet=target_a, affection=40, conflict=40
        )
        owner_b = CharacterSheetFactory()
        target_b = CharacterSheetFactory()
        thread_b = _bond_with_affection_conflict(
            owner=owner_b, threaded_sheet=target_b, affection=80, conflict=0
        )

        total_a = relationship_bond_modulation(thread_a, target_a.character, None, base_scaled=0)
        total_b = relationship_bond_modulation(thread_b, target_b.character, None, base_scaled=0)

        # base: round(20*80/110) = 15; devotion: round(10*20/50) = 4 -- identical
        # for both (same depth=80). fraught A: round(10*40/70) = 6; fraught B: 0.
        self.assertEqual(total_a, 15 + 6 + 4)
        self.assertEqual(total_b, 15 + 0 + 4)
        self.assertGreater(total_a, total_b)

    def test_beyond_threshold_depth_out_earns_at_threshold(self) -> None:
        """A bond exactly at devotion_threshold (depth=60) gets no devotion bonus;
        one 40 past it (depth=100) does, and the *total* gap between them exceeds
        what the base curve's own delta would give alone."""
        RelationshipBondPullTuning.objects.create(pk=1)
        owner_at = CharacterSheetFactory()
        target_at = CharacterSheetFactory()
        thread_at_threshold = _bond_with_affection_conflict(
            owner=owner_at, threaded_sheet=target_at, affection=60, conflict=0
        )
        owner_deep = CharacterSheetFactory()
        target_deep = CharacterSheetFactory()
        thread_deep = _bond_with_affection_conflict(
            owner=owner_deep, threaded_sheet=target_deep, affection=100, conflict=0
        )

        total_at_threshold = relationship_bond_modulation(
            thread_at_threshold, target_at.character, None, base_scaled=0
        )
        total_deep = relationship_bond_modulation(
            thread_deep, target_deep.character, None, base_scaled=0
        )

        # base@60: round(20*60/90) = 13; base@100: round(20*100/130) = 15 (delta 2).
        # devotion@60: max(0,0)=0 -> 0. devotion@100: round(10*40/70) = 6.
        self.assertEqual(total_at_threshold, 13 + 0)
        self.assertEqual(total_deep, 15 + 6)
        base_curve_delta = 15 - 13
        total_delta = total_deep - total_at_threshold
        self.assertGreater(total_delta, base_curve_delta)

    def test_shallow_bond_unchanged_from_baseline(self) -> None:
        """A shallow single-valence bond (10 affection) is far below both the
        fraught (needs both gauges) and devotion (needs depth>60) gates -- the
        function must return exactly today's pre-change value: base_scaled +
        soft_cap on the base term alone."""
        RelationshipBondPullTuning.objects.create(pk=1)
        owner = CharacterSheetFactory()
        target = CharacterSheetFactory()
        thread = _bond_with_affection_conflict(
            owner=owner, threaded_sheet=target, affection=10, conflict=0
        )

        total = relationship_bond_modulation(thread, target.character, None, base_scaled=4)

        # Pre-change expectation: base_scaled + _soft_cap(1*10, 20, 30)
        # = 4 + round(200/40) = 4 + 5 = 9.
        self.assertEqual(total, 9)

    def test_pure_conflict_deep_gets_no_fraught_term(self) -> None:
        """A deep bond invested entirely in Conflict (80) gets no fraught term
        (needs both gauges) and totals exactly the same as its pure-Affection
        twin (80) -- the base term is sign-blind."""
        RelationshipBondPullTuning.objects.create(pk=1)
        owner_neg = CharacterSheetFactory()
        target_neg = CharacterSheetFactory()
        thread_neg = _bond_with_affection_conflict(
            owner=owner_neg, threaded_sheet=target_neg, affection=0, conflict=80
        )
        owner_pos = CharacterSheetFactory()
        target_pos = CharacterSheetFactory()
        thread_pos = _bond_with_affection_conflict(
            owner=owner_pos, threaded_sheet=target_pos, affection=80, conflict=0
        )

        total_neg = relationship_bond_modulation(
            thread_neg, target_neg.character, None, base_scaled=0
        )
        total_pos = relationship_bond_modulation(
            thread_pos, target_pos.character, None, base_scaled=0
        )

        # base: round(20*80/110) = 15; devotion: round(10*20/50) = 4; fraught: 0.
        self.assertEqual(total_neg, 15 + 4)
        self.assertEqual(total_neg, total_pos)

    def test_tuning_row_edit_moves_the_fraught_bonus(self) -> None:
        """Staff-tunable without deploy: bumping fraught_cap on the singleton
        moves the bonus on the next call -- mirrors the get_*_config() /
        mutate-in-place / .save() precedent used by other singleton tuning
        tests (e.g. test_soul_tether_config.py)."""
        RelationshipBondPullTuning.objects.create(pk=1)
        owner = CharacterSheetFactory()
        target = CharacterSheetFactory()
        thread = _bond_with_affection_conflict(
            owner=owner, threaded_sheet=target, affection=40, conflict=40
        )

        total_before = relationship_bond_modulation(thread, target.character, None, base_scaled=0)

        cfg = get_relationship_bond_pull_tuning()
        cfg.fraught_cap = 100
        cfg.save()

        total_after = relationship_bond_modulation(thread, target.character, None, base_scaled=0)

        self.assertNotEqual(total_before, total_after)
        self.assertGreater(total_after, total_before)

    def test_devotion_keys_on_depth_not_affection(self) -> None:
        """Devotion is keyed on ``pair_depth()``, not the affection gauge (review
        Minor 11, #3957). Move depth alone (invested_depth=100, gauges at 0/0,
        devotion must fire past devotion_threshold=60) versus affection alone
        (affection=100, invested_depth stays 0, devotion must NOT fire since it
        never reads affection/conflict -- only ``depth``)."""
        RelationshipBondPullTuning.objects.create(pk=1)

        owner_depth = CharacterSheetFactory()
        target_depth = CharacterSheetFactory()
        thread_depth = _relationship_track_thread(
            owner=owner_depth, threaded_sheet=target_depth, invested_depth=100
        )
        total_depth = relationship_bond_modulation(
            thread_depth, target_depth.character, None, base_scaled=0
        )

        owner_affection = CharacterSheetFactory()
        target_affection = CharacterSheetFactory()
        thread_affection = _relationship_track_thread(
            owner=owner_affection, threaded_sheet=target_affection, invested_depth=0
        )
        bond_affection = owner_affection.relationships_as_source.get(target=target_affection)
        bond_affection.affection = 100
        bond_affection.save()
        total_affection = relationship_bond_modulation(
            thread_affection, target_affection.character, None, base_scaled=0
        )

        # base@depth=100: round(20*100/130) = 15; devotion@depth=100: max(0,40) ->
        # round(10*40/70) = 6; fraught: min(0,0)=0 -> 0.
        self.assertEqual(total_depth, 15 + 6)
        # base@depth=0: 0; devotion@depth=0: max(0,0-60)=0 -> 0; fraught:
        # min(affection=100, conflict=0)=0 -> 0. Affection alone moves nothing.
        self.assertEqual(total_affection, 0)
        self.assertGreater(total_depth, total_affection)


class CompanionTargetedThreadTests(TestCase):
    """A thread woven on a companion-targeted side earns no bond term (#3575)."""

    def test_modulation_passes_through_for_companion_bond(self) -> None:
        from world.companions.factories import CompanionFactory

        owner = CharacterSheetFactory()
        companion = CompanionFactory(owner=owner)
        relationship = CharacterRelationshipFactory(
            source=owner, target=None, target_companion=companion, is_active=True
        )
        thread = ThreadFactory(
            owner=owner,
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            target_relationship=relationship,
            target_trait=None,
            level=10,
        )
        effect = ThreadPullEffectFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            resonance=thread.resonance,
            effect_kind=EffectKind.FLAT_BONUS,
        )
        live_target = CharacterSheetFactory().character
        self.assertEqual(relationship_bond_modulation(thread, live_target, effect, 7), 7)
