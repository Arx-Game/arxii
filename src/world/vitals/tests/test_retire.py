"""Tests for the retire off-ramp (#2287)."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.vitals.constants import CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory
from world.vitals.services import is_retired, retire_character


class RetireCharacterTests(TestCase):
    """retire_character: dead-only, idempotent, sets the lock."""

    def _dead_sheet(self, *, days_dead: int = 0):
        vitals = CharacterVitalsFactory(
            life_state=CharacterLifeState.DEAD,
            died_at=timezone.now() - timedelta(days=days_dead),
        )
        return vitals.character_sheet, vitals

    def test_retire_living_character_raises(self) -> None:
        vitals = CharacterVitalsFactory()
        with self.assertRaises(ValueError):
            retire_character(vitals.character_sheet)

    def test_retire_sets_lock_and_is_idempotent(self) -> None:
        sheet, vitals = self._dead_sheet()
        self.assertFalse(is_retired(sheet))
        retire_character(sheet)
        vitals.refresh_from_db()
        self.assertIsNotNone(vitals.retired_at)
        self.assertTrue(is_retired(sheet))
        first_stamp = vitals.retired_at
        retire_character(sheet)
        vitals.refresh_from_db()
        self.assertEqual(vitals.retired_at, first_stamp)

    def test_is_retired_none_sheet(self) -> None:
        self.assertFalse(is_retired(None))


class AutoRetireTaskTests(TestCase):
    """The scheduler backstop releases only past-deadline unretired dead."""

    def test_auto_retire_respects_grace_window(self) -> None:
        from world.game_clock.tasks import auto_retire_dead_characters
        from world.vitals.models import VitalsConsequenceConfig

        config, _ = VitalsConsequenceConfig.objects.get_or_create(pk=1)

        fresh_dead = CharacterVitalsFactory(
            life_state=CharacterLifeState.DEAD, died_at=timezone.now()
        )
        stale_dead = CharacterVitalsFactory(
            life_state=CharacterLifeState.DEAD,
            died_at=timezone.now() - timedelta(days=config.auto_retire_days + 1),
        )
        alive = CharacterVitalsFactory()

        auto_retire_dead_characters()

        fresh_dead.refresh_from_db()
        stale_dead.refresh_from_db()
        alive.refresh_from_db()
        self.assertIsNone(fresh_dead.retired_at)
        self.assertIsNotNone(stale_dead.retired_at)
        self.assertIsNone(alive.retired_at)


class RetirePuppetLockTests(TestCase):
    """Retired characters vanish from availability and puppet checks."""

    def test_retired_character_not_available_and_not_puppetable(self) -> None:
        account = AccountFactory()
        sheet = CharacterSheetFactory()
        CharacterVitalsFactory(
            character_sheet=sheet,
            life_state=CharacterLifeState.DEAD,
            died_at=timezone.now(),
        )
        character = sheet.character
        character.db_account = account
        character.save(update_fields=["db_account"])

        retire_character(sheet)
        can, reason = account.can_puppet_character(character)
        self.assertFalse(can)
        self.assertEqual(reason, "That character has been laid to rest.")


class RetireActionTests(TestCase):
    """The retire action: self-retire dead-only, staff force path."""

    def test_self_retire_requires_death(self) -> None:
        from actions.definitions.vitals import RetireCharacterAction

        vitals = CharacterVitalsFactory()
        result = RetireCharacterAction().run(actor=vitals.character_sheet.character)
        self.assertFalse(result.success)
        self.assertIn("Only the dead", result.message)

    def test_self_retire_dead_succeeds(self) -> None:
        from actions.definitions.vitals import RetireCharacterAction

        vitals = CharacterVitalsFactory(life_state=CharacterLifeState.DEAD, died_at=timezone.now())
        sheet = vitals.character_sheet
        result = RetireCharacterAction().run(actor=sheet.character)
        self.assertTrue(result.success)
        self.assertTrue(is_retired(sheet))

    def test_non_staff_cannot_force_retire(self) -> None:
        from actions.definitions.vitals import RetireCharacterAction

        vitals = CharacterVitalsFactory(life_state=CharacterLifeState.DEAD, died_at=timezone.now())
        result = RetireCharacterAction().run(
            actor=vitals.character_sheet.character, target_name="Somebody"
        )
        self.assertFalse(result.success)
        self.assertIn("Only staff", result.message)
