from decimal import Decimal

import factory

from world.magic.models import (
    Affinity,
    AnimaRitualType,
    CharacterAnima,
    CharacterAnimaRitual,
    CharacterAura,
    CharacterGift,
    CharacterPower,
    CharacterResonance,
    Gift,
    IntensityTier,
    Power,
    Resonance,
    Thread,
    ThreadJournal,
    ThreadResonance,
    ThreadType,
)
from world.magic.types import (
    AffinityType,
    AnimaRitualCategory,
    ResonanceScope,
    ResonanceStrength,
)


class AffinityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Affinity
        django_get_or_create = ("affinity_type",)

    affinity_type = AffinityType.PRIMAL
    name = factory.LazyAttribute(lambda o: o.affinity_type.label)
    description = factory.LazyAttribute(lambda o: f"The {o.affinity_type.label} affinity.")
    admin_notes = ""


class ResonanceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Resonance
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Resonance {n}")
    slug = factory.Sequence(lambda n: f"resonance-{n}")
    default_affinity = factory.SubFactory(AffinityFactory)
    description = factory.LazyAttribute(lambda o: f"The {o.name} resonance.")
    admin_notes = ""


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
    resonance = factory.SubFactory(ResonanceFactory)
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
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Gift {n}")
    slug = factory.Sequence(lambda n: f"gift-{n}")
    affinity = factory.SubFactory(AffinityFactory)
    description = factory.LazyAttribute(lambda o: f"The {o.name} gift.")
    admin_notes = ""
    level_requirement = 1


class PowerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Power
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Power {n}")
    slug = factory.Sequence(lambda n: f"power-{n}")
    gift = factory.SubFactory(GiftFactory)
    affinity = factory.LazyAttribute(lambda o: o.gift.affinity)
    base_intensity = 10
    base_control = 10
    anima_cost = 1
    level_requirement = 1
    description = factory.LazyAttribute(lambda o: f"The {o.name} power.")
    admin_notes = ""


class CharacterGiftFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CharacterGift

    character = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    gift = factory.SubFactory(GiftFactory)
    notes = ""


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
    class Meta:
        model = CharacterAnimaRitual

    character = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    ritual_type = factory.SubFactory(AnimaRitualTypeFactory)
    personal_description = "A personal ritual of power."
    is_primary = False
    times_performed = 0


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
    resonance = factory.SubFactory(ResonanceFactory)
    strength = ResonanceStrength.MODERATE
    flavor_text = ""
