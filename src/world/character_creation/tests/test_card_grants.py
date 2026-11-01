"""The grant sidecars' own rules (#4852, slice 6 of #4813): the refusals and the Path reading.

The journeys (``integration_tests.test_card_grants_journeys``) walk the asks, the answers
and finalize through the real seams; these cover what a journey cannot reach.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.character_creation.offers import strongest_path_aspect
from world.classes.factories import (
    AspectFactory,
    DistinctionPathAspectGrantFactory,
    PathAspectFactory,
    PathFactory,
)
from world.distinctions.factories import DistinctionFactory
from world.societies.factories import (
    DistinctionOrganizationGrantFactory,
    DistinctionPrestigeGrantFactory,
    OrganizationFactory,
)
from world.societies.membership_services import base_rank_for_organization


class GrantSidecarRulesTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.card = DistinctionFactory(name="Renowned")
        cls.lodge = OrganizationFactory(name="The Honor Lodge")
        cls.other = OrganizationFactory(name="The Other Lodge")

    def test_a_prestige_grant_and_a_path_aspect_grant_are_never_zero(self) -> None:
        with self.assertRaises(ValidationError):
            DistinctionPrestigeGrantFactory.build(distinction=self.card, amount=0).full_clean()
        DistinctionPrestigeGrantFactory.build(distinction=self.card, amount=-300).full_clean()
        with self.assertRaises(ValidationError):
            DistinctionPathAspectGrantFactory.build(distinction=self.card, value=0).full_clean()

    def test_an_organization_grant_rank_belongs_to_its_organization(self) -> None:
        rank = base_rank_for_organization(self.other)
        with self.assertRaises(ValidationError):
            DistinctionOrganizationGrantFactory.build(
                distinction=self.card, organization=None, rank=rank
            ).full_clean()
        with self.assertRaises(ValidationError):
            DistinctionOrganizationGrantFactory.build(
                distinction=self.card, organization=self.lodge, rank=rank
            ).full_clean()
        DistinctionOrganizationGrantFactory.build(
            distinction=self.card, organization=self.other, rank=rank
        ).full_clean()


class StrongestPathAspectTest(TestCase):
    def test_the_heaviest_aspect_wins_and_a_tie_goes_by_name(self) -> None:
        path = PathFactory(name="Path of Steel")
        PathAspectFactory(character_path=path, aspect=AspectFactory(name="Warfare"), weight=2)
        PathAspectFactory(character_path=path, aspect=AspectFactory(name="Martial"), weight=1)
        self.assertEqual(strongest_path_aspect(path).name, "Warfare")
        tied = PathFactory(name="Path of Two")
        PathAspectFactory(character_path=tied, aspect=AspectFactory(name="Shadow"), weight=1)
        PathAspectFactory(character_path=tied, aspect=AspectFactory(name="Arcana"), weight=1)
        self.assertEqual(strongest_path_aspect(tied).name, "Arcana")
        self.assertIsNone(strongest_path_aspect(None))
        self.assertIsNone(strongest_path_aspect(PathFactory(name="Path of None")))
