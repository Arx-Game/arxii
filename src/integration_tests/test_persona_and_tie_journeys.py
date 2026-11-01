"""Journeys: a second persona and an organization tie from a card (#4856, slice 6 of #4813).

Maud holds no persona card, so Final Touches asks her for no face and finalize ignores the
one she saved anyway. Holding Presumed Dead, the Officially dead door opens and she finalizes
wearing the face, her true one believed dead. Holding Shady Alter Ego, she names a second
face she is not wearing. Holding The Catspaw, whose tie is with a gang, the draft offers the
realm's admitting gang and not its admitting guild; she takes a seat on the bottom rung, or a
name they already know at the Favored tier's floor. The expected shapes come from the
maintainer's rulings of 2026-11-01 (the card opens the door; the persona cards are the price
of a second face; renown at the Favored floor) and the parent's (ties optional and free).
"""

from __future__ import annotations

from integration_tests.harness import JourneyCase
from world.character_creation.constants import FinalTouchesPrompt, OfferArrival, OfferChapter
from world.character_creation.factories import DistinctionOfferFactory
from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.distinctions.factories import DistinctionFactory
from world.scenes.constants import PersonaType
from world.scenes.factories import DistinctionPersonaGrantFactory
from world.scenes.models import Persona
from world.scenes.services import active_persona_for_sheet
from world.societies.constants import OrganizationReputationCause
from world.societies.factories import (
    DistinctionOrganizationTieFactory,
    OrganizationFactory,
    OrganizationTypeFactory,
    SocietyFactory,
)
from world.societies.membership_services import active_membership_for_persona
from world.societies.models import OrganizationMembership, OrganizationReputation
from world.societies.types import FAVORED_FLOOR, ReputationTier

FACE = {"face_name": "Cambria", "concept": "A widow lately arrived", "quote": "", "never_do": ""}
SOBRIQUET = {"face_name": "The Lamplighter", "background": "Known in three cellars."}


class ASecondPersonaAndATie(FinalizationTestMixin, JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self._flush_common_caches()
        self.room = self.make_room("The Lamp Row")
        self.player = self.make_player("Maud", room=self.room)
        self.account = self.account_of(self.player)
        self._setup_finalization_base(self, prefix="Faces", height_min=700, height_max=800)
        self.society = SocietyFactory(name="The People of the Faces", realm=self.realm)
        self.gang_type = OrganizationTypeFactory(name="gang")
        self.guild_type = OrganizationTypeFactory(name="guild")
        self.gang = OrganizationFactory(
            name="The Ashfingers",
            society=self.society,
            org_type=self.gang_type,
            admits_player_characters=True,
        )
        self.guild = OrganizationFactory(
            name="The Lampwrights",
            society=self.society,
            org_type=self.guild_type,
            admits_player_characters=True,
        )
        self.presumed_dead = DistinctionFactory(name="Presumed Dead", cost_per_rank=5, max_rank=1)
        DistinctionPersonaGrantFactory(distinction=self.presumed_dead, worn=True)
        self.alter_ego = DistinctionFactory(name="Shady Alter Ego", cost_per_rank=5, max_rank=1)
        DistinctionPersonaGrantFactory(distinction=self.alter_ego, worn=False)
        self.catspaw = DistinctionFactory(name="The Catspaw", cost_per_rank=0, max_rank=1)
        DistinctionOrganizationTieFactory(distinction=self.catspaw, org_type=self.gang_type)
        self.offers = {
            card: DistinctionOfferFactory(
                distinction=card,
                chapter=OfferChapter.ACTORS_SHEET,
                arrives_as=OfferArrival.CHOICE,
                prompt=prompt,
            )
            for card, prompt in (
                (self.presumed_dead, "never_do"),
                (self.alter_ego, "protect"),
                (self.catspaw, "fear"),
            )
        }
        self.draft = self._create_base_draft(first_name="Maud")
        self.client = self.api(self.account)

    def _draft_url(self) -> str:
        return f"/api/character-creation/drafts/{self.draft.pk}/"

    def _sync(self, *cards) -> object:
        return self.client.put(
            f"/api/distinctions/drafts/{self.draft.pk}/distinctions/sync/",
            {
                "distinctions": [
                    {"id": card.pk, "rank": 1, "offer_id": self.offers[card].pk} for card in cards
                ]
            },
            format="json",
        )

    def _patch(self, draft_data: dict) -> object:
        return self.client.patch(self._draft_url(), {"draft_data": draft_data}, format="json")

    def _finalize(self):
        self.draft.refresh_from_db()
        return finalize_character(self.draft, add_to_roster=True).sheet_data

    def test_without_a_persona_card_no_face_is_asked_and_a_saved_one_is_ignored(self) -> None:
        payload = self.client.get(self._draft_url()).json()
        self.assertEqual(payload["final_touches_prompts"], [])
        response = self._patch({"officially_dead": FACE, "alter_ego": SOBRIQUET})
        self.assertEqual(response.status_code, 200, response.content)
        sheet = self._finalize()
        self.assertFalse(sheet.primary_persona.believed_deceased)
        self.assertEqual(Persona.objects.filter(character_sheet=sheet).count(), 1)

    def test_presumed_dead_opens_the_door_and_the_face_is_worn(self) -> None:
        response = self._sync(self.presumed_dead)
        self.assertEqual(response.status_code, 200, response.content)
        payload = self.client.get(self._draft_url()).json()
        self.assertEqual(payload["final_touches_prompts"], [FinalTouchesPrompt.OFFICIALLY_DEAD])
        (ask,) = payload["final_touches_cards"]
        self.assertEqual(
            (ask["name"], ask["prompt"], ask["choices"]), ("Presumed Dead", "officially_dead", [])
        )
        self.assertEqual(self._patch({"officially_dead": FACE}).status_code, 200)
        sheet = self._finalize()
        primary = sheet.primary_persona
        self.assertTrue(primary.believed_deceased)
        worn = active_persona_for_sheet(sheet)
        self.assertEqual((worn.name, worn.persona_type), ("Cambria", PersonaType.ESTABLISHED))
        self.assertEqual(worn.profile.concept, FACE["concept"])

    def test_shady_alter_ego_names_a_second_face_that_is_not_worn(self) -> None:
        response = self._sync(self.alter_ego)
        self.assertEqual(response.status_code, 200, response.content)
        payload = self.client.get(self._draft_url()).json()
        self.assertEqual(payload["final_touches_prompts"], [FinalTouchesPrompt.ALTER_EGO])
        response = self._patch({"alter_ego": {"face_name": "x", "rank": "high"}})
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(self._patch({"alter_ego": SOBRIQUET}).status_code, 200)
        sheet = self._finalize()
        primary = sheet.primary_persona
        self.assertFalse(primary.believed_deceased)
        self.assertEqual(active_persona_for_sheet(sheet).pk, primary.pk)
        hidden = Persona.objects.get(character_sheet=sheet, name="The Lamplighter")
        self.assertEqual(hidden.persona_type, PersonaType.ESTABLISHED)
        self.assertEqual(hidden.profile.background, SOBRIQUET["background"])

    def test_both_persona_cards_make_three_faces(self) -> None:
        response = self._sync(self.presumed_dead, self.alter_ego)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            self.client.get(self._draft_url()).json()["final_touches_prompts"],
            [FinalTouchesPrompt.OFFICIALLY_DEAD, FinalTouchesPrompt.ALTER_EGO],
        )
        self._patch({"officially_dead": FACE, "alter_ego": SOBRIQUET})
        sheet = self._finalize()
        self.assertEqual(Persona.objects.filter(character_sheet=sheet).count(), 3)
        self.assertEqual(active_persona_for_sheet(sheet).name, "Cambria")

    def test_the_catspaw_offers_the_realms_gang_and_a_seat_or_a_name(self) -> None:
        response = self._sync(self.catspaw)
        self.assertEqual(response.status_code, 200, response.content)
        payload = self.client.get(self._draft_url()).json()
        self.assertEqual(payload["final_touches_prompts"], [FinalTouchesPrompt.TIE])
        (ask,) = payload["final_touches_cards"]
        self.assertEqual(ask["detail"], "gang")
        self.assertEqual(
            ask["choices"], [{"id": self.gang.pk, "name": "The Ashfingers", "is_covert": False}]
        )
        key = str(self.catspaw.pk)
        # The guild is of the realm and admits, but is not a gang.
        response = self._patch(
            {"ties": {key: {"organization_id": self.guild.pk, "kind": "renown"}}}
        )
        self.assertEqual(response.status_code, 400, response.content)
        friend_tie = {"organization_id": self.gang.pk, "kind": "friend"}
        response = self._patch({"ties": {key: friend_tie}})
        self.assertEqual(response.status_code, 400, response.content)

        # A seat on the bottom rung.
        response = self._patch(
            {"ties": {key: {"organization_id": self.gang.pk, "kind": "membership"}}}
        )
        self.assertEqual(response.status_code, 200, response.content)
        sheet = self._finalize()
        primary = sheet.primary_persona
        membership = active_membership_for_persona(self.gang, primary)
        self.assertIsNotNone(membership)
        self.assertEqual(membership.rank.tier, 5)
        self.assertFalse(OrganizationReputation.objects.filter(persona=primary).exists())

    def test_the_renown_kind_starts_at_the_favored_floor(self) -> None:
        self._sync(self.catspaw)
        key = str(self.catspaw.pk)
        renown_tie = {"organization_id": self.gang.pk, "kind": "renown"}
        response = self._patch({"ties": {key: renown_tie}})
        self.assertEqual(response.status_code, 200, response.content)
        sheet = self._finalize()
        primary = sheet.primary_persona
        self.assertFalse(OrganizationMembership.objects.filter(persona=primary).exists())
        reputation = OrganizationReputation.objects.get(persona=primary, organization=self.gang)
        self.assertEqual(reputation.value, FAVORED_FLOOR)
        self.assertEqual(reputation.get_tier(), ReputationTier.FAVORED)
        (event,) = reputation.events.all()
        self.assertEqual(event.cause, OrganizationReputationCause.CHARACTER_CREATION)
        self.assertEqual(event.amount, FAVORED_FLOOR)
