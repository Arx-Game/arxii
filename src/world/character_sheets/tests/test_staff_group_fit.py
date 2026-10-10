"""Staff edit mode, piece E: group fit on any sheet (#4229, #3988)."""

from __future__ import annotations

from unittest import mock

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.achievements.constants import RewardType
from world.achievements.factories import RewardDefinitionFactory
from world.achievements.models import PersonaTitle
from world.character_creation.sheet_writers import SheetWriteError
from world.character_sheets.group_writer import (
    assign_role,
    bond_mentor,
    change_membership,
    change_tie_label,
    create_established_persona,
    declare_tie_label,
    grant_persona_title,
    remove_persona,
    rename_persona,
    seat_noble_title,
    set_guise_prose,
    set_tie_state,
    tie_side,
)
from world.character_sheets.models import ProfileTextVersion
from world.character_sheets.types import StaffTieDirection
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.covenants.factories import (
    CovenantFactory,
    CovenantRankFactory,
    CovenantRoleFactory,
    seed_mentor_bond_defaults,
)
from world.covenants.mentorship import mentor_band_problem
from world.covenants.models import CharacterCovenantRole, MentorBond, MentorBondConfig
from world.narrative.models import NarrativeMessage
from world.relationships.constants import LabelAwareness, TypeValence
from world.relationships.factories import RelationshipTierFactory, RelationshipTypeFactory
from world.relationships.models import RelationshipLabel
from world.relationships.services import is_mutual, mutual_hostile
from world.roster.factories import (
    KinspersonFactory,
    PlayerDataFactory,
    RosterApplicationFactory,
    RosterEntryFactory,
    RosterTenureFactory,
)
from world.roster.models import RosterType
from world.scenes.constants import PersonaType
from world.scenes.factories import InteractionFactory
from world.scenes.models import Persona


def _level(sheet, level: int) -> None:
    CharacterClassLevelFactory(
        character=sheet, character_class=CharacterClassFactory(), level=level, is_primary=True
    )


class PersonaWriterTests(TestCase):
    """Staff give a character faces, name them, write their cover bios, remove them."""

    def setUp(self) -> None:
        self.sheet = RosterEntryFactory().character_sheet
        self.staff = AccountFactory(is_staff=True)

    @override_settings(MAX_ESTABLISHED_PERSONAS_PER_SHEET=0)
    def test_staff_are_not_held_to_the_cap(self) -> None:
        face = create_established_persona(self.sheet, "The Grey Lady")
        assert face.persona_type == PersonaType.ESTABLISHED

    def test_the_character_s_own_face_is_renamed_elsewhere(self) -> None:
        with self.assertRaises(SheetWriteError):
            rename_persona(self.sheet.primary_persona, "Someone Else")

    def test_a_guise_bio_is_versioned_and_an_unchanged_field_writes_none(self) -> None:
        face = create_established_persona(self.sheet, "The Grey Lady")
        set_guise_prose(face, edited_by=self.staff, prose={"concept": "A widow in grey"})
        set_guise_prose(face, edited_by=self.staff, prose={"concept": "A widow in grey"})
        versions = ProfileTextVersion.objects.filter(profile=face.profile, field="concept")
        assert list(versions.values_list("text", "edited_by")) == [
            ("A widow in grey", self.staff.pk)
        ]

    def test_removing_the_worn_face_puts_the_character_back_in_their_own(self) -> None:
        from world.scenes.services import set_active_persona

        face = create_established_persona(self.sheet, "The Grey Lady")
        set_active_persona(self.sheet, face)
        remove_persona(face)
        assert not Persona.objects.filter(pk=face.pk).exists()
        assert self.sheet.active_persona_id == self.sheet.primary_persona.pk

    def test_a_face_with_history_stays(self) -> None:
        face = create_established_persona(self.sheet, "The Grey Lady")
        InteractionFactory(persona=face)
        with self.assertRaises(SheetWriteError):
            remove_persona(face)
        assert Persona.objects.filter(pk=face.pk).exists()


class TitleWriterTests(TestCase):
    def setUp(self) -> None:
        self.sheet = RosterEntryFactory().character_sheet
        self.face = self.sheet.primary_persona

    def test_a_title_reward_is_granted_once_and_another_reward_is_refused(self) -> None:
        reward = RewardDefinitionFactory(reward_type=RewardType.TITLE, name="Warden of Lamps")
        grant_persona_title(self.face, reward=reward)
        grant_persona_title(self.face, reward=reward)
        assert PersonaTitle.objects.filter(persona=self.face).count() == 1
        bonus = RewardDefinitionFactory(reward_type=RewardType.BONUS)
        with self.assertRaises(SheetWriteError):
            grant_persona_title(self.face, reward=bonus)

    def test_a_deed_titles_only_the_face_that_did_it(self) -> None:
        from world.societies.factories import LegendEntryFactory

        other_face = create_established_persona(self.sheet, "The Grey Lady")
        deed = LegendEntryFactory(persona=other_face, title="The Burning of the Mill")
        with self.assertRaises(SheetWriteError):
            grant_persona_title(self.face, legend_entry=deed)
        title = grant_persona_title(other_face, legend_entry=deed)
        assert title.display_name == "The Burning of the Mill"

    def test_a_noble_title_needs_a_place_in_the_family_tree(self) -> None:
        from world.character_creation.factories import RealmFactory
        from world.societies.houses.constants import TitleTier
        from world.societies.houses.models import Title

        title = Title.objects.create(
            name="Lady of Ashford", tier=TitleTier.BARONY, realm=RealmFactory()
        )
        with self.assertRaises(SheetWriteError):
            seat_noble_title(self.sheet, title)
        node = KinspersonFactory(sheet=self.sheet)
        assert seat_noble_title(self.sheet, title).holder_id == node.pk


class TieWriterTests(TestCase):
    """Labels are live by staff ruling; on a character nobody plays, from pickup."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.roster.seeds import ensure_rosters

        ensure_rosters()
        cls.rival = RelationshipTypeFactory(name="Rival", valence=TypeValence.HOSTILE)
        cls.staff_data = PlayerDataFactory(account=AccountFactory(is_staff=True))

    def setUp(self) -> None:
        from world.roster.models import Roster

        self.unpicked = RosterEntryFactory(
            roster=Roster.objects.get(roster_type=RosterType.AVAILABLE)
        ).character_sheet
        played = RosterEntryFactory()
        RosterTenureFactory(roster_entry=played, player_data=PlayerDataFactory())
        self.played = played.character_sheet

    def _rival_both_ways(self) -> None:
        for direction in (StaffTieDirection.TOWARD, StaffTieDirection.FROM):
            side = tie_side(self.unpicked, self.played, direction)
            declare_tie_label(side, self.rival, LabelAwareness.CLANDESTINE)

    def test_an_unpicked_character_s_label_is_inert_until_pickup_then_mutual(self) -> None:
        self._rival_both_ways()
        assert not mutual_hostile(self.unpicked, self.played)

        application = RosterApplicationFactory(character=self.unpicked)
        tenure = application.approve(self.staff_data)

        label = RelationshipLabel.objects.get(relationship__source=self.unpicked)
        assert label.declared_by_tenure_id == tenure.pk
        assert mutual_hostile(self.unpicked, self.played)

    def test_a_played_character_s_label_counts_at_once(self) -> None:
        side = tie_side(self.unpicked, self.played, StaffTieDirection.FROM)
        label = declare_tie_label(side, self.rival, LabelAwareness.CLANDESTINE)
        assert label.declared_by_tenure_id == self.played.roster_entry.current_tenure.pk
        assert label.staff_seeded

    def test_a_shift_keeps_the_label_waiting(self) -> None:
        side = tie_side(self.unpicked, self.played, StaffTieDirection.TOWARD)
        label = declare_tie_label(side, self.rival, LabelAwareness.PRIVATE)
        friend = RelationshipTypeFactory(name="Friend", valence=TypeValence.WARM)
        shifted = change_tie_label(label, new_type=friend, awareness=LabelAwareness.PUBLIC)
        assert shifted.staff_seeded
        assert shifted.declared_by_tenure_id is None
        assert shifted.awareness == LabelAwareness.PUBLIC
        assert is_mutual(side, friend) is False

    def test_staff_set_a_tier_without_xp_or_a_capstone(self) -> None:
        RelationshipTierFactory(tier_number=2)
        side = tie_side(self.unpicked, self.played, StaffTieDirection.TOWARD)
        set_tie_state(side, summary="Old enemies.", tier=2)
        side.refresh_from_db()
        assert (side.tier, side.summary) == (2, "Old enemies.")
        assert not side.capstones.exists()
        with self.assertRaises(SheetWriteError):
            set_tie_state(side, tier=9)


class CovenantAndMentorWriterTests(TestCase):
    def setUp(self) -> None:
        seed_mentor_bond_defaults()
        self.covenant = CovenantFactory(level=4)  # band [2, 6]
        self.role = CovenantRoleFactory(covenant_type=self.covenant.covenant_type)
        self.sheet = RosterEntryFactory().character_sheet
        _level(self.sheet, 1)  # out of band

    def test_staff_assignment_skips_the_band_gate_and_the_sworn_act(self) -> None:
        with mock.patch(
            "world.missions.services.external_acts.notify_external_act"
        ) as external_act:
            row = assign_role(self.sheet, self.covenant, self.role)
        external_act.assert_not_called()
        assert row.sworn_as_id == self.sheet.primary_persona.pk
        with self.assertRaises(SheetWriteError):
            assign_role(self.sheet, self.covenant, self.role)

    def test_a_membership_takes_one_change_at_a_time(self) -> None:
        row = assign_role(self.sheet, self.covenant, self.role)
        rank = CovenantRankFactory(covenant=self.covenant, tier=2)
        with self.assertRaises(SheetWriteError):
            change_membership(row, rank=rank, end=True)
        change_membership(row, rank=rank)
        assert CharacterCovenantRole.objects.get(pk=row.pk).rank_id == rank.pk
        change_membership(row, end=True)
        assert CharacterCovenantRole.objects.get(pk=row.pk).left_at is not None

    def test_a_band_violation_warns_staff_and_the_cap_still_holds(self) -> None:
        mentor = RosterEntryFactory().character_sheet
        _level(mentor, 1)  # both outside the band
        bond = bond_mentor(self.covenant, mentor=mentor, sidekick=self.sheet)
        assert bond.pk
        assert mentor_band_problem(
            covenant=self.covenant, mentor_sheet=mentor, sidekick_sheet=self.sheet
        )
        config = MentorBondConfig.objects.get(pk=1)
        config.max_sidekicks_per_mentor = 1
        config.save()
        other = RosterEntryFactory().character_sheet
        _level(other, 4)
        with self.assertRaises(SheetWriteError):
            bond_mentor(self.covenant, mentor=mentor, sidekick=other)
        assert MentorBond.objects.filter(mentor_sheet=mentor).count() == 1


class StaffWritesSendNothingTests(TestCase):
    """No group-fit write announces itself to anyone (#3988)."""

    def test_no_message_is_sent(self) -> None:
        seed_mentor_bond_defaults()
        covenant = CovenantFactory(level=4)
        sheet = RosterEntryFactory().character_sheet
        other = RosterEntryFactory().character_sheet
        _level(sheet, 1)
        _level(other, 4)
        staff = AccountFactory(is_staff=True)
        before = NarrativeMessage.objects.count()

        face = create_established_persona(sheet, "The Grey Lady")
        set_guise_prose(face, edited_by=staff, prose={"quote": "Hush."})
        grant_persona_title(
            face, reward=RewardDefinitionFactory(reward_type=RewardType.TITLE, name="Hushed")
        )
        side = tie_side(sheet, other, StaffTieDirection.TOWARD)
        declare_tie_label(side, RelationshipTypeFactory(), LabelAwareness.PUBLIC)
        assign_role(sheet, covenant, CovenantRoleFactory(covenant_type=covenant.covenant_type))
        bond_mentor(covenant, mentor=other, sidekick=sheet)

        assert NarrativeMessage.objects.count() == before


class GroupFitApiTests(TestCase):
    """The actions are staff-only, refuse another character's rows, and answer the sheet."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(is_staff=True)
        cls.player = PlayerDataFactory()

    def setUp(self) -> None:
        self.entry = RosterEntryFactory()
        RosterTenureFactory(player_data=self.player, roster_entry=self.entry, player_number=1)
        self.sheet = self.entry.character_sheet
        self.base = f"/api/character-sheets/{self.sheet.pk}"
        self.client = APIClient()
        self.client.force_authenticate(user=self.staff)

    def test_a_face_and_a_tie_show_in_the_staff_rows(self) -> None:
        other = RosterEntryFactory().character_sheet
        friend = RelationshipTypeFactory(name="Confidant")
        response = self.client.post(
            f"{self.base}/staff-personas/", {"name": "The Grey Lady"}, format="json"
        )
        assert response.status_code == 200, response.content[:800]
        response = self.client.post(
            f"{self.base}/staff-tie-labels/",
            {
                "other": other.pk,
                "direction": StaffTieDirection.TOWARD,
                "type": friend.pk,
                "awareness": LabelAwareness.PRIVATE,
            },
            format="json",
        )
        assert response.status_code == 200, response.content[:800]
        rows = response.data["staff_edit"]["rows"]
        assert [p["name"] for p in rows["personas"]] == ["The Grey Lady"]
        (tie,) = rows["ties"]
        assert tie["other"] == other.pk
        assert tie["other_name"] == other.primary_persona.name
        assert [label["name"] for label in tie["toward"]["labels"]] == ["Confidant"]
        assert tie["back"] is None

    def test_another_character_s_face_is_refused(self) -> None:
        stranger = RosterEntryFactory().character_sheet
        response = self.client.patch(
            f"{self.base}/staff-persona/",
            {"persona": stranger.primary_persona.pk, "name": "Taken"},
            format="json",
        )
        assert response.status_code == 400

    def test_a_bond_outside_the_band_carries_its_warning_in_the_rows(self) -> None:
        seed_mentor_bond_defaults()
        covenant = CovenantFactory(level=4)
        other = RosterEntryFactory().character_sheet
        response = self.client.post(
            f"{self.base}/staff-mentor-bonds/",
            {"covenant": covenant.pk, "other": other.pk, "as_mentor": True},
            format="json",
        )
        assert response.status_code == 200, response.content[:800]
        (bond,) = response.data["staff_edit"]["rows"]["mentor_bonds"]
        assert bond["as_mentor"] is True
        assert bond["warning"]

    def test_characters_are_searched_never_listed(self) -> None:
        other = RosterEntryFactory().character_sheet
        name = other.primary_persona.name
        options = self.client.get(f"{self.base}/staff-group-options/", {"character": name})
        assert options.status_code == 200, options.content[:800]
        assert {"id": other.pk, "name": name} in options.data["characters"]
        assert self.client.get(f"{self.base}/staff-group-options/").data["characters"] == []

    def test_the_player_cannot_use_the_group_actions(self) -> None:
        self.client.force_authenticate(user=self.player.account)
        for method, path in (
            ("post", "staff-personas"),
            ("patch", "staff-persona"),
            ("post", "staff-persona-remove"),
            ("post", "staff-titles"),
            ("post", "staff-title-remove"),
            ("post", "staff-noble-title"),
            ("post", "staff-tie-labels"),
            ("patch", "staff-tie-label"),
            ("patch", "staff-tie"),
            ("post", "staff-covenant-roles"),
            ("patch", "staff-covenant-role"),
            ("post", "staff-mentor-bonds"),
            ("post", "staff-mentor-bond-end"),
            ("get", "staff-group-options"),
        ):
            response = getattr(self.client, method)(f"{self.base}/{path}/", {}, format="json")
            assert response.status_code in {403, 404}, (path, response.status_code)
