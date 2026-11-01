"""Type definitions for the combat system."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from world.magic.types.power_ledger import PowerLedger
from world.vitals.types import DamageConsequenceResult

if TYPE_CHECKING:
    from collections.abc import Callable

    from world.character_sheets.models import CharacterSheet
    from world.checks.models import Consequence
    from world.checks.outcome_models import ConsequenceOutcome
    from world.checks.types import CheckResult
    from world.combat.constants import HeldGroundPassOutcome
    from world.combat.models import (
        Clash,
        ClashContribution,
        ClashRound,
        CombatOpponent,
        CombatOpponentAction,
        CombatParticipant,
        CombatRoundAction,
        ComboDefinition,
        ComboSlot,
        NpcTacticsConfig,
        ThreatPoolEntry,
    )
    from world.conditions.models import CompulsionResistBand, ConditionInstance, DamageType
    from world.conditions.types import (
        AppliedConditionResult,
        DamageInteractionResult,
        RemovedConditionResult,
    )
    from world.magic.models import Affinity, FuryTier
    from world.magic.models.techniques import Technique
    from world.magic.types import TechniqueUseResult
    from world.mechanics.models import ChallengeApproach
    from world.mechanics.types import CapabilitySource, ChallengeResolutionResult
    from world.scenes.models import Interaction
    from world.societies.models import LegendEntry
    from world.stories.models import BeatCompletion
    from world.traits.models import CheckOutcome

    PerformCheckFn = Callable[..., CheckResult]


@dataclass(frozen=True)
class OpponentDamageResult:
    """Result of applying damage to an NPC."""

    damage_dealt: int
    health_damaged: bool
    probed: bool
    probing_increment: int
    defeated: bool
    kills: int = 0  # swarm bodies cleared this hit (#875); 0 for non-swarm
    opponent_id: int | None = None  # FK to CombatOpponent; set by apply_damage_to_opponent (#1321)
    damage_interaction: DamageInteractionResult | None = (
        None  # condition-damage interaction result (#2018)
    )


@dataclass(frozen=True)
class ParticipantDamageResult:
    """Result of applying damage to a PC."""

    damage_dealt: int
    health_after: int
    knockout_eligible: bool
    death_eligible: bool
    permanent_wound_eligible: bool
    damage_interaction: DamageInteractionResult | None = (
        None  # condition-damage interaction result (#2018)
    )


@dataclass(frozen=True)
class ComboSlotMatch:
    """A single slot in a combo matched to a participant's action."""

    slot_number: int
    participant: CombatParticipant
    action: CombatRoundAction


@dataclass(frozen=True)
class AvailableCombo:
    """A combo whose slots are all satisfied by current round actions."""

    combo: ComboDefinition
    slot_matches: list[ComboSlotMatch]
    known_by_participant: bool


@dataclass(frozen=True)
class ComboSlotFill:
    """One slot of a combo as this round sees it: what it asks for, and who fills it (#3553).

    ``match`` is None while the slot is still open. The name accessors exist so
    the REST serializer and the telnet listing read the same thing.
    """

    slot: ComboSlot
    match: ComboSlotMatch | None

    @property
    def participant_id(self) -> int | None:
        return None if self.match is None else self.match.participant.pk

    @property
    def character_name(self) -> str | None:
        if self.match is None:
            return None
        return self.match.participant.character_sheet.character.db_key

    @property
    def technique_name(self) -> str | None:
        return None if self.match is None else self.match.action.focused_action.name


@dataclass(frozen=True)
class RoundCombo:
    """A combo taking shape this round: every slot listed, filled or open (#3553).

    Produced by ``scan_round_combos``. A complete fill is what ``AvailableCombo``
    has always described; a partial fill is listed only when a PC in the
    encounter already knows the combo, so hidden combos stay hidden until they
    fire.
    """

    combo: ComboDefinition
    slot_fills: list[ComboSlotFill]
    known_by_participant: bool

    @property
    def complete(self) -> bool:
        return all(fill.match is not None for fill in self.slot_fills)

    @property
    def slot_count(self) -> int:
        return len(self.slot_fills)

    @property
    def filled_count(self) -> int:
        return sum(1 for fill in self.slot_fills if fill.match is not None)

    @property
    def open_slots(self) -> list[ComboSlot]:
        return [fill.slot for fill in self.slot_fills if fill.match is None]

    def as_available(self) -> AvailableCombo:
        """The complete-fill view; only meaningful when ``complete`` is True."""
        return AvailableCombo(
            combo=self.combo,
            slot_matches=[fill.match for fill in self.slot_fills if fill.match is not None],
            known_by_participant=self.known_by_participant,
        )


@dataclass(frozen=True)
class DefenseResult:
    """Result of a PC defending against an NPC attack."""

    success_level: int
    damage_multiplier: float
    final_damage: int
    damage_result: ParticipantDamageResult


@dataclass
class ActionOutcome:
    """Outcome of a single entity's action during resolution."""

    entity_type: str  # "pc" or "npc"
    entity_label: str
    damage_results: list[OpponentDamageResult | ParticipantDamageResult] = field(
        default_factory=list,
    )
    combo_used: ComboDefinition | None = None
    damage_consequences: list[DamageConsequenceResult] = field(default_factory=list)
    participant_id: int | None = None
    effect_type_id: int | None = None


@dataclass
class StrikeResult:
    """What one ``fire_waiting_strikes`` call did (#4608).

    ``outcomes`` are the waiting strikes that fired, for the round's outcome list.
    ``mover_stopped`` is True when a strike left the mover unable to go on (defeated,
    downed, fled): its attack and the rest of its move are cancelled this round.
    """

    outcomes: list[ActionOutcome] = field(default_factory=list)
    mover_stopped: bool = False


@dataclass
class RoundResolutionResult:
    """Full result of resolving a combat round."""

    round_number: int
    action_outcomes: list[ActionOutcome] = field(default_factory=list)
    phase_transitions: list[tuple[CombatOpponent, int]] = field(default_factory=list)
    encounter_completed: bool = False
    available_combos: list[AvailableCombo] = field(default_factory=list)
    challenge_outcomes: list[ChallengeResolutionResult] = field(default_factory=list)
    clash_outcomes: list[ClashRoundResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Combat magic pipeline integration (Spec: 2026-04-30)
# ---------------------------------------------------------------------------


def _empty_ledger() -> PowerLedger:
    """Return an empty PowerLedger suitable as a default for CombatTechniqueResolution."""
    return PowerLedger(entries=(), total=0)


@dataclass(frozen=True)
class CombatTechniqueResolution:
    """Returned from a combat resolver into use_technique.

    Frozen — once the inner resolution is computed it cannot change.
    Read by the adapter to populate the outer ActionOutcome. Exposes
    check_result at the top level (no main_result wrapper) — the
    use_technique extractor accepts this shape per spec
    2026-04-30-combat-magic-pipeline-integration-design.

    ``power_ledger`` is the per-target ledger that includes the cast-level
    stages (BASE, ENVIRONMENT_SHIFT, etc.) plus the COMBAT_PULL stage appended
    by the resolver. Available for narration (Task 8) and future
    penetration-vs-resistance work (Task 7).  Defaults to an empty ledger for
    backwards-compatible construction in tests and legacy call sites.
    """

    check_result: CheckResult
    damage_results: list[OpponentDamageResult]
    applied_conditions: list[AppliedConditionResult]
    pull_flat_bonus: int
    scaled_damage: int
    power_ledger: PowerLedger = field(default_factory=lambda: _empty_ledger())
    removed_conditions: list[RemovedConditionResult] = field(default_factory=list)
    # Each enemy the cast's own morale row shook, before and after (#4619).
    morale_shifts: list[SpectacleShift] = field(default_factory=list)


@dataclass(frozen=True)
class CombatTechniqueResult:
    """Adapter's return shape — what _resolve_pc_action consumes.

    Wraps the magic-pipeline outcome (TechniqueUseResult) plus the
    combat-side damage_results extracted from it. Frozen because the
    cast is over by the time this is constructed.

    ``power_ledger`` mirrors the ledger on the inner
    ``CombatTechniqueResolution`` — threaded here so narration helpers can
    inspect ward/environment stages without reaching into nested dataclasses.
    Defaults to an empty ledger for unconfirmed casts (soulfray-cancelled) or
    paths where no resolution was produced.
    """

    damage_results: list[OpponentDamageResult]
    applied_conditions: list[AppliedConditionResult]
    technique_use_result: TechniqueUseResult
    power_ledger: PowerLedger = field(default_factory=lambda: _empty_ledger())
    fury_committed: FuryTier | None = None
    removed_conditions: list[RemovedConditionResult] = field(default_factory=list)

    @property
    def declared_strain_commitment(self) -> int:
        """Return the requested strain from the shared magic result."""
        value = self.technique_use_result.declared_strain_commitment
        return value if isinstance(value, int) else 0

    @property
    def effective_strain_commitment(self) -> int:
        """Return the amount actually paid after a non-lethal clamp."""
        value = self.technique_use_result.effective_strain_commitment
        return value if isinstance(value, int) else 0

    @property
    def strain_power_bonus(self) -> int:
        """Return the one-time authored power bonus from strain."""
        value = self.technique_use_result.strain_power_bonus
        return value if isinstance(value, int) else 0


# ---------------------------------------------------------------------------
# Clash pipeline types (Task 2.3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClashContributionResult:
    """Result of a single PC's per-round clash contribution.

    Produced by ``commit_to_clash``. Captures the check outcome and all
    magic-pipeline side-effects (anima cost, Soulfray, Audere) so the
    round-resolution engine can aggregate progress without re-running the cast.

    Fields:
        character: The ``CharacterSheet`` that made this contribution — echoes
            back the ``character`` argument passed to ``commit_to_clash`` so
            the aggregator can write the ``ClashContribution`` audit row without
            re-resolving the identity.
        action_slot: The ``ClashActionSlot`` value (``"FOCUSED"`` or
            ``"PASSIVE"``) — echoes back the ``action_slot`` argument.
        technique: The ``Technique`` used for this contribution — echoes back
            the ``technique`` argument.
        check_outcome: The ``CheckOutcome`` that the contribution roll produced.
        progress_delta: Change in clash progress this contribution contributes,
            derived from ``outcome_to_delta``.
        anima_committed: The raw strain commitment (anima poured in beyond the
            effective-cost floor).
        was_overburn: ``True`` when ``technique_use_result.was_deficit`` is set —
            the cast dipped into negative anima.
        was_audere: ``True`` when the character was in Audere during the cast.
        soulfray_severity_accrued: Severity points added by Soulfray this cast
            (``soulfray_result.severity_added`` when present, else 0).
        technique_use_result: The full ``TechniqueUseResult`` from the magic
            pipeline for callers that need lower-level details.
    """

    character: CharacterSheet
    action_slot: str
    technique: Technique
    check_outcome: CheckOutcome
    progress_delta: int
    anima_committed: int
    was_overburn: bool
    was_audere: bool
    soulfray_severity_accrued: int
    technique_use_result: TechniqueUseResult
    power: int = 0
    power_ledger: PowerLedger | None = None
    clash_interaction: Interaction | None = None


@dataclass(frozen=True)
class ClashRoundResult:
    """Result of one round of clash aggregation.

    Produced by ``aggregate_clash_round``. Carries the persisted DB rows and
    the numeric values that drove the meter update so the caller can surface
    feedback to players without re-querying.

    Fields:
        clash_round: The persisted ``ClashRound`` row written this round.
        contributions: The persisted ``ClashContribution`` rows — one per PC
            contribution passed in.
        pc_delta_sum: The raw sum of all PC contribution deltas this round.
        npc_delta: The NPC push magnitude (non-negative) passed in by the caller.
        progress_after: The updated ``clash.progress`` value after this round.
        resolution: The ``ClashResolutionResult`` when this round crossed a
            threshold and the clash resolved; ``None`` for a non-resolving round.
            Surfaces the result ``run_clash_round`` would otherwise discard so the
            round-resolution layer can broadcast an outcome narration (#644).
    """

    clash_round: ClashRound
    contributions: list[ClashContribution]
    pc_delta_sum: int
    npc_delta: int
    progress_after: int
    resolution: ClashResolutionResult | None = None


# ---------------------------------------------------------------------------
# Clash resolution types (Task 4.2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClashResolutionResult:
    """Result of clash resolution.

    Produced by ``resolve_clash``. Carries the resolved Clash row, the tier
    that triggered resolution, and the consequence (if any) drawn from the
    resolution pool.

    Fields:
        clash: The resolved ``Clash`` instance (status=RESOLVED,
            resolution and resolved_round set).
        resolution: The ``ClashResolution`` tier — echoed for caller
            convenience so the round driver need not re-read the model field.
        consequence_applied: The ``Consequence`` selected from the resolution
            pool, or ``None`` when the pool had no matching tier entry.
    """

    clash: Clash
    resolution: str  # ClashResolution value — str to avoid circular import at runtime
    consequence_applied: Consequence | None


# ---------------------------------------------------------------------------
# Clash round driver types (Task 5.2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PreparedClashContribution:
    """One PC's prepared input to ``run_clash_round``.

    Bundles everything the round driver needs to call ``commit_to_clash``
    for a single PC participant and compute the affinity tilt for that
    participant's technique against the NPC's attack affinity.

    Fields:
        character_sheet: The ``CharacterSheet`` of the PC making this
            contribution.
        action_slot: ``ClashActionSlot`` value (``"FOCUSED"`` or
            ``"PASSIVE"``).
        technique: The ``Technique`` the PC is using for this contribution.
        strain_commitment: Extra anima committed on top of the technique's
            effective cost floor.
        npc_attack_affinity: The ``Affinity`` of the NPC's attack (for the
            affinity tilt computation), or ``None`` for non-magical attacks.
    """

    character_sheet: CharacterSheet
    action_slot: str
    technique: Technique
    strain_commitment: int
    npc_attack_affinity: Affinity | None


# ---------------------------------------------------------------------------
# Escalation engine types (#872, Task 5)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EscalationTickResult:
    """Result of one participant's escalation tick.

    Fields:
        participant: The CombatParticipant ticked.
        escalation_level: The engagement's level after this tick.
        intensity_modifier: Engagement intensity modifier after this tick.
        control_modifier: Engagement control modifier after this tick.
        pace_success_level: The pace check outcome's success_level, or None
            when the check could not run (unseeded chart — degrade gracefully)
            or when capped=True (no check is rolled at the ceiling).
        capped: True when max_escalation_level stopped the ramp this tick.
    """

    participant: CombatParticipant
    escalation_level: int
    intensity_modifier: int
    control_modifier: int
    pace_success_level: int | None
    capped: bool


@dataclass(frozen=True)
class DigDeepResult:
    """What a character's dig deep did (#4738).

    ``outcome`` is the resolve roll's outcome (None when the check could not run),
    ``surge_amount`` the intensity the band gave (0 when it gave none), ``used_free_dig_deep``
    whether a free dig deep was spent in place of fatigue, and ``fatigue_spent`` the fatigue
    actually charged (0 when a free dig deep paid) from the pool ``fatigue_category``.
    """

    outcome: CheckOutcome | None
    surge_amount: int
    used_free_dig_deep: bool
    fatigue_spent: int
    fatigue_category: str


@dataclass(frozen=True)
class DramaticSurgeBeat:
    """One dramatic-surge event produced by ``apply_dramatic_surge`` (#2013).

    Returned to the immediate caller for optional inline use (tests, future
    callers); the durable source of truth for the round-result payload is
    ``DramaticSurgeRecord`` — this dataclass is not itself persisted.

    The last four fields describe a rolled surge (#4737): the roll's outcome name, the
    potency it was made against, the control change applied and the name of the band's
    condition. A fixed-amount surge leaves them at their defaults. ``record_id`` is the pk of
    the ``DramaticSurgeRecord`` written, so a caller can complete it.
    """

    participant: CombatParticipant
    trigger_kind: str
    amount: int
    narration: str
    round_number: int
    outcome_name: str = ""
    potency: int | None = None
    control_change: int = 0
    condition_name: str = ""
    record_id: int | None = None


# ---------------------------------------------------------------------------
# Equipped-gear combat contribution types (#508, Task 7)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WeaponContribution:
    """Effective combat contribution of a character's equipped weapon."""

    damage: int
    damage_type: DamageType | None


@dataclass(frozen=True)
class WonOverRow:
    """One WON_OVER opponent, as this viewer may act on it (#4091).

    ``condition`` is the designating allegiance instance, gated by visibility
    (``None`` when the condition is not visible to others and the viewer isn't
    its source) — the badge it carries, not the verb/label text, which the
    outcome line already named. ``can_bind``/``can_take_into_service`` require
    the viewer to be the one who charmed this NPC; ``can_send_away`` requires
    only that the viewer applied the designating instance (any verb);
    ``can_settle`` (ruling R2) depends only on the opponent's own state.
    ``bind_window_open`` is viewer-independent (unlike ``can_bind``, which also
    requires the viewer to be the charmer): it is Decision 19's own predicate
    (``_window_open``), true only when the designating hold is the charm kind
    (``Allegiance.ALLY_OF_CASTER`` — never Turned or Calmed) AND its source is
    still in the room. A web surface that wants to say "only the charmer can
    bind this" to a non-charmer viewer must gate on this flag, not on
    ``verb``/display text, which says nothing about whether the window is even
    open (#4091 demo-fidelity fix: the note previously showed on nameless
    Turned/Calmed rows too, where no viewer can ever bind).
    """

    opponent_id: int
    name: str
    verb: str
    source_label: str
    nameless: bool
    persona_id: int | None
    present: bool
    condition: ConditionInstance | None
    holds_until_settled: bool
    strength: int
    can_bind: bool
    can_take_into_service: bool
    can_send_away: bool
    can_settle: bool
    bind_window_open: bool


@dataclass(frozen=True)
class WonOverSnapshot:
    """The encounter-wide half of the won-over digest rows, taken BEFORE cleanup (#4091).

    ``cleanup_completed_encounter`` deletes ephemeral WON_OVER bodies, and the
    delete cascades away their allegiance ``ConditionInstance``; reading the rows
    afterward would silently drop every calmed or turned mook. ``complete_encounter``
    takes this snapshot first and hands it to ``deliver_aftermath_digests``.

    ``opponents`` are the identity-map-shared rows, so a body deleted by cleanup
    later reads ``objectdb_id is None`` here too. Every dict is keyed by
    ``CombatOpponent.pk`` (never ``objectdb_id``, which cleanup nulls). After
    cleanup, ``refresh_won_over_holds`` swaps in the surviving bodies' live
    ``instances``; ``designations`` and ``source_labels`` stay pre-cleanup.
    """

    opponents: list[CombatOpponent]
    instances: dict[int, list[ConditionInstance]]
    designations: dict[int, ConditionInstance]
    source_labels: dict[int, str]


@dataclass(frozen=True)
class AftermathDigest:
    """What one encounter changed for one participant, assembled at conclusion (#3551).

    Built from rows ``complete_encounter`` already writes; never persisted itself.
    ``conditions`` are the conditions still held that were applied during the
    fight (cleared ones leave no row). ``beat_visible_to_player`` is False for a
    SECRET beat, whose line only a GM or staff may see. ``companions_lost`` holds
    the names of this owner's companions released inside the aftermath window
    (#3652) - a companion defeated at EXTREME/LETHAL stakes and released when
    the fight completes. ``won_over`` holds every WON_OVER opponent of the
    encounter (not just this viewer's own charms), with per-row action flags
    computed against this viewer (#4091).
    """

    outcome: str
    consequence: ConsequenceOutcome | None
    conditions: list[ConditionInstance]
    legend_entries: list[LegendEntry]
    beat_completion: BeatCompletion | None
    beat_visible_to_player: bool
    peril_round_active: bool
    companions_lost: list[str]
    # Safe causal labels keyed by deed id. Source ids and check quality remain server-only.
    legend_recognitions: dict[int, list[dict[str, str]]] = field(default_factory=dict)
    # Existing story/scenario objective and authored branch selected for this fight.
    objective: dict[str, object] | None = None
    won_over: list[WonOverRow] = field(default_factory=list)


@dataclass(frozen=True)
class SpectacleShift:
    """One witness's morale state before and after a display (#4147)."""

    opponent_id: int
    before: str  # OpponentMoraleState value
    after: str


@dataclass(frozen=True)
class SpectacleResult:
    """What a display did: the lines to deliver and who moved (#4147)."""

    credit_line: str = ""
    flavour_line: str = ""
    heartened_line: str = ""  # authored Heartened flavour, GM-less scenes only
    shifts: tuple[SpectacleShift, ...] = ()
    heartened_ids: tuple[int, ...] = ()

    @property
    def lines(self) -> list[str]:
        lines = (self.credit_line, self.flavour_line, self.heartened_line)
        return [line for line in lines if line]


@dataclass(frozen=True)
class MovementProfile:
    """How an opponent moves and thinks this fight (#4607).

    Read from its CreatureTemplate, or the NPC defaults when it has none
    (``CombatOpponent.movement_profile``). Values are ``CreatureTactics`` and
    ``CreatureTraversal`` members.

    ``stop_at`` is the held ground its routes end in and never walk past (#4663): empty
    on the bare profile, filled for one planning pass by ``held_ground.routing_profile``.
    """

    tactics: str
    speed_hops: int
    traversal: str
    stop_at: frozenset[int] = frozenset()


@dataclass(frozen=True)
class PassOption:
    """One way a character may try to get past held ground (#4663).

    An approach on ``MovementConfig.held_ground_challenge`` whose capability the
    character holds, paired with her best source of it (its value is the roll's bonus).
    Built by ``held_ground_pass.pass_options``.
    """

    approach: ChallengeApproach
    capability_source: CapabilitySource


@dataclass(frozen=True)
class PassResult:
    """How a roll to get past held ground went (#4663, ``held_ground_pass.attempt_pass``).

    ``outcome`` reads the roll's success level: above 0 CLEAN, 0 PARTIAL (past, with
    whatever the challenge's authored consequence does), below 0 or no check at all
    STOPPED (in the held place, movement over for the round). ``holder_name`` is who
    held it.
    """

    outcome: HeldGroundPassOutcome
    resolution: ChallengeResolutionResult
    holder_name: str


@dataclass
class TacticsInputs:
    """What the NPC tactics ladder reads for one round, batch-fetched once (#4609).

    Part of ``NpcRoundContext``. ``prior_move_kinds`` maps an opponent to its move kind
    by round for the rounds just before this one (the waiting cap). ``aimed_at`` maps an
    opponent to the hostiles whose action this round is aimed at it (PC declarations and
    opponents' attack rows): who is hitting it, the unanswerable-attacker test's input.
    ``grounding_entry_ids`` are the threat entries whose on-hit pool grounds a flier.
    ``ally_entries_by_pool`` covers every active opponent's pool, for the bash test's
    group chip; ``wall_chips`` memoizes that chip per wall for the round.
    """

    config: NpcTacticsConfig
    prior_move_kinds: dict[int, dict[int, str]]
    aimed_at: dict[int, list[CombatParticipant | CombatOpponent]]
    grounding_entry_ids: set[int]
    ally_entries_by_pool: dict[int, list[ThreatPoolEntry]]
    wall_chips: dict[int, int] = field(default_factory=dict)


@dataclass
class SlotMoveResult:
    """What an opponent's move plan did in its resolution slot (#4609).

    Each flag is one of the progress guarantee's observable results. ``stopped`` is True
    when a waiting strike stopped the mover. ``attack_rows`` are attacks the move itself
    made (an opponent whose wall fell before it could bash strikes instead).
    """

    moved: bool = False
    bashed: bool = False
    fled: bool = False
    waited: bool = False
    stopped: bool = False
    attack_rows: list[CombatOpponentAction] = field(default_factory=list)

    @property
    def progressed(self) -> bool:
        return self.moved or self.bashed or self.fled or self.waited


@dataclass(frozen=True)
class CompulsionCost:
    """What declaring one action costs a compelled character this round (#4802).

    ``difficulty`` is the resist roll the action needs; ``forbidden`` says the compulsion
    names the action as forbidden, so its extra difficulty is included.
    """

    difficulty: int
    forbidden: bool


@dataclass(frozen=True)
class Steadier:
    """An ally who could steady a compelled fighter, with the bonus she would give (#4802)."""

    participant: CombatParticipant
    bonus: int


@dataclass(frozen=True)
class SteadyResult:
    """A steadying that happened: who steadied, and the second resist roll she gave (#4802)."""

    steadier: CombatParticipant
    check_result: CheckResult


@dataclass(frozen=True)
class CompulsionAttempt:
    """A compelled character's resist roll for something outside the round (#4802).

    Leaving an encounter and changing back roll at once, with no declaration to replace.
    ``allowed`` is whether the action goes ahead; ``line`` is the roll as the player is
    told it (empty when nothing was rolled); ``check_result`` is None when nothing rolled.
    ``waiting`` is set when a failed roll's wait has not run out: nothing rolled, and
    ``line`` tells the player when they can try again.
    """

    allowed: bool
    line: str
    check_result: CheckResult | None
    waiting: bool = False


@dataclass(frozen=True)
class CompulsionRoll:
    """One resist roll a compelled participant made at the round lock (#4802).

    ``action`` is the declaration the roll was made for; when ``final_band`` let the
    compulsion act, that row was deleted and the compulsion attack declared instead.
    ``steadied_by`` is the ally whose steadying gave the second roll, if any.
    """

    participant: CombatParticipant
    action: CombatRoundAction
    difficulty: int
    first_result: CheckResult
    steadied_by: CombatParticipant | None
    final_band: CompulsionResistBand | None
