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
# install — components ownership (Finding 1, #707 review fix)
#
# Unlike ``InstallEndpointTests`` above (which mocks ``SanctumInstallAction``
# entirely), these tests run the REAL action end-to-end through the web
# ``install`` endpoint so the component-ownership check is exercised for
# real: a legitimately-owned component gets consumed on success, and a
# component belonging to someone else's inventory is rejected before the
# Action ever runs (so it is never touched/consumed).
# ===========================================================================


def _mock_check_success_components() -> object:
    """Return a fake CheckResult whose outcome tier maps to SUCCESS (success_level=1).

    Mirrors ``test_sanctum_install_action_components.py``'s helper — the
    Sanctification check is patched deterministic so these tests exercise
    the component-ownership seam, not the check-roll RNG.
    """
    outcome = type("Outcome", (), {"success_level": 1})()
    return type("CheckResult", (), {"outcome": outcome})()


class InstallComponentsOwnershipEndpointTests(SanctumViewSetTestBase):
    """Real (unmocked) install through the web endpoint, component ownership."""

    def setUp(self) -> None:
        super().setUp()

        from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
        from world.locations.constants import HolderType, LocationParentType
        from world.locations.factories import LocationOwnershipFactory
        from world.magic.factories import CharacterResonanceFactory, ResonanceTierFactory
        from world.magic.seeds_checks import ensure_magic_check_content
        from world.magic.seeds_sanctum import (
            ensure_sanctification_personal_ritual,
            ensure_sanctum_rituals,
        )
        from world.magic.seeds_touchstone_content import ensure_touchstone_content
        from world.room_features.models import RoomFeatureKind
        from world.room_features.seeds import SANCTUM_KIND_NAME, ensure_sanctum_kind

        # The base class's ``setUp`` already created a generic SANCTUM-strategy
        # RoomFeatureKind via ``_personal_sanctum()`` (for the mocked-out
        # endpoint tests above). ``ensure_sanctum_kind()`` get_or_creates by
        # ``service_strategy`` — it would find that row and leave its name
        # alone, but ``perform_sanctification`` looks the kind up by
        # ``name=SANCTUM_KIND_NAME``. Normalize the name so both resolve the
        # same row.
        RoomFeatureKind.objects.filter(
            service_strategy=self.sanctum.feature_instance.feature_kind.service_strategy
        ).update(name=SANCTUM_KIND_NAME)
        ensure_sanctum_kind()
        ensure_sanctum_rituals()
        ensure_magic_check_content()

        self._check_patcher = patch("world.checks.services.perform_check")
        mock_check = self._check_patcher.start()
        mock_check.return_value = _mock_check_success_components()
        self.addCleanup(self._check_patcher.stop)

        self.install_room_profile = RoomProfileFactory()
        self.character.db_location = self.install_room_profile.objectdb
        self.character.save(update_fields=["db_location"])

        # Room ownership: the founder's PRIMARY persona holds the deed.
        LocationOwnershipFactory(
            parent_type=LocationParentType.ROOM,
            area=None,
            room_profile=self.install_room_profile,
            holder_type=HolderType.PERSONA,
            holder_persona=self.sheet.primary_persona,
            holder_organization=None,
        )

        self.install_resonance = ResonanceFactory(name="Praedari")
        self.tier = ResonanceTierFactory(name="Faint", tier_level=1)
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.install_resonance)

        self.ritual = ensure_sanctification_personal_ritual()
        self.template = ItemTemplateFactory(
            tied_resonance=self.install_resonance, resonance_tier=self.tier
        )
        self.touchstone = ItemInstanceFactory(
            template=self.template,
            attuned_to_character_sheet=self.sheet,
            holder_character_sheet=self.sheet,
        )
        _, reagent_templates = ensure_touchstone_content()
        self.reagents = [
            ItemInstanceFactory(template=t, holder_character_sheet=self.sheet)
            for t in reagent_templates
        ]
        self.all_component_pks = [self.touchstone.pk, *[r.pk for r in self.reagents]]

        # Real AccountDB + puppet wiring, mirroring ``InstallEndpointTests.setUp``
        # above — the install path (persona resolution, deed-holder checks) needs
        # ``request.user`` to be an actual ``AccountDB``, not a bare
        # ``SimpleNamespace``.
        from evennia_extensions.factories import AccountFactory

        self.account = AccountFactory()
        self.character.db_account_id = self.account.pk
        self.character.save(update_fields=["db_account_id"])
        puppet_patcher = patch.object(
            type(self.account), "puppet", new_callable=PropertyMock, return_value=self.character
        )
        puppet_patcher.start()
        self.addCleanup(puppet_patcher.stop)

    def _post_install_components(self, puppet, component_pks):
        return self._list_post(
            "install",
            puppet,
            {
                "room_profile_id": self.install_room_profile.pk,
                "resonance_type_id": self.install_resonance.pk,
                "owner_mode": "PERSONAL",
                "components": component_pks,
            },
        )

    def test_install_with_owned_components_succeeds_and_consumes_them(self) -> None:
        """Legitimately-owned components: install succeeds and they're consumed."""
        from world.items.models import ItemInstance

        resp = self._post_install_components(self.account, self.all_component_pks)

        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertFalse(resp.data["fizzled"])
        self.assertFalse(
            ItemInstance.objects.filter(pk__in=self.all_component_pks).exists(),
            "Owned components should have been consumed by the real install action.",
        )

    def test_install_with_other_characters_component_is_rejected(self) -> None:
        """A component belonging to a DIFFERENT character's inventory is rejected.

        The submitted item must be rejected with 400 and left untouched — it
        must never reach ``SanctumInstallAction`` (and therefore never get
        consumed), regardless of the account-wide roster state that the old,
        buggy serializer-level check used to (mis)consult.
        """
        from world.character_sheets.factories import CharacterSheetFactory
        from world.items.models import ItemInstance

        other_character = CharacterFactory()
        other_sheet = CharacterSheetFactory(character=other_character)
        foreign_touchstone = self.touchstone
        foreign_touchstone.holder_character_sheet = other_sheet
        foreign_touchstone.save(update_fields=["holder_character_sheet"])

        with patch(f"{_VIEWS}.SanctumInstallAction") as mock_cls:
            resp = self._post_install_components(self.account, self.all_component_pks)

        self.assertEqual(resp.status_code, 400)
        self.assertIn("not in your inventory", resp.data["detail"].lower())
        mock_cls.return_value.run.assert_not_called()
        self.assertTrue(ItemInstance.objects.filter(pk=foreign_touchstone.pk).exists())


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
