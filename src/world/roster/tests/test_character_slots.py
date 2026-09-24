"""Tests for the character slot ledger (#3996): ``world.roster.services.slots``."""

from django.test import TestCase, override_settings

from evennia_extensions.factories import AccountFactory
from world.character_creation.factories import CharacterDraftFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import ActivityState, LifecycleState
from world.roster.factories import (
    PlayerDataFactory,
    RosterApplicationFactory,
    RosterEntryFactory,
    RosterFactory,
    RosterTenureFactory,
)
from world.roster.models.choices import (
    ActivityRequirement,
    ApplicationStatus,
    RosterType,
    SlotHolderKind,
)
from world.roster.services.slots import (
    ACTIVITY_SLOT_FULL,
    SLOTS_FULL,
    SlotsFullError,
    assert_slot_available,
    character_slots,
)


def _held(player_data, *, requirement=ActivityRequirement.NONE, **sheet_kwargs):
    """A current tenure for ``player_data`` on an Active-shelf entry."""
    roster = RosterFactory(roster_type=RosterType.ACTIVE)
    sheet = CharacterSheetFactory(**sheet_kwargs)
    entry = RosterEntryFactory(
        character_sheet=sheet, roster=roster, activity_requirement=requirement
    )
    RosterTenureFactory(roster_entry=entry, player_data=player_data)
    return entry


@override_settings(CHARACTER_SLOTS_BASELINE=4)
class CharacterSlotsTests(TestCase):
    def setUp(self):
        self.account = AccountFactory()
        self.player_data = PlayerDataFactory(account=self.account)

    def _slots(self):
        # PlayerData caches its tenure list; read a fresh row the way a request does.
        self.account.refresh_from_db()
        self.account.player_data.__dict__.pop("cached_tenures", None)
        return character_slots(self.account)

    def test_empty_account_has_four_free_slots(self):
        slots = self._slots()
        assert slots.total == 4
        assert slots.used == 0
        assert slots.activity_used == 0
        assert slots.has_free_slot

    def test_tenure_draft_and_application_each_hold_a_slot(self):
        _held(self.player_data)
        CharacterDraftFactory(account=self.account)
        applied = RosterEntryFactory(roster=RosterFactory(roster_type=RosterType.AVAILABLE))
        RosterApplicationFactory(player_data=self.player_data, character=applied.character_sheet)
        slots = self._slots()
        assert slots.used == 3
        assert sorted(h.kind for h in slots.holders) == [
            SlotHolderKind.APPLICATION,
            SlotHolderKind.CHARACTER,
            SlotHolderKind.DRAFT,
        ]

    def test_frozen_and_retired_do_not_count_but_frozen_is_listed(self):
        _held(self.player_data, activity_state=ActivityState.FROZEN)
        _held(self.player_data, lifecycle_state=LifecycleState.RETIRED)
        _held(self.player_data, lifecycle_state=LifecycleState.DEAD)
        slots = self._slots()
        assert slots.used == 1
        assert [h.kind for h in slots.holders if not h.counts] == [SlotHolderKind.FROZEN]

    def test_activity_slot_counts_high_and_low_not_none(self):
        _held(self.player_data, requirement=ActivityRequirement.HIGH)
        _held(self.player_data, requirement=ActivityRequirement.LOW)
        _held(self.player_data, requirement=ActivityRequirement.NONE)
        slots = self._slots()
        assert slots.activity_used == 2
        assert not slots.has_free_activity_slot

    def test_pending_application_for_requirement_character_uses_activity_slot(self):
        applied = RosterEntryFactory(
            roster=RosterFactory(roster_type=RosterType.AVAILABLE),
            activity_requirement=ActivityRequirement.HIGH,
        )
        RosterApplicationFactory(player_data=self.player_data, character=applied.character_sheet)
        RosterApplicationFactory(
            player_data=self.player_data,
            character=RosterEntryFactory().character_sheet,
            status=ApplicationStatus.DENIED,
        )
        slots = self._slots()
        assert slots.used == 1
        assert slots.activity_used == 1

    def test_extra_slots_raise_the_total(self):
        self.player_data.extra_character_slots = 2
        self.player_data.save()
        assert self._slots().total == 6

    def test_staff_is_exempt(self):
        self.account.is_staff = True
        self.account.save()
        for _ in range(5):
            _held(self.player_data, requirement=ActivityRequirement.HIGH)
        self.account.refresh_from_db()
        self.account.player_data.__dict__.pop("cached_tenures", None)
        slots = assert_slot_available(self.account, wants_activity_requirement=True)
        assert slots.exempt
        assert slots.total is None
        assert slots.used == 5

    def test_assert_refuses_when_full_and_names_what_to_free(self):
        for _ in range(3):
            _held(self.player_data)
        CharacterDraftFactory(account=self.account)
        self.account.refresh_from_db()
        self.account.player_data.__dict__.pop("cached_tenures", None)
        with self.assertRaises(SlotsFullError) as ctx:
            assert_slot_available(self.account, wants_activity_requirement=False)
        assert ctx.exception.code == SLOTS_FULL
        assert "freeze or give up one of" in ctx.exception.user_message
        assert "finish or discard your draft" in ctx.exception.user_message

    def test_assert_refuses_second_activity_character(self):
        held = _held(self.player_data, requirement=ActivityRequirement.HIGH)
        self.account.refresh_from_db()
        self.account.player_data.__dict__.pop("cached_tenures", None)
        with self.assertRaises(SlotsFullError) as ctx:
            assert_slot_available(self.account, wants_activity_requirement=True)
        assert ctx.exception.code == ACTIVITY_SLOT_FULL
        assert held.character_sheet.character.db_key in ctx.exception.user_message
        # A character without a requirement still fits.
        assert_slot_available(self.account, wants_activity_requirement=False)

    def test_exclude_application_leaves_it_out_of_the_count(self):
        for _ in range(3):
            _held(self.player_data)
        applied = RosterEntryFactory(roster=RosterFactory(roster_type=RosterType.AVAILABLE))
        application = RosterApplicationFactory(
            player_data=self.player_data, character=applied.character_sheet
        )
        self.account.refresh_from_db()
        self.account.player_data.__dict__.pop("cached_tenures", None)
        assert character_slots(self.account).used == 4
        assert_slot_available(
            self.account, wants_activity_requirement=False, exclude_application=application
        )


class SlotGatesTests(TestCase):
    """The application and approval gates ask the ledger (#3996)."""

    @classmethod
    def setUpTestData(cls):
        from world.roster.seeds import ensure_rosters

        ensure_rosters()
        cls.staff = AccountFactory(is_staff=True)
        PlayerDataFactory(account=cls.staff)
        cls.player = AccountFactory()
        cls.player_data = PlayerDataFactory(account=cls.player)
        from evennia_extensions.factories import EmailAddressFactory

        EmailAddressFactory(user=cls.player, email=cls.player.email, verified=True, primary=True)

    def _available_entry(self, requirement=ActivityRequirement.NONE):
        from world.roster.models import Roster

        return RosterEntryFactory(
            roster=Roster.objects.get(roster_type=RosterType.AVAILABLE),
            activity_requirement=requirement,
        )

    def test_apply_is_refused_on_the_activity_slot(self):
        from rest_framework.test import APIClient

        _held(self.player_data, requirement=ActivityRequirement.HIGH)
        target = self._available_entry(ActivityRequirement.HIGH)
        client = APIClient()
        client.force_authenticate(self.player)
        response = client.post(
            f"/api/roster/entries/{target.pk}/apply/",
            {"message": "I would like to play this character because they seem interesting."},
            format="json",
        )
        assert response.status_code == 400, response.content
        assert ACTIVITY_SLOT_FULL in response.content.decode()

    @override_settings(CHARACTER_SLOTS_BASELINE=1)
    def test_approve_is_refused_when_the_slot_filled_after_applying(self):
        from world.roster.models import RosterTenure

        target = self._available_entry()
        application = RosterApplicationFactory(
            player_data=self.player_data, character=target.character_sheet
        )
        # The player takes a character after applying; the reviewer's approval must
        # not seat a second one.
        _held(self.player_data)
        self.player_data.__dict__.pop("cached_tenures", None)
        with self.assertRaises(SlotsFullError):
            application.approve(self.staff.player_data)
        application.refresh_from_db()
        assert application.status == ApplicationStatus.PENDING
        assert not RosterTenure.objects.filter(roster_entry=target).exists()

    @override_settings(CHARACTER_SLOTS_BASELINE=1)
    def test_approve_counts_its_own_application_out(self):
        target = self._available_entry()
        application = RosterApplicationFactory(
            player_data=self.player_data, character=target.character_sheet
        )
        tenure = application.approve(self.staff.player_data)
        assert tenure
        application.refresh_from_db()
        assert application.status == ApplicationStatus.APPROVED
