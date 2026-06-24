"""Tests for the public-reaction tidings feed service (#1450)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.secrets.factories import SecretFactory
from world.societies.factories import (
    LegendEntryFactory,
    OrganizationFactory,
    OrganizationMembershipFactory,
    SocietyFactory,
    SocietyReputationFactory,
)
from world.tidings.constants import FeedItemKind
from world.tidings.services import public_feed_for


class PublicFeedTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.persona = cls.sheet.primary_persona
        cls.society = SocietyFactory(name="The Compact")
        SocietyReputationFactory(persona=cls.persona, society=cls.society, value=300)

    def test_feed_includes_deeds_the_viewer_society_is_aware_of(self) -> None:
        deed = LegendEntryFactory(title="slew the wyrm")
        deed.societies_aware.add(self.society)

        feed = public_feed_for(self.persona)

        assert any(
            item.kind == FeedItemKind.DEED and item.headline == "slew the wyrm" for item in feed
        )

    def test_feed_includes_scandals_exposed_to_the_viewer_society(self) -> None:
        scandal = SecretFactory(content="consorts with the abyss")
        scandal.societies_exposed.add(self.society)

        feed = public_feed_for(self.persona)

        assert any(
            item.kind == FeedItemKind.SCANDAL and item.headline == "consorts with the abyss"
            for item in feed
        )

    def test_events_outside_the_viewer_societies_are_excluded(self) -> None:
        other_society = SocietyFactory(name="The Hollow")
        deed = LegendEntryFactory(title="unheard deed")
        deed.societies_aware.add(other_society)
        scandal = SecretFactory(content="unheard scandal")
        scandal.societies_exposed.add(other_society)

        headlines = {item.headline for item in public_feed_for(self.persona)}

        assert "unheard deed" not in headlines
        assert "unheard scandal" not in headlines

    def test_org_membership_society_also_grants_awareness(self) -> None:
        org_society = SocietyFactory(name="The Guild Realm")
        organization = OrganizationFactory(society=org_society)
        member_sheet = CharacterSheetFactory()
        OrganizationMembershipFactory(
            organization=organization, persona=member_sheet.primary_persona
        )
        deed = LegendEntryFactory(title="guild triumph")
        deed.societies_aware.add(org_society)

        feed = public_feed_for(member_sheet.primary_persona)

        assert any(item.headline == "guild triumph" for item in feed)

    def test_inactive_deeds_are_excluded(self) -> None:
        deed = LegendEntryFactory(title="forgotten deed", is_active=False)
        deed.societies_aware.add(self.society)

        headlines = {item.headline for item in public_feed_for(self.persona)}

        assert "forgotten deed" not in headlines

    def test_persona_with_no_society_awareness_gets_an_empty_feed(self) -> None:
        loner = CharacterSheetFactory().primary_persona

        assert public_feed_for(loner) == []
