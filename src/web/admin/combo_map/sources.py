"""Every authored row that sets or reads a condition or a condition property (#4891).

The combo map is only as good as this list. Each model field in the game that points at a
``Property``, ``ConditionTemplate`` or ``ConditionStage`` is either a setter source (a row
that lands the condition in play), a reader source (play checks whether something carries
the property or condition, and acts on it), or excluded with the reason why.
``web/admin/tests/test_combo_map_sources.py`` walks every model and fails on a field that is
in none of the three, so a new setter or reader cannot go missing from the map quietly.

The "Lands" and "Does" lines are read off the play code each source names. A setter lands a
condition template (play starts it at its first stage); no authored row lands a stage.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from django.db.models import Model, Q

from actions.models.effect_configs import ConditionOnCheckConfig, RemoveConditionOnCheckConfig
from actions.models.enhancement import ActionEnhancement
from flows.models.triggers import Trigger
from world.achievements.models import ConditionStatRule
from world.areas.positioning.models import RampartElementProfile
from world.battles.models import (
    BattleUnitTemplate,
    TechniquePropertyAffinity,
    TerrainPropertyEffect,
    WeatherTypePropertyEffect,
)
from world.checks.constants import EffectType
from world.checks.models import ConsequenceEffect
from world.combat.models import (
    ComboDefinition,
    DramaticSurgeRecord,
    SocialManeuverConfig,
    SurgeDegreeBand,
    ThreatPoolEntry,
)
from world.companions.models import CompanionAbility
from world.conditions.models import (
    Compulsion,
    ConditionCapabilityEffect,
    ConditionCheckModifier,
    ConditionConditionInteraction,
    ConditionDamageDealtModifier,
    ConditionDamageInteraction,
    ConditionDamageOverTime,
    ConditionInstance,
    ConditionModifierEffect,
    ConditionResistanceModifier,
    ConditionStage,
    ConditionStageOnEntry,
    ConditionTemplate,
    ControlLossBand,
    ControlLossTrigger,
    TreatmentTemplate,
)
from world.covenants.models import (
    CovenantRite,
    CovenantRiteParticipant,
    CovenantRiteRolePackage,
    InsightTableEntry,
    VowAddedEffect,
    VowAddedEffectAppliedCondition,
    VowAddedEffectRemovedCondition,
    VowSituationalPerkRung,
    VowSituationalPerkSituation,
    WeaknessPoolEntry,
)
from world.forms.models import AlternateSelf
from world.items.models import ItemTemplateProperty
from world.magic.audere import AudereThreshold
from world.magic.audere_majora import (
    AudereMajoraFaithVariantAppliedCondition,
    AudereMajoraThreshold,
)
from world.magic.models.affinity import Resonance
from world.magic.models.alterations import MagicalAlterationTemplate
from world.magic.models.crossing import CrossingOption
from world.magic.models.drift import DriftConfig
from world.magic.models.fury import FuryConfig
from world.magic.models.resonance_environment import ResonanceAlignmentBoonTier
from world.magic.models.rituals import Ritual
from world.magic.models.signature import SignatureMotifBonusAppliedCondition
from world.magic.models.soulfray import SoulfrayConfig
from world.magic.models.technique_draft import (
    TechniqueDraftAppliedCondition,
    TechniqueDraftRemovedCondition,
)
from world.magic.models.techniques import (
    Restriction,
    Technique,
    TechniqueAppliedCondition,
    TechniqueRemovedCondition,
)
from world.magic.specialization.models import TechniqueVariantAppliedCondition
from world.mechanics.models import (
    Application,
    ChallengeApproach,
    ChallengeTemplate,
    ChallengeTemplateProperty,
    ContextConsequencePool,
    ModifierTarget,
    ObjectProperty,
    Prerequisite,
    PropertyDamageModifier,
    PropertyDetonation,
)
from world.military.models import MilitaryUnit
from world.room_features.models import DefenseProgressionDetails, RoomWardDetails
from world.scenes.action_models import SceneActionRequest
from world.scenes.models import Persona
from world.species.models import SpeciesGiftGrant
from world.standoffs.models import (
    CharacterDrive,
    CreatureDrive,
    FactionRule,
    OpponentLineDrive,
    StandoffApproach,
    StandoffConfig,
    StandoffReveal,
    StandoffTerms,
)
from world.stories.models import Beat
from world.vitals.models import VitalsConsequenceConfig
from world.worship.models import MiracleAppliedCondition

#: A row's label or Lands/Does text, read off the row a source query returns. The rows are
#: of many models, so the callables take the row untyped.
RowText = Callable[[Any], str]


class Reads(StrEnum):
    """What a reader source's field points at."""

    PROPERTY = "property"
    CONDITION = "condition"
    STAGE = "stage"


def _fixed(text: str) -> RowText:
    return lambda _row: text


_TARGET_KIND_WHERE = {"self": "on self", "ally": "on an ally", "enemy": "on the target"}


def _by_target_kind(row: Any) -> str:
    return _TARGET_KIND_WHERE.get(row.target_kind, f"on {row.target_kind}")


def _consequence_where(row: Any) -> str:
    verb = "intoxicates" if row.effect_type == EffectType.INTOXICATE else "on"
    return f"{verb} {row.get_target_display().lower()}"


def _variant_label(row: Any) -> str:
    variant = row.variant
    return variant.name_override or f"Variant of {variant.parent_technique.name}"


def _named(path: str = "") -> RowText:
    """The ``name`` of the row at ``path`` (dotted; blank for the row itself).

    Used where ``__str__`` adds a related row's name (a technique's gift, a modifier
    target's category), which would cost a query per row and clutter the label.
    """

    def label(row: Any) -> str:
        obj = row
        for part in path.split(".") if path else ():
            obj = getattr(obj, part)
        return obj.name

    return label


@dataclass(frozen=True)
class SetterSource:
    """One authored field that lands the condition it names.

    ``field`` is the FK to ``ConditionTemplate`` on ``model``. ``owner`` is the dotted path
    to the row the label names and links to (blank for the row itself): a technique's
    applied-condition row links to its technique. ``covers`` names the model field this
    source accounts for when ``model`` is an M2M's own join table.
    """

    kind: str
    model: type[Model]
    field: str
    where: RowText
    owner: str = ""
    label: RowText | None = None
    related: tuple[str, ...] = ()
    narrow: Q | None = None
    covers: tuple[type[Model], str] | None = None


@dataclass(frozen=True)
class ReaderSource:
    """One authored field play reads presence of: a property, a condition, or a stage."""

    kind: str
    model: type[Model]
    field: str
    reads: Reads
    does: RowText
    owner: str = ""
    label: RowText | None = None
    related: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExcludedField:
    """A field that points at a property, condition or stage and is on neither list."""

    model: type[Model]
    field: str
    reason: str


_PRICE = "on self, as its price"
_ON_SELF = "on self"
_CONFIG = "config"

SETTER_SOURCES: tuple[SetterSource, ...] = (
    SetterSource(
        "technique",
        TechniqueAppliedCondition,
        "condition",
        _by_target_kind,
        owner="technique",
        label=_named("technique"),
        related=("technique",),
    ),
    SetterSource(
        "technique variant",
        TechniqueVariantAppliedCondition,
        "condition",
        _by_target_kind,
        owner="variant",
        label=_variant_label,
        related=("variant__parent_technique",),
    ),
    SetterSource(
        "vow effect",
        VowAddedEffectAppliedCondition,
        "condition",
        _by_target_kind,
        owner="effect",
        related=("effect__covenant_role",),
    ),
    SetterSource(
        "signature bonus",
        SignatureMotifBonusAppliedCondition,
        "condition",
        _by_target_kind,
        owner="signature_bonus",
        label=_named("signature_bonus"),
        related=("signature_bonus",),
    ),
    SetterSource(
        "miracle",
        MiracleAppliedCondition,
        "condition",
        _fixed("on the one it answers"),
        owner="miracle",
        label=_named("miracle"),
        related=("miracle",),
    ),
    SetterSource(
        "Audere Majora",
        AudereMajoraFaithVariantAppliedCondition,
        "condition",
        _fixed("on self, at the crossing"),
        owner="faith_variant",
        label=lambda row: f"{row.faith_variant.being.name} at {row.faith_variant.threshold}",
        related=("faith_variant__being", "faith_variant__threshold"),
    ),
    SetterSource("restriction", Restriction, "inflicted_condition", _fixed(_PRICE), label=_named()),
    SetterSource(
        "standoff approach",
        StandoffApproach,
        "target_condition",
        _fixed("on the pressed group"),
        label=_named(),
    ),
    SetterSource(
        "standoff approach",
        StandoffApproach,
        "ally_condition",
        _fixed("on the actor"),
        label=_named(),
    ),
    SetterSource(
        "covenant rite",
        CovenantRite,
        "granted_condition",
        _fixed("on each beneficiary"),
        label=_named("ritual"),
        related=("ritual",),
    ),
    SetterSource(
        "rite role package",
        CovenantRiteRolePackage,
        "condition_template",
        _fixed("on a participant in the role"),
        label=lambda row: f"{row.rite.ritual.name}, {row.covenant_role.name}",
        related=("rite__ritual", "covenant_role"),
    ),
    SetterSource(
        "check effect",
        ConditionOnCheckConfig,
        "condition",
        _fixed("on the target, on a won check"),
        owner="enhancement",
        related=("enhancement",),
    ),
    SetterSource(
        "check effect",
        ConditionOnCheckConfig,
        "immunity_condition",
        _fixed("on the target, as immunity after a failed check"),
        owner="enhancement",
        related=("enhancement",),
    ),
    SetterSource(
        "consequence",
        ConsequenceEffect,
        "condition_template",
        _consequence_where,
        owner="consequence",
        related=("consequence",),
        narrow=Q(effect_type__in=[EffectType.APPLY_CONDITION, EffectType.INTOXICATE]),
    ),
    SetterSource(
        "threat",
        ThreatPoolEntry.conditions_applied.through,
        "conditiontemplate",
        _fixed("on whoever the attack hits"),
        owner="threatpoolentry",
        label=_named("threatpoolentry"),
        related=("threatpoolentry",),
        covers=(ThreatPoolEntry, "conditions_applied"),
    ),
    SetterSource(
        "weakness",
        WeaknessPoolEntry,
        "condition",
        _fixed("on the boss, once read"),
        label=_named(),
    ),
    SetterSource("insight", InsightTableEntry, "condition", _by_target_kind, label=_named()),
    SetterSource(
        "rampart",
        RampartElementProfile,
        "signature_condition",
        _fixed("on an opponent pushed into it"),
        label=_named(),
    ),
    SetterSource(
        "stage entry",
        ConditionStageOnEntry,
        "condition",
        _fixed("on the bearer, entering the stage"),
        owner="stage",
        label=lambda row: str(row.stage),
        related=("stage__condition",),
    ),
    SetterSource(
        "condition",
        ConditionTemplate,
        "breath_runs_out_condition",
        _fixed("on the bearer when breath runs out"),
        label=_named(),
    ),
    SetterSource(
        "condition",
        ConditionTemplate,
        "retaliation_condition",
        _fixed("on an opponent that strikes the bearer"),
        label=_named(),
    ),
    SetterSource(
        "damage interaction",
        ConditionDamageInteraction,
        "applies_condition",
        _fixed("on the bearer, on damage"),
        label=lambda row: f"{row.condition.name} + {row.damage_type.name}",
        related=("condition", "damage_type"),
    ),
    SetterSource(
        "treatment backlash",
        TreatmentTemplate,
        "backlash_target_condition",
        _fixed("on the helper, on a failed treatment"),
        label=_named(),
    ),
    SetterSource(
        "treatment backlash",
        TreatmentTemplate,
        "target_condition",
        _fixed("on the helper, on a failed treatment"),
        narrow=Q(backlash_target_condition__isnull=True, backlash_severity_on_failure__gt=0),
        label=_named(),
    ),
    SetterSource(
        "control loss",
        ControlLossBand,
        "applies",
        _fixed("on self, on a control-loss roll"),
        owner="trigger",
        label=lambda row: f"{row.trigger}, {row.outcome.name}",
        related=("trigger__vulnerability", "outcome"),
    ),
    SetterSource(
        "surge",
        SurgeDegreeBand,
        "condition",
        _fixed("on the surging character"),
        owner="tuning",
        label=lambda row: f"{row.tuning}, {row.outcome.name}",
        related=("tuning", "outcome"),
    ),
    SetterSource(
        "species gift",
        SpeciesGiftGrant,
        "benefit_condition",
        _fixed("on the character, at creation"),
        related=("species", "gift"),
    ),
    SetterSource(
        "species gift",
        SpeciesGiftGrant,
        "drawback_condition",
        _fixed("on the character, at creation"),
        related=("species", "gift"),
    ),
    SetterSource(
        "alternate self",
        AlternateSelf,
        "emergence_condition",
        _fixed("on self, on emerging"),
        label=lambda row: row.display_name,
    ),
    SetterSource(
        "magical alteration",
        MagicalAlterationTemplate,
        "condition_template",
        _fixed("on the scarred character"),
        label=lambda row: f"Alteration, tier {row.tier}",
    ),
    SetterSource(
        "resonance boon",
        ResonanceAlignmentBoonTier,
        "condition_template",
        _fixed("on a character in an aligned room"),
        label=lambda row: (
            f"{row.affinity_interaction.source_affinity.name} in "
            f"{row.affinity_interaction.environment_affinity.name}, "
            f"magnitude {row.min_magnitude}+"
        ),
        related=(
            "affinity_interaction__source_affinity",
            "affinity_interaction__environment_affinity",
        ),
    ),
    SetterSource(
        _CONFIG,
        AudereThreshold,
        "audere_condition",
        _fixed("on self, accepting Audere"),
        label=_fixed("Audere threshold"),
    ),
    SetterSource(
        _CONFIG,
        AudereThreshold,
        "audere_majora_condition",
        _fixed("on self, at an Audere Majora crossing"),
        label=_fixed("Audere threshold"),
    ),
    SetterSource(
        _CONFIG,
        SoulfrayConfig,
        "condition",
        _fixed("on the caster as Soulfray builds"),
        label=_fixed("Soulfray config"),
    ),
    SetterSource(
        _CONFIG,
        DriftConfig,
        "conflict_condition",
        _fixed("on the caster, on a failed focus check"),
        label=_fixed("Drift config"),
    ),
    SetterSource(
        _CONFIG,
        FuryConfig,
        "berserk_condition",
        _fixed("on the caster, as Berserk"),
        label=_fixed("Fury config"),
    ),
    SetterSource(
        _CONFIG,
        SocialManeuverConfig,
        "rally_success_condition",
        _fixed("on the rallied ally"),
        label=_fixed("Social maneuver config"),
    ),
    SetterSource(
        _CONFIG,
        StandoffConfig,
        "pass_condition",
        _fixed("on the group, letting the party pass"),
        label=_fixed("Standoff config"),
    ),
    SetterSource(
        _CONFIG,
        StandoffConfig,
        "turn_condition",
        _fixed("on the group, turned"),
        label=_fixed("Standoff config"),
    ),
    SetterSource(
        _CONFIG,
        VitalsConsequenceConfig,
        "plummeting_condition",
        _fixed("on a falling character"),
        label=_fixed("Vitals config"),
    ),
    SetterSource(
        _CONFIG,
        VitalsConsequenceConfig,
        "surrounded_condition",
        _fixed("on an isolated battle participant"),
        label=_fixed("Vitals config"),
    ),
)

_CARRIER = "a target carrying it"

READER_SOURCES: tuple[ReaderSource, ...] = (
    ReaderSource(
        "perk situation",
        VowSituationalPerkSituation,
        "condition_property",
        Reads.PROPERTY,
        lambda row: f"{row.get_situation_display()}, turns on the perk",
        owner="perk",
        label=lambda row: str(row.perk),
        related=("perk__covenant_role",),
    ),
    ReaderSource(
        "perk rung",
        VowSituationalPerkRung,
        "condition_property",
        Reads.PROPERTY,
        lambda row: f"rung {row.rung_number}: {row.get_extra_situation_display().lower()}",
        owner="perk",
        label=lambda row: str(row.perk),
        related=("perk__covenant_role",),
    ),
    ReaderSource(
        "vow effect",
        VowAddedEffect,
        "condition_property",
        Reads.PROPERTY,
        lambda row: f"{row.get_situation_display() or 'carrier present'}, rides the cast",
        related=("covenant_role",),
    ),
    ReaderSource(
        "prerequisite",
        Prerequisite,
        "property",
        Reads.PROPERTY,
        _fixed("gates a capability or a cast target"),
        label=_named(),
    ),
    ReaderSource(
        "modifier target",
        ModifierTarget,
        "scope_opponent_property",
        Reads.PROPERTY,
        _fixed(f"modifier applies only against {_CARRIER}"),
        label=_named(),
    ),
    ReaderSource(
        "modifier target",
        ModifierTarget,
        "scope_opponent_condition",
        Reads.CONDITION,
        _fixed("modifier applies only against an opponent with it"),
        label=_named(),
    ),
    ReaderSource(
        "check effect",
        ConditionOnCheckConfig,
        "immunity_condition",
        Reads.CONDITION,
        _fixed("a target with it is immune to the effect"),
        owner="enhancement",
        related=("enhancement",),
    ),
    ReaderSource(
        "condition interaction",
        ConditionConditionInteraction,
        "condition",
        Reads.CONDITION,
        lambda row: f"{row.get_trigger_display()}: {row.get_outcome_display()}",
        related=("condition", "other_condition"),
    ),
    ReaderSource(
        "condition interaction",
        ConditionConditionInteraction,
        "other_condition",
        Reads.CONDITION,
        lambda row: f"{row.get_trigger_display()}: {row.get_outcome_display()}",
        related=("condition", "other_condition"),
    ),
    ReaderSource(
        "treatment",
        TreatmentTemplate,
        "target_condition",
        Reads.CONDITION,
        _fixed("treats a character who has it"),
        label=_named(),
    ),
    ReaderSource(
        "achievement stat",
        ConditionStatRule,
        "condition",
        Reads.CONDITION,
        _fixed("counts toward a stat when gained"),
        related=("condition", "stat"),
    ),
    ReaderSource(
        "combo",
        ComboDefinition,
        "required_clash_window_condition",
        Reads.CONDITION,
        _fixed("offered while an opponent has it"),
        label=_named(),
    ),
    ReaderSource(
        "story beat",
        Beat,
        "required_condition_template",
        Reads.CONDITION,
        _fixed("succeeds while the character has it"),
        label=lambda row: f"Beat on {row.episode.title}",
        related=("episode",),
    ),
    ReaderSource(
        _CONFIG,
        VitalsConsequenceConfig,
        "bleed_out_condition",
        Reads.CONDITION,
        _fixed("marks the character dying and advances each round"),
        label=_fixed("Vitals config"),
    ),
    ReaderSource(
        _CONFIG,
        AudereThreshold,
        "minimum_warp_stage",
        Reads.STAGE,
        lambda row: f"offers Audere from {row.minimum_warp_stage.name} on",
        label=_fixed("Audere threshold"),
        related=("minimum_warp_stage",),
    ),
    ReaderSource(
        "Audere Majora",
        AudereMajoraThreshold,
        "minimum_warp_stage",
        Reads.STAGE,
        lambda row: f"offers the crossing from {row.minimum_warp_stage.name} on",
        related=("minimum_warp_stage",),
    ),
)

_PLAY_STATE = "play state, not authored"
_OWN_EFFECT = "the condition's own effect row"
_DRIVE = "a standoff drive; drives never read condition properties"
_UNIT = "a battle unit's own property, never a condition's"
_SOURCE_PROPERTY = "a property of the effect's source, nothing on a target is checked"
_OBJECT_ONLY = "matches object properties only; a condition's properties never reach it"
_REMOVER = "removes the condition"
_DRAFT = "draft row, never reaches play"
_UNREAD = "no play code reads it yet"

EXCLUDED_FIELDS: tuple[ExcludedField, ...] = (
    ExcludedField(ConditionTemplate, "properties", "the properties the condition carries"),
    ExcludedField(ConditionStage, "properties", "the properties the stage carries"),
    ExcludedField(ConditionStage, "condition", "a stage's own template"),
    ExcludedField(ConditionStage, "on_entry_conditions", "listed through ConditionStageOnEntry"),
    ExcludedField(ConditionStageOnEntry, "stage", "the stage that owns the row"),
    ExcludedField(ConditionTemplate, "parent_condition", "aftermath link to its parent"),
    ExcludedField(Technique, "applied_conditions", "listed through TechniqueAppliedCondition"),
    ExcludedField(Technique, "properties", "tags on the technique itself"),
    ExcludedField(TechniqueRemovedCondition, "condition", _REMOVER),
    ExcludedField(VowAddedEffectRemovedCondition, "condition", _REMOVER),
    ExcludedField(RemoveConditionOnCheckConfig, "condition", _REMOVER),
    ExcludedField(TechniqueDraftAppliedCondition, "condition", _DRAFT),
    ExcludedField(TechniqueDraftRemovedCondition, "condition", _DRAFT),
    ExcludedField(ConditionInstance, "condition", _PLAY_STATE),
    ExcludedField(ConditionInstance, "current_stage", _PLAY_STATE),
    ExcludedField(ObjectProperty, "property", _PLAY_STATE),
    ExcludedField(CovenantRiteParticipant, "granted_condition", _PLAY_STATE),
    ExcludedField(DramaticSurgeRecord, "condition", _PLAY_STATE),
    ExcludedField(StandoffReveal, "drive", _PLAY_STATE),
    ExcludedField(SceneActionRequest, "target_condition_template", _PLAY_STATE),
    ExcludedField(Trigger, "source_stage", "a live trigger installed for a condition instance"),
    ExcludedField(RoomWardDetails, "reaction_condition", "a ward a player installed"),
    ExcludedField(DefenseProgressionDetails, "reaction_condition", "a player's ward project"),
    ExcludedField(ConditionCapabilityEffect, "condition", _OWN_EFFECT),
    ExcludedField(ConditionCapabilityEffect, "stage", _OWN_EFFECT),
    ExcludedField(ConditionModifierEffect, "condition", _OWN_EFFECT),
    ExcludedField(ConditionModifierEffect, "stage", _OWN_EFFECT),
    ExcludedField(ConditionCheckModifier, "condition", _OWN_EFFECT),
    ExcludedField(ConditionCheckModifier, "stage", _OWN_EFFECT),
    ExcludedField(ConditionResistanceModifier, "condition", _OWN_EFFECT),
    ExcludedField(ConditionResistanceModifier, "stage", _OWN_EFFECT),
    ExcludedField(ConditionDamageDealtModifier, "condition", _OWN_EFFECT),
    ExcludedField(ConditionDamageDealtModifier, "stage", _OWN_EFFECT),
    ExcludedField(ConditionDamageOverTime, "condition", _OWN_EFFECT),
    ExcludedField(ConditionDamageOverTime, "stage", _OWN_EFFECT),
    ExcludedField(ConditionDamageInteraction, "condition", _OWN_EFFECT),
    ExcludedField(Compulsion, "condition", _OWN_EFFECT),
    ExcludedField(ControlLossTrigger, "vulnerability", _OWN_EFFECT),
    ExcludedField(ControlLossTrigger, "stage", _OWN_EFFECT),
    ExcludedField(SoulfrayConfig, "anima_zero_stage", "caps Soulfray's advance, no presence"),
    ExcludedField(
        ActionEnhancement,
        "condition",
        "names the enhancement's source; nothing checks a condition-sourced one",
    ),
    ExcludedField(ConditionConditionInteraction, "result_condition", _UNREAD),
    ExcludedField(CompanionAbility, "conditions_applied", _UNREAD),
    ExcludedField(CompanionAbility, "grants_property", _UNREAD),
    ExcludedField(CompanionAbility, "effect_properties", _UNREAD),
    ExcludedField(Ritual, "site_property", _UNREAD),
    ExcludedField(
        CrossingOption,
        "condition_template",
        "its effects are summed as passive bonuses; the condition is never applied",
    ),
    ExcludedField(
        ConsequenceEffect,
        "property",
        "adds or removes an object property directly, not through a condition",
    ),
    ExcludedField(ItemTemplateProperty, "property", "an item's own object property"),
    ExcludedField(Persona, "properties", "a persona's own tags, not a condition's"),
    ExcludedField(PropertyDamageModifier, "property", _OBJECT_ONLY),
    ExcludedField(PropertyDetonation, "property", _OBJECT_ONLY),
    ExcludedField(ContextConsequencePool, "property", _OBJECT_ONLY),
    ExcludedField(Application, "target_property", _OBJECT_ONLY),
    ExcludedField(Application, "required_effect_property", _SOURCE_PROPERTY),
    ExcludedField(ChallengeApproach, "required_effect_property", _SOURCE_PROPERTY),
    ExcludedField(Resonance, "properties", _SOURCE_PROPERTY),
    ExcludedField(ThreatPoolEntry, "effect_properties", _SOURCE_PROPERTY),
    ExcludedField(ChallengeTemplate, "properties", "a challenge's own properties"),
    ExcludedField(ChallengeTemplateProperty, "property", "a challenge's own properties"),
    ExcludedField(TechniquePropertyAffinity, "property", _UNIT),
    ExcludedField(TerrainPropertyEffect, "property", _UNIT),
    ExcludedField(WeatherTypePropertyEffect, "property", _UNIT),
    ExcludedField(BattleUnitTemplate, "properties", _UNIT),
    ExcludedField(MilitaryUnit, "properties", _UNIT),
    ExcludedField(CreatureDrive, "property", _DRIVE),
    ExcludedField(FactionRule, "drive", _DRIVE),
    ExcludedField(StandoffTerms, "required_drive", _DRIVE),
    ExcludedField(OpponentLineDrive, "property", _DRIVE),
    ExcludedField(CharacterDrive, "property", _DRIVE),
)
