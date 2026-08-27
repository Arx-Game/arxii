"""Exile enforcement tests (#2378 Task 3) — decree, heat pin, ejection, breach, pardon lift.

``ExileSentenceTests`` in ``test_sentence_enforcement.py`` covers the end-to-end
``apply_exile`` path via a trial verdict; this module drills the individual
seams (:func:`pin_heat_for_decree`, :func:`eject`, :func:`is_magically_concealed`,
the pin exclusion in :func:`heat_decay_tick`, the breach-of-exile escalation in
the pipeline, and the pardon lift) directly.

Several assertions here re-fetch via ``Model.objects.get(pk=...)`` (after
``Model.flush_instance_cache()`` where the mutation was a bulk ``.update()``)
rather than ``instance.refresh_from_db()`` — a bare bulk ``.update()`` bypasses
the SharedMemoryModel identity map entirely (it never touches the cached Python
instance), and this codebase's established pattern
(``world/justice/tests/test_services.py``) flushes explicitly rather than
trusting ``refresh_from_db()`` to see it.
"""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from world.captivity.constants import CaptivityStatus
from world.captivity.factories import CaptivityFactory
from world.justice.constants import (
    BREACH_OF_EXILE_CRIME_SLUG,
    BREACH_WEIGHT_BONUS,
    EVASION_BOTCH_LEVEL,
    EXILE_PIN_DAYS,
    EXILE_PIN_VALUE,
    MAX_VALUE_FLOOR,
    RESCUE_WINDOW_DAYS,
    CaseStatus,
    GuardTrigger,
    SentenceKind,
)
from world.justice.lifecycle import pardon_persona
from world.justice.models import CrimeKind, ExileDecree, GuardEncounter, JusticeCase, PersonaHeat
from world.justice.pipeline import (
    _resolve_evasion_level,
    maybe_guard_encounter,
    resolve_guard_encounter,
)
from world.justice.sentences import eject, is_magically_concealed, pin_heat_for_decree
from world.justice.services import heat_decay_tick
from world.justice.tests.test_services import JusticeFixtureMixin
from world.scenes.factories import PersonaFactory


def _heat(persona, area, society, value):
    return PersonaHeat.objects.create(persona=persona, area=area, society=society, value=value)


class _FireRng:
    def random(self) -> float:
        return 0.0  # always under the pct → fires


class _DecreeFixtureMixin(JusticeFixtureMixin):
    def _decree(self, *, persona=None, pin_days=EXILE_PIN_DAYS, ends_at=None, now=None):
        now = now or timezone.now()
        persona = persona or self.persona
        return ExileDecree.objects.create(
            persona=persona,
            area=self.kingdom,
            society=self.crown,
            pin_until=now + timedelta(days=pin_days),
            ends_at=ends_at,
        )


class PinHeatForDecreeTests(_DecreeFixtureMixin, TestCase):
    def test_creates_row_at_pin_value(self):
        decree = self._decree()
        row = pin_heat_for_decree(decree)
        self.assertEqual(row.value, EXILE_PIN_VALUE)
        self.assertEqual(row.pinned_until, decree.pin_until)

    def test_floors_low_value_but_never_lowers_a_higher_one(self):
        decree = self._decree()
        _heat(self.persona, self.kingdom, self.crown, EXILE_PIN_VALUE + 500)
        row = pin_heat_for_decree(decree)
        self.assertEqual(row.value, EXILE_PIN_VALUE + 500)
        self.assertEqual(row.pinned_until, decree.pin_until)


class EjectTests(_DecreeFixtureMixin, TestCase):
    def _case(self):
        return JusticeCase.objects.create(
            persona=self.persona, area=self.kingdom, society=self.crown
        )

    def test_moves_character_when_destination_set(self):
        from evennia.utils.idmapper.models import flush_cache

        from evennia_extensions.factories import RoomProfileFactory
        from world.character_sheets.models import CharacterSheet

        destination = RoomProfileFactory()
        self.kingdom.exile_destination = destination
        self.kingdom.save(update_fields=["exile_destination"])
        case = self._case()

        moved = eject(case)

        self.assertTrue(moved)
        # move_to() persists via an instance .save(); the identity map itself
        # is untouched by that plain FK write on a related object, so pull a
        # fresh CharacterSheet rather than trusting a cached relation.
        flush_cache()
        sheet = CharacterSheet.objects.get(pk=case.persona.character_sheet.pk)
        self.assertEqual(sheet.character.location, destination.objectdb)

    def test_no_ops_when_destination_unset(self):
        from evennia.utils.idmapper.models import flush_cache

        from world.character_sheets.models import CharacterSheet

        case = self._case()
        sheet_pk = self.persona.character_sheet.pk
        before_location = self.persona.character_sheet.character.location

        moved = eject(case)

        self.assertFalse(moved)
        flush_cache()
        sheet = CharacterSheet.objects.get(pk=sheet_pk)
        self.assertEqual(sheet.character.location, before_location)


class MagicalConcealmentSeamTests(JusticeFixtureMixin, TestCase):
    def test_is_magically_concealed_returns_false(self):
        self.assertFalse(is_magically_concealed(self.persona))


class HeatDecayPinExclusionTests(JusticeFixtureMixin, TestCase):
    def test_pinned_row_untouched_and_survives_the_zero_delete(self):
        row = PersonaHeat.objects.create(
            persona=self.persona,
            area=self.kingdom,
            society=self.crown,
            value=EXILE_PIN_VALUE,
            pinned_until=timezone.now() + timedelta(days=1),
        )
        heat_decay_tick()
        PersonaHeat.flush_instance_cache()  # bulk update bypasses the identity map
        self.assertEqual(PersonaHeat.objects.get(pk=row.pk).value, EXILE_PIN_VALUE)

    def test_expired_pin_decays_again(self):
        row = PersonaHeat.objects.create(
            persona=self.persona,
            area=self.kingdom,
            society=self.crown,
            value=EXILE_PIN_VALUE,
            pinned_until=timezone.now() - timedelta(days=1),
        )
        heat_decay_tick()
        PersonaHeat.flush_instance_cache()  # bulk update bypasses the identity map
        self.assertLess(PersonaHeat.objects.get(pk=row.pk).value, EXILE_PIN_VALUE)


class EvasionForcedBotchTests(_DecreeFixtureMixin, TestCase):
    def _encounter(self):
        _heat(self.persona, self.kingdom, self.crown, MAX_VALUE_FLOOR)
        return GuardEncounter.objects.create(
            persona=self.persona, area=self.kingdom, trigger=GuardTrigger.ROOM_ARRIVAL
        )

    def test_forces_botch_while_pinned(self):
        self._decree()
        encounter = self._encounter()
        level = _resolve_evasion_level(encounter, None)
        self.assertEqual(level, EVASION_BOTCH_LEVEL)

    def test_check_level_injection_ignored_while_pinned(self):
        self._decree()
        encounter = self._encounter()
        level = _resolve_evasion_level(encounter, 2)
        self.assertEqual(level, EVASION_BOTCH_LEVEL)

    def test_magically_concealed_bypasses_the_force(self):
        self._decree()
        encounter = self._encounter()
        with patch("world.justice.pipeline.is_magically_concealed", return_value=True):
            level = _resolve_evasion_level(encounter, 2)
        self.assertEqual(level, 2)

    def test_expired_pin_no_longer_forces_botch(self):
        self._decree(pin_days=-1)
        encounter = self._encounter()
        level = _resolve_evasion_level(encounter, 2)
        self.assertEqual(level, 2)


class GuardEncounterDecreeBypassTests(_DecreeFixtureMixin, TestCase):
    def test_fires_below_every_floor_for_a_decree_holder(self):
        self._decree()
        # No heat at all — well below every trigger's tier floor.
        enc = maybe_guard_encounter(
            self.persona, self.kingdom, GuardTrigger.ROOM_ARRIVAL, rng=_FireRng()
        )
        self.assertIsNotNone(enc)

    def test_without_a_decree_the_floor_still_applies(self):
        enc = maybe_guard_encounter(
            self.persona, self.kingdom, GuardTrigger.ROOM_ARRIVAL, rng=_FireRng()
        )
        self.assertIsNone(enc)


class BreachEscalationTests(_DecreeFixtureMixin, TestCase):
    def test_capture_under_active_decree_adds_breach_weight_and_mints_crime_kind(self):
        self._decree()
        _heat(self.persona, self.kingdom, self.crown, MAX_VALUE_FLOOR)
        enc = maybe_guard_encounter(
            self.persona, self.kingdom, GuardTrigger.ROOM_ARRIVAL, rng=_FireRng()
        )
        with patch("world.captivity.services.capture_character", return_value=None):
            resolve_guard_encounter(enc, check_level=-3)

        case = JusticeCase.objects.get()
        self.assertEqual(case.prosecution_weight, MAX_VALUE_FLOOR + BREACH_WEIGHT_BONUS)
        self.assertTrue(CrimeKind.objects.filter(slug=BREACH_OF_EXILE_CRIME_SLUG).exists())

    def test_capture_without_a_decree_does_not_add_breach_weight(self):
        _heat(self.persona, self.kingdom, self.crown, MAX_VALUE_FLOOR)
        enc = maybe_guard_encounter(
            self.persona, self.kingdom, GuardTrigger.ROOM_ARRIVAL, rng=_FireRng()
        )
        with patch("world.captivity.services.capture_character", return_value=None):
            resolve_guard_encounter(enc, check_level=-3)

        case = JusticeCase.objects.get()
        self.assertEqual(case.prosecution_weight, MAX_VALUE_FLOOR)
        self.assertFalse(CrimeKind.objects.filter(slug=BREACH_OF_EXILE_CRIME_SLUG).exists())


class PardonLiftTests(_DecreeFixtureMixin, TestCase):
    def _magistrate(self):
        from world.justice.constants import MAGISTRATE_OFFICE
        from world.societies.factories import OrganizationFactory
        from world.societies.office_services import appoint_office

        org = OrganizationFactory(society=self.crown)
        granter = PersonaFactory()
        appoint_office(organization=org, slug=MAGISTRATE_OFFICE, holder=granter)
        return granter

    def test_pardon_lifts_decree_unpins_heat_voids_terminal_and_releases_captive(self):
        granter = self._magistrate()
        now = timezone.now()
        decree = self._decree(now=now)
        # A pinned row under a DIFFERENT society survives the base heat-clear
        # (scoped to the enforcing society) — proving the unpin step is its
        # own, society-independent sweep, not a side effect of the delete.
        other_society_row = _heat(self.persona, self.kingdom, self.rival, 50)
        other_society_row.pinned_until = now + timedelta(days=1)
        other_society_row.save(update_fields=["pinned_until"])

        case = JusticeCase.objects.create(
            persona=self.persona,
            area=self.kingdom,
            society=self.crown,
            status=CaseStatus.TRIED,
            sentence_kind=SentenceKind.BANISHMENT,
            terminal_due_at=now + timedelta(days=RESCUE_WINDOW_DAYS),
        )
        captivity = CaptivityFactory(captive=self.persona.character_sheet)
        case.captivity = captivity
        case.save(update_fields=["captivity"])

        pardon_persona(granter, self.persona, self.kingdom)

        ExileDecree.flush_instance_cache()  # decree lift is a bulk .update()
        self.assertIsNotNone(ExileDecree.objects.get(pk=decree.pk).lifted_at)

        PersonaHeat.flush_instance_cache()  # unpin is a bulk .update()
        self.assertIsNone(PersonaHeat.objects.get(pk=other_society_row.pk).pinned_until)

        case.refresh_from_db()
        self.assertIsNone(case.terminal_due_at)
        captivity.refresh_from_db()
        self.assertEqual(captivity.status, CaptivityStatus.RELEASED)

    def test_pardon_of_scheduled_terminal_delivers_voided_notice(self):
        # Final review: the sweep never sees this case again once terminal_due_at
        # is cleared — the VOIDED notice must fire right here, at pardon time.
        from world.narrative.constants import NarrativeCategory
        from world.narrative.models import NarrativeMessage

        granter = self._magistrate()
        now = timezone.now()
        case = JusticeCase.objects.create(
            persona=self.persona,
            area=self.kingdom,
            society=self.crown,
            status=CaseStatus.TRIED,
            sentence_kind=SentenceKind.BANISHMENT,
            terminal_due_at=now + timedelta(days=RESCUE_WINDOW_DAYS),
        )
        captivity = CaptivityFactory(captive=self.persona.character_sheet)
        case.captivity = captivity
        case.save(update_fields=["captivity"])

        pardon_persona(granter, self.persona, self.kingdom)

        latest_body = (
            NarrativeMessage.objects.filter(category=NarrativeCategory.JUSTICE)
            .order_by("-id")
            .values_list("body", flat=True)
            .first()
        )
        self.assertIsNotNone(latest_body)
        self.assertIn("was not carried out", latest_body)
        self.assertNotIn("has been carried out", latest_body)

    def test_pardon_releases_held_brig_captive_and_clears_sentence_ends_at(self):
        granter = self._magistrate()
        case = JusticeCase.objects.create(
            persona=self.persona,
            area=self.kingdom,
            society=self.crown,
            status=CaseStatus.TRIED,
            sentence_kind=SentenceKind.BRIG_TERM,
            sentence_ends_at=timezone.now() + timedelta(days=5),
        )
        captivity = CaptivityFactory(captive=self.persona.character_sheet)
        case.captivity = captivity
        case.save(update_fields=["captivity"])

        pardon_persona(granter, self.persona, self.kingdom)

        case.refresh_from_db()
        captivity.refresh_from_db()
        self.assertIsNone(case.sentence_ends_at)
        self.assertEqual(captivity.status, CaptivityStatus.RELEASED)
