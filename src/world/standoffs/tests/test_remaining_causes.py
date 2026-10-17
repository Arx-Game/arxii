"""The remaining causes and the re-test on a broken hold (#4415).

Hunger widens its margin with every action nobody feeds them; Hatred fires only on a
character matching a provoking faction rule, whatever the force, until the group breaks;
Territory runs out of patience after a set number of actions and warns one action
earlier. A Calm or Charmed hold that ends asks the NPC's cause again: it leaves when the
reason no longer holds, and fights (or is proposed to the GM) when it does.

Party level is patched (as in ``test_force``): two level-4 mooks weigh 8, and one party
member at ``PARTY`` weighs 10.
"""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from world.combat.constants import CauseKind, OpponentStatus, OpponentTier
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CreatureTemplateFactory,
)
from world.conditions.constants import Allegiance, DurationType
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.gm.constants import GMPromptKind
from world.gm.models import GMPrompt
from world.npc_services.allegiance_outcomes import lapsed_allegiance_sweep
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.societies.factories import OrganizationFactory
from world.standoffs.constants import (
    REASON_HUNGER,
    REASON_OUTWEIGHED,
    REASON_RULE_PROVOKES,
    REASON_TERRITORY,
    CauseEffect,
    StandoffGroupState,
)
from world.standoffs.factories import (
    FactionRuleFactory,
    StandoffGroupFactory,
    restamp_from_templates,
)
from world.standoffs.models import StandoffConfig
from world.standoffs.services.force import (
    cause_clock,
    cause_fire_reason,
    evaluate_causes,
    patience_line,
)
from world.standoffs.services.gm_view import build_gm_standoff_view
from world.standoffs.services.release import retest_cause_on_release
from world.standoffs.services.state import is_in_standoff, open_standoff
from world.traits.factories import CheckOutcomeFactory

LEVEL = "world.standoffs.services.force.effective_combat_level"
PARTY = 10  # one member at this level weighs 10 against the mooks' 8
STRONG = 100
WEAK = 1


class CauseBase(TestCase):
    cause = CauseKind.PREDATION

    def setUp(self) -> None:
        # setUp, not setUpTestData: every test moves groups, clocks and morale.
        self.encounter = CombatEncounterFactory()
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        self.template = CreatureTemplateFactory(
            tier=OpponentTier.MOOK, cause=self.cause, cause_margin_percent=0
        )
        self.mooks = [
            CombatOpponentFactory(
                encounter=self.encounter,
                creature_template=self.template,
                tier=OpponentTier.MOOK,
                level=4,
            )
            for _ in range(2)
        ]
        self.config = StandoffConfig.load()

    def group(self, **kwargs):
        return StandoffGroupFactory(
            encounter=self.encounter, creature_template=self.template, **kwargs
        )

    def reason(self, group, level: int = PARTY) -> str | None:
        with patch(LEVEL, return_value=level):
            return cause_fire_reason(group, self.config)


class HungerTests(CauseBase):
    cause = CauseKind.HUNGER

    def test_a_fed_or_fresh_crowd_holds_back_from_a_party_that_outweighs_it(self) -> None:
        self.assertIsNone(self.reason(self.group()))

    def test_the_margin_widens_each_action_nobody_feeds_them(self) -> None:
        # step 10: 8 x 120 = 960 < 1000 holds; 8 x 130 = 1040 fires.
        self.assertIsNone(self.reason(self.group(actions_elapsed=2)))
        self.assertEqual(
            self.reason(self.group(actions_elapsed=3)), REASON_HUNGER.format(margin=30)
        )

    def test_a_weak_party_meets_the_plain_reason_before_any_action(self) -> None:
        self.assertEqual(self.reason(self.group(), WEAK), REASON_OUTWEIGHED)

    def test_the_gm_reads_the_widened_margin(self) -> None:
        clock = cause_clock(self.group(actions_elapsed=3), self.config)
        self.assertEqual(clock, "Hunger margin 30%, widening 10 each action nobody feeds them.")

    def test_each_party_action_moves_the_clock_and_arrival_does_not(self) -> None:
        with patch(LEVEL, return_value=PARTY):
            (group,) = open_standoff(self.encounter)
            group.refresh_from_db()
            self.assertEqual(group.actions_elapsed, 0)
            for _ in range(3):
                evaluate_causes(self.encounter, [], after_action=True)
        self.encounter.refresh_from_db()
        group.refresh_from_db()
        self.assertEqual(group.actions_elapsed, 3)
        self.assertFalse(is_in_standoff(self.encounter))
        self.assertIs(self.encounter.initiated_by_pc_side, False)


class HatredTests(CauseBase):
    cause = CauseKind.HATRED

    def test_without_a_provoking_rule_they_never_fire_even_on_a_weak_party(self) -> None:
        self.assertIsNone(self.reason(self.group(), WEAK))

    def test_a_provoking_rule_fires_whatever_the_force(self) -> None:
        FactionRuleFactory(creature_template=self.template, rule={}, cause_effect="provoke")
        name = self.participant.character_sheet.character.key
        with patch("world.standoffs.services.force._presented_name", return_value=name):
            reason = self.reason(self.group(), STRONG)
        self.assertEqual(reason, REASON_RULE_PROVOKES.format(name=name))

    def test_a_broken_group_is_past_its_hatred(self) -> None:
        FactionRuleFactory(creature_template=self.template, rule={}, cause_effect="provoke")
        for mook in self.mooks:
            mook.morale = 0
            mook.save(update_fields=["morale"])
        self.assertIsNone(self.reason(self.group(), STRONG))

    def test_one_unbroken_member_keeps_the_hatred(self) -> None:
        FactionRuleFactory(creature_template=self.template, rule={}, cause_effect="provoke")
        self.mooks[0].morale = 0
        self.mooks[0].save(update_fields=["morale"])
        self.assertIsNotNone(self.reason(self.group(), STRONG))


class CauseEffectTests(CauseBase):
    def test_a_provoking_rule_sets_off_a_predation_group_the_party_outweighs(self) -> None:
        FactionRuleFactory(creature_template=self.template, rule={}, cause_effect="provoke")
        self.assertIsNotNone(self.reason(self.group(), STRONG))

    def test_suppression_still_stops_a_weak_party_being_hunted(self) -> None:
        FactionRuleFactory(
            creature_template=self.template, rule={}, cause_effect=CauseEffect.SUPPRESS
        )
        self.assertIsNone(self.reason(self.group(), WEAK))

    def test_the_most_specific_rule_decides_between_suppress_and_provoke(self) -> None:
        company = OrganizationFactory()
        self.template.organization = company
        self.template.save(update_fields=["organization"])
        restamp_from_templates(self.encounter)
        FactionRuleFactory(
            creature_template=None, organization=company, rule={}, cause_effect="provoke"
        )
        FactionRuleFactory(
            creature_template=self.template, rule={}, cause_effect=CauseEffect.SUPPRESS
        )
        self.assertIsNone(self.reason(self.group(), WEAK))

    def test_a_provoke_at_the_same_level_beats_a_suppress(self) -> None:
        FactionRuleFactory(
            creature_template=self.template, rule={}, cause_effect=CauseEffect.SUPPRESS
        )
        FactionRuleFactory(creature_template=self.template, rule={}, cause_effect="provoke")
        self.assertIsNotNone(self.reason(self.group(), STRONG))


class TerritoryTests(CauseBase):
    cause = CauseKind.TERRITORY

    def test_they_hold_while_patience_lasts_and_fire_when_it_runs_out(self) -> None:
        self.assertIsNone(self.reason(self.group(actions_elapsed=2), WEAK))
        self.assertEqual(
            self.reason(self.group(actions_elapsed=3), STRONG), REASON_TERRITORY.format(count=3)
        )

    def test_they_warn_one_action_before_and_then_attack(self) -> None:
        with patch(LEVEL, return_value=STRONG):
            (group,) = open_standoff(self.encounter)
            first: list[str] = []
            evaluate_causes(self.encounter, first, after_action=True)
            second: list[str] = []
            evaluate_causes(self.encounter, second, after_action=True)
            third: list[str] = []
            started = evaluate_causes(self.encounter, third, after_action=True)
        self.assertEqual(first, [])
        self.assertEqual(second, [patience_line(group)])
        self.assertEqual(patience_line(group), f"The {self.template.name} are losing patience.")
        self.assertTrue(started)
        self.assertEqual(third, [f"The {self.template.name} attack!"])

    def test_a_suppressing_rule_quiets_the_warning(self) -> None:
        FactionRuleFactory(
            creature_template=self.template, rule={}, cause_effect=CauseEffect.SUPPRESS
        )
        with patch(LEVEL, return_value=STRONG):
            open_standoff(self.encounter)
            lines: list[str] = []
            for _ in range(3):
                evaluate_causes(self.encounter, lines, after_action=True)
        self.assertEqual(lines, [])
        self.assertTrue(is_in_standoff(self.encounter))

    def test_the_gm_reads_the_patience_left(self) -> None:
        self.assertEqual(
            cause_clock(self.group(actions_elapsed=1), self.config), "Patience: 1 of 3 actions."
        )

    def test_the_gm_view_and_its_telnet_text_carry_the_clock_and_the_rule_effect(self) -> None:
        from commands.standoff import _render_gm_view

        FactionRuleFactory(creature_template=self.template, rule={}, cause_effect="provoke")
        for mook in self.mooks:
            mook.morale = 0  # broken: past the provoking rule, so the standoff stays open
            mook.save(update_fields=["morale"])
        with patch(LEVEL, return_value=STRONG):
            open_standoff(self.encounter)
            evaluate_causes(self.encounter, [], after_action=True)
            view = build_gm_standoff_view(self.encounter)
        (group,) = view.groups
        self.assertEqual(group.cause_clock, "Patience: 1 of 3 actions.")
        self.assertEqual(group.faction_rules[0].cause_effect, CauseEffect.PROVOKE)
        text = "\n".join(_render_gm_view(view))
        self.assertIn("    Patience: 1 of 3 actions.", text)
        self.assertIn(" - provokes them - matches", text)


class TerritoryInAGMRunSceneTests(CauseBase):
    cause = CauseKind.TERRITORY

    def setUp(self) -> None:
        super().setUp()
        self.gm = AccountFactory()
        scene = SceneFactory()
        SceneParticipationFactory(scene=scene, account=self.gm, is_gm=True)
        self.encounter.scene = scene
        self.encounter.save(update_fields=["scene"])

    def test_running_out_of_patience_is_a_proposal(self) -> None:
        with patch(LEVEL, return_value=STRONG):
            (group,) = open_standoff(self.encounter)
            for _ in range(3):
                evaluate_causes(self.encounter, [], after_action=True)
        group.refresh_from_db()
        self.assertEqual(group.state, StandoffGroupState.PROPOSED)
        self.assertEqual(group.proposal_reason, REASON_TERRITORY.format(count=3))
        self.assertTrue(
            GMPrompt.objects.filter(standoff_group=group, kind=GMPromptKind.STANDOFF_CAUSE)
        )


class ReleaseTests(CauseBase):
    """A hold on a member ended: its cause decides what it does next."""

    cause = CauseKind.ORDERS

    def settled_group(self):
        return self.group(
            state=StandoffGroupState.SETTLED, settled_outcome=CheckOutcomeFactory(success_level=1)
        )

    def release(self, level: int = PARTY) -> None:
        with patch(LEVEL, return_value=level):
            retest_cause_on_release(self.mooks[0].objectdb)
        self.mooks[0].refresh_from_db()
        self.encounter.refresh_from_db()

    def test_orders_met_by_terms_send_them_away_instead_of_attacking(self) -> None:
        self.settled_group()
        self.release(WEAK)
        self.assertEqual(self.mooks[0].status, OpponentStatus.FLED)
        self.assertEqual(self.mooks[1].status, OpponentStatus.ACTIVE)

    def test_a_predation_group_paid_off_still_hunts_a_weak_party(self) -> None:
        self.template.cause = CauseKind.PREDATION
        self.template.save(update_fields=["cause"])
        restamp_from_templates(self.encounter)
        group = self.settled_group()
        self.release(WEAK)
        group.refresh_from_db()
        self.assertEqual(self.mooks[0].status, OpponentStatus.ACTIVE)
        self.assertEqual(group.state, StandoffGroupState.FIGHTING)
        self.assertIsNone(group.settled_outcome)
        self.assertEqual(self.encounter.round_number, 1)
        self.assertIs(self.encounter.initiated_by_pc_side, False)

    def test_a_predation_group_a_strong_party_outweighs_leaves(self) -> None:
        self.template.cause = CauseKind.PREDATION
        self.template.save(update_fields=["cause"])
        restamp_from_templates(self.encounter)
        self.settled_group()
        self.release(STRONG)
        self.assertEqual(self.mooks[0].status, OpponentStatus.FLED)

    def test_in_a_gm_run_scene_the_cause_holding_is_a_proposal(self) -> None:
        self.template.cause = CauseKind.PREDATION
        self.template.save(update_fields=["cause"])
        restamp_from_templates(self.encounter)
        scene = SceneFactory()
        SceneParticipationFactory(scene=scene, account=AccountFactory(), is_gm=True)
        self.encounter.scene = scene
        self.encounter.save(update_fields=["scene"])
        group = self.settled_group()
        self.release(WEAK)
        group.refresh_from_db()
        self.assertEqual(group.state, StandoffGroupState.PROPOSED)
        self.assertTrue(group.proposal_reason.startswith("A hold on them ended"))
        self.assertEqual(self.encounter.round_number, 0)

    def test_mid_fight_a_released_mook_with_no_reason_left_leaves(self) -> None:
        self.encounter.round_number = 2
        self.encounter.save(update_fields=["round_number"])
        self.release(STRONG)
        self.assertEqual(self.mooks[0].status, OpponentStatus.FLED)

    def test_mid_fight_a_released_mook_whose_cause_holds_fights_on(self) -> None:
        self.encounter.round_number = 2
        self.encounter.save(update_fields=["round_number"])
        self.release(WEAK)
        self.assertEqual(self.mooks[0].status, OpponentStatus.ACTIVE)

    def test_no_cause_is_left_alone(self) -> None:
        self.template.cause = CauseKind.NONE
        self.template.save(update_fields=["cause"])
        restamp_from_templates(self.encounter)
        self.settled_group()
        self.release(STRONG)
        self.assertEqual(self.mooks[0].status, OpponentStatus.ACTIVE)

    def test_a_finished_encounter_is_left_alone(self) -> None:
        self.settled_group()
        self.encounter.status = RoundStatus.COMPLETED
        self.encounter.save(update_fields=["status"])
        self.release(STRONG)
        self.assertEqual(self.mooks[0].status, OpponentStatus.ACTIVE)

    def test_the_lapse_sweep_runs_the_retest(self) -> None:
        self.settled_group()
        calm = ConditionTemplateFactory(
            name="Calm 4415",
            default_duration_type=DurationType.INGAME_TIME,
            sets_allegiance=Allegiance.NEUTRAL,
        )
        ConditionInstanceFactory(
            target=self.mooks[0].objectdb,
            condition=calm,
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        with patch(LEVEL, return_value=STRONG):
            lapsed_allegiance_sweep()
        self.mooks[0].refresh_from_db()
        self.assertEqual(self.mooks[0].status, OpponentStatus.FLED)
