"""GM-run standoffs: a firing cause becomes a GM proposal (#4354).

The Orders cause fires on a botch against the group (a provocation) or when the party
does not outweigh it. With a GM in the scene the group goes PROPOSED and the GM decides;
with none (a mission) it attacks on its own, as in slice 1.
"""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.checks.factories import CheckTypeFactory
from world.combat.constants import CauseKind, OpponentTier
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CreatureTemplateFactory,
    seed_scaling_defaults,
)
from world.conditions.factories import ConditionTemplateFactory
from world.gm.constants import GMPromptGroup, GMPromptKind, GMPromptStatus
from world.gm.models import GMPrompt, GMPromptFilter
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.standoffs.constants import (
    REASON_OUTWEIGHED,
    REASON_PROVOKED_PRESS,
    REASON_PROVOKED_TERMS,
    ProposalResolution,
    StandoffGroupState,
    TermsEffect,
)
from world.standoffs.factories import (
    FactionRuleFactory,
    StandoffApproachFactory,
    StandoffTermsFactory,
)
from world.standoffs.models import StandoffConfig
from world.standoffs.services.proposals import resolve_proposal, standoff_is_gm_run
from world.standoffs.services.state import is_in_standoff, open_standoff
from world.standoffs.services.verbs import standoff_press, standoff_read, standoff_terms
from world.traits.factories import CheckOutcomeFactory

CHECK = "world.standoffs.services.verbs.perform_check"
LEVEL = "world.standoffs.services.force.effective_combat_level"
STRONG = 100  # a party member this level outweighs the group by any margin
WEAK = 1  # one at this level does not


def forced(level: int) -> SimpleNamespace:
    outcome = CheckOutcomeFactory(name=f"Forced tier {level}", success_level=level)
    return SimpleNamespace(success_level=level, outcome=outcome, chart=None)


class ProposalBase(TestCase):
    """An Orders group in a scene; ``gm`` runs the scene unless a test removes them."""

    with_gm = True

    def setUp(self) -> None:
        # setUp, not setUpTestData: every test changes groups, prompts and morale.
        seed_scaling_defaults()
        self.scene = SceneFactory()
        self.gm = AccountFactory()
        if self.with_gm:
            SceneParticipationFactory(scene=self.scene, account=self.gm, is_gm=True)
        self.encounter = CombatEncounterFactory(scene=self.scene)
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        self.template = CreatureTemplateFactory(
            tier=OpponentTier.MOOK, cause=CauseKind.ORDERS, cause_margin_percent=0
        )
        for _ in range(2):
            CombatOpponentFactory(
                encounter=self.encounter, creature_template=self.template, level=4
            )
        config = StandoffConfig.load()
        config.read_check_type = CheckTypeFactory()
        config.terms_check_type = CheckTypeFactory()
        config.pass_condition = ConditionTemplateFactory()
        config.save()
        self.approach = StandoffApproachFactory()
        self.level = patch(LEVEL, return_value=STRONG)
        self.level.start()
        self.addCleanup(self.level.stop)
        self.group = open_standoff(self.encounter)[0]

    def botch_press(self):
        with patch(CHECK, return_value=forced(-2)):
            return standoff_press(self.participant, self.group, self.approach)

    def prompts(self) -> list[GMPrompt]:
        return list(GMPrompt.objects.filter(standoff_group=self.group))

    def refresh(self) -> None:
        self.group.refresh_from_db()
        self.encounter.refresh_from_db()


class OrdersInAGMRunStoryTests(ProposalBase):
    def test_the_scene_gm_makes_it_gm_run(self) -> None:
        self.assertTrue(standoff_is_gm_run(self.encounter))

    def test_a_strong_party_meets_no_proposal_on_arrival(self) -> None:
        self.assertEqual(self.group.state, StandoffGroupState.OPEN)
        self.assertEqual(self.prompts(), [])

    def test_a_botched_press_proposes_instead_of_attacking(self) -> None:
        result = self.botch_press()
        self.refresh()
        self.assertFalse(result.fight_started)
        self.assertEqual(self.group.state, StandoffGroupState.PROPOSED)
        self.assertEqual(self.group.proposal_reason, REASON_PROVOKED_PRESS)
        self.assertTrue(is_in_standoff(self.encounter))
        self.assertEqual(self.encounter.round_number, 0)
        (prompt,) = self.prompts()
        self.assertEqual(prompt.kind, GMPromptKind.STANDOFF_CAUSE)
        self.assertEqual(prompt.addressed_to, self.gm)
        self.assertEqual(prompt.status, GMPromptStatus.PENDING)

    def test_a_botched_terms_is_a_provocation_too(self) -> None:
        terms = StandoffTermsFactory(effect=TermsEffect.PASS)
        with patch(CHECK, return_value=forced(-2)):
            standoff_terms(self.participant, self.group, terms)
        self.refresh()
        self.assertEqual(self.group.proposal_reason, REASON_PROVOKED_TERMS)

    def test_players_keep_acting_while_the_gm_decides(self) -> None:
        self.botch_press()
        with patch(CHECK, return_value=forced(1)):
            result = standoff_press(self.participant, self.group, self.approach)
        self.refresh()
        self.assertTrue(result.success)
        self.assertEqual(self.group.terms_ease, 1)
        self.assertEqual(self.group.state, StandoffGroupState.PROPOSED)

    def test_settling_a_proposed_group_closes_its_prompt(self) -> None:
        self.botch_press()
        terms = StandoffTermsFactory(effect=TermsEffect.PASS)
        with patch(CHECK, return_value=forced(1)):
            result = standoff_terms(self.participant, self.group, terms)
        self.assertTrue(result.settled)
        (prompt,) = self.prompts()
        self.assertEqual(prompt.status, GMPromptStatus.DISMISSED)

    def test_a_weak_party_is_proposed_on_the_force_test_alone(self) -> None:
        self.level.stop()
        with patch(LEVEL, return_value=WEAK), patch(CHECK, return_value=forced(1)):
            standoff_read(self.participant, self.group)
        self.level.start()
        self.refresh()
        self.assertEqual(self.group.state, StandoffGroupState.PROPOSED)
        self.assertEqual(self.group.proposal_reason, REASON_OUTWEIGHED)

    def test_a_suppressing_faction_rule_stops_the_provocation(self) -> None:
        FactionRuleFactory(creature_template=self.template, rule={}, suppresses_cause=True)
        self.botch_press()
        self.refresh()
        self.assertEqual(self.group.state, StandoffGroupState.OPEN)
        self.assertEqual(self.prompts(), [])

    def test_firing_again_restates_the_reason_without_a_second_prompt(self) -> None:
        self.botch_press()
        terms = StandoffTermsFactory(effect=TermsEffect.PASS)
        with patch(CHECK, return_value=forced(-2)):
            standoff_terms(self.participant, self.group, terms)
        self.refresh()
        self.assertEqual(self.group.proposal_reason, REASON_PROVOKED_TERMS)
        self.assertEqual(len(self.prompts()), 1)


class ResolutionTests(ProposalBase):
    def setUp(self) -> None:
        super().setUp()
        self.botch_press()
        (self.prompt,) = self.prompts()

    def test_confirm_starts_the_fight_as_the_npcs_act(self) -> None:
        outcome = resolve_proposal(self.prompt, ProposalResolution.CONFIRM, resolver=self.gm)
        self.refresh()
        self.prompt.refresh_from_db()
        self.assertTrue(outcome.fight_started)
        self.assertEqual(self.group.state, StandoffGroupState.FIGHTING)
        self.assertIs(self.encounter.initiated_by_pc_side, False)
        self.assertEqual(self.encounter.round_number, 1)
        self.assertEqual(self.prompt.status, GMPromptStatus.CONFIRMED)
        self.assertEqual(self.prompt.resolved_by, self.gm)

    def test_hold_reopens_and_the_next_action_tests_again(self) -> None:
        resolve_proposal(self.prompt, ProposalResolution.HOLD, resolver=self.gm)
        self.refresh()
        self.assertEqual(self.group.state, StandoffGroupState.OPEN)
        # The provocation is past; a strong party does not fire the force test.
        with patch(CHECK, return_value=forced(1)):
            standoff_read(self.participant, self.group)
        self.refresh()
        self.assertEqual(self.group.state, StandoffGroupState.OPEN)
        # A weak party does: the next action proposes again.
        self.level.stop()
        with patch(LEVEL, return_value=WEAK), patch(CHECK, return_value=forced(1)):
            standoff_press(self.participant, self.group, self.approach)
        self.level.start()
        self.refresh()
        self.assertEqual(self.group.state, StandoffGroupState.PROPOSED)
        self.assertEqual(
            sorted(p.status for p in self.prompts()),
            sorted([GMPromptStatus.PENDING, GMPromptStatus.DISMISSED]),
        )

    def test_override_needs_a_reason(self) -> None:
        outcome = resolve_proposal(self.prompt, ProposalResolution.OVERRIDE, resolver=self.gm)
        self.refresh()
        self.assertFalse(outcome.success)
        self.assertEqual(self.group.state, StandoffGroupState.PROPOSED)

    def test_override_records_the_reason_and_holds_until_force_moves(self) -> None:
        resolve_proposal(
            self.prompt,
            ProposalResolution.OVERRIDE,
            resolver=self.gm,
            reason="PLACEHOLDER override reason",
        )
        self.prompt.refresh_from_db()
        self.assertEqual(self.prompt.resolution_note, "Overridden: PLACEHOLDER override reason")
        self.refresh()
        self.assertEqual(self.group.state, StandoffGroupState.OPEN)
        # Same force: no re-test fires even though nothing has changed.
        with patch(CHECK, return_value=forced(1)):
            standoff_read(self.participant, self.group)
        self.refresh()
        self.assertEqual(self.group.state, StandoffGroupState.OPEN)
        # A botch ends the override.
        self.botch_press()
        self.refresh()
        self.assertEqual(self.group.state, StandoffGroupState.PROPOSED)

    def test_a_proposal_the_standoff_moved_past_closes_with_nothing_done(self) -> None:
        from world.standoffs.services.verbs import standoff_fight

        standoff_fight(self.participant, self.encounter)
        self.prompt.refresh_from_db()
        self.assertEqual(self.prompt.status, GMPromptStatus.DISMISSED)
        outcome = resolve_proposal(self.prompt, ProposalResolution.CONFIRM, resolver=self.gm)
        self.assertFalse(outcome.success)


class NoGMTests(ProposalBase):
    with_gm = False

    def test_a_botch_starts_the_fight_on_its_own(self) -> None:
        result = self.botch_press()
        self.refresh()
        self.assertTrue(result.fight_started)
        self.assertEqual(self.group.state, StandoffGroupState.FIGHTING)
        self.assertEqual(self.prompts(), [])


class MutedGMTests(ProposalBase):
    def setUp(self) -> None:
        super().setUp()
        GMPromptFilter.objects.create(account=self.gm, group=GMPromptGroup.STANDOFF, enabled=False)

    def test_a_gm_who_muted_standoffs_lets_the_cause_act(self) -> None:
        self.assertFalse(standoff_is_gm_run(self.encounter))
        result = self.botch_press()
        self.assertTrue(result.fight_started)


class PredationIgnoresProvocationTests(ProposalBase):
    def test_a_botch_against_a_predation_group_is_no_provocation(self) -> None:
        self.template.cause = CauseKind.PREDATION
        self.template.save(update_fields=["cause"])
        self.botch_press()
        self.refresh()
        self.assertEqual(self.group.state, StandoffGroupState.OPEN)
