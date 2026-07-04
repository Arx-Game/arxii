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

_MACHINE_MATCH_LIFECYCLE_MSG = (
    "machine_match_lifecycle_state is only allowed for NPC_FATE stakes — it "
    "would otherwise never match anything (#1760)."
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
    subject_standing_delta: int,
    sets_subject_lifecycle: str,
    machine_match_lifecycle_state: str = "",
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

    if machine_match_lifecycle_state and stake.subject_kind != StakeSubjectKind.NPC_FATE:
        problems.append(
            StakePayloadProblem(
                field="machine_match_lifecycle_state",
                message=_MACHINE_MATCH_LIFECYCLE_MSG,
            )
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

    if subject_standing_delta != 0:
        npc_ok = stake.subject_kind == StakeSubjectKind.NPC_FATE and stake.subject_sheet_id
        faction_ok = stake.subject_kind == StakeSubjectKind.FACTION and (
            stake.subject_society_id or stake.subject_organization_id
        )
        if not (npc_ok or faction_ok):
            problems.append(
                StakePayloadProblem(
                    field="subject_standing_delta",
                    message=(
                        "subject_standing_delta requires an NPC_FATE stake with "
                        "subject_sheet set, or a FACTION stake with subject_society "
                        "or subject_organization set."
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
    withdrawn_stake_ids = _withdrawn_consent_stake_ids(beat, stakes)

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
        elif stake.pk in withdrawn_stake_ids:
            # #1771 story 5: the stake's treasured subject had its sign-off
            # withdrawn on this beat — a revoked-consent wager never grades
            # WIN/LOSS, even though the beat itself resolves normally.
            column = StakeResolutionColumn.WITHDRAWAL
            resolution = _branch_for_column(stake, column)
            if resolution is None:
                # No authored WITHDRAWAL branch: pend for a GM's constrained
                # pick, same semantics as the whole-encounter withdrawal path.
                continue
        else:
            column = _machine_column_for_stake(stake, outcome)
            resolution = _branch_for_column(
                stake, column, prefer_lifecycle_state=_subject_lifecycle_state(stake)
            )
            if resolution is not None:
                # A lifecycle-state match may have selected a branch on the
                # OTHER column (#1760 — e.g. a DEAD/CAPTURED override firing
                # LOSS on a beat-level SUCCESS); record the branch's actual
                # column, not the outcome-derived default.
                column = resolution.column
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


def _machine_column_for_stake(
    stake: Stake,  # noqa: ARG001
    outcome: BeatOutcome,
) -> StakeResolutionColumn:
    """Map the beat outcome to this stake's column (the polarity default).

    The specific branch within that polarity is selected separately by
    _branch_for_column's lifecycle-state match (#1760); this function only
    picks WIN vs LOSS. ``stake`` is unused now that the old is-dead override
    moved into _branch_for_column, but kept in the signature — callers pass
    it uniformly with the withdrawal/GM-pick branch lookups.
    """
    if outcome == BeatOutcome.SUCCESS:
        return StakeResolutionColumn.WIN
    return StakeResolutionColumn.LOSS


def _subject_lifecycle_state(stake: Stake) -> str | None:
    """The stake's NPC_FATE subject's current lifecycle_state, or None.

    None when the stake isn't NPC_FATE or has no resolvable subject sheet —
    callers treat None as "no machine-match signal available."
    """
    if stake.subject_kind != StakeSubjectKind.NPC_FATE or stake.subject_sheet_id is None:
        return None
    return stake.subject_sheet.lifecycle_state


def _withdrawn_consent_stake_ids(beat: Beat, stakes: list[Stake]) -> set[int]:
    """Ids of ``stakes`` whose treasured subject has a WITHDRAWN sign-off on ``beat``.

    #1771 story 5 (per-stake override, distinct from the whole-encounter
    ``withdrawal=True`` FLED/ABANDONED path): a player who withdraws a
    ``TreasuredSignoff`` mid-story must never have that stake grade WIN/LOSS
    at a later ordinary completion, even though sibling stakes grade
    normally. Batched — one query for the beat's withdrawn
    ``TreasuredSignoff`` rows, one for the ``TreasuredSubject`` rows they
    point at — no query inside the loop over ``stakes``. Reuses
    ``boundaries._subject_identity`` (#1771 task 3) as the single identity-key
    definition also used by ``check_stake_boundaries``.
    """
    from world.boundaries.models import TreasuredSubject  # noqa: PLC0415
    from world.stories.models import TreasuredSignoff  # noqa: PLC0415
    from world.stories.services.boundaries import _subject_identity  # noqa: PLC0415

    treasured_ids = set(
        TreasuredSignoff.objects.filter(beat=beat, withdrawn_at__isnull=False).values_list(
            "treasured_subject_id", flat=True
        )
    )
    if not treasured_ids:
        return set()

    withdrawn_identities = {
        _subject_identity(
            subject_kind,
            subject_sheet_id,
            subject_item_id,
            subject_society_id,
            subject_organization_id,
            subject_label,
        )
        for (
            subject_kind,
            subject_sheet_id,
            subject_item_id,
            subject_society_id,
            subject_organization_id,
            subject_label,
        ) in TreasuredSubject.objects.filter(pk__in=treasured_ids).values_list(
            "subject_kind",
            "subject_sheet_id",
            "subject_item_id",
            "subject_society_id",
            "subject_organization_id",
            "subject_label",
        )
    }
    if not withdrawn_identities:
        return set()

    return {
        stake.pk
        for stake in stakes
        if _subject_identity(
            stake.subject_kind,
            stake.subject_sheet_id,
            stake.subject_item_id,
            stake.subject_society_id,
            stake.subject_organization_id,
            stake.subject_label,
        )
        in withdrawn_identities
    }


def _branch_for_column(
    stake: Stake, column: str, *, prefer_lifecycle_state: str | None = None
) -> StakeResolution | None:
    """The stake's authored resolution for `column`, from the prefetch when present.

    #1760: when prefer_lifecycle_state is set, a branch whose
    machine_match_lifecycle_state equals it wins over the column's plain
    (outcome_key="") default — and over the outcome-derived column itself,
    searched across ALL of the stake's authored branches (not just `column`).
    This generalizes the old is-dead-only override (which forced LOSS
    regardless of the beat's WIN/LOSS polarity) to the full LifecycleState
    ladder: an authored branch's own column wins when its
    machine_match_lifecycle_state matches the subject's actual state, same as
    a dead NPC always graded LOSS even on a beat-level SUCCESS. Falls back to
    the plain default within `column` when no branch matches — preserves
    pre-#1760 single-branch-per-column content unchanged.
    """
    resolutions = getattr(stake, "prefetched_resolutions", None)  # noqa: GETATTR_LITERAL
    if resolutions is None:
        resolutions = list(stake.resolutions.all())
    if prefer_lifecycle_state:
        matched = next(
            (r for r in resolutions if r.machine_match_lifecycle_state == prefer_lifecycle_state),
            None,
        )
        if matched is not None:
            return matched
    candidates = [r for r in resolutions if r.column == column]
    return next((r for r in candidates if r.outcome_key == ""), None) or next(
        iter(candidates), None
    )


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
    """Claim one stake's audit row, then fire its branch (pool + writer payloads).

    Shared by the machine path and the GM constrained pick — the only
    differences between them are ``method``/``resolved_by``/``gm_notes``.

    Claim-before-pay (#1770 PR3 review): the StakeOutcome row is created
    FIRST — winning the ``unique_outcome_per_stake`` constraint is the claim.
    A losing concurrent create refetches and returns the winner's row WITHOUT
    firing anything, so two racing resolutions can never both pay the WIN
    rewards (or double-fire the pool/writers). The callers' ``.exists()``
    pre-checks remain the fast path. The caller's enclosing transaction still
    rolls the claim and its effects back together on a genuine error.
    """
    from world.stories.services.beats import _fire_pool_with_context  # noqa: PLC0415

    try:
        with transaction.atomic():
            outcome = StakeOutcome.objects.create(
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
        logger.info(
            "Stake %s already claimed by a concurrent resolution (outcome %s); "
            "not firing this branch again.",
            stake.pk,
            existing.pk,
        )
        return existing

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
    return outcome


def resolve_stake_by_gm_pick(  # noqa: PLR0913 - mirrors record_gm_marked_outcome's surface
    stake: Stake,
    *,
    column: str,
    outcome_key: str = "",
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
    feeds the branch's subject_standing_delta writer.

    Defensive guards only (ResolveStakeInputSerializer validates for API
    callers): the stake must be unresolved and the column must be authored.
    ``outcome_key`` narrows the pick to one specific named branch within
    ``column`` (#1760) — blank picks the column's plain default branch,
    matching pre-#1760 authoring.
    """
    from world.stories.services.progress import get_active_progress_for_story  # noqa: PLC0415

    # Direct table query — never the related manager, whose prefetched cache
    # on the idmapper-shared Stake instance can be stale.
    if StakeOutcome.objects.filter(stake=stake).exists():
        msg = (
            f"Stake {stake.pk} already has a StakeOutcome; "
            "ResolveStakeInputSerializer should have rejected this."
        )
        raise ValueError(msg)
    resolution = stake.resolutions.filter(column=column, outcome_key=outcome_key).first()
    if resolution is None:
        msg = (
            f"Stake {stake.pk} has no authored resolution for column {column!r} "
            f"outcome_key {outcome_key!r}; a GM pick is constrained to authored "
            "branches."
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

    activation = _activation_for_gm_pick(stake.beat)

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


def _activation_for_gm_pick(beat: Beat) -> StakeContractActivation | None:
    """The activation the pended stakes actually ran under (#1770 PR3 review).

    A GM pick resolves a stake that pended at some earlier completion. Prefer
    the most recent activation locked at-or-before the beat's most recent
    BeatCompletion — a NEW activation opened after the stake pended (the beat
    re-engaged) must not change the pended stake's payout gate or its
    StakeOutcome.activation audit row. Fall back to the open activation, then
    the most recent one (picks on a beat with no completion yet).
    """
    from world.stories.services.stakes import get_open_activation  # noqa: PLC0415

    completion = beat.completions.order_by("-recorded_at", "-pk").first()
    if completion is not None:
        # StakeContractActivation.Meta.ordering is ["-locked_at"], so first()
        # is the most recent activation at-or-before that completion.
        activation = beat.stake_activations.filter(locked_at__lte=completion.recorded_at).first()
        if activation is not None:
            return activation
    return get_open_activation(beat) or beat.stake_activations.first()


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
    if resolution.subject_standing_delta != 0:
        _write_subject_standing(resolution, stake, participants)


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

    The reward band is re-verified at pay time (#1770 PR3 review): the
    ``is_ready`` verdict frozen on the activation can go stale in the
    pending-GM-pick window, so an out-of-band live total also skips the
    payout (banding bypass closed at both ends — the serializer refuses
    completed-beat edits, and the payout re-checks the band regardless).

    Delivery is per line x participant (ALL_EQUAL, mirroring mission reward
    distribution) through the SAME sink services the missions deed router
    dispatches to — never the deed-anchored router itself (it reads
    MissionDeedRecord rows, and stories must not depend on missions,
    ADR-0010). Same contract as the other writers: skip-and-log, never raise.
    """
    from world.stories.services.stakes import reward_band_problems_for_beat  # noqa: PLC0415

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
    band_problems = reward_band_problems_for_beat(stake.beat)
    if band_problems:
        logger.warning(
            "Stake %s WIN: skipping %d reward line(s) — reward band violated at "
            "pay time (lines changed after activation?): %s",
            stake.pk,
            len(lines),
            "; ".join(band_problems),
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

    # Persona -> CharacterSheet is the _write_npc_standing bridge in reverse
    # (Persona.character_sheet is a non-null FK).
    sheet = participant.character_sheet
    if line.sink == StakeRewardSink.MONEY:
        deliver_mission_money(
            recipient_sheet=sheet,
            amount=line.amount,
            ref=f"stake:{stake.pk}",
            reason_label="stake reward",
        )
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


def _write_subject_standing(
    resolution: StakeResolution,
    stake: Stake,
    participants: list[Persona] | None,
) -> None:
    """Adjust standing between the stake's subject and each participant (#1760).

    Dispatches on subject_kind: NPC_FATE writes NPCStanding via
    subject_sheet's primary persona (unchanged). FACTION writes
    SocietyReputation or OrganizationReputation via the participant's OWN
    persona (a society/org doesn't have a "primary persona" to be the other
    side of a pairwise standing row — reputation is persona-to-faction, not
    persona-to-persona).
    """
    if stake.subject_kind == StakeSubjectKind.NPC_FATE:
        _write_npc_standing(resolution, stake, participants)
    elif stake.subject_kind == StakeSubjectKind.FACTION:
        _write_faction_standing(resolution, stake, participants)


def _write_npc_standing(
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
            "StakeResolution %s: subject_standing_delta=%s but stake %s has no "
            "subject_sheet; skipping.",
            resolution.pk,
            resolution.subject_standing_delta,
            stake.pk,
        )
        return
    try:
        npc_persona = sheet.primary_persona
    except Persona.DoesNotExist:
        logger.warning(
            "StakeResolution %s: subject sheet %s has no primary persona; skipping standing delta.",
            resolution.pk,
            sheet.pk,
        )
        return
    if not participants:
        logger.warning(
            "StakeResolution %s: subject_standing_delta=%s but no participants "
            "resolved for the completion; skipping.",
            resolution.pk,
            resolution.subject_standing_delta,
        )
        return
    for participant in participants:
        adjust_npc_affection(participant, npc_persona, delta=resolution.subject_standing_delta)


def _write_faction_standing(
    resolution: StakeResolution,
    stake: Stake,
    participants: list[Persona] | None,
) -> None:
    """Adjust SocietyReputation/OrganizationReputation for each participant (#1760).

    Exactly one of subject_society/subject_organization is set per the
    payload validation gate — checks society first, matching how Stake's own
    FACTION-kind serializer validation orders the pair.
    """
    from world.societies.renown import (  # noqa: PLC0415
        bump_organization_reputation,
        bump_society_reputation,
    )

    if not participants:
        logger.warning(
            "StakeResolution %s: subject_standing_delta=%s but no participants "
            "resolved for the completion; skipping.",
            resolution.pk,
            resolution.subject_standing_delta,
        )
        return
    if stake.subject_society_id is not None:
        for participant in participants:
            bump_society_reputation(
                participant, stake.subject_society, resolution.subject_standing_delta
            )
    elif stake.subject_organization_id is not None:
        for participant in participants:
            bump_organization_reputation(
                participant, stake.subject_organization, resolution.subject_standing_delta
            )
    else:
        logger.warning(
            "StakeResolution %s: FACTION stake %s has neither subject_society "
            "nor subject_organization set; skipping.",
            resolution.pk,
            stake.pk,
        )
