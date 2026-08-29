"""Web-layer proof for the #3412 offscreen-act gate — goal acts (task 2).

Both ``CharacterGoalViewSet.update_all`` (``set_character_goals``) and
``GoalJournalViewSet.create`` (``log_goal_progress``) already route a gate
refusal to ``{"detail": <reason>}`` at 400 via their existing
``if not result.success`` branch (``get_action(...).run()``) — no view
changes were needed.
"""

from unittest.mock import patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from actions.constants import (
    OFFSCREEN_REASON_CAPTURED,
    OFFSCREEN_REASON_DEAD,
    OFFSCREEN_REASON_RETIRED,
    OFFSCREEN_REASON_UNCONSCIOUS,
)
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import LifecycleState
from world.conditions.factories import ConditionInstanceFactory, UnconsciousConditionFactory
from world.goals.factories import GoalDomainFactory
from world.roster.services.activity import set_lifecycle_state


class CharacterGoalUpdateAllOffscreenGateTests(TestCase):
    """``set_character_goals`` — the "goal set" act.

    Fresh character/sheet/domain per test (``setUp``) — each test mutates
    ``lifecycle_state`` differently; a class-shared instance would carry
    stale in-memory state across tests (see the journals sibling module for
    the same rationale spelled out in full).
    """

    def setUp(self) -> None:
        self.user = AccountFactory()
        self.character = CharacterFactory()
        self.character.db_account = self.user
        self.character.save()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.domain = GoalDomainFactory(name="Standing")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _post(self):
        data = {"goals": [{"domain": self.domain.id, "points": 5}]}
        with patch(
            "world.goals.views.CharacterGoalViewSet._get_character",
            return_value=self.character,
        ):
            return self.client.post("/api/goals/my-goals/update/", data, format="json")

    def test_captured_refused_with_smuggle_text(self) -> None:
        self.sheet.lifecycle_state = LifecycleState.CAPTURED
        self.sheet.save(update_fields=["lifecycle_state"])
        response = self._post()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], OFFSCREEN_REASON_CAPTURED)

    def test_unconscious_refused_with_dream_text(self) -> None:
        template = UnconsciousConditionFactory()
        ConditionInstanceFactory(target=self.character, condition=template)
        response = self._post()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], OFFSCREEN_REASON_UNCONSCIOUS)

    def test_dead_refused_with_seance_text(self) -> None:
        # lifecycle_state=DEAD directly, vitals untouched — exercises the
        # offscreen gate's own DEAD branch (see the journals sibling module
        # for why the global vitals-backed dead-gate is deliberately not
        # exercised here).
        set_lifecycle_state(self.sheet, LifecycleState.DEAD)
        response = self._post()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], OFFSCREEN_REASON_DEAD)

    def test_retired_refused_with_quiet_text(self) -> None:
        self.sheet.lifecycle_state = LifecycleState.RETIRED
        self.sheet.save(update_fields=["lifecycle_state"])
        response = self._post()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], OFFSCREEN_REASON_RETIRED)

    def test_alive_succeeds_exactly_as_before(self) -> None:
        response = self._post()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_points"], 5)


class GoalJournalCreateOffscreenGateTests(TestCase):
    """``log_goal_progress`` — the second gated goals entry point.

    Lighter-touch: proves the wiring (one refusal case) plus the ALIVE path
    stays byte-identical; the full lifecycle matrix is already proven above
    for the sibling ``set_character_goals`` entry point sharing the same
    ``check_availability`` gate.
    """

    def setUp(self) -> None:
        self.user = AccountFactory()
        self.character = CharacterFactory()
        self.character.db_account = self.user
        self.character.save()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _post(self):
        data = {"title": "Notes from the dark", "content": "Even so, I try."}
        with patch(
            "world.goals.views.GoalJournalViewSet._get_character",
            return_value=self.character,
        ):
            return self.client.post("/api/goals/journals/", data, format="json")

    def test_captured_refused_with_smuggle_text(self) -> None:
        self.sheet.lifecycle_state = LifecycleState.CAPTURED
        self.sheet.save(update_fields=["lifecycle_state"])
        response = self._post()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], OFFSCREEN_REASON_CAPTURED)

    def test_alive_succeeds_exactly_as_before(self) -> None:
        response = self._post()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["title"], "Notes from the dark")
