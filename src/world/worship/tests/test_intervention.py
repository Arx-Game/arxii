"""Divine intervention as one graded roll (#4349): what each result does and who pays.

The roll is forced to each tier with ``force_check_outcome``; the odds are the invocation
difficulty's own and are tested with the invocation check (``test_favor_invocation``).
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory, ConsequenceEffectFactory, ConsequenceFactory
from world.checks.test_helpers import force_check_outcome
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.traits.constants import CANONICAL_OUTCOME_LEVELS
from world.traits.factories import CheckOutcomeFactory
from world.vitals.factories import CharacterVitalsFactory
from world.worship.constants import (
    BelowZeroRule,
    FavorAwardKind,
    InterventionStatus,
    MiracleTrigger,
)
from world.worship.exceptions import PrayerForOwnCharacter, PrayerTargetUnavailable
from world.worship.factories import (
    DevotionConfigFactory,
    FavorOutcomeAwardFactory,
    WorshippedBeingFactory,
    make_chosen,
)
from world.worship.intervention_services import fire_divine_intervention, soften
from world.worship.models import DevotionStanding, Miracle, MiracleAppliedCondition
from world.worship.prayer_services import pray
from world.worship.services import (
    bump_devotion,
    get_divine_intervention_config,
    maybe_fire_divine_intervention,
)

_NO_BROADCAST = "world.worship.services._broadcast_miracle_narrative"


def _condition_on(sheet, name: str) -> bool:
    return ConditionInstance.objects.filter(
        target=sheet.character, condition__name=name, resolved_at__isnull=True
    ).exists()


class InterventionTestBase(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.praying = CharacterSheetFactory()
        cls.fallen = CharacterSheetFactory()
        cls.being = WorshippedBeingFactory(resonance_pool=500)
        cls.check_type = CheckTypeFactory(name="Invocation")
        cls.config = DevotionConfigFactory(invocation_check_type=cls.check_type)
        cls.outcomes = {
            name: CheckOutcomeFactory(name=name, success_level=level)
            for name, level in CANONICAL_OUTCOME_LEVELS.items()
        }
        costs = (
            (FavorAwardKind.INTERVENTION_SPEND, "Success", 20),
            (FavorAwardKind.INTERVENTION_SPEND, "Critical Success", 10),
            (FavorAwardKind.INTERVENTION_DEBT, "Success", 10),
            (FavorAwardKind.INTERVENTION_DEBT, "Partial Success", 15),
            (FavorAwardKind.INTERVENTION_WAIT_HOURS, "Success", 72),
            (FavorAwardKind.INTERVENTION_WAIT_HOURS, "Partial Success", 48),
            (FavorAwardKind.INTERVENTION_WAIT_HOURS, "Critical Failure", 168),
        )
        for kind, tier, amount in costs:
            FavorOutcomeAwardFactory(
                config=cls.config, kind=kind, outcome_tier=cls.outcomes[tier], amount=amount
            )
        cls.cooldown = ConditionTemplateFactory(name="Divine Intervention Cooldown")
        cls.brand = ConditionTemplateFactory(name="Brand of Silence")
        cls.respite = ConditionTemplateFactory(name="Respite")
        cls.mending = ConditionTemplateFactory(name="Mending")
        cls.pool = ConsequencePoolFactory(name="The Answers")
        for tier, label, condition in (
            ("Critical Failure", "The god turns away", cls.brand),
            ("Partial Success", "A breath of respite", cls.respite),
        ):
            row = ConsequenceFactory(
                outcome_tier=cls.outcomes[tier], label=label, mechanical_description=f"[{label}]"
            )
            ConsequenceEffectFactory(consequence=row, condition_template=condition, target="self")
            ConsequencePoolEntryFactory(pool=cls.pool, consequence=row)
        cls.being.intervention_pool = cls.pool
        cls.being.save(update_fields=["intervention_pool"])
        cls.rescue = Miracle.objects.create(
            name="A Hand Closes the Wound",
            being=cls.being,
            resonance_pool_cost=100,
            intervention_trigger=MiracleTrigger.NEAR_DEATH,
            favor_threshold=0,
            narrative_text="[PLACEHOLDER] A hand closes the wound.",
        )
        MiracleAppliedCondition.objects.create(
            miracle=cls.rescue, condition=cls.mending, base_severity=1, base_duration_rounds=5
        )
        cls.standing = DevotionStanding.objects.create(
            character_sheet=cls.praying, being=cls.being, favor=75
        )

    def _fire(self, outcome_name: str, **kwargs):
        kwargs.setdefault("being", self.being)
        kwargs.setdefault("target", self.fallen)
        with force_check_outcome(self.outcomes[outcome_name]), patch(_NO_BROADCAST):
            return fire_divine_intervention(
                self.praying,
                trigger=MiracleTrigger.NEAR_DEATH,
                trigger_event="prayer_near_death",
                **kwargs,
            )

    def _standing(self) -> DevotionStanding:
        return DevotionStanding.objects.get(character_sheet=self.praying, being=self.being)


class WhatEachResultDoesTests(InterventionTestBase):
    def test_a_backfire_lands_on_the_one_praying_not_the_one_in_danger(self) -> None:
        result = self._fire("Critical Failure")

        self.assertEqual(result.drawn.label, "The god turns away")
        self.assertTrue(_condition_on(self.praying, "Brand of Silence"))
        self.assertFalse(_condition_on(self.fallen, "Brand of Silence"))
        # A botch costs a long wait and no favor (no spend or debt row for it).
        self.assertEqual(result.cost.wait_hours, soften(168, 50))
        self.assertEqual(self._standing().favor, 75)

    def test_a_lesser_answer_lands_on_the_one_in_danger_and_leaves_favor_owed(self) -> None:
        result = self._fire("Partial Success")

        self.assertEqual(result.drawn.label, "A breath of respite")
        self.assertTrue(_condition_on(self.fallen, "Respite"))
        self.assertFalse(_condition_on(self.praying, "Respite"))
        # The 15 owed is cut by the high favor band (50 percent) and rounded up.
        self.assertEqual(result.cost.favor_owed, 8)
        self.assertEqual((self._standing().favor, self._standing().owed_favor), (75, 8))

    def _room_text(self, outcome_name: str) -> str:
        with patch("world.worship.intervention_services.route_intervention_text") as route:
            self._fire(outcome_name)
        return route.call_args.args[1]

    def test_the_room_reads_a_lesser_answers_text_and_the_condition_it_put_on(self) -> None:
        text = self._room_text("Partial Success")

        self.assertTrue(text.startswith("[A breath of respite]"), text)
        self.assertIn("Respite", text)
        # Never the roll, the difficulty or anyone's favor.
        self.assertNotIn("Difficulty", text)
        self.assertNotIn("favor", text.lower())

    def test_the_room_reads_a_backfires_text_and_the_condition_it_put_on(self) -> None:
        text = self._room_text("Critical Failure")

        self.assertTrue(text.startswith("[The god turns away]"), text)
        self.assertIn("Brand of Silence", text)
        self.assertNotIn("Difficulty", text)

    def test_a_failure_is_unanswered_and_costs_only_the_wait(self) -> None:
        result = self._fire("Failure")

        self.assertFalse(result.answered)
        self.assertEqual(result.effects, ())
        self.assertEqual((self._standing().favor, self._standing().owed_favor), (75, 0))
        self.assertTrue(_condition_on(self.praying, "Divine Intervention Cooldown"))

    def test_a_rescue_for_another_lands_on_them_and_costs_the_one_praying(self) -> None:
        result = self._fire("Success")

        self.assertEqual(result.performance.target_character, self.fallen)
        self.assertTrue(_condition_on(self.fallen, "Mending"))
        self.assertFalse(_condition_on(self.praying, "Mending"))
        self.assertEqual((self._standing().favor, self._standing().owed_favor), (55, 5))
        self.assertFalse(
            DevotionStanding.objects.filter(character_sheet=self.fallen, being=self.being).exists()
        )

    def test_a_critical_success_brings_the_bigger_miracle_else_the_rescue(self) -> None:
        bigger = Miracle.objects.create(
            name="The Sky Opens",
            being=self.being,
            resonance_pool_cost=100,
            intervention_trigger=MiracleTrigger.NEAR_DEATH,
            favor_threshold=0,
            min_outcome_tier=self.outcomes["Critical Success"],
            sort_order=5,
            narrative_text="[PLACEHOLDER] The sky opens.",
        )

        first = self._fire("Critical Success")
        # Only a critical success can bring it: a Success keeps to the ordinary rescue.
        ConditionInstance.objects.filter(condition=self.cooldown).delete()
        second = self._fire("Success")

        self.assertEqual(first.performance.miracle, bigger)
        self.assertEqual(first.cost.favor_spent, 10)
        self.assertEqual(second.performance.miracle, self.rescue)

    def test_an_unaffordable_miracle_falls_back_to_a_lesser_answer_costed_by_the_roll(self) -> None:
        self.being.resonance_pool = 10
        self.being.save(update_fields=["resonance_pool"])

        result = self._fire("Success")

        self.assertIsNone(result.performance)
        self.assertEqual(result.drawn.label, "A breath of respite")
        # No favor is spent (spend is for a miracle); the debt and wait are the rolled
        # Success tier's rows: the 10 owed softened by 50 percent.
        self.assertEqual((result.cost.favor_spent, result.cost.favor_owed), (0, 5))
        self.assertEqual(result.cost.wait_hours, soften(72, 50))


class NoRollAwardFallbackTests(InterventionTestBase):
    def test_the_partial_success_tier_is_found_by_name_beside_another_level_zero_tier(self) -> None:
        from world.worship.invocation_services import outcome_award, partial_success_outcome

        # A game may author its own tier at level 0; the lookup must not take it for Partial.
        CheckOutcomeFactory(name="AAA Detonation", success_level=0)
        FavorOutcomeAwardFactory(
            config=self.config,
            kind=FavorAwardKind.OFFICIANT,
            outcome_tier=self.outcomes["Partial Success"],
            amount=6,
        )

        self.assertEqual(partial_success_outcome(), self.outcomes["Partial Success"])
        self.assertEqual(outcome_award(FavorAwardKind.OFFICIANT, partial_success_outcome()), 6)


class MissingCostRowsTests(InterventionTestBase):
    def test_with_no_cost_rows_a_rescue_is_free_and_waits_the_default(self) -> None:
        # The behaviour a missing row means (the Required content page lists it): the rescue
        # costs no favor, leaves nothing owed, and waits the config's cooldown hours.
        self.config.outcome_awards.all().delete()

        result = self._fire("Success")

        self.assertIsNotNone(result.performance)
        cooldown_hours = get_divine_intervention_config().cooldown_hours
        self.assertEqual(
            (result.cost.favor_spent, result.cost.favor_owed, result.cost.wait_hours),
            (0, 0, cooldown_hours),
        )
        self.assertEqual((self._standing().favor, self._standing().owed_favor), (75, 0))


class LiveAnswerFloorTests(InterventionTestBase):
    def test_a_live_answer_still_needs_the_prayer_gate_of_favor(self) -> None:
        from world.worship.services import miracle_ineligibility

        # The being's miracle has its own threshold of 0, so only the gate (20) stops a
        # steward sending it to a character with little favor; owed favor does not.
        self.standing.favor = 10
        self.standing.save(update_fields=["favor"])
        refusal = miracle_ineligibility(self.praying, self.rescue)
        self.assertIn("below this miracle's threshold (20)", refusal)

        self.standing.favor = 20
        self.standing.owed_favor = 9
        self.standing.save(update_fields=["favor", "owed_favor"])
        self.assertEqual(miracle_ineligibility(self.praying, self.rescue), "")


class WhenTheBeingWillNotRollTests(InterventionTestBase):
    def test_favor_below_zero_fails_without_a_roll_by_default(self) -> None:
        self.standing.favor = -5
        self.standing.save(update_fields=["favor"])

        result = self._fire("Success")

        self.assertEqual(result.status, InterventionStatus.BELOW_ZERO)
        self.assertFalse(result.rolled)

    def test_favor_below_zero_can_be_a_much_harder_roll_instead(self) -> None:
        config = get_divine_intervention_config()
        config.below_zero_rule = BelowZeroRule.MUCH_HARDER
        config.save(update_fields=["below_zero_rule"])
        self.standing.favor = -5
        self.standing.save(update_fields=["favor"])

        with force_check_outcome(self.outcomes["Failure"]) as capture, patch(_NO_BROADCAST):
            result = fire_divine_intervention(
                self.praying,
                trigger=MiracleTrigger.NEAR_DEATH,
                trigger_event="prayer_near_death",
                being=self.being,
                target=self.fallen,
            )

        self.assertTrue(result.rolled)
        self.assertEqual(capture.target_difficulty, 90)

    def test_without_a_check_type_nothing_happens(self) -> None:
        self.config.invocation_check_type = None
        self.config.save(update_fields=["invocation_check_type"])

        result = self._fire("Success")

        self.assertEqual(result.status, InterventionStatus.NO_CHECK_TYPE)


class OwedFavorTests(InterventionTestBase):
    def test_earned_favor_pays_the_debt_first_at_base_then_scales_the_rest(self) -> None:
        make_chosen(self.praying, self.being)
        standing = self._standing()
        standing.owed_favor = 6
        standing.favor = 10
        standing.save(update_fields=["owed_favor", "favor"])

        bump = bump_devotion(self.praying, self.being, 10)

        # 6 of the 10 base pays the debt; the other 4 earns at the Chosen's 200 percent.
        self.assertEqual(bump.owed_paid, 6)
        self.assertEqual(bump.credited, 8)
        standing = self._standing()
        self.assertEqual((standing.owed_favor, standing.favor), (0, 18))


class IntercessionTests(InterventionTestBase):
    def test_the_being_steps_in_for_a_fallen_character_at_very_high_favor(self) -> None:
        # The fallen character is the one rolling: 90 favor is past the intercession threshold.
        DevotionStanding.objects.create(character_sheet=self.fallen, being=self.being, favor=90)
        Miracle.objects.create(
            name="Raised From the Dust",
            being=self.being,
            resonance_pool_cost=100,
            intervention_trigger=MiracleTrigger.INCAPACITATED,
            favor_threshold=0,
            narrative_text="[PLACEHOLDER] Raised from the dust.",
        )

        with force_check_outcome(self.outcomes["Success"]), patch(_NO_BROADCAST):
            maybe_fire_divine_intervention(self.fallen.character)

        standing = DevotionStanding.objects.get(character_sheet=self.fallen, being=self.being)
        self.assertEqual(standing.favor, 70)
        self.assertEqual(self.being.miracle_performances.get().target_character, self.fallen)

    def test_the_incapacitation_event_reaches_the_handler_through_its_flow(self) -> None:
        """The flow step hands the handler only the event's payload; the character is read
        from it (a live fight found the handler raising for want of a ``character`` argument)."""
        from django.test import override_settings

        from flows.constants import EventName
        from flows.emit import emit_event
        from flows.events.payloads import CharacterIncapacitatedPayload
        from world.worship.factories import wire_miracle_content
        from world.worship.services import install_divine_intervention_trigger

        with override_settings(SEED_SAMPLE_CONTENT=True):
            wire_miracle_content()
        DevotionStanding.objects.create(character_sheet=self.fallen, being=self.being, favor=90)
        install_divine_intervention_trigger(self.fallen, self.being)
        room = ObjectDBFactory(db_key="Chapel", db_typeclass_path="typeclasses.rooms.Room")
        self.fallen.character.db_location = room
        self.fallen.character.save(update_fields=["db_location"])
        Miracle.objects.create(
            name="Raised From the Dust",
            being=self.being,
            resonance_pool_cost=100,
            intervention_trigger=MiracleTrigger.INCAPACITATED,
            favor_threshold=0,
            narrative_text="[PLACEHOLDER] Raised from the dust.",
        )

        with force_check_outcome(self.outcomes["Success"]), patch(_NO_BROADCAST):
            emit_event(
                EventName.CHARACTER_INCAPACITATED,
                CharacterIncapacitatedPayload(character=self.fallen.character, source_event=None),
                location=room,
            )

        self.assertTrue(self.being.miracle_performances.exists())

    def test_below_the_threshold_nobody_steps_in(self) -> None:
        DevotionStanding.objects.create(character_sheet=self.fallen, being=self.being, favor=60)

        with force_check_outcome(self.outcomes["Success"]), patch(_NO_BROADCAST):
            maybe_fire_divine_intervention(self.fallen.character)

        self.assertFalse(self.being.miracle_performances.exists())


class PrayerForAnotherTests(InterventionTestBase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.room = ObjectDBFactory(db_key="Field", db_typeclass_path="typeclasses.rooms.Room")
        for sheet in (cls.praying, cls.fallen):
            sheet.character.db_location = cls.room
            sheet.character.save(update_fields=["db_location"])
        CharacterVitalsFactory(character_sheet=cls.praying, health=100, max_health=100)
        CharacterVitalsFactory(character_sheet=cls.fallen, health=5, max_health=100)

    def test_an_ally_prays_and_the_help_lands_on_the_fallen_character(self) -> None:
        with force_check_outcome(self.outcomes["Success"]), patch(_NO_BROADCAST):
            outcome = pray(self.praying, self.being, "Spare him.", on_behalf_of=self.fallen)

        self.assertEqual(outcome.dire_straits.kind, "near_death")
        self.assertEqual(outcome.intervention.performance.target_character, self.fallen)
        self.assertTrue(_condition_on(self.fallen, "Mending"))
        self.assertIn("answered your prayer for", " ".join(outcome.lines))

    def test_not_here_and_not_in_danger_are_one_refusal(self) -> None:
        healthy = CharacterSheetFactory()
        healthy.character.db_location = self.room
        healthy.character.save(update_fields=["db_location"])
        CharacterVitalsFactory(character_sheet=healthy, health=100, max_health=100)
        faraway = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=faraway, health=5, max_health=100)

        messages = set()
        for target in (healthy, faraway):
            with self.assertRaises(PrayerTargetUnavailable) as caught:
                pray(self.praying, self.being, "Spare them.", on_behalf_of=target)
            messages.add(caught.exception.user_message)

        self.assertEqual(len(messages), 1)

    def test_praying_for_another_of_your_own_characters_is_refused(self) -> None:
        player = PlayerDataFactory()
        for sheet in (self.praying, self.fallen):
            entry = RosterEntryFactory(character_sheet=sheet)
            RosterTenureFactory(roster_entry=entry, player_data=player, end_date=None)

        with self.assertRaises(PrayerForOwnCharacter):
            pray(self.praying, self.being, "Spare him.", on_behalf_of=self.fallen)

    def _notices_for(self, sheet) -> list[str]:
        from world.narrative.models import NarrativeMessageDelivery

        return [
            delivery.message.body
            for delivery in NarrativeMessageDelivery.objects.filter(
                recipient_character_sheet=sheet
            ).select_related("message")
        ]

    def test_the_fallen_character_is_told_who_prayed_and_what_landed_on_them(self) -> None:
        with (
            self.captureOnCommitCallbacks(execute=True),
            force_check_outcome(self.outcomes["Success"]),
            patch(_NO_BROADCAST),
        ):
            pray(self.praying, self.being, "Spare him.", on_behalf_of=self.fallen)

        told = self._notices_for(self.fallen)
        self.assertEqual(len(told), 2)
        self.assertIn("prayed to", told[0])
        self.assertIn("condition applied, Mending", " ".join(told))

    def test_a_failure_tells_the_fallen_character_nothing(self) -> None:
        with (
            self.captureOnCommitCallbacks(execute=True),
            force_check_outcome(self.outcomes["Failure"]),
            patch(_NO_BROADCAST),
        ):
            pray(self.praying, self.being, "Spare him.", on_behalf_of=self.fallen)

        self.assertEqual(self._notices_for(self.fallen), [])

    def test_with_no_scene_and_no_gm_the_text_still_reaches_the_room_and_the_one_it_touches(
        self,
    ) -> None:
        from unittest.mock import MagicMock

        from world.worship.services import route_intervention_text

        self.praying.character.msg = MagicMock()
        with self.captureOnCommitCallbacks(execute=True):
            route_intervention_text(self.fallen, "[A hand closes the wound.]", None)

        # The onlooker in the room hears it; the one it touched is sent it as a notice.
        self.assertTrue(self.praying.character.msg.called)
        self.assertIn("[A hand closes the wound.]", self._notices_for(self.fallen))

    def test_the_gm_prompt_names_who_prayed_and_the_tier(self) -> None:
        with (
            force_check_outcome(self.outcomes["Success"]),
            patch(_NO_BROADCAST),
            patch("world.gm.prompt_services.route_narratable_event", return_value=[]) as route,
        ):
            pray(self.praying, self.being, "Spare him.", on_behalf_of=self.fallen)

        event = route.call_args.args[0]
        self.assertIn("prayer for", event.context_text)
        self.assertIn("Success", event.context_text)
        self.assertEqual(event.character_sheet, self.fallen)


class DeliveryAndFailureTests(InterventionTestBase):
    """What each seat is told (#4349), and a failure staying out of incapacitation."""

    def test_a_result_the_being_had_nothing_to_answer_with_is_not_called_an_answer(self) -> None:
        from world.worship.intervention_services import intervention_lines

        self.being.resonance_pool = 10
        self.being.intervention_pool = None
        self.being.save(update_fields=["resonance_pool", "intervention_pool"])

        result = self._fire("Success")
        lines = intervention_lines(result)

        self.assertFalse(result.answered)
        self.assertIn("Nothing came of your call on", lines[0])
        self.assertNotIn("answered you", " ".join(lines))
        self.assertIn("will not answer again for", lines[0])

    def test_a_config_whose_intercession_threshold_is_below_the_gate_is_refused(self) -> None:
        from django.core.exceptions import ValidationError

        config = get_divine_intervention_config()
        config.prayer_favor_gate = 30
        config.favor_threshold = 20
        with self.assertRaises(ValidationError) as caught:
            config.full_clean()
        self.assertIn("favor_threshold", caught.exception.message_dict)

    def test_a_failure_inside_the_intervention_leaves_incapacitation_alone(self) -> None:
        with (
            patch(
                "world.worship.intervention_services.fire_divine_intervention",
                side_effect=ValueError("boom"),
            ),
            self.assertLogs("world.worship.services", level="ERROR") as logged,
        ):
            maybe_fire_divine_intervention(self.praying.character)

        self.assertIn("Divine intercession failed", logged.output[0])

    def test_a_prayed_for_name_may_have_spaces_in_either_part(self) -> None:
        from commands.worship import _split_prayed_for

        self.being.name = "Old Grey Shepherd"
        self.being.save(update_fields=["name"])

        self.assertEqual(
            _split_prayed_for("Wat Tyler Old Grey Shepherd"), ("Wat Tyler", "Old Grey Shepherd")
        )
        self.assertEqual(_split_prayed_for("Hobb Nowhere"), ("Hobb", "Nowhere"))
