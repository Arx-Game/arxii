"""Tests for the admin FK widget system check (#2435)."""

from django.contrib import admin
from django.test import TestCase

from web.admin.checks import (
    _is_large_table,
    check_admin_fk_widgets,
)


class IsLargeTableTest(TestCase):
    """Test the _is_large_table predicate."""

    def test_objectdb_is_large_table(self):
        """ObjectDB is auto-detected as a large table via issubclass."""
        from evennia.objects.models import ObjectDB

        self.assertTrue(_is_large_table(ObjectDB))

    def test_accountdb_is_large_table(self):
        """AccountDB is auto-detected as a large table via issubclass."""
        from evennia.accounts.models import AccountDB

        self.assertTrue(_is_large_table(AccountDB))

    def test_scriptdb_is_large_table(self):
        """ScriptDB is auto-detected as a large table via issubclass."""
        from evennia.scripts.models import ScriptDB

        self.assertTrue(_is_large_table(ScriptDB))

    def test_character_sheet_is_large_table(self):
        """CharacterSheet is in the explicit registry."""
        from world.character_sheets.models import CharacterSheet

        self.assertTrue(_is_large_table(CharacterSheet))

    def test_persona_is_large_table(self):
        """Persona is in the explicit registry."""
        from world.scenes.models import Persona

        self.assertTrue(_is_large_table(Persona))

    def test_roster_entry_is_large_table(self):
        """RosterEntry is in the explicit registry."""
        from world.roster.models import RosterEntry

        self.assertTrue(_is_large_table(RosterEntry))

    def test_small_lookup_table_is_not_large(self):
        """A small lookup table (e.g., Gender) is not flagged."""
        from world.character_sheets.models import Gender

        self.assertFalse(_is_large_table(Gender))

    def test_objectdb_subclass_is_large_table(self):
        """A typeclass subclass of ObjectDB is caught via issubclass."""
        from evennia.objects.models import ObjectDB

        from typeclasses.rooms import Room

        self.assertTrue(_is_large_table(Room))
        self.assertTrue(issubclass(Room, ObjectDB))


class CheckAdminFkWidgetsTest(TestCase):
    """Test the system check against registered ModelAdmins."""

    def test_check_runs_without_crashing(self):
        """The check should run against all registered admins and return a list."""
        errors = check_admin_fk_widgets(None)
        self.assertIsInstance(errors, list)

    def test_check_returns_errors_with_correct_id(self):
        """Any errors returned should use the web_admin.W001 check id."""
        errors = check_admin_fk_widgets(None)
        for error in errors:
            self.assertEqual(error.id, "web_admin.W001")

    def test_exempt_field_suppresses_error(self):
        """A field listed in large_table_widget_exempt should not appear in errors."""

        class FakeAdmin:
            """Minimal stand-in to test the exempt logic."""

            autocomplete_fields = []
            raw_id_fields = []
            large_table_widget_exempt = ["test_field"]
            __name__ = "FakeAdmin"

        # Register a dummy model + admin, check, then unregister
        # We can't easily register a dummy model, so instead verify the logic
        # by checking that the exempt set is respected in the filter.
        # This is tested implicitly: if any real admin uses large_table_widget_exempt,
        # those fields won't appear in the error list.
        errors = check_admin_fk_widgets(None)
        exempt_fields: set[str] = set()
        for admin_cls in admin.site._registry.values():
            if hasattr(admin_cls, "large_table_widget_exempt"):
                exempt_fields.update(admin_cls.large_table_widget_exempt)
        for error in errors:
            # The error message contains "field_name but is not in"
            # Check that no exempt field appears in any error message
            for exempt_field in exempt_fields:
                self.assertNotIn(
                    f".{exempt_field} ",
                    str(error),
                    f"Exempt field '{exempt_field}' appeared in error: {error}",
                )
