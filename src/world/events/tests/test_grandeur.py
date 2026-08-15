"""Event grandeur (#2357): spend -> sqrt-diminishing-returns score -> host/honoree deed.

SQLite tier. Mirrors ``test_catering.py``'s idiom — real currency transfers
through the audited ``world.currency.services.transfer`` sink, real
``LegendEntry`` deeds via ``create_solo_deed`` (mocked where only the call
shape matters).
"""

from unittest.mock import patch

from django.test import TestCase

from world.ceremonies.constants import CeremonyTypeKey
from world.ceremonies.factories import CeremonyFactory, CeremonyHonoreeFactory, CeremonyTypeFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.currency.services import get_or_create_purse, transfer
from world.events.constants import EventStatus, GrandeurCategory
from world.events.factories import EventFactory
from world.events.models import EventGrandeurContribution, EventHost
from world.events.services import (
    GRANDEUR_DEED_BASE_PER_POINT,
    GRANDEUR_DEED_MINIMUM_SCORE,
    GRANDEUR_HONOREE_CUT_PERCENT,
    GRANDEUR_SCORE_CAP,
    _award_grandeur_prestige,
    _grandeur_score,
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

    def test_completion_mints_the_host_deed(self):
        self._spend(9_000)  # score 3, exactly the minimum
        self.assertGreaterEqual(_grandeur_score(self.event), GRANDEUR_DEED_MINIMUM_SCORE)
        with patch("world.societies.services.create_solo_deed") as deed:
            _award_grandeur_prestige(self.event)
        deed.assert_called_once()
        self.assertEqual(deed.call_args.args[0], self.host_persona)
        self.assertEqual(deed.call_args.args[3], 3 * GRANDEUR_DEED_BASE_PER_POINT)

    def test_idempotent_completion_never_double_mints(self):
        """The completion hook only ever fires once — ``complete_event`` gates the
        ACTIVE->COMPLETED transition, so a second completion attempt raises before
        the hook can run again (mirrors catering's structural guard)."""
        from world.events.services import complete_event

        self._spend(9_000)
        complete_event(self.event)
        with self.assertRaises(EventError):
            complete_event(self.event)
        from world.societies.models import LegendEntry

        legendary_deeds = LegendEntry.objects.filter(
            persona=self.host_persona, title__icontains="legendary"
        )
        self.assertEqual(legendary_deeds.count(), 1)


class GrandeurHonoreeCutTest(TestCase):
    def setUp(self):
        self.event = EventFactory(status=EventStatus.ACTIVE)
        self.host_persona = _funded_persona()
        EventHost.objects.create(event=self.event, persona=self.host_persona, is_primary=True)
        self.contributor = _funded_persona(coppers=50_000)
        purse = get_or_create_purse(self.contributor.character_sheet)
        contribute_grandeur(
            self.event,
            self.contributor,
            category=GrandeurCategory.VENUE,
            amount=25_000,
            from_purse=purse,
        )

    def test_no_ceremony_no_honoree_cut(self):
        with patch("world.societies.services.create_solo_deed") as deed:
            _award_grandeur_prestige(self.event)
        deed.assert_called_once()  # host only

    def test_wedding_ceremony_awards_an_additive_honoree_deed(self):
        wedding_type = CeremonyTypeFactory(key=CeremonyTypeKey.WEDDING, name="Wedding")
        honoree_sheet = CharacterSheetFactory()
        ceremony = CeremonyFactory(ceremony_type=wedding_type, event=self.event)
        CeremonyHonoreeFactory(ceremony=ceremony, honoree_sheet=honoree_sheet)

        with patch("world.societies.services.create_solo_deed") as deed:
            _award_grandeur_prestige(self.event)

        self.assertEqual(deed.call_count, 2)  # host deed + honoree deed
        recipients = {call.args[0] for call in deed.call_args_list}
        self.assertIn(self.host_persona, recipients)
        self.assertIn(honoree_sheet.primary_persona, recipients)

        score = _grandeur_score(self.event)
        expected_honoree_value = (
            score * GRANDEUR_DEED_BASE_PER_POINT * GRANDEUR_HONOREE_CUT_PERCENT // 100
        )
        honoree_call = next(
            call for call in deed.call_args_list if call.args[0] == honoree_sheet.primary_persona
        )
        self.assertEqual(honoree_call.args[3], expected_honoree_value)

    def test_a_grand_ball_with_no_ceremony_pays_the_host_the_full_deed(self):
        with patch("world.societies.services.create_solo_deed") as deed:
            _award_grandeur_prestige(self.event)
        deed.assert_called_once()
