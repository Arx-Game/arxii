"""Player-boundary screening seam for stakes contracts (#1770 pillar 10).

The seam runs at authoring time (``StakeSerializer``) and at every
activation/commit call site (combat encounter creation, mission issue, the
``declare_stakes`` GM action). The per-player boundary registry (#1771) is
now wired: it follows the shape of the consent app
(``world.consent`` / ``world.boundaries``, ADR-0024/ADR-0086) — explicit
per-player preference rows consulted by free service functions, no signals.
At authoring time the participants are unknown (``character_sheets=[]``), so
the screen short-circuits to ``allowed=True`` there; the real enforcement
(hard-line block + treasured requires-signoff) fires at each
activation/commit call site where the party is known.

Call sites gate on ``StakeBoundaryReport.cleared`` (allowed AND no pending
sign-off), so #1771 can start returning ``requires_signoff`` without
revisiting any call site.

Privacy invariant (ADR-0033): a blocked report's ``blocked_reason_private``
is for staff/audit logging only. It is NEVER shown to the GM or other
players — a boundary is private; callers surface only a generic
"stakes could not be presented" failure.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from django.utils import timezone

from world.stories.types import PendingTreasuredSignoffs, StakeAvailability, StakeBoundaryReport

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from evennia_extensions.models import PlayerData
    from world.boundaries.models import TreasuredSubject
    from world.character_sheets.models import CharacterSheet
    from world.stories.models import Beat, Stake, TreasuredSignoff

# Identity key: (subject_kind, subject_sheet_id, subject_item_id,
# subject_society_id, subject_organization_id, subject_label-or-"").
SubjectIdentity = tuple[str, int | None, int | None, int | None, int | None, str]


def _subject_identity(  # noqa: PLR0913 — one arg per typed subject pointer; Task 4 reuses this exact shape
    subject_kind: str,
    subject_sheet_id: int | None,
    subject_item_id: int | None,
    subject_society_id: int | None,
    subject_organization_id: int | None,
    subject_label: str,
) -> SubjectIdentity:
    """Identity key comparing a ``Stake``'s wagered subject to a ``TreasuredSubject``.

    Two subjects are "the same thing" when ``subject_kind`` and whichever
    typed FK that kind actually populates are equal. Kinds with no typed
    pointer (CUSTOM / CAMPAIGN_TRACK / freeform LOCATION) fall back to the
    free-text ``subject_label`` as the identity, so untyped subjects with no
    FK set don't all collide on ``(kind, None, None, None, None)``.

    Shared by ``check_stake_boundaries`` (treasured requires-signoff
    matching) and ``resolve_stakes_for_completion``'s withdrawal override
    (#1771 task 4) — both must import this single definition to stay in sync.
    """
    has_typed_pointer = any(
        (subject_sheet_id, subject_item_id, subject_society_id, subject_organization_id)
    )
    return (
        subject_kind,
        subject_sheet_id,
        subject_item_id,
        subject_society_id,
        subject_organization_id,
        "" if has_typed_pointer else subject_label,
    )


def _treasured_requires_signoff(
    stakes: list[Stake],
    sheets: list[CharacterSheet],
    sheet_player: dict[int, int],
    sheet_tenure: dict[int, int],
    beat: Beat,
) -> set[int]:
    """Sheet ids whose treasured subject is staked on ``beat`` without an active sign-off.

    Batched: one query for the participants' ``TreasuredSubject`` rows, one
    for active ``TreasuredSignoff`` rows on this beat — no per-loop queries.
    """
    from world.boundaries.models import TreasuredSubject  # noqa: PLC0415
    from world.stories.models import TreasuredSignoff  # noqa: PLC0415

    tenure_ids = set(sheet_tenure.values())
    if not tenure_ids:
        return set()

    stake_identities = {
        _subject_identity(
            st.subject_kind,
            st.subject_sheet_id,
            st.subject_item_id,
            st.subject_society_id,
            st.subject_organization_id,
            st.subject_label,
        )
        for st in stakes
    }

    # tenure_id -> {identity: treasured_subject_id}, restricted to subjects
    # actually staked on this contract.
    treasured_by_tenure: dict[int, dict[SubjectIdentity, int]] = defaultdict(dict)
    treasured_rows = TreasuredSubject.objects.filter(owner_id__in=tenure_ids).values_list(
        "owner_id",
        "pk",
        "subject_kind",
        "subject_sheet_id",
        "subject_item_id",
        "subject_society_id",
        "subject_organization_id",
        "subject_label",
    )
    for (
        owner_id,
        pk,
        subject_kind,
        subject_sheet_id,
        subject_item_id,
        subject_society_id,
        subject_organization_id,
        subject_label,
    ) in treasured_rows:
        identity = _subject_identity(
            subject_kind,
            subject_sheet_id,
            subject_item_id,
            subject_society_id,
            subject_organization_id,
            subject_label,
        )
        if identity in stake_identities:
            treasured_by_tenure[owner_id][identity] = pk

    if not treasured_by_tenure:
        return set()

    player_ids = set(sheet_player.values())
    active_signoffs = set(
        TreasuredSignoff.objects.filter(
            beat=beat,
            withdrawn_at__isnull=True,
            player_data_id__in=player_ids,
        ).values_list("player_data_id", "treasured_subject_id")
    )

    requires: set[int] = set()
    for sheet in sheets:
        tenure_id = sheet_tenure.get(sheet.pk)
        player_id = sheet_player.get(sheet.pk)
        if tenure_id is None or player_id is None:
            continue
        for treasured_id in treasured_by_tenure.get(tenure_id, {}).values():
            if (player_id, treasured_id) not in active_signoffs:
                requires.add(sheet.pk)
                break
    return requires


def _resolve_sheet_identity(
    sheets: list[CharacterSheet],
) -> tuple[dict[int, int], dict[int, int]]:
    """sheet.pk -> player_data_id, and sheet.pk -> tenure.pk.

    Query-free: mirrors the cached ``roster_entry.current_tenure`` pattern in
    ``character_sheets/serializers.py`` (``_viewer_is_privileged``).
    """
    sheet_player: dict[int, int] = {}
    sheet_tenure: dict[int, int] = {}
    for sheet in sheets:
        entry = getattr(sheet, "roster_entry", None)  # noqa: GETATTR_LITERAL — OneToOne reverse may not exist
        cur = entry.current_tenure if entry else None
        if cur is not None:
            sheet_player[sheet.pk] = cur.player_data_id
            sheet_tenure[sheet.pk] = cur.pk
    return sheet_player, sheet_tenure


def _hard_line_blocked_pair_count(
    stakes: list[Stake],
    sheets: list[CharacterSheet],
    sheet_player: dict[int, int],
) -> int:
    """How many (player, stake) pairs hit a hard line — batched, no per-loop queries."""
    from world.boundaries.constants import BoundaryKind  # noqa: PLC0415
    from world.boundaries.models import ContentTheme, PlayerBoundary  # noqa: PLC0415

    player_ids = set(sheet_player.values())
    hard_rows = PlayerBoundary.objects.filter(
        owner_id__in=player_ids,
        kind=BoundaryKind.HARD_LINE,
        theme__isnull=False,
    ).values_list("owner_id", "theme_id")
    player_hard_themes: dict[int, set[int]] = defaultdict(set)
    for owner_id, theme_id in hard_rows:
        player_hard_themes[owner_id].add(theme_id)

    # template_id -> set(theme_id), one query across every staked template.
    template_ids = {st.template_id for st in stakes if st.template_id}
    stake_template_themes: dict[int, set[int]] = defaultdict(set)
    if template_ids:
        theme_rows = ContentTheme.objects.filter(
            stake_templates__in=template_ids,
        ).values_list("stake_templates", "pk")
        for template_id, theme_id in theme_rows:
            stake_template_themes[template_id].add(theme_id)

    count = 0
    for sheet in sheets:
        pid = sheet_player.get(sheet.pk)
        hard_themes = player_hard_themes.get(pid) if pid is not None else None
        if not hard_themes:
            continue
        count += sum(
            1
            for st in stakes
            if st.template_id and stake_template_themes.get(st.template_id, set()) & hard_themes
        )
    return count


def check_stake_boundaries(
    stakes: Iterable[Stake],
    character_sheets: Sequence[CharacterSheet],
) -> StakeBoundaryReport:
    """Screen a contract's stakes against the participants' boundaries.

    Accepts the whole contract's stakes in one call so call sites screen a
    beat's contract with a single invocation. ``character_sheets`` is the
    party the contract would activate for; at authoring time (StakeSerializer)
    the players are not yet known and callers pass an empty sequence.

    Two registries are consulted (#1771), both batched — no queries inside a
    loop over stakes or sheets:

    - **Hard lines** (``PlayerBoundary``, always private): if any participant
      hard-lined a content theme carried by any staked template, the whole
      report is blocked. ``blocked_reason_private`` is a terse staff/audit
      line only — see the module docstring's privacy invariant (ADR-0033).
    - **Treasured subjects** (``TreasuredSubject`` + ``TreasuredSignoff``):
      a participant whose treasured subject is staked on this beat without
      an active sign-off is added to ``requires_signoff``.
    """
    stakes = list(stakes)
    sheets = list(character_sheets)
    if not stakes or not sheets:
        return StakeBoundaryReport(allowed=True)

    sheet_player, sheet_tenure = _resolve_sheet_identity(sheets)

    blocked_count = _hard_line_blocked_pair_count(stakes, sheets, sheet_player)
    if blocked_count:
        return StakeBoundaryReport(
            allowed=False,
            blocked_reason_private=(
                f"hard-line theme match on {blocked_count} (player,stake) pair(s)"
            ),
        )

    # TREASURED SUBJECTS: requires-signoff, not a block.
    beat = stakes[0].beat
    requires = _treasured_requires_signoff(stakes, sheets, sheet_player, sheet_tenure, beat)
    if requires:
        return StakeBoundaryReport(allowed=True, requires_signoff=tuple(sorted(requires)))
    return StakeBoundaryReport(allowed=True)


def grant_treasured_signoff(
    beat: Beat,
    player_data: PlayerData,
    treasured_subject: TreasuredSubject,
) -> TreasuredSignoff:
    """Create (or reactivate) a player's pre-scene sign-off on ``beat``.

    Idempotent: the most recent existing ``TreasuredSignoff`` for this exact
    ``(beat, player_data, treasured_subject)`` triple is reactivated (its
    ``withdrawn_at`` cleared) instead of creating a duplicate row; calling
    this when an active signoff already exists is a no-op. Never hard-deletes
    or duplicates — story-significant data.
    """
    from world.stories.models import TreasuredSignoff  # noqa: PLC0415

    existing = (
        TreasuredSignoff.objects.filter(
            beat=beat,
            player_data=player_data,
            treasured_subject=treasured_subject,
        )
        .order_by("-granted_at", "-pk")
        .first()
    )
    if existing is not None:
        if not existing.active:
            existing.withdrawn_at = None
            existing.save(update_fields=["withdrawn_at"])
        return existing
    return TreasuredSignoff.objects.create(
        beat=beat,
        player_data=player_data,
        treasured_subject=treasured_subject,
    )


def withdraw_treasured_signoff(signoff: TreasuredSignoff) -> None:
    """Soft-withdraw a sign-off: sets ``withdrawn_at`` (never deletes). Idempotent."""
    if signoff.active:
        signoff.withdrawn_at = timezone.now()
        signoff.save(update_fields=["withdrawn_at"])


def stake_availability(
    beat: Beat,
    character_sheets: Sequence[CharacterSheet],
) -> StakeAvailability:
    """GM-facing counts of how ``beat``'s candidate stakes screen for a party (#1771).

    Reuses ``check_stake_boundaries`` once per candidate ``Stake`` on the beat
    so the exact same hard-line/treasured logic backs both the enforcement
    seam and this read — COUNTS ONLY, never a reason, never which player or
    stake (ADR-0033). One ``check_stake_boundaries`` call per stake (each
    already batched internally); bounded by the number of stakes on a single
    beat, not by scene/story size.
    """
    sheets = list(character_sheets)
    available = blocked = needs_signoff = 0
    for stake in beat.stakes.all():
        report = check_stake_boundaries([stake], sheets)
        if not report.allowed:
            blocked += 1
        elif report.requires_signoff:
            needs_signoff += 1
        else:
            available += 1
    return StakeAvailability(available=available, blocked=blocked, needs_signoff=needs_signoff)


def player_pending_treasured_signoffs(
    player_data: PlayerData,
    beats: Sequence[Beat],
) -> list[PendingTreasuredSignoffs]:
    """For each of ``beats``, which of ``player_data``'s own TreasuredSubjects are
    staked on it without an active TreasuredSignoff (#1853).

    Player-safe (ADR-0033): only ever reads this player's own TreasuredSubject/
    TreasuredSignoff rows plus the given beats' Stake rows — never another
    player's sheets, other stakes, hard-line info, or the GM's broader stake
    plan. Batched: one query for the player's own TreasuredSubjects (scoped to
    tenures where the player is the CURRENT player — ``end_date__isnull=True``,
    mirroring ``_resolve_sheet_identity``'s "current tenure only" semantics),
    one for Stake rows across all given beats, one for the player's active
    TreasuredSignoff rows across all given beats. Reuses ``_subject_identity``
    for matching — the same identity function ``_treasured_requires_signoff``
    uses, so this never drifts from the enforcement seam's definition of
    "match." Needs no CharacterSheet list at all (unlike the GM-side
    function) since TreasuredSubject.owner is a RosterTenure directly.
    """
    from world.boundaries.models import TreasuredSubject  # noqa: PLC0415
    from world.stories.models import Stake, TreasuredSignoff  # noqa: PLC0415

    beats = list(beats)
    if not beats:
        return []

    tenure_ids = list(
        player_data.tenures.filter(end_date__isnull=True).values_list("pk", flat=True)
    )
    if not tenure_ids:
        return []

    subjects = list(TreasuredSubject.objects.filter(owner_id__in=tenure_ids))
    if not subjects:
        return []

    subject_by_identity: dict[SubjectIdentity, int] = {
        _subject_identity(
            s.subject_kind,
            s.subject_sheet_id,
            s.subject_item_id,
            s.subject_society_id,
            s.subject_organization_id,
            s.subject_label,
        ): s.pk
        for s in subjects
    }

    beat_ids = [b.pk for b in beats]
    stake_rows = Stake.objects.filter(beat_id__in=beat_ids).values_list(
        "beat_id",
        "subject_kind",
        "subject_sheet_id",
        "subject_item_id",
        "subject_society_id",
        "subject_organization_id",
        "subject_label",
    )

    matched_by_beat: dict[int, set[int]] = defaultdict(set)
    for (
        beat_id,
        subject_kind,
        subject_sheet_id,
        subject_item_id,
        subject_society_id,
        subject_organization_id,
        subject_label,
    ) in stake_rows:
        identity = _subject_identity(
            subject_kind,
            subject_sheet_id,
            subject_item_id,
            subject_society_id,
            subject_organization_id,
            subject_label,
        )
        treasured_id = subject_by_identity.get(identity)
        if treasured_id is not None:
            matched_by_beat[beat_id].add(treasured_id)

    if not matched_by_beat:
        return []

    active_signoffs = set(
        TreasuredSignoff.objects.filter(
            beat_id__in=matched_by_beat.keys(),
            player_data=player_data,
            withdrawn_at__isnull=True,
        ).values_list("beat_id", "treasured_subject_id")
    )

    result: list[PendingTreasuredSignoffs] = []
    for beat_id, treasured_ids in matched_by_beat.items():
        pending = sorted(tid for tid in treasured_ids if (beat_id, tid) not in active_signoffs)
        if pending:
            result.append(
                PendingTreasuredSignoffs(beat_id=beat_id, treasured_subject_ids=tuple(pending))
            )
    result.sort(key=lambda e: e.beat_id)
    return result
