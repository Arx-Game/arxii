"""Tests for battle disconnect-pause service functions (#1899).

Covers: maybe_pause_battle_for_disconnect and its large-scale exception.
"""

from django.test import TestCase

from world.battles.constants import (
    LARGE_SCALE_BATTLE_PARTICIPANT_THRESHOLD,
    BattleParticipantStatus,
)
from world.battles.factories import BattleFactory, BattleParticipantFactory, BattleSideFactory
from world.character_sheets.factories import CharacterSheetFactory


class MaybePauseBattleForDisconnectTests(TestCase):
    def test_pauses_small_battle(self) -> None:
        from world.battles.services import maybe_pause_battle_for_disconnect

        battle = BattleFactory()
        side = BattleSideFactory(battle=battle)
        sheet = CharacterSheetFactory()
        BattleParticipantFactory(
            battle=battle, side=side, character_sheet=sheet, status=BattleParticipantStatus.ACTIVE
        )

        maybe_pause_battle_for_disconnect(sheet)

        battle.refresh_from_db()
        assert battle.is_paused is True

    def test_no_active_participant_is_a_noop(self) -> None:
        from world.battles.services import maybe_pause_battle_for_disconnect

        sheet = CharacterSheetFactory()
        maybe_pause_battle_for_disconnect(sheet)  # No BattleParticipant row — must not raise.

    def test_concluded_battle_is_not_paused(self) -> None:
        from django.utils import timezone

        from world.battles.services import maybe_pause_battle_for_disconnect

        battle = BattleFactory(concluded_at=timezone.now())
        side = BattleSideFactory(battle=battle)
        sheet = CharacterSheetFactory()
        BattleParticipantFactory(
            battle=battle, side=side, character_sheet=sheet, status=BattleParticipantStatus.ACTIVE
        )

        maybe_pause_battle_for_disconnect(sheet)

        battle.refresh_from_db()
        assert battle.is_paused is False

    def test_large_scale_battle_not_mid_crossing_is_not_paused(self) -> None:
        from world.battles.services import maybe_pause_battle_for_disconnect

        battle = BattleFactory()
        side = BattleSideFactory(battle=battle)
        disconnecting_sheet = CharacterSheetFactory()
        BattleParticipantFactory(
            battle=battle,
            side=side,
            character_sheet=disconnecting_sheet,
            status=BattleParticipantStatus.ACTIVE,
        )
        # Fill up to the large-scale threshold with other ACTIVE participants.
        for _ in range(LARGE_SCALE_BATTLE_PARTICIPANT_THRESHOLD - 1):
            BattleParticipantFactory(
                battle=battle,
                side=side,
                character_sheet=CharacterSheetFactory(),
                status=BattleParticipantStatus.ACTIVE,
            )

        maybe_pause_battle_for_disconnect(disconnecting_sheet)

        battle.refresh_from_db()
        assert battle.is_paused is False

    def test_large_scale_battle_mid_crossing_is_paused_anyway(self) -> None:
        from world.battles.services import maybe_pause_battle_for_disconnect
        from world.magic.factories import wire_audere_power_multipliers
        from world.magic.tests.majora_fixtures import build_crossing_world

        wire_audere_power_multipliers()
        (_character, disconnecting_sheet, _threshold, _prospect, _puissant, _offer) = (
            build_crossing_world(5, "_battlepause")
        )
        battle = BattleFactory()
        side = BattleSideFactory(battle=battle)
        BattleParticipantFactory(
            battle=battle,
            side=side,
            character_sheet=disconnecting_sheet,
            status=BattleParticipantStatus.ACTIVE,
        )
        for _ in range(LARGE_SCALE_BATTLE_PARTICIPANT_THRESHOLD - 1):
            BattleParticipantFactory(
                battle=battle,
                side=side,
                character_sheet=CharacterSheetFactory(),
                status=BattleParticipantStatus.ACTIVE,
            )

        maybe_pause_battle_for_disconnect(disconnecting_sheet)

        battle.refresh_from_db()
        assert battle.is_paused is True
