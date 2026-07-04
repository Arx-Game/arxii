"""Unit tests for the seven sanctum Actions (#1497).

TDD: the tests in Batch 1 (representative ops) were written first and confirmed
RED before the 7 Action classes were added to sanctum.py.

Coverage targets per brief:
  - SanctumWeaveAction: success path, service-error mapping, no-active-character gate
  - SanctumInstallAction: fizzle path (fiddly branch)
  - SanctumSeverAction: success path + service-error mapping
"""

from unittest.mock import patch

from django.test import TestCase

from actions.definitions import sanctum as sanctum_actions
from world.magic.seeds_sanctum import ensure_sanctification_personal_ritual


class SanctumActionBaseTests(TestCase):
    def test_base_is_self_targeted_magic(self):
        base = sanctum_actions.SanctumActionBase()
        self.assertEqual(base.category, "magic")
        self.assertEqual(base.target_type.name, "SELF")


# ---------------------------------------------------------------------------
# SanctumWeaveAction
# ---------------------------------------------------------------------------


class SanctumWeaveActionTests(TestCase):
    def test_weave_success_returns_thread_id(self):
        action = sanctum_actions.SanctumWeaveAction()
        fake_actor = object()
        fake_persona = type("P", (), {"character_sheet": "SHEET"})()
        fake_thread = type("T", (), {"pk": 77})()
        with (
            patch.object(action, "_persona", return_value=fake_persona),
            patch(
                "actions.definitions.sanctum.weave_sanctum_thread", return_value=fake_thread
            ) as woven,
        ):
            result = action.execute(fake_actor, sanctum="SANCTUM", slot_kind="HELPER")
        woven.assert_called_once_with("SANCTUM", "SHEET", "HELPER")
        self.assertTrue(result.success)
        self.assertEqual(result.data["thread_id"], 77)

    def test_weave_maps_service_error_to_failure(self):
        from world.magic.services.sanctum_weaving import SanctumWeavingError

        action = sanctum_actions.SanctumWeaveAction()
        fake_persona = type("P", (), {"character_sheet": "SHEET"})()
        exc = SanctumWeavingError("nope")
        exc.user_message = "You cannot weave here."
        with (
            patch.object(action, "_persona", return_value=fake_persona),
            patch("actions.definitions.sanctum.weave_sanctum_thread", side_effect=exc),
        ):
            result = action.execute(object(), sanctum="SANCTUM", slot_kind="HELPER")
        self.assertFalse(result.success)
        self.assertEqual(result.message, "You cannot weave here.")

    def test_no_active_character_fails(self):
        action = sanctum_actions.SanctumWeaveAction()
        with patch.object(action, "_persona", return_value=None):
            result = action.execute(object(), sanctum="SANCTUM", slot_kind="HELPER")
        self.assertFalse(result.success)


# ---------------------------------------------------------------------------
# SanctumInstallAction — fizzle branch
# ---------------------------------------------------------------------------


class SanctumInstallActionTests(TestCase):
    def setUp(self):
        # execute() now resolves the Sanctification Ritual row (#707, Task 8)
        # to validate/consume components before dispatching to
        # perform_sanctification (which is fully mocked below). No
        # RitualComponentRequirement rows exist here, so with no
        # components_provided kwarg this is a no-op past the row lookup.
        ensure_sanctification_personal_ritual()

    def test_install_fizzle_returns_fizzle_data(self):
        action = sanctum_actions.SanctumInstallAction()
        fake_persona = type("P", (), {"character_sheet": None})()
        fake_result = type(
            "R", (), {"fizzled": True, "success_level": -1, "tier": "fail", "sanctum_id": None}
        )()

        with (
            patch.object(action, "_persona", return_value=fake_persona),
            patch(
                "actions.definitions.sanctum.perform_sanctification",
                return_value=fake_result,
            ),
            patch(
                "actions.definitions.sanctum.sanctification_fizzle_detail",
                return_value="The rite failed to take hold.",
            ) as fizzle_detail,
        ):
            result = action.execute(
                object(),
                room_profile="RP",
                resonance="RES",
                owner_mode="PERSONAL",
            )

        fizzle_detail.assert_called_once_with("fail")
        self.assertTrue(result.success)
        self.assertTrue(result.data["fizzled"])
        self.assertEqual(result.data["success_level"], -1)
        self.assertEqual(result.data["tier"], "fail")
        self.assertEqual(result.data["detail"], "The rite failed to take hold.")

    def test_install_success_returns_sanctum_id(self):
        action = sanctum_actions.SanctumInstallAction()
        fake_persona = type("P", (), {"character_sheet": None})()
        fake_result = type(
            "R", (), {"fizzled": False, "success_level": 2, "tier": "success", "sanctum_id": 42}
        )()

        with (
            patch.object(action, "_persona", return_value=fake_persona),
            patch(
                "actions.definitions.sanctum.perform_sanctification",
                return_value=fake_result,
            ),
        ):
            result = action.execute(
                object(),
                room_profile="RP",
                resonance="RES",
                owner_mode="PERSONAL",
            )

        self.assertTrue(result.success)
        self.assertFalse(result.data["fizzled"])
        self.assertEqual(result.data["sanctum_id"], 42)
        self.assertEqual(result.data["success_level"], 2)
        self.assertEqual(result.data["tier"], "success")

    def test_install_maps_service_error_to_failure(self):
        from world.magic.services.sanctum_install import SanctificationError

        action = sanctum_actions.SanctumInstallAction()
        fake_persona = type("P", (), {"character_sheet": None})()
        exc = SanctificationError("bad room")
        exc.user_message = "This room cannot be sanctified."
        with (
            patch.object(action, "_persona", return_value=fake_persona),
            patch(
                "actions.definitions.sanctum.perform_sanctification",
                side_effect=exc,
            ),
        ):
            result = action.execute(
                object(), room_profile="RP", resonance="RES", owner_mode="PERSONAL"
            )
        self.assertFalse(result.success)
        self.assertEqual(result.message, "This room cannot be sanctified.")

    def test_install_no_active_character_fails(self):
        action = sanctum_actions.SanctumInstallAction()
        with patch.object(action, "_persona", return_value=None):
            result = action.execute(
                object(), room_profile="RP", resonance="RES", owner_mode="PERSONAL"
            )
        self.assertFalse(result.success)


# ---------------------------------------------------------------------------
# SanctumSeverAction
# ---------------------------------------------------------------------------


class SanctumSeverActionTests(TestCase):
    def test_sever_success_returns_empty_data(self):
        action = sanctum_actions.SanctumSeverAction()
        fake_persona = type("P", (), {})()
        with (
            patch.object(action, "_persona", return_value=fake_persona),
            patch("actions.definitions.sanctum.sever_sanctum_thread", return_value=None) as severed,
        ):
            result = action.execute(object(), thread="THREAD")
        severed.assert_called_once_with("THREAD")
        self.assertTrue(result.success)
        self.assertEqual(result.data, {})

    def test_sever_maps_service_error_to_failure(self):
        from world.magic.services.sanctum_weaving import SanctumWeavingError

        action = sanctum_actions.SanctumSeverAction()
        fake_persona = type("P", (), {})()
        exc = SanctumWeavingError("not yours")
        exc.user_message = "You cannot sever this thread."
        with (
            patch.object(action, "_persona", return_value=fake_persona),
            patch("actions.definitions.sanctum.sever_sanctum_thread", side_effect=exc),
        ):
            result = action.execute(object(), thread="THREAD")
        self.assertFalse(result.success)
        self.assertEqual(result.message, "You cannot sever this thread.")

    def test_sever_no_active_character_fails(self):
        action = sanctum_actions.SanctumSeverAction()
        with patch.object(action, "_persona", return_value=None):
            result = action.execute(object(), thread="THREAD")
        self.assertFalse(result.success)


# ---------------------------------------------------------------------------
# SanctumHomecomingAction
# ---------------------------------------------------------------------------


class SanctumHomecomingActionTests(TestCase):
    def test_homecoming_success_returns_result_fields(self):
        action = sanctum_actions.SanctumHomecomingAction()
        fake_persona = type("P", (), {})()
        fake_result = type(
            "R",
            (),
            {
                "base_resonance_added": 5,
                "overflow_escrowed": 0,
                "new_homecoming_sum": 15,
                "new_cap": 30,
                "success_level": 1,
                "tier": "success",
            },
        )()
        with (
            patch.object(action, "_persona", return_value=fake_persona),
            patch(
                "actions.definitions.sanctum.perform_homecoming_ritual",
                return_value=fake_result,
            ) as called,
        ):
            result = action.execute(
                object(),
                sanctum="SANCTUM",
                resonance_sacrificed=10,
                narrative_text="Story time.",
            )
        called.assert_called_once_with("SANCTUM", fake_persona, 10, narrative_text="Story time.")
        self.assertTrue(result.success)
        self.assertEqual(result.data["base_resonance_added"], 5)
        self.assertEqual(result.data["new_homecoming_sum"], 15)
        self.assertEqual(result.data["tier"], "success")

    def test_homecoming_no_active_character_fails(self):
        action = sanctum_actions.SanctumHomecomingAction()
        with patch.object(action, "_persona", return_value=None):
            result = action.execute(object(), sanctum="S", resonance_sacrificed=5)
        self.assertFalse(result.success)


# ---------------------------------------------------------------------------
# SanctumPurgingAction
# ---------------------------------------------------------------------------


class SanctumPurgingActionTests(TestCase):
    def test_purging_success_returns_result_fields(self):
        action = sanctum_actions.SanctumPurgingAction()
        fake_persona = type("P", (), {})()
        fake_result = type(
            "R",
            (),
            {
                "new_resonance_id": 7,
                "sum_after_drain": 20,
                "sacrifice_paid": 5,
                "success_level": 2,
                "tier": "crit",
            },
        )()
        with (
            patch.object(action, "_persona", return_value=fake_persona),
            patch(
                "actions.definitions.sanctum.perform_purging_ritual",
                return_value=fake_result,
            ) as called,
        ):
            result = action.execute(
                object(),
                sanctum="SANCTUM",
                new_resonance="NEW_RES",
                resonance_sacrificed=5,
            )
        called.assert_called_once_with("SANCTUM", fake_persona, "NEW_RES", 5)
        self.assertTrue(result.success)
        self.assertEqual(result.data["new_resonance_id"], 7)
        self.assertEqual(result.data["tier"], "crit")

    def test_purging_no_active_character_fails(self):
        action = sanctum_actions.SanctumPurgingAction()
        with patch.object(action, "_persona", return_value=None):
            result = action.execute(
                object(), sanctum="S", new_resonance="R", resonance_sacrificed=3
            )
        self.assertFalse(result.success)


# ---------------------------------------------------------------------------
# SanctumDissolveAction
# ---------------------------------------------------------------------------


class SanctumDissolveActionTests(TestCase):
    def test_dissolve_success_returns_result_fields(self):
        action = sanctum_actions.SanctumDissolveAction()
        fake_persona = type("P", (), {})()
        fake_result = type(
            "R",
            (),
            {
                "sanctum_id": 3,
                "success_level": 1,
                "recovered_amount": 50,
                "is_botch": False,
                "tier": "success",
            },
        )()
        with (
            patch.object(action, "_persona", return_value=fake_persona),
            patch(
                "actions.definitions.sanctum.perform_dissolution",
                return_value=fake_result,
            ) as called,
        ):
            result = action.execute(object(), sanctum="SANCTUM")
        called.assert_called_once_with("SANCTUM", fake_persona)
        self.assertTrue(result.success)
        self.assertEqual(result.data["sanctum_id"], 3)
        self.assertFalse(result.data["is_botch"])

    def test_dissolve_no_active_character_fails(self):
        action = sanctum_actions.SanctumDissolveAction()
        with patch.object(action, "_persona", return_value=None):
            result = action.execute(object(), sanctum="S")
        self.assertFalse(result.success)


# ---------------------------------------------------------------------------
# SanctumAbsorbAction
# ---------------------------------------------------------------------------


class SanctumAbsorbActionTests(TestCase):
    def test_absorb_success_returns_result_fields(self):
        action = sanctum_actions.SanctumAbsorbAction()
        fake_persona = type("P", (), {})()
        fake_result = type(
            "R",
            (),
            {
                "sanctum_id": 9,
                "weaving_drained": 10,
                "owner_bonus_drained": 5,
                "total_drained": 15,
            },
        )()
        with (
            patch.object(action, "_persona", return_value=fake_persona),
            patch(
                "actions.definitions.sanctum.absorb_sanctum_pool",
                return_value=fake_result,
            ) as called,
        ):
            result = action.execute(object(), sanctum="SANCTUM")
        called.assert_called_once_with("SANCTUM", fake_persona)
        self.assertTrue(result.success)
        self.assertEqual(result.data["sanctum_id"], 9)
        self.assertEqual(result.data["total_drained"], 15)

    def test_absorb_no_active_character_fails(self):
        action = sanctum_actions.SanctumAbsorbAction()
        with patch.object(action, "_persona", return_value=None):
            result = action.execute(object(), sanctum="S")
        self.assertFalse(result.success)
