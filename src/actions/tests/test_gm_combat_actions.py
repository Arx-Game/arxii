"""Tests for GM combat-encounter lifecycle actions (#1494)."""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.gm_combat import (
    AddEncounterParticipantAction,
    AddOpponentAction,
    BeginEncounterRoundAction,
    CreateEncounterAction,
    EndEncounterAction,
    GMTriggerDramaticBeatAction,
    PauseEncounterAction,
    PreviewOpponentDefaultsAction,
    RemoveEncounterParticipantAction,
    ResolveEncounterRoundAction,
    SpawnCreatureAction,
    UpdateEncounterSettingsAction,
)
from actions.registry import get_action
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    EncounterOutcome,
    OpponentTier,
    PaceMode,
    ParticipantStatus,
    RiskLevel,
    StakesLevel,
    SurgeTriggerKind,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    EscalationCurveFactory,
    ThreatPoolFactory,
    seed_scaling_defaults,
)
from world.combat.models import (
    BossPhase,
    BreakBarConfig,
    CombatEncounter,
    CombatOpponent,
    CombatParticipant,
    CreaturePhaseTemplate,
    CreatureTemplate,
    DramaticSurgeRecord,
)
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.mechanics.constants import EngagementType
from world.mechanics.services import begin_engagement
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.stories.constants import BeatPredicateType
from world.stories.factories import BeatFactory, ChapterFactory, EpisodeFactory, StoryFactory


def _make_room(label: str = "Room") -> object:
    return ObjectDBFactory(
        db_key=label,
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _make_actor_with_account(
    db_key: str,
    room: object,
    account: object,
) -> tuple[object, object]:
    """Create a PC in *room* whose ``active_account`` is *account*."""
    char = CharacterFactory(db_key=db_key, location=room)
    CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet__character=char)
    RosterTenureFactory(
        roster_entry=entry,
        player_data__account=account,
        end_date=None,
    )
    return char, entry.character_sheet


class GMCombatActionTestBase(TestCase):
    """Shared fixture: room, GM actor, non-GM actor, scene, encounter."""

    def setUp(self) -> None:
        self.room = _make_room("GMCombatRoom")

        # GM account/actor (staff)
        self.gm_account = AccountFactory(username="testgm", is_staff=True)
        self.gm_actor, self.gm_sheet = _make_actor_with_account(
            "gm_actor",
            self.room,
            self.gm_account,
        )

        # Non-GM player actor
        self.player_account = AccountFactory(username="testplayer")
        self.player_actor, self.player_sheet = _make_actor_with_account(
            "player_actor",
            self.room,
            self.player_account,
        )

        # Scene with the player as a non-GM participant and the GM as GM.
        self.scene = SceneFactory(location=self.room)
        SceneParticipationFactory(scene=self.scene, account=self.player_account, is_gm=False)
        SceneParticipationFactory(scene=self.scene, account=self.gm_account, is_gm=True)

        # Encounter in BETWEEN_ROUNDS by default.
        self.encounter = CombatEncounterFactory(
            room=self.room,
            scene=self.scene,
            status=RoundStatus.BETWEEN_ROUNDS,
            round_number=0,
            risk_level=RiskLevel.MODERATE,
            stakes_level=StakesLevel.LOCAL,
        )

    def _add_opponent(self) -> CombatOpponent:
        return CombatOpponentFactory(encounter=self.encounter)

    def _add_participant(self) -> CombatParticipant:
        return CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.player_sheet,
            status=ParticipantStatus.ACTIVE,
        )


class BeginEncounterRoundActionTests(GMCombatActionTestBase):
    """BeginEncounterRoundAction advances an encounter to DECLARING."""

    def test_gm_can_begin_round(self) -> None:
        self._add_opponent()
        result = BeginEncounterRoundAction().run(self.gm_actor)
        self.assertTrue(result.success, result.message)
        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.status, RoundStatus.DECLARING)
        self.assertEqual(self.encounter.round_number, 1)

    def test_non_gm_denied(self) -> None:
        self._add_opponent()
        result = BeginEncounterRoundAction().run(self.player_actor)
        self.assertFalse(result.success)
        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.status, RoundStatus.BETWEEN_ROUNDS)

    def test_fails_without_active_encounter(self) -> None:
        other_room = _make_room("OtherRoom")
        self.gm_actor.location = other_room
        result = BeginEncounterRoundAction().run(self.gm_actor)
        self.assertFalse(result.success)

    def test_fails_when_not_between_rounds(self) -> None:
        self._add_opponent()
        self.encounter.status = RoundStatus.DECLARING
        self.encounter.save(update_fields=["status"])
        result = BeginEncounterRoundAction().run(self.gm_actor)
        self.assertFalse(result.success)

    def test_fails_without_active_opponent(self) -> None:
        result = BeginEncounterRoundAction().run(self.gm_actor)
        self.assertFalse(result.success)
        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.status, RoundStatus.BETWEEN_ROUNDS)


class ResolveEncounterRoundActionTests(GMCombatActionTestBase):
    """ResolveEncounterRoundAction resolves a DECLARING round."""

    def setUp(self) -> None:
        super().setUp()
        self._add_opponent()
        self.encounter.status = RoundStatus.DECLARING
        self.encounter.round_number = 1
        self.encounter.save(update_fields=["status", "round_number"])

    def test_gm_can_resolve_round(self) -> None:
        self._add_participant()
        result = ResolveEncounterRoundAction().run(self.gm_actor)
        self.assertTrue(result.success, result.message)
        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.status, RoundStatus.BETWEEN_ROUNDS)

    def test_non_gm_denied(self) -> None:
        result = ResolveEncounterRoundAction().run(self.player_actor)
        self.assertFalse(result.success)
        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.status, RoundStatus.DECLARING)

    def test_fails_when_not_declaring(self) -> None:
        self.encounter.status = RoundStatus.BETWEEN_ROUNDS
        self.encounter.save(update_fields=["status"])
        result = ResolveEncounterRoundAction().run(self.gm_actor)
        self.assertFalse(result.success)


class AddOpponentActionTests(GMCombatActionTestBase):
    """AddOpponentAction creates a CombatOpponent in the encounter."""

    def setUp(self) -> None:
        super().setUp()
        seed_scaling_defaults()
        self.pool = ThreatPoolFactory()

    def test_gm_can_add_opponent(self) -> None:
        result = AddOpponentAction().run(
            self.gm_actor,
            name="Test Mook",
            tier=OpponentTier.MOOK,
            threat_pool_id=str(self.pool.pk),
        )
        self.assertTrue(result.success, result.message)
        self.assertTrue(
            CombatOpponent.objects.filter(encounter=self.encounter, name="Test Mook").exists()
        )

    def test_non_gm_denied(self) -> None:
        result = AddOpponentAction().run(
            self.player_actor,
            name="Test Mook",
            tier=OpponentTier.MOOK,
            threat_pool_id=str(self.pool.pk),
        )
        self.assertFalse(result.success)
        self.assertFalse(
            CombatOpponent.objects.filter(encounter=self.encounter, name="Test Mook").exists()
        )

    def test_resolves_threat_pool_by_name(self) -> None:
        result = AddOpponentAction().run(
            self.gm_actor,
            name="Named Pool Mook",
            tier=OpponentTier.MOOK,
            threat_pool_id=self.pool.name,
        )
        self.assertTrue(result.success, result.message)

    def test_missing_target(self) -> None:
        result = AddOpponentAction().run(self.gm_actor, name="", tier="")
        self.assertFalse(result.success)

    def test_cross_room_position_fails_without_orphaning_opponent(self) -> None:
        """Task 4 fold-in (#2005): a cross-room position surfaces a failure

        ActionResult and leaves no saved-but-unplaced CombatOpponent behind.
        """
        from world.areas.positioning.services import create_position

        other_room = _make_room("OtherRoomForPosition")
        position = create_position(other_room, "elsewhere")

        result = AddOpponentAction().run(
            self.gm_actor,
            name="Misplaced Mook",
            tier=OpponentTier.MOOK,
            threat_pool_id=str(self.pool.pk),
            position_id=position.pk,
        )

        self.assertFalse(result.success)
        self.assertFalse(
            CombatOpponent.objects.filter(encounter=self.encounter, name="Misplaced Mook").exists()
        )


class SpawnCreatureActionTests(GMCombatActionTestBase):
    """SpawnCreatureAction spawns an authored bestiary CreatureTemplate (#3424)."""

    def setUp(self) -> None:
        super().setUp()
        seed_scaling_defaults()
        self.pool = ThreatPoolFactory()

    def test_gm_can_spawn_creature(self) -> None:
        template = CreatureTemplate.objects.create(
            name="Gorehorn",
            tier=OpponentTier.MOOK,
            threat_pool=self.pool,
        )
        result = SpawnCreatureAction().run(self.gm_actor, template=str(template.pk))
        self.assertTrue(result.success, result.message)
        self.assertTrue(
            CombatOpponent.objects.filter(encounter=self.encounter, name="Gorehorn").exists()
        )

    def test_non_gm_denied(self) -> None:
        template = CreatureTemplate.objects.create(
            name="Gorehorn",
            tier=OpponentTier.MOOK,
            threat_pool=self.pool,
        )
        result = SpawnCreatureAction().run(self.player_actor, template=str(template.pk))
        self.assertFalse(result.success)
        self.assertFalse(
            CombatOpponent.objects.filter(encounter=self.encounter, name="Gorehorn").exists()
        )

    def test_resolves_template_by_name(self) -> None:
        CreatureTemplate.objects.create(
            name="Named Bestiary Mook",
            tier=OpponentTier.MOOK,
            threat_pool=self.pool,
        )
        result = SpawnCreatureAction().run(self.gm_actor, template="Named Bestiary Mook")
        self.assertTrue(result.success, result.message)

    def test_missing_template(self) -> None:
        result = SpawnCreatureAction().run(self.gm_actor)
        self.assertFalse(result.success)

    def test_unknown_template(self) -> None:
        result = SpawnCreatureAction().run(self.gm_actor, template="Nonexistent")
        self.assertFalse(result.success)

    def test_cross_room_position_fails_without_orphaning_opponent(self) -> None:
        """Mirrors AddOpponentActionTests' cross-room position coverage (#2005 Task 4)."""
        from world.areas.positioning.services import create_position

        template = CreatureTemplate.objects.create(
            name="Misplaced Beast",
            tier=OpponentTier.MOOK,
            threat_pool=self.pool,
        )
        other_room = _make_room("OtherRoomForSpawnPosition")
        position = create_position(other_room, "elsewhere")

        result = SpawnCreatureAction().run(
            self.gm_actor,
            template=str(template.pk),
            position_id=position.pk,
        )

        self.assertFalse(result.success)
        self.assertFalse(
            CombatOpponent.objects.filter(encounter=self.encounter, name="Misplaced Beast").exists()
        )

    def test_journey_authored_phases_and_break_bar_then_round_resolves(self) -> None:
        """Registry-dispatch journey test (#3424 spec Test seams).

        Spawns a template with authored phases + a break bar via
        ``action.run()`` (not the service function directly), asserts the
        cloned ``BossPhase`` rows and break-bar stamps land on the spawned
        ``CombatOpponent``, then resolves a round with it present.
        """
        template = CreatureTemplate.objects.create(
            name="Gorehorn the Undying",
            tier=OpponentTier.BOSS,
            threat_pool=self.pool,
        )
        phase_one = CreaturePhaseTemplate.objects.create(
            creature_template=template,
            phase_number=1,
            health_trigger_percentage=1.0,
            soak_value=5,
        )
        CreaturePhaseTemplate.objects.create(
            creature_template=template,
            phase_number=2,
            health_trigger_percentage=0.5,
            soak_value=10,
            extra_actions=1,
        )
        BreakBarConfig.objects.create(
            boss_phase=phase_one,
            max_threshold=30,
            vulnerability_rounds=2,
            intensity_bonus=2,
        )

        result = SpawnCreatureAction().run(self.gm_actor, template=str(template.pk))
        self.assertTrue(result.success, result.message)

        opponent = CombatOpponent.objects.get(encounter=self.encounter, name="Gorehorn the Undying")
        self.assertEqual(opponent.creature_template, template)
        phases = BossPhase.objects.filter(opponent=opponent).order_by("phase_number")
        self.assertEqual(phases.count(), 2)
        self.assertEqual(phases[0].soak_value, 5)
        self.assertEqual(phases[1].soak_value, 10)
        self.assertGreater(opponent.break_bar_threshold, 0)
        self.assertEqual(opponent.break_bar_current, opponent.break_bar_threshold)
        self.assertEqual(opponent.vulnerability_rounds, 2)

        # A round resolves cleanly with the spawned bestiary opponent present
        # -- covers web and telnet identically (both converge on action.run()).
        # A living PC participant keeps the encounter running after the round
        # (with none, resolution completes the encounter instead).
        self._add_participant()
        self.encounter.refresh_from_db()
        self.encounter.status = RoundStatus.DECLARING
        self.encounter.round_number = 1
        self.encounter.save(update_fields=["status", "round_number"])
        round_result = ResolveEncounterRoundAction().run(self.gm_actor)
        self.assertTrue(round_result.success, round_result.message)
        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.status, RoundStatus.BETWEEN_ROUNDS)


class AddEncounterParticipantActionTests(GMCombatActionTestBase):
    """AddEncounterParticipantAction enrolls a PC in the encounter."""

    def setUp(self) -> None:
        super().setUp()
        # A second PC in the room, not yet a participant.
        self.joiner_account = AccountFactory(username="joiner")
        self.joiner_actor, self.joiner_sheet = _make_actor_with_account(
            "joiner_actor",
            self.room,
            self.joiner_account,
        )

    def test_gm_can_add_participant(self) -> None:
        result = AddEncounterParticipantAction().run(
            self.gm_actor,
            character_sheet_id=str(self.joiner_sheet.pk),
        )
        self.assertTrue(result.success, result.message)
        self.assertTrue(
            CombatParticipant.objects.filter(
                encounter=self.encounter,
                character_sheet=self.joiner_sheet,
            ).exists()
        )

    def test_non_gm_denied(self) -> None:
        result = AddEncounterParticipantAction().run(
            self.player_actor,
            character_sheet_id=str(self.joiner_sheet.pk),
        )
        self.assertFalse(result.success)

    def test_resolves_character_by_name(self) -> None:
        result = AddEncounterParticipantAction().run(
            self.gm_actor,
            character_sheet_id="joiner_actor",
        )
        self.assertTrue(result.success, result.message)

    def test_missing_target(self) -> None:
        result = AddEncounterParticipantAction().run(self.gm_actor)
        self.assertFalse(result.success)

    def test_fails_for_character_not_in_room(self) -> None:
        other_room = _make_room("OtherRoom")
        _absent_actor, absent_sheet = _make_actor_with_account(
            "absent_actor",
            other_room,
            AccountFactory(username="absent"),
        )
        result = AddEncounterParticipantAction().run(
            self.gm_actor,
            character_sheet_id=str(absent_sheet.pk),
        )
        self.assertFalse(result.success)


class RemoveEncounterParticipantActionTests(GMCombatActionTestBase):
    """RemoveEncounterParticipantAction marks a participant REMOVED."""

    def setUp(self) -> None:
        super().setUp()
        self.participant = self._add_participant()

    def test_gm_can_remove_participant(self) -> None:
        result = RemoveEncounterParticipantAction().run(
            self.gm_actor,
            participant_id=str(self.participant.pk),
        )
        self.assertTrue(result.success, result.message)
        self.participant.refresh_from_db()
        self.assertEqual(self.participant.status, ParticipantStatus.REMOVED)

    def test_non_gm_denied(self) -> None:
        result = RemoveEncounterParticipantAction().run(
            self.player_actor,
            participant_id=str(self.participant.pk),
        )
        self.assertFalse(result.success)
        self.participant.refresh_from_db()
        self.assertEqual(self.participant.status, ParticipantStatus.ACTIVE)

    def test_resolves_participant_by_character_name(self) -> None:
        result = RemoveEncounterParticipantAction().run(
            self.gm_actor,
            participant_id="player_actor",
        )
        self.assertTrue(result.success, result.message)
        self.participant.refresh_from_db()
        self.assertEqual(self.participant.status, ParticipantStatus.REMOVED)

    def test_missing_target(self) -> None:
        result = RemoveEncounterParticipantAction().run(self.gm_actor)
        self.assertFalse(result.success)


class PauseEncounterActionTests(GMCombatActionTestBase):
    """PauseEncounterAction toggles encounter.is_paused."""

    def test_gm_can_pause(self) -> None:
        result = PauseEncounterAction().run(self.gm_actor)
        self.assertTrue(result.success, result.message)
        self.encounter.refresh_from_db()
        self.assertTrue(self.encounter.is_paused)

    def test_gm_can_unpause(self) -> None:
        self.encounter.is_paused = True
        self.encounter.save(update_fields=["is_paused"])
        result = PauseEncounterAction().run(self.gm_actor)
        self.assertTrue(result.success, result.message)
        self.encounter.refresh_from_db()
        self.assertFalse(self.encounter.is_paused)

    def test_non_gm_denied(self) -> None:
        result = PauseEncounterAction().run(self.player_actor)
        self.assertFalse(result.success)


class UpdateEncounterSettingsActionTests(GMCombatActionTestBase):
    """UpdateEncounterSettingsAction changes stakes/risk/pace/timer (#3383)."""

    def test_gm_can_change_stakes_level(self) -> None:
        result = UpdateEncounterSettingsAction().run(self.gm_actor, stakes_level=StakesLevel.WORLD)
        self.assertTrue(result.success, result.message)
        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.stakes_level, StakesLevel.WORLD)

    def test_gm_can_change_risk_level(self) -> None:
        result = UpdateEncounterSettingsAction().run(self.gm_actor, risk_level=RiskLevel.LETHAL)
        self.assertTrue(result.success, result.message)
        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.risk_level, RiskLevel.LETHAL)

    def test_gm_can_change_pace_mode(self) -> None:
        result = UpdateEncounterSettingsAction().run(self.gm_actor, pace_mode=PaceMode.MANUAL)
        self.assertTrue(result.success, result.message)
        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.pace_mode, PaceMode.MANUAL)

    def test_gm_can_change_timer(self) -> None:
        result = UpdateEncounterSettingsAction().run(self.gm_actor, pace_timer_minutes="20")
        self.assertTrue(result.success, result.message)
        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.pace_timer_minutes, 20)

    def test_invalid_stakes_level_rejected(self) -> None:
        result = UpdateEncounterSettingsAction().run(self.gm_actor, stakes_level="not_a_level")
        self.assertFalse(result.success)

    def test_invalid_timer_rejected(self) -> None:
        result = UpdateEncounterSettingsAction().run(
            self.gm_actor, pace_timer_minutes="not_a_number"
        )
        self.assertFalse(result.success)

    def test_non_gm_denied(self) -> None:
        result = UpdateEncounterSettingsAction().run(
            self.player_actor, stakes_level=StakesLevel.WORLD
        )
        self.assertFalse(result.success)

    def test_no_active_encounter_denied(self) -> None:
        self.encounter.status = RoundStatus.COMPLETED
        self.encounter.save(update_fields=["status"])
        result = UpdateEncounterSettingsAction().run(self.gm_actor, stakes_level=StakesLevel.WORLD)
        self.assertFalse(result.success)


class EndEncounterActionTests(GMCombatActionTestBase):
    """EndEncounterAction completes the encounter as ABANDONED."""

    def test_gm_can_end_encounter(self) -> None:
        self._add_participant()
        result = EndEncounterAction().run(self.gm_actor)
        self.assertTrue(result.success, result.message)
        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.status, RoundStatus.COMPLETED)
        self.assertEqual(self.encounter.outcome, EncounterOutcome.ABANDONED)

    def test_non_gm_denied(self) -> None:
        result = EndEncounterAction().run(self.player_actor)
        self.assertFalse(result.success)
        self.encounter.refresh_from_db()
        self.assertNotEqual(self.encounter.status, RoundStatus.COMPLETED)

    def test_fails_when_already_completed(self) -> None:
        self.encounter.status = RoundStatus.COMPLETED
        self.encounter.save(update_fields=["status"])
        result = EndEncounterAction().run(self.gm_actor)
        self.assertFalse(result.success)
        self.assertEqual(result.message, "Encounter already completed.")


class PreviewOpponentDefaultsActionTests(GMCombatActionTestBase):
    """PreviewOpponentDefaultsAction returns a stat-block preview."""

    def setUp(self) -> None:
        super().setUp()
        seed_scaling_defaults()

    def test_gm_can_preview(self) -> None:
        result = PreviewOpponentDefaultsAction().run(
            self.gm_actor,
            tier=OpponentTier.ELITE,
        )
        self.assertTrue(result.success, result.message)
        self.assertIn("max health", result.message.lower())

    def test_non_gm_denied(self) -> None:
        result = PreviewOpponentDefaultsAction().run(
            self.player_actor,
            tier=OpponentTier.ELITE,
        )
        self.assertFalse(result.success)

    def test_invalid_tier(self) -> None:
        result = PreviewOpponentDefaultsAction().run(self.gm_actor, tier="nope")
        self.assertFalse(result.success)

    def test_missing_tier(self) -> None:
        result = PreviewOpponentDefaultsAction().run(self.gm_actor)
        self.assertFalse(result.success)


class GMTriggerDramaticBeatActionTests(GMCombatActionTestBase):
    """GMTriggerDramaticBeatAction (#3387): SENIOR-gated manual dramatic-surge trigger."""

    def setUp(self) -> None:
        super().setUp()
        # is_staff_observer's staff bypass walks .account (the puppeting-account
        # attribute), not the roster-tenure-derived active_account _make_actor_with_account
        # wires up — set it explicitly, mirroring test_gm_adjudication_actions.py's
        # staff_actor fixture.
        self.gm_actor.db_account = self.gm_account
        self.gm_actor.save()

        self.encounter.escalation_curve = EscalationCurveFactory(spike_intensity_amount=4)
        self.encounter.save(update_fields=["escalation_curve"])
        self.participant = self._add_participant()
        begin_engagement(self.player_actor, EngagementType.COMBAT, source=self.encounter)

        self.senior_account = AccountFactory(username="senior_gm")
        GMProfileFactory(account=self.senior_account, level=GMLevel.SENIOR)
        self.senior_actor, _senior_sheet = _make_actor_with_account(
            "senior_gm_actor", self.room, self.senior_account
        )
        SceneParticipationFactory(scene=self.scene, account=self.senior_account, is_gm=True)

        self.junior_account = AccountFactory(username="junior_gm")
        GMProfileFactory(account=self.junior_account, level=GMLevel.JUNIOR)
        self.junior_actor, _junior_sheet = _make_actor_with_account(
            "junior_gm_actor", self.room, self.junior_account
        )
        SceneParticipationFactory(scene=self.scene, account=self.junior_account, is_gm=True)

    def test_senior_gm_triggers_a_surge(self) -> None:
        result = GMTriggerDramaticBeatAction().run(
            self.senior_actor, target=self.player_actor, reason="a costly misstep"
        )
        self.assertTrue(result.success, result.message)
        record = DramaticSurgeRecord.objects.get(
            encounter=self.encounter,
            participant=self.participant,
            trigger_kind=SurgeTriggerKind.GM_MANUAL,
        )
        self.assertEqual(record.reason, "a costly misstep")
        self.assertEqual(record.amount, 4)

    def test_staff_bypasses_the_senior_gate(self) -> None:
        """The GMCombatActionTestBase gm_actor is staff, no GMProfile at all."""
        result = GMTriggerDramaticBeatAction().run(
            self.gm_actor, target=self.player_actor, reason="staff override"
        )
        self.assertTrue(result.success, result.message)

    def test_junior_gm_is_refused(self) -> None:
        result = GMTriggerDramaticBeatAction().run(
            self.junior_actor, target=self.player_actor, reason="not senior enough"
        )
        self.assertFalse(result.success)
        self.assertFalse(
            DramaticSurgeRecord.objects.filter(
                encounter=self.encounter, trigger_kind=SurgeTriggerKind.GM_MANUAL
            ).exists()
        )

    def test_non_gm_is_refused(self) -> None:
        result = GMTriggerDramaticBeatAction().run(
            self.player_actor, target=self.player_actor, reason="self-serving"
        )
        self.assertFalse(result.success)

    def test_missing_reason_is_refused(self) -> None:
        result = GMTriggerDramaticBeatAction().run(self.senior_actor, target=self.player_actor)
        self.assertFalse(result.success)
        self.assertIn("reason", result.message.lower())

    def test_missing_target_is_refused(self) -> None:
        result = GMTriggerDramaticBeatAction().run(self.senior_actor, reason="no target given")
        self.assertFalse(result.success)

    def test_target_not_a_participant_is_refused(self) -> None:
        bystander_account = AccountFactory(username="bystander")
        bystander_actor, _bystander_sheet = _make_actor_with_account(
            "bystander_actor", self.room, bystander_account
        )
        result = GMTriggerDramaticBeatAction().run(
            self.senior_actor, target=bystander_actor, reason="not in the fight"
        )
        self.assertFalse(result.success)

    def test_repeat_trigger_on_same_character_is_a_distinct_refusal(self) -> None:
        first = GMTriggerDramaticBeatAction().run(
            self.senior_actor, target=self.player_actor, reason="first spotlight"
        )
        self.assertTrue(first.success, first.message)
        second = GMTriggerDramaticBeatAction().run(
            self.senior_actor, target=self.player_actor, reason="second spotlight"
        )
        self.assertFalse(second.success)
        self.assertIn("already", second.message.lower())
        self.assertEqual(
            DramaticSurgeRecord.objects.filter(
                encounter=self.encounter, trigger_kind=SurgeTriggerKind.GM_MANUAL
            ).count(),
            1,
        )

    def test_resolves_target_by_character_sheet_shared_pk_not_participant_pk(self) -> None:
        """The spec's explicit trap: character_sheet_id=target.pk, never a participant pk lookup."""
        result = GMTriggerDramaticBeatAction().run(
            self.senior_actor, target=self.player_sheet.character, reason="shared-pk resolution"
        )
        self.assertTrue(result.success, result.message)
        record = DramaticSurgeRecord.objects.get(
            encounter=self.encounter, trigger_kind=SurgeTriggerKind.GM_MANUAL
        )
        self.assertEqual(record.participant_id, self.participant.pk)


class CreateEncounterActionTests(TestCase):
    """CreateEncounterAction starts a new encounter in the actor's active scene (#3388)."""

    def setUp(self) -> None:
        self.room = _make_room("CreateEncounterRoom")

        self.gm_account = AccountFactory(username="createtestgm", is_staff=True)
        self.gm_actor, _ = _make_actor_with_account("create_gm_actor", self.room, self.gm_account)

        self.player_account = AccountFactory(username="createtestplayer")
        self.player_actor, _ = _make_actor_with_account(
            "create_player_actor",
            self.room,
            self.player_account,
        )

        self.scene = SceneFactory(location=self.room, is_active=True)
        SceneParticipationFactory(scene=self.scene, account=self.gm_account, is_gm=True)
        SceneParticipationFactory(scene=self.scene, account=self.player_account, is_gm=False)

    def test_gm_can_create_encounter(self) -> None:
        result = CreateEncounterAction().run(self.gm_actor)
        self.assertTrue(result.success, result.message)
        encounter = CombatEncounter.objects.get(scene=self.scene)
        self.assertEqual(encounter.room_id, self.room.pk)
        self.assertEqual(encounter.pace_mode, PaceMode.TIMED)

    def test_scene_owner_without_gm_flag_allowed(self) -> None:
        """Matches the web create gate: a co-owner may start combat even without is_gm."""
        owner_account = AccountFactory(username="createtestowner")
        SceneParticipationFactory(
            scene=self.scene, account=owner_account, is_owner=True, is_gm=False
        )
        owner_actor, _ = _make_actor_with_account("create_owner_actor", self.room, owner_account)

        result = CreateEncounterAction().run(owner_actor)
        self.assertTrue(result.success, result.message)
        self.assertTrue(CombatEncounter.objects.filter(scene=self.scene).exists())

    def test_non_gm_non_owner_denied(self) -> None:
        result = CreateEncounterAction().run(self.player_actor)
        self.assertFalse(result.success)
        self.assertFalse(CombatEncounter.objects.filter(scene=self.scene).exists())

    def test_no_active_scene_in_room(self) -> None:
        other_room = _make_room("NoSceneRoom")
        self.gm_actor.location = other_room
        result = CreateEncounterAction().run(self.gm_actor)
        self.assertFalse(result.success)
        self.assertIn("no active scene", result.message.lower())

    def test_invalid_pace_mode_creates_nothing(self) -> None:
        result = CreateEncounterAction().run(self.gm_actor, pace_mode="nope")
        self.assertFalse(result.success)
        self.assertFalse(CombatEncounter.objects.filter(scene=self.scene).exists())

    def test_valid_pace_mode_is_set(self) -> None:
        result = CreateEncounterAction().run(self.gm_actor, pace_mode=PaceMode.READY)
        self.assertTrue(result.success, result.message)
        encounter = CombatEncounter.objects.get(scene=self.scene)
        self.assertEqual(encounter.pace_mode, PaceMode.READY)

    def test_lead_gm_may_route_beat_id(self) -> None:
        """The story's own Lead GM may route the new encounter onto their beat (#3559)."""
        story = StoryFactory()
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        beat = BeatFactory(episode=episode, predicate_type=BeatPredicateType.OUTCOME_TIER)
        gm_profile = GMProfileFactory(account=self.gm_account)
        table = GMTableFactory(gm=gm_profile)
        story.primary_table = table
        story.save()

        result = CreateEncounterAction().run(self.gm_actor, beat_id=beat.pk)

        self.assertTrue(result.success, result.message)
        encounter = CombatEncounter.objects.get(scene=self.scene)
        self.assertEqual(encounter.story_beat_id, beat.pk)

    def test_staff_may_route_beat_id_for_any_story(self) -> None:
        story = StoryFactory()
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        beat = BeatFactory(episode=episode, predicate_type=BeatPredicateType.OUTCOME_TIER)

        result = CreateEncounterAction().run(self.gm_actor, beat_id=beat.pk)

        self.assertTrue(result.success, result.message)
        encounter = CombatEncounter.objects.get(scene=self.scene)
        self.assertEqual(encounter.story_beat_id, beat.pk)

    def test_non_lead_gm_denied_beat_id_and_creates_nothing(self) -> None:
        """A GM who isn't this beat's story's Lead GM cannot route onto it."""
        scene_gm_account = AccountFactory(username="createtestscenegm", is_staff=False)
        scene_gm_actor, _ = _make_actor_with_account(
            "create_scene_gm_actor", self.room, scene_gm_account
        )
        SceneParticipationFactory(scene=self.scene, account=scene_gm_account, is_gm=True)

        story = StoryFactory()
        chapter = ChapterFactory(story=story)
        episode = EpisodeFactory(chapter=chapter)
        beat = BeatFactory(episode=episode, predicate_type=BeatPredicateType.OUTCOME_TIER)
        other_account = AccountFactory(username="createtestleadgm", is_staff=False)
        other_gm_profile = GMProfileFactory(account=other_account)
        table = GMTableFactory(gm=other_gm_profile)
        story.primary_table = table
        story.save()

        result = CreateEncounterAction().run(scene_gm_actor, beat_id=beat.pk)

        self.assertFalse(result.success)
        self.assertFalse(CombatEncounter.objects.filter(scene=self.scene).exists())

    def test_malformed_beat_id_rejected(self) -> None:
        result = CreateEncounterAction().run(self.gm_actor, beat_id="")
        self.assertFalse(result.success)
        self.assertFalse(CombatEncounter.objects.filter(scene=self.scene).exists())

    def test_missing_beat_id_rejected(self) -> None:
        result = CreateEncounterAction().run(self.gm_actor, beat_id=999999)
        self.assertFalse(result.success)
        self.assertFalse(CombatEncounter.objects.filter(scene=self.scene).exists())


class RegistryCompletenessSmokeTest(TestCase):
    """New keys are discoverable through the registry."""

    def test_keys_registered(self) -> None:
        for key in (
            "create_encounter",
            "begin_encounter_round",
            "resolve_encounter_round",
            "add_opponent",
            "spawn_creature",
            "add_encounter_participant",
            "remove_encounter_participant",
            "pause_encounter",
            "end_encounter",
            "preview_opponent_defaults",
            "gm_trigger_dramatic_beat",
        ):
            with self.subTest(key=key):
                self.assertIsNotNone(get_action(key), f"{key} not registered")
