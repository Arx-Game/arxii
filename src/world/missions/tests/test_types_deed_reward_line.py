"""Tests for the DeedRewardLine in-memory dataclass (Phase 2, Task 2.4).

DeedRewardLine is the typed return/in-memory shape for engine-emitted
reward lines (the persisted shape is MissionDeedRewardLine rows). It must
be frozen and hashable, with a typed tuple payload — never a bare dict. No
database is touched, so plain ``unittest.TestCase`` is sufficient.
"""

import dataclasses
import unittest

from world.missions.constants import DeedRewardKind, DeedRewardSink
from world.missions.types import DeedRewardLine


class DeedRewardLineTests(unittest.TestCase):
    """Frozen, hashable, typed tuple payload (no dict)."""

    def test_constructs_with_typed_tuple_payload(self) -> None:
        line = DeedRewardLine(
            kind=DeedRewardKind.IMMEDIATE.value,
            sink=DeedRewardSink.MONEY.value,
            payload=(("amount", "250"),),
        )
        self.assertEqual(line.kind, "immediate")
        self.assertEqual(line.sink, "money")
        self.assertEqual(line.payload, (("amount", "250"),))

    def test_default_payload_is_empty_tuple_not_dict(self) -> None:
        line = DeedRewardLine(
            kind=DeedRewardKind.POST_CRON.value,
            sink=DeedRewardSink.BEAT.value,
        )
        self.assertEqual(line.payload, ())
        self.assertNotIsInstance(line.payload, dict)

    def test_is_frozen_and_hashable(self) -> None:
        line = DeedRewardLine(
            kind=DeedRewardKind.PROPAGATION.value,
            sink=DeedRewardSink.RUMOR.value,
            payload=(("ref", "heist"),),
        )
        self.assertTrue(dataclasses.is_dataclass(line))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            line.kind = "x"  # type: ignore[misc]
        self.assertIsInstance(hash(line), int)
