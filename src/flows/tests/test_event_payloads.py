import dataclasses

from django.test import TestCase

from flows.events.payloads import (
    AttackLandedPayload,
    DamageAppliedPayload,
    DamagePreApplyPayload,
    DamageSource,
    MovedPayload,
)


class EventPayloadTests(TestCase):
    def test_damage_pre_apply_mutable(self) -> None:
        # PRE payloads are mutable so ModifyPayload steps can amend them.
        payload = DamagePreApplyPayload(
            target=None,
            amount=10,
            damage_type="fire",
            source=DamageSource(type="character", ref=None),
        )
        payload.amount = 5
        self.assertEqual(payload.amount, 5)

    def test_damage_applied_frozen(self) -> None:
        # POST payloads are immutable.
        payload = DamageAppliedPayload(
            target=None,
            amount_dealt=10,
            damage_type="fire",
            source=DamageSource(type="character", ref=None),
            hp_after=50,
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            payload.amount_dealt = 20

    def test_attack_landed_frozen(self) -> None:
        # Check that AttackLandedPayload is frozen by verifying it raises
        # FrozenInstanceError when attempting to mutate
        payload = AttackLandedPayload(
            attacker=None,
            target=None,
            weapon=None,
            damage_result=None,
            action=None,
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            payload.attacker = object()

    def test_moved_frozen(self) -> None:
        payload = MovedPayload(
            character=None,
            origin=None,
            destination=None,
            exit_used=None,
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            payload.character = object()
