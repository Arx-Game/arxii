"""Cache-vs-transaction-rollback safety for TriggerHandler (#964).

The handler's sync hooks must not corrupt the in-memory cache when the
enclosing transaction rolls back: a rolled-back install must not leave a
phantom trigger, and a rolled-back removal must not drop a live one. The
contract is that ``on_trigger_added`` / ``on_trigger_removed`` defer their
cache invalidation to ``transaction.on_commit``.
"""

from django.db import transaction
from django.test import TestCase

from flows.constants import EventName
from flows.trigger_handler import TriggerHandler
from world.conditions.factories import ReactiveConditionFactory


class _ForceRollback(Exception):
    """Sentinel raised inside an atomic block to trigger a rollback."""


class TriggerHandlerRollbackTests(TestCase):
    def test_rolled_back_install_leaves_no_phantom(self) -> None:
        # Pre-populate the handler with one DAMAGE_APPLIED trigger; the
        # ATTACK_LANDED bucket starts empty.
        existing = ReactiveConditionFactory(event_name=EventName.DAMAGE_APPLIED)
        character = existing.obj
        handler = TriggerHandler(owner=character)
        self.assertEqual(len(handler.triggers_for("attack_landed")), 0)

        # Install an ATTACK_LANDED trigger inside a transaction that rolls back.
        with self.assertRaises(_ForceRollback):
            with transaction.atomic():
                new = ReactiveConditionFactory(
                    event_name=EventName.ATTACK_LANDED,
                    target=character,
                )
                handler.on_trigger_added(new)
                raise _ForceRollback

        # The never-committed row must not be in the cache.
        self.assertEqual(
            len(handler.triggers_for("attack_landed")),
            0,
            "phantom trigger leaked into the cache after rollback",
        )

    def test_rolled_back_removal_keeps_live_trigger(self) -> None:
        existing = ReactiveConditionFactory(event_name=EventName.ATTACK_LANDED)
        character = existing.obj
        handler = TriggerHandler(owner=character)
        self.assertEqual(len(handler.triggers_for("attack_landed")), 1)

        with self.assertRaises(_ForceRollback):
            with transaction.atomic():
                handler.on_trigger_removed(existing.pk)
                raise _ForceRollback

        # The removal never committed, so the live trigger must remain.
        self.assertEqual(
            len(handler.triggers_for("attack_landed")),
            1,
            "live trigger vanished from the cache after a rolled-back removal",
        )

    def test_committed_install_is_visible_after_commit(self) -> None:
        # Positive control: an install that commits is visible once the
        # on_commit callbacks run.
        existing = ReactiveConditionFactory(event_name=EventName.DAMAGE_APPLIED)
        character = existing.obj
        handler = TriggerHandler(owner=character)
        self.assertEqual(len(handler.triggers_for("attack_landed")), 0)

        with self.captureOnCommitCallbacks(execute=True):
            new = ReactiveConditionFactory(
                event_name=EventName.ATTACK_LANDED,
                target=character,
            )
            handler.on_trigger_added(new)

        self.assertEqual(len(handler.triggers_for("attack_landed")), 1)
