"""Tests for the perk announce dual-dispatch path (#2536, Task 6).

``announce_fired_perks`` is the presentation-contract seam (spec §5, ruling
1 — HARD telnet parity): every firing must reach BOTH the web WS interaction
payload and bare telnet clients. The WS half is asserted by mocking
``world.scenes.interaction_services._broadcast_to_location`` (the same
target ``test_outcome_broadcast.py`` (combat) and ``test_interaction_views.py``
(scenes) already patch for their own dual-dispatch assertions).

**The telnet half is deliberately NOT asserted by mocking away the delivery
primitive wholesale** (a review-cycle CRITICAL finding: every test here used
to fully mock ``flows.service_functions.communication.message_location``,
which hid a total telnet-delivery failure — the pre-fix implementation
resolved the broadcast room from the singleton Narrator persona's own,
unrelated, often-unset location instead of the caller-supplied ``location``,
so real telnet clients standing in the room got nothing, and a green suite
never caught it). Instead:

- Most tests here patch ``self.room.msg_contents`` via ``mock.patch.object``
  — an INSTANCE-level patch on the exact room object the firing is
  supposed to broadcast to. If the seam under test regresses to resolving
  some other object's location (the original bug shape), this mock is never
  invoked and the assertion fails loudly — this is "assert on the
  room-scoped send," scoped tightly enough to catch that exact regression
  class. Mirrors ``test_dramatic_surge_primitive.py``'s
  ``mock.patch.object(self.encounter.room, "msg_contents")`` pattern for
  the same kind of caller-less room-wide broadcast.
- ``test_telnet_delivery_reaches_a_character_actually_in_the_room`` goes
  further and does not mock ``msg_contents`` at all: a real character is
  placed IN ``self.room``, only its own terminal ``.msg()`` (the call every
  telnet session's output funnels through) is patched, and the real
  ``ObjectDB.msg_contents`` implementation runs unmocked end to end. This is
  the test that would have failed outright against the pre-fix
  implementation — no character anywhere ever received a ``.msg()`` call
  under that bug, because ``message_location`` no-oped silently on the
  Narrator's own unset location.

Not ``setUpTestData`` — factories here create Evennia ``ObjectDB`` instances
(``DbHolder``, not deepcopyable), same rationale as the other perk suites.
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.factories import VowSituationalPerkFactory
from world.covenants.perks.services import FiredPerk, announce_fired_perks
from world.scenes.constants import InteractionMode
from world.scenes.models import Interaction


class AnnounceFiredPerksTests(TestCase):
    def setUp(self) -> None:
        self.subject_character = CharacterFactory()
        self.subject_sheet = CharacterSheetFactory(character=self.subject_character)
        self.holder_character = CharacterFactory()
        self.holder_sheet = CharacterSheetFactory(character=self.holder_character)
        self.room = ObjectDBFactory(
            db_key="PerkAnnounceRoom",
            db_typeclass_path="typeclasses.rooms.Room",
        )

    def _firing(self, *, name="Scout's Instinct", holder=None, magnitude_tenths=15):
        perk = VowSituationalPerkFactory(
            name=name,
            announce_template="{holder} reveals the trap protecting {subject}!",
        )
        return FiredPerk(
            perk=perk,
            holder=holder or self.holder_sheet,
            magnitude_tenths=magnitude_tenths,
            rung_number=None,
        )

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_announce_dispatches_both_ws_and_telnet(self, mock_broadcast) -> None:
        firing = self._firing()

        with mock.patch.object(self.room, "msg_contents") as mock_msg_contents:
            announce_fired_perks([firing], subject=self.subject_sheet, location=self.room)

        assert mock_broadcast.call_count == 1
        assert mock_msg_contents.call_count == 1
        assert Interaction.objects.filter(mode=InteractionMode.OUTCOME).count() == 1

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_telnet_text_contains_perk_name(self, mock_broadcast) -> None:  # noqa: ARG002
        firing = self._firing(name="Scout's Instinct")

        with mock.patch.object(self.room, "msg_contents") as mock_msg_contents:
            announce_fired_perks([firing], subject=self.subject_sheet, location=self.room)

        (text,), _kwargs = mock_msg_contents.call_args
        assert "Scout's Instinct" in text

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_ws_payload_content_contains_rendered_template_and_perk_name(
        self, mock_broadcast
    ) -> None:
        firing = self._firing(name="Scout's Instinct")

        announce_fired_perks([firing], subject=self.subject_sheet, location=self.room)

        _location_arg, payload = mock_broadcast.call_args.args
        assert "Scout's Instinct" in payload["content"]
        assert self.holder_character.key in payload["content"]
        assert self.subject_character.key in payload["content"]

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_empty_fired_no_dispatch(self, mock_broadcast) -> None:
        with mock.patch.object(self.room, "msg_contents") as mock_msg_contents:
            announce_fired_perks([], subject=self.subject_sheet, location=self.room)

        mock_broadcast.assert_not_called()
        mock_msg_contents.assert_not_called()
        assert not Interaction.objects.filter(mode=InteractionMode.OUTCOME).exists()

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_none_location_no_dispatch(self, mock_broadcast) -> None:
        firing = self._firing()

        with mock.patch.object(self.room, "msg_contents") as mock_msg_contents:
            announce_fired_perks([firing], subject=self.subject_sheet, location=None)

        mock_broadcast.assert_not_called()
        mock_msg_contents.assert_not_called()
        assert not Interaction.objects.filter(mode=InteractionMode.OUTCOME).exists()

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_multiple_firings_each_dispatch_once_no_double_announce(self, mock_broadcast) -> None:
        """Two DIFFERENT perks firing in one resolution each announce exactly
        once — proves the loop doesn't double-dispatch per firing, the
        complementary half of the no-double-announce contract to the
        call-site (single-call-per-resolution) proof in
        ``test_power_derivation.py``/``test_situational_perk_check_bonus.py``."""
        firing_a = self._firing(name="Scout's Instinct")
        firing_b = self._firing(name="Last Bulwark")

        with mock.patch.object(self.room, "msg_contents") as mock_msg_contents:
            announce_fired_perks(
                [firing_a, firing_b], subject=self.subject_sheet, location=self.room
            )

        assert mock_broadcast.call_count == 2
        assert mock_msg_contents.call_count == 2
        assert Interaction.objects.filter(mode=InteractionMode.OUTCOME).count() == 2

    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_telnet_delivery_reaches_a_character_actually_in_the_room(
        self,
        mock_broadcast,  # noqa: ARG002
    ) -> None:
        """Fix for the review's CRITICAL finding (#2536 Task 6): proves
        genuine telnet delivery WITHOUT mocking the delivery primitive
        itself. A real character standing in ``self.room`` — not the
        Narrator's own, unrelated location — must receive the announce text
        via its own ``.msg()``, the terminal call every telnet session's
        output funnels through (Evennia's real ``ObjectDB.msg_contents``
        runs unmocked here and dispatches to it). Against the pre-fix
        implementation (caller state built from the singleton Narrator
        persona's own character) this test fails outright: the Narrator has
        no location in this test setup, so the old ``message_location`` call
        would silently no-op and ``listener.msg`` would never be called.
        """
        listener = CharacterFactory(location=self.room)
        firing = self._firing(name="Scout's Instinct")

        with mock.patch.object(listener, "msg") as mock_msg:
            announce_fired_perks([firing], subject=self.subject_sheet, location=self.room)

        assert mock_msg.call_count == 1
        _args, kwargs = mock_msg.call_args
        sent_text, _outkwargs = kwargs["text"]
        assert "Scout's Instinct" in sent_text
