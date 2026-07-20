"""Tests for the perk announce dual-dispatch path (#2536, Task 6).

``announce_fired_perks`` is the presentation-contract seam (spec §5, ruling
1 — HARD telnet parity): every firing must reach BOTH the web WS interaction
payload and bare telnet clients (``message_location``). Both dispatch
functions are imported lazily inside ``announce_fired_perks`` (module-level
lazy imports, per the file's existing style), so tests patch them at their
DEFINING modules — the same target ``test_outcome_broadcast.py`` (combat) and
``test_interaction_views.py`` (scenes) already patch for their own
dual-dispatch assertions on the same two functions.

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

    @mock.patch("flows.service_functions.communication.message_location")
    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_announce_dispatches_both_ws_and_telnet(
        self, mock_broadcast, mock_message_location
    ) -> None:
        firing = self._firing()

        announce_fired_perks([firing], subject=self.subject_sheet, location=self.room)

        assert mock_broadcast.call_count == 1
        assert mock_message_location.call_count == 1
        assert Interaction.objects.filter(mode=InteractionMode.OUTCOME).count() == 1

    @mock.patch("flows.service_functions.communication.message_location")
    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_telnet_text_contains_perk_name(
        self,
        mock_broadcast,  # noqa: ARG002
        mock_message_location,
    ) -> None:
        firing = self._firing(name="Scout's Instinct")

        announce_fired_perks([firing], subject=self.subject_sheet, location=self.room)

        _caller_state, text = mock_message_location.call_args.args
        assert "Scout's Instinct" in text

    @mock.patch("flows.service_functions.communication.message_location")
    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_ws_payload_content_contains_rendered_template_and_perk_name(
        self,
        mock_broadcast,
        mock_message_location,  # noqa: ARG002
    ) -> None:
        firing = self._firing(name="Scout's Instinct")

        announce_fired_perks([firing], subject=self.subject_sheet, location=self.room)

        _location_arg, payload = mock_broadcast.call_args.args
        assert "Scout's Instinct" in payload["content"]
        assert self.holder_character.key in payload["content"]
        assert self.subject_character.key in payload["content"]

    @mock.patch("flows.service_functions.communication.message_location")
    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_empty_fired_no_dispatch(self, mock_broadcast, mock_message_location) -> None:
        announce_fired_perks([], subject=self.subject_sheet, location=self.room)

        mock_broadcast.assert_not_called()
        mock_message_location.assert_not_called()
        assert not Interaction.objects.filter(mode=InteractionMode.OUTCOME).exists()

    @mock.patch("flows.service_functions.communication.message_location")
    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_none_location_no_dispatch(self, mock_broadcast, mock_message_location) -> None:
        firing = self._firing()

        announce_fired_perks([firing], subject=self.subject_sheet, location=None)

        mock_broadcast.assert_not_called()
        mock_message_location.assert_not_called()
        assert not Interaction.objects.filter(mode=InteractionMode.OUTCOME).exists()

    @mock.patch("flows.service_functions.communication.message_location")
    @mock.patch("world.scenes.interaction_services._broadcast_to_location")
    def test_multiple_firings_each_dispatch_once_no_double_announce(
        self, mock_broadcast, mock_message_location
    ) -> None:
        """Two DIFFERENT perks firing in one resolution each announce exactly
        once — proves the loop doesn't double-dispatch per firing, the
        complementary half of the no-double-announce contract to the
        call-site (single-call-per-resolution) proof in
        ``test_power_derivation.py``/``test_situational_perk_check_bonus.py``."""
        firing_a = self._firing(name="Scout's Instinct")
        firing_b = self._firing(name="Last Bulwark")

        announce_fired_perks([firing_a, firing_b], subject=self.subject_sheet, location=self.room)

        assert mock_broadcast.call_count == 2
        assert mock_message_location.call_count == 2
        assert Interaction.objects.filter(mode=InteractionMode.OUTCOME).count() == 2
