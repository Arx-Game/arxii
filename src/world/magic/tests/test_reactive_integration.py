"""Integration tests for reactive event emission in magic services.

All scenarios exercise the unified-dispatch model: ``emit_event(name, payload,
location)`` gathers triggers from the room and its contents, sorts by priority
desc, and dispatches on a single FlowStack. Self-targeting is expressed as a
filter (``SELF_FILTER``) rather than an old PERSONAL scope.

Tests verify:
- TECHNIQUE_PRE_CAST emitted before resolution
- TECHNIQUE_PRE_CAST cancellation prevents cast (no resolution, anima not deducted)
- TECHNIQUE_CAST emitted after successful resolution
- TECHNIQUE_AFFECTED emitted per target when targets provided
- TECHNIQUE_AFFECTED has correct target and effect
"""

from unittest.mock import MagicMock

from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import CharacterFactory
from flows.constants import EventName
from flows.consts import FlowActionChoices
from flows.events.payloads import (
    TechniqueAffectedPayload,
    TechniqueCastPayload,
    TechniquePreCastPayload,
)
from flows.factories import FlowDefinitionFactory, FlowStepDefinitionFactory
from world.conditions.factories import ReactiveConditionFactory
from world.magic.factories import (
    CharacterAnimaFactory,
    TechniqueFactory,
)
from world.magic.services import use_technique
from world.mechanics.factories import CharacterEngagementFactory

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


SELF_FILTER = {"path": "caster", "op": "==", "value": "self"}


def _create_room(key: str = "TestRoom") -> ObjectDB:
    return ObjectDB.objects.create(
        db_key=key,
        db_typeclass_path="typeclasses.rooms.Room",
    )


def _make_cancel_flow():
    """Return a FlowDefinition with a single CANCEL_EVENT step."""
    flow = FlowDefinitionFactory()
    FlowStepDefinitionFactory(
        flow=flow,
        parent_id=None,
        action=FlowActionChoices.CANCEL_EVENT,
        parameters={},
    )
    return flow


def _setup_caster(room=None):
    """Return (character, anima) with a controlled technique ready."""
    anima = CharacterAnimaFactory(current=20, maximum=20)
    char = anima.character
    CharacterEngagementFactory(character=char)
    if room is not None:
        char.location = room
    return char, anima


# ---------------------------------------------------------------------------
# TECHNIQUE_PRE_CAST / TECHNIQUE_CAST emission
# ---------------------------------------------------------------------------


class TechniquePreCastEmissionTest(TestCase):
    """use_technique emits TECHNIQUE_PRE_CAST then TECHNIQUE_CAST."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.technique = TechniqueFactory(intensity=5, control=10, anima_cost=3)

    def setUp(self) -> None:
        self.room = _create_room()
        self.char, self.anima = _setup_caster(room=self.room)

    def test_pre_cast_emitted(self) -> None:
        captured: list[tuple[str, object]] = []

        import world.magic.services.techniques as svc_mod

        original = svc_mod.emit_event

        def capturing(name, payload, **kw):
            captured.append((name, payload))
            return original(name, payload, **kw)

        svc_mod.emit_event = capturing
        try:
            use_technique(
                character=self.char,
                technique=self.technique,
                resolve_fn=MagicMock(return_value="result"),
            )
        finally:
            svc_mod.emit_event = original

        names = [n for n, _ in captured]
        self.assertIn(EventName.TECHNIQUE_PRE_CAST, names)

    def test_pre_cast_payload_correct(self) -> None:
        captured: list[TechniquePreCastPayload] = []

        import world.magic.services.techniques as svc_mod

        original = svc_mod.emit_event

        def capturing(name, payload, **kw):
            if name == EventName.TECHNIQUE_PRE_CAST:
                captured.append(payload)
            return original(name, payload, **kw)

        svc_mod.emit_event = capturing
        try:
            use_technique(
                character=self.char,
                technique=self.technique,
                resolve_fn=MagicMock(return_value="result"),
            )
        finally:
            svc_mod.emit_event = original

        self.assertEqual(len(captured), 1)
        p = captured[0]
        self.assertIsInstance(p, TechniquePreCastPayload)
        self.assertIs(p.caster, self.char)
        self.assertIs(p.technique, self.technique)

    def test_pre_cast_then_cast_order(self) -> None:
        order: list[str] = []

        import world.magic.services.techniques as svc_mod

        original = svc_mod.emit_event

        def ordering(name, payload, **kw):
            if name in (EventName.TECHNIQUE_PRE_CAST, EventName.TECHNIQUE_CAST):
                order.append(name)
            return original(name, payload, **kw)

        svc_mod.emit_event = ordering
        try:
            use_technique(
                character=self.char,
                technique=self.technique,
                resolve_fn=MagicMock(return_value="result"),
            )
        finally:
            svc_mod.emit_event = original

        self.assertIn(EventName.TECHNIQUE_PRE_CAST, order)
        self.assertIn(EventName.TECHNIQUE_CAST, order)
        self.assertLess(
            order.index(EventName.TECHNIQUE_PRE_CAST),
            order.index(EventName.TECHNIQUE_CAST),
        )

    def test_cast_payload_has_result(self) -> None:
        captured: list[TechniqueCastPayload] = []
        mock_result = MagicMock(return_value="cast_result")

        import world.magic.services.techniques as svc_mod

        original = svc_mod.emit_event

        def capturing(name, payload, **kw):
            if name == EventName.TECHNIQUE_CAST:
                captured.append(payload)
            return original(name, payload, **kw)

        svc_mod.emit_event = capturing
        try:
            use_technique(
                character=self.char,
                technique=self.technique,
                resolve_fn=mock_result,
            )
        finally:
            svc_mod.emit_event = original

        self.assertEqual(len(captured), 1)
        p = captured[0]
        self.assertIsInstance(p, TechniqueCastPayload)
        self.assertIs(p.caster, self.char)
        self.assertIs(p.technique, self.technique)
        self.assertIsNotNone(p.result)


# ---------------------------------------------------------------------------
# PRE cancellation
# ---------------------------------------------------------------------------


class TechniquePreCastCancellationTest(TestCase):
    """Cancelling TECHNIQUE_PRE_CAST prevents cast (no anima deducted, no resolution).

    The trigger is attached to the caster and filters on ``caster == self`` so
    it fires only when this specific caster is the one using a technique.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.technique = TechniqueFactory(intensity=5, control=10, anima_cost=3)

    def setUp(self) -> None:
        self.room = _create_room()
        self.char, self.anima = _setup_caster(room=self.room)

    def test_cancel_returns_not_confirmed(self) -> None:
        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.TECHNIQUE_PRE_CAST,
            filter_condition=SELF_FILTER,
            flow_definition=cancel_flow,
            target=self.char,
        )

        mock_resolve = MagicMock(return_value="result")
        result = use_technique(
            character=self.char,
            technique=self.technique,
            resolve_fn=mock_resolve,
        )

        self.assertFalse(result.confirmed)
        mock_resolve.assert_not_called()

    def test_cancel_does_not_deduct_anima(self) -> None:
        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.TECHNIQUE_PRE_CAST,
            filter_condition=SELF_FILTER,
            flow_definition=cancel_flow,
            target=self.char,
        )
        initial_anima = self.anima.current

        use_technique(
            character=self.char,
            technique=self.technique,
            resolve_fn=MagicMock(return_value="result"),
        )

        self.anima.refresh_from_db()
        self.assertEqual(self.anima.current, initial_anima)

    def test_technique_cast_not_emitted_on_cancel(self) -> None:
        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.TECHNIQUE_PRE_CAST,
            filter_condition=SELF_FILTER,
            flow_definition=cancel_flow,
            target=self.char,
        )
        cast_fired: list[bool] = []

        import world.magic.services.techniques as svc_mod

        original = svc_mod.emit_event

        def capturing(name, payload, **kw):
            if name == EventName.TECHNIQUE_CAST:
                cast_fired.append(True)
            return original(name, payload, **kw)

        svc_mod.emit_event = capturing
        try:
            use_technique(
                character=self.char,
                technique=self.technique,
                resolve_fn=MagicMock(return_value="result"),
            )
        finally:
            svc_mod.emit_event = original

        self.assertEqual(cast_fired, [])


# ---------------------------------------------------------------------------
# TECHNIQUE_AFFECTED per-target emission
# ---------------------------------------------------------------------------


class TechniqueAffectedEmissionTest(TestCase):
    """use_technique emits TECHNIQUE_AFFECTED for each target when targets provided."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.technique = TechniqueFactory(intensity=5, control=10, anima_cost=3)

    def setUp(self) -> None:
        self.room = _create_room()
        self.char, self.anima = _setup_caster(room=self.room)
        self.target1 = CharacterFactory()
        self.target1.location = self.room
        self.target2 = CharacterFactory()
        self.target2.location = self.room

    def test_affected_emitted_per_target(self) -> None:
        captured: list[TechniqueAffectedPayload] = []

        import world.magic.services.techniques as svc_mod

        original = svc_mod.emit_event

        def capturing(name, payload, **kw):
            if name == EventName.TECHNIQUE_AFFECTED:
                captured.append(payload)
            return original(name, payload, **kw)

        svc_mod.emit_event = capturing
        try:
            use_technique(
                character=self.char,
                technique=self.technique,
                resolve_fn=MagicMock(return_value="result"),
                targets=[self.target1, self.target2],
            )
        finally:
            svc_mod.emit_event = original

        self.assertEqual(len(captured), 2)

    def test_affected_payload_has_correct_targets(self) -> None:
        captured: list[TechniqueAffectedPayload] = []

        import world.magic.services.techniques as svc_mod

        original = svc_mod.emit_event

        def capturing(name, payload, **kw):
            if name == EventName.TECHNIQUE_AFFECTED:
                captured.append(payload)
            return original(name, payload, **kw)

        svc_mod.emit_event = capturing
        try:
            use_technique(
                character=self.char,
                technique=self.technique,
                resolve_fn=MagicMock(return_value="result"),
                targets=[self.target1, self.target2],
            )
        finally:
            svc_mod.emit_event = original

        captured_targets = {p.target for p in captured}
        self.assertIn(self.target1, captured_targets)
        self.assertIn(self.target2, captured_targets)

    def test_affected_not_emitted_without_targets(self) -> None:
        """When no targets passed, TECHNIQUE_AFFECTED is not emitted."""
        fired: list[bool] = []

        import world.magic.services.techniques as svc_mod

        original = svc_mod.emit_event

        def capturing(name, payload, **kw):
            if name == EventName.TECHNIQUE_AFFECTED:
                fired.append(True)
            return original(name, payload, **kw)

        svc_mod.emit_event = capturing
        try:
            use_technique(
                character=self.char,
                technique=self.technique,
                resolve_fn=MagicMock(return_value="result"),
            )
        finally:
            svc_mod.emit_event = original

        self.assertEqual(fired, [])

    def test_affected_payload_has_caster_and_technique(self) -> None:
        captured: list[TechniqueAffectedPayload] = []

        import world.magic.services.techniques as svc_mod

        original = svc_mod.emit_event

        def capturing(name, payload, **kw):
            if name == EventName.TECHNIQUE_AFFECTED:
                captured.append(payload)
            return original(name, payload, **kw)

        svc_mod.emit_event = capturing
        try:
            use_technique(
                character=self.char,
                technique=self.technique,
                resolve_fn=MagicMock(return_value="result"),
                targets=[self.target1],
            )
        finally:
            svc_mod.emit_event = original

        self.assertEqual(len(captured), 1)
        p = captured[0]
        self.assertIs(p.caster, self.char)
        self.assertIs(p.technique, self.technique)
        self.assertIs(p.target, self.target1)
