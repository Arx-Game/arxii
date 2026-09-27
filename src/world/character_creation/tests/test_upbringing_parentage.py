"""Upbringing parentage: no known parents, adoptive parents, known parents (#4024)."""

from django.core.exceptions import ValidationError
from django.test import TestCase
from evennia.accounts.models import AccountDB

from world.character_creation.constants import FamilyPath, Parentage
from world.character_creation.factories import OriginTemplateFactory
from world.character_creation.serializers import CGOriginTemplateSerializer
from world.character_creation.services import finalize_character
from world.character_creation.tests.test_services import FinalizationTestMixin
from world.character_sheets.models import Gender
from world.roster.constants import MembershipBasis, ParentageKind
from world.roster.factories import FamilyFactory
from world.roster.models import FamilyMembership, Kinsperson, ParentageEdge


class UpbringingParentageCleanTests(TestCase):
    """An Upbringing's parentage must agree with the family paths it offers."""

    def test_no_known_parents_offers_only_no_family(self):
        upbringing = OriginTemplateFactory.build(
            beginning=OriginTemplateFactory().beginning,
            parentage=Parentage.UNKNOWN,
            allows_claim_family=True,
            allows_name_family=False,
            allows_no_family=True,
        )
        with self.assertRaises(ValidationError) as ctx:
            upbringing.clean()
        self.assertIn("parentage", ctx.exception.message_dict)

    def test_no_known_parents_with_only_no_family_is_valid(self):
        upbringing = OriginTemplateFactory.build(
            beginning=OriginTemplateFactory().beginning,
            parentage=Parentage.UNKNOWN,
            allows_claim_family=False,
            allows_name_family=False,
            allows_no_family=True,
        )
        upbringing.clean()

    def test_adoptive_needs_a_family_path_and_no_familyless_route(self):
        upbringing = OriginTemplateFactory.build(
            beginning=OriginTemplateFactory().beginning,
            parentage=Parentage.ADOPTIVE,
            allows_claim_family=False,
            allows_name_family=False,
            allows_no_family=True,
        )
        with self.assertRaises(ValidationError) as ctx:
            upbringing.clean()
        self.assertIn("parentage", ctx.exception.message_dict)

    def test_adoptive_with_a_family_path_is_valid(self):
        upbringing = OriginTemplateFactory.build(
            beginning=OriginTemplateFactory().beginning,
            parentage=Parentage.ADOPTIVE,
            allows_claim_family=True,
            allows_name_family=True,
            allows_no_family=False,
        )
        upbringing.clean()

    def test_known_parents_is_the_default(self):
        self.assertEqual(OriginTemplateFactory().parentage, Parentage.KNOWN)


class UpbringingSerializerTests(TestCase):
    def test_payload_carries_parentage_and_its_note(self):
        upbringing = OriginTemplateFactory(
            parentage=Parentage.UNKNOWN,
            parentage_note="The Tree leaves no mother and no father.",
            allows_name_family=False,
            allows_no_family=True,
        )
        data = CGOriginTemplateSerializer(upbringing).data
        self.assertEqual(data["parentage"], Parentage.UNKNOWN)
        self.assertEqual(data["parentage_note"], "The Tree leaves no mother and no father.")


class FamilyChoiceDefaultTests(TestCase):
    """With an established family and your own both offered, creating your own
    is where the page starts; established is opted into (#4024)."""

    def test_both_offered_and_nothing_chosen_resolves_to_your_own(self):
        from world.character_creation.factories import CharacterDraftFactory

        upbringing = OriginTemplateFactory(allows_claim_family=True, allows_name_family=True)
        draft = CharacterDraftFactory(selected_origin_template=upbringing, family_path="")
        self.assertEqual(draft.resolve_family_path(), FamilyPath.NAMED)

    def test_a_stored_established_choice_still_wins(self):
        from world.character_creation.factories import CharacterDraftFactory

        upbringing = OriginTemplateFactory(allows_claim_family=True, allows_name_family=True)
        draft = CharacterDraftFactory(
            selected_origin_template=upbringing, family_path=FamilyPath.CLAIMED
        )
        self.assertEqual(draft.resolve_family_path(), FamilyPath.CLAIMED)


class ParentageFinalizeTests(FinalizationTestMixin, TestCase):
    """Finalize records parents by the Upbringing's parentage."""

    def setUp(self):
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="parentage")
        self._setup_finalization_base(self, prefix="Parentage Test", height_min=700, height_max=800)
        self.female, _ = Gender.objects.get_or_create(
            key="female", defaults={"display_name": "Female"}
        )
        self.male, _ = Gender.objects.get_or_create(key="male", defaults={"display_name": "Male"})

    def _finalize(self, upbringing, *, family=None, path=""):
        draft = self._create_base_draft(
            line_parent_name="Martha",
            other_parent_name="Bob",
            line_parent_gender_id=self.female.pk,
            other_parent_gender_id=self.male.pk,
        )
        draft.selected_origin_template = upbringing
        draft.family = family
        draft.family_path = path
        draft.save(update_fields=["selected_origin_template", "family", "family_path"])
        character = finalize_character(draft, add_to_roster=True)
        return Kinsperson.objects.get(sheet=character.sheet_data)

    def test_adoptive_records_adoptive_parents_and_an_adopted_membership(self):
        family = FamilyFactory(name="Whisper")
        upbringing = OriginTemplateFactory(
            beginning=self.beginnings,
            parentage=Parentage.ADOPTIVE,
            allows_claim_family=True,
            allows_name_family=False,
            allows_no_family=False,
        )
        node = self._finalize(upbringing, family=family, path=FamilyPath.CLAIMED)

        edges = ParentageEdge.objects.filter(child=node)
        self.assertEqual(edges.count(), 2)
        self.assertEqual({edge.kind for edge in edges}, {ParentageKind.ADOPTIVE})
        self.assertFalse(any(edge.is_ritual_invoker for edge in edges))
        membership = FamilyMembership.objects.get(kinsperson=node, family=family)
        self.assertEqual(membership.basis, MembershipBasis.ADOPTED)

    def test_no_known_parents_records_no_parents(self):
        upbringing = OriginTemplateFactory(
            beginning=self.beginnings,
            parentage=Parentage.UNKNOWN,
            allows_name_family=False,
            allows_no_family=True,
        )
        node = self._finalize(upbringing, path=FamilyPath.NONE)
        self.assertFalse(ParentageEdge.objects.filter(child=node).exists())

    def test_known_parents_are_unchanged(self):
        family = FamilyFactory(name="Redcloud")
        upbringing = OriginTemplateFactory(
            beginning=self.beginnings,
            allows_claim_family=True,
            allows_name_family=False,
        )
        node = self._finalize(upbringing, family=family, path=FamilyPath.CLAIMED)
        edges = ParentageEdge.objects.filter(child=node)
        self.assertEqual({edge.kind for edge in edges}, {ParentageKind.BIOLOGICAL})
        membership = FamilyMembership.objects.get(kinsperson=node, family=family)
        self.assertEqual(membership.basis, MembershipBasis.BORN)
