"""Reaction economy tests (#2639).

Two independent budgets share the interpose fire seam
(``_dispatch_interpose_action``, F-10c):

- ``CombatParticipant.reactions_used`` vs ``REACTIONS_PER_ROUND`` — how many
  reactions ONE participant may spend this round (v1: 1). Reset each round in
  ``begin_declaration_phase``.
- ``DamagePreApplyPayload.answers_consumed`` vs ``ABSORPTION_CAP_PER_MOMENT``
  — how many interceptors may answer ONE landing hit (v1: 2), regardless of
  who fired them.

``dispatch_interpose`` (the underlying capability-reaction machinery) is
mocked out in every test here — these tests isolate the budget gate/increment
logic, not the guardian's own roll.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.db import transaction
from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from flows.events.payloads import DamagePreApplyPayload, DamageSource
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ABSORPTION_CAP_PER_MOMENT, REACTIONS_PER_ROUND, CombatManeuver
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CombatRoundActionFactory,
)
from world.combat.services import _dispatch_interpose_action, begin_declaration_phase
from world.scenes.constants import RoundStatus


def _payload(amount: int = 10, *, answers_consumed: int = 0) -> DamagePreApplyPayload:
    target = MagicMock()
    return DamagePreApplyPayload(
        target=target,
        amount=amount,
        damage_type=None,
        source=DamageSource(type="character", ref=None),
        answers_consumed=answers_consumed,
    )


def _bare_character():
    """A real ObjectDB Character with no attached CharacterSheet.

    ``_dispatch_interpose_action`` calls ``bond_bonus(interposer, protected)``
    unmocked — that reads ``protected.character_sheet`` for a real DB query,
    so ``protected`` must be a genuine ObjectDB (a MagicMock's ``.character_sheet``
    would feed a MagicMock into the ORM filter and blow up), not a mock.
    """
    return CharacterFactory()


class ReactionsPerRoundGateTests(TestCase):
    """CombatParticipant.reactions_used vs REACTIONS_PER_ROUND (v1: 1/round)."""

    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=1)
        interposer_sheet = CharacterSheetFactory()
        self.interposer = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=interposer_sheet
        )
        self.action = CombatRoundActionFactory(
            participant=self.interposer,
            round_number=1,
            maneuver=CombatManeuver.INTERPOSE,
            is_ready=True,
        )
        self.protected = _bare_character()

    @patch("world.combat.services.dispatch_interpose")
    def test_first_reaction_fires_and_increments(self, mock_dispatch) -> None:
        mock_dispatch.return_value = MagicMock()

        _dispatch_interpose_action(self.action, self.protected, _payload())

        self.interposer.refresh_from_db()
        self.assertEqual(self.interposer.reactions_used, 1)
        self.assertEqual(mock_dispatch.call_count, 1)

    @patch("world.combat.services.dispatch_interpose")
    def test_second_declared_reaction_this_round_declines(self, mock_dispatch) -> None:
        mock_dispatch.return_value = MagicMock()

        _dispatch_interpose_action(self.action, self.protected, _payload())
        self.interposer.refresh_from_db()
        self.assertEqual(self.interposer.reactions_used, REACTIONS_PER_ROUND)

        payload_two = _payload()
        _dispatch_interpose_action(self.action, self.protected, payload_two)

        self.interposer.refresh_from_db()
        # Budget exhausted: no second dispatch attempt, no further increment,
        # payload untouched — the same "did not fire" shape as an unaffordable
        # or failed reaction.
        self.assertEqual(mock_dispatch.call_count, 1)
        self.assertEqual(self.interposer.reactions_used, REACTIONS_PER_ROUND)
        self.assertEqual(payload_two.amount, 10)

    @patch("world.combat.services.dispatch_interpose")
    def test_reset_next_round(self, mock_dispatch) -> None:
        mock_dispatch.return_value = MagicMock()

        _dispatch_interpose_action(self.action, self.protected, _payload())
        self.interposer.refresh_from_db()
        self.assertEqual(self.interposer.reactions_used, 1)

        # begin_declaration_phase requires BETWEEN_ROUNDS + an active opponent.
        self.encounter.status = RoundStatus.BETWEEN_ROUNDS
        self.encounter.save(update_fields=["status"])
        CombatOpponentFactory(encounter=self.encounter)

        with transaction.atomic():
            begin_declaration_phase(self.encounter)

        self.interposer.refresh_from_db()
        self.assertEqual(self.interposer.reactions_used, 0)

        # And the budget is usable again this new round.
        _dispatch_interpose_action(self.action, self.protected, _payload())
        self.interposer.refresh_from_db()
        self.assertEqual(self.interposer.reactions_used, 1)


class AbsorptionCapPerMomentTests(TestCase):
    """DamagePreApplyPayload.answers_consumed vs ABSORPTION_CAP_PER_MOMENT (v1: 2)."""

    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=1)
        self.protected = _bare_character()

    def _interposer_action(self):
        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(encounter=self.encounter, character_sheet=sheet)
        action = CombatRoundActionFactory(
            participant=participant,
            round_number=1,
            maneuver=CombatManeuver.INTERPOSE,
            is_ready=True,
        )
        return participant, action

    @patch("world.combat.services.dispatch_interpose")
    def test_two_answers_allowed_third_declines(self, mock_dispatch) -> None:
        mock_dispatch.return_value = MagicMock()
        _, action_one = self._interposer_action()
        _, action_two = self._interposer_action()
        _, action_three = self._interposer_action()
        payload = _payload()

        _dispatch_interpose_action(action_one, self.protected, payload)
        self.assertEqual(payload.answers_consumed, 1)
        self.assertEqual(mock_dispatch.call_count, 1)

        _dispatch_interpose_action(action_two, self.protected, payload)
        self.assertEqual(payload.answers_consumed, ABSORPTION_CAP_PER_MOMENT)
        self.assertEqual(mock_dispatch.call_count, 2)

        # Cap reached: a third distinct interposer still declines on THIS payload.
        _dispatch_interpose_action(action_three, self.protected, payload)
        self.assertEqual(payload.answers_consumed, ABSORPTION_CAP_PER_MOMENT)
        self.assertEqual(mock_dispatch.call_count, 2)

    @patch("world.combat.services.dispatch_interpose")
    def test_cap_is_per_payload_not_global(self, mock_dispatch) -> None:
        """A fresh payload (a different landing hit) starts its own count at 0."""
        mock_dispatch.return_value = MagicMock()
        _, action_one = self._interposer_action()

        first_payload = _payload()
        _dispatch_interpose_action(action_one, self.protected, first_payload)
        self.assertEqual(first_payload.answers_consumed, 1)

        second_payload = _payload()
        self.assertEqual(second_payload.answers_consumed, 0)
