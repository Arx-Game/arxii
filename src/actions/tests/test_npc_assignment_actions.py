"""Tests for NPC guard assignment actions (#2178)."""

from django.test import TestCase

from actions.registry import get_action


class AssignmentActionRegistryTests(TestCase):
    def test_assign_guard_action_registered(self):
        assert get_action("assign_guard") is not None

    def test_unassign_guard_action_registered(self):
        assert get_action("unassign_guard") is not None

    def test_list_guard_assignments_action_registered(self):
        assert get_action("list_guard_assignments") is not None
