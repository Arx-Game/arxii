"""Sentence enforcement tests (#2378) — brig terms served, terminal countdown, sweep."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from world.captivity.constants import CaptivityStatus
from world.captivity.factories import CaptivityFactory
from world.captivity.services import resolve_captivity
from world.character_sheets.types import LifecycleState
from world.currency.services import get_or_create_purse
from world.justice.constants import (
    BRIG_DAYS_PER_WEIGHT,
    EXECUTION_MIN_FAILED_OUTS,
    EXILE_PIN_VALUE,
    EXILE_TERM_DAYS_MIN,
    EXILE_TERM_DAYS_PER_WEIGHT_DIV,
    FINE_COPPERS_PER_WEIGHT,
    HUNTED_VALUE_FLOOR,
    MAX_VALUE_FLOOR,
    RESCUE_WINDOW_DAYS,
    GuardTrigger,
    SentenceKind,
)
from world.justice.models import ExileDecree, GuardEncounter, JusticeCase, PersonaHeat
from world.justice.pipeline import _take_into_custody, initiate_trial
from world.justice.sentences import apply_confiscation, sentence_sweep_tick
from world.justice.tests.test_services import JusticeFixtureMixin
from world.room_features.constants import BRIG_CAPACITY_PER_LEVEL, RoomFeatureServiceStrategy
from world.room_features.factories import RoomFeatureKindFactory
from world.room_features.models import BrigDetails, RoomFeatureInstance
from world.roster.factories import RosterTenureFactory


class _SentenceCaseMixin(JusticeFixtureMixin):
    def _case(self, *, weight, failed_outs=0, persona=None):
        return JusticeCase.objects.create(
            persona=persona or self.persona,
            area=self.kingdom,
            society=self.crown,
            prosecution_weight=weight,
            failed_outs=failed_outs,
        )

    def _hold(self, case, *, sheet=None):
        """Attach a HELD captivity to ``case`` for the sheet behind its persona."""
        sheet = sheet or case.persona.character_sheet
        captivity = CaptivityFactory(captive=sheet)
        case.captivity = captivity
        case.save(update_fields=["captivity"])
        return captivity

    def _pc_persona(self, *, opt_in: bool):
        tenure = RosterTenureFactory()
        player_data = tenure.player_data
        player_data.lethal_consequences_opt_in = opt_in
        player_data.save(update_fields=["lethal_consequences_opt_in"])
        return tenure.roster_entry.character_sheet.primary_persona

    def _brig_room(self, area):
        """Build an active Brig room feature in ``area`` (mirrors mechanics' capture tests)."""
        brig_room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        brig_profile = RoomProfileFactory(objectdb=brig_room, area=area)
        kind = RoomFeatureKindFactory(service_strategy=RoomFeatureServiceStrategy.BRIG)
        instance = RoomFeatureInstance.objects.create(
            room_profile=brig_profile, feature_kind=kind, level=1
        )
        BrigDetails.objects.create(feature_instance=instance, max_prisoners=BRIG_CAPACITY_PER_LEVEL)
        return brig_room


class BrigTermTests(_SentenceCaseMixin, TestCase):
    def test_brig_sentence_holds_captivity_and_sets_end_date(self):
        # HUNTED..MAX-1 weight, failed_outs=1 pre-trial → 2 after increment → BRIG_TERM.
        case = self._case(weight=120, failed_outs=1)
        captivity = self._hold(case)
        before = timezone.now()

        initiate_trial(case, case.persona, check_levels=[-3])
        case.refresh_from_db()
        captivity.refresh_from_db()

        self.assertEqual(case.sentence_kind, SentenceKind.BRIG_TERM)
        expected_amount = max(1, 120 * BRIG_DAYS_PER_WEIGHT // 10)
        self.assertEqual(case.sentence_amount, expected_amount)
        self.assertIsNotNone(case.sentence_ends_at)
        self.assertGreaterEqual(
            case.sentence_ends_at, before + timedelta(days=expected_amount) - timedelta(minutes=1)
        )
        self.assertEqual(captivity.status, CaptivityStatus.HELD)

    def test_sweep_releases_matured_brig_term(self):
        case = self._case(weight=120, failed_outs=1)
        captivity = self._hold(case)
        initiate_trial(case, case.persona, check_levels=[-3])
        case.refresh_from_db()
        self.assertEqual(case.sentence_kind, SentenceKind.BRIG_TERM)

        case.sentence_ends_at = timezone.now() - timedelta(days=1)
        case.save(update_fields=["sentence_ends_at"])

        touched = sentence_sweep_tick()

        case.refresh_from_db()
        captivity.refresh_from_db()
        self.assertEqual(touched, 1)
        self.assertEqual(captivity.status, CaptivityStatus.RELEASED)
        self.assertIsNone(case.sentence_ends_at)


class TerminalSentenceTests(_SentenceCaseMixin, TestCase):
    def _catastrophic_case(self, persona):
        # weight >= MAX and failed_outs one below the threshold, so the trial's
        # +1 increment lands exactly on EXECUTION_MIN_FAILED_OUTS (spec #2378 §9).
        return self._case(
            weight=MAX_VALUE_FLOOR, failed_outs=EXECUTION_MIN_FAILED_OUTS - 1, persona=persona
        )

    def test_opted_in_pc_reaches_execution_with_rescue_window(self):
        persona = self._pc_persona(opt_in=True)
        case = self._catastrophic_case(persona)
        captivity = self._hold(case, sheet=persona.character_sheet)
        before = timezone.now()

        initiate_trial(case, persona, check_levels=[-3])
        case.refresh_from_db()
        captivity.refresh_from_db()

        self.assertEqual(case.sentence_kind, SentenceKind.EXECUTION)
        self.assertIsNotNone(case.terminal_due_at)
        self.assertGreaterEqual(
            case.terminal_due_at, before + timedelta(days=RESCUE_WINDOW_DAYS) - timedelta(minutes=1)
        )
        self.assertEqual(captivity.status, CaptivityStatus.HELD)
        self.assertIsNone(case.terminal_carried_out_at)

    def test_sweep_before_due_date_does_nothing(self):
        persona = self._pc_persona(opt_in=True)
        case = self._catastrophic_case(persona)
        captivity = self._hold(case, sheet=persona.character_sheet)
        initiate_trial(case, persona, check_levels=[-3])
        case.refresh_from_db()
        self.assertEqual(case.sentence_kind, SentenceKind.EXECUTION)

        touched = sentence_sweep_tick()

        case.refresh_from_db()
        captivity.refresh_from_db()
        self.assertEqual(touched, 0)
        self.assertEqual(captivity.status, CaptivityStatus.HELD)
        self.assertIsNone(case.terminal_carried_out_at)

    def test_sweep_after_due_date_carries_out_execution(self):
        persona = self._pc_persona(opt_in=True)
        case = self._catastrophic_case(persona)
        captivity = self._hold(case, sheet=persona.character_sheet)
        initiate_trial(case, persona, check_levels=[-3])
        case.refresh_from_db()
        self.assertEqual(case.sentence_kind, SentenceKind.EXECUTION)

        case.terminal_due_at = timezone.now() - timedelta(days=1)
        case.save(update_fields=["terminal_due_at"])

        touched = sentence_sweep_tick()

        case.refresh_from_db()
        captivity.refresh_from_db()
        sheet = persona.character_sheet
        sheet.refresh_from_db()
        self.assertEqual(touched, 1)
        self.assertEqual(sheet.lifecycle_state, LifecycleState.DEAD)
        self.assertIsNotNone(sheet.lifecycle_state_at)
        self.assertEqual(captivity.status, CaptivityStatus.RELEASED)
        self.assertIsNotNone(case.terminal_carried_out_at)

    def test_non_opted_pc_gets_banishment_not_execution(self):
        from evennia_extensions.factories import RoomProfileFactory

        destination = RoomProfileFactory()
        self.kingdom.exile_destination = destination
        self.kingdom.save(update_fields=["exile_destination"])

        persona = self._pc_persona(opt_in=False)
        case = self._catastrophic_case(persona)
        captivity = self._hold(case, sheet=persona.character_sheet)

        initiate_trial(case, persona, check_levels=[-3])
        case.refresh_from_db()
        self.assertEqual(case.sentence_kind, SentenceKind.BANISHMENT)
        self.assertIsNotNone(case.terminal_due_at)

        case.terminal_due_at = timezone.now() - timedelta(days=1)
        case.save(update_fields=["terminal_due_at"])

        touched = sentence_sweep_tick()

        case.refresh_from_db()
        captivity.refresh_from_db()
        sheet = persona.character_sheet
        sheet.refresh_from_db()
        self.assertEqual(touched, 1)
        self.assertNotEqual(sheet.lifecycle_state, LifecycleState.DEAD)
        self.assertEqual(captivity.status, CaptivityStatus.RELEASED)
        self.assertIsNotNone(case.terminal_carried_out_at)

        decree = ExileDecree.objects.get(case=case)
        self.assertIsNone(decree.ends_at)  # permanent
        self.assertEqual(decree.persona, persona)
        self.assertEqual(decree.area, self.kingdom)

        heat_row = PersonaHeat.objects.get(persona=persona, area=self.kingdom, society=self.crown)
        self.assertGreaterEqual(heat_row.value, EXILE_PIN_VALUE)
        self.assertEqual(heat_row.pinned_until, decree.pin_until)

        # Ejected to the area's exile destination — the move that sticks, after
        # resolve_captivity's own default relocation.
        self.assertEqual(sheet.character.location, destination.objectdb)

    def test_escape_before_due_date_voids_the_terminal_sentence(self):
        persona = self._pc_persona(opt_in=True)
        case = self._catastrophic_case(persona)
        captivity = self._hold(case, sheet=persona.character_sheet)
        initiate_trial(case, persona, check_levels=[-3])
        case.refresh_from_db()
        self.assertEqual(case.sentence_kind, SentenceKind.EXECUTION)

        case.terminal_due_at = timezone.now() - timedelta(days=1)
        case.save(update_fields=["terminal_due_at"])

        # Escaped before the sweep ran — rescue succeeded, sentence voided.
        resolve_captivity(captivity, status=CaptivityStatus.ESCAPED)

        touched = sentence_sweep_tick()

        case.refresh_from_db()
        sheet = persona.character_sheet
        sheet.refresh_from_db()
        self.assertEqual(touched, 0)
        self.assertIsNone(case.terminal_due_at)
        self.assertIsNone(case.terminal_carried_out_at)
        self.assertNotEqual(sheet.lifecycle_state, LifecycleState.DEAD)


class ExileSentenceTests(_SentenceCaseMixin, TestCase):
    def test_first_full_verdict_at_hunted_weight_is_exile(self):
        # HUNTED weight, failed_outs=0 pre-trial → 1 after increment → EXILE band.
        case = self._case(weight=HUNTED_VALUE_FLOOR, failed_outs=0)
        captivity = self._hold(case)
        before = timezone.now()

        initiate_trial(case, case.persona, check_levels=[-3])
        case.refresh_from_db()
        captivity.refresh_from_db()

        self.assertEqual(case.sentence_kind, SentenceKind.EXILE)
        expected_amount = max(
            EXILE_TERM_DAYS_MIN, HUNTED_VALUE_FLOOR // EXILE_TERM_DAYS_PER_WEIGHT_DIV
        )
        self.assertEqual(case.sentence_amount, expected_amount)
        self.assertEqual(captivity.status, CaptivityStatus.RELEASED)

        decree = ExileDecree.objects.get(case=case)
        self.assertEqual(decree.persona, case.persona)
        self.assertEqual(decree.area, self.kingdom)
        self.assertIsNotNone(decree.ends_at)
        self.assertEqual(case.sentence_ends_at, decree.ends_at)
        self.assertGreaterEqual(
            decree.ends_at, before + timedelta(days=expected_amount) - timedelta(minutes=1)
        )

        heat_row = PersonaHeat.objects.get(
            persona=case.persona, area=self.kingdom, society=self.crown
        )
        self.assertGreaterEqual(heat_row.value, EXILE_PIN_VALUE)
        self.assertEqual(heat_row.pinned_until, decree.pin_until)

        # self.kingdom has no exile_destination configured: eject no-ops safely.
        self.assertIsNone(self.kingdom.exile_destination)

    def test_exile_ejects_when_destination_set(self):
        from evennia_extensions.factories import RoomProfileFactory

        destination = RoomProfileFactory()
        self.kingdom.exile_destination = destination
        self.kingdom.save(update_fields=["exile_destination"])

        case = self._case(weight=HUNTED_VALUE_FLOOR, failed_outs=0)
        self._hold(case)

        initiate_trial(case, case.persona, check_levels=[-3])
        case.refresh_from_db()

        sheet = case.persona.character_sheet
        sheet.refresh_from_db()
        self.assertEqual(sheet.character.location, destination.objectdb)


class ConfiscationSentenceTests(_SentenceCaseMixin, TestCase):
    """apply_confiscation (#2378 Task 4) — seize into the brig, or double-fine fallback."""

    def test_confiscation_moves_carried_items_into_brig(self):
        brig_room = self._brig_room(self.kingdom)
        case = self._case(weight=HUNTED_VALUE_FLOOR)
        self._hold(case)
        character = case.persona.character_sheet.character
        item = ObjectDBFactory(db_typeclass_path="typeclasses.objects.Object", location=character)

        apply_confiscation(case)

        item.refresh_from_db()
        self.assertEqual(item.location, brig_room)
        case.captivity.refresh_from_db()
        self.assertEqual(case.captivity.status, CaptivityStatus.RELEASED)

    def test_confiscation_falls_back_to_double_fine_without_brig(self):
        # self.kingdom has no Brig — falls back to the double-rate fine.
        case = self._case(weight=HUNTED_VALUE_FLOOR)
        self._hold(case)
        sheet = case.persona.character_sheet
        purse = get_or_create_purse(sheet)
        purse.balance = 100_000
        purse.save(update_fields=["balance"])

        apply_confiscation(case)

        purse.refresh_from_db()
        expected_debit = HUNTED_VALUE_FLOOR * FINE_COPPERS_PER_WEIGHT * 2
        self.assertEqual(purse.balance, 100_000 - expected_debit)
        case.captivity.refresh_from_db()
        self.assertEqual(case.captivity.status, CaptivityStatus.RELEASED)


class CustodyBrigRoutingTests(_SentenceCaseMixin, TestCase):
    """pipeline._take_into_custody routes arrests to the area's Brig (#2378 Task 4)."""

    def test_custody_routes_to_brig_when_available(self):
        brig_room = self._brig_room(self.kingdom)
        encounter = GuardEncounter.objects.create(
            persona=self.persona, area=self.kingdom, trigger=GuardTrigger.ROOM_ARRIVAL
        )

        captivity = _take_into_custody(encounter, self.crown)

        self.assertIsNotNone(captivity)
        self.assertEqual(captivity.holding_room, brig_room.room_profile)
        self.assertIsNone(captivity.cell)

    def test_custody_falls_back_to_instanced_cell_without_brig(self):
        # self.kingdom has no Brig — falls back to the instanced-cell default.
        encounter = GuardEncounter.objects.create(
            persona=self.persona, area=self.kingdom, trigger=GuardTrigger.ROOM_ARRIVAL
        )

        captivity = _take_into_custody(encounter, self.crown)

        self.assertIsNotNone(captivity)
        self.assertIsNone(captivity.holding_room)
        self.assertIsNotNone(captivity.cell)
