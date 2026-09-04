"""Lineage validation and pricing for Upbringings (#3617)."""

from django.test import TestCase
from rest_framework import serializers

from world.character_creation.constants import FamilyPath, Stage
from world.character_creation.factories import (
    BeginningsFactory,
    CharacterDraftFactory,
    OriginTemplateFactory,
    OriginTemplateSlotChoiceFactory,
    OriginTemplateSlotFactory,
    StartingAreaFactory,
    make_unknown_upbringing,
)
from world.character_creation.services import select_origin_template, set_family_path
from world.character_creation.validators import get_lineage_errors
from world.roster.constants import CRIME_KIND_NAME, NOBLE_KIND_NAME
from world.roster.factories import (
    FamilyFactory,
    FamilyKindFactory,
    KinSlotPoolFactory,
    KinspersonFactory,
)


def _draft_for(template, **extra):
    beginning = template.beginning
    return CharacterDraftFactory(
        selected_area=beginning.starting_area,
        selected_beginnings=beginning,
        selected_origin_template=template,
        **extra,
    )


class LineagePathValidationTest(TestCase):
    def test_no_upbringing_is_the_first_error(self):
        draft = CharacterDraftFactory(selected_beginnings=BeginningsFactory())
        assert get_lineage_errors(draft) == ["Choose your upbringing"]

    def test_several_paths_require_a_choice(self):
        template = OriginTemplateFactory(allows_claim_family=True, allows_name_family=True)
        draft = _draft_for(template)
        assert "Choose how your family fits your upbringing" in get_lineage_errors(draft)

    def test_named_path_needs_a_name(self):
        draft = _draft_for(OriginTemplateFactory())  # name-only path
        assert get_lineage_errors(draft) == ["Name your family"]
        draft.draft_data["new_family_name"] = "The Cisternwrights"
        assert get_lineage_errors(draft) == []

    def test_named_path_rejects_a_taken_name(self):
        FamilyFactory(name="The Millers")
        draft = _draft_for(OriginTemplateFactory(), draft_data={"new_family_name": "the millers"})
        assert get_lineage_errors(draft) == ["A family by that name already exists"]

    def test_none_path_needs_a_tarot_card(self):
        draft = _draft_for(make_unknown_upbringing(BeginningsFactory()))
        assert get_lineage_errors(draft) == ["Select a tarot card for your surname"]
        draft.draft_data["tarot_card_name"] = "The Fool"
        assert get_lineage_errors(draft) == []

    def test_claim_path_checks_kind_and_realm(self):
        crime = FamilyKindFactory(name=CRIME_KIND_NAME)
        noble = FamilyKindFactory(name=NOBLE_KIND_NAME)
        template = OriginTemplateFactory(
            allows_name_family=False, named_family_kind=None, allows_claim_family=True
        )
        template.claimable_kinds.add(crime)
        realm = template.beginning.starting_area.realm
        draft = _draft_for(template)
        assert get_lineage_errors(draft) == ["Select a family"]
        draft.family = FamilyFactory(kind=noble, origin_realm=realm)
        assert get_lineage_errors(draft) == ["That family is not open to this upbringing"]
        other_realm = StartingAreaFactory().realm
        draft.family = FamilyFactory(kind=crime, origin_realm=other_realm)
        assert get_lineage_errors(draft) == ["That family is not from your starting area"]
        draft.family = FamilyFactory(kind=crime, origin_realm=realm)
        assert get_lineage_errors(draft) == []

    def test_claim_path_rejects_a_non_playable_family(self):
        crime = FamilyKindFactory(name=CRIME_KIND_NAME)
        template = OriginTemplateFactory(
            allows_name_family=False, named_family_kind=None, allows_claim_family=True
        )
        realm = template.beginning.starting_area.realm
        draft = _draft_for(template)
        draft.family = FamilyFactory(kind=crime, origin_realm=realm, is_playable=False)
        assert get_lineage_errors(draft) == ["That family is not open to this upbringing"]

    def test_trust_gated_upbringing_is_rejected(self):
        template = OriginTemplateFactory(trust_required=5)
        draft = _draft_for(template, draft_data={"new_family_name": "Vale"})
        assert "That upbringing is not available to you" in get_lineage_errors(draft)

    def test_template_from_another_beginning_is_rejected(self):
        template = OriginTemplateFactory()
        draft = CharacterDraftFactory(
            selected_beginnings=BeginningsFactory(), selected_origin_template=template
        )
        assert "Your upbringing does not belong to your beginning" in get_lineage_errors(draft)


class PromptValidationTest(TestCase):
    def test_required_prompt_on_the_chosen_path_blocks(self):
        template = OriginTemplateFactory()
        slot = OriginTemplateSlotFactory(template=template, name="Duty", is_required=True)
        draft = _draft_for(template, draft_data={"new_family_name": "Vale"})
        assert get_lineage_errors(draft) == ["Duty is required"]
        draft.draft_data["origin_slots"] = {str(slot.id): "We kept the cisterns."}
        assert get_lineage_errors(draft) == []

    def test_prompt_on_another_path_is_ignored(self):
        template = OriginTemplateFactory()
        OriginTemplateSlotFactory(
            template=template, name="Role", is_required=True, applies_to=FamilyPath.CLAIMED
        )
        draft = _draft_for(template, draft_data={"new_family_name": "Vale"})
        assert get_lineage_errors(draft) == []

    def test_optional_prompt_does_not_block(self):
        template = OriginTemplateFactory()
        OriginTemplateSlotFactory(template=template, is_required=False)
        draft = _draft_for(template, draft_data={"new_family_name": "Vale"})
        assert get_lineage_errors(draft) == []

    def test_pick_list_accepts_a_choice_and_rejects_a_foreign_one(self):
        template = OriginTemplateFactory()
        slot = OriginTemplateSlotFactory(template=template, name="Role", allows_text=False)
        mine = OriginTemplateSlotChoiceFactory(slot=slot)
        foreign = OriginTemplateSlotChoiceFactory()
        draft = _draft_for(template, draft_data={"new_family_name": "Vale"})
        draft.draft_data["origin_choices"] = {str(slot.id): foreign.id}
        assert get_lineage_errors(draft) == ["Invalid choice for Role"]
        draft.draft_data["origin_choices"] = {str(slot.id): mine.id}
        assert get_lineage_errors(draft) == []

    def test_pick_list_without_text_rejects_a_text_only_answer(self):
        template = OriginTemplateFactory()
        slot = OriginTemplateSlotFactory(template=template, name="Role", allows_text=False)
        OriginTemplateSlotChoiceFactory(slot=slot)
        draft = _draft_for(template, draft_data={"new_family_name": "Vale"})
        draft.draft_data["origin_slots"] = {str(slot.id): "Something else"}
        assert get_lineage_errors(draft) == ["Role is required"]


class UpbringingPricingTest(TestCase):
    """The Decision 6 table: head 0/3/12, lieutenant 0/1/4, muscle 1/1/1."""

    @classmethod
    def setUpTestData(cls):
        cls.crime = FamilyKindFactory(name=CRIME_KIND_NAME)
        cls.template = OriginTemplateFactory(
            allows_name_family=False, named_family_kind=None, allows_claim_family=True
        )
        cls.slot = OriginTemplateSlotFactory(template=cls.template, name="Role", allows_text=False)
        cls.head = OriginTemplateSlotChoiceFactory(slot=cls.slot, cost_per_influence=3)
        cls.lieutenant = OriginTemplateSlotChoiceFactory(slot=cls.slot, cost_per_influence=1)
        cls.muscle = OriginTemplateSlotChoiceFactory(slot=cls.slot, cg_point_cost=1)
        cls.realm = cls.template.beginning.starting_area.realm

    def _cost(self, choice, influence):
        family = FamilyFactory(kind=self.crime, origin_realm=self.realm, influence=influence)
        draft = _draft_for(self.template, family=family)
        draft.draft_data["origin_choices"] = {str(self.slot.id): choice.id}
        return draft.calculate_upbringing_cost()

    def test_matrix(self):
        matrix = (
            (self.head, (0, 3, 12)),
            (self.lieutenant, (0, 1, 4)),
            (self.muscle, (1, 1, 1)),
        )
        for choice, expected in matrix:
            for influence, want in zip((0, 1, 4), expected, strict=True):
                assert self._cost(choice, influence) == want, (choice.name, influence)

    def test_template_cost_and_breakdown_line(self):
        self.template.cg_point_cost = 6
        self.template.save()
        family = FamilyFactory(kind=self.crime, origin_realm=self.realm, influence=2)
        draft = _draft_for(self.template, family=family)
        draft.draft_data["origin_choices"] = {str(self.slot.id): self.head.id}
        rows = [r for r in draft.calculate_cg_points_breakdown() if r["category"] == "upbringing"]
        assert rows == [{"category": "upbringing", "item": self.template.name, "cost": 12}]

    def test_named_path_never_multiplies(self):
        template = OriginTemplateFactory()
        slot = OriginTemplateSlotFactory(template=template, allows_text=False)
        head = OriginTemplateSlotChoiceFactory(slot=slot, cost_per_influence=3, cg_point_cost=2)
        draft = _draft_for(template, draft_data={"new_family_name": "Vale"})
        draft.draft_data["origin_choices"] = {str(slot.id): head.id}
        assert draft.calculate_upbringing_cost() == 2

    def test_hidden_slot_choice_is_excluded_after_path_switch(self):
        """A claim-only choice picked before a path switch is not priced (#3617 review)."""
        template = OriginTemplateFactory(allows_claim_family=True, allows_name_family=True)
        slot = OriginTemplateSlotFactory(
            template=template, name="Role", allows_text=False, applies_to=FamilyPath.CLAIMED
        )
        choice = OriginTemplateSlotChoiceFactory(slot=slot, cost_per_influence=3)
        family = FamilyFactory(influence=2, origin_realm=template.beginning.starting_area.realm)
        draft = _draft_for(template, family_path=FamilyPath.CLAIMED, family=family)
        draft.draft_data["origin_choices"] = {str(slot.id): choice.id}
        draft.save(update_fields=["draft_data"])
        assert draft.calculate_upbringing_cost() == template.cg_point_cost + 6

        set_family_path(draft, FamilyPath.NAMED)
        draft.draft_data["new_family_name"] = "Vale"
        draft.save(update_fields=["draft_data"])

        assert draft.calculate_upbringing_cost() == template.cg_point_cost

    def test_over_budget_shows_on_the_heritage_stage(self):
        self.template.cg_point_cost = 10_000
        self.template.save()
        family = FamilyFactory(kind=self.crime, origin_realm=self.realm)
        draft = _draft_for(self.template, family=family)
        errors = draft.get_stage_validation_errors()[Stage.HERITAGE]
        assert any(e.startswith("CG points over budget") for e in errors)


class SelectionServiceTest(TestCase):
    def test_changing_the_upbringing_clears_dependent_state(self):
        first = OriginTemplateFactory()
        second = OriginTemplateFactory(beginning=first.beginning, allows_no_family=True)
        draft_data = {"new_family_name": "Vale", "origin_slots": {"1": "x"}}
        draft = _draft_for(first, draft_data=draft_data)
        draft.family_path = FamilyPath.NAMED
        select_origin_template(draft, second)
        draft.refresh_from_db()
        assert draft.selected_origin_template == second
        assert draft.family_path == ""
        assert "new_family_name" not in draft.draft_data
        assert "origin_slots" not in draft.draft_data

    def test_wrong_beginning_is_refused(self):
        draft = _draft_for(OriginTemplateFactory())
        with self.assertRaises(serializers.ValidationError):
            select_origin_template(draft, OriginTemplateFactory())

    def test_set_family_path_refuses_a_path_the_upbringing_lacks(self):
        draft = _draft_for(OriginTemplateFactory())
        with self.assertRaises(serializers.ValidationError):
            set_family_path(draft, FamilyPath.NONE)
        set_family_path(draft, FamilyPath.NAMED)
        assert draft.family_path == FamilyPath.NAMED

    def test_set_family_path_switch_clears_stale_family_state(self):
        """Switching paths drops the old path's family/kin claims (#3617 review).

        Prompts (origin_slots) are not path-anchored the same way: a slot with
        ``applies_to=ANY`` still applies after the switch, so they survive.
        """
        template = OriginTemplateFactory(allows_claim_family=True, allows_name_family=True)
        family = FamilyFactory()
        kin_slot = KinspersonFactory()
        kin_pool = KinSlotPoolFactory()
        draft = _draft_for(
            template,
            family_path=FamilyPath.CLAIMED,
            family=family,
            claimed_kin_slot=kin_slot,
            claimed_kin_pool=kin_pool,
            draft_data={"new_family_name": "stale", "origin_slots": {"1": "kept"}},
        )
        set_family_path(draft, FamilyPath.NAMED)
        draft.refresh_from_db()
        assert draft.family_path == FamilyPath.NAMED
        assert draft.family is None
        assert draft.claimed_kin_slot is None
        assert draft.claimed_kin_pool is None
        assert "new_family_name" not in draft.draft_data
        assert draft.draft_data["origin_slots"] == {"1": "kept"}

    def test_set_family_path_same_path_is_a_noop(self):
        template = OriginTemplateFactory(allows_claim_family=True, allows_name_family=True)
        family = FamilyFactory()
        draft = _draft_for(template, family_path=FamilyPath.CLAIMED, family=family)
        set_family_path(draft, FamilyPath.CLAIMED)
        draft.refresh_from_db()
        assert draft.family_path == FamilyPath.CLAIMED
        assert draft.family == family
