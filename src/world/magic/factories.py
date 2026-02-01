from decimal import Decimal

import factory

from world.magic.models import (
    AnimaRitualPerformance,
    AnimaRitualType,
    CharacterAnima,
    CharacterAnimaRitual,
    CharacterAura,
    CharacterGift,
    CharacterPower,
    CharacterResonance,
    CharacterTechnique,
    EffectType,
    Gift,
    IntensityTier,
    Motif,
    MotifResonance,
    MotifResonanceAssociation,
    Power,
    ResonanceAssociation,
    Restriction,
    Technique,
    TechniqueStyle,
    Thread,
    ThreadJournal,
    ThreadResonance,
    ThreadType,
)
from world.magic.types import (
    AnimaRitualCategory,
    ResonanceScope,
    ResonanceStrength,
)
from world.mechanics.factories import ModifierCategoryFactory, ModifierTypeFactory
from world.mechanics.models import ModifierType


class EffectTypeFactory(factory.django.DjangoModelFactory):
    """Factory for EffectType with power scaling."""

    class Meta:
        model = EffectType
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Effect Type {n}")
    description = factory.LazyAttribute(lambda o: f"Description for {o.name}.")
    base_power = 10
    base_anima_cost = 2
    has_power_scaling = True


class BinaryEffectTypeFactory(EffectTypeFactory):
    """Factory for EffectType without power scaling (binary effects)."""

    name = factory.Sequence(lambda n: f"Binary Effect {n}")
    base_power = None
    has_power_scaling = False


class TechniqueStyleFactory(factory.django.DjangoModelFactory):
    """Factory for TechniqueStyle."""

    class Meta:
        model = TechniqueStyle
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Technique Style {n}")
    description = factory.LazyAttribute(lambda o: f"Description for {o.name}.")

    @factory.post_generation
    def allowed_paths(self, create, extracted, **kwargs):
        """Add allowed paths to the technique style."""
        if not create:
            return
        if extracted:
            for path in extracted:
                self.allowed_paths.add(path)


class RestrictionFactory(factory.django.DjangoModelFactory):
    """Factory for Restriction with optional allowed effect types."""

    class Meta:
        model = Restriction
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Restriction {n}")
    description = factory.LazyAttribute(lambda o: f"Description for {o.name}.")
    power_bonus = 10

    @factory.post_generation
    def allowed_effect_types(self, create, extracted, **kwargs):
        """Add allowed effect types to the restriction."""
        if not create:
            return
        if extracted:
            for effect_type in extracted:
                self.allowed_effect_types.add(effect_type)


class ResonanceAssociationFactory(factory.django.DjangoModelFactory):
    """Factory for ResonanceAssociation normalized tags."""

    class Meta:
        model = ResonanceAssociation
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Association {n}")
    description = factory.LazyAttribute(lambda o: f"Description for {o.name}.")
    category = ""


class AffinityModifierTypeFactory(ModifierTypeFactory):
    """Factory for creating affinity-category ModifierType instances."""

    class Meta:
        model = ModifierType
        django_get_or_create = ("category", "name")

    name = factory.Sequence(lambda n: f"Affinity{n}")
    category = factory.LazyFunction(
        lambda: ModifierCategoryFactory(name="affinity", description="Magical affinities")
    )
    description = factory.LazyAttribute(lambda o: f"The {o.name} affinity.")


class ResonanceModifierTypeFactory(ModifierTypeFactory):
    """Factory for creating resonance-category ModifierType instances."""

    class Meta:
        model = ModifierType
        django_get_or_create = ("category", "name")

    name = factory.Sequence(lambda n: f"Resonance{n}")
    category = factory.LazyFunction(
        lambda: ModifierCategoryFactory(name="resonance", description="Magical resonances")
    )
    description = factory.LazyAttribute(lambda o: f"The {o.name} resonance.")


class CharacterAuraFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CharacterAura

    character = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    celestial = Decimal("10.00")
    primal = Decimal("70.00")
    abyssal = Decimal("20.00")


class CharacterResonanceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CharacterResonance

    character = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    resonance = factory.SubFactory(ResonanceModifierTypeFactory)
    scope = ResonanceScope.SELF
    strength = ResonanceStrength.MODERATE
    flavor_text = ""
    is_active = True


# =============================================================================
# Phase 2: Gifts & Powers Factories
# =============================================================================


class IntensityTierFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = IntensityTier
        django_get_or_create = ("threshold",)

    name = factory.Sequence(lambda n: f"Tier {n}")
    threshold = factory.Sequence(lambda n: (n + 1) * 10)
    control_modifier = 0
    description = factory.LazyAttribute(lambda o: f"Tier at {o.threshold}+ intensity.")
    admin_notes = ""


class GiftFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Gift
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Gift {n}")
    affinity = factory.SubFactory(AffinityModifierTypeFactory)
    description = factory.LazyAttribute(lambda o: f"The {o.name} gift.")


class PowerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Power
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Power {n}")
    slug = factory.Sequence(lambda n: f"power-{n}")
    gift = factory.SubFactory(GiftFactory)
    affinity = factory.LazyAttribute(lambda o: o.gift.affinity)  # Inherits from gift
    base_intensity = 10
    base_control = 10
    anima_cost = 1
    level_requirement = 1
    description = factory.LazyAttribute(lambda o: f"The {o.name} power.")
    admin_notes = ""


class TechniqueFactory(factory.django.DjangoModelFactory):
    """Factory for Technique - NOT using django_get_or_create (player-created content)."""

    class Meta:
        model = Technique

    name = factory.Sequence(lambda n: f"Technique {n}")
    gift = factory.SubFactory(GiftFactory)
    style = factory.SubFactory(TechniqueStyleFactory)
    effect_type = factory.SubFactory(EffectTypeFactory)
    level = 1
    anima_cost = 2
    description = factory.LazyAttribute(lambda o: f"The {o.name} technique.")

    @factory.post_generation
    def restrictions(self, create, extracted, **kwargs):
        """Add restrictions to the technique."""
        if not create:
            return
        if extracted:
            for restriction in extracted:
                self.restrictions.add(restriction)


class CharacterGiftFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CharacterGift
        django_get_or_create = ("character", "gift")

    character = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    gift = factory.SubFactory(GiftFactory)


class CharacterTechniqueFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CharacterTechnique
        django_get_or_create = ("character", "technique")

    character = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    technique = factory.SubFactory(TechniqueFactory)


class CharacterPowerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CharacterPower

    character = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    power = factory.SubFactory(PowerFactory)
    times_used = 0
    notes = ""


# =============================================================================
# Phase 3: Anima Factories
# =============================================================================


class CharacterAnimaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CharacterAnima

    character = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    current = 10
    maximum = 10


class AnimaRitualTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AnimaRitualType
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Ritual Type {n}")
    slug = factory.Sequence(lambda n: f"ritual-type-{n}")
    category = AnimaRitualCategory.SOLITARY
    description = factory.LazyAttribute(lambda o: f"The {o.name} ritual.")
    admin_notes = ""
    base_recovery = 5


class CharacterAnimaRitualFactory(factory.django.DjangoModelFactory):
    """Factory for CharacterAnimaRitual with stat + skill + resonance."""

    class Meta:
        model = CharacterAnimaRitual

    character = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    stat = factory.SubFactory("world.traits.factories.TraitFactory", trait_type="stat")
    skill = factory.SubFactory("world.skills.factories.SkillFactory")
    specialization = None
    resonance = factory.SubFactory(ResonanceModifierTypeFactory)
    description = factory.Faker("paragraph")


class AnimaRitualPerformanceFactory(factory.django.DjangoModelFactory):
    """Factory for AnimaRitualPerformance records."""

    class Meta:
        model = AnimaRitualPerformance

    ritual = factory.SubFactory(CharacterAnimaRitualFactory)
    target_character = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    was_successful = True
    anima_recovered = factory.LazyAttribute(lambda o: 5 if o.was_successful else None)


# =============================================================================
# Phase 4: Threads Factories
# =============================================================================


class ThreadTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ThreadType
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Thread Type {n}")
    slug = factory.Sequence(lambda n: f"thread-type-{n}")
    description = factory.LazyAttribute(lambda o: f"The {o.name} relationship.")
    admin_notes = ""


class ThreadFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Thread

    initiator = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    receiver = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    romantic = 0
    trust = 0
    rivalry = 0
    protective = 0
    enmity = 0
    is_soul_tether = False


class ThreadJournalFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ThreadJournal

    thread = factory.SubFactory(ThreadFactory)
    author = factory.LazyAttribute(lambda o: o.thread.initiator)
    content = "A moment that defined our connection."


class ThreadResonanceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ThreadResonance

    thread = factory.SubFactory(ThreadFactory)
    resonance = factory.SubFactory(ResonanceModifierTypeFactory)
    strength = ResonanceStrength.MODERATE
    flavor_text = ""


# =============================================================================
# Phase 5: Motif Factories
# =============================================================================


class MotifFactory(factory.django.DjangoModelFactory):
    """Factory for Motif - character-level magical aesthetic."""

    class Meta:
        model = Motif

    character = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    draft = None
    description = factory.Faker("paragraph")


class MotifResonanceFactory(factory.django.DjangoModelFactory):
    """Factory for MotifResonance - resonance attached to a motif."""

    class Meta:
        model = MotifResonance

    motif = factory.SubFactory(MotifFactory)
    resonance = factory.SubFactory(ResonanceModifierTypeFactory)
    is_from_gift = False


class MotifResonanceAssociationFactory(factory.django.DjangoModelFactory):
    """Factory for MotifResonanceAssociation - normalized tag linkage."""

    class Meta:
        model = MotifResonanceAssociation

    motif_resonance = factory.SubFactory(MotifResonanceFactory)
    association = factory.SubFactory(ResonanceAssociationFactory)
