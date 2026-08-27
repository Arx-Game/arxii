"""Sentence-ladder consult tests (#2378 Task 4) — rung override + the lethal wall.

Drills ``pipeline._ladder_kind_and_amount`` (wired into ``_apply_sentence``'s
FULL-verdict path) via the public ``initiate_trial`` entry point, plus
``seeds.seed_placeholder_sentence_ladders``. ``ExecutionSentenceTests`` in
``test_sentence_enforcement.py`` covers the non-ladder terminal path; this
module only covers what a ladder rung changes about it.
"""

from django.test import TestCase

from world.justice.constants import (
    BRIG_DAYS_PER_WEIGHT,
    EXECUTION_MIN_FAILED_OUTS,
    MAX_VALUE_FLOOR,
    SentenceKind,
)
from world.justice.factories import SentenceLadderRungFactory
from world.justice.models import JusticeCase
from world.justice.pipeline import initiate_trial
from world.justice.seeds import seed_placeholder_sentence_ladders
from world.justice.tests.test_services import JusticeFixtureMixin
from world.roster.factories import RosterTenureFactory
from world.societies.factories import SocietyFactory


class _LadderCaseMixin(JusticeFixtureMixin):
    def _case(self, *, weight, failed_outs=0, persona=None):
        return JusticeCase.objects.create(
            persona=persona or self.persona,
            area=self.kingdom,
            society=self.crown,
            prosecution_weight=weight,
            failed_outs=failed_outs,
        )

    def _try(self, case, persona=None):
        # check_levels=[-3] with any weight >= 11 lands margin < VERDICT_LESSER_MARGIN,
        # i.e. always a FULL verdict — the ladder consult's gate.
        initiate_trial(case, persona or case.persona, check_levels=[-3])
        case.refresh_from_db()
        return case


class LadderOverrideTests(_LadderCaseMixin, TestCase):
    def test_ladder_rung_overrides_default_kind_at_matching_failed_outs(self):
        # weight=50 (below HUNTED) would default to FINE; the rung overrides it.
        SentenceLadderRungFactory(
            society=self.crown, level=0, sentence_kind=SentenceKind.CONFISCATION
        )
        case = self._case(weight=50, failed_outs=0)  # -> failed_outs=1 post-increment

        case = self._try(case)

        self.assertEqual(case.sentence_kind, SentenceKind.CONFISCATION)
        self.assertEqual(case.sentence_amount, 0)

    def test_higher_rung_wins_at_higher_failed_outs(self):
        SentenceLadderRungFactory(
            society=self.crown, level=0, sentence_kind=SentenceKind.CONFISCATION
        )
        SentenceLadderRungFactory(society=self.crown, level=1, sentence_kind=SentenceKind.EXILE)
        # failed_outs=1 pre -> 2 post: level<=1 matches, level 1 (EXILE) wins over level 0.
        case = self._case(weight=50, failed_outs=1)

        case = self._try(case)

        self.assertEqual(case.sentence_kind, SentenceKind.EXILE)

    def test_no_matching_rung_leaves_default_kind_untouched(self):
        # Rung exists but at a level failed_outs never reaches (level=5).
        SentenceLadderRungFactory(
            society=self.crown, level=5, sentence_kind=SentenceKind.CONFISCATION
        )
        case = self._case(weight=50, failed_outs=0)

        case = self._try(case)

        self.assertEqual(case.sentence_kind, SentenceKind.FINE)

    def test_arena_trial_rung_lands_brig_term(self):
        SentenceLadderRungFactory(
            society=self.crown, level=0, sentence_kind=SentenceKind.ARENA_TRIAL
        )
        case = self._case(weight=50, failed_outs=0)

        case = self._try(case)

        self.assertEqual(case.sentence_kind, SentenceKind.BRIG_TERM)
        self.assertEqual(case.sentence_amount, max(1, 50 * BRIG_DAYS_PER_WEIGHT // 10))

    def test_a_different_societys_rung_never_applies(self):
        other = SocietyFactory()
        SentenceLadderRungFactory(society=other, level=0, sentence_kind=SentenceKind.CONFISCATION)
        case = self._case(weight=50, failed_outs=0)

        case = self._try(case)

        self.assertEqual(case.sentence_kind, SentenceKind.FINE)


class LadderLethalWallTests(_LadderCaseMixin, TestCase):
    def _pc_persona(self, *, opt_in: bool):
        tenure = RosterTenureFactory()
        player_data = tenure.player_data
        player_data.lethal_consequences_opt_in = opt_in
        player_data.save(update_fields=["lethal_consequences_opt_in"])
        return tenure.roster_entry.character_sheet.primary_persona

    def test_execution_rung_falls_back_to_default_when_outs_not_exhausted(self):
        # weight >= MAX, but failed_outs=1 post-increment < EXECUTION_MIN_FAILED_OUTS(2):
        # the wall blocks the rung outright — default band (EXILE) applies instead.
        SentenceLadderRungFactory(society=self.crown, level=0, sentence_kind=SentenceKind.EXECUTION)
        case = self._case(weight=MAX_VALUE_FLOOR, failed_outs=0)

        case = self._try(case)

        self.assertEqual(case.sentence_kind, SentenceKind.EXILE)

    def test_execution_rung_falls_back_to_default_when_weight_too_low(self):
        # failed_outs exhausted, but weight < MAX_VALUE_FLOOR: wall still blocks.
        SentenceLadderRungFactory(society=self.crown, level=0, sentence_kind=SentenceKind.EXECUTION)
        case = self._case(weight=MAX_VALUE_FLOOR - 1, failed_outs=EXECUTION_MIN_FAILED_OUTS - 1)

        case = self._try(case)

        self.assertNotEqual(case.sentence_kind, SentenceKind.EXECUTION)

    def test_execution_rung_reaches_execution_for_npc_when_wall_holds(self):
        SentenceLadderRungFactory(society=self.crown, level=0, sentence_kind=SentenceKind.EXECUTION)
        case = self._case(weight=MAX_VALUE_FLOOR, failed_outs=EXECUTION_MIN_FAILED_OUTS - 1)

        case = self._try(case)

        self.assertEqual(case.sentence_kind, SentenceKind.EXECUTION)

    def test_execution_rung_yields_banishment_for_non_opted_pc(self):
        persona = self._pc_persona(opt_in=False)
        SentenceLadderRungFactory(society=self.crown, level=0, sentence_kind=SentenceKind.EXECUTION)
        case = self._case(
            weight=MAX_VALUE_FLOOR,
            failed_outs=EXECUTION_MIN_FAILED_OUTS - 1,
            persona=persona,
        )

        case = self._try(case, persona=persona)

        self.assertEqual(case.sentence_kind, SentenceKind.BANISHMENT)

    def test_banishment_rung_applies_directly_when_wall_holds(self):
        SentenceLadderRungFactory(
            society=self.crown, level=0, sentence_kind=SentenceKind.BANISHMENT
        )
        case = self._case(weight=MAX_VALUE_FLOOR, failed_outs=EXECUTION_MIN_FAILED_OUTS - 1)

        case = self._try(case)

        self.assertEqual(case.sentence_kind, SentenceKind.BANISHMENT)


class SeedPlaceholderLaddersTests(TestCase):
    def test_seeds_three_rungs_each_for_umbros_and_inferna(self):
        from world.justice.models import SentenceLadderRung

        umbros = SocietyFactory(name="Umbros")
        inferna = SocietyFactory(name="Inferna")

        written = seed_placeholder_sentence_ladders()

        self.assertEqual(written, 6)
        self.assertEqual(SentenceLadderRung.objects.filter(society=umbros).count(), 3)
        self.assertEqual(SentenceLadderRung.objects.filter(society=inferna).count(), 3)
        for rung in SentenceLadderRung.objects.filter(society__in=[umbros, inferna]):
            self.assertEqual(rung.flavor, "PLACEHOLDER")

    def test_seeds_return_zero_when_neither_society_exists(self):
        written = seed_placeholder_sentence_ladders()

        self.assertEqual(written, 0)

    def test_rerun_updates_rather_than_duplicates(self):
        from world.justice.models import SentenceLadderRung

        umbros = SocietyFactory(name="Umbros")
        SocietyFactory(name="Inferna")

        seed_placeholder_sentence_ladders()
        written_again = seed_placeholder_sentence_ladders()

        self.assertEqual(written_again, 6)
        self.assertEqual(SentenceLadderRung.objects.filter(society=umbros).count(), 3)
