"""Tests for the RELATIONSHIP_NO_STAKE picker inapplicability signal (#1849).

Mirrors world/magic/tests/test_pull_applicability_court.py's structure.
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import EffectKind, InapplicabilityReason, TargetKind
from world.magic.factories import ThreadFactory, ThreadPullEffectFactory
from world.magic.models import RelationshipBondPullTuning
from world.magic.services.pull_applicability import (
    PullActionContext,
    compute_thread_applicability,
)
from world.relationships.constants import TrackSign
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipTrackFactory,
    RelationshipTrackProgressFactory,
)
from world.scenes.services import active_persona_for_sheet


def _context(target_persona_id: int | None) -> PullActionContext:
    return PullActionContext(
        technique=None, effect_type_id=None, target_persona_id=target_persona_id, scene_id=None
    )


def _relationship_track_thread(*, owner, threaded_sheet):
    relationship = CharacterRelationshipFactory(
        source=owner, target=threaded_sheet, is_active=True, is_pending=False
    )
    progress = RelationshipTrackProgressFactory(relationship=relationship, developed_points=0)
    return ThreadFactory(
        owner=owner,
        target_kind=TargetKind.RELATIONSHIP_TRACK,
        target_relationship_track=progress,
        target_trait=None,
        level=10,
    )


class RelationshipNoStakeApplicabilityTests(TestCase):
    """Applicability rule for RELATIONSHIP_TRACK threads gated on the shared trigger check."""

    def test_no_stake_when_target_is_unrelated_third_party(self) -> None:
        owner = CharacterSheetFactory()
        threaded_sheet = CharacterSheetFactory()
        thread = _relationship_track_thread(owner=owner, threaded_sheet=threaded_sheet)
        ThreadPullEffectFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            resonance=thread.resonance,
            effect_kind=EffectKind.FLAT_BONUS,
        )
        unrelated_sheet = CharacterSheetFactory()
        context = _context(active_persona_for_sheet(unrelated_sheet).pk)

        rows = compute_thread_applicability(owner, context)

        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0].applicable)
        self.assertEqual(rows[0].reason, InapplicabilityReason.RELATIONSHIP_NO_STAKE.value)

    def test_applicable_when_target_is_threaded_person_directly(self) -> None:
        owner = CharacterSheetFactory()
        threaded_sheet = CharacterSheetFactory()
        thread = _relationship_track_thread(owner=owner, threaded_sheet=threaded_sheet)
        ThreadPullEffectFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            resonance=thread.resonance,
            effect_kind=EffectKind.FLAT_BONUS,
        )
        # Owner needs an active bond to threaded_sheet for step-4 "has a rewardable
        # bond" to pass, else it's equally a no-stake case. _relationship_track_thread
        # already created the owner->threaded_sheet CharacterRelationship (as the
        # thread's own anchor) -- CharacterRelationship has a unique_relationship_pair
        # constraint on (source, target), so add a SECOND track's progress to that
        # SAME relationship rather than creating a new one.
        bond = owner.relationships_as_source.get(target=threaded_sheet)
        RelationshipTrackProgressFactory(relationship=bond, developed_points=10)
        RelationshipBondPullTuning.objects.create(pk=1)
        context = _context(active_persona_for_sheet(threaded_sheet).pk)

        rows = compute_thread_applicability(owner, context)

        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].applicable)
        self.assertIsNone(rows[0].reason)

    def test_applicable_when_target_is_hostile_third_party(self) -> None:
        owner = CharacterSheetFactory()
        threaded_sheet = CharacterSheetFactory()
        thread = _relationship_track_thread(owner=owner, threaded_sheet=threaded_sheet)
        ThreadPullEffectFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            resonance=thread.resonance,
            effect_kind=EffectKind.FLAT_BONUS,
        )
        # Same unique-pair note as above: reuse the anchor's own relationship.
        bond = owner.relationships_as_source.get(target=threaded_sheet)
        RelationshipTrackProgressFactory(relationship=bond, developed_points=10)
        RelationshipBondPullTuning.objects.create(pk=1)
        x_sheet = CharacterSheetFactory()
        hostile = CharacterRelationshipFactory(
            source=x_sheet, target=threaded_sheet, is_active=True, is_pending=False
        )
        negative_track = RelationshipTrackFactory(sign=TrackSign.NEGATIVE)
        RelationshipTrackProgressFactory(
            relationship=hostile, track=negative_track, developed_points=5
        )
        context = _context(active_persona_for_sheet(x_sheet).pk)

        rows = compute_thread_applicability(owner, context)

        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].applicable)
        self.assertIsNone(rows[0].reason)

    def test_no_stake_when_owner_has_no_rewardable_bond_even_if_target_is_y(self) -> None:
        """Trigger holds (target IS Y) but the owner's bond to Y is still PENDING
        (never mutually consented) -- equally a no-stake case per Design step 4.

        Note: the thread's own anchor relationship (owner->threaded_sheet) can't be
        deleted here -- Thread.target_relationship_track is on_delete=PROTECT, so
        deleting the relationship it anchors on would raise ProtectedError. Instead,
        flip the anchor relationship itself to pending, which is a realistic shape
        (the thread was woven before the relationship's mutual-consent handshake
        completed) and correctly fails the is_pending=False filter.
        """
        owner = CharacterSheetFactory()
        threaded_sheet = CharacterSheetFactory()
        thread = _relationship_track_thread(owner=owner, threaded_sheet=threaded_sheet)
        ThreadPullEffectFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            resonance=thread.resonance,
            effect_kind=EffectKind.FLAT_BONUS,
        )
        anchor_relationship = thread.target_relationship_track.relationship
        anchor_relationship.is_pending = True
        anchor_relationship.save(update_fields=["is_pending"])
        context = _context(active_persona_for_sheet(threaded_sheet).pk)

        rows = compute_thread_applicability(owner, context)

        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0].applicable)
        self.assertEqual(rows[0].reason, InapplicabilityReason.RELATIONSHIP_NO_STAKE.value)


class RelationshipNoStakePrivacyTests(TestCase):
    """#1849 privacy gate: the indirect trigger must not leak X's hostility toward Y
    when the owner can't perceive X."""

    def test_no_leak_when_owner_cannot_perceive_hostile_target(self) -> None:
        from evennia.objects.models import ObjectDB

        owner = CharacterSheetFactory()
        threaded_sheet = CharacterSheetFactory()
        thread = _relationship_track_thread(owner=owner, threaded_sheet=threaded_sheet)
        ThreadPullEffectFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            resonance=thread.resonance,
            effect_kind=EffectKind.FLAT_BONUS,
        )
        # Reuse the anchor's own owner->threaded_sheet relationship (unique_relationship_pair).
        bond = owner.relationships_as_source.get(target=threaded_sheet)
        RelationshipTrackProgressFactory(relationship=bond, developed_points=10)
        RelationshipBondPullTuning.objects.create(pk=1)
        x_sheet = CharacterSheetFactory()
        hostile = CharacterRelationshipFactory(
            source=x_sheet, target=threaded_sheet, is_active=True, is_pending=False
        )
        negative_track = RelationshipTrackFactory(sign=TrackSign.NEGATIVE)
        RelationshipTrackProgressFactory(
            relationship=hostile, track=negative_track, developed_points=5
        )
        owner_room = ObjectDB.objects.create(
            db_key="OwnerRoom2", db_typeclass_path="typeclasses.rooms.Room"
        )
        x_room = ObjectDB.objects.create(
            db_key="XRoom2", db_typeclass_path="typeclasses.rooms.Room"
        )
        owner.character.location = owner_room
        x_sheet.character.location = x_room
        context = _context(active_persona_for_sheet(x_sheet).pk)

        rows = compute_thread_applicability(owner, context)

        # Treated as applicable (no leak) rather than surfacing RELATIONSHIP_NO_STAKE,
        # mirroring _court_pull_would_have_effect's can-perceive fallback.
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].applicable)
        self.assertIsNone(rows[0].reason)
