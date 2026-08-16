"""Tests for evennia_extensions.typeclass_hook_guard (issue #3195)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase


class NoopHookTests(TestCase):
    """The generated no-op stub logs a warning and behaves like a real pass-bodied hook."""

    def test_noop_logs_warning_with_class_attr_and_pk(self) -> None:
        from evennia_extensions.typeclass_hook_guard import _make_noop_hook

        stub = _make_noop_hook("AccountDB", "at_server_reload")

        class _FakeBareInstance:
            pk = 42

        with patch("evennia_extensions.typeclass_hook_guard.logger") as mock_logger:
            result = stub(_FakeBareInstance())

        self.assertIsNone(result)
        mock_logger.log_warn.assert_called_once()
        message = mock_logger.log_warn.call_args[0][0]
        self.assertIn("AccountDB", message)
        self.assertIn("at_server_reload", message)
        self.assertIn("42", message)
        self.assertIn("3195", message)

    def test_noop_accepts_and_ignores_call_arguments(self) -> None:
        """Matches upstream's pass-bodied hooks: any call signature is accepted."""
        from evennia_extensions.typeclass_hook_guard import _make_noop_hook

        stub = _make_noop_hook("ScriptDB", "_pause_task")

        class _FakeBareInstance:
            pk = 7

        with patch("evennia_extensions.typeclass_hook_guard.logger"):
            result = stub(_FakeBareInstance(), auto_pause=True)

        self.assertIsNone(result)


class InstallLifecycleHookGuardsTests(TestCase):
    """install_lifecycle_hook_guards() patches only genuinely missing hooks."""

    def test_bare_classes_get_every_hook_the_shutdown_path_calls(self) -> None:
        """After the guard, every hook evennia/server/service.py's shutdown() calls exists.

        AppConfig.ready() already installed the guard for this process before any test
        runs, so this asserts the steady-state postcondition rather than a before/after
        transition.
        """
        import evennia

        from evennia_extensions.typeclass_hook_guard import install_lifecycle_hook_guards

        install_lifecycle_hook_guards()

        self.assertTrue(hasattr(evennia.ObjectDB, "at_server_reload"))
        self.assertTrue(hasattr(evennia.ObjectDB, "at_server_shutdown"))
        self.assertTrue(hasattr(evennia.AccountDB, "at_server_reload"))
        self.assertTrue(hasattr(evennia.AccountDB, "at_server_shutdown"))
        self.assertTrue(hasattr(evennia.AccountDB, "unpuppet_all"))
        self.assertTrue(hasattr(evennia.ScriptDB, "at_server_reload"))
        self.assertTrue(hasattr(evennia.ScriptDB, "at_server_shutdown"))
        self.assertTrue(hasattr(evennia.ScriptDB, "_pause_task"))

    def test_bare_accountdb_hook_is_the_installed_guard_stub(self) -> None:
        """AccountDB itself has no at_server_reload upstream (issue #3195) -- confirm
        the attribute the guard adds lives directly on the bare class, not inherited
        from a typeclass, and that calling it warns instead of raising."""
        import evennia

        from evennia_extensions.typeclass_hook_guard import install_lifecycle_hook_guards

        install_lifecycle_hook_guards()

        stub = evennia.AccountDB.__dict__["at_server_reload"]

        class _FakeBareAccount:
            pk = 99

        with patch("evennia_extensions.typeclass_hook_guard.logger") as mock_logger:
            stub(_FakeBareAccount())

        mock_logger.log_warn.assert_called_once()

    def test_typeclassed_hook_is_never_overridden(self) -> None:
        """A typeclass's own hook is untouched: the guard only patches the bare class,
        and MRO means a typeclassed instance never falls through to the stub."""
        from evennia.accounts.accounts import DefaultAccount

        from evennia_extensions.typeclass_hook_guard import install_lifecycle_hook_guards

        original = DefaultAccount.__dict__["at_server_reload"]

        install_lifecycle_hook_guards()

        self.assertIs(DefaultAccount.__dict__["at_server_reload"], original)

    def test_install_is_idempotent(self) -> None:
        """Calling install twice does not replace an already-installed stub."""
        import evennia

        from evennia_extensions.typeclass_hook_guard import install_lifecycle_hook_guards

        install_lifecycle_hook_guards()
        first_stub = evennia.AccountDB.__dict__["at_server_reload"]

        install_lifecycle_hook_guards()
        second_stub = evennia.AccountDB.__dict__["at_server_reload"]

        self.assertIs(first_stub, second_stub)

    def test_script_is_active_is_not_guarded(self) -> None:
        """is_active is a model-field property on bare ScriptDB, not a typeclass hook,
        so the guard must not replace it with a stub."""
        import evennia

        from evennia_extensions.typeclass_hook_guard import install_lifecycle_hook_guards

        install_lifecycle_hook_guards()

        # is_active is always present (the idmapper metaclass generates it as a
        # property wrapper around db_is_active at class-definition time), and
        # the guard must leave it exactly that: a property, never a guard stub.
        self.assertIsInstance(evennia.ScriptDB.__dict__["is_active"], property)
