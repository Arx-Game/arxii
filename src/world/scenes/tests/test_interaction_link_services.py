"""Tests for the POSE→ACTION auto-link service."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from world.scenes.constants import InteractionMode
from world.scenes.factories import (
    InteractionActionFactory,
    InteractionFactory,
    PersonaFactory,
    SceneFactory,
)
from world.scenes.interaction_link_services import auto_link_pose_to_actions
from world.scenes.models import Interaction, InteractionAction, Persona, Scene


def _make_interaction(
    *,
    scene: Scene,
    persona: Persona,
    mode: str,
    ts_offset_seconds: int,
    base_ts: "timezone.datetime",
) -> Interaction:
    """Create an Interaction with a controlled timestamp.

    InteractionFactory uses auto_now_add which can produce identical microsecond
    timestamps in fast test runs. We set the timestamp explicitly via .update()
    and then mutate the in-memory instance so callers see the updated timestamp
    without needing a fresh DB fetch (which would go through the SharedMemoryModel
    identity map and return the stale cached instance).
    """
    row = InteractionFactory(scene=scene, persona=persona, mode=mode)
    target_ts = base_ts + timedelta(seconds=ts_offset_seconds)
    Interaction.objects.filter(pk=row.pk).update(timestamp=target_ts)
    # Mutate the in-memory instance directly — the .update() above set the DB
    # value; we sync the Python object without going through the identity map.
    row.timestamp = target_ts
    return row


class AutoLinkPoseToActionsTests(TestCase):
    """Service-level tests for auto_link_pose_to_actions.

    Uses setUp (not setUpTestData) to create fresh fixture objects per test,
    avoiding SharedMemoryModel identity-map contamination from PK recycling
    (SQLite recycles PKs after Django TestCase's per-test transaction rollback).
    """

    def setUp(self) -> None:
        # Flush ALL SharedMemoryModel caches before each test. Django TestCase
        # wraps each test in a transaction that is rolled back; SQLite recycles
        # PKs after rollback. Without flushing, SharedMemoryModelBase.__call__
        # returns stale cached instances for recycled PKs across all models
        # (Interaction, Persona, Scene, etc.), causing wrong field values to
        # leak across tests via the identity map.
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()
        self.scene = SceneFactory()
        self.persona = PersonaFactory()
        self.base_ts = timezone.now() - timedelta(hours=1)

    def test_links_actions_since_last_pose(self) -> None:
        action_a = _make_interaction(
            scene=self.scene,
            persona=self.persona,
            mode=InteractionMode.ACTION,
            ts_offset_seconds=1,
            base_ts=self.base_ts,
        )
        action_b = _make_interaction(
            scene=self.scene,
            persona=self.persona,
            mode=InteractionMode.ACTION,
            ts_offset_seconds=2,
            base_ts=self.base_ts,
        )
        pose = _make_interaction(
            scene=self.scene,
            persona=self.persona,
            mode=InteractionMode.POSE,
            ts_offset_seconds=10,
            base_ts=self.base_ts,
        )

        auto_link_pose_to_actions(pose)

        links = list(InteractionAction.objects.filter(pose=pose).order_by("ordering"))
        self.assertEqual(
            {link.action_interaction_id for link in links},
            {action_a.pk, action_b.pk},
        )

    def test_does_not_link_actions_from_other_personas(self) -> None:
        other_persona = PersonaFactory()
        _make_interaction(
            scene=self.scene,
            persona=other_persona,
            mode=InteractionMode.ACTION,
            ts_offset_seconds=1,
            base_ts=self.base_ts,
        )
        pose = _make_interaction(
            scene=self.scene,
            persona=self.persona,
            mode=InteractionMode.POSE,
            ts_offset_seconds=10,
            base_ts=self.base_ts,
        )
        auto_link_pose_to_actions(pose)
        self.assertEqual(InteractionAction.objects.filter(pose=pose).count(), 0)

    def test_does_not_link_actions_from_other_scenes(self) -> None:
        other_scene = SceneFactory()
        _make_interaction(
            scene=other_scene,
            persona=self.persona,
            mode=InteractionMode.ACTION,
            ts_offset_seconds=1,
            base_ts=self.base_ts,
        )
        pose = _make_interaction(
            scene=self.scene,
            persona=self.persona,
            mode=InteractionMode.POSE,
            ts_offset_seconds=10,
            base_ts=self.base_ts,
        )
        auto_link_pose_to_actions(pose)
        self.assertEqual(InteractionAction.objects.filter(pose=pose).count(), 0)

    def test_does_not_link_actions_already_attached_to_prior_pose(self) -> None:
        """Actions linked to a prior pose are excluded from subsequent auto-link."""
        # Create a prior POSE and an ACTION linked to it (simulating a prior auto-link).
        prior_pose = _make_interaction(
            scene=self.scene,
            persona=self.persona,
            mode=InteractionMode.POSE,
            ts_offset_seconds=5,
            base_ts=self.base_ts,
        )
        action_already_linked = _make_interaction(
            scene=self.scene,
            persona=self.persona,
            mode=InteractionMode.ACTION,
            ts_offset_seconds=1,
            base_ts=self.base_ts,
        )
        # Directly attach action_already_linked to prior_pose via the bridge.
        InteractionActionFactory(pose=prior_pose, action_interaction=action_already_linked)

        # A second unlinked action comes after the prior pose.
        action_new = _make_interaction(
            scene=self.scene,
            persona=self.persona,
            mode=InteractionMode.ACTION,
            ts_offset_seconds=10,
            base_ts=self.base_ts,
        )
        second_pose = _make_interaction(
            scene=self.scene,
            persona=self.persona,
            mode=InteractionMode.POSE,
            ts_offset_seconds=20,
            base_ts=self.base_ts,
        )

        auto_link_pose_to_actions(second_pose)

        # Only action_new should attach; action_already_linked is excluded.
        links = list(InteractionAction.objects.filter(pose=second_pose))
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].action_interaction_id, action_new.pk)

    def test_no_op_on_non_pose_interaction(self) -> None:
        # Defensive: passing a non-POSE Interaction is a programmer error
        # but the service should no-op rather than write garbage.
        action = _make_interaction(
            scene=self.scene,
            persona=self.persona,
            mode=InteractionMode.ACTION,
            ts_offset_seconds=1,
            base_ts=self.base_ts,
        )
        result = auto_link_pose_to_actions(action)
        self.assertEqual(result, [])
        self.assertEqual(InteractionAction.objects.count(), 0)
