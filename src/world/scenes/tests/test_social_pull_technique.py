"""A declared pull on a technique-enhanced social action reaches the roll.

The plain branch of ``_resolve_action_against_persona`` folds the charged
pull's FLAT_BONUS into the check; the technique branch must do the same, or a
player pays resonance for nothing.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.models import ActionEnhancement
from evennia_extensions.factories import AccountFactory
from world.checks.factories import create_social_action_templates
from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    CharacterTechniqueFactory,
    ResonanceFactory,
    TechniqueFactory,
    ThreadFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
)
from world.magic.models import CharacterResonance
from world.magic.types.pull import CastPullDeclaration
from world.scenes import action_services
from world.scenes.action_constants import ActionRequestStatus, ConsentDecision
from world.scenes.action_models import SceneActionPullDeclaration
from world.scenes.action_services import create_action_request, respond_to_action_request
from world.scenes.factories import PersonaFactory, SceneFactory
from world.traits.factories import CheckSystemSetupFactory

PULL_FLAT_BONUS = 5


class TechniqueSocialPullTests(TestCase):
    """Declare a pull on a technique-enhanced flirt, accept, read the roll."""

    @classmethod
    def setUpTestData(cls) -> None:
        CheckSystemSetupFactory.create()
        templates = create_social_action_templates()
        cls.flirt_template = next(t for t in templates if t.name == "Flirt")
        cls.scene = SceneFactory()
        cls.initiator = PersonaFactory()
        cls.target = PersonaFactory()
        target_character = cls.target.character_sheet.character
        target_character.db_account = AccountFactory()
        target_character.save(update_fields=["db_account"])

        cls.sheet = cls.initiator.character_sheet
        cls.technique = TechniqueFactory(intensity=3, control=8, anima_cost=2)
        CharacterTechniqueFactory(character=cls.sheet, technique=cls.technique)
        ActionEnhancement.objects.create(
            base_action_key="flirt",
            variant_name="Enchanted Flirt",
            source_type="technique",
            technique=cls.technique,
        )
        CharacterAnimaFactory(character=cls.sheet, current=20, maximum=30)
        cls.resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=cls.sheet, resonance=cls.resonance, balance=20, lifetime_earned=20
        )
        cls.thread = ThreadFactory(owner=cls.sheet, resonance=cls.resonance, as_track_thread=True)
        ThreadPullCostFactory(tier=1, resonance_cost=2, anima_per_thread=1)
        ThreadPullEffectFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            resonance=cls.resonance,
            tier=1,
            flat_bonus_amount=PULL_FLAT_BONUS,
        )

    def _accept_with_pull(self) -> list[int]:
        """Accept a technique flirt that declares a pull; return roll modifiers seen."""
        request = create_action_request(
            scene=self.scene,
            initiator_persona=self.initiator,
            target_persona=self.target,
            action_key="flirt",
            technique=self.technique,
            pull=CastPullDeclaration(resonance=self.resonance, tier=1, threads=(self.thread,)),
        )
        request.action_template = self.flirt_template
        request.save(update_fields=["action_template"])
        seen: list[int] = []
        real = action_services.start_action_resolution

        def spy(**kwargs):
            seen.append(kwargs["extra_modifiers"])
            return real(**kwargs)

        with (
            patch("world.scenes.action_services.accrue"),
            patch.object(action_services, "start_action_resolution", side_effect=spy),
        ):
            result = respond_to_action_request(
                action_request=request, decision=ConsentDecision.ACCEPT
            )
        assert result is not None
        assert result.technique_result is not None
        request.refresh_from_db()
        assert request.status == ActionRequestStatus.RESOLVED
        return seen

    def test_declared_pull_bonus_reaches_the_technique_roll(self) -> None:
        seen = self._accept_with_pull()

        decl = SceneActionPullDeclaration.objects.get()
        assert decl.charged_flat_bonus == PULL_FLAT_BONUS
        balance = CharacterResonance.objects.get(
            character_sheet=self.sheet, resonance=self.resonance
        ).balance
        assert balance == 18  # charged exactly once
        assert seen == [PULL_FLAT_BONUS]
