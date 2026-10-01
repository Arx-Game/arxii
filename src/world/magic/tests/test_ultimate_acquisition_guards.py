"""Ultimates never become ordinary techniques (#4098 decision 4)."""

from django.test import TestCase

from world.achievements.constants import AccessChangeSource
from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
)
from world.covenants.models import CovenantRoleGiftGrant
from world.covenants.sphinx import judge_vow
from world.magic.constants import AcquisitionOrigin, TechniqueFunction
from world.magic.exceptions import UltimateNotLearnable
from world.magic.factories import (
    CharacterGiftFactory,
    GiftFactory,
    KnownUltimateFactory,
    PathGiftGrantFactory,
    TechniqueFactory,
    TechniqueFunctionTagFactory,
    TraditionFactory,
    UltimateTechniqueFactory,
)
from world.magic.services.cg_catalog import get_technique_options
from world.magic.services.technique_acquisition import learn_technique
from world.progression.models import TechniqueKnownRequirement


class LearnSeamRefusesUltimateTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.ultimate = UltimateTechniqueFactory()
        CharacterGiftFactory(character=cls.sheet, gift=cls.ultimate.gift)

    def test_learn_technique_refuses_even_gm_grant(self) -> None:
        with self.assertRaises(UltimateNotLearnable):
            learn_technique(
                self.sheet,
                self.ultimate,
                source=AccessChangeSource.GM_AWARD,
                origin=AcquisitionOrigin.GM_GRANT,
            )


class CatalogPoolExcludesUltimateTests(TestCase):
    def test_starter_pool_never_returns_an_ultimate(self) -> None:
        ultimate = UltimateTechniqueFactory()
        grant = PathGiftGrantFactory(gift=ultimate.gift)
        # .add() bypasses limit_choices_to: simulate a row slipped in before the flag.
        grant.starter_techniques.add(ultimate)
        options = get_technique_options(
            grant.path, grant.gift, TraditionFactory(), include_unready=True
        )
        self.assertNotIn(ultimate, options.pool)


class KnownUltimateSatisfiesRequirementTests(TestCase):
    def test_upgrade_requirement_met_by_known_ultimate(self) -> None:
        sheet = CharacterSheetFactory()
        earlier = UltimateTechniqueFactory()
        upgrade = UltimateTechniqueFactory(gift=earlier.gift)
        requirement = TechniqueKnownRequirement.objects.create(
            technique=upgrade, required_technique=earlier
        )
        self.assertFalse(requirement.is_met_by_character(sheet.character)[0])
        KnownUltimateFactory(character=sheet, technique=earlier)
        self.assertTrue(requirement.is_met_by_character(sheet.character)[0])


class RoleGrantExcludesUltimateTests(TestCase):
    """Engaging a covenant role never auto-grants an ultimate (#4098)."""

    def test_engage_grants_only_the_ordinary_technique(self) -> None:
        from world.covenants.services import set_engaged_membership
        from world.magic.models import CharacterTechnique

        cov = CovenantFactory(name="UltimateRoleCov", covenant_type=CovenantType.DURANCE)
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        gift = GiftFactory(name="UltimateRoleGift")
        ordinary = TechniqueFactory(gift=gift)
        ultimate = UltimateTechniqueFactory(gift=gift)

        CovenantRoleGiftGrant.objects.create(
            covenant_role=role,
            gift=gift,
            unlock_thread_level=0,
        )

        membership = CharacterCovenantRoleFactory(covenant=cov, covenant_role=role)
        sheet = membership.character_sheet

        set_engaged_membership(membership=membership)

        self.assertTrue(
            CharacterTechnique.objects.filter(character=sheet, technique=ordinary).exists()
        )
        self.assertFalse(
            CharacterTechnique.objects.filter(character=sheet, technique=ultimate).exists()
        )


class SphinxShoppingListExcludesUltimateTests(TestCase):
    """The Sphinx never recommends an ultimate as a shopping-list pick (#4098)."""

    def test_shopping_list_never_names_an_ultimate(self) -> None:
        sheet = CharacterSheetFactory()
        role = CovenantRoleFactory()
        from world.covenants.factories import CovenantRoleTechniqueSpecialtyFactory

        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=role, function=TechniqueFunction.BARRIER
        )

        ultimate = UltimateTechniqueFactory(name="Ward Absolute")
        TechniqueFunctionTagFactory(technique=ultimate, function=TechniqueFunction.BARRIER)
        CharacterGiftFactory(character=sheet, gift=ultimate.gift)

        verdict = judge_vow(sheet, role)

        shopping_names = [item.technique_name for item in verdict.shopping_list]
        self.assertNotIn("Ward Absolute", shopping_names)
