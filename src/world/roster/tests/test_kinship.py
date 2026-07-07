"""Kinship graph tests (#2062): derivation matrix, visibility, souls, slots."""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.constants import (
    DefinitionTier,
    MembershipBasis,
    ParentageKind,
    RelationshipType,
)
from world.roster.factories import (
    FamilyFactory,
    KinSlotPoolFactory,
    KinspersonFactory,
    UnionKindFactory,
)
from world.roster.models import Kinsperson, RosterEntry
from world.roster.services import kinship
from world.roster.services.kinship import OMNISCIENT


def _person(name: str, **kwargs) -> Kinsperson:
    return kinship.create_person(name=name, **kwargs)


def _pc_with_entry(name: str):
    """A sheet-bound node + its RosterEntry (the viewer identity)."""
    from world.roster.factories import RosterEntryFactory

    character = CharacterFactory(db_key=name)
    sheet = CharacterSheetFactory(character=character)
    entry = RosterEntryFactory(character_sheet=sheet)
    node = kinship.create_person(tier=DefinitionTier.PC, sheet=sheet)
    return node, entry, sheet


class DerivationMatrixTests(TestCase):
    """Blood, marriage, foster, and step relations derive with distinct labels."""

    def setUp(self) -> None:
        self.mother = _person("Mother")
        self.father = _person("Father")
        self.child = _person("Child")
        kinship.record_parentage(child=self.child, parent=self.mother)
        kinship.record_parentage(child=self.child, parent=self.father)

    def test_parent_child_labels(self) -> None:
        assert (
            kinship.derive_relationship(self.child, self.mother, OMNISCIENT)
            == RelationshipType.PARENT
        )
        assert (
            kinship.derive_relationship(self.mother, self.child, OMNISCIENT)
            == RelationshipType.CHILD
        )

    def test_full_and_half_siblings(self) -> None:
        full = _person("Full Sibling")
        kinship.record_parentage(child=full, parent=self.mother)
        kinship.record_parentage(child=full, parent=self.father)
        half = _person("Half Sibling")
        kinship.record_parentage(child=half, parent=self.mother)
        assert kinship.derive_relationship(self.child, full, OMNISCIENT) == RelationshipType.SIBLING
        assert (
            kinship.derive_relationship(self.child, half, OMNISCIENT)
            == RelationshipType.HALF_SIBLING
        )

    def test_polycule_four_parents_all_derive(self) -> None:
        """Tree-of-Souls children carry N parents, any composition."""
        extra_a = _person("Third Parent")
        extra_b = _person("Fourth Parent")
        kinship.record_parentage(child=self.child, parent=extra_a, kind=ParentageKind.TREE_OF_SOULS)
        kinship.record_parentage(child=self.child, parent=extra_b, kind=ParentageKind.TREE_OF_SOULS)
        edges = kinship.parents_of(self.child, OMNISCIENT)
        assert len(edges) == 4
        assert (
            kinship.derive_relationship(self.child, extra_b, OMNISCIENT) == RelationshipType.PARENT
        )

    def test_vampiric_progenitor_coexists_with_biological(self) -> None:
        sire = _person("Progenitor")
        kinship.record_parentage(child=self.child, parent=sire, kind=ParentageKind.VAMPIRIC_EMBRACE)
        kinds = {e.kind for e in kinship.parents_of(self.child, OMNISCIENT)}
        assert ParentageKind.VAMPIRIC_EMBRACE in kinds
        assert ParentageKind.BIOLOGICAL in kinds

    def test_foster_labeled_and_excluded_from_lineage(self) -> None:
        foster = _person("Foster Mother")
        kinship.record_parentage(child=self.child, parent=foster, kind=ParentageKind.FOSTER)
        assert (
            kinship.derive_relationship(self.child, foster, OMNISCIENT)
            == RelationshipType.FOSTER_PARENT
        )
        # Lineage walks exclude foster: no sibling via foster parent.
        foster_kid = _person("Foster Sibling")
        kinship.record_parentage(child=foster_kid, parent=foster, kind=ParentageKind.FOSTER)
        assert (
            kinship.derive_relationship(self.child, foster_kid, OMNISCIENT)
            == RelationshipType.FOSTER_SIBLING
        )

    def test_spouse_step_and_in_law_derive_from_unions(self) -> None:
        marriage = UnionKindFactory()
        stepmother = _person("Stepmother")
        kinship.record_union(kind=marriage, members=[self.father, stepmother])
        assert (
            kinship.derive_relationship(self.father, stepmother, OMNISCIENT)
            == RelationshipType.SPOUSE
        )
        assert (
            kinship.derive_relationship(self.child, stepmother, OMNISCIENT)
            == RelationshipType.STEP_PARENT
        )
        # In-law: spouse's blood kin.
        step_mother_mother = _person("Stepmother's Mother")
        kinship.record_parentage(child=stepmother, parent=step_mother_mother)
        assert (
            kinship.derive_relationship(self.father, step_mother_mother, OMNISCIENT)
            == RelationshipType.IN_LAW
        )

    def test_grandparent_aunt_cousin_walks(self) -> None:
        grandma = _person("Grandmother")
        kinship.record_parentage(child=self.mother, parent=grandma)
        aunt = _person("Aunt")
        kinship.record_parentage(child=aunt, parent=grandma)
        cousin = _person("Cousin")
        kinship.record_parentage(child=cousin, parent=aunt)
        assert (
            kinship.derive_relationship(self.child, grandma, OMNISCIENT)
            == RelationshipType.GRANDPARENT
        )
        assert (
            kinship.derive_relationship(self.child, aunt, OMNISCIENT) == RelationshipType.AUNT_UNCLE
        )
        assert (
            kinship.derive_relationship(self.child, cousin, OMNISCIENT) == RelationshipType.COUSIN
        )

    def test_adding_a_brother_ripples_everywhere(self) -> None:
        """The ripple rule: one added node updates every derived readout."""
        grandchild = _person("Grandchild")
        kinship.record_parentage(child=grandchild, parent=self.child)
        brother = _person("New Brother")
        kinship.record_parentage(child=brother, parent=self.mother)
        kinship.record_parentage(child=brother, parent=self.father)
        assert (
            kinship.derive_relationship(grandchild, brother, OMNISCIENT)
            == RelationshipType.AUNT_UNCLE
        )
        assert (
            kinship.derive_relationship(self.mother, brother, OMNISCIENT) == RelationshipType.CHILD
        )


class VisibilityTests(TestCase):
    """Truth vs public record, per-viewer knowledge, staff-only facts."""

    def setUp(self) -> None:
        self.child_node, self.child_entry, self.child_sheet = _pc_with_entry("Heir")
        self.official = _person("Official Father")
        self.real = _person("Real Father")
        kinship.record_parentage(child=self.child_node, parent=self.official, is_true=False)
        self.hidden = kinship.record_parentage(
            child=self.child_node,
            parent=self.real,
            is_public_record=False,
            secret_content="The heir's true father is another PLACEHOLDER.",
        )

    def test_public_false_edge_renders_to_strangers(self) -> None:
        _stranger_node, stranger_entry, _sheet = _pc_with_entry("Stranger")
        edges = kinship.parents_of(self.child_node, stranger_entry)
        assert [e.parent_id for e in edges] == [self.official.pk]

    def test_subject_does_not_know_their_own_hidden_truth(self) -> None:
        """The Misbegotten rule: even the child starts unaware."""
        edges = kinship.parents_of(self.child_node, self.child_entry)
        assert [e.parent_id for e in edges] == [self.official.pk]

    def test_secret_knowledge_reveals_the_truth(self) -> None:
        from world.secrets.services import grant_secret_knowledge

        assert self.hidden.secret is not None
        grant_secret_knowledge(roster_entry=self.child_entry, secret=self.hidden.secret)
        parent_ids = {e.parent_id for e in kinship.parents_of(self.child_node, self.child_entry)}
        assert self.real.pk in parent_ids

    def test_subject_unaware_secret_off_own_shelf(self) -> None:
        from world.secrets.services import secrets_owned_by

        assert self.hidden.secret is not None
        shelf = secrets_owned_by(self.child_sheet)
        assert self.hidden.secret not in list(shelf)

    def test_hidden_fact_with_no_secret_is_staff_only(self) -> None:
        ghost_parent = _person("Ghost")
        nameless = _person("Nameless Child")
        edge = kinship.record_parentage(child=nameless, parent=ghost_parent, is_public_record=False)
        assert edge.secret is None
        assert kinship.parents_of(nameless, self.child_entry) == []
        assert len(kinship.parents_of(nameless, OMNISCIENT)) == 1


class SoulChainTests(TestCase):
    """The Monique/Covet case: chains are transitive, knowledge is per-life."""

    def setUp(self) -> None:
        self.pc_node, self.pc_entry, self.pc_sheet = _pc_with_entry("Seeker")
        self.covet = _person("Covet", is_deceased=True)
        self.monique = _person("Monique", is_deceased=True)
        inc = kinship.record_incarnation(soul=None, kinsperson=self.covet, is_public_record=True)
        self.soul = inc.soul
        # Monique's membership is public (the world knew she was Covet reborn).
        kinship.record_incarnation(soul=self.soul, kinsperson=self.monique, is_public_record=True)
        # The PC's own membership is hidden behind a secret.
        self.own = kinship.record_incarnation(
            soul=self.soul,
            kinsperson=self.pc_node,
            is_public_record=False,
            secret_content="You are the latest life of an old soul PLACEHOLDER.",
        )

    def test_unaware_pc_sees_no_chain(self) -> None:
        assert kinship.incarnation_chain_of(self.pc_node, self.pc_entry) == []

    def test_learning_own_membership_reveals_public_lives_only(self) -> None:
        from world.secrets.services import grant_secret_knowledge

        grant_secret_knowledge(roster_entry=self.pc_entry, secret=self.own.secret)
        chain_ids = {
            inc.kinsperson_id for inc in kinship.incarnation_chain_of(self.pc_node, self.pc_entry)
        }
        # Both prior lives are public record, so knowing your own membership
        # reveals the whole public chain — Covet AND Monique here.
        assert chain_ids == {self.covet.pk, self.monique.pk}

    def test_hidden_intermediate_life_stays_undiscovered(self) -> None:
        from world.secrets.services import grant_secret_knowledge

        # Re-hide Monique's membership behind its own (unlearned) secret.
        monique_inc = self.soul.incarnations.get(kinsperson=self.monique)
        monique_inc.is_public_record = False
        monique_inc.save(update_fields=["is_public_record"])
        grant_secret_knowledge(roster_entry=self.pc_entry, secret=self.own.secret)
        chain_ids = {
            inc.kinsperson_id for inc in kinship.incarnation_chain_of(self.pc_node, self.pc_entry)
        }
        assert chain_ids == {self.covet.pk}
        assert (
            kinship.derive_relationship(self.pc_node, self.covet, self.pc_entry)
            == RelationshipType.PAST_INCARNATION
        )


class SlotAndPoolTests(TestCase):
    def test_mint_from_pool_decrements_and_links_parents(self) -> None:
        family = FamilyFactory(family_type="noble")
        parent = KinspersonFactory(family=family)
        pool = KinSlotPoolFactory(family=family, count_remaining=2, parents=[parent])

        minted = kinship.mint_from_pool(pool)

        pool.refresh_from_db()
        assert pool.count_remaining == 1
        assert minted.is_appable
        assert [e.parent_id for e in kinship.parents_of(minted, OMNISCIENT)] == [parent.pk]

    def test_exhausted_pool_refuses(self) -> None:
        pool = KinSlotPoolFactory(count_remaining=0)
        with self.assertRaises(kinship.KinshipServiceError):
            kinship.mint_from_pool(pool)

    def test_claim_binds_sheet_and_closes_slot(self) -> None:
        family = FamilyFactory()
        slot = KinspersonFactory(family=family, is_appable=True, name="Open Slot")
        character = CharacterFactory(db_key="Claimant")
        sheet = CharacterSheetFactory(character=character)

        claimed = kinship.claim_appable_node(node=slot, sheet=sheet)

        assert claimed.sheet_id == sheet.pk
        assert claimed.definition_tier == DefinitionTier.PC
        assert not claimed.is_appable

    def test_double_claim_refused(self) -> None:
        slot = KinspersonFactory(is_appable=True)
        sheet_a = CharacterSheetFactory(character=CharacterFactory(db_key="First"))
        sheet_b = CharacterSheetFactory(character=CharacterFactory(db_key="Second"))
        kinship.claim_appable_node(node=slot, sheet=sheet_a)
        with self.assertRaises(kinship.KinshipServiceError):
            kinship.claim_appable_node(node=slot, sheet=sheet_b)


class MembershipTests(TestCase):
    def test_primary_membership_maintains_surname_denorm(self) -> None:
        person = KinspersonFactory()
        old_family = FamilyFactory()
        new_family = FamilyFactory()
        kinship.add_membership(kinsperson=person, family=old_family, basis=MembershipBasis.BORN)
        person.refresh_from_db()
        assert person.family_id == old_family.pk

        kinship.add_membership(
            kinsperson=person, family=new_family, basis=MembershipBasis.MARRIED_IN
        )
        person.refresh_from_db()
        assert person.family_id == new_family.pk
        assert person.family_memberships.filter(is_primary=True).count() == 1

    def test_end_membership_clears_denorm(self) -> None:
        person = KinspersonFactory()
        family = FamilyFactory()
        membership = kinship.add_membership(
            kinsperson=person, family=family, basis=MembershipBasis.BORN
        )
        kinship.end_membership(membership=membership)
        person.refresh_from_db()
        assert person.family_id is None


class DeferredDefinitionTests(TestCase):
    def test_only_the_holder_may_define(self) -> None:
        holder_sheet = CharacterSheetFactory(character=CharacterFactory(db_key="Holder"))
        other_sheet = CharacterSheetFactory(character=CharacterFactory(db_key="Other"))
        node = KinspersonFactory(name="", deferred_definer=holder_sheet)
        with self.assertRaises(kinship.KinshipServiceError):
            kinship.define_deferred(actor_sheet=other_sheet, node=node, name="Intruder's Idea")
        defined = kinship.define_deferred(
            actor_sheet=holder_sheet, node=node, name="My Long-Lost Mother"
        )
        assert defined.name == "My Long-Lost Mother"
        assert defined.deferred_definer is None


class SeedTests(TestCase):
    def test_kinship_demo_seed_idempotent(self) -> None:
        from world.seeds.kinship import DUCAL_HOUSE_NAME, seed_kinship_demo

        seed_kinship_demo()
        first_count = Kinsperson.objects.count()
        seed_kinship_demo()
        assert Kinsperson.objects.count() == first_count
        from world.roster.models import Family

        family = Family.objects.get(name=DUCAL_HOUSE_NAME)
        nodes, pools = kinship.open_slots_for(family)
        assert len(nodes) == 2
        assert len(pools) == 1

    def test_tree_payload_hides_the_truth_from_strangers(self) -> None:
        from world.roster.models import Family
        from world.seeds.kinship import DUCAL_HOUSE_NAME, seed_kinship_demo

        seed_kinship_demo()
        family = Family.objects.get(name=DUCAL_HOUSE_NAME)
        _node, entry, _sheet = _pc_with_entry("Bystander")
        payload = kinship.family_tree_for(family, entry)
        # The hidden-true sire edge is invisible; the public-false edge shows.
        hidden = [e for e in payload.parentage if e["via_secret"]]
        assert hidden == []
        omniscient_payload = kinship.family_tree_for(family, OMNISCIENT)
        assert any(not e["is_true"] for e in omniscient_payload.parentage)


class RosterEntryFactoryCheck(TestCase):
    def test_pc_with_entry_helper(self) -> None:
        node, entry, sheet = _pc_with_entry("Selfcheck")
        assert node.sheet_id == sheet.pk
        assert isinstance(entry, RosterEntry)
