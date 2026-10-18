"""Journeys for magical skills (#4450): a technique's skill joins the roll its cast makes.

A caster on a Path whose staff-set technique skill is, say, Occult rolls her cast with that
skill added to the check the cast already used. These journeys cast the way the web client does
(``dispatch_player_action`` on ``cast_technique``) and read back the roll the cast made.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from actions.factories import ActionTemplateFactory
from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.services import perform_check
from world.checks.test_helpers import force_check_outcome
from world.checks.types import CheckResult, ExtraTraitTerm
from world.classes.factories import PathFactory
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterAnimaFactory,
    GiftFactory,
    TechniqueFactory,
)
from world.progression.factories import CharacterPathHistoryFactory
from world.scenes.factories import SceneFactory
from world.scenes.tests.cast_test_helpers import grant_technique
from world.skills.factories import SkillFactory
from world.traits.factories import CheckSystemSetupFactory, StatTraitFactory
from world.traits.models import CharacterTraitValue, CheckOutcome, PointConversionRange, TraitType
from world.vitals.models import CharacterVitals

SKILL_VALUE = 30


class CastingWithATechniqueSkill(JourneyCase):
    """Ysmay and Hobb walk the same Path; only Ysmay has trained its technique skill."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.SKILL,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        self.skill = SkillFactory()
        self.path = PathFactory(technique_skill=self.skill)
        self.lantern = self.make_room("The Lantern")
        SceneFactory(room=self.lantern)

        check_type = CheckTypeFactory()
        CheckTypeTraitFactory(check_type=check_type, trait=StatTraitFactory(), weight=1)
        self.template = ActionTemplateFactory(check_type=check_type)
        self.technique = TechniqueFactory(
            gift=GiftFactory(),
            anima_cost=1,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=self.template,
        )
        self.ysmay = self.caster_on_the_path("Ysmay", skill_value=SKILL_VALUE)
        self.hobb = self.caster_on_the_path("Hobb", skill_value=0)

    def caster_on_the_path(self, name: str, *, skill_value: int):
        character = self.make_player(name, room=self.lantern)
        sheet = character.sheet_data
        CharacterPathHistoryFactory(character=sheet, path=self.path)
        grant_technique(sheet.primary_persona, self.technique)
        CharacterAnimaFactory(character=sheet, current=20, maximum=30)
        CharacterVitals.objects.create(
            character_sheet=sheet, health=50, max_health=50, base_max_health=50
        )
        if skill_value:
            CharacterTraitValue.objects.create(
                character=sheet, trait=self.skill.trait, value=skill_value
            )
        return character

    def cast_and_read_the_roll(self, character) -> tuple[tuple[ExtraTraitTerm, ...], CheckResult]:
        """Cast the technique on the web seam; return the terms the roll carried and its result."""
        rolled: list[CheckResult] = []

        def spy(*args, **kwargs) -> CheckResult:
            result = perform_check(*args, **kwargs)
            rolled.append(result)
            return result

        success = CheckOutcome.objects.get(name="Success")
        with (
            force_check_outcome(success) as capture,
            patch("actions.services.perform_check", side_effect=spy),
        ):
            outcome = self.web(character, "cast_technique", technique_id=self.technique.pk)
        self.assertTrue(outcome.detail.success, outcome.detail.message)
        self.assertEqual(len(rolled), 1)
        return capture.extra_traits, rolled[0]

    def test_scene_cast_adds_path_technique_skill(self) -> None:
        terms, result = self.cast_and_read_the_roll(self.ysmay)

        self.assertEqual(terms, (ExtraTraitTerm(trait=self.skill.trait, weight=Decimal("1.00")),))
        _, untrained = self.cast_and_read_the_roll(self.hobb)
        self.assertEqual(result.trait_points - untrained.trait_points, SKILL_VALUE)
