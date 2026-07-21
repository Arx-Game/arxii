"""Tests for the endorsement/resonance-threshold distinction rank-up (#2037 Decision 8).

``DistinctionResonanceRankThreshold`` (``world/magic/models/grants.py``) is the reverse
sidecar of ``DistinctionResonanceGrant``: sustained investment in a Resonance ranks up a
Distinction the character already holds. ``check_distinction_rank_thresholds``
(``world/magic/services/distinction_resonance.py``) is the consumer, called from
``grant_resonance`` only for ``ACCELERATED_GAIN_SOURCES``.
"""

from unittest.mock import patch

from django.contrib import admin as django_admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.distinctions.models import CharacterDistinction
from world.distinctions.types import DistinctionOrigin
from world.magic.constants import GainSource
from world.magic.factories import (
    DistinctionResonanceRankThresholdFactory,
    PoseEndorsementFactory,
    ResonanceFactory,
)
from world.magic.models import ResonanceGrant
from world.magic.models.grants import DistinctionResonanceRankThreshold
from world.magic.services.resonance import grant_resonance


def _endorsement(sheet, resonance):
    return PoseEndorsementFactory(endorsee_sheet=sheet, resonance=resonance)


class CheckDistinctionRankThresholdsTests(TestCase):
    def test_crossing_threshold_via_pose_endorsement_ranks_up_once(self) -> None:
        sheet = CharacterSheetFactory()
        distinction = DistinctionFactory(max_rank=3)
        resonance = ResonanceFactory()
        DistinctionResonanceRankThresholdFactory(
            distinction=distinction,
            resonance=resonance,
            rank=2,
            lifetime_earned_threshold=10,
        )
        cd = CharacterDistinctionFactory(
            character=sheet,
            distinction=distinction,
            rank=1,
            origin=DistinctionOrigin.CHARACTER_CREATION,
        )

        grant_resonance(
            sheet,
            resonance,
            10,
            source=GainSource.POSE_ENDORSEMENT,
            pose_endorsement=_endorsement(sheet, resonance),
        )

        cd.refresh_from_db()
        self.assertEqual(cd.rank, 2)
        # Provenance is first-acquisition history, never rewritten by a rank-up.
        self.assertEqual(cd.origin, DistinctionOrigin.CHARACTER_CREATION)

    def test_repeat_grant_past_threshold_does_not_refire(self) -> None:
        """Ledger-idempotent: current_rank+1 keying moves past the row once crossed."""
        sheet = CharacterSheetFactory()
        distinction = DistinctionFactory(max_rank=3)
        resonance = ResonanceFactory()
        DistinctionResonanceRankThresholdFactory(
            distinction=distinction,
            resonance=resonance,
            rank=2,
            lifetime_earned_threshold=10,
        )
        cd = CharacterDistinctionFactory(character=sheet, distinction=distinction, rank=1)

        grant_resonance(
            sheet,
            resonance,
            10,
            source=GainSource.POSE_ENDORSEMENT,
            pose_endorsement=_endorsement(sheet, resonance),
        )
        cd.refresh_from_db()
        self.assertEqual(cd.rank, 2)

        # A second grant, still well past the (now-passed) rank-2 threshold, must not
        # advance the distinction further — there is no rank-3 threshold authored.
        grant_resonance(
            sheet,
            resonance,
            5,
            source=GainSource.POSE_ENDORSEMENT,
            pose_endorsement=_endorsement(sheet, resonance),
        )
        cd.refresh_from_db()
        self.assertEqual(cd.rank, 2)

    def test_distinction_source_seed_never_triggers(self) -> None:
        """Feedback-loop guard: a DISTINCTION-sourced grant is never accelerated."""
        sheet = CharacterSheetFactory()
        distinction = DistinctionFactory(max_rank=3)
        resonance = ResonanceFactory()
        DistinctionResonanceRankThresholdFactory(
            distinction=distinction,
            resonance=resonance,
            rank=2,
            lifetime_earned_threshold=10,
        )
        cd = CharacterDistinctionFactory(character=sheet, distinction=distinction, rank=1)

        grant_resonance(
            sheet,
            resonance,
            50,
            source=GainSource.DISTINCTION,
            source_character_distinction=cd,
        )

        cd.refresh_from_db()
        self.assertEqual(cd.rank, 1)

    def test_below_threshold_is_noop(self) -> None:
        sheet = CharacterSheetFactory()
        distinction = DistinctionFactory(max_rank=3)
        resonance = ResonanceFactory()
        DistinctionResonanceRankThresholdFactory(
            distinction=distinction,
            resonance=resonance,
            rank=2,
            lifetime_earned_threshold=100,
        )
        cd = CharacterDistinctionFactory(character=sheet, distinction=distinction, rank=1)

        grant_resonance(
            sheet,
            resonance,
            5,
            source=GainSource.POSE_ENDORSEMENT,
            pose_endorsement=_endorsement(sheet, resonance),
        )

        cd.refresh_from_db()
        self.assertEqual(cd.rank, 1)

    def test_unheld_distinction_is_not_granted(self) -> None:
        """RANKS UP HELD DISTINCTIONS ONLY — never mints one fresh."""
        sheet = CharacterSheetFactory()
        distinction = DistinctionFactory(max_rank=3)
        resonance = ResonanceFactory()
        DistinctionResonanceRankThresholdFactory(
            distinction=distinction,
            resonance=resonance,
            rank=1,
            lifetime_earned_threshold=5,
        )

        grant_resonance(
            sheet,
            resonance,
            10,
            source=GainSource.POSE_ENDORSEMENT,
            pose_endorsement=_endorsement(sheet, resonance),
        )

        self.assertFalse(
            CharacterDistinction.objects.filter(character=sheet, distinction=distinction).exists()
        )

    def test_multi_threshold_catch_up_in_one_grant(self) -> None:
        """Documented choice: loop to a fully caught-up final state per grant call."""
        sheet = CharacterSheetFactory()
        distinction = DistinctionFactory(max_rank=4)
        resonance = ResonanceFactory()
        DistinctionResonanceRankThresholdFactory(
            distinction=distinction, resonance=resonance, rank=2, lifetime_earned_threshold=10
        )
        DistinctionResonanceRankThresholdFactory(
            distinction=distinction, resonance=resonance, rank=3, lifetime_earned_threshold=20
        )
        DistinctionResonanceRankThresholdFactory(
            distinction=distinction, resonance=resonance, rank=4, lifetime_earned_threshold=30
        )
        cd = CharacterDistinctionFactory(character=sheet, distinction=distinction, rank=1)

        # One grant that jumps lifetime_earned straight past all three thresholds.
        grant_resonance(
            sheet,
            resonance,
            35,
            source=GainSource.POSE_ENDORSEMENT,
            pose_endorsement=_endorsement(sheet, resonance),
        )

        cd.refresh_from_db()
        self.assertEqual(cd.rank, 4)

    def test_exclusion_conflict_is_caught_and_does_not_raise(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        distinction_a = DistinctionFactory(max_rank=2)
        distinction_b = DistinctionFactory(max_rank=1)
        distinction_a.mutually_exclusive_with.add(distinction_b)
        DistinctionResonanceRankThresholdFactory(
            distinction=distinction_a, resonance=resonance, rank=2, lifetime_earned_threshold=5
        )
        cd_a = CharacterDistinctionFactory(character=sheet, distinction=distinction_a, rank=1)
        CharacterDistinctionFactory(character=sheet, distinction=distinction_b, rank=1)

        # Must not raise — the exclusion conflict is caught, logged, and skipped.
        grant_resonance(
            sheet,
            resonance,
            10,
            source=GainSource.POSE_ENDORSEMENT,
            pose_endorsement=_endorsement(sheet, resonance),
        )

        cd_a.refresh_from_db()
        self.assertEqual(cd_a.rank, 1)

    def test_threshold_check_exception_does_not_break_the_grant(self) -> None:
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()

        with patch(
            "world.magic.services.distinction_resonance.check_distinction_rank_thresholds",
            side_effect=RuntimeError("boom"),
        ):
            cr = grant_resonance(
                sheet,
                resonance,
                7,
                source=GainSource.POSE_ENDORSEMENT,
                pose_endorsement=_endorsement(sheet, resonance),
            )

        self.assertEqual(cr.balance, 7)
        self.assertEqual(cr.lifetime_earned, 7)
        self.assertTrue(
            ResonanceGrant.objects.filter(character_sheet=sheet, resonance=resonance).exists()
        )


class DistinctionResonanceRankThresholdAdminTest(TestCase):
    def test_registered_and_editable(self) -> None:
        self.assertIn(DistinctionResonanceRankThreshold, django_admin.site._registry)
        user_model = get_user_model()
        superuser = user_model.objects.create_superuser(
            "threshold_admin", "threshold_admin@example.com", "pw"
        )
        request = RequestFactory().get("/")
        request.user = superuser
        model_admin = django_admin.site._registry[DistinctionResonanceRankThreshold]
        self.assertTrue(model_admin.has_add_permission(request))
        self.assertTrue(model_admin.has_change_permission(request))
