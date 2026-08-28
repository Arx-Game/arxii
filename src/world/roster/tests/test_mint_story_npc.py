"""GM story-NPC on-ramp service tests (#3426) — mint_story_npc + check_story_npc_cap."""

from __future__ import annotations

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, seed_default_gm_level_caps
from world.roster.models import RosterTenure
from world.roster.services.staff_characters import StaffMintError, mint_story_npc


class MintStoryNpcServiceTests(TestCase):
    def test_junior_gm_can_mint_and_gets_a_tenure(self) -> None:
        account = AccountFactory(username="junior_gm")
        GMProfileFactory(account=account, level=GMLevel.JUNIOR)
        seed_default_gm_level_caps()

        character = mint_story_npc(
            gm_account=account, name="Master Aldous", description="A grim watchman."
        )

        assert character.db_key == "Master Aldous"
        sheet = character.sheet_data
        assert sheet.additional_desc == "A grim watchman."
        tenure = RosterTenure.objects.get(roster_entry__character_sheet=sheet)
        assert tenure.player_data.account_id == account.pk
        assert tenure.end_date is None

    def test_mint_without_description_leaves_desc_untouched(self) -> None:
        account = AccountFactory(username="junior_gm_no_desc")
        GMProfileFactory(account=account, level=GMLevel.JUNIOR)
        seed_default_gm_level_caps()

        character = mint_story_npc(gm_account=account, name="Nameless Guard")

        assert character.sheet_data.additional_desc == ""

    def test_starting_gm_refused(self) -> None:
        account = AccountFactory(username="starting_gm")
        GMProfileFactory(account=account, level=GMLevel.STARTING)
        seed_default_gm_level_caps()

        with self.assertRaises(StaffMintError) as caught:
            mint_story_npc(gm_account=account, name="Too Junior")
        assert "Junior GM" in caught.exception.user_message

    def test_no_gm_profile_refused(self) -> None:
        account = AccountFactory(username="no_gm_profile")
        seed_default_gm_level_caps()

        with self.assertRaises(StaffMintError) as caught:
            mint_story_npc(gm_account=account, name="Nobody's NPC")
        assert "GM trust required" in caught.exception.user_message

    def test_staff_bypasses_trust_and_cap(self) -> None:
        account = AccountFactory(username="staffer", is_staff=True)
        # Deliberately no GMProfile and no seeded caps -- staff bypass must
        # short-circuit both checks entirely.
        character = mint_story_npc(gm_account=account, name="Staff-Minted NPC")
        assert character.db_key == "Staff-Minted NPC"

    def test_cap_enforced_then_refused(self) -> None:
        account = AccountFactory(username="capped_gm")
        GMProfileFactory(account=account, level=GMLevel.JUNIOR)
        seed_default_gm_level_caps()

        mint_story_npc(gm_account=account, name="First NPC")
        mint_story_npc(gm_account=account, name="Second NPC")

        with self.assertRaises(StaffMintError) as caught:
            mint_story_npc(gm_account=account, name="Third NPC")
        assert "2 story NPC" in caught.exception.user_message

    def test_no_cap_row_refuses_everything(self) -> None:
        """Most-restrictive default: no GMLevelCap row configured means 0, refuse."""
        account = AccountFactory(username="uncapped_gm")
        GMProfileFactory(account=account, level=GMLevel.JUNIOR)
        # Deliberately skip seed_default_gm_level_caps().

        with self.assertRaises(StaffMintError):
            mint_story_npc(gm_account=account, name="No Cap Row")

    def test_ended_tenure_does_not_count_against_cap(self) -> None:
        account = AccountFactory(username="turnover_gm")
        GMProfileFactory(account=account, level=GMLevel.JUNIOR)
        seed_default_gm_level_caps()

        mint_story_npc(gm_account=account, name="Retired NPC")
        mint_story_npc(gm_account=account, name="Active NPC 1")

        # End the first NPC's tenure -- it should free a cap slot.
        RosterTenure.objects.filter(
            roster_entry__character_sheet__character__db_key="Retired NPC"
        ).update(end_date=timezone.now())

        # This would raise if the ended tenure still counted (cap is 2 at JUNIOR).
        mint_story_npc(gm_account=account, name="Active NPC 2")
