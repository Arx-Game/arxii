"""Tests for the GameTickScript."""

from unittest.mock import MagicMock, create_autospec, patch

from django.test import TestCase
from twisted.internet.task import LoopingCall


class GameTickRepeatTests(TestCase):
    @patch("world.game_clock.scripts.run_due_tasks")
    @patch("world.game_clock.scripts.get_ic_now")
    @patch("world.game_clock.scripts.close_old_connections")
    def test_at_repeat_heals_connections_before_any_query(
        self, mock_close: MagicMock, mock_ic_now: MagicMock, mock_run: MagicMock
    ) -> None:
        """close_old_connections runs FIRST — before get_ic_now's query.

        Ordering is the contract: a dead connection (Postgres restarted under
        the long-lived Server) must be discarded before the tick's first
        query, or the tick raises OperationalError forever (2026-08-23
        reload-wedge incident).
        """
        from world.game_clock.scripts import GameTickScript

        call_order: list[str] = []
        mock_close.side_effect = lambda: call_order.append("close")
        mock_ic_now.side_effect = lambda: call_order.append("ic_now")
        mock_run.return_value = []

        GameTickScript.at_repeat(MagicMock())
        self.assertEqual(call_order[0], "close")
        self.assertIn("ic_now", call_order)


class EnsureGameTickScriptTests(TestCase):
    @patch("world.game_clock.scripts.GameTickScript")
    def test_skips_creation_when_exists(self, mock_gts: MagicMock) -> None:
        """Does not create a new script if one exists."""
        from world.game_clock.scripts import ensure_game_tick_script

        mock_gts.objects.first.return_value = MagicMock()
        ensure_game_tick_script()
        mock_gts.objects.first.assert_called_once()

    @patch("evennia.utils.create.create_script")
    @patch("world.game_clock.scripts.GameTickScript")
    def test_creates_when_not_exists(self, mock_gts: MagicMock, mock_create: MagicMock) -> None:
        """Creates the script if it doesn't exist."""
        from world.game_clock.scripts import ensure_game_tick_script

        mock_gts.objects.first.return_value = None
        ensure_game_tick_script()
        mock_create.assert_called_once()


class EnsureGameTickScriptRearmTests(TestCase):
    """The row existing is not enough: its timer has to be running (#4001).

    Evennia re-arms a persistent script at boot only through
    ``_unpause_task(auto_unpause=True)``, which needs a ``_paused_time`` the
    previous stop stored. A hard kill stores nothing, so the row stays
    ``db_is_active=True`` with no timer across every later boot. Production
    ran that way from the 2026-08-23 SIGKILL recovery until #3993, with the
    tick-level connection heal from #3327 deployed and never ticking.
    """

    def tearDown(self) -> None:
        from world.game_clock.scripts import GameTickScript

        for script in GameTickScript.objects.all():
            script.stop()

    def test_rearms_an_existing_row_whose_timer_is_not_running(self) -> None:
        from evennia.utils.create import create_script

        from world.game_clock.scripts import (
            SCRIPT_KEY,
            TICK_INTERVAL,
            GameTickScript,
            ensure_game_tick_script,
        )

        script = create_script(
            GameTickScript,
            key=SCRIPT_KEY,
            persistent=True,
            interval=TICK_INTERVAL,
            autostart=False,
        )
        self.assertIsNone(script.ndb._task)

        ensure_game_tick_script()

        script = GameTickScript.objects.get(db_key=SCRIPT_KEY)
        self.assertIsNotNone(script.ndb._task)
        self.assertTrue(script.ndb._task.running)

    def test_leaves_a_script_staff_paused_by_hand_paused(self) -> None:
        """A manual pause is a choice, not a lost timer; Evennia's own boot unpause
        (auto_unpause=True) respects it and so does the re-arm."""
        from evennia.utils.create import create_script

        from world.game_clock.scripts import (
            SCRIPT_KEY,
            TICK_INTERVAL,
            GameTickScript,
            ensure_game_tick_script,
        )

        script = create_script(
            GameTickScript, key=SCRIPT_KEY, persistent=True, interval=TICK_INTERVAL
        )
        script.pause()
        self.assertIsNone(script.time_until_next_repeat())

        ensure_game_tick_script()

        self.assertIsNone(GameTickScript.objects.get(db_key=SCRIPT_KEY).time_until_next_repeat())

    def test_boot_order_rearm_then_evennia_unpause_keeps_one_timer(self) -> None:
        """At boot our at_server_start hook runs before Evennia's
        update_scripts_after_server_start (run_init_hooks precedes
        at_post_portal_sync); the second pass must not replace or double the timer."""
        from evennia import ScriptDB
        from evennia.utils.create import create_script

        from world.game_clock.scripts import (
            SCRIPT_KEY,
            TICK_INTERVAL,
            GameTickScript,
            ensure_game_tick_script,
        )

        create_script(
            GameTickScript,
            key=SCRIPT_KEY,
            persistent=True,
            interval=TICK_INTERVAL,
            autostart=False,
        )
        ensure_game_tick_script()
        task = GameTickScript.objects.get(db_key=SCRIPT_KEY).ndb._task
        self.assertTrue(task.running)

        ScriptDB.objects.update_scripts_after_server_start()

        after = GameTickScript.objects.get(db_key=SCRIPT_KEY).ndb._task
        self.assertIs(after, task)
        self.assertTrue(after.running)

    def test_leaves_a_running_timer_alone(self) -> None:
        from evennia.utils.create import create_script

        from world.game_clock.scripts import (
            SCRIPT_KEY,
            TICK_INTERVAL,
            GameTickScript,
            ensure_game_tick_script,
        )

        script = create_script(
            GameTickScript, key=SCRIPT_KEY, persistent=True, interval=TICK_INTERVAL
        )
        task = script.ndb._task
        self.assertTrue(task.running)

        ensure_game_tick_script()

        self.assertIs(GameTickScript.objects.get(db_key=SCRIPT_KEY).ndb._task, task)


class MaintenanceLoopRearmTests(TestCase):
    """The tick re-arms Evennia's maintenance loop when it has died (#4001).

    That LoopingCall stops for good when its own database call raises (a
    Postgres restart under the Server does exactly that), and it is what
    saves runtime, processes idle timeouts and closes the connection every
    seven hours. Nothing else restarts it.
    """

    @patch("world.game_clock.scripts.run_due_tasks")
    @patch("world.game_clock.scripts.get_ic_now", MagicMock(return_value=None))
    @patch("world.game_clock.scripts.close_old_connections", MagicMock())
    @patch("world.game_clock.scripts.evennia")
    def test_at_repeat_restarts_a_stopped_maintenance_loop(
        self,
        mock_evennia: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        from world.game_clock.scripts import GameTickScript

        mock_run.return_value = []
        # Autospec so a drift on LoopingCall.start fails here, not in production.
        task = create_autospec(LoopingCall, instance=True)
        task.running = False
        mock_evennia.EVENNIA_SERVER_SERVICE.maintenance_task = task

        GameTickScript.at_repeat(MagicMock())

        task.start.assert_called_once_with(60, now=False)

    @patch("world.game_clock.scripts.run_due_tasks")
    @patch("world.game_clock.scripts.get_ic_now", MagicMock(return_value=None))
    @patch("world.game_clock.scripts.close_old_connections", MagicMock())
    @patch("world.game_clock.scripts.evennia")
    def test_at_repeat_leaves_a_running_maintenance_loop_alone(
        self,
        mock_evennia: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        from world.game_clock.scripts import GameTickScript

        mock_run.return_value = []
        task = create_autospec(LoopingCall, instance=True)
        task.running = True
        mock_evennia.EVENNIA_SERVER_SERVICE.maintenance_task = task

        GameTickScript.at_repeat(MagicMock())

        task.start.assert_not_called()
