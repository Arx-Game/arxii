"""Standoff verbs: read, press, terms, fight and share a spark."""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from world.checks.factories import CheckTypeFactory
from world.checks.social_target import SocialDifficulty
from world.combat.constants import CauseKind, OpponentStatus, OpponentTier
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CreatureTemplateFactory,
    seed_scaling_defaults,
)
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.mechanics.factories import ApplicationFactory
from world.standoffs.constants import DriveStrength, RevealKind, StandoffGroupState, TermsEffect
from world.standoffs.factories import (
    CreatureDriveFactory,
    RegardRuleFactory,
    StandoffApproachFactory,
    StandoffRevealFactory,
    StandoffTermsFactory,
)
from world.standoffs.models import StandoffConfig, StandoffReveal, StandoffSparkShare
from world.standoffs.services.force import evaluate_causes
from world.standoffs.services.state import is_in_standoff, open_standoff
from world.standoffs.services.verbs import (
    press_difficulty,
    standoff_fight,
    standoff_press,
    standoff_read,
    standoff_share_spark,
    standoff_terms,
)
from world.traits.factories import CheckOutcomeFactory

CHECK = "world.standoffs.services.verbs.perform_check"
SOCIAL = "world.standoffs.services.verbs.social_target_difficulty"


def forced(level: int) -> SimpleNamespace:
    outcome = CheckOutcomeFactory(name=f"Forced tier {level}", success_level=level)
    return SimpleNamespace(success_level=level, outcome=outcome, chart=None)


class VerbBase(TestCase):
    def setUp(self) -> None:
        # setUp, not setUpTestData: tests mutate groups, opponents and the config.
        seed_scaling_defaults()
        self.encounter = CombatEncounterFactory()
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        self.template = CreatureTemplateFactory(tier=OpponentTier.MOOK, cause=CauseKind.NONE)
        self.members = [
            CombatOpponentFactory(
                encounter=self.encounter, creature_template=self.template, level=2
            )
            for _ in range(2)
        ]
        self.config = StandoffConfig.load()
        self.config.read_check_type = CheckTypeFactory()
        self.config.terms_check_type = CheckTypeFactory()
        self.config.pass_condition = ConditionTemplateFactory()
        self.config.turn_condition = ConditionTemplateFactory()
        self.config.save()
        self.group = open_standoff(self.encounter)[0]


class ReadTests(VerbBase):
    def setUp(self) -> None:
        super().setUp()
        self.template.cause = CauseKind.PREDATION
        self.template.save(update_fields=["cause"])
        self.drive = CreatureDriveFactory(
            creature_template=self.template, strength=DriveStrength.MAJOR
        )

    def test_success_reveals_the_focus(self) -> None:
        with patch(CHECK, return_value=forced(1)):
            result = standoff_read(self.participant, self.group, focus_kind=RevealKind.CAUSE)
        self.assertTrue(result.success)
        self.assertEqual([r.kind for r in result.revealed], [RevealKind.CAUSE])

    def test_success_focus_on_a_drive(self) -> None:
        with patch(CHECK, return_value=forced(1)):
            result = standoff_read(
                self.participant,
                self.group,
                focus_kind=RevealKind.DRIVE,
                focus_drive_id=self.drive.pk,
            )
        self.assertEqual([r.drive_id for r in result.revealed], [self.drive.pk])

    def test_success_drive_focus_without_an_id_reveals_the_strongest_drive(self) -> None:
        CreatureDriveFactory(creature_template=self.template, strength=DriveStrength.MINOR)
        with patch(CHECK, return_value=forced(1)):
            result = standoff_read(self.participant, self.group, focus_kind=RevealKind.DRIVE)
        self.assertEqual([r.drive_id for r in result.revealed], [self.drive.pk])

    def test_partial_reveals_exactly_one(self) -> None:
        with patch(CHECK, return_value=forced(0)):
            result = standoff_read(self.participant, self.group)
        self.assertEqual(len(result.revealed), 1)

    def test_critical_reveals_everything(self) -> None:
        with patch(CHECK, return_value=forced(2)):
            result = standoff_read(self.participant, self.group)
        self.assertEqual({r.kind for r in result.revealed}, {RevealKind.CAUSE, RevealKind.DRIVE})

    def test_failure_reveals_nothing(self) -> None:
        with patch(CHECK, return_value=forced(-1)):
            result = standoff_read(self.participant, self.group)
        self.assertFalse(result.success)
        self.assertFalse(StandoffReveal.objects.exists())

    def test_nothing_hidden_is_refused_without_a_roll(self) -> None:
        StandoffRevealFactory(group=self.group, kind=RevealKind.CAUSE)
        StandoffRevealFactory(group=self.group, kind=RevealKind.DRIVE, drive=self.drive)
        with patch(CHECK) as roll:
            result = standoff_read(self.participant, self.group)
        self.assertFalse(result.success)
        roll.assert_not_called()

    def test_unmatched_regard_rule_is_not_hidden_for_the_party(self) -> None:
        # A rule needing a species no participant has never shows up as readable.
        RegardRuleFactory(
            creature_template=self.template,
            rule={"leaf": "has_species", "params": {"species_id": 999999}},
        )
        with patch(CHECK, return_value=forced(2)):
            result = standoff_read(self.participant, self.group)
        self.assertNotIn(RevealKind.REGARD, {r.kind for r in result.revealed})


class PressTests(VerbBase):
    def setUp(self) -> None:
        super().setUp()
        self.approach = StandoffApproachFactory()

    def test_success_eases_terms(self) -> None:
        with patch(CHECK, return_value=forced(1)):
            result = standoff_press(self.participant, self.group, self.approach)
        self.assertTrue(result.success)
        self.group.refresh_from_db()
        self.assertEqual(self.group.terms_ease, 1)

    def test_a_critical_press_still_eases_once(self) -> None:
        with patch(CHECK, return_value=forced(2)):
            standoff_press(self.participant, self.group, self.approach)
        self.group.refresh_from_db()
        self.assertEqual(self.group.terms_ease, 1)

    def test_two_presses_each_ease_once(self) -> None:
        with patch(CHECK, return_value=forced(1)):
            standoff_press(self.participant, self.group, self.approach)
            standoff_press(self.participant, self.group, self.approach)
        self.group.refresh_from_db()
        self.assertEqual(self.group.terms_ease, 2)

    def test_last_group_emptied_completes_the_standoff(self) -> None:
        for member in self.members:
            member.status = OpponentStatus.FLED
            member.save(update_fields=["status"])
        with patch("world.standoffs.services.routing.complete_standoff") as complete:
            self.assertFalse(evaluate_causes(self.encounter))
        complete.assert_called_once_with(self.encounter)
        self.group.refresh_from_db()
        self.assertEqual(self.group.state, StandoffGroupState.SETTLED)

    def test_botch_emboldens(self) -> None:
        with patch(CHECK, return_value=forced(-2)):
            standoff_press(self.participant, self.group, self.approach)
        self.group.refresh_from_db()
        self.assertEqual(self.group.emboldened_bands, self.config.botch_force_bands)

    def test_morale_damaging_approach_wears_down_members(self) -> None:
        self.approach.damages_morale = True
        self.approach.save(update_fields=["damages_morale"])
        before = self.members[0].morale
        with patch(CHECK, return_value=forced(1)):
            standoff_press(self.participant, self.group, self.approach)
        self.members[0].refresh_from_db()
        self.assertLess(self.members[0].morale, before)

    def test_refused_after_the_fight_began_without_a_roll(self) -> None:
        standoff_fight(self.participant, self.encounter)
        with patch(CHECK) as roll:
            result = standoff_press(self.participant, self.group, self.approach)
        self.assertFalse(result.success)
        roll.assert_not_called()

    def test_refused_on_a_settled_group_without_a_roll(self) -> None:
        self.group.state = StandoffGroupState.SETTLED
        self.group.save(update_fields=["state"])
        with patch(CHECK) as roll:
            result = standoff_press(self.participant, self.group, self.approach)
        self.assertFalse(result.success)
        roll.assert_not_called()

    def test_a_drive_the_approach_targets_is_passed_as_a_hit(self) -> None:
        drive = CreatureDriveFactory(creature_template=self.template, strength=DriveStrength.MAJOR)
        ApplicationFactory(capability=self.approach.capability, target_property=drive.property)
        with (
            patch(CHECK, return_value=forced(0)),
            patch(SOCIAL, return_value=SocialDifficulty(difficulty=5)) as graded,
        ):
            standoff_press(self.participant, self.group, self.approach)
        hits = graded.call_args.kwargs["drive_hits"]
        self.assertEqual([(h.label, h.strength) for h in hits], [(drive.property.name, 2)])

    def test_hidden_drive_still_eases_but_is_not_named(self) -> None:
        drive = CreatureDriveFactory(creature_template=self.template, strength=DriveStrength.MAJOR)
        ApplicationFactory(capability=self.approach.capability, target_property=drive.property)
        with patch(CHECK, return_value=forced(1)):
            hidden = standoff_press(self.participant, self.group, self.approach)
        self.assertNotIn(drive.property.name, hidden.message)
        self.assertEqual(
            press_difficulty(
                self.group, self.participant.character_sheet, self.approach
            ).eased_bands,
            2,
        )
        StandoffRevealFactory(group=self.group, kind=RevealKind.DRIVE, drive=drive)
        with patch(CHECK, return_value=forced(1)):
            shown = standoff_press(self.participant, self.group, self.approach)
        self.assertIn(drive.property.name, shown.message)

    def test_botch_can_tip_a_predator_into_a_fight(self) -> None:
        self.template.cause = CauseKind.PREDATION
        self.template.save(update_fields=["cause"])
        with (
            patch(CHECK, return_value=forced(-2)),
            patch("world.standoffs.services.verbs.evaluate_causes", return_value=True),
        ):
            result = standoff_press(self.participant, self.group, self.approach)
        self.assertTrue(result.fight_started)


class TermsTests(VerbBase):
    def setUp(self) -> None:
        super().setUp()
        self.terms = StandoffTermsFactory(effect=TermsEffect.PASS)

    def test_success_settles_and_applies_the_pass_condition(self) -> None:
        other = CreatureTemplateFactory(cause=CauseKind.NONE)
        CombatOpponentFactory(encounter=self.encounter, creature_template=other)
        self.group.refresh_from_db()
        from world.standoffs.models import StandoffGroup

        StandoffGroup.objects.create(encounter=self.encounter, creature_template=other)
        with patch(CHECK, return_value=forced(1)):
            result = standoff_terms(self.participant, self.group, self.terms)
        self.assertTrue(result.settled)
        self.group.refresh_from_db()
        self.assertEqual(self.group.state, StandoffGroupState.SETTLED)
        self.assertEqual(self.group.settled_outcome.success_level, 1)
        for member in self.members:
            self.assertTrue(
                ConditionInstance.objects.filter(
                    target=member.objectdb, condition=self.config.pass_condition
                ).exists()
            )
        self.assertTrue(is_in_standoff(self.encounter))

    def test_partial_settles_with_the_partial_outcome(self) -> None:
        with patch(CHECK, return_value=forced(0)):
            standoff_terms(self.participant, self.group, self.terms)
        self.group.refresh_from_db()
        self.assertEqual(self.group.settled_outcome.success_level, 0)

    def test_failure_leaves_the_group_open(self) -> None:
        with patch(CHECK, return_value=forced(-1)):
            result = standoff_terms(self.participant, self.group, self.terms)
        self.assertFalse(result.success)
        self.group.refresh_from_db()
        self.assertEqual(self.group.state, StandoffGroupState.OPEN)

    def test_botch_emboldens(self) -> None:
        with patch(CHECK, return_value=forced(-2)):
            standoff_terms(self.participant, self.group, self.terms)
        self.group.refresh_from_db()
        self.assertEqual(self.group.emboldened_bands, self.config.botch_force_bands)

    def test_flee_sends_members_away(self) -> None:
        terms = StandoffTermsFactory(effect=TermsEffect.FLEE)
        with patch(CHECK, return_value=forced(1)):
            standoff_terms(self.participant, self.group, terms)
        for member in self.members:
            member.refresh_from_db()
            self.assertEqual(member.status, OpponentStatus.FLED)

    def test_required_unrevealed_drive_is_refused_without_a_roll(self) -> None:
        drive = CreatureDriveFactory(creature_template=self.template)
        terms = StandoffTermsFactory(required_drive=drive.property)
        with patch(CHECK) as roll:
            result = standoff_terms(self.participant, self.group, terms)
        self.assertFalse(result.success)
        roll.assert_not_called()
        StandoffRevealFactory(group=self.group, kind=RevealKind.DRIVE, drive=drive)
        with patch(CHECK, return_value=forced(1)):
            self.assertTrue(standoff_terms(self.participant, self.group, terms).success)

    def test_second_terms_on_a_settled_group_is_refused(self) -> None:
        other = CreatureTemplateFactory(cause=CauseKind.NONE)
        CombatOpponentFactory(encounter=self.encounter, creature_template=other)
        from world.standoffs.models import StandoffGroup

        StandoffGroup.objects.create(encounter=self.encounter, creature_template=other)
        with patch(CHECK, return_value=forced(1)):
            standoff_terms(self.participant, self.group, self.terms)
        with patch(CHECK) as roll:
            second = standoff_terms(self.participant, self.group, self.terms)
        self.assertFalse(second.success)
        roll.assert_not_called()

    def test_terms_ease_takes_bands_off_the_difficulty(self) -> None:
        from world.standoffs.services.verbs import terms_difficulty

        self.group.terms_ease = 2
        with patch(SOCIAL, return_value=SocialDifficulty(difficulty=0)) as graded:
            terms_difficulty(self.group, self.participant.character_sheet, self.terms)
        self.assertEqual(graded.call_args.kwargs["extra_bands"], -2)

    def test_settling_every_group_completes_as_a_victory(self) -> None:
        with patch(CHECK, return_value=forced(1)):
            result = standoff_terms(self.participant, self.group, self.terms)
        self.assertTrue(result.settled)
        self.encounter.refresh_from_db()
        from world.combat.constants import EncounterOutcome

        self.assertEqual(self.encounter.outcome, EncounterOutcome.VICTORY)


class FightTests(VerbBase):
    def test_fight_breaks_the_standoff(self) -> None:
        result = standoff_fight(self.participant, self.encounter)
        self.assertTrue(result.fight_started)
        self.encounter.refresh_from_db()
        self.assertFalse(is_in_standoff(self.encounter))
        self.assertIs(self.encounter.initiated_by_pc_side, True)

    def test_second_fight_is_refused(self) -> None:
        standoff_fight(self.participant, self.encounter)
        self.assertFalse(standoff_fight(self.participant, self.encounter).success)

    def test_terms_after_the_fight_are_refused(self) -> None:
        standoff_fight(self.participant, self.encounter)
        with patch(CHECK) as roll:
            result = standoff_terms(
                self.participant, self.group, StandoffTermsFactory(effect=TermsEffect.PASS)
            )
        self.assertFalse(result.success)
        roll.assert_not_called()


class ShareSparkTests(VerbBase):
    def test_matching_rule_is_shared_once(self) -> None:
        rule = RegardRuleFactory(creature_template=self.template, rule={})
        self.assertTrue(standoff_share_spark(self.participant, self.group, rule).success)
        standoff_share_spark(self.participant, self.group, rule)
        self.assertEqual(StandoffSparkShare.objects.count(), 1)

    def test_rule_that_does_not_match_is_refused(self) -> None:
        rule = RegardRuleFactory(
            creature_template=self.template,
            rule={"leaf": "has_species", "params": {"species_id": 999999}},
        )
        self.assertFalse(standoff_share_spark(self.participant, self.group, rule).success)
        self.assertFalse(StandoffSparkShare.objects.exists())


class ActingOnASparkRevealsItTests(VerbBase):
    """A press or terms that a regard rule shifted shares that spark with the group."""

    def setUp(self) -> None:
        super().setUp()
        self.approach = StandoffApproachFactory()
        self.terms = StandoffTermsFactory(effect=TermsEffect.PASS)

    def _shares(self) -> int:
        return StandoffSparkShare.objects.filter(group=self.group).count()

    def test_press_shifted_by_a_rule_shares_it(self) -> None:
        rule = RegardRuleFactory(
            creature_template=self.template, rule={}, difficulty_shift_bands=-1
        )
        with patch(CHECK, return_value=forced(1)):
            standoff_press(self.participant, self.group, self.approach)
        share = StandoffSparkShare.objects.get(group=self.group)
        self.assertEqual(share.regard_rule, rule)
        self.assertEqual(share.character_sheet, self.participant.character_sheet)

    def test_press_with_an_inert_rule_shares_nothing(self) -> None:
        RegardRuleFactory(creature_template=self.template, rule={})
        with patch(CHECK, return_value=forced(1)):
            standoff_press(self.participant, self.group, self.approach)
        self.assertEqual(self._shares(), 0)

    def test_press_hitting_a_rules_drive_shares_it(self) -> None:
        drive = CreatureDriveFactory(creature_template=self.template, strength=DriveStrength.MINOR)
        ApplicationFactory(capability=self.approach.capability, target_property=drive.property)
        rule = RegardRuleFactory(
            creature_template=self.template, rule={}, drive=drive.property, drive_shift=1
        )
        with patch(CHECK, return_value=forced(1)):
            standoff_press(self.participant, self.group, self.approach)
        shared = list(StandoffSparkShare.objects.values_list("regard_rule", flat=True))
        self.assertEqual(shared, [rule.pk])

    def test_press_aimed_at_a_drive_the_rule_weakened_to_zero_still_shares(self) -> None:
        drive = CreatureDriveFactory(creature_template=self.template, strength=DriveStrength.MINOR)
        ApplicationFactory(capability=self.approach.capability, target_property=drive.property)
        rule = RegardRuleFactory(
            creature_template=self.template, rule={}, drive=drive.property, drive_shift=-1
        )
        with patch(CHECK, return_value=forced(1)):
            standoff_press(self.participant, self.group, self.approach)
        shared = list(StandoffSparkShare.objects.values_list("regard_rule", flat=True))
        self.assertEqual(shared, [rule.pk])

    def test_a_rule_naming_a_drive_with_no_shift_shares_nothing(self) -> None:
        drive = CreatureDriveFactory(creature_template=self.template, strength=DriveStrength.MINOR)
        ApplicationFactory(capability=self.approach.capability, target_property=drive.property)
        RegardRuleFactory(
            creature_template=self.template, rule={}, drive=drive.property, drive_shift=0
        )
        with patch(CHECK, return_value=forced(1)):
            standoff_press(self.participant, self.group, self.approach)
        self.assertEqual(self._shares(), 0)

    def test_press_missing_a_rules_drive_shares_nothing(self) -> None:
        drive = CreatureDriveFactory(creature_template=self.template, strength=DriveStrength.MINOR)
        RegardRuleFactory(
            creature_template=self.template, rule={}, drive=drive.property, drive_shift=1
        )
        with patch(CHECK, return_value=forced(1)):
            standoff_press(self.participant, self.group, self.approach)
        self.assertEqual(self._shares(), 0)

    def test_terms_shifted_by_a_rule_shares_it(self) -> None:
        RegardRuleFactory(creature_template=self.template, rule={}, difficulty_shift_bands=1)
        with patch(CHECK, return_value=forced(-1)):
            standoff_terms(self.participant, self.group, self.terms)
        self.assertEqual(self._shares(), 1)

    def test_a_refused_verb_shares_nothing(self) -> None:
        RegardRuleFactory(creature_template=self.template, rule={}, difficulty_shift_bands=1)
        standoff_fight(self.participant, self.encounter)
        standoff_press(self.participant, self.group, self.approach)
        self.assertEqual(self._shares(), 0)


class ResultMessageTests(VerbBase):
    """Messages name the outcome word, and a press names the new terms ease."""

    def setUp(self) -> None:
        super().setUp()
        self.approach = StandoffApproachFactory()
        self.terms = StandoffTermsFactory(effect=TermsEffect.PASS)

    def test_press_success_names_the_outcome_and_the_new_ease(self) -> None:
        with patch(CHECK, return_value=forced(1)):
            first = standoff_press(self.participant, self.group, self.approach)
            second = standoff_press(self.participant, self.group, self.approach)
        self.assertEqual(first.message, "Success. They soften. Terms are now 1 step easier.")
        self.assertEqual(second.message, "Success. They soften. Terms are now 2 steps easier.")

    def test_press_failure_and_botch_name_the_outcome(self) -> None:
        with patch(CHECK, return_value=forced(-1)):
            failed = standoff_press(self.participant, self.group, self.approach)
        with patch(CHECK, return_value=forced(-2)):
            botched = standoff_press(self.participant, self.group, self.approach)
        self.assertEqual(failed.message, "Failure. Your words do not move them.")
        self.assertEqual(botched.message, "Critical failure. It goes badly; they grow bolder.")

    def test_read_names_the_outcome(self) -> None:
        self.template.cause = CauseKind.PREDATION
        self.template.save(update_fields=["cause"])
        with patch(CHECK, return_value=forced(-1)):
            missed = standoff_read(self.participant, self.group)
        self.assertEqual(missed.message, "You study them. Failure. You learn nothing.")
        with patch(CHECK, return_value=forced(1)):
            result = standoff_read(self.participant, self.group)
        self.assertEqual(result.message, "You study them. Success.")

    def test_terms_name_the_outcome(self) -> None:
        with patch(CHECK, return_value=forced(-1)):
            refused = standoff_terms(self.participant, self.group, self.terms)
        self.assertEqual(refused.message, "Failure. They refuse your terms.")
        with patch(CHECK, return_value=forced(1)):
            accepted = standoff_terms(self.participant, self.group, self.terms)
        self.assertEqual(accepted.message, "Success. They accept.")


class TermsDescriptionMessageTests(VerbBase):
    def test_success_message_uses_the_terms_description_when_set(self) -> None:
        terms = StandoffTermsFactory(effect=TermsEffect.PASS, description="PLACEHOLDER they go")
        with patch(CHECK, return_value=forced(1)):
            result = standoff_terms(self.participant, self.group, terms)
        self.assertEqual(result.message, "Success. PLACEHOLDER they go")


class TermsTheaterTests(VerbBase):
    def setUp(self) -> None:
        super().setUp()
        self.terms = StandoffTermsFactory(effect=TermsEffect.PASS)

    def _assert_emitted(self, level: int) -> None:
        theater = "world.standoffs.services.verbs.maybe_emit_resolution_theater"
        faces = "world.standoffs.services.verbs.check_outcome_faces"
        with (
            patch(CHECK, return_value=forced(level)) as roll,
            patch(faces, return_value=(["face"], "picked")) as built,
            patch(theater) as emit,
        ):
            standoff_terms(self.participant, self.group, self.terms)
        built.assert_called_once_with(roll.return_value)
        emit.assert_called_once_with(
            character=self.participant.character_sheet.character,
            title=self.terms.name,
            consequences=["face"],
            selected="picked",
            force=True,
        )

    def test_the_terms_roll_emits_the_success_wheel(self) -> None:
        self._assert_emitted(1)

    def test_a_refused_terms_roll_emits_the_wheel_too(self) -> None:
        self._assert_emitted(-1)
