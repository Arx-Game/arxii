"""Journeys: joining an established family takes a seat staff opened (#5130, ADR-5130).

Kathryn's player claims House Katta. The house is offered because it has a seat to
take; its seat reads as the head's child; the family alone leaves the Lineage stage
incomplete; picking the seat completes it; finalize binds the character to that seat
with the parents staff wrote, and the names the player typed for parents earlier add
nobody. Once the seat is taken the house has none left and is no longer offered.
"""

from __future__ import annotations

from evennia_extensions.factories import AccountFactory
from integration_tests.harness import JourneyCase
from world.character_creation.constants import Parentage, Stage
from world.character_creation.factories import OriginTemplateFactory
from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.roster.constants import RelationshipType
from world.roster.factories import FamilyFactory
from world.roster.models import Kinsperson, ParentageEdge
from world.roster.services import kinship
from world.societies.factories import OrganizationFactory
from world.societies.houses.constants import TitleTier
from world.societies.houses.models import Title

CHOOSE_A_PLACE = "Choose your place in the family"


class JoiningAnEstablishedFamily(FinalizationTestMixin, JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self._flush_common_caches()
        self.account = AccountFactory()
        self._setup_finalization_base(self, prefix="Seat", height_min=700, height_max=800)
        self.template = OriginTemplateFactory(
            beginning=self.beginnings,
            allows_claim_family=True,
            allows_name_family=False,
            allows_no_family=False,
            parentage=Parentage.KNOWN,
        )
        # House Katta: Alarysa holds its title, and her daughter's seat is open.
        self.katta = FamilyFactory(name="Katta", origin_realm=self.realm)
        house = OrganizationFactory(name="House Katta", family=self.katta)
        self.alarysa = kinship.create_person(name="Alarysa", family=self.katta)
        self.galleron = kinship.create_person(name="Galleron", family=self.katta)
        Title.objects.create(
            name="County of Katta",
            tier=TitleTier.COUNTY,
            realm=self.realm,
            house=house,
            holder=self.alarysa,
        )
        self.seat = kinship.create_person(name="Kathryn", family=self.katta)
        self.seat.is_appable = True
        self.seat.name_locked = True
        self.seat.save(update_fields=["is_appable", "name_locked"])
        for parent in (self.alarysa, self.galleron):
            kinship.record_parentage(child=self.seat, parent=parent)
        # A family nobody can be seated in.
        self.closed = FamilyFactory(name="Valeweep", origin_realm=self.realm)
        kinship.create_person(name="Ysmae", family=self.closed)
        self.client = self.api(self.account)

    def _draft(self):
        draft = self._create_base_draft(
            first_name="Kathryn", line_parent_name="Martha", other_parent_name="Bob"
        )
        draft.selected_origin_template = self.template
        draft.draft_data.pop("tarot_card_name", None)
        draft.save()
        return draft

    def _patch(self, draft, body: dict):
        response = self.client.patch(
            f"/api/character-creation/drafts/{draft.pk}/", body, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    @staticmethod
    def _lineage_errors(body: dict) -> list[str]:
        return body["stage_errors"].get(str(int(Stage.LINEAGE)), [])

    def _offered(self) -> dict[str, bool]:
        rows = self.client.get("/api/roster/families/").json()
        return {row["name"]: row["has_open_seat"] for row in rows}

    def test_the_family_is_joined_through_its_open_seat(self) -> None:
        draft = self._draft()

        # Only the house with a seat to take is offered.
        offered = self._offered()
        self.assertTrue(offered["Katta"])
        self.assertFalse(offered["Valeweep"])

        # The seat says what it is to the head of the house.
        seats = self.client.get(f"/api/roster/families/{self.katta.pk}/slots/").json()
        self.assertEqual(seats["head_name"], "Alarysa")
        self.assertEqual(
            [(row["name"], row["name_locked"], row["head_relation"]) for row in seats["slots"]],
            [("Kathryn", True, RelationshipType.CHILD)],
        )

        # The family alone is not a place in it.
        body = self._patch(draft, {"family_id": self.katta.pk})
        self.assertIn(CHOOSE_A_PLACE, self._lineage_errors(body))
        body = self._patch(draft, {"claimed_kin_slot_id": self.seat.pk})
        self.assertEqual(body["claimed_kin_slot"], self.seat.pk)
        self.assertEqual(self._lineage_errors(body), [])

        # Finalize seats the character: the node is the seat, the parents are the
        # ones staff wrote, and the names typed for parents earlier add nobody.
        draft.refresh_from_db()
        character = finalize_character(draft, add_to_roster=True)
        node = Kinsperson.objects.get(sheet=character.sheet_data)
        self.assertEqual(node.pk, self.seat.pk)
        parents = {edge.parent.name for edge in ParentageEdge.objects.filter(child=node)}
        self.assertEqual(parents, {"Alarysa", "Galleron"})
        self.assertFalse(Kinsperson.objects.filter(name__in=["Martha", "Bob"]).exists())

        # The seat is taken: the house has none left and is no longer offered.
        seats = self.client.get(f"/api/roster/families/{self.katta.pk}/slots/").json()
        self.assertEqual(seats["slots"], [])
        self.assertFalse(self._offered()["Katta"])

    def test_a_seat_of_another_family_is_no_seat_here(self) -> None:
        draft = self._draft()
        other = FamilyFactory(name="Ashcombe", origin_realm=self.realm)
        elsewhere = kinship.create_person(name="Bram", family=other)
        elsewhere.is_appable = True
        elsewhere.save(update_fields=["is_appable"])

        self._patch(draft, {"family_id": self.katta.pk})
        body = self._patch(draft, {"claimed_kin_slot_id": elsewhere.pk})
        self.assertIn(
            "That place belongs to a family you are not joining", self._lineage_errors(body)
        )
        # Changing family lets go of the seat picked in the old one.
        self._patch(draft, {"claimed_kin_slot_id": self.seat.pk})
        body = self._patch(draft, {"family_id": other.pk})
        self.assertIsNone(body["claimed_kin_slot"])
        self.assertIn(CHOOSE_A_PLACE, self._lineage_errors(body))
