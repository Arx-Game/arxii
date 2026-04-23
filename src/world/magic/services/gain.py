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

from django.db import transaction
from evennia.accounts.models import AccountDB

from evennia_extensions.models import RoomProfile
from world.character_sheets.models import CharacterSheet
from world.magic.models import (
    Resonance,
    ResonanceGainConfig,
    RoomAuraProfile,
    RoomResonance,
)


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
    aura = getattr(room_profile, "room_aura_profile", None)  # noqa: GETATTR_LITERAL — OneToOne reverse accessor, raised RelatedObjectDoesNotExist if missing
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
