"""Tests for regional house aspects + features (#2079)."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.societies.houses.creator import (
    approve_house_claim,
    materialize_house_claim,
    submit_house_claim,
)
from world.societies.houses.models import (
    HouseAspectDefinition,
    HouseAspectOption,
    HouseFeature,
)
from world.societies.houses.services import HousesServiceError
from world.societies.tests.test_house_creator import HouseCreatorTestData


class AspectModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.definition = HouseAspectDefinition.objects.create(
            name="House Virtue TEST",
            prompt="Which virtue did your house cling to?",
        )
        cls.option = HouseAspectOption.objects.create(
            definition=cls.definition, name="Fortitude TEST"
        )
        cls.feature = HouseFeature.objects.create(
            name="Hearth Right TEST",
            slug="hearth-right-test",
            description="Guests under your roof are sacrosanct.",
        )

    def test_definition_defaults_single_pick(self):
        self.assertEqual(self.definition.min_picks, 1)
        self.assertEqual(self.definition.max_picks, 1)

    def test_option_unique_per_definition(self):
        with transaction.atomic(), self.assertRaises(IntegrityError):
            HouseAspectOption.objects.create(definition=self.definition, name="Fortitude TEST")

    def test_feature_slug_unique(self):
        with transaction.atomic(), self.assertRaises(IntegrityError):
            HouseFeature.objects.create(
                name="Other TEST", slug="hearth-right-test", description="x"
            )


class AspectTestData(HouseCreatorTestData):
    """The Phase-D creator scaffolding plus attached aspect requirements."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.virtue = HouseAspectDefinition.objects.create(
            name="House Virtue", prompt="Which virtue rules the house?"
        )
        cls.fortitude = HouseAspectOption.objects.create(definition=cls.virtue, name="Fortitude")
        cls.candor = HouseAspectOption.objects.create(definition=cls.virtue, name="Candor")
        cls.retired = HouseAspectOption.objects.create(
            definition=cls.virtue, name="Retired", is_active=False
        )
        cls.traditions = HouseAspectDefinition.objects.create(
            name="Traditions", prompt="Pick two traditions.", min_picks=2, max_picks=2
        )
        cls.trad_a = HouseAspectOption.objects.create(definition=cls.traditions, name="Vigil")
        cls.trad_b = HouseAspectOption.objects.create(definition=cls.traditions, name="Tithe")
        cls.trad_c = HouseAspectOption.objects.create(definition=cls.traditions, name="Feast")
        cls.template.aspect_definitions.add(cls.virtue, cls.traditions)
        cls.hearth = HouseFeature.objects.create(
            name="Hearth Right", slug="hearth-right", description="Guests are sacrosanct."
        )
        cls.template.features.add(cls.hearth)

    def _submit_full(self, **overrides):
        kwargs = {
            "draft": self.draft,
            "title": self.title,
            "template": self.template,
            "house_name": "Thornwood",
            "backstory": "An old marcher line.",
            "words": "The Fens Endure",
            "colors": "russet and bog-iron grey",
            "sigil_description": "A heron statant on a black chief.",
            "lands_writeup": "Fen villages and eel weirs along the marches.",
            "aspect_picks": {
                self.virtue.pk: [self.fortitude.pk],
                self.traditions.pk: [self.trad_a.pk, self.trad_b.pk],
            },
        }
        kwargs.update(overrides)
        return submit_house_claim(**kwargs)


class CreatorAspectGateTests(AspectTestData):
    """Aspect and styling gates refuse before staff ever look."""

    def test_happy_path_persists_picks_and_stylings(self):
        claim = self._submit_full()
        self.assertEqual(claim.aspects.count(), 3)
        self.assertEqual(claim.words, "The Fens Endure")
        self.assertEqual(claim.colors, "russet and bog-iron grey")
        self.assertIn("heron", claim.sigil_description)
        self.assertIn("eel weirs", claim.lands_writeup)

    def test_missing_definition_picks_refused(self):
        with self.assertRaises(HousesServiceError):
            self._submit_full(aspect_picks={self.virtue.pk: [self.fortitude.pk]})

    def test_over_count_refused(self):
        with self.assertRaises(HousesServiceError):
            self._submit_full(
                aspect_picks={
                    self.virtue.pk: [self.fortitude.pk, self.candor.pk],
                    self.traditions.pk: [self.trad_a.pk, self.trad_b.pk],
                }
            )

    def test_option_from_other_definition_refused(self):
        with self.assertRaises(HousesServiceError):
            self._submit_full(
                aspect_picks={
                    self.virtue.pk: [self.trad_a.pk],
                    self.traditions.pk: [self.trad_a.pk, self.trad_b.pk],
                }
            )

    def test_inactive_option_refused(self):
        with self.assertRaises(HousesServiceError):
            self._submit_full(
                aspect_picks={
                    self.virtue.pk: [self.retired.pk],
                    self.traditions.pk: [self.trad_a.pk, self.trad_b.pk],
                }
            )

    def test_picks_for_unattached_definition_refused(self):
        stray = HouseAspectDefinition.objects.create(name="Stray", prompt="Not on template.")
        stray_option = HouseAspectOption.objects.create(definition=stray, name="X")
        with self.assertRaises(HousesServiceError):
            self._submit_full(
                aspect_picks={
                    self.virtue.pk: [self.fortitude.pk],
                    self.traditions.pk: [self.trad_a.pk, self.trad_b.pk],
                    stray.pk: [stray_option.pk],
                }
            )

    def test_duplicate_picks_refused(self):
        with self.assertRaises(HousesServiceError):
            self._submit_full(
                aspect_picks={
                    self.virtue.pk: [self.fortitude.pk],
                    self.traditions.pk: [self.trad_a.pk, self.trad_a.pk],
                }
            )

    def test_blank_words_refused(self):
        with self.assertRaises(HousesServiceError):
            self._submit_full(words="   ")

    def test_blank_lands_refused_for_landed_title(self):
        with self.assertRaises(HousesServiceError):
            self._submit_full(lands_writeup="")


class MaterializationAspectTests(AspectTestData):
    """Approved claims write stylings, facets, features, and lands onto the world."""

    def test_materialization_writes_identity(self):
        from evennia_extensions.factories import AccountFactory

        claim = self._submit_full()
        approve_house_claim(claim, reviewer=AccountFactory())
        sheet = CharacterSheetFactory()
        org = materialize_house_claim(claim, sheet=sheet)

        self.assertEqual(org.words, "The Fens Endure")
        self.assertEqual(org.colors, "russet and bog-iron grey")
        self.assertIn("heron", org.sigil_description)
        self.assertEqual(org.aspects.count(), 3)
        picked = {a.option.name for a in org.aspects.select_related("option")}
        self.assertEqual(picked, {"Fortitude", "Vigil", "Tithe"})
        self.assertEqual(org.features.count(), 1)
        self.assertEqual(org.features.first().feature.slug, "hearth-right")
        self.seat.refresh_from_db()
        self.assertIn("eel weirs", self.seat.description)
