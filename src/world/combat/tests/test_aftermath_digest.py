"""Tests for the encounter aftermath digest (#3551): builder, renderer, delivery."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from world.checks.factories import ConsequenceFactory
from world.checks.outcome_models import ConsequenceOutcome
from world.checks.types import CheckResult
from world.combat.aftermath import build_aftermath_digest, render_aftermath_digest
from world.combat.constants import EncounterOutcome, ParticipantStatus
from world.combat.factories import EncounterAftermathRuleFactory
from world.combat.narrator import get_or_create_narrator_persona
from world.combat.services import complete_encounter
from world.combat.tests.test_encounter_aftermath import _CompletionSeamTestBase
from world.combat.types import AftermathDigest
from world.conditions.constants import BLEED_OUT_CONDITION_NAME
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.missions.factories import MissionDeedRecordFactory
from world.scenes.constants import InteractionMode, InteractionVisibility
from world.scenes.models import Interaction
from world.scenes.place_models import InteractionReceiver
from world.societies.factories import LegendEntryFactory
from world.societies.models import LegendEntry
from world.stories.constants import BeatPredicateType, BeatVisibility
from world.stories.factories import BeatCompletionFactory, BeatFactory
from world.traits.factories import CheckOutcomeFactory


def _seed_rule_with_pool(
    outcome: str,
    risk_level: str,
    success_level: int = -1,
) -> tuple:
    """Seed an aftermath rule cell whose pool has one consequence at a tier.

    Mirrors ``CompleteEncounterTests._seed_rule_with_pool`` in
    ``test_encounter_aftermath.py`` (module-level copy per the task brief).
    """
    tier = CheckOutcomeFactory(
        name=f"AftermathDigestTier{outcome}{success_level}", success_level=success_level
    )
    consequence = ConsequenceFactory(outcome_tier=tier, character_loss=False)
    pool = ConsequencePoolFactory()
    ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
    rule = EncounterAftermathRuleFactory(
        outcome=outcome,
        risk_level=risk_level,
        consequence_pool=pool,
    )
    return rule, pool, consequence, tier


class BuildAftermathDigestTests(_CompletionSeamTestBase):
    """Tests for build_aftermath_digest's assembly rules (#3551)."""

    def test_digest_reports_aftermath_consequence(self) -> None:
        encounter = self._make_encounter()
        pc_one = self._add_pc(encounter)
        pc_two = self._add_pc(encounter)
        rule, _pool, consequence, tier = _seed_rule_with_pool(
            EncounterOutcome.DEFEAT, encounter.risk_level
        )

        forced = CheckResult(
            check_type=rule.check_type,
            outcome=tier,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )
        with patch(
            "world.checks.consequence_resolution.perform_check",
            return_value=forced,
        ):
            complete_encounter(encounter, outcome=EncounterOutcome.DEFEAT)

        digest_one = build_aftermath_digest(encounter, pc_one)
        digest_two = build_aftermath_digest(encounter, pc_two)

        outcome_one = ConsequenceOutcome.objects.get(character=pc_one.character_sheet)
        outcome_two = ConsequenceOutcome.objects.get(character=pc_two.character_sheet)

        self.assertEqual(digest_one.consequence, outcome_one)
        self.assertEqual(digest_one.consequence.selected_consequence, consequence)
        self.assertEqual(digest_two.consequence, outcome_two)
        self.assertNotEqual(digest_one.consequence.pk, digest_two.consequence.pk)

    def test_digest_lists_only_conditions_applied_during_the_fight(self) -> None:
        encounter = self._make_encounter()
        participant = self._add_pc(encounter)
        character = participant.character_sheet.character

        old_condition = ConditionInstanceFactory(target=character)
        ConditionInstance.objects.filter(pk=old_condition.pk).update(
            applied_at=encounter.created_at - timedelta(hours=1)
        )
        new_condition = ConditionInstanceFactory(target=character)

        complete_encounter(encounter, outcome=EncounterOutcome.VICTORY)

        digest = build_aftermath_digest(encounter, participant)
        self.assertEqual([c.pk for c in digest.conditions], [new_condition.pk])

    def test_digest_reports_legend_inside_window_only(self) -> None:
        encounter = self._make_encounter()
        participant = self._add_pc(encounter)
        sheet = participant.character_sheet

        complete_encounter(encounter, outcome=EncounterOutcome.VICTORY)
        encounter.refresh_from_db()

        in_window_entry = LegendEntryFactory(persona=sheet.primary_persona)
        out_of_window_entry = LegendEntryFactory(persona=sheet.primary_persona)
        LegendEntry.objects.filter(pk=out_of_window_entry.pk).update(
            created_at=encounter.completed_at + timedelta(minutes=2)
        )

        digest = build_aftermath_digest(encounter, participant)
        self.assertEqual([e.pk for e in digest.legend_entries], [in_window_entry.pk])

    def test_digest_reports_beat_completion_and_secret_visibility(self) -> None:
        encounter = self._make_encounter()
        participant = self._add_pc(encounter)
        sheet = participant.character_sheet

        beat = BeatFactory(
            predicate_type=BeatPredicateType.OUTCOME_TIER, visibility=BeatVisibility.SECRET
        )
        encounter.story_beat = beat
        encounter.save(update_fields=["story_beat"])

        complete_encounter(encounter, outcome=EncounterOutcome.VICTORY)
        encounter.refresh_from_db()

        completion = BeatCompletionFactory(
            beat=beat, character_sheet=sheet, outcome_tier=CheckOutcomeFactory()
        )

        digest = build_aftermath_digest(encounter, participant)
        self.assertEqual(digest.beat_completion, completion)
        self.assertFalse(digest.beat_visible_to_player)

        hidden_text = render_aftermath_digest(digest, include_secret_beat=False)
        self.assertNotIn("Story:", hidden_text)
        visible_text = render_aftermath_digest(digest, include_secret_beat=True)
        self.assertIn("Story:", visible_text)

        # A HINTED beat's completion is visible to the player.
        hinted_encounter = self._make_encounter()
        hinted_participant = self._add_pc(hinted_encounter)
        hinted_beat = BeatFactory(
            predicate_type=BeatPredicateType.OUTCOME_TIER, visibility=BeatVisibility.HINTED
        )
        hinted_encounter.story_beat = hinted_beat
        hinted_encounter.save(update_fields=["story_beat"])
        complete_encounter(hinted_encounter, outcome=EncounterOutcome.VICTORY)
        hinted_encounter.refresh_from_db()
        BeatCompletionFactory(
            beat=hinted_beat,
            character_sheet=hinted_participant.character_sheet,
            outcome_tier=CheckOutcomeFactory(),
        )
        hinted_digest = build_aftermath_digest(hinted_encounter, hinted_participant)
        self.assertTrue(hinted_digest.beat_visible_to_player)

    def test_digest_skips_beat_for_scenario_encounters(self) -> None:
        deed = MissionDeedRecordFactory()
        encounter = self._make_encounter(scenario_deed=deed)
        participant = self._add_pc(encounter)

        complete_encounter(encounter, outcome=EncounterOutcome.VICTORY)

        digest = build_aftermath_digest(encounter, participant)
        self.assertIsNone(digest.beat_completion)

    def test_digest_peril_flag(self) -> None:
        encounter = self._make_encounter()
        participant = self._add_pc(encounter)
        character = participant.character_sheet.character

        bleed_out = ConditionTemplateFactory(name=BLEED_OUT_CONDITION_NAME)
        ConditionInstanceFactory(target=character, condition=bleed_out)

        complete_encounter(encounter, outcome=EncounterOutcome.DEFEAT)

        digest = build_aftermath_digest(encounter, participant)
        self.assertTrue(digest.peril_round_active)
        text = render_aftermath_digest(digest, include_secret_beat=False)
        self.assertIn("Your peril is not over", text)


class DeliverAftermathDigestsTests(_CompletionSeamTestBase):
    """Tests for complete_encounter's delivery of the aftermath digest (#3551)."""

    def test_complete_encounter_delivers_private_digest_per_participant(self) -> None:
        encounter = self._make_encounter()
        active_one = self._add_pc(encounter)
        active_two = self._add_pc(encounter)
        fled = self._add_pc(encounter, status=ParticipantStatus.FLED)
        removed = self._add_pc(encounter, status=ParticipantStatus.REMOVED)

        for participant in (active_one, active_two, fled, removed):
            participant.character_sheet.character.msg = MagicMock()

        complete_encounter(encounter, outcome=EncounterOutcome.VICTORY)

        narrator = get_or_create_narrator_persona()
        private_interactions = Interaction.objects.filter(
            scene=encounter.scene,
            mode=InteractionMode.OUTCOME,
            visibility=InteractionVisibility.PERCEIVED_ONLY,
            persona=narrator,
        )
        self.assertEqual(private_interactions.count(), 3)
        for interaction in private_interactions:
            self.assertTrue(interaction.content.startswith("Aftermath: Victory"))
            self.assertEqual(InteractionReceiver.objects.filter(interaction=interaction).count(), 1)

        expected_persona_ids = {
            active_one.character_sheet.primary_persona.pk,
            active_two.character_sheet.primary_persona.pk,
            fled.character_sheet.primary_persona.pk,
        }
        actual_persona_ids = {
            InteractionReceiver.objects.get(interaction=interaction).persona_id
            for interaction in private_interactions
        }
        self.assertEqual(actual_persona_ids, expected_persona_ids)

        # Each ACTIVE/FLED character gets two msg calls: the WebSocket interaction
        # push (_send_to_objects) and the plain-text telnet line. Both carry the
        # same digest text, so the plain-text call is the same across all three.
        texts = set()
        for participant in (active_one, active_two, fled):
            character = participant.character_sheet.character
            self.assertEqual(character.msg.call_count, 2)
            plain_calls = [c for c in character.msg.call_args_list if c.args]
            self.assertEqual(len(plain_calls), 1)
            texts.add(plain_calls[0].args[0])
        self.assertEqual(len(texts), 1)
        self.assertTrue(next(iter(texts)).startswith("Aftermath: Victory"))

        removed.character_sheet.character.msg.assert_not_called()

        self.assertEqual(
            Interaction.objects.filter(scene=encounter.scene, mode=InteractionMode.OUTCOME).count(),
            4,
        )

    def test_abandoned_still_delivers_digest(self) -> None:
        encounter = self._make_encounter()
        self._add_pc(encounter)

        complete_encounter(encounter, outcome=EncounterOutcome.ABANDONED)

        narrator = get_or_create_narrator_persona()
        interaction = Interaction.objects.get(
            scene=encounter.scene,
            mode=InteractionMode.OUTCOME,
            visibility=InteractionVisibility.PERCEIVED_ONLY,
            persona=narrator,
        )
        self.assertIn("Aftermath: Abandoned.", interaction.content)
        self.assertNotIn("Consequence:", interaction.content)


class RenderAftermathDigestTests(TestCase):
    """Tests for render_aftermath_digest's section omission (#3551)."""

    def test_render_omits_empty_sections(self) -> None:
        digest = AftermathDigest(
            outcome=EncounterOutcome.VICTORY,
            consequence=None,
            conditions=[],
            legend_entries=[],
            beat_completion=None,
            beat_visible_to_player=False,
            peril_round_active=False,
        )
        text = render_aftermath_digest(digest, include_secret_beat=False)
        self.assertEqual(text, "Aftermath: Victory.")
        self.assertEqual(len(text.splitlines()), 1)
