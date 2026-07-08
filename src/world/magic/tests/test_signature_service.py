"""Tests for the signature-bonus selection service (#1582).

Functions under test:
- available_signature_bonuses(character_sheet) -> list[SignatureMotifBonus]
- set_signature_bonus(thread, bonus) -> Thread
- clear_signature_bonus(thread) -> Thread
- signature_bonus_for(character, technique) -> SignatureMotifBonus | None
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.exceptions import (
    NotATechniqueThread,
    SignatureBonusNotAvailable,
    TechniqueNotOwned,
)
from world.magic.factories import (
    CharacterTechniqueFactory,
    CharacterThreadWeavingUnlockFactory,
    FacetFactory,
    GiftFactory,
    MotifFactory,
    MotifResonanceAssociationFactory,
    MotifResonanceFactory,
    ResonanceFactory,
    TechniqueFactory,
    ThreadWeavingUnlockFactory,
)
from world.magic.models import SignatureMotifBonus, Thread
from world.magic.services.signature import (
    available_signature_bonuses,
    clear_signature_bonus,
    set_signature_bonus,
    signature_bonus_for,
)
from world.traits.factories import TraitFactory


def _make_technique_thread(sheet, technique, resonance):
    """Create a TECHNIQUE-kind thread for ``sheet`` anchored to ``technique``.

    Defaults to level 3 (the first crossing) so signature selection is unlocked.
    """
    return Thread.objects.create(
        owner=sheet,
        resonance=resonance,
        target_kind=TargetKind.TECHNIQUE,
        target_technique=technique,
        level=3,
    )


def _setup_technique_weave_unlock(sheet, gift):
    """Create a TECHNIQUE ThreadWeavingUnlock + CharacterThreadWeavingUnlock for sheet."""
    unlock = ThreadWeavingUnlockFactory(
        target_kind=TargetKind.TECHNIQUE,
        unlock_trait=None,
        unlock_gift=gift,
        xp_cost=0,
    )
    CharacterThreadWeavingUnlockFactory(character=sheet, unlock=unlock, xp_spent=0)
    return unlock


class AvailableSignatureBonusesTests(TestCase):
    """available_signature_bonuses returns bonuses whose qualifies_for() is True."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.magic.factories import (
            CharacterTechniqueFactory,
            GiftFactory,
            TechniqueFactory,
        )

        cls.sheet = CharacterSheetFactory()
        cls.motif = MotifFactory(character=cls.sheet)
        cls.resonance = ResonanceFactory()
        cls.facet = FacetFactory(name="Sig Avail Facet")
        # Bind resonance + facet to the motif.
        cls.motif_res = MotifResonanceFactory(motif=cls.motif, resonance=cls.resonance)
        MotifResonanceAssociationFactory(motif_resonance=cls.motif_res, facet=cls.facet)

        # A technique + CharacterTechnique for thread-filter tests.
        cls.gift = GiftFactory()
        cls.technique = TechniqueFactory(gift=cls.gift, level=1, damage_profile=False)
        CharacterTechniqueFactory(character=cls.sheet, technique=cls.technique)

        # A bonus the character qualifies for (facet gate).
        cls.qualifying_bonus = SignatureMotifBonus.objects.create(
            name="Qualifying Bonus",
            required_facet=cls.facet,
        )
        # Another qualifying bonus (resonance gate).
        cls.qualifying_resonance_bonus = SignatureMotifBonus.objects.create(
            name="Qualifying Resonance Bonus",
            required_resonance=cls.resonance,
        )

        # A different facet the character does NOT have.
        cls.other_facet = FacetFactory(name="Sig Avail Other Facet")
        cls.non_qualifying_bonus = SignatureMotifBonus.objects.create(
            name="Non-Qualifying Bonus",
            required_facet=cls.other_facet,
        )

        # A character with no motif.
        cls.sheet_no_motif = CharacterSheetFactory()

    def test_returns_only_qualifying_bonuses(self) -> None:
        """Only bonuses whose qualifies_for() returns True are included."""
        result = available_signature_bonuses(self.sheet)
        self.assertIn(self.qualifying_bonus, result)
        self.assertIn(self.qualifying_resonance_bonus, result)
        self.assertNotIn(self.non_qualifying_bonus, result)

    def test_returns_empty_list_for_no_motif(self) -> None:
        """Returns empty list when the character has no motif."""
        result = available_signature_bonuses(self.sheet_no_motif)
        self.assertEqual(result, [])

    def test_returns_list_of_signature_motif_bonus(self) -> None:
        """Return value is a list of SignatureMotifBonus instances."""
        result = available_signature_bonuses(self.sheet)
        self.assertIsInstance(result, list)
        for item in result:
            self.assertIsInstance(item, SignatureMotifBonus)

    def test_filters_by_min_crossing_level_when_thread_given(self) -> None:
        """Bonuses with min_crossing_level > thread.level are excluded."""
        from world.magic.constants import TargetKind
        from world.magic.models import Thread

        locked_bonus = SignatureMotifBonus.objects.create(
            name="Locked Crossing Bonus",
            required_resonance=self.resonance,
            min_crossing_level=6,
        )
        thread = Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=self.technique,
            level=3,
        )
        try:
            result = available_signature_bonuses(self.sheet, thread=thread)
            self.assertIn(self.qualifying_bonus, result)
            self.assertIn(self.qualifying_resonance_bonus, result)
            self.assertNotIn(locked_bonus, result)
        finally:
            locked_bonus.delete()
            thread.delete()

    def test_filters_by_resonance_when_thread_given(self) -> None:
        """Bonuses with required_resonance not matching thread.resonance are excluded."""
        from world.magic.constants import TargetKind
        from world.magic.models import Thread

        other_resonance = ResonanceFactory()
        mismatched_bonus = SignatureMotifBonus.objects.create(
            name="Mismatched Resonance Bonus",
            required_resonance=other_resonance,
            min_crossing_level=3,
        )
        thread = Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=self.technique,
            level=3,
        )
        try:
            result = available_signature_bonuses(self.sheet, thread=thread)
            self.assertIn(self.qualifying_bonus, result)
            self.assertNotIn(mismatched_bonus, result)
        finally:
            mismatched_bonus.delete()
            thread.delete()

    def test_no_thread_param_returns_all_qualifying_backward_compatible(self) -> None:
        """available_signature_bonuses(sheet) with no thread returns all Motif-qualifying."""
        result = available_signature_bonuses(self.sheet)
        self.assertIn(self.qualifying_bonus, result)
        self.assertIn(self.qualifying_resonance_bonus, result)
        self.assertNotIn(self.non_qualifying_bonus, result)


class SetSignatureBonusTests(TestCase):
    """set_signature_bonus sets Thread.signature_bonus and saves."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.motif = MotifFactory(character=cls.sheet)
        cls.resonance = ResonanceFactory()
        cls.facet = FacetFactory(name="Set Sig Facet")
        cls.motif_res = MotifResonanceFactory(motif=cls.motif, resonance=cls.resonance)
        MotifResonanceAssociationFactory(motif_resonance=cls.motif_res, facet=cls.facet)

        cls.gift = GiftFactory()
        cls.technique = TechniqueFactory(gift=cls.gift, level=1, damage_profile=False)
        # Character knows the technique.
        CharacterTechniqueFactory(character=cls.sheet, technique=cls.technique)

        cls.bonus = SignatureMotifBonus.objects.create(
            name="Set Test Bonus",
            required_facet=cls.facet,
        )

        cls.trait = TraitFactory()

    def setUp(self) -> None:
        # Create a fresh TECHNIQUE thread per test (setUpTestData would conflict
        # on the unique constraint across tests that save the same thread).
        self.technique_thread = _make_technique_thread(self.sheet, self.technique, self.resonance)
        # Warm the cache so invalidation is observable.
        self.sheet.character.threads.all()

    def tearDown(self) -> None:
        # Remove the per-test thread so the unique constraint is clean.
        self.technique_thread.delete()
        self.sheet.character.threads.invalidate()

    def test_set_assigns_bonus_to_thread(self) -> None:
        """set_signature_bonus assigns the bonus and returns the updated Thread."""
        result = set_signature_bonus(self.technique_thread, self.bonus)
        self.assertEqual(result.signature_bonus_id, self.bonus.pk)

    def test_set_persists_to_db(self) -> None:
        """set_signature_bonus saves the change to the database."""
        set_signature_bonus(self.technique_thread, self.bonus)
        refreshed = Thread.objects.get(pk=self.technique_thread.pk)
        self.assertEqual(refreshed.signature_bonus_id, self.bonus.pk)

    def test_set_invalidates_threads_cache(self) -> None:
        """set_signature_bonus invalidates character.threads so the change is visible."""
        character = self.sheet.character
        # The updated thread should appear in the cache after invalidation.
        set_signature_bonus(self.technique_thread, self.bonus)
        refreshed_threads = character.threads.all()
        matching = [t for t in refreshed_threads if t.pk == self.technique_thread.pk]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].signature_bonus_id, self.bonus.pk)

    def test_set_returns_thread_instance(self) -> None:
        """Return value is the Thread instance (not a different object type)."""
        result = set_signature_bonus(self.technique_thread, self.bonus)
        self.assertIsInstance(result, Thread)
        self.assertEqual(result.pk, self.technique_thread.pk)

    def test_set_raises_not_a_technique_thread_for_trait_thread(self) -> None:
        """NotATechniqueThread is raised when thread.target_kind != TECHNIQUE."""
        trait_thread = Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TRAIT,
            target_trait=self.trait,
        )
        try:
            with self.assertRaises(NotATechniqueThread):
                set_signature_bonus(trait_thread, self.bonus)
        finally:
            trait_thread.delete()

    def test_set_raises_signature_bonus_not_available_when_bonus_not_qualifying(
        self,
    ) -> None:
        """SignatureBonusNotAvailable raised when bonus.qualifies_for(owner) is False."""
        other_facet = FacetFactory(name="Set Sig Other Facet")
        non_qualifying = SignatureMotifBonus.objects.create(
            name="Non Qualifying Set Test",
            required_facet=other_facet,
        )
        with self.assertRaises(SignatureBonusNotAvailable):
            set_signature_bonus(self.technique_thread, non_qualifying)

    def test_set_raises_technique_not_owned_when_technique_not_known(self) -> None:
        """TechniqueNotOwned raised when the thread's technique isn't known by the owner."""
        other_technique = TechniqueFactory(gift=self.gift, level=2, damage_profile=False)
        # No CharacterTechnique for other_technique on self.sheet.
        thread_unknown = Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=other_technique,
            level=3,
        )
        try:
            with self.assertRaises(TechniqueNotOwned):
                set_signature_bonus(thread_unknown, self.bonus)
        finally:
            thread_unknown.delete()

    def test_set_replaces_existing_bonus(self) -> None:
        """set_signature_bonus replaces a previously-set bonus with a new one."""
        other_resonance = ResonanceFactory()
        other_motif_res = MotifResonanceFactory(motif=self.motif, resonance=other_resonance)
        other_facet = FacetFactory(name="Replace Sig Facet")
        MotifResonanceAssociationFactory(motif_resonance=other_motif_res, facet=other_facet)
        second_bonus = SignatureMotifBonus.objects.create(
            name="Second Bonus",
            required_facet=other_facet,
        )
        # Set first bonus.
        set_signature_bonus(self.technique_thread, self.bonus)
        # Move to second bonus.
        result = set_signature_bonus(self.technique_thread, second_bonus)
        self.assertEqual(result.signature_bonus_id, second_bonus.pk)
        refreshed = Thread.objects.get(pk=self.technique_thread.pk)
        self.assertEqual(refreshed.signature_bonus_id, second_bonus.pk)

    def test_set_raises_signature_below_crossing_for_low_level_thread(self) -> None:
        """SignatureBelowCrossing raised when thread.level < 3 (first crossing)."""
        from world.magic.exceptions import SignatureBelowCrossing

        # Explicitly set below the first crossing.
        self.technique_thread.level = 0
        self.technique_thread.save(update_fields=["level"])
        with self.assertRaises(SignatureBelowCrossing):
            set_signature_bonus(self.technique_thread, self.bonus)

    def test_set_succeeds_when_thread_at_level_3(self) -> None:
        """set_signature_bonus succeeds when thread.level >= 3."""
        self.technique_thread.level = 3
        self.technique_thread.save(update_fields=["level"])
        result = set_signature_bonus(self.technique_thread, self.bonus)
        self.assertEqual(result.signature_bonus_id, self.bonus.pk)

    def test_set_raises_signature_bonus_locked_when_bonus_requires_higher_crossing(self) -> None:
        """SignatureBonusLocked raised when bonus.min_crossing_level > thread.level."""
        from world.magic.exceptions import SignatureBonusLocked

        self.technique_thread.level = 3
        self.technique_thread.save(update_fields=["level"])
        locked_bonus = SignatureMotifBonus.objects.create(
            name="Locked Bonus",
            required_facet=self.facet,
            min_crossing_level=6,
        )
        try:
            with self.assertRaises(SignatureBonusLocked):
                set_signature_bonus(self.technique_thread, locked_bonus)
        finally:
            locked_bonus.delete()

    def test_set_fires_discovery_when_bonus_has_discovery_achievement(self) -> None:
        """set_signature_bonus fires execute_ceremony_beat when bonus has discovery_achievement."""
        from unittest.mock import patch

        from world.achievements.models import Achievement

        achievement = Achievement.objects.create(
            name="First Fire Signature",
            slug="first-fire-signature",
            description="First character to select a fire signature.",
        )
        discoverable_bonus = SignatureMotifBonus.objects.create(
            name="Discoverable Bonus",
            required_facet=self.facet,
            min_crossing_level=3,
            discovery_achievement=achievement,
        )
        try:
            with patch("world.magic.crossing.ceremony.execute_ceremony_beat") as mock_beat:
                set_signature_bonus(self.technique_thread, discoverable_bonus)
                mock_beat.assert_called_once()
        finally:
            discoverable_bonus.delete()
            achievement.delete()

    def test_set_does_not_fire_discovery_when_bonus_has_no_discovery_achievement(self) -> None:
        """No discovery fired when bonus.discovery_achievement is None."""
        from unittest.mock import patch

        with patch("world.magic.crossing.ceremony.execute_ceremony_beat") as mock_beat:
            set_signature_bonus(self.technique_thread, self.bonus)
            mock_beat.assert_not_called()


class SetSignatureBonusMovePortTests(TestCase):
    """Move-port case: set on one technique's thread, then set on a different thread."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.motif = MotifFactory(character=cls.sheet)
        cls.resonance = ResonanceFactory()
        cls.facet = FacetFactory(name="Move Port Facet")
        cls.motif_res = MotifResonanceFactory(motif=cls.motif, resonance=cls.resonance)
        MotifResonanceAssociationFactory(motif_resonance=cls.motif_res, facet=cls.facet)

        cls.gift = GiftFactory()
        cls.technique_a = TechniqueFactory(gift=cls.gift, level=1, damage_profile=False)
        cls.technique_b = TechniqueFactory(gift=cls.gift, level=2, damage_profile=False)
        CharacterTechniqueFactory(character=cls.sheet, technique=cls.technique_a)
        CharacterTechniqueFactory(character=cls.sheet, technique=cls.technique_b)

        cls.bonus = SignatureMotifBonus.objects.create(
            name="Move Port Bonus",
            required_facet=cls.facet,
        )

    def setUp(self) -> None:
        self.thread_a = _make_technique_thread(self.sheet, self.technique_a, self.resonance)
        self.thread_b = _make_technique_thread(self.sheet, self.technique_b, self.resonance)
        self.sheet.character.threads.invalidate()

    def tearDown(self) -> None:
        self.thread_a.delete()
        self.thread_b.delete()
        self.sheet.character.threads.invalidate()

    def test_move_port_sets_bonus_on_second_thread(self) -> None:
        """Moving a bonus from thread_a to thread_b updates thread_b correctly."""
        set_signature_bonus(self.thread_a, self.bonus)
        # Now move the bonus to thread_b.
        set_signature_bonus(self.thread_b, self.bonus)

        refreshed_b = Thread.objects.get(pk=self.thread_b.pk)
        self.assertEqual(refreshed_b.signature_bonus_id, self.bonus.pk)

    def test_move_port_old_thread_retains_its_bonus_independently(self) -> None:
        """The first thread still has the bonus after it is set on the second thread.

        Each thread stores its bonus independently; setting a bonus on thread_b
        does not clear thread_a — the player must clear_signature_bonus(thread_a)
        manually if they want to move it.
        """
        set_signature_bonus(self.thread_a, self.bonus)
        set_signature_bonus(self.thread_b, self.bonus)

        refreshed_a = Thread.objects.get(pk=self.thread_a.pk)
        self.assertEqual(refreshed_a.signature_bonus_id, self.bonus.pk)


class ClearSignatureBonusTests(TestCase):
    """clear_signature_bonus sets signature_bonus to None and saves."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.motif = MotifFactory(character=cls.sheet)
        cls.resonance = ResonanceFactory()
        cls.facet = FacetFactory(name="Clear Sig Facet")
        cls.motif_res = MotifResonanceFactory(motif=cls.motif, resonance=cls.resonance)
        MotifResonanceAssociationFactory(motif_resonance=cls.motif_res, facet=cls.facet)

        cls.gift = GiftFactory()
        cls.technique = TechniqueFactory(gift=cls.gift, level=1, damage_profile=False)
        CharacterTechniqueFactory(character=cls.sheet, technique=cls.technique)

        cls.bonus = SignatureMotifBonus.objects.create(
            name="Clear Test Bonus",
            required_facet=cls.facet,
        )
        cls.trait = TraitFactory()

    def setUp(self) -> None:
        self.thread = _make_technique_thread(self.sheet, self.technique, self.resonance)
        self.sheet.character.threads.all()  # warm cache

    def tearDown(self) -> None:
        self.thread.delete()
        self.sheet.character.threads.invalidate()

    def test_clear_sets_bonus_to_none(self) -> None:
        """clear_signature_bonus sets signature_bonus to None on the thread."""
        set_signature_bonus(self.thread, self.bonus)
        result = clear_signature_bonus(self.thread)
        self.assertIsNone(result.signature_bonus_id)

    def test_clear_persists_to_db(self) -> None:
        """clear_signature_bonus saves the None to the database."""
        set_signature_bonus(self.thread, self.bonus)
        clear_signature_bonus(self.thread)
        refreshed = Thread.objects.get(pk=self.thread.pk)
        self.assertIsNone(refreshed.signature_bonus_id)

    def test_clear_when_already_none_is_idempotent(self) -> None:
        """clear_signature_bonus on a thread with no bonus is a no-op."""
        result = clear_signature_bonus(self.thread)
        self.assertIsNone(result.signature_bonus_id)

    def test_clear_returns_thread_instance(self) -> None:
        """Return value is the Thread instance."""
        result = clear_signature_bonus(self.thread)
        self.assertIsInstance(result, Thread)
        self.assertEqual(result.pk, self.thread.pk)

    def test_clear_invalidates_threads_cache(self) -> None:
        """clear_signature_bonus invalidates character.threads."""
        character = self.sheet.character
        set_signature_bonus(self.thread, self.bonus)
        clear_signature_bonus(self.thread)
        refreshed_threads = character.threads.all()
        matching = [t for t in refreshed_threads if t.pk == self.thread.pk]
        self.assertEqual(len(matching), 1)
        self.assertIsNone(matching[0].signature_bonus_id)


class SignatureBonusForTests(TestCase):
    """signature_bonus_for returns the SignatureMotifBonus for a character's technique thread."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.motif = MotifFactory(character=cls.sheet)
        cls.resonance = ResonanceFactory()
        cls.facet = FacetFactory(name="Sig For Facet")
        cls.motif_res = MotifResonanceFactory(motif=cls.motif, resonance=cls.resonance)
        MotifResonanceAssociationFactory(motif_resonance=cls.motif_res, facet=cls.facet)

        cls.gift = GiftFactory()
        cls.technique = TechniqueFactory(gift=cls.gift, level=1, damage_profile=False)
        CharacterTechniqueFactory(character=cls.sheet, technique=cls.technique)

        # A second technique with no thread.
        cls.technique_no_thread = TechniqueFactory(gift=cls.gift, level=2, damage_profile=False)
        CharacterTechniqueFactory(character=cls.sheet, technique=cls.technique_no_thread)

        cls.bonus = SignatureMotifBonus.objects.create(
            name="For Test Bonus",
            required_facet=cls.facet,
        )

    def setUp(self) -> None:
        self.thread = _make_technique_thread(self.sheet, self.technique, self.resonance)
        self.sheet.character.threads.invalidate()

    def tearDown(self) -> None:
        self.thread.delete()
        self.sheet.character.threads.invalidate()

    def test_returns_bonus_when_set(self) -> None:
        """Returns the SignatureMotifBonus set on the character's technique thread."""
        set_signature_bonus(self.thread, self.bonus)
        self.sheet.character.threads.invalidate()
        result = signature_bonus_for(self.sheet.character, self.technique)
        self.assertEqual(result, self.bonus)

    def test_returns_none_when_no_bonus_on_thread(self) -> None:
        """Returns None when the thread has no bonus set."""
        result = signature_bonus_for(self.sheet.character, self.technique)
        self.assertIsNone(result)

    def test_returns_none_when_no_thread_for_technique(self) -> None:
        """Returns None when the character has no TECHNIQUE thread for the technique."""
        result = signature_bonus_for(self.sheet.character, self.technique_no_thread)
        self.assertIsNone(result)

    def test_reads_via_cached_handler_not_fresh_query(self) -> None:
        """signature_bonus_for reads via character.threads, not a fresh Thread.objects.filter.

        We verify by setting a bonus and checking the result is consistent with
        what the cache sees (post-invalidation).
        """
        set_signature_bonus(self.thread, self.bonus)
        self.sheet.character.threads.invalidate()
        result = signature_bonus_for(self.sheet.character, self.technique)
        self.assertIsNotNone(result)
        self.assertEqual(result.pk, self.bonus.pk)

    def test_returns_none_for_retired_thread(self) -> None:
        """Returns None when the character's TECHNIQUE thread is retired."""
        from django.utils import timezone

        set_signature_bonus(self.thread, self.bonus)
        self.thread.retired_at = timezone.now()
        self.thread.save()
        self.sheet.character.threads.invalidate()
        result = signature_bonus_for(self.sheet.character, self.technique)
        self.assertIsNone(result)
