"""Tests for GMAwardDistinctionAction (#2037, #2628) — the JUNIOR-tier GM distinction award.

#2628 update: the action now goes through the SheetUpdateRequest framework
and charges XP on the sign-based model. Tests give the target an XP tracker
and mock the advancement gate.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.definitions.distinctions import GMAwardDistinctionAction
from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.distinctions.models import CharacterDistinction
from world.distinctions.types import DistinctionOrigin
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.narrative.models import NarrativeMessage
from world.progression.models.rewards import ExperiencePointsData
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


class GMAwardDistinctionActionTests(TestCase):
    def _gm_actor(self, level: str, *, db_key: str = "AwardDistinctionGM") -> object:
        actor = CharacterFactory(db_key=db_key)
        CharacterSheetFactory(character=actor)
        entry = RosterEntryFactory(character_sheet__character=actor)
        tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
        GMProfileFactory(account=tenure.player_data.account, level=level)
        return actor

    def _staff_actor(self, *, db_key: str = "AwardDistinctionStaff") -> object:
        account = AccountFactory(username=f"account_{db_key}", is_staff=True)
        actor = CharacterFactory(db_key=db_key)
        actor.db_account = account
        actor.save()
        return actor

    def setUp(self) -> None:
        self.target = CharacterFactory(db_key="AwardDistinctionTarget")
        self.target_sheet = CharacterSheetFactory(character=self.target)
        self.target_account = AccountFactory(username="award_target_acct")
        self.target.account = self.target_account
        self.target.save()
        ExperiencePointsData.objects.get_or_create(
            account=self.target_account,
            defaults={"total_earned": 100, "total_spent": 0},
        )
        self.distinction = DistinctionFactory(
            name="Silver Tongue", slug="silver-tongue", cost_per_rank=10, max_rank=3
        )
        self._patcher = patch("world.magic.services.alterations.enforce_advancement_gate")
        self._patcher.start()

    def tearDown(self) -> None:
        self._patcher.stop()

    def _run(self, actor, **kwargs):
        defaults = {
            "target_name": self.target.key,
            "distinction_slug": self.distinction.slug,
        }
        defaults.update(kwargs)
        with patch.object(actor, "search", return_value=self.target):
            return GMAwardDistinctionAction().run(actor, **defaults)

    def test_junior_gm_awards_distinction(self) -> None:
        actor = self._gm_actor(GMLevel.JUNIOR)
        result = self._run(actor)

        assert result.success is True
        cd = CharacterDistinction.objects.get(
            character=self.target.sheet_data, distinction=self.distinction
        )
        assert cd.rank == 1
        assert cd.origin == DistinctionOrigin.GM_AWARD
        # Narration fired: the grant seam creates a NarrativeMessage for the target.
        assert NarrativeMessage.objects.filter(
            deliveries__recipient_character_sheet=self.target_sheet
        ).exists()

    def test_starting_gm_below_junior_tier_is_blocked(self) -> None:
        actor = self._gm_actor(GMLevel.STARTING)
        result = self._run(actor)

        assert result.success is False
        assert "Junior GM" in result.message
        assert not CharacterDistinction.objects.filter(character=self.target.sheet_data).exists()

    def test_missing_gm_profile_is_blocked(self) -> None:
        actor = CharacterFactory(db_key="AwardDistinctionNoProfile")
        actor.db_account = AccountFactory(username="award_distinction_no_profile", is_staff=False)
        actor.save()
        result = self._run(actor)

        assert result.success is False
        assert result.message == "GM trust required."
        assert not CharacterDistinction.objects.filter(character=self.target.sheet_data).exists()

    def test_staff_bypass_without_gm_profile_awards(self) -> None:
        actor = self._staff_actor()
        result = self._run(actor)

        assert result.success is True
        assert CharacterDistinction.objects.filter(
            character=self.target.sheet_data, distinction=self.distinction
        ).exists()

    def test_slug_lookup_is_case_insensitive(self) -> None:
        actor = self._staff_actor(db_key="AwardDistinctionStaffCase")
        result = self._run(actor, distinction_slug="SILVER-Tongue")

        assert result.success is True

    def test_unknown_slug_fails_clearly(self) -> None:
        actor = self._staff_actor(db_key="AwardDistinctionStaffUnknown")
        result = self._run(actor, distinction_slug="no-such-distinction")

        assert result.success is False
        assert "No active distinction found" in result.message
        assert not CharacterDistinction.objects.filter(character=self.target.sheet_data).exists()

    def test_inactive_distinction_is_not_awardable(self) -> None:
        DistinctionFactory(name="Retired", slug="retired", is_active=False)
        actor = self._staff_actor(db_key="AwardDistinctionStaffInactive")
        result = self._run(actor, distinction_slug="retired")

        assert result.success is False
        assert "No active distinction found" in result.message

    def test_unknown_target_fails(self) -> None:
        actor = self._staff_actor(db_key="AwardDistinctionStaffNoTarget")
        with patch.object(actor, "search", return_value=None):
            result = GMAwardDistinctionAction().run(
                actor, target_name="Nobody", distinction_slug=self.distinction.slug
            )
        assert result.success is False

    def test_target_without_sheet_fails(self) -> None:
        no_sheet = CharacterFactory(db_key="AwardDistinctionNoSheet")
        actor = self._staff_actor(db_key="AwardDistinctionStaffNoSheet")
        with patch.object(actor, "search", return_value=no_sheet):
            result = GMAwardDistinctionAction().run(
                actor, target_name=no_sheet.key, distinction_slug=self.distinction.slug
            )
        assert result.success is False
        assert result.message == "That is not a character."

    def test_re_award_ranks_up(self) -> None:
        CharacterDistinctionFactory(
            character=self.target.sheet_data,
            distinction=self.distinction,
            rank=1,
            origin=DistinctionOrigin.CHARACTER_CREATION,
        )
        actor = self._staff_actor(db_key="AwardDistinctionStaffRankUp")
        result = self._run(actor)

        assert result.success is True
        cd = CharacterDistinction.objects.get(
            character=self.target.sheet_data, distinction=self.distinction
        )
        assert cd.rank == 2
        # Rank-up never rewrites the original acquisition origin (seam behavior,
        # ratified in the Task 1 tests).
        assert cd.origin == DistinctionOrigin.CHARACTER_CREATION

    def test_explicit_rank_validated_but_grant_advances_one_step(self) -> None:
        # #2628: the request framework calls grant_distinction with rank=None
        # (advance one step). An explicit rank is validated against max_rank
        # but the actual rank comes from grant_distinction's advance-one-step.
        actor = self._staff_actor(db_key="AwardDistinctionStaffRank3")
        result = self._run(actor, rank=3)

        assert result.success is True
        cd = CharacterDistinction.objects.get(
            character=self.target.sheet_data, distinction=self.distinction
        )
        # New grant at rank 1 (advance one step from nothing).
        assert cd.rank == 1

    def test_rank_below_one_is_rejected(self) -> None:
        actor = self._staff_actor(db_key="AwardDistinctionStaffRank0")
        result = self._run(actor, rank=0)

        assert result.success is False
        assert "positive whole number" in result.message
        assert not CharacterDistinction.objects.filter(character=self.target.sheet_data).exists()

    def test_garbage_rank_is_rejected(self) -> None:
        actor = self._staff_actor(db_key="AwardDistinctionStaffRankGarbage")
        result = self._run(actor, rank="lots")

        assert result.success is False
        assert "positive whole number" in result.message

    def test_rank_above_max_rank_is_rejected_naming_max(self) -> None:
        actor = self._staff_actor(db_key="AwardDistinctionStaffRank9")
        result = self._run(actor, rank=9)

        assert result.success is False
        assert "maximum rank of 3" in result.message
        assert not CharacterDistinction.objects.filter(character=self.target.sheet_data).exists()

    def test_exclusion_violation_surfaces_user_message(self) -> None:
        rival = DistinctionFactory(name="Rival Trait", slug="rival-trait")
        self.distinction.mutually_exclusive_with.add(rival)
        CharacterDistinctionFactory(character=self.target.sheet_data, distinction=rival, rank=1)

        actor = self._staff_actor(db_key="AwardDistinctionStaffExcl")
        result = self._run(actor)

        assert result.success is False
        assert "Mutually exclusive" in result.message
        assert not CharacterDistinction.objects.filter(
            character=self.target.sheet_data, distinction=self.distinction
        ).exists()

    def test_missing_kwargs_fails_with_usage(self) -> None:
        actor = self._staff_actor(db_key="AwardDistinctionStaffMissing")
        result = GMAwardDistinctionAction().run(actor)
        assert result.success is False
        assert "Usage" in result.message
