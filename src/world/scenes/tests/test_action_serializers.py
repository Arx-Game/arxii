"""Tests for TechniqueCastCreateSerializer pull-declaration validation (#854)."""

from __future__ import annotations

from django.test import TestCase
from django.utils import timezone

from world.magic.constants import TargetKind
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterSheetFactory,
    ResonanceFactory,
    TechniqueFactory,
    ThreadFactory,
)
from world.scenes.action_serializers import TechniqueCastCreateSerializer
from world.scenes.factories import SceneFactory


class CastPullValidationTests(TestCase):
    """Validation of the nested pull declaration on the cast serializer (#854)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.persona = cls.sheet.primary_persona
        cls.scene = SceneFactory()
        cls.resonance = ResonanceFactory()
        # Non-hostile technique: binary effect (base_power=None) + no damage profile.
        cls.technique = TechniqueFactory(
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
        )
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=cls.technique,
        )

    def _data(self, **pull_overrides: object) -> dict:
        pull: dict = {
            "resonance_id": self.resonance.pk,
            "tier": 2,
            "thread_ids": [self.thread.pk],
            **pull_overrides,
        }
        return {
            "scene": self.scene.pk,
            "initiator_persona": self.persona.pk,
            "technique_id": self.technique.pk,
            "pull": pull,
        }

    def test_valid_pull_resolves_instances(self) -> None:
        ser = TechniqueCastCreateSerializer(data=self._data())
        self.assertTrue(ser.is_valid(), ser.errors)
        pull = ser.validated_data["pull"]
        self.assertEqual(pull["resonance"].pk, self.resonance.pk)
        self.assertEqual([t.pk for t in pull["threads"]], [self.thread.pk])

    def test_unowned_thread_rejected(self) -> None:
        other_thread = ThreadFactory(
            owner=CharacterSheetFactory(),
            resonance=self.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=self.technique,
        )
        ser = TechniqueCastCreateSerializer(data=self._data(thread_ids=[other_thread.pk]))
        self.assertFalse(ser.is_valid())
        self.assertIn("pull", ser.errors)

    def test_resonance_mismatch_rejected(self) -> None:
        ser = TechniqueCastCreateSerializer(data=self._data(resonance_id=ResonanceFactory().pk))
        self.assertFalse(ser.is_valid())
        self.assertIn("pull", ser.errors)

    def test_tier_out_of_bounds_rejected(self) -> None:
        ser = TechniqueCastCreateSerializer(data=self._data(tier=4))
        self.assertFalse(ser.is_valid())

    def test_hostile_technique_with_pull_rejected(self) -> None:
        """Pull declarations are forbidden on hostile casts — combat owns that flow.

        A hostile technique has base_power non-null on its effect_type, which
        auto-seeds a damage profile (base_damage > 0). is_technique_hostile()
        returns True for any technique with base_damage > 0 on a damage profile.
        """
        # Default TechniqueFactory uses EffectTypeFactory (base_power=10) and
        # auto-seeds a damage profile, making is_technique_hostile() return True.
        hostile_technique = TechniqueFactory()
        data = self._data()
        data["technique_id"] = hostile_technique.pk
        ser = TechniqueCastCreateSerializer(data=data)
        self.assertFalse(ser.is_valid())
        self.assertIn("pull", ser.errors)
        self.assertIn("hostile", str(ser.errors["pull"][0]).lower())

    def test_retired_thread_rejected(self) -> None:
        """A thread with retired_at set must be rejected by pull validation.

        Uses a separate Technique anchor to avoid the unique constraint on
        (owner, resonance, target_technique) that would prevent two threads
        for the same combination.
        """
        other_technique = TechniqueFactory(
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
        )
        retired_thread = ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_trait=None,
            target_technique=other_technique,
            retired_at=timezone.now(),
        )
        ser = TechniqueCastCreateSerializer(data=self._data(thread_ids=[retired_thread.pk]))
        self.assertFalse(ser.is_valid())
        self.assertIn("pull", ser.errors)

    def test_duplicate_thread_ids_rejected(self) -> None:
        ser = TechniqueCastCreateSerializer(
            data=self._data(thread_ids=[self.thread.pk, self.thread.pk])
        )
        self.assertFalse(ser.is_valid())
        self.assertIn("pull", ser.errors)

    def test_cast_without_pull_still_valid(self) -> None:
        data = self._data()
        del data["pull"]
        ser = TechniqueCastCreateSerializer(data=data)
        self.assertTrue(ser.is_valid(), ser.errors)
