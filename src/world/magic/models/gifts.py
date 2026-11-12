"""Gifts and Traditions — character magical portfolios and schools.

Gifts are thematic collections of magical techniques.
Traditions represent schools of practice or philosophy.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.functional import cached_property

from core.models import ArxSharedMemoryModel as SharedMemoryModel
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.contributors.models import CreditedContent
from world.items.constants import GearArchetype
from world.locations.constants import STAT_CLAMPS, STAT_DEFAULTS, StatKey
from world.magic.constants import AcquisitionOrigin, GiftKind, SubstanceDirection
from world.magic.models.affinity import Resonance

# Lazy model reference (Django app_label.ModelName), extracted to satisfy S1192.
CHARACTER_SHEET_MODEL = "arxii.CharacterSheet"


class GiftManager(NaturalKeyManager):
    """Manager for Gift with natural key support."""


class Gift(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """
    A thematic collection of magical powers.

    Gifts represent a character's supernatural portfolio - like "Shadow Majesty"
    for dark regal influence. Each Gift contains multiple Powers that unlock
    as the character levels.

    Affinities and Resonances are proper domain models.
    """

    name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Display name for this gift.",
    )
    description = models.TextField(
        blank=True,
        help_text="Player-facing description of this gift.",
    )
    kind = models.CharField(
        max_length=16,
        choices=GiftKind.choices,
        default=GiftKind.MAJOR,
        db_index=True,
        help_text=(
            "Major: the one CG-chosen gift. Minor: shared/acquirable gifts that "
            "species abilities and in-play powers are delivered as (ADR-0050)."
        ),
    )
    # on_delete=PROTECT, deliberately unlike Species.parent, which CASCADEs
    # (#2891, ADR-0192). Facet.parent used to be the second such precedent; #3776
    # flattened Facet and removed it. A child gift is not a taxonomy leaf
    # that is meaningless without its parent — it is a self-standing playable
    # gift that characters hold (CharacterGift) and thread (Thread.target_gift).
    # Cascading from the umbrella would delete gifts carrying live character
    # state; PROTECT forces the author to re-parent the kinds first.
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
        help_text=(
            "Umbrella gift this gift hangs beneath. A character holding this gift "
            "also reaches the parent's techniques, on one thread "
            "(e.g. Vulpi.parent = Khati)."
        ),
    )
    resonances = models.ManyToManyField(
        Resonance,
        blank=True,
        related_name="gifts",
        help_text="Resonances associated with this gift.",
    )
    creator = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_gifts",
        help_text="Character who created this gift.",
    )
    codex_entry = models.ForeignKey(
        "arxii.CodexEntry",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="gifts",
        help_text="Lore entry this gift is bound to, if any.",
    )
    # A Minor Gift (species ability, in-play power) is magic the character never
    # chose, so tying its casting manner to whatever Path they DID choose gives the
    # gift itself no say — a Khati's species magic would be as loud as their Path
    # (#2905). This lets a gift impose its own casting style directly, overriding
    # the caster's Path style when set. Null = defer to the caster's Path, as before
    # (today's behavior, and every Major Gift's expected behavior).
    style = models.ForeignKey(
        "arxii.TechniqueStyle",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="gifts",
        help_text=(
            "Casting style this gift imposes, overriding the caster's Path style "
            "(#2905). Its skill is the one this gift's casts add (#5002). Null = defer "
            "to the caster's Path style and its skill."
        ),
    )
    # The gift points at the item primitive (ADR-0010). The weapon made from it carries
    # ItemInstance.natural_weapon_gift back to this gift, so a plain copy of the same
    # template stays ordinary gear (#4898).
    natural_weapon_template = models.ForeignKey(
        "arxii.ItemTemplate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="natural_weapon_gifts",
        limit_choices_to={"gear_archetype": GearArchetype.UNARMED},
        help_text=(
            "Claws, a bite or horns this gift gives its holder: an Unarmed item template "
            "worn at the skin layer. Made and equipped once when the gift is gained; it "
            "comes off only if the gift is lost. Blank = no natural weapon."
        ),
    )
    ultimate_techniques = models.ManyToManyField(
        "arxii.Technique",
        blank=True,
        related_name="ultimate_for_gifts",
        limit_choices_to={"is_ultimate": True},
        help_text=(
            "#4118: this MINOR gift's ultimates, revealed at Audere to any character holding "
            "it (Path-agnostic). Minor gifts only: a major gift's ultimates hang on its "
            "Path Gift Grants. Empty is fine; a minor gift needs no ultimate."
        ),
    )

    objects = GiftManager()

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        if self.kind == GiftKind.MAJOR and self.pk and self.ultimate_techniques.exists():
            raise ValidationError(
                {
                    "kind": "A major gift's ultimates hang on its Path Gift Grants; clear "
                    "ultimate_techniques first."
                }
            )

    def get_affinity_breakdown(self) -> dict[str, int]:
        """Derive affinity from resonances' affinities."""
        counts: dict[str, int] = {}
        for resonance in self.resonances.select_related("affinity").all():
            aff_name = resonance.affinity.name
            counts[aff_name] = counts.get(aff_name, 0) + 1
        return counts

    @cached_property
    def cached_resonances(self) -> list:
        """Resonances for this gift. Supports Prefetch(to_attr=)."""
        return list(self.resonances.all())

    @cached_property
    def cached_techniques(self) -> list:
        """Techniques for this gift. Supports Prefetch(to_attr=).

        This gift's OWN techniques — deliberately not widened to the lineage,
        because it is the ``Prefetch(to_attr="cached_techniques")`` target for
        the gift API. Use ``inherited_techniques`` for "everything a holder of
        this gift reaches."
        """
        return list(self.techniques.all())

    @property
    def lineage(self) -> list["Gift"]:
        """This gift followed by every ancestor gift, nearest first (#2891).

        Mirrors ``Species.lineage``: the chain is one or two deep in practice (a
        Khati kind under Khati, an elf line under Elf) and every row is served by
        the idmapper cache after the first read, so the walk is cheap enough to
        do inline.

        A ``parent`` cycle would be a data defect rather than a modelled state;
        the seen-set keeps it from hanging whatever produced it.
        """
        chain: list[Gift] = []
        seen: set[int] = set()
        current: Gift | None = self
        while current is not None and current.pk not in seen:
            seen.add(current.pk)
            chain.append(current)
            current = current.parent
        return chain

    @property
    def lineage_ids(self) -> frozenset[int]:
        """pks of ``lineage`` — membership tests without re-walking the chain."""
        return frozenset(gift.pk for gift in self.lineage)

    @property
    def inherited_techniques(self) -> list:
        """Every ordinary technique a holder of this gift reaches (#2891).

        This gift's own techniques first, then each ancestor's, nearest ancestor
        first. De-duplicated by pk so a diamond (should a gift ever be reachable
        twice) yields each technique once. Excludes ``is_ultimate`` techniques
        (#4098 fix round 1): both callers (the organization gift-grant handler's
        ``acquired_techniques_for``, and the GIFT-thread crossing handler's
        variant-discovery parent list) mean "techniques holding this gift grants
        or lets you specialize" — an ultimate is reached only by discovering it
        at Audere/Audere Majora, never by holding a gift.

        This is the pool read; ``cached_techniques`` stays the own-techniques
        accessor the gift API prefetches into.
        """
        techniques: list = []
        seen: set[int] = set()
        for gift in self.lineage:
            for technique in gift.cached_techniques:
                if technique.pk in seen or technique.is_ultimate:
                    continue
                seen.add(technique.pk)
                techniques.append(technique)
        return techniques


class GiftSubstanceManager(NaturalKeyManager):
    """Manager for GiftSubstance with natural key support (keyed on its gift)."""


class GiftSubstance(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """What a gift is made of: the room condition that is its substance (#5018).

    A shadow gift works through shadow, which is the room's lighting, falling. A caster
    of the gift is stronger where the room is rich in it, and her casts call it up where
    it is missing. A child gift with no row of its own uses its parent's. A gift with no
    row is unchanged: no power line, no call-up.

    ``full_at`` is how far the room condition must sit from an ordinary room's value for
    the substance to be at full strength; it is *present* from a share of that distance
    set on ``ResonanceEnvironmentConfig.substance_present_pct``. (Code and the services
    call the room condition a "reading", one point of it a "step" and ``full_at`` the
    "measure"; staff-facing text never does.)
    """

    gift = models.OneToOneField(
        Gift,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="substance",
        help_text="The gift this is the substance of.",
    )
    label = models.CharField(
        verbose_name="Name in lines",
        max_length=60,
        help_text='What the cast card and the roll breakdown call it ("shadow", "water").',
    )
    stat_key = models.CharField(
        verbose_name="Which room condition feeds it",
        max_length=20,
        choices=StatKey.choices,
        help_text=(
            "The room condition this gift draws on. Lighting for shadow: -2 is pitch dark, "
            "+2 is blazing light."
        ),
    )
    direction = models.CharField(
        verbose_name="Stronger when it is",
        max_length=10,
        choices=SubstanceDirection.choices,
        help_text=(
            "Shadow is stronger when lighting is lower (darker). Water, wind and fire are "
            "stronger when wet, wind and heat are higher."
        ),
    )
    full_at = models.PositiveIntegerField(
        verbose_name="Full strength at",
        default=2,
        help_text=(
            "How far from an ordinary room counts as full strength. For lighting, 2 means "
            "pitch dark (an ordinary room is 0). Wet, wind and heat run from 0 to 100000; "
            "pick the value you treat as soaking, a gale or blazing. It cannot be further "
            "than the room condition can go."
        ),
    )
    opposed_by = models.CharField(
        verbose_name="Weakened by",
        max_length=20,
        choices=StatKey.choices,
        blank=True,
        help_text=(
            "Another room condition that works against it, such as Dry for water. Leave "
            "blank if only the opposite of its own condition weakens it (bright light for "
            "shadow)."
        ),
    )
    arrival_line = models.CharField(
        verbose_name="When it arrives, the room sees",
        max_length=200,
        help_text=(
            "The line the room sees whenever it is called up, by a cast or with no "
            'technique ("The shadows in the room deepen."). It never names the caster.'
        ),
    )

    property = models.ForeignKey(
        "arxii.Property",
        verbose_name="Property new techniques start with",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gift_substances",
        help_text=(
            "The property a new technique on this gift starts with ticked, such as "
            "'shadow'. Only a convenience: untick it on any technique where it does not "
            "belong, and nothing reads it in play. Leave blank and new techniques start "
            "with no property ticked."
        ),
    )

    objects = GiftSubstanceManager()

    class NaturalKeyConfig:
        fields = ["gift"]
        dependencies = ["magic.Gift"]

    class Meta:
        verbose_name = "Gift substance"
        verbose_name_plural = "Gift substances"

    def __str__(self) -> str:
        return f"{self.label} ({self.gift})"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if not self.full_at or self.full_at < 1:
            errors["full_at"] = "Full strength must be at least 1."
        if self.opposed_by and self.opposed_by == self.stat_key:
            errors["opposed_by"] = "A room condition cannot weaken itself; leave this blank."
        if self.stat_key and self.direction:
            low, high = STAT_CLAMPS[StatKey(self.stat_key)]
            ordinary = STAT_DEFAULTS[StatKey(self.stat_key)]
            reach = (
                ordinary - low if self.direction == SubstanceDirection.FALLING else high - ordinary
            )
            if self.direction == SubstanceDirection.FALLING and reach <= 0:
                errors["direction"] = (
                    "This room condition cannot go below an ordinary room, so a gift cannot "
                    "be stronger when it is lower. Use Lighting for shadow, or pick Higher."
                )
            elif self.full_at and self.full_at > reach:
                errors["full_at"] = (
                    f"This room condition only goes {reach} from an ordinary room that way, "
                    "so full strength cannot be more than that."
                )
        if errors:
            raise ValidationError(errors)


class CharacterGift(SharedMemoryModel):
    """
    Links a character to a Gift they know.

    Characters start with one Gift at creation and may learn more
    through play, training, or transformation.
    """

    character = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="character_gifts",
        help_text="The character who knows this gift.",
    )
    gift = models.ForeignKey(
        Gift,
        on_delete=models.PROTECT,
        related_name="character_grants",
        help_text="The gift known.",
    )
    acquired_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this gift was acquired.",
    )
    origin = models.CharField(
        max_length=30,
        choices=AcquisitionOrigin.choices,
        default=AcquisitionOrigin.CHARACTER_CREATION,
        help_text="How this gift was acquired (#3055). Default covers pre-existing rows "
        "minted before this field existed, which were overwhelmingly CG gift-stage picks; "
        "every creation site now sets this explicitly.",
    )

    class Meta:
        unique_together = ["character", "gift"]
        verbose_name = "Character Gift"
        verbose_name_plural = "Character Gifts"

    def __str__(self) -> str:
        return f"{self.gift} on {self.character}"


class TraditionManager(NaturalKeyManager):
    """Manager for Tradition with natural key support."""


class Tradition(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """
    A magical tradition representing a school of practice or philosophy.

    Traditions group practitioners who share techniques, beliefs, or methods.
    """

    @cached_property
    def cached_codex_grants(self) -> list:
        """Codex grants — the Prefetch/query shared interface (#2386).

        Authored content: negligible staleness on the identity-mapped row.
        """
        return list(self.codex_grants.all())

    name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Display name for this tradition.",
    )
    description = models.TextField(
        blank=True,
        help_text="Player-facing description of this tradition's philosophy and practices.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this tradition is currently available for selection.",
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display ordering within lists (lower numbers appear first).",
    )

    favored_affinities = models.ManyToManyField(
        "arxii.Affinity",
        blank=True,
        related_name="favoring_traditions",
        help_text=(
            "A student whose Gift resonance belongs to an affinity checked here gets "
            "extra magical training and finds this Tradition's courses easier. None "
            "checked: affinity never helps."
        ),
    )

    objects = TraditionManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Tradition"
        verbose_name_plural = "Traditions"

    def __str__(self) -> str:
        return self.name


class CharacterTradition(SharedMemoryModel):
    """
    Links a character to a tradition they belong to.

    Characters may join traditions during creation or through play. History is
    preserved (#2441 ruling 2): switching or leaving a tradition sets ``left_at``
    on the old row rather than deleting it — the record of having been Unbound,
    or a member of a since-abandoned tradition, persists. A character has at
    most one ACTIVE (``left_at IS NULL``) row at a time, enforced by
    ``unique_active_tradition_per_character`` below — mirrors
    ``OrganizationMembership.left_at`` + its active-row constraint
    (``world.societies.models``). ``unique_together`` on (character, tradition)
    was deliberately dropped: rejoining a tradition after having left it must be
    able to create a second historical row for the same pair, which a
    character+tradition unique key would forbid. ``world.magic.services.
    tradition_membership.join_tradition``/``leave_tradition`` are the only
    writers of this row outside CG finalization (which creates the character's
    first, unconditionally-active row) and Django admin.
    """

    character = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="character_traditions",
        help_text="The character who belongs to this tradition.",
    )
    tradition = models.ForeignKey(
        Tradition,
        on_delete=models.PROTECT,
        related_name="character_traditions",
        help_text="The tradition the character belongs to.",
    )
    acquired_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the character joined this tradition.",
    )
    left_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "When the character left this tradition, voluntarily or via a switch "
            "to another tradition (#2441). Null = this is the character's "
            "currently active tradition."
        ),
    )

    class Meta:
        verbose_name = "Character Tradition"
        verbose_name_plural = "Character Traditions"
        constraints = [
            models.UniqueConstraint(
                fields=["character"],
                condition=models.Q(left_at__isnull=True),
                name="unique_active_tradition_per_character",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.tradition} on {self.character}"
