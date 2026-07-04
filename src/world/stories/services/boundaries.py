"""Player-boundary screening seam for stakes contracts (#1770 pillar 10).

The seam runs at authoring time (``StakeSerializer``) and at every
activation/commit call site (combat encounter creation, mission issue, the
``declare_stakes`` GM action), so it exists from day one even though the
screening itself is an allow-all stub. The real implementation — a
per-player boundary registry (tracked on the boundaries sibling issue of
#1770, #1771) — will follow the shape of the consent app
(``world.consent.services``, ADR-0024): explicit per-player preference rows
consulted by free service functions, no signals.

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

from world.stories.types import StakeBoundaryReport

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from world.character_sheets.models import CharacterSheet
    from world.stories.models import Beat, Stake

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
