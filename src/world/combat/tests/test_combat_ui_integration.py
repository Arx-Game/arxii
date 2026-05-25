"""Full UI round-trip integration test — Phase 12 Task 12.1.

End-to-end backend integration:
1. Dispatch a clash contribution via ActionRef → ClashContributionDeclaration written.
2. Commit a thread pull → CombatPull created with M2M thread association.
3. Submit a POSE that auto-links prior ACTION Interactions.
4. Assert the full data-model state.

No mocking — all steps use real DB state via factories.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from actions.player_interface import dispatch_player_action
from actions.types import ActionBackend, ActionRef
from world.combat.constants import ClashActionSlot, ClashStatus, EncounterStatus
from world.combat.factories import (
    ClashConfigFactory,
    ClashFactory,
    CombatEncounterFactory,
    CombatParticipantFactory,
    CombatPullFactory,
)
from world.combat.models import (
    ClashContributionDeclaration,
    CombatPull,
)
from world.magic.factories import TechniqueFactory, ThreadFactory
from world.scenes.constants import InteractionMode
from world.scenes.factories import InteractionFactory, SceneFactory
from world.scenes.interaction_link_services import auto_link_pose_to_actions
from world.scenes.models import Interaction, InteractionAction


class CombatUIRoundTripIntegrationTests(TestCase):
    """Full data-model round-trip: clash dispatch → pull commit → pose auto-link.

    Uses setUp (not setUpTestData) for objects that involve Evennia ObjectDB —
    ObjectDB is not deepcopyable by Django's setUpTestData machinery.
    SharedMemoryModel identity-map is flushed at the start of each test to
    prevent stale cached instances leaking across tests in SQLite runs (SQLite
    recycles PKs after Django TestCase's per-test transaction rollback).
    """

    def setUp(self) -> None:
        # Flush SharedMemoryModel cache before each test (SQLite PK recycling guard).
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()

        # Singletons required by the dispatch path.
        self.config = ClashConfigFactory()

        # --- Combat setup ---
        self.encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        self.sheet = self.participant.character_sheet
        self.character = self.sheet.character

        # An ACTIVE clash in the same encounter.
        self.clash = ClashFactory(encounter=self.encounter, status=ClashStatus.ACTIVE)

        # A technique the participant will use for the clash contribution.
        self.technique = TechniqueFactory()

        # --- Scene / persona setup ---
        self.scene = SceneFactory()
        self.persona = self.sheet.primary_persona
        self.base_ts = timezone.now() - timedelta(hours=1)

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _make_interaction(self, *, mode: str, ts_offset_seconds: int) -> Interaction:
        """Create an Interaction with a controlled timestamp.

        auto_now_add on Interaction.timestamp may produce identical microsecond
        timestamps in fast test runs. We set the timestamp explicitly via
        .update() and mutate the in-memory instance so callers see the updated
        value without going through the identity map (which would return the stale
        cached instance).
        """
        row = InteractionFactory(scene=self.scene, persona=self.persona, mode=mode)
        target_ts = self.base_ts + timedelta(seconds=ts_offset_seconds)
        Interaction.objects.filter(pk=row.pk).update(timestamp=target_ts)
        row.timestamp = target_ts
        return row

    # ------------------------------------------------------------------
    # Step A — Dispatch a focused-clash action via dispatch_player_action
    # ------------------------------------------------------------------

    def test_step_a_dispatch_clash_contribution(self) -> None:
        """dispatch_player_action with a clash ActionRef writes a ClashContributionDeclaration."""
        ref = ActionRef(
            backend=ActionBackend.COMBAT,
            clash_id=self.clash.pk,
            clash_action_slot=ClashActionSlot.FOCUSED,
        )

        result = dispatch_player_action(
            character=self.character,
            ref=ref,
            kwargs={
                "technique_id": self.technique.pk,
                "strain_commitment": 3,
            },
        )

        self.assertTrue(result.deferred)

        decl = ClashContributionDeclaration.objects.get(
            participant=self.participant,
            clash=self.clash,
        )
        self.assertEqual(decl.technique_id, self.technique.pk)
        self.assertEqual(decl.action_slot, ClashActionSlot.FOCUSED)
        self.assertEqual(decl.strain_commitment, 3)
        self.assertEqual(decl.encounter_id, self.encounter.pk)
        self.assertEqual(decl.round_number, self.encounter.round_number)

    def test_step_a_passive_slot_dispatch(self) -> None:
        """dispatch_player_action also accepts PASSIVE slot without error."""
        ref = ActionRef(
            backend=ActionBackend.COMBAT,
            clash_id=self.clash.pk,
            clash_action_slot=ClashActionSlot.PASSIVE,
        )

        result = dispatch_player_action(
            character=self.character,
            ref=ref,
            kwargs={"technique_id": self.technique.pk, "strain_commitment": 0},
        )

        self.assertTrue(result.deferred)
        decl = ClashContributionDeclaration.objects.get(
            participant=self.participant,
            clash=self.clash,
        )
        self.assertEqual(decl.action_slot, ClashActionSlot.PASSIVE)

    # ------------------------------------------------------------------
    # Step B — Commit a thread pull (CombatPull + M2M thread)
    # ------------------------------------------------------------------

    def test_step_b_combat_pull_with_m2m_thread(self) -> None:
        """CombatPull row exists with correct M2M thread association and resonance_spent."""
        thread = ThreadFactory(owner=self.sheet)

        pull = CombatPullFactory(
            participant=self.participant,
            encounter=self.encounter,
            round_number=self.encounter.round_number,
            tier=1,
            resonance_spent=2,
            anima_spent=0,
        )
        pull.threads.add(thread)

        fetched = CombatPull.objects.get(pk=pull.pk)
        self.assertEqual(fetched.resonance_spent, 2)
        self.assertEqual(fetched.tier, 1)
        self.assertEqual(list(fetched.threads.all()), [thread])
        self.assertEqual(fetched.participant_id, self.participant.pk)
        self.assertEqual(fetched.encounter_id, self.encounter.pk)

    # ------------------------------------------------------------------
    # Step C — Submit a POSE; auto_link attaches prior ACTION Interactions
    # ------------------------------------------------------------------

    def test_step_c_pose_auto_link_connects_action_interactions(self) -> None:
        """auto_link_pose_to_actions bridges the POSE to prior ACTION rows."""
        action_a = self._make_interaction(mode=InteractionMode.ACTION, ts_offset_seconds=1)
        action_b = self._make_interaction(mode=InteractionMode.ACTION, ts_offset_seconds=2)
        pose = self._make_interaction(mode=InteractionMode.POSE, ts_offset_seconds=10)

        links = auto_link_pose_to_actions(pose)

        self.assertEqual(len(links), 2)
        linked_action_ids = {link.action_interaction_id for link in links}
        self.assertEqual(linked_action_ids, {action_a.pk, action_b.pk})

    # ------------------------------------------------------------------
    # Step D — Full data-model state assertions
    # ------------------------------------------------------------------

    def test_step_d_full_round_trip_data_model_state(self) -> None:
        """All four artifacts exist simultaneously with correct state.

        Exercises Steps A + B + C in a single test, asserting the combined
        data-model state: ClashContributionDeclaration, CombatPull with M2M
        threads, Interaction rows for ACTION + POSE, and InteractionAction
        bridges connecting them.
        """
        # Step A — clash contribution declaration.
        ref = ActionRef(
            backend=ActionBackend.COMBAT,
            clash_id=self.clash.pk,
            clash_action_slot=ClashActionSlot.FOCUSED,
        )
        dispatch_player_action(
            character=self.character,
            ref=ref,
            kwargs={"technique_id": self.technique.pk, "strain_commitment": 1},
        )

        # Step B — thread pull commit via factory (real DB state, no service mocking).
        thread = ThreadFactory(owner=self.sheet)
        pull = CombatPullFactory(
            participant=self.participant,
            encounter=self.encounter,
            round_number=self.encounter.round_number,
            tier=1,
            resonance_spent=2,
            anima_spent=0,
        )
        pull.threads.add(thread)

        # Step C — ACTION interactions then POSE with auto-link.
        action_a = self._make_interaction(mode=InteractionMode.ACTION, ts_offset_seconds=1)
        action_b = self._make_interaction(mode=InteractionMode.ACTION, ts_offset_seconds=2)
        pose = self._make_interaction(mode=InteractionMode.POSE, ts_offset_seconds=10)
        auto_link_pose_to_actions(pose)

        # Assert D1: ClashContributionDeclaration with correct fields.
        decl = ClashContributionDeclaration.objects.get(
            participant=self.participant,
            clash=self.clash,
        )
        self.assertEqual(decl.technique_id, self.technique.pk)
        self.assertEqual(decl.action_slot, ClashActionSlot.FOCUSED)
        self.assertEqual(decl.strain_commitment, 1)

        # Assert D2: CombatPull with M2M thread association.
        fetched_pull = CombatPull.objects.get(pk=pull.pk)
        self.assertEqual(fetched_pull.resonance_spent, 2)
        self.assertIn(thread, fetched_pull.threads.all())

        # Assert D3: Interaction rows — two ACTIONs and one POSE.
        self.assertEqual(action_a.mode, InteractionMode.ACTION)
        self.assertEqual(action_b.mode, InteractionMode.ACTION)
        self.assertEqual(pose.mode, InteractionMode.POSE)
        self.assertTrue(
            Interaction.objects.filter(
                scene=self.scene,
                persona=self.persona,
                mode=InteractionMode.ACTION,
            ).count()
            >= 2
        )

        # Assert D4: InteractionAction bridges connect POSE to the ACTION rows.
        bridge_ids = set(
            InteractionAction.objects.filter(pose=pose).values_list(
                "action_interaction_id", flat=True
            )
        )
        self.assertEqual(bridge_ids, {action_a.pk, action_b.pk})
