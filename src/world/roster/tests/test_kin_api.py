"""Kin tree + relationship API tests (#3003).

Covers the two read-only HTTP surfaces over the kinship graph:
``GET /api/roster/kin/tree/<character_id>/`` (delegates to
``kin_tree_for_sheet``) and ``GET /api/roster/kin/relationship/?a=&b=``
(delegates to ``derive_relationship``, its first production caller).
Visibility is asserted end to end through the HTTP layer, not just the
service — ADR-0097's viewer-aware gating must survive the view/serializer.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.constants import DefinitionTier, RelationshipType
from world.roster.factories import FamilyFactory, RosterTenureFactory
from world.roster.services import kinship


def _sheet_with_account(name: str):
    """A CharacterSheet with an active tenure bound to a fresh account."""
    account = AccountFactory()
    sheet = CharacterSheetFactory(character=CharacterFactory(db_key=name))
    RosterTenureFactory(
        roster_entry__character_sheet=sheet,
        player_data__account=account,
    )
    return sheet, account


class CharacterKinTreeViewTests(APITestCase):
    """GET /api/roster/kin/tree/<character_id>/."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Family-bound character: must match the family's own tree endpoint.
        cls.family = FamilyFactory()
        cls.bound_sheet, cls.viewer_account = _sheet_with_account("Scion")
        kinship.create_person(tier=DefinitionTier.PC, sheet=cls.bound_sheet, family=cls.family)

        # Familyless character with a visible mother: payload.family is null.
        cls.orphan_sheet, _ = _sheet_with_account("Orphan")
        cls.orphan_node = kinship.create_person(tier=DefinitionTier.PC, sheet=cls.orphan_sheet)
        cls.orphan_mother = kinship.create_person(name="Orphan's Mother")
        kinship.record_parentage(child=cls.orphan_node, parent=cls.orphan_mother)

        # Familyless character with a hidden true parent (the Misbegotten case).
        cls.misbegotten_sheet, _ = _sheet_with_account("Misbegotten")
        cls.misbegotten_node = kinship.create_person(
            tier=DefinitionTier.PC, sheet=cls.misbegotten_sheet
        )
        cls.official_father = kinship.create_person(name="Official Father")
        cls.secret_father = kinship.create_person(name="Secret Father")
        kinship.record_parentage(
            child=cls.misbegotten_node, parent=cls.official_father, is_true=False
        )
        cls.hidden_edge = kinship.record_parentage(
            child=cls.misbegotten_node,
            parent=cls.secret_father,
            is_public_record=False,
            secret_content="The Misbegotten's true father is another PLACEHOLDER.",
        )

        cls.staff_account = AccountFactory(is_staff=True)

    def test_family_bound_matches_family_viewset_tree(self) -> None:
        self.client.force_authenticate(user=self.viewer_account)
        own = self.client.get(f"/api/roster/kin/tree/{self.bound_sheet.pk}/")
        reference = self.client.get(f"/api/roster/families/{self.family.pk}/tree/")
        self.assertEqual(own.status_code, status.HTTP_200_OK)
        self.assertEqual(reference.status_code, status.HTTP_200_OK)
        own_ids = {n["id"] for n in own.data["nodes"]}
        reference_ids = {n["id"] for n in reference.data["nodes"]}
        self.assertEqual(own_ids, reference_ids)

    def test_familyless_payload_has_null_family(self) -> None:
        self.client.force_authenticate(user=self.viewer_account)
        response = self.client.get(f"/api/roster/kin/tree/{self.orphan_sheet.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["family"])
        node_ids = {n["id"] for n in response.data["nodes"]}
        self.assertIn(self.orphan_node.pk, node_ids)
        self.assertIn(self.orphan_mother.pk, node_ids)

    def test_viewer_without_secret_sees_no_hidden_edge(self) -> None:
        self.client.force_authenticate(user=self.viewer_account)
        response = self.client.get(f"/api/roster/kin/tree/{self.misbegotten_sheet.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(
            any(e["parent_id"] == self.secret_father.pk for e in response.data["parentage"])
        )

    def test_staff_sees_hidden_edge_flagged_via_secret(self) -> None:
        self.client.force_authenticate(user=self.staff_account)
        response = self.client.get(f"/api/roster/kin/tree/{self.misbegotten_sheet.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        edge = next(
            e for e in response.data["parentage"] if e["parent_id"] == self.secret_father.pk
        )
        self.assertTrue(edge["via_secret"])

    def test_unknown_character_404(self) -> None:
        self.client.force_authenticate(user=self.staff_account)
        response = self.client.get("/api/roster/kin/tree/999999/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_rejected(self) -> None:
        response = self.client.get(f"/api/roster/kin/tree/{self.bound_sheet.pk}/")
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )


class KinRelationshipViewTests(APITestCase):
    """GET /api/roster/kin/relationship/?a=&b=."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.mother = kinship.create_person(name="Mother")
        cls.father = kinship.create_person(name="Father")
        cls.grandma = kinship.create_person(name="Grandmother")
        kinship.record_parentage(child=cls.mother, parent=cls.grandma)

        cls.viewer_sheet, cls.viewer_account = _sheet_with_account("Viewer")
        cls.viewer_node = kinship.create_person(tier=DefinitionTier.PC, sheet=cls.viewer_sheet)
        kinship.record_parentage(child=cls.viewer_node, parent=cls.mother)
        kinship.record_parentage(child=cls.viewer_node, parent=cls.father)

        # Known cousin: mother's sister's child, all public record.
        cls.aunt = kinship.create_person(name="Aunt")
        kinship.record_parentage(child=cls.aunt, parent=cls.grandma)
        cls.cousin_sheet, _ = _sheet_with_account("Cousin")
        cls.cousin_node = kinship.create_person(tier=DefinitionTier.PC, sheet=cls.cousin_sheet)
        kinship.record_parentage(child=cls.cousin_node, parent=cls.aunt)

        # Hidden half-sibling: shares the mother, but that edge is secret.
        # record_parentage's hidden-secret minting anchors the subject on the
        # child (about=child) — so half_sibling_node/-account is the secret's
        # own subject (ADR-0097: no implicit pass for the subject either).
        cls.half_sibling_sheet, cls.half_sibling_account = _sheet_with_account("HalfSibling")
        cls.half_sibling_node = kinship.create_person(
            tier=DefinitionTier.PC, sheet=cls.half_sibling_sheet
        )
        cls.hidden_edge = kinship.record_parentage(
            child=cls.half_sibling_node,
            parent=cls.mother,
            is_public_record=False,
            secret_content="A hidden half-sibling shares Mother's blood PLACEHOLDER.",
        )

        # A real sheet with no Kinsperson node at all (no CG kinship record).
        cls.unbound_sheet, _ = _sheet_with_account("Unbound")

        cls.staff_account = AccountFactory(is_staff=True)

    def test_known_cousin_returns_label(self) -> None:
        self.client.force_authenticate(user=self.viewer_account)
        response = self.client.get(
            "/api/roster/kin/relationship/",
            {"a": self.viewer_sheet.pk, "b": self.cousin_sheet.pk},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["label"], RelationshipType.COUSIN)

    def test_hidden_half_sibling_is_null_for_unknowing_viewer(self) -> None:
        self.client.force_authenticate(user=self.viewer_account)
        response = self.client.get(
            "/api/roster/kin/relationship/",
            {"a": self.viewer_sheet.pk, "b": self.half_sibling_sheet.pk},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["label"])

    def test_hidden_half_sibling_revealed_to_staff(self) -> None:
        self.client.force_authenticate(user=self.staff_account)
        response = self.client.get(
            "/api/roster/kin/relationship/",
            {"a": self.viewer_sheet.pk, "b": self.half_sibling_sheet.pk},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["label"], RelationshipType.HALF_SIBLING)

    def test_subject_of_hidden_secret_gets_no_implicit_pass(self) -> None:
        """ADR-0097: even the secret's own subject doesn't see it unlearned."""
        self.client.force_authenticate(user=self.half_sibling_account)
        response = self.client.get(
            "/api/roster/kin/relationship/",
            {"a": self.half_sibling_sheet.pk, "b": self.viewer_sheet.pk},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["label"])

    def test_unbound_character_is_null_not_404(self) -> None:
        """A real CharacterSheet with no Kinsperson node is a valid empty
        state (200, null), distinct from a CharacterSheet that doesn't exist
        (404) — matches ``kin_tree_for_sheet``'s own empty-payload branch."""
        self.client.force_authenticate(user=self.viewer_account)
        response = self.client.get(
            "/api/roster/kin/relationship/",
            {"a": self.viewer_sheet.pk, "b": self.unbound_sheet.pk},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["label"])

    def test_nonexistent_character_404(self) -> None:
        self.client.force_authenticate(user=self.viewer_account)
        response = self.client.get(
            "/api/roster/kin/relationship/",
            {"a": self.viewer_sheet.pk, "b": 999999},
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_missing_query_params_is_bad_request(self) -> None:
        self.client.force_authenticate(user=self.viewer_account)
        response = self.client.get("/api/roster/kin/relationship/", {"a": self.viewer_sheet.pk})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_rejected(self) -> None:
        response = self.client.get(
            "/api/roster/kin/relationship/",
            {"a": self.viewer_sheet.pk, "b": self.cousin_sheet.pk},
        )
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )


class FamilySerializerParticleTests(APITestCase):
    """#3261 — the family payload carries its resolved particle pair for CG preview."""

    def test_particles_serialize_for_housed_family(self) -> None:
        from world.roster.constants import NOBLE_KIND_NAME
        from world.roster.factories import FamilyKindFactory
        from world.roster.serializers.families import FamilySerializer
        from world.societies.factories import OrganizationFactory
        from world.societies.houses.models import NobiliaryParticle

        noble_kind = FamilyKindFactory(name=NOBLE_KIND_NAME)
        family = FamilyFactory(name="Volante", kind=noble_kind)
        org = OrganizationFactory(name="House Volante", family=family)
        NobiliaryParticle.objects.create(
            realm=org.society.realm,
            kind=noble_kind,
            particle="za",
            taken_in_particle="zas",
        )
        data = FamilySerializer(family).data
        self.assertEqual(data["born_particle"], "za")
        self.assertEqual(data["taken_in_particle"], "zas")

    def test_particles_blank_for_unhoused_family(self) -> None:
        from world.roster.serializers.families import FamilySerializer

        family = FamilyFactory(name="Driftfolk")
        data = FamilySerializer(family).data
        self.assertEqual(data["born_particle"], "")
        self.assertEqual(data["taken_in_particle"], "")
