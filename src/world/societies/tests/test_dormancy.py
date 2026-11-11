"""Dormancy (#5069 slice 3, #5078): a house nobody plays goes dormant and its coin stops
accruing; a house in a lull keeps accruing uncapped; a login or a roster approval wakes it.
Presence is the test, never actions (owner, 2026-11-11)."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from world.currency.constants import IncomeStreamKind
from world.currency.models import OrgIncomeStream
from world.currency.services import run_weekly_economy
from world.roster.factories import (
    FamilyFactory,
    PlayerDataFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)
from world.scenes.factories import PersonaFactory
from world.societies.factories import OrganizationFactory, OrganizationMembershipFactory
from world.societies.houses.dormancy import mark_dormant_houses, wake_houses_for
from world.societies.houses.models import DominionConfig
from world.societies.models import Organization


def _house_with_member(*, logged_in_days_ago: int | None, name: str):
    """A house with an income stream and one member whose character sits on the
    roster under an account; ``None`` leaves the character unplayed (no tenure)."""
    house = OrganizationFactory(name=name, family=FamilyFactory(name=name))
    OrgIncomeStream.objects.create(
        organization=house,
        name=f"{name} taxes",
        kind=IncomeStreamKind.DOMAIN_TAX,
        gross_amount=1000,
    )
    persona = PersonaFactory()
    OrganizationMembershipFactory(organization=house, persona=persona)
    entry = RosterEntryFactory(character_sheet=persona.character_sheet)
    account = None
    if logged_in_days_ago is not None:
        account = AccountFactory()
        account.last_login = timezone.now() - timedelta(days=logged_in_days_ago)
        account.save(update_fields=["last_login"])
        RosterTenureFactory(roster_entry=entry, player_data=PlayerDataFactory(account=account))
    return house, account


class DormancyTests(TestCase):
    def setUp(self):
        dials = DominionConfig.load()
        dials.dormancy_window_days = 30
        dials.save()

    def test_a_house_nobody_plays_goes_dormant_and_a_played_one_stays_awake(self):
        empty, _ = _house_with_member(logged_in_days_ago=None, name="House Katta")
        lull, _ = _house_with_member(logged_in_days_ago=20, name="House Lull")
        lapsed, _ = _house_with_member(logged_in_days_ago=45, name="House Lapsed")

        marked = mark_dormant_houses()

        self.assertEqual(marked, 2)
        self.assertIsNotNone(Organization.objects.get(pk=empty.pk).dormant_since)
        self.assertIsNotNone(Organization.objects.get(pk=lapsed.pk).dormant_since)
        self.assertIsNone(Organization.objects.get(pk=lull.pk).dormant_since)
        # a second pass changes nothing and keeps the first stamp
        first = Organization.objects.get(pk=empty.pk).dormant_since
        self.assertEqual(mark_dormant_houses(), 0)
        self.assertEqual(Organization.objects.get(pk=empty.pk).dormant_since, first)

    def test_a_house_with_no_income_stream_is_left_alone(self):
        idle = OrganizationFactory(name="The Debating Society", family=FamilyFactory())

        mark_dormant_houses()

        self.assertIsNone(Organization.objects.get(pk=idle.pk).dormant_since)

    def test_an_institution_with_no_family_keeps_its_books_running(self):
        # A guild or a temple has no one to app into it and hoard; only houses sleep.
        temple = OrganizationFactory(name="Temple of the Ash")
        OrgIncomeStream.objects.create(
            organization=temple,
            name="Temple tithes",
            kind=IncomeStreamKind.DOMAIN_TAX,
            gross_amount=500,
        )

        mark_dormant_houses()
        run_weekly_economy()

        self.assertIsNone(Organization.objects.get(pk=temple.pk).dormant_since)
        self.assertEqual(OrgIncomeStream.objects.get(organization=temple).uncollected_pool, 500)

    def test_the_weekly_economy_marks_then_skips_a_dormant_house(self):
        empty, _ = _house_with_member(logged_in_days_ago=None, name="House Katta")
        lull, _ = _house_with_member(logged_in_days_ago=3, name="House Lull")

        counts = run_weekly_economy()

        self.assertEqual(counts["dormant"], 1)
        self.assertEqual(OrgIncomeStream.objects.get(organization=empty).uncollected_pool, 0)
        self.assertEqual(OrgIncomeStream.objects.get(organization=lull).uncollected_pool, 1000)
        run_weekly_economy()
        self.assertEqual(OrgIncomeStream.objects.get(organization=lull).uncollected_pool, 2000)
        self.assertEqual(
            OrgIncomeStream.objects.get(organization=empty).uncollected_pool,
            0,
            "a lull accrues uncapped; an empty house accrues nothing",
        )

    def test_a_login_wakes_the_houses_the_account_plays_in(self):
        lapsed, account = _house_with_member(logged_in_days_ago=45, name="House Lapsed")
        other, _ = _house_with_member(logged_in_days_ago=None, name="House Other")
        mark_dormant_houses()
        self.assertIsNotNone(Organization.objects.get(pk=lapsed.pk).dormant_since)

        woken = wake_houses_for(account)

        self.assertEqual(woken, 1)
        self.assertIsNone(Organization.objects.get(pk=lapsed.pk).dormant_since)
        self.assertIsNotNone(Organization.objects.get(pk=other.pk).dormant_since)

    def test_a_roster_approval_wakes_the_house(self):
        # the tenure is the approval: a character taken up by a new player
        empty, _ = _house_with_member(logged_in_days_ago=None, name="House Katta")
        mark_dormant_houses()
        member = empty.memberships.get()
        entry = member.persona.character_sheet.roster_entry
        newcomer = AccountFactory()
        newcomer.last_login = timezone.now()
        newcomer.save(update_fields=["last_login"])

        RosterTenureFactory(roster_entry=entry, player_data=PlayerDataFactory(account=newcomer))
        woken = wake_houses_for(newcomer)

        self.assertEqual(woken, 1)
        self.assertIsNone(Organization.objects.get(pk=empty.pk).dormant_since)
