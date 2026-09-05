"""Lineage rules for Family Templates and Vacancies (#3648)."""

from django.test import TestCase

from world.character_creation.factories import (
    BeginningsFactory,
    CharacterDraftFactory,
    OriginTemplateFactory,
)
from world.character_creation.services import select_origin_template
from world.character_creation.validators import get_lineage_errors
from world.roster.constants import CRIME_KIND_NAME
from world.roster.factories import FamilyFactory, FamilyKindFactory, KinSlotPoolFactory
from world.societies.factories import OrganizationFactory, VacancyFactory
from world.societies.houses.factories import HouseTemplateFactory
from world.societies.houses.models import HouseAspectDefinition, HouseAspectOption


class NamePathTemplateRulesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.beginning = BeginningsFactory()
        realm = cls.beginning.starting_area.realm
        cls.tpl_a = HouseTemplateFactory(
            name="Household A", realm=realm, name_pattern=r"[A-Z][a-z]+"
        )
        cls.tpl_b = HouseTemplateFactory(name="Household B", realm=realm)
        cls.charge = HouseAspectDefinition.objects.create(name="Charge", prompt="Kept what?")
        cls.granaries = HouseAspectOption.objects.create(definition=cls.charge, name="Granaries")
        cls.tpl_a.aspect_definitions.add(cls.charge)
        cls.served = OrganizationFactory(name="House Regency")
        cls.tpl_a.served_house_choices.add(cls.served)

    def _draft(self, upbringing, **extra):
        return CharacterDraftFactory(
            selected_area=self.beginning.starting_area,
            selected_beginnings=self.beginning,
            selected_origin_template=upbringing,
            **extra,
        )

    def test_two_templates_require_a_pick(self):
        upbringing = OriginTemplateFactory(
            beginning=self.beginning, family_templates=[self.tpl_a, self.tpl_b]
        )
        draft = self._draft(upbringing, draft_data={"new_family_name": "Wright"})
        assert "Choose a family template" in get_lineage_errors(draft)

    def test_aspects_and_pattern_and_served_house(self):
        upbringing = OriginTemplateFactory(beginning=self.beginning, family_templates=[self.tpl_a])
        draft = self._draft(upbringing, draft_data={"new_family_name": "wright"})
        errors = get_lineage_errors(draft)
        assert any("does not fit" in e for e in errors)
        assert any("Charge" in e for e in errors)
        draft.draft_data["new_family_name"] = "Wright"
        draft.draft_data["family_aspect_picks"] = {str(self.charge.id): [self.granaries.id]}
        draft.served_house = OrganizationFactory(name="House Elsewhere")
        assert "That house is not one your family could have served" in get_lineage_errors(draft)
        draft.served_house = self.served
        assert get_lineage_errors(draft) == []

    def test_malformed_name_pattern_fails_soft(self):
        """A staff-authored regex that does not compile must not 500 (#3648 review)."""
        bad = HouseTemplateFactory(
            name="Broken Pattern House",
            realm=self.beginning.starting_area.realm,
            name_pattern="[",
        )
        upbringing = OriginTemplateFactory(beginning=self.beginning, family_templates=[bad])
        draft = self._draft(upbringing, draft_data={"new_family_name": "Wright"})
        errors = get_lineage_errors(draft)
        assert "This family template's naming rule is misconfigured; tell staff" in errors

    def test_family_aspect_picks_as_a_string_fails_soft(self):
        draft = self._draft(
            OriginTemplateFactory(beginning=self.beginning, family_templates=[self.tpl_a]),
            draft_data={"new_family_name": "Wright", "family_aspect_picks": "garbage"},
        )
        assert "Your family's choices could not be read" in get_lineage_errors(draft)

    def test_family_aspect_picks_as_a_list_fails_soft(self):
        draft = self._draft(
            OriginTemplateFactory(beginning=self.beginning, family_templates=[self.tpl_a]),
            draft_data={"new_family_name": "Wright", "family_aspect_picks": [1, 2, 3]},
        )
        assert "Your family's choices could not be read" in get_lineage_errors(draft)

    def test_family_aspect_picks_inner_value_as_a_string_fails_soft(self):
        """A dict outer shape with a non-list inner value must not silently pass (#3648 review).

        Iterating a string yields its characters, so without an explicit
        ``isinstance(values, list)`` guard ``{"5": "34"}`` would int()-cast each
        digit character and silently produce ``{5: [3, 4]}`` instead of erroring.
        """
        draft = self._draft(
            OriginTemplateFactory(beginning=self.beginning, family_templates=[self.tpl_a]),
            draft_data={
                "new_family_name": "Wright",
                "family_aspect_picks": {str(self.charge.id): "34"},
            },
        )
        assert "Your family's choices could not be read" in get_lineage_errors(draft)


class VacancyRulesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.beginning = BeginningsFactory()
        realm = cls.beginning.starting_area.realm
        crime = FamilyKindFactory(name=CRIME_KIND_NAME)
        cls.family = FamilyFactory(name="the Marrow", kind=crime, influence=5, origin_realm=realm)
        cls.org = OrganizationFactory(name="the Marrow", family=cls.family)
        cls.claim = OriginTemplateFactory(
            beginning=cls.beginning, allows_name_family=False, allows_claim_family=True
        )
        cls.claim.claimable_kinds.add(crime)
        cls.none = OriginTemplateFactory(
            beginning=cls.beginning, allows_name_family=False, allows_no_family=True
        )
        cls.pool = KinSlotPoolFactory(family=cls.family, description="a niece")
        cls.kin = VacancyFactory(
            organization=cls.org,
            name="The niece",
            kin_pool=cls.pool,
            cg_point_cost=1,
            cost_per_influence=1,
        )
        cls.thug = VacancyFactory(organization=cls.org, name="Low thug", count_remaining=None)

    def _draft(self, upbringing, **extra):
        return CharacterDraftFactory(
            selected_area=self.beginning.starting_area,
            selected_beginnings=self.beginning,
            selected_origin_template=upbringing,
            **extra,
        )

    def test_claim_path_requires_a_kin_vacancy_when_one_is_offered(self):
        draft = self._draft(self.claim, family=self.family)
        assert "Choose your place in the family" in get_lineage_errors(draft)
        draft.selected_vacancy = self.kin
        assert get_lineage_errors(draft) == []

    def test_retainer_vacancy_in_own_family_is_refused(self):
        draft = self._draft(self.claim, family=self.family, selected_vacancy=self.thug)
        assert "Choose your place in the family" in get_lineage_errors(draft)

    def test_retainer_vacancy_on_the_none_path(self):
        draft = self._draft(
            self.none, selected_vacancy=self.thug, draft_data={"tarot_card_name": "The Moon"}
        )
        assert get_lineage_errors(draft) == []

    def test_kin_vacancy_prices_off_its_family_influence(self):
        draft = self._draft(self.claim, family=self.family, selected_vacancy=self.kin)
        assert draft.calculate_upbringing_cost() == 6

    def test_manual_kin_claim_with_a_vacancy_is_refused(self):
        draft = self._draft(
            self.claim, family=self.family, selected_vacancy=self.kin, claimed_kin_pool=self.pool
        )
        assert "Your place in the family already covers your kin slot" in get_lineage_errors(draft)

    def test_changing_upbringing_clears_the_vacancy(self):
        draft = self._draft(self.claim, family=self.family, selected_vacancy=self.kin)
        select_origin_template(draft, self.none)
        draft.refresh_from_db()
        assert draft.selected_vacancy is None
