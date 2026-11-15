"""Imbuing, weaving and gift provisioning write ThreadResonance rows (#5123)."""

from django.test import TestCase

from actions.definitions.imbue import ImbueAction
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.exceptions import (
    ANCHOR_ALREADY_WOVEN_MESSAGE,
    ResonanceInsufficient,
    ThreadAnchorTakenError,
)
from world.magic.factories import (
    CharacterResonanceFactory,
    CharacterThreadWeavingUnlockFactory,
    GiftFactory,
    ImbuingRitualFactory,
    ResonanceFactory,
    ThreadFactory,
    ThreadPullEffectFactory,
    ThreadWeavingUnlockFactory,
)
from world.magic.models import (
    CharacterResonance,
    PendingRitualEffect,
    Thread,
    ThreadLevelUnlock,
    ThreadResonance,
)
from world.magic.services import spend_resonance_for_imbuing
from world.magic.services.threads import imbue_ready_threads, thread_level_multiplier, weave_thread
from world.magic.specialization.services import gift_resonances_for, provision_latent_gift_thread
from world.traits.factories import TraitFactory


class ImbueRowsTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.fury = ResonanceFactory(name="Fury")
        cls.domination = ResonanceFactory(name="Domination")
        cls.wonder = ResonanceFactory(name="Wonder")

    def setUp(self) -> None:
        # Level 10 owner (level cap 100), every XP boundary paid, so only the bucket decides.
        self.sheet = CharacterSheetFactory(_class_level=10)
        for resonance in (self.fury, self.domination, self.wonder):
            CharacterResonanceFactory(character_sheet=self.sheet, resonance=resonance, balance=1000)

    def _thread(self, *, level: int = 10) -> Thread:
        thread = ThreadFactory(
            owner=self.sheet,
            resonance=self.fury,
            level=level,
            developed_points=0,
            _trait_value=999,
        )
        for boundary in range(10, 110, 10):
            ThreadLevelUnlock.objects.create(thread=thread, unlocked_level=boundary, xp_spent=0)
        return thread

    def test_imbue_adds_to_named_row_and_developed_points(self) -> None:
        thread = self._thread()

        spend_resonance_for_imbuing(self.sheet, thread, self.domination, 30)

        thread.refresh_from_db()
        row = ThreadResonance.objects.get(thread=thread, resonance=self.domination)
        self.assertEqual(row.amount, 30)
        self.assertEqual(thread.developed_points, 30)
        balance = self.sheet.character.resonances.balance(self.domination)
        self.assertEqual(balance, 970)

    def test_imbue_new_resonance_creates_row(self) -> None:
        thread = self._thread()
        self.assertEqual(ThreadResonance.objects.filter(thread=thread).count(), 1)

        spend_resonance_for_imbuing(self.sheet, thread, self.wonder, 5)

        rows = {r.resonance_id: r.amount for r in ThreadResonance.objects.filter(thread=thread)}
        self.assertEqual(rows, {self.fury.pk: 0, self.wonder.pk: 5})

    def test_levelling_never_lowers_a_row(self) -> None:
        thread = self._thread()

        spend_resonance_for_imbuing(self.sheet, thread, self.fury, 60)
        spend_resonance_for_imbuing(self.sheet, thread, self.domination, 90)

        thread.refresh_from_db()
        self.assertEqual(thread.level, 11)  # the 150 in the bucket paid 100 for level 11
        self.assertEqual(thread.developed_points, 50)
        rows = {r.resonance_id: r.amount for r in ThreadResonance.objects.filter(thread=thread)}
        self.assertEqual(rows, {self.fury.pk: 60, self.domination.pk: 90})

    def test_leading_flips_when_second_overtakes(self) -> None:
        thread = self._thread(level=9)  # Fury's 10 raises it to level 10 before Domination
        fury_bump = ThreadPullEffectFactory(
            target_kind=TargetKind.TRAIT, resonance=self.fury, as_intensity_bump=True
        )
        domination_bump = ThreadPullEffectFactory(
            target_kind=TargetKind.TRAIT,
            resonance=self.domination,
            as_intensity_bump=True,
            intensity_bump_amount=7,
        )
        handler = self.sheet.character.threads

        spend_resonance_for_imbuing(self.sheet, thread, self.fury, 10)
        self.assertEqual(thread.level, 10)
        scale = thread_level_multiplier(thread.level)
        self.assertEqual(thread.resonance, self.fury)
        self.assertEqual(
            handler._tier0_intensity_bumps[thread.pk],
            round(fury_bump.intensity_bump_amount * scale),
        )

        spend_resonance_for_imbuing(self.sheet, thread, self.domination, 15)

        thread.refresh_from_db()
        rows = {r.resonance_id: r.amount for r in ThreadResonance.objects.filter(thread=thread)}
        self.assertEqual(rows, {self.fury.pk: 10, self.domination.pk: 15})
        self.assertEqual(thread.resonance, self.domination)
        self.assertEqual(
            self.sheet.character.threads._tier0_intensity_bumps[thread.pk],
            round(domination_bump.intensity_bump_amount * scale),
        )

    def test_resonance_not_held_is_refused(self) -> None:
        thread = self._thread()
        stranger = ResonanceFactory(name="Stranger")

        with self.assertRaises(ResonanceInsufficient):
            spend_resonance_for_imbuing(self.sheet, thread, stranger, 1)

        self.assertFalse(ThreadResonance.objects.filter(thread=thread, resonance=stranger).exists())

    def _set_balances(self, **balances: int) -> None:
        """Set each held resonance's balance by lowercase name, zero for the rest."""
        for cr in CharacterResonance.objects.filter(character_sheet=self.sheet):
            cr.balance = balances.get(cr.resonance.name.lower(), 0)
            cr.save(update_fields=["balance"])
        self.sheet.character.resonances.invalidate()

    def test_ready_when_any_held_resonance_has_balance(self) -> None:
        thread = self._thread()

        # Fury leads the thread and has nothing; Wonder, which has no row, can still imbue it.
        self._set_balances(wonder=3)
        self.assertIn(thread, imbue_ready_threads(self.sheet))

        self._set_balances()
        self.assertNotIn(thread, imbue_ready_threads(self.sheet))

    def test_gift_thread_takes_a_resonance_off_the_gifts_list(self) -> None:
        gift = GiftFactory()
        gift.resonances.add(self.fury, self.wonder)
        thread = provision_latent_gift_thread(self.sheet, gift, resonances=[self.fury])

        spend_resonance_for_imbuing(self.sheet, thread, self.domination, 5)

        self.assertTrue(
            ThreadResonance.objects.filter(thread=thread, resonance=self.domination).exists()
        )

    def test_gift_thread_is_ready_on_any_funded_resonance(self) -> None:
        gift = GiftFactory()
        gift.resonances.add(self.fury)
        thread = provision_latent_gift_thread(self.sheet, gift, resonances=[self.fury])

        self._set_balances(domination=3)
        self.assertIn(thread, imbue_ready_threads(self.sheet))

        self._set_balances()
        self.assertNotIn(thread, imbue_ready_threads(self.sheet))

    def test_action_names_the_paying_resonance(self) -> None:
        thread = self._thread()
        PendingRitualEffect.objects.get_or_create(
            character=self.sheet, ritual=ImbuingRitualFactory()
        )

        result = ImbueAction().run(
            actor=self.sheet.character,
            thread=thread,
            amount=12,
            resonance_id=self.domination.pk,
        )

        self.assertTrue(result.success, result.message)
        row = ThreadResonance.objects.get(thread=thread, resonance=self.domination)
        self.assertEqual(row.amount, 12)

    def test_action_refuses_a_resonance_id_that_is_not_one(self) -> None:
        thread = self._thread()
        PendingRitualEffect.objects.get_or_create(
            character=self.sheet, ritual=ImbuingRitualFactory()
        )

        for bad in ("abc", 0, 10**9):
            result = ImbueAction().run(
                actor=self.sheet.character, thread=thread, amount=1, resonance_id=bad
            )
            self.assertFalse(result.success)
            self.assertEqual(result.message, f"No resonance with id {bad}.")
        self.assertEqual(ThreadResonance.objects.get(thread=thread).amount, 0)

    def test_action_defaults_to_the_leading_resonance(self) -> None:
        thread = self._thread()
        PendingRitualEffect.objects.get_or_create(
            character=self.sheet, ritual=ImbuingRitualFactory()
        )

        result = ImbueAction().run(actor=self.sheet.character, thread=thread, amount=12)

        self.assertTrue(result.success, result.message)
        self.assertEqual(ThreadResonance.objects.get(thread=thread, resonance=self.fury).amount, 12)


class WeaveRowsTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.fury = ResonanceFactory(name="Fury")
        cls.domination = ResonanceFactory(name="Domination")
        cls.sheet = CharacterSheetFactory()
        cls.trait = TraitFactory()
        CharacterThreadWeavingUnlockFactory(
            character=cls.sheet, unlock=ThreadWeavingUnlockFactory(unlock_trait=cls.trait)
        )

    def test_weave_writes_the_named_resonance_row(self) -> None:
        thread = weave_thread(self.sheet, TargetKind.TRAIT, self.trait, self.fury)

        rows = list(ThreadResonance.objects.filter(thread=thread))
        self.assertEqual([(r.resonance, r.amount) for r in rows], [(self.fury, 0)])
        self.assertEqual(thread.resonance, self.fury)

    def test_weave_existing_anchor_refused(self) -> None:
        weave_thread(self.sheet, TargetKind.TRAIT, self.trait, self.fury)

        with self.assertRaises(ThreadAnchorTakenError) as raised:
            weave_thread(self.sheet, TargetKind.TRAIT, self.trait, self.domination)

        self.assertEqual(raised.exception.user_message, ANCHOR_ALREADY_WOVEN_MESSAGE)
        self.assertEqual(
            Thread.objects.filter(owner=self.sheet, target_trait=self.trait).count(), 1
        )

    def test_weave_gift_existing_thread_refused(self) -> None:
        gift = GiftFactory()
        provision_latent_gift_thread(self.sheet, gift, resonances=[self.fury])

        with self.assertRaises(ThreadAnchorTakenError):
            weave_thread(self.sheet, TargetKind.GIFT, gift, self.domination)


class GiftRowsTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.fury = ResonanceFactory(name="Fury")
        cls.domination = ResonanceFactory(name="Domination")
        cls.wonder = ResonanceFactory(name="Wonder")
        cls.gift = GiftFactory()

    def test_provision_writes_rows_at_zero_in_the_order_given(self) -> None:
        sheet = CharacterSheetFactory()

        thread = provision_latent_gift_thread(
            sheet, self.gift, resonances=[self.fury, self.domination, self.wonder]
        )

        rows = list(ThreadResonance.objects.filter(thread=thread).order_by("id"))
        self.assertEqual(
            [(r.resonance, r.amount) for r in rows],
            [(self.fury, 0), (self.domination, 0), (self.wonder, 0)],
        )
        self.assertEqual(thread.resonance, self.fury)

    def test_provision_is_idempotent_on_the_gift(self) -> None:
        sheet = CharacterSheetFactory()
        first = provision_latent_gift_thread(sheet, self.gift, resonances=[self.fury])
        second = provision_latent_gift_thread(sheet, self.gift, resonances=[self.domination])

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ThreadResonance.objects.filter(thread=first).count(), 1)

    def test_gift_resonances_in_row_order(self) -> None:
        sheet = CharacterSheetFactory(_class_level=10)
        CharacterResonanceFactory(character_sheet=sheet, resonance=self.domination, balance=50)
        thread = provision_latent_gift_thread(
            sheet, self.gift, resonances=[self.fury, self.domination, self.wonder]
        )
        character = sheet.character

        self.assertEqual(
            gift_resonances_for(character, self.gift), [self.fury, self.domination, self.wonder]
        )

        thread.level = 10  # past the one-point levels, so the 5 stays in the bucket
        thread.save(update_fields=["level"])
        spend_resonance_for_imbuing(sheet, thread, self.domination, 5)

        # Domination now holds the most, so it leads, then the zero rows in creation order.
        self.assertEqual(
            gift_resonances_for(character, self.gift), [self.domination, self.fury, self.wonder]
        )
