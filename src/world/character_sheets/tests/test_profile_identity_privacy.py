"""Fail-closed identity gating on the character-sheet profile endpoint (#1109).

GET /api/character-sheets/{pk}/ is the "click a name -> profile" surface, reachable for any
character. It must not de-anonymize: a non-privileged viewer of a character presenting a
non-primary face (an anonymous mask, or a named alt with a hidden link) never sees the real
name / bio, and only the owner / staff ever see the full secret alt list.
"""

from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerData
from world.character_sheets.models import Gender
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaDiscoveryFactory, PersonaFactory
from world.traits.factories import CharacterTraitValueFactory, StatTraitFactory


def _gender(key):
    return Gender.objects.get_or_create(key=key, defaults={"display_name": key.title()})[0]


class ProfileIdentityPrivacyTests(APITestCase):
    def _character_sheet(self, account, *, fake_active=False, extra_alt=False, gender_key="male"):
        roster_entry = RosterEntryFactory()
        player_data, _ = PlayerData.objects.get_or_create(account=account)
        RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
        sheet = roster_entry.character_sheet
        sheet.gender = _gender(gender_key)
        sheet.concept = "A secret villain"
        sheet.quote = "Mwahaha"
        sheet.background = "Born in the undercity"
        if fake_active:
            mask = PersonaFactory(
                character_sheet=sheet,
                is_fake_name=True,
                name="stag mask",
                description="a masked figure",
            )
            sheet.active_persona = mask
        if extra_alt:
            PersonaFactory(
                character_sheet=sheet, name="Robert", persona_type=PersonaType.ESTABLISHED
            )
        sheet.save()
        return sheet

    def _get(self, sheet, viewer):
        self.client.force_authenticate(user=viewer)
        return self.client.get(f"/api/character-sheets/{sheet.pk}/")

    def test_non_owner_of_an_anonymous_character_sees_sdesc_and_redacted_bio(self) -> None:
        sheet = self._character_sheet(AccountFactory(), fake_active=True, extra_alt=True)
        viewer = AccountFactory()
        self._character_sheet(viewer)  # the viewer needs to be a player

        data = self._get(sheet, viewer).data
        assert data["identity"]["name"] == "a man wearing a stag mask"
        assert data["identity"]["concept"] == ""  # bio withheld
        assert data["identity"]["family"] is None
        # Only the presented face — never the secret alt list.
        assert len(data["personas"]) == 1
        assert data["personas"][0]["name"] == "a man wearing a stag mask"
        assert data["personas"][0]["description"] == ""

    def test_owner_sees_their_full_sheet_including_every_persona(self) -> None:
        owner = AccountFactory()
        sheet = self._character_sheet(owner, fake_active=True, extra_alt=True)

        data = self._get(sheet, owner).data
        assert data["identity"]["concept"] == "A secret villain"  # revealed to the owner
        # mask + primary + Robert
        assert len(data["personas"]) == 3

    def test_staff_sees_the_full_sheet(self) -> None:
        sheet = self._character_sheet(AccountFactory(), fake_active=True, extra_alt=True)
        staff = AccountFactory(is_staff=True)
        data = self._get(sheet, staff).data
        assert data["identity"]["concept"] == "A secret villain"
        assert len(data["personas"]) == 3

    def test_non_owner_of_a_public_named_character_sees_bio_but_not_the_alt_list(self) -> None:
        sheet = self._character_sheet(AccountFactory(), fake_active=False, extra_alt=True)
        viewer = AccountFactory()
        self._character_sheet(viewer)

        data = self._get(sheet, viewer).data
        # Roster transparency: the public primary identity's bio is visible...
        assert data["identity"]["concept"] == "A secret villain"
        # ...but the secret alt list is NOT — only the presented (primary) face.
        assert len(data["personas"]) == 1

    def test_a_discoverer_sees_the_revealed_identity(self) -> None:
        owner = AccountFactory()
        sheet = self._character_sheet(owner, fake_active=True)
        viewer = AccountFactory()
        viewer_sheet = self._character_sheet(viewer)
        PersonaDiscoveryFactory(
            persona=sheet.active_persona,
            linked_to=sheet.primary_persona,
            discovered_by=viewer_sheet,
        )

        data = self._get(sheet, viewer).data
        assert data["identity"]["name"] == f"stag mask ({sheet.primary_persona.name})"
        assert data["identity"]["concept"] == "A secret villain"  # discovery reveals the bio

    def test_mechanical_sections_are_private_from_a_non_owner(self) -> None:
        # A fully public, named character: roster transparency reveals the bio + story, but the
        # mechanical sheet (stats/skills/magic/goals) is private regardless — not browsable by a
        # passer-by, even of a non-anonymous character.
        sheet = self._character_sheet(AccountFactory(), fake_active=False)
        CharacterTraitValueFactory(
            character=sheet.character, trait=StatTraitFactory(name="strength"), value=5
        )
        viewer = AccountFactory()
        self._character_sheet(viewer)

        data = self._get(sheet, viewer).data
        # Story is public (roster transparency) for the revealed public face...
        assert data["story"]["background"] == "Born in the undercity"
        # ...but the stat block is private, even when there is data to show.
        assert data["stats"] == {}
        assert data["skills"] == []
        assert data["magic"] is None
        assert data["goals"] == []

    def test_owner_sees_their_private_mechanical_sections(self) -> None:
        owner = AccountFactory()
        sheet = self._character_sheet(owner, fake_active=False)
        CharacterTraitValueFactory(
            character=sheet.character, trait=StatTraitFactory(name="strength"), value=5
        )
        data = self._get(sheet, owner).data
        assert data["stats"] == {"strength": 5}
        assert data["story"]["background"] == "Born in the undercity"

    def test_story_is_withheld_from_a_non_revealed_anonymous_figure(self) -> None:
        sheet = self._character_sheet(AccountFactory(), fake_active=True)
        viewer = AccountFactory()
        self._character_sheet(viewer)

        data = self._get(sheet, viewer).data
        # Anonymous and undiscovered: even the (otherwise public) story is withheld, because a
        # masked figure's real background would de-anonymize them.
        assert data["story"]["background"] == ""

    def test_owner_viewing_a_non_primary_face_sees_the_primary_in_parens(self) -> None:
        owner = AccountFactory()
        sheet = self._character_sheet(owner, fake_active=True)

        data = self._get(sheet, owner).data
        # The owner is never restricted, and a non-primary active face shows the real (primary)
        # identity in parens so it is never ambiguous which character the mask belongs to.
        assert data["identity"]["name"] == f"stag mask ({sheet.primary_persona.name})"
