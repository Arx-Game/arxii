"""Payload dataclasses for reactive events.

PRE-event payloads are mutable (ModifyPayloadStep amends them in place).
POST-event payloads are frozen — reactive flows cannot rewrite history.

Payloads carry model instances, NOT primary keys. The SharedMemoryModel
identity map guarantees cheap attribute walks; re-fetching by pk would
defeat the cache.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from typeclasses.characters import Character
    from typeclasses.exits import Exit
    from typeclasses.rooms import Room
    from world.areas.positioning.models import Position
    from world.combat.models import (
        CombatEncounter,
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
    from world.magic.types.power_ledger import PowerLedger
    from world.scenes.models import Scene


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
    """PERSONAL scope, cancellable. Mutable so scars can modify damage.

    ``answers_consumed`` (#2639): per-moment absorption cap counter. The
    interpose fire seam (``world.combat.services._dispatch_interpose_action``)
    increments this when it actually fires; once it reaches
    ``world.combat.constants.ABSORPTION_CAP_PER_MOMENT`` further interceptors
    on THIS payload decline. Standing defenses (absorb/reflect/blink
    conditions) are deliberately outside this cap — flagged judgment call,
    they carry their own reactive costs.
    """

    target: Character
    amount: int
    damage_type: DamageType | None
    source: DamageSource
    answers_consumed: int = 0


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


# ---- Combat encounter lifecycle ----


@dataclass(frozen=True)
class CombatRoundStartingPayload:
    """ROOM scope, non-cancellable. Fires at the top of resolve_round."""

    encounter_id: int
    round_number: int


@dataclass(frozen=True)
class EncounterCompletedPayload:
    encounter: CombatEncounter
    outcome: str  # EncounterOutcome value
    scene: Scene | None
    room: Room | None


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
    sections: list[str] = field(default_factory=list)


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
    power: int
    ledger: PowerLedger


@dataclass(frozen=True)
class TechniqueCastPayload:
    caster: Character
    technique: Technique
    targets: list[Character | ObjectDB]
    intensity: int
    power: int
    ledger: PowerLedger
    # `result` is the return of a caller-provided ``resolve_fn: Callable[..., Any]``;
    # its shape is defined by the caller, not this layer. Intentionally opaque.
    result: object


@dataclass(frozen=True)
class TechniqueAffectedPayload:
    caster: Character
    technique: Technique
    power: int
    ledger: PowerLedger
    target: Character | ObjectDB
    effect: object


# ---- Positioning ----


@dataclass(frozen=True)
class FallEvent:
    """An entity has entered a CHASM position (the reactive catch hook, #1018)."""

    faller: ObjectDB
    position: Position


# ---- Asset lifecycle (#1905) ----


@dataclass(frozen=True)
class AssetStatusPayload:
    """An NPCAsset's status has transitioned (#1905).

    Emitted post-transition by ``transition_asset_status()`` so designers
    can author reactive triggers (alert the promoter, spawn a rescue mission).
    """

    asset_pk: int
    promoter_persona_pk: int
    asset_persona_pk: int
    old_status: str
    new_status: str
    reason: str


# ---- Agriculture (#1864, #2218) ----


@dataclass
class FoodPreCollectPayload:
    """Cancellable pre-collection payload for the food collection mini-game (#2218).

    Emitted by ``collect_field_food`` *before* the pool is zeroed and the
    check is rolled. Reactive flows may inspect the pool size and mutate
    ``difficulty_modifier`` (e.g. intimidation increases difficulty for a
    larger haul) or cancel the collection entirely (e.g. an NPC refuses
    to hand over the food and the encounter must be resolved by other means).

    The ``pool_difficulty_bonus`` is pre-computed from the pool size by the
    service function — the base difficulty plus this bonus yields the
    effective difficulty passed to the check. Reactive flows may further
    adjust ``difficulty_modifier`` on top.
    """

    character: Character
    field_instance: object
    domain: object | None
    gathered: int
    pool_difficulty_bonus: int
    difficulty_modifier: int = 0


@dataclass(frozen=True)
class FoodCollectedPayload:
    """Post-collection outcome payload (#1864, #2218).

    Emitted after food has landed (or been lost) in the stockpile. Read-only
    — reactive flows cannot rewrite history.
    """

    character: Character
    domain: object | None
    gathered: int
    landed: int
    overflow: int
    catastrophe: bool


# ---- Inter-domain food transfer (#2219) ----


@dataclass
class FoodPreTransferPayload:
    """Cancellable pre-transfer payload for inter-domain food transfer (#2219).

    Emitted by ``transfer_food`` *before* food is deducted from the source
    stockpile. Reactive flows may cancel the transfer (bandit ambush, border
    closure) — the food stays put. The ``amount`` field is mutable so a future
    extension can reduce it (loss-in-transit), but the MVP service does not
    read it back.
    """

    character: Character
    source_domain: object
    target_domain: object
    amount: int


@dataclass(frozen=True)
class FoodTransferredPayload:
    """Post-transfer outcome payload (#2219). Read-only."""

    character: Character
    source_domain: object
    target_domain: object
    amount: int
    landed: int
    overflow: int


PAYLOAD_FOR_EVENT: dict[str, type] = {
    "attack_pre_resolve": AttackPreResolvePayload,
    "attack_landed": AttackLandedPayload,
    "attack_missed": AttackMissedPayload,
    "damage_pre_apply": DamagePreApplyPayload,
    "damage_applied": DamageAppliedPayload,
    "character_incapacitated": CharacterIncapacitatedPayload,
    "character_killed": CharacterKilledPayload,
    "combat_round_starting": CombatRoundStartingPayload,
    "encounter_completed": EncounterCompletedPayload,
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
    "fell": FallEvent,
    "asset_compromised": AssetStatusPayload,
    "asset_lost": AssetStatusPayload,
    "asset_dismissed": AssetStatusPayload,
    "food_pre_collect": FoodPreCollectPayload,
    "food_collected": FoodCollectedPayload,
    "food_pre_transfer": FoodPreTransferPayload,
    "food_transferred": FoodTransferredPayload,
}
