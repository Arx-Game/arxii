"""The relationship-gain lever (#4394) at the affection shift seam."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.mechanics.constants import (
    RELATIONSHIP_GAIN_CATEGORY_NAME,
    RELATIONSHIP_GAIN_TARGET_NAME,
)
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
