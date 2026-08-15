"""Ambient room texture: roaming flavor emits + room-state risk telegraphing (#2988).

Pins: scope-pool precedence (room > area > generic), season/phase gating, per-row cooldown,
the single-axis room-state gate (the whole "risk telegraph" mechanism — no second model),
weighted-selection determinism under a patched RNG, online-occupied-room derivation from live
sessions (never a grid scan), and the scheduler's phase-transition idempotence.

Area-scoped-pool precedence needs a real ``Area``/``AreaClosure`` (Postgres-only materialized
view — ``@tag("postgres")``, see the running-tests skill); every other case here uses a bare
``RoomProfile`` with no ``area``, which never touches that view.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, tag
from django.utils import timezone

from evennia_extensions.factories import AccountFactory, RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.game_clock.constants import Season, TimePhase
from world.game_clock.models import ScheduledTaskRecord
from world.game_clock.task_registry import phase_transitioned_since_last_run
from world.locations.constants import StatKey
from world.locations.factories import LocationValueOverrideFactory
from world.narrative.ambient_texture import (
    AMBIENT_TASK_KEY,
    roll_and_echo_ambient_texture,
    select_ambient_emit,
)
from world.narrative.constants import NarrativeCategory
from world.narrative.factories import AmbientEmitFactory
from world.narrative.models import NarrativeMessage, NarrativeMessageDelivery, UserCategoryMute
from world.narrative.services import set_category_mute


def _room() -> object:
    """A bare RoomProfile's ObjectDB — no Area, so it never touches AreaClosure."""
    return RoomProfileFactory().objectdb


def _online_sheet_in(room: object) -> object:
    """A CharacterSheet whose character sits in ``room`` (for delivery-side tests)."""
    sheet = CharacterSheetFactory()
    sheet.character.location = room
    return sheet


class ScopePoolPrecedenceTests(TestCase):
    """Decision 2: most-specific non-empty scope wins — room > area > generic pool."""

    def test_generic_pool_used_when_no_scoped_row_exists(self) -> None:
        room = _room()
        generic = AmbientEmitFactory()
        result = select_ambient_emit(room, season=Season.SUMMER, phase=TimePhase.DAY)
        assert result == generic

    def test_room_scoped_row_wins_over_generic_pool(self) -> None:
        profile = RoomProfileFactory()
        room = profile.objectdb
        AmbientEmitFactory()  # generic pool row — must be shadowed
        room_row = AmbientEmitFactory(room_profile=profile)
        result = select_ambient_emit(room, season=Season.SUMMER, phase=TimePhase.DAY)
        assert result == room_row

    @tag("postgres")
    def test_area_scoped_row_wins_over_generic_but_loses_to_room(self) -> None:
        area = AreaFactory(level=AreaLevel.WARD)
        profile = RoomProfileFactory(area=area)
        room = profile.objectdb
        AmbientEmitFactory()  # generic pool — shadowed by the area row
        area_row = AmbientEmitFactory(area=area)
        assert select_ambient_emit(room, season=Season.SUMMER, phase=TimePhase.DAY) == area_row

        room_row = AmbientEmitFactory(room_profile=profile)
        assert select_ambient_emit(room, season=Season.SUMMER, phase=TimePhase.DAY) == room_row


class SeasonPhaseGateTests(TestCase):
    def test_row_gated_out_of_its_flagged_season_is_never_selected(self) -> None:
        room = _room()
        AmbientEmitFactory(in_spring=False, in_summer=False, in_autumn=False, in_winter=False)
        assert select_ambient_emit(room, season=Season.SUMMER, phase=TimePhase.DAY) is None

    def test_row_matching_season_and_phase_is_selected(self) -> None:
        room = _room()
        row = AmbientEmitFactory()  # every flag True by factory default
        assert select_ambient_emit(room, season=Season.WINTER, phase=TimePhase.NIGHT) == row

    def test_row_gated_out_of_its_flagged_phase_is_never_selected(self) -> None:
        room = _room()
        AmbientEmitFactory(at_dawn=False, at_day=False, at_dusk=False, at_night=False)
        assert select_ambient_emit(room, season=Season.SUMMER, phase=TimePhase.DAY) is None


class CooldownTests(TestCase):
    def test_row_still_in_cooldown_is_excluded(self) -> None:
        room = _room()
        now = timezone.now()
        AmbientEmitFactory(cooldown_minutes=30, last_fired_at=now - timedelta(minutes=5))
        assert select_ambient_emit(room, season=Season.SUMMER, phase=TimePhase.DAY, now=now) is None

    def test_row_past_cooldown_is_eligible_again(self) -> None:
        room = _room()
        now = timezone.now()
        row = AmbientEmitFactory(cooldown_minutes=30, last_fired_at=now - timedelta(minutes=45))
        assert select_ambient_emit(room, season=Season.SUMMER, phase=TimePhase.DAY, now=now) == row

    def test_never_fired_row_ignores_cooldown(self) -> None:
        room = _room()
        row = AmbientEmitFactory(cooldown_minutes=60, last_fired_at=None)
        assert select_ambient_emit(room, season=Season.SUMMER, phase=TimePhase.DAY) == row


class StateGateTests(TestCase):
    """Decision 3: the single-axis room-state gate — risk telegraphing, no second model."""

    def test_row_below_gate_min_is_excluded(self) -> None:
        profile = RoomProfileFactory()
        room = profile.objectdb
        LocationValueOverrideFactory(
            on_room=True, room_profile=profile, stat_key=StatKey.CRIME, value=10
        )
        AmbientEmitFactory(
            room_profile=profile, gate_stat_key=StatKey.CRIME, gate_min=60, gate_max=None
        )
        assert select_ambient_emit(room, season=Season.SUMMER, phase=TimePhase.DAY) is None

    def test_row_at_or_above_gate_min_is_included(self) -> None:
        profile = RoomProfileFactory()
        room = profile.objectdb
        LocationValueOverrideFactory(
            on_room=True, room_profile=profile, stat_key=StatKey.CRIME, value=60
        )
        row = AmbientEmitFactory(
            room_profile=profile, gate_stat_key=StatKey.CRIME, gate_min=60, gate_max=None
        )
        assert select_ambient_emit(room, season=Season.SUMMER, phase=TimePhase.DAY) == row

    def test_row_above_gate_max_is_excluded(self) -> None:
        profile = RoomProfileFactory()
        room = profile.objectdb
        LocationValueOverrideFactory(
            on_room=True, room_profile=profile, stat_key=StatKey.ORDER, value=90
        )
        AmbientEmitFactory(
            room_profile=profile, gate_stat_key=StatKey.ORDER, gate_min=None, gate_max=20
        )
        assert select_ambient_emit(room, season=Season.SUMMER, phase=TimePhase.DAY) is None

    def test_ungated_row_ignores_room_state_entirely(self) -> None:
        room = _room()
        row = AmbientEmitFactory()  # gate_stat_key="" by default
        assert select_ambient_emit(room, season=Season.SUMMER, phase=TimePhase.DAY) == row


class WeightedSelectionTests(TestCase):
    """Weighted-random pick reuses ``select_weighted`` (deliver_ambient_group's own helper)."""

    @patch("world.checks.outcome_utils.random.choices")  # NOSONAR — patched RNG, not real use
    def test_selection_weights_random_choices_by_row_weight(self, mock_choices) -> None:
        room = _room()
        low = AmbientEmitFactory(weight=1)
        high = AmbientEmitFactory(weight=9)
        mock_choices.return_value = [high]

        result = select_ambient_emit(room, season=Season.SUMMER, phase=TimePhase.DAY)

        assert result == high
        _, kwargs = mock_choices.call_args
        assert set(kwargs["weights"]) == {1, 9}
        called_items = mock_choices.call_args.args[0]
        assert set(called_items) == {low, high}


class PhaseTransitionGuardTests(TestCase):
    """Mirrors weather's #2845 phase-boundary guard against the ambient task's own key.

    The guard function itself never stamps ``ScheduledTaskRecord`` — the scheduler
    (``task_registry.run_due_tasks``) does that AFTER invoking the callable, including on
    no-op runs (see that function's docstring). So these test the guard directly, exactly
    like ``world.weather.tests.test_weather.PhaseAlignedWeatherTickTests``.
    """

    def _stamp(self, ic_dt) -> None:
        record, _ = ScheduledTaskRecord.objects.get_or_create(task_key=AMBIENT_TASK_KEY)
        record.last_ic_run_at = ic_dt
        record.save(update_fields=["last_ic_run_at"])

    def test_first_run_fires(self) -> None:
        from datetime import UTC, datetime

        noon = datetime(2020, 5, 10, 12, 0, tzinfo=UTC)
        with patch("world.game_clock.services.get_ic_now", return_value=noon):
            assert phase_transitioned_since_last_run(AMBIENT_TASK_KEY) is True

    def test_same_phase_noops_boundary_fires(self) -> None:
        from datetime import UTC, datetime

        noon = datetime(2020, 5, 10, 12, 0, tzinfo=UTC)
        one_pm = datetime(2020, 5, 10, 13, 0, tzinfo=UTC)
        night = datetime(2020, 5, 10, 20, 30, tzinfo=UTC)
        self._stamp(noon)
        with patch("world.game_clock.services.get_ic_now", return_value=one_pm):
            assert phase_transitioned_since_last_run(AMBIENT_TASK_KEY) is False
        with patch("world.game_clock.services.get_ic_now", return_value=night):
            assert phase_transitioned_since_last_run(AMBIENT_TASK_KEY) is True


class SchedulerIdempotenceTests(TestCase):
    """Calling the driver twice within one IC phase delivers only once (#2988)."""

    def test_second_call_in_same_phase_delivers_nothing_new(self) -> None:
        from datetime import UTC, datetime

        noon = datetime(2020, 5, 10, 12, 0, tzinfo=UTC)
        room = _room()
        sheet = _online_sheet_in(room)
        AmbientEmitFactory()
        session = SimpleNamespace(puppet=sheet.character)

        with patch("world.game_clock.services.get_ic_now", return_value=noon):
            with patch("evennia.SESSION_HANDLER") as handler:
                handler.get_sessions.return_value = [session]
                roll_and_echo_ambient_texture()  # first-ever run: no stamp yet, fires
        first_count = NarrativeMessage.objects.filter(category=NarrativeCategory.ATMOSPHERE).count()
        assert first_count == 1

        # Mirrors what task_registry.run_due_tasks stamps AFTER a run (including a no-op
        # one) — the callable itself never stamps, so the test stamps on its behalf.
        ScheduledTaskRecord.objects.update_or_create(
            task_key=AMBIENT_TASK_KEY, defaults={"last_ic_run_at": noon}
        )

        with patch("world.game_clock.services.get_ic_now", return_value=noon):
            with patch("evennia.SESSION_HANDLER") as handler:
                handler.get_sessions.return_value = [session]
                roll_and_echo_ambient_texture()  # same DAY phase — must no-op
        second_count = NarrativeMessage.objects.filter(
            category=NarrativeCategory.ATMOSPHERE
        ).count()
        assert second_count == first_count


class OnlineOccupiedRoomDeliveryTests(TestCase):
    """Decision 5: the candidate room set is derived from live sessions, never a room scan."""

    def _fire(self, sessions: list) -> None:
        from datetime import UTC, datetime

        noon = datetime(2020, 5, 10, 12, tzinfo=UTC)
        with patch("world.game_clock.services.get_ic_now", return_value=noon):
            with patch("evennia.SESSION_HANDLER") as handler:
                handler.get_sessions.return_value = sessions
                roll_and_echo_ambient_texture()

    def test_room_with_no_online_occupant_is_never_rolled(self) -> None:
        room = _room()
        AmbientEmitFactory(room_profile=RoomProfileFactory(objectdb=room))
        self._fire(sessions=[])  # nobody online anywhere
        assert not NarrativeMessage.objects.filter(category=NarrativeCategory.ATMOSPHERE).exists()

    def test_puppetless_session_is_skipped_not_a_crash(self) -> None:
        self._fire(sessions=[SimpleNamespace(puppet=None)])
        assert not NarrativeMessage.objects.filter(category=NarrativeCategory.ATMOSPHERE).exists()

    def test_only_session_derived_rooms_are_candidates(self) -> None:
        """A room that exists in the DB but has no session in it gets nothing (no grid scan)."""
        occupied = _room()
        RoomProfileFactory()  # a second, unoccupied room — must never receive an echo
        AmbientEmitFactory()  # generic pool, eligible anywhere
        sheet = _online_sheet_in(occupied)
        self._fire(sessions=[SimpleNamespace(puppet=sheet.character)])

        deliveries = NarrativeMessageDelivery.objects.filter(
            message__category=NarrativeCategory.ATMOSPHERE
        )
        assert deliveries.count() == 1
        assert deliveries.first().recipient_character_sheet_id == sheet.pk

    def test_delivery_reaches_every_online_occupant_of_a_room(self) -> None:
        room = _room()
        sheet_a = _online_sheet_in(room)
        sheet_b = CharacterSheetFactory()
        sheet_b.character.location = room
        AmbientEmitFactory()
        self._fire(
            sessions=[
                SimpleNamespace(puppet=sheet_a.character),
                SimpleNamespace(puppet=sheet_b.character),
            ]
        )
        message = NarrativeMessage.objects.get(category=NarrativeCategory.ATMOSPHERE)
        recipient_ids = set(
            message.deliveries.values_list("recipient_character_sheet_id", flat=True)
        )
        assert recipient_ids == {sheet_a.pk, sheet_b.pk}

    def test_muted_account_still_gets_a_delivery_row(self) -> None:
        """Squelch (#1522 UserCategoryMute) suppresses the live push, never the delivery row."""
        room = _room()
        sheet = _online_sheet_in(room)
        account = AccountFactory()
        sheet.character.db_account = account
        sheet.character.save(update_fields=["db_account"])
        set_category_mute(account=account, category=NarrativeCategory.ATMOSPHERE, muted=True)
        AmbientEmitFactory()

        self._fire(sessions=[SimpleNamespace(puppet=sheet.character)])

        assert UserCategoryMute.objects.filter(
            account=account, category=NarrativeCategory.ATMOSPHERE
        ).exists()
        assert NarrativeMessageDelivery.objects.filter(
            message__category=NarrativeCategory.ATMOSPHERE,
            recipient_character_sheet=sheet,
        ).exists()
