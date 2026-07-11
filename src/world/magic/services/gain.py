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

from decimal import Decimal
import math
from typing import TYPE_CHECKING

from django.db import transaction

if TYPE_CHECKING:
    from world.items.models import Style
    from world.magic.models.dramatic_moment import (
        DramaticMomentSuggestion,
        DramaticMomentTag,
        DramaticMomentType,
    )
    from world.magic.models.endorsement import EntryFlourishRecord, StylePresentationEndorsement
from django.utils import timezone
from evennia.accounts.models import AccountDB

from evennia_extensions.models import RoomProfile
from world.character_sheets.models import CharacterSheet
from world.locations.constants import RESONANCE_DEFAULT_MAGNITUDE, KeyType, LocationParentType
from world.locations.models import LocationValueModifier
from world.magic.exceptions import EndorsementValidationError
from world.magic.models import (
    CharacterResonance,
    PoseEndorsement,
    Resonance,
    ResonanceGainConfig,
    ResonanceGrant,
    SceneEntryEndorsement,
)
from world.magic.types import (
    ResonanceDailyTickSummary,
    ResonanceWeeklySettlementSummary,
    SettlementResult,
)
from world.scenes.constants import InteractionMode, InteractionVisibility, ScenePrivacyMode
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
        cfg = ResonanceGainConfig.objects.cached_singleton()
    if cfg is None:
        cfg, _ = ResonanceGainConfig.objects.get_or_create(pk=1)
    return cfg


ROOM_RESONANCE_TAG_SOURCE = "tag_room_resonance"
_ERR_ALT_ENDORSE = "Cannot endorse an alt character"
_ERR_RESONANCE_UNCLAIMED = "Endorsee has not claimed this resonance"


@transaction.atomic
def tag_room_resonance(
    room_profile: RoomProfile,
    resonance: Resonance,
    set_by: AccountDB | None = None,  # noqa: ARG001
) -> LocationValueModifier:
    """Tag a room with a resonance by creating a cascade modifier row.

    Idempotent — returns the existing row (matched by room_profile +
    resonance + source) if already tagged. The row uses
    ``RESONANCE_DEFAULT_MAGNITUDE`` as its value and ``change_per_day=0``
    (permanent). Staff can re-tune the magnitude via direct cascade-row edits.

    Distinct from staff-authored stacking modifiers because the lookup
    matches on ``source=ROOM_RESONANCE_TAG_SOURCE`` — multiple unrelated
    modifier rows on the same (room, resonance) can coexist with different
    sources.
    """
    row, _ = LocationValueModifier.objects.update_or_create(
        parent_type=LocationParentType.ROOM,
        room_profile=room_profile,
        key_type=KeyType.RESONANCE,
        resonance=resonance,
        source=ROOM_RESONANCE_TAG_SOURCE,
        defaults={
            "stat_key": "",
            "value": RESONANCE_DEFAULT_MAGNITUDE,
            "change_per_day": 0,
        },
    )
    return row


@transaction.atomic
def untag_room_resonance(
    room_profile: RoomProfile,
    resonance: Resonance,
) -> None:
    """Remove the tag cascade row for this (room, resonance). No-op if absent.

    Only removes rows whose ``source=ROOM_RESONANCE_TAG_SOURCE``. Other
    stacking modifiers on the same (room, resonance) with different sources
    are left alone.
    """
    LocationValueModifier.objects.filter(
        parent_type=LocationParentType.ROOM,
        room_profile=room_profile,
        key_type=KeyType.RESONANCE,
        resonance=resonance,
        source=ROOM_RESONANCE_TAG_SOURCE,
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

    Computes: (resonances with a positive room-level cascade row on
              sheet.current_residence) ∩ (sheet.character_resonances —
              claimed set).

    Uses a direct cascade-row query (NOT effective_value's full cascade
    walk) — the trickle gate cares about what the room itself emits,
    not values inherited from parent areas. Single query for the room's
    rows; the cascade-resolved magnitude is not needed for this gate.
    """
    rp = sheet.current_residence
    if rp is None:
        return set()
    tagged_ids = set(
        LocationValueModifier.objects.filter(
            parent_type=LocationParentType.ROOM,
            room_profile=rp,
            key_type=KeyType.RESONANCE,
            value__gt=0,
        ).values_list("resonance_id", flat=True)
    )
    claimed_ids = set(sheet.resonances.values_list("resonance_id", flat=True))
    matched_ids = tagged_ids & claimed_ids
    return set(Resonance.objects.filter(pk__in=matched_ids))


def resonance_grant_history_for_sheet(
    sheet: CharacterSheet,
    *,
    resonance: Resonance | None = None,
    limit: int = 10,
) -> list[ResonanceGrant]:
    """Return this character's most recent ``ResonanceGrant`` rows, newest first.

    Mirrors ``ResonanceGrantViewSet``'s ordering (``-granted_at``) and user-scoping
    shape (`world/magic/views.py`) — the single read path for both the web audit
    ledger and the telnet ``resonance history`` command. Optionally narrowed to one
    claimed resonance.
    """
    qs = ResonanceGrant.objects.filter(character_sheet=sheet).select_related("resonance")
    if resonance is not None:
        qs = qs.filter(resonance=resonance)
    return list(qs.order_by("-granted_at")[:limit])


@transaction.atomic
def create_pose_endorsement(  # noqa: C901
    endorser_sheet: CharacterSheet,
    interaction: Interaction,
    resonance: Resonance,
) -> PoseEndorsement:
    """Validate and persist a pose endorsement (Spec C §2.2 + §7).

    Preconditions (raises EndorsementValidationError on failure):
    1. Interaction author (persona field) has a character sheet
    2. Endorser != endorsee (no self-endorsement)
    3. Endorser's account != endorsee's account (no alt-endorsement)
    4. WHISPER: endorser must be the direct recipient (InteractionReceiver row)
    5. VERY_PRIVATE: endorser must have SceneParticipation (allowed by participants)
    6. Endorser was present (scene participation OR interaction receiver)
    7. Endorsee has claimed this resonance
    8. No duplicate (endorser × interaction already endorsed)
    """
    if endorser_sheet.is_protagonism_locked:
        msg = "Endorser is locked from protagonism and cannot endorse poses"
        raise EndorsementValidationError(msg)

    endorsee_persona = interaction.persona
    if endorsee_persona is None:
        msg = "Interaction has no author persona"
        raise EndorsementValidationError(msg)
    endorsee_sheet = endorsee_persona.character_sheet
    if endorsee_sheet is None:
        msg = "Interaction author has no character sheet"
        raise EndorsementValidationError(msg)

    if endorsee_sheet.is_protagonism_locked:
        msg = "Endorsee is locked from protagonism and cannot receive endorsements"
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
        msg = _ERR_ALT_ENDORSE
        raise EndorsementValidationError(msg)

    if interaction.mode == InteractionMode.WHISPER:
        # Whispers may only be endorsed by the direct recipient
        if (
            endorser_account is None
            or not InteractionReceiver.objects.filter(
                interaction=interaction,
                account=endorser_account,
            ).exists()
        ):
            msg = "Whispers can only be endorsed by the recipient"
            raise EndorsementValidationError(msg)
    elif not _endorser_was_present(endorser_sheet, endorser_account, interaction):
        # VERY_PRIVATE and standard poses both gate on scene participation
        msg = "Endorser was not present for this interaction"
        raise EndorsementValidationError(msg)

    if not CharacterResonance.objects.filter(
        character_sheet=endorsee_sheet, resonance=resonance
    ).exists():
        msg = _ERR_RESONANCE_UNCLAIMED
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


def get_endorseable_poses_in_scene(
    endorser_sheet: CharacterSheet,
    endorsee_sheet: CharacterSheet,
    scene: Scene,
) -> list[tuple[int, Interaction]]:
    """Return (1-based absolute position, Interaction) pairs visible to the endorser.

    Only POSE and WHISPER interactions are returned — SAY and EMIT interactions
    are not endorseable as poses.

    Position numbering is stable across all of the endorsee's POSE and WHISPER
    interactions in the scene (including invisible ones), so a pose's number never
    shifts when private poses exist earlier in the timeline.

    Visibility rules:
    - WHISPER: only visible if the endorser has an InteractionReceiver row.
    - VERY_PRIVATE: only visible if the endorser has SceneParticipation.
    - All other: visible (endorser is in the scene).
    """
    endorser_account = account_for_sheet(endorser_sheet)

    is_participant = (
        endorser_account is not None
        and SceneParticipation.objects.filter(scene=scene, account=endorser_account).exists()
    )

    all_interactions = list(
        Interaction.objects.filter(
            scene=scene,
            persona__character_sheet=endorsee_sheet,
            mode__in=[InteractionMode.POSE, InteractionMode.WHISPER],
        )
        .select_related("persona")
        .order_by("timestamp", "pk")
    )

    # Batch-fetch the whisper PKs the endorser received to avoid per-row queries
    whisper_pks = {iact.pk for iact in all_interactions if iact.mode == InteractionMode.WHISPER}
    received_whisper_pks: set[int] = set()
    if whisper_pks and endorser_account is not None:
        received_whisper_pks = set(
            InteractionReceiver.objects.filter(
                interaction_id__in=whisper_pks,
                account=endorser_account,
            ).values_list("interaction_id", flat=True)
        )

    result: list[tuple[int, Interaction]] = []
    for idx, interaction in enumerate(all_interactions, start=1):
        if interaction.mode == InteractionMode.WHISPER:
            if interaction.pk not in received_whisper_pks:
                continue
        elif interaction.visibility == InteractionVisibility.VERY_PRIVATE:
            if not is_participant:
                continue
        result.append((idx, interaction))

    return result


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
        if endorsement.endorsee_sheet.is_protagonism_locked:
            # Endorsee is subsumed — skip resonance grant for this tick.
            endorsement.granted_amount = 0
            endorsement.settled_at = now
            endorsement.save(update_fields=["granted_amount", "settled_at"])
            continue
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

    if endorser_sheet.is_protagonism_locked:
        msg = "Endorser is locked from protagonism and cannot endorse scene entries"
        raise EndorsementValidationError(msg)
    if endorsee_sheet.is_protagonism_locked:
        msg = "Endorsee is locked from protagonism and cannot receive scene-entry endorsements"
        raise EndorsementValidationError(msg)

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
        msg = _ERR_ALT_ENDORSE
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
        msg = _ERR_RESONANCE_UNCLAIMED
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


def _endorser_can_see_scene(
    endorser_account: AccountDB | None,
    scene: Scene,
) -> bool:
    """True if the endorser's account has read access to the scene log.

    Awareness gate for style-presentation endorsements (broader than co-presence):
    - PUBLIC scene: any account (including non-participants) can read the log.
    - PRIVATE / EPHEMERAL scene: only current scene participants.
    - No account (untenured sheet): cannot see non-public scenes.
    """
    if scene.privacy_mode == ScenePrivacyMode.PUBLIC:
        return True
    if endorser_account is None:
        return False
    return SceneParticipation.objects.filter(scene=scene, account=endorser_account).exists()


def _endorsee_worn_bound_styles(
    endorsee_sheet: CharacterSheet,
    resonance: Resonance,
) -> list[Style]:
    """Every worn ``Style`` bound to ``resonance`` via the endorsee's Motif.

    Mirrors the ``passive_motif_style_bonuses`` walker logic in
    ``world/mechanics/services.py``: motif → resonances.get(resonance=resonance)
    → style_assignments.all() → binding.style → equipped_items.item_styles_for.
    Returns [] if there is no binding or no matching worn style.
    """
    from world.magic.models.motifs import Motif, MotifResonance  # noqa: PLC0415

    try:
        motif = endorsee_sheet.motif
    except Motif.DoesNotExist:
        return []

    try:
        mr = motif.resonances.get(resonance=resonance)
    except MotifResonance.DoesNotExist:
        return []

    char = endorsee_sheet.character
    if not hasattr(char, "equipped_items"):
        return []

    return [
        binding.style
        for binding in mr.style_assignments.all()
        if char.equipped_items.item_styles_for(binding.style)
    ]


@transaction.atomic
def create_style_presentation_endorsement(
    endorser_sheet: CharacterSheet,
    endorsee_sheet: CharacterSheet,
    scene: Scene,
    resonance: Resonance,
) -> StylePresentationEndorsement:
    """Validate, persist, and fire a style-presentation resonance grant (#1152).

    Awareness-gated (not co-presence-gated) sibling of
    ``create_scene_entry_endorsement``. The endorser must be able to read the
    scene log; the endorsee must be wearing an item whose Style is bound to
    ``resonance`` in their Motif. No entry-pose requirement.

    Preconditions (raises EndorsementValidationError on failure):
    1. Endorser not protagonism-locked.
    2. Endorsee not protagonism-locked.
    3. Endorser != endorsee (no self-endorsement).
    4. Endorser's account != endorsee's account (no alt-endorsement).
    5. Endorser can see the scene (SceneParticipation OR PUBLIC scene).
    6. Endorsee has claimed this resonance (CharacterResonance row exists).
    7. Endorsee currently wears an item bound to ``resonance`` via MotifResonanceStyle.
    8. No duplicate (endorser × endorsee × scene) row.

    The base grant (``cfg.style_presentation_grant``) is scaled by the
    ``AudacityTuning`` multiplier of the matched worn Style's audacity tier — when
    multiple worn items match the binding, the highest-audacity match wins (#2029).
    """
    from world.magic.constants import GainSource  # noqa: PLC0415
    from world.magic.models.endorsement import StylePresentationEndorsement  # noqa: PLC0415
    from world.magic.services.resonance import grant_resonance  # noqa: PLC0415

    if endorser_sheet.is_protagonism_locked:
        msg = "Endorser is locked from protagonism and cannot endorse style presentations"
        raise EndorsementValidationError(msg)
    if endorsee_sheet.is_protagonism_locked:
        msg = (
            "Endorsee is locked from protagonism and cannot receive style-presentation endorsements"
        )
        raise EndorsementValidationError(msg)

    if endorser_sheet == endorsee_sheet:
        msg = "Cannot endorse your own style presentation"
        raise EndorsementValidationError(msg)

    endorser_account = account_for_sheet(endorser_sheet)
    endorsee_account = account_for_sheet(endorsee_sheet)
    if (
        endorser_account is not None
        and endorsee_account is not None
        and endorser_account == endorsee_account
    ):
        msg = _ERR_ALT_ENDORSE
        raise EndorsementValidationError(msg)

    if not _endorser_can_see_scene(endorser_account, scene):
        msg = "Endorser cannot view this scene"
        raise EndorsementValidationError(msg)

    if not CharacterResonance.objects.filter(
        character_sheet=endorsee_sheet, resonance=resonance
    ).exists():
        msg = _ERR_RESONANCE_UNCLAIMED
        raise EndorsementValidationError(msg)

    matched_styles = _endorsee_worn_bound_styles(endorsee_sheet, resonance)
    if not matched_styles:
        msg = "Endorsee is not wearing an item bound to this resonance via their Motif"
        raise EndorsementValidationError(msg)

    if StylePresentationEndorsement.objects.filter(
        endorser_sheet=endorser_sheet,
        endorsee_sheet=endorsee_sheet,
        scene=scene,
    ).exists():
        msg = "Already endorsed this style presentation"
        raise EndorsementValidationError(msg)

    from world.items.services.styles import audacity_multiplier_for  # noqa: PLC0415

    # The endorsee may wear multiple items whose styles all bind to this resonance
    # (e.g. two style-tagged garments). Reward the boldest presented style — scale
    # the grant by the highest-audacity match rather than the first/only one (#2029).
    best_style = max(matched_styles, key=lambda s: s.audacity)
    multiplier = audacity_multiplier_for(best_style)

    cfg = get_resonance_gain_config()
    # Mirrors the truncating int() coercion `grant_resonance` itself uses when
    # scaling amounts (see the ACCELERATED_GAIN_SOURCES branch); granted_amount is a
    # PositiveIntegerField, so floor at 1 to guarantee a positive grant even at the
    # lowest (UNDERSTATED) tier.
    grant_amount = max(1, int(cfg.style_presentation_grant * multiplier))
    try:
        _persona_snapshot = endorsee_sheet.primary_persona
    except Persona.DoesNotExist:
        _persona_snapshot = None
    endorsement = StylePresentationEndorsement.objects.create(
        endorser_sheet=endorser_sheet,
        endorsee_sheet=endorsee_sheet,
        scene=scene,
        resonance=resonance,
        persona_snapshot=_persona_snapshot,
        granted_amount=grant_amount,
    )
    grant_resonance(
        endorsee_sheet,
        resonance,
        grant_amount,
        source=GainSource.STYLE_PRESENTATION,
        style_presentation_endorsement=endorsement,
    )
    return endorsement


@transaction.atomic
def create_entry_flourish(
    character_sheet: CharacterSheet,
    resonance: Resonance,
    *,
    scene: Scene | None,
    amount: int | None = None,
) -> EntryFlourishRecord:
    """Record a successful entry flourish and fire the resonance grant.

    Called after the Entrance social action resolves successfully. The resonance
    was declared by the player as their flourish's expression.

    Validates the character has claimed the resonance, then creates the
    EntryFlourishRecord and fires grant_resonance atomically.

    Args:
        character_sheet: The character performing the flourish.
        resonance: The resonance the character expressed during their entrance.
        scene: Scene context; None if outside a scene.
        amount: Override the config default; None uses entry_flourish_grant.

    Returns:
        The created EntryFlourishRecord.

    Raises:
        EndorsementValidationError: If the character hasn't claimed this resonance.
    """
    from world.magic.constants import GainSource  # noqa: PLC0415
    from world.magic.models.endorsement import EntryFlourishRecord  # noqa: PLC0415
    from world.magic.services.resonance import grant_resonance  # noqa: PLC0415

    if scene is not None:
        existing = EntryFlourishRecord.objects.filter(
            character_sheet=character_sheet, scene=scene
        ).first()
        if existing is not None:
            return existing  # already flourished this scene — skip gracefully

    if not CharacterResonance.objects.filter(
        character_sheet=character_sheet, resonance=resonance
    ).exists():
        msg = "Character has not claimed this resonance"
        raise EndorsementValidationError(msg)

    cfg = get_resonance_gain_config()
    granted = amount if amount is not None else cfg.entry_flourish_grant

    record = EntryFlourishRecord.objects.create(
        character_sheet=character_sheet,
        resonance=resonance,
        scene=scene,
        granted_amount=granted,
    )
    grant_resonance(
        character_sheet,
        resonance,
        granted,
        source=GainSource.ENTRY_FLOURISH,
        entry_flourish=record,
    )
    return record


@transaction.atomic
def create_dramatic_moment_tag(
    *,
    character_sheet: CharacterSheet,
    moment_type: DramaticMomentType,
    tagged_by: AccountDB,
    scene: Scene | None,
    interaction: Interaction | None = None,
) -> DramaticMomentTag:
    """Tag a character's dramatic scene moment and fire resonance + renown.

    Both the resonance grant and the renown award fire in one atomic transaction.
    If the character has no primary persona, the renown step is skipped — the
    resonance grant still fires. Fire_renown_award's best-effort notification
    runs outside the transaction by design (see fire_renown_award docstring).

    Raises:
        EndorsementValidationError: If the character hasn't claimed the resonance.
        DramaticMomentCapExceeded: If per_scene_cap for this (moment_type, scene, sheet) is reached.
    """
    from world.magic.constants import GainSource  # noqa: PLC0415
    from world.magic.exceptions import DramaticMomentCapExceeded  # noqa: PLC0415
    from world.magic.models.dramatic_moment import DramaticMomentTag  # noqa: PLC0415
    from world.magic.services.resonance import grant_resonance  # noqa: PLC0415

    if not CharacterResonance.objects.filter(
        character_sheet=character_sheet, resonance=moment_type.resonance
    ).exists():
        msg = "Character has not claimed this resonance"
        raise EndorsementValidationError(msg)

    existing = DramaticMomentTag.objects.filter(
        moment_type=moment_type,
        character_sheet=character_sheet,
        scene=scene,
    ).count()
    if existing >= moment_type.per_scene_cap:
        raise DramaticMomentCapExceeded(DramaticMomentCapExceeded.user_message)

    tag = DramaticMomentTag.objects.create(
        moment_type=moment_type,
        character_sheet=character_sheet,
        scene=scene,
        tagged_by=tagged_by,
        interaction=interaction,
        interaction_timestamp=interaction.timestamp if interaction is not None else None,
    )
    grant_resonance(
        character_sheet,
        moment_type.resonance,
        moment_type.resonance_amount,
        source=GainSource.DRAMATIC_MOMENT,
        dramatic_moment=tag,
    )

    try:
        persona = character_sheet.primary_persona
    except Persona.DoesNotExist:
        persona = None

    if persona is not None:
        from world.societies.renown import fire_renown_award  # noqa: PLC0415

        fire_renown_award(
            persona=persona,
            magnitude=moment_type.magnitude,
            risk=moment_type.risk,
            reach=moment_type.reach or None,
            archetypes=list(moment_type.archetypes.all()),
            origin_area=(
                scene.location.area
                if scene and hasattr(scene, "location") and scene.location
                else None
            ),
            title=moment_type.label,
        )

    return tag


def maybe_suggest_dramatic_moments(
    *,
    character_sheet: CharacterSheet,
    scene: Scene | None,
    success_level: int,
    interaction: Interaction | None = None,
) -> list[DramaticMomentSuggestion]:
    """Create PENDING GM suggestions for a high-success technique entrance (#2183).

    Bridges the technique-entrance deferral markers (Tasks 1-2) to the existing
    DramaticMomentTag machinery without auto-tagging: for every flagged
    DramaticMomentType whose threshold the success level clears, whose resonance the
    character has claimed, and whose per-scene cap isn't already spent on real tags,
    creates (idempotently) a PENDING DramaticMomentSuggestion for a GM to later
    confirm or dismiss via ``resolve_dramatic_moment_suggestion``.

    No-ops (returns []) when scene is None — a suggestion is scoped to a scene, same
    as the DramaticMomentTag per-scene cap it mirrors.
    """
    from world.magic.constants import SuggestionStatus  # noqa: PLC0415
    from world.magic.models.dramatic_moment import (  # noqa: PLC0415
        DramaticMomentSuggestion,
        DramaticMomentTag,
        DramaticMomentType,
    )

    if scene is None:
        return []

    created: list[DramaticMomentSuggestion] = []
    flagged = DramaticMomentType.objects.filter(
        suggest_on_technique_entrance=True,
        suggestion_min_success_level__lte=success_level,
    )
    for moment_type in flagged:
        if not CharacterResonance.objects.filter(
            character_sheet=character_sheet, resonance=moment_type.resonance
        ).exists():
            continue
        if (
            DramaticMomentTag.objects.filter(
                moment_type=moment_type, character_sheet=character_sheet, scene=scene
            ).count()
            >= moment_type.per_scene_cap
        ):
            continue
        suggestion, was_created = DramaticMomentSuggestion.objects.get_or_create(
            moment_type=moment_type,
            character_sheet=character_sheet,
            scene=scene,
            status=SuggestionStatus.PENDING,
            defaults={
                "success_level": success_level,
                "interaction": interaction,
                "interaction_timestamp": interaction.timestamp if interaction else None,
            },
        )
        if was_created:
            created.append(suggestion)
    return created


def resolve_dramatic_moment_suggestion(
    suggestion: DramaticMomentSuggestion, *, resolver: AccountDB, confirm: bool
) -> DramaticMomentSuggestion:
    """Confirm or dismiss a PENDING DramaticMomentSuggestion (#2183).

    Confirming mints a real DramaticMomentTag via ``create_dramatic_moment_tag``
    (which fires the resonance grant + renown award); its EndorsementValidationError
    / DramaticMomentCapExceeded propagate uncaught to the caller (API layer maps
    them to safe 400 responses). Dismissing just closes out the suggestion.

    Raises:
        DramaticMomentSuggestionAlreadyResolved: If the suggestion isn't PENDING.
    """
    from world.magic.constants import SuggestionStatus  # noqa: PLC0415
    from world.magic.exceptions import DramaticMomentSuggestionAlreadyResolved  # noqa: PLC0415

    if suggestion.status != SuggestionStatus.PENDING:
        raise DramaticMomentSuggestionAlreadyResolved

    with transaction.atomic():
        if confirm:
            tag = create_dramatic_moment_tag(
                character_sheet=suggestion.character_sheet,
                moment_type=suggestion.moment_type,
                tagged_by=resolver,
                scene=suggestion.scene,
                interaction=suggestion.interaction,
            )
            suggestion.confirmed_tag = tag
            suggestion.status = SuggestionStatus.CONFIRMED
        else:
            suggestion.status = SuggestionStatus.DISMISSED
        suggestion.resolved_by = resolver
        suggestion.save()
    return suggestion


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
        if sheet.is_protagonism_locked:
            continue
        sheets_processed += 1
        matched = get_residence_resonances(sheet)
        rp = sheet.current_residence
        if rp is None or not matched:
            continue

        for resonance in matched:
            try:
                with transaction.atomic():
                    grant_resonance(
                        sheet,
                        resonance,
                        cfg.residence_daily_trickle_per_resonance,
                        source=GainSource.ROOM_RESIDENCE,
                        room_profile=rp,
                    )
                    grants_issued += 1
            except Exception:  # noqa: BLE001, S112
                # TODO: structured log via Evennia logger.
                continue

    return ResonanceDailyTickSummary(
        residence_grants_issued=grants_issued,
        sheets_processed=sheets_processed,
    )


def outfit_daily_trickle_for_character(sheet: CharacterSheet) -> int:
    """Daily resonance trickle from worn facet-bearing items (Spec D §5.1).

    Note: "outfit" here refers to the character's *current loadout* (whatever
    is worn right now), not the saved Outfit entity in
    ``world.items.models.Outfit``. The two concepts coexist: a saved Outfit
    is a named arrangement; the current loadout is whatever EquippedItem
    rows exist on the character at this moment.

    For each equipped item:
      For each ItemFacet on the item:
        If the wearer has a Thread on that Facet:
          grant_resonance(
            sheet,
            thread.resonance,
            amount=trickle_for(item, item_facet, thread),
            source=GainSource.OUTFIT_TRICKLE,
            outfit_item_facet=item_facet,
          )

    Returns: count of grants issued for this sheet.
    """
    from world.magic.constants import GainSource  # noqa: PLC0415
    from world.magic.services.resonance import grant_resonance  # noqa: PLC0415

    config = get_resonance_gain_config()
    base = config.outfit_daily_trickle_per_item_resonance
    grants_issued = 0

    for item_facet in sheet.character.equipped_items.iter_item_facets():
        item = item_facet.item_instance
        item_q_mult = item.quality_tier.stat_multiplier if item.quality_tier else Decimal(1)
        attach_q_mult = item_facet.attachment_quality_tier.stat_multiplier

        thread = sheet.character.threads.thread_for_facet(item_facet.facet)
        if thread is None:
            continue

        level_factor = max(1, thread.level)  # level 0 = ×1, level 5 = ×5
        amount = int(base * item_q_mult * attach_q_mult * level_factor)
        if amount <= 0:
            continue

        grant_resonance(
            sheet,
            thread.resonance,
            amount=amount,
            source=GainSource.OUTFIT_TRICKLE,
            outfit_item_facet=item_facet,
        )
        grants_issued += 1

    return grants_issued


def outfit_trickle_tick() -> int:
    """Outfit trickle tick (Spec D §5.1).

    Iterates all CharacterSheets, skipping protagonism-locked sheets. For each
    sheet, delegates to outfit_daily_trickle_for_character per-sheet in its own
    atomic block so a single failure does not poison the whole tick.

    Returns: total count of grants issued across all sheets.
    """
    total_grants = 0

    for sheet in CharacterSheet.objects.all().iterator():
        if sheet.is_protagonism_locked:
            continue
        try:
            with transaction.atomic():
                total_grants += outfit_daily_trickle_for_character(sheet)
        except Exception:  # noqa: BLE001, S112
            # TODO: structured log via Evennia logger.
            continue

    return total_grants


def resonance_daily_tick() -> ResonanceDailyTickSummary:
    """Master daily tick (Spec C §5). Runs residence + outfit trickle."""
    residence_summary = residence_trickle_tick()
    outfit_grants = outfit_trickle_tick()
    return ResonanceDailyTickSummary(
        residence_grants_issued=residence_summary.residence_grants_issued,
        outfit_grants_issued=outfit_grants,
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
        except Exception:  # noqa: BLE001, S112
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
