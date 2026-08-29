"""Web-layer proof for the #3412 offscreen-act gate — journal acts (task 2).

``JournalEntryViewSet.create`` (``create_journal_entry``) already routes a gate
refusal to ``{"detail": <reason>}`` at 400 via its existing
``if not result.success`` branch (``get_action(...).run()`` — see
``actions/base.py``'s ``check_availability``/``run``) — no view change was
needed. This proves the full lifecycle-state matrix (CAPTURED / unconscious /
DEAD / RETIRED / ALIVE) reaches the web client correctly, representative of
the other three gated journal acts (edit/respond/set-disposition), which
share the identical ``check_availability`` wiring.

Only the ALIVE (success) path reaches ``create_journal_entry``'s service body
and its XP/stat side effects — a gate refusal short-circuits inside
``Action.run()`` before ``execute()`` is ever called — so only that one test
mocks ``award_xp``/``increment_stat``; the four refusal tests need no such
mocking.
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
from world.roster.services.activity import set_lifecycle_state


class JournalCreateOffscreenGateTests(TestCase):
    """CAPTURED / unconscious / DEAD / RETIRED refuse; ALIVE succeeds unchanged.

    Fresh character/sheet per test (``setUp``, not ``setUpTestData``) — each
    test mutates ``lifecycle_state`` differently, and a shared instance would
    either carry stale in-memory state across tests or risk idmapper rollback
    staleness (see ``reference_idmapper_rollback_staleness``).
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
        data = {
            "title": "Word from afar",
            "body": "Whatever word can still reach.",
            "is_public": False,
        }
        with patch(
            "world.journals.views.JournalEntryViewSet._get_character",
            return_value=self.character,
        ):
            return self.client.post("/api/journals/entries/", data, format="json")

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
        # offscreen gate's own (defense-in-depth) DEAD branch, distinct from
        # the global vitals-backed dead-gate, which would otherwise win first
        # with "The dead cannot do that." (see actions/base.py's absorption).
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

    @patch("world.journals.services.award_xp")
    def test_alive_succeeds_exactly_as_before(self, mock_award: object) -> None:
        response = self._post()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["title"], "Word from afar")
        # The gate never blocks ALIVE — execution reaches the real service
        # body and its unchanged XP side effect fires, same as before.
        self.assertTrue(mock_award.called)
