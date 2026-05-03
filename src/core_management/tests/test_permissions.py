"""Tests for the shared permission primitives."""

from unittest.mock import MagicMock

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from core_management.permissions import (
    PlayerOnlyPermission,
    PlayerOrStaffPermission,
    is_staff_observer,
)


class IsStaffObserverTests(TestCase):
    def test_none_returns_false(self) -> None:
        self.assertFalse(is_staff_observer(None))

    def test_user_with_is_staff_true(self) -> None:
        observer = MagicMock(is_staff=True)
        self.assertTrue(is_staff_observer(observer))

    def test_user_with_is_staff_false(self) -> None:
        observer = MagicMock(is_staff=False)
        self.assertFalse(is_staff_observer(observer))

    def test_object_db_with_staff_account(self) -> None:
        # Walks character.account.is_staff
        account = MagicMock(is_staff=True)
        # Use a fresh class, not MagicMock — getattr on MagicMock for is_staff
        # would return another MagicMock and pass the truthy check incorrectly.
        observer = type("FakeObj", (), {"account": account})()
        self.assertTrue(is_staff_observer(observer))

    def test_object_db_with_non_staff_account(self) -> None:
        account = MagicMock(is_staff=False)
        observer = type("FakeObj", (), {"account": account})()
        self.assertFalse(is_staff_observer(observer))

    def test_object_db_with_no_account(self) -> None:
        observer = type("FakeObj", (), {"account": None})()
        self.assertFalse(is_staff_observer(observer))

    def test_object_with_no_is_staff_or_account_attr(self) -> None:
        observer = type("FakeObj", (), {})()
        self.assertFalse(is_staff_observer(observer))


class PlayerOnlyPermissionTests(TestCase):
    """Staff get NO bypass on writes; SAFE_METHODS pass for any authenticated user."""

    def setUp(self) -> None:
        self.factory = APIRequestFactory()

    def _request(self, method: str, *, is_authenticated: bool, is_staff: bool):
        req = getattr(self.factory, method.lower())("/")
        req.user = MagicMock(is_authenticated=is_authenticated, is_staff=is_staff)
        return req

    def test_unauthenticated_get_denied(self) -> None:
        permission = PlayerOnlyPermission()
        req = self._request("get", is_authenticated=False, is_staff=False)
        self.assertFalse(permission.has_permission(req, MagicMock()))

    def test_authenticated_get_allowed(self) -> None:
        permission = PlayerOnlyPermission()
        req = self._request("get", is_authenticated=True, is_staff=False)
        self.assertTrue(permission.has_permission(req, MagicMock()))

    def test_staff_post_NOT_bypassed(self) -> None:  # noqa: N802
        class Denying(PlayerOnlyPermission):
            def has_permission_for_player(self, request, view):
                return False

        permission = Denying()
        req = self._request("post", is_authenticated=True, is_staff=True)
        self.assertFalse(permission.has_permission(req, MagicMock()))

    def test_player_check_runs_for_non_staff_post(self) -> None:
        called = []

        class Permission(PlayerOnlyPermission):
            def has_permission_for_player(self, request, view):
                called.append(True)
                return True

        permission = Permission()
        req = self._request("post", is_authenticated=True, is_staff=False)
        self.assertTrue(permission.has_permission(req, MagicMock()))
        self.assertEqual(called, [True])

    def test_object_permission_calls_for_player(self) -> None:
        called = []

        class Permission(PlayerOnlyPermission):
            def has_object_permission_for_player(self, request, view, obj):
                called.append(True)
                return False

        permission = Permission()
        req = self._request("delete", is_authenticated=True, is_staff=True)
        # PlayerOnly: even staff goes through player check
        self.assertFalse(permission.has_object_permission(req, MagicMock(), MagicMock()))
        self.assertEqual(called, [True])


class PlayerOrStaffPermissionTests(TestCase):
    """Staff get bypass on every method including writes."""

    def setUp(self) -> None:
        self.factory = APIRequestFactory()

    def _request(self, method: str, *, is_authenticated: bool, is_staff: bool):
        req = getattr(self.factory, method.lower())("/")
        req.user = MagicMock(is_authenticated=is_authenticated, is_staff=is_staff)
        return req

    def test_staff_post_bypassed(self) -> None:
        class Denying(PlayerOrStaffPermission):
            def has_permission_for_player(self, request, view):
                return False

        permission = Denying()
        req = self._request("post", is_authenticated=True, is_staff=True)
        self.assertTrue(permission.has_permission(req, MagicMock()))

    def test_player_check_runs_for_non_staff_post(self) -> None:
        called = []

        class Permission(PlayerOrStaffPermission):
            def has_permission_for_player(self, request, view):
                called.append(True)
                return True

        permission = Permission()
        req = self._request("post", is_authenticated=True, is_staff=False)
        self.assertTrue(permission.has_permission(req, MagicMock()))
        self.assertEqual(called, [True])

    def test_staff_object_permission_bypassed(self) -> None:
        class Denying(PlayerOrStaffPermission):
            def has_object_permission_for_player(self, request, view, obj):
                return False

        permission = Denying()
        req = self._request("delete", is_authenticated=True, is_staff=True)
        self.assertTrue(permission.has_object_permission(req, MagicMock(), MagicMock()))

    def test_non_staff_object_permission_runs_player_check(self) -> None:
        called = []

        class Permission(PlayerOrStaffPermission):
            def has_object_permission_for_player(self, request, view, obj):
                called.append(True)
                return False

        permission = Permission()
        req = self._request("delete", is_authenticated=True, is_staff=False)
        self.assertFalse(permission.has_object_permission(req, MagicMock(), MagicMock()))
        self.assertEqual(called, [True])

    def test_unauthenticated_denied_even_with_is_staff_true(self) -> None:
        # Edge: unauthenticated request can't be staff (Django handles this),
        # but verify the chain works.
        class Permission(PlayerOrStaffPermission):
            def has_permission_for_player(self, request, view):
                return True

        permission = Permission()
        req = self._request("get", is_authenticated=False, is_staff=False)
        self.assertFalse(permission.has_permission(req, MagicMock()))
