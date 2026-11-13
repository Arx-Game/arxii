"""The name path materializes Family + org + aspects + features + fealty (#3648)."""

from django.test import TestCase
from evennia.accounts.models import AccountDB

from world.character_creation.factories import OriginTemplateFactory
from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.roster.constants import COMMONER_KIND_NAME
from world.roster.factories import FamilyKindFactory
from world.roster.models import Family, KinSlotPool
from world.societies.factories import OrganizationFactory, OrganizationTypeFactory
from world.societies.houses.factories import HouseTemplateFactory
from world.societies.houses.models import (
    FealtyEdge,
    HouseCharterOption,
    HouseCharterQuestion,
    HouseFeature,
    OrganizationFacet,
    OrganizationFeature,
)
from world.societies.houses.services import house_for_family


class NamedFamilyMaterializeTest(FinalizationTestMixin, TestCase):
    def setUp(self) -> None:
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="named_family_org")
        self._setup_finalization_base(self, prefix="Named Org", height_min=700, height_max=800)
        commoner = FamilyKindFactory(name=COMMONER_KIND_NAME)
        self.served = OrganizationFactory(name="House Regency")
        self.template = HouseTemplateFactory(
            name="Caretaker Household",
            realm=self.area.realm,
            kind=commoner,
            org_type=OrganizationTypeFactory(name="commoner_family"),
            starting_kin_slots=2,
        )
        self.template.served_house_choices.add(self.served)
        self.charge = HouseCharterQuestion.objects.create(
            name="Charge", prompt="What did your family keep?"
        )
        self.granaries = HouseCharterOption.objects.create(definition=self.charge, name="Granaries")
        self.template.charter_questions.add(self.charge)
        self.registry = HouseFeature.objects.create(
            name="Registry-bound", slug="registry-bound", description="Named in the Archive."
        )
        self.template.features.add(self.registry)
        self.upbringing = OriginTemplateFactory(
            beginning=self.beginnings, family_templates=[self.template]
        )

    def _named_draft(self):
        draft = self._create_base_draft(
            new_family_name="Cisternwrights",
            family_facet_picks={str(self.charge.id): [self.granaries.id]},
        )
        draft.selected_origin_template = self.upbringing
        draft.served_house = self.served
        draft.draft_data.pop("tarot_card_name", None)
        draft.save()
        return draft

    def test_name_path_builds_the_full_package(self) -> None:
        character = finalize_character(self._named_draft(), add_to_roster=True)
        sheet = character.sheet_data

        family = Family.objects.get(name="Cisternwrights")
        assert family.influence == 0
        assert family.created_by_cg is True
        assert family.created_by == self.account
        assert family.kind.name == COMMONER_KIND_NAME
        assert sheet.family == family

        org = house_for_family(family)
        assert org is not None
        assert org.name == "Cisternwrights"
        assert org.org_type.name == "commoner_family"
        assert org.society == self.template.society
        assert OrganizationFacet.objects.filter(
            organization=org, definition=self.charge, option=self.granaries
        ).exists()
        assert OrganizationFeature.objects.filter(organization=org, feature=self.registry).exists()
        assert FealtyEdge.objects.filter(vassal=org, liege=self.served).exists()
        assert KinSlotPool.objects.filter(family=family).count() == 1
        assert org.ranks.count() == 5

    def test_name_path_writes_the_patron_the_charter_question_names(self) -> None:
        """#4205: the name path founds through the same builder, so the god picked on
        the charter's patron question is the family org's patron too. #5110: the pick
        is a god of the question's worship, carried in ``family_patron_being_id``."""
        from world.codex.factories import CodexEntryFactory
        from world.worship.factories import WorshippedBeingFactory, WorshipTraditionFactory

        liturgy = WorshipTraditionFactory(name="Church Liturgy")
        calyx = WorshippedBeingFactory(
            name="Calyx",
            tradition=liturgy,
            codex_entry=CodexEntryFactory(name="Calyx", is_public=True),
        )
        patron = HouseCharterQuestion.objects.create(
            name="Patron",
            prompt="Whom does the family serve?",
            sets_patron=True,
            patron_tradition=liturgy,
        )
        self.template.charter_questions.add(patron)
        draft = self._create_base_draft(
            new_family_name="Cisternwrights",
            family_facet_picks={str(self.charge.id): [self.granaries.id]},
            family_patron_being_id=calyx.pk,
        )
        draft.selected_origin_template = self.upbringing
        draft.served_house = self.served
        draft.draft_data.pop("tarot_card_name", None)
        draft.save()

        finalize_character(draft, add_to_roster=True)
        org = house_for_family(Family.objects.get(name="Cisternwrights"))
        assert org is not None
        assert org.patron == calyx

    def test_second_finalize_on_the_same_family_id_is_idempotent(self) -> None:
        draft = self._named_draft()
        finalize_character(draft, add_to_roster=True)
        assert Family.objects.filter(name="Cisternwrights").count() == 1
