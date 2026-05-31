"""Tests for ThreadHubSummaryView (GET /api/magic/thread-hub-summary/).

Covers:
- Empty character (no threads, no balances) returns the empty shape.
- Character with ready/near-xp-lock/blocked threads and a TRAIT weaving unlock.
- Auth required (unauthenticated → 401/403).
- Alt-guard: account with multiple active tenures and ?character_sheet_id= resolves
  correctly; without it returns 400.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from evennia_extensions.models import PlayerData
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterResonanceFactory,
    CharacterTechniqueFactory,
    CharacterThreadWeavingUnlockFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
    ThreadFactory,
    ThreadWeavingUnlockFactory,
    ThreadXPLockedLevelFactory,
)
from world.mechanics.factories import PropertyFactory
from world.relationships.factories import RelationshipTrackFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.traits.factories import CharacterTraitValueFactory, TraitFactory


def _link_account_to_sheet(account, character, sheet):
    """Tie an AccountDB to a CharacterSheet via an active RosterTenure.

    Reuses an existing PlayerData row if the account already has one — this
    supports linking multiple active tenures to the same account for alt-guard
    tests, since PlayerData has a one-to-one constraint with Account.
    """
    character.account = account
    account.characters.add(character)
    player_data, _ = PlayerData.objects.get_or_create(account=account)
    return RosterTenureFactory(
        roster_entry=RosterEntryFactory(character_sheet=sheet),
        player_data=player_data,
    )


_URL = "/api/magic/thread-hub-summary/"


class ThreadHubSummaryEmptyCharacterTests(APITestCase):
    """Empty character returns the empty shape with all TargetKind keys False."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="hub_empty_account")
        cls.character = CharacterFactory(db_key="HubEmptyChar")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        _link_account_to_sheet(cls.account, cls.character, cls.sheet)

    def test_empty_character_returns_expected_shape(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.get(_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        data = response.data
        self.assertEqual(data["balances"], [])
        self.assertEqual(data["ready_thread_ids"], [])
        self.assertEqual(data["near_xp_lock_thread_ids"], [])
        self.assertEqual(data["blocked_thread_ids"], [])

        # Every TargetKind must appear and must be False for an empty character.
        eligibility = data["weaving_eligibility"]
        for kind in TargetKind:
            self.assertIn(kind.value, eligibility, f"Missing TargetKind.{kind.name}")
            self.assertFalse(eligibility[kind.value], f"Expected False for {kind.name}")


class ThreadHubSummaryPopulatedTests(APITestCase):
    """Character with threads, balances, and a TRAIT weaving unlock."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="hub_populated_account")
        cls.character = CharacterFactory(db_key="HubPopulatedChar")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        _link_account_to_sheet(cls.account, cls.character, cls.sheet)

        cls.resonance = ResonanceFactory()

        # Resonance balance row.
        cls.cr = CharacterResonanceFactory(
            character_sheet=cls.sheet,
            resonance=cls.resonance,
            balance=25,
            lifetime_earned=50,
            flavor_text="fire and ash",
        )

        # --- ready-to-imbue thread ---
        # level=0 (below any cap), balance=25 above 0 → imbue_ready
        cls.ready_thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            as_trait_thread=True,
            _trait_value=100,
            _path_stage=3,  # path cap=30; anchor cap=100 → effective=30
            level=0,
            developed_points=0,
        )

        # --- near-xp-lock thread ---
        # level=0, next_boundary=10.  Seed ThreadXPLockedLevel at boundary 10.
        # dp_needed = 10 (each level 0-9 costs 1 dp since (n-9)*100 ≤ 0).
        # With developed_points=5: dp_to_boundary = 10 - 5 = 5, within 100.
        cls.xp_locked = ThreadXPLockedLevelFactory(level=10, xp_cost=150)
        cls.near_thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            as_trait_thread=True,
            _trait_value=100,
            _path_stage=3,
            level=0,
            developed_points=5,
        )

        # --- blocked thread (level == effective cap) ---
        # _trait_value=5 → anchor cap=5; _path_stage=3 → path cap=30 → effective=5.
        # level=5 == effective cap → blocked.
        cls.blocked_thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            as_trait_thread=True,
            _trait_value=5,
            _path_stage=3,
            level=5,
            developed_points=0,
        )

        # --- TRAIT weaving unlock ---
        cls.unlock = ThreadWeavingUnlockFactory(target_kind=TargetKind.TRAIT)
        CharacterThreadWeavingUnlockFactory(
            character=cls.sheet,
            unlock=cls.unlock,
        )

    def test_balances_present(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.get(_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        balances = response.data["balances"]
        self.assertEqual(len(balances), 1)
        b = balances[0]
        self.assertEqual(b["resonance_id"], self.resonance.pk)
        self.assertEqual(b["balance"], 25)
        self.assertEqual(b["lifetime_earned"], 50)
        self.assertEqual(b["flavor_text"], "fire and ash")

    def test_ready_thread_id_present(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.get(_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        self.assertIn(self.ready_thread.pk, response.data["ready_thread_ids"])

    def test_near_xp_lock_entry_present(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.get(_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        near = response.data["near_xp_lock_thread_ids"]
        # Should contain an entry for near_thread
        near_ids = [entry["thread_id"] for entry in near]
        self.assertIn(self.near_thread.pk, near_ids)
        # Verify xp_cost and boundary_level fields
        near_entry = next(e for e in near if e["thread_id"] == self.near_thread.pk)
        self.assertEqual(near_entry["xp_cost"], 150)
        self.assertEqual(near_entry["boundary_level"], 10)

    def test_blocked_thread_id_present(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.get(_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        self.assertIn(self.blocked_thread.pk, response.data["blocked_thread_ids"])

    def test_trait_weaving_eligibility_true(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.get(_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        eligibility = response.data["weaving_eligibility"]
        self.assertTrue(eligibility[TargetKind.TRAIT.value])

    def test_all_target_kinds_present_in_eligibility(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.get(_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        eligibility = response.data["weaving_eligibility"]
        for kind in TargetKind:
            self.assertIn(kind.value, eligibility, f"Missing TargetKind.{kind.name}")


class ThreadHubSummaryAuthTests(APITestCase):
    """Unauthenticated requests are rejected."""

    def test_unauthenticated_is_rejected(self) -> None:
        response = self.client.get(_URL)
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )


class ThreadHubSummaryAltGuardTests(APITestCase):
    """Alt-guard: multiple active tenures require explicit character_sheet_id."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="hub_altguard_account")

        # First character/sheet
        cls.character1 = CharacterFactory(db_key="HubAltChar1")
        cls.sheet1 = CharacterSheetFactory(character=cls.character1)
        _link_account_to_sheet(cls.account, cls.character1, cls.sheet1)

        # Second character/sheet — same account → multiple active tenures
        cls.character2 = CharacterFactory(db_key="HubAltChar2")
        cls.sheet2 = CharacterSheetFactory(character=cls.character2)
        _link_account_to_sheet(cls.account, cls.character2, cls.sheet2)

    def test_multiple_tenures_without_sheet_id_returns_400(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.get(_URL)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_multiple_tenures_with_explicit_sheet_id_returns_200(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.get(_URL, {"character_sheet_id": self.sheet1.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)


class ThreadHubSummaryPickerDataTests(APITestCase):
    """Picker data fields (weavable_traits, weavable_techniques, room_property_ids,
    weavable_relationship_track_ids) are populated from the character's handlers + unlocks."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="picker_data_account")
        cls.character = CharacterFactory(db_key="PickerDataChar")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        _link_account_to_sheet(cls.account, cls.character, cls.sheet)

        # TRAIT unlock + matching trait value > 0
        cls.trait = TraitFactory(name="Persuasion")
        cls.trait_unlock = ThreadWeavingUnlockFactory(
            target_kind="TRAIT",
            unlock_trait=cls.trait,
            unlock_gift=None,
            unlock_room_property=None,
            unlock_track=None,
        )
        CharacterThreadWeavingUnlockFactory(character=cls.sheet, unlock=cls.trait_unlock)
        CharacterTraitValueFactory(
            character=cls.character,
            trait=cls.trait,
            value=30,  # display_value = 3.0
        )

        # TECHNIQUE unlock + matching CharacterTechnique
        cls.gift = GiftFactory(name="TestGift")
        cls.technique = TechniqueFactory(name="TestTechnique", gift=cls.gift)
        cls.tech_unlock = ThreadWeavingUnlockFactory(
            target_kind="TECHNIQUE",
            unlock_trait=None,
            unlock_gift=cls.gift,
            unlock_room_property=None,
            unlock_track=None,
        )
        CharacterThreadWeavingUnlockFactory(character=cls.sheet, unlock=cls.tech_unlock)
        CharacterTechniqueFactory(character=cls.sheet, technique=cls.technique)

        # ROOM unlock
        cls.prop = PropertyFactory(name="Sacred Ground")
        cls.room_unlock = ThreadWeavingUnlockFactory(
            target_kind="ROOM",
            unlock_trait=None,
            unlock_gift=None,
            unlock_room_property=cls.prop,
            unlock_track=None,
        )
        CharacterThreadWeavingUnlockFactory(character=cls.sheet, unlock=cls.room_unlock)

        # RELATIONSHIP_TRACK unlock
        cls.track = RelationshipTrackFactory(name="Loyalty")
        cls.track_unlock = ThreadWeavingUnlockFactory(
            target_kind="RELATIONSHIP_TRACK",
            unlock_trait=None,
            unlock_gift=None,
            unlock_room_property=None,
            unlock_track=cls.track,
        )
        CharacterThreadWeavingUnlockFactory(character=cls.sheet, unlock=cls.track_unlock)

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.account)
        # Invalidate the technique handler cache so it re-reads for each test.
        if "techniques" in self.character.__dict__:
            del self.character.__dict__["techniques"]

    def test_weavable_trait_with_value_appears(self) -> None:
        response = self.client.get(_URL)
        self.assertEqual(response.status_code, 200, response.data)
        traits = response.data["weavable_traits"]
        self.assertEqual(len(traits), 1)
        self.assertEqual(traits[0]["trait_id"], self.trait.pk)
        self.assertEqual(traits[0]["name"], "Persuasion")
        self.assertAlmostEqual(float(traits[0]["display_value"]), 3.0, places=1)

    def test_trait_with_zero_value_excluded(self) -> None:
        """Trait unlock exists but character's value is 0 → not in weavable_traits."""
        zero_trait = TraitFactory(name="ZeroTrait")
        zero_unlock = ThreadWeavingUnlockFactory(
            target_kind="TRAIT",
            unlock_trait=zero_trait,
            unlock_gift=None,
            unlock_room_property=None,
            unlock_track=None,
        )
        CharacterThreadWeavingUnlockFactory(character=self.sheet, unlock=zero_unlock)
        # No CharacterTraitValue row → handler returns DefaultTraitValue with value=0

        response = self.client.get(_URL)
        self.assertEqual(response.status_code, 200)
        trait_ids = [t["trait_id"] for t in response.data["weavable_traits"]]
        self.assertNotIn(zero_trait.pk, trait_ids)

    def test_weavable_technique_appears(self) -> None:
        response = self.client.get(_URL)
        self.assertEqual(response.status_code, 200)
        techniques = response.data["weavable_techniques"]
        self.assertEqual(len(techniques), 1)
        self.assertEqual(techniques[0]["technique_id"], self.technique.pk)
        self.assertEqual(techniques[0]["name"], "TestTechnique")
        self.assertEqual(techniques[0]["gift_id"], self.gift.pk)
        self.assertEqual(techniques[0]["gift_name"], "TestGift")

    def test_room_property_id_appears(self) -> None:
        response = self.client.get(_URL)
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.prop.pk, response.data["room_property_ids"])

    def test_relationship_track_id_appears(self) -> None:
        response = self.client.get(_URL)
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.track.pk, response.data["weavable_relationship_track_ids"])

    def test_empty_character_has_empty_picker_lists(self) -> None:
        """Character with no weaving unlocks gets four empty lists."""
        empty_account = AccountFactory(username="picker_empty_account")
        empty_char = CharacterFactory(db_key="PickerEmptyChar")
        empty_sheet = CharacterSheetFactory(character=empty_char)
        _link_account_to_sheet(empty_account, empty_char, empty_sheet)

        self.client.force_authenticate(user=empty_account)
        response = self.client.get(_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["weavable_traits"], [])
        self.assertEqual(response.data["weavable_techniques"], [])
        self.assertEqual(response.data["room_property_ids"], [])
        self.assertEqual(response.data["weavable_relationship_track_ids"], [])
