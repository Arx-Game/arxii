"""Tests for #3412's ``unread_narrative_count`` on ``RosterEntryViewSet.mine``.

The Hall (the logged-in home page) needs a per-character unread-tidings
count for the account's own roster entries. This exercises the annotation
added to ``mine``'s queryset and the corresponding
``MyRosterEntrySerializer`` field, including the query-count discipline
(the annotation must not add per-row queries) and the fallback path used
when a ``RosterEntry`` is serialized without the annotation (the ``select``
endpoint's ``selected_entry`` fragment).
"""

from __future__ import annotations

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.narrative.factories import NarrativeMessageDeliveryFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.roster.models import RosterEntry
from world.roster.serializers import MyRosterEntrySerializer


def _entry_for(player_data):
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    entry = RosterEntryFactory(character_sheet=sheet)
    RosterTenureFactory(player_data=player_data, roster_entry=entry)
    return entry


class MineUnreadNarrativeCountTests(TestCase):
    url = "/api/roster/entries/mine/"

    def setUp(self):
        self.client = APIClient()
        self.player = PlayerDataFactory()
        self.entry = _entry_for(self.player)
        self.client.force_authenticate(user=self.player.account)

    def test_unread_counted(self):
        sheet = self.entry.character_sheet
        NarrativeMessageDeliveryFactory(recipient_character_sheet=sheet, acknowledged_at=None)
        NarrativeMessageDeliveryFactory(recipient_character_sheet=sheet, acknowledged_at=None)

        response = self.client.get(self.url)

        assert response.status_code == 200
        row = next(r for r in response.data if r["id"] == self.entry.pk)
        assert row["unread_narrative_count"] == 2

    def test_acknowledged_not_counted(self):
        sheet = self.entry.character_sheet
        NarrativeMessageDeliveryFactory(recipient_character_sheet=sheet, acknowledged_at=None)
        NarrativeMessageDeliveryFactory(
            recipient_character_sheet=sheet, acknowledged_at=timezone.now()
        )

        response = self.client.get(self.url)

        row = next(r for r in response.data if r["id"] == self.entry.pk)
        assert row["unread_narrative_count"] == 1

    def test_no_deliveries_is_zero(self):
        response = self.client.get(self.url)

        row = next(r for r in response.data if r["id"] == self.entry.pk)
        assert row["unread_narrative_count"] == 0

    def test_other_accounts_deliveries_excluded(self):
        other_player = PlayerDataFactory()
        other_entry = _entry_for(other_player)
        NarrativeMessageDeliveryFactory(
            recipient_character_sheet=other_entry.character_sheet, acknowledged_at=None
        )

        response = self.client.get(self.url)

        row = next(r for r in response.data if r["id"] == self.entry.pk)
        assert row["unread_narrative_count"] == 0

    def test_annotation_is_a_single_aggregate_query_not_per_row(self):
        """The annotation is one aggregated JOIN/GROUP BY, not a per-row query.

        Two owned entries (each with an unread delivery) must still only hit
        ``narrative_message_delivery`` once — a per-row query would regress
        this. (Other fields on this serializer already run per-entry queries
        of their own — pre-existing, out of scope here — so this asserts on
        the delivery table specifically rather than total query count.)
        """
        second_entry = _entry_for(self.player)
        for entry in (self.entry, second_entry):
            NarrativeMessageDeliveryFactory(
                recipient_character_sheet=entry.character_sheet, acknowledged_at=None
            )

        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(self.url)
        assert response.status_code == 200
        assert len(response.data) == 2
        delivery_queries = [
            q for q in ctx.captured_queries if "narrativemessagedelivery" in q["sql"].lower()
        ]
        assert len(delivery_queries) == 1

    def test_serializer_falls_back_when_unannotated(self):
        """A plain (unannotated) RosterEntry still serializes a correct count.

        Exercises the fallback path used by the #3412 ``select`` endpoint's
        ``selected_entry`` fragment, which serializes ``player_data.selected_entry``
        (a plain FK fetch) rather than an entry from ``mine``'s annotated queryset.
        """
        sheet = self.entry.character_sheet
        NarrativeMessageDeliveryFactory(recipient_character_sheet=sheet, acknowledged_at=None)

        plain_entry = RosterEntry.objects.get(pk=self.entry.pk)
        assert "unread_narrative_count" not in plain_entry.__dict__

        data = MyRosterEntrySerializer(plain_entry).data
        assert data["unread_narrative_count"] == 1
