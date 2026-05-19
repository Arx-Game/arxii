"""Tests for AffordanceBinding (Phase 1, Task 1.2).

The binding is the authored-once link from a durable descriptor to an
affordance. It reuses ``core.mixins.DiscriminatorMixin`` for the
heterogeneous descriptor side (exactly one typed FK active per
``source_kind``) and reuses the existing ``checks.CheckType`` /
``checks.Consequence`` substrate (no new check/consequence models).

These tests assert the discriminator contract (exactly-one enforcement),
the produces⇔check_type invariant in ``clean()``, and that the factory
round-trips.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.checks.factories import CheckTypeFactory, ConsequenceFactory
from world.conditions.factories import CapabilityTypeFactory
from world.distinctions.factories import DistinctionFactory
from world.missions.constants import OptionProduces
from world.missions.factories import AffordanceBindingFactory, AffordanceFactory
from world.missions.models import SOURCE_CAPABILITY, SOURCE_DISTINCTION, AffordanceBinding


class AffordanceBindingDiscriminatorTests(TestCase):
    """DiscriminatorMixin: exactly the typed FK named by source_kind is set."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.affordance = AffordanceFactory(name="distraction")
        cls.distinction = DistinctionFactory(slug="charming")

    def test_branch_distinction_binding_round_trips(self) -> None:
        binding = AffordanceBindingFactory(
            affordance=self.affordance,
            source_distinction=self.distinction,
        )
        fetched = AffordanceBinding.objects.get(pk=binding.pk)
        self.assertEqual(fetched.source_kind, SOURCE_DISTINCTION)
        self.assertEqual(fetched.get_active_target(), self.distinction)
        self.assertEqual(fetched.produces, OptionProduces.BRANCH)
        self.assertIsNone(fetched.check_type)

    def test_wrong_typed_fk_for_source_kind_is_rejected(self) -> None:
        capability = CapabilityTypeFactory(name="brute-force")
        binding = AffordanceBinding(
            source_kind=SOURCE_CAPABILITY,
            source_distinction=self.distinction,  # mismatched: should be capability
            affordance=self.affordance,
            produces=OptionProduces.BRANCH,
            ic_framing="x",
        )
        with self.assertRaises(ValidationError):
            binding.full_clean()
        # And the correctly-shaped capability binding validates.
        ok = AffordanceBinding(
            source_kind=SOURCE_CAPABILITY,
            source_capability=capability,
            affordance=self.affordance,
            produces=OptionProduces.BRANCH,
            ic_framing="x",
        )
        ok.full_clean()

    def test_missing_typed_fk_for_source_kind_is_rejected(self) -> None:
        binding = AffordanceBinding(
            source_kind=SOURCE_DISTINCTION,
            affordance=self.affordance,
            produces=OptionProduces.BRANCH,
            ic_framing="x",
        )
        with self.assertRaises(ValidationError):
            binding.full_clean()


class AffordanceBindingProducesInvariantTests(TestCase):
    """produces == CHECK ⟺ check_type set; produces == BRANCH ⟹ check_type null."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.affordance = AffordanceFactory(name="lethal")
        cls.distinction = DistinctionFactory(slug="deadly")
        cls.check_type = CheckTypeFactory(name="Assassinate")
        cls.consequence = ConsequenceFactory()

    def test_check_binding_requires_check_type(self) -> None:
        binding = AffordanceBinding(
            source_kind=SOURCE_DISTINCTION,
            source_distinction=self.distinction,
            affordance=self.affordance,
            produces=OptionProduces.CHECK,
            ic_framing="strike",
        )
        with self.assertRaises(ValidationError):
            binding.full_clean()

    def test_branch_binding_rejects_check_type(self) -> None:
        binding = AffordanceBinding(
            source_kind=SOURCE_DISTINCTION,
            source_distinction=self.distinction,
            affordance=self.affordance,
            produces=OptionProduces.BRANCH,
            check_type=self.check_type,
            ic_framing="sneak",
        )
        with self.assertRaises(ValidationError):
            binding.full_clean()

    def test_valid_check_binding_with_rider_round_trips(self) -> None:
        binding = AffordanceBindingFactory(
            affordance=self.affordance,
            source_distinction=self.distinction,
            produces=OptionProduces.CHECK,
            check_type=self.check_type,
            base_risk=4,
            rider=self.consequence,
        )
        fetched = AffordanceBinding.objects.get(pk=binding.pk)
        self.assertEqual(fetched.produces, OptionProduces.CHECK)
        self.assertEqual(fetched.check_type, self.check_type)
        self.assertEqual(fetched.base_risk, 4)
        self.assertEqual(fetched.rider, self.consequence)
