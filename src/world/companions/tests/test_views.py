"""Tests for the companions API (#672)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIRequestFactory, APITestCase, force_authenticate

from actions.types import ActionResult
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.companions.factories import CompanionArchetypeFactory, CompanionFactory
from world.companions.views import CompanionViewSet
from world.roster.factories import RosterTenureFactory


def _actor_user(character):
    """Fake authenticated user whose ``puppet`` is ``character``."""
    return SimpleNamespace(
        is_authenticated=True,
        is_staff=False,
        pk=character.db_account_id,
        puppet=character,
    )


def _no_puppet_user():
    """Fake authenticated user with no puppet — actor cannot be resolved."""
    return SimpleNamespace(is_authenticated=True, is_staff=False, pk=None, puppet=None)


class CompanionViewSetTests(APITestCase):
    def test_lists_only_own_active_companions(self) -> None:
        tenure = RosterTenureFactory()
        account = tenure.player_data.account
        sheet = tenure.roster_entry.character_sheet
        mine = CompanionFactory(owner=sheet)
        CompanionFactory()  # someone else's — must not appear

        self.client.force_authenticate(account)
        response = self.client.get("/api/companions/companions/")

        self.assertEqual(response.status_code, 200)
        names = [row["name"] for row in response.data["results"]]
        self.assertIn(mine.name, names)
        self.assertEqual(len(names), 1)

    def test_unauthenticated_is_denied(self) -> None:
        # DRF returns 403, not 401, here: SessionAuthentication is the only
        # authenticator configured (REST_FRAMEWORK.DEFAULT_AUTHENTICATION_CLASSES)
        # and its authenticate_header() returns None, so there's no
        # WWW-Authenticate challenge to trigger a 401 — matches
        # world.ships.tests.test_views's identical
        # test_list_unauthenticated_returns_403.
        response = self.client.get("/api/companions/companions/")

        self.assertEqual(response.status_code, 403)


class CompanionArchetypeViewSetTests(APITestCase):
    def test_lists_catalog(self) -> None:
        tenure = RosterTenureFactory()
        archetype = CompanionArchetypeFactory()

        self.client.force_authenticate(tenure.player_data.account)
        response = self.client.get("/api/companions/companion-archetypes/")

        self.assertEqual(response.status_code, 200)
        names = [row["name"] for row in response.data]
        self.assertIn(archetype.name, names)


# ===========================================================================
# Write endpoints — bind / release / fight / deploy (#1918)
#
# Each endpoint converges on action.run() via PuppetActorMixin, mirroring
# SanctumViewSet's HTTP contract: success → 200/201 with result.data; failure
# → 400 {"detail": result.message}; no-puppet → 400 {"detail": "No active character."}.
# The Actions are mocked so these tests exercise the view wiring, not the
# game logic (that's covered by test_companion_actions.py).
# ===========================================================================


_VIEWS = "world.companions.views"


class CompanionWriteEndpointTestBase(TestCase):
    """Common setup for the write endpoint tests."""

    def setUp(self) -> None:
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.factory = APIRequestFactory()

    # -- helpers --------------------------------------------------------------

    def _ok_result(self, data: dict) -> ActionResult:
        return ActionResult(success=True, message="ok", data=data)

    def _fail_result(self, message: str = "Something went wrong.") -> ActionResult:
        return ActionResult(success=False, message=message, data={})

    def _list_post(self, action_name, puppet, payload):
        url = f"/api/companions/companions/{action_name}/"
        request = self.factory.post(url, payload, format="json")
        force_authenticate(request, user=puppet)
        view = CompanionViewSet.as_view({"post": action_name})
        return view(request)

    def _detail_post(self, action_name, puppet, pk, payload=None):
        url = f"/api/companions/companions/{pk}/{action_name}/"
        request = self.factory.post(url, payload or {}, format="json")
        force_authenticate(request, user=puppet)
        view = CompanionViewSet.as_view({"post": action_name})
        return view(request, pk=str(pk))


class BindEndpointTests(CompanionWriteEndpointTestBase):
    def test_bind_success_returns_201_with_companion_id(self) -> None:
        with patch(f"{_VIEWS}.BindCompanionAction") as mock_cls:
            mock_cls.return_value.run.return_value = self._ok_result({"companion_id": 42})
            resp = self._list_post(
                "bind",
                _actor_user(self.character),
                {"archetype_id": 1, "gift_id": 2, "name": "Skree"},
            )

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["companion_id"], 42)

    def test_bind_failure_returns_400_with_detail(self) -> None:
        with patch(f"{_VIEWS}.BindCompanionAction") as mock_cls:
            mock_cls.return_value.run.return_value = self._fail_result(
                "Not enough Companion Capacity."
            )
            resp = self._list_post(
                "bind",
                _actor_user(self.character),
                {"archetype_id": 1, "gift_id": 2, "name": "Fang"},
            )

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["detail"], "Not enough Companion Capacity.")

    def test_bind_no_puppet_returns_400(self) -> None:
        resp = self._list_post(
            "bind",
            _no_puppet_user(),
            {"archetype_id": 1, "gift_id": 2, "name": "Skree"},
        )

        self.assertEqual(resp.status_code, 400)
        self.assertIn("active character", resp.data["detail"].lower())

    def test_bind_missing_fields_returns_400(self) -> None:
        """Invalid serializer body (missing required fields) → 400."""
        resp = self._list_post("bind", _actor_user(self.character), {"archetype_id": 1})

        self.assertEqual(resp.status_code, 400)


class ReleaseEndpointTests(CompanionWriteEndpointTestBase):
    def test_release_success_returns_200(self) -> None:
        companion = CompanionFactory(owner=self.sheet)
        with (
            patch.object(CompanionViewSet, "get_object", return_value=companion),
            patch(f"{_VIEWS}.ReleaseCompanionAction") as mock_cls,
        ):
            mock_cls.return_value.run.return_value = self._ok_result({})
            resp = self._detail_post("release", _actor_user(self.character), companion.pk)

        self.assertEqual(resp.status_code, 200)

    def test_release_failure_returns_400_with_detail(self) -> None:
        companion = CompanionFactory(owner=self.sheet)
        with (
            patch.object(CompanionViewSet, "get_object", return_value=companion),
            patch(f"{_VIEWS}.ReleaseCompanionAction") as mock_cls,
        ):
            mock_cls.return_value.run.return_value = self._fail_result("No longer active.")
            resp = self._detail_post("release", _actor_user(self.character), companion.pk)

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["detail"], "No longer active.")

    def test_release_no_puppet_returns_400(self) -> None:
        companion = CompanionFactory(owner=self.sheet)
        with patch.object(CompanionViewSet, "get_object", return_value=companion):
            resp = self._detail_post("release", _no_puppet_user(), companion.pk)

        self.assertEqual(resp.status_code, 400)
        self.assertIn("active character", resp.data["detail"].lower())

    def test_cannot_release_other_players_companion(self) -> None:
        """A foreign companion is not in the caller's queryset → 404.

        ``get_object`` raises ``Http404`` when the pk is not in the caller's
        scoped queryset (a foreign companion would be excluded). We patch it
        to simulate that queryset-scope behavior, since the SimpleNamespace
        test user has no roster chain for a real queryset resolution.
        """
        from rest_framework.exceptions import NotFound

        other_sheet = CharacterSheetFactory()
        foreign = CompanionFactory(owner=other_sheet)
        with patch.object(CompanionViewSet, "get_object", side_effect=NotFound):
            resp = self._detail_post("release", _actor_user(self.character), foreign.pk)

        self.assertEqual(resp.status_code, 404)


class FightEndpointTests(CompanionWriteEndpointTestBase):
    def test_fight_success_returns_200_with_opponent_id(self) -> None:
        companion = CompanionFactory(owner=self.sheet)
        with (
            patch.object(CompanionViewSet, "get_object", return_value=companion),
            patch(f"{_VIEWS}.CompanionFightAction") as mock_cls,
        ):
            mock_cls.return_value.run.return_value = self._ok_result({"opponent_id": 7})
            resp = self._detail_post("fight", _actor_user(self.character), companion.pk)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["opponent_id"], 7)

    def test_fight_requires_active_combat_returns_400(self) -> None:
        companion = CompanionFactory(owner=self.sheet)
        with (
            patch.object(CompanionViewSet, "get_object", return_value=companion),
            patch(f"{_VIEWS}.CompanionFightAction") as mock_cls,
        ):
            mock_cls.return_value.run.return_value = self._fail_result(
                "You are not in active combat."
            )
            resp = self._detail_post("fight", _actor_user(self.character), companion.pk)

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["detail"], "You are not in active combat.")

    def test_cannot_fight_other_players_companion(self) -> None:
        """A foreign companion is not in the caller's queryset → 404."""
        from rest_framework.exceptions import NotFound

        other_sheet = CharacterSheetFactory()
        foreign = CompanionFactory(owner=other_sheet)
        with patch.object(CompanionViewSet, "get_object", side_effect=NotFound):
            resp = self._detail_post("fight", _actor_user(self.character), foreign.pk)

        self.assertEqual(resp.status_code, 404)


class DeployEndpointTests(CompanionWriteEndpointTestBase):
    def test_deploy_success_returns_200_with_vehicle_id(self) -> None:
        companion = CompanionFactory(owner=self.sheet)
        with (
            patch.object(CompanionViewSet, "get_object", return_value=companion),
            patch(f"{_VIEWS}.DeployCompanionAction") as mock_cls,
        ):
            mock_cls.return_value.run.return_value = self._ok_result({"vehicle_id": 9})
            resp = self._detail_post("deploy", _actor_user(self.character), companion.pk)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["vehicle_id"], 9)

    def test_deploy_requires_active_battle_returns_400(self) -> None:
        companion = CompanionFactory(owner=self.sheet)
        with (
            patch.object(CompanionViewSet, "get_object", return_value=companion),
            patch(f"{_VIEWS}.DeployCompanionAction") as mock_cls,
        ):
            mock_cls.return_value.run.return_value = self._fail_result("You are not in a battle.")
            resp = self._detail_post("deploy", _actor_user(self.character), companion.pk)

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["detail"], "You are not in a battle.")

    def test_cannot_deploy_other_players_companion(self) -> None:
        """A foreign companion is not in the caller's queryset → 404."""
        from rest_framework.exceptions import NotFound

        other_sheet = CharacterSheetFactory()
        foreign = CompanionFactory(owner=other_sheet)
        with patch.object(CompanionViewSet, "get_object", side_effect=NotFound):
            resp = self._detail_post("deploy", _actor_user(self.character), foreign.pk)

        self.assertEqual(resp.status_code, 404)
