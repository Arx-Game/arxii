"""Telnet ``accept makeover`` / ``decline makeover`` through the offer registry (#4187)."""

from commands.offer_registry import find_handler
from world.items.tests.test_makeover_requests import MakeoverAskFixture
from world.scenes.action_constants import ActionRequestStatus


class MakeoverOfferHandlerTests(MakeoverAskFixture):
    def handler(self):
        handler = find_handler("makeover")
        self.assertIsNotNone(handler, "the items app must register the handler on ready()")
        return handler

    def test_pending_for_returns_the_targets_open_ask(self):
        request = self.offer()
        handler = self.handler()
        self.assertEqual(handler.pending_for(self.other_sheet), request)
        self.assertIsNone(handler.pending_for(self.sheet))
        self.assertIn("crimson", handler.describe(request))

    def test_accept_restyles_and_spends_a_charge(self):
        request = self.offer()
        line = self.handler().accept(request, self.other, "")
        self.assertTrue(line)
        request.refresh_from_db()
        self.assertEqual(request.status, ActionRequestStatus.ACCEPTED)
        self.assertEqual(self.charges(), 7)

    def test_decline_spends_nothing(self):
        request = self.offer()
        line = self.handler().decline(request, self.other)
        self.assertTrue(line)
        request.refresh_from_db()
        self.assertEqual(request.status, ActionRequestStatus.DENIED)
        self.assertEqual(self.charges(), 8)

    def test_lapsed_ask_is_not_pending(self):
        self.offer()
        self.actor.location = self.remote
        self.assertIsNone(self.handler().pending_for(self.other_sheet))

    def test_accept_after_lapse_answers_honestly(self):
        request = self.offer()
        self.actor.location = self.remote
        line = self.handler().accept(request, self.other, "")
        self.assertIn("no longer here", line)
        self.assertEqual(self.charges(), 8)
