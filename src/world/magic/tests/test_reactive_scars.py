"""Reactive scars for magic and perception events.

All scenarios exercise the unified-dispatch model: ``emit_event(name, payload,
location)`` gathers triggers from the room and its contents, sorts by priority
desc, and dispatches on a single FlowStack. Self-targeting is expressed as a
filter (``SELF_FILTER``) rather than an old PERSONAL scope.

Tests use SimpleNamespace stubs for the Technique ref because the real affinity
path (technique.gift.resonances → affinity) crosses an M2M boundary that the
filter DSL cannot traverse. Tests that require frozen-payload mutation or
schema additions remain skipped with explanatory notes.
"""

from types import SimpleNamespace

from django.test import TestCase
from evennia.objects.models import ObjectDB

from evennia_extensions.factories import CharacterFactory
from flows.constants import EventName
from flows.consts import FlowActionChoices
from flows.emit import emit_event
from flows.events.payloads import DamagePreApplyPayload, DamageSource
from flows.factories import FlowDefinitionFactory, FlowStepDefinitionFactory
from world.conditions.factories import ReactiveConditionFactory
from world.magic.factories import TechniqueFactory
from world.mechanics.factories import PropertyFactory

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


SELF_FILTER = {"path": "target", "op": "==", "value": "self"}


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


def _source_technique_with_affinity(affinity_name: str):
    """Return a DamageSource(type='technique') with stub ref.affinity attribute."""
    ref = SimpleNamespace(affinity=affinity_name)
    return DamageSource(type="technique", ref=ref)


def _source_technique_with_resonance(resonance_name: str):
    """Return a DamageSource(type='technique') with stub ref.resonance attribute."""
    ref = SimpleNamespace(resonance=resonance_name)
    return DamageSource(type="technique", ref=ref)


# ---------------------------------------------------------------------------
# Examine / perception scars (Mage Sight, Soul Sight)
# ---------------------------------------------------------------------------


class MageSightScarTest(TestCase):
    """ "Mage Sight" scar appends scar description to return_appearance output
    ONLY for targets whose primary persona carries the 'abyssal' Property tag.

    The scar is modelled as an EXAMINE_PRE handler: the flow appends to the
    mutable ``sections`` list on ``ExaminePrePayload``.  After emit_event
    returns, ``return_appearance`` concatenates those sections onto the base
    appearance string.
    """

    def setUp(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory

        self.room = _create_room("MageSightRoom")

        # Create three characters, each with a sheet + primary persona.
        observer_sheet = CharacterSheetFactory()
        abyssal_sheet = CharacterSheetFactory()
        plain_sheet = CharacterSheetFactory()

        self.observer = observer_sheet.character
        self.abyssal_target = abyssal_sheet.character
        self.plain_target = plain_sheet.character

        for c in (self.observer, self.abyssal_target, self.plain_target):
            c.location = self.room

        # Tag abyssal_target's primary persona with the 'abyssal' Property.
        abyssal_prop = PropertyFactory(name="abyssal")
        abyssal_sheet.primary_persona.properties.add(abyssal_prop)

        # Build the scar flow: MODIFY_PAYLOAD appends a section to sections list.
        flow = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=flow,
            parent_id=None,
            action=FlowActionChoices.MODIFY_PAYLOAD,
            parameters={
                "field": "sections",
                "op": "add",
                "value": ["Your mage sight burns: abyssal."],
            },
        )

        # Wire the scar onto the observer: fires on EXAMINE_PRE when the target
        # has the 'abyssal' Property (via Character.has_property).
        ReactiveConditionFactory(
            event_name=EventName.EXAMINE_PRE,
            filter_condition={"path": "target", "op": "has_property", "value": "abyssal"},
            flow_definition=flow,
            target=self.observer,
        )
        # Invalidate the trigger cache so the new reactive condition is picked up.
        self.observer.trigger_handler._populated = False

    def test_mage_sight_appends_to_abyssal_target(self) -> None:
        """Examining an abyssal-tagged target appends the scar section to the output."""
        result = self.abyssal_target.return_appearance(self.observer)
        self.assertIn("mage sight burns", result)

    def test_near_miss_non_abyssal_target_unchanged(self) -> None:
        """Examining a non-abyssal target does not trigger the scar — output unchanged."""
        result = self.plain_target.return_appearance(self.observer)
        self.assertNotIn("mage sight burns", result)


class SoulSightScarTest(TestCase):
    """ "Soul Sight" scar appends a revealing line to return_appearance output
    ONLY for targets whose primary persona carries the 'masked-identity' Property tag.

    The scar is modelled as an EXAMINE_PRE handler: the flow appends to the
    mutable ``sections`` list on ``ExaminePrePayload``.  After emit_event
    returns, ``return_appearance`` concatenates those sections onto the base
    appearance string.
    """

    def setUp(self) -> None:
        from world.character_sheets.factories import CharacterSheetFactory

        self.room = _create_room("SoulSightRoom")

        # Create three characters, each with a sheet + primary persona.
        observer_sheet = CharacterSheetFactory()
        masked_sheet = CharacterSheetFactory()
        plain_sheet = CharacterSheetFactory()

        self.observer = observer_sheet.character
        self.masked_target = masked_sheet.character
        self.plain_target = plain_sheet.character

        for c in (self.observer, self.masked_target, self.plain_target):
            c.location = self.room

        # Tag masked_target's primary persona with the 'masked-identity' Property.
        masked_prop = PropertyFactory(name="masked-identity")
        masked_sheet.primary_persona.properties.add(masked_prop)

        # Build the scar flow: MODIFY_PAYLOAD appends a section to sections list.
        flow = FlowDefinitionFactory()
        FlowStepDefinitionFactory(
            flow=flow,
            parent_id=None,
            action=FlowActionChoices.MODIFY_PAYLOAD,
            parameters={
                "field": "sections",
                "op": "add",
                "value": ["Soul sight pierces the mask."],
            },
        )

        # Wire the scar onto the observer: fires on EXAMINE_PRE when the target
        # has the 'masked-identity' Property (via Character.has_property).
        ReactiveConditionFactory(
            event_name=EventName.EXAMINE_PRE,
            filter_condition={
                "path": "target",
                "op": "has_property",
                "value": "masked-identity",
            },
            flow_definition=flow,
            target=self.observer,
        )
        # Invalidate the trigger cache so the new reactive condition is picked up.
        self.observer.trigger_handler._populated = False

    def test_soul_sight_reveals_masked_identity(self) -> None:
        """Examining a masked-identity target appends the scar section to the output."""
        result = self.masked_target.return_appearance(self.observer)
        self.assertIn("Soul sight pierces", result)

    def test_near_miss_unmasked_target_unchanged(self) -> None:
        """Examining an unmasked target does not trigger the scar — output unchanged."""
        result = self.plain_target.return_appearance(self.observer)
        self.assertNotIn("Soul sight pierces", result)


# ---------------------------------------------------------------------------
# Affinity/resonance layering
# ---------------------------------------------------------------------------


class AffinityBroadVsResonanceNarrowTest(TestCase):
    """Affinity-broad vs resonance-narrow filter discrimination.

    Two scars on the same character:
      - A broad ward: blocks any technique whose ``source.ref.affinity == "abyssal"``.
      - A narrow ward: blocks only when ``source.ref.resonance == "shadow"``.

    The affinity filter is evaluated via filter path ``source.ref.affinity``.
    The resonance filter is evaluated via filter path ``source.ref.resonance``.
    Both use SimpleNamespace stubs because the real DB path (technique → gift →
    resonances M2M → affinity) crosses an M2M that the filter DSL cannot traverse.
    """

    def setUp(self):
        self.room = _create_room("AffinityRoom")
        self.character = CharacterFactory()
        self.character.location = self.room

        # Broad affinity ward: cancels any abyssal technique
        self.broad_cancel = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition={
                "and": [
                    SELF_FILTER,
                    {"path": "source.ref.affinity", "op": "==", "value": "abyssal"},
                ]
            },
            flow_definition=self.broad_cancel,
            target=self.character,
        )

    def _emit(self, source):
        payload = DamagePreApplyPayload(
            target=self.character,
            amount=10,
            damage_type="arcane",
            source=source,
        )
        return emit_event(EventName.DAMAGE_PRE_APPLY, payload, location=self.room)

    def test_hit_affinity_broad_fires_on_abyssal(self):
        """Abyssal affinity matches the broad ward — dispatch is cancelled."""
        stack = self._emit(_source_technique_with_affinity("abyssal"))
        self.assertTrue(stack.was_cancelled())

    def test_near_miss_affinity_broad_misses_celestial(self):
        """Celestial affinity does not match the abyssal ward — passes through."""
        stack = self._emit(_source_technique_with_affinity("celestial"))
        self.assertFalse(stack.was_cancelled())

    def test_hit_resonance_narrow_fires_on_shadow(self):
        """Resonance-narrow filter fires only when resonance == 'shadow'."""
        # Add a resonance-narrow ward to the character
        narrow_cancel = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition={
                "and": [
                    SELF_FILTER,
                    {"path": "source.ref.resonance", "op": "==", "value": "shadow"},
                ]
            },
            flow_definition=narrow_cancel,
            target=self.character,
        )
        self.character.trigger_handler._populated = False

        stack = self._emit(_source_technique_with_resonance("shadow"))
        self.assertTrue(stack.was_cancelled())

    def test_near_miss_resonance_narrow_misses_flame(self):
        """Non-shadow resonance does not match the narrow ward."""
        narrow_cancel = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition={
                "and": [
                    SELF_FILTER,
                    {"path": "source.ref.resonance", "op": "==", "value": "shadow"},
                ]
            },
            flow_definition=narrow_cancel,
            target=self.character,
        )
        self.character.trigger_handler._populated = False

        stack = self._emit(_source_technique_with_resonance("flame"))
        # The stub ref has no `affinity`, so the broad ward's path is unresolved;
        # the narrow ward's resonance is "flame" != "shadow" → no match.
        self.assertFalse(stack.was_cancelled())


class PropertyTaggedTechniqueTest(TestCase):
    """Property-tagged technique — scar fires when technique carries a Property.

    A scar with filter ``{path: 'source.ref', op: 'has_property', value: 'cursed'}``
    fires on techniques that carry the ``cursed`` Property tag, and does NOT fire on
    techniques without it.
    """

    def setUp(self):
        self.room = _create_room("PropertyRoom")
        self.character = CharacterFactory()
        self.character.location = self.room

        self.cursed = PropertyFactory(name="cursed")

        cancel_flow = _make_cancel_flow()
        ReactiveConditionFactory(
            event_name=EventName.DAMAGE_PRE_APPLY,
            filter_condition={
                "and": [
                    SELF_FILTER,
                    {"path": "source.ref", "op": "has_property", "value": "cursed"},
                ]
            },
            flow_definition=cancel_flow,
            target=self.character,
        )

    def _emit(self, technique):
        payload = DamagePreApplyPayload(
            target=self.character,
            amount=10,
            damage_type="arcane",
            source=DamageSource(type="technique", ref=technique),
        )
        return emit_event(EventName.DAMAGE_PRE_APPLY, payload, location=self.room)

    def test_technique_with_property_fires_scar(self):
        """A technique carrying the 'cursed' Property triggers the scar — dispatch cancelled."""
        technique = TechniqueFactory(damage_profile=False)
        technique.properties.add(self.cursed)
        stack = self._emit(technique)
        self.assertTrue(stack.was_cancelled())

    def test_near_miss_technique_without_property_does_not_fire(self):
        """A technique without any Property does not match has_property — passes through."""
        technique = TechniqueFactory(damage_profile=False)
        stack = self._emit(technique)
        self.assertFalse(stack.was_cancelled())
