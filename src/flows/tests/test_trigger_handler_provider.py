"""Tests for TriggerHandler as a pure trigger provider (Phase 2, Task 2).

After the unified-dispatch rewrite, TriggerHandler no longer has a
``dispatch`` method — dispatch lives in ``flows.emit.emit_event``.
TriggerHandler's job is to populate and expose ``triggers_for(event_name)``.
"""

from django.test import TestCase

from flows.trigger_handler import TriggerHandler


class TriggerHandlerProviderTests(TestCase):
    def test_no_dispatch_method(self) -> None:
        self.assertFalse(hasattr(TriggerHandler, "dispatch"))

    def test_triggers_for_returns_list(self) -> None:
        handler = TriggerHandler(owner=None)
        self.assertEqual(handler.triggers_for("attack_landed"), [])
