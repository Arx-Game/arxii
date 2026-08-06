"""Tests for the grant-time resonance resolver (#2971).

An authored gift can carry an empty ``resonances`` supported set (meaning
"unrestricted" per #2968) — but a granted gift must ALWAYS get a GIFT thread,
or downstream reads (cast resolution, dramatic-moment grants, ...) have
nowhere to read a resonance from. ``_resolve_grant_resonance`` is the shared
policy that fills in a resonance when none is explicitly chosen (or when the
explicit choice doesn't fit a non-empty supported set); ``grant_gift_to_character``
runs every grant through it and always provisions the thread, raising
``GiftResonanceUnresolvable`` only when nothing resolves at all.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.exceptions import GiftResonanceUnresolvable
from world.magic.factories import (
    AffinityFactory,
    CharacterResonanceFactory,
    GiftFactory,
    ResonanceFactory,
    RitualCheckConfigFactory,
)
from world.magic.models import CharacterGift, Thread
from world.magic.specialization.services import (
    _resolve_grant_resonance,
    grant_gift_to_character,
    provision_latent_gift_thread,
)


class ResolveGrantResonanceTests(TestCase):
    """Direct tests of ``_resolve_grant_resonance``'s fallback ladder."""

    def test_empty_set_with_existing_gift_thread_uses_its_resonance(self):
        sheet = CharacterSheetFactory()
        gift = GiftFactory()
        resonance = ResonanceFactory()
        provision_latent_gift_thread(sheet, gift, resonance=resonance)

        resolved = _resolve_grant_resonance(sheet, gift)

        self.assertEqual(resolved, resonance)

    def test_empty_set_no_threads_uses_highest_lifetime_earned_claim(self):
        sheet = CharacterSheetFactory()
        gift = GiftFactory()
        low = ResonanceFactory()
        high = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=sheet, resonance=low, lifetime_earned=5)
        CharacterResonanceFactory(character_sheet=sheet, resonance=high, lifetime_earned=50)

        resolved = _resolve_grant_resonance(sheet, gift)

        self.assertEqual(resolved, high)

    def test_empty_set_no_threads_no_claims_uses_anima_ritual_resonance(self):
        sheet = CharacterSheetFactory()
        gift = GiftFactory()
        ritual_resonance = ResonanceFactory()
        RitualCheckConfigFactory(
            ritual__author_account=sheet.character.db_account,
            resonance=ritual_resonance,
        )

        resolved = _resolve_grant_resonance(sheet, gift)

        self.assertEqual(resolved, ritual_resonance)

    def test_empty_set_with_nothing_at_all_raises(self):
        sheet = CharacterSheetFactory()
        gift = GiftFactory()

        with self.assertRaises(GiftResonanceUnresolvable):
            _resolve_grant_resonance(sheet, gift)

    def test_non_empty_set_with_claimed_member_uses_claimed(self):
        sheet = CharacterSheetFactory()
        affinity = AffinityFactory()
        first = ResonanceFactory(affinity=affinity, name="AAA_grr5")
        claimed = ResonanceFactory(affinity=affinity, name="BBB_grr5")
        gift = GiftFactory()
        gift.resonances.add(first, claimed)
        CharacterResonanceFactory(character_sheet=sheet, resonance=claimed, lifetime_earned=1)

        resolved = _resolve_grant_resonance(sheet, gift)

        self.assertEqual(resolved, claimed)

    def test_non_empty_set_with_no_claim_uses_first_in_set(self):
        sheet = CharacterSheetFactory()
        affinity = AffinityFactory()
        first = ResonanceFactory(affinity=affinity, name="AAA_grr6")
        second = ResonanceFactory(affinity=affinity, name="BBB_grr6")
        gift = GiftFactory()
        gift.resonances.add(second, first)

        resolved = _resolve_grant_resonance(sheet, gift)

        self.assertEqual(resolved, first)

    def test_preferred_excluded_by_non_empty_set_falls_through_to_set_policy(self):
        sheet = CharacterSheetFactory()
        affinity = AffinityFactory()
        in_set = ResonanceFactory(affinity=affinity, name="AAA_grr7")
        also_in_set = ResonanceFactory(affinity=affinity, name="BBB_grr7")
        outside_set = ResonanceFactory()
        gift = GiftFactory()
        gift.resonances.add(in_set, also_in_set)
        CharacterResonanceFactory(character_sheet=sheet, resonance=also_in_set, lifetime_earned=1)

        resolved = _resolve_grant_resonance(sheet, gift, preferred=outside_set)

        self.assertEqual(resolved, also_in_set)
        self.assertNotEqual(resolved, outside_set)

    def test_preferred_in_set_wins(self):
        sheet = CharacterSheetFactory()
        affinity = AffinityFactory()
        first = ResonanceFactory(affinity=affinity, name="AAA_grr7b")
        preferred = ResonanceFactory(affinity=affinity, name="BBB_grr7b")
        gift = GiftFactory()
        gift.resonances.add(first, preferred)

        resolved = _resolve_grant_resonance(sheet, gift, preferred=preferred)

        self.assertEqual(resolved, preferred)


class GrantGiftToCharacterAlwaysProvisionsTests(TestCase):
    """``grant_gift_to_character`` always provisions a thread (#2971)."""

    def test_resonance_none_on_empty_set_gift_provisions_a_thread(self):
        sheet = CharacterSheetFactory()
        gift = GiftFactory()
        ritual_resonance = ResonanceFactory()
        RitualCheckConfigFactory(
            ritual__author_account=sheet.character.db_account,
            resonance=ritual_resonance,
        )

        grant_gift_to_character(sheet, gift)

        gift_threads = [
            t
            for t in sheet.character.threads.all()
            if t.target_kind == TargetKind.GIFT and t.target_gift_id == gift.pk
        ]
        self.assertEqual(len(gift_threads), 1)
        self.assertEqual(gift_threads[0].resonance, ritual_resonance)

    def test_unresolvable_grant_raises_and_mints_no_thread(self):
        """Resolution runs BEFORE the ``CharacterGift`` row is minted (#2971
        review fix), so an unresolvable grant leaves no trace at all — no
        thread AND no CharacterGift. A CharacterGift with no thread is the
        exact corrupted state #2971 exists to eliminate; committing the
        CharacterGift first would just move that state to the failure path.
        """
        sheet = CharacterSheetFactory()
        gift = GiftFactory()

        with self.assertRaises(GiftResonanceUnresolvable):
            grant_gift_to_character(sheet, gift)

        self.assertFalse(
            Thread.objects.filter(
                owner=sheet, target_kind=TargetKind.GIFT, target_gift=gift
            ).exists()
        )
        self.assertFalse(CharacterGift.objects.filter(character=sheet, gift=gift).exists())

    def test_regrant_prefers_direct_hold_over_lower_pk_descendant_thread(self):
        """Covering-thread step must prefer a DIRECT thread on the granted gift
        over a lower-pk thread on a DESCENDANT gift (#2971 final-review fix).

        ``gift_threads_for(character, X)`` returns threads whose ``target_gift``
        is ``X`` itself or a DESCENDANT of ``X`` (``X.pk`` must be in the
        thread's own gift's ``lineage_ids``, which walks from that gift UPWARD
        through its ancestors) — so querying for a CHILD gift never sees a
        thread on its PARENT (the parent isn't a descendant of the child); the
        ambiguous case is the reverse. A thread on the child gift DOES cover
        the parent (the child's lineage includes the parent), so querying for
        the PARENT while the character holds both a lower-pk thread on the
        CHILD and a higher-pk DIRECT thread on the parent itself must resolve
        the direct thread's resonance, not the child's — ``gift_threads_for``
        sorts direct-hold-first regardless of pk order, and the resolver must
        honor that ordering (``covering[0]``) rather than re-sorting by pk
        (``min(covering, key=lambda t: t.pk)``), or the older child-gift thread
        wins and a bare re-grant of the parent mints a second thread on it
        (idempotency in ``provision_latent_gift_thread`` is keyed on the exact
        (owner, gift, resonance) triple).
        """
        sheet = CharacterSheetFactory()
        parent_gift = GiftFactory()
        child_gift = GiftFactory(parent=parent_gift)
        descendant_resonance = ResonanceFactory()
        direct_resonance = ResonanceFactory()

        # Descendant (child-gift) thread minted FIRST (lower pk) — covers the
        # parent via lineage, but is NOT a direct hold on it.
        grant_gift_to_character(sheet, child_gift, resonance=descendant_resonance)
        # Direct thread on the parent gift itself, minted SECOND (higher pk),
        # at a different resonance.
        grant_gift_to_character(sheet, parent_gift, resonance=direct_resonance)
        thread_count_before = Thread.objects.filter(owner=sheet).count()

        resolved = _resolve_grant_resonance(sheet, parent_gift)
        _character_gift, created = grant_gift_to_character(sheet, parent_gift)

        self.assertEqual(resolved, direct_resonance)
        self.assertFalse(created)
        self.assertEqual(Thread.objects.filter(owner=sheet).count(), thread_count_before)
        direct_thread = Thread.objects.get(
            owner=sheet, target_kind=TargetKind.GIFT, target_gift=parent_gift
        )
        self.assertEqual(direct_thread.resonance, direct_resonance)

    def test_regrant_of_owned_gift_is_a_true_noop_using_gifts_own_thread(self):
        """An unconditional re-grant of an already-owned gift must not mint a
        second thread at a different resonance (#2971 spec-review delta).

        The earlier thread (lower pk) sits on a DIFFERENT gift; the resolver
        must prefer the resonance of the thread already covering THIS gift,
        not the earliest GIFT thread across the whole character.
        """
        sheet = CharacterSheetFactory()
        other_gift = GiftFactory()
        gift = GiftFactory()
        earlier_resonance = ResonanceFactory()
        own_resonance = ResonanceFactory()

        grant_gift_to_character(sheet, other_gift, resonance=earlier_resonance)
        grant_gift_to_character(sheet, gift, resonance=own_resonance)
        thread_count_before = Thread.objects.filter(owner=sheet).count()

        _character_gift, created = grant_gift_to_character(sheet, gift)

        self.assertFalse(created)
        self.assertEqual(Thread.objects.filter(owner=sheet).count(), thread_count_before)
        own_thread = Thread.objects.get(owner=sheet, target_kind=TargetKind.GIFT, target_gift=gift)
        self.assertEqual(own_thread.resonance, own_resonance)
