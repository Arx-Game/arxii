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
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.distinctions.types import DistinctionVisibility
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

    def test_cover_persona_with_its_own_profile_shows_the_cover_bio(self) -> None:
        # #1270 slice 2 — a cover face that has authored its own profile reads as a real person:
        # its fabricated bio shows, NOT the real one, NOT blank. With no fabricated family on the
        # cover profile, family reads as None (the real one is never substituted in).
        from world.character_sheets.factories import ProfileFactory

        sheet = self._character_sheet(AccountFactory(), fake_active=True)  # presents "stag mask"
        cover = sheet.active_persona
        cover.profile = ProfileFactory(concept="A kindly merchant", background="Sells fine silks.")
        cover.save()
        viewer = AccountFactory()
        self._character_sheet(viewer)

        data = self._get(sheet, viewer).data
        assert data["identity"]["concept"] == "A kindly merchant"  # the cover's own bio
        assert data["story"]["background"] == "Sells fine silks."
        assert data["identity"]["family"] is None  # no fabricated family → none, never the real

    def test_cover_persona_presents_its_own_fabricated_lineage(self) -> None:
        # #1270 slice 3 — a cover with a fabricated family/heritage shows THAT lineage to an
        # outsider (so the cover reads as a real person), while the real lineage stays hidden.
        from world.character_sheets.factories import ProfileFactory
        from world.roster.factories import FamilyFactory

        real_family = FamilyFactory(name="Blackmoor")
        cover_family = FamilyFactory(name="Greenvale")
        sheet = self._character_sheet(AccountFactory(), fake_active=True)
        sheet.family = real_family  # the real lineage on true_profile
        sheet.save()
        cover = sheet.active_persona
        cover.profile = ProfileFactory(concept="A kindly merchant", family=cover_family)
        cover.save()
        viewer = AccountFactory()
        self._character_sheet(viewer)

        data = self._get(sheet, viewer).data
        # The outsider sees the cover's fabricated family, never the real "Blackmoor".
        assert data["identity"]["family"]["name"] == "Greenvale"

    def test_owner_of_a_cover_sees_their_real_lineage_not_the_cover(self) -> None:
        # The owner is revealed → sees the REAL family on true_profile, not the cover's fake one.
        from world.character_sheets.factories import ProfileFactory
        from world.roster.factories import FamilyFactory

        real_family = FamilyFactory(name="Blackmoor")
        cover_family = FamilyFactory(name="Greenvale")
        owner = AccountFactory()
        sheet = self._character_sheet(owner, fake_active=True)
        sheet.family = real_family
        sheet.save()
        cover = sheet.active_persona
        cover.profile = ProfileFactory(family=cover_family)
        cover.save()

        data = self._get(sheet, owner).data
        assert data["identity"]["family"]["name"] == "Blackmoor"  # the real lineage

    def test_anonymous_face_without_a_cover_profile_withholds_lineage(self) -> None:
        # No cover profile → an outsider sees no lineage at all (never the real one).
        from world.roster.factories import FamilyFactory

        sheet = self._character_sheet(AccountFactory(), fake_active=True)
        sheet.family = FamilyFactory(name="Blackmoor")
        sheet.save()
        viewer = AccountFactory()
        self._character_sheet(viewer)

        data = self._get(sheet, viewer).data
        assert data["identity"]["family"] is None

    def test_anonymous_face_without_a_cover_profile_still_redacts_bio(self) -> None:
        # No authored cover profile → the real bio is never shown to a non-owner (no de-anon).
        sheet = self._character_sheet(AccountFactory(), fake_active=True)  # mask, no own profile
        viewer = AccountFactory()
        self._character_sheet(viewer)
        data = self._get(sheet, viewer).data
        assert data["identity"]["concept"] == ""
        assert data["story"]["background"] == ""

    def _distinction_names(self, data) -> set[str]:
        return {d["name"] for d in data["distinctions"]}

    def test_a_kind_private_distinction_is_hidden_from_a_non_owner(self) -> None:
        # Most distinctions are public, but a scandalous/criminal kind is authored PRIVATE and
        # must not out the player to a passer-by — while the owner still sees it.
        sheet = self._character_sheet(AccountFactory(), fake_active=False)
        CharacterDistinctionFactory(
            character=sheet.character,
            distinction=DistinctionFactory(
                name="Renowned Duelist", default_visibility=DistinctionVisibility.PUBLIC
            ),
        )
        CharacterDistinctionFactory(
            character=sheet.character,
            distinction=DistinctionFactory(
                name="Wanted Criminal", default_visibility=DistinctionVisibility.PRIVATE
            ),
        )
        viewer = AccountFactory()
        self._character_sheet(viewer)

        assert self._distinction_names(self._get(sheet, viewer).data) == {"Renowned Duelist"}
        assert self._distinction_names(self._get(sheet, AccountFactory(is_staff=True)).data) == {
            "Renowned Duelist",
            "Wanted Criminal",
        }

    def test_owner_sees_every_distinction_including_private(self) -> None:
        owner = AccountFactory()
        sheet = self._character_sheet(owner, fake_active=False)
        CharacterDistinctionFactory(
            character=sheet.character,
            distinction=DistinctionFactory(
                name="Wanted Criminal", default_visibility=DistinctionVisibility.PRIVATE
            ),
        )
        assert self._distinction_names(self._get(sheet, owner).data) == {"Wanted Criminal"}

    def test_player_privacy_gate_overrides_a_public_default(self) -> None:
        # The per-character gate: a player hides an otherwise-public distinction. The override
        # wins over the kind default, so a non-owner no longer sees it.
        sheet = self._character_sheet(AccountFactory(), fake_active=False)
        CharacterDistinctionFactory(
            character=sheet.character,
            distinction=DistinctionFactory(
                name="Secret Affair", default_visibility=DistinctionVisibility.PUBLIC
            ),
            visibility_override=DistinctionVisibility.PRIVATE,
        )
        viewer = AccountFactory()
        self._character_sheet(viewer)

        assert self._distinction_names(self._get(sheet, viewer).data) == set()
