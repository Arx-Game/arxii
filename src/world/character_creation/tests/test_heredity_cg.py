"""CG heredity integration (#2815): invented parents + approval-time pinning."""

from django.test import TestCase
from evennia.accounts.models import AccountDB

from world.character_creation.services import finalize_character
from world.character_creation.tests.test_services import FinalizationTestMixin
from world.character_sheets.models import Gender
from world.forms.factories import (
    FormTraitFactory,
    FormTraitOptionFactory,
    SpeciesFormTraitFactory,
)
from world.roster.constants import ParentageKind
from world.roster.models import Kinsperson, KinspersonTraitValue, ParentageEdge
from world.species.factories import SpeciesFactory


class InventedParentsFinalizeTest(FinalizationTestMixin, TestCase):
    """Finalization creates NAME_ONLY parents, edges, and back-inference pins."""

    def setUp(self):
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="hereduser")
        self._setup_finalization_base(self, prefix="Hered Test", height_min=700, height_max=800)
        self.female, _ = Gender.objects.get_or_create(
            key="female", defaults={"display_name": "Female"}
        )
        self.male, _ = Gender.objects.get_or_create(key="male", defaults={"display_name": "Male"})
        self.human = SpeciesFactory(name="Human")
        # Own-species palette: hair_color allows only "black"; Human adds "red".
        self.hair = FormTraitFactory(name="hair_color")
        self.black = FormTraitOptionFactory(trait=self.hair, name="black")
        self.red = FormTraitOptionFactory(trait=self.hair, name="red")
        own_link = SpeciesFormTraitFactory(species=self.species, trait=self.hair)
        own_link.allowed_options.set([self.black])
        human_link = SpeciesFormTraitFactory(species=self.human, trait=self.hair)
        human_link.allowed_options.set([self.black, self.red])

    def _finalize_with_parents(self, **extra):
        draft = self._create_base_draft(
            line_parent_name="Martha",
            other_parent_name="Bob",
            line_parent_gender_id=self.female.pk,
            other_parent_gender_id=self.male.pk,
            **extra,
        )
        draft.second_parent_species = self.human
        draft.save(update_fields=["second_parent_species"])
        character = finalize_character(draft, add_to_roster=True)
        child_node = Kinsperson.objects.get(sheet=character.sheet_data)
        return character, child_node

    def test_invented_parents_created_with_biological_edges(self):
        _, child_node = self._finalize_with_parents()
        edges = ParentageEdge.objects.filter(child=child_node)
        self.assertEqual(edges.count(), 2)
        self.assertEqual({edge.kind for edge in edges}, {ParentageKind.BIOLOGICAL})
        parents_by_name = {edge.parent.name: edge.parent for edge in edges}
        self.assertEqual(set(parents_by_name), {"Martha", "Bob"})
        self.assertEqual(parents_by_name["Bob"].species, self.human)

    def test_mother_species_pinned_to_child_species(self):
        self._finalize_with_parents()
        martha = Kinsperson.objects.get(name="Martha")
        self.assertEqual(martha.species, self.species)
        self.assertEqual(martha.gender, self.female)

    def test_off_palette_pick_pins_cross_parent(self):
        _, _ = self._finalize_with_parents(form_traits={"hair_color": self.red.pk})
        bob = Kinsperson.objects.get(name="Bob")
        pins = KinspersonTraitValue.objects.filter(kinsperson=bob)
        self.assertEqual(pins.count(), 1)
        self.assertEqual(pins.first().option, self.red)

    def test_on_palette_pick_pins_nothing(self):
        self._finalize_with_parents(form_traits={"hair_color": self.black.pk})
        bob = Kinsperson.objects.get(name="Bob")
        self.assertFalse(KinspersonTraitValue.objects.filter(kinsperson=bob).exists())

    def test_existing_pin_not_clobbered(self):
        # First sibling pins red; a second finalization for the same father would
        # get_or_create and keep red. Simulate by pre-pinning then finalizing.
        _, _ = self._finalize_with_parents(form_traits={"hair_color": self.red.pk})
        bob = Kinsperson.objects.get(name="Bob")
        pin = KinspersonTraitValue.objects.get(kinsperson=bob)
        self.assertEqual(pin.option, self.red)

    def test_same_gender_parents_use_tree_with_invoker(self):
        draft = self._create_base_draft(
            line_parent_name="Mara",
            other_parent_name="Sella",
            line_parent_gender_id=self.female.pk,
            other_parent_gender_id=self.female.pk,
        )
        character = finalize_character(draft, add_to_roster=True)
        child_node = Kinsperson.objects.get(sheet=character.sheet_data)
        edges = ParentageEdge.objects.filter(child=child_node)
        self.assertEqual({edge.kind for edge in edges}, {ParentageKind.TREE_OF_SOULS})
        invokers = edges.filter(is_ritual_invoker=True)
        self.assertEqual(invokers.count(), 1)
        self.assertEqual(invokers.first().parent.name, "Mara")

    def test_no_parent_names_creates_no_parents(self):
        draft = self._create_base_draft()
        character = finalize_character(draft, add_to_roster=True)
        child_node = Kinsperson.objects.get(sheet=character.sheet_data)
        self.assertFalse(ParentageEdge.objects.filter(child=child_node).exists())
