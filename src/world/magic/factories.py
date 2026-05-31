from datetime import UTC, datetime, timedelta
from decimal import Decimal

import factory

from actions.constants import ActionCategory
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ConditionTemplateFactory
from world.covenants.factories import CovenantFactory, CovenantRoleFactory
from world.magic.audere import SOULFRAY_CONDITION_NAME, AudereThreshold
from world.magic.constants import (
    AffinityInteractionAggressor,
    AffinityInteractionKind,
    AlterationKind,
    AlterationTier,
    CantripArchetype,
    EffectKind,
    ParticipationRule,
    PendingAlterationStatus,
    ResonanceValence,
    RitualExecutionKind,
    TargetKind,
    VitalBonusTarget,
)
from world.magic.models import (
    Affinity,
    AffinityInteraction,
    AnimaRitualPerformance,
    CharacterAnima,
    CharacterAura,
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
    RitualSceneActionConfig,
    SoulfrayConfig,
    Technique,
    TechniqueAppliedCondition,
    TechniqueCapabilityGrant,
    TechniqueCapabilityRequirement,
    TechniqueDamageProfile,
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
from world.magic.models.knowledge import CharacterRitualKnowledge
from world.magic.types.ritual import SoulfrayContent
from world.roster.factories import RosterEntryFactory
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


class AffinityInteractionFactory(factory.django.DjangoModelFactory):
    """Factory for AffinityInteraction directed-pair rows."""

    class Meta:
        model = AffinityInteraction

    source_affinity = factory.SubFactory(AffinityFactory)
    environment_affinity = factory.SubFactory(AffinityFactory)
    valence = ResonanceValence.ALIGNED
    kind = AffinityInteractionKind.AMPLIFY
    aggressor = AffinityInteractionAggressor.ENVIRONMENT


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
    action_category = ActionCategory.PHYSICAL
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

    @factory.post_generation
    def damage_profile(self, create, extracted, **kwargs):
        """Auto-seed a damage profile from EffectType.base_power when present.

        Pass damage_profile=False to skip. Pass any non-False truthy value
        to also skip (caller has attached their own profile).
        """
        if not create:
            return
        if extracted is False:
            return
        if extracted is not None:
            return
        if self.effect_type.base_power:
            TechniqueDamageProfileFactory(
                technique=self,
                base_damage=self.effect_type.base_power,
            )


class TechniqueCapabilityGrantFactory(factory.django.DjangoModelFactory):
    """Factory for TechniqueCapabilityGrant."""

    class Meta:
        model = TechniqueCapabilityGrant

    technique = factory.SubFactory(TechniqueFactory)
    capability = factory.SubFactory("world.conditions.factories.CapabilityTypeFactory")
    base_value = 5
    intensity_multiplier = Decimal("1.0")


class TechniqueCapabilityRequirementFactory(factory.django.DjangoModelFactory):
    """Factory for TechniqueCapabilityRequirement."""

    class Meta:
        model = TechniqueCapabilityRequirement

    technique = factory.SubFactory(TechniqueFactory)
    capability = factory.SubFactory("world.conditions.factories.CapabilityTypeFactory")
    minimum_value = 1


class TechniqueAppliedConditionFactory(factory.django.DjangoModelFactory):
    """Factory for TechniqueAppliedCondition — technique-to-condition through model."""

    class Meta:
        model = TechniqueAppliedCondition

    technique = factory.SubFactory(TechniqueFactory)
    condition = factory.SubFactory("world.conditions.factories.ConditionTemplateFactory")
    target_kind = "enemy"
    minimum_success_level = 1
    base_severity = 1
    severity_intensity_multiplier = Decimal(0)
    severity_per_extra_sl = 0
    base_duration_rounds = None
    duration_intensity_multiplier = Decimal(0)
    duration_per_extra_sl = 0
    stack_count = 1


class TechniqueDamageProfileFactory(factory.django.DjangoModelFactory):
    """Factory for TechniqueDamageProfile — per-component damage scaling row."""

    class Meta:
        model = TechniqueDamageProfile

    technique = factory.SubFactory("world.magic.factories.TechniqueFactory", damage_profile=False)
    damage_type = None
    minimum_success_level = 1
    base_damage = 5
    damage_intensity_multiplier = Decimal(0)
    damage_per_extra_sl = 0


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
    client_hosted = True


class AtonementRitualFactory(RitualFactory):
    """Seed factory for the canonical 'Rite of Atonement' ritual.

    SERVICE-dispatched (deviation from spec §4.1 FLOW recommendation — see
    services/atonement.py for rationale).  Uses django_get_or_create so
    repeated calls in tests return the same row.  Scope #7 Phase 8.
    """

    class Meta:
        model = Ritual
        django_get_or_create = ("name",)

    name = "Rite of Atonement"
    description = (
        "A ritual of self-cleansing for those touched by corruption. "
        "Effective only at stages 1-2; requires Celestial or Primal affinity."
    )
    narrative_prose = (
        "The performer kneels at a consecrated site and speaks the words of "
        "unbinding, drawing the corruption out of themselves through sustained "
        "focus and will. The process is painful and requires witnesses to anchor "
        "the soul."
    )
    execution_kind = RitualExecutionKind.SERVICE
    service_function_path = "world.magic.services.atonement.perform_atonement_rite"
    flow = None
    hedge_accessible = False
    glimpse_eligible = False


class RitualComponentRequirementFactory(factory.django.DjangoModelFactory):
    """Factory for RitualComponentRequirement."""

    class Meta:
        model = RitualComponentRequirement

    ritual = factory.SubFactory(RitualFactory)
    item_template = factory.SubFactory("world.items.factories.ItemTemplateFactory")
    quantity = 1
    min_quality_tier = None


class RitualSceneActionConfigFactory(factory.django.DjangoModelFactory):
    """Factory for RitualSceneActionConfig sidecar.

    Requires a SCENE_ACTION ritual. The stat/skill/check_type mirrors the
    CharacterAnimaRitual factory pattern.
    """

    class Meta:
        model = RitualSceneActionConfig

    ritual = factory.SubFactory(
        RitualFactory,
        execution_kind=RitualExecutionKind.SCENE_ACTION,
        service_function_path="",
        flow=None,
    )
    stat = factory.SubFactory(TraitFactory)
    skill = factory.SubFactory("world.skills.factories.SkillFactory")
    specialization = None
    resonance = None
    check_type = factory.SubFactory("world.checks.factories.CheckTypeFactory")
    target_difficulty = 3


class AnimaRitualPerformanceFactory(factory.django.DjangoModelFactory):
    """Factory for AnimaRitualPerformance records.

    The ritual FK points to Ritual (execution_kind=SCENE_ACTION).
    Use RitualSceneActionConfigFactory(ritual=...) to build the full pair.
    """

    class Meta:
        model = AnimaRitualPerformance

    ritual = factory.SubFactory(
        RitualFactory,
        execution_kind=RitualExecutionKind.SCENE_ACTION,
        service_function_path="",
        flow=None,
    )
    target_character = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    was_successful = True
    anima_recovered = factory.LazyAttribute(lambda o: 5 if o.was_successful else None)


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
    - _developed_points=<int>  → set developed_points directly on the RelationshipTrackProgress
                                 (overrides _track_tier_index; requires as_track_thread=True)
    - as_capstone_thread=True  → switch to RELATIONSHIP_CAPSTONE kind
    - _capstone_points=<int>   → set points directly on the RelationshipCapstone
                                 (overrides default 100; requires as_capstone_thread=True)
    - _path_stage=<int>        → add a CharacterPathHistory row for thread.owner with
                                 a Path of that stage (applies to capstone + effective cap)
    - as_room_thread=True   → switch to ROOM kind (raises AnchorCapNotImplemented)
    - as_covenant_role_thread=True → switch to COVENANT_ROLE kind; creates a CovenantRole

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

    # Must be declared after as_track_thread so self.target_relationship_track is populated.
    @factory.post_generation  # type: ignore[misc]
    def _developed_points(
        self: "Thread", create: bool, extracted: object, **kwargs: object
    ) -> None:
        """Set developed_points directly on the RelationshipTrackProgress.

        Use this param when you need an arbitrary value (e.g. 37) rather than
        a tier-threshold multiple of 10.  Overrides any value set by
        _track_tier_index.  Requires as_track_thread=True.
        """
        if not create or extracted is None:
            return
        if self.target_relationship_track is None:
            return
        progress = self.target_relationship_track
        progress.developed_points = int(extracted)  # type: ignore[arg-type]
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

    # Must be declared after as_capstone_thread so self.target_capstone is populated.
    @factory.post_generation  # type: ignore[misc]
    def _capstone_points(self: "Thread", create: bool, extracted: object, **kwargs: object) -> None:
        """Set points directly on the RelationshipCapstone.

        Use this param to override the default points=100 from RelationshipCapstoneFactory
        with an arbitrary value (e.g. 0, 50, 500).  Requires as_capstone_thread=True.
        """
        if not create or extracted is None:
            return
        if self.target_capstone is None:
            return
        capstone = self.target_capstone
        capstone.points = int(extracted)  # type: ignore[arg-type]
        capstone.save(update_fields=["points"])

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

    @factory.post_generation  # type: ignore[misc]
    def as_covenant_role_thread(
        self: "Thread", create: bool, extracted: object, **kwargs: object
    ) -> None:
        """Switch to COVENANT_ROLE kind: create a CovenantRole."""
        if not create or not extracted:
            return
        from world.covenants.factories import CovenantRoleFactory

        role = CovenantRoleFactory()
        Thread.objects.filter(pk=self.pk).update(
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=role,
            target_trait=None,
        )
        self.target_kind = TargetKind.COVENANT_ROLE
        self.target_covenant_role = role
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


class CorruptionConfigFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "magic.CorruptionConfig"
        django_get_or_create = ("pk",)

    pk = 1


class PoseEndorsementFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "magic.PoseEndorsement"

    endorser_sheet = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    endorsee_sheet = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    interaction = factory.SubFactory("world.scenes.factories.InteractionFactory")
    timestamp = factory.LazyAttribute(lambda o: o.interaction.timestamp)
    resonance = factory.SubFactory(ResonanceFactory)


class SceneEntryEndorsementFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "magic.SceneEntryEndorsement"

    endorser_sheet = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    endorsee_sheet = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    scene = factory.SubFactory("world.scenes.factories.SceneFactory")
    resonance = factory.SubFactory(ResonanceFactory)
    granted_amount = 4


def with_corruption_at_stage(sheet, resonance, stage: int):
    """Test helper: set up a corrupted character at a given stage.

    Creates the per-resonance Corruption ConditionTemplate (or reuses one),
    creates 5 stages with default severity thresholds (50, 200, 500, 1000, 1500),
    sets corruption_current to the stage's threshold, and creates the
    ConditionInstance with the appropriate current_stage. Returns the instance.

    Uses ``sheet.character`` (ObjectDB) as the ConditionInstance target,
    consistent with the canonical sheet→character path on CharacterSheet.
    """
    from world.conditions.factories import (
        ConditionInstanceFactory,
        ConditionStageFactory,
        ConditionTemplateFactory,
    )

    template = ConditionTemplateFactory(
        name=f"Corrupted by {resonance.name}",
        has_progression=True,
        corruption_resonance=resonance,
    )
    thresholds = [50, 200, 500, 1000, 1500]
    stage_rows = []
    for i, threshold in enumerate(thresholds, start=1):
        stage_rows.append(
            ConditionStageFactory(
                condition=template,
                stage_order=i,
                severity_threshold=threshold,
            )
        )

    target_stage_row = stage_rows[stage - 1]
    severity = target_stage_row.severity_threshold

    char_res, _ = CharacterResonance.objects.get_or_create(
        character_sheet=sheet,
        resonance=resonance,
    )
    char_res.corruption_current = severity
    char_res.corruption_lifetime = severity
    char_res.save()

    return ConditionInstanceFactory(
        target=sheet.character,
        condition=template,
        current_stage=target_stage_row,
        severity=severity,
    )


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


# =============================================================================
# Scope #7 Phase 9 — Reference Corruption content factories
# =============================================================================

_ABYSSAL_AFFINITY_NAME: str = "abyssal"


def _make_magical_endurance_check_type():
    """Return the canonical 'Magical Endurance' CheckType, creating it if absent.

    Uses direct ORM get_or_create so the call is idempotent and converges with
    the row authored by seed_magic_config().  The old CheckTypeFactory approach
    created a fresh CheckCategory SubFactory on every call, making the
    (name, category) natural key novel each time and leaking orphan CheckType rows.
    """
    from world.checks.models import CheckCategory, CheckType

    magic_cat, _ = CheckCategory.objects.get_or_create(name="Magic")
    check_type, _ = CheckType.objects.get_or_create(
        name="Magical Endurance",
        defaults={"category": magic_cat},
    )
    return check_type


class CorruptionConditionTemplateFactory(factory.django.DjangoModelFactory):
    """Factory for a per-resonance Corruption ConditionTemplate with 5 stages.

    Authors the full 5-stage shape per spec §6.2 / §6.3 / §11:
    - HOLD_OVERFLOW on all stages (resist check gates each advancement)
    - Primal DCs: 8, 12, 18, 22, 28
    - Abyssal DCs: 12, 18, 25, 30, 35  (harder to resist)
    - passive_decay_per_day: 2 (Primal) / 1 (Abyssal) — TUNING PLACEHOLDER
    - passive_decay_max_severity: None/0 (Primal, decays to zero) / 10 (Abyssal,
      only lowest stages decay) — TUNING PLACEHOLDER per §11
    - passive_decay_blocked_in_engagement: False — corruption decays during normal
      life per §11 ("not blocked by engagement")

    Tuning rationale (Spec B §11):
    - Primal: Low-tier Primal users should be able to clear corruption without a
      Sineater; rate 2/day fully clears faster. max_severity=None → decays to zero.
    - Abyssal: Abyssal users past tier 1 cannot rely on decay alone; rate 1/day
      with max_severity=10 means only the very lowest stages ever auto-decay.

    These values are PLACEHOLDERS for Phase 14 tuning via SoulTetherConfig.

    The affinity is inferred from corruption_resonance.affinity.name.lower().
    """

    class Meta:
        model = "conditions.ConditionTemplate"
        django_get_or_create = ("corruption_resonance",)

    name = factory.LazyAttribute(lambda o: f"Corrupted by {o.corruption_resonance.name}")
    category = factory.SubFactory("world.conditions.factories.ConditionCategoryFactory")
    description = factory.LazyAttribute(
        lambda o: f"Corruption from the {o.corruption_resonance.name} resonance."
    )
    has_progression = True
    # passive_decay_per_day and passive_decay_blocked_in_engagement are set in
    # post_generation once we know whether the resonance is Primal or Abyssal.
    passive_decay_per_day = 0  # overwritten in post_generation
    passive_decay_blocked_in_engagement = False
    corruption_resonance = factory.SubFactory(ResonanceFactory)

    @factory.post_generation  # type: ignore[misc]
    def stages(self, create: bool, extracted: object, **kwargs: object) -> None:
        """Author 5 ConditionStage rows with HOLD_OVERFLOW + resist params.

        Also sets affinity-aware passive decay tuning (Spec B §11).

        Idempotent: skips stage creation if stages already exist (handles
        the django_get_or_create case where the template row is reused).
        """
        if not create:
            return
        # If stages already exist (e.g. template was get_or_created), skip.
        if self.stages.exists():
            return
        from world.conditions.factories import ConditionStageFactory
        from world.conditions.types import AdvancementResistFailureKind

        thresholds = [50, 200, 500, 1000, 1500]
        is_abyssal = self.corruption_resonance.affinity.name.lower() == _ABYSSAL_AFFINITY_NAME
        difficulties = [12, 18, 25, 30, 35] if is_abyssal else [8, 12, 18, 22, 28]
        check_type = _make_magical_endurance_check_type()

        for i, (threshold, dc) in enumerate(zip(thresholds, difficulties, strict=True), start=1):
            ConditionStageFactory(
                condition=self,
                stage_order=i,
                severity_threshold=threshold,
                resist_check_type=check_type,
                resist_difficulty=dc,
                advancement_resist_failure_kind=AdvancementResistFailureKind.HOLD_OVERFLOW,
            )

        # Spec B §11 passive decay tuning — TUNING PLACEHOLDERS for Phase 14.
        #
        # Primal (e.g. Wild Hunt):
        #   decay_per_day=2, max_severity=None (decays all the way to zero).
        #   Low-tier Primal characters can clear corruption without a Sineater.
        #
        # Abyssal (e.g. Web of Spiders):
        #   decay_per_day=1, max_severity=10 (only the very lowest stages auto-decay).
        #   Abyssal-primary characters past tier 1 must rely on Sineating or Atonement.
        if is_abyssal:
            self.passive_decay_per_day = 1
            self.passive_decay_max_severity = 10  # decays only below this severity
        else:
            self.passive_decay_per_day = 2
            self.passive_decay_max_severity = None  # decays to zero
        self.save(update_fields=["passive_decay_per_day", "passive_decay_max_severity"])


class CorruptionTwistTemplateFactory(factory.django.DjangoModelFactory):
    """Factory for a CORRUPTION_TWIST MagicalAlterationTemplate.

    Requires an existing ConditionTemplate (created separately — the twist
    layers magic-specific metadata on top of a condition).  Defaults produce
    a stage-2 twist for the given resonance.
    """

    class Meta:
        model = MagicalAlterationTemplate

    condition_template = factory.SubFactory("world.conditions.factories.ConditionTemplateFactory")
    tier = AlterationTier.MARKED
    origin_affinity = factory.LazyAttribute(lambda o: o.resonance.affinity)
    origin_resonance = factory.SubFactory(ResonanceFactory)
    resonance = factory.LazyAttribute(lambda o: o.origin_resonance)
    stage_threshold = 2
    kind = AlterationKind.CORRUPTION_TWIST
    weakness_magnitude = 0
    resonance_bonus_magnitude = 0
    social_reactivity_magnitude = 0
    is_visible_at_rest = False
    is_library_entry = False

    class Params:
        # Convenience: build a twist wired to a specific resonance without
        # setting origin_affinity manually.
        for_resonance = factory.Trait(
            origin_resonance=factory.SubFactory(ResonanceFactory),
            resonance=factory.SelfAttribute("origin_resonance"),
            origin_affinity=factory.LazyAttribute(lambda o: o.origin_resonance.affinity),
        )


# =============================================================================
# Resonance Pivot Spec B — Soul Tether factories (Phase 3)
# =============================================================================


class SineatingFactory(factory.django.DjangoModelFactory):
    """Audit-row factory for a Sineating action (Spec B §7).

    ``units_accepted == 0`` means the Sineater declined. Default is a
    successful 5-unit Sineating.
    """

    class Meta:
        model = "magic.Sineating"

    sinner_sheet = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    sineater_sheet = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    relationship = factory.SubFactory("world.relationships.factories.CharacterRelationshipFactory")
    scene = None
    resonance = factory.SubFactory("world.magic.factories.ResonanceFactory")
    units_offered = 5
    units_accepted = 5
    anima_cost = 10
    fatigue_cost = 5


class SoulTetherRescueFactory(factory.django.DjangoModelFactory):
    """Audit-row factory for a stage-3+ rescue ritual (Spec B §9)."""

    class Meta:
        model = "magic.SoulTetherRescue"

    sinner_sheet = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    sineater_sheet = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    relationship = factory.SubFactory("world.relationships.factories.CharacterRelationshipFactory")
    scene = None
    resonance = factory.SubFactory("world.magic.factories.ResonanceFactory")
    sinner_stage_at_start = 4
    sinner_stage_at_end = 3
    severity_reduced = 5
    sineater_strain_taken = 3
    check_outcome = factory.SubFactory("world.traits.factories.CheckOutcomeFactory")


class TetherStrainTemplateFactory(factory.django.DjangoModelFactory):
    """ConditionTemplate factory for Tether Strain (Spec B §6).

    Single template; ConditionInstances are lazily created per (sineater, resonance).
    Uses django_get_or_create so repeated calls in tests return the same row.
    """

    class Meta:
        model = "conditions.ConditionTemplate"
        django_get_or_create = ("name",)

    name = "Tether Strain"
    category = factory.SubFactory("world.conditions.factories.ConditionCategoryFactory")
    description = "The wear of carrying another soul's sins. Decays with rest."
    has_progression = True
    passive_decay_per_day = 1
    passive_decay_max_severity = None  # decays all the way to zero
    passive_decay_blocked_in_engagement = False

    @factory.post_generation  # type: ignore[misc]
    def stages(self, create: bool, extracted: object, **kwargs: object) -> None:
        """Wire 5 Tether Strain stages per Spec B §6.3 (idempotent)."""
        if not create:
            return
        if self.stages.exists():
            return
        wire_tether_strain_stages(self)


def wire_tether_strain_stages(template: object) -> list:
    """Author the 5 stages of Tether Strain per Spec B §6.3.

    Stage 1 - Bone-Tired (severity 5)
    Stage 2 - Soul-Worn (severity 10)
    Stage 3 - Heart-Cracked (severity 18)
    Stage 4 - Shadow-Touched (severity 28)
    Stage 5 - Half-Lost (severity 40)

    Specific stage effects (mishap chance, AP reduction, etc.) are authored in
    later tasks. Returns the list of created ConditionStage rows.
    Idempotent: skips stages that already exist.
    """
    from world.conditions.factories import ConditionStageFactory

    stage_spec = [
        ("Bone-Tired", 5),
        ("Soul-Worn", 10),
        ("Heart-Cracked", 18),
        ("Shadow-Touched", 28),
        ("Half-Lost", 40),
    ]
    stages = []
    for i, (stage_name, threshold) in enumerate(stage_spec, start=1):
        stage_obj = ConditionStageFactory(
            condition=template,
            stage_order=i,
            name=stage_name,
            severity_threshold=threshold,
        )
        stages.append(stage_obj)
    return stages


class SoulTetherActiveTemplateFactory(factory.django.DjangoModelFactory):
    """Marker ConditionTemplate installed on Sinners when their first tether forms.

    No stages — pure marker. The two reactive subscribers (redirect handler
    and stage-advance prompt) are wired as TriggerDefinition rows and
    referenced by name in service code when installing Trigger instances.

    Uses django_get_or_create so repeated calls return the same row.
    """

    class Meta:
        model = "conditions.ConditionTemplate"
        django_get_or_create = ("name",)

    name = "Soul Tether Active"
    category = factory.SubFactory("world.conditions.factories.ConditionCategoryFactory")
    description = (
        "Marker condition installed on Sinners with an active Soul Tether. "
        "Carries the reactive subscriber triggers."
    )
    has_progression = False
    passive_decay_per_day = 0
    passive_decay_blocked_in_engagement = False


class AcceptSoulTetherRitualFactory(factory.django.DjangoModelFactory):
    """BILATERAL SESSION-dispatched Ritual for Soul Tether formation (Spec B §12, Slice B).

    Both participants must accept a RitualSession and declare their role
    (SINNER or SINEATER) before the session fires.  The service wrapper
    accept_soul_tether_via_session reads both participant_kwargs entries and
    delegates to accept_soul_tether with the canonical initiator/partner shape.

    Uses django_get_or_create so repeated calls return the same row.
    """

    class Meta:
        model = "magic.Ritual"
        django_get_or_create = ("name",)

    name = "accept_soul_tether"
    description = (
        "A ritual that forms a Soul Tether bond between two willing souls — "
        "a Sinner (Abyssal-aligned) and a Sineater (Celestial- or Primal-aligned)."
    )
    narrative_prose = (
        "Two souls stand at the boundary between light and dark, each choosing to "
        "carry a part of the other. The Sineater opens themselves to carry the weight "
        "of the Sinner's corruption, and the bond is sealed."
    )
    execution_kind = RitualExecutionKind.SERVICE
    service_function_path = "world.magic.services.soul_tether.accept_soul_tether_via_session"
    flow = None
    hedge_accessible = False
    glimpse_eligible = False
    participation_rule = ParticipationRule.BILATERAL
    min_participants = 2
    max_participants = 2
    input_schema = factory.LazyFunction(
        lambda: {
            "fields": [
                {
                    "name": "resonance_id",
                    "label": "Resonance",
                    "type": "resonance_picker",
                    "required": True,
                    "scope": "owned_by_caller",
                    "help": "The resonance that will channel the bond.",
                },
                {
                    "name": "writeup",
                    "label": "Bond Writeup",
                    "type": "text",
                    "required": False,
                    "help": "Narrative description of the bond formation.",
                },
            ],
            "participant_fields": [
                {
                    "name": "soul_tether_role",
                    "label": "Your Role",
                    "type": "soul_tether_role_picker",
                    "required": True,
                    "help": "Choose SINNER (Abyssal-aligned) or SINEATER (Celestial/Primal).",
                },
            ],
        }
    )


class SoulTetherRescueRitualFactory(factory.django.DjangoModelFactory):
    """SERVICE-dispatched Ritual for Soul Tether rescue (Spec B §9).

    Used when a Sinner reaches corruption stage 3+ and the Sineater
    performs the ritual to pull them back from the brink.

    Uses django_get_or_create so repeated calls return the same row.
    """

    class Meta:
        model = "magic.Ritual"
        django_get_or_create = ("name",)

    name = "soul_tether_rescue"
    description = (
        "A Sineater pulls their Sinner back from the brink of Subsumption. "
        "Requires the Sinner to be at corruption stage 3 or higher."
    )
    narrative_prose = (
        "The Sineater reaches through the bond between them, anchoring the Sinner's "
        "soul and drawing the worst of the corruption into themselves. It is costly, "
        "painful work — but it keeps the Sinner from being lost entirely."
    )
    execution_kind = RitualExecutionKind.SERVICE
    service_function_path = "world.magic.services.soul_tether.perform_soul_tether_rescue"
    flow = None
    hedge_accessible = False
    glimpse_eligible = False


def _build_soul_tether_redirect_flow() -> object:
    """Build a FlowDefinition with one CALL_SERVICE_FUNCTION step for the redirect handler.

    The step calls ``soul_tether_redirect_handler`` with the event payload.
    Uses the flows system's ``CALL_SERVICE_FUNCTION`` action (FlowActionChoices).
    """
    from flows.consts import FlowActionChoices
    from flows.factories import FlowStepDefinitionFactory
    from flows.models import FlowDefinition

    flow, _ = FlowDefinition.objects.get_or_create(name="soul_tether_redirect")
    if not flow.steps.exists():
        FlowStepDefinitionFactory(
            flow=flow,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name="world.magic.services.soul_tether.soul_tether_redirect_handler",
            parameters={"payload": "@payload"},
        )
    return flow


def _build_soul_tether_stage_advance_prompt_flow() -> object:
    """Build a FlowDefinition with one CALL_SERVICE_FUNCTION step for the stage-advance prompt.

    The step calls ``soul_tether_stage_advance_prompt`` with the event payload.
    """
    from flows.consts import FlowActionChoices
    from flows.factories import FlowStepDefinitionFactory
    from flows.models import FlowDefinition

    flow, _ = FlowDefinition.objects.get_or_create(name="soul_tether_stage_advance_prompt")
    if not flow.steps.exists():
        FlowStepDefinitionFactory(
            flow=flow,
            action=FlowActionChoices.CALL_SERVICE_FUNCTION,
            variable_name=("world.magic.services.soul_tether.soul_tether_stage_advance_prompt"),
            parameters={"payload": "@payload"},
        )
    return flow


class SoulTetherRedirectTriggerDefinitionFactory(factory.django.DjangoModelFactory):
    """TriggerDefinition for the CORRUPTION_ACCRUING redirect handler (Spec B §5).

    Listens for ``corruption_accruing`` events and calls the redirect service
    to drain the Hollow before corruption mutation fires.
    Priority 100 — fires before default handlers.
    """

    class Meta:
        model = "flows.TriggerDefinition"
        django_get_or_create = ("name",)

    name = "soul_tether_redirect"
    event_name = "corruption_accruing"
    flow_definition = factory.LazyFunction(_build_soul_tether_redirect_flow)
    priority = 100
    base_filter_condition = None  # all filtering happens in the service function


class SoulTetherStageAdvancePromptTriggerDefinitionFactory(factory.django.DjangoModelFactory):
    """TriggerDefinition for the stage-advance prompt handler (Spec B §8).

    Listens for ``condition_stage_advance_check_about_to_fire`` events and
    fires a PROMPT_PLAYER to the Sineater before the resist check resolves.
    Priority 100 — fires before default handlers.
    """

    class Meta:
        model = "flows.TriggerDefinition"
        django_get_or_create = ("name",)

    name = "soul_tether_stage_advance_prompt"
    event_name = "condition_stage_advance_check_about_to_fire"
    flow_definition = factory.LazyFunction(_build_soul_tether_stage_advance_prompt_flow)
    priority = 100
    base_filter_condition = None


def wire_soul_tether_active_template(_template: object) -> tuple:
    """Create the two TriggerDefinition rows for Soul Tether subscribers.

    Note: In this system, TriggerDefinitions are not M2M-linked to
    ConditionTemplate. They are installed as Trigger instances on characters
    when a ConditionInstance of SoulTetherActiveTemplate is applied (by
    ``accept_soul_tether`` service). This function creates the canonical
    TriggerDefinition rows so the service can reference them by name.

    Returns (redirect_trigger_def, stage_advance_trigger_def).
    """
    redirect_def = SoulTetherRedirectTriggerDefinitionFactory()
    stage_advance_def = SoulTetherStageAdvancePromptTriggerDefinitionFactory()
    return redirect_def, stage_advance_def


def wire_soul_tether_stat_definitions() -> None:
    """Idempotent seed for Soul Tether achievement stat definitions (Spec B §14.3).

    Creates StatDefinition rows for all 7 stats fired by Soul Tether services:
    - sineating.units_accepted: Units accepted in a Sineating (fired by resolve_sineating)
    - sineating.units_declined: Sineating requests declined (fired by resolve_sineating)
    - sineating.requests_made: Sineating requests initiated (fired by request_sineating)
    - rescue.performed: Soul Tether rescues performed (fired by perform_soul_tether_rescue)
    - rescue.stage5_save: Rescues from stage 5 Subsumption (fired by perform_soul_tether_rescue)
    - rescue.severity_reduced: Corruption severity reduced (fired by perform_soul_tether_rescue)
    - tether.formed: Soul Tethers formed (fired by accept_soul_tether)

    Safe to call multiple times — uses get_or_create on the stat key.
    """
    from world.achievements.factories import StatDefinitionFactory

    stat_configs = [
        {
            "key": "sineating.units_accepted",
            "name": "Sins Eaten",
            "description": "Total units of corruption consumed by Sineating",
        },
        {
            "key": "sineating.units_declined",
            "name": "Sineating Requests Declined",
            "description": "Times a Sineating request was declined",
        },
        {
            "key": "sineating.requests_made",
            "name": "Sineating Requests Made",
            "description": "Times the Sinner requested to be Hollowed",
        },
        {
            "key": "rescue.performed",
            "name": "Soul Tether Rescues Performed",
            "description": "Times the Sineater rescued the Sinner from Corruption",
        },
        {
            "key": "rescue.stage5_save",
            "name": "Subsumption Saves",
            "description": "Times the Sineater rescued the Sinner from stage 5 Subsumption",
        },
        {
            "key": "rescue.severity_reduced",
            "name": "Corruption Severity Reduced",
            "description": "Total Corruption severity reduced through Soul Tether rescues",
        },
        {
            "key": "tether.formed",
            "name": "Soul Tethers Formed",
            "description": "Soul Tether bonds formed with other players",
        },
    ]

    for config in stat_configs:
        StatDefinitionFactory(
            key=config["key"],
            name=config["name"],
            description=config["description"],
        )


def wire_soul_tether_content() -> object:
    """Idempotent seed for all Spec B authored content.

    Creates (get_or_create):
    - StatDefinition rows for all Soul Tether stats (Phase 12)
    - TetherStrainTemplate + 5 stages
    - SoulTetherActiveTemplate (marker condition)
    - SoulTetherRedirectTriggerDefinition + backing FlowDefinition
    - SoulTetherStageAdvancePromptTriggerDefinition + backing FlowDefinition
    - accept_soul_tether Ritual (SERVICE-dispatched)
    - soul_tether_rescue Ritual (SERVICE-dispatched)

    Returns a ``SoulTetherContent`` dataclass with references to all created rows.
    Safe to call multiple times — does not create duplicates.
    """
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class SoulTetherContent:
        strain_template: object
        active_template: object
        redirect_trigger_def: object
        stage_advance_trigger_def: object
        accept_ritual: object
        rescue_ritual: object

    # Phase 12: Wire achievement stat definitions
    wire_soul_tether_stat_definitions()

    strain_template = TetherStrainTemplateFactory()
    active_template = SoulTetherActiveTemplateFactory()

    redirect_trigger_def, stage_advance_trigger_def = wire_soul_tether_active_template(
        active_template
    )

    accept_ritual = AcceptSoulTetherRitualFactory()
    rescue_ritual = SoulTetherRescueRitualFactory()

    return SoulTetherContent(
        strain_template=strain_template,
        active_template=active_template,
        redirect_trigger_def=redirect_trigger_def,
        stage_advance_trigger_def=stage_advance_trigger_def,
        accept_ritual=accept_ritual,
        rescue_ritual=rescue_ritual,
    )


def author_reference_corruption_content() -> None:
    """Seed 1 Primal + 1 Abyssal reference Corruption content set.

    Creates (or reuses) two reference resonances — "Wild Hunt" (Primal) and
    "Web of Spiders" (Abyssal) — and for each:
    - one per-resonance Corruption ConditionTemplate with 5 stages
    - 6 CORRUPTION_TWIST MagicalAlterationTemplate rows (stages 2, 3, 4 × 2)

    Idempotent: safe to call repeatedly.  CorruptionConditionTemplateFactory
    uses django_get_or_create on corruption_resonance; twist factories create
    new rows each time, so the twist-exists check below prevents duplication.
    """
    primal_affinity = AffinityFactory(name="Primal")
    abyssal_affinity = AffinityFactory(name="Abyssal")
    wild_hunt = ResonanceFactory(name="Wild Hunt", affinity=primal_affinity)
    web_of_spiders = ResonanceFactory(name="Web of Spiders", affinity=abyssal_affinity)

    for resonance in (wild_hunt, web_of_spiders):
        # ConditionTemplate (idempotent via django_get_or_create on corruption_resonance)
        CorruptionConditionTemplateFactory(corruption_resonance=resonance)

        # CORRUPTION_TWIST templates — 2 per stage 2/3/4
        for stage in (2, 3, 4):
            existing = MagicalAlterationTemplate.objects.filter(
                kind=AlterationKind.CORRUPTION_TWIST,
                resonance=resonance,
                stage_threshold=stage,
            ).count()
            for _i in range(max(0, 2 - existing)):
                from world.conditions.factories import ConditionTemplateFactory

                twist_condition = ConditionTemplateFactory()
                CorruptionTwistTemplateFactory(
                    condition_template=twist_condition,
                    origin_resonance=resonance,
                    resonance=resonance,
                    origin_affinity=resonance.affinity,
                    stage_threshold=stage,
                    kind=AlterationKind.CORRUPTION_TWIST,
                )


class CharacterRitualKnowledgeFactory(factory.django.DjangoModelFactory):
    """Factory for CharacterRitualKnowledge."""

    class Meta:
        model = CharacterRitualKnowledge
        django_get_or_create = ("roster_entry", "ritual")

    roster_entry = factory.SubFactory(RosterEntryFactory)
    ritual = factory.SubFactory(RitualFactory)
    learned_from = None


class RitualSessionFactory(factory.django.DjangoModelFactory):
    """Factory for RitualSession — transient coordination row for multi-participant rituals."""

    class Meta:
        model = "magic.RitualSession"

    ritual = factory.SubFactory(RitualFactory)
    initiator = factory.SubFactory(CharacterSheetFactory)
    proposed_terms = ""
    session_kwargs = factory.LazyFunction(dict)
    expires_at = factory.LazyFunction(lambda: datetime.now(UTC) + timedelta(hours=1))


class RitualSessionParticipantFactory(factory.django.DjangoModelFactory):
    """Factory for RitualSessionParticipant."""

    class Meta:
        model = "magic.RitualSessionParticipant"

    session = factory.SubFactory(RitualSessionFactory)
    character_sheet = factory.SubFactory(CharacterSheetFactory)
    state = "INVITED"
    participant_kwargs = factory.LazyFunction(dict)


class RitualSessionCovenantRefFactory(factory.django.DjangoModelFactory):
    """Reference of kind=COVENANT (session-level)."""

    class Meta:
        model = "magic.RitualSessionReference"

    session = factory.SubFactory(RitualSessionFactory)
    participant = None
    kind = "COVENANT"
    ref_covenant = factory.SubFactory(CovenantFactory)
    ref_covenant_role = None


class RitualSessionCovenantRoleRefFactory(factory.django.DjangoModelFactory):
    """Reference of kind=COVENANT_ROLE (typically participant-level)."""

    class Meta:
        model = "magic.RitualSessionReference"

    session = factory.SubFactory(RitualSessionFactory)
    participant = factory.SubFactory(RitualSessionParticipantFactory)
    kind = "COVENANT_ROLE"
    ref_covenant = None
    ref_covenant_role = factory.SubFactory(CovenantRoleFactory)


class CovenantFormationRitualFactory(factory.django.DjangoModelFactory):
    """Factory for the covenant formation ritual.

    Per project rule "no data migrations for game content": this factory is
    the single source for the formation ritual definition, used by tests and
    (eventually) by an authoring UI surfacing sane defaults. It is NOT
    seeded via Django data migrations.
    """

    class Meta:
        model = "magic.Ritual"
        django_get_or_create = ("name",)

    name = "Covenant Formation"
    description = "Bind multiple souls in a sworn magical covenant."
    narrative_prose = "Three or more swear an oath of magical bond..."
    execution_kind = RitualExecutionKind.SERVICE
    service_function_path = "world.covenants.services.create_covenant_via_session"
    flow = None
    participation_rule = ParticipationRule.FORMATION
    input_schema = factory.LazyFunction(
        lambda: {
            "fields": [
                {"name": "name", "type": "text", "label": "Covenant name", "required": True},
                {
                    "name": "covenant_type",
                    "type": "select",
                    "options": ["DURANCE", "BATTLE"],
                    "required": True,
                },
                {"name": "sworn_objective", "type": "textarea", "required": True},
                {
                    "name": "invitees",
                    "type": "character_search",
                    "multi": True,
                    "min": 1,
                    "required": True,
                },
            ],
            "participant_fields": [
                {
                    "name": "chosen_covenant_role",
                    "type": "covenant_role_picker",
                    "depends_on": "covenant_type",
                    "required": True,
                },
            ],
        }
    )


class CovenantInductionRitualFactory(factory.django.DjangoModelFactory):
    """Factory for the covenant induction ritual."""

    class Meta:
        model = "magic.Ritual"
        django_get_or_create = ("name",)

    name = "Covenant Induction"
    description = "Welcome a new member into an existing covenant."
    narrative_prose = "An existing covenant inducts a new member..."
    execution_kind = RitualExecutionKind.SERVICE
    service_function_path = "world.covenants.services.induct_member_via_session"
    flow = None
    participation_rule = ParticipationRule.INDUCTION
    input_schema = factory.LazyFunction(
        lambda: {
            "fields": [
                {
                    "name": "target_covenant",
                    "type": "covenant_picker",
                    "filter": "initiator_active_memberships",
                    "required": True,
                },
                {
                    "name": "candidate",
                    "type": "character_search",
                    "multi": False,
                    "required": True,
                },
            ],
            "participant_fields": [
                {
                    "name": "chosen_covenant_role",
                    "type": "covenant_role_picker",
                    "depends_on": "session.target_covenant.covenant_type",
                    "applies_to": "candidate_only",
                    "required": True,
                },
            ],
        }
    )
