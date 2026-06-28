"""Tests for SanctumViewSet — HTTP contract for all 7 endpoints (#1497).

Exercises each `@action` the way the web frontend hits it:
  • success → exact JSON keys + status (weave 201, sever 204, install 201/fizzle 200, others 200)
  • failure → 400 ``{"detail": <user_message>}``
  • no-puppet → 400 ``{"detail": "No active character."}``

Uses ``force_authenticate`` + a ``SimpleNamespace`` puppet-bearing user mirroring
``world/relationships/tests/test_update_viewset.py``.  Business logic is mocked via
the Action class — those paths are exercised by ``test_sanctum_*.py`` and
``test_actions_sanctum*.py``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from actions.types import ActionResult
from evennia_extensions.factories import CharacterFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import SanctumSlotKind, TargetKind
from world.magic.factories import ResonanceFactory
from world.magic.models import SanctumDetails, SanctumOwnerMode, Thread
from world.magic.views_sanctum import SanctumViewSet
from world.room_features.constants import RoomFeatureServiceStrategy
from world.room_features.factories import RoomFeatureInstanceFactory, RoomFeatureKindFactory

_VIEWS = "world.magic.views_sanctum"


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


def _personal_sanctum(resonance=None):
    """Build a minimal PERSONAL Sanctum for tests."""
    resonance = resonance or ResonanceFactory()
    room_profile = RoomProfileFactory()
    sanctum_kind = RoomFeatureKindFactory(
        service_strategy=RoomFeatureServiceStrategy.SANCTUM,
    )
    instance = RoomFeatureInstanceFactory(
        room_profile=room_profile,
        feature_kind=sanctum_kind,
        level=3,
    )
    sanctum = SanctumDetails.objects.create(
        feature_instance=instance,
        resonance_type=resonance,
        owner_mode=SanctumOwnerMode.PERSONAL,
    )
    return sanctum, resonance


class SanctumViewSetTestBase(TestCase):
    """Common setup for SanctumViewSet tests."""

    def setUp(self) -> None:
        from evennia.utils.idmapper.models import flush_cache

        flush_cache()
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.sanctum, self.resonance = _personal_sanctum()
        self.factory = APIRequestFactory()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _detail_post(self, action_name, puppet, payload, feature_instance_id=None, **extra_kwargs):
        fid = (
            feature_instance_id
            if feature_instance_id is not None
            else self.sanctum.feature_instance_id
        )
        url = f"/api/magic/sanctums/{fid}/{action_name}/"
        request = self.factory.post(url, payload, format="json")
        force_authenticate(request, user=puppet)
        view = SanctumViewSet.as_view({"post": action_name})
        return view(request, feature_instance_id=str(fid), **extra_kwargs)

    def _list_post(self, action_name, puppet, payload):
        url = f"/api/magic/sanctums/{action_name}/"
        request = self.factory.post(url, payload, format="json")
        force_authenticate(request, user=puppet)
        view = SanctumViewSet.as_view({"post": action_name})
        return view(request)

    def _ok_action_result(self, data: dict) -> ActionResult:
        return ActionResult(success=True, message="ok", data=data)

    def _fail_action_result(self, message: str = "Something went wrong.") -> ActionResult:
        return ActionResult(success=False, message=message, data={})


# ===========================================================================
# homecoming
# ===========================================================================


class HomecomingEndpointTests(SanctumViewSetTestBase):
    _HOMECOMING_DATA = {
        "base_resonance_added": 10,
        "overflow_escrowed": 0,
        "new_homecoming_sum": 10,
        "new_cap": 100,
        "success_level": 1,
        "tier": 1,
    }

    def _post_homecoming(self, puppet, resonance_id=None):
        if resonance_id is None:
            resonance_id = self.resonance.pk
        return self._detail_post(
            "homecoming",
            puppet,
            {"resonance_sacrificed": resonance_id},
        )

    def test_homecoming_success_returns_200_with_all_keys(self) -> None:
        with (
            patch.object(SanctumViewSet, "get_object", return_value=self.sanctum),
            patch(f"{_VIEWS}.SanctumHomecomingAction") as mock_cls,
        ):
            mock_cls.return_value.run.return_value = self._ok_action_result(self._HOMECOMING_DATA)
            resp = self._post_homecoming(_actor_user(self.character))

        self.assertEqual(resp.status_code, 200)
        for key in self._HOMECOMING_DATA:
            self.assertIn(key, resp.data, msg=f"Missing key: {key}")

    def test_homecoming_failure_returns_400_with_detail(self) -> None:
        with (
            patch.object(SanctumViewSet, "get_object", return_value=self.sanctum),
            patch(f"{_VIEWS}.SanctumHomecomingAction") as mock_cls,
        ):
            mock_cls.return_value.run.return_value = self._fail_action_result(
                "Not the owner of this Sanctum."
            )
            resp = self._post_homecoming(_actor_user(self.character))

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["detail"], "Not the owner of this Sanctum.")

    def test_homecoming_no_puppet_returns_400(self) -> None:
        with patch.object(SanctumViewSet, "get_object", return_value=self.sanctum):
            resp = self._post_homecoming(_no_puppet_user())

        self.assertEqual(resp.status_code, 400)
        self.assertIn("active character", resp.data["detail"].lower())


# ===========================================================================
# purging
# ===========================================================================


class PurgingEndpointTests(SanctumViewSetTestBase):
    _PURGING_DATA = {
        "new_resonance_id": 99,
        "sum_after_drain": 50,
        "sacrifice_paid": 20,
        "success_level": 1,
        "tier": 1,
    }

    def setUp(self) -> None:
        super().setUp()
        self.new_resonance = ResonanceFactory()
        self._PURGING_DATA = dict(self._PURGING_DATA, new_resonance_id=self.new_resonance.pk)

    def _post_purging(self, puppet):
        return self._detail_post(
            "purging",
            puppet,
            {
                "new_resonance_id": self.new_resonance.pk,
                "resonance_sacrificed": 10,
            },
        )

    def test_purging_success_returns_200_with_all_keys(self) -> None:
        with (
            patch.object(SanctumViewSet, "get_object", return_value=self.sanctum),
            patch(f"{_VIEWS}.SanctumPurgingAction") as mock_cls,
        ):
            mock_cls.return_value.run.return_value = self._ok_action_result(self._PURGING_DATA)
            resp = self._post_purging(_actor_user(self.character))

        self.assertEqual(resp.status_code, 200)
        for key in self._PURGING_DATA:
            self.assertIn(key, resp.data, msg=f"Missing key: {key}")

    def test_purging_failure_returns_400_with_detail(self) -> None:
        with (
            patch.object(SanctumViewSet, "get_object", return_value=self.sanctum),
            patch(f"{_VIEWS}.SanctumPurgingAction") as mock_cls,
        ):
            mock_cls.return_value.run.return_value = self._fail_action_result(
                "Resonance type is unchanged."
            )
            resp = self._post_purging(_actor_user(self.character))

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["detail"], "Resonance type is unchanged.")

    def test_purging_no_puppet_returns_400(self) -> None:
        with patch.object(SanctumViewSet, "get_object", return_value=self.sanctum):
            resp = self._post_purging(_no_puppet_user())

        self.assertEqual(resp.status_code, 400)
        self.assertIn("active character", resp.data["detail"].lower())


# ===========================================================================
# weave
# ===========================================================================


class WeaveEndpointTests(SanctumViewSetTestBase):
    """Weave returns HTTP 201 with SanctumThreadSerializer body.

    The Action returns only ``{"thread_id": pk}``; the viewset re-queries
    the Thread and serializes it.
    """

    def setUp(self) -> None:
        super().setUp()
        # Create a SANCTUM thread directly — ThreadFactory defaults to TRAIT kind
        # and doesn't clear target_trait, which violates the thread_sanctum_payload
        # CheckConstraint. Use Thread.objects.create with all non-SANCTUM FKs null.
        self.thread = Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.SANCTUM,
            target_sanctum_details=self.sanctum,
            slot_kind=SanctumSlotKind.PERSONAL_OWN,
        )

    def _post_weave(self, puppet, slot_kind="PERSONAL_OWN"):
        return self._detail_post("weave", puppet, {"slot_kind": slot_kind})

    def test_weave_success_returns_201_with_thread_keys(self) -> None:
        with (
            patch.object(SanctumViewSet, "get_object", return_value=self.sanctum),
            patch(f"{_VIEWS}.SanctumWeaveAction") as mock_cls,
        ):
            mock_cls.return_value.run.return_value = self._ok_action_result(
                {"thread_id": self.thread.pk}
            )
            resp = self._post_weave(_actor_user(self.character))

        self.assertEqual(resp.status_code, 201)
        # SanctumThreadSerializer keys
        for key in ("id", "owner", "target_sanctum_details", "slot_kind", "level"):
            self.assertIn(key, resp.data, msg=f"Missing serializer key: {key}")

    def test_weave_failure_returns_400_with_detail(self) -> None:
        with (
            patch.object(SanctumViewSet, "get_object", return_value=self.sanctum),
            patch(f"{_VIEWS}.SanctumWeaveAction") as mock_cls,
        ):
            mock_cls.return_value.run.return_value = self._fail_action_result(
                "Owner cannot weave helper threads."
            )
            resp = self._post_weave(_actor_user(self.character))

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["detail"], "Owner cannot weave helper threads.")

    def test_weave_no_puppet_returns_400(self) -> None:
        with patch.object(SanctumViewSet, "get_object", return_value=self.sanctum):
            resp = self._post_weave(_no_puppet_user())

        self.assertEqual(resp.status_code, 400)
        self.assertIn("active character", resp.data["detail"].lower())


# ===========================================================================
# install
# ===========================================================================


class InstallEndpointTests(SanctumViewSetTestBase):
    """Install is ``detail=False`` — no ``get_object`` call."""

    def setUp(self) -> None:
        super().setUp()
        self.room_profile = RoomProfileFactory()

        # Build a real AccountDB + RosterTenure chain so ``SanctumDetailsSerializer``
        # resolves ``_viewer_character_sheet`` via
        # ``RosterEntry.objects.for_account(request.user)`` without being patched.
        # The other tests still use SimpleNamespace users (fizzle / failure / no-puppet
        # all return early before the serializer runs, so no roster lookup fires).
        from evennia_extensions.factories import AccountFactory
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )

        self.account = AccountFactory()
        # Link the existing character to the real account so ``_resolve_actor``
        # passes its ``sheet.character.db_account_id == request.user.pk`` guard.
        self.character.db_account_id = self.account.pk
        self.character.save(update_fields=["db_account_id"])
        # Tenure chain: account → PlayerData → RosterTenure → RosterEntry → sheet.
        player_data = PlayerDataFactory(account=self.account)
        roster_entry = RosterEntryFactory(character_sheet=self.sheet)
        RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
        # ``puppet`` is a read-only Evennia property; mock it for the duration of
        # this test so ``_resolve_actor`` sees our character as the active puppet.
        puppet_patcher = patch.object(
            type(self.account), "puppet", new_callable=PropertyMock, return_value=self.character
        )
        puppet_patcher.start()
        self.addCleanup(puppet_patcher.stop)

    def _post_install(self, puppet, owner_mode="PERSONAL"):
        return self._list_post(
            "install",
            puppet,
            {
                "room_profile_id": self.room_profile.pk,
                "resonance_type_id": self.resonance.pk,
                "owner_mode": owner_mode,
            },
        )

    def test_install_success_returns_201_with_full_serializer_body(self) -> None:
        """Install success: ``SanctumDetailsSerializer`` runs un-patched.

        Uses a real account + RosterTenure fixture so the serializer can
        resolve ``_viewer_character_sheet`` from ``for_account``. Asserts all
        13 ``SanctumDetailsSerializer.Meta.fields`` are present in the merged
        response — the riskiest contract point in the #1497 refactor.
        """
        with patch(f"{_VIEWS}.SanctumInstallAction") as mock_cls:
            mock_cls.return_value.run.return_value = self._ok_action_result(
                {
                    "sanctum_id": self.sanctum.pk,
                    "fizzled": False,
                    "success_level": 1,
                    "tier": "success",
                }
            )
            resp = self._post_install(self.account)

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["fizzled"], False)
        self.assertIn("success_level", resp.data)
        self.assertIn("tier", resp.data)
        # Every field declared in SanctumDetailsSerializer.Meta.fields must appear —
        # this proves the serializer ran for real and the full contract is intact.
        from world.magic.serializers_sanctum import (
            SanctumDetailsSerializer as _Ser,
        )

        for key in _Ser.Meta.fields:
            self.assertIn(key, resp.data, msg=f"Missing SanctumDetailsSerializer field: {key}")

    def test_install_fizzle_returns_200_with_fizzle_body(self) -> None:
        with patch(f"{_VIEWS}.SanctumInstallAction") as mock_cls:
            mock_cls.return_value.run.return_value = self._ok_action_result(
                {
                    "fizzled": True,
                    "success_level": 0,
                    "tier": 1,
                    "detail": "The sanctification ritual fails.",
                }
            )
            resp = self._post_install(_actor_user(self.character))

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["fizzled"])
        self.assertIn("detail", resp.data)
        self.assertIn("success_level", resp.data)
        self.assertIn("tier", resp.data)

    def test_install_failure_returns_400_with_detail(self) -> None:
        with patch(f"{_VIEWS}.SanctumInstallAction") as mock_cls:
            mock_cls.return_value.run.return_value = self._fail_action_result(
                "Room is not owned by you."
            )
            resp = self._post_install(_actor_user(self.character))

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["detail"], "Room is not owned by you.")

    def test_install_no_puppet_returns_400(self) -> None:
        resp = self._post_install(_no_puppet_user())

        self.assertEqual(resp.status_code, 400)
        self.assertIn("active character", resp.data["detail"].lower())


# ===========================================================================
# dissolve
# ===========================================================================


class DissolveEndpointTests(SanctumViewSetTestBase):
    _DISSOLVE_DATA = {
        "sanctum_id": 1,  # updated in setUp
        "success_level": 1,
        "recovered_amount": 50,
        "is_botch": False,
        "tier": 1,
    }

    def setUp(self) -> None:
        super().setUp()
        self._DISSOLVE_DATA = dict(self._DISSOLVE_DATA, sanctum_id=self.sanctum.pk)

    def _post_dissolve(self, puppet):
        return self._detail_post("dissolve", puppet, {})

    def test_dissolve_success_returns_200_with_all_keys(self) -> None:
        with (
            patch.object(SanctumViewSet, "get_object", return_value=self.sanctum),
            patch(f"{_VIEWS}.SanctumDissolveAction") as mock_cls,
        ):
            mock_cls.return_value.run.return_value = self._ok_action_result(self._DISSOLVE_DATA)
            resp = self._post_dissolve(_actor_user(self.character))

        self.assertEqual(resp.status_code, 200)
        for key in self._DISSOLVE_DATA:
            self.assertIn(key, resp.data, msg=f"Missing key: {key}")

    def test_dissolve_failure_returns_400_with_detail(self) -> None:
        with (
            patch.object(SanctumViewSet, "get_object", return_value=self.sanctum),
            patch(f"{_VIEWS}.SanctumDissolveAction") as mock_cls,
        ):
            mock_cls.return_value.run.return_value = self._fail_action_result(
                "You must be present to dissolve the Sanctum."
            )
            resp = self._post_dissolve(_actor_user(self.character))

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["detail"], "You must be present to dissolve the Sanctum.")

    def test_dissolve_no_puppet_returns_400(self) -> None:
        with patch.object(SanctumViewSet, "get_object", return_value=self.sanctum):
            resp = self._post_dissolve(_no_puppet_user())

        self.assertEqual(resp.status_code, 400)
        self.assertIn("active character", resp.data["detail"].lower())


# ===========================================================================
# absorb
# ===========================================================================


class AbsorbEndpointTests(SanctumViewSetTestBase):
    _ABSORB_DATA = {
        "sanctum_id": 1,  # updated in setUp
        "weaving_drained": 30,
        "owner_bonus_drained": 10,
        "total_drained": 40,
    }

    def setUp(self) -> None:
        super().setUp()
        self._ABSORB_DATA = dict(self._ABSORB_DATA, sanctum_id=self.sanctum.pk)

    def _post_absorb(self, puppet):
        return self._detail_post("absorb", puppet, {})

    def test_absorb_success_returns_200_with_all_keys(self) -> None:
        with (
            patch.object(SanctumViewSet, "get_object", return_value=self.sanctum),
            patch(f"{_VIEWS}.SanctumAbsorbAction") as mock_cls,
        ):
            mock_cls.return_value.run.return_value = self._ok_action_result(self._ABSORB_DATA)
            resp = self._post_absorb(_actor_user(self.character))

        self.assertEqual(resp.status_code, 200)
        for key in self._ABSORB_DATA:
            self.assertIn(key, resp.data, msg=f"Missing key: {key}")

    def test_absorb_failure_returns_400_with_detail(self) -> None:
        with (
            patch.object(SanctumViewSet, "get_object", return_value=self.sanctum),
            patch(f"{_VIEWS}.SanctumAbsorbAction") as mock_cls,
        ):
            mock_cls.return_value.run.return_value = self._fail_action_result(
                "No pending payout to absorb."
            )
            resp = self._post_absorb(_actor_user(self.character))

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["detail"], "No pending payout to absorb.")

    def test_absorb_no_puppet_returns_400(self) -> None:
        with patch.object(SanctumViewSet, "get_object", return_value=self.sanctum):
            resp = self._post_absorb(_no_puppet_user())

        self.assertEqual(resp.status_code, 400)
        self.assertIn("active character", resp.data["detail"].lower())


# ===========================================================================
# sever
# ===========================================================================


class SeverEndpointTests(SanctumViewSetTestBase):
    """Sever returns HTTP 204 no content on success."""

    def setUp(self) -> None:
        super().setUp()
        # Create a SANCTUM thread directly — see WeaveEndpointTests for rationale.
        self.thread = Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.SANCTUM,
            target_sanctum_details=self.sanctum,
            slot_kind=SanctumSlotKind.PERSONAL_OWN,
        )

    def _post_sever(self, puppet, thread_id=None):
        tid = thread_id if thread_id is not None else self.thread.pk
        return self._detail_post(
            "sever",
            puppet,
            {},
            thread_id=str(tid),
        )

    def test_sever_success_returns_204(self) -> None:
        with (
            patch.object(SanctumViewSet, "get_object", return_value=self.sanctum),
            patch(f"{_VIEWS}.SanctumSeverAction") as mock_cls,
        ):
            mock_cls.return_value.run.return_value = self._ok_action_result({})
            resp = self._post_sever(_actor_user(self.character))

        self.assertEqual(resp.status_code, 204)

    def test_sever_failure_returns_400_with_detail(self) -> None:
        with (
            patch.object(SanctumViewSet, "get_object", return_value=self.sanctum),
            patch(f"{_VIEWS}.SanctumSeverAction") as mock_cls,
        ):
            mock_cls.return_value.run.return_value = self._fail_action_result(
                "Thread is already retired."
            )
            resp = self._post_sever(_actor_user(self.character))

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["detail"], "Thread is already retired.")

    def test_sever_no_puppet_returns_400(self) -> None:
        with patch.object(SanctumViewSet, "get_object", return_value=self.sanctum):
            resp = self._post_sever(_no_puppet_user())

        self.assertEqual(resp.status_code, 400)
        self.assertIn("active character", resp.data["detail"].lower())
