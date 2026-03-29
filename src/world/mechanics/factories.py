"""Factory classes for mechanics models."""

from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from actions.factories import ConsequencePoolFactory
from world.mechanics.constants import PropertyHolder
from world.mechanics.models import (
    Application,
    ApproachConsequence,
    ChallengeApproach,
    ChallengeCategory,
    ChallengeTemplate,
    ChallengeTemplateConsequence,
    ChallengeTemplateProperty,
    CharacterModifier,
    ContextConsequencePool,
    ModifierCategory,
    ModifierSource,
    ModifierTarget,
    ObjectProperty,
    Prerequisite,
    Property,
    PropertyCategory,
    SituationChallengeLink,
    SituationTemplate,
    TraitCapabilityDerivation,
)


class ModifierCategoryFactory(DjangoModelFactory):
    """Factory for creating ModifierCategory instances."""

    class Meta:
        model = ModifierCategory
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Category{n}")
    description = factory.Faker("sentence")
    display_order = factory.Sequence(lambda n: n)


class ModifierTargetFactory(DjangoModelFactory):
    """Factory for creating ModifierTarget instances."""

    class Meta:
        model = ModifierTarget
        django_get_or_create = ("category", "name")

    name = factory.Sequence(lambda n: f"ModifierTarget{n}")
    category = factory.SubFactory(ModifierCategoryFactory)
    description = factory.Faker("sentence")
    display_order = factory.Sequence(lambda n: n)
    is_active = True


class ModifierSourceFactory(DjangoModelFactory):
    """Factory for creating ModifierSource instances.

    By default creates a source with no specific origin (unknown source).
    Use DistinctionModifierSourceFactory for sources with valid modifier_target.
    """

    class Meta:
        model = ModifierSource

    # All source fields are nullable - default is unknown source
    distinction_effect = None
    character_distinction = None


class DistinctionModifierSourceFactory(ModifierSourceFactory):
    """Factory for creating ModifierSource from a distinction.

    This creates a source with valid distinction_effect (which provides modifier_target)
    and character_distinction (for cascade deletion).
    """

    distinction_effect = factory.SubFactory("world.distinctions.factories.DistinctionEffectFactory")
    character_distinction = factory.SubFactory(
        "world.distinctions.factories.CharacterDistinctionFactory"
    )


class CharacterModifierFactory(DjangoModelFactory):
    """Factory for creating CharacterModifier instances.

    By default uses DistinctionModifierSourceFactory to ensure valid source.
    The target FK is derived from the source's distinction_effect.target.
    """

    class Meta:
        model = CharacterModifier

    character = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    value = factory.Faker("random_int", min=-50, max=50)
    source = factory.SubFactory(DistinctionModifierSourceFactory)
    target = factory.LazyAttribute(lambda o: o.source.distinction_effect.target)


# ---------------------------------------------------------------------------
# Prerequisite types
# ---------------------------------------------------------------------------


class PrerequisiteFactory(DjangoModelFactory):
    """Factory for creating Prerequisite instances."""

    class Meta:
        model = Prerequisite
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Prerequisite{n}")
    description = factory.Faker("sentence")
    property = factory.SubFactory("world.mechanics.factories.PropertyFactory")
    property_holder = PropertyHolder.SELF
    minimum_value = 1


# ---------------------------------------------------------------------------
# Property / Application layer
# ---------------------------------------------------------------------------


class PropertyCategoryFactory(DjangoModelFactory):
    """Factory for creating PropertyCategory instances."""

    class Meta:
        model = PropertyCategory
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"PropertyCategory{n}")
    description = factory.Faker("sentence")
    display_order = factory.Sequence(lambda n: n)


class PropertyFactory(DjangoModelFactory):
    """Factory for creating Property instances."""

    class Meta:
        model = Property
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Property{n}")
    description = factory.Faker("sentence")
    category = factory.SubFactory(PropertyCategoryFactory)


class ObjectPropertyFactory(DjangoModelFactory):
    """Factory for creating ObjectProperty instances."""

    class Meta:
        model = ObjectProperty

    property = factory.SubFactory(PropertyFactory)
    value = 1


class ApplicationFactory(DjangoModelFactory):
    """Factory for creating Application instances."""

    class Meta:
        model = Application
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Application{n}")
    capability = factory.SubFactory("world.conditions.factories.CapabilityTypeFactory")
    target_property = factory.SubFactory(PropertyFactory)
    description = factory.Faker("sentence")


# ---------------------------------------------------------------------------
# Trait → Capability derivation
# ---------------------------------------------------------------------------


class TraitCapabilityDerivationFactory(DjangoModelFactory):
    """Factory for creating TraitCapabilityDerivation instances."""

    class Meta:
        model = TraitCapabilityDerivation

    trait = factory.SubFactory("world.traits.factories.TraitFactory")
    capability = factory.SubFactory("world.conditions.factories.CapabilityTypeFactory")
    base_value = 0
    trait_multiplier = Decimal("1.00")


# ---------------------------------------------------------------------------
# Challenge system
# ---------------------------------------------------------------------------


class ChallengeCategoryFactory(DjangoModelFactory):
    """Factory for creating ChallengeCategory instances."""

    class Meta:
        model = ChallengeCategory
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"ChallengeCategory{n}")
    description = factory.Faker("sentence")
    display_order = factory.Sequence(lambda n: n)


class ChallengeTemplateFactory(DjangoModelFactory):
    """Factory for creating ChallengeTemplate instances."""

    class Meta:
        model = ChallengeTemplate
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"ChallengeTemplate{n}")
    description_template = factory.Faker("sentence")
    severity = 1
    goal = factory.Faker("sentence")
    category = factory.SubFactory(ChallengeCategoryFactory)


class ChallengeTemplatePropertyFactory(DjangoModelFactory):
    """Factory for creating ChallengeTemplateProperty instances."""

    class Meta:
        model = ChallengeTemplateProperty

    challenge_template = factory.SubFactory(ChallengeTemplateFactory)
    property = factory.SubFactory(PropertyFactory)
    value = 1


class ChallengeTemplateConsequenceFactory(DjangoModelFactory):
    """Factory for creating ChallengeTemplateConsequence instances."""

    class Meta:
        model = ChallengeTemplateConsequence

    challenge_template = factory.SubFactory(ChallengeTemplateFactory)
    consequence = factory.SubFactory("world.checks.factories.ConsequenceFactory")


class ChallengeApproachFactory(DjangoModelFactory):
    """Factory for creating ChallengeApproach instances."""

    class Meta:
        model = ChallengeApproach

    challenge_template = factory.SubFactory(ChallengeTemplateFactory)
    application = factory.SubFactory(ApplicationFactory)
    check_type = factory.SubFactory("world.checks.factories.CheckTypeFactory")
    display_name = factory.Sequence(lambda n: f"Approach{n}")
    custom_description = factory.Faker("sentence")


class ApproachConsequenceFactory(DjangoModelFactory):
    """Factory for creating ApproachConsequence instances."""

    class Meta:
        model = ApproachConsequence

    approach = factory.SubFactory(ChallengeApproachFactory)
    consequence = factory.SubFactory("world.checks.factories.ConsequenceFactory")


# ---------------------------------------------------------------------------
# Situation system
# ---------------------------------------------------------------------------


class SituationTemplateFactory(DjangoModelFactory):
    """Factory for creating SituationTemplate instances."""

    class Meta:
        model = SituationTemplate
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"SituationTemplate{n}")
    description_template = factory.Faker("sentence")
    category = factory.SubFactory(ChallengeCategoryFactory)


class SituationChallengeLinkFactory(DjangoModelFactory):
    """Factory for creating SituationChallengeLink instances."""

    class Meta:
        model = SituationChallengeLink

    situation_template = factory.SubFactory(SituationTemplateFactory)
    challenge_template = factory.SubFactory(ChallengeTemplateFactory)
    display_order = factory.Sequence(lambda n: n)


class ContextConsequencePoolFactory(DjangoModelFactory):
    """Factory for ContextConsequencePool."""

    class Meta:
        model = ContextConsequencePool

    property = factory.SubFactory(PropertyFactory)
    consequence_pool = factory.SubFactory(ConsequencePoolFactory)
    check_type = factory.SubFactory("world.checks.factories.CheckTypeFactory")
    description = ""
