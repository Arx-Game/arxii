"""Tests for regional house facets + features (#2079, #2868)."""

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
    HouseCharterOption,
    HouseCharterQuestion,
    HouseFeature,
)
from world.societies.houses.services import HousesServiceError
from world.societies.houses.types import ClaimLandDraft
from world.societies.tests.test_house_creator import HouseCreatorTestData


class AspectModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.definition = HouseCharterQuestion.objects.create(
            name="House Virtue TEST",
            prompt="Which virtue did your house cling to?",
        )
        cls.option = HouseCharterOption.objects.create(
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
            HouseCharterOption.objects.create(definition=self.definition, name="Fortitude TEST")

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
        cls.definition = HouseCharterQuestion.objects.create(
            name="House Quiddity TEST", prompt="What drives your house?"
        )
        cls.option = HouseCharterOption.objects.create(
            definition=cls.definition, name="Leviathan TEST", codex_entry=cls.entry
        )

    def test_codex_entry_is_optional(self):
        unbound = HouseCharterOption.objects.create(
            definition=self.definition, name="Unwritten TEST"
        )
        self.assertIsNone(unbound.codex_entry)

    def test_reverse_accessor(self):
        self.assertEqual(list(self.entry.house_charter_options.all()), [self.option])

    def test_bound_entry_is_protected(self):
        """PROTECT: deleting a linked entry must not silently orphan the catalog."""
        with transaction.atomic(), self.assertRaises(ProtectedError):
            self.entry.delete()


class AspectNaturalKeyTests(TestCase):
    """#2868 — the catalog is lore-repo content, so it must round-trip."""

    @classmethod
    def setUpTestData(cls):
        cls.definition = HouseCharterQuestion.objects.create(
            name="House Quiddity NK TEST", prompt="What drives your house?"
        )
        cls.option = HouseCharterOption.objects.create(
            definition=cls.definition, name="Glamour NK TEST"
        )

    def test_definition_natural_key_is_name(self):
        self.assertEqual(self.definition.natural_key(), ("House Quiddity NK TEST",))

    def test_definition_round_trip(self):
        found = HouseCharterQuestion.objects.get_by_natural_key(*self.definition.natural_key())
        self.assertEqual(found.pk, self.definition.pk)

    def test_option_natural_key_includes_definition(self):
        self.assertEqual(self.option.natural_key(), ("House Quiddity NK TEST", "Glamour NK TEST"))

    def test_option_round_trip(self):
        found = HouseCharterOption.objects.get_by_natural_key(*self.option.natural_key())
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
        cls.virtue = HouseCharterQuestion.objects.create(
            name="House Virtue", prompt="Which virtue rules the house?"
        )
        cls.fortitude = HouseCharterOption.objects.create(definition=cls.virtue, name="Fortitude")
        cls.candor = HouseCharterOption.objects.create(definition=cls.virtue, name="Candor")
        cls.retired = HouseCharterOption.objects.create(
            definition=cls.virtue, name="Retired", is_active=False
        )
        cls.traditions = HouseCharterQuestion.objects.create(
            name="Traditions", prompt="Pick two traditions.", min_picks=2, max_picks=2
        )
        cls.trad_a = HouseCharterOption.objects.create(definition=cls.traditions, name="Vigil")
        cls.trad_b = HouseCharterOption.objects.create(definition=cls.traditions, name="Tithe")
        cls.trad_c = HouseCharterOption.objects.create(definition=cls.traditions, name="Feast")
        cls.template.charter_questions.add(cls.virtue, cls.traditions)
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
            "facet_picks": {
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
        self.assertEqual(claim.facets.count(), 3)
        self.assertEqual(claim.words, "The Fens Endure")
        self.assertEqual(claim.colors, "russet and bog-iron grey")
        self.assertIn("heron", claim.sigil_description)
        self.assertIn("eel weirs", claim.lands.get(title=self.title).description)

    def test_missing_definition_picks_refused(self):
        with self.assertRaises(HousesServiceError):
            self._submit_full(facet_picks={self.virtue.pk: [self.fortitude.pk]})

    def test_over_count_refused(self):
        with self.assertRaises(HousesServiceError):
            self._submit_full(
                facet_picks={
                    self.virtue.pk: [self.fortitude.pk, self.candor.pk],
                    self.traditions.pk: [self.trad_a.pk, self.trad_b.pk],
                }
            )

    def test_option_from_other_definition_refused(self):
        with self.assertRaises(HousesServiceError):
            self._submit_full(
                facet_picks={
                    self.virtue.pk: [self.trad_a.pk],
                    self.traditions.pk: [self.trad_a.pk, self.trad_b.pk],
                }
            )

    def test_inactive_option_refused(self):
        with self.assertRaises(HousesServiceError):
            self._submit_full(
                facet_picks={
                    self.virtue.pk: [self.retired.pk],
                    self.traditions.pk: [self.trad_a.pk, self.trad_b.pk],
                }
            )

    def test_picks_for_unattached_definition_refused(self):
        stray = HouseCharterQuestion.objects.create(name="Stray", prompt="Not on template.")
        stray_option = HouseCharterOption.objects.create(definition=stray, name="X")
        with self.assertRaises(HousesServiceError):
            self._submit_full(
                facet_picks={
                    self.virtue.pk: [self.fortitude.pk],
                    self.traditions.pk: [self.trad_a.pk, self.trad_b.pk],
                    stray.pk: [stray_option.pk],
                }
            )

    def test_duplicate_picks_refused(self):
        with self.assertRaises(HousesServiceError):
            self._submit_full(
                facet_picks={
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
        self.assertEqual(org.facets.count(), 3)
        picked = {a.option.name for a in org.facets.select_related("option")}
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
            facet_picks={
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
        picked = {(a["definition"], a["option"]) for a in house["facets"]}
        self.assertIn(("House Virtue", "Fortitude"), picked)
        self.assertEqual(len(house["facets"]), 3)
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
    """#4205: an option is one typed thing. #5110: a patron question takes no options,
    since its choices are gods."""

    @classmethod
    def setUpTestData(cls):
        from django.core.exceptions import ValidationError

        from world.worship.factories import WorshippedBeingFactory, WorshipTraditionFactory

        cls.ValidationError = ValidationError
        cls.calyx_entry = CodexEntryFactory(name="Calyx")
        cls.calyx = WorshippedBeingFactory(name="Calyx", codex_entry=cls.calyx_entry)
        cls.patron = HouseCharterQuestion.objects.create(
            name="Patron",
            prompt="Whom does the house serve?",
            sets_patron=True,
            patron_tradition=WorshipTraditionFactory(name="Church Liturgy"),
        )
        cls.plain = HouseCharterQuestion.objects.create(name="Virtue", prompt="Which?")

    def test_a_being_and_a_lore_entry_are_not_both_claimed(self):
        option = HouseCharterOption(
            definition=self.plain,
            name="Calyx",
            being=self.calyx,
            codex_entry=CodexEntryFactory(name="Calyx, again"),
        )
        with self.assertRaises(self.ValidationError) as caught:
            option.full_clean()
        self.assertIn("codex_entry", caught.exception.message_dict)

    def test_a_patron_question_takes_no_options(self):
        option = HouseCharterOption(definition=self.patron, name="Calyx", being=self.calyx)
        with self.assertRaises(self.ValidationError) as caught:
            option.full_clean()
        self.assertIn("definition", caught.exception.message_dict)

    def test_the_target_entry_is_the_options_own_else_the_beings_page(self):
        lore = CodexEntryFactory(name="The Battle of the Ford")
        by_lore = HouseCharterOption(definition=self.plain, name="Ford", codex_entry=lore)
        by_being = HouseCharterOption(definition=self.plain, name="Calyx", being=self.calyx)
        bare = HouseCharterOption(definition=self.plain, name="Bare")
        self.assertEqual(by_lore.target_entry_id, lore.pk)
        self.assertEqual(by_being.target_entry_id, self.calyx_entry.pk)
        self.assertIsNone(bare.target_entry_id)

    def test_one_patron_question_per_charter(self):
        from world.societies.houses.factories import HouseTemplateFactory

        second = HouseCharterQuestion.objects.create(
            name="Totem", prompt="Which totem?", sets_patron=True
        )
        template = HouseTemplateFactory()
        template.charter_questions.add(self.patron)
        template.full_clean()
        template.charter_questions.add(second)
        with self.assertRaises(self.ValidationError) as caught:
            template.full_clean()
        self.assertIn("charter_questions", caught.exception.message_dict)


class PatronFoundingTests(AspectTestData):
    """#4205: the pick on the patron question becomes the house's patron, once, at
    founding. #5110: the pick is a god the question offers, the active and public gods
    of its worship, and the house shows it by the god's own name."""

    @classmethod
    def setUpTestData(cls):
        from world.worship.factories import WorshippedBeingFactory, WorshipTraditionFactory

        super().setUpTestData()
        cls.liturgy = WorshipTraditionFactory(name="Church Liturgy")
        cls.calyx_entry = CodexEntryFactory(name="Calyx", is_public=True)
        cls.calyx = WorshippedBeingFactory(
            name="Calyx", tradition=cls.liturgy, codex_entry=cls.calyx_entry
        )
        # Three gods the question must never offer: one whose page is not public, one
        # with no page at all, one retired, and one of another worship.
        cls.hidden = WorshippedBeingFactory(
            name="The Veiled One",
            tradition=cls.liturgy,
            codex_entry=CodexEntryFactory(name="The Veiled One", is_public=False),
        )
        cls.pageless = WorshippedBeingFactory(name="Nameless", tradition=cls.liturgy)
        cls.retired_god = WorshippedBeingFactory(
            name="Old Zircon",
            tradition=cls.liturgy,
            is_active=False,
            codex_entry=CodexEntryFactory(name="Old Zircon", is_public=True),
        )
        cls.occult = WorshippedBeingFactory(
            name="The Fleshreaper",
            tradition=WorshipTraditionFactory(name="Occultism"),
            codex_entry=CodexEntryFactory(name="The Fleshreaper", is_public=True),
        )
        cls.patron = HouseCharterQuestion.objects.create(
            name="Patron",
            prompt="Whom does the house serve?",
            sets_patron=True,
            patron_tradition=cls.liturgy,
        )
        cls.template.charter_questions.add(cls.patron)

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

    def test_the_question_offers_the_active_public_gods_of_its_worship(self):
        from world.societies.houses.creator import patron_choices

        self.assertEqual([being.name for being in patron_choices(self.patron)], ["Calyx"])
        # with no worship set it offers nobody
        unset = HouseCharterQuestion.objects.create(name="Totem", prompt="Which?")
        self.assertEqual(patron_choices(unset), [])

    def test_founding_writes_the_patron_by_the_gods_own_name(self):
        from world.roster.services.kinship import OMNISCIENT
        from world.societies.houses.almanach import publish_house
        from world.societies.houses.almanach_reads import document_for_house
        from world.societies.serializers import OrganizationSerializer

        org = self._found("Knightsmere", patron_being_id=self.calyx.pk)
        self.assertEqual(org.patron, self.calyx)

        expected = {
            "being_id": self.calyx.pk,
            "being_name": "Calyx",
            "codex_entry_id": self.calyx_entry.pk,
        }
        house = OrganizationSerializer(org).data["house"]
        self.assertEqual(house["patron"], expected)
        # the patron is the house's own line, never one of its option picks
        self.assertEqual(
            sorted(facet["option"] for facet in house["facets"]), ["Fortitude", "Tithe", "Vigil"]
        )
        publish_house(org)
        document = document_for_house(org, viewer=OMNISCIENT, staff=True)
        self.assertEqual(document.house["patron"], expected)

    def test_a_patron_whose_page_stops_being_public_is_not_named_to_a_player(self):
        """The house keeps its patron; a reader who is not staff is not told a god
        whose Codex page is no longer public. Staff still read it."""
        from world.societies.houses.almanach_reads import patron_payload
        from world.societies.serializers import OrganizationSerializer

        org = self._found("Shroudmere", patron_being_id=self.calyx.pk)
        self.calyx_entry.is_public = False
        self.calyx_entry.save(update_fields=["is_public"])
        try:
            self.assertEqual(org.patron, self.calyx)
            self.assertIsNone(OrganizationSerializer(org).data["house"]["patron"])
            self.assertEqual(patron_payload(org)["being_name"], "Calyx")
        finally:
            # the entry is identity-mapped and class-shared: put it back for the rest
            self.calyx_entry.is_public = True
            self.calyx_entry.save(update_fields=["is_public"])

    def test_a_required_patron_left_unpicked_is_refused(self):
        with self.assertRaises(HousesServiceError) as caught:
            self._submit_full()
        self.assertIn("choose one", caught.exception.user_message)

    def test_a_god_the_question_does_not_offer_is_refused(self):
        for god in (self.hidden, self.pageless, self.retired_god, self.occult):
            with self.subTest(god=god.name), self.assertRaises(HousesServiceError) as caught:
                self._submit_full(patron_being_id=god.pk)
            self.assertIn("not one of the choices", caught.exception.user_message)

    def test_the_patron_question_is_not_answered_with_an_option(self):
        picks = {
            self.virtue.pk: [self.fortitude.pk],
            self.traditions.pk: [self.trad_a.pk, self.trad_b.pk],
            self.patron.pk: [self.fortitude.pk],
        }
        with self.assertRaises(HousesServiceError):
            self._submit_full(facet_picks=picks, patron_being_id=self.calyx.pk)

    def test_a_charter_without_a_patron_question_writes_none(self):
        from world.societies.serializers import OrganizationSerializer

        self.template.charter_questions.remove(self.patron)
        org = self._found("Godlessmere")
        self.assertIsNone(org.patron)
        self.assertIsNone(OrganizationSerializer(org).data["house"]["patron"])
        with self.assertRaises(HousesServiceError):
            self._submit_full(patron_being_id=self.calyx.pk)


class PatronQuestionShapeTests(TestCase):
    """#4205 review fold-ins: a patron question is single-pick, and the template admin
    refuses two patron questions on the selection it is about to save."""

    def test_a_patron_question_takes_exactly_one_pick(self):
        from django.core.exceptions import ValidationError

        from world.worship.factories import WorshipTraditionFactory

        liturgy = WorshipTraditionFactory(name="Church Liturgy")
        wide = HouseCharterQuestion(
            name="Patrons", prompt="Whom?", sets_patron=True, max_picks=2, patron_tradition=liturgy
        )
        with self.assertRaises(ValidationError) as caught:
            wide.full_clean()
        self.assertIn("max_picks", caught.exception.message_dict)
        HouseCharterQuestion(
            name="Patron", prompt="Whom?", sets_patron=True, patron_tradition=liturgy
        ).full_clean()

    def test_a_patron_question_says_which_worship_its_gods_are_of(self):
        """#5110: the worship is what makes the choices; only a patron question has one."""
        from django.core.exceptions import ValidationError

        from world.worship.factories import WorshipTraditionFactory

        with self.assertRaises(ValidationError) as caught:
            HouseCharterQuestion(name="Patron", prompt="Whom?", sets_patron=True).full_clean()
        self.assertIn("patron_tradition", caught.exception.message_dict)
        with self.assertRaises(ValidationError) as caught:
            HouseCharterQuestion(
                name="Virtue", prompt="Which?", patron_tradition=WorshipTraditionFactory()
            ).full_clean()
        self.assertIn("patron_tradition", caught.exception.message_dict)

    def test_the_template_admin_refuses_two_patron_questions_before_the_m2m_save(self):
        from world.societies.admin import HouseTemplateAdminForm
        from world.societies.houses.factories import HouseTemplateFactory

        template = HouseTemplateFactory()
        first = HouseCharterQuestion.objects.create(name="Patron", prompt="Whom?", sets_patron=True)
        second = HouseCharterQuestion.objects.create(
            name="Totem", prompt="Which?", sets_patron=True
        )
        base = {
            field: getattr(template, f"{field}_id", None) or getattr(template, field)
            for field in ("name", "realm", "kind", "society", "org_type")
        }
        base.update(
            {
                "name_pattern": template.name_pattern,
                "starting_kin_slots": template.starting_kin_slots,
                "charter_questions": [first.pk, second.pk],
            }
        )
        form = HouseTemplateAdminForm(data=base, instance=template)
        self.assertFalse(form.is_valid())
        self.assertIn("charter_questions", form.errors)
        base["charter_questions"] = [first.pk]
        form = HouseTemplateAdminForm(data=base, instance=template)
        self.assertNotIn("charter_questions", form.errors)
