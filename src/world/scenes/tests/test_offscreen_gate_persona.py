"""Web-layer proof for the #3412 offscreen-act gate — persona + cross-act (task 2).

``PersonaViewSet.set_active`` dispatches through ``dispatch_player_action`` →
``SetActivePersonaAction.run()`` and, on a gate refusal, already raises
``serializers.ValidationError(detail.message)`` — DRF's exception handler
renders a plain-string ``ValidationError`` as ``{"detail": <reason>}`` at 400,
the identical wire shape the journals/goals viewsets produce via their own
``result.message`` branches. No view change was needed.

Every existing ``SetActivePersonaEndpointTests`` (ALIVE path,
``world/scenes/tests/test_active_persona.py``) stays untouched — the gate
only changes degraded states.

This module also carries the cross-act payload-shape assertion (all three
gated viewsets agree on ``{"detail": <str>}``) and one telnet-parity spot
check (``action.run()`` called directly, bypassing the web layer entirely).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from actions.constants import (
    OFFSCREEN_REASON_CAPTURED,
    OFFSCREEN_REASON_DEAD,
    OFFSCREEN_REASON_RETIRED,
    OFFSCREEN_REASON_UNCONSCIOUS,
)
from actions.definitions.personas import SetActivePersonaAction
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import LifecycleState
from world.conditions.factories import ConditionInstanceFactory, UnconsciousConditionFactory
from world.goals.factories import GoalDomainFactory
from world.roster.services.activity import set_lifecycle_state
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory
from world.scenes.views import PersonaViewSet


class SetActivePersonaOffscreenGateTests(TestCase):
    """CAPTURED / unconscious / DEAD / RETIRED refuse; ALIVE succeeds unchanged.

    Fresh character/sheet/persona per test (``setUp``) — mirrors the same
    per-test-isolation rationale as the journals/goals sibling modules.
    """

    def setUp(self) -> None:
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.alt = PersonaFactory(character_sheet=self.sheet, persona_type=PersonaType.ESTABLISHED)
        self.factory = APIRequestFactory()
        self.view = PersonaViewSet.as_view({"post": "set_active"})

    def _post(self):
        request = self.factory.post(
            "/api/scenes/personas/set-active/", {"persona_id": self.alt.pk}, format="json"
        )
        user = SimpleNamespace(is_authenticated=True, is_staff=False, puppet=self.character)
        force_authenticate(request, user=user)
        return self.view(request)

    def test_captured_refused_with_smuggle_text(self) -> None:
        self.sheet.lifecycle_state = LifecycleState.CAPTURED
        self.sheet.save(update_fields=["lifecycle_state"])
        response = self._post()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(str(response.data["detail"]), OFFSCREEN_REASON_CAPTURED)

    def test_unconscious_refused_with_dream_text(self) -> None:
        template = UnconsciousConditionFactory()
        ConditionInstanceFactory(target=self.character, condition=template)
        response = self._post()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(str(response.data["detail"]), OFFSCREEN_REASON_UNCONSCIOUS)

    def test_dead_refused_with_seance_text(self) -> None:
        # lifecycle_state=DEAD directly, vitals untouched — the offscreen
        # gate's own DEAD branch (see the journals sibling module for why the
        # global vitals-backed dead-gate is deliberately not exercised here).
        set_lifecycle_state(self.sheet, LifecycleState.DEAD)
        response = self._post()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(str(response.data["detail"]), OFFSCREEN_REASON_DEAD)

    def test_retired_refused_with_quiet_text(self) -> None:
        self.sheet.lifecycle_state = LifecycleState.RETIRED
        self.sheet.save(update_fields=["lifecycle_state"])
        response = self._post()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(str(response.data["detail"]), OFFSCREEN_REASON_RETIRED)

    def test_alive_succeeds_exactly_as_before(self) -> None:
        response = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["active_persona_id"], self.alt.pk)


class OffscreenGatePayloadShapeTests(TestCase):
    """Cross-act assertion: the CAPTURED refusal payload shape is uniform.

    Journals (``get_action(...).run()`` → ``{"detail": result.message}``,
    400), goals (identical shape), and persona (``ValidationError`` → DRF's
    ``{"detail": exc.detail}``, 400) all reach the same
    ``{"detail": <str>}`` wire shape — a client can rely on ``detail`` alone
    regardless of which act it dispatched (task 4/FE consumes this).
    """

    def setUp(self) -> None:
        self.user = AccountFactory()
        self.character = CharacterFactory()
        self.character.db_account = self.user
        self.character.save()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.sheet.lifecycle_state = LifecycleState.CAPTURED
        self.sheet.save(update_fields=["lifecycle_state"])
        self.alt = PersonaFactory(character_sheet=self.sheet, persona_type=PersonaType.ESTABLISHED)
        self.domain = GoalDomainFactory(name="Wealth")

    def _assert_uniform_captured_refusal(self, response) -> None:
        self.assertEqual(response.status_code, 400)
        self.assertEqual(list(response.data.keys()), ["detail"])
        self.assertEqual(str(response.data["detail"]), OFFSCREEN_REASON_CAPTURED)

    def test_journal_create_payload_shape(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.user)
        with (
            patch("world.journals.services.award_xp"),
            patch("world.journals.services.increment_stat"),
            patch(
                "world.journals.views.JournalEntryViewSet._get_character",
                return_value=self.character,
            ),
        ):
            response = client.post(
                "/api/journals/entries/",
                {"title": "T", "body": "B", "is_public": False},
                format="json",
            )
        self._assert_uniform_captured_refusal(response)

    def test_goal_update_all_payload_shape(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.user)
        with patch(
            "world.goals.views.CharacterGoalViewSet._get_character",
            return_value=self.character,
        ):
            response = client.post(
                "/api/goals/my-goals/update/",
                {"goals": [{"domain": self.domain.id, "points": 5}]},
                format="json",
            )
        self._assert_uniform_captured_refusal(response)

    def test_persona_set_active_payload_shape(self) -> None:
        factory = APIRequestFactory()
        view = PersonaViewSet.as_view({"post": "set_active"})
        request = factory.post(
            "/api/scenes/personas/set-active/", {"persona_id": self.alt.pk}, format="json"
        )
        user = SimpleNamespace(is_authenticated=True, is_staff=False, puppet=self.character)
        force_authenticate(request, user=user)
        response = view(request)
        self._assert_uniform_captured_refusal(response)


class TelnetParitySpotCheckTests(TestCase):
    """One direct ``action.run()`` call — the telnet-equivalent seam.

    Telnet commands call ``action.run()`` directly (never through DRF), so
    this proves the same gate + reason text fires identically off the web
    layer entirely — spot-checking one representative act
    (``set_active_persona``) per the task brief.
    """

    def test_captured_actor_gets_smuggle_text_via_run(self) -> None:
        character = CharacterFactory()
        sheet = CharacterSheetFactory(character=character)
        sheet.lifecycle_state = LifecycleState.CAPTURED
        sheet.save(update_fields=["lifecycle_state"])
        alt = PersonaFactory(character_sheet=sheet, persona_type=PersonaType.ESTABLISHED)

        result = SetActivePersonaAction().run(actor=character, persona_id=alt.pk)

        self.assertFalse(result.success)
        self.assertEqual(result.message, OFFSCREEN_REASON_CAPTURED)
