from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.functional import cached_property
from evennia.utils.idmapper.models import SharedMemoryModel

from core.managers import ArxSharedMemoryManager
from evennia_extensions.mixins import CachedPropertiesMixin, RelatedCacheClearingMixin
from world.magic.constants import LedgerOp, PowerStage
from world.scenes.constants import (
    DecisiveCheckMarkerStatus,
    InteractionMode,
    InteractionVisibility,
    PersonaType,
    PoseKind,
    ReactionValence,
    RoundStatus,
    ScenePrivacyMode,
    SceneRoundMode,
    SceneRoundParticipantStatus,
    SceneRoundStartReason,
    SummaryAction,
    SummaryStatus,
)
from world.scenes.managers import InteractionManager, SceneManager
from world.scenes.round_models import AbstractRound
from world.societies.constants import FameTier

if TYPE_CHECKING:
    from evennia.accounts.models import AccountDB

    from world.scenes.legend_murmur_handler import PersonaLegendMurmurHandler
    from world.scenes.persona_handlers import ScenePersonaHandler
    from world.scenes.place_models import InteractionReceiver

# Lazy model references (Django app_label.ModelName), extracted to satisfy S1192.
CHARACTER_SHEET_MODEL = "character_sheets.CharacterSheet"
INTERACTION_MODEL = "scenes.Interaction"
PLAYER_DATA_MODEL = "evennia_extensions.PlayerData"
SCENE_ROUND_PARTICIPANT_MODEL = "scenes.SceneRoundParticipant"
ROSTER_TENURE_MODEL = "roster.RosterTenure"


class Scene(CachedPropertiesMixin, SharedMemoryModel):
    """
    A scene is a recorded roleplay session that captures messages from participants.
    Similar to dominion.RPEvent but focused on message recording and scene management.
    """

    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True)
    location = models.ForeignKey(
        "objects.ObjectDB",
        blank=True,
        null=True,
        related_name="scenes_held",
        on_delete=models.SET_NULL,
        help_text="The room/location where this scene takes place",
    )
    date_started = models.DateTimeField(auto_now_add=True)
    date_finished = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True, db_index=True)
    privacy_mode = models.CharField(
        max_length=20,
        choices=ScenePrivacyMode.choices,
        default=ScenePrivacyMode.PUBLIC,
        help_text="Privacy floor for all interactions in this scene",
    )
    summary = models.TextField(
        blank=True,
        help_text="Scene summary — required for ephemeral scenes, optional for others",
    )
    summary_status = models.CharField(
        max_length=20,
        choices=SummaryStatus.choices,
        default=SummaryStatus.DRAFT,
        blank=True,
        help_text="Status of collaborative summary (mainly for ephemeral scenes)",
    )
    event = models.ForeignKey(
        "events.Event",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="scenes",
        help_text="The scheduled event that spawned this scene, if any",
    )

    participants = models.ManyToManyField(
        "accounts.AccountDB",
        through="SceneParticipation",
        related_name="participated_scenes",
        help_text="Accounts that have participated in this scene",
    )

    objects = SceneManager()

    class Meta:
        ordering = ["-date_started"]
        constraints = [
            models.UniqueConstraint(
                fields=["event"],
                condition=models.Q(event__isnull=False, is_active=True),
                name="unique_active_scene_per_event",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.date_started})"

    @property
    def is_finished(self) -> bool:
        return self.date_finished is not None

    @property
    def is_public(self) -> bool:
        """Backwards-compatible check — scene is public if privacy mode is PUBLIC."""
        return self.privacy_mode == ScenePrivacyMode.PUBLIC

    @property
    def is_ephemeral(self) -> bool:
        """Whether this scene is ephemeral (content never stored)."""
        return self.privacy_mode == ScenePrivacyMode.EPHEMERAL

    @cached_property
    def participations_cached(self) -> list[SceneParticipation]:
        """Return participations for this scene, cached."""
        return list(self.participations.select_related("account"))

    @property
    def persona_handler(self) -> ScenePersonaHandler:
        """Return a lightweight persona handler for this scene."""
        from world.scenes.persona_handlers import ScenePersonaHandler  # noqa: PLC0415

        return ScenePersonaHandler(self)

    def is_owner(self, account: AccountDB | None) -> bool:
        """Return True if ``account`` owns this scene."""
        if account is None:
            return False
        return any(
            part.account_id == account.id and part.is_owner for part in self.participations_cached
        )

    def has_character_present(self, character_ids: set[int]) -> bool:
        """Check if any of the given characters are at this scene's location.

        Uses the room's contents cache (Evennia identity map) instead of
        querying. No DB hit if the room is already loaded.
        """
        if not self.location:
            return False
        present_ids = {ob.pk for ob in self.location.contents}
        return bool(present_ids & set(character_ids))

    def is_gm(self, account: AccountDB | None) -> bool:
        """Check if the given account is a GM of this scene.

        Uses participations_cached to avoid a query.
        """
        if account is None:
            return False
        return any(p.account_id == account.pk and p.is_gm for p in self.participations_cached)

    def is_viewable_by(self, account: AccountDB | None) -> bool:
        """Return True if ``account`` may view this scene.

        Mirrors ``Scene.objects.viewable_by`` for a single instance. Uses
        ``participations_cached`` so it costs zero queries when the scene is
        already in the identity map (same approach as ``is_gm``/``is_owner``).
        """
        if self.is_public:
            return True
        if account is None or not account.is_authenticated:
            return False
        if account.is_staff:
            return True
        return any(p.account_id == account.pk for p in self.participations_cached)

    def _validate_privacy_against_room(self) -> None:
        """Enforce the scene privacy<->room-publicness invariant (#1287).

        A publicly-listed room may host only PUBLIC scenes; PRIVATE/EPHEMERAL
        scenes leak in a space anyone can enter. No location, a room with no
        RoomProfile, and non-public rooms are unconstrained. One-directional.
        See docs/systems/scenes.md.
        """
        from evennia_extensions.models import room_is_publicly_listed  # noqa: PLC0415

        if self.location_id is None or self.privacy_mode == ScenePrivacyMode.PUBLIC:
            return
        if room_is_publicly_listed(self.location):
            raise ValidationError(
                {
                    "privacy_mode": (
                        f"A {self.get_privacy_mode_display()} scene cannot be held "
                        "in a publicly-listed room; only PUBLIC scenes are allowed there."
                    )
                }
            )

    def clean(self) -> None:
        super().clean()
        self._validate_privacy_against_room()

    def save(self, *args: object, **kwargs: object) -> None:
        self._validate_privacy_against_room()
        super().save(*args, **kwargs)

    def finish_scene(self) -> None:
        """Mark the scene as finished and stop recording new messages"""
        if not self.is_finished:
            self.date_finished = timezone.now()
            self.is_active = False
            self.save()
            from world.scenes.power_ledger_services import purge_scene_power_ledger  # noqa: PLC0415

            purge_scene_power_ledger(self)

            # Very Attracted (the temporary allure double from a flirt/seduce) lasts to end of
            # scene OR ~2 IC days, whichever first (#1697) — clear it for participants now.
            from world.relationships.services import clear_very_attracted  # noqa: PLC0415

            sheets = {
                persona.character_sheet
                for persona in self.persona_handler.active_participant_personas()
            }
            clear_very_attracted(sheets)


class SceneParticipation(RelatedCacheClearingMixin, SharedMemoryModel):
    """
    Links accounts to scenes they participate in
    """

    scene = models.ForeignKey(
        Scene,
        on_delete=models.CASCADE,
        related_name="participations",
    )
    account = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.CASCADE,
        related_name="scene_participations",
    )
    is_gm = models.BooleanField(default=False)
    is_owner = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)
    left_at = models.DateTimeField(blank=True, null=True)

    related_cache_fields = ["scene"]

    class Meta:
        unique_together = ["scene", "account"]


class SceneUnseenObserver(SharedMemoryModel):
    """An active unseen-observation grant on a scene (#1225).

    Tracks that *some* mechanism (physical concealment today; a future scrying/
    remote-viewing feature later) lets `observer` witness `scene` without other
    participants' characters being aware. `source_label` is an admin/debugging hint,
    never surfaced to players — the OOC notice this powers is deliberately
    identity-free (see world.scenes.services.register_unseen_observer).
    """

    scene = models.ForeignKey(
        Scene,
        on_delete=models.CASCADE,
        related_name="unseen_observers",
    )
    observer = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="unseen_observations",
    )
    source_label = models.CharField(
        max_length=100,
        help_text="Admin/debugging hint for what granted this (e.g. 'concealment'). "
        "Never shown to players — the OOC notice never reveals identity or mechanism.",
    )
    started_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["scene", "observer"],
                name="unique_unseen_observer_per_scene",
            ),
        ]

    def __str__(self) -> str:
        return f"unseen observer on {self.scene_id} ({self.source_label})"


class Persona(CachedPropertiesMixin, SharedMemoryModel):
    """A face the character shows the world.

    Every character has at least one primary persona (their 'real' identity).
    Established personas are persistent alter egos with their own reputation
    and relationships. Temporary personas are throwaway disguises.
    """

    character_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="personas",
        help_text="The character sheet this persona belongs to.",
    )
    name = models.CharField(max_length=255, help_text="Display name for this persona")
    colored_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Name with color formatting codes",
    )
    description = models.TextField(blank=True, help_text="Physical description text")
    # #1270 — the bio this face presents. The PRIMARY persona points at the sheet's
    # true_profile (the real bio); an established/cover persona may own its own Profile (a
    # fabricated bio) so it does not out itself with an empty one. Null falls back to the
    # sheet's true_profile.
    profile = models.ForeignKey(
        "character_sheets.Profile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="personas",
        help_text="The bio this persona presents (#1270); null ⇒ the sheet's true_profile.",
    )
    thumbnail_url = models.URLField(blank=True, max_length=500)
    thumbnail = models.ForeignKey(
        "evennia_extensions.Media",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="persona_thumbnails",
        help_text="Visual representation",
    )
    persona_type = models.CharField(
        max_length=20,
        choices=PersonaType.choices,
        default=PersonaType.TEMPORARY,
        help_text="PRIMARY = real identity, ESTABLISHED = persistent alter ego, "
        "TEMPORARY = throwaway disguise, ALTERNATE = an alternate self's persona "
        "(shapeshift/possession/past-life)",
    )
    is_fake_name = models.BooleanField(
        default=False,
        help_text="True when this persona obscures the character's identity",
    )
    is_system = models.BooleanField(
        default=False,
        db_index=True,
        help_text="OOC system/narrator/GM identity. Excluded from the persona "
        "picker (PersonaViewSet filters is_system=False); its authored "
        "interactions still display in the scene log.",
    )
    properties = models.ManyToManyField(
        "mechanics.Property",
        related_name="personas",
        blank=True,
        help_text="Neutral descriptive tags on this persona (e.g. masked-identity, "
        "abyssal), used by reactive examine-filters via has_property.",
    )

    # #676 Phase A: Renown system fields. Five prestige sources (denormalized
    # for cheap read), plus the cached total. Sources are updated event-driven
    # in subsequent phases (B+); Phase A just establishes the schema and the
    # cron decay infrastructure for fame. All fields default to 0; existing
    # personas don't need backfill.
    prestige_from_dwellings = models.BigIntegerField(
        default=0,
        help_text=(
            "Denormalized prestige from owned/tenanted dwellings (Phase D wires "
            "the polish-flow updates). Signed — can drop on decay or scandal."
        ),
    )
    prestige_from_items = models.BigIntegerField(
        default=0,
        help_text=(
            "Denormalized prestige from equipped/displayed items (Phase F wires "
            "the equipment-flow updates). Signed — can drop on item loss."
        ),
    )
    prestige_from_orgs = models.BigIntegerField(
        default=0,
        help_text=(
            "Denormalized prestige from org memberships (Phase C wires the "
            "rank-weighted outflow from each org). Signed."
        ),
    )
    prestige_from_deeds = models.BigIntegerField(
        default=0,
        help_text=(
            "Permanent accumulated prestige from Renown event deeds (Phase B "
            "wires the event-fire awards). Signed — rare scandal awards subtract."
        ),
    )
    prestige_from_fashion = models.BigIntegerField(
        default=0,
        help_text=(
            "Denormalized prestige from fashion presentations at events (#514). "
            "Recomputed from FashionPresentation acclaim. Signed."
        ),
    )
    total_prestige = models.BigIntegerField(
        default=0,
        help_text=(
            "Denormalized sum of the five prestige source fields. Updated "
            "whenever any source field is written. Signed."
        ),
    )
    fame_points = models.BigIntegerField(
        default=0,
        help_text=(
            "Current fame buffer for this persona. Event-augmented (renown "
            "fires + legend spreads) and cron-decayed (5 + 5% per IC day). "
            "Floors at 0. The derived fame_tier field is recomputed on every "
            "write to this field."
        ),
    )
    fame_tier = models.CharField(
        max_length=20,
        choices=FameTier.choices,
        default=FameTier.NORMAL,
        help_text=(
            "Derived display tier — Normal / Talked About / Celebrity / "
            "Household Name / World Famous. Recomputed whenever fame_points "
            "is written; UI reads this directly. Multiplier lookup lives in "
            "societies.constants.FAME_TIER_MULTIPLIERS."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet", "name"],
                name="unique_persona_name_per_character",
            ),
            models.UniqueConstraint(
                fields=["character_sheet"],
                condition=models.Q(persona_type="primary"),
                name="unique_primary_persona_per_character_sheet",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_persona_type_display()})"

    @property
    def is_established_or_primary(self) -> bool:
        """Whether this persona can have relationships, reputation, legend."""
        return self.persona_type in (PersonaType.PRIMARY, PersonaType.ESTABLISHED)

    @cached_property
    def legend_murmur(self) -> PersonaLegendMurmurHandler:
        """Cached handler for this persona's legend-murmur deed data (#2523)."""
        from world.scenes.legend_murmur_handler import PersonaLegendMurmurHandler  # noqa: PLC0415

        return PersonaLegendMurmurHandler(self)

    def display_ic(self) -> str:
        """Persona name only — what IC observers see."""
        return self.name

    def display_with_history(self) -> str:
        """Add tenure disambiguation when useful.

        - No tenure or first tenure: 'Bob'
        - Later tenure (player_number > 1), name differs from character:
          'Bob (Thomas #2)'
        - Later tenure, name matches character: 'Thomas #2' (collapse redundancy)
        """
        sheet = self.character_sheet
        if sheet is None:
            return self.name
        try:
            entry = sheet.roster_entry
        except ObjectDoesNotExist:
            return self.name
        tenure = entry.current_tenure if entry else None
        if tenure is None or tenure.player_number == 1:
            return self.name
        char_name = sheet.character.db_key
        if self.name == char_name:
            return f"{char_name} #{tenure.player_number}"
        return f"{self.name} ({char_name} #{tenure.player_number})"

    def display_to_staff(self) -> str:  # noqa: PLR0911
        """Full staff context — persona, character, player number, account.

        - First tenure: 'Bob (Thomas, played by Fred)'
        - Later tenure: 'Bob (Thomas #2, played by Fred)'
        - No current player: 'Bob (Thomas — no current player)'
        """
        sheet = self.character_sheet
        if sheet is None:
            return self.name
        try:
            entry = sheet.roster_entry
        except ObjectDoesNotExist:
            return self.name
        if entry is None:
            return self.name
        char_name = sheet.character.db_key
        tenure = entry.current_tenure
        if tenure is None:
            return f"{self.name} ({char_name} — no current player)"
        if tenure.player_data is None or tenure.player_data.account is None:
            return f"{self.name} ({char_name} — no current player)"
        account_name = tenure.player_data.account.username
        if tenure.player_number == 1:
            return f"{self.name} ({char_name}, played by {account_name})"
        return f"{self.name} ({char_name} #{tenure.player_number}, played by {account_name})"


class PersonaDiscovery(SharedMemoryModel):
    """Records that a character discovered two personas are the same person.

    Stores only raw discovery pairs. A service function handles resolution
    logic (what name to display, transitive chains, etc.).
    """

    persona = models.ForeignKey(
        Persona,
        on_delete=models.PROTECT,
        related_name="discoveries_as_subject",
        help_text="The persona that was identified/encountered (lower PK for normalization)",
    )
    linked_to = models.ForeignKey(
        Persona,
        on_delete=models.PROTECT,
        related_name="discoveries_as_linked",
        help_text="The persona they were discovered to be the same person as (higher PK)",
    )
    discovered_by = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="persona_discoveries",
        help_text="The character who figured out these two personas are the same person",
    )
    discovered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["persona", "linked_to", "discovered_by"],
                name="unique_persona_discovery",
            ),
            models.CheckConstraint(
                check=models.Q(persona_id__lt=models.F("linked_to_id")),
                name="persona_discovery_normalized_order",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.discovered_by} knows {self.persona.name} = {self.linked_to.name}"

    def clean(self) -> None:
        super().clean()
        if (
            self.persona_id is not None
            and self.linked_to_id is not None
            and self.persona_id > self.linked_to_id
        ):
            self.persona_id, self.linked_to_id = self.linked_to_id, self.persona_id

    def save(self, *args: object, **kwargs: object) -> None:
        if (
            self.persona_id is not None
            and self.linked_to_id is not None
            and self.persona_id > self.linked_to_id
        ):
            self.persona_id, self.linked_to_id = self.linked_to_id, self.persona_id
        super().save(*args, **kwargs)


class Block(SharedMemoryModel):
    """One player blocking another, persona-scoped by default (#1278).

    The blocker (``owner``) blocks ``blocked_player``. By default the coded block is the exact
    ``blocker_persona`` ↔ ``blocked_persona`` pair; ``account_level=True`` is the blocker's
    conscious opt-in to have *all* of their characters block the target. Keyed on PlayerData
    (account), so the block follows the *person*: a character re-rostered to a different player
    no longer matches, and the original player returning re-activates it.

    **Anti-derivation (#1278):** coded enforcement is for the exact blocked pair (or account-level
    blocker side) only. The blocked player's *other* identities get a separate awareness + staff
    flag layer — never coded effects the blocker could observe and use to derive their alts.

    **Cron-delayed clear:** lifting a block sets ``pending_removal_at`` to a future cron tick; the
    block stays active until then (kills the lift → snipe → re-block pattern), and a cron finalizes
    removal. Slice 1 is the model + resolution; the visibility/interaction wiring, the Mute sibling,
    the awareness/flag layer, and the cron job are follow-up slices.

    Supersedes the unwired account-level ``evennia_extensions.PlayerBlockList`` (removed).
    """

    owner = models.ForeignKey(
        PLAYER_DATA_MODEL,
        on_delete=models.CASCADE,
        related_name="blocks_made",
        help_text="The player who created the block (the blocker).",
    )
    blocked_player = models.ForeignKey(
        PLAYER_DATA_MODEL,
        on_delete=models.CASCADE,
        related_name="blocks_received",
        help_text="The player being blocked.",
    )
    blocker_persona = models.ForeignKey(
        Persona,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="blocks_from",
        help_text="The face the blocker blocked from; null when account_level (all their faces).",
    )
    blocked_persona = models.ForeignKey(
        Persona,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="blocks_against",
        help_text="The face that was blocked (shown on the blocker's block list).",
    )
    account_level = models.BooleanField(
        default=False,
        help_text="Opt-in: all of the blocker's characters block the target.",
    )
    pending_removal_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "When a lifted block finalizes (cron). The block stays active until then; "
            "null means it has not been lifted."
        ),
    )
    reason = models.CharField(max_length=200, blank=True, help_text="Optional reason.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "blocked_player", "blocker_persona", "blocked_persona"],
                name="unique_block_pair",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.owner} blocks {self.blocked_player}"

    @property
    def is_active(self) -> bool:
        """Active unless a lift grace period has already elapsed."""
        return self.pending_removal_at is None or self.pending_removal_at > timezone.now()


class Friendship(SharedMemoryModel):
    """An OOC friend designation — a trusted-RP-partner list, Block's positive twin (#1727).

    This is an **out-of-character** list (MMO friends-list style: people you like, have chemistry
    with, want to keep playing), **entirely separate from the IC relationship tracker** — a friend
    is NOT "positive affection". It drives login/logoff watch alerts and the ``FRIENDS_WHITELIST``
    consent mode (#1698).

    **Symmetric per-tenure scoping** — a friendship binds *this player's run of character A*
    (``friender_tenure``) to *that player's run of character B* (``friend_tenure``). Tenure on both
    sides makes it **re-roster-safe both ways** (the bond dies when either character is re-rostered
    to a different player) and **alt-private** (friending from character A never marks your other
    characters, and the target is a character, not the person behind it — neither side outs alts).
    "Friend from all my characters" fans out into one row per *your current tenure*, each
    independently removable.
    """

    friender_tenure = models.ForeignKey(
        ROSTER_TENURE_MODEL,
        on_delete=models.CASCADE,
        related_name="friendships_made",
        help_text="The friender's tenure (this player's run of the character that friended).",
    )
    friend_tenure = models.ForeignKey(
        ROSTER_TENURE_MODEL,
        on_delete=models.CASCADE,
        related_name="friendships_received",
        help_text="The friended character's tenure (a specific player's run of that character).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["friender_tenure", "friend_tenure"], name="unique_friendship"
            ),
        ]
        indexes = [models.Index(fields=["friend_tenure"])]

    def __str__(self) -> str:
        return f"{self.friender_tenure} → {self.friend_tenure}"


class Rivalry(SharedMemoryModel):
    """A one-way IC rivalry declaration — the antagonism-consent counterpart to Friendship (#2170).

    A player marks another character their rival. It drives the ``RIVALS`` consent mode: a rival
    may aim the antagonism categories at you that you've opened to rivals. **Double opt-in** — a
    *mutual* rivalry (both directions declared) is required for the RIVALS gate to pass, so no one
    is dragged into a rivalry one-sidedly (see ``world.scenes.friend_services.is_rival``).

    **Symmetric per-tenure scoping** (mirrors ``Friendship``): binds *this player's run of A*
    (``rivaler_tenure``) to *that player's run of B* (``rival_tenure``) — re-roster-safe both ways
    and alt-private (declaring a rival from character A never marks your other characters, and the
    target is a character, not the person behind it).
    """

    rivaler_tenure = models.ForeignKey(
        ROSTER_TENURE_MODEL,
        on_delete=models.CASCADE,
        related_name="rivalries_made",
        help_text="The declarer's tenure (this player's run of the character that named a rival).",
    )
    rival_tenure = models.ForeignKey(
        ROSTER_TENURE_MODEL,
        on_delete=models.CASCADE,
        related_name="rivalries_received",
        help_text="The named rival's tenure (a specific player's run of that character).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["rivaler_tenure", "rival_tenure"], name="unique_rivalry"
            ),
        ]
        indexes = [models.Index(fields=["rival_tenure"])]

    def __str__(self) -> str:
        return f"{self.rivaler_tenure} ⚔ {self.rival_tenure}"


class Mute(SharedMemoryModel):
    """One player filtering a persona out of their own view (#1278) — the lighter sibling of Block.

    Unlike Block, Mute is **one-way, persona-scoped, and purely cosmetic**: it only changes what the
    muter sees, the muted player is never aware, and there is no interaction ban or sheet lockout.
    The muter chooses whether it hides the persona's IC content, OOC content, or both. Fully
    reversible. No anti-derivation concern — nothing about it is observable to the muted party.
    """

    owner = models.ForeignKey(
        PLAYER_DATA_MODEL,
        on_delete=models.CASCADE,
        related_name="mutes_made",
        help_text="The player who muted (the muter).",
    )
    muted_persona = models.ForeignKey(
        Persona,
        on_delete=models.CASCADE,
        related_name="muted_by",
        help_text="The face the muter no longer wants to see.",
    )
    mute_ic = models.BooleanField(default=True, help_text="Hide this persona's IC content.")
    mute_ooc = models.BooleanField(default=True, help_text="Hide this persona's OOC content.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "muted_persona"], name="unique_mute"),
        ]

    def __str__(self) -> str:
        return f"{self.owner} mutes {self.muted_persona.name}"


class BlockContactFlag(SharedMemoryModel):
    """A blocked player attempted contact with the blocker — flagged for staff (#1278).

    The coded block prevents the *exact* blocked pair; a blocked player using **another identity**
    to reach the blocker is circumvention, which the anti-derivation rule deliberately does NOT
    code-prevent (that would leak the alt). Instead the attempt is recorded here for staff — who
    see real identities — with **zero signal to either player**. Anchored on accounts + the personas
    worn so staff can derive the full identity chain.
    """

    blocker_account = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.CASCADE,
        related_name="+",
        help_text="The account that did the blocking (the target of the contact attempt).",
    )
    blocked_account = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.CASCADE,
        related_name="+",
        help_text="The blocked account that attempted contact (the initiator).",
    )
    initiator_persona = models.ForeignKey(
        Persona,
        on_delete=models.CASCADE,
        related_name="+",
        help_text="The face the blocked player used to attempt contact.",
    )
    target_persona = models.ForeignKey(
        Persona,
        on_delete=models.CASCADE,
        related_name="+",
        help_text="The blocker's face they tried to contact.",
    )
    scene = models.ForeignKey(
        Scene,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="The scene the attempt occurred in, if any.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    resolved = models.BooleanField(
        default=False, help_text="Whether staff have reviewed this flag."
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"contact-flag: {self.blocked_account_id} → {self.blocker_account_id}"


class Interaction(SharedMemoryModel):
    """An atomic IC interaction — one writer, one piece of content, one audience.

    Created automatically whenever a character poses, emits, says, whispers,
    shouts, or takes a mechanical action. The universal building block of RP
    recording. Scenes are optional containers; interactions exist independently.
    """

    persona = models.ForeignKey(
        Persona,
        on_delete=models.PROTECT,
        related_name="interactions_written",
        help_text="How the writer appeared at this moment. Always set — every "
        "interaction has a persona, even if it's just the character's primary persona.",
    )
    writer_account = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "The account that wrote this, pinned at creation (#1219). Party identity for "
            "private-content log visibility — stable across persona hand-offs, so an "
            "inheriting player is never treated as a party to the prior player's whispers."
        ),
    )
    scene = models.ForeignKey(
        Scene,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interactions",
        help_text="Scene container if one was active",
    )
    place = models.ForeignKey(
        "scenes.Place",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interactions",
        help_text="Sub-location where this interaction occurred",
    )
    target_personas = models.ManyToManyField(
        Persona,
        blank=True,
        through="InteractionTargetPersona",
        related_name="interactions_targeted",
        help_text="Explicit IC targets for thread derivation",
    )
    content = models.TextField(
        help_text="The actual written text of the interaction",
    )
    mode = models.CharField(
        max_length=20,
        choices=InteractionMode.choices,
        default=InteractionMode.POSE,
        help_text="The type of IC interaction",
    )
    visibility = models.CharField(
        max_length=20,
        choices=InteractionVisibility.choices,
        default=InteractionVisibility.DEFAULT,
        help_text="Privacy override — can only escalate, never reduce",
    )
    pose_kind = models.CharField(
        max_length=16,
        choices=PoseKind.choices,
        default=PoseKind.STANDARD,
        db_index=True,
        help_text=(
            "Classifies the pose as standard, entry, or departure. "
            "Set by the +enter command (future) or scene-entry hook. "
            "Spec C reads ENTRY to filter scene-entry-endorsement targets."
        ),
    )
    vote_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of weekly votes (nominations for Memorable Poses)",
    )
    strain_committed = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Canonical post-resolution audit of strain the player actually "
            "committed for this action. Populated for both clash and non-clash."
        ),
    )
    fury_committed = models.ForeignKey(
        "magic.FuryTier",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Post-resolution audit of the realized Fury tier (clash + non-clash).",
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = InteractionManager()

    class Meta:
        # NO ordering — cursor pagination handles it. Default ordering on a
        # partitioned table forces cross-partition merge-sorts on every query.
        indexes = [
            models.Index(fields=["persona", "timestamp"]),
            models.Index(fields=["scene", "timestamp"]),
            # Fast exclusion of very_private for staff queryset
            models.Index(
                fields=["timestamp"],
                name="interaction_very_private_idx",
                condition=models.Q(visibility="very_private"),
            ),
            # Organic grid RP (no scene) queries
            models.Index(
                fields=["timestamp"],
                name="interaction_no_scene_idx",
                condition=models.Q(scene__isnull=True),
            ),
        ]
        constraints = [
            # Mirrors the CHECK (vote_count >= 0) in the partition SQL so
            # makemigrations stays in sync with the raw DDL.
            models.CheckConstraint(
                check=models.Q(vote_count__gte=0),
                name="interaction_vote_count_nonnegative",
            ),
        ]

    def __str__(self) -> str:
        content_preview = str(self.content)[:50]
        return f"{self.persona.name}: {content_preview}..."

    @property
    def cached_receivers(self) -> list[InteractionReceiver]:
        """Receiver records. Uses Prefetch(to_attr=) when available, else queries."""
        try:
            return self._cached_receivers
        except AttributeError:
            from world.scenes.place_models import InteractionReceiver  # noqa: PLC0415

            return list(InteractionReceiver.objects.filter(interaction=self))

    @cached_receivers.setter
    def cached_receivers(self, value: list[InteractionReceiver]) -> None:
        """Allow Prefetch(to_attr='cached_receivers') to set this."""
        self._cached_receivers = value

    @property
    def cached_target_personas(self) -> list[Persona]:
        """Target personas. Uses Prefetch(to_attr=) when available, else queries."""
        try:
            return self._cached_target_personas
        except AttributeError:
            return list(self.target_personas.all())

    @cached_target_personas.setter
    def cached_target_personas(self, value: list[Persona]) -> None:
        """Allow Prefetch(to_attr='cached_target_personas') to set this."""
        self._cached_target_personas = value

    @property
    def cached_favorites(self) -> list[InteractionFavorite]:
        """Favorites. Uses Prefetch(to_attr=) when available, else queries."""
        try:
            return self._cached_favorites
        except AttributeError:
            return list(self.favorites.all())

    @cached_favorites.setter
    def cached_favorites(self, value: list[InteractionFavorite]) -> None:
        """Allow Prefetch(to_attr='cached_favorites') to set this."""
        self._cached_favorites = value

    @property
    def cached_reactions(self) -> list[InteractionReaction]:
        """Reactions. Uses Prefetch(to_attr=) when available, else queries."""
        try:
            return self._cached_reactions
        except AttributeError:
            return list(self.reactions.all())

    @cached_reactions.setter
    def cached_reactions(self, value: list[InteractionReaction]) -> None:
        """Allow Prefetch(to_attr='cached_reactions') to set this."""
        self._cached_reactions = value

    @property
    def cached_action_links(self) -> list[InteractionAction]:
        """InteractionAction bridge rows for this POSE. Uses Prefetch(to_attr=) when available."""
        try:
            return self._cached_action_links
        except AttributeError:
            return list(
                InteractionAction.objects.filter(pose=self).select_related("action_interaction")
            )

    @cached_action_links.setter
    def cached_action_links(self, value: list[InteractionAction]) -> None:
        """Allow Prefetch(to_attr='cached_action_links') to set this."""
        self._cached_action_links = value


class InteractionFavorite(SharedMemoryModel):
    """Private bookmark for a cherished RP moment.

    Purely private — no other player sees what you bookmarked. Social feedback
    (kudos, pose voting, reactions) is handled by separate systems.
    """

    interaction = models.ForeignKey(
        Interaction,
        on_delete=models.CASCADE,
        related_name="favorites",
        db_constraint=False,
        help_text="The bookmarked interaction",
    )
    timestamp = models.DateTimeField(
        help_text="Denormalized from interaction — required for composite FK "
        "with partitioned table",
    )
    roster_entry = models.ForeignKey(
        "roster.RosterEntry",
        on_delete=models.CASCADE,
        related_name="favorited_interactions",
        help_text="The player who bookmarked this",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["interaction", "roster_entry"],
                name="unique_favorite_per_interaction",
            ),
        ]

    def __str__(self) -> str:
        return f"Favorite: interaction {self.interaction_id} by {self.roster_entry}"


class InteractionReaction(SharedMemoryModel):
    """Emoji reaction on an interaction.

    Originally intended as a temporary bridge model, but now fully integrated
    with the API layer (viewset, serializer, filters), frontend components,
    admin, factories, and tests. #2161 resolved the "will this get merged into
    kudos/voting?" question raised in this docstring's earlier revisions:
    reactions stay their own axis (see ADR-0115) — expression + an ambient
    relationship bump (``ReactionEmoji.valence``) — distinct from kudos
    (graciousness, ``award_kudos``) and votes (popularity/ranking,
    ``WeeklyVote``). No migration is planned; this model is the permanent
    home for emoji reactions, not a bridge.
    """

    interaction = models.ForeignKey(
        Interaction,
        on_delete=models.CASCADE,
        related_name="reactions",
        db_constraint=False,
        help_text="The interaction being reacted to",
    )
    timestamp = models.DateTimeField(
        help_text="Denormalized from interaction for composite FK with partitioned table",
    )
    account = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.CASCADE,
        related_name="interaction_reactions",
    )
    emoji = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["interaction", "account", "emoji"],
                name="unique_interaction_reaction",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.account} reacted {self.emoji} to interaction {self.interaction_id}"


class ReactionEmoji(SharedMemoryModel):
    """Staff-editable catalog of reaction emoji and their relationship valence (#1699).

    Valence NEUTRAL = cosmetic only (the pre-#1699 behavior). Nonzero valence
    additionally fires an ambient relationship bump at the pose's author.
    Playtest decides which emoji survive — that's a data edit here, not a
    deploy.
    """

    emoji = models.CharField(max_length=32, unique=True)
    valence = models.SmallIntegerField(
        choices=ReactionValence.choices,
        default=ReactionValence.NEUTRAL,
        help_text="+1 fires a positive relationship bump, -1 negative, 0 cosmetic only",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive emoji disappear from the web picker without deleting history",
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "emoji"]

    def __str__(self) -> str:
        return f"{self.emoji} ({self.get_valence_display()})"


class InteractionTargetPersona(SharedMemoryModel):
    """Explicit through model for interaction target personas.

    Needed for composite FK compatibility with partitioned Interaction table.
    """

    interaction = models.ForeignKey(
        Interaction,
        on_delete=models.CASCADE,
        related_name="interaction_targets",
        db_constraint=False,
    )
    timestamp = models.DateTimeField(
        help_text="Denormalized from interaction for partitioned table FK",
    )
    persona = models.ForeignKey(
        Persona,
        on_delete=models.CASCADE,
        related_name="targeted_in_interactions",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["interaction", "persona"],
                name="unique_target_per_interaction",
            ),
        ]


class InteractionAction(SharedMemoryModel):
    """Links a POSE Interaction to the ACTION Interaction(s) it elaborates.

    Pattern A from the unified-combat-ui spec: the bridge points at the
    ACTION-mode Interaction (not the underlying CombatRoundAction /
    ClashContribution directly). The ACTION Interaction is the polymorphic
    join point — different mechanical action types still reach a uniform
    bridge target without contenttypes.
    """

    pose = models.ForeignKey(
        INTERACTION_MODEL,
        on_delete=models.CASCADE,
        related_name="action_links",
        db_constraint=False,
        help_text="The POSE Interaction that elaborates the action(s).",
    )
    action_interaction = models.ForeignKey(
        INTERACTION_MODEL,
        on_delete=models.CASCADE,
        related_name="pose_links",
        db_constraint=False,
        help_text="The ACTION Interaction being elaborated.",
    )
    ordering = models.PositiveSmallIntegerField(
        default=0,
        help_text="Display order within the pose (low values render first).",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["pose", "action_interaction"],
                name="unique_action_link_per_pose",
            ),
        ]
        indexes = [
            models.Index(fields=["pose", "ordering"]),
            models.Index(fields=["action_interaction"]),
        ]

    def __str__(self) -> str:
        return f"{self.pose_id} ↔ {self.action_interaction_id}"

    def clean(self) -> None:
        super().clean()
        # NOTE: Django does not call clean() on save(). Callers (e.g. the
        # Phase 2 auto-link service) must invoke full_clean() before save()
        # to enforce these mode invariants.
        if self.pose_id is not None and self.pose.mode != InteractionMode.POSE:
            raise ValidationError({"pose": "Bridge pose must be a POSE-mode Interaction."})
        if (
            self.action_interaction_id is not None
            and self.action_interaction.mode != InteractionMode.ACTION
        ):
            raise ValidationError(
                {"action_interaction": "Linked target must be an ACTION-mode Interaction."}
            )


class InteractionPowerLedgerEntry(SharedMemoryModel):
    """One persisted stage entry of a cast's power ledger.

    Child of the ACTION-mode Interaction the cast/action resolved into. The
    transient ``world.magic.types.power_ledger.PowerLedger`` is copied here at
    resolution time so the per-stage breakdown is re-viewable from the log.
    FK uses ``db_constraint=False`` because ``scenes_interaction`` is partitioned.
    """

    interaction = models.ForeignKey(
        INTERACTION_MODEL,
        on_delete=models.CASCADE,
        related_name="power_ledger_entries",
        db_constraint=False,
        help_text="The ACTION-mode Interaction this ledger entry belongs to.",
    )
    ordering = models.PositiveSmallIntegerField(
        default=0,
        help_text="0-based index preserving the ledger's stage order.",
    )
    stage = models.CharField(max_length=20, choices=PowerStage.choices)
    source_label = models.CharField(max_length=120)
    op = models.CharField(max_length=12, choices=LedgerOp.choices)
    amount = models.IntegerField(
        help_text="Signed delta (add) | whole percent (multiply) | target value (set).",
    )
    running_total = models.IntegerField(help_text="Cumulative power after this entry.")

    class Meta:
        ordering = ["ordering"]
        indexes = [models.Index(fields=["interaction", "ordering"])]

    def __str__(self) -> str:
        return f"{self.interaction_id} [{self.ordering}] {self.stage}={self.running_total}"


class SceneSummaryRevision(SharedMemoryModel):
    """A revision in the collaborative summary editing flow for ephemeral scenes.

    All author references use Persona (IC identity), never Account. Players
    editing a summary see 'Revised by The Masked Baron', not 'Revised by steve_2847'.
    """

    scene = models.ForeignKey(
        Scene,
        on_delete=models.CASCADE,
        related_name="summary_revisions",
        help_text="The ephemeral scene this revision belongs to",
    )
    persona = models.ForeignKey(
        Persona,
        on_delete=models.PROTECT,
        related_name="summary_revisions",
        help_text="Who submitted this revision (IC identity, never account)",
    )
    content = models.TextField(
        help_text="The summary text for this revision",
    )
    action = models.CharField(
        max_length=20,
        choices=SummaryAction.choices,
        help_text="Whether this is a submission, edit, or agreement",
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.persona.name} {self.action} summary for {self.scene.name}"


class SceneCheckModifier(SharedMemoryModel):
    """
    Defines how a scene's surroundings modify a specific check type.

    Authors use this to express environmental fiction mechanically — a dark
    dungeon imposes a -10 Perception penalty; sacred ground grants +5 to Faith
    checks.  One row per (scene, check_type) pair; multiple check types on the
    same scene each get their own row.

    Surface choice: FK to Scene (not ObjectDB/location) because:
    - Scene is the encapsulating roleplay session already passed by
      combat/scene callers via collect_check_modifiers(scene=...).
    - Location (ObjectDB) is too broad — any game object, not just rooms.
    - A scene represents the active *context* in which a check happens,
      which is exactly what surroundings modifiers should attach to.

    Mirrors ConditionCheckModifier: FK check_type, IntegerField modifier_value,
    UniqueConstraint per (scene, check_type).
    """

    scene = models.ForeignKey(
        Scene,
        on_delete=models.CASCADE,
        related_name="check_modifiers",
        help_text="The scene whose surroundings this modifier describes",
    )
    check_type = models.ForeignKey(
        "checks.CheckType",
        on_delete=models.CASCADE,
        related_name="scene_check_modifiers",
        help_text="The check type this modifier applies to",
    )
    modifier_value = models.IntegerField(
        help_text="Flat modifier (positive = bonus, negative = penalty)",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["scene", "check_type"],
                name="scene_check_modifier_unique_scene_check_type",
            ),
        ]

    def __str__(self) -> str:
        sign = "+" if self.modifier_value >= 0 else ""
        return f"{self.scene.name}: {sign}{self.modifier_value} to {self.check_type.name}"


class SceneRound(AbstractRound):
    """A non-combat round/turn structure anchored to a room.

    Mirrors CombatEncounter's lifecycle without coupling to combat. One active
    (non-completed) round per room.
    """

    room = models.ForeignKey(
        "objects.ObjectDB",
        on_delete=models.PROTECT,
        related_name="scene_rounds",
        help_text="Room the round takes place in (mirrors CombatEncounter.room).",
    )
    scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scene_rounds",
    )
    start_reason = models.CharField(
        max_length=20,
        choices=SceneRoundStartReason.choices,
        default=SceneRoundStartReason.OPT_IN,
    )
    mode = models.CharField(
        max_length=20, choices=SceneRoundMode.choices, default=SceneRoundMode.POSE_ORDER
    )
    advance_quorum_pct = models.PositiveSmallIntegerField(default=60)
    max_actions_per_round = models.PositiveSmallIntegerField(default=1)
    per_target_repeat_lock = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["room"],
                condition=models.Q(
                    status__in=[
                        RoundStatus.DECLARING,
                        RoundStatus.RESOLVING,
                        RoundStatus.BETWEEN_ROUNDS,
                    ]
                ),
                name="one_active_scene_round_per_room",
            ),
        ]

    def __str__(self) -> str:
        return f"SceneRound(room={self.room_id}, round={self.round_number}, {self.status})"


class SceneRoundDefaultsConfig(SharedMemoryModel):
    """Singleton (pk=1) staff-tunable defaults for new scene rounds."""

    objects = ArxSharedMemoryManager()

    default_mode = models.CharField(
        max_length=20, choices=SceneRoundMode.choices, default=SceneRoundMode.POSE_ORDER
    )
    advance_quorum_pct = models.PositiveSmallIntegerField(default=60)
    max_actions_per_round = models.PositiveSmallIntegerField(default=1)
    per_target_repeat_lock = models.BooleanField(default=False)
    anti_spam_seconds = models.PositiveSmallIntegerField(default=5)
    abandonment_grace_rounds = models.PositiveIntegerField(
        default=2,
        help_text=(
            "N action-driven beats an abandoned downed victim waits for rescue before"
            " their fate resolves."
        ),
    )
    sudden_harm_interpose_threshold = models.PositiveIntegerField(
        default=10,
        help_text=(
            "Minimum out-of-combat sudden-harm amount that justifies holding for a"
            " reactive Interpose beat (#1316); below this, harm applies immediately."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        "accounts.AccountDB",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="scene_round_defaults_updates",
    )

    def __str__(self) -> str:
        return f"SceneRoundDefaultsConfig(pk={self.pk})"


def get_scene_round_defaults_config() -> SceneRoundDefaultsConfig:
    obj = SceneRoundDefaultsConfig.objects.cached_singleton()
    if obj is None:
        obj, _ = SceneRoundDefaultsConfig.objects.get_or_create(pk=1)
    return obj


class SceneRoundParticipant(SharedMemoryModel):
    """A character taking turns in a SceneRound."""

    scene_round = models.ForeignKey(
        SceneRound, on_delete=models.CASCADE, related_name="participants"
    )
    character_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="scene_round_participations",
    )
    initiative_order = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=SceneRoundParticipantStatus.choices,
        default=SceneRoundParticipantStatus.ACTIVE,
    )

    class Meta:
        ordering = ["initiative_order", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["scene_round", "character_sheet"],
                name="unique_scene_round_participant",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.character_sheet} in {self.scene_round_id}"


class SceneActionDeclaration(SharedMemoryModel):
    """Consumer-owned bridge: a participant's declared action (or explicit pass) for a
    social scene round. Mirrors combat's ``RoundChallengeDeclaration`` (no polymorphic FK).

    ``is_pass=True`` with null challenge FKs is an explicit pass. A CHALLENGE declaration
    stores ``(challenge_instance, challenge_approach)`` and is re-validated/resolved at
    round resolution via ``get_available_actions`` (mirrors combat's post-pass).
    """

    scene_round = models.ForeignKey(
        "scenes.SceneRound", on_delete=models.CASCADE, related_name="action_declarations"
    )
    round_number = models.PositiveIntegerField()
    participant = models.ForeignKey(
        SCENE_ROUND_PARTICIPANT_MODEL,
        on_delete=models.CASCADE,
        related_name="action_declarations",
    )
    challenge_instance = models.ForeignKey(
        "mechanics.ChallengeInstance",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="scene_declarations",
    )
    challenge_approach = models.ForeignKey(
        "mechanics.ChallengeApproach",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="scene_declarations",
    )
    target_persona = models.ForeignKey(
        "scenes.Persona",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="targeted_scene_declarations",
    )
    succor_target = models.ForeignKey(
        SCENE_ROUND_PARTICIPANT_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="succor_declarations",
        help_text="The participant this declaration shelters, when maneuver is Succor (#1744).",
    )
    succor_resolution = models.FloatField(
        null=True,
        blank=True,
        help_text="Cached graded outcome of this round's Succor resolution (#1744).",
    )
    interpose_target = models.ForeignKey(
        SCENE_ROUND_PARTICIPANT_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interpose_declarations",
        help_text="The participant this declaration guards, when maneuver is Interpose (#1316).",
    )
    is_immediate = models.BooleanField(
        default=False,
        help_text=(
            "True for a resolved POSE_ORDER/OPEN action; False for a deferred STRICT declaration."
        ),
    )
    is_pass = models.BooleanField(default=False)
    declared_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["participant__initiative_order", "declared_at", "pk"]

    def __str__(self) -> str:
        kind = "pass" if self.is_pass else "challenge"
        return f"SceneActionDeclaration({self.participant_id}, r{self.round_number}, {kind})"


class PendingSuddenHarm(SharedMemoryModel):
    """A one-shot out-of-combat damage payload held pending a reactive Interpose beat (#1316).

    Created by ``world.scenes.sudden_harm.arm_or_apply_sudden_harm`` when a bystander is
    present and the harm clears ``SceneRoundDefaultsConfig.sudden_harm_interpose_threshold``.
    Resolved (and deleted) by ``world.scenes.sudden_harm.resolve_pending_interpose_harm`` at
    the bound round's resolution. Multiple unresolved rows may exist per target at once (e.g.
    a single Consequence with two DEAL_DAMAGE effects against the same target) — resolution
    iterates and resolves each independently.
    """

    target_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="pending_sudden_harm",
        help_text="The character this pending harm targets; multiple unresolved rows may exist.",
    )
    scene_round = models.ForeignKey(
        "scenes.SceneRound",
        on_delete=models.CASCADE,
        related_name="pending_sudden_harms",
        help_text="The round bound to resolve this harm.",
    )
    amount = models.PositiveIntegerField(
        help_text="The raw pending damage amount, before any interpose mitigation.",
    )
    damage_type = models.ForeignKey(
        "conditions.DamageType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="pending_sudden_harm_entries",
        help_text="The damage type, if typed (null = untyped).",
    )
    source_description = models.CharField(
        max_length=200,
        blank=True,
        help_text="Freeform narration of what caused the harm.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this pending harm was created.",
    )

    def __str__(self) -> str:
        return f"PendingSuddenHarm({self.amount} on {self.target_sheet_id})"


class DecisiveCheckMarker(SharedMemoryModel):
    """GM-declared marker: the next graded check in this scene resolves this beat.

    Created before the decisive check resolves (pre-declared, #1748). When the
    next social-template action or benign cast produces a CheckOutcome, the hook
    in decisive_check_services calls record_outcome_tier_completion and marks
    this RESOLVED.

    Marker creation also activates stakes contracts on the scene's staked beats
    (the freeform-scene equivalent of encounter creation or mission acceptance),
    since scenes have no encounter-start/mission-issue seam to hang activation on.
    """

    scene = models.ForeignKey(
        "scenes.Scene",
        on_delete=models.CASCADE,
        related_name="decisive_markers",
    )
    beat = models.ForeignKey(
        "stories.Beat",
        on_delete=models.CASCADE,
        related_name="decisive_markers",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    status = models.CharField(
        max_length=10,
        choices=DecisiveCheckMarkerStatus.choices,
        default=DecisiveCheckMarkerStatus.PENDING,
        db_index=True,
    )
    resolved_outcome_tier = models.ForeignKey(
        "traits.CheckOutcome",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="The CheckOutcome that resolved this marker (audit).",
    )
    created_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["scene"],
                condition=Q(status="pending"),
                name="one_pending_decisive_marker_per_scene",
            ),
        ]
        indexes = [models.Index(fields=["scene", "status"])]

    def __str__(self) -> str:
        return f"DecisiveCheckMarker(scene={self.scene_id}, beat={self.beat_id}, {self.status})"


# Import place_models, action_models, and reaction_models for Django model discovery
from world.scenes.action_models import SceneActionRequest  # noqa: E402, F401
from world.scenes.boon_models import Boon  # noqa: E402, F401
from world.scenes.place_models import InteractionReceiver, Place, PlacePresence  # noqa: E402, F401
from world.scenes.reaction_models import ReactionWindow, WindowReaction  # noqa: E402, F401
from world.scenes.speaker_queue_models import SpeakerQueue, SpeakerQueueEntry  # noqa: E402, F401
