"""TechniqueVariant: matching_variant + newly_crossed_variants + payload shape.

Task 4 of the gift-specialization engine (#1578). ``TechniqueVariant`` is the
concrete subclass of ``AbstractSpecializedVariant`` (Task 3): a parent
``Technique`` gets variant rows keyed by ``(parent_technique, resonance,
unlock_thread_level)``. When a character's GIFT thread crosses a variant's
``unlock_thread_level`` the resolver picks the variant and the cast pipeline
reads its name/intensity deltas + payload. Mirrors the proven covenant sub-role
pattern (single-depth only).
"""

from django.db import IntegrityError, transaction
from django.test import TestCase
import factory

from world.conditions.factories import (
    CapabilityTypeFactory,
    ConditionTemplateFactory,
    DamageTypeFactory,
)
from world.magic.factories import ResonanceFactory, TechniqueFactory
from world.magic.specialization.models import (
    TechniqueVariant,
)


class TechniqueVariantResolutionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.parent_technique = TechniqueFactory()
        cls.resonance = ResonanceFactory()

    def _make_variant(
        self,
        *,
        unlock_level,
        resonance=None,
        name=None,
        intensity_delta=0,
    ):
        # CharField(blank=True) stores "" not NULL (Django convention,
        # ADR-0007); coerce None -> "" so callers can pass name=None.
        return TechniqueVariant.objects.create(
            parent_technique=self.parent_technique,
            resonance=resonance or self.resonance,
            unlock_thread_level=unlock_level,
            name_override=name or "",
            intensity_delta=intensity_delta,
        )

    def test_matching_variant_none_below_threshold(self) -> None:
        self._make_variant(unlock_level=3)
        result = TechniqueVariant.matching_variant(
            self.parent_technique, resonance=self.resonance, thread_level=2
        )
        self.assertIsNone(result)

    def test_matching_variant_at_threshold(self) -> None:
        v3 = self._make_variant(unlock_level=3)
        result = TechniqueVariant.matching_variant(
            self.parent_technique, resonance=self.resonance, thread_level=3
        )
        self.assertEqual(result, v3)

    def test_matching_variant_highest_wins(self) -> None:
        self._make_variant(unlock_level=3)
        v5 = self._make_variant(unlock_level=5)
        result = TechniqueVariant.matching_variant(
            self.parent_technique, resonance=self.resonance, thread_level=5
        )
        self.assertEqual(result, v5)

    def test_matching_variant_wrong_resonance_returns_none(self) -> None:
        self._make_variant(unlock_level=3)
        other = ResonanceFactory()
        result = TechniqueVariant.matching_variant(
            self.parent_technique, resonance=other, thread_level=5
        )
        self.assertIsNone(result)

    def test_newly_crossed_variants(self) -> None:
        v3 = self._make_variant(unlock_level=3)
        v5 = self._make_variant(unlock_level=5)
        crossed = TechniqueVariant.newly_crossed_variants(
            self.parent_technique,
            resonance_id=self.resonance.pk,
            starting_level=2,
            new_level=5,
        )
        self.assertEqual(set(crossed), {v3, v5})

    def test_newly_crossed_variants_empty_when_no_gain(self) -> None:
        self._make_variant(unlock_level=3)
        crossed = TechniqueVariant.newly_crossed_variants(
            self.parent_technique,
            resonance_id=self.resonance.pk,
            starting_level=5,
            new_level=5,
        )
        self.assertEqual(list(crossed), [])

    def test_discovery_narrative_personal_when_not_first(self) -> None:
        # is_first=False returns empty recipients (the ceremony caller —
        # fire_variant_discoveries — supplies [thread.owner]) plus personal
        # prose naming the variant form + its resonance. See the brief's note
        # on the discovery_narrative recipient contract.
        v = self._make_variant(unlock_level=3, name="Celestial Form")
        recipients, body = v.discovery_narrative(is_first=False)
        self.assertEqual(list(recipients), [])
        self.assertIn("Celestial Form", body)
        self.assertIn(self.resonance.name, body)

    def test_discovery_narrative_gamewide_when_first(self) -> None:
        # is_first=True returns gamewide recipients via
        # active_player_character_sheets() + "first time" prose. No
        # CharacterSheetFactory rows are needed to assert the prose branch;
        # we only check the body names the form + resonance.
        v = self._make_variant(unlock_level=3, name="Celestial Form")
        recipients, body = v.discovery_narrative(is_first=True)
        self.assertIsInstance(recipients, list)
        self.assertIn("Celestial Form", body)
        self.assertIn(self.resonance.name, body)

    def test_unique_constraint_parent_resonance_level(self) -> None:
        self._make_variant(unlock_level=3)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._make_variant(unlock_level=3)  # duplicate (parent, resonance, level)

    def test_str_uses_name_override(self) -> None:
        v = self._make_variant(unlock_level=3, name="Celestial Form")
        self.assertIn("Celestial Form", str(v))
        self.assertIn(str(self.resonance.pk), str(v))

    def test_str_falls_back_to_parent_id_when_no_override(self) -> None:
        v = self._make_variant(unlock_level=3, name=None)
        self.assertIn(str(self.parent_technique.pk), str(v))

    def test_payload_children_related_names(self) -> None:
        # The 3 payload children attach via related_names capability_grants /
        # damage_profiles / condition_applications, mirroring Technique*.
        v = self._make_variant(unlock_level=3)
        grant = TechniqueVariantCapabilityGrantFactory(variant=v)
        profile = TechniqueVariantDamageProfileFactory(variant=v)
        cond = TechniqueVariantAppliedConditionFactory(variant=v)
        self.assertEqual(v.capability_grants.get(), grant)
        self.assertEqual(v.damage_profiles.get(), profile)
        self.assertEqual(v.condition_applications.get(), cond)


# --- payload-child factories (local; only the variant rows need a real factory) ---


class TechniqueVariantCapabilityGrantFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "magic.TechniqueVariantCapabilityGrant"

    variant = factory.SubFactory("world.magic.factories.TechniqueVariantFactory")
    capability = factory.SubFactory(CapabilityTypeFactory)


class TechniqueVariantDamageProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "magic.TechniqueVariantDamageProfile"

    variant = factory.SubFactory("world.magic.factories.TechniqueVariantFactory")
    damage_type = factory.SubFactory(DamageTypeFactory)


class TechniqueVariantAppliedConditionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "magic.TechniqueVariantAppliedCondition"

    variant = factory.SubFactory("world.magic.factories.TechniqueVariantFactory")
    condition = factory.SubFactory(ConditionTemplateFactory)
