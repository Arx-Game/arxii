"""Journeys for leading the fight (#4603): a player marks a target for covenant-mates.

Mira and Tomas are played fighters in one declaring round-1 encounter in "The Road", against a
Bandit Captain and a Bandit Guard. A GM account sits in the scene. A mark is a free act: it writes
no round action and uses none of the marker's turn (ADR-0003). It names one foe for the round, and
every reader of the encounter sees it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from actions.constants import ActionBackend
from actions.factories import ActionTemplateFactory
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.combat.constants import ActionCategory, OpponentStatus, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatMark, CombatRoundAction
from world.combat.services import begin_declaration_phase, resolve_round
from world.fatigue.constants import EffortLevel
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterTechniqueFactory,
    EffectTypeFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneParticipationFactory
from world.traits.factories import CheckSystemSetupFactory, StatTraitFactory
from world.vitals.models import CharacterVitals

if TYPE_CHECKING:
    from world.magic.models import Technique

NOT_IN_ROUND = "You are not in an active combat round."


def _flat_roll(*_args: object, **_kwargs: object) -> MagicMock:
    """A roll fixed at success level 0."""
    return MagicMock(success_level=0)


class MarkingATarget(JourneyCase):
    """Mira marks the Bandit Captain for Tomas; the GM and Tomas both see it."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        self.road = self.make_room("The Road")
        self.mira = self.make_player("Mira", room=self.road)
        self.tomas = self.make_player("Tomas", room=self.road)
        self.stranger = self.make_player("Odo", room=self.road)
        for player in (self.mira, self.tomas):
            CharacterVitals.objects.create(
                character_sheet=player.sheet_data, health=100, max_health=100, base_max_health=100
            )

        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.road
        )
        self.mira_seat = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.mira.sheet_data,
            status=ParticipantStatus.ACTIVE,
        )
        self.tomas_seat = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.tomas.sheet_data,
            status=ParticipantStatus.ACTIVE,
        )
        self.captain = CombatOpponentFactory(encounter=self.encounter, name="Bandit Captain")
        self.guard = CombatOpponentFactory(encounter=self.encounter, name="Bandit Guard")

        self.gm_account = self.account_of(self.make_player("Ravenna", room=self.road))
        SceneParticipationFactory(
            scene=self.encounter.scene, account=self.gm_account, is_gm=True, is_owner=True
        )

    # -- helpers ---------------------------------------------------------------

    def _mira_knows_a_technique(self) -> Technique:
        check_type = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=check_type, trait=StatTraitFactory(), weight=1)
        technique = TechniqueFactory(
            gift=GiftFactory(),
            anima_cost=1,
            effect_type=EffectTypeFactory(base_power=10),
            damage_profile=False,
            action_category=ActionCategory.SOCIAL,
            action_template=ActionTemplateFactory(check_type=check_type),
        )
        sheet = self.mira.sheet_data
        CharacterTechniqueFactory(character=sheet, technique=technique)
        CharacterAnimaFactory(character=sheet, current=20, maximum=30)
        return technique

    def _mira_declares(self, technique: Technique) -> object:
        ref = ActionRef(
            backend=ActionBackend.COMBAT, technique_id=technique.pk, action_slot="focused"
        )
        return dispatch_player_action(
            self.mira,
            ref,
            {
                "effort_level": EffortLevel.MEDIUM,
                "focused_opponent_target_id": self.guard.pk,
            },
        )

    def _marks_seen_by(self, account: object) -> list[tuple[int, int]]:
        body = self.api(account).get(f"/api/combat/{self.encounter.pk}/").json()
        return [(m["participant_id"], m["opponent_id"]) for m in body["marks"]]

    # -- the journeys ----------------------------------------------------------

    def test_mira_marks_the_captain_from_the_web(self) -> None:
        result = self.web(self.mira, "combat_mark", opponent_id=self.captain.pk)
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(result.detail.message, "You mark Bandit Captain.")
        self.assertEqual(CombatMark.objects.get(participant=self.mira_seat).opponent, self.captain)

    def test_mira_marks_the_captain_by_telnet(self) -> None:
        out = self.telnet(self.mira, "combat mark Bandit Captain")
        self.assertIn("You mark Bandit Captain.", out)
        self.assertIn("Mira marked Bandit Captain.", self.telnet(self.tomas, "combat"))

    def test_everyone_at_the_fight_reads_the_mark(self) -> None:
        self.web(self.mira, "combat_mark", opponent_id=self.captain.pk)
        expected = [(self.mira_seat.pk, self.captain.pk)]
        for account in (
            self.account_of(self.tomas),
            self.account_of(self.mira),
            self.gm_account,
        ):
            self.assertEqual(self._marks_seen_by(account), expected)

    def test_marking_does_not_use_her_action(self) -> None:
        technique = self._mira_knows_a_technique()
        declared = self._mira_declares(technique)
        self.assertTrue(declared.deferred)

        result = self.web(self.mira, "combat_mark", opponent_id=self.captain.pk)
        self.assertTrue(result.detail.success, result.detail.message)

        action = CombatRoundAction.objects.get(participant=self.mira_seat, round_number=1)
        self.assertEqual(action.focused_opponent_target, self.guard)
        self.assertEqual(CombatRoundAction.objects.filter(participant=self.mira_seat).count(), 1)

    def test_marking_first_then_declaring_still_declares(self) -> None:
        technique = self._mira_knows_a_technique()
        self.web(self.mira, "combat_mark", opponent_id=self.captain.pk)
        self.assertFalse(CombatRoundAction.objects.filter(participant=self.mira_seat).exists())

        declared = self._mira_declares(technique)

        self.assertTrue(declared.deferred)
        action = CombatRoundAction.objects.get(participant=self.mira_seat, round_number=1)
        self.assertEqual(action.focused_opponent_target, self.guard)
        self.assertEqual(CombatMark.objects.get(participant=self.mira_seat).opponent, self.captain)

    def test_marking_again_moves_the_mark(self) -> None:
        self.web(self.mira, "combat_mark", opponent_id=self.captain.pk)
        self.web(self.mira, "combat_mark", opponent_id=self.guard.pk)
        self.assertEqual(
            list(
                CombatMark.objects.filter(participant=self.mira_seat).values_list(
                    "opponent", flat=True
                )
            ),
            [self.guard.pk],
        )

    def test_the_mark_ends_with_the_round(self) -> None:
        self.web(self.mira, "combat_mark", opponent_id=self.captain.pk)
        self.assertEqual(len(self._marks_seen_by(self.account_of(self.tomas))), 1)

        resolve_round(
            self.encounter,
            defense_check_fn=_flat_roll,
            offense_check_fn=_flat_roll,
        )
        begin_declaration_phase(self.encounter)

        self.assertEqual(self.encounter.round_number, 2)
        self.assertEqual(self._marks_seen_by(self.account_of(self.tomas)), [])

    def test_marking_between_rounds_is_refused(self) -> None:
        self.encounter.status = RoundStatus.BETWEEN_ROUNDS
        self.encounter.save(update_fields=["status"])

        result = self.web(self.mira, "combat_mark", opponent_id=self.captain.pk)

        self.assertFalse(result.detail.success)
        self.assertEqual(result.detail.message, NOT_IN_ROUND)
        self.assertFalse(CombatMark.objects.exists())

    def test_marking_a_fled_bandit_is_refused(self) -> None:
        self.captain.status = OpponentStatus.FLED
        self.captain.save(update_fields=["status"])

        out = self.telnet(self.mira, "combat mark Bandit Captain")

        self.assertIn("No active opponent named 'Bandit Captain'", out)
        self.assertFalse(CombatMark.objects.exists())

    def test_someone_outside_the_fight_cannot_mark(self) -> None:
        result = self.web(self.stranger, "combat_mark", opponent_id=self.captain.pk)

        self.assertFalse(result.detail.success)
        self.assertEqual(result.detail.message, NOT_IN_ROUND)
        self.assertFalse(CombatMark.objects.exists())
