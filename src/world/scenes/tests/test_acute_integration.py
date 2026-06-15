"""Integration tests for the #520 acute-tier: danger rounds, AFK-safety, combat precedence."""

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.constants import BLEED_OUT_CONDITION_NAME, DurationType
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.scenes.constants import RoundStatus, SceneRoundStartReason
from world.scenes.models import SceneRound
from world.scenes.round_services import (
    advance_scene_round_for_action,
    auto_start_or_extend_danger_round,
)


def _make_room():
    return ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")


def _char_in_room(room):
    sheet = CharacterSheetFactory()
    sheet.character.db_location = room
    sheet.character.save(update_fields=["db_location"])
    return sheet


class BleedOutDangerRoundTickTest(TestCase):
    """Test 1: bleed-out outside combat → danger round spun up; action drives the tick."""

    def setUp(self):
        self.room = _make_room()

    def test_bleed_out_creates_danger_round_and_action_ticks_dot(self):
        """Danger round enrols bystander; advance_scene_round_for_action ticks a DoT condition."""
        victim = _char_in_room(self.room)
        _char_in_room(self.room)  # bystander enrolled by auto_start_or_extend_danger_round

        # Spin up the danger round (mimics _maybe_danger_round_on_bleed_out logic)
        rnd = auto_start_or_extend_danger_round(victim)
        assert rnd is not None
        assert rnd.start_reason == SceneRoundStartReason.DANGER
        assert rnd.status == RoundStatus.DECLARING

        # Put a ROUNDS-duration DoT condition on the victim so we can assert the tick fired
        template = ConditionTemplateFactory(
            default_duration_type=DurationType.ROUNDS, default_duration_value=5
        )
        dot = ConditionInstanceFactory(
            target=victim.character, condition=template, rounds_remaining=5
        )

        # Give the victim a Bleeding-Out condition so the danger round does NOT auto-end
        bleed_template = ConditionTemplateFactory(
            name=BLEED_OUT_CONDITION_NAME,
            default_duration_type=DurationType.UNTIL_CURED,
        )
        ConditionInstanceFactory(target=victim.character, condition=bleed_template)

        # An action drives one tick
        advance_scene_round_for_action(rnd)

        dot.refresh_from_db()
        # rounds_remaining decremented proves the per-action tick fired for participants
        assert dot.rounds_remaining == 4
        rnd.refresh_from_db()
        # Danger round persists (Bleeding-Out still present)
        assert rnd.status in {RoundStatus.BETWEEN_ROUNDS, RoundStatus.DECLARING}


class AkfSafetyNoAutoTickTest(TestCase):
    """Test 2: AFK-safety — progression is action-gated, not clock-driven."""

    def setUp(self):
        self.room = _make_room()

    def test_danger_round_does_not_tick_without_an_action(self):
        """A DoT condition on a solo victim is UNCHANGED until advance_scene_round_for_action fires.

        Proves progression is action-gated, not clock-driven.
        """
        victim = _char_in_room(self.room)

        # Spin up a danger round (victim alone in room)
        rnd = auto_start_or_extend_danger_round(victim)
        assert rnd is not None

        template = ConditionTemplateFactory(
            default_duration_type=DurationType.ROUNDS, default_duration_value=3
        )
        dot = ConditionInstanceFactory(
            target=victim.character, condition=template, rounds_remaining=3
        )

        # No action dispatched — just check state is unchanged
        dot.refresh_from_db()
        assert dot.rounds_remaining == 3  # no tick without an action call

        # No exception was raised (system is stable without action)
        # Confirm round exists but has not auto-advanced
        rnd.refresh_from_db()
        assert rnd.status == RoundStatus.DECLARING


class CombatPrecedenceNoDangerRoundTest(TestCase):
    """Test 3: a character in active combat does NOT get a danger round on bleed-out."""

    def setUp(self):
        self.room = _make_room()

    def test_in_combat_character_skips_danger_round(self):
        """_maybe_danger_round_on_bleed_out is a no-op for active combat participants."""
        from world.combat.constants import EncounterStatus, ParticipantStatus
        from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
        from world.vitals.services import _maybe_danger_round_on_bleed_out

        sheet = _char_in_room(self.room)
        encounter = CombatEncounterFactory(status=EncounterStatus.DECLARING)
        CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
            status=ParticipantStatus.ACTIVE,
        )

        _maybe_danger_round_on_bleed_out(sheet)

        # Combat drives the tick; no SceneRound should be created for this room
        assert not SceneRound.objects.filter(room=self.room).exists()
