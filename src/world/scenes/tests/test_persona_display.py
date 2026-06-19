"""Per-viewer persona display resolution (#1109): sdesc, discovery reveal, self-ownership."""

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.models import Gender
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import InteractionMode, ScenePrivacyMode
from world.scenes.factories import (
    InteractionFactory,
    PersonaDiscoveryFactory,
    PersonaFactory,
    SceneFactory,
)
from world.scenes.persona_display import compose_sdesc


def _gender(key):
    return Gender.objects.get_or_create(key=key, defaults={"display_name": key.title()})[0]


def _played_character(account, *, gender_key="male"):
    roster_entry = RosterEntryFactory()
    player_data = PlayerDataFactory(account=account)
    RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
    sheet = roster_entry.character_sheet
    sheet.gender = _gender(gender_key)
    sheet.save(update_fields=["gender"])
    return roster_entry


class ComposeSdescTests(TestCase):
    def test_gender_noun_mapping(self) -> None:
        roster_entry = RosterEntryFactory()
        sheet = roster_entry.character_sheet
        mask = PersonaFactory(character_sheet=sheet, is_fake_name=True, name="stag mask")

        sheet.gender = _gender("male")
        sheet.save(update_fields=["gender"])
        assert compose_sdesc(mask) == "a man wearing a stag mask"

        sheet.gender = _gender("female")
        sheet.save(update_fields=["gender"])
        assert compose_sdesc(mask) == "a woman wearing a stag mask"

        sheet.gender = _gender("nonbinary")
        sheet.save(update_fields=["gender"])
        assert compose_sdesc(mask) == "a person wearing a stag mask"


class PersonaDisplayApiTests(APITestCase):
    def _persona_name(self, response, interaction_pk):
        for row in response.data["results"]:
            if row["id"] == interaction_pk:
                return row["persona"]["name"]
        return None

    def _public_pose_by(self, persona):
        scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        return InteractionFactory(persona=persona, mode=InteractionMode.POSE, scene=scene)

    def test_non_owner_sees_an_anonymous_face_as_an_sdesc(self) -> None:
        owner = AccountFactory()
        roster_entry = _played_character(owner, gender_key="male")
        mask = PersonaFactory(
            character_sheet=roster_entry.character_sheet, is_fake_name=True, name="stag mask"
        )
        pose = self._public_pose_by(mask)

        viewer = AccountFactory()
        _played_character(viewer)
        self.client.force_authenticate(user=viewer)
        response = self.client.get(reverse("interaction-list"))
        assert self._persona_name(response, pose.pk) == "a man wearing a stag mask"

    def test_owner_is_never_restricted_from_their_own_face(self) -> None:
        owner = AccountFactory()
        roster_entry = _played_character(owner)
        mask = PersonaFactory(
            character_sheet=roster_entry.character_sheet, is_fake_name=True, name="stag mask"
        )
        pose = self._public_pose_by(mask)

        self.client.force_authenticate(user=owner)
        response = self.client.get(reverse("interaction-list"))
        # The owning player sees the real persona name, never the anonymized sdesc.
        assert self._persona_name(response, pose.pk) == "stag mask"

    def test_a_viewer_who_discovered_the_link_sees_the_reveal(self) -> None:
        owner = AccountFactory()
        roster_entry = _played_character(owner)
        sheet = roster_entry.character_sheet
        mask = PersonaFactory(character_sheet=sheet, is_fake_name=True, name="stag mask")
        pose = self._public_pose_by(mask)

        viewer = AccountFactory()
        viewer_entry = _played_character(viewer)
        PersonaDiscoveryFactory(
            persona=mask,
            linked_to=sheet.primary_persona,
            discovered_by=viewer_entry.character_sheet,
        )

        self.client.force_authenticate(user=viewer)
        response = self.client.get(reverse("interaction-list"))
        assert self._persona_name(response, pose.pk) == (
            f"{sheet.primary_persona.name} (as stag mask)"
        )

    def test_a_named_public_face_renders_by_name_to_everyone(self) -> None:
        owner = AccountFactory()
        roster_entry = _played_character(owner)
        named = roster_entry.character_sheet.primary_persona  # not fake
        pose = self._public_pose_by(named)

        viewer = AccountFactory()
        _played_character(viewer)
        self.client.force_authenticate(user=viewer)
        response = self.client.get(reverse("interaction-list"))
        assert self._persona_name(response, pose.pk) == named.name

    def test_display_resolution_is_batched_not_n_plus_one(self) -> None:
        """The per-viewer resolution adds ONE discovery query for the whole page, and reads the
        apparent gender from the (prefetched) select_related — never per anonymous persona."""
        viewer = AccountFactory()
        _played_character(viewer)
        for i in range(8):
            owner = AccountFactory()
            entry = _played_character(owner)
            mask = PersonaFactory(
                character_sheet=entry.character_sheet, is_fake_name=True, name=f"mask {i}"
            )
            self._public_pose_by(mask)

        self.client.force_authenticate(user=viewer)
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(reverse("interaction-list"))
        assert response.status_code == 200

        sql = [q["sql"].lower() for q in ctx.captured_queries]
        discovery_queries = [s for s in sql if "personadiscovery" in s]
        gender_queries = [s for s in sql if "character_sheets_gender" in s]
        # One discovery query for all 8 masks; gender comes via select_related — neither grows
        # per anonymous persona (8 masks must not mean 8 of either).
        assert len(discovery_queries) <= 1, f"discovery not batched: {len(discovery_queries)}"
        assert len(gender_queries) <= 1, f"gender resolved per-row (N+1): {len(gender_queries)}"
