"""Tests for GM combat-encounter lifecycle actions (#1494)."""

from __future__ import annotations

from django.test import TestCase

from actions.definitions.gm_combat import (
    AddEncounterParticipantAction,
    AddOpponentAction,
    BeginEncounterRoundAction,
    EndEncounterAction,
    PauseEncounterAction,
    PreviewOpponentDefaultsAction,
    RemoveEncounterParticipantAction,
    ResolveEncounterRoundAction,
)
from actions.registry import get_action
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    EncounterOutcome,
    OpponentTier,
    ParticipantStatus,
    RiskLevel,
    StakesLevel,
)
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolFactory,
    seed_scaling_defaults,
)
from world.combat.models import CombatOpponent, CombatParticipant
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneFactory, SceneParticipationFactory


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


class RegistryCompletenessSmokeTest(TestCase):
    """New keys are discoverable through the registry."""

    def test_keys_registered(self) -> None:
        for key in (
            "begin_encounter_round",
            "resolve_encounter_round",
            "add_opponent",
            "add_encounter_participant",
            "remove_encounter_participant",
            "pause_encounter",
            "end_encounter",
            "preview_opponent_defaults",
        ):
            with self.subTest(key=key):
                self.assertIsNotNone(get_action(key), f"{key} not registered")
