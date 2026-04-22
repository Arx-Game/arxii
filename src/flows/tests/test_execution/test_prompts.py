"""Pending-prompt registry: Deferreds held by (account_id, prompt_key)."""

from django.test import TestCase
from twisted.internet.defer import Deferred

from flows.execution.prompts import (
    _pending_prompts,
    register_pending_prompt,
    resolve_pending_prompt,
    timeout_pending_prompt,
)


class PendingPromptTests(TestCase):
    def tearDown(self) -> None:
        _pending_prompts.clear()

    def test_register_creates_deferred(self) -> None:
        deferred = register_pending_prompt(account_id=42, prompt_key="test")
        self.assertIsInstance(deferred, Deferred)
        self.assertIn((42, "test"), _pending_prompts)

    def test_resolve_fires_deferred(self) -> None:
        deferred = register_pending_prompt(account_id=42, prompt_key="test")
        results = []
        deferred.addCallback(results.append)
        resolved = resolve_pending_prompt(account_id=42, prompt_key="test", answer="yes")
        self.assertTrue(resolved)
        self.assertEqual(results, ["yes"])
        self.assertNotIn((42, "test"), _pending_prompts)

    def test_resolve_unknown_returns_false(self) -> None:
        resolved = resolve_pending_prompt(account_id=42, prompt_key="nope", answer="x")
        self.assertFalse(resolved)

    def test_timeout_fires_default(self) -> None:
        deferred = register_pending_prompt(
            account_id=42,
            prompt_key="test",
            default_answer="no",
        )
        results = []
        deferred.addCallback(results.append)
        timed_out = timeout_pending_prompt(account_id=42, prompt_key="test")
        self.assertTrue(timed_out)
        self.assertEqual(results, ["no"])
        self.assertNotIn((42, "test"), _pending_prompts)

    def test_timeout_unknown_returns_false(self) -> None:
        timed_out = timeout_pending_prompt(account_id=42, prompt_key="nope")
        self.assertFalse(timed_out)
