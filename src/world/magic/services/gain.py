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
import logging
import math
from typing import TYPE_CHECKING, Any

from django.db import transaction

if TYPE_CHECKING:
    from collections.abc import Sequence

    from world.gm.models import GMPrompt
    from world.items.models import Style
    from world.magic.models.dramatic_moment import (
        DramaticMomentTag,
        DramaticMomentType,
    )
    from world.magic.models.endorsement import EntryFlourishRecord, StylePresentationEndorsement
    from world.magic.models.techniques import Technique
    from world.societies.models import PhilosophicalArchetype
from django.utils import timezone
from evennia.accounts.models import AccountDB

from actions.constants import ActionCategory
from evennia_extensions.models import RoomProfile
from world.areas.services import area_for_scene
from world.character_sheets.models import CharacterSheet
from world.checks.constants import ModifierLane
from world.checks.modifier_values import load_baselines
from world.locations.constants import RESONANCE_DEFAULT_MAGNITUDE, KeyType, LocationParentType
from world.locations.models import LocationValueModifier
from world.magic.exceptions import EndorsementValidationError
from world.magic.models import (
    CharacterResonance,
    PoseEndorsement,
    RecordedAct,
    Resonance,
    ResonanceGainConfig,
    ResonanceGrant,
    SceneEntryEndorsement,
)
from world.magic.services.gain_fatigue import (
    charge_gain_fatigue,
    gain_without_act_refusal_line,
    gain_without_act_shrunk_line,
    pose_gain_payer,
    send_player_line,
    tell_gainer,
    tell_player,
)
from world.magic.types import (
    ResonanceDailyTickSummary,
    ResonanceWeeklySettlementSummary,
    SettlementResult,
)
from world.magic.types.marking import GainFatigueCharge
from world.scenes.constants import (
    InteractionMode,
    InteractionVisibility,
    PoseKind,
    ScenePrivacyMode,
)
from world.scenes.interaction_services import notify_interaction_changed
from world.scenes.models import Interaction, Persona, Scene, SceneParticipation
from world.scenes.place_models import InteractionReceiver
from world.scenes.services import active_persona_for_sheet, is_scene_gm_or_staff

logger = logging.getLogger(__name__)

# What a gain with no act came from, as the private line names it (#5327).
_WHAT_ENDORSEMENT = "that endorsement"
_WHAT_TAG = "that tag"
_ERR_OWN_TAG = "You cannot tag a moment for your own character."
_RETRY_NEXT_WEEK = "It will be tried again at next week's settlement."


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


def player_of_sheet(sheet: CharacterSheet) -> AccountDB | None:
    """The account that plays ``sheet`` right now, a lent NPC's borrower included (#5327).

    Unlike ``account_for_sheet``, which reads only the current tenure, this follows the loan
    rule the rest of the game uses (``npc_lending.current_player_of``): the borrower of a lent
    NPC plays it and its holder does not. The endorsement and tag routes ask this question.
    """
    from world.roster.services.npc_lending import current_player_of  # noqa: PLC0415

    return current_player_of(sheet)


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
_ERR_NO_RESONANCE = "Which resonance? This pose did not reach for one."
_ERR_MARK_PAID = (
    "That pose already paid its writer for an act she marked, so it cannot also be endorsed. "
    "Endorse another pose instead."
)
_ERR_ENDORSEMENT_SETTLED = "That endorsement has already been settled and can no longer change."
_ERR_NOT_YOUR_ENDORSEMENT = "Only the player who made that endorsement can change it."
_ERR_NOT_YOURS_TO_ANSWER = (
    "Only the player whose pose it is, the scene's GM or staff can answer a proposed resonance."
)
_ERR_NOT_WAITING = "That endorsement is not waiting for an answer."
_ERR_OWN_RESONANCE = (
    "That pose named its own resonance, so an endorsement of it cannot pick another."
)


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
    qs = ResonanceGrant.objects.filter(character_sheet=sheet).select_related(
        "resonance__affinity__skill"
    )
    if resonance is not None:
        qs = qs.filter(resonance=resonance)
    return list(qs.order_by("-granted_at")[:limit])


def pose_number_in_scene(endorser_sheet: CharacterSheet, interaction: Interaction) -> int | None:
    """The number ``poses <char>`` and ``endorse pose`` give ``interaction`` for ``endorser_sheet``
    (its position among its author's poses in the scene), or None when it has no scene or the
    endorser cannot see it."""
    scene = interaction.scene
    if scene is None or interaction.persona is None:
        return None
    author = interaction.persona.character_sheet
    if author is None:
        return None
    for number, row in get_endorseable_poses_in_scene(endorser_sheet, author, scene):
        if row.pk == interaction.pk:
            return number
    return None


def waiting_picks_from(
    witness_sheet: CharacterSheet, poser_sheet: CharacterSheet, scene: Scene
) -> list[tuple[int, PoseEndorsement]]:
    """The picks ``witness_sheet`` has waiting on ``poser_sheet``'s poses in ``scene``, as
    ``(pose number, pick)`` pairs in pose order (#5327).

    The pose number is the one ``poses`` gives the witness and the proposal line quotes, so
    ``endorse accept <witness> #N`` names a pick by who proposed it and on which pose.
    """
    numbered = {
        interaction.pk: number
        for number, interaction in get_endorseable_poses_in_scene(witness_sheet, poser_sheet, scene)
    }
    rows = PoseEndorsement.objects.filter(
        endorser_sheet=witness_sheet,
        endorsee_sheet=poser_sheet,
        interaction_id__in=numbered,
        awaiting_acceptance=True,
        settled_at__isnull=True,
    ).select_related("resonance", "interaction__persona")
    return sorted(((numbered[row.interaction_id], row) for row in rows), key=lambda pair: pair[0])


def _tell_poser_of_proposal(endorsement: PoseEndorsement) -> None:
    """Tell the poser, once the pick commits, which resonance a witness proposed on her pose
    and how to answer it (#5327). The line names the witness as she knows them, and the pose by
    its number, the way ``endorse accept`` and ``endorse decline`` name it."""
    from world.magic.services.kindling import shown_names  # noqa: PLC0415

    poser = endorsement.endorsee_sheet
    witness = endorsement.endorser_sheet
    resonance_name = endorsement.resonance.name
    interaction = endorsement.interaction

    def _send() -> None:
        name = shown_names(poser, [witness.pk]).get(witness.pk, "Someone")
        number = pose_number_in_scene(witness, interaction)
        if number is None:
            line = f"{name} proposed {resonance_name} on your pose. Answer it on the web."
        else:
            line = (
                f"{name} proposed {resonance_name} on your pose #{number}. "
                f"Use endorse accept {name} #{number} or endorse decline {name} #{number}."
            )
        send_player_line(poser, line, ooc_note="A resonance proposed on your pose")

    transaction.on_commit(_send)


def _announce_endorsement(endorsement: PoseEndorsement) -> None:
    """Tell a new endorsement's audience: the poser when the pick waits for her, and everyone
    who reads the pose, who refetch it."""
    if endorsement.awaiting_acceptance:
        _tell_poser_of_proposal(endorsement)
    notify_interaction_changed(endorsement.interaction)


def _pose_endorsement_target(
    interaction: Interaction, chosen: Resonance | None
) -> tuple[Resonance, bool]:
    """The resonance an endorsement of ``interaction`` pays, and whether it waits (#5327).

    The one the pose reached for when its author named one: that endorsement is confirmed and
    does not wait. On a pose that named none, ``chosen`` is any resonance the witness picked,
    whether or not it is in the poser's aura, and the row waits for the poser to accept it.

    Raises:
        EndorsementValidationError: the pose named no resonance and none was chosen.
    """
    reach = interaction.cached_resonance_reach
    if reach is not None:
        return reach.resonance, False
    if chosen is None:
        raise EndorsementValidationError(_ERR_NO_RESONANCE)
    return chosen, True


@transaction.atomic
def create_pose_endorsement(  # noqa: C901
    endorser_sheet: CharacterSheet,
    interaction: Interaction,
    resonance: Resonance | None = None,
) -> PoseEndorsement:
    """Validate and persist a pose endorsement (Spec C §2.2 + §7).

    A pose whose author reached for a resonance (#5308) is endorsed for that resonance:
    ``resonance`` is then ignored, since the author named it. A pose that reached for nothing
    needs ``resonance``, any resonance at all (#5327): the row is saved waiting for the poser
    to accept it (``awaiting_acceptance``), and settlement skips it until she does.

    Preconditions (raises EndorsementValidationError on failure):
    1. Interaction author (persona field) has a character sheet
    2. Endorser != endorsee (no self-endorsement)
    3. Endorser's account != endorsee's account (no alt-endorsement)
    4. WHISPER: endorser must be the direct recipient (InteractionReceiver row)
    5. VERY_PRIVATE: endorser must have SceneParticipation (allowed by participants)
    6. Endorser was present (scene participation OR interaction receiver)
    7. The pose's mark has not already paid (an act marked on it paid its writer)
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

    endorser_account = player_of_sheet(endorser_sheet)
    endorsee_account = player_of_sheet(endorsee_sheet)
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

    resonance, awaiting = _pose_endorsement_target(interaction, resonance)

    if RecordedAct.objects.filter(
        marked_interaction=interaction, marked_grant__isnull=False
    ).exists():
        raise EndorsementValidationError(_ERR_MARK_PAID)

    existing = PoseEndorsement.objects.filter(
        endorser_sheet=endorser_sheet, interaction=interaction
    ).first()
    if existing is not None:
        msg = "Already endorsed this pose"
        raise EndorsementValidationError(msg)

    # Peek, don't read: interaction.cached_endorsements is a PrunedCachedProperty, so
    # reading it here would trigger a query whenever the cache happens to be cold --
    # defeating the point of caching it in the common (cold) case. A dict-lookup peek
    # costs nothing, and skipping the mutation on a cold cache loses nothing: the next
    # real read recomputes fresh from the DB anyway (#3816).
    cached = interaction.__dict__.get("cached_endorsements")
    endorsement = PoseEndorsement.objects.create(
        endorser_sheet=endorser_sheet,
        endorsee_sheet=endorsee_sheet,
        interaction=interaction,
        timestamp=interaction.timestamp,
        resonance=resonance,
        awaiting_acceptance=awaiting,
        persona_snapshot=endorsee_persona,
        endorser_persona=active_persona_for_sheet(endorser_sheet),
    )
    # PoseEndorsement.objects.create() above runs PoseEndorsement.save(), which
    # (via RelatedCacheClearingMixin + related_cache_fields=["interaction"])
    # clears ALL of interaction's cached_* attributes as a collateral side effect
    # of that write -- including the one we peeked above. That clearing is
    # correct and load-bearing on its own (it is what covers PoseEndorsementViewSet
    # .destroy(), which has no direct-mutation counterpart at all), but it means
    # the assignment below is not redundant with it: it re-warms specifically
    # cached_endorsements from the pre-write snapshot we captured, rather than
    # leaving it cold until the next reader re-queries. Do not remove the mixin
    # thinking this line already covers it -- the delete path depends on the
    # mixin alone (ADR-0298).
    if cached is not None:
        interaction.cached_endorsements = [*cached, endorsement]
    _announce_endorsement(endorsement)
    return endorsement


def retract_pose_endorsement(endorsement: PoseEndorsement) -> None:
    """Delete a pose endorsement and tell the pose's audience it changed (#4508)."""
    interaction = endorsement.interaction
    endorsement.delete()
    notify_interaction_changed(interaction)


def _open_endorsement(endorsement: PoseEndorsement) -> PoseEndorsement:
    """Lock ``endorsement`` while it is unsettled, so a change cannot race the weekly tick.

    Raises:
        EndorsementValidationError: the weekly settlement already took it.
    """
    locked = (
        PoseEndorsement.objects.select_for_update()
        .filter(pk=endorsement.pk, settled_at__isnull=True)
        .first()
    )
    if locked is None:
        raise EndorsementValidationError(_ERR_ENDORSEMENT_SETTLED)
    return locked


def _may_answer_proposal(endorsement: PoseEndorsement, by: AccountDB) -> bool:
    """Whether ``by`` may accept or decline a proposed resonance on this pose (#5327).

    The poser's own player, the scene's GM (``Scene.is_gm``, never an owner) and staff, each
    only when they can read the pose as the scene log decides. Nobody answers a pick her own
    account made: a GM who proposed a resonance cannot accept it too.
    """
    if player_of_sheet(endorsement.endorser_sheet) == by:
        return False
    interaction = endorsement.interaction
    poser_account = player_of_sheet(endorsement.endorsee_sheet)
    if not (
        (poser_account is not None and poser_account == by)
        or is_scene_gm_or_staff(by, interaction.scene)
    ):
        return False
    return Interaction.objects.readable_by(by).filter(pk=interaction.pk).exists()


@transaction.atomic
def change_pose_endorsement(
    endorsement: PoseEndorsement, resonance: Resonance, by: AccountDB
) -> PoseEndorsement:
    """Swap the resonance a witness picked on a pose, and put it back to waiting (#5327).

    Allowed to the endorser until the weekly settlement pays the row, even after the poser
    accepted the old pick: the new pick waits for her again. A pick of the resonance already
    on the row changes nothing. A pose that named its own resonance has nothing to pick.

    Raises:
        EndorsementValidationError: ``by`` did not make the endorsement, the pose named its own
            resonance, or the weekly settlement already took the row.
    """
    if player_of_sheet(endorsement.endorser_sheet) != by:
        raise EndorsementValidationError(_ERR_NOT_YOUR_ENDORSEMENT)
    row = _open_endorsement(endorsement)
    if row.interaction.cached_resonance_reach is not None:
        raise EndorsementValidationError(_ERR_OWN_RESONANCE)
    if row.resonance_id == resonance.pk:
        return row
    row.resonance = resonance
    row.awaiting_acceptance = True
    row.save(update_fields=["resonance", "awaiting_acceptance"])
    # The poser is told once, when the pick is made. A change tells her nothing more: she reads
    # the current pick on the pose, and a witness cannot flood her by changing it.
    notify_interaction_changed(row.interaction)
    return row


@transaction.atomic
def withdraw_pose_endorsement(endorsement: PoseEndorsement, by: AccountDB) -> None:
    """The endorser takes back her own endorsement, until the weekly settlement pays it (#5327).

    Raises:
        EndorsementValidationError: ``by`` did not make the endorsement, or the weekly
            settlement already took the row.
    """
    if player_of_sheet(endorsement.endorser_sheet) != by:
        raise EndorsementValidationError(_ERR_NOT_YOUR_ENDORSEMENT)
    retract_pose_endorsement(_open_endorsement(endorsement))


@transaction.atomic
def accept_pose_proposal(endorsement: PoseEndorsement, by: AccountDB) -> PoseEndorsement:
    """Accept the resonance a witness proposed, so the weekly settlement pays it (#5327).

    Raises:
        EndorsementValidationError: ``by`` may not answer it, it is not waiting, or the weekly
            settlement already took the row.
    """
    if not _may_answer_proposal(endorsement, by):
        raise EndorsementValidationError(_ERR_NOT_YOURS_TO_ANSWER)
    row = _open_endorsement(endorsement)
    if not row.awaiting_acceptance:
        raise EndorsementValidationError(_ERR_NOT_WAITING)
    row.awaiting_acceptance = False
    row.save(update_fields=["awaiting_acceptance"])
    notify_interaction_changed(row.interaction)
    return row


@transaction.atomic
def decline_pose_proposal(endorsement: PoseEndorsement, by: AccountDB) -> None:
    """Decline the resonance a witness proposed: the row is deleted and pays nothing (#5327).

    Raises:
        EndorsementValidationError: ``by`` may not answer it, it is not waiting, or the weekly
            settlement already took the row.
    """
    if not _may_answer_proposal(endorsement, by):
        raise EndorsementValidationError(_ERR_NOT_YOURS_TO_ANSWER)
    row = _open_endorsement(endorsement)
    if not row.awaiting_acceptance:
        raise EndorsementValidationError(_ERR_NOT_WAITING)
    retract_pose_endorsement(row)


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
        receiver_persona = endorser_sheet.primary_persona
    except Persona.DoesNotExist:
        return False
    return InteractionReceiver.objects.filter(
        interaction=interaction, persona=receiver_persona
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
    endorser_account = player_of_sheet(endorser_sheet)

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
        elif interaction.visibility == InteractionVisibility.VERY_PRIVATE and not is_participant:
            continue
        result.append((idx, interaction))

    return result


@transaction.atomic
def settle_weekly_pot(endorser_sheet: CharacterSheet) -> SettlementResult:
    """Settle all unsettled PoseEndorsement rows for one endorser.

    Distributes the weekly pot across the endorser's unsettled endorsements
    using ceiling division, writes grants via grant_resonance (ledger rows
    auto-written), and marks each endorsement settled_at=now.

    A row still waiting for the poser to accept it (#5327) is skipped, in the split and in the
    count, and stays unsettled until she answers.

    Idempotent — a second call with no new unsettled rows is a no-op.
    """
    # Inner import to avoid circular with services/resonance.py
    from world.magic.constants import GainSource  # noqa: PLC0415
    from world.magic.services.resonance import grant_resonance  # noqa: PLC0415

    unsettled = list(
        PoseEndorsement.objects.select_for_update().filter(
            endorser_sheet=endorser_sheet,
            settled_at__isnull=True,
            awaiting_acceptance=False,
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
    # The pot is a budget of UNSCALED shares: each endorsement draws ``share`` of it, and the
    # resonance's own affinity's earn rate (#5231) is its bonus on top, applied inside
    # ``grant_resonance``.
    # So the split stays in unscaled terms, while what is stored and totalled below is the
    # amount the ledger row actually recorded.
    share = math.ceil(cfg.weekly_pot_per_character / n)
    now = timezone.now()
    total_granted = 0
    settled = 0

    for endorsement in unsettled:
        if endorsement.endorsee_sheet.is_protagonism_locked:
            # Endorsee is subsumed — skip resonance grant for this tick.
            endorsement.granted_amount = 0
            endorsement.settled_at = now
            endorsement.save(update_fields=["granted_amount", "settled_at"])
            settled += 1
            continue
        # A gain that points at no act tires whoever pays for it (#5327), as a mark does.
        gainer = endorsement.endorsee_sheet
        charge = charge_gain_fatigue(
            gainer,
            pose_gain_payer(gainer, endorsement.resonance, endorsement.interaction),
            endorsement.resonance,
            ActionCategory.SOCIAL,
            share,
            from_mark=False,
        )
        if charge.refused and not charge.shrunk:
            # Nothing was asked of anyone (the pot's share is 0): it settles paying nothing.
            endorsement.granted_amount = 0
            endorsement.settled_at = now
            endorsement.save(update_fields=["granted_amount", "settled_at"])
            settled += 1
            continue
        if charge.refused:
            # Its payer is too worn. Left unsettled: the next weekly settlement tries it again,
            # once the payer has recovered. Stamping it settled would end it, and the endorser
            # cannot make the same endorsement twice.
            tell_gainer(
                gainer,
                gain_without_act_refusal_line(
                    charge,
                    gainer,
                    endorsement.resonance,
                    what=_WHAT_ENDORSEMENT,
                    next_step=_RETRY_NEXT_WEEK,
                ),
            )
            continue
        ledger: list = []
        grant_resonance(
            gainer,
            endorsement.resonance,
            charge.amount,
            source=GainSource.POSE_ENDORSEMENT,
            pose_endorsement=endorsement,
            ledger_out=ledger,
        )
        if charge.shrunk:
            tell_gainer(
                gainer,
                gain_without_act_shrunk_line(
                    charge,
                    gainer,
                    endorsement.resonance,
                    what=_WHAT_ENDORSEMENT,
                    paid=ledger[-1].amount,
                ),
            )
        endorsement.granted_amount = ledger[-1].amount
        endorsement.settled_at = now
        endorsement.save(update_fields=["granted_amount", "settled_at"])
        total_granted += ledger[-1].amount
        settled += 1

    return SettlementResult(
        endorser_sheet=endorser_sheet,
        endorsements_settled=settled,
        total_granted=total_granted,
    )


def _keep_granted_amount(row: Any, ledger: list[ResonanceGrant]) -> None:
    """Make a receipt row's ``granted_amount`` the amount its ledger row recorded.

    ``grant_resonance`` scales the amount by the earn rate of the resonance's own affinity
    (#5231), so the number the receipt was created with is not always the number granted. No
    write when they agree.
    """
    if ledger[-1].amount != row.granted_amount:
        row.granted_amount = ledger[-1].amount
        row.save(update_fields=["granted_amount"])


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

    if endorser_sheet.is_protagonism_locked:
        msg = "Endorser is locked from protagonism and cannot endorse scene entries"
        raise EndorsementValidationError(msg)
    if endorsee_sheet.is_protagonism_locked:
        msg = "Endorsee is locked from protagonism and cannot receive scene-entry endorsements"
        raise EndorsementValidationError(msg)

    if endorser_sheet == endorsee_sheet:
        msg = "Cannot endorse your own entry"
        raise EndorsementValidationError(msg)

    endorser_account = player_of_sheet(endorser_sheet)
    endorsee_account = player_of_sheet(endorsee_sheet)
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
        endorser_persona=active_persona_for_sheet(endorser_sheet),
        granted_amount=cfg.scene_entry_grant,
    )
    ledger: list = []
    grant_resonance(
        endorsee_sheet,
        resonance,
        cfg.scene_entry_grant,
        source=GainSource.SCENE_ENTRY,
        scene_entry_endorsement=endorsement,
        ledger_out=ledger,
    )
    _keep_granted_amount(endorsement, ledger)
    _notify_entry_poses(scene, endorsee_sheet)
    return endorsement


def _notify_entry_poses(scene: Scene, endorsee_sheet: CharacterSheet) -> None:
    """Announce every entrance pose ``endorsee_sheet`` made in ``scene``: it shows the endorsers."""

    for entry in Interaction.objects.filter(
        scene=scene, persona__character_sheet=endorsee_sheet, pose_kind=PoseKind.ENTRY
    ):
        notify_interaction_changed(entry)


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

    endorser_account = player_of_sheet(endorser_sheet)
    endorsee_account = player_of_sheet(endorsee_sheet)
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
        endorser_persona=active_persona_for_sheet(endorser_sheet),
        granted_amount=grant_amount,
    )
    ledger: list = []
    grant_resonance(
        endorsee_sheet,
        resonance,
        grant_amount,
        source=GainSource.STYLE_PRESENTATION,
        style_presentation_endorsement=endorsement,
        ledger_out=ledger,
    )
    _keep_granted_amount(endorsement, ledger)

    _bump_showcase_engagement(endorsee_sheet, scene)
    return endorsement


def _bump_showcase_engagement(endorsee_sheet: CharacterSheet, scene: Scene) -> None:
    """Feed a style endorsement into the weekly showcase settlement (#2907).

    A peer endorsing your style presentation IS the "other players positive
    this" signal the settlement ladder reads — bump the endorsee's unsettled
    showing in this scene (fallback: their latest unsettled showing this
    week; coarse v1, guess flagged on #2907).
    """
    from world.items.models import FashionShowing  # noqa: PLC0415
    from world.items.services.fashion_showcase import record_showing_engagement  # noqa: PLC0415

    showing = (
        FashionShowing.objects.filter(
            character_sheet=endorsee_sheet, settled=False, scene=scene
        ).first()
        or FashionShowing.objects.filter(character_sheet=endorsee_sheet, settled=False).first()
    )
    if showing is not None:
        record_showing_engagement(showing)


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

    Creates the EntryFlourishRecord and fires grant_resonance atomically. The resonance need
    not be one the character holds yet: a flourish in a new resonance earns it (#5308), and
    the grant creates the character's row. The entrance made no roll that reaches this far,
    so the bonus resonance check uses the stat staff set for ENTRY_FLOURISH.

    Args:
        character_sheet: The character performing the flourish.
        resonance: The resonance the character expressed during their entrance.
        scene: Scene context; None if outside a scene.
        amount: Override the config default; None uses entry_flourish_grant.

    Returns:
        The created EntryFlourishRecord.
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

    cfg = get_resonance_gain_config()
    granted = amount if amount is not None else cfg.entry_flourish_grant

    record = EntryFlourishRecord.objects.create(
        character_sheet=character_sheet,
        resonance=resonance,
        scene=scene,
        granted_amount=granted,
    )
    ledger: list = []
    grant_resonance(
        character_sheet,
        resonance,
        granted,
        source=GainSource.ENTRY_FLOURISH,
        entry_flourish=record,
        ledger_out=ledger,
    )
    _keep_granted_amount(record, ledger)
    return record


def _resolve_moment_resonance(
    *,
    character_sheet: CharacterSheet,
    moment_type: DramaticMomentType,
    technique: Technique | None,
    resonance: Resonance | None,
    may_choose: bool,
) -> Resonance | None:
    """Resolve which resonance a dramatic moment grants, or None to skip the grant.

    A *resonance* the tagger named is used as it is, whether or not the character has it, when
    ``may_choose`` (the scene's GM or staff, #5327). Anyone else keeps what a scene owner could
    do before: a named resonance counts only when the character already has it, and otherwise
    the tag pays as if none was named, so the tag never says whether she has it. Then, in
    order, taking the first the character has actually claimed:

    1. the resonance woven into the entrance technique's gift, via
       ``gift_resonances_for`` (the ADR-0052 derive-on-read seam);
    2. the moment type's authored override;
    3. the character's anima-ritual resonance — their "main" one.

    Step 3 exists because step 1 can come up empty even for a technique-driven
    entrance — e.g. a gift-holder whose thread was provisioned at a resonance
    that isn't among the candidates already tried. Their anima ritual is the
    one place a "main" resonance is always recorded, so it is the last resort
    before granting nothing. (As of #2971, ``grant_gift_to_character`` always
    provisions a GIFT thread, so step 1 is no longer the common failure case
    it once was — this fallback stays as a defense for sheets whose thread
    predates that guarantee, or whose thread's resonance the character never
    claimed.)
    """
    from world.magic.specialization.services import gift_resonances_for  # noqa: PLC0415

    candidates: list[Resonance] = []
    if resonance is not None:
        if may_choose:
            return resonance
        candidates.append(resonance)
    if technique is not None and technique.gift_id:
        # CharacterSheet.character is a primary_key OneToOne, so it is always
        # present on a saved sheet. gift_resonances_for reads the woven GIFT
        # thread off it and falls back to the gift's authored set itself.
        candidates.extend(gift_resonances_for(character_sheet.character, technique.gift))
    if moment_type.resonance_id:
        candidates.append(moment_type.resonance)
    main = anima_ritual_resonance(character_sheet)
    if main is not None:
        candidates.append(main)

    for candidate in candidates:
        if CharacterResonance.objects.filter(
            character_sheet=character_sheet, resonance=candidate
        ).exists():
            return candidate
    return None


def anima_ritual_resonance(character_sheet: CharacterSheet) -> Resonance | None:
    """The character's anima-ritual resonance: their 'main' one, if authored.

    The ritual carries two picks (#5280), a Primal one and an optional Celestial or
    Abyssal one. The 'main' is the pick whose affinity is the aura's main affinity;
    otherwise the Primal pick, else the outward pick. Best-effort: no ritual, or no
    pick on its config, simply yields no candidate.
    """
    from world.magic.services.anima import get_character_anima_ritual  # noqa: PLC0415
    from world.magic.services.drift import own_affinity  # noqa: PLC0415

    ritual = get_character_anima_ritual(character_sheet.character)
    if ritual is None:
        return None
    # ``check_config_or_none`` is the model's own ReverseOneToOneOrNone
    # descriptor; the sidecar is optional, so don't reinvent the guard.
    config = ritual.check_config_or_none
    if config is None:
        return None
    picks = [pick for pick in (config.primal_resonance, config.outward_resonance) if pick]
    main = own_affinity(character_sheet)
    if main is not None:
        for pick in picks:
            if pick.affinity_id == main.pk:
                return pick
    return picks[0] if picks else None


def _tell_tagged_player(
    character_sheet: CharacterSheet,
    moment_type: DramaticMomentType,
    grant: ResonanceGrant,
    tagged_by: AccountDB,
    scene: Scene | None,
) -> None:
    """Tell the tagged player which resonance a tag paid (#5327).

    The tagger may have named the resonance, so the player would otherwise not know which one
    grew. The line names the moment type and the resonance, not an amount, and the tagger by
    role, never by account: "Staff", "The scene's GM", else "Someone". It is sent as a private
    message once the tag commits, so a player who is offline reads it at login.
    """
    if tagged_by.is_staff:
        who = "Staff"
    elif scene is not None and scene.is_gm(tagged_by):
        who = "The scene's GM"
    else:
        who = "Someone"
    # The label is staff-written and may open with an article ("A Flourish of Steel"), so the
    # sentence puts no article in front of it.
    line = f"{who} tagged your pose: {moment_type.label}. It paid you {grant.resonance.name}."
    tell_player(character_sheet, line, ooc_note="A dramatic moment tag")


def _worn_payer_name(payer: CharacterSheet, interaction: Interaction | None) -> str:
    """The face ``payer`` shows in the scene, for the line that says she is too worn.

    The pose's own author name when she wrote it, else the face she presents now: never her
    real name behind a mask.
    """
    if (
        interaction is not None
        and interaction.persona is not None
        and interaction.persona.character_sheet_id == payer.pk
    ):
        return interaction.persona.name
    try:
        return active_persona_for_sheet(payer).name
    except Persona.DoesNotExist:
        return "That character"


def _charge_tag_fatigue(
    character_sheet: CharacterSheet,
    moment_type: DramaticMomentType,
    granted_resonance: Resonance,
    interaction: Interaction | None,
) -> GainFatigueCharge:
    """Charge the fatigue a person's tag costs its payer, before the tag is written (#5327).

    A tag points at no act, so the gain tires whoever pays for it as a mark would (the tagged
    character for Primal and Celestial, the pose's one named target for Abyssal, nobody when
    the pose names none or several). A payer who is running low shrinks the gain.

    Raises:
        EndorsementValidationError: the payer has nothing left to pay with, so the tag is
            refused before any row exists and spends none of the scene's per-scene cap.
    """
    charge = charge_gain_fatigue(
        character_sheet,
        pose_gain_payer(character_sheet, granted_resonance, interaction),
        granted_resonance,
        ActionCategory.SOCIAL,
        moment_type.resonance_amount,
        from_mark=False,
    )
    if charge.refused and charge.shrunk and charge.payer is not None:
        name = _worn_payer_name(charge.payer, interaction)
        msg = (
            f"{name} is too worn for this tag to pay. "
            f"Tag another pose, or wait until {name} has recovered."
        )
        raise EndorsementValidationError(msg)
    return charge


def _pay_dramatic_moment(
    character_sheet: CharacterSheet,
    granted_resonance: Resonance,
    tag: DramaticMomentTag,
    charge: GainFatigueCharge,
) -> ResonanceGrant | None:
    """Pay a tag the amount its payer's fatigue left (#5327); the grant, or None when that
    amount is 0.

    A payer who ran low shrank the amount, and the tagged player is told so, with what to
    expect next.
    """
    from world.magic.constants import GainSource  # noqa: PLC0415
    from world.magic.services.resonance import grant_resonance  # noqa: PLC0415

    if charge.amount <= 0:
        return None
    ledger: list[ResonanceGrant] = []
    grant_resonance(
        character_sheet,
        granted_resonance,
        charge.amount,
        source=GainSource.DRAMATIC_MOMENT,
        dramatic_moment=tag,
        ledger_out=ledger,
    )
    if charge.shrunk:
        tell_gainer(
            character_sheet,
            gain_without_act_shrunk_line(
                charge,
                character_sheet,
                granted_resonance,
                what=_WHAT_TAG,
                paid=ledger[-1].amount,
            ),
        )
    return ledger[-1]


@transaction.atomic
def create_dramatic_moment_tag(  # noqa: PLR0913 - cohesive params describing one tag event
    *,
    character_sheet: CharacterSheet,
    moment_type: DramaticMomentType,
    tagged_by: AccountDB,
    scene: Scene | None,
    interaction: Interaction | None = None,
    technique: Technique | None = None,
    resonance: Resonance | None = None,
    archetypes: Sequence[PhilosophicalArchetype] = (),
    by_system: bool = False,
) -> DramaticMomentTag:
    """Tag a character's dramatic scene moment and fire resonance + renown.

    Both the resonance grant and the renown award fire in one atomic transaction.
    If the character has no primary persona, the renown step is skipped — the
    resonance grant still fires. Fire_renown_award's best-effort notification
    runs outside the transaction by design (see fire_renown_award docstring).

    Who may do what (#5327), enforced here so no path can skip it:

    - nobody tags a character she plays now (``player_of_sheet``, a lent NPC's borrower
      included);
    - the scene's GM and staff (``is_scene_gm_or_staff``) may name any resonance, in the
      character's aura or not; anyone else's named resonance counts only when the character
      already has it;
    - the tagger's tag tires its payer (``_charge_tag_fatigue``); a payer with nothing left
      refuses the tag before it is written.

    ``by_system`` is true for an outcome the game itself pays (a standoff's ending): no person
    tagged, so none of the three rules above applies and no fatigue is charged.

    The resonance granted is resolved, not dictated by the moment type
    (ruled 2026-08-04 — resonance comes from the player). In order:

    1. an explicit *resonance* argument, under the rule above;
    2. the resonance woven into the gift of *technique*, when the entrance was
       cast with one — the expected path, since most dramatic entrances should
       be technique-driven;
    3. ``moment_type.resonance``, if a type pins one as an authored override.

    If none of those resolve, the renown award still fires and the resonance
    grant is simply skipped — a moment can be worth recognising without paying
    a currency the character has no claim to.

    *archetypes*, when given, are the archetypes of this particular act and replace the
    moment type's own for the renown award (a standoff's terms carry their own, #4323);
    empty keeps the type's.

    Raises:
        DramaticMomentCapExceeded: If per_scene_cap for this (moment_type, scene, sheet) is reached.
        EndorsementValidationError: The tagger plays the character, or the payer is too worn.
    """
    from world.magic.exceptions import DramaticMomentCapExceeded  # noqa: PLC0415
    from world.magic.models.dramatic_moment import DramaticMomentTag  # noqa: PLC0415

    if not by_system and player_of_sheet(character_sheet) == tagged_by:
        raise EndorsementValidationError(_ERR_OWN_TAG)

    granted_resonance = _resolve_moment_resonance(
        character_sheet=character_sheet,
        moment_type=moment_type,
        technique=technique,
        resonance=resonance,
        may_choose=is_scene_gm_or_staff(tagged_by, scene),
    )

    existing = DramaticMomentTag.objects.filter(
        moment_type=moment_type,
        character_sheet=character_sheet,
        scene=scene,
    ).count()
    if existing >= moment_type.per_scene_cap:
        raise DramaticMomentCapExceeded(DramaticMomentCapExceeded.user_message)

    charge = GainFatigueCharge(amount=moment_type.resonance_amount, charged=0, payer=None)
    if granted_resonance is not None and not by_system:
        charge = _charge_tag_fatigue(character_sheet, moment_type, granted_resonance, interaction)

    # Peek (not read) BEFORE the create below — DramaticMomentTag carries
    # RelatedCacheClearingMixin, so .create() clears every cached_* attribute on
    # `interaction` as a side effect, including this one. Reading the property here
    # would either force an unwanted query or get wiped out from under us.
    cached_tags = (
        interaction.__dict__.get("cached_dramatic_moment_tags") if interaction is not None else None
    )

    tag = DramaticMomentTag.objects.create(
        moment_type=moment_type,
        character_sheet=character_sheet,
        scene=scene,
        tagged_by=tagged_by,
        interaction=interaction,
        interaction_timestamp=interaction.timestamp if interaction is not None else None,
    )
    if cached_tags is not None:
        interaction.cached_dramatic_moment_tags = [*cached_tags, tag]
    if granted_resonance is not None:
        paid = _pay_dramatic_moment(character_sheet, granted_resonance, tag, charge)
        if paid is not None and resonance is not None and not by_system:
            _tell_tagged_player(character_sheet, moment_type, paid, tagged_by, scene)

    _fire_moment_renown(character_sheet, moment_type, scene, archetypes)

    if interaction is not None:
        notify_interaction_changed(interaction)
    return tag


def _fire_moment_renown(
    character_sheet: CharacterSheet,
    moment_type: DramaticMomentType,
    scene: Scene | None,
    archetypes: Sequence[PhilosophicalArchetype],
) -> None:
    """Fire the moment's renown award for the character's primary persona, if she has one."""
    try:
        persona = character_sheet.primary_persona
    except Persona.DoesNotExist:
        return

    from world.societies.renown import fire_renown_award  # noqa: PLC0415

    fire_renown_award(
        persona=persona,
        magnitude=moment_type.magnitude,
        risk=moment_type.risk,
        reach=moment_type.reach or None,
        archetypes=list(archetypes) or list(moment_type.archetypes.all()),
        origin_area=area_for_scene(scene),
        title=moment_type.label,
    )


def maybe_suggest_dramatic_moments(
    *,
    character_sheet: CharacterSheet,
    scene: Scene | None,
    success_level: int,
    interaction: Interaction | None = None,
    technique: Technique | None = None,
) -> list[GMPrompt]:
    """Create PENDING GM suggestions for a high-success technique entrance (#2183).

    Bridges the technique-entrance deferral markers (Tasks 1-2) to the existing
    DramaticMomentTag machinery without auto-tagging: for every flagged
    DramaticMomentType whose threshold the success level clears, and whose
    per-scene cap isn't already spent on real tags, creates (idempotently) a
    PENDING GMPrompt for a GM to later confirm or dismiss via
    ``resolve_dramatic_moment_suggestion``.

    *technique* is the technique the entrance was cast with. It is stored on the
    suggestion so that confirming it can resolve the resonance from the thread
    the character wove into that technique's gift — most dramatic entrances are
    expected to be technique-driven (ruled 2026-08-04).

    There is deliberately NO claimed-resonance filter here. It used to skip any
    moment type whose authored resonance the character had not claimed, which
    made every flagged type unreachable the moment its authored resonance was one
    nobody claims. Eligibility is now the success threshold and the per-scene cap;
    what the moment resonates as is resolved at confirm time.

    No-ops (returns []) when scene is None — a suggestion is scoped to a scene, same
    as the DramaticMomentTag per-scene cap it mirrors.
    """
    from world.gm.constants import GMPromptKind, GMPromptStatus  # noqa: PLC0415
    from world.gm.models import GMPrompt  # noqa: PLC0415
    from world.gm.prompt_services import (  # noqa: PLC0415
        notify_gm_prompt,
        prompt_recipients,
        scene_gm_accounts,
    )
    from world.magic.models.dramatic_moment import (  # noqa: PLC0415
        DramaticMomentTag,
        DramaticMomentType,
    )

    if scene is None:
        return []

    gms = scene_gm_accounts(scene)
    # #4101 fix round 1: one batched mute query over every scene GM
    # (prompt_recipients), not a per-GM prompts_enabled() call in a loop.
    if gms and not prompt_recipients(scene, GMPromptKind.DRAMATIC_MOMENT, candidates=gms):
        return []

    created: list[GMPrompt] = []
    flagged = DramaticMomentType.objects.filter(
        suggest_on_technique_entrance=True,
        suggestion_min_success_level__lte=success_level,
    )
    for moment_type in flagged:
        if (
            DramaticMomentTag.objects.filter(
                moment_type=moment_type, character_sheet=character_sheet, scene=scene
            ).count()
            >= moment_type.per_scene_cap
        ):
            continue
        suggestion, was_created = GMPrompt.objects.get_or_create(
            moment_type=moment_type,
            character_sheet=character_sheet,
            scene=scene,
            status=GMPromptStatus.PENDING,
            kind=GMPromptKind.DRAMATIC_MOMENT,
            defaults={
                "success_level": success_level,
                "interaction": interaction,
                "interaction_timestamp": interaction.timestamp if interaction else None,
                "technique": technique,
                # #4101 fix round 3, ruling R9-3: a dramatic_moment prompt anchored to
                # an entrance pose freezes the subject's face from that SAME pose
                # (the one real signal already on hand) rather than re-deriving it.
                "subject_persona": interaction.persona if interaction else None,
            },
        )
        if was_created:
            created.append(suggestion)
            # #4101 final review, F1: reach the scene's GMs live with the same
            # gm_prompt frame a narration prompt gets, once the row is committed.
            transaction.on_commit(lambda p=suggestion: notify_gm_prompt(p), robust=True)
    return created


def resolve_dramatic_moment_suggestion(
    suggestion: GMPrompt, *, resolver: AccountDB, confirm: bool
) -> GMPrompt:
    """Confirm or dismiss a PENDING GMPrompt (#2183).

    Confirming mints a real DramaticMomentTag via ``create_dramatic_moment_tag``
    (which fires the resonance grant + renown award); its EndorsementValidationError
    / DramaticMomentCapExceeded propagate uncaught to the caller (API layer maps
    them to safe 400 responses). Dismissing just closes out the suggestion.

    Raises:
        DramaticMomentSuggestionAlreadyResolved: If the suggestion isn't PENDING.
        DramaticMomentSuggestionWrongKind: If ``suggestion.kind`` isn't
            ``dramatic_moment`` (#4101 fix round 1) -- this service mints/dismisses
            dramatic-moment tags specifically and must never act on a narration
            prompt (miracle/death/crossing/...) even if one somehow reaches it.
    """
    from world.gm.constants import GMPromptKind, GMPromptStatus  # noqa: PLC0415
    from world.magic.exceptions import (  # noqa: PLC0415
        DramaticMomentSuggestionAlreadyResolved,
        DramaticMomentSuggestionWrongKind,
    )

    if suggestion.kind != GMPromptKind.DRAMATIC_MOMENT:
        raise DramaticMomentSuggestionWrongKind
    if suggestion.status != GMPromptStatus.PENDING:
        raise DramaticMomentSuggestionAlreadyResolved

    with transaction.atomic():
        if confirm:
            tag = create_dramatic_moment_tag(
                character_sheet=suggestion.character_sheet,
                moment_type=suggestion.moment_type,
                tagged_by=resolver,
                scene=suggestion.scene,
                interaction=suggestion.interaction,
                # Carry the entrance technique so the grant follows the thread the
                # character wove into its gift, rather than an authored constant.
                technique=suggestion.technique,
            )
            suggestion.confirmed_tag = tag
            suggestion.status = GMPromptStatus.CONFIRMED
        else:
            suggestion.status = GMPromptStatus.DISMISSED
        suggestion.resolved_by = resolver
        suggestion.save()

    return suggestion


def residence_trickle_tick() -> ResonanceDailyTickSummary:
    """Daily residence-trickle tick (Spec C §5.3).

    Iterates sheets with a declared residence; for each matching
    (residence-tagged ∩ sheet-claimed) resonance, writes one ``TrickleAccrual`` row worth
    cfg.residence_daily_trickle_per_resonance. The trickle pays nothing on its own: it waits
    until an anima ritual harvests it (#5308), so a tick changes no balance.

    Per-character accruals are wrapped in nested atomic blocks so a single
    failure doesn't poison the whole tick. Non-residence sheets are skipped.
    ``residence_grants_issued`` on the summary counts the accrual rows written.
    """
    from world.magic.constants import TrickleSource  # noqa: PLC0415
    from world.magic.models import TrickleAccrual  # noqa: PLC0415

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
                    TrickleAccrual.objects.create(
                        character_sheet=sheet,
                        resonance=resonance,
                        amount=cfg.residence_daily_trickle_per_resonance,
                        source=TrickleSource.ROOM_RESIDENCE,
                        room_profile=rp,
                    )
                    grants_issued += 1
            except Exception:
                logger.exception("resonance trickle skipped a sheet (audit: was silent)")
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
          TrickleAccrual(
            character_sheet=sheet,
            resonance=thread.resonance,
            amount=trickle_for(item, item_facet, thread),
            source=TrickleSource.OUTFIT_TRICKLE,
            outfit_item_facet=item_facet,
          )

    The trickle waits for the next anima ritual to harvest it (#5308); nothing is granted here.

    Returns: count of accrual rows written for this sheet.
    """
    from world.magic.constants import TrickleSource  # noqa: PLC0415
    from world.magic.models import TrickleAccrual  # noqa: PLC0415
    from world.magic.services.threads import thread_rung  # noqa: PLC0415

    config = get_resonance_gain_config()
    base = config.outfit_daily_trickle_per_item_resonance
    grants_issued = 0
    rung_factors = None  # the OUTFIT_TRICKLE lane, loaded once when a threaded facet needs it

    for item_facet in sheet.character.equipped_items.iter_item_facets():
        item = item_facet.item_instance
        item_q_mult = item.quality_tier.stat_multiplier if item.quality_tier else Decimal(1)
        attach_q_mult = item_facet.attachment_quality_tier.stat_multiplier

        thread = sheet.character.threads.thread_for_facet(item_facet.facet)
        if thread is None:
            continue

        # The OUTFIT_TRICKLE lane's row at the thread's rung (thread_rung, #5091); a thread
        # below rung 1 reads the rung 1 row (#5093). The seeded rows are the rung itself.
        if rung_factors is None:
            rung_factors = load_baselines(ModifierLane.OUTFIT_TRICKLE)
        level_factor = rung_factors.baseline(max(1, thread_rung(thread.level)))
        amount = int(base * item_q_mult * attach_q_mult * level_factor)
        if amount <= 0:
            continue

        TrickleAccrual.objects.create(
            character_sheet=sheet,
            resonance=thread.resonance,
            amount=amount,
            source=TrickleSource.OUTFIT_TRICKLE,
            outfit_item_facet=item_facet,
        )
        grants_issued += 1

    return grants_issued


def waiting_trickles(sheet: CharacterSheet) -> dict[int, int]:
    """Resonance id to what ``sheet``'s days have piled up there and no anima ritual has
    harvested yet (#5308). The sum of the unharvested ``TrickleAccrual`` rows; the rows are
    the only store, so nothing here can drift from what a ritual will harvest.
    """
    from django.db.models import Sum  # noqa: PLC0415

    from world.magic.models import TrickleAccrual  # noqa: PLC0415

    rows = (
        TrickleAccrual.objects.filter(character_sheet=sheet, harvested_at__isnull=True)
        .values_list("resonance_id")
        .annotate(total=Sum("amount"))
    )
    return dict(rows)


def outfit_trickle_tick() -> int:
    """Outfit trickle tick (Spec D §5.1).

    Driven from the *narrow* side: a sheet can only earn an outfit trickle
    through ``thread_for_facet``, so a sheet owning no active FACET-kind Thread
    would walk its whole wardrobe and grant nothing. Selecting those owners up
    front is therefore behaviour-identical to scanning every CharacterSheet,
    and turns a per-playerbase scan into work proportional to the (much
    smaller) set of characters who have actually woven a facet thread.

    Skips protagonism-locked sheets. Each sheet is processed in its own atomic
    block so a single failure does not poison the whole tick.

    Returns: total count of grants issued across all sheets.
    """
    from world.magic.constants import TargetKind  # noqa: PLC0415
    from world.magic.models import Thread  # noqa: PLC0415

    total_grants = 0

    # Matches CharacterThreadHandler._all's notion of "active" (non-retired),
    # so the narrowing cannot skip a sheet the per-sheet pass would have paid out.
    facet_thread_owner_ids = set(
        Thread.objects.filter(
            target_kind=TargetKind.FACET,
            retired_at__isnull=True,
        ).values_list("owner_id", flat=True)
    )
    if not facet_thread_owner_ids:
        return 0

    sheets = CharacterSheet.objects.filter(pk__in=facet_thread_owner_ids)
    for sheet in sheets.iterator():
        if sheet.is_protagonism_locked:
            continue
        try:
            with transaction.atomic():
                total_grants += outfit_daily_trickle_for_character(sheet)
        except Exception:
            logger.exception("Outfit resonance trickle failed for sheet %s", sheet.pk)
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

    Finds all endorsers with any unsettled, accepted PoseEndorsement rows, calls
    settle_weekly_pot on each. Per-endorser settlement wrapped in try/except
    so a single failure doesn't poison the whole tick.
    """
    endorser_ids = (
        PoseEndorsement.objects.filter(settled_at__isnull=True, awaiting_acceptance=False)
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
        except Exception:
            logger.exception("resonance grant loop skipped an entry (audit: was silent)")
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
