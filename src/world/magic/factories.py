from decimal import Decimal

import factory

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ConditionTemplateFactory
from world.magic.audere import SOULFRAY_CONDITION_NAME, AudereThreshold
from world.magic.constants import (
    AlterationTier,
    CantripArchetype,
    EffectKind,
    PendingAlterationStatus,
    RitualExecutionKind,
    TargetKind,
    VitalBonusTarget,
)
from world.magic.models import (
    Affinity,
    AnimaRitualPerformance,
    CharacterAnima,
    CharacterAnimaRitual,
    CharacterAura,
    CharacterFacet,
    CharacterGift,
    CharacterResonance,
    CharacterTechnique,
    CharacterThreadWeavingUnlock,
    CharacterTradition,
    EffectType,
    Facet,
    Gift,
    ImbuingProseTemplate,
    IntensityTier,
    MagicalAlterationEvent,
    MagicalAlterationTemplate,
    MishapPoolTier,
    Motif,
    MotifResonance,
    MotifResonanceAssociation,
    PendingAlteration,
    Resonance,
    Restriction,
    Ritual,
    RitualComponentRequirement,
    SoulfrayConfig,
    Technique,
    TechniqueCapabilityGrant,
    TechniqueOutcomeModifier,
    TechniqueStyle,
    Thread,
    ThreadLevelUnlock,
    ThreadPullCost,
    ThreadPullEffect,
    ThreadWeavingTeachingOffer,
    ThreadWeavingUnlock,
    ThreadXPLockedLevel,
    Tradition,
)
from world.magic.models.anima import AnimaConfig
from world.magic.types.ritual import SoulfrayContent
from world.traits.factories import TraitFactory


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


class AffinityFactory(factory.django.DjangoModelFactory):
    """Factory for Affinity model."""

    class Meta:
        model = Affinity
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Affinity{n}")
    description = factory.LazyAttribute(lambda o: f"The {o.name} affinity.")


class ResonanceFactory(factory.django.DjangoModelFactory):
    """Factory for Resonance model."""

    class Meta:
        model = Resonance
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Resonance{n}")
    description = factory.LazyAttribute(lambda o: f"The {o.name} resonance.")
    affinity = factory.SubFactory(AffinityFactory)
    opposite = None

    @factory.post_generation
    def properties(self, create: bool, extracted: list | None, **kwargs: object) -> None:
        if not create or not extracted:
            return
        self.properties.add(*extracted)


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
        django_get_or_create = ("character_sheet", "resonance")

    character_sheet = factory.SubFactory(CharacterSheetFactory)
    resonance = factory.SubFactory(ResonanceFactory)
    balance = 0
    lifetime_earned = 0
    flavor_text = ""

    class Params:
        with_balance = factory.Trait(balance=10, lifetime_earned=10)
        claimed_only = factory.Trait(balance=0, lifetime_earned=0)


# =============================================================================
# Phase 2: Gifts & Techniques Factories
# =============================================================================


class GiftFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Gift
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Gift {n}")
    description = factory.LazyAttribute(lambda o: f"The {o.name} gift.")


class TechniqueFactory(factory.django.DjangoModelFactory):
    """Factory for Technique - NOT using django_get_or_create (player-created content)."""

    class Meta:
        model = Technique

    name = factory.Sequence(lambda n: f"Technique {n}")
    gift = factory.SubFactory(GiftFactory)
    style = factory.SubFactory(TechniqueStyleFactory)
    effect_type = factory.SubFactory(EffectTypeFactory)
    level = 1
    intensity = 1
    control = 1
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


class TechniqueCapabilityGrantFactory(factory.django.DjangoModelFactory):
    """Factory for TechniqueCapabilityGrant."""

    class Meta:
        model = TechniqueCapabilityGrant

    technique = factory.SubFactory(TechniqueFactory)
    capability = factory.SubFactory("world.conditions.factories.CapabilityTypeFactory")
    base_value = 5
    intensity_multiplier = Decimal("1.0")


class IntensityTierFactory(factory.django.DjangoModelFactory):
    """Factory for IntensityTier - configurable power thresholds."""

    class Meta:
        model = IntensityTier

    name = factory.Sequence(lambda n: f"Tier {n}")
    threshold = factory.Sequence(lambda n: (n + 1) * 5)
    control_modifier = 0
    description = ""


class CharacterGiftFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CharacterGift
        django_get_or_create = ("character", "gift")

    character = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    gift = factory.SubFactory(GiftFactory)


class TraditionFactory(factory.django.DjangoModelFactory):
    """Factory for Tradition."""

    class Meta:
        model = Tradition
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Tradition {n}")
    description = factory.LazyAttribute(lambda o: f"Description of {o.name}.")
    is_active = True
    sort_order = 0


class CharacterTraditionFactory(factory.django.DjangoModelFactory):
    """Factory for CharacterTradition."""

    class Meta:
        model = CharacterTradition
        django_get_or_create = ("character", "tradition")

    character = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    tradition = factory.SubFactory(TraditionFactory)


class CharacterTechniqueFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CharacterTechnique
        django_get_or_create = ("character", "technique")

    character = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    technique = factory.SubFactory(TechniqueFactory)


# =============================================================================
# Phase 3: Anima Factories
# =============================================================================


class CharacterAnimaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CharacterAnima

    character = factory.SubFactory("evennia_extensions.factories.CharacterFactory")
    current = 10
    maximum = 10


class CharacterAnimaRitualFactory(factory.django.DjangoModelFactory):
    """Factory for CharacterAnimaRitual with stat + skill + resonance."""

    class Meta:
        model = CharacterAnimaRitual

    character = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    stat = factory.SubFactory("world.traits.factories.TraitFactory", trait_type="stat")
    skill = factory.SubFactory("world.skills.factories.SkillFactory")
    specialization = None
    resonance = factory.SubFactory(ResonanceFactory)
    check_type = factory.SubFactory("world.checks.factories.CheckTypeFactory")
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
# Phase 5: Motif Factories
# =============================================================================


class MotifFactory(factory.django.DjangoModelFactory):
    """Factory for Motif - character-level magical aesthetic."""

    class Meta:
        model = Motif

    character = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    description = factory.Faker("paragraph")


class MotifResonanceFactory(factory.django.DjangoModelFactory):
    """Factory for MotifResonance - resonance attached to a motif."""

    class Meta:
        model = MotifResonance

    motif = factory.SubFactory(MotifFactory)
    resonance = factory.SubFactory(ResonanceFactory)
    is_from_gift = False


# =============================================================================
# Phase 6: Facet Factories
# =============================================================================


class FacetFactory(factory.django.DjangoModelFactory):
    """Factory for Facet model."""

    class Meta:
        model = Facet

    name = factory.Sequence(lambda n: f"Facet{n}")
    description = factory.LazyAttribute(lambda o: f"The {o.name} facet.")
    parent = None


class CharacterFacetFactory(factory.django.DjangoModelFactory):
    """Factory for CharacterFacet model."""

    class Meta:
        model = CharacterFacet

    character = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    facet = factory.SubFactory(FacetFactory)
    resonance = factory.SubFactory(ResonanceFactory)
    flavor_text = factory.LazyAttribute(lambda o: f"The meaning of {o.facet.name}")


class MotifResonanceAssociationFactory(factory.django.DjangoModelFactory):
    """Factory for MotifResonanceAssociation - facet linkage."""

    class Meta:
        model = MotifResonanceAssociation

    motif_resonance = factory.SubFactory(MotifResonanceFactory)
    facet = factory.SubFactory(FacetFactory)


# =============================================================================
# Cantrip Factories
# =============================================================================


class CantripFactory(factory.django.DjangoModelFactory):
    """Factory for Cantrip - staff-curated starter technique templates."""

    class Meta:
        model = "magic.Cantrip"

    name = factory.Sequence(lambda n: f"Cantrip {n}")
    description = factory.Faker("sentence")
    archetype = CantripArchetype.ATTACK
    effect_type = factory.SubFactory(EffectTypeFactory)
    style = factory.SubFactory(TechniqueStyleFactory)
    base_intensity = 1
    base_control = 1
    base_anima_cost = 5
    requires_facet = False
    is_active = True
    sort_order = factory.Sequence(lambda n: n)


class AudereThresholdFactory(factory.django.DjangoModelFactory):
    """Factory for AudereThreshold global configuration."""

    class Meta:
        model = AudereThreshold

    minimum_intensity_tier = factory.SubFactory(IntensityTierFactory)
    minimum_warp_stage = factory.SubFactory("world.conditions.factories.ConditionStageFactory")
    intensity_bonus = 20
    anima_pool_bonus = 30
    warp_multiplier = 2


# =============================================================================
# Scope #3: Soulfray Progression Factories
# =============================================================================


class SoulfrayConfigFactory(factory.django.DjangoModelFactory):
    """Factory for SoulfrayConfig global configuration."""

    class Meta:
        model = SoulfrayConfig

    soulfray_threshold_ratio = Decimal("0.30")
    severity_scale = 10
    deficit_scale = 5
    resilience_check_type = factory.SubFactory("world.checks.factories.CheckTypeFactory")
    base_check_difficulty = 15
    # Ritual budget defaults per spec §8.7 (mirrors migration 0021 defaults)
    ritual_budget_critical_success = 10
    ritual_budget_success = 6
    ritual_budget_partial = 3
    ritual_budget_failure = 1
    ritual_severity_cost_per_point = 1


class MishapPoolTierFactory(factory.django.DjangoModelFactory):
    """Factory for MishapPoolTier deficit-to-pool mapping."""

    class Meta:
        model = MishapPoolTier

    min_deficit = 1
    max_deficit = None
    consequence_pool = factory.SubFactory("actions.factories.ConsequencePoolFactory")


class TechniqueOutcomeModifierFactory(factory.django.DjangoModelFactory):
    """Factory for TechniqueOutcomeModifier."""

    class Meta:
        model = TechniqueOutcomeModifier

    outcome = factory.SubFactory("world.traits.factories.CheckOutcomeFactory")
    modifier_value = 0


# =============================================================================
# Scope #5: Magical Alteration Factories
# =============================================================================


class MagicalAlterationTemplateFactory(factory.django.DjangoModelFactory):
    """Factory for MagicalAlterationTemplate."""

    class Meta:
        model = MagicalAlterationTemplate

    condition_template = factory.SubFactory(ConditionTemplateFactory)
    tier = AlterationTier.MARKED
    origin_affinity = factory.SubFactory(AffinityFactory)
    origin_resonance = factory.LazyAttribute(
        lambda o: ResonanceFactory(affinity=o.origin_affinity),
    )
    weakness_magnitude = 0
    resonance_bonus_magnitude = 0
    social_reactivity_magnitude = 0
    is_visible_at_rest = False
    is_library_entry = False


class PendingAlterationFactory(factory.django.DjangoModelFactory):
    """Factory for PendingAlteration."""

    class Meta:
        model = PendingAlteration

    character = factory.SubFactory(CharacterSheetFactory)
    status = PendingAlterationStatus.OPEN
    tier = AlterationTier.MARKED
    origin_affinity = factory.SubFactory(AffinityFactory)
    origin_resonance = factory.LazyAttribute(
        lambda o: ResonanceFactory(affinity=o.origin_affinity),
    )


class MagicalAlterationEventFactory(factory.django.DjangoModelFactory):
    """Factory for MagicalAlterationEvent."""

    class Meta:
        model = MagicalAlterationEvent

    character = factory.SubFactory(CharacterSheetFactory)
    alteration_template = factory.SubFactory(MagicalAlterationTemplateFactory)


# =============================================================================
# Resonance Pivot Spec A — Phase 3 Lookup Factories
# =============================================================================


class ThreadPullCostFactory(factory.django.DjangoModelFactory):
    """Factory for ThreadPullCost — per-tier pull cost lookup."""

    class Meta:
        model = ThreadPullCost
        django_get_or_create = ("tier",)

    tier = 1
    resonance_cost = 1
    anima_per_thread = 1
    label = "soft"


class ThreadXPLockedLevelFactory(factory.django.DjangoModelFactory):
    """Factory for ThreadXPLockedLevel — XP-locked level boundaries."""

    class Meta:
        model = ThreadXPLockedLevel
        django_get_or_create = ("level",)

    level = 20
    xp_cost = 200


class ThreadPullEffectFactory(factory.django.DjangoModelFactory):
    """Factory for ThreadPullEffect — authored pull-effect templates.

    Defaults to a tier-0 FLAT_BONUS for a fresh resonance. Use traits
    (as_intensity_bump, as_vital_bonus, as_capability_grant,
    as_narrative_only) to switch payload shape.
    """

    class Meta:
        model = ThreadPullEffect

    target_kind = TargetKind.TRAIT
    resonance = factory.SubFactory(ResonanceFactory)
    tier = 0
    min_thread_level = 0
    effect_kind = EffectKind.FLAT_BONUS
    flat_bonus_amount = 1

    class Params:
        as_flat_bonus = factory.Trait(
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=2,
        )
        as_intensity_bump = factory.Trait(
            effect_kind=EffectKind.INTENSITY_BUMP,
            intensity_bump_amount=1,
            flat_bonus_amount=None,
        )
        as_vital_bonus = factory.Trait(
            effect_kind=EffectKind.VITAL_BONUS,
            flat_bonus_amount=None,
            vital_bonus_amount=5,
            vital_target=VitalBonusTarget.MAX_HEALTH,
        )
        as_capability_grant = factory.Trait(
            effect_kind=EffectKind.CAPABILITY_GRANT,
            flat_bonus_amount=None,
            capability_grant=factory.SubFactory(
                "world.conditions.factories.CapabilityTypeFactory",
            ),
        )
        as_narrative_only = factory.Trait(
            effect_kind=EffectKind.NARRATIVE_ONLY,
            flat_bonus_amount=None,
            narrative_snippet="A whisper at the edge of hearing.",
        )


class ImbuingProseTemplateFactory(factory.django.DjangoModelFactory):
    """Factory for ImbuingProseTemplate — authored fallback prose templates."""

    class Meta:
        model = ImbuingProseTemplate

    resonance = factory.SubFactory(ResonanceFactory)
    target_kind = TargetKind.TRAIT
    prose = "default prose"


class RitualFactory(factory.django.DjangoModelFactory):
    """Factory for Ritual.

    Defaults to a SERVICE-kind ritual with a placeholder dotted path so the
    default factory build passes clean(). Override execution_kind / flow /
    service_function_path for other shapes.
    """

    class Meta:
        model = Ritual
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Ritual {n}")
    description = factory.Faker("paragraph")
    hedge_accessible = False
    glimpse_eligible = False
    narrative_prose = factory.Faker("paragraph")
    execution_kind = RitualExecutionKind.SERVICE
    service_function_path = "world.magic.services.placeholder_ritual"
    flow = None


class ImbuingRitualFactory(RitualFactory):
    """Seed factory for the canonical 'Rite of Imbuing' ritual.

    Uses django_get_or_create so repeated calls in tests return the same row.
    Spec A §4.3 lines 1270-1286.
    """

    class Meta:
        model = Ritual
        django_get_or_create = ("name",)

    name = "Rite of Imbuing"
    execution_kind = RitualExecutionKind.SERVICE
    service_function_path = "world.magic.services.spend_resonance_for_imbuing"
    flow = None


class RitualComponentRequirementFactory(factory.django.DjangoModelFactory):
    """Factory for RitualComponentRequirement."""

    class Meta:
        model = RitualComponentRequirement

    ritual = factory.SubFactory(RitualFactory)
    item_template = factory.SubFactory("world.items.factories.ItemTemplateFactory")
    quantity = 1
    min_quality_tier = None


# =============================================================================
# Resonance Pivot Spec A — Phase 4 Thread Factories
# =============================================================================


class ThreadFactory(factory.django.DjangoModelFactory):
    """Factory for Thread.

    Defaults to TRAIT-kind (the simplest discriminator with no typeclass-registry
    coupling). Override target_kind + the matching target_* FK for other shapes.

    Convenience post-gen params (Phase 10, Spec A §2.4 cap-helper tests):
    - as_trait_thread=True  → keep TRAIT kind; use with _trait_value=<int>
    - _trait_value=<int>    → set CharacterTraitValue.value for (owner, target_trait)
    - as_technique_thread=True → switch to TECHNIQUE kind; use with _technique_level=<int>
    - _technique_level=<int>   → set target_technique.level (saved in place)
    - as_track_thread=True  → switch to RELATIONSHIP_TRACK kind
    - _track_tier_index=<int>  → create a RelationshipTier with that tier_number on the
                                 progress.track; set developed_points >= threshold so
                                 current_tier returns that tier
    - as_capstone_thread=True  → switch to RELATIONSHIP_CAPSTONE kind
    - _path_stage=<int>        → add a CharacterPathHistory row for thread.owner with
                                 a Path of that stage (applies to capstone + effective cap)
    - as_item_thread=True   → switch to ITEM kind (raises AnchorCapNotImplemented)
    - as_room_thread=True   → switch to ROOM kind (raises AnchorCapNotImplemented)

    NOTE: this factory intentionally does NOT call full_clean(). DB-level
    CheckConstraints catch shape errors at write time; clean() is opt-in via
    tests that exercise validation explicitly.
    """

    class Meta:
        model = Thread

    owner = factory.SubFactory(CharacterSheetFactory)
    resonance = factory.SubFactory(ResonanceFactory)
    target_kind = TargetKind.TRAIT
    target_trait = factory.SubFactory(TraitFactory)
    level = 0
    developed_points = 0

    @factory.post_generation  # type: ignore[misc]
    def as_trait_thread(self: "Thread", create: bool, extracted: object, **kwargs: object) -> None:
        """No-op: TRAIT is already the default kind. Exists for test readability."""

    @factory.post_generation  # type: ignore[misc]
    def _trait_value(self: "Thread", create: bool, extracted: object, **kwargs: object) -> None:
        """Set CharacterTraitValue.value for (owner.character, target_trait)."""
        if not create or extracted is None:
            return
        from world.traits.models import CharacterTraitValue

        CharacterTraitValue.objects.update_or_create(
            character=self.owner.character,
            trait=self.target_trait,
            defaults={"value": int(extracted)},  # type: ignore[arg-type]
        )

    @factory.post_generation  # type: ignore[misc]
    def as_technique_thread(
        self: "Thread", create: bool, extracted: object, **kwargs: object
    ) -> None:
        """Switch to TECHNIQUE kind: create a Technique, clear target_trait."""
        if not create or not extracted:
            return
        tech = TechniqueFactory(level=1)
        Thread.objects.filter(pk=self.pk).update(
            target_kind=TargetKind.TECHNIQUE,
            target_technique=tech,
            target_trait=None,
        )
        self.target_kind = TargetKind.TECHNIQUE
        self.target_technique = tech
        self.target_trait = None  # type: ignore[assignment]

    @factory.post_generation  # type: ignore[misc]
    def _technique_level(self: "Thread", create: bool, extracted: object, **kwargs: object) -> None:
        """Set target_technique.level (after as_technique_thread has run)."""
        if not create or extracted is None:
            return
        if self.target_technique is not None:
            self.target_technique.level = int(extracted)  # type: ignore[arg-type]
            self.target_technique.save(update_fields=["level"])

    @factory.post_generation  # type: ignore[misc]
    def as_track_thread(self: "Thread", create: bool, extracted: object, **kwargs: object) -> None:
        """Switch to RELATIONSHIP_TRACK kind: create a RelationshipTrackProgress."""
        if not create or not extracted:
            return
        from world.relationships.factories import RelationshipTrackProgressFactory

        progress = RelationshipTrackProgressFactory()
        Thread.objects.filter(pk=self.pk).update(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            target_relationship_track=progress,
            target_trait=None,
        )
        self.target_kind = TargetKind.RELATIONSHIP_TRACK
        self.target_relationship_track = progress
        self.target_trait = None  # type: ignore[assignment]

    @factory.post_generation  # type: ignore[misc]
    def _track_tier_index(
        self: "Thread", create: bool, extracted: object, **kwargs: object
    ) -> None:
        """Create a RelationshipTier with tier_number=extracted on the progress track.

        Sets developed_points on the progress so that current_tier returns the
        newly created tier (developed_points = tier.point_threshold).
        """
        if not create or extracted is None:
            return
        if self.target_relationship_track is None:
            return
        tier_number = int(extracted)  # type: ignore[arg-type]
        from world.relationships.factories import RelationshipTierFactory

        progress = self.target_relationship_track
        tier = RelationshipTierFactory(
            track=progress.track,
            tier_number=tier_number,
            point_threshold=tier_number * 10,
        )
        # Set developed_points so current_tier resolves to this tier.
        progress.developed_points = tier.point_threshold
        progress.save(update_fields=["developed_points"])

    @factory.post_generation  # type: ignore[misc]
    def as_capstone_thread(
        self: "Thread", create: bool, extracted: object, **kwargs: object
    ) -> None:
        """Switch to RELATIONSHIP_CAPSTONE kind: create a RelationshipCapstone."""
        if not create or not extracted:
            return
        from world.relationships.factories import RelationshipCapstoneFactory

        capstone = RelationshipCapstoneFactory()
        Thread.objects.filter(pk=self.pk).update(
            target_kind=TargetKind.RELATIONSHIP_CAPSTONE,
            target_capstone=capstone,
            target_trait=None,
        )
        self.target_kind = TargetKind.RELATIONSHIP_CAPSTONE
        self.target_capstone = capstone
        self.target_trait = None  # type: ignore[assignment]

    @factory.post_generation  # type: ignore[misc]
    def _path_stage(self: "Thread", create: bool, extracted: object, **kwargs: object) -> None:
        """Add a CharacterPathHistory row for thread.owner with a Path of the given stage."""
        if not create or extracted is None:
            return
        stage = int(extracted)  # type: ignore[arg-type]
        from world.classes.factories import PathFactory
        from world.progression.models.paths import CharacterPathHistory

        path = PathFactory(stage=stage)
        CharacterPathHistory.objects.create(character=self.owner.character, path=path)

    @factory.post_generation  # type: ignore[misc]
    def as_item_thread(self: "Thread", create: bool, extracted: object, **kwargs: object) -> None:
        """Switch to ITEM kind: create an ObjectDB."""
        if not create or not extracted:
            return
        from evennia_extensions.factories import ObjectDBFactory

        obj = ObjectDBFactory()
        Thread.objects.filter(pk=self.pk).update(
            target_kind=TargetKind.ITEM,
            target_object=obj,
            target_trait=None,
        )
        self.target_kind = TargetKind.ITEM
        self.target_object = obj
        self.target_trait = None  # type: ignore[assignment]

    @factory.post_generation  # type: ignore[misc]
    def as_room_thread(self: "Thread", create: bool, extracted: object, **kwargs: object) -> None:
        """Switch to ROOM kind: create an ObjectDB."""
        if not create or not extracted:
            return
        from evennia_extensions.factories import ObjectDBFactory

        obj = ObjectDBFactory()
        Thread.objects.filter(pk=self.pk).update(
            target_kind=TargetKind.ROOM,
            target_object=obj,
            target_trait=None,
        )
        self.target_kind = TargetKind.ROOM
        self.target_object = obj
        self.target_trait = None  # type: ignore[assignment]


class ThreadLevelUnlockFactory(factory.django.DjangoModelFactory):
    """Factory for ThreadLevelUnlock — per-thread level-unlock receipt."""

    class Meta:
        model = ThreadLevelUnlock

    thread = factory.SubFactory(ThreadFactory)
    unlocked_level = 20
    xp_spent = 200


# =============================================================================
# Resonance Pivot Spec A — Phase 5 ThreadWeaving Factories
# =============================================================================


class ThreadWeavingUnlockFactory(factory.django.DjangoModelFactory):
    """Factory for ThreadWeavingUnlock — authored unlock catalog.

    Defaults to TRAIT-kind (the simplest discriminator with no typeclass-registry
    coupling). Override target_kind + the matching unlock_* field for other shapes.
    Pass ``unlock_trait=None`` explicitly when switching to another kind so the
    factory's default doesn't populate the wrong column.

    NOTE: this factory intentionally does NOT call full_clean(). DB-level
    CheckConstraints catch shape errors at write time; clean() is opt-in via
    tests that exercise validation explicitly.
    """

    class Meta:
        model = ThreadWeavingUnlock

    target_kind = TargetKind.TRAIT
    unlock_trait = factory.SubFactory(TraitFactory)
    xp_cost = 100


class CharacterThreadWeavingUnlockFactory(factory.django.DjangoModelFactory):
    """Factory for CharacterThreadWeavingUnlock — per-character purchase record."""

    class Meta:
        model = CharacterThreadWeavingUnlock

    character = factory.SubFactory(CharacterSheetFactory)
    unlock = factory.SubFactory(ThreadWeavingUnlockFactory)
    xp_spent = 100
    teacher = None


class ThreadWeavingTeachingOfferFactory(factory.django.DjangoModelFactory):
    """Factory for ThreadWeavingTeachingOffer — teacher-side offer record."""

    class Meta:
        model = ThreadWeavingTeachingOffer

    teacher = factory.SubFactory("world.roster.factories.RosterTenureFactory")
    unlock = factory.SubFactory(ThreadWeavingUnlockFactory)
    pitch = factory.Faker("paragraph")
    gold_cost = 0
    banked_ap = 0


# =============================================================================
# Scope 6 §8 — Seed Content Factories
# =============================================================================


class AnimaConfigFactory(factory.django.DjangoModelFactory):
    """Factory for AnimaConfig singleton (spec §8.8).

    Uses django_get_or_create on pk=1 to mirror AnimaConfig.get_singleton().
    Repeated calls in the same test DB return the same row.
    """

    class Meta:
        model = AnimaConfig
        django_get_or_create = ("id",)

    id = 1
    daily_regen_percent = 5
    daily_regen_blocking_property_key = "blocks_anima_regen"


class _SoulfrayContentFactory:
    """Callable helper that seeds the 5-stage Soulfray condition per spec §8.1.

    Not a DjangoModelFactory — this is a composition helper. Callers invoke
    ``SoulfrayContentFactory()`` to get a ``SoulfrayContent`` dataclass holding:
      - template: the seeded ConditionTemplate (name=SOULFRAY_CONDITION_NAME)
      - stages: list of 5 ConditionStage rows [Fraying, Tearing, Ripping,
                Sundering, Unravelling] in stage_order order
      - blocks_anima_regen: the seeded Property row (name="blocks_anima_regen")

    After stage creation, backfills
    ``template.passive_decay_max_severity = stages[1].severity_threshold - 1``
    (= 5, one below Tearing) so passive decay only operates at stage 1.

    Idempotent: uses get_or_create on template name and stage unique_together
    so running twice in one test class setup does not double-create rows.
    """

    # Stage spec per §8.1
    _STAGES = [
        {"stage_order": 1, "name": "Fraying", "severity_threshold": 1},
        {"stage_order": 2, "name": "Tearing", "severity_threshold": 6},
        {"stage_order": 3, "name": "Ripping", "severity_threshold": 16},
        {"stage_order": 4, "name": "Sundering", "severity_threshold": 36},
        {"stage_order": 5, "name": "Unravelling", "severity_threshold": 66},
    ]

    def __call__(self) -> SoulfrayContent:
        from world.conditions.models import ConditionStage
        from world.mechanics.factories import BlocksAnimaRegenPropertyFactory

        # Ensure the blocks_anima_regen property exists
        blocks_prop = BlocksAnimaRegenPropertyFactory()

        # Build the Soulfray ConditionTemplate (get_or_create via factory's
        # django_get_or_create on name)
        template = ConditionTemplateFactory(
            name=SOULFRAY_CONDITION_NAME,
            has_progression=True,
            passive_decay_per_day=1,
            passive_decay_blocked_in_engagement=True,
        )

        stages = []
        for spec in self._STAGES:
            stage, _ = ConditionStage.objects.get_or_create(
                condition=template,
                stage_order=spec["stage_order"],
                defaults={
                    "name": spec["name"],
                    "severity_threshold": spec["severity_threshold"],
                    "description": f"Soulfray {spec['name']} stage.",
                },
            )
            stages.append(stage)

        # Wire blocks_anima_regen onto stages 2–5 (Tearing onward, per §8.4)
        for stage in stages[1:]:
            stage.properties.add(blocks_prop)

        # Backfill passive_decay_max_severity = Tearing.severity_threshold - 1 = 5
        tearing_threshold = stages[1].severity_threshold
        if template.passive_decay_max_severity != tearing_threshold - 1:
            template.passive_decay_max_severity = tearing_threshold - 1
            template.save(update_fields=["passive_decay_max_severity"])

        return SoulfrayContent(
            template=template,
            stages=tuple(stages),
            blocks_anima_regen=blocks_prop,
        )


SoulfrayContentFactory = _SoulfrayContentFactory()


class ResonanceGainConfigFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "magic.ResonanceGainConfig"
        django_get_or_create = ("pk",)

    pk = 1


class RoomAuraProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "magic.RoomAuraProfile"

    room_profile = factory.SubFactory("evennia_extensions.factories.RoomProfileFactory")


class RoomResonanceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "magic.RoomResonance"

    room_aura_profile = factory.SubFactory(RoomAuraProfileFactory)
    resonance = factory.SubFactory(ResonanceFactory)


def wire_soulfray_aftermath(content: SoulfrayContent) -> None:
    """Create ConditionStageOnEntry rows for Soulfray aftermath per spec §8.3.

    Stage 3 (Ripping)   → soul_ache severity=1
    Stage 4 (Sundering) → soul_ache severity=1, arcane_tremor severity=1
    Stage 5 (Unravelling) → arcane_tremor severity=1, aura_bleed severity=2

    Requires the aftermath ConditionTemplates to already exist (created by
    SoulAcheTemplateFactory, ArcaneTremorTemplateFactory, AuraBleedTemplateFactory).
    Idempotent: get_or_create on the through-model's unique constraint.
    """
    from world.conditions.models import (
        ConditionStageOnEntry,
        ConditionTemplate,
    )

    soul_ache = ConditionTemplate.objects.get(name="soul_ache")
    arcane_tremor = ConditionTemplate.objects.get(name="arcane_tremor")
    aura_bleed = ConditionTemplate.objects.get(name="aura_bleed")

    ripping = content.stages[2]
    sundering = content.stages[3]
    unravelling = content.stages[4]

    # Stage 3 → soul_ache
    ConditionStageOnEntry.objects.get_or_create(
        stage=ripping, condition=soul_ache, defaults={"severity": 1}
    )

    # Stage 4 → soul_ache + arcane_tremor
    ConditionStageOnEntry.objects.get_or_create(
        stage=sundering, condition=soul_ache, defaults={"severity": 1}
    )
    ConditionStageOnEntry.objects.get_or_create(
        stage=sundering, condition=arcane_tremor, defaults={"severity": 1}
    )

    # Stage 5 → arcane_tremor + aura_bleed
    ConditionStageOnEntry.objects.get_or_create(
        stage=unravelling, condition=arcane_tremor, defaults={"severity": 1}
    )
    ConditionStageOnEntry.objects.get_or_create(
        stage=unravelling, condition=aura_bleed, defaults={"severity": 2}
    )
