"""One test per authoring recipe in docs/systems/family-authoring-recipes.md (#3617, #3648).

Each test authors ONLY the rows the recipe names, through the same models staff
use in admin. Recipes 1, 2, 3, 9, 10, 11 and 12 build an Upbringing and assert on
``get_lineage_errors``/``calculate_upbringing_cost``, the CG-facing surface;
recipes 4 through 7 have no CG surface of their own and instead assert
directly on the houses/societies rows the recipe names (``FealtyEdge``,
``OrgPact``, ``OrganizationAspect``/``OrganizationFeature``). Recipe 8 (a
claim-path role pick-list priced by influence) is folded into 11 and 12, which
cover the same ground through a Vacancy instead. If a recipe stops working,
this file says which one.
"""

from django.test import TestCase
from django.utils import timezone

from world.character_creation.constants import FamilyPath
from world.character_creation.factories import (
    BeginningsFactory,
    CharacterDraftFactory,
    OriginTemplateFactory,
    OriginTemplateSlotFactory,
    make_unknown_upbringing,
)
from world.character_creation.validators import get_lineage_errors
from world.roster.constants import CRIME_KIND_NAME, NOBLE_KIND_NAME
from world.roster.factories import FamilyFactory, FamilyKindFactory
from world.societies.factories import OrganizationFactory
from world.societies.houses.models import (
    FealtyEdge,
    HouseAspectDefinition,
    HouseAspectOption,
    HouseFeature,
    OrganizationAspect,
    OrganizationFeature,
    OrgPact,
    PactKind,
)
from world.societies.houses.services import house_for_family


def _draft(template, **extra):
    return CharacterDraftFactory(
        selected_area=template.beginning.starting_area,
        selected_beginnings=template.beginning,
        selected_origin_template=template,
        **extra,
    )


class UpbringingRecipesTest(TestCase):
    def test_recipe_1_caretaker_family_upbringing(self):
        """Recipe 1: an Upbringing for a beginning (name your own family + a write-in)."""
        caretaker = BeginningsFactory(name="Caretaker")
        template = OriginTemplateFactory(
            beginning=caretaker,
            name="Caretaker family",
            frame_narrative="Your family took a Caretaker Vow and has kept it since.",
        )
        slot = OriginTemplateSlotFactory(
            template=template,
            name="Duty",
            prompt="What did your family keep running in Arx?",
        )
        draft = _draft(
            template,
            draft_data={
                "new_family_name": "Cisternwrights",
                "origin_slots": {str(slot.id): "The cisterns."},
            },
        )
        assert get_lineage_errors(draft) == []
        assert draft.calculate_upbringing_cost() == 0

    def test_recipe_2_orphan_upbringing(self):
        """Recipe 2: an orphan is an Upbringing on the none path with its own prompts."""
        template = OriginTemplateFactory(
            beginning=BeginningsFactory(),
            name="Orphan of the cumberwards",
            allows_name_family=False,
            allows_no_family=True,
        )
        slot = OriginTemplateSlotFactory(
            template=template,
            name="Survival",
            prompt="How did you survive?",
            applies_to=FamilyPath.NONE,
        )
        draft = _draft(template, draft_data={"tarot_card_name": "The Fool"})
        assert get_lineage_errors(draft) == ["Survival is required"]
        draft.draft_data["origin_slots"] = {str(slot.id): "Running for a crime family."}
        assert get_lineage_errors(draft) == []

    def test_recipe_3_amnesiac_beginning(self):
        """Recipe 3: Sleeper = one 'Unknown' Upbringing, no prompts."""
        template = make_unknown_upbringing(BeginningsFactory(name="Sleeper"))
        draft = _draft(template, draft_data={"tarot_card_name": "The Fool"})
        assert get_lineage_errors(draft) == []
        assert draft.resolve_family_path() == FamilyPath.NONE

    def test_recipe_4_family_with_influence(self):
        """Recipe 4: a staff-authored family with influence, rooted in an organisation."""
        crime = FamilyKindFactory(name=CRIME_KIND_NAME)
        family = FamilyFactory(name="The Vessari", kind=crime, influence=4)
        org = OrganizationFactory(name="The Vessari", family=family)
        assert house_for_family(family) == org
        assert family.influence == 4

    def test_recipe_5_subordinate_family(self):
        """Recipe 5: subordination is a FealtyEdge (or parent_org), never a new field."""
        noble = FamilyKindFactory(name=NOBLE_KIND_NAME)
        liege_org = OrganizationFactory(family=FamilyFactory(kind=noble, influence=5))
        clan_org = OrganizationFactory(
            family=FamilyFactory(
                name="Clan Ashfang",
                kind=FamilyKindFactory(name="Clan"),
                influence=2,
            )
        )
        edge = FealtyEdge.objects.create(vassal=clan_org, liege=liege_org)
        assert edge.liege == liege_org
        assert clan_org.fealty.liege == liege_org

    def test_recipe_6_patron_family(self):
        """Recipe 6: patronage is an OrgPact on an authored PactKind row."""
        patronage = PactKind.objects.create(name="Patronage", allied_share_pct=10)
        humble = OrganizationFactory(
            family=FamilyFactory(kind=FamilyKindFactory(name="Humble"), influence=3)
        )
        crime = OrganizationFactory(
            family=FamilyFactory(kind=FamilyKindFactory(name=CRIME_KIND_NAME), influence=2)
        )
        pact = OrgPact.objects.create(
            kind=patronage, party_a=humble, party_b=crime, ratified_at=timezone.now()
        )
        assert pact.is_standing

    def test_recipe_7_culture_specific_fact(self):
        """Recipe 7: quiddity = aspect definition + options; Letter of Marque = feature."""
        org = OrganizationFactory(
            family=FamilyFactory(kind=FamilyKindFactory(name=NOBLE_KIND_NAME), influence=3)
        )
        quiddity = HouseAspectDefinition.objects.create(
            name="House Quiddity", prompt="Which quiddity marks your house?"
        )
        pride = HouseAspectOption.objects.create(definition=quiddity, name="Pride")
        OrganizationAspect.objects.create(organization=org, definition=quiddity, option=pride)
        marque = HouseFeature.objects.create(
            name="Letter of Marque and Reprisal",
            slug="letter-of-marque",
            description="Licensed to raid.",
        )
        OrganizationFeature.objects.create(organization=org, feature=marque)
        assert list(org.aspects.values_list("option__name", flat=True)) == ["Pride"]
        assert org.features.filter(feature__slug="letter-of-marque").exists()

    def test_recipe_9_new_family_kind(self):
        """Recipe 9: a new kind is a row; an Upbringing offers it by picking the row."""
        humble = FamilyKindFactory(name="Humble", description="Stripped-titles gentry.")
        template = OriginTemplateFactory(
            beginning=BeginningsFactory(),
            name="One of the Humble",
            cg_point_cost=6,
            allows_name_family=False,
            allows_claim_family=True,
        )
        template.claimable_kinds.add(humble)
        family = FamilyFactory(
            kind=humble, influence=2, origin_realm=template.beginning.starting_area.realm
        )
        draft = _draft(template, family=family)
        assert get_lineage_errors(draft) == []
        assert draft.calculate_upbringing_cost() == 6

    def test_recipe_10_family_template_on_the_name_path(self):
        """Recipe 10: a Family Template makes every named family of a type come out the same."""
        from world.societies.factories import OrganizationFactory
        from world.societies.houses.factories import HouseTemplateFactory

        caretaker = BeginningsFactory(name="Caretaker")
        template = HouseTemplateFactory(
            name="Caretaker Household", realm=caretaker.starting_area.realm
        )
        charge = HouseAspectDefinition.objects.create(name="Charge", prompt="What did you keep?")
        granaries = HouseAspectOption.objects.create(definition=charge, name="Granaries")
        template.aspect_definitions.add(charge)
        template.served_house_choices.add(OrganizationFactory(name="House Regency"))
        upbringing = OriginTemplateFactory(
            beginning=caretaker, name="Raised to a Charge", family_templates=[template]
        )
        draft = _draft(
            upbringing,
            draft_data={
                "new_family_name": "Cisternwright",
                "family_aspect_picks": {str(charge.id): [granaries.id]},
            },
        )
        assert get_lineage_errors(draft) == []
        assert draft.resolve_family_template() == template

    def test_recipe_11_kin_vacancy_backed_by_a_pool(self):
        """Recipe 11: a place in a staff family, priced by influence, backed by a slot pool."""
        from world.roster.factories import KinSlotPoolFactory
        from world.societies.factories import OrganizationFactory, VacancyFactory

        noble = FamilyKindFactory(name=NOBLE_KIND_NAME)
        beginning = BeginningsFactory(name="Infernal Nobility")
        family = FamilyFactory(
            name="House Ash", kind=noble, influence=8, origin_realm=beginning.starting_area.realm
        )
        org = OrganizationFactory(name="House Ash", family=family)
        pool = KinSlotPoolFactory(family=family, description="a daughter of the house")
        daughter = VacancyFactory(
            organization=org,
            name="Third daughter",
            kin_pool=pool,
            importance=1,
            presumed_importance=5,
            cg_point_cost=1,
            cost_per_influence=1,
        )
        upbringing = OriginTemplateFactory(
            beginning=beginning,
            name="Of the Blood",
            allows_name_family=False,
            allows_claim_family=True,
        )
        upbringing.claimable_kinds.add(noble)
        draft = _draft(upbringing, family=family, selected_vacancy=daughter)
        assert get_lineage_errors(draft) == []
        assert draft.calculate_upbringing_cost() == 9
        assert daughter.basis == "kin"

    def test_recipe_12_standing_retainer_vacancy(self):
        """Recipe 12: a standing opening anyone reachable may take, on any path."""
        from world.societies.factories import OrganizationFactory, VacancyFactory

        crime = FamilyKindFactory(name=CRIME_KIND_NAME)
        beginning = BeginningsFactory(name="Off the Street")
        family = FamilyFactory(
            name="the Marrow", kind=crime, influence=5, origin_realm=beginning.starting_area.realm
        )
        org = OrganizationFactory(name="the Marrow", family=family)
        thug = VacancyFactory(organization=org, name="Low thug", count_remaining=None)
        upbringing = OriginTemplateFactory(
            beginning=beginning, allows_name_family=False, allows_no_family=True
        )
        draft = _draft(
            upbringing, selected_vacancy=thug, draft_data={"tarot_card_name": "The Moon"}
        )
        assert get_lineage_errors(draft) == []
        assert draft.calculate_upbringing_cost() == 0
        assert thug.is_open
