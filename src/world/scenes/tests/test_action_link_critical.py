"""Tests for ``has_critical_effect`` on the action-link payload (#996).

The pose feed exposes a cheap per-action-link flag so the frontend can
auto-expand the outcome detail panel on first paint when a linked action had a
load-bearing (critical) outcome — currently: it defeated its focused opponent.

The signal MUST be derived purely from prefetched data (the linked ACTION's
``combat_round_actions`` + their ``focused_opponent_target``); it must not add a
query per action link.
"""

from __future__ import annotations

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import OpponentStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CombatRoundActionFactory,
)
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import InteractionMode, ScenePrivacyMode
from world.scenes.factories import InteractionFactory, PersonaFactory, SceneFactory
from world.scenes.models import Interaction, InteractionAction


class ActionLinkCriticalEffectTests(APITestCase):
    """``has_critical_effect`` reflects opponent-defeat on the linked action."""

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()

        # Identity chain so the authenticated account "owns" the pose persona
        # (own-persona interactions always appear in the feed).
        self.account = AccountFactory()
        self.character = CharacterFactory()
        self.roster_entry = RosterEntryFactory(character_sheet__character=self.character)
        self.player_data = PlayerDataFactory(account=self.account)
        self.tenure = RosterTenureFactory(
            player_data=self.player_data,
            roster_entry=self.roster_entry,
        )
        self.sheet = CharacterSheetFactory(character=self.character)
        self.persona = self.sheet.primary_persona
        # ACTION interactions use a persona the account does NOT own AND live in
        # a PRIVATE scene, so they never surface as their own feed rows — the feed
        # stays at exactly the poses (isolating the per-link query count).
        self.action_persona = PersonaFactory()
        self.private_scene = SceneFactory(privacy_mode=ScenePrivacyMode.PRIVATE)

        self.encounter = CombatEncounterFactory()

        self.client.force_authenticate(user=self.account)

    def _make_pose(self) -> Interaction:
        return InteractionFactory(persona=self.persona, mode=InteractionMode.POSE)

    def _add_link(self, pose: Interaction, opponent_status: str) -> None:
        """Link ``pose`` to a fresh ACTION whose round-action targeted an opponent
        in ``opponent_status``."""
        opponent = CombatOpponentFactory(encounter=self.encounter, status=opponent_status)
        action_interaction = InteractionFactory(
            persona=self.action_persona,
            mode=InteractionMode.ACTION,
            scene=self.private_scene,
        )
        # Fresh participant per round-action: (participant, round_number) is unique.
        participant = CombatParticipantFactory(encounter=self.encounter)
        CombatRoundActionFactory(
            participant=participant,
            interaction=action_interaction,
            interaction_timestamp=action_interaction.timestamp,
            focused_opponent_target=opponent,
        )
        existing = pose.action_links.count()
        InteractionAction.objects.create(
            pose=pose,
            action_interaction=action_interaction,
            ordering=existing,
        )

    def _link_for_pose(self, results: list[dict], pose_id: int) -> dict:
        pose_row = next(r for r in results if r["id"] == pose_id)
        self.assertEqual(len(pose_row["action_links"]), 1)
        return pose_row["action_links"][0]

    def test_has_critical_effect_true_when_opponent_defeated(self) -> None:
        pose = self._make_pose()
        self._add_link(pose, OpponentStatus.DEFEATED)
        response = self.client.get(reverse("interaction-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        link = self._link_for_pose(response.data["results"], pose.pk)
        self.assertTrue(link["has_critical_effect"])

    def test_has_critical_effect_false_when_opponent_active(self) -> None:
        pose = self._make_pose()
        self._add_link(pose, OpponentStatus.ACTIVE)
        response = self.client.get(reverse("interaction-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        link = self._link_for_pose(response.data["results"], pose.pk)
        self.assertFalse(link["has_critical_effect"])

    def test_critical_flag_is_not_n_plus_one(self) -> None:
        """has_critical_effect reads prefetched data: the linked CombatRoundActions
        are fetched in ONE query for the whole feed, not one per action link."""
        pose = self._make_pose()
        self._add_link(pose, OpponentStatus.DEFEATED)
        self._add_link(pose, OpponentStatus.DEFEATED)
        self._add_link(pose, OpponentStatus.DEFEATED)
        url = reverse("interaction-list")

        # Warm the SharedMemoryModel identity map so the measured request reflects
        # steady-state query behaviour, not cold-cache noise.
        self.client.get(url)

        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        pose_row = next(r for r in response.data["results"] if r["id"] == pose.pk)
        self.assertEqual(len(pose_row["action_links"]), 3)

        cra_queries = [q for q in ctx.captured_queries if "combatroundaction" in q["sql"].lower()]
        self.assertLessEqual(
            len(cra_queries),
            1,
            f"has_critical_effect issued {len(cra_queries)} CombatRoundAction queries "
            "for 3 links — expected a single prefetch (N+1 regression).",
        )
