"""
Factory definitions for character creation system tests.
"""

import factory
import factory.django as factory_django

from world.character_creation.models import (
    Beginnings,
    CharacterDraft,
    DraftAnimaRitual,
    DraftGift,
    DraftMotif,
    DraftMotifResonance,
    DraftTechnique,
    StartingArea,
)
from world.realms.models import Realm


class RealmFactory(factory_django.DjangoModelFactory):
    """Factory for creating Realm instances."""

    class Meta:
        model = Realm
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"TestRealm{n}")
    description = factory.LazyAttribute(lambda obj: f"Description of {obj.name}")


class StartingAreaFactory(factory_django.DjangoModelFactory):
    """Factory for creating StartingArea instances."""

    class Meta:
        model = StartingArea
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"TestArea{n}")
    description = factory.LazyAttribute(lambda obj: f"Description of {obj.name}")
    realm = factory.SubFactory(RealmFactory)
    is_active = True
    access_level = StartingArea.AccessLevel.ALL
    minimum_trust = 0


class BeginningsFactory(factory_django.DjangoModelFactory):
    """Factory for creating Beginnings instances."""

    class Meta:
        model = Beginnings

    name = factory.Sequence(lambda n: f"TestBeginnings{n}")
    description = factory.LazyAttribute(lambda obj: f"Description of {obj.name}")
    starting_area = factory.SubFactory(StartingAreaFactory)
    is_active = True
    trust_required = 0
    family_known = True
    grants_species_languages = True
    sort_order = 0
    cg_point_cost = 0
    social_rank = 0


class CharacterDraftFactory(factory_django.DjangoModelFactory):
    """Factory for creating CharacterDraft instances."""

    class Meta:
        model = CharacterDraft

    account = factory.SubFactory("evennia_extensions.factories.AccountFactory")
    selected_area = factory.SubFactory(StartingAreaFactory)
    current_stage = CharacterDraft.Stage.ORIGIN

    # Stage 5: Path
    selected_path = None  # Optional, set in tests as needed

    # Stage 7: Appearance fields (default to None)
    height_band = None
    height_inches = None
    build = None


class DraftGiftFactory(factory_django.DjangoModelFactory):
    """Factory for creating DraftGift instances."""

    class Meta:
        model = DraftGift

    draft = factory.SubFactory(CharacterDraftFactory)
    name = factory.Sequence(lambda n: f"Draft Gift {n}")
    affinity = factory.SubFactory("world.magic.factories.AffinityModifierTypeFactory")
    description = factory.LazyAttribute(lambda obj: f"Description of {obj.name}")


class DraftTechniqueFactory(factory_django.DjangoModelFactory):
    """Factory for creating DraftTechnique instances."""

    class Meta:
        model = DraftTechnique

    gift = factory.SubFactory(DraftGiftFactory)
    name = factory.Sequence(lambda n: f"Draft Technique {n}")
    style = factory.SubFactory("world.magic.factories.TechniqueStyleFactory")
    effect_type = factory.SubFactory("world.magic.factories.EffectTypeFactory")
    level = 1
    description = factory.LazyAttribute(lambda obj: f"Description of {obj.name}")


class DraftMotifFactory(factory_django.DjangoModelFactory):
    """Factory for creating DraftMotif instances."""

    class Meta:
        model = DraftMotif

    draft = factory.SubFactory(CharacterDraftFactory)
    description = factory.Sequence(lambda n: f"Draft Motif description {n}")


class DraftMotifResonanceFactory(factory_django.DjangoModelFactory):
    """Factory for creating DraftMotifResonance instances."""

    class Meta:
        model = DraftMotifResonance

    motif = factory.SubFactory(DraftMotifFactory)
    resonance = factory.SubFactory("world.magic.factories.ResonanceModifierTypeFactory")
    is_from_gift = True


class DraftAnimaRitualFactory(factory_django.DjangoModelFactory):
    """Factory for creating DraftAnimaRitual instances."""

    class Meta:
        model = DraftAnimaRitual

    draft = factory.SubFactory(CharacterDraftFactory)
    stat = factory.SubFactory("world.traits.factories.TraitFactory")
    skill = factory.SubFactory("world.skills.factories.SkillFactory")
    specialization = None
    resonance = factory.SubFactory("world.magic.factories.ResonanceModifierTypeFactory")
    description = factory.Sequence(lambda n: f"Anima ritual description {n}")
