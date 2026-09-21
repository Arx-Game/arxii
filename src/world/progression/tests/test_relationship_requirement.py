"""Tests for RelationshipRequirement — character-intrinsic label/tier gate (#2116, #3957).

Schema rework: dropped the freeform `relationship_target`/`minimum_level` stub
(previously hardcoded `return False`) for `required_type` (nullable FK to
`RelationshipType` — null = any type) + `minimum_tier` + `minimum_count`,
implemented as a count of the character's own qualifying open
`RelationshipLabel` rows, distinct by relationship (#3957: one side may carry
several labels, but only counts once).
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.classes.factories import CharacterClassFactory
from world.progression.models import ClassLevelUnlock, RelationshipRequirement
from world.relationships.factories import (
    CharacterRelationshipFactory,
    RelationshipLabelFactory,
    RelationshipTierFactory,
    RelationshipTypeFactory,
)


def _make_type_with_tiers(name: str):
    """A labelled type, plus the shared 1/2/3 tier ladder (idempotent across test classes)."""
    RelationshipTierFactory(tier_number=1)
    RelationshipTierFactory(tier_number=2)
    RelationshipTierFactory(tier_number=3)
    return RelationshipTypeFactory(name=name)


class RelationshipRequirementBoundaryTierTests(TestCase):
    """met/unmet compares the side's claimed ``tier`` against ``minimum_tier`` directly."""

    @classmethod
    def setUpTestData(cls):
        cls.character_class = CharacterClassFactory()
        cls.unlock = ClassLevelUnlock.objects.create(
            character_class=cls.character_class, target_level=4
        )
        cls.type = _make_type_with_tiers("Trust")

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.sheet = CharacterSheetFactory(character=self.character)
        self.other_sheet = CharacterSheetFactory()

    def _side_at_tier(self, tier_number: int, *, type_=None):
        relationship = CharacterRelationshipFactory(
            source=self.sheet, target=self.other_sheet, is_active=True, tier=tier_number
        )
        RelationshipLabelFactory(relationship=relationship, type=type_ or self.type)
        return relationship

    def test_below_minimum_tier_is_unmet(self) -> None:
        self._side_at_tier(1)
        req = RelationshipRequirement.objects.create(
            class_level_unlock=self.unlock,
            required_type=self.type,
            minimum_tier=2,
            minimum_count=1,
        )
        met, _message = req.is_met_by_character(self.character)
        assert met is False

    def test_at_minimum_tier_is_met(self) -> None:
        self._side_at_tier(2)
        req = RelationshipRequirement.objects.create(
            class_level_unlock=self.unlock,
            required_type=self.type,
            minimum_tier=2,
            minimum_count=1,
        )
        met, _message = req.is_met_by_character(self.character)
        assert met is True

    def test_above_minimum_tier_is_met(self) -> None:
        self._side_at_tier(3)
        req = RelationshipRequirement.objects.create(
            class_level_unlock=self.unlock,
            required_type=self.type,
            minimum_tier=2,
            minimum_count=1,
        )
        met, _message = req.is_met_by_character(self.character)
        assert met is True

    def test_no_relationship_at_all_is_unmet(self) -> None:
        req = RelationshipRequirement.objects.create(
            class_level_unlock=self.unlock,
            required_type=self.type,
            minimum_tier=1,
            minimum_count=1,
        )
        met, _message = req.is_met_by_character(self.character)
        assert met is False


class RelationshipRequirementTypeKindTests(TestCase):
    """``required_type`` narrows the count; null means any labelled type qualifies."""

    @classmethod
    def setUpTestData(cls):
        cls.character_class = CharacterClassFactory()
        cls.unlock = ClassLevelUnlock.objects.create(
            character_class=cls.character_class, target_level=4
        )
        cls.trust_type = _make_type_with_tiers("Trust2")
        cls.respect_type = RelationshipTypeFactory(name="Respect2")

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.sheet = CharacterSheetFactory(character=self.character)
        self.other_sheet = CharacterSheetFactory()
        self.relationship = CharacterRelationshipFactory(
            source=self.sheet, target=self.other_sheet, is_active=True, tier=1
        )
        RelationshipLabelFactory(relationship=self.relationship, type=self.respect_type)

    def test_specific_type_ignores_other_types(self) -> None:
        req = RelationshipRequirement.objects.create(
            class_level_unlock=self.unlock,
            required_type=self.trust_type,
            minimum_tier=1,
            minimum_count=1,
        )
        met, _message = req.is_met_by_character(self.character)
        assert met is False

    def test_null_type_matches_any_labelled_type(self) -> None:
        req = RelationshipRequirement.objects.create(
            class_level_unlock=self.unlock,
            required_type=None,
            minimum_tier=1,
            minimum_count=1,
        )
        met, _message = req.is_met_by_character(self.character)
        assert met is True


class RelationshipRequirementMinimumCountTests(TestCase):
    """``minimum_count`` requires that many distinct qualifying SIDES (relationships).

    Distinctness is by relationship, not by label — a side carrying two
    qualifying labels still counts once (#3957: ``.values("relationship_id")
    .distinct()``).
    """

    @classmethod
    def setUpTestData(cls):
        cls.character_class = CharacterClassFactory()
        cls.unlock = ClassLevelUnlock.objects.create(
            character_class=cls.character_class, target_level=4
        )
        cls.type = _make_type_with_tiers("TrackA")

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.sheet = CharacterSheetFactory(character=self.character)

    def _qualifying_side(self):
        other_sheet = CharacterSheetFactory()
        relationship = CharacterRelationshipFactory(
            source=self.sheet, target=other_sheet, is_active=True, tier=1
        )
        RelationshipLabelFactory(relationship=relationship, type=self.type)
        return relationship

    def test_one_qualifying_side_insufficient_for_count_two(self) -> None:
        self._qualifying_side()
        req = RelationshipRequirement.objects.create(
            class_level_unlock=self.unlock,
            required_type=None,
            minimum_tier=1,
            minimum_count=2,
        )
        met, _message = req.is_met_by_character(self.character)
        assert met is False

    def test_two_qualifying_sides_meets_count_two(self) -> None:
        self._qualifying_side()
        self._qualifying_side()
        req = RelationshipRequirement.objects.create(
            class_level_unlock=self.unlock,
            required_type=None,
            minimum_tier=1,
            minimum_count=2,
        )
        met, _message = req.is_met_by_character(self.character)
        assert met is True


class RelationshipRequirementNoLeakTests(TestCase):
    """Unmet text renders only the authored gate + the character's own progress."""

    @classmethod
    def setUpTestData(cls):
        cls.character_class = CharacterClassFactory()
        cls.unlock = ClassLevelUnlock.objects.create(
            character_class=cls.character_class, target_level=4
        )
        cls.type = _make_type_with_tiers("Secretive")

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.character = self.sheet.character
        self.sheet = CharacterSheetFactory(character=self.character)
        self.other_sheet = CharacterSheetFactory(character=CharacterFactory(db_key="OtherParty"))

    def test_unmet_message_never_names_other_character(self) -> None:
        relationship = CharacterRelationshipFactory(
            source=self.sheet, target=self.other_sheet, is_active=True, tier=1
        )
        RelationshipLabelFactory(relationship=relationship, type=self.type)
        req = RelationshipRequirement.objects.create(
            class_level_unlock=self.unlock,
            required_type=self.type,
            minimum_tier=3,
            minimum_count=1,
        )
        met, message = req.is_met_by_character(self.character)
        assert met is False
        assert "OtherParty" not in message

    def test_str_renders_authored_gate(self) -> None:
        req = RelationshipRequirement.objects.create(
            class_level_unlock=self.unlock,
            required_type=self.type,
            minimum_tier=2,
            minimum_count=3,
        )
        text = str(req)
        assert "Secretive" in text
        assert "2" in text
        assert "3" in text
