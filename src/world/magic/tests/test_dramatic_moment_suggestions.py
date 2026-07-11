"""Tests for the technique-entrance suggestion bridge (#2183).

Task 3 of the dramatic-technique-driven-combat-entrance feature: the
DramaticMomentSuggestion model + maybe_suggest_dramatic_moments /
resolve_dramatic_moment_suggestion services + the "Grand Entrance" seed. Nothing
calls these services yet — Tasks 4/5/6 wire the actual technique-entrance cast
path to maybe_suggest_dramatic_moments and a GM-facing resolve surface to
resolve_dramatic_moment_suggestion.
"""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import GainSource, SuggestionStatus
from world.magic.exceptions import DramaticMomentSuggestionAlreadyResolved
from world.magic.factories import (
    CharacterResonanceFactory,
    DramaticMomentTagFactory,
    DramaticMomentTypeFactory,
    ResonanceFactory,
    ensure_dramatic_entrance_content,
)
from world.magic.models import CharacterResonance, ResonanceGrant
from world.magic.models.dramatic_moment import DramaticMomentSuggestion, DramaticMomentType
from world.magic.services.gain import (
    maybe_suggest_dramatic_moments,
    resolve_dramatic_moment_suggestion,
)
from world.scenes.factories import InteractionFactory, SceneFactory


class MaybeSuggestDramaticMomentsTest(TestCase):
    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=0,
            lifetime_earned=0,
        )
        self.moment_type = DramaticMomentTypeFactory(
            resonance=self.resonance,
            suggest_on_technique_entrance=True,
            suggestion_min_success_level=3,
            per_scene_cap=1,
        )
        self.scene = SceneFactory()
        self.interaction = InteractionFactory(scene=self.scene)

    def test_suggest_creates_pending_rows(self):
        created = maybe_suggest_dramatic_moments(
            character_sheet=self.sheet,
            scene=self.scene,
            success_level=3,
            interaction=self.interaction,
        )
        self.assertEqual(len(created), 1)
        suggestion = created[0]
        self.assertEqual(suggestion.status, SuggestionStatus.PENDING)
        self.assertEqual(suggestion.success_level, 3)
        self.assertEqual(suggestion.scene, self.scene)
        self.assertEqual(suggestion.interaction, self.interaction)
        self.assertEqual(suggestion.interaction_timestamp, self.interaction.timestamp)
        self.assertEqual(
            DramaticMomentSuggestion.objects.filter(status=SuggestionStatus.PENDING).count(), 1
        )

    def test_suggest_respects_threshold(self):
        created = maybe_suggest_dramatic_moments(
            character_sheet=self.sheet,
            scene=self.scene,
            success_level=2,
        )
        self.assertEqual(created, [])
        self.assertFalse(DramaticMomentSuggestion.objects.exists())

    def test_suggest_skips_unflagged(self):
        self.moment_type.suggest_on_technique_entrance = False
        self.moment_type.save()
        created = maybe_suggest_dramatic_moments(
            character_sheet=self.sheet,
            scene=self.scene,
            success_level=5,
        )
        self.assertEqual(created, [])
        self.assertFalse(DramaticMomentSuggestion.objects.exists())

    def test_suggest_skips_unclaimed_resonance(self):
        other_sheet = CharacterSheetFactory()
        created = maybe_suggest_dramatic_moments(
            character_sheet=other_sheet,
            scene=self.scene,
            success_level=5,
        )
        self.assertEqual(created, [])
        self.assertFalse(DramaticMomentSuggestion.objects.exists())

    def test_suggest_skips_capped(self):
        DramaticMomentTagFactory(
            moment_type=self.moment_type,
            character_sheet=self.sheet,
            scene=self.scene,
        )
        created = maybe_suggest_dramatic_moments(
            character_sheet=self.sheet,
            scene=self.scene,
            success_level=5,
        )
        self.assertEqual(created, [])
        self.assertFalse(DramaticMomentSuggestion.objects.exists())

    def test_suggest_idempotent_per_scene(self):
        first = maybe_suggest_dramatic_moments(
            character_sheet=self.sheet,
            scene=self.scene,
            success_level=3,
        )
        self.assertEqual(len(first), 1)
        second = maybe_suggest_dramatic_moments(
            character_sheet=self.sheet,
            scene=self.scene,
            success_level=4,
        )
        self.assertEqual(second, [])
        self.assertEqual(
            DramaticMomentSuggestion.objects.filter(status=SuggestionStatus.PENDING).count(), 1
        )

    def test_suggest_returns_empty_without_scene(self):
        created = maybe_suggest_dramatic_moments(
            character_sheet=self.sheet,
            scene=None,
            success_level=5,
        )
        self.assertEqual(created, [])
        self.assertFalse(DramaticMomentSuggestion.objects.exists())


class ResolveDramaticMomentSuggestionTest(TestCase):
    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=0,
            lifetime_earned=0,
        )
        self.moment_type = DramaticMomentTypeFactory(
            resonance=self.resonance,
            resonance_amount=15,
            suggest_on_technique_entrance=True,
            suggestion_min_success_level=3,
        )
        self.scene = SceneFactory()
        self.resolver = AccountFactory()
        [self.suggestion] = maybe_suggest_dramatic_moments(
            character_sheet=self.sheet,
            scene=self.scene,
            success_level=4,
        )

    def test_confirm_creates_tag_and_links(self):
        resolved = resolve_dramatic_moment_suggestion(
            self.suggestion, resolver=self.resolver, confirm=True
        )
        self.assertEqual(resolved.status, SuggestionStatus.CONFIRMED)
        self.assertIsNotNone(resolved.confirmed_tag)
        self.assertEqual(resolved.resolved_by, self.resolver)
        cr = CharacterResonance.objects.get(character_sheet=self.sheet, resonance=self.resonance)
        self.assertEqual(cr.balance, 15)
        grant = ResonanceGrant.objects.get(source=GainSource.DRAMATIC_MOMENT)
        self.assertEqual(grant.amount, 15)

    def test_dismiss_no_tag(self):
        resolved = resolve_dramatic_moment_suggestion(
            self.suggestion, resolver=self.resolver, confirm=False
        )
        self.assertEqual(resolved.status, SuggestionStatus.DISMISSED)
        self.assertIsNone(resolved.confirmed_tag)
        self.assertEqual(resolved.resolved_by, self.resolver)
        self.assertFalse(ResonanceGrant.objects.filter(source=GainSource.DRAMATIC_MOMENT).exists())

    def test_double_resolve_raises(self):
        resolve_dramatic_moment_suggestion(self.suggestion, resolver=self.resolver, confirm=False)
        with self.assertRaises(DramaticMomentSuggestionAlreadyResolved):
            resolve_dramatic_moment_suggestion(
                self.suggestion, resolver=self.resolver, confirm=True
            )


class EnsureDramaticEntranceContentTest(TestCase):
    def test_seed_idempotent(self):
        first = ensure_dramatic_entrance_content()
        second = ensure_dramatic_entrance_content()
        self.assertEqual(first.pk, second.pk)
        qs = DramaticMomentType.objects.filter(label="Grand Entrance")
        self.assertEqual(qs.count(), 1)
        moment_type = qs.get()
        self.assertTrue(moment_type.suggest_on_technique_entrance)
        self.assertEqual(moment_type.suggestion_min_success_level, 3)

    def test_seed_preserves_staff_edits(self):
        """A re-run must not clobber staff tuning of the existing row (#2183)."""
        first = ensure_dramatic_entrance_content()
        first.resonance_amount = 999
        first.save(update_fields=["resonance_amount"])

        second = ensure_dramatic_entrance_content()

        self.assertEqual(first.pk, second.pk)
        qs = DramaticMomentType.objects.filter(label="Grand Entrance")
        self.assertEqual(qs.count(), 1)
        moment_type = qs.get()
        self.assertEqual(moment_type.resonance_amount, 999)
