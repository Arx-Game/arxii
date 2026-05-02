"""Payload dataclasses for reactive events.

PRE-event payloads are mutable (ModifyPayloadStep amends them in place).
POST-event payloads are frozen — reactive flows cannot rewrite history.

Payloads carry model instances, NOT primary keys. The SharedMemoryModel
identity map guarantees cheap attribute walks; re-fetching by pk would
defeat the cache.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from typeclasses.characters import Character
    from typeclasses.exits import Exit
    from typeclasses.rooms import Room
    from world.combat.models import (
        CombatOpponent,
        CombatOpponentAction,
        CombatRoundAction,
    )
    from world.combat.types import (
        DefenseResult,
        OpponentDamageResult,
        ParticipantDamageResult,
    )
    from world.conditions.models import (
        ConditionInstance,
        ConditionStage,
        ConditionTemplate,
        DamageType,
    )
    from world.magic.models import Technique


@dataclass
class DamageSource:
    """Discriminated union identifying what inflicted damage."""

    type: Literal["character", "technique", "scar", "environment", "item"]
    # Known refs: Character | Technique | ConditionInstance | Room | ObjectDB | None.
    # The "item" fallback path in damage_source.classify_source accepts any object
    # (including raw strings like "fire trap"), so the runtime type is broader.
    ref: object | None


# ---- Combat ----


@dataclass
class AttackPreResolvePayload:
    """Cancellable pre-resolve payload. Covers AE and single-target attacks.

    ``targets`` is always a list. Single-target callers pass ``[character]``.
    Attacker may be a PC (``Character``) or an NPC (``CombatOpponent``).
    """

    attacker: Character | CombatOpponent
    targets: list[Character]
    weapon: ObjectDB | None
    action: CombatRoundAction | CombatOpponentAction


@dataclass(frozen=True)
class AttackLandedPayload:
    attacker: Character | CombatOpponent
    target: Character
    weapon: ObjectDB | None
    damage_result: OpponentDamageResult | ParticipantDamageResult | DefenseResult | None
    action: CombatRoundAction | CombatOpponentAction | None


@dataclass(frozen=True)
class AttackMissedPayload:
    attacker: Character | CombatOpponent
    target: Character
    weapon: ObjectDB | None
    action: CombatRoundAction | CombatOpponentAction | None


@dataclass
class DamagePreApplyPayload:
    """PERSONAL scope, cancellable. Mutable so scars can modify damage."""

    target: Character
    amount: int
    damage_type: DamageType | None
    source: DamageSource


@dataclass(frozen=True)
class DamageAppliedPayload:
    target: Character
    amount_dealt: int
    damage_type: DamageType | None
    source: DamageSource
    hp_after: int


@dataclass(frozen=True)
class CharacterIncapacitatedPayload:
    character: Character
    source_event: str | None  # EventName value that led to incapacitation


@dataclass(frozen=True)
class CharacterKilledPayload:
    character: Character
    source_event: str | None


# ---- Movement ----


@dataclass
class MovePreDepartPayload:
    character: Character
    origin: Room | None
    destination: Room | None
    exit_used: Exit | str | None


@dataclass(frozen=True)
class MovedPayload:
    character: Character
    origin: Room | None
    destination: Room | None
    exit_used: Exit | str | None


# ---- Perception ----


@dataclass
class ExaminePrePayload:
    observer: Character
    target: ObjectDB


@dataclass(frozen=True)
class ExaminedPayload:
    observer: Character
    target: ObjectDB


# ---- Conditions ----


@dataclass
class ConditionPreApplyPayload:
    target: ObjectDB
    template: ConditionTemplate
    source: Character | Technique | DamageSource | None
    stage: ConditionStage | None


@dataclass(frozen=True)
class ConditionAppliedPayload:
    target: ObjectDB
    instance: ConditionInstance
    stage: ConditionStage | None


@dataclass(frozen=True)
class ConditionStageChangedPayload:
    target: ObjectDB
    instance: ConditionInstance
    old_stage: ConditionStage | None
    new_stage: ConditionStage | None


@dataclass(frozen=True)
class ConditionRemovedPayload:
    target: ObjectDB
    instance_id: int
    template: ConditionTemplate
    source: Character | Technique | DamageSource | None


# ---- Techniques ----


@dataclass
class TechniquePreCastPayload:
    caster: Character
    technique: Technique
    targets: list[Character | ObjectDB]
    intensity: int


@dataclass(frozen=True)
class TechniqueCastPayload:
    caster: Character
    technique: Technique
    targets: list[Character | ObjectDB]
    intensity: int
    # `result` is the return of a caller-provided ``resolve_fn: Callable[..., Any]``;
    # its shape is defined by the caller, not this layer. Intentionally opaque.
    result: object


@dataclass(frozen=True)
class TechniqueAffectedPayload:
    caster: Character
    technique: Technique
    target: Character | ObjectDB
    effect: object


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
