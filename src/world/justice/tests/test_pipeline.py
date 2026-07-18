"""Justice pipeline tests (#2378) — triggers, evasion, evidence, trial, wall."""

from unittest.mock import patch

from django.test import TestCase

from world.justice.constants import (
    EXECUTION_MIN_FAILED_OUTS,
    HUNTED_VALUE_FLOOR,
    MAX_VALUE_FLOOR,
    WANTED_VALUE_FLOOR,
    CaseStatus,
    EncounterOutcome,
    GuardTrigger,
    SentenceKind,
    Verdict,
)
from world.justice.models import GuardEncounter, JusticeCase, PersonaHeat
from world.justice.pipeline import (
    JusticePipelineError,
    exculpatory_total,
    expose_exculpatory,
    initiate_trial,
    maybe_guard_encounter,
    release_threshold,
    resolve_guard_encounter,
    submit_exculpatory,
)
from world.justice.tests.test_services import JusticeFixtureMixin
from world.scenes.factories import PersonaFactory


class _FireRng:
    def random(self) -> float:
        return 0.0  # always under the pct → fires


class _NeverRng:
    def random(self) -> float:
        return 0.999999


def _heat(persona, area, society, value):
    return PersonaHeat.objects.create(persona=persona, area=area, society=society, value=value)


class TriggerLadderTests(JusticeFixtureMixin, TestCase):
    def test_below_wanted_nothing_fires(self):
        _heat(self.persona, self.kingdom, self.crown, WANTED_VALUE_FLOOR - 1)
        for trigger in GuardTrigger:
            self.assertIsNone(
                maybe_guard_encounter(self.persona, self.kingdom, trigger, rng=_FireRng())
            )

    def test_wanted_fires_only_on_npc_transaction(self):
        _heat(self.persona, self.kingdom, self.crown, WANTED_VALUE_FLOOR)
        self.assertIsNone(
            maybe_guard_encounter(
                self.persona, self.kingdom, GuardTrigger.PUBLIC_INTERACTION, rng=_FireRng()
            )
        )
        self.assertIsNone(
            maybe_guard_encounter(
                self.persona, self.kingdom, GuardTrigger.ROOM_ARRIVAL, rng=_FireRng()
            )
        )
        enc = maybe_guard_encounter(
            self.persona, self.kingdom, GuardTrigger.NPC_TRANSACTION, rng=_FireRng()
        )
        self.assertIsNotNone(enc)

    def test_hunted_adds_public_interaction(self):
        _heat(self.persona, self.kingdom, self.crown, HUNTED_VALUE_FLOOR)
        enc = maybe_guard_encounter(
            self.persona, self.kingdom, GuardTrigger.PUBLIC_INTERACTION, rng=_FireRng()
        )
        self.assertIsNotNone(enc)
        # Room arrival still needs max.
        enc.resolved_at = enc.opened_at
        enc.save(update_fields=["resolved_at"])
        self.assertIsNone(
            maybe_guard_encounter(
                self.persona, self.kingdom, GuardTrigger.ROOM_ARRIVAL, rng=_FireRng()
            )
        )

    def test_max_fires_on_room_arrival_and_rng_gate(self):
        _heat(self.persona, self.kingdom, self.crown, MAX_VALUE_FLOOR)
        self.assertIsNone(
            maybe_guard_encounter(
                self.persona, self.kingdom, GuardTrigger.ROOM_ARRIVAL, rng=_NeverRng()
            )
        )
        enc = maybe_guard_encounter(
            self.persona, self.kingdom, GuardTrigger.ROOM_ARRIVAL, rng=_FireRng()
        )
        self.assertIsNotNone(enc)

    def test_open_encounter_and_case_suppress(self):
        _heat(self.persona, self.kingdom, self.crown, MAX_VALUE_FLOOR)
        maybe_guard_encounter(self.persona, self.kingdom, GuardTrigger.ROOM_ARRIVAL, rng=_FireRng())
        self.assertIsNone(
            maybe_guard_encounter(
                self.persona, self.kingdom, GuardTrigger.ROOM_ARRIVAL, rng=_FireRng()
            )
        )
        GuardEncounter.objects.all().delete()
        JusticeCase.objects.create(persona=self.persona, area=self.kingdom, society=self.crown)
        self.assertIsNone(
            maybe_guard_encounter(
                self.persona, self.kingdom, GuardTrigger.ROOM_ARRIVAL, rng=_FireRng()
            )
        )


class EvasionTests(JusticeFixtureMixin, TestCase):
    def _encounter(self, value=MAX_VALUE_FLOOR):
        _heat(self.persona, self.kingdom, self.crown, value)
        return maybe_guard_encounter(
            self.persona, self.kingdom, GuardTrigger.ROOM_ARRIVAL, rng=_FireRng()
        )

    def test_clean_escape(self):
        enc = resolve_guard_encounter(self._encounter(), check_level=2)
        self.assertEqual(enc.outcome, EncounterOutcome.ESCAPED)
        self.assertFalse(JusticeCase.objects.exists())

    def test_seen_escape_bumps_heat(self):
        enc = self._encounter()
        before = PersonaHeat.objects.get(persona=self.persona, area=self.kingdom).value
        resolve_guard_encounter(enc, check_level=-1)
        after = PersonaHeat.objects.get(persona=self.persona, area=self.kingdom).value
        self.assertGreater(after, before)
        self.assertFalse(JusticeCase.objects.exists())

    def test_botch_captures_and_opens_case(self):
        enc = self._encounter()
        with patch("world.captivity.services.capture_character", return_value=None):
            resolve_guard_encounter(enc, check_level=-3)
        case = JusticeCase.objects.get()
        self.assertEqual(case.persona, self.persona)
        self.assertEqual(case.society, self.crown)
        self.assertEqual(case.prosecution_weight, MAX_VALUE_FLOOR)
        self.assertEqual(case.status, CaseStatus.AWAITING_TRIAL)


class EvidenceTests(JusticeFixtureMixin, TestCase):
    def _case(self, weight=100):
        return JusticeCase.objects.create(
            persona=self.persona,
            area=self.kingdom,
            society=self.crown,
            prosecution_weight=weight,
        )

    def test_threshold_release(self):
        case = self._case(weight=40)  # threshold = 20
        helper = PersonaFactory()
        submit_exculpatory(case, helper)  # 10
        case.refresh_from_db()
        self.assertEqual(case.status, CaseStatus.AWAITING_TRIAL)
        submit_exculpatory(case, helper)  # 20 → released
        case.refresh_from_db()
        self.assertEqual(case.status, CaseStatus.RELEASED_EVIDENCE)

    def test_manufactured_is_banded_and_never_negative(self):
        case = self._case(weight=1000)
        helper = PersonaFactory()
        good = submit_exculpatory(case, helper, manufactured=True, check_level=2)
        bad = submit_exculpatory(case, helper, manufactured=True, check_level=-3)
        self.assertGreater(good.weight, 0)
        self.assertEqual(bad.weight, 0)
        self.assertGreaterEqual(exculpatory_total(case), good.weight)

    def test_exposure_backfires_on_submitter_only(self):
        case = self._case(weight=40)
        helper = PersonaFactory()
        evidence = submit_exculpatory(case, helper, manufactured=True, check_level=2)
        submit_exculpatory(case, helper)
        submit_exculpatory(case, helper)
        case.refresh_from_db()
        released_status = case.status
        with patch("world.justice.services.accrue_heat") as mock_accrue:
            expose_exculpatory(evidence)
        mock_accrue.assert_called_once()
        self.assertEqual(mock_accrue.call_args.kwargs["persona"], helper)
        case.refresh_from_db()
        self.assertEqual(case.status, released_status)  # never worsens the accused

    def test_closed_case_rejects_submissions(self):
        case = self._case()
        case.status = CaseStatus.TRIED
        case.save(update_fields=["status"])
        with self.assertRaises(JusticePipelineError):
            submit_exculpatory(case, PersonaFactory())

    def test_release_threshold_floor(self):
        self.assertGreaterEqual(release_threshold(self._case(weight=2)), 10)


class TrialTests(JusticeFixtureMixin, TestCase):
    def _case(self, weight=50, persona=None):
        return JusticeCase.objects.create(
            persona=persona or self.persona,
            area=self.kingdom,
            society=self.crown,
            prosecution_weight=weight,
        )

    def test_only_the_accused_initiates(self):
        case = self._case()
        with self.assertRaises(JusticePipelineError):
            initiate_trial(case, PersonaFactory(), check_levels=[3])

    def test_acquittal_on_strong_defense(self):
        case = self._case(weight=10)
        initiate_trial(case, self.persona, check_levels=[3])
        case.refresh_from_db()
        self.assertEqual(case.verdict, Verdict.ACQUITTED)
        self.assertEqual(case.failed_outs, 0)

    def test_full_verdict_fines_and_counts_a_failed_out(self):
        case = self._case(weight=50)
        initiate_trial(case, self.persona, check_levels=[0])
        case.refresh_from_db()
        self.assertEqual(case.verdict, Verdict.FULL)
        self.assertEqual(case.failed_outs, 1)
        self.assertEqual(case.sentence_kind, SentenceKind.FINE)
        self.assertGreater(case.sentence_amount, 0)

    def test_helpers_move_the_verdict(self):
        case = self._case(weight=25)
        helpers = [PersonaFactory(), PersonaFactory()]
        initiate_trial(case, self.persona, helpers, check_levels=[2, 2, 2])
        case.refresh_from_db()
        self.assertEqual(case.verdict, Verdict.ACQUITTED)


class LethalWallTests(JusticeFixtureMixin, TestCase):
    """ADR-0023: NPCs may hang; PCs need opt-in + an exhausted case."""

    def _pc_persona(self, *, opt_in: bool):
        from world.roster.factories import RosterTenureFactory

        tenure = RosterTenureFactory()
        player_data = tenure.player_data
        player_data.lethal_consequences_opt_in = opt_in
        player_data.save(update_fields=["lethal_consequences_opt_in"])
        return tenure.roster_entry.character_sheet.primary_persona

    def _catastrophic_case(self, persona, failed_outs=0):
        return JusticeCase.objects.create(
            persona=persona,
            area=self.kingdom,
            society=self.crown,
            prosecution_weight=MAX_VALUE_FLOOR + 20,
            failed_outs=failed_outs,
        )

    def test_npc_can_be_executed(self):
        case = self._catastrophic_case(self.persona)  # factory persona: no account
        initiate_trial(case, self.persona, check_levels=[-3])
        case.refresh_from_db()
        self.assertEqual(case.sentence_kind, SentenceKind.EXECUTION)

    def test_pc_without_opt_in_never_executes(self):
        persona = self._pc_persona(opt_in=False)
        case = self._catastrophic_case(persona, failed_outs=5)
        initiate_trial(case, persona, check_levels=[-3])
        case.refresh_from_db()
        self.assertEqual(case.sentence_kind, SentenceKind.BRIG_TERM)

    def test_pc_opt_in_still_needs_exhaustion(self):
        persona = self._pc_persona(opt_in=True)
        case = self._catastrophic_case(persona, failed_outs=0)
        initiate_trial(case, persona, check_levels=[-3])
        case.refresh_from_db()
        self.assertEqual(case.sentence_kind, SentenceKind.BRIG_TERM)

    def test_pc_opt_in_and_exhausted_reaches_execution(self):
        persona = self._pc_persona(opt_in=True)
        case = self._catastrophic_case(persona, failed_outs=EXECUTION_MIN_FAILED_OUTS)
        initiate_trial(case, persona, check_levels=[-3])
        case.refresh_from_db()
        self.assertEqual(case.sentence_kind, SentenceKind.EXECUTION)
