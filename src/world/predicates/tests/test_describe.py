"""describe_leaf turns a matched predicate leaf into a short player-facing reason."""

from django.test import TestCase

from world.achievements.factories import AchievementFactory
from world.character_creation.factories import OriginTemplateFactory
from world.distinctions.factories import DistinctionFactory
from world.items.factories import ItemTemplateFactory
from world.predicates.describe import describe_leaf
from world.species.factories import SpeciesFactory


class DescribeLeafTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.species = SpeciesFactory(name="Placeholder Folk")
        cls.template = OriginTemplateFactory(name="Placeholder Hearth")
        cls.distinction = DistinctionFactory(slug="placeholder-mark", name="Placeholder Mark")
        cls.achievement = AchievementFactory(slug="placeholder-feat", name="Placeholder Feat")
        cls.item = ItemTemplateFactory(name="Placeholder Token")

    def _leaf(self, leaf_name: str, **params: object) -> dict:
        return {"leaf": leaf_name, "params": params}

    def test_has_species(self) -> None:
        leaf = self._leaf("has_species", species_id=self.species.pk)
        self.assertEqual(describe_leaf(leaf), "you are Placeholder Folk")

    def test_has_upbringing(self) -> None:
        leaf = self._leaf("has_upbringing", origin_template_id=self.template.pk)
        self.assertEqual(describe_leaf(leaf), "your upbringing: Placeholder Hearth")

    def test_has_distinction(self) -> None:
        leaf = self._leaf("has_distinction", slug="placeholder-mark")
        self.assertEqual(describe_leaf(leaf), "you have Placeholder Mark")

    def test_has_achievement(self) -> None:
        leaf = self._leaf("has_achievement", slug="placeholder-feat")
        self.assertEqual(describe_leaf(leaf), "you have Placeholder Feat")

    def test_has_item(self) -> None:
        leaf = self._leaf("has_item", template_id=self.item.pk)
        self.assertEqual(describe_leaf(leaf), "you have Placeholder Token")

    def test_name_keyed_leaves(self) -> None:
        self.assertEqual(
            describe_leaf(self._leaf("is_member_of_org", org="Placeholder Org")),
            "you belong to Placeholder Org",
        )
        self.assertEqual(
            describe_leaf(self._leaf("min_org_rank", org="Placeholder Org", rank=2)),
            "you belong to Placeholder Org",
        )
        self.assertEqual(
            describe_leaf(self._leaf("is_member_of_society", society="Placeholder Soc")),
            "your standing in Placeholder Soc",
        )
        self.assertEqual(
            describe_leaf(
                self._leaf("min_society_standing", society="Placeholder Soc", tier="liked")
            ),
            "your standing in Placeholder Soc",
        )
        self.assertEqual(
            describe_leaf(self._leaf("has_codex_entry", subject="S", name="Placeholder Entry")),
            "you have Placeholder Entry",
        )
        self.assertEqual(
            describe_leaf(self._leaf("has_skill", skill="Placeholder")), "you have Placeholder"
        )
        self.assertEqual(
            describe_leaf(self._leaf("min_trait", trait="Placeholder", value=3)),
            "you have Placeholder",
        )
        self.assertEqual(
            describe_leaf(self._leaf("has_resonance", name="Placeholder")), "you have Placeholder"
        )
        self.assertEqual(
            describe_leaf(self._leaf("has_capability", name="Placeholder")), "you have Placeholder"
        )

    def test_unrecognised_leaf_is_none(self) -> None:
        self.assertIsNone(describe_leaf(self._leaf("has_thread")))
        self.assertIsNone(describe_leaf(self._leaf("min_character_level", level=3)))

    def test_missing_row_is_none(self) -> None:
        self.assertIsNone(describe_leaf(self._leaf("has_species", species_id=0)))
        self.assertIsNone(describe_leaf(self._leaf("has_distinction", slug="nope")))
