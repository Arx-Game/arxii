"""Verifies AE event emission produces parallel per-target FlowStacks.

For area-effect events (one emit, many targets), each PERSONAL dispatch
gets its own fresh FlowStack so the recursion cap is enforced per-target,
not shared across the whole AE fan-out.
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from flows.emit import emit_event
from flows.events.names import EventNames
from flows.events.payloads import DamagePreApplyPayload, DamageSource
from world.conditions.factories import ReactiveConditionFactory


class AETopologyTests(TestCase):
    def test_ae_parallel_personal_stacks(self) -> None:
        alice = CharacterFactory()
        bob = CharacterFactory()
        carol = CharacterFactory()
        for char in (alice, bob, carol):
            ReactiveConditionFactory(
                event_name=EventNames.DAMAGE_PRE_APPLY,
                target=char,
            )

        stacks_seen = []
        for char in (alice, bob, carol):
            payload = DamagePreApplyPayload(
                target=char,
                amount=10,
                damage_type="fire",
                source=DamageSource(type="character", ref=None),
            )
            stack = emit_event(
                EventNames.DAMAGE_PRE_APPLY,
                payload,
                personal_target=char,
            )
            stacks_seen.append(stack)

        self.assertEqual(
            {s.owner.pk for s in stacks_seen},
            {alice.pk, bob.pk, carol.pk},
        )
        for stack in stacks_seen:
            self.assertEqual(stack.depth, 1)
