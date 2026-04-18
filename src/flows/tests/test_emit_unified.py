"""Signature/surface tests for the unified-dispatch emit_event (Phase 2, Task 3).

Behaviour is exercised by the Phase 5 integration tests. This module
just pins the public surface: emit_event takes ``location``, not
``personal_target`` / ``room``.
"""

import inspect

from django.test import TestCase

from flows.emit import emit_event


class EmitUnifiedTests(TestCase):
    def test_signature_takes_location(self) -> None:
        sig = inspect.signature(emit_event)
        self.assertIn("location", sig.parameters)
        self.assertNotIn("personal_target", sig.parameters)
        self.assertNotIn("room", sig.parameters)
