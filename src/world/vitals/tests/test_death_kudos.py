"""Tests for the capped death-kudos channel (#2287)."""

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.progression.models import CharacterXP, KudosPointsData
from world.scenes.factories import SceneFactory
from world.scenes.models import SceneParticipation
from world.vitals.constants import CharacterLifeState
from world.vitals.death_kudos import DeathKudosError, award_death_kudos
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.seeds import ensure_death_kudos_category
from world.vitals.services import retire_character

LIFETIME_SPENT = 500


class DeathKudosTests(TestCase):
    """Tier amounts, the lifetime-spend cap, and the eligibility gates."""

    @classmethod
    def setUpTestData(cls) -> None:
        ensure_death_kudos_category()
        cls.recipient_account = AccountFactory()
        cls.sheet = CharacterSheetFactory()
        cls.scene = SceneFactory()
        cls.vitals = CharacterVitalsFactory(
            character_sheet=cls.sheet,
            life_state=CharacterLifeState.DEAD,
            died_at=timezone.now(),
            died_in_scene=cls.scene,
        )
        cls.character = cls.sheet.character
        cls.character.db_account = cls.recipient_account
        cls.character.save(update_fields=["db_account"])
        CharacterXP.objects.create(
            character=cls.character.sheet_data,
            total_earned=LIFETIME_SPENT,
            total_spent=LIFETIME_SPENT,
        )

    def _participant(self, *, is_gm: bool = False):
        account = AccountFactory()
        SceneParticipation.objects.create(scene=self.scene, account=account, is_gm=is_gm)
        return account

    def _staff(self):
        account = AccountFactory()
        account.is_staff = True
        account.save(update_fields=["is_staff"])
        return account

    def test_gm_grant_is_half_lifetime_spend(self) -> None:
        gm = self._participant(is_gm=True)
        result = award_death_kudos(gm, self.character)
        self.assertEqual(result.amount, LIFETIME_SPENT // 2)
        self.assertFalse(result.capped)
        points = KudosPointsData.objects.get(account=self.recipient_account)
        self.assertEqual(points.total_earned, LIFETIME_SPENT // 2)

    def test_player_grant_is_five_percent(self) -> None:
        player = self._participant()
        result = award_death_kudos(player, self.character)
        self.assertEqual(result.amount, LIFETIME_SPENT // 20)

    def test_cap_then_trickle_floors(self) -> None:
        # GM + staff each take 50%: the cap (100% of lifetime spend) is full.
        award_death_kudos(self._participant(is_gm=True), self.character)
        award_death_kudos(self._staff(), self.character)
        # Post-cap: players land the floor of 1, staff the floor of 20.
        player_result = award_death_kudos(self._participant(), self.character)
        self.assertEqual(player_result.amount, 1)
        self.assertTrue(player_result.capped)
        staff_result = award_death_kudos(self._staff(), self.character)
        self.assertEqual(staff_result.amount, 20)
        self.assertTrue(staff_result.capped)

    def test_double_give_rejected(self) -> None:
        player = self._participant()
        award_death_kudos(player, self.character)
        with self.assertRaises(DeathKudosError):
            award_death_kudos(player, self.character)

    def test_non_participant_rejected(self) -> None:
        outsider = AccountFactory()
        with self.assertRaises(DeathKudosError):
            award_death_kudos(outsider, self.character)

    def test_window_closes_at_retire(self) -> None:
        player = self._participant()
        retire_character(self.sheet)
        with self.assertRaises(DeathKudosError):
            award_death_kudos(player, self.character)

    def test_living_character_rejected(self) -> None:
        alive_sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=alive_sheet)
        with self.assertRaises(DeathKudosError):
            award_death_kudos(self._staff(), alive_sheet.character)

    def test_self_honor_rejected(self) -> None:
        SceneParticipation.objects.create(scene=self.scene, account=self.recipient_account)
        with self.assertRaises(DeathKudosError):
            award_death_kudos(self.recipient_account, self.character)


class OffscreenDeathKudosTests(TestCase):
    """No death scene: staff-only channel."""

    @classmethod
    def setUpTestData(cls) -> None:
        ensure_death_kudos_category()
        cls.recipient_account = AccountFactory()
        cls.sheet = CharacterSheetFactory()
        CharacterVitalsFactory(
            character_sheet=cls.sheet,
            life_state=CharacterLifeState.DEAD,
            died_at=timezone.now(),
        )
        cls.character = cls.sheet.character
        cls.character.db_account = cls.recipient_account
        cls.character.save(update_fields=["db_account"])

    def test_player_rejected_staff_allowed(self) -> None:
        player = AccountFactory()
        with self.assertRaises(DeathKudosError):
            award_death_kudos(player, self.character)
        staff = AccountFactory()
        staff.is_staff = True
        staff.save(update_fields=["is_staff"])
        result = award_death_kudos(staff, self.character)
        # No CharacterXP rows: lifetime spend 0 → the staff floor of 20.
        self.assertEqual(result.amount, 20)
