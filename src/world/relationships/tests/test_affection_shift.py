"""Tests for automatic affection shifts (#1697): service, effect handler, seeds."""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.relationships.constants import TrackSystemKey
from world.relationships.models import (
    AffectionShift,
    CharacterRelationship,
    RelationshipTrackProgress,
)
from world.relationships.services import apply_affection_shift
from world.scenes.factories import SceneFactory
from world.seeds.relationship_scale import seed_relationship_scale_content


def _shift_effect(amount: int):
    """A minimal SHIFT_AFFECTION ConsequenceEffect row for service-level tests."""
    from world.checks.constants import EffectTarget, EffectType
    from world.checks.models import Consequence, ConsequenceEffect
    from world.traits.models import CheckOutcome

    outcome, _ = CheckOutcome.objects.get_or_create(name="Success")
    consequence, _ = Consequence.objects.get_or_create(
        outcome_tier=outcome, label=f"shift-test-{amount}", defaults={"character_loss": False}
    )
    return ConsequenceEffect.objects.create(
        consequence=consequence,
        effect_type=EffectType.SHIFT_AFFECTION,
        target=EffectTarget.TARGET,
        affection_amount=amount,
    )


class ApplyAffectionShiftTests(TestCase):
    def setUp(self) -> None:
        from evennia.utils.idmapper.models import flush_cache

        flush_cache()
        seed_relationship_scale_content()
        # source = the social action's TARGET (their regard moves toward the actor).
        self.target_of_action = CharacterSheetFactory()
        self.actor = CharacterSheetFactory()
        self.scene = SceneFactory()

    def test_positive_shift_lands_on_regard(self) -> None:
        effect = _shift_effect(5)
        shift = apply_affection_shift(
            source=self.target_of_action,
            target=self.actor,
            scene=self.scene,
            effect=effect,
            amount=5,
        )
        self.assertIsNotNone(shift)
        relationship = CharacterRelationship.objects.get(
            source=self.target_of_action, target=self.actor
        )
        self.assertEqual(relationship.affection, 5)
        progress = RelationshipTrackProgress.objects.get(
            relationship=relationship, track__system_key=TrackSystemKey.REGARD
        )
        self.assertEqual(progress.developed_points, 5)
        self.assertEqual(progress.capacity, 5)

    def test_negative_shift_lands_on_friction(self) -> None:
        effect = _shift_effect(-10)
        apply_affection_shift(
            source=self.target_of_action,
            target=self.actor,
            scene=self.scene,
            effect=effect,
            amount=-10,
        )
        relationship = CharacterRelationship.objects.get(
            source=self.target_of_action, target=self.actor
        )
        self.assertEqual(relationship.affection, -10)
        self.assertTrue(
            RelationshipTrackProgress.objects.filter(
                relationship=relationship, track__system_key=TrackSystemKey.FRICTION
            ).exists()
        )

    def test_repeat_in_same_scene_is_deduped(self) -> None:
        effect = _shift_effect(5)
        first = apply_affection_shift(
            source=self.target_of_action,
            target=self.actor,
            scene=self.scene,
            effect=effect,
            amount=5,
        )
        second = apply_affection_shift(
            source=self.target_of_action,
            target=self.actor,
            scene=self.scene,
            effect=effect,
            amount=5,
        )
        self.assertIsNotNone(first)
        self.assertIsNone(second)
        relationship = CharacterRelationship.objects.get(
            source=self.target_of_action, target=self.actor
        )
        self.assertEqual(relationship.affection, 5)
        self.assertEqual(AffectionShift.objects.count(), 1)

    def test_new_scene_shifts_again(self) -> None:
        effect = _shift_effect(5)
        apply_affection_shift(
            source=self.target_of_action,
            target=self.actor,
            scene=self.scene,
            effect=effect,
            amount=5,
        )
        other_scene = SceneFactory()
        again = apply_affection_shift(
            source=self.target_of_action,
            target=self.actor,
            scene=other_scene,
            effect=effect,
            amount=5,
        )
        self.assertIsNotNone(again)
        relationship = CharacterRelationship.objects.get(
            source=self.target_of_action, target=self.actor
        )
        self.assertEqual(relationship.affection, 10)


class BoonProvenanceShiftTests(TestCase):
    """Boon-keyed shifts (#2540): per-Boon dedup — serial boons stack within one scene."""

    def setUp(self) -> None:
        from evennia.utils.idmapper.models import flush_cache

        flush_cache()
        seed_relationship_scale_content()
        self.granter = CharacterSheetFactory()
        self.asker = CharacterSheetFactory()
        self.scene = SceneFactory()

    def _boon(self):
        from world.scenes.action_constants import BoonKind
        from world.scenes.boon_models import Boon
        from world.scenes.factories import SceneActionRequestFactory

        request = SceneActionRequestFactory(scene=self.scene, action_key="boon")
        return Boon.objects.create(action_request=request, kind=BoonKind.DEED, deed_text="x")

    def test_two_boons_in_one_scene_both_shift(self) -> None:
        first = apply_affection_shift(
            source=self.granter,
            target=self.asker,
            scene=self.scene,
            effect=None,
            boon=self._boon(),
            amount=-15,
        )
        second = apply_affection_shift(
            source=self.granter,
            target=self.asker,
            scene=self.scene,
            effect=None,
            boon=self._boon(),
            amount=-15,
        )
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        relationship = CharacterRelationship.objects.get(source=self.granter, target=self.asker)
        self.assertEqual(relationship.affection, -30)  # stacks — serial asks wear out welcome

    def test_provenance_is_exactly_one_of_effect_or_boon(self) -> None:
        with self.assertRaises(ValueError):
            apply_affection_shift(
                source=self.granter,
                target=self.asker,
                scene=self.scene,
                effect=None,
                amount=-15,
            )
        with self.assertRaises(ValueError):
            apply_affection_shift(
                source=self.granter,
                target=self.asker,
                scene=self.scene,
                effect=_shift_effect(-15),
                boon=self._boon(),
                amount=-15,
            )


class ShiftAffectionSeedTests(TestCase):
    """Flirt/Seduce success consequences carry the SHIFT_AFFECTION effects."""

    def test_seed_attaches_signed_shift_effects(self) -> None:
        from world.checks.constants import EffectType
        from world.checks.models import ConsequenceEffect
        from world.seeds.checks import seed_check_resolution_tables
        from world.seeds.social_actions import (
            FLIRT_AFFECTION_SHIFT,
            SEDUCE_AFFECTION_SHIFT,
            seed_social_action_content,
        )
        from world.seeds.social_checks import seed_social_check_content
        from world.seeds.social_relationships import seed_social_relationship_content

        seed_check_resolution_tables()
        seed_social_check_content()
        seed_social_relationship_content()
        seed_social_action_content()

        amounts = set(
            ConsequenceEffect.objects.filter(effect_type=EffectType.SHIFT_AFFECTION).values_list(
                "affection_amount", flat=True
            )
        )
        self.assertEqual(amounts, {FLIRT_AFFECTION_SHIFT, SEDUCE_AFFECTION_SHIFT})

    def test_seed_authors_the_attractive_allure_grant(self) -> None:
        from world.distinctions.models import Distinction
        from world.seeds.social_relationships import seed_social_relationship_content

        seed_social_relationship_content()
        attractive = Distinction.objects.get(slug="attractive")
        effect = attractive.effects.get()
        self.assertEqual(effect.target.name, "allure")
        self.assertGreater(effect.value_per_rank, 0)

    def test_seed_gives_smitten_its_teeth(self) -> None:
        from world.seeds.social_actions import ensure_smitten_condition

        smitten = ensure_smitten_condition()
        self.assertEqual(smitten.exploitable_tiers, 2)
