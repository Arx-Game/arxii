from unittest import mock
from unittest.mock import MagicMock

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.constants import DurationType
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.scenes.constants import (
    InteractionMode,
    RoundStatus,
    SceneRoundMode,
    SceneRoundStartReason,
)
from world.scenes.factories import SceneRoundFactory, SceneRoundParticipantFactory
from world.scenes.models import Interaction, SceneActionDeclaration
from world.scenes.round_services import (
    advance_scene_round,
    end_scene_round,
    maybe_resolve_scene_round,
    resolve_scene_round,
    scene_round_is_complete,
    start_scene_round,
)


class SceneRoundServiceTests(TestCase):
    def test_start_sets_declaring_and_increments(self):
        rnd = SceneRoundFactory(status=RoundStatus.BETWEEN_ROUNDS, round_number=0)
        start_scene_round(rnd)
        rnd.refresh_from_db()
        assert rnd.status == RoundStatus.DECLARING
        assert rnd.round_number == 1

    def test_advance_ticks_participant_conditions(self):
        rnd = SceneRoundFactory(status=RoundStatus.DECLARING, round_number=1)
        sheet = CharacterSheetFactory()
        SceneRoundParticipantFactory(scene_round=rnd, character_sheet=sheet)
        target = sheet.character
        template = ConditionTemplateFactory(
            default_duration_type=DurationType.ROUNDS, default_duration_value=3
        )
        inst = ConditionInstanceFactory(target=target, condition=template, rounds_remaining=3)

        advance_scene_round(rnd)

        inst.refresh_from_db()
        assert inst.rounds_remaining == 2
        rnd.refresh_from_db()
        assert rnd.status == RoundStatus.BETWEEN_ROUNDS

    def test_end_marks_completed(self):
        rnd = SceneRoundFactory(status=RoundStatus.BETWEEN_ROUNDS)
        end_scene_round(rnd)
        rnd.refresh_from_db()
        assert rnd.status == RoundStatus.COMPLETED
        assert rnd.completed_at is not None

    def test_action_tick_advances_round_and_ticks_dot(self):
        from world.scenes.round_services import advance_scene_round_for_action

        rnd = SceneRoundFactory(
            status=RoundStatus.BETWEEN_ROUNDS,
            round_number=0,
            start_reason=SceneRoundStartReason.OPT_IN,
        )
        sheet = CharacterSheetFactory()
        SceneRoundParticipantFactory(scene_round=rnd, character_sheet=sheet)
        template = ConditionTemplateFactory(
            default_duration_type=DurationType.ROUNDS, default_duration_value=3
        )
        inst = ConditionInstanceFactory(
            target=sheet.character, condition=template, rounds_remaining=3
        )
        advance_scene_round_for_action(rnd)
        inst.refresh_from_db()
        assert inst.rounds_remaining == 2
        rnd.refresh_from_db()
        assert rnd.status == RoundStatus.BETWEEN_ROUNDS  # opt-in round stays active

    def test_danger_round_ends_when_no_bleedout_remains(self):
        # Under #1466, a danger round is STRICT and auto-ends inside resolve_scene_round
        # once no ACTIVE participant carries an acute danger condition.
        from evennia_extensions.factories import ObjectDBFactory

        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        rnd = SceneRoundFactory(
            room=room,
            status=RoundStatus.DECLARING,
            round_number=1,
            start_reason=SceneRoundStartReason.DANGER,
            mode=SceneRoundMode.STRICT,
        )
        sheet = CharacterSheetFactory()
        SceneRoundParticipantFactory(scene_round=rnd, character_sheet=sheet)
        resolve_scene_round(rnd)  # nobody Bleeding-Out -> danger round auto-ends
        rnd.refresh_from_db()
        assert rnd.status == RoundStatus.COMPLETED

    def test_danger_round_persists_while_bleedout_remains(self):
        # A danger round keeps going (advances to the next round) while a participant is
        # still Bleeding-Out.
        from evennia_extensions.factories import ObjectDBFactory
        from world.conditions.constants import BLEED_OUT_CONDITION_NAME

        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        rnd = SceneRoundFactory(
            room=room,
            status=RoundStatus.DECLARING,
            round_number=1,
            start_reason=SceneRoundStartReason.DANGER,
            mode=SceneRoundMode.STRICT,
        )
        sheet = CharacterSheetFactory()
        SceneRoundParticipantFactory(scene_round=rnd, character_sheet=sheet)
        bleed_template = ConditionTemplateFactory(
            name=BLEED_OUT_CONDITION_NAME,
            default_duration_type=DurationType.UNTIL_CURED,
        )
        ConditionInstanceFactory(target=sheet.character, condition=bleed_template)
        resolve_scene_round(rnd)
        rnd.refresh_from_db()
        assert rnd.status == RoundStatus.DECLARING  # peril persists -> next round
        assert rnd.round_number == 2


class SceneRoundResolutionTests(TestCase):
    def setUp(self):
        from evennia_extensions.factories import ObjectDBFactory

        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.rnd = SceneRoundFactory(
            room=self.room,
            status=RoundStatus.DECLARING,
            round_number=1,
            start_reason=SceneRoundStartReason.OPT_IN,
        )

    def _participant(self, *, present: bool, initiative_order: int = 0):
        sheet = CharacterSheetFactory()
        if present:
            sheet.character.db_location = self.room
            sheet.character.save(update_fields=["db_location"])
        return SceneRoundParticipantFactory(
            scene_round=self.rnd,
            character_sheet=sheet,
            initiative_order=initiative_order,
        )

    def _declare_pass(self, participant):
        return SceneActionDeclaration.objects.create(
            scene_round=self.rnd,
            round_number=self.rnd.round_number,
            participant=participant,
            is_pass=True,
        )

    def _downed_victim(
        self, *, source_character=None, abandoned_since_round=None, initiative_order=0
    ):
        """A present participant carrying an active Bleeding Out condition (downed).

        Returns (participant, bleed_out_instance). Pair with a patched ``can_act``
        that returns False for this participant's sheet to make them truly "downed".
        """
        from world.conditions.factories import BleedingOutConditionFactory

        participant = self._participant(present=True, initiative_order=initiative_order)
        inst = ConditionInstanceFactory(
            target=participant.character_sheet.character,
            condition=BleedingOutConditionFactory(),
            source_character=source_character,
            abandoned_since_round=abandoned_since_round,
        )
        return participant, inst

    def test_not_complete_when_present_participant_undeclared(self):
        p1 = self._participant(present=True, initiative_order=0)
        self._participant(present=True, initiative_order=1)
        self._declare_pass(p1)  # only one of two present participants has declared
        assert scene_round_is_complete(self.rnd) is False

    def test_complete_when_absent_participant_is_implicit_pass(self):
        present = self._participant(present=True, initiative_order=0)
        self._participant(present=False, initiative_order=1)  # absent => implicit pass
        self._declare_pass(present)
        assert scene_round_is_complete(self.rnd) is True

    def test_not_complete_when_no_one_present(self):
        self._participant(present=False, initiative_order=0)
        self._participant(present=False, initiative_order=1)
        # Nobody present to drive resolution.
        assert scene_round_is_complete(self.rnd) is False

    def test_not_complete_when_present_have_not_declared(self):
        self._participant(present=True, initiative_order=0)
        self._participant(present=True, initiative_order=1)
        assert scene_round_is_complete(self.rnd) is False

    def test_resolve_pass_only_advances_round_and_clears_bridge_rows(self):
        p1 = self._participant(present=True, initiative_order=0)
        p2 = self._participant(present=True, initiative_order=1)
        self._declare_pass(p1)
        self._declare_pass(p2)
        template = ConditionTemplateFactory(
            default_duration_type=DurationType.ROUNDS, default_duration_value=3
        )
        inst = ConditionInstanceFactory(
            target=p1.character_sheet.character, condition=template, rounds_remaining=3
        )

        resolve_scene_round(self.rnd)

        assert SceneActionDeclaration.objects.filter(scene_round=self.rnd).count() == 0
        self.rnd.refresh_from_db()
        assert self.rnd.status == RoundStatus.DECLARING
        assert self.rnd.round_number == 2
        inst.refresh_from_db()
        assert inst.rounds_remaining == 2  # shared END tick fired

    def test_force_resolves_when_present_not_all_declared(self):
        # A GM force-resolve calls resolve_scene_round directly to resolve an incomplete
        # round (undeclared present participants are swept as implicit passes).
        p1 = self._participant(present=True, initiative_order=0)
        self._participant(present=True, initiative_order=1)  # never declares
        self._declare_pass(p1)
        assert scene_round_is_complete(self.rnd) is False

        resolve_scene_round(self.rnd)

        self.rnd.refresh_from_db()
        assert self.rnd.status == RoundStatus.DECLARING
        assert self.rnd.round_number == 2
        assert SceneActionDeclaration.objects.filter(scene_round=self.rnd).count() == 0

    def test_resolve_rejects_non_declaring_round(self):
        self.rnd.status = RoundStatus.BETWEEN_ROUNDS
        self.rnd.save(update_fields=["status"])
        with self.assertRaises(ValueError):
            resolve_scene_round(self.rnd)

    def test_maybe_resolve_is_noop_when_incomplete(self):
        p1 = self._participant(present=True, initiative_order=0)
        self._participant(present=True, initiative_order=1)  # undeclared
        self._declare_pass(p1)

        maybe_resolve_scene_round(self.rnd)

        self.rnd.refresh_from_db()
        assert self.rnd.status == RoundStatus.DECLARING
        assert self.rnd.round_number == 1  # unchanged
        assert SceneActionDeclaration.objects.filter(scene_round=self.rnd).count() == 1

    def test_maybe_resolve_resolves_when_complete(self):
        p1 = self._participant(present=True, initiative_order=0)
        p2 = self._participant(present=True, initiative_order=1)
        self._declare_pass(p1)
        self._declare_pass(p2)

        maybe_resolve_scene_round(self.rnd)

        self.rnd.refresh_from_db()
        assert self.rnd.status == RoundStatus.DECLARING
        assert self.rnd.round_number == 2
        assert SceneActionDeclaration.objects.filter(scene_round=self.rnd).count() == 0

    def test_complete_on_quorum_not_unanimity(self):
        # 3 present, 2 declare, advance_quorum_pct=60 -> ceil(0.6*3)=2 met -> complete.
        # (Under the old unanimity rule this was False — the AFK stall fixed in #1480.)
        self.rnd.advance_quorum_pct = 60
        self.rnd.save(update_fields=["advance_quorum_pct"])
        p1 = self._participant(present=True, initiative_order=0)
        p2 = self._participant(present=True, initiative_order=1)
        self._participant(present=True, initiative_order=2)  # undeclared (AFK)
        self._declare_pass(p1)
        self._declare_pass(p2)
        assert scene_round_is_complete(self.rnd) is True

    def test_not_complete_below_quorum(self):
        # 3 present, 1 declares, quorum 60 -> ceil(0.6*3)=2 not met -> incomplete.
        self.rnd.advance_quorum_pct = 60
        self.rnd.save(update_fields=["advance_quorum_pct"])
        p1 = self._participant(present=True, initiative_order=0)
        self._participant(present=True, initiative_order=1)
        self._participant(present=True, initiative_order=2)
        self._declare_pass(p1)
        assert scene_round_is_complete(self.rnd) is False

    def test_quorum_100_reproduces_unanimity(self):
        # quorum 100 -> ceil(1.0*3)=3 -> every present can_act participant must declare.
        self.rnd.advance_quorum_pct = 100
        self.rnd.save(update_fields=["advance_quorum_pct"])
        p1 = self._participant(present=True, initiative_order=0)
        p2 = self._participant(present=True, initiative_order=1)
        self._participant(present=True, initiative_order=2)  # undeclared
        self._declare_pass(p1)
        self._declare_pass(p2)
        assert scene_round_is_complete(self.rnd) is False

    def test_afk_own_peril_skipped_on_quorum_resolve(self):
        # 3 present, 2 declare (quorum 60 met), the undeclared third is AFK. The AFK
        # participant's OWN acute condition must NOT tick on the END round-resolution
        # tick (ADR-0004: an AFK character is not harmed while away), while a declarer's
        # own condition DOES tick. This is the #1480 companion to the quorum change —
        # without it, quorum resolution would advance an AFK person's own peril.
        self.rnd.mode = SceneRoundMode.STRICT
        self.rnd.advance_quorum_pct = 60
        self.rnd.save(update_fields=["mode", "advance_quorum_pct"])
        p_decl = self._participant(present=True, initiative_order=0)
        p_afk = self._participant(present=True, initiative_order=1)  # never declares
        p_third = self._participant(present=True, initiative_order=2)
        self._declare_pass(p_decl)
        self._declare_pass(p_third)
        dot_template = ConditionTemplateFactory(
            default_duration_type=DurationType.ROUNDS, default_duration_value=3
        )
        decl_dot = ConditionInstanceFactory(
            target=p_decl.character_sheet.character,
            condition=dot_template,
            rounds_remaining=3,
        )
        afk_dot = ConditionInstanceFactory(
            target=p_afk.character_sheet.character,
            condition=dot_template,
            rounds_remaining=3,
        )

        resolve_scene_round(self.rnd)

        decl_dot.refresh_from_db()
        afk_dot.refresh_from_db()
        assert decl_dot.rounds_remaining == 2  # declarer's own condition ticked
        assert afk_dot.rounds_remaining == 3  # AFK (undeclared) own condition skipped

    def test_downed_victim_held_and_marked_when_only_bystander_declares(self):
        # A downed (unconscious) bleeding victim; the encounter that downed them is NOT
        # acting this round — only an uninvolved bystander declares. The victim's
        # bleed-out must NOT advance (excluded from the END tick) and must be marked
        # abandoned for this round (#1479). tick_round_for_targets is patched so the
        # selection logic is asserted without traversing the PG-only bleed-out path.
        from evennia_extensions.factories import ObjectDBFactory

        self.rnd.mode = SceneRoundMode.STRICT
        self.rnd.save(update_fields=["mode"])
        npc_source = ObjectDBFactory()  # off-screen attacker, not enrolled this round
        victim_p, bleed = self._downed_victim(source_character=npc_source, initiative_order=0)
        bystander = self._participant(present=True, initiative_order=1)  # potential rescuer
        self._declare_pass(bystander)

        def fake_can_act(sheet):
            return sheet is None or sheet.character_id != victim_p.character_sheet.character_id

        with (
            mock.patch("world.vitals.services.can_act", side_effect=fake_can_act),
            mock.patch("world.scenes.round_services.tick_round_for_targets") as tick,
        ):
            resolve_scene_round(self.rnd)

        ticked = set(tick.call_args.args[0])
        assert victim_p.character_sheet.character not in ticked  # peril held, did not advance
        bleed.refresh_from_db()
        assert bleed.abandoned_since_round == 1  # stamped with the resolved round_number

    def test_downed_victim_advances_and_marker_cleared_when_source_declares(self):
        # The hostile SOURCE that downed the victim declares this round — "the encounter
        # that downed them is still acting." The victim's bleed-out advances (included in
        # the END tick) and any prior abandonment marker is cleared (#1479).
        self.rnd.mode = SceneRoundMode.STRICT
        self.rnd.save(update_fields=["mode"])
        source_p = self._participant(present=True, initiative_order=0)
        victim_p, bleed = self._downed_victim(
            source_character=source_p.character_sheet.character,
            abandoned_since_round=5,  # stale marker from a prior abandoned round
            initiative_order=1,
        )
        self._declare_pass(source_p)

        def fake_can_act(sheet):
            return sheet is None or sheet.character_id != victim_p.character_sheet.character_id

        with (
            mock.patch("world.vitals.services.can_act", side_effect=fake_can_act),
            mock.patch("world.scenes.round_services.tick_round_for_targets") as tick,
        ):
            resolve_scene_round(self.rnd)

        ticked = set(tick.call_args.args[0])
        assert victim_p.character_sheet.character in ticked  # peril advances
        bleed.refresh_from_db()
        assert bleed.abandoned_since_round is None  # cleared — hostile drove again


class SceneRoundAbandonmentTests(TestCase):
    """Abandonment resolution (#1479 Task 8): N-beat grace window + solo-immediate.

    An abandoned downed victim (held, marked) resolves through the
    source-appropriate abandonment pool once they have waited
    ``abandonment_grace_rounds`` beats; a departure that removes the last
    potential rescuer resolves a still-downed victim immediately.
    """

    def setUp(self):
        from evennia_extensions.factories import ObjectDBFactory
        from world.checks.factories import CheckTypeFactory
        from world.conditions.factories import BleedingOutConditionFactory, ConditionStageFactory
        from world.scenes.models import get_scene_round_defaults_config
        from world.traits.factories import CheckOutcomeFactory
        from world.vitals.factories import create_abandonment_pools

        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.rnd = SceneRoundFactory(
            room=self.room,
            status=RoundStatus.DECLARING,
            round_number=1,
            mode=SceneRoundMode.STRICT,
            start_reason=SceneRoundStartReason.OPT_IN,
        )
        self.check_type = CheckTypeFactory()
        self.bleed_out = BleedingOutConditionFactory()
        self.stage = ConditionStageFactory(
            condition=self.bleed_out,
            stage_order=1,
            name="Dying",
            resist_check_type=self.check_type,
            resist_difficulty=40,
            rounds_to_next=None,
        )
        create_abandonment_pools()
        self.failure_outcome = CheckOutcomeFactory(name="Failure", success_level=-1)
        cfg = get_scene_round_defaults_config()
        cfg.abandonment_grace_rounds = 2
        cfg.save(update_fields=["abandonment_grace_rounds"])

    def _present(self, *, initiative_order=0):
        sheet = CharacterSheetFactory()
        sheet.character.db_location = self.room
        sheet.character.save(update_fields=["db_location"])
        return SceneRoundParticipantFactory(
            scene_round=self.rnd, character_sheet=sheet, initiative_order=initiative_order
        )

    def _downed_victim(self, *, source_character, abandoned_since_round=None, initiative_order=0):
        from world.vitals.constants import CharacterLifeState
        from world.vitals.factories import CharacterVitalsFactory

        p = self._present(initiative_order=initiative_order)
        CharacterVitalsFactory(
            character_sheet=p.character_sheet,
            life_state=CharacterLifeState.ALIVE,
            health=-5,
            max_health=100,
        )
        inst = ConditionInstanceFactory(
            target=p.character_sheet.character,
            condition=self.bleed_out,
            current_stage=self.stage,
            source_character=source_character,
            abandoned_since_round=abandoned_since_round,
        )
        return p, inst

    def _declare_pass(self, participant):
        return SceneActionDeclaration.objects.create(
            scene_round=self.rnd,
            round_number=self.rnd.round_number,
            participant=participant,
            is_pass=True,
        )

    def _set_round_number(self, n):
        self.rnd.round_number = n
        self.rnd.save(update_fields=["round_number"])

    @staticmethod
    def _fake_can_act_for(victim_p):
        def fake_can_act(sheet):
            return sheet is None or sheet.character_id != victim_p.character_sheet.character_id

        return fake_can_act

    def test_abandoned_victim_resolves_after_grace(self):
        # Held + marked at round 1; resolving round 3 → delta 2 >= grace 2 → fate resolves.
        from evennia_extensions.factories import CharacterFactory

        npc_source = CharacterFactory()  # off-screen NPC: not enrolled, never drives
        victim_p, _bleed = self._downed_victim(
            source_character=npc_source, abandoned_since_round=1, initiative_order=0
        )
        bystander = self._present(initiative_order=1)  # potential rescuer present
        self._set_round_number(3)
        self._declare_pass(bystander)

        with (
            mock.patch(
                "world.vitals.services.can_act",
                side_effect=self._fake_can_act_for(victim_p),
            ),
            mock.patch("world.scenes.round_services.tick_round_for_targets"),
            self._force_failure(),
        ):
            resolve_scene_round(self.rnd)

        from world.vitals.constants import CharacterLifeState

        victim_p.character_sheet.vitals.refresh_from_db()
        assert victim_p.character_sheet.vitals.life_state == CharacterLifeState.DEAD

    def test_abandoned_victim_below_grace_not_resolved(self):
        from evennia_extensions.factories import CharacterFactory
        from world.vitals.constants import CharacterLifeState

        npc_source = CharacterFactory()
        victim_p, _bleed = self._downed_victim(
            source_character=npc_source, abandoned_since_round=1, initiative_order=0
        )
        bystander = self._present(initiative_order=1)
        self._set_round_number(2)  # delta 1 < grace 2 → not yet
        self._declare_pass(bystander)

        with (
            mock.patch(
                "world.vitals.services.can_act",
                side_effect=self._fake_can_act_for(victim_p),
            ),
            mock.patch("world.scenes.round_services.tick_round_for_targets"),
            self._force_failure(),
        ):
            resolve_scene_round(self.rnd)

        victim_p.character_sheet.vitals.refresh_from_db()
        assert victim_p.character_sheet.vitals.life_state == CharacterLifeState.ALIVE
        from world.conditions.models import ConditionInstance

        assert ConditionInstance.objects.filter(
            target=victim_p.character_sheet.character, condition=self.bleed_out
        ).exists()

    def test_rescue_before_grace_no_resolution(self):
        # The bleed-out is cleared before the grace window elapses → no roll, victim saved.
        from evennia_extensions.factories import CharacterFactory
        from world.conditions.services import remove_condition
        from world.vitals.constants import CharacterLifeState

        npc_source = CharacterFactory()
        victim_p, _bleed = self._downed_victim(
            source_character=npc_source, abandoned_since_round=1, initiative_order=0
        )
        bystander = self._present(initiative_order=1)
        self._set_round_number(3)  # grace would be met
        self._declare_pass(bystander)

        remove_condition(victim_p.character_sheet.character, self.bleed_out)  # rescue

        with (
            mock.patch(
                "world.vitals.services.can_act",
                side_effect=self._fake_can_act_for(victim_p),
            ),
            mock.patch("world.scenes.round_services.tick_round_for_targets"),
            self._force_failure(),
        ):
            resolve_scene_round(self.rnd)

        victim_p.character_sheet.vitals.refresh_from_db()
        assert victim_p.character_sheet.vitals.life_state == CharacterLifeState.ALIVE

    def test_solo_last_rescuer_leaves_resolves_immediately(self):
        from evennia_extensions.factories import CharacterFactory
        from world.vitals.constants import CharacterLifeState

        npc_source = CharacterFactory()  # off-screen
        victim_p, _bleed = self._downed_victim(source_character=npc_source, initiative_order=0)
        rescuer = self._present(initiative_order=1)

        with (
            mock.patch(
                "world.vitals.services.can_act",
                side_effect=self._fake_can_act_for(victim_p),
            ),
            self._force_failure(),
        ):
            # The last conscious other character leaves the room.
            self.room.at_object_leave(rescuer.character_sheet.character, None)

        victim_p.character_sheet.vitals.refresh_from_db()
        assert victim_p.character_sheet.vitals.life_state == CharacterLifeState.DEAD

    def test_abandonment_death_auto_ends_danger_round(self):
        """Regression: abandonment death must clear the acute-peril condition so
        _danger_persists returns False and the DANGER round auto-ends (COMPLETED)
        instead of cycling forever with a dead victim still carrying bleed-out (#1479).

        Before the fix, _resolve_peril_via_pool cleared the condition only on
        SURVIVAL, leaving it on dead characters → _danger_persists True → the
        DANGER round never auto-ended.
        """
        from evennia_extensions.factories import CharacterFactory
        from world.conditions.models import ConditionInstance
        from world.vitals.constants import CharacterLifeState

        npc_source = CharacterFactory()  # NPC source permits death
        victim_p, _bleed = self._downed_victim(
            source_character=npc_source, abandoned_since_round=1, initiative_order=0
        )
        bystander = self._present(initiative_order=1)
        # round_number=3, grace=2 → 3-1=2 >= 2 → abandonment fires this resolve.
        self._set_round_number(3)
        self._declare_pass(bystander)

        # Change the round to DANGER so the auto-end logic fires.
        self.rnd.start_reason = SceneRoundStartReason.DANGER
        self.rnd.save(update_fields=["start_reason"])

        with (
            mock.patch(
                "world.vitals.services.can_act",
                side_effect=self._fake_can_act_for(victim_p),
            ),
            mock.patch("world.scenes.round_services.tick_round_for_targets"),
            self._force_failure(),
        ):
            resolve_scene_round(self.rnd)

        # Victim died.
        victim_p.character_sheet.vitals.refresh_from_db()
        assert victim_p.character_sheet.vitals.life_state == CharacterLifeState.DEAD

        # Critical regression assertion: the acute-peril condition must be cleared on
        # death so _danger_persists returns False.
        assert not ConditionInstance.objects.filter(
            target=victim_p.character_sheet.character, condition=self.bleed_out
        ).exists(), (
            "Acute-peril condition must be cleared on death; "
            "if it persists _danger_persists stays True and the DANGER round freezes"
        )

        # The DANGER round must auto-end (COMPLETED) because _danger_persists is False.
        self.rnd.refresh_from_db()
        assert self.rnd.status == RoundStatus.COMPLETED, (
            f"DANGER round must auto-end after peril clears; got {self.rnd.status!r}"
        )

    def _force_failure(self):
        from world.checks.test_helpers import force_check_outcome

        return force_check_outcome(self.failure_outcome)


class SceneRoundOutcomeBroadcastTests(TestCase):
    """_resolve_scene_declarations broadcasts an OUTCOME narration for each resolved challenge."""

    def setUp(self):
        from evennia_extensions.factories import ObjectDBFactory
        from world.mechanics.factories import ChallengeApproachFactory, ChallengeInstanceFactory

        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.rnd = SceneRoundFactory(
            room=self.room,
            status=RoundStatus.DECLARING,
            round_number=1,
            start_reason=SceneRoundStartReason.OPT_IN,
        )
        self.sheet = CharacterSheetFactory()
        self.sheet.character.db_location = self.room
        self.sheet.character.db_key = "Kira"
        self.sheet.character.save(update_fields=["db_location", "db_key"])
        self.participant = SceneRoundParticipantFactory(
            scene_round=self.rnd,
            character_sheet=self.sheet,
            initiative_order=0,
        )
        self.challenge_instance = ChallengeInstanceFactory(location=self.room)
        self.approach = ChallengeApproachFactory(
            challenge_template=self.challenge_instance.template
        )

    def _declare_challenge(self):
        return SceneActionDeclaration.objects.create(
            scene_round=self.rnd,
            round_number=self.rnd.round_number,
            participant=self.participant,
            challenge_instance=self.challenge_instance,
            challenge_approach=self.approach,
            is_pass=False,
        )

    def _fake_resolution_result(self, *, success_level: int = 1):
        check_result = MagicMock()
        check_result.outcome_name = "Decisive Success" if success_level > 0 else "Failure"
        check_result.success_level = success_level
        outcome = MagicMock()
        outcome.challenge_name = self.challenge_instance.template.name
        outcome.approach_name = self.approach.display_name
        outcome.check_result = check_result
        return outcome

    def test_outcome_interaction_created_on_challenge_resolution(self):
        self._declare_challenge()
        fake_result = self._fake_resolution_result(success_level=1)
        fake_action = MagicMock()
        fake_action.challenge_instance_id = self.challenge_instance.pk
        fake_action.approach_id = self.approach.pk
        fake_action.capability_source = None
        with (
            mock.patch(
                "world.mechanics.challenge_resolution.resolve_challenge", return_value=fake_result
            ),
            mock.patch(
                "world.mechanics.services.get_available_actions", return_value=[fake_action]
            ),
        ):
            resolve_scene_round(self.rnd)
        assert Interaction.objects.filter(mode=InteractionMode.OUTCOME).count() == 1

    def test_outcome_interaction_content_matches_narration(self):
        self._declare_challenge()
        fake_result = self._fake_resolution_result(success_level=1)
        fake_action = MagicMock()
        fake_action.challenge_instance_id = self.challenge_instance.pk
        fake_action.approach_id = self.approach.pk
        fake_action.capability_source = None
        with (
            mock.patch(
                "world.mechanics.challenge_resolution.resolve_challenge", return_value=fake_result
            ),
            mock.patch(
                "world.mechanics.services.get_available_actions", return_value=[fake_action]
            ),
        ):
            resolve_scene_round(self.rnd)
        interaction = Interaction.objects.get(mode=InteractionMode.OUTCOME)
        assert "Kira" in interaction.content
        assert "succeeds" in interaction.content

    def test_no_outcome_when_check_result_is_none(self):
        self._declare_challenge()
        fake_result = self._fake_resolution_result()
        fake_result.check_result = None
        fake_action = MagicMock()
        fake_action.challenge_instance_id = self.challenge_instance.pk
        fake_action.approach_id = self.approach.pk
        fake_action.capability_source = None
        with (
            mock.patch(
                "world.mechanics.challenge_resolution.resolve_challenge", return_value=fake_result
            ),
            mock.patch(
                "world.mechanics.services.get_available_actions", return_value=[fake_action]
            ),
        ):
            resolve_scene_round(self.rnd)
        assert Interaction.objects.filter(mode=InteractionMode.OUTCOME).count() == 0

    def test_pass_declarations_produce_no_outcome_interaction(self):
        SceneActionDeclaration.objects.create(
            scene_round=self.rnd,
            round_number=self.rnd.round_number,
            participant=self.participant,
            is_pass=True,
        )
        resolve_scene_round(self.rnd)
        assert Interaction.objects.filter(mode=InteractionMode.OUTCOME).count() == 0
