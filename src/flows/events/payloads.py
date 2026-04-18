"""Payload dataclasses for reactive events.

PRE-event payloads are mutable (ModifyPayloadStep amends them in place).
POST-event payloads are frozen — reactive flows cannot rewrite history.

Payloads carry model instances, NOT primary keys. The SharedMemoryModel
identity map guarantees cheap attribute walks; re-fetching by pk would
defeat the cache.
"""

from dataclasses import dataclass
from typing import Any, Literal

# Forward-typed as Any to avoid circular imports.
# Real types resolve at attribute-access time via identity-mapped instances.


@dataclass
class DamageSource:
    """Discriminated union identifying what inflicted damage."""

    type: Literal["character", "technique", "scar", "environment", "item"]
    ref: Any  # Character | Technique | ConditionInstance | Room | ObjectDB


# ---- Combat ----


@dataclass
class AttackPreResolvePayload:
    """Cancellable pre-resolve payload. Covers AE and single-target attacks.

    ``targets`` is always a list. Single-target callers pass ``[character]``.
    """

    attacker: Any
    targets: list  # list[Character]
    weapon: Any
    action: Any  # CombatAction


@dataclass(frozen=True)
class AttackLandedPayload:
    attacker: Any
    target: Any
    weapon: Any
    damage_result: Any
    action: Any


@dataclass(frozen=True)
class AttackMissedPayload:
    attacker: Any
    target: Any
    weapon: Any
    action: Any


@dataclass
class DamagePreApplyPayload:
    """PERSONAL scope, cancellable. Mutable so scars can modify damage."""

    target: Any
    amount: int
    damage_type: str
    source: DamageSource


@dataclass(frozen=True)
class DamageAppliedPayload:
    target: Any
    amount_dealt: int
    damage_type: str
    source: DamageSource
    hp_after: int


@dataclass(frozen=True)
class CharacterIncapacitatedPayload:
    character: Any
    source_event: str | None  # EventNames value that led to incapacitation


@dataclass(frozen=True)
class CharacterKilledPayload:
    character: Any
    source_event: str | None


# ---- Movement ----


@dataclass
class MovePreDepartPayload:
    character: Any
    origin: Any
    destination: Any
    exit_used: Any


@dataclass(frozen=True)
class MovedPayload:
    character: Any
    origin: Any
    destination: Any
    exit_used: Any


# ---- Perception ----


@dataclass
class ExaminePrePayload:
    observer: Any
    target: Any


@dataclass(frozen=True)
class ExaminedPayload:
    observer: Any
    target: Any
    result: Any  # ExamineResult object - holds description, sections, etc.


# ---- Conditions ----


@dataclass
class ConditionPreApplyPayload:
    target: Any
    template: Any  # ConditionTemplate
    source: Any
    stage: Any  # ConditionStage | None


@dataclass(frozen=True)
class ConditionAppliedPayload:
    target: Any
    instance: Any  # ConditionInstance
    stage: Any


@dataclass(frozen=True)
class ConditionStageChangedPayload:
    target: Any
    instance: Any
    old_stage: Any
    new_stage: Any


@dataclass(frozen=True)
class ConditionRemovedPayload:
    target: Any
    instance_id: int
    template: Any
    source: Any


# ---- Techniques ----


@dataclass
class TechniquePreCastPayload:
    caster: Any
    technique: Any
    targets: list  # list[Character or ObjectDB]
    intensity: int


@dataclass(frozen=True)
class TechniqueCastPayload:
    caster: Any
    technique: Any
    targets: list
    intensity: int
    result: Any


@dataclass(frozen=True)
class TechniqueAffectedPayload:
    caster: Any
    technique: Any
    target: Any
    effect: Any


PAYLOAD_FOR_EVENT: dict[str, type] = {
    "attack_pre_resolve": AttackPreResolvePayload,
    "attack_landed": AttackLandedPayload,
    "attack_missed": AttackMissedPayload,
    "damage_pre_apply": DamagePreApplyPayload,
    "damage_applied": DamageAppliedPayload,
    "character_incapacitated": CharacterIncapacitatedPayload,
    "character_killed": CharacterKilledPayload,
    "move_pre_depart": MovePreDepartPayload,
    "moved": MovedPayload,
    "examine_pre": ExaminePrePayload,
    "examined": ExaminedPayload,
    "condition_pre_apply": ConditionPreApplyPayload,
    "condition_applied": ConditionAppliedPayload,
    "condition_stage_changed": ConditionStageChangedPayload,
    "condition_removed": ConditionRemovedPayload,
    "technique_pre_cast": TechniquePreCastPayload,
    "technique_cast": TechniqueCastPayload,
    "technique_affected": TechniqueAffectedPayload,
}
