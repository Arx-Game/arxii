"""Verdict notifications + brig visitation advert (#2378 Task 6)."""

from unittest import mock

from django.test import TestCase

from world.captivity.factories import CaptivityFactory
from world.justice.constants import Verdict
from world.justice.models import ExculpatoryEvidence, JusticeCase
from world.justice.notifications import notify_brig_visitation, notify_verdict
from world.justice.pipeline import initiate_trial
from world.justice.sentences import sentence_sweep_tick
from world.justice.tests.test_services import JusticeFixtureMixin
from world.narrative.constants import NarrativeCategory
from world.narrative.models import NarrativeMessageDelivery
from world.roster.factories import RosterTenureFactory
from world.scenes.factories import PersonaFactory
from world.scenes.friend_services import add_friend


class _CaseMixin(JusticeFixtureMixin):
    def _case(self, *, weight, failed_outs=0, persona=None):
        return JusticeCase.objects.create(
            persona=persona or self.persona,
            area=self.kingdom,
            society=self.crown,
            prosecution_weight=weight,
            failed_outs=failed_outs,
        )

    def _hold(self, case, *, sheet=None):
        sheet = sheet or case.persona.character_sheet
        captivity = CaptivityFactory(captive=sheet)
        case.captivity = captivity
        case.save(update_fields=["captivity"])
        return captivity


class VerdictNotificationTests(_CaseMixin, TestCase):
    def test_acquittal_notifies_accused_and_submitter_deduped(self):
        case = self._case(weight=0)
        submitter = PersonaFactory()
        ExculpatoryEvidence.objects.create(case=case, submitter_persona=submitter, weight=0)

        # margin = 0*ADVOCACY_WEIGHT_PER_LEVEL - 0 (weight) = 0 >= VERDICT_ACQUIT_MARGIN.
        initiate_trial(case, case.persona, check_levels=[0])
        case.refresh_from_db()
        self.assertEqual(case.verdict, "acquitted")

        accused_sheet = case.persona.character_sheet
        submitter_sheet = submitter.character_sheet
        deliveries = NarrativeMessageDelivery.objects.filter(
            message__category=NarrativeCategory.JUSTICE
        )
        self.assertEqual(
            set(deliveries.values_list("recipient_character_sheet_id", flat=True)),
            {accused_sheet.pk, submitter_sheet.pk},
        )

    def test_notify_verdict_dedupes_when_submitter_is_the_accused(self):
        case = self._case(weight=0)
        case.verdict = Verdict.ACQUITTED
        case.save(update_fields=["verdict"])
        ExculpatoryEvidence.objects.create(case=case, submitter_persona=case.persona, weight=0)

        count = notify_verdict(case)

        self.assertEqual(count, 1)

    def test_guilty_verdict_body_includes_sentence_line(self):
        # weight below HUNTED_VALUE_FLOOR, no advocacy → FULL verdict, FINE sentence.
        case = self._case(weight=50)
        self._hold(case)

        initiate_trial(case, case.persona, check_levels=[-3])
        case.refresh_from_db()
        self.assertEqual(case.verdict, "full")
        self.assertTrue(case.sentence_kind)

        delivery = (
            NarrativeMessageDelivery.objects.filter(
                message__category=NarrativeCategory.JUSTICE,
                recipient_character_sheet=case.persona.character_sheet,
            )
            .select_related("message")
            .first()
        )
        self.assertIsNotNone(delivery)
        self.assertIn("PLACEHOLDER: The magistrates of", delivery.message.body)
        self.assertIn(" - sentence: ", delivery.message.body)

    def test_notify_verdict_reaches_the_accused_with_no_submitters(self):
        # Baseline: the accused's own sheet always counts, even with no submitters.
        case = self._case(weight=0)
        case.verdict = Verdict.ACQUITTED
        case.save(update_fields=["verdict"])

        count = notify_verdict(case)

        self.assertEqual(count, 1)


class BrigVisitationTests(_CaseMixin, TestCase):
    def _pc_persona(self):
        tenure = RosterTenureFactory()
        return tenure, tenure.roster_entry.character_sheet.primary_persona

    def test_brig_sentence_notifies_active_friends(self):
        accused_tenure, accused_persona = self._pc_persona()
        watcher_tenure = RosterTenureFactory()
        add_friend(friender_tenure=watcher_tenure, friend_tenure=accused_tenure)

        case = self._case(weight=120, failed_outs=1, persona=accused_persona)
        self._hold(case, sheet=accused_persona.character_sheet)

        watcher_account = watcher_tenure.player_data.account
        with mock.patch.object(watcher_account, "msg", create=True) as mock_msg:
            initiate_trial(case, accused_persona, check_levels=[-3])

        case.refresh_from_db()
        self.assertEqual(case.sentence_kind, "brig_term")
        mock_msg.assert_called_once()
        (call_text,), _kwargs = mock_msg.call_args
        self.assertIn("PLACEHOLDER (OOC): ", call_text)
        self.assertIn("is imprisoned in", call_text)

    def test_ended_friendship_is_not_notified(self):
        accused_tenure, accused_persona = self._pc_persona()
        watcher_tenure = RosterTenureFactory()
        add_friend(friender_tenure=watcher_tenure, friend_tenure=accused_tenure)
        watcher_tenure.end_date = watcher_tenure.start_date
        watcher_tenure.save(update_fields=["end_date"])

        case = self._case(weight=120, failed_outs=1, persona=accused_persona)
        self._hold(case, sheet=accused_persona.character_sheet)

        count = notify_brig_visitation(case)

        self.assertEqual(count, 0)

    def test_dedupes_by_account_across_multiple_watching_tenures(self):
        accused_tenure, accused_persona = self._pc_persona()
        watcher_tenure = RosterTenureFactory()
        second_watcher_tenure = RosterTenureFactory(player_data=watcher_tenure.player_data)
        add_friend(friender_tenure=watcher_tenure, friend_tenure=accused_tenure)
        add_friend(friender_tenure=second_watcher_tenure, friend_tenure=accused_tenure)

        case = self._case(weight=120, failed_outs=1, persona=accused_persona)
        self._hold(case, sheet=accused_persona.character_sheet)

        watcher_account = watcher_tenure.player_data.account
        with mock.patch.object(watcher_account, "msg", create=True):
            count = notify_brig_visitation(case)

        self.assertEqual(count, 1)


class SweepReNotifyTests(_CaseMixin, TestCase):
    def test_sweep_carrying_out_a_terminal_sentence_renotifies(self):
        from datetime import timedelta

        from django.utils import timezone

        from world.justice.constants import EXECUTION_MIN_FAILED_OUTS, MAX_VALUE_FLOOR

        persona = self.persona
        case = self._case(
            weight=MAX_VALUE_FLOOR, failed_outs=EXECUTION_MIN_FAILED_OUTS - 1, persona=persona
        )
        self._hold(case)
        initiate_trial(case, persona, check_levels=[-3])
        case.refresh_from_db()

        deliveries_before = NarrativeMessageDelivery.objects.filter(
            message__category=NarrativeCategory.JUSTICE
        ).count()
        self.assertGreater(deliveries_before, 0)

        case.terminal_due_at = timezone.now() - timedelta(days=1)
        case.save(update_fields=["terminal_due_at"])

        sentence_sweep_tick()

        deliveries_after = NarrativeMessageDelivery.objects.filter(
            message__category=NarrativeCategory.JUSTICE
        ).count()
        self.assertGreater(deliveries_after, deliveries_before)
