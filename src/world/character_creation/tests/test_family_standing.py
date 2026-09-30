"""CG family standing (#4060 slice 4): an Upbringing answer sets how a new family starts."""

from django.test import TestCase
from evennia.accounts.models import AccountDB

from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_creation.constants import QuestionKind
from world.character_creation.factories import (
    OriginTemplateFactory,
    OriginTemplateSlotChoiceFactory,
    OriginTemplateSlotFactory,
)
from world.character_creation.questionnaire import picked_family_standing
from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.roster.constants import COMMONER_KIND_NAME
from world.roster.factories import FamilyKindFactory
from world.roster.models import Family
from world.societies.factories import OrganizationFactory, OrganizationTypeFactory
from world.societies.houses.factories import HoldingKindFactory, HouseTemplateFactory
from world.societies.houses.models import DomainHolding
from world.societies.houses.services import create_domain, house_for_family


class FamilyStandingTests(FinalizationTestMixin, TestCase):
    def setUp(self):
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="standing_family")
        self._setup_finalization_base(self, prefix="Standing", height_min=700, height_max=800)
        capital = AreaFactory(level=AreaLevel.BARONY, realm=self.area.realm, is_capital=True)
        self.mayor = OrganizationFactory(name="Office of the Lord Mayor")
        self.home = create_domain(area=capital, name="Luxen", owner_org=self.mayor)
        self.tavern = HoldingKindFactory(name="Tavern", base_gross=1000)
        self.template = HouseTemplateFactory(
            name="Trading Household",
            realm=self.area.realm,
            kind=FamilyKindFactory(name=COMMONER_KIND_NAME),
            org_type=OrganizationTypeFactory(name="commoner_family"),
        )
        self.template.holdings.add(self.tavern)
        self.upbringing = OriginTemplateFactory(
            beginning=self.beginnings, family_templates=[self.template]
        )
        question = OriginTemplateSlotFactory(
            template=self.upbringing,
            kind=QuestionKind.PICK,
            prompt="How did the family fare?",
            is_required=False,
        )
        self.comfortable = OriginTemplateSlotChoiceFactory(
            slot=question, name="In comfort", family_standing=75
        )
        OriginTemplateSlotChoiceFactory(slot=question, name="Hand to mouth", family_standing=25)

    def _named_draft(self, *, choice=None):
        draft = self._create_base_draft(new_family_name="Cisternwrights")
        draft.selected_origin_template = self.upbringing
        draft.draft_data.pop("tarot_card_name", None)
        if choice is not None:
            draft.draft_data["origin_choices"] = {str(choice.slot_id): choice.id}
        draft.save()
        return draft

    def test_the_picked_answer_is_the_familys_standing(self):
        draft = self._named_draft(choice=self.comfortable)
        self.assertEqual(picked_family_standing(draft), 75)
        self.assertIsNone(picked_family_standing(self._named_draft()))

    def test_a_new_family_gets_its_templates_businesses_on_the_home_domain_at_that_standing(self):
        finalize_character(self._named_draft(choice=self.comfortable), add_to_roster=True)

        family = Family.objects.get(name="Cisternwrights")
        org = house_for_family(family)
        holding = DomainHolding.objects.get(owner_org=org)
        self.assertEqual(holding.domain, self.home)
        self.assertEqual(holding.kind, self.tavern)
        self.assertEqual(holding.standing, 75)
        self.assertEqual(holding.income_stream.organization, org)

    def test_no_standing_answer_leaves_the_default(self):
        finalize_character(self._named_draft(), add_to_roster=True)

        org = house_for_family(Family.objects.get(name="Cisternwrights"))
        self.assertEqual(DomainHolding.objects.get(owner_org=org).standing, 50)
