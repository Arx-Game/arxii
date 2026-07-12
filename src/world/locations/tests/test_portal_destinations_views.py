"""API tests for GET /api/locations/portal-destinations/ (#2222).

Personal like comfort: only serves a character the requesting account actually plays. These
tests pin the view's auth/ownership envelope and the leak-table visibility rule (locked anchor
invisible to a stranger, visible to the room's owner) at the HTTP seam; the full service-level
matrix (kind narrowing, standing gate, current-room exclusion) is already pinned in
``world/magic/tests/test_portal_travel.py`` — this view rides that service unmodified.
"""

from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
    RoomProfileFactory,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.locations.factories import LocationOwnershipFactory
from world.magic.factories import (
    CharacterTechniqueFactory,
    PortalAnchorFactory,
    PortalAnchorKindFactory,
    TechniqueFactory,
)
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory

PORTAL_DESTINATIONS_URL = "/api/locations/portal-destinations/"


def _make_room(key: str):
    room = ObjectDBFactory(db_key=key, db_typeclass_path="typeclasses.rooms.Room")
    room_profile = RoomProfileFactory(objectdb=room)
    return room, room_profile


class PortalDestinationsApiTest(APITestCase):
    def setUp(self) -> None:
        self.user = AccountFactory()
        self.origin, self.origin_rp = _make_room("Origin")
        self.character = CharacterFactory(location=self.origin)
        self.sheet = CharacterSheetFactory(character=self.character)
        # Wire the account to the character via an active roster tenure so for_account finds it.
        entry = RosterEntryFactory(character_sheet=self.sheet)
        RosterTenureFactory(
            roster_entry=entry,
            player_data=PlayerDataFactory(account=self.user),
        )

    def test_requires_authentication(self) -> None:
        response = self.client.get(PORTAL_DESTINATIONS_URL, {"character_id": self.sheet.pk})
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_missing_character_id_is_400(self) -> None:
        self.client.force_authenticate(user=self.user)
        response = self.client.get(PORTAL_DESTINATIONS_URL)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unowned_character_is_404(self) -> None:
        other_sheet = CharacterSheetFactory()
        self.client.force_authenticate(user=self.user)
        response = self.client.get(PORTAL_DESTINATIONS_URL, {"character_id": other_sheet.pk})
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_no_travel_technique_returns_empty(self) -> None:
        self.client.force_authenticate(user=self.user)
        response = self.client.get(PORTAL_DESTINATIONS_URL, {"character_id": self.sheet.pk})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"] == []

    def test_open_anchor_of_known_kind_is_listed(self) -> None:
        kind = PortalAnchorKindFactory(name="Mirror")
        technique = TechniqueFactory(travel_anchor_kind=kind)
        CharacterTechniqueFactory(character=self.sheet, technique=technique)
        dest_room, dest_rp = _make_room("Destination")
        anchor = PortalAnchorFactory(room_profile=dest_rp, kind=kind, name="a tall mirror")

        self.client.force_authenticate(user=self.user)
        response = self.client.get(PORTAL_DESTINATIONS_URL, {"character_id": self.sheet.pk})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"] == [
            {
                "anchor_id": anchor.pk,
                "room_id": dest_room.id,
                "room_name": "Destination",
                "kind_name": "Mirror",
                "anchor_name": "a tall mirror",
            }
        ]

    def test_current_room_anchor_excluded(self) -> None:
        kind = PortalAnchorKindFactory()
        technique = TechniqueFactory(travel_anchor_kind=kind)
        CharacterTechniqueFactory(character=self.sheet, technique=technique)
        PortalAnchorFactory(room_profile=self.origin_rp, kind=kind)

        self.client.force_authenticate(user=self.user)
        response = self.client.get(PORTAL_DESTINATIONS_URL, {"character_id": self.sheet.pk})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"] == []

    def test_locked_anchor_invisible_to_stranger(self) -> None:
        kind = PortalAnchorKindFactory()
        technique = TechniqueFactory(travel_anchor_kind=kind)
        CharacterTechniqueFactory(character=self.sheet, technique=technique)
        _dest, dest_rp = _make_room("Locked Room")
        PortalAnchorFactory(room_profile=dest_rp, kind=kind, is_network_open=False)

        self.client.force_authenticate(user=self.user)
        response = self.client.get(PORTAL_DESTINATIONS_URL, {"character_id": self.sheet.pk})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"] == []

    def test_locked_anchor_visible_to_owner(self) -> None:
        kind = PortalAnchorKindFactory()
        technique = TechniqueFactory(travel_anchor_kind=kind)
        CharacterTechniqueFactory(character=self.sheet, technique=technique)
        _dest, dest_rp = _make_room("Owned Room")
        anchor = PortalAnchorFactory(room_profile=dest_rp, kind=kind, is_network_open=False)
        LocationOwnershipFactory(
            on_room=True, room_profile=dest_rp, holder_persona=self.sheet.primary_persona
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(PORTAL_DESTINATIONS_URL, {"character_id": self.sheet.pk})

        assert response.status_code == status.HTTP_200_OK
        assert [row["anchor_id"] for row in response.data["results"]] == [anchor.pk]
