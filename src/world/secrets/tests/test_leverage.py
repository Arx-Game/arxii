"""Leverage model + mint/query services (#1680).

Leverage is the standing marker a successful blackmail mints: holder over subject,
founded on a Secret. `mint_leverage` records it (idempotent); `has_leverage` is the
read behind the `has_leverage_over` predicate leaf and the FAVOR offer gate.
"""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.secrets.factories import LeverageFactory, SecretFactory
from world.secrets.models import Leverage
from world.secrets.services import has_leverage, mint_leverage, reveal_leveraged_secret


class MintLeverageTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.holder = CharacterSheetFactory()
        cls.subject = CharacterSheetFactory()
        cls.secret = SecretFactory(subject_sheet=cls.subject)

    def test_mints_a_row(self) -> None:
        leverage = mint_leverage(
            holder_sheet=self.holder, subject_sheet=self.subject, founded_on=self.secret
        )
        self.assertEqual(leverage.holder_sheet, self.holder)
        self.assertEqual(leverage.subject_sheet, self.subject)
        self.assertEqual(leverage.founded_on, self.secret)

    def test_idempotent_on_same_triple(self) -> None:
        first = mint_leverage(
            holder_sheet=self.holder, subject_sheet=self.subject, founded_on=self.secret
        )
        second = mint_leverage(
            holder_sheet=self.holder, subject_sheet=self.subject, founded_on=self.secret
        )
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Leverage.objects.count(), 1)

    def test_unique_constraint_enforced(self) -> None:
        LeverageFactory(
            holder_sheet=self.holder, subject_sheet=self.subject, founded_on=self.secret
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Leverage.objects.create(
                holder_sheet=self.holder, subject_sheet=self.subject, founded_on=self.secret
            )


class HasLeverageTests(TestCase):
    def test_true_when_leverage_exists(self) -> None:
        lev = LeverageFactory()
        self.assertTrue(
            has_leverage(holder_sheet=lev.holder_sheet, subject_sheet=lev.subject_sheet)
        )

    def test_false_without_leverage(self) -> None:
        self.assertFalse(
            has_leverage(
                holder_sheet=CharacterSheetFactory(), subject_sheet=CharacterSheetFactory()
            )
        )

    def test_scoped_to_the_pair(self) -> None:
        lev = LeverageFactory()
        other = CharacterSheetFactory()
        # holder holds leverage over subject, not over an unrelated sheet
        self.assertFalse(has_leverage(holder_sheet=lev.holder_sheet, subject_sheet=other))
        # and an unrelated holder has none over subject
        self.assertFalse(has_leverage(holder_sheet=other, subject_sheet=lev.subject_sheet))


class RevealLeveragedSecretTests(TestCase):
    def test_reveal_fires_and_spends_the_leverage(self) -> None:
        lev = LeverageFactory()  # holder_sheet / subject_sheet / founded_on (a Secret)
        fired = reveal_leveraged_secret(revealer_sheet=lev.holder_sheet, secret=lev.founded_on)
        self.assertTrue(fired)
        # The secret is out — every leverage founded on it is spent.
        self.assertFalse(Leverage.objects.filter(founded_on=lev.founded_on).exists())

    def test_reveal_without_leverage_is_a_noop(self) -> None:
        secret = SecretFactory()
        fired = reveal_leveraged_secret(revealer_sheet=CharacterSheetFactory(), secret=secret)
        self.assertFalse(fired)
