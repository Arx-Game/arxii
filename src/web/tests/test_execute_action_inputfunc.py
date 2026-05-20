"""Tests for the ``execute_action`` websocket inputfunc.

The inputfunc is the unified web entry point for game mutations: the React
frontend sends an inbound ``execute_action`` message, the inputfunc resolves
the action key and any ``*_id`` kwargs to model instances, runs the action
on the session's puppeted character, and pushes back an ``ACTION_RESULT``
message. This module exercises the puppet/lookup/dispatch glue with mocks
so the contract stays stable as actions are added or modified.

Phase 3 / Task 15 extended this to route through the unified
``dispatch_player_action`` function — the new unified shape
``{ref: {...}, kwargs: {...}}`` normalises alongside the legacy
``{action: key, kwargs: {...}}`` shape into a single dispatch path.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.constants import ActionBackend
from actions.errors import ActionDispatchError
from actions.types import ActionInterrupted, ActionResult, DispatchResult
from server.conf.inputfuncs import execute_action
from web.webclient.message_types import WebsocketMessageType


class _StubActor:
    """Minimal stub actor for unit tests that don't need a real CharacterSheet.

    ``dispatch_player_action`` accesses ``character.sheet_data`` to resolve the
    character sheet.  Raising ``AttributeError`` (which ``RelatedObjectDoesNotExist``
    subclasses) makes ``_get_character_sheet`` return ``None`` — skipping any
    round-context DB queries that would otherwise try to filter on a stub PK.
    """

    @property
    def sheet_data(self) -> None:  # type: ignore[return]
        msg = "no sheet"
        raise AttributeError(msg)


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
        actor = _StubActor()
        session = _make_session(puppet=actor)
        with patch("actions.registry.get_action") as get_action:
            execute_action(session, kwargs={})
        get_action.assert_not_called()
        payload = _result_payload(session)
        self.assertEqual(payload["kwargs"]["success"], False)
        self.assertIn("No action specified", payload["kwargs"]["message"])

    def test_unknown_action_key_sends_error(self) -> None:
        """An unknown action key returns a structured error without dispatching."""
        actor = _StubActor()
        session = _make_session(puppet=actor)
        with patch("actions.registry.get_action", return_value=None):
            execute_action(session, action="not_a_real_action", kwargs={})
        payload = _result_payload(session)
        self.assertEqual(payload["kwargs"]["success"], False)
        self.assertIn("Unknown action", payload["kwargs"]["message"])
        self.assertIn("not_a_real_action", payload["kwargs"]["message"])

    def test_happy_path_runs_action_and_returns_result(self) -> None:
        """Valid action key + kwargs routes through dispatch_player_action and returns result.

        The inputfunc now routes through ``dispatch_player_action`` (the unified
        write path).  The ACTION_RESULT contract — ``{success, message, data}`` — is
        unchanged; only the dispatch chain is deeper.
        """
        actor = _StubActor()
        session = _make_session(puppet=actor)
        dispatch_result = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=True, message="You equip it.", data={"slot": "torso"}),
        )
        stub_action = MagicMock()
        stub_action.objectdb_target_kwargs = frozenset()

        with (
            patch("actions.registry.get_action", return_value=stub_action),
            patch("actions.player_interface.dispatch_player_action", return_value=dispatch_result),
        ):
            execute_action(session, action="equip", kwargs={"slot": "torso"})

        payload = _result_payload(session)
        self.assertEqual(payload["type"], WebsocketMessageType.ACTION_RESULT.value)
        self.assertEqual(payload["kwargs"]["success"], True)
        self.assertEqual(payload["kwargs"]["message"], "You equip it.")
        self.assertEqual(payload["kwargs"]["data"], {"slot": "torso"})

    def test_object_id_kwarg_is_resolved(self) -> None:
        """Keys ending in ``_id`` whose stripped name is declared on the action are resolved.

        Resolution happens in the inputfunc before calling ``dispatch_player_action``.
        The dispatch path receives the resolved ObjectDB instance (not the raw int).
        Verified by checking what kwargs are passed to ``dispatch_player_action``.
        """
        actor = _StubActor()
        session = _make_session(puppet=actor)
        target_obj = MagicMock(name="resolved_target")
        stub_action = MagicMock()
        stub_action.objectdb_target_kwargs = frozenset({"target"})
        dispatch_result = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=True),
        )

        with (
            patch("actions.registry.get_action", return_value=stub_action),
            patch("evennia.objects.models.ObjectDB.objects.get", return_value=target_obj) as get,
            patch(
                "actions.player_interface.dispatch_player_action",
                return_value=dispatch_result,
            ) as mock_dispatch,
        ):
            execute_action(session, action="give", kwargs={"target_id": 42})

        get.assert_called_once_with(pk=42)
        # dispatch_player_action receives the resolved object (not the raw int).
        _, _, passed_kwargs = mock_dispatch.call_args.args
        self.assertIn("target", passed_kwargs)
        self.assertEqual(passed_kwargs["target"], target_obj)
        self.assertNotIn("target_id", passed_kwargs)

    def test_object_id_not_found_sends_error(self) -> None:
        """An unresolvable object id sends an error and does not run the action."""
        from evennia.objects.models import ObjectDB

        actor = _StubActor()
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
        """ActionInterrupted from action.run is forwarded as a failure response.

        ``ActionInterrupted`` can bubble up from within ``dispatch_player_action``
        (raised by ``action.run`` inside the REGISTRY branch).  The inputfunc
        catches it and sends a failure response, preserving the original behavior.
        """
        actor = _StubActor()
        session = _make_session(puppet=actor)
        stub_action = MagicMock()
        stub_action.objectdb_target_kwargs = frozenset()

        with (
            patch("actions.registry.get_action", return_value=stub_action),
            patch(
                "actions.player_interface.dispatch_player_action",
                side_effect=ActionInterrupted("A trigger blocked it."),
            ),
        ):
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
        actor = _StubActor()
        session = _make_session(puppet=actor)
        stub_action = MagicMock()
        stub_action.objectdb_target_kwargs = frozenset({"identifier"})
        dispatch_result = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=True),
        )

        with (
            patch("actions.registry.get_action", return_value=stub_action),
            patch("evennia.objects.models.ObjectDB.objects.get") as get,
            patch(
                "actions.player_interface.dispatch_player_action",
                return_value=dispatch_result,
            ) as mock_dispatch,
        ):
            execute_action(session, action="custom", kwargs={"identifier_id": "some-slug"})

        get.assert_not_called()
        # Non-int id kwargs pass through unresolved to dispatch_player_action.
        _, _, passed_kwargs = mock_dispatch.call_args.args
        self.assertEqual(passed_kwargs.get("identifier_id"), "some-slug")

    def test_undeclared_id_kwarg_passes_through_unresolved(self) -> None:
        """Keys ending in ``_id`` not declared on the action are passed through raw.

        This is the regression test for C1: the frontend sends ``outfit_id`` for
        ``apply_outfit``, but Outfit is not an ObjectDB. With the opt-in
        resolver, ``outfit_id`` arrives at the action unchanged (so it can look
        up ``Outfit.objects.get(pk=...)`` itself).
        """
        actor = _StubActor()
        session = _make_session(puppet=actor)
        stub_action = MagicMock()
        # apply_outfit does NOT declare outfit in objectdb_target_kwargs.
        stub_action.objectdb_target_kwargs = frozenset()
        dispatch_result = DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=True),
        )

        with (
            patch("actions.registry.get_action", return_value=stub_action),
            patch("evennia.objects.models.ObjectDB.objects.get") as get,
            patch(
                "actions.player_interface.dispatch_player_action",
                return_value=dispatch_result,
            ) as mock_dispatch,
        ):
            execute_action(session, action="apply_outfit", kwargs={"outfit_id": 42})

        # Resolver did NOT touch the int — outfit_id arrives raw at dispatch.
        get.assert_not_called()
        _, _, passed_kwargs = mock_dispatch.call_args.args
        self.assertEqual(passed_kwargs.get("outfit_id"), 42)
        self.assertNotIn("outfit", passed_kwargs)


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


class UnifiedDispatchPathTests(TestCase):
    """Tests for the unified ``dispatch_player_action`` routing added in Phase 3 / Task 15.

    Verifies that:
    - The new ``{ref: {...}, kwargs: {...}}`` unified shape dispatches via
      ``dispatch_player_action``.
    - The legacy ``{action: key, kwargs: {...}}`` shape is *normalised* into
      the same ``dispatch_player_action`` path (no separate dispatch branch).
    - An ``ActionDispatchError`` from ``dispatch_player_action`` maps to
      ``{success: False, message: exc.user_message}`` — never ``str(exc)``
      or a raw traceback.
    - The ``objectdb_target_kwargs`` ``_id`` → ObjectDB resolution is preserved
      for registry actions dispatched through the unified path.
    """

    def _stub_dispatch_result(
        self,
        message: str = "You equip it.",
        data: dict | None = None,
    ) -> DispatchResult:
        """Build a REGISTRY DispatchResult wrapping an ActionResult."""
        return DispatchResult(
            backend=ActionBackend.REGISTRY,
            deferred=False,
            detail=ActionResult(success=True, message=message, data=data or {}),
        )

    # ------------------------------------------------------------------
    # New unified shape: {ref: {backend, registry_key}, kwargs: {...}}
    # ------------------------------------------------------------------

    def test_unified_ref_shape_dispatches_via_dispatch_player_action(self) -> None:
        """The new ``{ref: {backend, registry_key}, kwargs}`` payload reaches
        ``dispatch_player_action`` and returns a success ACTION_RESULT."""
        actor = MagicMock()
        session = _make_session(puppet=actor)
        dispatch_result = self._stub_dispatch_result("You equip it.", {"slot": "torso"})

        stub_registry = MagicMock(objectdb_target_kwargs=frozenset())
        with (
            patch(
                "actions.player_interface.dispatch_player_action",
                return_value=dispatch_result,
            ) as mock_dispatch,
            patch("actions.registry.get_action", return_value=stub_registry),
        ):
            execute_action(
                session,
                ref={"backend": "registry", "registry_key": "equip"},
                kwargs={"slot": "torso"},
            )

        # dispatch_player_action must have been called (unified path used)
        mock_dispatch.assert_called_once()
        payload = _result_payload(session)
        self.assertEqual(payload["type"], WebsocketMessageType.ACTION_RESULT.value)
        self.assertTrue(payload["kwargs"]["success"])
        self.assertEqual(payload["kwargs"]["message"], "You equip it.")
        self.assertEqual(payload["kwargs"]["data"], {"slot": "torso"})

    # ------------------------------------------------------------------
    # Legacy shape: {action: key, kwargs: {...}} normalised to same path
    # ------------------------------------------------------------------

    def test_legacy_shape_normalises_to_same_dispatch_player_action_path(self) -> None:
        """The legacy ``{action: key}`` shape is normalised into
        ``dispatch_player_action`` — the same path as the unified shape.

        Both shapes must produce identical ACTION_RESULT payloads.
        """
        actor = MagicMock()
        dispatch_result = self._stub_dispatch_result("You equip it.", {"slot": "torso"})

        stub_registry = MagicMock(objectdb_target_kwargs=frozenset())

        # --- unified shape ---
        session_unified = _make_session(puppet=actor)
        with (
            patch(
                "actions.player_interface.dispatch_player_action",
                return_value=dispatch_result,
            ),
            patch("actions.registry.get_action", return_value=stub_registry),
        ):
            execute_action(
                session_unified,
                ref={"backend": "registry", "registry_key": "equip"},
                kwargs={"slot": "torso"},
            )

        # --- legacy shape ---
        session_legacy = _make_session(puppet=actor)
        with (
            patch(
                "actions.player_interface.dispatch_player_action",
                return_value=dispatch_result,
            ),
            patch("actions.registry.get_action", return_value=stub_registry),
        ):
            execute_action(session_legacy, action="equip", kwargs={"slot": "torso"})

        # Both should produce identical payloads
        unified_payload = _result_payload(session_unified)
        legacy_payload = _result_payload(session_legacy)
        self.assertEqual(unified_payload["kwargs"], legacy_payload["kwargs"])
        self.assertTrue(legacy_payload["kwargs"]["success"])

    # ------------------------------------------------------------------
    # ActionDispatchError → safe user_message, not str(exc)
    # ------------------------------------------------------------------

    def test_dispatch_error_maps_to_safe_user_message_not_str_exc(self) -> None:
        """``ActionDispatchError`` raised by ``dispatch_player_action`` maps to
        ``{success: False, message: exc.user_message}`` — never ``str(exc)``
        (which would be the opaque code string, not a user-safe message).
        """
        actor = MagicMock()
        session = _make_session(puppet=actor)
        err = ActionDispatchError(ActionDispatchError.UNKNOWN_ACTION_REF)
        safe_msg = err.user_message  # "That action is no longer available."

        stub_registry = MagicMock(objectdb_target_kwargs=frozenset())
        with (
            patch(
                "actions.player_interface.dispatch_player_action",
                side_effect=err,
            ),
            patch("actions.registry.get_action", return_value=stub_registry),
        ):
            execute_action(session, action="equip", kwargs={})

        payload = _result_payload(session)
        self.assertEqual(payload["kwargs"]["success"], False)
        # Must be the user_message, NOT str(exc) which would be the raw code string
        self.assertEqual(payload["kwargs"]["message"], safe_msg)
        self.assertNotEqual(payload["kwargs"]["message"], str(err))
        self.assertIsNone(payload["kwargs"]["data"])

    # ------------------------------------------------------------------
    # objectdb_target_kwargs resolution preserved in unified path
    # ------------------------------------------------------------------

    def test_objectdb_resolution_still_happens_before_unified_dispatch(self) -> None:
        """``_id``-suffixed kwargs declared in ``objectdb_target_kwargs`` are still
        resolved to ObjectDB instances before calling ``dispatch_player_action``.

        The registry action's ``objectdb_target_kwargs`` is read from the ``Action``
        object so the resolver knows which ``_id`` args to resolve. The resolved
        object (not the raw int) must be passed to ``dispatch_player_action``.
        """
        actor = MagicMock()
        session = _make_session(puppet=actor)
        target_obj = MagicMock(name="resolved_target")
        dispatch_result = self._stub_dispatch_result()

        stub_action = MagicMock()
        stub_action.objectdb_target_kwargs = frozenset({"target"})

        with (
            patch("actions.registry.get_action", return_value=stub_action),
            patch("evennia.objects.models.ObjectDB.objects.get", return_value=target_obj) as db_get,
            patch(
                "actions.player_interface.dispatch_player_action",
                return_value=dispatch_result,
            ) as mock_dispatch,
        ):
            execute_action(session, action="give", kwargs={"target_id": 42})

        # ObjectDB lookup must have fired
        db_get.assert_called_once_with(pk=42)
        # dispatch_player_action receives the resolved object (not the raw int).
        # dispatch_player_action(actor, ref, kwargs) — kwargs is the 3rd positional.
        passed_kwargs = mock_dispatch.call_args.args[2]
        self.assertIn("target", passed_kwargs)
        self.assertEqual(passed_kwargs["target"], target_obj)
        self.assertNotIn("target_id", passed_kwargs)
