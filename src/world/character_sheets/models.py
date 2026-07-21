"""
Character sheet models for storing character demographic and descriptive data.

This replaces Arx I's character data stored in Evennia attributes with proper
Django models for better data integrity, querying, and performance.

Based on Arx I's evennia_extensions/character_extensions/models.py patterns
and the evennia_extensions/object_extensions/models.py display name system.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from world.achievements.handlers import StatHandler
    from world.achievements.models import Achievement
    from world.classes.models import CharacterClassLevel
    from world.conditions.models import CapabilityType, ConditionTemplate
    from world.items.handlers import CharacterSheetOutfitsHandler
    from world.magic.models.affinity import Resonance
    from world.mechanics.models import Property
    from world.scenes.models import Persona

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.functional import cached_property
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel

from core.descriptors import ReverseOneToOneOrNone
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.character_creation.constants import OriginStoryState
from world.character_sheets.types import (
    DECAY_TIER_THRESHOLDS_DAYS,
    ActivityState,
    LifecycleState,
    MaritalStatus,
    ProfileTextField,
    SheetVisibility,
)


class Heritage(NaturalKeyMixin, SharedMemoryModel):
    """
    Canonical heritage types that affect a character's origin story.

    Examples: Sleeper (awakened from magical slumber, unknown origins),
    Misbegotten (born from Tree of Souls, no parents), Normal (standard upbringing).
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Heritage name (e.g., 'Sleeper', 'Misbegotten', 'Normal')",
    )
    description = models.TextField(
        blank=True,
        help_text="Description of this heritage type",
    )
    is_special = models.BooleanField(
        default=False,
        help_text="True for special heritages that bypass normal family rules",
    )
    family_known = models.BooleanField(
        default=True,
        help_text="Whether characters with this heritage know their family at creation",
    )
    family_display = models.CharField(
        max_length=100,
        blank=True,
        help_text="What to display for family (e.g., 'Unknown', 'Discoverable in play')",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        verbose_name = "Heritage"
        verbose_name_plural = "Heritages"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Profile(SharedMemoryModel):
    """The bio/narrative surface a persona presents (#1270).

    Sliced out of ``CharacterSheet`` so a cover identity can carry its *own* fabricated
    bio instead of an empty one — the absence of a bio would otherwise immediately out a
    cover. A sheet owns one ``true_profile`` (its real bio, presented by the PRIMARY
    persona); established/cover personas may each own their own ``Profile``.

    Holds the narrative *text* fields (slice 1) and the *lineage* FKs — family, heritage,
    tarot, origin (slice 3). A cover persona may own its own Profile to present a fabricated
    bio + lineage; the sheet's ``true_profile`` is the real one, surfaced through forwarding
    properties on ``CharacterSheet`` so existing ``sheet.<field>`` reads/writes are unchanged.
    """

    concept = models.CharField(
        max_length=255,
        blank=True,
        help_text="Public character concept/archetype",
    )
    real_concept = models.CharField(
        max_length=255,
        blank=True,
        help_text="Hidden/secret character concept (staff field)",
    )
    quote = models.TextField(blank=True, help_text="Character quote/motto")
    personality = models.TextField(
        blank=True,
        help_text="Character personality description",
    )
    background = models.TextField(blank=True, help_text="Character background story")
    obituary = models.TextField(
        blank=True,
        help_text="Death notice if character is deceased",
    )

    # Lineage (#1270 slice 3). Sliced off CharacterSheet so a cover identity can present its
    # OWN (fabricated) lineage. Mechanical reads use the sheet's forwarding properties (always
    # → ``true_profile``, the real lineage); only display reads the *presented* face's profile.
    heritage = models.ForeignKey(
        Heritage,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="profiles",
        help_text="Character's heritage (Normal, Sleeper, Misbegotten, etc.)",
    )
    origin_realm = models.ForeignKey(
        "realms.Realm",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="profiles",
        help_text="Realm/homeland the character is from",
    )
    family = models.ForeignKey(
        "roster.Family",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="profiles",
        help_text="Character's family. Null for orphans/unknown lineage.",
    )
    tarot_card = models.ForeignKey(
        "tarot.TarotCard",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="profiles",
        help_text="Tarot card from naming ritual (for familyless characters).",
    )
    tarot_reversed = models.BooleanField(
        default=False,
        help_text="Whether the tarot card is reversed.",
    )

    class Meta:
        verbose_name = "Profile"
        verbose_name_plural = "Profiles"

    def __str__(self) -> str:
        return self.concept or f"Profile #{self.pk}"


# The fields that live on ``Profile`` and are exposed on ``CharacterSheet`` as forwarding
# properties (→ ``true_profile``). Creation routes these kwargs to the profile; readers/writers
# keep using ``sheet.<field>`` unchanged (#1270). Bio (slice 1) + lineage (slice 3).
_PROFILE_BIO_FIELDS: tuple[str, ...] = (
    "concept",
    "real_concept",
    "quote",
    "personality",
    "background",
    "obituary",
)
_PROFILE_LINEAGE_FIELDS: tuple[str, ...] = (
    "heritage",
    "origin_realm",
    "family",
    "tarot_card",
    "tarot_reversed",
)
_PROFILE_FIELDS: tuple[str, ...] = _PROFILE_BIO_FIELDS + _PROFILE_LINEAGE_FIELDS


class ProfileTextVersion(SharedMemoryModel):
    """One accepted state of a Profile prose field — history is never lost (#2631).

    Every write path to a versioned field (table-request approval, staff/admin
    edit) snapshots through ``services.update_profile_text``; nothing may
    overwrite ``Profile.background``/``personality`` silently. Full text per
    version (not diffs). The first post-CG write also captures the CG-approved
    original as the initial row, so the earliest version is always the CG text.

    Stamped with the IC datetime and active Era (season) at write time so a
    roster browser reads the character's textual history as an in-world arc.
    Finer narrative context (which story/chapter) derives from the causing
    request via the reverse link on ``gm.ProfileTextRequestDetails.applied_version``.
    """

    profile = models.ForeignKey(
        "character_sheets.Profile",
        on_delete=models.CASCADE,
        related_name="text_versions",
    )
    field = models.CharField(
        max_length=20,
        choices=ProfileTextField.choices,
        help_text="Which Profile prose field this version belongs to.",
    )
    text = models.TextField(help_text="The full field text as of this version.")
    created_at = models.DateTimeField(auto_now_add=True)
    ic_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="IC datetime at write time (null if the game clock was unset).",
    )
    era = models.ForeignKey(
        "stories.Era",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="profile_text_versions",
        help_text="The active Era (season) at write time.",
    )
    edited_by = models.ForeignKey(
        "accounts.AccountDB",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="profile_text_edits",
        help_text="Staff editor for admin-path writes; null for request-driven "
        "and CG-original snapshots.",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["profile", "field"])]
        verbose_name = "Profile Text Version"
        verbose_name_plural = "Profile Text Versions"

    def __str__(self) -> str:
        return (
            f"{self.get_field_display()} v@{self.created_at:%Y-%m-%d} (profile {self.profile_id})"
        )


class CharacterSheet(SharedMemoryModel):
    """
    Primary character demographic and identity data storage.

    Replaces Arx I's CharacterSheet model and item_data attribute system
    with proper Django model fields for better data integrity and querying.
    """

    character = models.OneToOneField(
        ObjectDB,
        on_delete=models.CASCADE,
        related_name="sheet_data",
        primary_key=True,
        help_text="The character this sheet belongs to",
    )

    origin_story_state = models.CharField(
        max_length=20,
        choices=OriginStoryState.choices,
        default=OriginStoryState.NOT_STARTED,
        help_text=(
            "Deferral/progress state of the guided origin story (#2478). "
            "Cache of slot-row truth — maintained by "
            "world.character_creation.services.origin_story, never written directly."
        ),
    )

    # Basic Identity & Demographics
    age = models.PositiveSmallIntegerField(
        default=18,
        validators=[MinValueValidator(16), MaxValueValidator(200)],
        help_text="Character's apparent age",
    )
    real_age = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10000)],
        help_text="Character's true age (staff/hidden field)",
    )

    # Physical Characteristics (Build/Height system)
    true_height_inches = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(12), MaxValueValidator(600)],
        help_text="Character's true height in inches (staff-visible only)",
    )
    build = models.ForeignKey(
        "forms.Build",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="character_sheets",
        help_text="Character's body type",
    )
    weight_pounds = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Calculated weight in pounds (staff-visible only)",
    )

    gender = models.ForeignKey(
        "Gender",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="character_sheets",
        help_text="Character's gender identity",
    )
    pronouns = models.ForeignKey(
        "Pronouns",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="character_sheets",
        help_text="Character's pronoun set",
    )
    # Individual pronoun fields (auto-derived from gender at finalization, editable in-game)
    pronoun_subject = models.CharField(
        max_length=20,
        default="they",
        help_text="Subject pronoun (e.g., 'he', 'she', 'they')",
    )
    pronoun_object = models.CharField(
        max_length=20,
        default="them",
        help_text="Object pronoun (e.g., 'him', 'her', 'them')",
    )
    pronoun_possessive = models.CharField(
        max_length=20,
        default="their",
        help_text="Possessive pronoun (e.g., 'his', 'her', 'their')",
    )

    # Heritage and Origin lineage moved to Profile (#1270 slice 3); read/written through the
    # forwarding properties below (sheet.heritage / sheet.origin_realm → true_profile).

    # Species
    species = models.ForeignKey(
        "species.Species",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="character_sheets",
        help_text="Character's species (may have parent for subspecies)",
    )

    # Residence & Trickle
    current_residence = models.ForeignKey(
        "evennia_extensions.RoomProfile",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="residents",
        help_text=(
            "Character's declared residence. Narrative declaration; mechanical "
            "resonance trickle fires only if the room has a positive cascade-row "
            "modifier (LocationStatModifier, key_type=resonance) matching one of "
            "the character's claimed resonances. Deliberately separate from "
            "ObjectDB db_home (which is a respawn-location concern)."
        ),
    )

    # Social & Identity
    # #1270 — the real bio surface, sliced out of the sheet into Profile. The PRIMARY
    # persona presents this; the narrative text fields (concept, quote, background, …) are
    # read back through forwarding properties below so existing reads stay unchanged.
    true_profile = models.OneToOneField(
        "character_sheets.Profile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owning_sheet",
        help_text="This character's real bio (presented by the PRIMARY persona).",
    )
    marital_status = models.CharField(
        max_length=20,
        choices=MaritalStatus.choices,
        default=MaritalStatus.SINGLE,
        help_text="Character's marital status",
    )
    # family / tarot_card / tarot_reversed lineage moved to Profile (#1270 slice 3);
    # read/written through the forwarding properties below.
    vocation = models.CharField(
        max_length=255,
        blank=True,
        help_text="Character profession - will be FK later",
    )
    social_rank = models.PositiveSmallIntegerField(
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(20)],
        help_text="Social standing/rank (1=highest, 20=lowest)",
    )
    rollmod = models.SmallIntegerField(default=0)

    # Privacy tiers (#1271) — player-controlled visibility for the mechanical sheet
    # sections. Default SELF preserves the #1269 "private by default" behaviour; a player
    # can open a section to FRIENDS (their allow list) or PUBLIC. Bio/story tiers are a
    # follow-up (they interact with the presented-identity gating).
    stats_visibility = models.CharField(
        max_length=10,
        choices=SheetVisibility.choices,
        default=SheetVisibility.SELF,
        help_text="Who can see this character's stats.",
    )
    skills_visibility = models.CharField(
        max_length=10,
        choices=SheetVisibility.choices,
        default=SheetVisibility.SELF,
        help_text="Who can see this character's skills.",
    )
    magic_visibility = models.CharField(
        max_length=10,
        choices=SheetVisibility.choices,
        default=SheetVisibility.SELF,
        help_text="Who can see this character's magic.",
    )
    goals_visibility = models.CharField(
        max_length=10,
        choices=SheetVisibility.choices,
        default=SheetVisibility.SELF,
        help_text="Who can see this character's goals.",
    )

    # #981 — the persona (face) this character is currently presenting as. NULL
    # means "on their PRIMARY persona" (the resolver defaults to it), so a fresh
    # sheet writes no row. Mutated ONLY via ``scenes.services.set_active_persona``
    # (an explicit player switch, or an IC act such as a mask being removed →
    # restore the covered face). ``SET_NULL`` so a deleted persona safely reverts
    # to primary, never a dangling/foreign identity.
    active_persona = models.ForeignKey(
        "scenes.Persona",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=(
            "The face this character is currently presenting as (#981); NULL ⇒ "
            "PRIMARY. Resolve via active_persona_for_sheet; set only via "
            "set_active_persona — never gate IC reads on primary_persona directly."
        ),
    )

    # Temporal & Cultural
    birthday = models.CharField(
        max_length=255,
        blank=True,
        help_text="Character birthday - consider DateField later",
    )

    # Descriptive Text Fields
    # NOTE: quote / personality / background / obituary moved to Profile (#1270) and are
    # exposed via forwarding properties below. additional_desc stays — it is appearance
    # text (read by _build_appearance), distinct from the narrative bio.
    additional_desc = models.TextField(
        blank=True,
        help_text="Additional character description",
    )

    # Activity & Lifecycle (#671 — inactivity detection)
    # Activity is the OOC axis ("is this character being played"); Lifecycle is
    # the IC axis ("what is their condition in the world"). Orthogonal.
    activity_state = models.CharField(
        max_length=8,
        choices=ActivityState.choices,
        default=ActivityState.ACTIVE,
        help_text=(
            "OOC engagement state. ACTIVE / HIATUS (player-declared, time-bounded)"
            " / INACTIVE (auto-inferred) / FROZEN (OC swap, 30-day cooldown)."
        ),
    )
    activity_state_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="HIATUS end date OR FROZEN cooldown floor. Null in ACTIVE/INACTIVE.",
    )
    lifecycle_state = models.CharField(
        max_length=8,
        choices=LifecycleState.choices,
        default=LifecycleState.ALIVE,
        help_text=(
            "IC condition. ALIVE / CAPTURED / COMA / RETIRED / DEAD. Orthogonal to"
            " activity_state — both must be ALIVE+ACTIVE for the character to count"
            " as 'present and playing' to consumer systems."
        ),
    )
    lifecycle_state_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When lifecycle_state last changed. Null for default ALIVE.",
    )

    # OC distinction (#671 — minimal pair; full OC creation flow is a follow-up)
    is_oc = models.BooleanField(
        default=False,
        help_text="True if this character was created by a player as their own OC.",
    )
    created_by = models.ForeignKey(
        "accounts.AccountDB",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="characters_created",
        help_text=(
            "The account that created this character. Null for grandfathered or"
            " staff-seeded rows. Survives account deletion via SET_NULL."
        ),
    )

    # Mission cap (#686 — applies to NPC-mediated missions only; trigger-based
    # mission offers from rooms/items explicitly bypass this cap)
    max_active_npc_missions = models.PositiveSmallIntegerField(
        default=3,
        help_text=(
            "OOC cap on simultaneously-active NPC-given missions. NPC mission "
            "givers don't show offers when this PC is at the cap. Trigger-based "
            "mission offers (rooms, items) ignore the cap. Staff-overridable."
        ),
    )

    # Timestamps
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Sheet for {self.character.key}"

    # --- Bio forwarding (#1270) ------------------------------------------
    # The narrative bio lives on Profile now; these properties forward to the real bio
    # (``true_profile``) so every existing ``sheet.<field>`` read — item_data handler,
    # roster serializers, telnet — and write keeps working transparently against the true
    # profile. Reads on a sheet without a true_profile return empty; writes lazily create
    # one (persisted by the save() cascade below).

    def _ensure_true_profile(self) -> Profile:
        if self.true_profile is None:
            self.true_profile = Profile()
        return self.true_profile

    @property
    def concept(self) -> str:
        return self.true_profile.concept if self.true_profile is not None else ""

    @concept.setter
    def concept(self, value: str) -> None:
        self._ensure_true_profile().concept = value

    @property
    def real_concept(self) -> str:
        return self.true_profile.real_concept if self.true_profile is not None else ""

    @real_concept.setter
    def real_concept(self, value: str) -> None:
        self._ensure_true_profile().real_concept = value

    @property
    def quote(self) -> str:
        return self.true_profile.quote if self.true_profile is not None else ""

    @quote.setter
    def quote(self, value: str) -> None:
        self._ensure_true_profile().quote = value

    @property
    def personality(self) -> str:
        return self.true_profile.personality if self.true_profile is not None else ""

    @personality.setter
    def personality(self, value: str) -> None:
        self._ensure_true_profile().personality = value

    @property
    def background(self) -> str:
        return self.true_profile.background if self.true_profile is not None else ""

    @background.setter
    def background(self, value: str) -> None:
        self._ensure_true_profile().background = value

    @property
    def obituary(self) -> str:
        return self.true_profile.obituary if self.true_profile is not None else ""

    @obituary.setter
    def obituary(self, value: str) -> None:
        self._ensure_true_profile().obituary = value

    # --- Lineage forwarding (#1270 slice 3) ------------------------------
    # Lineage FKs live on Profile now; mechanical callers read the REAL lineage through
    # these (always → true_profile). Only the display layer reads a *cover* persona's
    # profile. Reads on a sheet without a true_profile return the field's empty default.

    @property
    def heritage(self) -> Heritage | None:
        return self.true_profile.heritage if self.true_profile is not None else None

    @heritage.setter
    def heritage(self, value: Heritage | None) -> None:
        self._ensure_true_profile().heritage = value

    @property
    def origin_realm(self) -> Any:
        return self.true_profile.origin_realm if self.true_profile is not None else None

    @origin_realm.setter
    def origin_realm(self, value: Any) -> None:
        self._ensure_true_profile().origin_realm = value

    @property
    def family(self) -> Any:
        return self.true_profile.family if self.true_profile is not None else None

    @family.setter
    def family(self, value: Any) -> None:
        self._ensure_true_profile().family = value

    @property
    def tarot_card(self) -> Any:
        return self.true_profile.tarot_card if self.true_profile is not None else None

    @tarot_card.setter
    def tarot_card(self, value: Any) -> None:
        self._ensure_true_profile().tarot_card = value

    @property
    def tarot_reversed(self) -> bool:
        return self.true_profile.tarot_reversed if self.true_profile is not None else False

    @tarot_reversed.setter
    def tarot_reversed(self, value: bool) -> None:
        self._ensure_true_profile().tarot_reversed = value

    def save(self, *args: object, **kwargs: object) -> None:
        # Persist an attached true_profile first so a bio set via the forwarding setters
        # (and any lazily-created profile) is saved and has a pk for the FK (#1270).
        if self.true_profile is not None:
            self.true_profile.save()
        super().save(*args, **kwargs)

    # --- Activity / Lifecycle helpers (#671) -----------------------------

    @property
    def is_dormant(self) -> bool:
        """True when any consumer should treat this character as inactive.

        Returns True if ``activity_state != ACTIVE`` (HIATUS, INACTIVE, FROZEN)
        OR ``lifecycle_state != ALIVE`` (CAPTURED, COMA, RETIRED, DEAD).
        Two simple column comparisons; safe to call in tight loops.
        """
        return (
            self.activity_state != ActivityState.ACTIVE
            or self.lifecycle_state != LifecycleState.ALIVE
        )

    @property
    def decay_tier(self) -> str | None:
        """Inactivity tier from days-since-last-signal, or None when fresh.

        Walks the FK chain ``roster_entry -> roster.activity_requirement`` and
        ``roster_entry -> current_tenure -> player_data.account.last_login``
        plus ``roster_entry.last_puppeted`` for HIGH-tier rosters. Returns the
        biggest matching tier (DORMANT > LONG_INACTIVE > INACTIVE >
        RECENT_INACTIVE) or None when the most recent signal is < 14 days old.

        Callers iterating many sheets should ``prefetch_related``
        ``roster_entry__tenures__player_data__account`` to amortize the chain.
        Single calls amortize cheaply via SharedMemoryModel's identity map.
        """
        last_signal = self._last_activity_signal_at()
        if last_signal is None:
            return None
        days = (timezone.now() - last_signal).days
        for tier, threshold in DECAY_TIER_THRESHOLDS_DAYS.items():
            if days >= threshold:
                return tier
        return None

    def _last_activity_signal_at(self) -> datetime | None:
        """Return the most recent activity signal for this sheet, or None.

        For HIGH-tier rosters: max of Account.last_login and
        RosterEntry.last_puppeted. For LOW-tier: Account.last_login. For
        NONE-tier and ROSTERED characters (no current tenure): max of any
        available signal (so consumers can still read decay_tier even when
        the cron won't auto-flip activity_state).
        """
        entry = self.roster_entry_or_none
        if entry is None:
            return self.created_by.last_login if self.created_by_id else None

        current = entry.current_tenure
        last_login = current.player_data.account.last_login if current is not None else None

        from world.roster.models.choices import ActivityRequirement  # noqa: PLC0415

        requirement = entry.roster.activity_requirement
        if requirement == ActivityRequirement.LOW:
            return last_login

        # HIGH and NONE both fall back to "max of available signals"
        candidates = [s for s in (last_login, entry.last_puppeted) if s is not None]
        return max(candidates) if candidates else None

    @cached_property
    def stats(self) -> StatHandler:
        """Cached stat handler for achievement stat tracking."""
        from world.achievements.handlers import StatHandler  # noqa: PLC0415

        return StatHandler(self)

    # Reverse-OneToOne safe accessors (the *_or_none family, #2386): missing row
    # → None; genuine attribute bugs still raise. Use the raw accessors
    # (``sheet.vitals`` etc.) directly where a missing row is a hard bug —
    # vitals/fatigue are seeded at CG finalization; roster_entry is absent for
    # test/NPC sheets outside the roster flow.
    roster_entry_or_none = ReverseOneToOneOrNone("roster_entry")
    vitals_or_none = ReverseOneToOneOrNone("vitals")
    fatigue_or_none = ReverseOneToOneOrNone("fatigue")
    active_alternate_self_or_none = ReverseOneToOneOrNone("active_alternate_self")
    path_intent_or_none = ReverseOneToOneOrNone("path_intent")

    @cached_property
    def primary_persona(self) -> Persona:
        """Return the PRIMARY persona for this character.

        Raises Persona.DoesNotExist if somehow the invariant is violated.
        Every CharacterSheet must have exactly one PRIMARY persona; if it
        does not, that is a loud error state, not a silent None.
        """
        from world.scenes.constants import PersonaType  # noqa: PLC0415

        return self.personas.get(persona_type=PersonaType.PRIMARY)

    def clean(self) -> None:
        """Validate ``active_persona`` is one of this sheet's own faces (#981).

        Defense-in-depth: ``scenes.services.set_active_persona`` is the only
        intended writer and already validates ownership, but this guards
        admin / ``full_clean`` callers from planting a cross-sheet
        (foreign-identity) active persona that the resolver would then serve.
        """
        super().clean()
        if self.active_persona_id is not None and self.active_persona.character_sheet_id != self.pk:
            msg = "Active persona must be one of this character's own personas."
            raise ValidationError({"active_persona": msg})

    @cached_property
    def cached_payload_personas(self) -> list[Persona]:
        """PRIMARY + ESTABLISHED personas, ordered for the account payload.

        Serves as the ``to_attr`` target for::

            Prefetch(
                "character_sheet__personas",
                queryset=Persona.objects.filter(
                    persona_type__in=[PersonaType.PRIMARY, PersonaType.ESTABLISHED]
                ).order_by("-persona_type", "created_at", "id"),
                to_attr="cached_payload_personas",
            )

        PRIMARY first (descending alphabetical: 'p' > 'e'), then ESTABLISHED
        by ``created_at`` with ``id`` as a deterministic tiebreaker.
        TEMPORARY personas are excluded — they are scene-bound and not
        selectable from a portrait grid.

        When prefetched, Django populates this directly. When accessed without
        prefetch, falls back to a fresh query. The fallback ordering MUST
        match the Prefetch ordering exactly, or prefetched vs. non-prefetched
        rows will diverge.
        """
        from world.scenes.constants import PersonaType  # noqa: PLC0415

        return list(
            self.personas.filter(
                persona_type__in=[PersonaType.PRIMARY, PersonaType.ESTABLISHED]
            ).order_by("-persona_type", "created_at", "id")
        )

    @cached_property
    def cached_character_class_levels(self) -> list[CharacterClassLevel]:
        """All CharacterClassLevel records for this character's ObjectDB.

        Serves as the ``to_attr`` target for::

            Prefetch(
                "character__character_class_levels",
                queryset=CharacterClassLevel.objects.select_related("character_class"),
                to_attr="cached_character_class_levels",
            )

        When prefetched, Django populates this directly. When accessed without
        prefetch, falls back to a fresh query.

        To invalidate after mutating levels::

            sheet.invalidate_class_level_cache()

        Note: ``CharacterClassLevel.character`` FKs to ObjectDB (shared-pk with
        CharacterSheet), so we walk ``self.character.character_class_levels``.
        """
        from world.classes.models import CharacterClassLevel  # noqa: PLC0415

        return list(
            CharacterClassLevel.objects.filter(character=self.character).select_related(
                "character_class"
            )
        )

    @cached_property
    def current_level(self) -> int:
        """Character's current level — the highest level across all class assignments.

        Returns 0 if the character has no class assignments (freshly created test
        characters, NPCs without classes).

        Derived from ``cached_character_class_levels``; invalidate after any
        mutation to class levels::

            sheet.invalidate_class_level_cache()
        """
        levels = [ccl.level for ccl in self.cached_character_class_levels]
        return max(levels) if levels else 0

    def invalidate_class_level_cache(self) -> None:
        """Clear the cached class-level data.

        Call this after any code path that mutates the character's
        CharacterClassLevel records (create, update, delete, bulk ops).
        Progression services, admin actions, and test fixtures that set
        levels directly must call this so subsequent reads of
        ``current_level`` and ``cached_character_class_levels`` reflect
        the mutation.

        Example::

            CharacterClassLevel.objects.create(character=sheet.character, ...)
            sheet.invalidate_class_level_cache()
        """
        self.__dict__.pop("cached_character_class_levels", None)
        self.__dict__.pop("current_level", None)

    @cached_property
    def cached_achievements_held(self) -> set[Achievement]:
        """Set of Achievement instances this character has earned.

        Serves as the ``to_attr`` target for::

            Prefetch(
                "achievements__achievement",
                queryset=CharacterAchievement.objects.select_related("achievement"),
                to_attr="cached_achievements_held",
            )

        When prefetched, Django populates this directly. When accessed without
        prefetch, falls back to a fresh query.

        To invalidate after granting or revoking an achievement::

            sheet.invalidate_achievement_cache()
        """

        return {ca.achievement for ca in self.achievements.select_related("achievement").all()}

    def invalidate_achievement_cache(self) -> None:
        """Clear the cached achievement data.

        Call this after any code path that grants or revokes a
        ``CharacterAchievement`` for this sheet.  Achievement services and
        admin actions must call this so subsequent reads of
        ``cached_achievements_held`` reflect the mutation.

        Example::

            CharacterAchievement.objects.create(character_sheet=sheet, ...)
            sheet.invalidate_achievement_cache()
        """
        self.__dict__.pop("cached_achievements_held", None)

    @cached_property
    def cached_active_condition_templates(self) -> set[ConditionTemplate]:
        """Set of ConditionTemplate instances currently active on this character.

        Queries ConditionInstance rows where target == self.character (ObjectDB).
        Only non-suppressed instances are included.

        Serves as the ``to_attr`` target for::

            Prefetch(
                "character__condition_instances",
                queryset=ConditionInstance.objects.filter(
                    is_suppressed=False
                ).select_related("condition"),
                to_attr="cached_active_condition_templates",
            )

        When prefetched, Django populates this directly. When accessed without
        prefetch, falls back to a fresh query.

        To invalidate after applying or removing a condition::

            sheet.invalidate_condition_cache()
        """
        from world.conditions.models import ConditionInstance  # noqa: PLC0415

        return {
            ci.condition
            for ci in ConditionInstance.objects.filter(
                target=self.character,
                is_suppressed=False,
            ).select_related("condition")
        }

    def invalidate_condition_cache(self) -> None:
        """Clear the cached active-condition data.

        Call this after any code path that applies, removes, or suppresses
        a ``ConditionInstance`` for this character.

        Example::

            ConditionInstance.objects.filter(target=sheet.character, ...).delete()
            sheet.invalidate_condition_cache()
        """
        self.__dict__.pop("cached_active_condition_templates", None)

    # ==========================================================================
    # Corruption helpers (Scope #7)
    # ==========================================================================

    def get_corruption_stage(self, resonance: Resonance) -> int:
        """Return current Corruption stage for one resonance (0-5).

        0 = no condition exists or no current stage. 1-5 = current_stage.stage_order.
        ``sheet.character`` is the ObjectDB target for ConditionInstance rows.
        """
        from world.conditions.models import ConditionInstance  # noqa: PLC0415

        instance = (
            ConditionInstance.objects.filter(
                target=self.character,
                condition__corruption_resonance=resonance,
            )
            .select_related("current_stage")
            .first()
        )
        if instance is None or instance.current_stage is None:
            return 0
        return instance.current_stage.stage_order

    def get_tether_strain_stage(self) -> int:
        """Return the Sineater's current Tether Strain condition stage (0-5).

        0 = no condition instance exists or no current stage. 1-5 = current_stage.stage_order.
        ``sheet.character`` is the ObjectDB target for ConditionInstance rows.
        """
        from world.conditions.models import ConditionInstance  # noqa: PLC0415

        instance = (
            ConditionInstance.objects.filter(
                target=self.character,
                condition__name="Tether Strain",
            )
            .select_related("current_stage")
            .first()
        )
        if instance is None or instance.current_stage is None:
            return 0
        return instance.current_stage.stage_order

    @cached_property
    def saved_outfits(self) -> CharacterSheetOutfitsHandler:
        """Cached handler for this sheet's saved outfit definitions.

        Named ``saved_outfits`` rather than ``outfits`` because Django's
        reverse RelatedManager from ``Outfit.character_sheet`` already
        occupies the ``outfits`` attribute on this class.
        """
        from world.items.handlers import CharacterSheetOutfitsHandler  # noqa: PLC0415

        return CharacterSheetOutfitsHandler(self)

    @cached_property
    def is_protagonism_locked(self) -> bool:
        """True if the character is mechanically locked from protagonism.

        Today: corruption terminal stage (stage_order=5) is the only source.
        Future: berserker terminal state, possession, etc. extend the OR.
        """
        return self._has_corruption_terminal_stage()

    def _has_corruption_terminal_stage(self) -> bool:
        """Return True if any per-resonance Corruption condition is at stage 5."""
        from world.conditions.models import ConditionInstance  # noqa: PLC0415

        return ConditionInstance.objects.filter(
            target=self.character,
            condition__corruption_resonance__isnull=False,
            current_stage__stage_order=5,
        ).exists()

    @property
    def in_control(self) -> bool:
        """Whether this character is in control of their own actions.

        Derived from active conditions on each read: False if any active
        condition's category is ``alters_behavior`` (rage/possession/charm/
        mind-control). Reuses the canonical consent signal (ADR-0024) — not a
        stored flag and not a per-status name lookup.

        Deliberately NOT a ``@cached_property``. The active-condition list is
        already cached on the character's ``CharacterConditionHandler``
        (``character.conditions`` — a ``cached_property`` whose ``invalidate()``
        is called by every condition mutation service), so this property reads
        that cache and never issues its own query. Caching the *derived boolean*
        here would create a second, uncoordinated cache that the conditions
        handler cannot invalidate — exactly the stale-control bug that surfaced
        in PR #1605 review, where ``revert_alternate_self`` had to manually
        ``pop`` the cached value to see a freshly-cleared rage condition. As a
        plain property it always reflects the freshest conditions the handler
        knows, and no caller needs to invalidate it.

        A benign shift (bird-to-fly) has no alters_behavior conditions, so this
        stays True and the form is self-revertible anytime.
        """
        return not any(
            inst.condition.category.alters_behavior for inst in self.character.conditions.active()
        )

    def display_ic(self) -> str:
        """Delegate to primary_persona.display_ic()."""
        return self.primary_persona.display_ic()

    def display_with_history(self) -> str:
        """Delegate to primary_persona.display_with_history()."""
        return self.primary_persona.display_with_history()

    def display_to_staff(self) -> str:
        """Delegate to primary_persona.display_to_staff()."""
        return self.primary_persona.display_to_staff()

    def effective_capability(self, capability: CapabilityType) -> int:
        """Authored magnitude for this character's hold on ``capability``.

        Direct passthrough — get_effective_capability_value already takes a
        CharacterSheet + CapabilityType instance. Exists so CharacterSheet
        conforms to world.mechanics.types.HasCapabilities alongside BattleUnit.
        """
        from world.conditions.services import get_effective_capability_value  # noqa: PLC0415

        return get_effective_capability_value(self, capability)

    def has_property(self, prop: Property) -> bool:
        """True if this character carries ``prop`` via runtime attachment or
        persona-authored identity tags.

        Instance-keyed sibling of Character.has_property (name-keyed,
        typeclasses/characters.py:234-253) — same two attachment surfaces, no
        redundant name lookup since the caller already has the Property
        instance. Exists so CharacterSheet conforms to
        world.mechanics.types.HasProperties alongside BattleUnit.
        """
        from world.scenes.models import Persona  # noqa: PLC0415

        if self.character.object_properties.filter(property=prop).exists():
            return True
        try:
            persona = self.primary_persona
        except Persona.DoesNotExist:
            return False
        return persona.properties.filter(pk=prop.pk).exists()

    class Meta:
        verbose_name = "Character Sheet"
        verbose_name_plural = "Character Sheets"


# CharacterDescription model removed - functionality moved to:
# - evennia_extensions.ObjectDisplayData for basic display info
#   (colored_name, longname, descriptions)
# - world.scenes.Persona for character identities and contextual appearances


# --- Canonical models for gender and pronouns --------------------------------


class Gender(NaturalKeyMixin, SharedMemoryModel):
    """
    Canonical gender identities available across the site.

    Decoupled from pronouns so players can mix gender identity with any pronoun set.
    """

    key = models.CharField(max_length=50, unique=True, help_text="Internal key (e.g., 'male')")
    display_name = models.CharField(max_length=100, help_text="Display label (e.g., 'Male')")

    is_default = models.BooleanField(
        default=False,
        help_text="Whether this is the default option when none selected",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["key"]

    class Meta:
        verbose_name = "Gender"
        verbose_name_plural = "Genders"
        ordering = ["display_name"]

    def __str__(self) -> str:
        return self.display_name


class Pronouns(NaturalKeyMixin, SharedMemoryModel):
    """
    Canonical pronoun sets available across the site.

    Decoupled from gender so players can choose any pronoun combination.
    """

    key = models.CharField(max_length=50, unique=True, help_text="Internal key (e.g., 'he_him')")
    display_name = models.CharField(max_length=100, help_text="Display label (e.g., 'he/him')")

    # Pronoun forms
    subject = models.CharField(max_length=50, help_text="Subject pronoun (e.g., 'he')")
    object = models.CharField(max_length=50, help_text="Object pronoun (e.g., 'him')")
    possessive = models.CharField(max_length=50, help_text="Possessive pronoun (e.g., 'his')")

    is_default = models.BooleanField(
        default=False,
        help_text="Whether this is the default option when none selected",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["key"]

    class Meta:
        verbose_name = "Pronoun Set"
        verbose_name_plural = "Pronoun Sets"
        ordering = ["display_name"]

    def __str__(self) -> str:
        return self.display_name
