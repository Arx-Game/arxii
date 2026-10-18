"""Per-viewer persona display resolution (#1109): sdesc, discovery reveal, self-ownership."""

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerData
from world.character_sheets.models import Gender
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.roster.services.selection import set_selected_entry
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


def _played_character(account, *, gender_key="male", selected=True):
    """A character the account plays and, by default, is on (its durable selection).

    The reveal rule's viewer is the selected character (#4413), the way login and ``@ic``
    leave it; ``selected=False`` adds a second character the account is not on.
    """
    roster_entry = RosterEntryFactory()
    player_data, _ = PlayerData.objects.get_or_create(account=account)
    RosterTenureFactory(player_data=player_data, roster_entry=roster_entry)
    sheet = roster_entry.character_sheet
    sheet.gender = _gender(gender_key)
    sheet.save(update_fields=["gender"])
    if selected:
        set_selected_entry(player_data, roster_entry)
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
            f"stag mask ({sheet.primary_persona.name})"
        )

    def test_a_discovery_belongs_to_the_character_who_made_it_not_the_account(self) -> None:
        """On Hobb, a player meets the stranger Maud unmasked (#4413): the reveal is the
        active character's, a reminder that Hobb does not know."""
        owner = AccountFactory()
        sheet = _played_character(owner).character_sheet
        mask = PersonaFactory(character_sheet=sheet, is_fake_name=True, name="stag mask")
        pose = self._public_pose_by(mask)

        player = AccountFactory()
        _played_character(player)  # Hobb, the one the player is on
        maud = _played_character(player, selected=False)
        PersonaDiscoveryFactory(
            persona=mask, linked_to=sheet.primary_persona, discovered_by=maud.character_sheet
        )

        self.client.force_authenticate(user=player)
        response = self.client.get(reverse("interaction-list"))
        assert self._persona_name(response, pose.pk) == "a man wearing a stag mask"

        set_selected_entry(PlayerData.objects.get(account=player), maud)
        response = self.client.get(reverse("interaction-list"))
        assert self._persona_name(response, pose.pk) == f"stag mask ({sheet.primary_persona.name})"

    def test_your_other_character_s_face_is_a_stranger_s_while_you_play_this_one(self) -> None:
        player = AccountFactory()
        _played_character(player)  # Hobb, the one the player is on
        maud = _played_character(player, selected=False, gender_key="female")
        mask = PersonaFactory(
            character_sheet=maud.character_sheet, is_fake_name=True, name="stag mask"
        )
        pose = self._public_pose_by(mask)

        self.client.force_authenticate(user=player)
        response = self.client.get(reverse("interaction-list"))
        assert self._persona_name(response, pose.pk) == "a woman wearing a stag mask"

        set_selected_entry(PlayerData.objects.get(account=player), maud)
        response = self.client.get(reverse("interaction-list"))
        assert self._persona_name(response, pose.pk) == "stag mask"

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
        # Table name derived (not hardcoded): a stale string here would go
        # silently vacuous (never matching any real table) rather than catching
        # a per-row N+1 — see #2906.
        gender_table = Gender._meta.db_table.lower()
        gender_queries = [s for s in sql if gender_table in s]
        # One discovery query for all 8 masks; gender comes via select_related — neither grows
        # per anonymous persona (8 masks must not mean 8 of either).
        assert len(discovery_queries) <= 1, f"discovery not batched: {len(discovery_queries)}"
        assert len(gender_queries) <= 1, f"gender resolved per-row (N+1): {len(gender_queries)}"


class SightThroughAMaskTests(TestCase):
    """A ``disguise_sight`` lever on a kind reveals a disguise of that kind, no contest (#4396)."""

    @classmethod
    def setUpTestData(cls):
        from world.forms.factories import CharacterFormFactory
        from world.forms.models import FormType
        from world.mechanics.constants import DISGUISE_SIGHT_CATEGORY_NAME
        from world.mechanics.test_helpers import grant_lever
        from world.scenes.services import create_mask

        cls.owner_entry = _played_character(AccountFactory(), gender_key="female")
        cls.sheet = cls.owner_entry.character_sheet
        cls.primary = cls.sheet.primary_persona
        cls.bare_mask = PersonaFactory(
            character_sheet=cls.sheet, is_fake_name=True, name="stag mask"
        )
        cls.named_alt = PersonaFactory(character_sheet=cls.sheet, is_fake_name=False, name="Maud")
        glamour_form = CharacterFormFactory(character=cls.sheet, form_type=FormType.DISGUISE)
        cls.glamour = create_mask(
            cls.sheet, name="glamour", disguise_form=glamour_form, disguise_kind="magical"
        )

        cls.keen = _played_character(AccountFactory()).character_sheet
        grant_lever(cls.keen, DISGUISE_SIGHT_CATEGORY_NAME, "mundane", 1)
        cls.warded = _played_character(AccountFactory()).character_sheet
        grant_lever(cls.warded, DISGUISE_SIGHT_CATEGORY_NAME, "magical", 1)
        cls.plain = _played_character(AccountFactory()).character_sheet

    def _seen_by(self, persona, viewer_sheet):
        from world.scenes.persona_display import resolve_display_for_viewer

        return resolve_display_for_viewer(persona, viewer_sheet=viewer_sheet)

    def _revealed_to(self, persona, viewer_sheet):
        from world.scenes.persona_display import identity_revealed_to_viewer

        return identity_revealed_to_viewer(persona, viewer_sheet=viewer_sheet)

    def test_a_bare_fake_name_is_a_mundane_disguise_and_keen_eyes_read_it(self) -> None:
        assert self._seen_by(self.bare_mask, self.keen) == (
            f"stag mask ({self.primary.name})",
            True,
        )
        assert self._revealed_to(self.bare_mask, self.keen) is True
        assert self._seen_by(self.bare_mask, self.plain) == ("a woman wearing a stag mask", False)
        assert self._revealed_to(self.bare_mask, self.plain) is False

    def test_sight_on_one_kind_leaves_the_other_kind_a_stranger(self) -> None:
        # The glamour is the worn face over a MAGICAL overlay: mundane sight is no help.
        assert self._seen_by(self.glamour, self.keen) == ("a woman wearing a glamour", False)
        assert self._seen_by(self.glamour, self.warded) == (
            f"glamour ({self.primary.name})",
            True,
        )
        # And warded eyes do not read a plain false name.
        assert self._seen_by(self.bare_mask, self.warded) == ("a woman wearing a stag mask", False)

    def test_a_named_alt_is_not_a_disguise_sight_can_pierce(self) -> None:
        for viewer in (self.keen, self.warded):
            assert self._seen_by(self.named_alt, viewer) == ("Maud", False)
            assert self._revealed_to(self.named_alt, viewer) is False

    def test_the_page_map_reads_sight_once_and_marks_the_reveal_allowed(self) -> None:
        from world.scenes.persona_display import build_persona_display_map

        with CaptureQueriesContext(connection) as ctx:
            resolved = build_persona_display_map(
                [self.bare_mask, self.glamour, self.named_alt], viewer_sheet=self.keen
            )
        assert resolved[self.bare_mask.pk] == (f"stag mask ({self.primary.name})", True, True)
        assert resolved[self.glamour.pk] == ("a woman wearing a glamour", False, False)
        assert resolved[self.named_alt.pk] == ("Maud", False, True)
        sql = [q["sql"].lower() for q in ctx.captured_queries]
        sheet_loads = [s for s in sql if "arxii_charactersheet" in s and "where" in s]
        assert len(sheet_loads) <= 1, f"sight read per persona, not per page: {len(sheet_loads)}"

    def test_without_the_targets_authored_nothing_is_pierced(self) -> None:
        # The rows are content: a database where staff never authored the category reads
        # every sight as 0, whatever modifiers a character carries.
        from unittest.mock import patch

        with patch("world.mechanics.constants.DISGUISE_SIGHT_CATEGORY_NAME", "not_authored"):
            seen = self._seen_by(self.bare_mask, self.keen)
        assert seen == ("a woman wearing a stag mask", False)
