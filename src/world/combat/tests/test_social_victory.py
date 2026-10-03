"""A field won over without violence is an ordinary VICTORY (#4091, Decisions 7 and 10)."""

from datetime import timedelta
from unittest import mock
from unittest.mock import MagicMock

from django.test import TestCase
from evennia.objects.objects import ObjectSessionHandler

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.checks.outcome_models import ConsequenceOutcome
from world.checks.types import CheckResult
from world.combat.achievement_counters import (
    STAT_KEY_OPPONENTS_WON_OVER,
    _get_or_create_stat_def,
)
from world.combat.constants import EncounterOutcome, OpponentStatus, OpponentTier
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    EncounterAftermathRuleFactory,
)
from world.combat.models import CombatEncounter, CombatOpponent
from world.combat.services import (
    _check_encounter_completion,
    _classify_encounter_outcome,
    complete_encounter,
)
from world.combat.won_over import stamp_won_over_opponents, won_over_labels
from world.conditions.constants import Allegiance
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.scenes.constants import InteractionMode, InteractionVisibility
from world.scenes.models import Interaction
from world.traits.factories import CheckOutcomeFactory


def _outcome_interaction(encounter: CombatEncounter) -> Interaction:
    return Interaction.objects.get(
        scene=encounter.scene,
        mode=InteractionMode.OUTCOME,
        visibility=InteractionVisibility.DEFAULT,
    )


def _patch_sessions(sessions_by_pk: dict) -> object:
    """Patch ``ObjectSessionHandler.all`` per-character (mirrors
    world/scenes/tests/test_outcome_delivery.py's helper of the same name)."""

    def _fake_all(handler: ObjectSessionHandler) -> list[object]:
        return sessions_by_pk.get(handler.obj.pk, [])

    return mock.patch.object(ObjectSessionHandler, "all", _fake_all)


class SocialVictoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        check = CheckTypeFactory(name="Victory break")
        cls.charm = ConditionTemplateFactory(
            name="Victory charm",
            sets_allegiance=Allegiance.ALLY_OF_CASTER,
            allegiance_break_check_type=check,
        )
        cls.calm = ConditionTemplateFactory(
            name="Victory calm",
            sets_allegiance=Allegiance.NEUTRAL,
            allegiance_break_check_type=check,
        )
        cls.turn = ConditionTemplateFactory(
            name="Victory turn",
            sets_allegiance=Allegiance.TURNED,
            allegiance_break_check_type=check,
        )

    def setUp(self):
        self.enc = CombatEncounterFactory()
        self.pc = CombatParticipantFactory(encounter=self.enc)
        self.source = self.pc.character_sheet.character

    def _win_over(self, opp, template):
        ConditionInstanceFactory(
            target=opp.objectdb, condition=template, source_character=self.source
        )

    def test_charm_and_calm_end_in_victory(self):  # Success signal 1
        a = CombatOpponentFactory(encounter=self.enc, aftermath_pool=ConsequencePoolFactory())
        b = CombatOpponentFactory(encounter=self.enc, aftermath_pool=ConsequencePoolFactory())
        self._win_over(a, self.charm)
        self._win_over(b, self.calm)
        self.assertTrue(_check_encounter_completion(self.enc))
        self.assertEqual(_classify_encounter_outcome(self.enc), EncounterOutcome.VICTORY)
        complete_encounter(self.enc, outcome=EncounterOutcome.VICTORY)
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual({a.status, b.status}, {OpponentStatus.WON_OVER})

    def test_turned_only_remainder_ends_fight(self):
        a = CombatOpponentFactory(encounter=self.enc)
        self._win_over(a, self.turn)
        self.assertTrue(_check_encounter_completion(self.enc))

    def test_fled_hero_killer_still_blocks_victory(self):  # Review Focus 4
        a = CombatOpponentFactory(encounter=self.enc)
        CombatOpponentFactory(
            encounter=self.enc, tier=OpponentTier.HERO_KILLER, status=OpponentStatus.FLED
        )
        self._win_over(a, self.charm)
        self.assertNotEqual(_classify_encounter_outcome(self.enc), EncounterOutcome.VICTORY)

    def test_won_over_hero_killer_is_a_victory(self):  # fix round 2
        """A Hero Killer won over counts as won over: social victory ends the fight too."""
        a = CombatOpponentFactory(encounter=self.enc)
        hero_killer = CombatOpponentFactory(encounter=self.enc, tier=OpponentTier.HERO_KILLER)
        self._win_over(a, self.charm)
        self._win_over(hero_killer, self.calm)
        self.assertEqual(_classify_encounter_outcome(self.enc), EncounterOutcome.VICTORY)

    def test_charm_from_before_the_fight_does_not_win_it(self):  # Review Focus 1
        a = CombatOpponentFactory(encounter=self.enc)
        instance = ConditionInstanceFactory(
            target=a.objectdb, condition=self.charm, source_character=self.source
        )
        # .update_with_reason bypasses auto_now_add; then mirror it on the
        # identity-mapped instance.
        earlier = self.enc.created_at - timedelta(minutes=5)
        type(instance).objects.filter(pk=instance.pk).update_with_reason(
            reason="test: backdate applied_at to before the encounter started",
            applied_at=earlier,
        )
        instance.applied_at = earlier
        self.assertFalse(_check_encounter_completion(self.enc))

    def test_won_over_aftermath_pools_fire(self):
        pool_a = ConsequencePoolFactory()
        pool_b = ConsequencePoolFactory()
        a = CombatOpponentFactory(encounter=self.enc, aftermath_pool=pool_a)
        b = CombatOpponentFactory(encounter=self.enc, aftermath_pool=pool_b)
        self._win_over(a, self.charm)
        self._win_over(b, self.calm)

        with mock.patch(
            "world.checks.consequence_resolution.apply_pool_deterministically",
            return_value=[],
        ) as mock_apply:
            complete_encounter(self.enc, outcome=EncounterOutcome.VICTORY)

        self.assertEqual(mock_apply.call_count, 2)
        called_pools = {call.kwargs["pool"] for call in mock_apply.call_args_list}
        self.assertEqual(called_pools, {pool_a, pool_b})

    def test_aftermath_rule_runs_for_social_victory_like_a_fought_win(self):
        tier = CheckOutcomeFactory(name="WonOverAftermathTier", success_level=-1)
        consequence = ConsequenceFactory(outcome_tier=tier, character_loss=False)
        pool = ConsequencePoolFactory()
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
        rule = EncounterAftermathRuleFactory(
            outcome=EncounterOutcome.VICTORY,
            risk_level=self.enc.risk_level,
            consequence_pool=pool,
        )
        a = CombatOpponentFactory(encounter=self.enc)
        self._win_over(a, self.charm)

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
        with mock.patch(
            "world.checks.consequence_resolution.perform_check",
            return_value=forced,
        ):
            complete_encounter(self.enc, outcome=EncounterOutcome.VICTORY)

        self.assertTrue(
            ConsequenceOutcome.objects.filter(character=self.pc.character_sheet).exists()
        )

    def test_outcome_content_names_won_over_opponents(self):
        a = CombatOpponentFactory(encounter=self.enc, name="Bandit")
        b = CombatOpponentFactory(encounter=self.enc, name="Thug")
        self._win_over(a, self.charm)
        self._win_over(b, self.calm)

        complete_encounter(self.enc, outcome=EncounterOutcome.VICTORY)

        content = _outcome_interaction(self.enc).content
        self.assertIn("charmed", content)
        self.assertIn("calmed", content)
        self.assertIn("Bandit", content)
        self.assertIn("Thug", content)

    def test_opponents_won_over_counter_increments(self):
        a = CombatOpponentFactory(encounter=self.enc)
        b = CombatOpponentFactory(encounter=self.enc)
        self._win_over(a, self.charm)
        self._win_over(b, self.calm)

        complete_encounter(self.enc, outcome=EncounterOutcome.VICTORY)

        stat_def = _get_or_create_stat_def(STAT_KEY_OPPONENTS_WON_OVER)
        self.assertEqual(self.pc.character_sheet.stats.get(stat_def), 2)

    def test_stamping_updates_the_held_instance_with_no_refresh(self):  # fix round 1
        a = CombatOpponentFactory(encounter=self.enc)
        self._win_over(a, self.charm)

        # Held BEFORE completion, never refreshed afterward. stamp_won_over_opponents
        # must mutate this exact identity-mapped instance (not just the DB row) —
        # a bulk .update() would leave it stale (#4091 fix round 1).
        held = CombatOpponent.objects.get(pk=a.pk)
        self.assertIs(held, a)

        complete_encounter(self.enc, outcome=EncounterOutcome.VICTORY)

        self.assertEqual(a.status, OpponentStatus.WON_OVER)

    def test_won_over_source_label_is_the_pc_persona_name(self):  # fix round 2
        # Stamps directly rather than through complete_encounter: cleanup
        # deletes the ephemeral opponent's ObjectDB (and cascades its
        # ConditionInstance) right after the OUTCOME line is built, so this
        # isolates the label logic from that teardown.
        persona = self.pc.character_sheet.primary_persona
        persona.name = "The Hidden Hand"
        persona.save(update_fields=["name"])

        a = CombatOpponentFactory(encounter=self.enc)
        self._win_over(a, self.charm)

        stamp_won_over_opponents(self.enc)

        [(_name, _verb, source_label)] = won_over_labels(self.enc)
        # The persona this PC is CURRENTLY presenting as -- never a raw
        # ObjectDB.key, and never str(CombatParticipant)'s "Sheet for {key}".
        self.assertEqual(source_label, "The Hidden Hand")

    def test_won_over_source_label_r1_prefers_the_in_fight_hold(self):  # fix round 2, R1 in labels
        """A pre-fight TURNED must not out-rank an in-fight Calm for the LABEL either.

        TURNED out-ranks NEUTRAL in ALLEGIANCE_PRECEDENCE, so without the
        applied_since filter the stale pre-fight TURNED would still designate
        the label as "turned" even though what actually happened THIS fight
        was a calm.
        """
        a = CombatOpponentFactory(encounter=self.enc)
        stale = ConditionInstanceFactory(
            target=a.objectdb, condition=self.turn, source_character=self.source
        )
        earlier = self.enc.created_at - timedelta(minutes=5)
        type(stale).objects.filter(pk=stale.pk).update_with_reason(
            reason="test: backdate applied_at to before the encounter started",
            applied_at=earlier,
        )
        self._win_over(a, self.calm)

        stamp_won_over_opponents(self.enc)

        [(_name, verb, _src)] = won_over_labels(self.enc)
        self.assertEqual(verb, "calmed")

    def test_victory_line_reaches_a_telnet_only_session(self):  # fix round 2, telnet parity
        """The OUTCOME line (won-over clause included) must reach a bare telnet
        session as plain text, not only the WebSocket ``interaction=`` payload.
        """
        from evennia.objects.models import ObjectDB

        room = ObjectDB.objects.get(pk=self.enc.room_id)
        character = self.pc.character_sheet.character
        character.location = room
        character.save()

        a = CombatOpponentFactory(encounter=self.enc)
        b = CombatOpponentFactory(encounter=self.enc)
        self._win_over(a, self.charm)
        self._win_over(b, self.calm)

        telnet_session = MagicMock()
        telnet_session.protocol_key = "telnet"
        character.msg = MagicMock()

        with (
            _patch_sessions({character.pk: [telnet_session]}),
            self.captureOnCommitCallbacks(execute=True),
        ):
            complete_encounter(self.enc, outcome=EncounterOutcome.VICTORY)

        # Plain-text calls are the ones with no "interaction" kwarg (#3807's
        # telnet-parity line); the structured WebSocket payload is a separate call.
        text_calls = [
            call
            for call in character.msg.call_args_list
            if call.args and "interaction" not in call.kwargs
        ]
        self.assertTrue(text_calls, character.msg.call_args_list)
        text = " ".join(str(call.args[0]) for call in text_calls)
        self.assertIn("charmed", text)
        self.assertIn("calmed", text)
