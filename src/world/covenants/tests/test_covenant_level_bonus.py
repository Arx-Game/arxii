"""Covenant rank passive bonus (#762) — engagement-gated, level-scaled, derive-on-read.

A CovenantLevelBonus row authored against a ModifierTarget grants engaged
members a permanent buff equal to ``covenant.level * bonus_per_level``,
stacking additively across engaged covenants (mirrors covenant_role_bonus
stacking, spec 2026-05-09 §3.6).
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    make_engaged_member,
    wire_covenant_level_bonus_catalog,
)
from world.covenants.models import CovenantLevelBonus
from world.covenants.services import set_engaged_membership
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.mechanics.models import ModifierTarget
from world.mechanics.services import covenant_level_bonus, get_modifier_total


class CovenantLevelBonusServiceTests(TestCase):
    """Unit behaviour for the covenant_level_bonus derive-on-read service."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory(db_key="LevelBonusChar")
        cls.sheet = CharacterSheetFactory(character=cls.character, primary_persona=False)

        cls.stat_category = ModifierCategoryFactory(name="stat_level_bonus")
        cls.target = ModifierTargetFactory(name="LevelBonusTarget", category=cls.stat_category)
        cls.config = CovenantLevelBonus.objects.create(
            modifier_target=cls.target, bonus_per_level=1
        )

    def setUp(self) -> None:
        self.character.covenant_roles.invalidate()

    def test_returns_level_times_coefficient_for_engaged_member(self) -> None:
        """Engaged member of a level-3 covenant → 3 * 1 = 3."""
        cov = CovenantFactory(covenant_type=CovenantType.DURANCE, level=3)
        make_engaged_member(character_sheet=self.sheet, covenant=cov)
        self.character.covenant_roles.invalidate()
        self.assertEqual(covenant_level_bonus(self.sheet, self.target), 3)

    def test_returns_zero_when_not_engaged(self) -> None:
        """Active but non-engaged membership contributes nothing."""
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE, level=5),
            covenant_role=CovenantRoleFactory(covenant_type=CovenantType.DURANCE),
            # engaged defaults to False
        )
        self.character.covenant_roles.invalidate()
        self.assertEqual(covenant_level_bonus(self.sheet, self.target), 0)

    def test_returns_zero_when_no_config_for_target(self) -> None:
        """A target without a CovenantLevelBonus row returns 0."""
        other = ModifierTargetFactory(name="NoBonusTarget", category=self.stat_category)
        cov = CovenantFactory(covenant_type=CovenantType.DURANCE, level=4)
        make_engaged_member(character_sheet=self.sheet, covenant=cov)
        self.character.covenant_roles.invalidate()
        self.assertEqual(covenant_level_bonus(self.sheet, other), 0)

    def test_stacks_across_two_engaged_covenants(self) -> None:
        """Durance level 2 + Battle level 3 → (2 + 3) * 1 = 5 (stacks additively)."""
        durance = CovenantFactory(covenant_type=CovenantType.DURANCE, level=2)
        make_engaged_member(character_sheet=self.sheet, covenant=durance)

        battle = CovenantFactory(covenant_type=CovenantType.BATTLE, level=3)
        battle_role = CovenantRoleFactory(covenant_type=CovenantType.BATTLE)
        battle_m = CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=battle,
            covenant_role=battle_role,
        )
        set_engaged_membership(membership=battle_m)
        self.character.covenant_roles.invalidate()

        self.assertEqual(covenant_level_bonus(self.sheet, self.target), 5)


class CovenantLevelBonusIntegrationTests(TestCase):
    """get_modifier_total folds the covenant-level bonus into stat-category targets."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.character = CharacterFactory(db_key="LevelBonusIntChar")
        cls.sheet = CharacterSheetFactory(character=cls.character, primary_persona=False)

    def setUp(self) -> None:
        self.character.covenant_roles.invalidate()

    def test_get_modifier_total_includes_level_bonus(self) -> None:
        """After seeding the catalog, an engaged member's willpower total picks up the bonus."""
        config = wire_covenant_level_bonus_catalog()
        cov = CovenantFactory(covenant_type=CovenantType.DURANCE, level=3)
        make_engaged_member(character_sheet=self.sheet, covenant=cov)
        self.character.covenant_roles.invalidate()

        # Equipment-relevant 'stat' category target → equipment walk runs and folds in.
        total = get_modifier_total(self.sheet, config.modifier_target)
        self.assertEqual(total, 3)


class WireCovenantLevelBonusCatalogTests(TestCase):
    """The seed helper is idempotent (factories-as-seed-data convention)."""

    def test_idempotent(self) -> None:
        first = wire_covenant_level_bonus_catalog()
        second = wire_covenant_level_bonus_catalog()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(CovenantLevelBonus.objects.count(), 1)
        # The willpower stat target is reused, not duplicated.
        self.assertEqual(
            ModifierTarget.objects.filter(category__name="stat", name="willpower").count(), 1
        )
