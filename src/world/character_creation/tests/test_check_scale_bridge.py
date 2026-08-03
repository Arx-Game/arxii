"""#2894 acceptance: CG output and hand-seeded rows roll identical check points.

The scale ruling (Apostate, ADR-0193): stats display single-digit but store
×10 under the hood; skills store and display their true 1-100 value. CG
finalization converts stat dots ×10 and bridges each CG skill verbatim into a
matching ``CharacterTraitValue`` — so a freshly finalized character
contributes real points to checks, identical to a test character whose rows
were seeded by hand on the storage scale.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from evennia.accounts.models import AccountDB

from world.character_creation.services import finalize_character
from world.character_creation.tests.test_services import DEFAULT_STATS, FinalizationTestMixin
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import (
    CheckCategoryFactory,
    CheckTypeFactory,
    CheckTypeTraitFactory,
)
from world.checks.services import perform_check
from world.skills.factories import SkillFactory
from world.traits.factories import CheckSystemSetupFactory
from world.traits.models import (
    CharacterTraitValue,
    CheckRank,
    PointConversionRange,
    Trait,
    TraitType,
)


class CgCheckScaleBridgeTests(FinalizationTestMixin, TestCase):
    """A CG-finalized character and a hand-seeded twin score the same points."""

    def setUp(self):
        self._flush_common_caches()
        Trait.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        self.account = AccountDB.objects.create(username="bridgeuser")
        self._setup_finalization_base(self, prefix="Bridge Test", height_min=700, height_max=800)

        CheckSystemSetupFactory.create()
        for trait_type in (TraitType.STAT, TraitType.SKILL):
            PointConversionRange.objects.get_or_create(
                trait_type=trait_type,
                min_value=1,
                defaults={"max_value": 100, "points_per_level": 1},
            )
        for rank_val, min_pts, name in [
            (0, 0, "BridgeNone"),
            (1, 10, "BridgeNovice"),
            (2, 25, "BridgeCompetent"),
            (3, 50, "BridgeExpert"),
        ]:
            CheckRank.objects.get_or_create(
                rank=rank_val, defaults={"min_points": min_pts, "name": name}
            )

    def test_cg_character_matches_hand_seeded_check_points(self):
        skill = SkillFactory()
        # Skills store AND display true value: 30 is 30 (ADR-0193).
        draft = self._create_base_draft(skills={str(skill.pk): 30})
        character = finalize_character(draft, add_to_roster=True)

        strength = Trait.objects.get(name="strength", trait_type=TraitType.STAT)
        category = CheckCategoryFactory(name="bridge_test_category")
        check_type = CheckTypeFactory(name="bridge_test_check", category=category)
        CheckTypeTraitFactory(check_type=check_type, trait=strength, weight=Decimal("0.5"))
        CheckTypeTraitFactory(check_type=check_type, trait=skill.trait, weight=Decimal("1.0"))

        twin = CharacterSheetFactory().character
        CharacterTraitValue.objects.create(
            character=twin.sheet_data, trait=strength, value=20
        )  # display 2, like DEFAULT_STATS
        CharacterTraitValue.objects.create(character=twin.sheet_data, trait=skill.trait, value=30)

        cg_result = perform_check(character, check_type, target_difficulty=0)
        twin_result = perform_check(twin, check_type, target_difficulty=0)

        # strength 20 × 0.5 → 10 pts; skill 30 × 1.0 → 30 pts (1 pt/level)
        assert cg_result.trait_points == 40
        assert twin_result.trait_points == 40

    def test_finalize_bridges_cg_skills_into_trait_rows(self):
        skill = SkillFactory()
        draft = self._create_base_draft(skills={str(skill.pk): 30})
        character = finalize_character(draft, add_to_roster=True)

        row = CharacterTraitValue.objects.get(character_id=character.pk, trait=skill.trait)
        assert row.value == 30

    def test_finalize_stores_stats_internal_scale(self):
        draft = self._create_base_draft()
        character = finalize_character(draft, add_to_roster=True)

        strength = Trait.objects.get(name="strength", trait_type=TraitType.STAT)
        row = CharacterTraitValue.objects.get(character_id=character.pk, trait=strength)
        assert row.value == DEFAULT_STATS["strength"] * 10
