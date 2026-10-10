"""Tests for regional house aspects + features (#2079, #2868)."""

from django.core import serializers as django_serializers
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.codex.factories import CodexEntryFactory
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
from world.societies.houses.types import ClaimLandDraft
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


class AspectCodexLinkTests(TestCase):
    """#2868 — an option binds the CodexEntry carrying its write-up."""

    @classmethod
    def setUpTestData(cls):
        cls.entry = CodexEntryFactory(name="The Leviathan TEST")
        cls.definition = HouseAspectDefinition.objects.create(
            name="House Quiddity TEST", prompt="What drives your house?"
        )
        cls.option = HouseAspectOption.objects.create(
            definition=cls.definition, name="Leviathan TEST", codex_entry=cls.entry
        )

    def test_codex_entry_is_optional(self):
        unbound = HouseAspectOption.objects.create(
            definition=self.definition, name="Unwritten TEST"
        )
        self.assertIsNone(unbound.codex_entry)

    def test_reverse_accessor(self):
        self.assertEqual(list(self.entry.house_aspect_options.all()), [self.option])

    def test_bound_entry_is_protected(self):
        """PROTECT: deleting a linked entry must not silently orphan the catalog."""
        with transaction.atomic(), self.assertRaises(ProtectedError):
            self.entry.delete()


class AspectNaturalKeyTests(TestCase):
    """#2868 — the catalog is lore-repo content, so it must round-trip."""

    @classmethod
    def setUpTestData(cls):
        cls.definition = HouseAspectDefinition.objects.create(
            name="House Quiddity NK TEST", prompt="What drives your house?"
        )
        cls.option = HouseAspectOption.objects.create(
            definition=cls.definition, name="Glamour NK TEST"
        )

    def test_definition_natural_key_is_name(self):
        self.assertEqual(self.definition.natural_key(), ("House Quiddity NK TEST",))

    def test_definition_round_trip(self):
        found = HouseAspectDefinition.objects.get_by_natural_key(*self.definition.natural_key())
        self.assertEqual(found.pk, self.definition.pk)

    def test_option_natural_key_includes_definition(self):
        self.assertEqual(self.option.natural_key(), ("House Quiddity NK TEST", "Glamour NK TEST"))

    def test_option_round_trip(self):
        found = HouseAspectOption.objects.get_by_natural_key(*self.option.natural_key())
        self.assertEqual(found.pk, self.option.pk)

    def test_option_serializes_without_raw_pks(self):
        data = django_serializers.serialize(
            "json",
            [self.option],
            use_natural_foreign_keys=True,
            use_natural_primary_keys=True,
        )
        self.assertIn("House Quiddity NK TEST", data)
        self.assertNotIn(f'"definition": {self.definition.pk}', data)


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
            "lands": [
                ClaimLandDraft(
                    title_id=self.title.pk,
                    description="Fen villages and eel weirs along the marches.",
                )
            ],
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
        self.assertIn("eel weirs", claim.lands.get(title=self.title).description)

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


class DisplaySurfaceTests(AspectTestData):
    """Org payload + telnet sheet/house carry the identity facets."""

    @classmethod
    def setUpTestData(cls):
        from evennia_extensions.factories import AccountFactory

        super().setUpTestData()
        claim = submit_house_claim(
            draft=cls.draft,
            title=cls.title,
            template=cls.template,
            house_name="Thornwood",
            backstory="An old marcher line.",
            words="The Fens Endure",
            colors="russet and bog-iron grey",
            sigil_description="A heron statant on a black chief.",
            lands=[
                ClaimLandDraft(
                    title_id=cls.title.pk,
                    description="Fen villages and eel weirs along the marches.",
                )
            ],
            aspect_picks={
                cls.virtue.pk: [cls.fortitude.pk],
                cls.traditions.pk: [cls.trad_a.pk, cls.trad_b.pk],
            },
        )
        approve_house_claim(claim, reviewer=AccountFactory())
        cls.sheet = CharacterSheetFactory()
        cls.org = materialize_house_claim(claim, sheet=cls.sheet)

    def test_org_payload_carries_stylings_and_facets(self):
        from world.societies.serializers import OrganizationSerializer

        payload = OrganizationSerializer(self.org).data
        self.assertEqual(payload["words"], "The Fens Endure")
        self.assertEqual(payload["colors"], "russet and bog-iron grey")
        self.assertIn("heron", payload["sigil_description"])
        house = payload["house"]
        picked = {(a["definition"], a["option"]) for a in house["aspects"]}
        self.assertIn(("House Virtue", "Fortitude"), picked)
        self.assertEqual(len(house["aspects"]), 3)
        self.assertEqual(house["features"][0]["slug"], "hearth-right")
        # #3983: standing and land are on the house block itself, so an org
        # page never needs a second call into the Almanach for them. The
        # count is the document's own demesne rule (baronies held).
        self.assertEqual(house["house_state"], self.org.house_state)
        self.assertEqual(house["demesne"], 1)

    def test_sheet_house_section_lists_identity(self):
        from types import SimpleNamespace

        from commands.account.sheet_sections import _render_house_section

        command = SimpleNamespace(caller=SimpleNamespace(character_sheet=self.sheet))
        lines = "\n".join(_render_house_section(command))
        self.assertIn("The Fens Endure", lines)
        self.assertIn("russet and bog-iron grey", lines)
        self.assertIn("House Virtue: Fortitude", lines)
        self.assertIn("Hearth Right", lines)


class AspectTargetTests(TestCase):
    """#4205: an option is one typed thing, and a patron question's options always
    carry a god and a name for it."""

    @classmethod
    def setUpTestData(cls):
        from django.core.exceptions import ValidationError

        from world.worship.factories import BeingNicknameFactory, WorshippedBeingFactory

        cls.ValidationError = ValidationError
        cls.calyx_entry = CodexEntryFactory(name="Calyx")
        cls.calyx = WorshippedBeingFactory(name="Calyx", codex_entry=cls.calyx_entry)
        cls.knight = BeingNicknameFactory(being=cls.calyx, name="The One True Knight")
        cls.other = WorshippedBeingFactory(name="The Fleshreaper")
        cls.other_name = BeingNicknameFactory(being=cls.other, name="The Gory Goddess")
        cls.patron = HouseAspectDefinition.objects.create(
            name="Patron", prompt="Whom does the house serve?", sets_patron=True
        )
        cls.plain = HouseAspectDefinition.objects.create(name="Virtue", prompt="Which?")

    def test_a_nickname_must_be_the_beings_own(self):
        option = HouseAspectOption(
            definition=self.plain, name="Calyx", being=self.calyx, being_nickname=self.other_name
        )
        with self.assertRaises(self.ValidationError) as caught:
            option.full_clean()
        self.assertIn("being_nickname", caught.exception.message_dict)
        option.being_nickname = self.knight
        option.full_clean()

    def test_a_nickname_without_its_being_is_refused(self):
        option = HouseAspectOption(definition=self.plain, name="X", being_nickname=self.knight)
        with self.assertRaises(self.ValidationError) as caught:
            option.full_clean()
        self.assertIn("being_nickname", caught.exception.message_dict)

    def test_a_being_and_a_lore_entry_are_not_both_claimed(self):
        option = HouseAspectOption(
            definition=self.plain,
            name="Calyx",
            being=self.calyx,
            codex_entry=CodexEntryFactory(name="Calyx, again"),
        )
        with self.assertRaises(self.ValidationError) as caught:
            option.full_clean()
        self.assertIn("codex_entry", caught.exception.message_dict)

    def test_a_patron_question_needs_a_being_and_a_name(self):
        option = HouseAspectOption(definition=self.patron, name="Nobody")
        with self.assertRaises(self.ValidationError) as caught:
            option.full_clean()
        self.assertIn("being", caught.exception.message_dict)
        option.being = self.calyx
        option.being_nickname = self.knight
        option.full_clean()

    def test_the_target_entry_is_the_options_own_else_the_beings_page(self):
        lore = CodexEntryFactory(name="The Battle of the Ford")
        by_lore = HouseAspectOption(definition=self.plain, name="Ford", codex_entry=lore)
        by_being = HouseAspectOption(definition=self.plain, name="Calyx", being=self.calyx)
        bare = HouseAspectOption(definition=self.plain, name="Bare")
        self.assertEqual(by_lore.target_entry_id, lore.pk)
        self.assertEqual(by_being.target_entry_id, self.calyx_entry.pk)
        self.assertIsNone(bare.target_entry_id)

    def test_one_patron_question_per_charter(self):
        from world.societies.houses.factories import HouseTemplateFactory

        second = HouseAspectDefinition.objects.create(
            name="Totem", prompt="Which totem?", sets_patron=True
        )
        template = HouseTemplateFactory()
        template.aspect_definitions.add(self.patron)
        template.full_clean()
        template.aspect_definitions.add(second)
        with self.assertRaises(self.ValidationError) as caught:
            template.full_clean()
        self.assertIn("aspect_definitions", caught.exception.message_dict)


class PatronFoundingTests(AspectTestData):
    """#4205: the pick on the patron question becomes the house's patron, once, at founding."""

    @classmethod
    def setUpTestData(cls):
        from world.worship.factories import BeingNicknameFactory, WorshippedBeingFactory

        super().setUpTestData()
        cls.calyx_entry = CodexEntryFactory(name="Calyx")
        cls.calyx = WorshippedBeingFactory(name="Calyx", codex_entry=cls.calyx_entry)
        cls.knight = BeingNicknameFactory(being=cls.calyx, name="The One True Knight")
        cls.patron = HouseAspectDefinition.objects.create(
            name="Patron", prompt="Whom does the house serve?", sets_patron=True
        )
        cls.calyx_option = HouseAspectOption.objects.create(
            definition=cls.patron, name="Calyx", being=cls.calyx, being_nickname=cls.knight
        )
        cls.template.aspect_definitions.add(cls.patron)

    def _picks(self):
        return {
            self.virtue.pk: [self.fortitude.pk],
            self.traditions.pk: [self.trad_a.pk, self.trad_b.pk],
            self.patron.pk: [self.calyx_option.pk],
        }

    def _found(self, name, **overrides):
        """Submit, approve and materialize on a method-local title: ``assign_holder``
        mutates the identity-mapped title, so a class-shared one would be seated
        for the next test too (idmapper rollback staleness)."""
        from evennia_extensions.factories import AccountFactory
        from world.societies.houses.almanach import plant_rung
        from world.societies.houses.constants import TitleTier

        own_title = plant_rung(
            realm=self.realm, tier=TitleTier.BARONY, name=name, parent_title=self.crown_county
        )
        claim = self._submit_full(
            title=own_title,
            lands=[ClaimLandDraft(title_id=own_title.pk, description="Fen villages.")],
            **overrides,
        )
        approve_house_claim(claim, reviewer=AccountFactory())
        return materialize_house_claim(claim, sheet=CharacterSheetFactory())

    def test_founding_writes_the_patron_by_the_houses_own_name(self):
        from world.roster.services.kinship import OMNISCIENT
        from world.societies.houses.almanach import publish_house
        from world.societies.houses.almanach_reads import document_for_house
        from world.societies.serializers import OrganizationSerializer

        org = self._found("Knightsmere", aspect_picks=self._picks())
        self.assertEqual(org.patron_nickname, self.knight)

        # Every read says what the pick is and where it opens.
        house = OrganizationSerializer(org).data["house"]
        self.assertEqual(
            house["patron"],
            {
                "nickname": "The One True Knight",
                "being_name": "Calyx",
                "codex_entry_id": self.calyx_entry.pk,
            },
        )
        calyx_facet = next(a for a in house["aspects"] if a["option"] == "Calyx")
        self.assertEqual(calyx_facet["being_name"], "Calyx")
        self.assertEqual(calyx_facet["target_entry_id"], self.calyx_entry.pk)
        plain_facet = next(a for a in house["aspects"] if a["option"] == "Fortitude")
        self.assertEqual(plain_facet["being_name"], "")
        self.assertIsNone(plain_facet["target_entry_id"])
        publish_house(org)
        document = document_for_house(org, viewer=OMNISCIENT, staff=True)
        self.assertEqual(document.house["patron"]["nickname"], "The One True Knight")
        self.assertEqual(
            next(a for a in document.house["aspects"] if a["option"] == "Calyx")["target_entry_id"],
            self.calyx_entry.pk,
        )

    def test_a_charter_without_a_patron_question_writes_none(self):
        from world.societies.serializers import OrganizationSerializer

        self.template.aspect_definitions.remove(self.patron)
        org = self._found("Godlessmere")
        self.assertIsNone(org.patron_nickname)
        self.assertIsNone(OrganizationSerializer(org).data["house"]["patron"])
