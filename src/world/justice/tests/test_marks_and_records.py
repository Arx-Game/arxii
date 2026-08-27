"""Humiliation prestige + derived public records + my-case countdown tests (#2378 Task 5)."""

from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from world.justice.constants import (
    HUMILIATION_MARK_EXPLANATION,
    HUMILIATION_PRESTIGE_HIT,
    HUMILIATION_TERM_DAYS,
    CaseStatus,
    SentenceKind,
    Verdict,
)
from world.justice.factories import ExileDecreeFactory
from world.justice.models import JusticeCase
from world.justice.sentences import (
    active_humiliation_mark,
    active_public_marks,
    apply_humiliation,
    mint_humiliation_brand,
    schedule_sentence,
    sentence_sweep_tick,
)
from world.justice.tests.test_services import JusticeFixtureMixin
from world.roster.factories import RosterTenureFactory
from world.scenes.factories import PersonaFactory
from world.scenes.serializers import PersonaSerializer


class HumiliationPrestigeTests(JusticeFixtureMixin, TestCase):
    """apply_humiliation (#2378 Task 5): a prestige hit clamped at zero."""

    def _case(self, *, persona=None):
        return JusticeCase.objects.create(
            persona=persona or self.persona,
            area=self.kingdom,
            society=self.crown,
            prosecution_weight=10,
        )

    def test_debits_prestige_up_to_the_hit(self):
        self.persona.prestige_from_deeds = 200
        self.persona.save(update_fields=["prestige_from_deeds"])
        case = self._case()

        apply_humiliation(case)

        self.persona.refresh_from_db()
        self.assertEqual(self.persona.prestige_from_deeds, 200 - HUMILIATION_PRESTIGE_HIT)

    def test_never_drops_below_zero(self):
        self.persona.prestige_from_deeds = 10  # less than the hit itself
        self.persona.save(update_fields=["prestige_from_deeds"])
        case = self._case()

        apply_humiliation(case)

        self.persona.refresh_from_db()
        self.assertEqual(self.persona.prestige_from_deeds, 0)

    def test_already_zero_prestige_is_a_no_op(self):
        case = self._case()  # fresh persona: prestige_from_deeds defaults to 0

        apply_humiliation(case)

        self.persona.refresh_from_db()
        self.assertEqual(self.persona.prestige_from_deeds, 0)

    def test_schedule_sentence_applies_humiliation_before_releasing(self):
        from world.captivity.constants import CaptivityStatus
        from world.captivity.factories import CaptivityFactory

        self.persona.prestige_from_deeds = 100
        self.persona.save(update_fields=["prestige_from_deeds"])
        case = self._case()
        case.sentence_kind = SentenceKind.HUMILIATION
        case.save(update_fields=["sentence_kind"])
        captivity = CaptivityFactory(captive=self.persona.character_sheet)
        case.captivity = captivity
        case.save(update_fields=["captivity"])

        schedule_sentence(case)

        self.persona.refresh_from_db()
        captivity.refresh_from_db()
        self.assertEqual(self.persona.prestige_from_deeds, 100 - HUMILIATION_PRESTIGE_HIT)
        self.assertEqual(captivity.status, CaptivityStatus.RELEASED)

    def test_persists_the_actual_hit_onto_the_case(self):
        """#2378 follow-up: the EXACT applied hit is stored, not re-derived later."""
        self.persona.prestige_from_deeds = 10  # less than HUMILIATION_PRESTIGE_HIT
        self.persona.save(update_fields=["prestige_from_deeds"])
        case = self._case()

        apply_humiliation(case)

        case.refresh_from_db()
        self.assertEqual(case.humiliation_prestige_hit, 10)

    def test_zero_hit_persists_zero(self):
        case = self._case()  # fresh persona: prestige_from_deeds defaults to 0

        apply_humiliation(case)

        case.refresh_from_db()
        self.assertEqual(case.humiliation_prestige_hit, 0)

    def test_calls_the_brand_seam(self):
        """mint_humiliation_brand (#2378 follow-up ruling 5) fires from apply_humiliation."""
        case = self._case()

        with mock.patch("world.justice.sentences.mint_humiliation_brand") as mint:
            apply_humiliation(case)

        mint.assert_called_once_with(case)


class HumiliationBrandSeamTests(JusticeFixtureMixin, TestCase):
    """mint_humiliation_brand (#2378 follow-up ruling 5) — documented no-op seam."""

    def test_is_a_no_op_that_never_raises(self):
        case = JusticeCase.objects.create(
            persona=self.persona, area=self.kingdom, society=self.crown, prosecution_weight=10
        )
        self.assertIsNone(mint_humiliation_brand(case))


class HumiliationRestoreSweepTests(JusticeFixtureMixin, TestCase):
    """sentence_sweep_tick's restore leg (#2378 follow-up ruling 5)."""

    def _tried_case(self, *, resolved_at, hit, persona=None):
        return JusticeCase.objects.create(
            persona=persona or self.persona,
            area=self.kingdom,
            society=self.crown,
            prosecution_weight=10,
            status=CaseStatus.TRIED,
            verdict=Verdict.FULL,
            sentence_kind=SentenceKind.HUMILIATION,
            resolved_at=resolved_at,
            humiliation_prestige_hit=hit,
        )

    def test_restores_the_exact_hit_once_the_term_ends(self):
        self.persona.prestige_from_deeds = 0
        self.persona.save(update_fields=["prestige_from_deeds"])
        self._tried_case(
            resolved_at=timezone.now() - timedelta(days=HUMILIATION_TERM_DAYS, hours=1),
            hit=HUMILIATION_PRESTIGE_HIT,
        )

        touched = sentence_sweep_tick()

        self.persona.refresh_from_db()
        self.assertEqual(touched, 1)
        self.assertEqual(self.persona.prestige_from_deeds, HUMILIATION_PRESTIGE_HIT)

    def test_does_not_restore_before_the_term_ends(self):
        self.persona.prestige_from_deeds = 0
        self.persona.save(update_fields=["prestige_from_deeds"])
        case = self._tried_case(resolved_at=timezone.now(), hit=HUMILIATION_PRESTIGE_HIT)

        touched = sentence_sweep_tick()

        case.refresh_from_db()
        self.persona.refresh_from_db()
        self.assertEqual(touched, 0)
        self.assertEqual(self.persona.prestige_from_deeds, 0)
        self.assertEqual(case.humiliation_prestige_hit, HUMILIATION_PRESTIGE_HIT)

    def test_a_zero_hit_never_restores_anything(self):
        """A case whose hit was already clamped to zero must not double-award."""
        self._tried_case(
            resolved_at=timezone.now() - timedelta(days=HUMILIATION_TERM_DAYS, hours=1), hit=0
        )

        touched = sentence_sweep_tick()

        self.persona.refresh_from_db()
        self.assertEqual(touched, 0)
        self.assertEqual(self.persona.prestige_from_deeds, 0)

    def test_idempotent_a_second_sweep_does_not_restore_again(self):
        self.persona.prestige_from_deeds = 0
        self.persona.save(update_fields=["prestige_from_deeds"])
        case = self._tried_case(
            resolved_at=timezone.now() - timedelta(days=HUMILIATION_TERM_DAYS, hours=1),
            hit=HUMILIATION_PRESTIGE_HIT,
        )

        first = sentence_sweep_tick()
        second = sentence_sweep_tick()

        case.refresh_from_db()
        self.persona.refresh_from_db()
        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        self.assertEqual(case.humiliation_prestige_hit, 0)
        self.assertEqual(self.persona.prestige_from_deeds, HUMILIATION_PRESTIGE_HIT)


class ActiveHumiliationMarkTests(JusticeFixtureMixin, TestCase):
    """active_humiliation_mark (#2378 follow-up ruling 5) — persona-scoped read."""

    def _humiliation_case(self, *, resolved_at, persona=None):
        return JusticeCase.objects.create(
            persona=persona or self.persona,
            area=self.kingdom,
            society=self.crown,
            prosecution_weight=10,
            status=CaseStatus.TRIED,
            verdict=Verdict.FULL,
            sentence_kind=SentenceKind.HUMILIATION,
            resolved_at=resolved_at,
        )

    def test_no_case_returns_none(self):
        self.assertIsNone(active_humiliation_mark(self.persona))

    def test_appears_during_the_term(self):
        now = timezone.now()
        case = self._humiliation_case(resolved_at=now)

        mark = active_humiliation_mark(self.persona, now=now)

        self.assertIsNotNone(mark)
        self.assertEqual(mark.kind, SentenceKind.HUMILIATION)
        self.assertEqual(mark.persona_name, self.persona.name)
        self.assertEqual(mark.area_name, self.kingdom.name)
        self.assertEqual(mark.until, case.resolved_at + timedelta(days=HUMILIATION_TERM_DAYS))

    def test_disappears_after_the_term(self):
        now = timezone.now()
        self._humiliation_case(resolved_at=now - timedelta(days=HUMILIATION_TERM_DAYS, hours=1))

        mark = active_humiliation_mark(self.persona, now=now)

        self.assertIsNone(mark)

    def test_scoped_to_the_persona_not_other_personas_in_the_same_area(self):
        now = timezone.now()
        other = PersonaFactory()
        self._humiliation_case(resolved_at=now, persona=other)

        mark = active_humiliation_mark(self.persona, now=now)

        self.assertIsNone(mark)

    def test_only_tried_cases_count(self):
        """An AWAITING_TRIAL humiliation-kind row (never really possible, but a
        wrong status must never leak the mark) does not match."""
        now = timezone.now()
        JusticeCase.objects.create(
            persona=self.persona,
            area=self.kingdom,
            society=self.crown,
            prosecution_weight=10,
            status=CaseStatus.AWAITING_TRIAL,
            sentence_kind=SentenceKind.HUMILIATION,
            resolved_at=now,
        )

        mark = active_humiliation_mark(self.persona, now=now)

        self.assertIsNone(mark)


class PersonaSerializerHumiliationMarkTests(JusticeFixtureMixin, TestCase):
    """PersonaSerializer.humiliation_mark (#2378 follow-up ruling 5) — the
    examine/profile surface active_humiliation_mark feeds.
    """

    def test_none_when_no_active_mark(self):
        data = PersonaSerializer(self.persona).data
        self.assertIsNone(data["humiliation_mark"])

    def test_present_with_neutral_copy_during_the_term(self):
        now = timezone.now()
        JusticeCase.objects.create(
            persona=self.persona,
            area=self.kingdom,
            society=self.crown,
            prosecution_weight=10,
            status=CaseStatus.TRIED,
            verdict=Verdict.FULL,
            sentence_kind=SentenceKind.HUMILIATION,
            resolved_at=now,
        )

        data = PersonaSerializer(self.persona).data

        self.assertIsNotNone(data["humiliation_mark"])
        self.assertEqual(data["humiliation_mark"]["kind"], SentenceKind.HUMILIATION)
        self.assertEqual(data["humiliation_mark"]["explanation"], HUMILIATION_MARK_EXPLANATION)

    def test_absent_once_the_term_has_passed(self):
        now = timezone.now()
        JusticeCase.objects.create(
            persona=self.persona,
            area=self.kingdom,
            society=self.crown,
            prosecution_weight=10,
            status=CaseStatus.TRIED,
            verdict=Verdict.FULL,
            sentence_kind=SentenceKind.HUMILIATION,
            resolved_at=now - timedelta(days=HUMILIATION_TERM_DAYS, hours=1),
        )

        data = PersonaSerializer(self.persona).data

        self.assertIsNone(data["humiliation_mark"])


class ActivePublicMarksTests(JusticeFixtureMixin, TestCase):
    """active_public_marks (#2378 Task 5) — derived, term-limited public record."""

    def _humiliation_case(self, *, resolved_at, persona=None):
        return JusticeCase.objects.create(
            persona=persona or self.persona,
            area=self.kingdom,
            society=self.crown,
            prosecution_weight=10,
            status=CaseStatus.TRIED,
            verdict=Verdict.FULL,
            sentence_kind=SentenceKind.HUMILIATION,
            resolved_at=resolved_at,
        )

    def _terminal_case(self, *, terminal_due_at, terminal_carried_out_at=None, persona=None):
        return JusticeCase.objects.create(
            persona=persona or self.persona,
            area=self.kingdom,
            society=self.crown,
            prosecution_weight=200,
            status=CaseStatus.TRIED,
            verdict=Verdict.FULL,
            sentence_kind=SentenceKind.EXECUTION,
            terminal_due_at=terminal_due_at,
            terminal_carried_out_at=terminal_carried_out_at,
        )

    def test_fresh_humiliation_appears_with_the_term_end_as_until(self):
        now = timezone.now()
        self._humiliation_case(resolved_at=now)

        marks = active_public_marks(area=self.kingdom, now=now)

        mark = next(m for m in marks if m.kind == SentenceKind.HUMILIATION)
        self.assertEqual(mark.persona_name, self.persona.name)
        self.assertEqual(mark.area_name, self.kingdom.name)
        self.assertEqual(mark.until, now + timedelta(days=HUMILIATION_TERM_DAYS))

    def test_humiliation_ages_off_past_the_term(self):
        now = timezone.now()
        self._humiliation_case(resolved_at=now - timedelta(days=HUMILIATION_TERM_DAYS, hours=1))

        marks = active_public_marks(area=self.kingdom, now=now)

        self.assertFalse(any(m.kind == SentenceKind.HUMILIATION for m in marks))

    def test_active_decree_appears_with_its_end_date(self):
        now = timezone.now()
        ends_at = now + timedelta(days=5)
        ExileDecreeFactory(
            persona=self.persona, area=self.kingdom, society=self.crown, ends_at=ends_at
        )

        marks = active_public_marks(area=self.kingdom, now=now)

        mark = next(m for m in marks if m.kind == "exile")
        self.assertEqual(mark.persona_name, self.persona.name)
        self.assertEqual(mark.until, ends_at)

    def test_permanent_banishment_appears_with_until_none(self):
        now = timezone.now()
        ExileDecreeFactory(
            persona=self.persona, area=self.kingdom, society=self.crown, ends_at=None
        )

        marks = active_public_marks(area=self.kingdom, now=now)

        mark = next(m for m in marks if m.kind == "banishment")
        self.assertIsNone(mark.until)

    def test_lifted_decree_does_not_appear(self):
        now = timezone.now()
        ExileDecreeFactory(
            persona=self.persona,
            area=self.kingdom,
            society=self.crown,
            ends_at=None,
            lifted_at=now,
        )

        marks = active_public_marks(area=self.kingdom, now=now)

        self.assertFalse(any(m.kind in ("exile", "banishment") for m in marks))

    def test_expired_temporary_decree_does_not_appear(self):
        now = timezone.now()
        ExileDecreeFactory(
            persona=self.persona,
            area=self.kingdom,
            society=self.crown,
            ends_at=now - timedelta(days=1),
        )

        marks = active_public_marks(area=self.kingdom, now=now)

        self.assertFalse(any(m.kind == "exile" for m in marks))

    def test_scheduled_terminal_appears_while_pending(self):
        now = timezone.now()
        case = self._terminal_case(terminal_due_at=now + timedelta(days=3))

        marks = active_public_marks(area=self.kingdom, now=now)

        mark = next(m for m in marks if m.kind == SentenceKind.EXECUTION)
        self.assertEqual(mark.persona_name, self.persona.name)
        self.assertEqual(mark.until, case.terminal_due_at)

    def test_terminal_disappears_once_carried_out(self):
        now = timezone.now()
        self._terminal_case(terminal_due_at=now + timedelta(days=3), terminal_carried_out_at=now)

        marks = active_public_marks(area=self.kingdom, now=now)

        self.assertFalse(any(m.kind == SentenceKind.EXECUTION for m in marks))

    def test_marks_scoped_to_their_own_area(self):
        now = timezone.now()
        self._humiliation_case(resolved_at=now)

        marks = active_public_marks(area=self.rival_kingdom, now=now)

        self.assertEqual(marks, [])


class WantedRecordsApiTests(JusticeFixtureMixin, TestCase):
    """GET /api/justice/wanted/ carries a ``records`` list (#2378 Task 5)."""

    def _pc_entry(self):
        tenure = RosterTenureFactory()
        return tenure.player_data.account, tenure.roster_entry

    def _get(self, account, **params):
        client = APIClient()
        client.force_authenticate(user=account)
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return client.get(f"/api/justice/wanted/?{query}")

    def test_wanted_board_includes_public_marks(self):
        account, entry = self._pc_entry()
        JusticeCase.objects.create(
            persona=self.persona,
            area=self.kingdom,
            society=self.crown,
            prosecution_weight=10,
            status=CaseStatus.TRIED,
            verdict=Verdict.FULL,
            sentence_kind=SentenceKind.HUMILIATION,
            resolved_at=timezone.now(),
        )

        response = self._get(account, area=self.kingdom.pk, viewer=entry.pk)

        self.assertEqual(response.status_code, 200)
        records = response.data["records"]
        self.assertTrue(any(r["kind"] == SentenceKind.HUMILIATION for r in records))
        self.assertEqual(records[0]["persona_name"], self.persona.name)

    def test_wanted_board_records_empty_when_nothing_active(self):
        account, entry = self._pc_entry()

        response = self._get(account, area=self.kingdom.pk, viewer=entry.pk)

        self.assertEqual(response.data["records"], [])


class MyCaseCountdownFieldsTests(JusticeFixtureMixin, TestCase):
    """GET /api/justice/my-case/ exposes sentence + countdown fields (#2378 Task 5)."""

    def _pc(self):
        tenure = RosterTenureFactory()
        return tenure.player_data.account, tenure.roster_entry

    def _get(self, account, entry):
        client = APIClient()
        client.force_authenticate(user=account)
        return client.get(f"/api/justice/my-case/?viewer={entry.pk}")

    def test_awaiting_trial_case_carries_blank_sentence_fields(self):
        account, entry = self._pc()
        persona = entry.character_sheet.primary_persona
        JusticeCase.objects.create(
            persona=persona, area=self.kingdom, society=self.crown, prosecution_weight=20
        )

        response = self._get(account, entry)

        case = response.data["case"]
        self.assertIsNotNone(case)
        self.assertEqual(case["sentence_kind"], "")
        self.assertIsNone(case["sentence_ends_at"])
        self.assertIsNone(case["terminal_due_at"])

    def test_active_brig_term_exposes_countdown_fields(self):
        account, entry = self._pc()
        persona = entry.character_sheet.primary_persona
        JusticeCase.objects.create(
            persona=persona,
            area=self.kingdom,
            society=self.crown,
            prosecution_weight=20,
            status=CaseStatus.TRIED,
            verdict=Verdict.FULL,
            sentence_kind=SentenceKind.BRIG_TERM,
            sentence_amount=3,
            sentence_ends_at=timezone.now() + timedelta(days=3),
            resolved_at=timezone.now(),
        )

        response = self._get(account, entry)

        case = response.data["case"]
        self.assertIsNotNone(case)
        self.assertEqual(case["sentence_kind"], SentenceKind.BRIG_TERM)
        self.assertEqual(case["sentence_amount"], 3)
        self.assertIsNotNone(case["sentence_ends_at"])
        self.assertIsNone(case["terminal_due_at"])

    def test_pending_terminal_exposes_terminal_due_at(self):
        account, entry = self._pc()
        persona = entry.character_sheet.primary_persona
        JusticeCase.objects.create(
            persona=persona,
            area=self.kingdom,
            society=self.crown,
            prosecution_weight=200,
            status=CaseStatus.TRIED,
            verdict=Verdict.FULL,
            sentence_kind=SentenceKind.EXECUTION,
            terminal_due_at=timezone.now() + timedelta(days=2),
            resolved_at=timezone.now(),
        )

        response = self._get(account, entry)

        case = response.data["case"]
        self.assertIsNotNone(case)
        self.assertEqual(case["sentence_kind"], SentenceKind.EXECUTION)
        self.assertIsNotNone(case["terminal_due_at"])

    def test_served_brig_term_drops_out_of_view(self):
        account, entry = self._pc()
        persona = entry.character_sheet.primary_persona
        JusticeCase.objects.create(
            persona=persona,
            area=self.kingdom,
            society=self.crown,
            prosecution_weight=20,
            status=CaseStatus.TRIED,
            verdict=Verdict.FULL,
            sentence_kind=SentenceKind.BRIG_TERM,
            sentence_amount=3,
            sentence_ends_at=None,  # already served + cleared by the daily sweep
            resolved_at=timezone.now(),
        )

        response = self._get(account, entry)

        self.assertIsNone(response.data["case"])

    def test_no_case_at_all_returns_none(self):
        account, entry = self._pc()

        response = self._get(account, entry)

        self.assertIsNone(response.data["case"])
