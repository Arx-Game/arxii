"""Tests for the public-reaction tidings feed service (#1450)."""

from django.test import TestCase, tag

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.secrets.factories import SecretFactory
from world.societies.factories import (
    LegendEntryFactory,
    OrganizationFactory,
    OrganizationMembershipFactory,
    PhilosophicalArchetypeFactory,
    SocietyFactory,
    SocietyReputationFactory,
)
from world.tidings.constants import FeedItemKind
from world.tidings.services import (
    hub_feed_for_room,
    public_feed_for,
    public_feed_for_societies,
)


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

    def test_scandal_category_derived_from_scandal_named_archetype(self) -> None:
        treacherous = PhilosophicalArchetypeFactory(name="Treacherous Scandal")
        scandal = SecretFactory(content="sold the family cipher")
        scandal.archetypes.add(treacherous)
        scandal.societies_exposed.add(self.society)

        item = next(
            i for i in public_feed_for(self.persona) if i.headline == "sold the family cipher"
        )

        assert item.category == "Treacherous Scandal"

    def test_non_scandal_archetypes_yield_no_category(self) -> None:
        valorous = PhilosophicalArchetypeFactory(name="Valorous")
        deed = LegendEntryFactory(title="held the gate")
        deed.archetypes.add(valorous)
        deed.societies_aware.add(self.society)

        item = next(i for i in public_feed_for(self.persona) if i.headline == "held the gate")

        assert item.category is None


@tag("postgres")  # Area.save() refreshes the areas_areaclosure materialized view
class SocietyScopedFeedTests(TestCase):
    """The extracted society-scoped core + the civic-hub room scope (#1450 final slice)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.crown = SocietyFactory(name="The Crown")
        cls.rival = SocietyFactory(name="The Rival Court")
        cls.kingdom = AreaFactory(level=AreaLevel.KINGDOM, dominant_society=cls.crown)
        cls.city = AreaFactory(level=AreaLevel.CITY, parent=cls.kingdom)
        cls.room = RoomProfileFactory(area=cls.city).objectdb

    def test_empty_society_scope_is_an_empty_feed(self) -> None:
        assert public_feed_for_societies([]) == []

    def test_society_scope_reads_deeds_and_scandals(self) -> None:
        deed = LegendEntryFactory(title="crowned the tourney")
        deed.societies_aware.add(self.crown)
        scandal = SecretFactory(content="poisoned the toast")
        scandal.societies_exposed.add(self.crown)

        headlines = {item.headline for item in public_feed_for_societies([self.crown.pk])}

        assert headlines == {"crowned the tourney", "poisoned the toast"}

    def test_hub_feed_scopes_to_the_rooms_local_societies(self) -> None:
        local_deed = LegendEntryFactory(title="local triumph")
        local_deed.societies_aware.add(self.crown)
        foreign_deed = LegendEntryFactory(title="foreign whisper")
        foreign_deed.societies_aware.add(self.rival)

        headlines = {item.headline for item in hub_feed_for_room(self.room)}

        assert "local triumph" in headlines
        assert "foreign whisper" not in headlines

    def test_hub_feed_for_missing_room_is_empty(self) -> None:
        assert hub_feed_for_room(None) == []

    def test_hub_feed_respects_limit(self) -> None:
        for index in range(4):
            deed = LegendEntryFactory(title=f"deed {index}")
            deed.societies_aware.add(self.crown)

        assert len(hub_feed_for_room(self.room, limit=2)) == 2
