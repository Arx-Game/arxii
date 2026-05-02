"""Tests for the ``execute_action`` websocket inputfunc.

The inputfunc is the unified web entry point for game mutations: the React
frontend sends an inbound ``execute_action`` message, the inputfunc resolves
the action key and any ``*_id`` kwargs to model instances, runs the action
on the session's puppeted character, and pushes back an ``ACTION_RESULT``
message. This module exercises the puppet/lookup/dispatch glue with mocks
so the contract stays stable as actions are added or modified.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.types import ActionInterrupted, ActionResult
from server.conf.inputfuncs import execute_action
from web.webclient.message_types import WebsocketMessageType


def _make_session(puppet: object = None) -> MagicMock:
    """Build a stub session with a configurable ``puppet`` and recording ``msg``."""
    session = MagicMock()
    session.puppet = puppet
    return session


def _result_payload(session: MagicMock) -> dict:
    """Pull the kwargs payload from the most recent ``session.msg`` call."""
    assert session.msg.called, "session.msg was not called"
    return session.msg.call_args.kwargs


class ExecuteActionInputfuncTests(TestCase):
    """End-to-end behavior of the ``execute_action`` inputfunc."""

    def test_no_puppet_sends_error(self) -> None:
        """When session.puppet is None, an error response is sent and no action runs."""
        session = _make_session(puppet=None)
        with patch("actions.registry.get_action") as get_action:
            execute_action(session, action="equip", kwargs={})
        get_action.assert_not_called()
        payload = _result_payload(session)
        self.assertEqual(payload["type"], WebsocketMessageType.ACTION_RESULT.value)
        self.assertEqual(payload["kwargs"]["success"], False)
        self.assertIn("playing a character", payload["kwargs"]["message"])

    def test_missing_action_key_sends_error(self) -> None:
        """Inbound payload without an ``action`` key returns a structured error."""
        actor = MagicMock()
        session = _make_session(puppet=actor)
        with patch("actions.registry.get_action") as get_action:
            execute_action(session, kwargs={})
        get_action.assert_not_called()
        payload = _result_payload(session)
        self.assertEqual(payload["kwargs"]["success"], False)
        self.assertIn("No action specified", payload["kwargs"]["message"])

    def test_unknown_action_key_sends_error(self) -> None:
        """An unknown action key returns a structured error without dispatching."""
        actor = MagicMock()
        session = _make_session(puppet=actor)
        with patch("actions.registry.get_action", return_value=None):
            execute_action(session, action="not_a_real_action", kwargs={})
        payload = _result_payload(session)
        self.assertEqual(payload["kwargs"]["success"], False)
        self.assertIn("Unknown action", payload["kwargs"]["message"])
        self.assertIn("not_a_real_action", payload["kwargs"]["message"])

    def test_happy_path_runs_action_and_returns_result(self) -> None:
        """Valid action key + kwargs runs the action and forwards its result."""
        actor = MagicMock()
        session = _make_session(puppet=actor)
        stub_action = MagicMock()
        stub_action.run.return_value = ActionResult(
            success=True,
            message="You equip it.",
            data={"slot": "torso"},
        )
        with patch("actions.registry.get_action", return_value=stub_action):
            execute_action(session, action="equip", kwargs={"slot": "torso"})
        stub_action.run.assert_called_once_with(actor, slot="torso")
        payload = _result_payload(session)
        self.assertEqual(payload["type"], WebsocketMessageType.ACTION_RESULT.value)
        self.assertEqual(payload["kwargs"]["success"], True)
        self.assertEqual(payload["kwargs"]["message"], "You equip it.")
        self.assertEqual(payload["kwargs"]["data"], {"slot": "torso"})

    def test_object_id_kwarg_is_resolved(self) -> None:
        """Keys ending in ``_id`` whose stripped name is declared on the action are resolved."""
        actor = MagicMock()
        session = _make_session(puppet=actor)
        target_obj = MagicMock(name="resolved_target")
        stub_action = MagicMock()
        stub_action.objectdb_target_kwargs = frozenset({"target"})
        stub_action.run.return_value = ActionResult(success=True)

        with (
            patch("actions.registry.get_action", return_value=stub_action),
            patch("evennia.objects.models.ObjectDB.objects.get", return_value=target_obj) as get,
        ):
            execute_action(session, action="give", kwargs={"target_id": 42})

        get.assert_called_once_with(pk=42)
        # The ``_id`` suffix is stripped before dispatch.
        stub_action.run.assert_called_once_with(actor, target=target_obj)

    def test_object_id_not_found_sends_error(self) -> None:
        """An unresolvable object id sends an error and does not run the action."""
        from evennia.objects.models import ObjectDB

        actor = MagicMock()
        session = _make_session(puppet=actor)
        stub_action = MagicMock()
        stub_action.objectdb_target_kwargs = frozenset({"target"})

        with (
            patch("actions.registry.get_action", return_value=stub_action),
            patch(
                "evennia.objects.models.ObjectDB.objects.get",
                side_effect=ObjectDB.DoesNotExist,
            ),
        ):
            execute_action(session, action="give", kwargs={"target_id": 9999999})

        stub_action.run.assert_not_called()
        payload = _result_payload(session)
        self.assertEqual(payload["kwargs"]["success"], False)
        self.assertIn("Object not found", payload["kwargs"]["message"])
        self.assertIn("target_id", payload["kwargs"]["message"])

    def test_action_interrupted_sends_error(self) -> None:
        """ActionInterrupted from action.run is forwarded as a failure response."""
        actor = MagicMock()
        session = _make_session(puppet=actor)
        stub_action = MagicMock()
        stub_action.objectdb_target_kwargs = frozenset()
        stub_action.run.side_effect = ActionInterrupted("A trigger blocked it.")

        with patch("actions.registry.get_action", return_value=stub_action):
            execute_action(session, action="equip", kwargs={})

        payload = _result_payload(session)
        self.assertEqual(payload["kwargs"]["success"], False)
        self.assertEqual(payload["kwargs"]["message"], "A trigger blocked it.")

    def test_non_int_id_kwarg_passes_through(self) -> None:
        """Keys ending in ``_id`` with non-int values are not resolved.

        The wire format is documented as int-only for ``*_id`` keys; anything
        else (e.g., a slug) is passed through unchanged. This guards against
        the resolver eating string-id-shaped values that the action can
        handle directly.
        """
        actor = MagicMock()
        session = _make_session(puppet=actor)
        stub_action = MagicMock()
        stub_action.objectdb_target_kwargs = frozenset({"identifier"})
        stub_action.run.return_value = ActionResult(success=True)

        with (
            patch("actions.registry.get_action", return_value=stub_action),
            patch("evennia.objects.models.ObjectDB.objects.get") as get,
        ):
            execute_action(session, action="custom", kwargs={"identifier_id": "some-slug"})

        get.assert_not_called()
        stub_action.run.assert_called_once_with(actor, identifier_id="some-slug")

    def test_undeclared_id_kwarg_passes_through_unresolved(self) -> None:
        """Keys ending in ``_id`` not declared on the action are passed through raw.

        This is the regression test for C1: the frontend sends ``outfit_id`` for
        ``apply_outfit``, but Outfit is not an ObjectDB. With the opt-in
        resolver, ``outfit_id`` arrives at the action unchanged (so it can look
        up ``Outfit.objects.get(pk=...)`` itself).
        """
        actor = MagicMock()
        session = _make_session(puppet=actor)
        stub_action = MagicMock()
        # apply_outfit does NOT declare outfit in objectdb_target_kwargs.
        stub_action.objectdb_target_kwargs = frozenset()
        stub_action.run.return_value = ActionResult(success=True)

        with (
            patch("actions.registry.get_action", return_value=stub_action),
            patch("evennia.objects.models.ObjectDB.objects.get") as get,
        ):
            execute_action(session, action="apply_outfit", kwargs={"outfit_id": 42})

        # Resolver did NOT touch the int — kwarg arrives raw.
        get.assert_not_called()
        stub_action.run.assert_called_once_with(actor, outfit_id=42)


class ApplyOutfitInputfuncIntegrationTests(TestCase):
    """End-to-end smoke test: ``apply_outfit`` via the real inputfunc + real action.

    This is the regression test for C1 (the resolver was eating ``outfit_id``
    because it ended in ``_id`` and Outfit isn't an ObjectDB). Without the
    opt-in resolver, this test would either explode with ``ObjectDB.DoesNotExist``
    or with the inputfunc sending ``"Wear which outfit?"`` because ``outfit``
    arrived as ``None``.
    """

    def test_apply_outfit_via_inputfunc_equips_items(self) -> None:
        """Real inputfunc + real ApplyOutfitAction → outfit pieces equipped."""
        from evennia_extensions.factories import (
            AccountFactory,
            CharacterFactory,
            ObjectDBFactory,
        )
        from world.character_sheets.factories import CharacterSheetFactory
        from world.items.constants import BodyRegion, EquipmentLayer
        from world.items.factories import (
            ItemInstanceFactory,
            ItemTemplateFactory,
            OutfitFactory,
            OutfitSlotFactory,
            TemplateSlotFactory,
        )
        from world.items.models import EquippedItem

        room = ObjectDBFactory(
            db_key="InputfuncApplyOutfitRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        account = AccountFactory(username="inputfunc_apply_outfit_account")
        actor = CharacterFactory(db_key="InputfuncApplyOutfitChar", location=room)
        actor.db_account = account
        actor.save()
        sheet = CharacterSheetFactory(character=actor)

        wardrobe_template = ItemTemplateFactory(
            name="InputfuncApplyOutfitWardrobe",
            is_wardrobe=True,
            is_container=True,
        )
        wardrobe_obj = ObjectDBFactory(
            db_key="InputfuncApplyOutfitWardrobeObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        wardrobe_obj.location = room
        wardrobe_obj.save()
        wardrobe = ItemInstanceFactory(template=wardrobe_template, game_object=wardrobe_obj)

        shirt_template = ItemTemplateFactory(name="InputfuncApplyOutfitShirt")
        TemplateSlotFactory(
            template=shirt_template,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )
        shirt_obj = ObjectDBFactory(
            db_key="InputfuncApplyOutfitShirtObj",
            db_typeclass_path="typeclasses.objects.Object",
        )
        shirt_obj.location = actor
        shirt_obj.save()
        shirt = ItemInstanceFactory(template=shirt_template, game_object=shirt_obj)

        outfit = OutfitFactory(
            character_sheet=sheet,
            wardrobe=wardrobe,
            name="InputfuncApplyOutfitLook",
        )
        OutfitSlotFactory(
            outfit=outfit,
            item_instance=shirt,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.BASE,
        )

        session = _make_session(puppet=actor)
        with patch.object(room, "msg_contents"):
            execute_action(session, action="apply_outfit", kwargs={"outfit_id": outfit.pk})

        payload = _result_payload(session)
        self.assertEqual(payload["type"], WebsocketMessageType.ACTION_RESULT.value)
        self.assertTrue(
            payload["kwargs"]["success"],
            f"Expected success, got: {payload['kwargs']}",
        )
        self.assertTrue(EquippedItem.objects.filter(character=actor, item_instance=shirt).exists())
