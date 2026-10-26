"""A standing guard intercepts through the interpose seam (#4584).

A ``ConditionTemplate`` with ``source_guards_bearer`` set makes the instance's
``source_character`` try to intercept each hit on the bearer, as if she had
declared an INTERPOSE naming the bearer, without declaring one. She pays the
same costs a declared guardian pays (a reaction this round, which makes her next
one harder since #4676, and ``ABSORPTION_CAP_PER_MOMENT``) and mundane interpose
fatigue at very low effort.

``dispatch_interpose`` (the guardian's own roll) is mocked out here, as in
``test_reaction_economy.py``: these tests isolate selection, budgets and cost.

Built in ``setUp`` (not ``setUpTestData``): the tests mutate participant rows.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from flows.events.payloads import DamagePreApplyPayload, DamageSource
from world.combat.constants import (
    ABSORPTION_CAP_PER_MOMENT,
    INTERPOSE_BASE_FATIGUE_COST,
    ActionCategory,
    CombatManeuver,
    ParticipantStatus,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    CombatRoundActionFactory,
)
from world.combat.services import _ensure_interpose_challenges, _try_interpose
from world.conditions.constants import FoundationalCapability
from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionCapabilityEffectFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
    UnconsciousConditionFactory,
)
from world.conditions.services import apply_condition, guardians_by_target
from world.fatigue.constants import EFFORT_COST_MULTIPLIER, MIN_FATIGUE_COST, EffortLevel
from world.fatigue.services import get_or_create_fatigue_pool
from world.magic.factories import TechniqueFactory
from world.mechanics.factories import ChallengeTemplateFactory
from world.mechanics.models import ChallengeInstance
from world.scenes.constants import RoundStatus

RESCUE_PATH = "world.combat.services.damage.interception._record_story_envoy_rescue"
TECHNIQUE_PATH = "world.combat.services.damage.interception._try_technique_interpose"


def _payload(amount: int = 10, *, answers_consumed: int = 0) -> DamagePreApplyPayload:
    return DamagePreApplyPayload(
        target=MagicMock(),
        amount=amount,
        damage_type=None,
        source=DamageSource(type="character", ref=None),
        answers_consumed=answers_consumed,
    )


class StandingGuardTests(TestCase):
    """A guardian's standing guard is tried between named and guard-anyone declarations."""

    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=1)
        self.ward = CombatParticipantFactory(encounter=self.encounter)
        self.guard_a = CombatParticipantFactory(encounter=self.encounter)
        self.guard_b = CombatParticipantFactory(encounter=self.encounter)
        self.guard_c = CombatParticipantFactory(encounter=self.encounter)
        self.watch = ConditionTemplateFactory(name="Shadowing 4584", source_guards_bearer=True)

    def _guard(self, ward, guardian) -> None:
        ConditionInstanceFactory(
            target=ward.character_sheet.character,
            condition=self.watch,
            source_character=guardian.character_sheet.character,
        )

    def _declare(self, participant, *, target=None):
        return CombatRoundActionFactory(
            participant=participant,
            round_number=1,
            maneuver=CombatManeuver.INTERPOSE,
            focused_ally_target=target,
            is_ready=True,
        )

    @patch("world.combat.services.dispatch_interpose")
    def test_a_standing_guard_steps_in_without_declaring(self, dispatch) -> None:
        self._guard(self.ward, self.guard_a)
        payload = _payload(10)

        _try_interpose(self.ward, payload)

        self.assertEqual(dispatch.call_args.args[0], self.guard_a.character_sheet.character)
        self.guard_a.refresh_from_db()
        self.assertEqual(self.guard_a.reactions_used, 1)
        self.assertEqual(payload.answers_consumed, 1)
        pool = get_or_create_fatigue_pool(self.guard_a.character_sheet)
        expected = max(
            MIN_FATIGUE_COST,
            int(INTERPOSE_BASE_FATIGUE_COST * EFFORT_COST_MULTIPLIER[EffortLevel.VERY_LOW]),
        )
        self.assertEqual(pool.get_current(ActionCategory.PHYSICAL), expected)

    @patch("world.combat.services.dispatch_interpose")
    def test_a_guard_who_already_reacted_still_guards_with_a_harder_roll(self, dispatch) -> None:
        dispatch.return_value = MagicMock()
        self.guard_a.reactions_used = 1
        self.guard_a.save(update_fields=["reactions_used"])
        self._guard(self.ward, self.guard_a)

        _try_interpose(self.ward, _payload(10))

        dispatch.assert_called_once()
        self.assertEqual(dispatch.call_args.kwargs["extra_modifiers"], -2)
        self.guard_a.refresh_from_db()
        self.assertEqual(self.guard_a.reactions_used, 2)

    @patch("world.combat.services.dispatch_interpose")
    def test_a_guard_counts_against_the_absorption_cap(self, dispatch) -> None:
        self._guard(self.ward, self.guard_a)
        payload = _payload(10, answers_consumed=ABSORPTION_CAP_PER_MOMENT)

        with patch("world.scenes.interaction_services.narrate_privately"):
            _try_interpose(self.ward, payload)

        dispatch.assert_not_called()
        self.assertEqual(payload.answers_consumed, ABSORPTION_CAP_PER_MOMENT)

    @patch("world.combat.services.dispatch_interpose", return_value=None)
    def test_named_declarations_then_guards_then_guard_anyone(self, dispatch) -> None:
        self._declare(self.guard_c, target=None)
        self._declare(self.guard_a, target=self.ward)
        self._guard(self.ward, self.guard_b)

        _try_interpose(self.ward, _payload(10))

        callers = [call.args[0] for call in dispatch.call_args_list]
        self.assertEqual(
            callers,
            [
                self.guard_a.character_sheet.character,
                self.guard_b.character_sheet.character,
                self.guard_c.character_sheet.character,
            ],
        )

    @patch("world.combat.services.dispatch_interpose", return_value=None)
    def test_a_guardian_with_a_declaration_and_a_guard_is_tried_once(self, dispatch) -> None:
        self._declare(self.guard_a, target=self.ward)
        self._guard(self.ward, self.guard_a)

        _try_interpose(self.ward, _payload(10))

        self.assertEqual(dispatch.call_count, 1)

    @patch("world.combat.services.dispatch_interpose")
    def test_a_guard_anyone_technique_declarer_uses_her_technique(self, dispatch) -> None:
        """Her declaration takes precedence over her standing guard on the ward."""
        action = CombatRoundActionFactory(
            participant=self.guard_c,
            round_number=1,
            maneuver=CombatManeuver.INTERPOSE,
            focused_ally_target=None,
            focused_action=TechniqueFactory(),
            is_ready=True,
        )
        self._guard(self.ward, self.guard_c)

        with patch(TECHNIQUE_PATH, return_value=True) as technique:
            _try_interpose(self.ward, _payload(10))

        technique.assert_called_once()
        self.assertEqual(technique.call_args.args[0], action)
        dispatch.assert_not_called()

    @patch("world.combat.services.dispatch_interpose")
    def test_a_guard_anyone_declarer_pays_her_declared_effort(self, dispatch) -> None:
        CombatRoundActionFactory(
            participant=self.guard_c,
            round_number=1,
            maneuver=CombatManeuver.INTERPOSE,
            focused_ally_target=None,
            effort_level=EffortLevel.HIGH,
            is_ready=True,
        )
        self._guard(self.ward, self.guard_c)

        _try_interpose(self.ward, _payload(10))

        self.assertEqual(dispatch.call_count, 1)
        pool = get_or_create_fatigue_pool(self.guard_c.character_sheet)
        expected = max(
            MIN_FATIGUE_COST,
            int(INTERPOSE_BASE_FATIGUE_COST * EFFORT_COST_MULTIPLIER[EffortLevel.HIGH]),
        )
        self.assertEqual(pool.get_current(ActionCategory.PHYSICAL), expected)

    @patch("world.combat.services.dispatch_interpose")
    def test_a_guardian_who_named_another_ward_does_not_guard_this_one(self, dispatch) -> None:
        self._declare(self.guard_b, target=self.guard_c)
        self._guard(self.ward, self.guard_b)

        _try_interpose(self.ward, _payload(10))

        dispatch.assert_not_called()
        self.guard_b.refresh_from_db()
        self.assertEqual(self.guard_b.reactions_used, 0)

    @patch("world.combat.services.dispatch_interpose")
    def test_a_self_cast_guard_never_interposes_for_its_bearer(self, dispatch) -> None:
        self._guard(self.ward, self.ward)

        _try_interpose(self.ward, _payload(10))

        dispatch.assert_not_called()

    @patch("world.combat.services.dispatch_interpose")
    def test_a_guard_from_someone_not_fighting_is_ignored(self, dispatch) -> None:
        self.guard_a.status = ParticipantStatus.FLED
        self.guard_a.save(update_fields=["status"])
        self._guard(self.ward, self.guard_a)

        _try_interpose(self.ward, _payload(10))

        dispatch.assert_not_called()

    def _knock_out(self, participant) -> None:
        """Zero the participant's awareness: she stays ACTIVE but cannot act."""
        awareness = CapabilityTypeFactory(name=FoundationalCapability.AWARENESS, innate_baseline=1)
        unconscious = UnconsciousConditionFactory()
        ConditionCapabilityEffectFactory(condition=unconscious, capability=awareness, value=-100)
        apply_condition(target=participant.character_sheet.character, condition=unconscious)

    @patch("world.combat.services.dispatch_interpose")
    def test_a_knocked_out_guardian_does_not_step_in(self, dispatch) -> None:
        self._guard(self.ward, self.guard_a)
        self._knock_out(self.guard_a)
        payload = _payload(10)

        with patch("world.scenes.interaction_services.narrate_privately") as private:
            _try_interpose(self.ward, payload)

        dispatch.assert_not_called()
        private.assert_not_called()
        self.assertEqual(payload.answers_consumed, 0)
        self.guard_a.refresh_from_db()
        self.assertEqual(self.guard_a.status, ParticipantStatus.ACTIVE)
        self.assertEqual(self.guard_a.reactions_used, 0)
        pool = get_or_create_fatigue_pool(self.guard_a.character_sheet)
        self.assertEqual(pool.get_current(ActionCategory.PHYSICAL), 0)

    @patch("world.combat.services.dispatch_interpose")
    def test_a_conscious_guardian_steps_in_past_a_knocked_out_one(self, dispatch) -> None:
        self._guard(self.ward, self.guard_a)
        ConditionInstanceFactory(
            target=self.ward.character_sheet.character,
            condition=ConditionTemplateFactory(name="Escorting 4584", source_guards_bearer=True),
            source_character=self.guard_b.character_sheet.character,
        )
        self._knock_out(self.guard_a)

        _try_interpose(self.ward, _payload(10))

        self.assertEqual(dispatch.call_args.args[0], self.guard_b.character_sheet.character)

    def test_a_ward_guarded_only_by_a_knocked_out_guardian_gets_no_challenge(self) -> None:
        template = ChallengeTemplateFactory(name="Interpose")
        self._guard(self.ward, self.guard_a)
        self._knock_out(self.guard_a)

        _ensure_interpose_challenges(self.encounter, {})

        self.assertFalse(
            ChallengeInstance.objects.filter(
                template=template, target_object=self.ward.character_sheet.character
            ).exists()
        )

    def test_a_standing_rescue_credits_the_guardians_own_action(self) -> None:
        """A rescue records with the guardian's own declaration this round, if any."""
        self._guard(self.ward, self.guard_a)
        own_action = CombatRoundActionFactory(participant=self.guard_a, round_number=1)

        def _halve(_interposer, _protected, payload, **_kwargs):
            payload.amount //= 2
            return MagicMock()

        with (
            patch("world.combat.services.dispatch_interpose", side_effect=_halve),
            patch(RESCUE_PATH) as rescue,
        ):
            _try_interpose(self.ward, _payload(10))

        rescue.assert_called_once_with(
            self.guard_a, own_action, self.ward.character_sheet.character
        )

    def test_a_standing_rescue_without_an_own_action_records_nothing(self) -> None:
        self._guard(self.ward, self.guard_a)

        def _halve(_interposer, _protected, payload, **_kwargs):
            payload.amount //= 2
            return MagicMock()

        with (
            patch("world.combat.services.dispatch_interpose", side_effect=_halve),
            patch(RESCUE_PATH) as rescue,
        ):
            payload = _payload(10)
            _try_interpose(self.ward, payload)

        self.assertEqual(payload.amount, 5)
        rescue.assert_not_called()

    def test_a_guarded_ward_gets_an_interpose_challenge_with_no_declarations(self) -> None:
        template = ChallengeTemplateFactory(name="Interpose")
        self._guard(self.ward, self.guard_a)

        _ensure_interpose_challenges(self.encounter, {})

        self.assertTrue(
            ChallengeInstance.objects.filter(
                template=template,
                target_object=self.ward.character_sheet.character,
                is_active=True,
            ).exists()
        )
        self.assertFalse(
            ChallengeInstance.objects.filter(
                template=template,
                target_object=self.guard_b.character_sheet.character,
            ).exists()
        )


class GuardiansByTargetTests(TestCase):
    """``guardians_by_target`` reads guardians by field, oldest first, without self-guards."""

    def setUp(self) -> None:
        participants = CombatParticipantFactory.create_batch(4)
        self.ward, self.first, self.second, self.other_ward = (
            p.character_sheet.character for p in participants
        )
        self.watch = ConditionTemplateFactory(name="Tailing 4584", source_guards_bearer=True)
        self.plain = ConditionTemplateFactory(name="Watched 4584")

    def test_oldest_first_distinct_and_self_excluded(self) -> None:
        ConditionInstanceFactory(
            target=self.ward, condition=self.watch, source_character=self.first
        )
        ConditionInstanceFactory(
            target=self.ward,
            condition=ConditionTemplateFactory(name="Self watch 4584", source_guards_bearer=True),
            source_character=self.ward,
        )
        ConditionInstanceFactory(
            target=self.ward,
            condition=ConditionTemplateFactory(name="Escort 4584", source_guards_bearer=True),
            source_character=self.second,
        )
        ConditionInstanceFactory(
            target=self.ward,
            condition=ConditionTemplateFactory(
                name="Second escort 4584", source_guards_bearer=True
            ),
            source_character=self.first,
        )
        ConditionInstanceFactory(
            target=self.other_ward, condition=self.plain, source_character=self.first
        )
        ConditionInstanceFactory(
            target=self.other_ward, condition=self.watch, source_character=None
        )

        result = guardians_by_target([self.ward, self.other_ward])

        self.assertEqual(result, {self.ward.pk: [self.first.pk, self.second.pk]})
