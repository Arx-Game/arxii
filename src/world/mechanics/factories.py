"""Factory classes for mechanics models."""

from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from evennia.objects.models import ObjectDB
import factory
from factory.django import DjangoModelFactory

from actions.factories import ConsequencePoolFactory
from world.mechanics.constants import (
    POWER_MULTIPLIER_TARGET_NAME,
    TEAM_DAMAGE_PERCENT_TARGET_NAME,
    EngagementType,
    PropertyHolder,
)
from world.mechanics.models import (
    Application,
    ApproachConsequence,
    ChallengeApproach,
    ChallengeCategory,
    ChallengeInstance,
    ChallengeTemplate,
    ChallengeTemplateConsequence,
    ChallengeTemplateProperty,
    CharacterEngagement,
    CharacterModifier,
    ContextConsequencePool,
    ModifierCategory,
    ModifierSource,
    ModifierTarget,
    ObjectProperty,
    Prerequisite,
    Property,
    PropertyCategory,
    PropertyDamageModifier,
    PropertyDetonation,
    SituationChallengeLink,
    SituationInstance,
    SituationTemplate,
    SituationTrapLink,
    TraitCapabilityDerivation,
)

_CHECK_TYPE_FACTORY_PATH = "world.checks.factories.CheckTypeFactory"


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


class PowerCategoryFactory(ModifierCategoryFactory):
    """The 'power' ModifierCategory — derived-power buffs. Default, not equipment-driven."""

    name = "power"
    description = "Power buffs that raise a technique's landed effect (derived, never stored)."


class GlobalPowerTargetFactory(ModifierTargetFactory):
    """The unscoped global 'power' ModifierTarget (applies to every cast)."""

    category = factory.SubFactory(PowerCategoryFactory)
    name = "power"
    target_resonance = None


class PowerMultiplierTargetFactory(ModifierTargetFactory):
    """The 'power_multiplier' ModifierTarget — holds percent-delta power buffs (#636).

    Contributions are summed as percent deltas (35 = +35%); _derive_power applies
    them multiplicatively to channeled intensity. Unscoped (applies to every cast).
    """

    category = factory.SubFactory(PowerCategoryFactory)
    name = POWER_MULTIPLIER_TARGET_NAME
    target_resonance = None


class TeamDamagePercentTargetFactory(ModifierTargetFactory):
    """The bounded 'team_damage_percent' ModifierTarget — Uplift's team-wide %, priced
    per-target-level, vow-keyed-DR'd, and clamped to ``TEAM_BUFF_LANE_CAP_PERCENT``
    (#2643). Same "power" category as ``PowerMultiplierTargetFactory`` (so the
    existing ``_get_power_targets()`` catalog read picks it up), but read/clamped as
    its own separate lane — never folded into the legacy unbounded target. See
    ``world.magic.services.techniques._apply_power_multiplier_stage``.
    """

    category = factory.SubFactory(PowerCategoryFactory)
    name = TEAM_DAMAGE_PERCENT_TARGET_NAME
    target_resonance = None


def ensure_team_damage_percent_target() -> ModifierTarget:
    """Idempotently ensure the bounded team-damage-percent lane's ModifierTarget row
    exists (#2643). Mirrors ``world.magic.factories.wire_audere_power_multipliers``'s
    ModifierTarget-ensure idiom for ``power_multiplier`` (factories-as-seed-data): the
    row itself is mechanics config, not authored game content, so — unlike the
    ConditionModifierEffect/ConditionTemplate rows that actually author a Uplift/
    Undermine buff (lore-repo content) — it is safe and correct to seed directly.
    Called from the magic dev seed (``world.seeds.game_content.magic.seed_magic_dev``)
    and from test setup that needs the lane readable without authoring a full buff.
    """
    return TeamDamagePercentTargetFactory()


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


class AerialPropertyFactory(PropertyFactory):
    """Named factory for the 'aerial' property tag.

    Marks an object as currently airborne (navigating the aerial layer).
    ``django_get_or_create = ("name",)`` is inherited; repeated calls return the same row.
    """

    name = "aerial"
    description = "Marks an object as currently navigating the aerial layer."


class BlocksAnimaRegenPropertyFactory(PropertyFactory):
    """Named factory for the 'blocks_anima_regen' property tag.

    Used by ConditionStage.properties on Soulfray stages 2+ (§8.4).
    ``django_get_or_create = ("name",)`` is inherited from PropertyFactory,
    so repeated calls return the same row.
    """

    name = "blocks_anima_regen"
    description = "Blocks daily anima regeneration while this stage is active."


class FatigueCollapseImmunePropertyFactory(PropertyFactory):
    """Named factory for the 'fatigue_collapse_immune' property tag.

    Applied to condition templates (e.g. Audere, Audere Majora) to suppress
    fatigue-based KO while the condition is active.
    ``django_get_or_create = ("name",)`` is inherited; repeated calls return the same row.
    """

    name = "fatigue_collapse_immune"
    description = "Suppresses collapse from fatigue while this condition is active."


class DeathDeferredPropertyFactory(PropertyFactory):
    """Named factory for the 'death_deferred' property tag.

    Applied to condition templates (e.g. Audere, Audere Majora) to defer
    death while the condition is active. When the condition expires, any
    pending deferred death resolves.
    ``django_get_or_create = ("name",)`` is inherited; repeated calls return the same row.
    """

    name = "death_deferred"
    description = "Defers death while this condition is active; resolves on condition expiry."


class ObjectPropertyFactory(DjangoModelFactory):
    """Factory for creating ObjectProperty instances."""

    class Meta:
        model = ObjectProperty

    property = factory.SubFactory(PropertyFactory)
    value = 1


class PropertyDamageModifierFactory(DjangoModelFactory):
    """Factory for creating PropertyDamageModifier instances."""

    class Meta:
        model = PropertyDamageModifier

    property = factory.SubFactory(PropertyFactory)
    damage_type = None
    modifier_value = 10


class PropertyDetonationFactory(DjangoModelFactory):
    """Factory for creating PropertyDetonation instances."""

    class Meta:
        model = PropertyDetonation

    property = factory.SubFactory(PropertyFactory)
    consequence_pool = factory.SubFactory(ConsequencePoolFactory)
    description = ""


class ApplicationFactory(DjangoModelFactory):
    """Factory for creating Application instances."""

    class Meta:
        model = Application
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Application{n}")
    capability = factory.SubFactory("world.conditions.factories.CapabilityTypeFactory")
    target_property = factory.SubFactory(PropertyFactory)
    description = factory.Faker("sentence")
    default_template = None


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
    check_type = factory.SubFactory(_CHECK_TYPE_FACTORY_PATH)
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
    target_object_name = factory.Sequence(lambda n: f"target object {n}")
    display_order = factory.Sequence(lambda n: n)


class SituationTrapLinkFactory(DjangoModelFactory):
    """Factory for creating SituationTrapLink instances."""

    class Meta:
        model = SituationTrapLink

    situation_template = factory.SubFactory(SituationTemplateFactory)
    name = factory.Sequence(lambda n: f"situation-trap-{n}")
    consequence_pool = factory.SubFactory("actions.factories.ConsequencePoolFactory")
    detect_check_type = factory.SubFactory(_CHECK_TYPE_FACTORY_PATH)
    disarm_check_type = factory.SubFactory(_CHECK_TYPE_FACTORY_PATH)
    detect_difficulty = 20
    disarm_difficulty = 20
    is_hidden = True


class ChallengeInstanceFactory(DjangoModelFactory):
    """Factory for creating ChallengeInstance instances."""

    class Meta:
        model = ChallengeInstance

    template = factory.SubFactory(ChallengeTemplateFactory)
    location = factory.SubFactory("evennia_extensions.factories.ObjectDBFactory")
    target_object = factory.SubFactory("evennia_extensions.factories.ObjectDBFactory")
    is_active = True
    is_revealed = True


class SituationInstanceFactory(DjangoModelFactory):
    """Factory for creating SituationInstance instances."""

    class Meta:
        model = SituationInstance

    template = factory.SubFactory(SituationTemplateFactory)
    location = factory.SubFactory("evennia_extensions.factories.ObjectDBFactory")


class ContextConsequencePoolFactory(DjangoModelFactory):
    """Factory for ContextConsequencePool."""

    class Meta:
        model = ContextConsequencePool

    property = factory.SubFactory(PropertyFactory)
    consequence_pool = factory.SubFactory(ConsequencePoolFactory)
    check_type = factory.SubFactory(_CHECK_TYPE_FACTORY_PATH)
    description = ""


# ---------------------------------------------------------------------------
# Engagement
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Modifier target helpers (get-or-create for seed/test use)
# ---------------------------------------------------------------------------


def max_health_modifier_target() -> ModifierTarget:
    """Get-or-create the MAX_HEALTH ModifierTarget used by covenant-role health armor.

    Idempotent: repeated calls return the same row. Creates a 'vitals' category
    via ModifierCategoryFactory if one does not yet exist.
    """
    from world.vitals.constants import MAX_HEALTH_MODIFIER_TARGET

    target, _ = ModifierTarget.objects.get_or_create(
        name=MAX_HEALTH_MODIFIER_TARGET,
        defaults={"category": ModifierCategoryFactory(name="vitals")},
    )
    return target


class CharacterEngagementFactory(DjangoModelFactory):
    """Factory for creating CharacterEngagement instances."""

    class Meta:
        model = CharacterEngagement

    character = factory.SubFactory("evennia_extensions.factories.ObjectDBFactory")
    engagement_type = EngagementType.CHALLENGE
    source_content_type = factory.LazyFunction(lambda: ContentType.objects.get_for_model(ObjectDB))
    source_id = factory.LazyAttribute(lambda o: o.character.pk)
