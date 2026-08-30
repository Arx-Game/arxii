"""Event grandeur (#2357): spend -> sqrt-diminishing-returns score -> host/honoree deed.

SQLite tier. Mirrors ``test_catering.py``'s idiom — real currency transfers
through the audited ``world.currency.services.transfer`` sink, real
``LegendEntry`` deeds via ``create_solo_deed`` (mocked where only the call
shape matters).
"""

from unittest.mock import patch

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.currency.services import get_or_create_purse, transfer
from world.events.constants import EventStatus, GrandeurCategory
from world.events.factories import EventFactory
from world.events.models import EventGrandeurContribution, EventHost
from world.events.services import (
    GRANDEUR_SCORE_CAP,
    _award_grandeur_prestige,
    _grandeur_score,
    cancel_event,
    contribute_grandeur,
)
from world.events.types import EventError


def _funded_persona(*, coppers: int = 0):
    """A CharacterSheetFactory's primary persona, purse pre-funded via the audited sink."""
    sheet = CharacterSheetFactory()
    persona = sheet.primary_persona
    if coppers:
        transfer(amount=coppers, reason="test seed", to_purse=get_or_create_purse(sheet))
    return persona


class ContributeGrandeurTest(TestCase):
    def setUp(self):
        self.event = EventFactory(status=EventStatus.ACTIVE)
        self.persona = _funded_persona(coppers=10_000)

    def test_contribution_debits_the_purse_and_records_the_row(self):
        purse = get_or_create_purse(self.persona.character_sheet)
        row = contribute_grandeur(
            self.event,
            self.persona,
            category=GrandeurCategory.VENUE,
            amount=4_000,
            from_purse=purse,
        )
        self.assertEqual(row.category, GrandeurCategory.VENUE)
        self.assertEqual(row.amount_spent, 4_000)
        self.assertEqual(row.contributed_by, self.persona)
        purse.refresh_from_db()
        self.assertEqual(purse.balance, 6_000)

    def test_insufficient_funds_raises_and_debits_nothing(self):
        purse = get_or_create_purse(self.persona.character_sheet)
        with self.assertRaises(EventError):
            contribute_grandeur(
                self.event,
                self.persona,
                category=GrandeurCategory.DECOR,
                amount=999_999,
                from_purse=purse,
            )
        purse.refresh_from_db()
        self.assertEqual(purse.balance, 10_000)
        self.assertFalse(EventGrandeurContribution.objects.filter(event=self.event).exists())

    def test_draft_events_refuse_contributions(self):
        draft_event = EventFactory(status=EventStatus.DRAFT)
        purse = get_or_create_purse(self.persona.character_sheet)
        with self.assertRaises(EventError):
            contribute_grandeur(
                draft_event,
                self.persona,
                category=GrandeurCategory.VENUE,
                amount=1_000,
                from_purse=purse,
            )

    def test_completed_events_refuse_new_contributions(self):
        self.event.status = EventStatus.COMPLETED
        self.event.save(update_fields=["status"])
        purse = get_or_create_purse(self.persona.character_sheet)
        with self.assertRaises(EventError):
            contribute_grandeur(
                self.event,
                self.persona,
                category=GrandeurCategory.VENUE,
                amount=1_000,
                from_purse=purse,
            )


class GrandeurScoreTest(TestCase):
    def setUp(self):
        self.event = EventFactory(status=EventStatus.ACTIVE)
        self.persona = _funded_persona(coppers=50_000_000)

    def _spend(self, amount: int, category: str = GrandeurCategory.VENUE) -> None:
        purse = get_or_create_purse(self.persona.character_sheet)
        contribute_grandeur(
            self.event, self.persona, category=category, amount=amount, from_purse=purse
        )

    def test_no_contributions_score_zero(self):
        self.assertEqual(_grandeur_score(self.event), 0)

    def test_score_is_the_sqrt_of_total_spend_in_points(self):
        # 9000 coppers / 1000-per-point = 9 points; sqrt(9) = 3.
        self._spend(9_000)
        self.assertEqual(_grandeur_score(self.event), 3)

    def test_diminishing_returns_ten_x_spend_is_not_ten_x_score(self):
        self._spend(9_000)
        base_score = _grandeur_score(self.event)
        self._spend(81_000)  # total now 90_000 -> 90 points -> sqrt ~ 9.49 -> 9
        tenx_score = _grandeur_score(self.event)
        self.assertGreater(tenx_score, base_score)
        self.assertLess(tenx_score, base_score * 10)

    def test_score_is_capped(self):
        self._spend(50_000_000)
        self.assertEqual(_grandeur_score(self.event), GRANDEUR_SCORE_CAP)


class GrandeurPrestigeTest(TestCase):
    def setUp(self):
        self.event = EventFactory(status=EventStatus.ACTIVE)
        self.host_persona = _funded_persona()
        EventHost.objects.create(event=self.event, persona=self.host_persona, is_primary=True)
        self.contributor = _funded_persona(coppers=50_000)

    def _spend(self, amount: int) -> None:
        purse = get_or_create_purse(self.contributor.character_sheet)
        contribute_grandeur(
            self.event,
            self.contributor,
            category=GrandeurCategory.VENUE,
            amount=amount,
            from_purse=purse,
        )

    def test_no_score_no_deed(self):
        with patch("world.societies.services.create_solo_deed") as deed:
            _award_grandeur_prestige(self.event)
        deed.assert_not_called()

    def test_below_minimum_score_mints_nothing(self):
        # score 2 < GRANDEUR_DEED_MINIMUM_SCORE (3): 4000 coppers -> 4 points -> sqrt(4)=2.
        self._spend(4_000)
        with patch("world.societies.services.create_solo_deed") as deed:
            _award_grandeur_prestige(self.event)
        deed.assert_not_called()

    def test_cancel_leaves_contributions_spent_with_no_prestige_minted(self):
        event = EventFactory(status=EventStatus.SCHEDULED)
        host_persona = _funded_persona()
        EventHost.objects.create(event=event, persona=host_persona, is_primary=True)
        contributor = _funded_persona(coppers=50_000)
        purse = get_or_create_purse(contributor.character_sheet)

        contribute_grandeur(
            event, contributor, category=GrandeurCategory.VENUE, amount=25_000, from_purse=purse
        )
        purse.refresh_from_db()
        self.assertEqual(purse.balance, 25_000, "the spend already left the purse")

        cancel_event(event)

        purse.refresh_from_db()
        self.assertEqual(purse.balance, 25_000, "cancellation does not refund the spend")
        self.assertTrue(
            EventGrandeurContribution.objects.filter(event=event).exists(),
            "the contribution row survives cancellation as a spent record",
        )
        from world.societies.models import LegendEntry

        self.assertFalse(
            LegendEntry.objects.filter(persona=host_persona).exists(),
            "no prestige mints on cancellation — only complete_event awards it",
        )
