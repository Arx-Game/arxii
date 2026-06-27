"""TDD tests for technique draft services (Task 3).

Covers:
- start_technique_draft / get_or_start_draft / get_active_draft round-trips
- set_draft_fields scalar + FK persistence
- add/remove restriction, capability grant, damage profile, applied condition
- discard_draft
- draft_to_design: derives level, raises TechniqueDraftIncomplete on missing fields
- validate_design_for_character: gift ownership gate (PlayerPolicy) + StaffPolicy no-op
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
)
from world.magic.exceptions import (
    GiftNotOwned,
    NoActiveTechniqueDraft,
    TechniqueDraftIncomplete,
    UnknownGift,
)
from world.magic.factories import (
    CharacterGiftFactory,
    EffectTypeFactory,
    GiftFactory,
    RestrictionFactory,
    TechniqueStyleFactory,
)
from world.magic.models import (
    TechniqueDraft,
    TechniqueDraftAppliedCondition,
    TechniqueDraftCapabilityGrant,
    TechniqueDraftDamageProfile,
)
from world.magic.services.technique_builder import (
    PlayerPolicy,
    StaffPolicy,
    get_technique_tier_budget,
    validate_design_for_character,
)
from world.magic.services.technique_draft import (
    add_draft_applied_condition,
    add_draft_capability_grant,
    add_draft_damage_profile,
    add_draft_restriction,
    discard_draft,
    draft_to_design,
    get_active_draft,
    get_or_start_draft,
    remove_draft_applied_condition,
    remove_draft_capability_grant,
    remove_draft_damage_profile,
    remove_draft_restriction,
    set_draft_fields,
    start_technique_draft,
)
from world.magic.types.technique_builder import TechniqueDesignInput


def _minimal_design(**override) -> TechniqueDesignInput:
    """Return a minimal TechniqueDesignInput for validate_design_for_character tests."""
    base: dict = {
        "name": "Test",
        "description": "",
        "gift_id": 1,
        "style_id": 1,
        "effect_type_id": 1,
        "action_category": "physical",
        "tier": 1,
        "intensity": 0,
        "control": 0,
        "anima_cost": 0,
        "level": 1,
    }
    base.update(override)
    return TechniqueDesignInput(**base)


# =============================================================================
# start / get round-trips
# =============================================================================


class StartGetDraftTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()

    def test_get_or_start_creates_draft(self) -> None:
        draft = get_or_start_draft(self.sheet)
        assert isinstance(draft, TechniqueDraft)
        assert draft.character_id == self.sheet.pk

    def test_get_or_start_idempotent(self) -> None:
        d1 = get_or_start_draft(self.sheet)
        d2 = get_or_start_draft(self.sheet)
        assert d1.pk == d2.pk

    def test_start_sets_name(self) -> None:
        draft = start_technique_draft(self.sheet, name="Ember Strike")
        assert draft.name == "Ember Strike"
        assert draft.character_id == self.sheet.pk

    def test_start_replaces_existing_draft(self) -> None:
        old = start_technique_draft(self.sheet, name="Old")
        new = start_technique_draft(self.sheet, name="New")
        assert new.pk != old.pk
        assert not TechniqueDraft.objects.filter(pk=old.pk).exists()

    def test_get_active_draft_returns_existing(self) -> None:
        draft = start_technique_draft(self.sheet, name="Active")
        found = get_active_draft(self.sheet)
        assert found.pk == draft.pk

    def test_get_active_draft_raises_when_none(self) -> None:
        fresh_sheet = CharacterSheetFactory()
        with self.assertRaises(NoActiveTechniqueDraft):
            get_active_draft(fresh_sheet)


# =============================================================================
# set_draft_fields
# =============================================================================


class SetDraftFieldsTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.gift = GiftFactory(creator=cls.sheet)
        cls.style = TechniqueStyleFactory()
        cls.effect_type = EffectTypeFactory()

    def test_set_scalar_fields_persists(self) -> None:
        draft = start_technique_draft(self.sheet, name="Base")
        set_draft_fields(draft, intensity=5, control=3, anima_cost=2, tier=2)
        draft.refresh_from_db()
        assert draft.intensity == 5
        assert draft.control == 3
        assert draft.anima_cost == 2
        assert draft.tier == 2

    def test_set_fk_fields_persists(self) -> None:
        draft = start_technique_draft(self.sheet, name="Base")
        set_draft_fields(draft, gift=self.gift, style=self.style, effect_type=self.effect_type)
        draft.refresh_from_db()
        assert draft.gift_id == self.gift.pk
        assert draft.style_id == self.style.pk
        assert draft.effect_type_id == self.effect_type.pk


# =============================================================================
# restrictions + payload children
# =============================================================================


class DraftRestrictionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.restriction = RestrictionFactory()

    def test_add_and_remove_restriction(self) -> None:
        draft = start_technique_draft(self.sheet, name="R")
        add_draft_restriction(draft, self.restriction)
        assert draft.restrictions.filter(pk=self.restriction.pk).exists()
        remove_draft_restriction(draft, self.restriction)
        assert not draft.restrictions.filter(pk=self.restriction.pk).exists()


class DraftCapabilityGrantTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.cap = CapabilityTypeFactory()

    def test_add_and_remove_capability_grant(self) -> None:
        draft = start_technique_draft(self.sheet, name="Cap")
        row = add_draft_capability_grant(
            draft, capability=self.cap, base_value=4, intensity_multiplier=0.5
        )
        assert isinstance(row, TechniqueDraftCapabilityGrant)
        assert row.capability_id == self.cap.pk
        assert row.base_value == 4

        remove_draft_capability_grant(row.pk)
        assert not TechniqueDraftCapabilityGrant.objects.filter(pk=row.pk).exists()


class DraftDamageProfileTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()

    def test_add_and_remove_damage_profile(self) -> None:
        draft = start_technique_draft(self.sheet, name="Dam")
        row = add_draft_damage_profile(
            draft, damage_type=None, base_damage=5, damage_intensity_multiplier=0.0
        )
        assert isinstance(row, TechniqueDraftDamageProfile)
        assert row.base_damage == 5

        remove_draft_damage_profile(row.pk)
        assert not TechniqueDraftDamageProfile.objects.filter(pk=row.pk).exists()


class DiscardDraftTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()

    def test_discard_removes_draft(self) -> None:
        start_technique_draft(self.sheet, name="Gone")
        discard_draft(self.sheet)
        assert not TechniqueDraft.objects.filter(character=self.sheet).exists()

    def test_discard_noop_when_no_draft(self) -> None:
        fresh = CharacterSheetFactory()
        discard_draft(fresh)  # must not raise


# =============================================================================
# draft_to_design
# =============================================================================


class DraftToDesignTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.gift = GiftFactory(creator=cls.sheet)
        cls.style = TechniqueStyleFactory()
        cls.effect_type = EffectTypeFactory()

    def _make_complete_draft(self) -> TechniqueDraft:
        draft = start_technique_draft(self.sheet, name="Fire Bolt")
        set_draft_fields(
            draft,
            description="A bolt of fire.",
            gift=self.gift,
            style=self.style,
            effect_type=self.effect_type,
            action_category="physical",
            tier=1,
            intensity=3,
            control=2,
            anima_cost=2,
        )
        return draft

    def test_builds_design_with_derived_level(self) -> None:
        draft = self._make_complete_draft()
        design = draft_to_design(draft)

        assert isinstance(design, TechniqueDesignInput)
        expected_level = get_technique_tier_budget(1).representative_level
        assert design.level == expected_level
        assert design.name == "Fire Bolt"
        assert design.description == "A bolt of fire."
        assert design.gift_id == self.gift.pk
        assert design.style_id == self.style.pk
        assert design.effect_type_id == self.effect_type.pk
        assert design.tier == 1
        assert design.intensity == 3
        assert design.control == 2
        assert design.anima_cost == 2

    def test_raises_incomplete_all_required_missing(self) -> None:
        """Blank draft (no name, no FK knobs, no tier) raises TechniqueDraftIncomplete."""
        draft = TechniqueDraft.objects.create(character=CharacterSheetFactory())
        with self.assertRaises(TechniqueDraftIncomplete) as ctx:
            draft_to_design(draft)

        exc = ctx.exception
        assert "name" in exc.missing_fields
        assert "gift" in exc.missing_fields
        assert "style" in exc.missing_fields
        assert "effect_type" in exc.missing_fields
        assert "action_category" in exc.missing_fields
        assert "tier" in exc.missing_fields

    def test_raises_incomplete_partial_missing(self) -> None:
        """Draft with only a name set still raises for remaining required fields."""
        draft = start_technique_draft(self.sheet, name="Named")
        with self.assertRaises(TechniqueDraftIncomplete) as ctx:
            draft_to_design(draft)

        exc = ctx.exception
        assert "name" not in exc.missing_fields  # name is set
        assert "gift" in exc.missing_fields


# =============================================================================
# draft_to_design payload read paths
# =============================================================================


class DraftToDesignPayloadTests(TestCase):
    """Verify that draft_to_design carries restriction_ids, capability_grants,
    damage_profiles, and applied_conditions into the resulting TechniqueDesignInput."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.gift = GiftFactory(creator=cls.sheet)
        cls.style = TechniqueStyleFactory()
        cls.effect_type = EffectTypeFactory()
        cls.restriction = RestrictionFactory()
        cls.cap = CapabilityTypeFactory()
        cls.damage_type = DamageTypeFactory()
        cls.condition = ConditionTemplateFactory()

    def test_payload_fields_carried_through(self) -> None:
        draft = start_technique_draft(self.sheet, name="Payload Test")
        set_draft_fields(
            draft,
            description="Test payload.",
            gift=self.gift,
            style=self.style,
            effect_type=self.effect_type,
            action_category="physical",
            tier=1,
            intensity=2,
            control=1,
            anima_cost=1,
        )
        add_draft_restriction(draft, self.restriction)
        grant_row = add_draft_capability_grant(
            draft, capability=self.cap, base_value=3, intensity_multiplier=0.5
        )
        damage_row = add_draft_damage_profile(
            draft, damage_type=self.damage_type, base_damage=4, damage_intensity_multiplier=1.0
        )
        condition_row = add_draft_applied_condition(
            draft, condition=self.condition, base_severity=2, base_duration_rounds=3
        )

        design = draft_to_design(draft)

        assert self.restriction.pk in design.restriction_ids
        assert len(design.capability_grants) == 1
        assert design.capability_grants[0].capability_id == grant_row.capability_id
        assert design.capability_grants[0].base_value == 3
        assert len(design.damage_profiles) == 1
        assert design.damage_profiles[0].damage_type_id == damage_row.damage_type_id
        assert design.damage_profiles[0].base_damage == 4
        assert len(design.applied_conditions) == 1
        assert design.applied_conditions[0].condition_id == condition_row.condition_id
        assert design.applied_conditions[0].base_severity == 2
        assert design.applied_conditions[0].base_duration_rounds == 3


# =============================================================================
# validate_design_for_character
# =============================================================================


class ValidateDesignForCharacterTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.gift = GiftFactory(creator=cls.sheet)
        cls.other_gift = GiftFactory()  # not owned by cls.sheet
        CharacterGiftFactory(character=cls.sheet, gift=cls.gift)

    def test_player_policy_raises_for_unowned_gift(self) -> None:
        design = _minimal_design(gift_id=self.other_gift.pk)
        with self.assertRaises(GiftNotOwned):
            validate_design_for_character(design, PlayerPolicy(), self.sheet)

    def test_player_policy_passes_for_owned_gift(self) -> None:
        design = _minimal_design(gift_id=self.gift.pk)
        # Must not raise
        validate_design_for_character(design, PlayerPolicy(), self.sheet)

    def test_staff_policy_noop_for_unowned_gift(self) -> None:
        design = _minimal_design(gift_id=self.other_gift.pk)
        # Must not raise even when the gift is not owned
        validate_design_for_character(design, StaffPolicy(), None)

    def test_player_policy_raises_for_nonexistent_gift(self) -> None:
        design = _minimal_design(gift_id=999999)
        with self.assertRaises(UnknownGift):
            validate_design_for_character(design, PlayerPolicy(), self.sheet)


# =============================================================================
# applied conditions (payload child — light smoke test)
# =============================================================================


class DraftAppliedConditionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()

    def test_add_and_remove_applied_condition(self) -> None:
        condition = ConditionTemplateFactory()
        draft = start_technique_draft(self.sheet, name="Cond")
        row = add_draft_applied_condition(draft, condition=condition, base_severity=2)
        assert row.condition_id == condition.pk
        assert row.base_severity == 2

        remove_draft_applied_condition(row.pk)
        assert not TechniqueDraftAppliedCondition.objects.filter(pk=row.pk).exists()
