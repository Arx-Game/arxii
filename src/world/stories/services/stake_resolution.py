"""Per-stake resolution: machine grading, GM constrained pick, world-state writers.

#1770 PR2. stakes.py owns readiness/activation; this module owns what happens
when a staked beat completes — grading each stake to a column, firing the
authored branch's consequence pool, applying its structured world-state
writers, and writing the StakeOutcome audit/routing row.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import IntegrityError, transaction
from django.db.models import Prefetch

from world.societies.constants import RenownRisk
from world.stories.constants import (
    BeatOutcome,
    StakeOutcomeMethod,
    StakeResolutionColumn,
    StakeRewardSink,
    StakeSubjectKind,
    StoryScope,
)
from world.stories.models import StakeOutcome, StakeResolution, StakeRewardLine
from world.stories.types import StakePayloadProblem

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.gm.models import GMProfile
    from world.scenes.models import Persona
    from world.stories.models import Beat, BeatCompletion, Stake, StakeContractActivation
    from world.stories.types import AnyStoryProgress
    from world.traits.models import CheckOutcome

logger = logging.getLogger(__name__)

_PILLAR_12_LIFECYCLE_MSG = (
    "sets_subject_lifecycle is only allowed for NPC_FATE stakes whose subject "
    "sheet is not player-held (pillar 12: removal is mechanically mediated — "
    "route into peril via escalates_to_risk + consequence pools instead)."
)


def sheet_is_player_held(sheet: CharacterSheet) -> bool:
    """Whether a character sheet is currently held by a player (pillar 12 gate).

    Player-held = the sheet has a RosterEntry with a current (open-ended)
    tenure. A branch payload may never write lifecycle state onto such a
    sheet — PC removal must be mechanically mediated (peril -> vitals ->
    process_damage_consequences), never GM fiat.
    """
    from world.roster.services.activity import current_roster_entry  # noqa: PLC0415

    entry = current_roster_entry(sheet)
    return entry is not None and entry.current_tenure is not None


def stake_resolution_payload_problems(
    *,
    stake: Stake,
    forfeits_subject_item: bool,
    npc_affection_delta: int,
    sets_subject_lifecycle: str,
) -> list[StakePayloadProblem]:
    """Validate a StakeResolution's writer payloads against its stake (pillar 12).

    Shared by StakeResolution.clean (admin defense) and
    StakeResolutionSerializer.validate (the user-input gate). Returns an empty
    list when the payload combination is legal.
    """
    problems: list[StakePayloadProblem] = []

    if sets_subject_lifecycle and (
        stake.subject_kind != StakeSubjectKind.NPC_FATE
        or stake.subject_sheet_id is None
        or sheet_is_player_held(stake.subject_sheet)
    ):
        problems.append(
            StakePayloadProblem(field="sets_subject_lifecycle", message=_PILLAR_12_LIFECYCLE_MSG)
        )

    if forfeits_subject_item and (
        stake.subject_kind != StakeSubjectKind.ITEM or stake.subject_item_id is None
    ):
        problems.append(
            StakePayloadProblem(
                field="forfeits_subject_item",
                message=("forfeits_subject_item requires an ITEM stake with subject_item set."),
            )
        )

    if npc_affection_delta != 0 and (
        stake.subject_kind not in (StakeSubjectKind.NPC_FATE, StakeSubjectKind.FACTION)
        or stake.subject_sheet_id is None
    ):
        problems.append(
            StakePayloadProblem(
                field="npc_affection_delta",
                message=(
                    "npc_affection_delta requires an NPC_FATE or FACTION stake "
                    "with subject_sheet set."
                ),
            )
        )

    return problems


# ---------------------------------------------------------------------------
# Per-stake resolution (machine grading + GM constrained pick)
# ---------------------------------------------------------------------------


def resolve_stakes_for_completion(  # noqa: PLR0913
    *,
    beat: Beat,
    outcome: BeatOutcome,
    completion: BeatCompletion,
    progress: AnyStoryProgress | None,
    scope: str,
    explicit_participants: list[Persona] | None = None,
    outcome_tier: CheckOutcome | None = None,
    withdrawal: bool = False,
) -> list[StakeOutcome]:
    """Grade every open stake on a completing beat and fire the chosen branches.

    Called inside the atomic completion tail
    (world.stories.services.beats._create_completion_and_fire_pool), between
    the beat-level pool fire and resolve_open_activation — so the open
    activation is still readable for the audit FK.

    Participant resolution (same derivation as the beat-level pool fire,
    ``beats._resolve_participants_for_pool``) happens INSIDE this function,
    after the early returns — an unstaked or deferred completion never pays
    the participant-derivation queries and can never be rolled back by a
    participant-resolution edge case.

    Semantics (#1770 pillars 11-12):
      - No stakes -> []. Idempotent: any stake that already has a StakeOutcome
        row (e.g. a GM's earlier constrained pick) is skipped.
      - outcome == PENDING_GM_REVIEW and not withdrawal -> no-op; the stakes
        wait for the GM's pick / final mark.
      - withdrawal=True (combat FLED/ABANDONED): stakes WITH an authored
        WITHDRAWAL resolution fire it (method=MACHINE); stakes without one are
        left unresolved — they pend with the beat's PENDING_GM_REVIEW.
      - Otherwise the beat's outcome maps to a column (SUCCESS -> WIN,
        FAILURE/EXPIRED -> LOSS), with a data-where-it-exists override: an
        NPC_FATE stake whose subject's vitals read DEAD grades LOSS even on a
        beat-level SUCCESS (pillar 11 — the vitals write IS the grade).
      - The chosen column's authored branch fires its consequence pool
        (tier-aware, same guards/context as beat pools) and applies its writer
        payloads. A missing branch still writes a StakeOutcome with
        resolution=None (audit honesty — an unready contract that ran anyway).
      - escalates_to_risk stays recorded on the fired resolution for authoring;
        no automatic scene-spawn here (the fuse walk validates reachability).
    """
    from world.stories.services.beats import _resolve_participants_for_pool  # noqa: PLC0415
    from world.stories.services.stakes import get_open_activation  # noqa: PLC0415

    stakes = list(
        beat.stakes.prefetch_related(
            Prefetch(
                "resolutions",
                queryset=StakeResolution.objects.prefetch_related(
                    Prefetch(
                        "reward_lines",
                        queryset=StakeRewardLine.objects.select_related("resonance"),
                        to_attr="prefetched_reward_lines",
                    )
                ),
                to_attr="prefetched_resolutions",
            )
        )
    )
    if not stakes:
        return []
    if outcome == BeatOutcome.PENDING_GM_REVIEW and not withdrawal:
        return []

    already_resolved = set(
        StakeOutcome.objects.filter(stake__in=stakes).values_list("stake_id", flat=True)
    )
    activation = get_open_activation(beat)
    participants = _resolve_participants_for_pool(
        completion=completion,
        progress=progress,
        scope=scope,
        explicit_participants=explicit_participants,
    )

    outcomes: list[StakeOutcome] = []
    for stake in stakes:
        if stake.pk in already_resolved:
            continue
        if withdrawal:
            resolution = _branch_for_column(stake, StakeResolutionColumn.WITHDRAWAL)
            if resolution is None:
                # No authored withdrawal branch: the stake pends with the
                # beat's PENDING_GM_REVIEW for a GM's constrained pick.
                continue
            column = StakeResolutionColumn.WITHDRAWAL
        else:
            column = _machine_column_for_stake(stake, outcome)
            resolution = _branch_for_column(stake, column)
        outcomes.append(
            _fire_branch_and_record(
                stake=stake,
                resolution=resolution,
                column=column,
                method=StakeOutcomeMethod.MACHINE,
                activation=activation,
                progress=progress,
                scope=scope,
                participants=participants,
                outcome_tier=outcome_tier,
            )
        )
    return outcomes


def _machine_column_for_stake(stake: Stake, outcome: BeatOutcome) -> StakeResolutionColumn:
    """Map the beat outcome to this stake's column, with data-driven overrides.

    Pillar 11 (machine grading where the data exists): an NPC_FATE stake whose
    subject sheet's vitals read DEAD is a LOSS regardless of the beat's column —
    combat already wrote the truth into CharacterVitals.
    """
    column = (
        StakeResolutionColumn.WIN if outcome == BeatOutcome.SUCCESS else StakeResolutionColumn.LOSS
    )
    if (
        stake.subject_kind == StakeSubjectKind.NPC_FATE
        and stake.subject_sheet_id is not None
        and _subject_is_dead(stake.subject_sheet)
    ):
        return StakeResolutionColumn.LOSS
    return column


def _subject_is_dead(sheet: CharacterSheet) -> bool:
    """Whether the subject's vitals mortality marker reads DEAD."""
    from world.vitals.services import is_dead  # noqa: PLC0415

    return is_dead(sheet)


def _branch_for_column(stake: Stake, column: str) -> StakeResolution | None:
    """The stake's authored resolution for ``column``, from the prefetch when present."""
    resolutions = getattr(stake, "prefetched_resolutions", None)  # noqa: GETATTR_LITERAL
    if resolutions is None:
        resolutions = list(stake.resolutions.all())
    return next((r for r in resolutions if r.column == column), None)


def _fire_branch_and_record(  # noqa: PLR0913
    *,
    stake: Stake,
    resolution: StakeResolution | None,
    column: str,
    method: str,
    activation: StakeContractActivation | None,
    progress: AnyStoryProgress | None,
    scope: str,
    participants: list[Persona],
    outcome_tier: CheckOutcome | None = None,
    resolved_by: GMProfile | None = None,
    gm_notes: str = "",
) -> StakeOutcome:
    """Fire one stake's branch (pool + writer payloads) and write its audit row.

    Shared by the machine path and the GM constrained pick — the only
    differences between them are ``method``/``resolved_by``/``gm_notes``.

    One-outcome-per-stake is enforced by the ``unique_outcome_per_stake``
    constraint; the callers' ``.exists()`` pre-checks are the fast path, and a
    losing concurrent create recovers by returning the winner's row (same
    pattern as PR1's activation race handling).
    """
    from world.stories.services.beats import _fire_pool_with_context  # noqa: PLC0415

    if resolution is not None:
        if resolution.consequence_pool_id is not None:
            _fire_pool_with_context(
                pool=resolution.consequence_pool,
                beat=stake.beat,
                progress=progress,
                scope=scope,
                participants=participants,
                outcome_tier=outcome_tier,
            )
        _apply_branch_writers(resolution, stake, participants)
        if column == StakeResolutionColumn.WIN:
            _apply_stake_rewards(resolution, stake, participants, activation)
    else:
        logger.warning(
            "Stake %s resolved at column %r with no authored branch "
            "(unready contract ran anyway); recording resolution=None.",
            stake.pk,
            column,
        )
    try:
        with transaction.atomic():
            return StakeOutcome.objects.create(
                stake=stake,
                activation=activation,
                resolution=resolution,
                column=column,
                method=method,
                resolved_by=resolved_by,
                gm_notes=gm_notes,
            )
    except IntegrityError:
        existing = StakeOutcome.objects.filter(stake=stake).first()
        if existing is None:
            raise
        return existing


def resolve_stake_by_gm_pick(  # noqa: PLR0913 - mirrors record_gm_marked_outcome's surface
    stake: Stake,
    *,
    column: str,
    gm_profile: GMProfile | None,
    gm_notes: str = "",
    participants: list[Persona] | None = None,
    extra_participants: list[Persona] | None = None,
) -> StakeOutcome:
    """Resolve one stake at a GM-chosen column (#1770 PR2 — constrained pick).

    Fires the chosen column's authored branch exactly like the machine path
    (pool + writer payloads) but records method=GM_PICK with the deciding GM
    and their notes. The pick is constrained: the column must be among the
    stake's authored resolutions — a GM never composes a consequence freehand
    at resolution time.

    ``participants`` / ``extra_participants`` — same semantics as
    record_gm_marked_outcome (and the machine path's participant derivation):
    GROUP scope uses ``participants`` (required when the picked branch's pool
    carries LEGEND_AWARD); CHARACTER scope credits the progress's primary
    persona plus ``extra_participants``; GLOBAL takes none. The same list
    feeds the branch's npc_affection_delta writer.

    Defensive guards only (ResolveStakeInputSerializer validates for API
    callers): the stake must be unresolved and the column must be authored.
    """
    from world.stories.services.progress import get_active_progress_for_story  # noqa: PLC0415
    from world.stories.services.stakes import get_open_activation  # noqa: PLC0415

    # Direct table query — never the related manager, whose prefetched cache
    # on the idmapper-shared Stake instance can be stale.
    if StakeOutcome.objects.filter(stake=stake).exists():
        msg = (
            f"Stake {stake.pk} already has a StakeOutcome; "
            "ResolveStakeInputSerializer should have rejected this."
        )
        raise ValueError(msg)
    resolution = stake.resolutions.filter(column=column).first()
    if resolution is None:
        msg = (
            f"Stake {stake.pk} has no authored resolution for column {column!r}; "
            "a GM pick is constrained to authored columns."
        )
        raise ValueError(msg)

    story = stake.beat.episode.chapter.story
    scope = story.scope
    progress = get_active_progress_for_story(story)
    resolved_participants: list[Persona] = []
    if scope == StoryScope.CHARACTER:
        if progress is not None:
            resolved_participants = [progress.character_sheet.primary_persona]
        if extra_participants:
            resolved_participants.extend(extra_participants)
    elif scope == StoryScope.GROUP and participants:
        resolved_participants = list(participants)

    # The open activation is normally already closed by the completion tail;
    # fall back to the most recent activation for the audit FK.
    activation = get_open_activation(stake.beat) or stake.beat.stake_activations.first()

    with transaction.atomic():
        return _fire_branch_and_record(
            stake=stake,
            resolution=resolution,
            column=column,
            method=StakeOutcomeMethod.GM_PICK,
            activation=activation,
            progress=progress,
            scope=scope,
            participants=resolved_participants,
            resolved_by=gm_profile,
            gm_notes=gm_notes,
        )


# ---------------------------------------------------------------------------
# World-state writers
# ---------------------------------------------------------------------------


def _apply_branch_writers(
    resolution: StakeResolution,
    stake: Stake,
    participants: list[Persona] | None,
) -> None:
    """Apply a fired branch's structured world-state payloads (#1770 PR2).

    Each writer skips-and-logs when its subject is unresolvable rather than
    raising — a half-applicable branch must not roll back the completion.
    Captivity of a PC is deliberately NOT a branch write (pillar 12): capture
    arrives via terminal consequence pools / EffectType.CAPTURE.
    """
    if resolution.sets_subject_lifecycle:
        _write_subject_lifecycle(resolution, stake)
    if resolution.forfeits_subject_item:
        _write_item_forfeit(resolution, stake)
    if resolution.npc_affection_delta != 0:
        _write_npc_affection(resolution, stake, participants)


def _write_subject_lifecycle(resolution: StakeResolution, stake: Stake) -> None:
    """set_lifecycle_state on the stake's subject sheet (NPC_FATE, non-player-held).

    Defense in depth on top of the serializer/clean validation: skip+log when
    the sheet is missing or player-held (pillar 12 — a PC's lifecycle is only
    ever written downstream of process_damage_consequences).
    """
    from world.roster.services.activity import set_lifecycle_state  # noqa: PLC0415

    sheet = stake.subject_sheet
    if sheet is None:
        logger.warning(
            "StakeResolution %s: sets_subject_lifecycle=%r but stake %s has no "
            "subject_sheet; skipping.",
            resolution.pk,
            resolution.sets_subject_lifecycle,
            stake.pk,
        )
        return
    if sheet_is_player_held(sheet):
        logger.warning(
            "StakeResolution %s: refusing lifecycle write on player-held sheet %s "
            "(pillar 12); skipping.",
            resolution.pk,
            sheet.pk,
        )
        return
    set_lifecycle_state(sheet, resolution.sets_subject_lifecycle)


def _write_item_forfeit(resolution: StakeResolution, stake: Stake) -> None:
    """Soft-forfeit the stake's subject item (never hard-delete)."""
    from world.items.services.usage import forfeit_item_instance  # noqa: PLC0415

    item = stake.subject_item
    if item is None:
        logger.warning(
            "StakeResolution %s: forfeits_subject_item but stake %s has no subject_item; skipping.",
            resolution.pk,
            stake.pk,
        )
        return
    forfeit_item_instance(
        item_instance=item,
        note=f"Forfeited — stake {stake.pk} resolved at {resolution.column}.",
    )


def _apply_stake_rewards(
    resolution: StakeResolution,
    stake: Stake,
    participants: list[Persona] | None,
    activation: StakeContractActivation | None,
) -> None:
    """Pay the WIN branch's authored reward lines (#1770 PR3, two-sided contract).

    The anti-farming gate (pillars 4/7/8): rewards fire ONLY from a locked
    activation that was ready and priced above effective NONE — no activation,
    an unready contract, or an over-leveled party (effective NONE) skips the
    payout entirely. Loss/withdrawal consequences are ungated (reality doesn't
    care; only the payout math does); the GM-pick path honors the same gate
    via the activation the pick resolves under.

    Delivery is per line x participant (ALL_EQUAL, mirroring mission reward
    distribution) through the SAME sink services the missions deed router
    dispatches to — never the deed-anchored router itself (it reads
    MissionDeedRecord rows, and stories must not depend on missions,
    ADR-0010). Same contract as the other writers: skip-and-log, never raise.
    """
    lines = _reward_lines_for(resolution)
    if not lines:
        return
    if activation is None:
        logger.info(
            "Stake %s WIN: skipping %d reward line(s) — no contract activation recorded.",
            stake.pk,
            len(lines),
        )
        return
    if not activation.is_ready:
        logger.info(
            "Stake %s WIN: skipping %d reward line(s) — activation %s was not ready (%s).",
            stake.pk,
            len(lines),
            activation.pk,
            activation.readiness_notes,
        )
        return
    if activation.effective_risk == RenownRisk.NONE:
        logger.info(
            "Stake %s WIN: skipping %d reward line(s) — activation %s priced at "
            "effective NONE (over-leveled party pays nothing, pillar 4).",
            stake.pk,
            len(lines),
            activation.pk,
        )
        return
    if not participants:
        logger.info(
            "Stake %s WIN: skipping %d reward line(s) — no participants resolved "
            "for the completion.",
            stake.pk,
            len(lines),
        )
        return
    for line in lines:
        for participant in participants:
            _deliver_reward_line(line, participant, stake)


def _reward_lines_for(resolution: StakeResolution) -> list[StakeRewardLine]:
    """The branch's reward lines, from the nested prefetch when present."""
    lines = getattr(resolution, "prefetched_reward_lines", None)  # noqa: GETATTR_LITERAL
    if lines is None:
        lines = list(resolution.reward_lines.all())
    return lines


def _deliver_reward_line(line: StakeRewardLine, participant: Persona, stake: Stake) -> None:
    """Deliver one reward line to one participant's sheet (skip-and-log)."""
    from world.currency.services import deliver_mission_money  # noqa: PLC0415
    from world.magic.constants import GainSource  # noqa: PLC0415
    from world.magic.services.resonance import grant_resonance  # noqa: PLC0415

    # Persona -> CharacterSheet is the _write_npc_affection bridge in reverse
    # (Persona.character_sheet is a non-null FK).
    sheet = participant.character_sheet
    if line.sink == StakeRewardSink.MONEY:
        deliver_mission_money(recipient_sheet=sheet, amount=line.amount, ref=f"stake:{stake.pk}")
        return
    if line.sink == StakeRewardSink.RESONANCE:
        if line.resonance is None:
            logger.warning(
                "StakeRewardLine %s: sink=RESONANCE but resonance is null "
                "(deleted after authoring?); skipping.",
                line.pk,
            )
            return
        grant_resonance(sheet, line.resonance, line.amount, source=GainSource.STAKE_REWARD)
        return
    logger.warning(
        "StakeRewardLine %s: unknown sink %r; skipping.",
        line.pk,
        line.sink,
    )


def _write_npc_affection(
    resolution: StakeResolution,
    stake: Stake,
    participants: list[Persona] | None,
) -> None:
    """Adjust NPCStanding between the subject's primary persona and each participant."""
    from world.npc_services.services import adjust_npc_affection  # noqa: PLC0415
    from world.scenes.models import Persona  # noqa: PLC0415

    sheet = stake.subject_sheet
    if sheet is None:
        logger.warning(
            "StakeResolution %s: npc_affection_delta=%s but stake %s has no "
            "subject_sheet; skipping.",
            resolution.pk,
            resolution.npc_affection_delta,
            stake.pk,
        )
        return
    try:
        npc_persona = sheet.primary_persona
    except Persona.DoesNotExist:
        logger.warning(
            "StakeResolution %s: subject sheet %s has no primary persona; "
            "skipping affection delta.",
            resolution.pk,
            sheet.pk,
        )
        return
    if not participants:
        logger.warning(
            "StakeResolution %s: npc_affection_delta=%s but no participants "
            "resolved for the completion; skipping.",
            resolution.pk,
            resolution.npc_affection_delta,
        )
        return
    for participant in participants:
        adjust_npc_affection(participant, npc_persona, delta=resolution.npc_affection_delta)
