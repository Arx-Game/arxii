"""Integration tests for the #520 acute-tier under #1466's unified model.

Danger is now an ordinary STRICT scene round: a peril ensures the round, and the peril
ticks at *round resolution* (presence-gated ``maybe_resolve_scene_round``), which fires
the shared end-tick. AFK-safety is inherited from presence-gating — no declaration, no
resolution, no tick. Combat precedence is unchanged (combat drives its own tick).
"""

from django.test import TestCase

from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.constants import BLEED_OUT_CONDITION_NAME, DurationType
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.scenes.constants import RoundStatus, SceneRoundMode, SceneRoundStartReason
from world.scenes.models import SceneActionDeclaration, SceneRound, SceneRoundParticipant
from world.scenes.round_services import (
    ensure_round_for_acute_condition,
    maybe_resolve_scene_round,
)


def _make_room():
    return ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")


def _char_in_room(room):
    sheet = CharacterSheetFactory()
    sheet.character.db_location = room
    sheet.character.save(update_fields=["db_location"])
    return sheet


def _declare_pass(rnd, sheet):
    participant = SceneRoundParticipant.objects.get(scene_round=rnd, character_sheet=sheet)
    return SceneActionDeclaration.objects.create(
        scene_round=rnd,
        round_number=rnd.round_number,
        participant=participant,
        is_pass=True,
        is_immediate=False,
    )


class BleedOutDangerRoundTickTest(TestCase):
    """Test 1: bleed-out outside combat -> STRICT danger round; resolution ticks the peril."""

    def setUp(self):
        self.room = _make_room()

    def test_bleed_out_creates_strict_round_and_resolution_ticks_dot(self):
        """Danger round enrols bystander; presence-gated resolution ticks a DoT condition
        and the round persists while Bleeding-Out remains."""
        victim = _char_in_room(self.room)
        bystander = _char_in_room(self.room)  # enrolled by ensure_round_for_acute_condition

        rnd = ensure_round_for_acute_condition(victim)
        assert rnd is not None
        assert rnd.start_reason == SceneRoundStartReason.DANGER
        assert rnd.mode == SceneRoundMode.STRICT
        assert rnd.status == RoundStatus.DECLARING

        # A ROUNDS-duration DoT lets us prove the end-tick fired for participants.
        template = ConditionTemplateFactory(
            default_duration_type=DurationType.ROUNDS, default_duration_value=5
        )
        dot = ConditionInstanceFactory(
            target=victim.character, condition=template, rounds_remaining=5
        )
        # An UNTIL_CURED Bleeding-Out keeps the danger round alive (does not auto-end).
        bleed_template = ConditionTemplateFactory(
            name=BLEED_OUT_CONDITION_NAME,
            default_duration_type=DurationType.UNTIL_CURED,
        )
        ConditionInstanceFactory(target=victim.character, condition=bleed_template)

        # Both present conscious participants declare -> presence-complete -> resolve.
        _declare_pass(rnd, victim)
        _declare_pass(rnd, bystander)
        maybe_resolve_scene_round(rnd)

        dot.refresh_from_db()
        assert dot.rounds_remaining == 4  # end-tick fired for participants
        rnd.refresh_from_db()
        # Bleeding-Out persists -> the danger round advanced to the next round, not COMPLETED.
        assert rnd.status == RoundStatus.DECLARING


class AfkSafetyNoAutoTickTest(TestCase):
    """Test 2: AFK-safety — progression is presence-gated, not clock-driven."""

    def setUp(self):
        self.room = _make_room()

    def test_danger_round_does_not_tick_without_a_declaration(self):
        """A DoT on a lone victim is UNCHANGED until a present participant declares
        (driving resolution). Proves progression is presence-gated, not clock-driven."""
        victim = _char_in_room(self.room)

        rnd = ensure_round_for_acute_condition(victim)  # victim alone in room
        assert rnd is not None

        template = ConditionTemplateFactory(
            default_duration_type=DurationType.ROUNDS, default_duration_value=3
        )
        dot = ConditionInstanceFactory(
            target=victim.character, condition=template, rounds_remaining=3
        )

        # No declaration -> maybe_resolve is a no-op -> nothing ticks.
        maybe_resolve_scene_round(rnd)

        dot.refresh_from_db()
        assert dot.rounds_remaining == 3  # no tick without a declaration
        rnd.refresh_from_db()
        assert rnd.status == RoundStatus.DECLARING  # did not advance


class CombatPrecedenceNoDangerRoundTest(TestCase):
    """Test 3: a character in active combat does NOT get a danger round on bleed-out."""

    def setUp(self):
        self.room = _make_room()

    def test_in_combat_character_skips_danger_round(self):
        """_maybe_danger_round_on_bleed_out is a no-op for active combat participants."""
        from world.combat.constants import ParticipantStatus
        from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
        from world.vitals.services import _maybe_danger_round_on_bleed_out

        sheet = _char_in_room(self.room)
        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING)
        CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
            status=ParticipantStatus.ACTIVE,
        )

        _maybe_danger_round_on_bleed_out(sheet)

        # Combat drives the tick; no SceneRound should be created for this room.
        assert not SceneRound.objects.filter(room=self.room).exists()
