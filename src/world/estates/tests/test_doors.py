"""The three settlement doors: funeral seam, reading action, sweeper (#1985)."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from actions.definitions.estates import WillReadingAction
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.estates.constants import SettlementDoor, SettlementStatus
from world.estates.factories import WillExecutorFactory, WillFactory
from world.estates.models import EstateSettlement
from world.estates.services import open_settlement
from world.game_clock.tasks import auto_settle_estates
from world.vitals.constants import CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory


def _dead_sheet_with_character(key):
    character = CharacterFactory(db_key=key)
    sheet = CharacterSheetFactory(character=character)
    CharacterVitalsFactory(character_sheet=sheet, life_state=CharacterLifeState.DEAD)
    return sheet


class FuneralDoorTests(TestCase):
    def test_ceremonies_execute_will_settles_the_estate(self):
        from world.ceremonies.services import execute_will

        sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=sheet, life_state=CharacterLifeState.DEAD)
        open_settlement(sheet)
        execute_will(sheet)
        settlement = EstateSettlement.objects.get(character_sheet=sheet)
        self.assertEqual(settlement.status, SettlementStatus.SETTLED)
        self.assertEqual(settlement.settled_via, SettlementDoor.FUNERAL)

    def test_execute_will_without_settlement_is_a_quiet_noop(self):
        sheet = CharacterSheetFactory()
        from world.ceremonies.services import execute_will

        execute_will(sheet)  # long-dead honoree with no window — must not raise
        self.assertFalse(EstateSettlement.objects.filter(character_sheet=sheet).exists())


class WillReadingActionTests(TestCase):
    def setUp(self):
        self.room = ObjectDBFactory(
            db_key="ReadingRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.deceased_sheet = _dead_sheet_with_character("Fred")
        self.executor_char = CharacterFactory(db_key="Sam", location=self.room)
        self.executor_sheet = CharacterSheetFactory(character=self.executor_char)
        self.will = WillFactory(
            character_sheet=self.deceased_sheet, testament_text="To my heirs, everything."
        )
        WillExecutorFactory(will=self.will, persona=self.executor_sheet.primary_persona)
        open_settlement(self.deceased_sheet)

    def test_executor_reading_settles_the_estate(self):
        result = WillReadingAction().run(self.executor_char, target_name="Fred")
        self.assertTrue(result.success, result.message)
        settlement = EstateSettlement.objects.get(character_sheet=self.deceased_sheet)
        self.assertEqual(settlement.status, SettlementStatus.SETTLED)
        self.assertEqual(settlement.settled_via, SettlementDoor.READING)

    def test_non_executor_is_refused(self):
        stranger = CharacterFactory(db_key="Stranger", location=self.room)
        CharacterSheetFactory(character=stranger)
        result = WillReadingAction().run(stranger, target_name="Fred")
        self.assertFalse(result.success)
        settlement = EstateSettlement.objects.get(character_sheet=self.deceased_sheet)
        self.assertEqual(settlement.status, SettlementStatus.PENDING)

    def test_already_settled_estate_refuses_politely(self):
        WillReadingAction().run(self.executor_char, target_name="Fred")
        result = WillReadingAction().run(self.executor_char, target_name="Fred")
        self.assertFalse(result.success)


class SweeperDoorTests(TestCase):
    def test_past_deadline_settles_via_auto(self):
        sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=sheet, life_state=CharacterLifeState.DEAD)
        settlement = open_settlement(sheet)
        settlement.deadline = timezone.now() - timedelta(hours=1)
        settlement.save(update_fields=["deadline"])
        auto_settle_estates()
        settlement.refresh_from_db()
        self.assertEqual(settlement.status, SettlementStatus.SETTLED)
        self.assertEqual(settlement.settled_via, SettlementDoor.AUTO)

    def test_future_deadline_is_untouched(self):
        sheet = CharacterSheetFactory()
        CharacterVitalsFactory(character_sheet=sheet, life_state=CharacterLifeState.DEAD)
        settlement = open_settlement(sheet)
        auto_settle_estates()
        settlement.refresh_from_db()
        self.assertEqual(settlement.status, SettlementStatus.PENDING)
