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
    HouseAspectDefinition,
    HouseAspectOption,
    HouseFeature,
    OrganizationAspect,
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
        self.charge = HouseAspectDefinition.objects.create(
            name="Charge", prompt="What did your family keep?"
        )
        self.granaries = HouseAspectOption.objects.create(definition=self.charge, name="Granaries")
        self.template.aspect_definitions.add(self.charge)
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
            family_aspect_picks={str(self.charge.id): [self.granaries.id]},
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
        assert OrganizationAspect.objects.filter(
            organization=org, definition=self.charge, option=self.granaries
        ).exists()
        assert OrganizationFeature.objects.filter(organization=org, feature=self.registry).exists()
        assert FealtyEdge.objects.filter(vassal=org, liege=self.served).exists()
        assert KinSlotPool.objects.filter(family=family).count() == 1
        assert org.ranks.count() == 5

    def test_second_finalize_on_the_same_family_id_is_idempotent(self) -> None:
        draft = self._named_draft()
        finalize_character(draft, add_to_roster=True)
        assert Family.objects.filter(name="Cisternwrights").count() == 1
