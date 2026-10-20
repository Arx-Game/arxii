"""Cosmetic Mage Scars (#4501): a reward with no drawbacks that never gates advancement."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import DamageTypeFactory
from world.conditions.models import ConditionResistanceModifier
from world.magic.constants import MIN_ALTERATION_DESCRIPTION_LENGTH, AlterationTier
from world.magic.factories import (
    AffinityFactory,
    MagicalAlterationTemplateFactory,
    PendingAlterationFactory,
    ResonanceFactory,
)
from world.magic.models import PendingAlteration
from world.magic.services import (
    create_pending_alteration,
    has_pending_alterations,
    validate_alteration_resolution,
)
from world.scenes.factories import SceneFactory


class CosmeticScarMergeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.affinity = AffinityFactory(name="Primal")
        cls.resonance = ResonanceFactory(name="Ember", affinity=cls.affinity)
        cls.scene = SceneFactory()

    def _queue(self, tier, *, cosmetic):
        return create_pending_alteration(
            character=self.sheet,
            tier=tier,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            scene=self.scene,
            is_cosmetic=cosmetic,
        )

    def test_a_reward_never_raises_a_cost_and_a_cost_never_taints_a_reward(self) -> None:
        cost = self._queue(AlterationTier.MARKED, cosmetic=False)
        reward = self._queue(AlterationTier.REMADE, cosmetic=True)
        self.assertTrue(reward.created)
        self.assertNotEqual(cost.pending.pk, reward.pending.pk)
        cost.pending.refresh_from_db()
        self.assertEqual(cost.pending.tier, AlterationTier.MARKED)

        raised = self._queue(AlterationTier.TOUCHED, cosmetic=False)
        self.assertEqual(raised.pending.pk, cost.pending.pk)
        self.assertEqual(raised.pending.tier, AlterationTier.TOUCHED)
        self.assertFalse(PendingAlteration.objects.get(pk=reward.pending.pk).tier == 3)

    def test_two_rewards_in_one_scene_merge(self) -> None:
        first = self._queue(AlterationTier.MARKED, cosmetic=True)
        second = self._queue(AlterationTier.TOUCHED, cosmetic=True)
        self.assertEqual(first.pending.pk, second.pending.pk)
        self.assertEqual(second.pending.tier, AlterationTier.TOUCHED)

    def test_only_a_costly_scar_holds_advancement_back(self) -> None:
        PendingAlterationFactory(character=self.sheet, is_cosmetic=True)
        self.assertFalse(has_pending_alterations(self.sheet))
        PendingAlterationFactory(character=self.sheet)
        self.assertTrue(has_pending_alterations(self.sheet))


class CosmeticResolutionValidationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.affinity = AffinityFactory(name="Primal")
        cls.resonance = ResonanceFactory(name="Ember", affinity=cls.affinity)
        cls.sheet = CharacterSheetFactory()
        cls.damage_type = DamageTypeFactory(name="Holy")

    def _scratch(self, **overrides):
        payload = {
            "tier": AlterationTier.TOUCHED,
            "origin_affinity_id": self.affinity.pk,
            "origin_resonance_id": self.resonance.pk,
            "player_description": "A" * MIN_ALTERATION_DESCRIPTION_LENGTH,
            "observer_description": "B" * MIN_ALTERATION_DESCRIPTION_LENGTH,
            "weakness_magnitude": 0,
            "resonance_bonus_magnitude": 0,
            "social_reactivity_magnitude": 0,
            "is_visible_at_rest": False,
        }
        payload.update(overrides)
        return validate_alteration_resolution(
            pending_tier=AlterationTier.TOUCHED,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload=payload,
            is_staff=False,
            character_sheet=self.sheet,
            is_cosmetic=True,
        )

    def test_a_cosmetic_scar_written_with_no_drawbacks_passes(self) -> None:
        self.assertEqual(self._scratch(), [])

    def test_any_drawback_is_refused(self) -> None:
        for field in (
            "weakness_magnitude",
            "resonance_bonus_magnitude",
            "social_reactivity_magnitude",
        ):
            errors = self._scratch(**{field: 1})
            self.assertTrue(any("no drawbacks" in e for e in errors), field)

    def _library_entry(self, **fields):
        return MagicalAlterationTemplateFactory(
            tier=AlterationTier.TOUCHED,
            origin_affinity=self.affinity,
            origin_resonance=self.resonance,
            is_library_entry=True,
            **fields,
        )

    def _library(self, entry):
        return validate_alteration_resolution(
            pending_tier=AlterationTier.TOUCHED,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload={"library_entry_pk": entry.pk},
            is_staff=False,
            character_sheet=self.sheet,
            is_cosmetic=True,
        )

    def test_a_library_entry_with_no_drawbacks_is_accepted(self) -> None:
        self.assertEqual(self._library(self._library_entry()), [])

    def test_a_library_entry_with_a_magnitude_is_refused(self) -> None:
        errors = self._library(self._library_entry(social_reactivity_magnitude=1))
        self.assertTrue(any("no drawbacks" in e for e in errors))

    def test_a_library_entry_whose_condition_carries_a_modifier_is_refused(self) -> None:
        entry = self._library_entry()
        ConditionResistanceModifier.objects.create(
            condition=entry.condition_template, damage_type=self.damage_type, modifier_value=-1
        )
        self.assertTrue(any("no drawbacks" in e for e in self._library(entry)))

    def test_ordinary_scars_may_still_take_a_drawback_entry(self) -> None:
        entry = self._library_entry(social_reactivity_magnitude=1)
        errors = validate_alteration_resolution(
            pending_tier=AlterationTier.TOUCHED,
            pending_affinity_id=self.affinity.pk,
            pending_resonance_id=self.resonance.pk,
            payload={"library_entry_pk": entry.pk},
            is_staff=False,
            character_sheet=self.sheet,
        )
        self.assertEqual(errors, [])


class CosmeticScarSerializerTests(TestCase):
    def test_a_cosmetic_scar_reads_cosmetic_with_every_drawback_cap_at_zero(self) -> None:
        from world.magic.serializers import PendingAlterationSerializer

        costly = PendingAlterationFactory(tier=AlterationTier.TOUCHED)
        cosmetic = PendingAlterationFactory(tier=AlterationTier.TOUCHED, is_cosmetic=True)

        costly_data = PendingAlterationSerializer(costly).data
        cosmetic_data = PendingAlterationSerializer(cosmetic).data

        self.assertFalse(costly_data["is_cosmetic"])
        self.assertEqual(costly_data["tier_caps"]["weakness_cap"], 3)
        self.assertTrue(cosmetic_data["is_cosmetic"])
        self.assertEqual(
            [
                cosmetic_data["tier_caps"][key]
                for key in ("weakness_cap", "resonance_cap", "social_cap")
            ],
            [0, 0, 0],
        )
