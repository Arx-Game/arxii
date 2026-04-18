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
    """ "Mage Sight" scar appends scar description to at_examined output
    ONLY for targets with abyssal affinity.

    Skipped: ExaminedPayload is @dataclass(frozen=True) in flows/events/payloads.py.
    A reactive scar cannot mutate ExaminedPayload.result in-place. The scar needs
    a mutable payload or a dedicated pre-examine decoration hook to append content.

    Design follow-up: Either unfreeze ExaminedPayload (allowing post-hoc decoration)
    or model Mage Sight as an EXAMINE_PRE handler that annotates the observer's
    perception context before ExaminedPayload is constructed. Until then, the full
    end-to-end test cannot be written.

    Intent:
        observer has Mage Sight scar (trigger on EXAMINED, filter: target has abyssal aura).
        examine(observer, abyssal_target) → result.sections contains scar-appended text.
        examine(observer, non_abyssal_target) → result.sections unchanged.
    """

    def test_mage_sight_appends_to_abyssal_target(self):
        self.skipTest(
            "ExaminedPayload is frozen=True; reactive scars cannot mutate the result. "
            "Design follow-up needed: unfreeze ExaminedPayload or add an EXAMINE_PRE "
            "decoration hook. See flows/events/payloads.py."
        )

    def test_near_miss_non_abyssal_target_unchanged(self):
        self.skipTest(
            "ExaminedPayload is frozen=True; reactive scars cannot mutate the result. "
            "Design follow-up needed: unfreeze ExaminedPayload or add an EXAMINE_PRE "
            "decoration hook. See flows/events/payloads.py."
        )


class SoulSightScarTest(TestCase):
    """ "Soul Sight" scar reveals true identity only when target has
    the specific persona-type property.

    Skipped: Same design gap as MageSightScarTest. ExaminedPayload is frozen=True,
    preventing scar mutation of the result. Additionally, the persona-type property
    system (linking Properties from world/mechanics to characters) is not yet wired
    into the examine pipeline's payload construction.

    Design follow-up: Two preconditions required before implementing:
      1. ExaminedPayload must be mutable (or a pre-examine hook must exist).
      2. The examine pipeline must include persona/property data in the payload
         so the filter DSL can walk target.persona_type.property.

    Intent:
        observer has Soul Sight scar (trigger on EXAMINED, filter: target has
        "masked-identity" property on their primary persona).
        examine(observer, masked_target) → result contains true identity disclosure.
        examine(observer, unmasked_target) → result unchanged.
    """

    def test_soul_sight_reveals_masked_identity(self):
        self.skipTest(
            "ExaminedPayload is frozen=True; reactive scars cannot mutate the result. "
            "Additionally, persona-type property filtering in the examine payload is "
            "not yet wired. Two design gaps must close before this test can run. "
            "See flows/events/payloads.py."
        )

    def test_near_miss_unmasked_target_unchanged(self):
        self.skipTest(
            "ExaminedPayload is frozen=True; reactive scars cannot mutate the result. "
            "Additionally, persona-type property filtering in the examine payload is "
            "not yet wired. Two design gaps must close before this test can run. "
            "See flows/events/payloads.py."
        )


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

    Skipped: Technique model has no ``properties`` M2M field. The ``has_property``
    filter path ``source.ref.properties`` is unresolvable until a Technique → Property
    M2M is added to ``world/magic/models.py``.

    Intent: a scar with filter ``{path: 'source.ref', op: 'has_property', value: 'cursed'}``
    should fire on techniques that carry the ``cursed`` Property tag, and NOT fire on
    techniques without it. Implement when Technique gains a ``properties`` M2M.
    """

    def test_technique_with_property_fires_scar(self):
        self.skipTest(
            "Technique model has no 'properties' M2M field. "
            "Add Technique.properties M2M to world.mechanics.Property, then implement "
            "this test using has_property filter op. See world/magic/models.py:Technique."
        )

    def test_near_miss_technique_without_property_does_not_fire(self):
        self.skipTest(
            "Technique model has no 'properties' M2M field. "
            "Add Technique.properties M2M to world.mechanics.Property, then implement "
            "this test using has_property filter op. See world/magic/models.py:Technique."
        )
