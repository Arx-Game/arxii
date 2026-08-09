"""The guarded beta-reset wipe service (#3055 PR 2).

**What this is.** A one-shot, heavily-guarded wipe of every play-provenance row in the
world, run once at the alpha→beta early-access cutover to derive a "pristine, as-authored"
world from the acquisition-provenance ledger (ADR-0206): strip everything a character
acquired through PLAY, and whatever carries CG/authoring provenance IS the baseline.

**Four independent guards, all of which must pass before anything is deleted:**

1. ``BETA_RESET_ENABLED`` — a hardcoded module-level constant (below), not a setting or
   env var. Flipping it to ``False`` at cutover is a reviewed code change — re-enabling
   the command later requires another one, by construction. This is deliberately NOT an
   env var or DB flag: those can be flipped without review.
2. ``ReleaseLatch`` — a belt-and-suspenders, DB-side, one-way marker (``world.beta_reset.
   models.ReleaseLatch``). Independent of the constant above: even a stale deploy that
   still has ``BETA_RESET_ENABLED = True`` baked in is stopped once ``mark_released()``
   has written a row. There is no "unmark" path.
3. **Typed confirmation phrase** — the operator must type ``CONFIRMATION_PHRASE`` exactly
   (see the management command's ``--confirm`` argument).
4. **Verified-fresh-backup precheck** — the operator must supply
   ``--backup-verified-at <ISO timestamp>`` within ``BACKUP_FRESHNESS_WINDOW`` of "now."
   This command does NOT run or verify a backup itself (that's ``infra/scripts/
   restore-rehearsal.sh``, run by hand) — it only refuses to proceed without evidence one
   was done recently.

**Default is dry-run.** ``wipe_pristine_world(execute=False)`` (the default) touches
nothing and returns per-model counts of what WOULD be deleted. Only ``execute=True`` —
which the command only reaches after all four guards above pass — performs the delete,
inside one transaction, calling ``refresh_legend_views()`` at the end.

**Scope: what this wipes.** See ``SCOPE_TABLE`` below — the single source of truth,
introspectable by tests and by PR 3. Two shapes:

- **Wholesale** (``filter_kwargs=None``): every row in the table is play-state with no
  CG/authoring counterpart (scenes, journals, justice, secrets, NPC standing, economy
  ledgers, achievements earned, Discovery, legend/renown ledgers). Delete all rows.
- **Provenance-filtered** (``filter_kwargs`` set): the table mixes CG/authoring rows with
  play-time rows, distinguished by a discriminator column (``CharacterTechnique.origin``,
  ``CharacterGift.origin``, ``CharacterTraitChange.source``, ``CharacterDistinction.origin``).
  Delete only rows whose discriminator value is in the play-time set; the CG/authoring value
  IS the pristine baseline and survives untouched.

**PR 2 / PR 3 boundary — read this before touching derived values.** This service does
**NOT** step ``CharacterTraitValue`` back down after deleting a play-time
``CharacterTraitChange`` row, even though that row recorded the exact delta. That
"replay the ledger backwards to restore a derived value" logic is **PR 3's roster
progress-reset** scope (the spec: "roster characters progress-reset (via the ledger)" is
explicitly PR 3), which needs to be careful and precise because PR 3 operates on
characters that are *kept*. PR 2's own characters — the alpha test population — are
**deleted wholesale at cutover by a separate step outside this command** (not by
``wipe_pristine_world`` — this service never touches ``CharacterSheet``, ``Persona``,
``RosterEntry``, or ``RosterTenure`` at all), so any derived-value drift this wipe leaves
behind on a surviving ledger is moot for them. This wipe is reusable general-purpose
"strip play-state, keep provenance-tagged CG rows" plumbing; PR 3 is what makes the
numbers on a *kept* character's sheet consistent again.

**What this does NOT touch, and why:**

- ``CharacterSheet`` / ``Persona`` / ``RosterEntry`` / ``RosterTenure`` / ``Organization`` /
  ``Covenant`` — structural identity, out of scope (see the PR 2/PR 3 boundary above).
- ``GMProfile`` / ``AccountDB`` / kudos / ``Block`` / ``Friendship`` / ``Rivalry`` /
  ``Mute`` — account-level data (#3055 PR 3's policy layer decides what survives at the
  account boundary; this command never reaches AccountDB-anchored rows).
- ``CrimeKind`` / ``AreaLaw`` / ``SecretCategory`` / ``Profession`` / catalog & config
  singletons (e.g. ``SceneRoundDefaultsConfig``, ``ReactionEmoji``) — authored/staff
  config, not play-state.
- ``DistinctionPurseDrain`` — a distinction's authored drain-rate rule, not a per-character
  ledger row.
- ``OrganizationTreasury`` / org economics (``OrgEconomicsProfile``, ``OrgIncomeStream``,
  ``IncomeDeclaration``, ``OrgObligation``, ``ContributionRecord``) — org-scoped books.
  Organizations themselves survive the reset, so their accumulated treasury/economics
  state is left alone by deliberate choice, not oversight; if a future PR decides orgs
  should also reset, this is the place to extend ``SCOPE_TABLE``.
- ``CharacterCodexKnowledge`` — no CG-vs-play discriminator exists on this model (a CG
  grant and a play-time research payoff both just write ``status=KNOWN`` with no origin
  tag), so it cannot be safely provenance-filtered today. Left untouched; flagged here
  rather than guessed at. "Codex first-learner records" (the spec's own phrase) is
  ``achievements.Discovery`` — covered below — not this table.
- ``KudosTransaction.character`` / ``Block.blocker_persona`` / ``Block.blocked_persona`` —
  already resilient by construction (``SET_NULL``, not ``PROTECT``/``CASCADE``); nothing
  to do here even though these rows reference play-state that partially survives.

**PROTECT-ordering landmines this table resolves (see the ADR-0207 + tests for detail):**

- ``FrameJobDetails.evidence`` is ``PROTECT`` against ``CrimeEvidence`` — ``FrameJobDetails``
  must be deleted before ``CrimeEvidence``.
- ``CombatEncounter.scene`` and ``TreatmentAttempt.scene`` are both ``PROTECT`` against
  ``scenes.Scene`` — both must be deleted before ``Scene`` (they're not spec-named by app,
  but they block the spec-named "scenes" wipe from running at all).
- ``NPCStanding.persona`` / ``.npc_persona`` are ``PROTECT`` against ``scenes.Persona`` —
  irrelevant in practice since this wipe never deletes ``Persona``, but ``NPCStanding`` is
  deleted anyway as its own wholesale play-state row (per-PC-NPC disposition).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.db import transaction
from django.db.models import Model
from django.utils import timezone
from evennia.accounts.models import AccountDB

from world.achievements.models import CharacterAchievement, Discovery
from world.beta_reset.exceptions import (
    AlreadyReleasedError,
    BackupNotVerifiedError,
    BetaResetDisabledError,
    ConfirmationPhraseMismatchError,
    ReleaseLatchedError,
)
from world.beta_reset.models import ReleaseLatch
from world.combat.models import CombatEncounter
from world.conditions.models import TreatmentAttempt
from world.currency.models import (
    Business,
    CharacterEmployment,
    CharacterPurse,
    Contract,
    CurrencyTransfer,
    DebtInstrument,
    PurseDrainWeek,
)
from world.distinctions.models import CharacterDistinction
from world.distinctions.types import DistinctionOrigin
from world.journals.models import JournalEntry, WeeklyJournalXP
from world.justice.models import (
    AccusationCrimeClaim,
    AccusationNullification,
    CrimeEvidence,
    DeedCrimeTag,
    DenounceRecord,
    ExculpatoryEvidence,
    FrameJobDetails,
    GuardEncounter,
    HeatSource,
    JusticeCase,
    LieLowState,
    PardonGrant,
    PersonaHeat,
)
from world.magic.constants import AcquisitionOrigin
from world.magic.models import CharacterGift, CharacterTechnique, ResonanceGrant
from world.npc_services.models import NPCStanding
from world.progression.models import CharacterXPTransaction, ClassLevelAdvancement
from world.scenes.models import (
    DecisiveCheckMarker,
    Interaction,
    InteractionAction,
    InteractionFavorite,
    InteractionPowerLedgerEntry,
    InteractionReaction,
    InteractionTargetPersona,
    PendingSuddenHarm,
    PersonaDiscovery,
    Scene,
    SceneActionDeclaration,
    SceneCheckModifier,
    SceneParticipation,
    SceneRound,
    SceneRoundParticipant,
    SceneSummaryRevision,
    SceneUnseenObserver,
)
from world.secrets.models import Secret
from world.societies.models import LegendEntry, LegendEvent, refresh_legend_views
from world.traits.models import CharacterTraitChange, TraitChangeSource

# =============================================================================
# Guard 1: hardcoded source constant
# =============================================================================

#: LOUD WARNING: this is a literal, not a setting/env var, by deliberate design (#3055
#: PR 2). Flip this to False in a reviewed PR at the beta early-access cutover. Re-enabling
#: it afterward requires another reviewed code change — that friction is the point. Do NOT
#: replace this with an environment variable or a DB-driven flag; that would let someone
#: re-arm the wipe without a code review, which is exactly the failure mode this guards
#: against. See ADR-0207.
BETA_RESET_ENABLED = True

#: The exact phrase the operator must type via ``--confirm``. Deliberately unambiguous —
#: not "yes"/"confirm", but a sentence that reads as what it does.
CONFIRMATION_PHRASE = "wipe the alpha world"

#: How fresh ``--backup-verified-at`` must be. This command does not verify a backup
#: itself (see ``infra/scripts/restore-rehearsal.sh``); it only refuses to run without
#: recent evidence one was done.
BACKUP_FRESHNESS_WINDOW = timedelta(hours=24)

# =============================================================================
# Provenance discriminator splits (ADR-0206) — which values are PLAY-TIME (wiped) vs
# CG/authoring (survive). Read straight off each enum's own docstring; see the module
# docstring above and world/magic/constants.py:660 / world/traits/models.py
# (TraitChangeSource) / world/distinctions/types.py:52 for the source-of-truth enums
# this classifies.
# =============================================================================

#: CHARACTER_CREATION (CG finalize) and SPECIES_GRANT/AUTHORED are CG/authoring-time —
#: SPECIES_GRANT fires from ``provision_species_gifts``, called from
#: ``finalize_magic_data`` during CG finalize, same moment as CHARACTER_CREATION; AUTHORED
#: is a designer/staff minting a brand-new Technique into the catalog (an authoring act),
#: not a character acquiring something through play. Every other value is a play-time grant.
PLAY_TIME_ACQUISITION_ORIGINS = frozenset(
    {
        AcquisitionOrigin.PATH_GRANT,
        AcquisitionOrigin.TRAINED,
        AcquisitionOrigin.ROLE_GRANT,
        AcquisitionOrigin.ORGANIZATION_GRANT,
        AcquisitionOrigin.ALTERNATE_SELF_GRANT,
        AcquisitionOrigin.GM_GRANT,
    }
)

#: CHARACTER_CREATION is CG-time; every other source (level-ups, maturation, stat points,
#: GM grants) happens during play.
PLAY_TIME_TRAIT_CHANGE_SOURCES = frozenset(
    {
        TraitChangeSource.DEVELOPMENT_LEVEL_UP,
        TraitChangeSource.MATURATION,
        TraitChangeSource.LEVEL_STAT_POINT,
        TraitChangeSource.GM_GRANT,
    }
)

#: CHARACTER_CREATION and SPECIES are both CG-time (the distinctions app's own docstring:
#: "SPECIES ... is a finalize-time origin alongside CHARACTER_CREATION"). Every other
#: source is a post-CG, in-play acquisition through ``grant_distinction``.
PLAY_TIME_DISTINCTION_ORIGINS = frozenset(
    {
        DistinctionOrigin.GAMEPLAY,
        DistinctionOrigin.GM_AWARD,
        DistinctionOrigin.ACHIEVEMENT_AUTO_GRANT,
        DistinctionOrigin.CONSEQUENCE_POOL,
        DistinctionOrigin.ENDORSEMENT_THRESHOLD,
        DistinctionOrigin.UNLOCK_PURCHASE,
    }
)


@dataclass(frozen=True)
class ScopeEntry:
    """One row in ``SCOPE_TABLE``: a model plus how to select its play-state rows.

    ``filter_kwargs=None`` means "delete every row" (wholesale play-state, no
    CG/authoring counterpart exists in this table). A non-``None`` dict is passed to
    ``.filter(**filter_kwargs)`` before ``.delete()`` — the provenance-filtered shape.
    """

    model: type[Model]
    filter_kwargs: dict[str, Any] | None
    note: str


#: The single source of truth for what this wipe touches, in explicit dependency-safe
#: order (a ``ProtectedError`` at any position means a newly-added FK needs a new entry
#: ahead of its target — see the module docstring's "PROTECT-ordering landmines" section).
#: PR 3 and tests introspect this list directly rather than re-deriving it.
SCOPE_TABLE: list[ScopeEntry] = [
    # --- Acquisition-provenance ledger: filter by discriminator, not wholesale ---
    ScopeEntry(
        CharacterTechnique,
        {"origin__in": list(PLAY_TIME_ACQUISITION_ORIGINS)},
        "Play-time technique acquisitions (AcquisitionOrigin). CHARACTER_CREATION/"
        "SPECIES_GRANT/AUTHORED rows are CG/authoring and survive.",
    ),
    ScopeEntry(
        CharacterGift,
        {"origin__in": list(PLAY_TIME_ACQUISITION_ORIGINS)},
        "Play-time gift acquisitions (AcquisitionOrigin), same split as CharacterTechnique.",
    ),
    ScopeEntry(
        CharacterTraitChange,
        {"source__in": list(PLAY_TIME_TRAIT_CHANGE_SOURCES)},
        "Play-time trait-value change receipts (TraitChangeSource). Derived "
        "CharacterTraitValue is NOT stepped back — see the PR 2/PR 3 boundary in this "
        "module's docstring.",
    ),
    ScopeEntry(
        CharacterDistinction,
        {"origin__in": list(PLAY_TIME_DISTINCTION_ORIGINS)},
        "Post-CG distinction grants (DistinctionOrigin). CHARACTER_CREATION/SPECIES rows "
        "are CG/authoring and survive.",
    ),
    # --- Already-adequate receipts (#3055 spec's own phrase): wholesale, no CG variant ---
    ScopeEntry(CharacterXPTransaction, None, "XP ledger — inherently play-time."),
    ScopeEntry(ResonanceGrant, None, "Resonance-gain ledger — inherently play-time."),
    ScopeEntry(ClassLevelAdvancement, None, "Class-level advancement ledger — play-time."),
    # --- Achievements earned + Discovery slots (explicit spec scope) ---
    ScopeEntry(CharacterAchievement, None, "Per-character earned-achievement records."),
    ScopeEntry(Discovery, None, "First-ever-discovery slots (also codex first-learner)."),
    # --- Combat/conditions rows that PROTECT-block the Scene wipe below. Not spec-named
    # by app, but scenes/journals cannot wipe cleanly without clearing these first. ---
    ScopeEntry(
        CombatEncounter,
        None,
        "PROTECT-unblocker: CombatEncounter.scene is PROTECT against scenes.Scene.",
    ),
    ScopeEntry(
        TreatmentAttempt,
        None,
        "PROTECT-unblocker: TreatmentAttempt.scene is PROTECT against scenes.Scene.",
    ),
    # --- Scenes/journals (explicit spec scope): children before Scene itself. Most of
    # these cascade automatically off Scene/Interaction, but several (Interaction itself,
    # DecisiveCheckMarker, ...) are SET_NULL rather than CASCADE, so they're listed
    # explicitly instead of relying on cascade behavior. ---
    ScopeEntry(SceneParticipation, None, "Scene attendance rows."),
    ScopeEntry(SceneUnseenObserver, None, "Scene late-join visibility rows."),
    ScopeEntry(PersonaDiscovery, None, "Persona alt-identity discovery pairs."),
    ScopeEntry(InteractionFavorite, None, "Pose favorites."),
    ScopeEntry(InteractionReaction, None, "Pose reactions."),
    ScopeEntry(InteractionTargetPersona, None, "Pose target-persona rows."),
    ScopeEntry(InteractionAction, None, "Pose-to-action-declaration links."),
    ScopeEntry(InteractionPowerLedgerEntry, None, "Per-pose power-spend ledger rows."),
    ScopeEntry(Interaction, None, "The RP content log itself (poses/emits/says)."),
    ScopeEntry(SceneSummaryRevision, None, "Collaborative scene-summary edit history."),
    ScopeEntry(SceneCheckModifier, None, "Scene-scoped check modifiers."),
    ScopeEntry(SceneRoundParticipant, None, "Non-combat round participation rows."),
    ScopeEntry(SceneActionDeclaration, None, "Declared scene-round actions."),
    ScopeEntry(PendingSuddenHarm, None, "In-flight sudden-harm interpose windows."),
    ScopeEntry(DecisiveCheckMarker, None, "Pre-declared decisive-check markers."),
    ScopeEntry(SceneRound, None, "Non-combat round/turn structures."),
    ScopeEntry(Scene, None, "The scene containers themselves."),
    ScopeEntry(JournalEntry, None, "Journal entries (JournalTag cascades with it)."),
    ScopeEntry(WeeklyJournalXP, None, "Weekly journal-XP award tracker."),
    # --- Justice (explicit spec scope): FrameJobDetails before CrimeEvidence (PROTECT). ---
    ScopeEntry(ExculpatoryEvidence, None, "Justice-case exculpatory evidence submissions."),
    ScopeEntry(
        FrameJobDetails,
        None,
        "PROTECT-ordering: FrameJobDetails.evidence is PROTECT against CrimeEvidence — "
        "must be deleted before it.",
    ),
    ScopeEntry(CrimeEvidence, None, "Gathered crime evidence."),
    ScopeEntry(DenounceRecord, None, "Public denunciation records."),
    ScopeEntry(AccusationNullification, None, "Nullified/withdrawn accusations."),
    ScopeEntry(AccusationCrimeClaim, None, "Accusation crime claims."),
    ScopeEntry(HeatSource, None, "Per-source heat contributions."),
    ScopeEntry(PersonaHeat, None, "Per-persona-per-area heat totals."),
    ScopeEntry(DeedCrimeTag, None, "Crime tags on deeds."),
    ScopeEntry(LieLowState, None, "Active lying-low states."),
    ScopeEntry(PardonGrant, None, "Pardon grants."),
    ScopeEntry(GuardEncounter, None, "Guard-encounter records."),
    ScopeEntry(JusticeCase, None, "The justice cases themselves."),
    # --- Secrets (explicit spec scope): wholesale on Secret cascades every child row
    # (SecretVictim/Grievance/Knowledge/Gossip/Leverage/AccusationRebuttal are all CASCADE
    # off Secret). No CG-vs-play split exists on Secret.provenance (SecretProvenance is a
    # canonicity spectrum, not an acquisition-time discriminator — see the module docstring
    # of world.secrets.constants.SecretProvenance) — every Secret row is play-state. ---
    ScopeEntry(Secret, None, "Every secret and its cascading child rows."),
    # --- NPC standing (explicit spec scope) ---
    ScopeEntry(NPCStanding, None, "Per-(PC persona, NPC persona) disposition rows."),
    # --- Economy ledgers (explicit spec scope: "currency contracts/debts" are IN scope) ---
    ScopeEntry(CurrencyTransfer, None, "Money-movement audit trail."),
    ScopeEntry(Contract, None, "Consent-gated economic agreements (ContractTerm cascades)."),
    ScopeEntry(DebtInstrument, None, "Standing org-to-org debts."),
    ScopeEntry(CharacterEmployment, None, "Character job assignments."),
    ScopeEntry(Business, None, "Persona-owned business ventures."),
    ScopeEntry(PurseDrainWeek, None, "Weekly distinction-purse-drain audit rows."),
    ScopeEntry(
        CharacterPurse, None, "Personal coin balances (lazily recreated at 0 on next access)."
    ),
    # --- Legend/renown ledgers (explicit spec scope) — LegendEntry cascades LegendSpread/
    # LegendDeedStory/PersonaDeedKnowledge/CovenantLegendCredit; refresh_legend_views() is
    # called once, after the whole wipe, by wipe_pristine_world() itself. ---
    ScopeEntry(LegendEntry, None, "Per-persona deed ledger (cascades its detail rows)."),
    ScopeEntry(LegendEvent, None, "Legend-spreading event records."),
]


@dataclass(frozen=True)
class ScopeCount:
    """One model's row count for a dry-run or post-execute report."""

    label: str
    would_delete: int


@dataclass(frozen=True)
class WipeReport:
    """The result of a ``wipe_pristine_world`` call, dry-run or real."""

    executed: bool
    counts: list[ScopeCount]

    @property
    def total(self) -> int:
        return sum(c.would_delete for c in self.counts)


def _scope_queryset(entry: ScopeEntry):
    qs = entry.model.objects.all()
    if entry.filter_kwargs:
        qs = qs.filter(**entry.filter_kwargs)
    return qs


def preview_pristine_world_wipe() -> WipeReport:
    """Dry-run: count what ``wipe_pristine_world(execute=True)`` would delete.

    Read-only. Never called with any guard checks — a dry-run is always safe to run,
    which is exactly why it's the command's default behavior.
    """
    counts = [
        ScopeCount(entry.model.__name__, _scope_queryset(entry).count()) for entry in SCOPE_TABLE
    ]
    return WipeReport(executed=False, counts=counts)


def check_beta_reset_enabled() -> None:
    """Guard 1: the hardcoded constant. Raises ``BetaResetDisabledError`` if flipped off."""
    if not BETA_RESET_ENABLED:
        raise BetaResetDisabledError


def check_release_latch() -> None:
    """Guard 2: the one-way DB latch. Raises ``ReleaseLatchedError`` if any row exists."""
    if ReleaseLatch.objects.exists():
        raise ReleaseLatchedError


def check_confirmation_phrase(typed: str | None) -> None:
    """Guard 3: the typed confirmation phrase must match exactly.

    ``typed=None`` (never supplied — the non-TTY-safe default) is always a mismatch.
    """
    if typed != CONFIRMATION_PHRASE:
        raise ConfirmationPhraseMismatchError


def check_backup_verified(
    backup_verified_at: datetime | None, *, now: datetime | None = None
) -> None:
    """Guard 4: the operator asserts a backup was verified recently.

    This function does not (and cannot) confirm a backup actually happened — it only
    enforces the operator supplied a plausible, fresh timestamp. See the module
    docstring for what the operator must have actually done first.
    """
    if backup_verified_at is None:
        raise BackupNotVerifiedError
    now = now or timezone.now()
    if backup_verified_at > now:
        future_msg = "--backup-verified-at is in the future. Nothing was touched."
        raise BackupNotVerifiedError(future_msg)
    if now - backup_verified_at > BACKUP_FRESHNESS_WINDOW:
        stale_msg = (
            f"--backup-verified-at is older than {BACKUP_FRESHNESS_WINDOW}. Re-verify the "
            "backup and try again. Nothing was touched."
        )
        raise BackupNotVerifiedError(stale_msg)


def wipe_pristine_world(
    *,
    execute: bool = False,
    confirm: str | None = None,
    backup_verified_at: datetime | None = None,
) -> WipeReport:
    """Dry-run (default) or execute the guarded beta-reset wipe.

    ``execute=False`` (the default) is always safe: it only counts rows, via
    ``preview_pristine_world_wipe()``, and none of the four guards below run.

    ``execute=True`` runs every guard, in order, before touching a single row:
    ``BETA_RESET_ENABLED`` → ``ReleaseLatch`` → confirmation phrase → verified-backup
    freshness. Any guard failure raises and changes nothing. Only once all four pass does
    the delete run, in one transaction, in ``SCOPE_TABLE`` order, followed by
    ``refresh_legend_views()``.

    This function assumes the server is quiesced (no concurrent writers) — see the
    management command's ``--help`` text for the operational assumption. No cache-flush
    machinery is built here; SharedMemoryModel's own invalidation on ``.delete()`` is
    trusted, per the ``sharedmemory-model`` skill.
    """
    if not execute:
        return preview_pristine_world_wipe()

    check_beta_reset_enabled()
    check_release_latch()
    check_confirmation_phrase(confirm)
    check_backup_verified(backup_verified_at)

    counts: list[ScopeCount] = []
    with transaction.atomic():
        for entry in SCOPE_TABLE:
            qs = _scope_queryset(entry)
            deleted, _ = qs.delete()
            counts.append(ScopeCount(entry.model.__name__, deleted))
        refresh_legend_views()

    return WipeReport(executed=True, counts=counts)


def mark_released(*, released_by: AccountDB, note: str = "") -> ReleaseLatch:
    """Write the one-way ``ReleaseLatch`` row. Refuses if one already exists.

    This is the belt-and-suspenders guard's write side — call it once, at the real
    cutover, separately from (before or after, doesn't matter) flipping
    ``BETA_RESET_ENABLED`` to False in code. There is no "unmark" function.
    """
    if ReleaseLatch.objects.exists():
        raise AlreadyReleasedError
    return ReleaseLatch.objects.create(released_by=released_by, note=note)
