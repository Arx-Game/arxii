"""Tests for RELATIONSHIP_TRACK pull modulation (#1849).

Mirrors world/magic/tests/test_pull_modulation_passthrough.py's structure and
world/magic/services/pull_modulation_court.py's shape, but this rule has no
polarity gate (Decisions 3/4 in the #1849 spec) and reads CharacterRelationship
instead of NpcRegard.
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import EffectKind, TargetKind
from world.magic.factories import ThreadFactory, ThreadPullEffectFactory
from world.magic.models import RelationshipBondPullTuning
from world.magic.services.resonance import resolve_pull_effects
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipTrackProgressFactory,
)


def _relationship_track_thread(*, owner, threaded_sheet, developed_points: int = 0):
    """Build a RELATIONSHIP_TRACK thread owned by `owner`, anchored to a relationship
    where `owner` is source and `threaded_sheet` is target."""
    relationship = CharacterRelationshipFactory(
        source=owner, target=threaded_sheet, is_active=True, is_pending=False
    )
    progress = RelationshipTrackProgressFactory(
        relationship=relationship, developed_points=developed_points
    )
    return ThreadFactory(
        owner=owner,
        target_kind=TargetKind.RELATIONSHIP_TRACK,
        target_relationship_track=progress,
        target_trait=None,
        level=10,
    )


class RelationshipBondModulationDirectTriggerTests(TestCase):
    """Live target IS the threaded person Y."""

    def test_direct_target_empowers_pull_by_saturating_curve(self) -> None:
        owner = CharacterSheetFactory()
        threaded_sheet = CharacterSheetFactory()
        thread = _relationship_track_thread(
            owner=owner, threaded_sheet=threaded_sheet, developed_points=0
        )
        # Owner's own bond to Y is the relationship _relationship_track_thread already
        # created as the anchor (unique_relationship_pair forbids a second
        # (owner, threaded_sheet) row) -- add a second track's progress to it.
        bond_relationship = owner.relationships_as_source.get(target=threaded_sheet)
        RelationshipTrackProgressFactory(relationship=bond_relationship, developed_points=30)
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
        # S = 1*30 = 30; bonus = round(20*30/(30+30)) = round(10.0) = 10.
        # scaled_value = 4 + 10 = 14.
        self.assertEqual(flat_rows[0].scaled_value, 14)

    def test_no_owner_to_threaded_person_relationship_leaves_unchanged(self) -> None:
        owner = CharacterSheetFactory()
        threaded_sheet = CharacterSheetFactory()
        # thread anchors owner's relationship-track thread, but there is no SEPARATE
        # owner->threaded_sheet CharacterRelationship row with developed points beyond
        # the one created for the anchor itself (developed_points=0 by default).
        thread = _relationship_track_thread(
            owner=owner, threaded_sheet=threaded_sheet, developed_points=0
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
        # developed_points=0 -> S=0 -> _soft_cap returns 0 -> bonus 0 -> unchanged.
        self.assertEqual(flat_rows[0].scaled_value, 4)


class RelationshipBondModulationIndirectTriggerTests(TestCase):
    """Live target is a third party X hostile toward the threaded person Y."""

    def test_hostile_third_party_target_empowers_via_owner_bond(self) -> None:
        owner = CharacterSheetFactory()
        threaded_sheet = CharacterSheetFactory()
        thread = _relationship_track_thread(
            owner=owner, threaded_sheet=threaded_sheet, developed_points=0
        )
        # Owner's own bond to Y: 30 developed points.
        bond_relationship = owner.relationships_as_source.get(target=threaded_sheet)
        RelationshipTrackProgressFactory(relationship=bond_relationship, developed_points=30)
        RelationshipBondPullTuning.objects.create(pk=1, coefficient=1, cap=20, half_saturation=30)
        # X (a third party) is net-negative toward Y.
        x_sheet = CharacterSheetFactory()
        from world.relationships.constants import TrackSign
        from world.relationships.factories import RelationshipTrackFactory

        hostile_relationship = CharacterRelationshipFactory(
            source=x_sheet, target=threaded_sheet, is_active=True, is_pending=False
        )
        negative_track = RelationshipTrackFactory(sign=TrackSign.NEGATIVE)
        RelationshipTrackProgressFactory(
            relationship=hostile_relationship, track=negative_track, developed_points=10
        )
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
        # bond to Y (30 points), never X's hostility magnitude (10 points).
        self.assertEqual(flat_rows[0].scaled_value, 14)

    def test_indirect_trigger_magnitude_unaffected_by_x_hostility_size(self) -> None:
        """Changing X's hostility magnitude doesn't change the bonus size, only
        whether it fires — the scale is always the owner's own bond to Y."""
        owner = CharacterSheetFactory()
        threaded_sheet = CharacterSheetFactory()
        thread = _relationship_track_thread(
            owner=owner, threaded_sheet=threaded_sheet, developed_points=0
        )
        bond_relationship = owner.relationships_as_source.get(target=threaded_sheet)
        RelationshipTrackProgressFactory(relationship=bond_relationship, developed_points=30)
        RelationshipBondPullTuning.objects.create(pk=1, coefficient=1, cap=20, half_saturation=30)
        x_sheet = CharacterSheetFactory()
        from world.relationships.constants import TrackSign
        from world.relationships.factories import RelationshipTrackFactory

        hostile_relationship = CharacterRelationshipFactory(
            source=x_sheet, target=threaded_sheet, is_active=True, is_pending=False
        )
        negative_track = RelationshipTrackFactory(sign=TrackSign.NEGATIVE)
        # Very high hostility magnitude (1000 points) -- bonus must still be 14.
        RelationshipTrackProgressFactory(
            relationship=hostile_relationship, track=negative_track, developed_points=1000
        )
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
        """X exists, has no relationship (or a positive one) toward Y, and isn't Y:
        neither trigger condition holds -> no-op."""
        owner = CharacterSheetFactory()
        threaded_sheet = CharacterSheetFactory()
        thread = _relationship_track_thread(
            owner=owner, threaded_sheet=threaded_sheet, developed_points=0
        )
        bond_relationship = owner.relationships_as_source.get(target=threaded_sheet)
        RelationshipTrackProgressFactory(relationship=bond_relationship, developed_points=30)
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


class RelationshipBondModulationPendingInactiveTests(TestCase):
    """Pending (never-consented) or broken-off relationships must not count."""

    def test_pending_owner_to_y_relationship_does_not_reward(self) -> None:
        owner = CharacterSheetFactory()
        threaded_sheet = CharacterSheetFactory()
        thread = _relationship_track_thread(
            owner=owner, threaded_sheet=threaded_sheet, developed_points=0
        )
        RelationshipBondPullTuning.objects.create(pk=1, coefficient=1, cap=20, half_saturation=30)
        # Owner->Y relationship is the anchor _relationship_track_thread already
        # created (unique_relationship_pair forbids a second row for this pair) --
        # flip it to PENDING (never mutually consented) and add developed points.
        pending_relationship = owner.relationships_as_source.get(target=threaded_sheet)
        pending_relationship.is_pending = True
        pending_relationship.save(update_fields=["is_pending"])
        RelationshipTrackProgressFactory(relationship=pending_relationship, developed_points=30)
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
            owner=owner, threaded_sheet=threaded_sheet, developed_points=0
        )
        bond_relationship = owner.relationships_as_source.get(target=threaded_sheet)
        RelationshipTrackProgressFactory(relationship=bond_relationship, developed_points=30)
        RelationshipBondPullTuning.objects.create(pk=1, coefficient=1, cap=20, half_saturation=30)
        x_sheet = CharacterSheetFactory()
        from world.relationships.constants import TrackSign
        from world.relationships.factories import RelationshipTrackFactory

        # X->Y relationship is hostile but INACTIVE (broken off) -- must not trigger.
        broken_off_relationship = CharacterRelationshipFactory(
            source=x_sheet, target=threaded_sheet, is_active=False, is_pending=False
        )
        negative_track = RelationshipTrackFactory(sign=TrackSign.NEGATIVE)
        RelationshipTrackProgressFactory(
            relationship=broken_off_relationship, track=negative_track, developed_points=10
        )
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
        from evennia.objects.models import ObjectDB

        owner = CharacterSheetFactory()
        threaded_sheet = CharacterSheetFactory()
        thread = _relationship_track_thread(
            owner=owner, threaded_sheet=threaded_sheet, developed_points=0
        )
        bond_relationship = owner.relationships_as_source.get(target=threaded_sheet)
        RelationshipTrackProgressFactory(relationship=bond_relationship, developed_points=30)
        RelationshipBondPullTuning.objects.create(pk=1, coefficient=1, cap=20, half_saturation=30)
        x_sheet = CharacterSheetFactory()
        from world.relationships.constants import TrackSign
        from world.relationships.factories import RelationshipTrackFactory

        hostile_relationship = CharacterRelationshipFactory(
            source=x_sheet, target=threaded_sheet, is_active=True, is_pending=False
        )
        negative_track = RelationshipTrackFactory(sign=TrackSign.NEGATIVE)
        RelationshipTrackProgressFactory(
            relationship=hostile_relationship, track=negative_track, developed_points=10
        )
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
        owner_room = ObjectDB.objects.create(
            db_key="OwnerRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        x_room = ObjectDB.objects.create(db_key="XRoom", db_typeclass_path="typeclasses.rooms.Room")
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
            owner=owner, threaded_sheet=threaded_sheet, developed_points=0
        )
        bond_relationship = owner.relationships_as_source.get(target=threaded_sheet)
        RelationshipTrackProgressFactory(relationship=bond_relationship, developed_points=30)
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
