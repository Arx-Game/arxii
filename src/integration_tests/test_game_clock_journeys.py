"""Journeys: staff run the game clock (#5248).

A staff account pauses the clock, sets the date while it stands still, and resumes it,
and the world carries on from exactly the date set: the real time the clock sat paused
is never counted. A jump of the date asks one thing, whether characters age with the
calendar or keep their ages. Either way a character in their dying days keeps the days
they had left and an event still to come moves with the calendar; a change to an earlier
date always keeps ages, and the aging tasks carry on from the new date.

Every step goes through ``/api/clock/``, the seam the staff hub's Game clock page uses.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from django.utils import timezone

from evennia_extensions.factories import AccountFactory, CharacterFactory
from integration_tests.harness import JourneyCase
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import Heritage
from world.events.constants import EventStatus
from world.events.factories import EventFactory
from world.game_clock.factories import GameClockFactory
from world.game_clock.models import GameClock, GameClockHistory, ScheduledTaskRecord
from world.game_clock.services import get_ic_now
from world.game_clock.tasks import aging_birthday_tick_task
from world.species.factories import SpeciesFactory
from world.vitals.aging import run_death_sweep
from world.vitals.constants import CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory

BIRTHDAY_TASK = "aging.birthday_tick"
#: Real seconds a test may take between two reads of a running clock, in IC terms.
SLACK = timedelta(minutes=5)


def _ic(year: int, month: int = 1, day: int = 1, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)


def _iso(moment: datetime) -> str:
    """ISO text with a four-digit year (``strftime`` does not pad a year under 1000)."""
    return (
        f"{moment.year:04d}-{moment.month:02d}-{moment.day:02d}"
        f"T{moment.hour:02d}:{moment.minute:02d}:{moment.second:02d}Z"
    )


class StaffRunTheGameClock(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self.staff = AccountFactory(is_staff=True)
        self.client = self.api(self.staff)

    # -- helpers ---------------------------------------------------------

    def _clock(self, ic_time: datetime, **kwargs: object) -> GameClock:
        return GameClockFactory(anchor_ic_time=ic_time, **kwargs)

    def _state(self) -> dict:
        response = self.client.get("/api/clock/")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def _set_date(self, ic_time: datetime, age_handling: str, reason: str = "A test") -> object:
        return self.client.post(
            "/api/clock/adjust/",
            {"ic_datetime": _iso(ic_time), "reason": reason, "age_handling": age_handling},
            format="json",
        )

    def _character(self, *, born: int) -> object:
        """A mortal whose birthday is the 12th of Vowing, with a birth year."""
        sheet = CharacterSheetFactory(
            character=CharacterFactory(),
            birthday_month=6,
            birthday_day=12,
            matured_years=24,
            withered_years=0,
            ic_birth_year=born,
        )
        sheet.species = SpeciesFactory(name=f"Mortal (clock journey {sheet.pk})")
        sheet.save()
        return sheet

    def _stamp_birthday_task(self, ic_time: datetime) -> ScheduledTaskRecord:
        record, _ = ScheduledTaskRecord.objects.get_or_create(task_key=BIRTHDAY_TASK)
        record.last_ic_run_at = ic_time
        record.save(update_fields=["last_ic_run_at"])
        return record

    # -- pause, set, resume ----------------------------------------------

    def test_resume_counts_none_of_the_time_spent_paused(self) -> None:
        """A clock that sat paused for a week carries on from the date it showed."""
        self._clock(_ic(1000), paused=True, anchor_real_time=timezone.now() - timedelta(days=7))

        response = self.client.post("/api/clock/unpause/")

        self.assertEqual(response.status_code, 200, response.content)
        state = self._state()
        self.assertFalse(state["paused"])
        self.assertEqual(
            (state["year"], state["month"], state["day"], state["hour"]), (1000, 1, 1, 0)
        )
        self.assertLess(get_ic_now() - _ic(1000), SLACK)

    def test_staff_pause_set_the_date_and_resume_from_it(self) -> None:
        """Paused, the clock takes a new date and stays paused; resume starts there."""
        self._clock(_ic(1000, 3, 9))

        self.assertEqual(self.client.post("/api/clock/pause/").status_code, 200)
        self.assertTrue(self._state()["paused"])

        response = self._set_date(_ic(1000, 3, 15), "kept", reason="Opening day is in spring")
        self.assertEqual(response.status_code, 200, response.content)
        state = self._state()
        self.assertTrue(state["paused"], "setting the date must not start the clock")
        self.assertEqual(state["date_display"], "the 15th of the Month of Thawing, Year 1000")

        self.assertEqual(self.client.post("/api/clock/unpause/").status_code, 200)
        state = self._state()
        self.assertFalse(state["paused"])
        self.assertEqual(state["date_display"], "the 15th of the Month of Thawing, Year 1000")

        history = self.client.get("/api/clock/history/").json()["results"]
        self.assertEqual([row["change"] for row in history], ["resumed", "date_kept", "paused"])
        self.assertEqual(history[1]["reason"], "Opening day is in spring")
        self.assertEqual((history[0]["reason"], history[2]["reason"]), ("", ""))
        self.assertEqual(history[1]["changed_by_name"], self.staff.username)
        self.assertEqual(
            history[1]["new_date_display"], "the 15th of the Month of Thawing, Year 1000"
        )

    def test_the_clock_read_carries_the_speed_and_the_month_names(self) -> None:
        self._clock(_ic(1000))
        state = self._state()
        self.assertEqual(state["time_ratio"], 3.0)
        self.assertEqual(len(state["month_names"]), 12)
        self.assertEqual(
            (state["month_names"][0], state["month_names"][11]), ("Dreaming", "Ending")
        )

    def test_changing_the_speed_does_not_move_the_date(self) -> None:
        self._clock(_ic(1000, 3, 9))
        response = self.client.post(
            "/api/clock/ratio/", {"ratio": 1.0, "reason": "A slow weekend"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        state = self._state()
        self.assertEqual(state["time_ratio"], 1.0)
        self.assertEqual((state["year"], state["month"], state["day"]), (1000, 3, 9))
        row = self.client.get("/api/clock/history/").json()["results"][0]
        self.assertEqual(row["change"], "speed")

    # -- a jump of the date ----------------------------------------------

    def test_a_jump_forward_with_characters_aging(self) -> None:
        """Twenty years on, a thirty-year-old is fifty and has matured twenty years."""
        self._clock(_ic(1000))
        sheet = self._character(born=970)
        record = self._stamp_birthday_task(_ic(1000))
        self.assertEqual(sheet.chronological_age, 30)

        response = self._set_date(_ic(1020), "aged")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(sheet.ic_birth_year, 970, "aging leaves the birth year alone")
        self.assertEqual(sheet.chronological_age, 50)
        self.assertEqual(record.last_ic_run_at, _ic(1000), "the gap is the birthday task's to walk")
        aging_birthday_tick_task()
        self.assertEqual(sheet.matured_years, 44)
        row = GameClockHistory.objects.latest("pk")
        self.assertEqual((row.change, row.birth_year_shift), ("date_aged", 0))

    def test_a_jump_forward_with_characters_keeping_their_ages(self) -> None:
        """Twenty years on, a thirty-year-old is still thirty and has not matured."""
        self._clock(_ic(1000))
        sheet = self._character(born=970)
        record = self._stamp_birthday_task(_ic(1000))

        response = self._set_date(_ic(1020), "kept")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(sheet.ic_birth_year, 990)
        self.assertEqual(sheet.chronological_age, 30)
        self.assertEqual(record.last_ic_run_at, _ic(1020))
        aging_birthday_tick_task()
        self.assertEqual(sheet.matured_years, 24, "nobody ages through a jump that kept ages")
        row = GameClockHistory.objects.latest("pk")
        self.assertEqual((row.change, row.birth_year_shift), ("date_kept", 20))
        # The database agrees with the cached rows the tasks read.
        self.assertEqual(
            type(sheet).objects.filter(pk=sheet.pk).values_list("ic_birth_year", flat=True)[0], 990
        )

    def test_a_change_to_an_earlier_date_keeps_ages_and_the_aging_tasks_carry_on(self) -> None:
        """Set back twenty years: ages hold, and the aging tasks are not left waiting
        for the calendar to reach the old date again."""
        self._clock(_ic(1020, 6, 1))
        sheet = self._character(born=990)
        record = self._stamp_birthday_task(_ic(1020, 6, 1))

        response = self._set_date(_ic(1000, 6, 1), "kept", reason="The year was entered wrong")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            record.last_ic_run_at,
            _ic(1000, 6, 1),
            "a stamp left in Year 1020 keeps the aging tasks idle for twenty game years",
        )
        self.assertEqual(sheet.ic_birth_year, 970)
        self.assertEqual(sheet.chronological_age, 30)

    def test_a_change_to_an_earlier_date_cannot_age_characters(self) -> None:
        self._clock(_ic(1020, 6, 1))
        sheet = self._character(born=990)

        response = self._set_date(_ic(1000, 6, 1), "aged")

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(
            response.json()["detail"], "A change to an earlier date keeps characters' ages."
        )
        self.assertEqual(self._state()["year"], 1020)
        self.assertEqual(sheet.ic_birth_year, 990)
        self.assertFalse(GameClockHistory.objects.exists())

    def test_a_jump_never_ends_a_dying_window(self) -> None:
        """Ten days from death before the jump is ten days from death after it."""
        self._clock(_ic(1000), paused=True)
        vitals = CharacterVitalsFactory(
            character_sheet=self._character(born=930),
            aging_death_ic_deadline=_ic(1000) + timedelta(days=10),
        )

        response = self._set_date(_ic(1020), "aged")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(vitals.aging_death_ic_deadline, _ic(1020) + timedelta(days=10))
        self.assertEqual(run_death_sweep(ic_now=get_ic_now()), 0)
        self.assertEqual(vitals.life_state, CharacterLifeState.ALIVE)

    def test_an_event_still_to_come_moves_with_the_calendar(self) -> None:
        self._clock(_ic(1000), paused=True)
        coming = EventFactory(
            status=EventStatus.SCHEDULED,
            scheduled_real_time=timezone.now() + timedelta(days=7),
            scheduled_ic_time=_ic(1000, 1, 22),
        )
        ended = EventFactory(
            status=EventStatus.COMPLETED,
            scheduled_real_time=timezone.now() - timedelta(days=7),
            scheduled_ic_time=_ic(999, 12, 10),
        )

        response = self._set_date(_ic(1020), "kept")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(coming.scheduled_ic_time, _ic(1020, 1, 22))
        self.assertEqual(ended.scheduled_ic_time, _ic(999, 12, 10), "the past keeps its date")

    def test_a_jump_inside_one_year_keeping_ages_skips_the_birthdays_between(self) -> None:
        """Three months later, ages kept: no birth year moves and nobody has the birthday
        that fell in between."""
        self._clock(_ic(1000, 4, 1), paused=True)
        sheet = self._character(born=970)  # birthday the 12th of Vowing
        record = self._stamp_birthday_task(_ic(1000, 4, 1))

        response = self._set_date(_ic(1000, 8, 1), "kept")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(sheet.ic_birth_year, 970)
        self.assertEqual(record.last_ic_run_at, _ic(1000, 8, 1))
        aging_birthday_tick_task()
        self.assertEqual(sheet.matured_years, 24)
        row = GameClockHistory.objects.latest("pk")
        self.assertEqual((row.change, row.birth_year_shift), ("date_kept", 0))

    def test_the_same_jump_with_characters_aging_gives_the_birthday(self) -> None:
        self._clock(_ic(1000, 4, 1), paused=True)
        sheet = self._character(born=970)
        self._stamp_birthday_task(_ic(1000, 4, 1))

        self.assertEqual(self._set_date(_ic(1000, 8, 1), "aged").status_code, 200)

        aging_birthday_tick_task()
        self.assertEqual(sheet.matured_years, 25)
        self.assertEqual(sheet.chronological_age, 30, "the calendar year did not change")

    def test_keeping_ages_moves_every_tasks_stamp_and_aging_leaves_them(self) -> None:
        self._clock(_ic(1000), paused=True)
        birthday = self._stamp_birthday_task(_ic(1000))
        weather = ScheduledTaskRecord.objects.create(
            task_key="weather.roll", last_ic_run_at=_ic(999, 12, 31)
        )
        never_ran = ScheduledTaskRecord.objects.create(task_key="aging.decline_check")

        self.assertEqual(self._set_date(_ic(1010), "aged").status_code, 200)
        self.assertEqual(
            (birthday.last_ic_run_at, weather.last_ic_run_at), (_ic(1000), _ic(999, 12, 31))
        )
        self.assertEqual(
            never_ran.last_ic_run_at,
            _ic(1000),
            "a task that never ran starts from where the jump began, so it walks the gap",
        )

        self.assertEqual(self._set_date(_ic(1020), "kept").status_code, 200)
        self.assertEqual(
            (birthday.last_ic_run_at, weather.last_ic_run_at, never_ran.last_ic_run_at),
            (_ic(1020), _ic(1020), _ic(1020)),
        )

    def test_a_dying_window_follows_a_change_to_an_earlier_date(self) -> None:
        self._clock(_ic(1020), paused=True)
        vitals = CharacterVitalsFactory(
            character_sheet=self._character(born=950),
            aging_death_ic_deadline=_ic(1020) + timedelta(days=10),
        )

        self.assertEqual(self._set_date(_ic(1000), "kept").status_code, 200)

        self.assertEqual(vitals.aging_death_ic_deadline, _ic(1000) + timedelta(days=10))
        self.assertEqual(run_death_sweep(ic_now=get_ic_now()), 0)

    def test_a_character_with_no_birth_year_and_an_event_under_way_are_left_alone(self) -> None:
        self._clock(_ic(1000), paused=True)
        sleeper = CharacterSheetFactory(character=CharacterFactory(), ic_birth_year=None)
        draft = EventFactory(
            status=EventStatus.DRAFT,
            scheduled_real_time=timezone.now() + timedelta(days=3),
            scheduled_ic_time=_ic(1000, 1, 10),
        )
        under_way = EventFactory(
            status=EventStatus.ACTIVE,
            scheduled_real_time=timezone.now() + timedelta(hours=1),
            scheduled_ic_time=_ic(1000, 1, 1),
        )

        self.assertEqual(self._set_date(_ic(1020), "kept").status_code, 200)

        self.assertIsNone(sleeper.ic_birth_year)
        self.assertEqual(draft.scheduled_ic_time, _ic(1020, 1, 10))
        self.assertEqual(under_way.scheduled_ic_time, _ic(1000, 1, 1))

    def test_a_date_something_cannot_follow_is_refused_and_nothing_changes(self) -> None:
        """An event dated near the calendar's end cannot move twenty years on. The whole
        change is refused, and the clock, the character and the event are as they were."""
        clock = self._clock(_ic(1000), paused=True)
        sheet = self._character(born=970)
        record = self._stamp_birthday_task(_ic(1000))
        far = EventFactory(
            status=EventStatus.SCHEDULED,
            scheduled_real_time=timezone.now() + timedelta(days=7),
            scheduled_ic_time=_ic(9990),
        )

        response = self._set_date(_ic(1020), "kept")

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(
            response.json()["detail"],
            "That date is too far away: something already dated cannot follow the jump.",
        )
        self.assertEqual(clock.anchor_ic_time, _ic(1000))
        self.assertEqual(self._state()["year"], 1000)
        self.assertEqual(sheet.ic_birth_year, 970)
        self.assertEqual(record.last_ic_run_at, _ic(1000))
        self.assertEqual(far.scheduled_ic_time, _ic(9990))
        self.assertFalse(GameClockHistory.objects.exists())

    def test_the_history_can_be_narrowed_to_one_kind(self) -> None:
        self._clock(_ic(1000))
        self.client.post("/api/clock/pause/")
        self.client.post("/api/clock/unpause/")
        self.client.post("/api/clock/pause/")

        paused = self.client.get("/api/clock/history/", {"change": "paused"}).json()
        everything = self.client.get("/api/clock/history/").json()

        self.assertEqual(paused["count"], 2)
        self.assertEqual({row["change"] for row in paused["results"]}, {"paused"})
        self.assertEqual(everything["count"], 3)

    # -- the preview ------------------------------------------------------

    def test_the_preview_says_what_a_change_would_do_and_writes_nothing(self) -> None:
        self._clock(_ic(1000, 5, 4), paused=True)
        self._character(born=970)
        EventFactory(
            status=EventStatus.SCHEDULED, scheduled_real_time=timezone.now() + timedelta(days=7)
        )
        Heritage.objects.create(name="Misbegotten", first_appeared_ic=date(980, 1, 1))
        Heritage.objects.create(name="Normal")

        response = self.client.get("/api/clock/adjust-preview/", {"ic_datetime": _iso(_ic(950))})

        self.assertEqual(response.status_code, 200, response.content)
        preview = response.json()
        self.assertEqual(preview["direction"], "back")
        self.assertEqual(preview["year_shift"], -50)
        self.assertEqual(preview["characters_with_birth_year"], 1)
        self.assertEqual(preview["upcoming_events"], 1)
        self.assertEqual(preview["heritages_not_yet_appeared"], ["Misbegotten"])
        self.assertEqual(
            preview["current_date_display"], "the 4th of the Month of Rising, Year 1000"
        )
        self.assertEqual(self._state()["year"], 1000)
        self.assertFalse(GameClockHistory.objects.exists())

    # -- who may ----------------------------------------------------------

    def test_a_player_cannot_read_the_history_or_the_preview_or_move_the_clock(self) -> None:
        self._clock(_ic(1000))
        player = self.api(AccountFactory())

        self.assertEqual(player.get("/api/clock/history/").status_code, 403)
        self.assertEqual(
            player.get("/api/clock/adjust-preview/", {"ic_datetime": _iso(_ic(1020))}).status_code,
            403,
        )
        moved = player.post(
            "/api/clock/adjust/",
            {"ic_datetime": _iso(_ic(1020)), "reason": "x", "age_handling": "kept"},
            format="json",
        )
        self.assertEqual(moved.status_code, 403)
        self.assertEqual(self._state()["year"], 1000)
