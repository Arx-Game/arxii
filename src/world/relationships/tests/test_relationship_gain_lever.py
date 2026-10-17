"""The relationship-gain lever (#4394) at the affection shift seam."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import EffectTarget, EffectType
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.checks.types import ResolutionContext
from world.mechanics.constants import (
    RELATIONSHIP_GAIN_CATEGORY_NAME,
    RELATIONSHIP_GAIN_TARGET_NAME,
)
from world.mechanics.effect_handlers import apply_effect
from world.mechanics.test_helpers import grant_lever
from world.relationships.models import CharacterRelationship
from world.relationships.services import apply_affection_shift
from world.relationships.tests.test_affection_shift import _shift_effect
from world.scenes.factories import SceneFactory


class RelationshipGainLeverTests(TestCase):
    def setUp(self) -> None:
        self.guarded = CharacterSheetFactory()  # the one whose regard moves
        self.actor = CharacterSheetFactory()
        self.scene = SceneFactory()

    def _shift(self, amount: int):
        return apply_affection_shift(
            source=self.guarded,
            target=self.actor,
            scene=self.scene,
            effect=_shift_effect(amount),
            amount=amount,
        )

    def _side(self) -> CharacterRelationship:
        return CharacterRelationship.objects.get(source=self.guarded, target=self.actor)

    def test_without_a_lever_the_shift_lands_whole(self) -> None:
        self._shift(4)
        assert self._side().affection == 4

    def test_a_guarded_character_warms_more_slowly(self) -> None:
        grant_lever(
            self.guarded, RELATIONSHIP_GAIN_CATEGORY_NAME, RELATIONSHIP_GAIN_TARGET_NAME, -25
        )
        shift = self._shift(4)
        assert shift.amount == 3
        assert self._side().affection == 3

    def test_conflict_is_not_a_gain(self) -> None:
        grant_lever(
            self.guarded, RELATIONSHIP_GAIN_CATEGORY_NAME, RELATIONSHIP_GAIN_TARGET_NAME, -25
        )
        self._shift(-10)
        assert self._side().conflict == 10

    def test_the_actor_lever_does_not_apply(self) -> None:
        grant_lever(self.actor, RELATIONSHIP_GAIN_CATEGORY_NAME, RELATIONSHIP_GAIN_TARGET_NAME, -25)
        self._shift(4)
        assert self._side().affection == 4


class ShiftAffectionHandlerTests(TestCase):
    """The consequence handler names a zeroed gain for what it is and reports the scaled shift."""

    def setUp(self) -> None:
        self.recipient = CharacterSheetFactory()  # the social action's target
        self.actor = CharacterSheetFactory()
        self.scene = SceneFactory()
        self.effect = ConsequenceEffectFactory(
            consequence=ConsequenceFactory(),
            effect_type=EffectType.SHIFT_AFFECTION,
            target=EffectTarget.TARGET,
            affection_amount=4,
        )

    def _apply(self):
        context = ResolutionContext(
            character=self.actor.character, target=self.recipient.character, scene=self.scene
        )
        return apply_effect(self.effect, context)

    def test_a_scaled_shift_is_reported_as_applied(self) -> None:
        grant_lever(
            self.recipient, RELATIONSHIP_GAIN_CATEGORY_NAME, RELATIONSHIP_GAIN_TARGET_NAME, -25
        )
        result = self._apply()
        assert result.applied
        assert result.description.endswith("shifts +3")

    def test_a_gain_scaled_to_nothing_is_not_called_a_repeat(self) -> None:
        grant_lever(
            self.recipient, RELATIONSHIP_GAIN_CATEGORY_NAME, RELATIONSHIP_GAIN_TARGET_NAME, -100
        )
        result = self._apply()
        assert not result.applied
        assert result.skip_reason == "no_gain"
