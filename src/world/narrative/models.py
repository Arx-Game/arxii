from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.mixins import DiscriminatorMixin
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.contributors.models import CreditedContent
from world.locations.constants import LocationParentType, StatKey
from world.narrative.constants import (
    ConditionConnector,
    ConditionType,
    GemitReach,
    NarrativeCategory,
)
from world.societies.constants import FameTier

_STR_PREVIEW_LEN = 40
_GEMIT_PREVIEW_LEN = 60
_STORY_FK = "arxii.Story"
_ACCOUNT_DB_FK = "accounts.AccountDB"


class NarrativeMessage(SharedMemoryModel):
    """A single IC message delivered to one or more characters.

    The message itself is immutable after send. Per-recipient state
    (delivered, acknowledged) lives on NarrativeMessageDelivery.
    """

    body = models.TextField(
        help_text="IC content shown to recipients.",
    )
    ooc_note = models.TextField(
        blank=True,
        help_text=(
            "OOC context visible to staff and GMs with access to the "
            "recipient's character — explains why this message was sent, "
            "what it's about, etc. Not shown to players in-character."
        ),
    )
    category = models.CharField(
        max_length=20,
        choices=NarrativeCategory.choices,
    )
    sender_account = models.ForeignKey(
        _ACCOUNT_DB_FK,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="narrative_messages_sent",
        help_text="Null = automated/system-sourced.",
    )

    # Optional context FKs — populated when a narrative message is produced
    # by the stories system. Consumers of the message can use these to
    # render story-log entries, link to the related story, etc.
    related_story = models.ForeignKey(
        _STORY_FK,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="narrative_messages",
    )
    related_beat_completion = models.ForeignKey(
        "arxii.BeatCompletion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="narrative_messages",
    )
    related_episode_resolution = models.ForeignKey(
        "arxii.EpisodeResolution",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="narrative_messages",
    )

    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["category", "-sent_at"]),
            models.Index(fields=["sender_account", "-sent_at"]),
        ]

    def __str__(self) -> str:
        truncated = len(self.body) > _STR_PREVIEW_LEN
        preview = self.body[:_STR_PREVIEW_LEN] + ("..." if truncated else "")
        return f"NarrativeMessage({self.category}) {preview}"


class AmbientStirLine(SharedMemoryModel):
    """One source-ambiguous "something IC happened here" line (#885).

    The audience-side half of the mission play loop — when a character
    resolves a mission beat (and, by design, when future GM events / room
    triggers / magic emit ambience), bystanders in the room receive a line
    drawn from this pool. The pool is deliberately GENERIC and shared
    across all emitting systems so observers cannot tell what stirred —
    the ambiguity is the RP bait (design tenet: audience sees ambiguity,
    actor sees clarity).

    Rows are staff-authored (admin-editable per the flavor-text rule —
    never hardcoded prose). An empty pool means no ambient emission, never
    an error.
    """

    body = models.TextField(
        help_text=(
            "The ambient line shown to bystanders. Keep it source-ambiguous "
            "— it must read the same whether a mission, a GM event, or "
            "magic stirred the room."
        ),
    )
    weight = models.PositiveIntegerField(
        default=1,
        help_text="Relative draw weight within the active pool.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive lines stay authored but are never drawn.",
    )

    def __str__(self) -> str:
        truncated = len(self.body) > _STR_PREVIEW_LEN
        preview = self.body[:_STR_PREVIEW_LEN] + ("..." if truncated else "")
        return f"AmbientStirLine({preview})"


class NarrativeMessageDelivery(SharedMemoryModel):
    """Per-recipient delivery state for a NarrativeMessage.

    One row per (message, character_sheet) pair. A single message can
    fan out to many recipients (e.g., a GM sends a covenant-wide message
    to 5 of 8 members — that's one NarrativeMessage and 5 Delivery rows).
    """

    message = models.ForeignKey(
        NarrativeMessage,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    recipient_character_sheet = models.ForeignKey(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="narrative_message_deliveries",
    )
    delivered_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Timestamp when the message was pushed to the character's puppeted "
            "session. Null until online delivery or login catch-up delivers it."
        ),
    )
    acknowledged_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Timestamp when the player acknowledged having seen the message. "
            "Null until the player marks it read. Used to distinguish 'unread' "
            "in future UI work."
        ),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["message", "recipient_character_sheet"],
                name="unique_delivery_per_message_per_recipient",
            )
        ]
        indexes = [
            models.Index(fields=["recipient_character_sheet", "delivered_at"]),
            models.Index(fields=["recipient_character_sheet", "acknowledged_at"]),
        ]

    def __str__(self) -> str:
        state = "delivered" if self.delivered_at else "queued"
        return (
            f"NarrativeMessageDelivery(msg=#{self.message_id}, "
            f"sheet=#{self.recipient_character_sheet_id}, {state})"
        )


class Gemit(SharedMemoryModel):
    """A staff-sent real-time broadcast (#1450).

    Persistent record so the audience can browse retroactively. Does NOT
    fan out into NarrativeMessageDelivery rows — gemit is broadcast, not
    per-recipient. ``reach`` scopes the audience: GAME_WIDE reaches every
    online session; SPECIFIED reaches the members of any combination of the
    linked ``reach_societies`` and/or ``reach_organizations`` (not exclusive).
    """

    body = models.TextField(
        help_text="Broadcast text shown to the audience (staff-authored verbatim, colour and all).",
    )
    reach = models.CharField(
        max_length=20,
        choices=GemitReach.choices,
        default=GemitReach.GAME_WIDE,
        help_text="Audience scope: game-wide, or the members of the linked societies / orgs.",
    )
    reach_societies = models.ManyToManyField(
        "arxii.Society",
        blank=True,
        related_name="gemits",
        help_text="SPECIFIED-reach societies whose members get this gemit (mixable with orgs).",
    )
    reach_organizations = models.ManyToManyField(
        "arxii.Organization",
        blank=True,
        related_name="gemits",
        help_text="For SPECIFIED reach, organizations whose members receive this gemit (may mix).",
    )
    sender_account = models.ForeignKey(
        _ACCOUNT_DB_FK,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gemits_sent",
        help_text="Null = system-generated.",
    )
    related_era = models.ForeignKey(
        "arxii.Era",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gemits",
        help_text="Optional: link to the era this gemit relates to.",
    )
    related_story = models.ForeignKey(
        _STORY_FK,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gemits",
        help_text="Optional: link to a specific story this gemit relates to.",
    )
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["-sent_at"]),
            models.Index(fields=["sender_account", "-sent_at"]),
        ]

    def __str__(self) -> str:
        truncated = len(self.body) > _GEMIT_PREVIEW_LEN
        preview = self.body[:_GEMIT_PREVIEW_LEN] + ("..." if truncated else "")
        return f"Gemit #{self.pk}: {preview}"


class UserStoryMute(SharedMemoryModel):
    """A user's preference to suppress real-time narrative pushes for a specific story.

    Does NOT gate read access — muted users still see the story in their
    dashboard and can browse the log. Only suppresses the live
    character.msg() push when narrative messages fire on that story.
    """

    account = models.ForeignKey(
        _ACCOUNT_DB_FK,
        on_delete=models.CASCADE,
        related_name="story_mutes",
    )
    story = models.ForeignKey(
        _STORY_FK,
        on_delete=models.CASCADE,
        related_name="muted_by",
    )
    muted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["account", "story"],
                name="unique_user_story_mute",
            )
        ]
        indexes = [
            models.Index(fields=["account", "story"]),
        ]

    def __str__(self) -> str:
        return f"UserStoryMute(account=#{self.account_id}, story=#{self.story_id})"


class UserCategoryMute(SharedMemoryModel):
    """A user's preference to suppress real-time pushes for a whole narrative category.

    The category-level analogue of ``UserStoryMute`` (e.g. mute the ``WEATHER`` echo). Like that
    model, it does NOT gate read access — muted messages still create delivery rows and remain
    readable in the category's tab; only the live ``character.msg()`` push is skipped.
    """

    account = models.ForeignKey(
        _ACCOUNT_DB_FK,
        on_delete=models.CASCADE,
        related_name="category_mutes",
    )
    category = models.CharField(max_length=20, choices=NarrativeCategory.choices)
    muted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["account", "category"],
                name="unique_user_category_mute",
            )
        ]
        indexes = [
            models.Index(fields=["account", "category"]),
        ]

    def __str__(self) -> str:
        return f"UserCategoryMute(account=#{self.account_id}, category={self.category})"


class AmbientEmoteLine(DiscriminatorMixin, SharedMemoryModel):
    """An authored room/area-entry reaction — plain atmosphere or category-conditional
    (#2471 v2).

    Zero ``AmbientEmoteCondition`` rows = unconditional plain atmosphere (private to the
    arriver). One or more conditions (joined by ``condition_connector``) compile to a real
    Trigger-system filter (``world.narrative.ambient_content.compile_line_filter``) —
    condition matching itself lives in the DSL, not in application code. Room-wide
    (arriver + bystanders, actor/audience split) when conditional; private when not.

    Attach point is Area or Room (``parent_type``, most-specific-wins **per condition
    group** — see ``core_management.grid_import._install_ambient_triggers``), mirroring
    ``world.locations.LocationValueOverride``.
    """

    DISCRIMINATOR_FIELD = "parent_type"
    DISCRIMINATOR_MAP = {
        LocationParentType.AREA: "area",
        LocationParentType.ROOM: "room_profile",
    }

    parent_type = models.CharField(
        max_length=10,
        choices=LocationParentType.choices,
        help_text="Selects which FK (area or room_profile) is active.",
    )
    area = models.ForeignKey(
        "arxii.Area",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="ambient_emote_lines",
    )
    room_profile = models.ForeignKey(
        "arxii.RoomProfile",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="ambient_emote_lines",
    )

    condition_connector = models.CharField(
        max_length=3,
        choices=ConditionConnector.choices,
        default=ConditionConnector.AND,
        help_text="How this line's conditions combine. Ignored with 0-1 conditions.",
    )

    bystander_body = models.TextField(
        blank=True,
        help_text="What the room's other occupants see. Leave empty for unconditional lines.",
    )
    arriver_body = models.TextField(
        blank=True,
        help_text="What the arriving character sees.",
    )

    weight = models.PositiveIntegerField(
        default=1,
        help_text="Relative draw weight among this condition-group's own lines.",
    )
    fire_chance = models.PositiveIntegerField(
        default=100,
        help_text="0-100: probability this line fires once selected. Dial down noisy rooms.",
    )
    cooldown_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Re-fire throttle after this line fires, scoped to the line itself.",
    )
    last_fired_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Runtime only — never exported to the lore repo grid bundle.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["parent_type", "id"]

    def clean(self) -> None:
        errors: dict[str, str] = self._validate_discriminator(
            self.DISCRIMINATOR_FIELD, self.DISCRIMINATOR_MAP
        )
        if not self.bystander_body and not self.arriver_body:
            errors.setdefault(
                "arriver_body", "Author at least one of bystander_body / arriver_body."
            )
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        target = self.get_active_target_name()
        return f"AmbientEmoteLine(@ {target})"


class AmbientEmoteCondition(SharedMemoryModel):
    """One leaf condition on an AmbientEmoteLine (#2471 v2).

    Compiles to one DSL filter leaf — see
    ``world.narrative.ambient_content.compile_line_filter``. Multiple conditions on the
    same line combine via the line's ``condition_connector``.
    """

    line = models.ForeignKey(
        AmbientEmoteLine,
        on_delete=models.CASCADE,
        related_name="conditions",
    )
    condition_type = models.CharField(max_length=20, choices=ConditionType.choices)
    species = models.ForeignKey(
        "arxii.Species",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
        help_text="Required when condition_type is SPECIES.",
    )
    resonance = models.ForeignKey(
        "arxii.Resonance",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
        help_text="Required when condition_type is RESONANCE_MIN (with minimum_value).",
    )
    minimum_value = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Minimum lifetime_earned for resonance. Required when condition_type is RESONANCE_MIN."
        ),
    )
    distinction = models.ForeignKey(
        "arxii.Distinction",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
        help_text="Required when condition_type is DISTINCTION.",
    )
    min_fame_tier = models.CharField(
        max_length=20,
        choices=FameTier.choices,
        blank=True,
        default="",
        help_text="Required when condition_type is RENOWN_MIN.",
    )
    perceiving_society = models.ForeignKey(
        "arxii.Society",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="+",
        help_text=(
            "RENOWN_MIN only: perceive the arriver's fame tier through this society's "
            "fame_perception_offset. Null = raw fame tier."
        ),
    )

    class Meta:
        ordering = ["line", "id"]

    def clean(self) -> None:
        errors: dict[str, str] = {}
        if self.condition_type == ConditionType.SPECIES:
            if not self.species_id:
                errors["species"] = "Required when condition_type is SPECIES."
        elif self.condition_type == ConditionType.RESONANCE_MIN:
            if not self.resonance_id:
                errors["resonance"] = "Required when condition_type is RESONANCE_MIN."
            if not self.minimum_value:
                errors["minimum_value"] = "Required when condition_type is RESONANCE_MIN."
        elif self.condition_type == ConditionType.DISTINCTION:
            if not self.distinction_id:
                errors["distinction"] = "Required when condition_type is DISTINCTION."
        elif self.condition_type == ConditionType.RENOWN_MIN and not self.min_fame_tier:
            errors["min_fame_tier"] = "Required when condition_type is RENOWN_MIN."
        if errors:
            raise ValidationError(errors)

    def save(self, *args: object, **kwargs: object) -> None:
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"AmbientEmoteCondition({self.condition_type} on line #{self.line_id})"


class AmbientEmit(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """A periodic room-linger flavor line — plain atmosphere or a room-state risk telegraph
    (#2988).

    Fires while occupants remain in a room, not just on arrival (the gap
    ``AmbientEmoteLine`` — entry-triggered — doesn't cover). One model serves both roaming
    flavor and risk telegraphing: the only difference is whether ``gate_stat_key`` is set. A
    "CRIME >= 60" row telegraphs a seedy district; an ungated row is plain atmosphere. No
    NPC/encounter spawning lives here — text only (#2378 is the spawner, off this same
    substrate, later).

    Location scope is plain nullable FKs, NOT a ``DiscriminatorMixin`` pair (unlike
    ``AmbientEmoteLine``): most rows have no scope at all (a generic "eyes in the shadows"
    risk line fires in any CRIME-cleared room). ``room_profile`` set = this room only;
    ``area`` set = this subtree; neither set = generic pool. Selection
    (``world.narrative.ambient_texture.select_ambient_emit``) picks the most-specific
    non-empty scope pool (room > area > generic), mirroring the location cascade's
    most-specific-wins convention without reusing its cascade walk (pool selection, not a
    stat/resonance axis).
    """

    key = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
        help_text=(
            "Stable identity, e.g. 'market-bustle-003' or 'crime-telegraph-007' "
            "(#2980-style convention). Assigned once, never recomputed from the text — "
            "the text is what a writer rewrites in place."
        ),
    )
    text = models.TextField(help_text="The line shown to the room. PLACEHOLDER.")
    gm_notes = models.TextField(blank=True, default="")
    weight = models.PositiveIntegerField(
        default=1,
        help_text="Relative weight in weighted-random selection within its scope pool.",
    )
    cooldown_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Re-fire throttle after this row fires, scoped to the row itself.",
    )
    last_fired_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Runtime only — never exported to the content repo.",
    )

    # Location scope — plain nullable FKs (see class docstring): most rows carry neither.
    area = models.ForeignKey(
        "arxii.Area",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="ambient_emits",
    )
    room_profile = models.ForeignKey(
        "arxii.RoomProfile",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="ambient_emits",
    )

    # Room-state gate — single axis per row (mirrors WeatherType's min/max_temperature shape).
    # Blank/empty = ungated (plain flavor, no risk signal).
    gate_stat_key = models.CharField(
        max_length=20,
        choices=StatKey.choices,
        blank=True,
        default="",
        help_text="The world.locations stat axis this row telegraphs. Blank = ungated.",
    )
    gate_min = models.SmallIntegerField(
        null=True,
        blank=True,
        help_text="Row fires only when the room's cascade-resolved gate_stat_key >= this.",
    )
    gate_max = models.SmallIntegerField(
        null=True,
        blank=True,
        help_text="Row fires only when the room's cascade-resolved gate_stat_key <= this.",
    )

    # Season gates (IC calendar season from game_clock; AUTUMN <- Arx-1 "fall").
    in_spring = models.BooleanField(default=False)
    in_summer = models.BooleanField(default=False)
    in_autumn = models.BooleanField(default=False)
    in_winter = models.BooleanField(default=False)
    # Time-of-day gates (game_clock TimePhase).
    at_dawn = models.BooleanField(default=False)
    at_day = models.BooleanField(default=False)
    at_dusk = models.BooleanField(default=False)
    at_night = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]

    class NaturalKeyConfig:
        fields = ["key"]

    objects = NaturalKeyManager()

    def __str__(self) -> str:
        return f"AmbientEmit #{self.pk}"
