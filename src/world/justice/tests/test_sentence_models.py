"""Sentence-enforcement schema tests: ExileDecree + SentenceLadderRung (#2378)."""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from world.justice.constants import SentenceKind
from world.justice.factories import ExileDecreeFactory, SentenceLadderRungFactory
from world.justice.models import ExileDecree


class ExileDecreeActiveForTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.decree = ExileDecreeFactory(ends_at=timezone.now() + timedelta(days=30))

    def test_active_for_returns_current_decree(self):
        active = ExileDecree.active_for(self.decree.persona, self.decree.area)
        self.assertEqual(active, self.decree)

    def test_active_for_returns_none_after_lifted(self):
        self.decree.lifted_at = timezone.now()
        self.decree.save()
        active = ExileDecree.active_for(self.decree.persona, self.decree.area)
        self.assertIsNone(active)

    def test_active_for_returns_permanent_decree(self):
        permanent = ExileDecreeFactory(ends_at=None)
        active = ExileDecree.active_for(permanent.persona, permanent.area)
        self.assertEqual(active, permanent)


class SentenceLadderRungModelTest(TestCase):
    def test_unique_society_level(self):
        rung = SentenceLadderRungFactory(level=0, sentence_kind=SentenceKind.FINE)
        with transaction.atomic(), self.assertRaises(IntegrityError):
            SentenceLadderRungFactory(
                society=rung.society, level=0, sentence_kind=SentenceKind.BRIG_TERM
            )
