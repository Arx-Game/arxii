"""Spec C — resonance gain services.

Accessor reference (verified 2026-04-23 during implementation):

- CharacterSheet → primary Persona:
    `sheet.primary_persona` — @cached_property on CharacterSheet
    (character_sheets/models.py:273-283); raises Persona.DoesNotExist if the
    PRIMARY invariant is violated; never returns None.
    Underlying query: self.personas.get(persona_type=PersonaType.PRIMARY)

- CharacterSheet → Account (current):
    No direct FK. Traversal chain:
      sheet.roster_entry          (RosterEntry OneToOne, related_name="roster_entry",
                                   roster/models/roster_core.py:70)
      → .tenures.filter(end_date__isnull=True)
                                  (RosterTenure FK to RosterEntry, related_name="tenures",
                                   roster/models/tenures.py:30-33; is_current ↔ end_date is None,
                                   tenures.py:115-117)
      → .player_data              (RosterTenure.player_data FK to PlayerData,
                                   related_name="tenures", tenures.py:25-28)
      → .account                  (PlayerData.account OneToOne to AccountDB,
                                   evennia_extensions/models.py:38-43)
    Full path: sheet.roster_entry.tenures.get(end_date__isnull=True).player_data.account
    Helper: PlayerData.cached_active_tenures uses is_current (end_date is None)
    and PlayerData.get_available_characters() walks the same chain
    (evennia_extensions/models.py:98-116).

- SceneParticipation predicate:
    SceneParticipation FKs to AccountDB (field: `account`, related_name="scene_participations",
    scenes/models.py:155-158). Unique together: ["scene", "account"].
    "Was this account a participant in scene X":
      SceneParticipation.objects.filter(scene=scene, account=account).exists()
    Note: participates at the Account level, NOT at the Persona or CharacterSheet level.

- InteractionReceiver FK target:
    InteractionReceiver.persona FK → scenes.Persona (related_name="interactions_received",
    scenes/place_models.py:96-100). Target is a Persona, not an Account or CharacterSheet.
    Query: InteractionReceiver.objects.filter(persona=persona, interaction__scene=scene)

- AccountDB → current CharacterSheet(s):
    No single-call helper exists. Reverse traversal:
      account.player_data         (PlayerData OneToOne reverse, evennia_extensions/models.py:38-43)
      → .cached_active_tenures    (@property, returns list of RosterTenure where end_date is None,
                                   evennia_extensions/models.py:98-101; requires
                                   prefetch_related("tenures") upstream)
      → tenure.roster_entry.character_sheet
                                  (RosterEntry.character_sheet OneToOne,
                                   roster/models/roster_core.py:70-74)
    ORM equivalent (no prefetch):
      CharacterSheet.objects.filter(
          roster_entry__tenures__player_data__account=account,
          roster_entry__tenures__end_date__isnull=True,
      )
    PlayerData.get_available_characters() (evennia_extensions/models.py:103-109)
    walks this chain but returns ObjectDB characters, not CharacterSheets — caller
    must step to .item_data.sheet or use the ORM query above for sheets directly.
"""

from __future__ import annotations

import math

from django.db import transaction
from django.utils import timezone
from evennia.accounts.models import AccountDB

from evennia_extensions.models import RoomProfile
from world.character_sheets.models import CharacterSheet
from world.magic.exceptions import EndorsementValidationError
from world.magic.models import (
    CharacterResonance,
    PoseEndorsement,
    Resonance,
    ResonanceGainConfig,
    RoomAuraProfile,
    RoomResonance,
    SceneEntryEndorsement,
)
from world.magic.types import (
    ResonanceDailyTickSummary,
    ResonanceWeeklySettlementSummary,
    SettlementResult,
)
from world.scenes.constants import InteractionMode, InteractionVisibility
from world.scenes.models import Interaction, Persona, Scene, SceneParticipation
from world.scenes.place_models import InteractionReceiver


def account_for_sheet(sheet: CharacterSheet) -> AccountDB | None:
    """Resolve a CharacterSheet to the Account currently playing it.

    Walks CharacterSheet → RosterEntry → current RosterTenure → PlayerData → Account.
    Returns None if the sheet has no RosterEntry or no current tenure (between
    players, retired, NPC). Alt-guard comparisons that receive None should
    treat it as "no alt relationship proven" — fail-open at the sheet layer.
    """
    try:
        roster_entry = sheet.roster_entry
    except CharacterSheet.roster_entry.RelatedObjectDoesNotExist:
        return None
    current_tenure = roster_entry.tenures.filter(end_date__isnull=True).first()
    if current_tenure is None:
        return None
    player_data = current_tenure.player_data
    if player_data is None:
        return None
    return player_data.account


def get_resonance_gain_config() -> ResonanceGainConfig:
    """Get-or-create the resonance gain config singleton (pk=1)."""
    with transaction.atomic():
        cfg, _ = ResonanceGainConfig.objects.get_or_create(pk=1)
        return cfg


@transaction.atomic
def tag_room_resonance(
    room_profile: RoomProfile,
    resonance: Resonance,
    set_by: AccountDB | None = None,
) -> RoomResonance:
    """Tag a room with a resonance. Lazy-creates RoomAuraProfile if missing.

    Idempotent — returns the existing row unchanged if already tagged.
    """
    aura, _ = RoomAuraProfile.objects.get_or_create(room_profile=room_profile)
    tag, _ = RoomResonance.objects.get_or_create(
        room_aura_profile=aura,
        resonance=resonance,
        defaults={"set_by": set_by},
    )
    return tag


@transaction.atomic
def untag_room_resonance(
    room_profile: RoomProfile,
    resonance: Resonance,
) -> None:
    """Remove a resonance tag. No-op if absent."""
    aura = getattr(room_profile, "room_aura_profile", None)  # noqa: GETATTR_LITERAL — OneToOne reverse accessor, raises RelatedObjectDoesNotExist if missing
    if aura is None:
        return
    RoomResonance.objects.filter(
        room_aura_profile=aura,
        resonance=resonance,
    ).delete()


@transaction.atomic
def set_residence(
    sheet: CharacterSheet,
    room_profile: RoomProfile | None,
) -> None:
    """Set or clear a character's current residence."""
    sheet.current_residence = room_profile
    sheet.save(update_fields=["current_residence"])


def get_residence_resonances(sheet: CharacterSheet) -> set[Resonance]:
    """Return the set of resonances granting trickle for this character.

    Computes: (sheet.current_residence → RoomAuraProfile → tags)
              ∩ (sheet.character_resonances — claimed set).
    """
    rp = sheet.current_residence
    if rp is None:
        return set()
    aura = getattr(rp, "room_aura_profile", None)  # noqa: GETATTR_LITERAL — OneToOne reverse accessor, raises RelatedObjectDoesNotExist if missing
    if aura is None:
        return set()
    tagged_ids = set(
        RoomResonance.objects.filter(room_aura_profile=aura).values_list("resonance_id", flat=True)
    )
    claimed_ids = set(sheet.resonances.values_list("resonance_id", flat=True))
    matched_ids = tagged_ids & claimed_ids
    return set(Resonance.objects.filter(pk__in=matched_ids))


@transaction.atomic
def create_pose_endorsement(
    endorser_sheet: CharacterSheet,
    interaction: Interaction,
    resonance: Resonance,
) -> PoseEndorsement:
    """Validate and persist a pose endorsement (Spec C §2.2 + §7).

    Preconditions (raises EndorsementValidationError on failure):
    1. Interaction author (persona field) has a character sheet
    2. Endorser != endorsee (no self-endorsement)
    3. Endorser's account != endorsee's account (no alt-endorsement)
    4. Interaction is not a whisper
    5. Interaction is not VERY_PRIVATE
    6. Endorser was present (scene participation OR interaction receiver)
    7. Endorsee has claimed this resonance
    8. No duplicate (endorser × interaction already endorsed)
    """
    endorsee_persona = interaction.persona
    if endorsee_persona is None:
        msg = "Interaction has no author persona"
        raise EndorsementValidationError(msg)
    endorsee_sheet = endorsee_persona.character_sheet
    if endorsee_sheet is None:
        msg = "Interaction author has no character sheet"
        raise EndorsementValidationError(msg)

    if endorser_sheet == endorsee_sheet:
        msg = "Cannot endorse your own pose"
        raise EndorsementValidationError(msg)

    endorser_account = account_for_sheet(endorser_sheet)
    endorsee_account = account_for_sheet(endorsee_sheet)
    if (
        endorser_account is not None
        and endorsee_account is not None
        and endorser_account == endorsee_account
    ):
        msg = "Cannot endorse an alt character"
        raise EndorsementValidationError(msg)

    if interaction.mode == InteractionMode.WHISPER:
        msg = "Whispers cannot be endorsed"
        raise EndorsementValidationError(msg)

    if interaction.visibility == InteractionVisibility.VERY_PRIVATE:
        msg = "Very-private interactions cannot be endorsed"
        raise EndorsementValidationError(msg)

    if not _endorser_was_present(endorser_sheet, endorser_account, interaction):
        msg = "Endorser was not present for this interaction"
        raise EndorsementValidationError(msg)

    if not CharacterResonance.objects.filter(
        character_sheet=endorsee_sheet, resonance=resonance
    ).exists():
        msg = "Endorsee has not claimed this resonance"
        raise EndorsementValidationError(msg)

    existing = PoseEndorsement.objects.filter(
        endorser_sheet=endorser_sheet, interaction=interaction
    ).first()
    if existing is not None:
        msg = "Already endorsed this pose"
        raise EndorsementValidationError(msg)

    return PoseEndorsement.objects.create(
        endorser_sheet=endorser_sheet,
        endorsee_sheet=endorsee_sheet,
        interaction=interaction,
        timestamp=interaction.timestamp,
        resonance=resonance,
        persona_snapshot=endorsee_persona,
    )


def _endorser_was_present(
    endorser_sheet: CharacterSheet,
    endorser_account: AccountDB | None,
    interaction: Interaction,
) -> bool:
    """True if the endorser participated in the scene or received the interaction.

    - Scene RP: SceneParticipation row for (scene, account).
    - Organic grid RP (no scene): InteractionReceiver row for (interaction, persona).
    """
    scene = interaction.scene
    if scene is not None:
        if endorser_account is None:
            return False
        return SceneParticipation.objects.filter(scene=scene, account=endorser_account).exists()
    # Organic grid RP — check receivers. Need endorser's primary Persona.
    try:
        endorser_persona = endorser_sheet.primary_persona
    except Persona.DoesNotExist:
        return False
    return InteractionReceiver.objects.filter(
        interaction=interaction, persona=endorser_persona
    ).exists()


@transaction.atomic
def settle_weekly_pot(endorser_sheet: CharacterSheet) -> SettlementResult:
    """Settle all unsettled PoseEndorsement rows for one endorser.

    Distributes the weekly pot across the endorser's unsettled endorsements
    using ceiling division, writes grants via grant_resonance (ledger rows
    auto-written), and marks each endorsement settled_at=now.

    Idempotent — a second call with no new unsettled rows is a no-op.
    """
    # Inner import to avoid circular with services/resonance.py
    from world.magic.constants import GainSource  # noqa: PLC0415
    from world.magic.services.resonance import grant_resonance  # noqa: PLC0415

    unsettled = list(
        PoseEndorsement.objects.select_for_update().filter(
            endorser_sheet=endorser_sheet, settled_at__isnull=True
        )
    )
    if not unsettled:
        return SettlementResult(
            endorser_sheet=endorser_sheet,
            endorsements_settled=0,
            total_granted=0,
        )

    cfg = get_resonance_gain_config()
    n = len(unsettled)
    share = math.ceil(cfg.weekly_pot_per_character / n)
    now = timezone.now()
    total_granted = 0

    for endorsement in unsettled:
        grant_resonance(
            endorsement.endorsee_sheet,
            endorsement.resonance,
            share,
            source=GainSource.POSE_ENDORSEMENT,
            pose_endorsement=endorsement,
        )
        endorsement.granted_amount = share
        endorsement.settled_at = now
        endorsement.save(update_fields=["granted_amount", "settled_at"])
        total_granted += share

    return SettlementResult(
        endorser_sheet=endorser_sheet,
        endorsements_settled=n,
        total_granted=total_granted,
    )


@transaction.atomic
def create_scene_entry_endorsement(
    endorser_sheet: CharacterSheet,
    endorsee_sheet: CharacterSheet,
    scene: Scene,
    resonance: Resonance,
) -> SceneEntryEndorsement:
    """Validate, persist, and fire scene-entry grant in one transaction (Spec C §2.3, §7)."""
    from world.magic.constants import GainSource  # noqa: PLC0415
    from world.magic.services.resonance import grant_resonance  # noqa: PLC0415
    from world.scenes.constants import PoseKind  # noqa: PLC0415

    if endorser_sheet == endorsee_sheet:
        msg = "Cannot endorse your own entry"
        raise EndorsementValidationError(msg)

    endorser_account = account_for_sheet(endorser_sheet)
    endorsee_account = account_for_sheet(endorsee_sheet)
    if (
        endorser_account is not None
        and endorsee_account is not None
        and endorser_account == endorsee_account
    ):
        msg = "Cannot endorse an alt character"
        raise EndorsementValidationError(msg)

    if endorser_account is None:
        msg = "Endorser has no current account"
        raise EndorsementValidationError(msg)
    if not SceneParticipation.objects.filter(scene=scene, account=endorser_account).exists():
        msg = "Endorser never participated in this scene"
        raise EndorsementValidationError(msg)

    if not CharacterResonance.objects.filter(
        character_sheet=endorsee_sheet, resonance=resonance
    ).exists():
        msg = "Endorsee has not claimed this resonance"
        raise EndorsementValidationError(msg)

    # Find the endorsee's entry pose in this scene.
    # Interaction.persona FK → Persona; Persona.character_sheet FK → CharacterSheet
    entry_interaction = (
        Interaction.objects.filter(
            scene=scene,
            persona__character_sheet=endorsee_sheet,
            pose_kind=PoseKind.ENTRY,
        )
        .order_by("timestamp")
        .first()
    )
    if entry_interaction is None:
        msg = "Endorsee has no entry pose in this scene"
        raise EndorsementValidationError(msg)

    if SceneEntryEndorsement.objects.filter(
        endorser_sheet=endorser_sheet,
        endorsee_sheet=endorsee_sheet,
        scene=scene,
    ).exists():
        msg = "Already endorsed this entry"
        raise EndorsementValidationError(msg)

    cfg = get_resonance_gain_config()
    endorsement = SceneEntryEndorsement.objects.create(
        endorser_sheet=endorser_sheet,
        endorsee_sheet=endorsee_sheet,
        scene=scene,
        entry_interaction=entry_interaction,
        entry_interaction_timestamp=entry_interaction.timestamp,
        resonance=resonance,
        persona_snapshot=entry_interaction.persona,
        granted_amount=cfg.scene_entry_grant,
    )
    grant_resonance(
        endorsee_sheet,
        resonance,
        cfg.scene_entry_grant,
        source=GainSource.SCENE_ENTRY,
        scene_entry_endorsement=endorsement,
    )
    return endorsement


def residence_trickle_tick() -> ResonanceDailyTickSummary:
    """Daily residence-trickle tick (Spec C §5.3).

    Iterates sheets with a declared residence; for each matching
    (residence-tagged ∩ sheet-claimed) resonance, fires a single
    grant_resonance call worth cfg.residence_daily_trickle_per_resonance.

    Per-character grants are wrapped in nested atomic blocks so a single
    failure doesn't poison the whole tick. Non-residence sheets are skipped.
    """
    from world.magic.constants import GainSource  # noqa: PLC0415
    from world.magic.services.resonance import grant_resonance  # noqa: PLC0415

    cfg = get_resonance_gain_config()
    grants_issued = 0
    sheets_processed = 0

    sheets_with_residence = CharacterSheet.objects.exclude(current_residence__isnull=True)

    for sheet in sheets_with_residence.iterator():
        sheets_processed += 1
        matched = get_residence_resonances(sheet)
        rp = sheet.current_residence
        aura = getattr(rp, "room_aura_profile", None)  # noqa: GETATTR_LITERAL — OneToOne reverse accessor, raises RelatedObjectDoesNotExist if missing
        if aura is None or not matched:
            continue

        for resonance in matched:
            try:
                with transaction.atomic():
                    grant_resonance(
                        sheet,
                        resonance,
                        cfg.residence_daily_trickle_per_resonance,
                        source=GainSource.ROOM_RESIDENCE,
                        room_aura_profile=aura,
                    )
                    grants_issued += 1
            except Exception:  # noqa: BLE001, S112 — log + continue to avoid tick poison
                # TODO: structured log via Evennia logger.
                continue

    return ResonanceDailyTickSummary(
        residence_grants_issued=grants_issued,
        sheets_processed=sheets_processed,
    )


def get_outfit_resonance_contributions(
    sheet: CharacterSheet,  # noqa: ARG001
) -> list[tuple[Resonance, int]]:
    """Stub — empty until Items app ships (Spec C §5.4).

    Placeholder argument preserves the future signature when the Items app ships.
    When Items lands, returns a list of (resonance, per_item_count) tuples
    aggregated across the character's worn item instances.
    """
    return []


def outfit_trickle_tick() -> int:
    """Outfit trickle tick. Currently a no-op (Items app not yet present).

    Returns: count of grants issued (always 0 at launch).
    """
    # When Items lands, iterate sheets × worn items × resonance tags, grant
    # per-item. Guarded so nothing is granted with OUTFIT_ITEM source value
    # before the source_item_instance FK exists in the schema.
    return 0


def resonance_daily_tick() -> ResonanceDailyTickSummary:
    """Master daily tick (Spec C §5). Runs residence + outfit trickle."""
    residence_summary = residence_trickle_tick()
    _outfit_grants = outfit_trickle_tick()  # always 0 at launch
    return ResonanceDailyTickSummary(
        residence_grants_issued=residence_summary.residence_grants_issued,
        outfit_grants_issued=0,
        sheets_processed=residence_summary.sheets_processed,
    )


def resonance_weekly_settlement_tick() -> ResonanceWeeklySettlementSummary:
    """Master weekly settlement tick (Spec C §5).

    Finds all endorsers with any unsettled PoseEndorsement rows, calls
    settle_weekly_pot on each. Per-endorser settlement wrapped in try/except
    so a single failure doesn't poison the whole tick.
    """
    endorser_ids = (
        PoseEndorsement.objects.filter(settled_at__isnull=True)
        .values_list("endorser_sheet_id", flat=True)
        .distinct()
    )
    endorsers_settled = 0
    total_endorsements = 0
    total_granted = 0

    for sheet_id in endorser_ids:
        sheet = CharacterSheet.objects.get(pk=sheet_id)
        try:
            result = settle_weekly_pot(sheet)
        except Exception:  # noqa: BLE001, S112 — isolate per-endorser failures so one bad row doesn't poison the tick
            continue
        if result.endorsements_settled:
            endorsers_settled += 1
            total_endorsements += result.endorsements_settled
            total_granted += result.total_granted

    return ResonanceWeeklySettlementSummary(
        endorsers_settled=endorsers_settled,
        total_endorsements_settled=total_endorsements,
        total_granted=total_granted,
    )
