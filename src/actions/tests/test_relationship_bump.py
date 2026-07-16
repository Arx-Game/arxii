"""Tests for RelationshipBumpAction (#1699): backfill anchoring + both doors' kwargs."""

from django.test import TestCase
from evennia.utils.idmapper import models as idmapper_models

from actions.definitions.relationships import RelationshipBumpAction
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.relationships.constants import BumpValence, TrackSign, TrackSystemKey
from world.relationships.factories import RelationshipTrackFactory
from world.relationships.models import CharacterRelationship, RelationshipBump
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import InteractionMode
from world.scenes.factories import (
    InteractionFactory,
    SceneFactory,
    SceneParticipationFactory,
)


def _char_with_account(room):
    char = CharacterFactory()
    char.location = room
    char.save()
    sheet = CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet=sheet)
    tenure = RosterTenureFactory(roster_entry=entry)
    return char, sheet, tenure.player_data.account


class RelationshipBumpActionTests(TestCase):
    """Backfill anchoring, budget exhaustion, and explicit-interaction dispatch."""

    def setUp(self) -> None:
        idmapper_models.flush_cache()
        RelationshipTrackFactory(
            name="Regard", sign=TrackSign.POSITIVE, system_key=TrackSystemKey.REGARD
        )
        RelationshipTrackFactory(
            name="Friction", sign=TrackSign.NEGATIVE, system_key=TrackSystemKey.FRICTION
        )
        self.room = ObjectDBFactory(db_key="TestRoom", db_typeclass_path="typeclasses.rooms.Room")
        self.scene = SceneFactory(location=self.room, is_active=True)
        self.actor, self.actor_sheet, self.actor_account = _char_with_account(self.room)
        self.target, self.target_sheet, self.target_account = _char_with_account(self.room)
        SceneParticipationFactory(scene=self.scene, account=self.actor_account)
        SceneParticipationFactory(scene=self.scene, account=self.target_account)

    def _pose(self):
        return InteractionFactory(
            scene=self.scene,
            persona=self.target_sheet.primary_persona,
            mode=InteractionMode.POSE,
        )

    def test_backfill_anchors_newest_unbumped_pose(self) -> None:
        first = self._pose()
        second = self._pose()
        result = RelationshipBumpAction().run(
            actor=self.actor, target_sheet=self.target_sheet, valence=1
        )
        self.assertTrue(result.success, result.message)
        bump = RelationshipBump.objects.get()
        self.assertEqual(bump.interaction_id, second.pk)
        self.assertEqual(bump.valence, BumpValence.POSITIVE)

        # Second bump backfills to the older pose.
        result = RelationshipBumpAction().run(
            actor=self.actor, target_sheet=self.target_sheet, valence=-1
        )
        self.assertTrue(result.success, result.message)
        self.assertEqual(
            set(RelationshipBump.objects.values_list("interaction_id", flat=True)),
            {first.pk, second.pk},
        )

    def test_budget_exhaustion_message(self) -> None:
        self._pose()
        action = RelationshipBumpAction()
        first = action.run(actor=self.actor, target_sheet=self.target_sheet, valence=1)
        self.assertTrue(first.success, first.message)
        second = action.run(actor=self.actor, target_sheet=self.target_sheet, valence=1)
        self.assertFalse(second.success)
        self.assertIn("already acknowledged", second.message)

    def test_no_scene_fails_cleanly(self) -> None:
        self.scene.is_active = False
        self.scene.save()
        result = RelationshipBumpAction().run(
            actor=self.actor, target_sheet=self.target_sheet, valence=1
        )
        self.assertFalse(result.success)

    def test_explicit_interaction_kwarg_used_directly(self) -> None:
        pose = self._pose()
        result = RelationshipBumpAction().run(
            actor=self.actor,
            target_sheet=self.target_sheet,
            valence=1,
            interaction=pose,
        )
        self.assertTrue(result.success, result.message)
        self.assertEqual(RelationshipBump.objects.get().interaction_id, pose.pk)

    def test_self_target_rejected(self) -> None:
        result = RelationshipBumpAction().run(
            actor=self.actor, target_sheet=self.actor_sheet, valence=1
        )
        self.assertFalse(result.success)
        self.assertEqual(CharacterRelationship.objects.count(), 0)
