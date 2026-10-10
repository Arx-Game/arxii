"""Staff edit mode on the character sheet, piece A: prose, identity, history (#3988)."""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import (
    CharacterSheetFactory,
    GenderFactory,
    PronounsFactory,
)
from world.character_sheets.models import ProfileTextVersion
from world.character_sheets.services import (
    ensure_true_profile,
    rename_character,
    restore_profile_text_version,
    set_physical_description,
    staff_edit_sheet,
    update_profile_text,
)
from world.character_sheets.types import ProfileTextField
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory


class VersionedProseTests(TestCase):
    """Every prose field keeps its history, the description included."""

    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.profile = self.sheet.true_profile

    def test_each_new_field_captures_the_original_on_first_write(self) -> None:
        for field in ("concept", "real_concept", "quote", "obituary"):
            setattr(self.profile, field, f"original {field}")
            self.profile.save(update_fields=[field])
            update_profile_text(self.profile, field, f"rewritten {field}")
            texts = list(
                ProfileTextVersion.objects.filter(profile=self.profile, field=field)
                .order_by("created_at")
                .values_list("text", flat=True)
            )
            assert texts == [f"original {field}", f"rewritten {field}"], field
            assert getattr(self.profile, field) == f"rewritten {field}"

    def test_the_description_routes_through_the_versioned_write(self) -> None:
        self.sheet.additional_desc = "Tall, with a scar."
        self.sheet.save(update_fields=["additional_desc"])

        set_physical_description(self.sheet, "Tall, the scar long faded.")

        self.sheet.refresh_from_db()
        assert self.sheet.additional_desc == "Tall, the scar long faded."
        texts = list(
            ProfileTextVersion.objects.filter(
                profile=self.profile, field=ProfileTextField.DESCRIPTION
            )
            .order_by("created_at")
            .values_list("text", flat=True)
        )
        assert texts == ["Tall, with a scar.", "Tall, the scar long faded."]

    def test_blanking_a_field_keeps_the_earlier_text(self) -> None:
        self.profile.quote = ""
        self.profile.save(update_fields=["quote"])
        update_profile_text(self.profile, ProfileTextField.QUOTE, "Arx endures.")
        update_profile_text(self.profile, ProfileTextField.QUOTE, "")
        texts = set(
            ProfileTextVersion.objects.filter(
                profile=self.profile, field=ProfileTextField.QUOTE
            ).values_list("text", flat=True)
        )
        assert texts == {"Arx endures.", ""}

    def test_a_restore_adds_a_version_and_deletes_nothing(self) -> None:
        self.profile.background = ""
        self.profile.save(update_fields=["background"])
        first = update_profile_text(self.profile, ProfileTextField.BACKGROUND, "First.")
        update_profile_text(self.profile, ProfileTextField.BACKGROUND, "Second.")
        staff = AccountFactory(is_staff=True)

        restore_profile_text_version(first, edited_by=staff)

        assert self.profile.background == "First."
        rows = ProfileTextVersion.objects.filter(
            profile=self.profile, field=ProfileTextField.BACKGROUND
        )
        assert rows.count() == 3
        assert rows.order_by("-created_at").first().edited_by == staff

    def test_a_sheet_with_no_profile_gets_one(self) -> None:
        sheet = CharacterSheetFactory(primary_persona=False)
        sheet.true_profile = None
        sheet.save(update_fields=["true_profile"])
        profile = ensure_true_profile(sheet)
        assert sheet.true_profile_id == profile.pk


class RenameTests(TestCase):
    def test_the_key_and_the_primary_persona_move_together(self) -> None:
        sheet = CharacterSheetFactory()
        rename_character(sheet, "  Sharlotte  ")
        sheet.character.refresh_from_db()
        assert sheet.character.db_key == "Sharlotte"
        assert sheet.primary_persona.name == "Sharlotte"


class StaffEditServiceTests(TestCase):
    def test_choosing_a_pronoun_set_copies_its_forms_onto_the_sheet(self) -> None:
        sheet = CharacterSheetFactory()
        pronouns = PronounsFactory(subject="she", object="her", possessive="her")
        staff = AccountFactory(is_staff=True)

        staff_edit_sheet(sheet, {"pronouns": pronouns, "vocation": "Smith"}, edited_by=staff)

        sheet.refresh_from_db()
        assert (sheet.pronoun_subject, sheet.pronoun_object, sheet.pronoun_possessive) == (
            "she",
            "her",
            "her",
        )
        assert sheet.vocation == "Smith"


class StaffEditEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(is_staff=True)
        cls.player = PlayerDataFactory()
        cls.entry = RosterEntryFactory()
        RosterTenureFactory(player_data=cls.player, roster_entry=cls.entry, player_number=1)
        cls.sheet = cls.entry.character_sheet
        cls.url = f"/api/character-sheets/{cls.sheet.pk}/staff-edit/"

    def setUp(self) -> None:
        self.client = APIClient()

    def test_staff_edit_saves_prose_and_identity_and_answers_with_the_sheet(self) -> None:
        gender = GenderFactory()
        self.client.force_authenticate(user=self.staff)
        response = self.client.patch(
            self.url,
            {"background": "Raised by wolves.", "gender": gender.pk, "social_rank": 4},
            format="json",
        )
        assert response.status_code == 200, response.content[:800]
        assert response.data["staff_edit"]["prose"]["background"] == "Raised by wolves."
        assert response.data["staff_edit"]["gender"] == gender.pk
        assert response.data["staff_edit"]["social_rank"] == 4
        version = ProfileTextVersion.objects.get(
            profile=self.sheet.true_profile, field="background", text="Raised by wolves."
        )
        assert version.edited_by == self.staff

    def test_the_owner_cannot_staff_edit(self) -> None:
        self.client.force_authenticate(user=self.player.account)
        response = self.client.patch(self.url, {"background": "Mine."}, format="json")
        assert response.status_code == 404

    def test_the_payload_carries_staff_edit_fields_for_staff_only(self) -> None:
        detail = f"/api/character-sheets/{self.sheet.pk}/"
        self.client.force_authenticate(user=self.player.account)
        assert self.client.get(detail).data["staff_edit"] is None
        self.client.force_authenticate(user=self.staff)
        assert self.client.get(detail).data["staff_edit"]["name"] == self.sheet.character.db_key

    def test_unknown_fields_and_bad_choices_are_refused(self) -> None:
        self.client.force_authenticate(user=self.staff)
        response = self.client.patch(self.url, {"rollmod": 5}, format="json")
        assert response.status_code == 400
        assert "rollmod" in response.data
        response = self.client.patch(self.url, {"gender": 999999}, format="json")
        assert response.status_code == 400
        assert "gender" in response.data

    def test_restore_is_staff_only_and_adds_a_version(self) -> None:
        profile = self.sheet.true_profile
        profile.fear = ""
        profile.save(update_fields=["fear"])
        first = update_profile_text(profile, ProfileTextField.FEAR, "Fire.")
        update_profile_text(profile, ProfileTextField.FEAR, "Water.")
        restore = f"/api/character-sheets/{self.sheet.pk}/profile-text-versions/{first.pk}/restore/"

        self.client.force_authenticate(user=self.player.account)
        assert self.client.post(restore).status_code == 404

        self.client.force_authenticate(user=self.staff)
        response = self.client.post(restore)
        assert response.status_code == 200, response.content[:800]
        assert response.data["staff_edit"]["prose"]["fear"] == "Fire."
        assert ProfileTextVersion.objects.filter(profile=profile, field="fear").count() == 3


class TenureScopedHistoryTests(TestCase):
    """A new roster tenant never reads the previous player's prose (#3988)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.entry = RosterEntryFactory()
        cls.sheet = cls.entry.character_sheet
        cls.first = PlayerDataFactory()
        now = timezone.now()
        RosterTenureFactory(
            player_data=cls.first,
            roster_entry=cls.entry,
            player_number=1,
            start_date=now - timedelta(days=30),
            end_date=now - timedelta(days=1),
        )
        cls.sheet.true_profile.background = ""
        cls.sheet.true_profile.save(update_fields=["background"])
        cls.old = update_profile_text(cls.sheet.true_profile, "background", "Tenant A's past.")
        ProfileTextVersion.objects.filter(pk=cls.old.pk).update_with_reason(
            reason="backdate a version into the previous tenure for the test",
            created_at=now - timedelta(days=10),
        )
        cls.second = PlayerDataFactory()
        RosterTenureFactory(
            player_data=cls.second,
            roster_entry=cls.entry,
            player_number=2,
            start_date=now - timedelta(hours=1),
        )
        cls.new = update_profile_text(cls.sheet.true_profile, "background", "Tenant B's past.")
        cls.url = f"/api/character-sheets/{cls.sheet.pk}/profile-text-versions/"

    def setUp(self) -> None:
        self.client = APIClient()

    def test_the_current_tenant_sees_only_their_own_era(self) -> None:
        self.client.force_authenticate(user=self.second.account)
        texts = [row["text"] for row in self.client.get(self.url).data]
        assert texts == ["Tenant B's past."]

    def test_staff_see_everything(self) -> None:
        self.client.force_authenticate(user=AccountFactory(is_staff=True))
        texts = {row["text"] for row in self.client.get(self.url).data}
        assert texts == {"Tenant A's past.", "Tenant B's past."}


class HeritageListTests(TestCase):
    def test_lists_every_heritage_by_name(self) -> None:
        from world.character_sheets.models import Heritage

        Heritage.objects.get_or_create(name="Sleeper")
        Heritage.objects.get_or_create(name="Misbegotten")
        client = APIClient()
        client.force_authenticate(user=AccountFactory(is_staff=True))
        response = client.get("/api/character-sheets/heritages/?name=sleep")
        assert response.status_code == 200, response.content[:400]
        assert [row["name"] for row in response.data] == ["Sleeper"]
