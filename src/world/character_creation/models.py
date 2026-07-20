"""
Character Creation models.

Models for the staged character creation flow:
- StartingArea: Selectable origin locations that gate heritage options
- Beginnings: Worldbuilding paths (e.g., Sleeper, Normal Upbringing) for each area
- CharacterDraft: In-progress character creation state
"""

from __future__ import annotations

from datetime import timedelta
import logging

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Prefetch
from django.utils import timezone
from django.utils.functional import cached_property
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper.models import SharedMemoryModel
from rest_framework import serializers

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.character_creation.constants import (
    AGE_MAX,
    AGE_MIN,
    CG_MODIFIER_CATEGORY,
    REQUIRED_STATS,
    STARTING_TECHNIQUE_PICKS_TARGET,
    STAT_DEFAULT_VALUE,
    STAT_DISPLAY_DIVISOR,
    ApplicationStatus,
    CommentType,
    Stage,
    StartingAreaAccessLevel,
)
from world.character_creation.types import (
    CGPointBreakdownEntry,
    StageValidationErrors,
)
from world.classes.models import PathStage

logger = logging.getLogger(__name__)


class CGPointBudget(NaturalKeyMixin, SharedMemoryModel):
    """
    Global CG point budget configuration.

    Single-row model for configuring the character creation point budget.
    Staff can change this without code changes.
    """

    name = models.CharField(
        max_length=100,
        default="Default Budget",
        help_text="Name for this budget configuration",
    )
    starting_points = models.IntegerField(
        default=100,
        help_text="Starting CG points for character creation",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this budget is currently active",
    )
    xp_conversion_rate = models.PositiveIntegerField(
        default=2,
        help_text="XP awarded per unspent CG point (e.g., 2 means 2 XP per 1 CG point)",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        verbose_name = "CG Point Budget"
        verbose_name_plural = "CG Point Budgets"

    def __str__(self) -> str:
        active = " (Active)" if self.is_active else ""
        return f"{self.name}: {self.starting_points} points{active}"

    @classmethod
    def get_active_budget(cls) -> int:
        """Get the current active CG point budget."""
        budget = cls.objects.filter(is_active=True).first()
        return budget.starting_points if budget else 100

    @classmethod
    def get_active_conversion_rate(cls) -> int:
        """Get the current active CG point to XP conversion rate."""
        budget = cls.objects.filter(is_active=True).first()
        return budget.xp_conversion_rate if budget else 2


class StartingArea(NaturalKeyMixin, SharedMemoryModel):
    """
    A starting location/city that players can select in character creation.

    Each area gates which heritage options, species, and families are available.
    Maps to an Evennia room for character starting location.

    Note: ``default_starting_room`` may be unset on a hand-built row (a staff
    config gap) — ``CharacterDraft.get_starting_room()`` falls back to the
    canonical seeded room + logs a warning in that case (#2121); it never
    silently spawns a character with ``location=None``.
    """

    # Alias for backward compatibility — canonical definition is in constants.py
    AccessLevel = StartingAreaAccessLevel

    # Canonical realm this StartingArea references (data lives in `realms.Realm`)
    realm = models.ForeignKey(
        "realms.Realm",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="starting_areas",
        help_text="Canonical realm/area referenced by this StartingArea (realms app).",
    )

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Display name of the starting area (e.g., 'Arx')",
    )
    description = models.TextField(
        help_text="Rich description shown on hover/click in character creation",
    )
    crest_art = models.ForeignKey(
        "evennia_extensions.Media",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="starting_area_crests",
        help_text="Crest/flag art for this area. Leave unset for gradient placeholder.",
    )
    default_starting_room = models.ForeignKey(
        "evennia_extensions.RoomProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="starting_area_default",
        help_text="Default room (via its RoomProfile) where characters from this area "
        "start. A staff config gap if unset — get_starting_room() falls back to the "
        "canonical seeded room (#2121).",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this area can be selected in character creation",
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display order in selection UI (lower = first)",
    )
    access_level = models.CharField(
        max_length=20,
        choices=AccessLevel.choices,
        default=AccessLevel.ALL,
        help_text="Who can select this area in character creation",
    )
    minimum_trust = models.IntegerField(
        default=0,
        help_text="Minimum trust required when access_level is 'trust_required'",
    )
    grants_residence_tenancy = models.BooleanField(
        default=True,
        help_text="Whether finalizing a character here grants a LocationTenancy at the "
        "starting room (#2036) — auto-defaulting current_residence via "
        "maybe_default_residence, so the daily residence-trickle gate is reachable with "
        "zero manual player step. An authored per-area toggle: not every starting area "
        "need be residence-backed (e.g. a staff testing area with no real dorm room).",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Starting Area"
        verbose_name_plural = "Starting Areas"

    def __str__(self) -> str:
        return self.name

    def is_accessible_by(self, account: AccountDB) -> bool:
        """Check if an account can select this starting area."""
        if not self.is_active:
            return False

        # Staff bypass all restrictions
        if account.is_staff:
            return True

        if self.access_level == self.AccessLevel.STAFF_ONLY:
            return False

        if self.access_level == self.AccessLevel.TRUST_REQUIRED:
            # TODO: Implement trust system - this will raise AttributeError until then
            try:
                account_trust = account.trust
            except AttributeError:
                msg = "Trust system not yet implemented on Account model"
                raise NotImplementedError(msg) from None
            return account_trust >= self.minimum_trust

        return True  # AccessLevel.ALL


class Beginnings(NaturalKeyMixin, SharedMemoryModel):
    """
    Character creation worldbuilding paths for each starting area.

    Replaces SpecialHeritage with a universal system that provides worldbuilding
    context for all paths (not just special ones). Each Beginnings option can
    gate which species are available and whether family is selectable.

    Examples:
    - Arx: "Normal Upbringing", "Sleeper", "Misbegotten"
    - Umbros: "Noble Birth", "Military Caste", "Servant Class"
    - Luxen: "Patrician Elite", "Merchant Class", "Khati Underclass"
    """

    name = models.CharField(
        max_length=100,
        help_text="Display name (e.g., 'Sleeper', 'Noble Birth')",
    )
    description = models.TextField(
        help_text="Worldbuilding text shown to players",
    )
    art = models.ForeignKey(
        "evennia_extensions.Media",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="beginnings_art",
        help_text="Visual presentation art for this beginnings path.",
    )
    starting_area = models.ForeignKey(
        StartingArea,
        on_delete=models.CASCADE,
        related_name="beginnings",
        help_text="The starting area this option belongs to",
    )
    trust_required = models.IntegerField(
        default=0,
        help_text="Minimum trust level required to see/select this option",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Staff toggle to enable/disable this option",
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display order in selection UI (lower = first)",
    )
    family_known = models.BooleanField(
        default=True,
        help_text="Whether family is selectable in Lineage stage (False = 'Unknown')",
    )
    allowed_species = models.ManyToManyField(
        "species.Species",
        blank=True,
        related_name="beginnings",
        help_text="Species available for this path. Parent species include all children.",
    )
    starting_languages = models.ManyToManyField(
        "species.Language",
        blank=True,
        related_name="beginnings",
        help_text="Languages granted to all characters from this path",
    )
    grants_species_languages = models.BooleanField(
        default=True,
        help_text="If False, characters don't get species' racial language (Misbegotten)",
    )
    # TODO: Implement finalize_character integration to grant society awareness/membership
    # based on this field. See societies system design doc for details.
    societies = models.ManyToManyField(
        "societies.Society",
        blank=True,
        related_name="connected_beginnings",
        help_text="Societies characters gain awareness/membership in during character creation",
    )
    traditions = models.ManyToManyField(
        "magic.Tradition",
        through="BeginningTradition",
        blank=True,
        related_name="available_beginnings",
        help_text="Traditions available for this beginning during CG.",
    )

    objects = NaturalKeyManager()

    social_rank = models.IntegerField(
        default=0,
        help_text="Staff-only rank for determining noble/commoner/royal (not exposed to players)",
    )
    cg_point_cost = models.IntegerField(
        default=0,
        help_text="CG point cost for this beginning; summed with species gift "
        "grant costs into the character-creation points budget.",
    )
    heritage = models.ForeignKey(
        "character_sheets.Heritage",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="beginnings",
        help_text="Heritage type for characters with this beginning "
        "(e.g., Sleeper, Misbegotten). "
        "Null defaults to 'Normal' heritage at finalization.",
    )
    starting_room_override = models.ForeignKey(
        ObjectDB,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="beginnings_start",
        help_text="Override starting room for this Beginnings path (e.g., Sleeper wake room)",
    )
    property_grant_profile = models.ForeignKey(
        "buildings.PropertyGrantProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="beginnings",
        help_text=(
            "Granted automatically at finalize_character when set. "
            "NULL = no automatic property grant for this path."
        ),
    )
    prelude_mission = models.ForeignKey(
        "missions.MissionTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "The prelude Mission auto-granted at CG finalization for characters "
            "choosing this Beginning (#2470). Null = no auto-grant (e.g. content "
            "not authored yet for this Beginning)."
        ),
    )

    class NaturalKeyConfig:
        fields = ["starting_area", "name"]
        dependencies = ["character_creation.StartingArea"]

    class Meta:
        verbose_name = "Beginnings"
        verbose_name_plural = "Beginnings"
        unique_together = [["starting_area", "name"]]

    def __str__(self) -> str:
        return f"{self.name} ({self.starting_area.name})"

    @cached_property
    def cached_allowed_species(self) -> list:
        """
        Get allowed species with prefetch support.

        This cached_property serves as the target for Prefetch(..., to_attr=).
        When prefetched, Django populates this directly. When accessed without
        prefetch, falls back to a fresh query.

        To invalidate: del instance.cached_allowed_species
        """
        return list(self.allowed_species.all())

    @cached_property
    def cached_starting_languages(self) -> list:
        """
        Get starting languages with prefetch support.

        This cached_property serves as the target for Prefetch(..., to_attr=).
        When prefetched, Django populates this directly. When accessed without
        prefetch, falls back to a fresh query.

        To invalidate: del instance.cached_starting_languages
        """
        return list(self.starting_languages.all())

    @cached_property
    def cached_beginning_traditions(self) -> list[BeginningTradition]:
        """All BeginningTradition rows for this Beginning, ordered for CG.

        Returns BT rows with ``tradition`` and ``required_distinction``
        select_related, sorted by ``(sort_order, id)``. The list is the same
        for every caller asking about a given Beginning, so caching on the
        SharedMemoryModel-instance is the correct location: populated once
        per Beginning per process, reused across all subsequent requests.

        Use this from views/serializers instead of viewset-scoped helpers.

        To invalidate: ``del instance.cached_beginning_traditions``.
        """
        from world.codex.models import TraditionCodexGrant  # noqa: PLC0415

        return list(
            self.beginning_traditions.select_related("tradition", "required_distinction")
            .prefetch_related(
                Prefetch(
                    "tradition__codex_grants",
                    queryset=TraditionCodexGrant.objects.only("tradition_id", "entry_id"),
                    to_attr="cached_codex_grants",
                ),
            )
            .order_by("sort_order", "id")
        )

    @cached_property
    def cached_codex_grants(self) -> list:
        """Codex grants — the Prefetch/query shared interface (#2386).

        Authored content: negligible staleness on the identity-mapped row.
        """
        return list(self.codex_grants.all())

    def is_accessible_by(self, account: AccountDB) -> bool:
        """Check if an account can see/select this option."""
        if not self.is_active:
            return False

        if account.is_staff:
            return True

        if self.trust_required > 0:
            try:
                account_trust = account.trust
            except AttributeError:
                return self.trust_required == 0
            return account_trust >= self.trust_required

        return True

    def get_available_species(self) -> models.QuerySet:
        """
        Get all species available for this Beginnings, expanding parents to children.

        If a parent species (e.g., Khati) is in allowed_species, all its children
        (Vulpi, Cani, etc.) are available. Leaf species are returned directly.

        Returns:
            QuerySet of Species that can be selected for this path
        """
        from world.species.models import Species  # noqa: PLC0415

        result_ids = set()
        for species in self.allowed_species.all():
            children = species.children.all()
            if children.exists():
                # Parent species - add all children
                result_ids.update(children.values_list("id", flat=True))
            else:
                # Leaf species - add directly
                result_ids.add(species.id)
        return Species.objects.filter(id__in=result_ids).order_by("sort_order", "name")

    def get_starting_languages(self, species: models.Model) -> models.QuerySet:
        """
        Get starting languages for a character with this Beginnings and species.

        Args:
            species: The selected Species

        Returns:
            QuerySet of Language objects
        """
        from world.species.models import Language  # noqa: PLC0415

        language_ids = set(self.starting_languages.values_list("id", flat=True))
        if self.grants_species_languages:
            language_ids.update(species.starting_languages.values_list("id", flat=True))
        return Language.objects.filter(id__in=language_ids)


class BeginningTradition(NaturalKeyMixin, SharedMemoryModel):
    """Maps which traditions are available for each beginning during CG.
    CG-only concern -- traditions exist independently post-CG."""

    beginning = models.ForeignKey(
        Beginnings,
        on_delete=models.CASCADE,
        related_name="beginning_traditions",
    )
    tradition = models.ForeignKey(
        "magic.Tradition",
        on_delete=models.CASCADE,
        related_name="beginning_traditions",
    )
    required_distinction = models.ForeignKey(
        "distinctions.Distinction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Distinction required to select this tradition for this beginning.",
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display order within this beginning's tradition list.",
    )

    class Meta:
        unique_together = ["beginning", "tradition"]
        ordering = ["sort_order"]
        verbose_name = "Beginning Tradition"
        verbose_name_plural = "Beginning Traditions"

    class NaturalKeyConfig:
        fields = ["beginning", "tradition"]

    objects = NaturalKeyManager()

    def __str__(self) -> str:
        return f"{self.beginning} -> {self.tradition}"


class OriginTemplateManager(NaturalKeyManager):
    """Manager for OriginTemplate with natural key support."""


class OriginTemplate(NaturalKeyMixin, SharedMemoryModel):
    """Authored origin-story frame for a Beginning (#2478).

    Content model — authored in the lore repo, exported/imported via
    ``CONTENT_MODELS``. No factory-seeded catalog. Multiple templates per
    beginning are allowed (Decision 1); today one active template auto-assigns.

    No slug field — natural key is (beginning, name), mirroring ``Beginnings``
    itself (``["starting_area", "name"]``) and ``BeginningTradition``
    (``["beginning", "tradition"]``).
    """

    beginning = models.ForeignKey(
        Beginnings,
        on_delete=models.CASCADE,
        related_name="origin_templates",
        help_text="The beginning this origin-story frame belongs to.",
    )
    name = models.CharField(max_length=100, help_text="Template name (part of natural key).")
    frame_narrative = models.TextField(
        help_text="The fixed frame prose every character with this beginning shares."
    )
    is_active = models.BooleanField(
        default=True, help_text="Inactive templates are hidden from CG."
    )
    sort_order = models.PositiveSmallIntegerField(
        default=0, help_text="Display order when multiple templates exist."
    )

    objects = OriginTemplateManager()

    class Meta:
        verbose_name = "Origin Template"
        verbose_name_plural = "Origin Templates"
        unique_together = [["beginning", "name"]]
        ordering = ["beginning", "sort_order", "name"]

    class NaturalKeyConfig:
        fields = ["beginning", "name"]
        dependencies = ["character_creation.Beginnings"]

    def __str__(self) -> str:
        return self.name


class OriginTemplateSlotManager(NaturalKeyManager):
    """Manager for OriginTemplateSlot with natural key support."""


class OriginTemplateSlot(NaturalKeyMixin, SharedMemoryModel):
    """Authored slot prompt within an origin-story template (#2478).

    Content model — authored in the lore repo. No slug — natural key is
    (template, name), mirroring ``BeginningTradition``.
    """

    template = models.ForeignKey(
        OriginTemplate,
        on_delete=models.CASCADE,
        related_name="slots",
        help_text="The template this slot belongs to.",
    )
    name = models.CharField(max_length=100, help_text="Slot name (part of natural key).")
    prompt = models.TextField(help_text="The question shown to the player.")
    example = models.TextField(
        blank=True, help_text="Short illustrative answer shown in the guided step."
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_required = models.BooleanField(
        default=True,
        help_text="Required slots are marked in the post-CG finish-later editor.",
    )

    objects = OriginTemplateSlotManager()

    class Meta:
        verbose_name = "Origin Template Slot"
        verbose_name_plural = "Origin Template Slots"
        unique_together = [["template", "name"]]
        ordering = ["template", "sort_order", "name"]

    class NaturalKeyConfig:
        fields = ["template", "name"]
        dependencies = ["character_creation.OriginTemplate"]

    def __str__(self) -> str:
        return self.name


class CharacterOriginSlot(SharedMemoryModel):
    """A character's authored answer to an origin-story slot (#2478).

    Instance data — NOT a content model, never exported. Mirrors
    ``CharacterGlimpseTag`` (``glimpse.py:65-88``).
    """

    sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="origin_slots",
        help_text="The character sheet this slot answer belongs to.",
    )
    slot = models.ForeignKey(
        OriginTemplateSlot,
        on_delete=models.PROTECT,
        related_name="character_rows",
        help_text="The catalog slot this answer fills.",
    )
    value = models.TextField(help_text="The player's authored answer.")

    class Meta:
        verbose_name = "Character Origin Slot"
        verbose_name_plural = "Character Origin Slots"
        unique_together = [["sheet", "slot"]]
        ordering = ["slot__sort_order"]

    def __str__(self) -> str:
        return f"{self.slot} on {self.sheet}"


class CharacterDraft(SharedMemoryModel):
    """
    In-progress character creation state.

    Stores all staged data as JSON, allowing players to leave and return
    without losing progress. Drafts expire after 2 months of account inactivity.
    """

    # Stage enum imported from constants.py for easier external access
    Stage = Stage

    # Ownership
    account = models.ForeignKey(
        AccountDB,
        on_delete=models.CASCADE,
        related_name="character_drafts",
        help_text="Account creating this character",
    )
    # TODO: Add table FK when Table model exists
    # table = models.ForeignKey(
    #     "tables.Table",
    #     on_delete=models.SET_NULL,
    #     null=True,
    #     blank=True,
    #     help_text="GM table this character is being created for (staff/GM only)",
    # )

    # Stage tracking
    current_stage = models.PositiveSmallIntegerField(
        choices=Stage.choices,
        default=Stage.ORIGIN,
        help_text="Current stage in character creation flow",
    )

    # Stage 1: Origin
    selected_area = models.ForeignKey(
        StartingArea,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drafts",
        help_text="Selected starting area",
    )

    # Stage 2: Heritage
    selected_beginnings = models.ForeignKey(
        "Beginnings",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drafts",
        help_text="Selected beginnings path",
    )

    selected_species = models.ForeignKey(
        "species.Species",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drafts",
        help_text="Selected species",
    )

    selected_gender = models.ForeignKey(
        "character_sheets.Gender",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drafts",
        help_text="Selected gender",
    )

    age = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(AGE_MIN), MaxValueValidator(AGE_MAX)],
        help_text=f"Character age in years ({AGE_MIN}-{AGE_MAX})",
    )

    # Stage 9: Identity — worship declarations (#2355)
    public_worship = models.ForeignKey(
        "worship.WorshippedBeing",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={"is_active": True},
        related_name="+",
        help_text="The being this character publicly worships (optional).",
    )
    secret_worship = models.ForeignKey(
        "worship.WorshippedBeing",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={"is_active": True},
        related_name="+",
        help_text=(
            "The being this character SECRETLY worships — the public faith is a front; "
            "finalization mints a Secret."
        ),
    )

    # Stage 3: Lineage (merged into Heritage in new flow)
    family = models.ForeignKey(
        "roster.Family",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="character_drafts",
        help_text="Selected family (null for orphan or special heritage).",
    )
    # Kinship slot claim (#2062): the appable node or pool this OC fills.
    claimed_kin_slot = models.ForeignKey(
        "roster.Kinsperson",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drafts",
        help_text="Appable kinship node this character claims at finalization.",
    )
    claimed_kin_pool = models.ForeignKey(
        "roster.KinSlotPool",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drafts",
        help_text="Slot pool a node is minted from at finalization.",
    )
    defer_parents = models.BooleanField(
        default=False,
        help_text=(
            "CG deferral (#2062): leave parents deliberately undefined, to be "
            "filled later through review."
        ),
    )
    # Note: orphan intent can be represented in draft_data to avoid extra boolean field.

    # Stage 5: Path
    selected_path = models.ForeignKey(
        "classes.Path",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={"stage": PathStage.PROSPECT, "is_active": True},
        related_name="drafts",
        help_text="Selected starting path (Prospect stage only)",
    )
    selected_tradition = models.ForeignKey(
        "magic.Tradition",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Selected magical tradition (gates magic template).",
    )

    # Stage 7: Appearance
    height_band = models.ForeignKey(
        "forms.HeightBand",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drafts",
        help_text="Selected height band for CG",
    )
    height_inches = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Exact height in inches within the selected band",
    )
    build = models.ForeignKey(
        "forms.Build",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drafts",
        help_text="Selected build type",
    )

    # Stage 4-7: Complex data stored as JSON
    draft_data = models.JSONField(
        default=dict,
        help_text="Staged data: stats, skills, traits, identity, etc.",
    )

    # GM roster character creation fields
    is_gm_creation = models.BooleanField(
        default=False,
        help_text="GM is designing a roster character, not playing one.",
    )
    target_table = models.ForeignKey(
        "gm.GMTable",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="draft_characters",
        help_text="Which GM table the finalized character will belong to. "
        "Required at finalize for GM drafts.",
    )
    story_title = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Title for the Story created at finalize (GM drafts only).",
    )
    story_description = models.TextField(
        blank=True,
        default="",
        help_text="Description for the Story created at finalize (GM drafts only).",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Character Draft"
        verbose_name_plural = "Character Drafts"

    def __str__(self) -> str:
        name = self.draft_data.get("first_name", "Unnamed")
        account_name = self.account.username if self.account else "No Account"
        return f"Draft: {name} ({account_name})"

    @property
    def is_expired(self) -> bool:
        """Check if draft has expired due to account inactivity."""
        # Staff drafts don't expire
        if self.account and self.account.is_staff:
            return False

        # Expire after 2 months of no updates
        expiry_threshold = timezone.now() - timedelta(days=60)
        return self.updated_at < expiry_threshold

    def get_starting_room(self) -> ObjectDB | None:
        """
        Determine the starting room for this character.

        Priority:
        1. Beginnings starting_room_override (e.g., Sleeper wake room)
        2. StartingArea default_starting_room
        3. The canonical fallback room seeded by
           ``world.seeds.character_creation.ensure_canonical_fallback_room`` (#2121)
           — logged loudly, since it means a staff config gap (an unwired
           Beginnings/StartingArea), not expected steady-state. Never
           ``location=None``: a config gap the player can't fix must not
           block their finalize.
        4. None — only when even the canonical fallback room hasn't been
           seeded (e.g. a raw DB that never ran the Big Button). Logged as an
           error; callers must not assume this can't happen.
        """
        if self.selected_beginnings and self.selected_beginnings.starting_room_override:
            return self.selected_beginnings.starting_room_override

        if self.selected_area and self.selected_area.default_starting_room:
            return self.selected_area.default_starting_room.objectdb

        from world.character_creation.constants import (  # noqa: PLC0415
            FALLBACK_STARTING_ROOM_KEY,
            FALLBACK_STARTING_ROOM_TYPECLASS,
        )

        fallback = ObjectDB.objects.filter(
            db_key=FALLBACK_STARTING_ROOM_KEY,
            db_typeclass_path=FALLBACK_STARTING_ROOM_TYPECLASS,
        ).first()
        if fallback is not None:
            logger.warning(
                "CharacterDraft %s has no Beginnings/StartingArea starting room "
                "wired — falling back to the canonical seeded room %r.",
                self.pk,
                fallback.db_key,
            )
            return fallback

        logger.error(
            "CharacterDraft %s has no Beginnings/StartingArea starting room, and "
            "the canonical fallback room is not seeded — character will spawn "
            "with location=None. Run the Big Button seed to fix this.",
            self.pk,
        )
        return None

    def get_stage_completion(self) -> dict[int, bool]:
        """
        Check completion status of each stage.

        Returns dict mapping stage number to completion boolean.
        Uses get_stage_validation_errors() so both share cached computation.
        """
        errors = self.get_stage_validation_errors()
        return {
            stage: not errors.get(stage, []) for stage in self.Stage if stage != self.Stage.REVIEW
        } | {self.Stage.REVIEW: False}

    def get_stage_validation_errors(self) -> StageValidationErrors:
        """
        Get validation errors for each stage.

        Returns dict mapping stage number to list of error messages.
        Empty list means the stage is complete. Result is cached on the
        instance so get_stage_completion() and serializer share computation.
        """
        if hasattr(self, "_cached_stage_errors"):
            return self._cached_stage_errors

        from world.character_creation.validators import get_all_stage_errors  # noqa: PLC0415

        errors = get_all_stage_errors(self)
        self._cached_stage_errors = errors
        return errors

    def _is_heritage_complete(self) -> bool:
        """Check if heritage stage is complete."""
        return not self.get_stage_validation_errors().get(self.Stage.HERITAGE, [])

    def _is_lineage_complete(self) -> bool:
        """Check if lineage stage is complete."""
        return not self.get_stage_validation_errors().get(self.Stage.LINEAGE, [])

    def _get_distinction_bonus(self, modifier_target_name: str, category_name: str) -> int:
        """Sum distinction effect values targeting a specific ModifierTarget."""
        from world.distinctions.models import DistinctionEffect  # noqa: PLC0415

        distinctions_data = self.draft_data.get("distinctions", [])
        if not distinctions_data:
            return 0

        entries = {
            d["distinction_id"]: d.get("rank", 1)
            for d in distinctions_data
            if d.get("distinction_id")
        }
        if not entries:
            return 0

        effects = DistinctionEffect.objects.filter(
            distinction_id__in=entries.keys(),
            target__name=modifier_target_name,
            target__category__name=category_name,
        ).select_related("target")

        return sum(effect.get_value_at_rank(entries[effect.distinction_id]) for effect in effects)

    @property
    def starting_technique_picks(self) -> int:
        """How many techniques the player may pick at CG magic stage.

        Base of 1, plus any distinction bonus targeting the
        ``starting_technique_picks`` ModifierTarget in the
        ``character_creation`` ModifierCategory (#2426).
        """
        return 1 + self._get_distinction_bonus(
            STARTING_TECHNIQUE_PICKS_TARGET, CG_MODIFIER_CATEGORY
        )

    def calculate_stat_budget(self) -> int:
        """Total stat points = default * stat_count + net bonuses."""
        bonuses = self.get_all_stat_bonuses()
        base = STAT_DEFAULT_VALUE * len(REQUIRED_STATS)
        net_bonus = sum(bonuses.values())
        return base + net_bonus

    def calculate_points_remaining(self) -> int:
        """Budget minus allocated points. 0 = fully allocated."""
        budget = self.calculate_stat_budget()
        stats = self.draft_data.get("stats", {})
        if not stats:
            return budget - (STAT_DEFAULT_VALUE * len(REQUIRED_STATS))
        spent = sum(stats.values())
        return budget - spent

    def calculate_cg_points_breakdown(self) -> list[CGPointBreakdownEntry]:
        """
        Build itemized breakdown of CG point costs from actual data sources.

        Returns:
            List of typed dicts with category, item, and cost keys.
        """
        breakdown: list[CGPointBreakdownEntry] = []
        if self.selected_beginnings and self.selected_beginnings.cg_point_cost:
            breakdown.append(
                {
                    "category": "heritage",
                    "item": self.selected_beginnings.name,
                    "cost": self.selected_beginnings.cg_point_cost,
                }
            )
        for d in self.draft_data.get("distinctions", []):
            cost = d.get("cost", 0)
            if cost:
                breakdown.append(
                    {
                        "category": "distinction",
                        "item": d.get("distinction_name", "Unknown"),
                        "cost": cost,
                    }
                )
        if self.selected_species_id is not None:
            from world.species.services import total_species_gift_cost  # noqa: PLC0415

            species_cost = total_species_gift_cost(self.selected_species)
            if species_cost:
                breakdown.append(
                    {
                        "category": "species",
                        "item": self.selected_species.name,
                        "cost": species_cost,
                    }
                )
        return breakdown

    def calculate_cg_points_spent(self) -> int:
        """
        Calculate total CG points spent from actual data sources.

        Derived from breakdown to guarantee consistency.

        Returns:
            Total CG points spent
        """
        return sum(entry["cost"] for entry in self.calculate_cg_points_breakdown())

    def calculate_cg_points_remaining(self) -> int:
        """
        Calculate remaining CG points.

        Returns:
            Number of CG points remaining (can be negative if over budget)
        """
        starting = CGPointBudget.get_active_budget()
        spent = self.calculate_cg_points_spent()
        return starting - spent

    def get_stat_bonuses_from_heritage(self) -> dict[str, int]:
        """
        Get stat bonuses from selected species.

        Returns:
            Dict mapping stat names to bonus values (e.g., {"strength": 1})
        """
        if not self.selected_species:
            return {}
        return self.selected_species.get_stat_bonuses_dict()

    def get_stat_bonuses_from_distinctions(self) -> dict[str, int]:
        """Get stat bonuses from selected distinctions.

        Looks up DistinctionEffect records for each selected distinction
        and returns bonuses for effects targeting the 'stat' category.

        Returns:
            Dict mapping stat names to display-scale bonus values
            (e.g., {"strength": 1} for +10 internal).
        """
        from world.distinctions.models import DistinctionEffect  # noqa: PLC0415
        from world.mechanics.constants import STAT_CATEGORY_NAME  # noqa: PLC0415

        distinctions_data = self.draft_data.get("distinctions", [])
        if not distinctions_data:
            return {}

        distinction_ids = [d["distinction_id"] for d in distinctions_data]
        ranks_by_id = {d["distinction_id"]: d.get("rank", 1) for d in distinctions_data}

        effects = (
            DistinctionEffect.objects.filter(
                distinction_id__in=distinction_ids,
                target__category__name=STAT_CATEGORY_NAME,
            )
            .select_related("target", "target__category")
            .distinct()
        )

        bonuses: dict[str, int] = {}
        for effect in effects:
            stat_name = effect.target.name
            rank = ranks_by_id.get(effect.distinction_id, 1)
            value = effect.get_value_at_rank(rank)
            display_value = value // STAT_DISPLAY_DIVISOR
            bonuses[stat_name] = bonuses.get(stat_name, 0) + display_value

        return bonuses

    def get_all_stat_bonuses(self) -> dict[str, int]:
        """Get combined stat bonuses from all sources.

        Aggregates bonuses from heritage (species) and distinctions.

        Returns:
            Dict mapping stat names to total display-scale values.
        """
        heritage = self.get_stat_bonuses_from_heritage()
        distinctions = self.get_stat_bonuses_from_distinctions()

        combined: dict[str, int] = {}
        all_stats = set(heritage.keys()) | set(distinctions.keys())
        for stat in all_stats:
            combined[stat] = heritage.get(stat, 0) + distinctions.get(stat, 0)
        return combined

    def calculate_final_stats(self) -> dict[str, int]:
        """Return allocated stats (already in 1-5 scale). No bonuses applied on top."""
        stats = self.draft_data.get("stats", {})
        return {name: stats.get(name, STAT_DEFAULT_VALUE) for name in REQUIRED_STATS}

    def _is_attributes_complete(self) -> bool:
        """Check if the Attributes & Skills stage is complete (stats + skill allocation)."""
        return not self.get_stage_validation_errors().get(self.Stage.ATTRIBUTES, [])

    def _is_path_complete(self) -> bool:
        """Check Stage 5 (Path) completion status."""
        return not self.get_stage_validation_errors().get(self.Stage.PATH, [])

    def validate_path_skills(self) -> None:
        """
        Validate skill point allocation data.

        Skill allocation is now part of the Attributes & Skills stage
        (formerly validated as part of the "Path & Skills" stage, #2426) —
        the method name is kept since ``draft_data["skills"]``/
        ``draft_data["specializations"]`` are unchanged.

        Raises:
            rest_framework.serializers.ValidationError: If validation fails,
                with specific error message describing the issue.

        Checks:
        - Total points spent <= budget
        - Specializations only where parent >= threshold
        - No values exceed CG max
        """
        from world.skills.models import SkillPointBudget, Specialization  # noqa: PLC0415

        budget = SkillPointBudget.get_active_budget()
        skills = self.draft_data.get("skills", {})
        specializations = self.draft_data.get("specializations", {})

        # Calculate total points spent
        skill_points = sum(skills.values())
        spec_points = sum(specializations.values())
        total_spent = skill_points + spec_points

        if total_spent > budget.total_points:
            msg = f"Total skill points ({total_spent}) exceeds budget ({budget.total_points})."
            raise serializers.ValidationError(msg)

        # Validate no skill values exceed CG max
        for value in skills.values():
            if value > budget.max_skill_value:
                msg = f"Skill value ({value}) exceeds maximum allowed ({budget.max_skill_value})."
                raise serializers.ValidationError(msg)

        # Validate no specialization values exceed CG max
        for value in specializations.values():
            if value > budget.max_specialization_value:
                msg = (
                    f"Specialization value ({value}) exceeds maximum allowed "
                    f"({budget.max_specialization_value})."
                )
                raise serializers.ValidationError(msg)

        # Validate specializations have parent at threshold
        for spec_id, spec_value in specializations.items():
            if spec_value > 0:
                try:
                    spec = Specialization.objects.get(pk=int(spec_id))
                    parent_value = skills.get(str(spec.parent_skill_id), 0)
                    if parent_value < budget.specialization_unlock_threshold:
                        msg = (
                            f"Specialization '{spec.name}' requires parent skill "
                            f"at {budget.specialization_unlock_threshold} or higher "
                            f"(current: {parent_value})."
                        )
                        raise serializers.ValidationError(msg)
                except Specialization.DoesNotExist:
                    msg = f"Invalid specialization ID: {spec_id}."
                    raise serializers.ValidationError(msg) from None

    def _is_distinctions_complete(self) -> bool:
        """Check if distinctions stage is complete."""
        return not self.get_stage_validation_errors().get(self.Stage.DISTINCTIONS, [])

    def _is_appearance_complete(self) -> bool:
        """Check if appearance stage is complete."""
        return not self.get_stage_validation_errors().get(self.Stage.APPEARANCE, [])

    def _is_identity_complete(self) -> bool:
        """Check if identity stage is complete."""
        return not self.get_stage_validation_errors().get(self.Stage.IDENTITY, [])

    def can_submit(self) -> bool:
        """Check if all required stages are complete for submission."""
        completion = self.get_stage_completion()
        # All stages except REVIEW must be complete
        required_stages = [s for s in self.Stage if s != self.Stage.REVIEW]
        return all(completion.get(stage, False) for stage in required_stages)


SOFT_DELETE_DAYS = 14


class DraftApplication(SharedMemoryModel):
    """Tracks the review lifecycle of a character draft submission."""

    draft = models.OneToOneField(
        CharacterDraft,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="application",
    )
    player_account = models.ForeignKey(
        AccountDB,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_applications",
        help_text="The player who submitted this application (survives draft deletion).",
    )
    character_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Character name populated at approval time (survives draft deletion).",
    )
    status = models.CharField(
        max_length=30,
        choices=ApplicationStatus.choices,
        default=ApplicationStatus.SUBMITTED,
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewer = models.ForeignKey(
        AccountDB,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="claimed_applications",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    submission_notes = models.TextField(
        blank=True,
        help_text="Player's notes about the character submission.",
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set on deny/withdraw for soft-delete grace period.",
    )
    invited_via = models.ForeignKey(
        "roster.GameInvite",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="applications",
        help_text=(
            "If the applicant arrived via a game invite, the invite that "
            "brought them. Set by annotate_application() during submission."
        ),
    )

    class Meta:
        verbose_name = "Draft Application"
        verbose_name_plural = "Draft Applications"

    def __str__(self) -> str:
        name = self.draft or self.character_name or "Unknown"
        return f"Application for {name} ({self.get_status_display()})"

    @property
    def is_locked(self) -> bool:
        """Draft is locked (read-only for player) when submitted or in review."""
        return self.status in (ApplicationStatus.SUBMITTED, ApplicationStatus.IN_REVIEW)

    @property
    def is_terminal(self) -> bool:
        """Application is in a terminal state (approved, denied, withdrawn)."""
        return self.status in (
            ApplicationStatus.APPROVED,
            ApplicationStatus.DENIED,
            ApplicationStatus.WITHDRAWN,
        )

    @property
    def is_editable(self) -> bool:
        """Draft is editable when revisions are requested."""
        return self.status == ApplicationStatus.REVISIONS_REQUESTED

    @cached_property
    def cached_comments(self) -> list:
        """
        Get comments with prefetch support.

        This cached_property serves as the target for Prefetch(..., to_attr=).
        When prefetched, Django populates this directly. When accessed without
        prefetch, falls back to a fresh query with author select_related.

        To invalidate: del instance.cached_comments
        """
        return list(self.comments.select_related("author"))


class DraftApplicationComment(SharedMemoryModel):
    """A comment or status change event in an application's conversation thread."""

    application = models.ForeignKey(
        DraftApplication,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    author = models.ForeignKey(
        AccountDB,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Null for system-generated status change events.",
    )
    text = models.TextField()
    comment_type = models.CharField(
        max_length=20,
        choices=CommentType.choices,
        default=CommentType.MESSAGE,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Application Comment"
        verbose_name_plural = "Application Comments"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.get_comment_type_display()} on {self.application} at {self.created_at}"


class CGExplanation(NaturalKeyMixin, SharedMemoryModel):
    """Key-value store for admin-editable CG explanatory text.

    Each row is one piece of CG copy (heading, intro, description, etc.).
    The key matches what the frontend expects (e.g. "origin_heading").
    Staff can add new keys directly in the admin without migrations.
    """

    key = models.CharField(max_length=100, unique=True)
    text = models.TextField(blank=True)
    help_text = models.TextField(blank=True, help_text="Reminder of which CG stage uses this key")

    objects = NaturalKeyManager()

    class Meta:
        verbose_name = "CG Explanation"
        verbose_name_plural = "CG Explanations"

    class NaturalKeyConfig:
        fields = ["key"]

    def __str__(self) -> str:
        return self.key
