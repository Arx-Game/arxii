"""Story-asset custody — the single custody-check service seam (#2001).

Protects load-bearing story assets (NPCs, items, factions, locations, custom
subjects) from being appeared-with/harmed/removed by actors outside the
story that declared them ``StoryProtectedSubject``. Every enforcement point
(death guard, stake authoring, opponent spawning, ...) funnels through
``check_subject_custody`` so the participation/staff/clearance rule can never
drift between call sites.

Axis note (ADR pending, see issue #2001): this is GM/story-declared
*narrative structure* protection — distinct from ``world.boundaries``
(player-declared OOC emotional safety). Neither replaces the other.

Subject identity matching reuses ``_subject_identity`` from
``world.stories.services.boundaries`` (single definition, shared with the
``Stake``/``TreasuredSubject`` boundary screen) — ``StoryProtectedSubject``
and ``Stake`` share the exact typed-subject-FK shape, so the same identity
tuple compares either model's rows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.stories.constants import BeatOutcome, CustodyScope, StakeResolutionColumn
from world.stories.models import StoryParticipation, StoryProtectedSubject
from world.stories.services.boundaries import SubjectIdentity, _subject_identity
from world.stories.services.custody_clearance import active_clearance_exists
from world.stories.types import CustodyVerdict, StoryStatus

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.stories.models import Stake, Story


def _protection_window_active(protection: StoryProtectedSubject) -> bool:
    """Whether ``protection`` currently guards its subject.

    Ported verbatim from the original ``is_death_prevented_by_story`` window
    check: beat-scoped protections apply only while the beat is unsatisfied;
    story-level protections apply only while the story is ACTIVE.
    """
    if protection.beat is not None:
        return protection.beat.outcome == BeatOutcome.UNSATISFIED
    return protection.story.status == StoryStatus.ACTIVE


def _matching_protections(subject_identity: SubjectIdentity) -> list[StoryProtectedSubject]:
    """Active, window-open ``StoryProtectedSubject`` rows matching ``subject_identity``.

    One query: filtering by ``subject_kind`` (the identity's first element)
    narrows the row scan at the database; the typed-FK-or-label identity
    comparison happens in Python via ``_subject_identity``, mirroring how
    ``boundaries.py`` matches ``Stake`` rows against ``TreasuredSubject`` rows.

    Ordered ``created_at, pk`` ascending (oldest first) rather than the
    model's default ``Meta.ordering`` (``-created_at, -pk``, newest first):
    ``check_subject_custody`` reports the FIRST row of this list as the
    blocking custodian, and the oldest-declared protection is the original
    custodian — the natural authority to route a clearance request to.
    """
    kind = subject_identity[0]
    candidates = (
        StoryProtectedSubject.objects.filter(subject_kind=kind, is_active=True)
        .select_related("story__primary_table__gm__account", "beat")
        .order_by("created_at", "pk")
    )
    return [
        row
        for row in candidates
        if _protection_window_active(row)
        and _subject_identity(
            row.subject_kind,
            row.subject_sheet_id,
            row.subject_item_id,
            row.subject_society_id,
            row.subject_organization_id,
            row.subject_label,
        )
        == subject_identity
    ]


def _actor_character_ids(actor_account: AccountDB | None) -> set[int]:
    """ObjectDB pks of the characters ``actor_account`` currently plays.

    Bounded by the account's active tenures (typically one, rarely more) —
    mirrors ``PlayerData.get_available_characters``'s tenure walk, not a
    query-per-loop-row concern. ``CharacterSheet.character`` is a primary-key
    ``OneToOneField``, so ``roster_entry.character_sheet_id`` already IS the
    ObjectDB pk with no extra hop.
    """
    if actor_account is None:
        return set()
    player_data = getattr(actor_account, "player_data", None)  # noqa: GETATTR_LITERAL
    if player_data is None:
        return set()
    return {tenure.roster_entry.character_sheet_id for tenure in player_data.cached_active_tenures}


def _active_clearance_allows(
    protection: StoryProtectedSubject,
    actor_account: AccountDB | None,
    scope: str,
) -> bool:
    """Whether an active, unrevoked ``CustodyClearance`` covers this actor at ``scope``.

    Delegates to ``custody_clearance.active_clearance_exists`` (#2001 Task 3) —
    active means status GRANTED, ``revoked_at`` null, scope index >= the
    required scope's index, and the clearance's requester's account matches
    ``actor_account``.
    """
    return active_clearance_exists(protected_subject=protection, account=actor_account, scope=scope)


def check_subject_custody(
    *,
    subject_identity: SubjectIdentity,
    actor_account: AccountDB | None,
    scope: str,
    acting_story: Story | None = None,
) -> CustodyVerdict:
    """THE custody seam — every enforcement point calls this.

    Allowed when:
    - No active ``StoryProtectedSubject`` matches ``subject_identity``; OR
    - ``actor_account`` is staff; OR
    - For EVERY matching protection: the protection's own story IS
      ``acting_story`` (acting from within the very story that protects the
      subject is never "a different story"), OR the actor participates in
      that protecting story (mirrors ``is_death_prevented_by_story``'s
      participation test, resolved via the actor's currently-played
      characters), OR an active, unrevoked ``CustodyClearance`` at >= scope
      exists for the actor (``custody_clearance.active_clearance_exists``).

    When blocked, ``requires_scope`` echoes ``scope`` back: a
    ``StoryProtectedSubject`` row has no per-scope grain of its own (that is
    what ``CustodyClearance.scope`` will express), so an active protection
    blocks every scope uniformly until a clearance says otherwise.
    ``custodian_gm_username``/``protecting_subject_id`` report the OLDEST
    blocking protection (earliest ``created_at``, tie-broken by ``pk``) when
    several stories protect the same identity: the original custodian is the
    natural authority to route a clearance request to, so the verdict must
    not drift onto whichever story most recently added an overlapping
    protection. ``_matching_protections`` orders ascending for this reason —
    it does not rely on the model's default (most-recent-first) ordering.

    Batched: one query for matching protections, one for participation
    across every still-unresolved protecting story — never a query per
    protection.
    """
    if actor_account is not None and actor_account.is_staff:
        return CustodyVerdict(allowed=True)

    protections = _matching_protections(subject_identity)
    if not protections:
        return CustodyVerdict(allowed=True)

    # A protection whose OWN story is the acting story is never "a different
    # story" — no participation/clearance check needed for it.
    unresolved = [
        protection
        for protection in protections
        if acting_story is None or protection.story_id != acting_story.pk
    ]
    if not unresolved:
        return CustodyVerdict(allowed=True)

    actor_character_ids = _actor_character_ids(actor_account)
    participant_story_ids: set[int] = set()
    if actor_character_ids:
        story_ids = {protection.story_id for protection in unresolved}
        participant_story_ids = set(
            StoryParticipation.objects.filter(
                story_id__in=story_ids,
                character_id__in=actor_character_ids,
                is_active=True,
            ).values_list("story_id", flat=True)
        )

    blocking = [
        protection
        for protection in unresolved
        if protection.story_id not in participant_story_ids
        and not _active_clearance_allows(protection, actor_account, scope)
    ]
    if not blocking:
        return CustodyVerdict(allowed=True)

    first = blocking[0]
    custodian_gm_username = None
    if first.story.primary_table is not None:
        custodian_gm_username = first.story.primary_table.gm.account.username
    return CustodyVerdict(
        allowed=False,
        requires_scope=scope,
        custodian_gm_username=custodian_gm_username,
        protecting_subject_id=first.pk,
    )


def _stake_intended_scope(stake: Stake) -> str:
    """Derive the custody scope a ``Stake``'s authored resolutions actually reach for.

    REMOVE if any resolution sets the subject's lifecycle or forfeits the
    subject item; else HARM if any resolution adjusts standing (any column)
    or fires a consequence pool on its LOSS branch; else APPEAR.
    """
    resolutions = list(stake.resolutions.all())
    if any(r.sets_subject_lifecycle or r.forfeits_subject_item for r in resolutions):
        return CustodyScope.REMOVE
    if any(
        r.subject_standing_delta != 0
        or (r.column == StakeResolutionColumn.LOSS and r.consequence_pool_id is not None)
        for r in resolutions
    ):
        return CustodyScope.HARM
    return CustodyScope.APPEAR


def custody_verdict_for_stake(
    stake: Stake,
    actor_account: AccountDB | None,
    *,
    intended_scope: str | None = None,
) -> CustodyVerdict:
    """Custody verdict for staking/resolving ``stake``'s wagered subject.

    ``intended_scope``: pass explicitly to check a single authored branch in
    isolation (e.g. the ``StakeResolution`` writer validation checking one
    LOSS branch's REMOVE requirement) rather than the stake's aggregate.
    Left as None (the common case, e.g. ``StakeSerializer.validate``) derives
    it from every authored resolution via ``_stake_intended_scope``.
    """
    if intended_scope is None:
        intended_scope = _stake_intended_scope(stake)
    subject_identity = _subject_identity(
        stake.subject_kind,
        stake.subject_sheet_id,
        stake.subject_item_id,
        stake.subject_society_id,
        stake.subject_organization_id,
        stake.subject_label,
    )
    return check_subject_custody(
        subject_identity=subject_identity,
        actor_account=actor_account,
        scope=intended_scope,
        acting_story=stake.beat.episode.chapter.story,
    )


def is_death_prevented_by_story(
    npc_sheet: CharacterSheet,
    attacker: ObjectDB | None,
) -> bool:
    """Return True if the NPC's death is prevented by story-criticality.

    Preserved exact signature and behavior from the original #1874
    implementation (moved here from ``world.stories.npc_protection``, which
    is now a thin re-export shim for the combat/vitals import sites). Kept
    character-based (not re-expressed over ``check_subject_custody``'s
    account-based participation test): ``StoryParticipation.character`` can
    be an NPC ally with no ``AccountDB`` at all, so mapping through an
    account here would silently break NPC participants. The two functions
    share only the window-active predicate (``_protection_window_active``).

    Checks all active ``StoryProtectedSubject`` rows for the NPC (matched via
    ``subject_sheet``). For each, verifies whether the attacker is a
    participant in that story (via ``StoryParticipation``). If ANY active
    dependency has a non-participant attacker, death is prevented.

    Returns False (death permitted) when:
    - No active dependencies exist for this NPC.
    - The attacker is a participant in ALL active dependent stories.
    - All dependencies are inactive (story concluded, beat resolved, or
      manually deactivated).

    Returns True (death prevented) when:
    - Any active dependency exists and the attacker is not a participant in
      that story.
    - Any active dependency exists and the attacker is None (environmental
      death — a story-critical NPC is also protected from non-actor sources).

    This is a parallel gate to ``has_death_deferred`` — both are independent
    checks in the death-gate sequence.

    Args:
        npc_sheet: The NPC's CharacterSheet.
        attacker: The attacking character's ObjectDB, or None for environmental.

    Returns:
        True if death is prevented, False if permitted.
    """
    deps = list(
        StoryProtectedSubject.objects.filter(
            subject_sheet=npc_sheet,
            is_active=True,
        ).select_related("story", "beat")
    )

    if not deps:
        return False

    for dep in deps:
        if not _protection_window_active(dep):
            continue

        if attacker is None:
            return True

        is_participant = StoryParticipation.objects.filter(
            story=dep.story,
            character=attacker,
            is_active=True,
        ).exists()

        if not is_participant:
            return True

    return False
