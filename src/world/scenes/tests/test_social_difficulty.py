"""Affection-derived social difficulty + relative shifts (#1697)."""

from types import SimpleNamespace

from django.test import TestCase

from world.scenes.action_constants import DIFFICULTY_VALUES, DifficultyChoice
from world.scenes.social_difficulty import resolved_base_difficulty


def _request(*, category, tier_modifier=0):
    """A minimal SceneActionRequest stand-in for the difficulty helper (it reads template only)."""
    template = SimpleNamespace(category=category, difficulty_tier_modifier=tier_modifier)
    return SimpleNamespace(action_template=template, initiator_persona=None)


class ResolvedBaseDifficultyTests(TestCase):
    def test_non_social_uses_absolute_choice(self) -> None:
        req = _request(category="magic")
        value = resolved_base_difficulty(
            action_request=req, difficulty_choice=DifficultyChoice.HARD, target_sheet=None
        )
        self.assertEqual(value, DIFFICULTY_VALUES[DifficultyChoice.HARD])

    def test_social_neutral_no_target_is_normal(self) -> None:
        # No target_sheet → affection 0 (neutral); defender NORMAL → no shift → Normal.
        req = _request(category="social")
        value = resolved_base_difficulty(
            action_request=req, difficulty_choice=DifficultyChoice.NORMAL, target_sheet=None
        )
        self.assertEqual(value, DIFFICULTY_VALUES[DifficultyChoice.NORMAL])

    def test_defender_hard_shifts_one_tier_above_the_derived_base(self) -> None:
        # Neutral base (Normal) + defender HARD (+1 tier relative to Normal) → Hard.
        req = _request(category="social")
        value = resolved_base_difficulty(
            action_request=req, difficulty_choice=DifficultyChoice.HARD, target_sheet=None
        )
        self.assertEqual(value, DIFFICULTY_VALUES[DifficultyChoice.HARD])

    def test_seduce_tier_modifier_adds_a_tier(self) -> None:
        # Neutral base (Normal) + defender NORMAL (no shift) + Seduce (+1 tier) → Hard.
        req = _request(category="social", tier_modifier=1)
        value = resolved_base_difficulty(
            action_request=req, difficulty_choice=DifficultyChoice.NORMAL, target_sheet=None
        )
        self.assertEqual(value, DIFFICULTY_VALUES[DifficultyChoice.HARD])

    def test_clamps_at_the_top_tier(self) -> None:
        # Defender DAUNTING (+2) + Seduce (+1) from Normal base → clamps at Harrowing (top).
        req = _request(category="social", tier_modifier=1)
        value = resolved_base_difficulty(
            action_request=req, difficulty_choice=DifficultyChoice.DAUNTING, target_sheet=None
        )
        self.assertEqual(value, DIFFICULTY_VALUES[DifficultyChoice.HARROWING])


class AffectionTierLadderTests(TestCase):
    """The #1697 ladder: one tier per affection band, rungs from the #1699 system tracks."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.seeds.relationship_scale import seed_relationship_scale_content

        seed_relationship_scale_content()

    def setUp(self) -> None:
        from evennia.utils.idmapper.models import flush_cache

        from world.character_sheets.factories import CharacterSheetFactory

        flush_cache()
        self.actor_sheet = CharacterSheetFactory()
        self.target_sheet = CharacterSheetFactory()

    def _social_request(self, tier_modifier: int = 0):
        template = SimpleNamespace(category="social", difficulty_tier_modifier=tier_modifier)
        persona = SimpleNamespace(character_sheet=self.actor_sheet)
        return SimpleNamespace(action_template=template, initiator_persona=persona)

    def _give_affection(self, amount: int) -> None:
        """Give the target amount affection toward the actor via system-track points."""
        from world.relationships.constants import TrackSystemKey
        from world.relationships.models import (
            CharacterRelationship,
            RelationshipTrack,
            RelationshipTrackProgress,
        )

        key = TrackSystemKey.REGARD if amount > 0 else TrackSystemKey.FRICTION
        track = RelationshipTrack.objects.get(system_key=key)
        relationship, _ = CharacterRelationship.objects.get_or_create(
            source=self.target_sheet, target=self.actor_sheet
        )
        RelationshipTrackProgress.objects.create(
            relationship=relationship,
            track=track,
            capacity=abs(amount),
            developed_points=abs(amount),
        )

    def _value(self, tier_modifier: int = 0) -> int:
        return resolved_base_difficulty(
            action_request=self._social_request(tier_modifier),
            difficulty_choice=DifficultyChoice.NORMAL,
            target_sheet=self.target_sheet,
        )

    def test_one_band_of_warmth_eases_one_tier(self) -> None:
        self._give_affection(25)
        self.assertEqual(self._value(), DIFFICULTY_VALUES[DifficultyChoice.EASY])

    def test_two_bands_of_warmth_ease_two_tiers(self) -> None:
        self._give_affection(100)
        self.assertEqual(self._value(), DIFFICULTY_VALUES[DifficultyChoice.TRIVIAL])

    def test_one_band_of_dislike_hardens_one_tier(self) -> None:
        self._give_affection(-25)
        self.assertEqual(self._value(), DIFFICULTY_VALUES[DifficultyChoice.HARD])

    def test_deep_hostility_clamps_at_harrowing(self) -> None:
        self._give_affection(-2000)
        self.assertEqual(self._value(), DIFFICULTY_VALUES[DifficultyChoice.HARROWING])

    def test_below_first_band_stays_normal(self) -> None:
        self._give_affection(10)
        self.assertEqual(self._value(), DIFFICULTY_VALUES[DifficultyChoice.NORMAL])

    def test_exploitable_condition_eases_rolls_against_the_bearer(self) -> None:
        from world.conditions.services import apply_condition
        from world.seeds.social_actions import ensure_smitten_condition

        smitten = ensure_smitten_condition()
        apply_condition(self.target_sheet.character, smitten, severity=1)
        # Neutral base (Normal) − 2 exploitable tiers → Trivial.
        self.assertEqual(self._value(), DIFFICULTY_VALUES[DifficultyChoice.TRIVIAL])
