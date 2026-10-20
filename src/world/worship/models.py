"""Worship foundation models (#2355) and miracles (#2360).

Gods, spirits, totems, and dark powers as authorable entities (``WorshippedBeing``)
that accumulate worship in a vast resonance pool, fed by ceremonies (#2289) and
future worship acts. Beings are deliberately NOT CharacterSheets (see the ADR in
this PR): most gods are never played; the rare manifested god links an
``avatar_sheet``. Consumers (ceremonies, miracles) point INTO this app; it imports
no consumer system (ADR-0010).
"""

from django.core.exceptions import ValidationError
from django.db import models

from core.managers import ArxSharedMemoryManager
from core.models import ArxSharedMemoryModel as SharedMemoryModel
from world.contributors.models import CreditedContent
from world.items.constants import MeaningSignalKind
from world.magic.models.techniques import (
    AbstractAppliedCondition,
    AbstractDamageProfile,
)
from world.scenes.action_constants import DifficultyChoice
from world.worship.constants import (
    ANSWER_FACT_MIN_SUCCESS_LEVEL,
    ANSWER_FOLLOW_UP_MIN_SUCCESS_LEVEL,
    ANSWER_ONLOOKER_LINE_MAX_LENGTH,
    FAVOR_INVOCATION_LINE_MAX_LENGTH,
    BeingRelationshipValence,
    BeingResonanceTier,
    ConsecrationScope,
    DireStraitsKind,
    FavorAwardKind,
    MiracleTrigger,
    PledgeCreditSource,
    RiteTier,
)

# Verbose name reused across Meta verbose_name / verbose_name_plural / __str__ (python:S1192).
CHOSEN_FAVOR_CONFIG_VERBOSE = "Chosen Favor Config"
CHARACTER_SHEET_MODEL = "arxii.CharacterSheet"
ACCOUNT_DB_MODEL = "accounts.AccountDB"


class PatronageValence(models.TextChoices):
    """The nature of a Chosen's bond with their patron (#2550).

    Null on ``DevotionStanding.valence`` means ordinary worship (not a patronage).
    """

    DEVOTIONAL = "devotional", "Devotional"
    ANTAGONISTIC = "antagonistic", "Antagonistic"
    PACT = "pact", "Pact"


class WorshipTradition(SharedMemoryModel):
    """A style of worship (PLACEHOLDER names: Liturgy/Spiritcalling/Druidry/Occultism).

    Bridges a being to the Rites specialization its ceremonies roll with.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(
        blank=True, help_text="PLACEHOLDER lore — Apostate rewrite pending."
    )
    rites_specialization = models.ForeignKey(
        "arxii.Specialization",
        on_delete=models.PROTECT,
        related_name="worship_traditions",
        help_text="The Rites specialization ceremonies of this tradition roll with.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class WorshippedBeing(SharedMemoryModel):
    """A worshippable god/spirit/power with a vast accumulating resonance pool.

    ``resonance_pool`` is spendable by the future miracles system (#2360);
    ``lifetime_worship`` is the monotonic audit twin (mirrors the
    balance/lifetime_earned split on ``CharacterResonance``).
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(
        blank=True, help_text="PLACEHOLDER lore — Apostate rewrite pending."
    )
    domains = models.TextField(
        blank=True,
        help_text=(
            "Plain-text spheres/domains (e.g. 'Carnage, wanton bloodshed, feral "
            "battle, ferocity'). No lookup table — overlap across gods is expected "
            "and fine; confirmed no mechanical matching need exists (#3776)."
        ),
    )
    tradition = models.ForeignKey(WorshipTradition, on_delete=models.PROTECT, related_name="beings")
    resonance_pool = models.BigIntegerField(
        default=0, help_text="Spendable accumulated worship (miracles draw here, #2360)."
    )
    lifetime_worship = models.BigIntegerField(
        default=0, help_text="Monotonic total worship ever received (audit)."
    )
    avatar_sheet = models.OneToOneField(
        CHARACTER_SHEET_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="avatar_of_being",
        help_text="Rare: the NPC sheet a manifested god is played through.",
    )
    is_active = models.BooleanField(default=True)
    gm_notes = models.TextField(
        blank=True,
        default="",
        help_text="Staff-only prose: continuity, who this being was in Arx 1. Never shown "
        "to players (#3780).",
    )
    tarot_cards = models.ManyToManyField(
        "arxii.TarotCard",
        through="arxii.BeingTarotCard",
        through_fields=("being", "card"),
        blank=True,
        related_name="represented_beings",
        help_text=(
            "Cards people believe represent this being, upright or reversed "
            "(BeingTarotCard.is_reversed, #4198). Pure association, no cap."
        ),
    )
    codex_entry = models.ForeignKey(
        "arxii.CodexEntry",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="worshipped_beings",
        help_text=(
            "This being's Codex page. Visibility (Public/Obscure/Secret) is read "
            "entirely through the linked entry's is_public tier — no separate "
            "visibility field on WorshippedBeing itself."
        ),
    )
    ultimate_techniques = models.ManyToManyField(
        "arxii.Technique",
        blank=True,
        related_name="ultimate_for_beings",
        limit_choices_to={"is_ultimate": True},
        help_text=(
            "#4098: ultimates this being makes available to its Chosen (an active "
            "patronage) at Audere. The being makes them available; the Chosen pays."
        ),
    )
    invocation_check_type = models.ForeignKey(
        "arxii.CheckType",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invocation_for_beings",
        help_text=(
            "Optional override of Devotion config's default invocation check type for "
            "this being (#4333). Blank uses the default."
        ),
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class WorshipFeastDay(SharedMemoryModel):
    """A being's feast day (#3776). Mirrors weather.FeastDay's (ic_month, ic_day) shape.

    Worship gets its own model rather than reusing weather's — a religious concept
    shouldn't be owned by the weather app. Recurs annually; no year field. Gives a
    universal worship-rite reward multiplier to anyone worshipping this being on this
    date (wired in issue #3777).
    """

    being = models.ForeignKey(WorshippedBeing, on_delete=models.CASCADE, related_name="feast_days")
    ic_month = models.PositiveSmallIntegerField()
    ic_day = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=100)
    lore = models.TextField(blank=True)

    class Meta:
        ordering = ["being", "ic_month", "ic_day"]
        constraints = [
            models.UniqueConstraint(
                fields=["being", "ic_month", "ic_day"], name="unique_being_feast_day"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.being})"


class BeingTarotCard(SharedMemoryModel):
    """A card people believe represents a being, and which way up (#4198).

    The link row behind ``WorshippedBeing.tarot_cards``: it adopted the auto M2M table
    (``arxii_worshippedbeing_tarot_cards``) in place so the rows entered before the
    orientation existed carry over as uprights. One row per (being, card); reversal is
    a flag on the link, as ``TarotCard.get_surname(is_reversed)`` already treats it,
    not a second card.
    """

    being = models.ForeignKey(
        WorshippedBeing,
        on_delete=models.CASCADE,
        db_column="worshippedbeing_id",
        related_name="card_links",
    )
    card = models.ForeignKey(
        "arxii.TarotCard",
        on_delete=models.CASCADE,
        db_column="tarotcard_id",
        related_name="being_links",
    )
    is_reversed = models.BooleanField(
        default=False,
        db_default=False,
        help_text="The card represents the being reversed.",
    )

    class Meta:
        db_table = "arxii_worshippedbeing_tarot_cards"
        ordering = ["being", "card__name", "is_reversed"]
        constraints = [
            models.UniqueConstraint(fields=["being", "card"], name="unique_being_tarot_card"),
        ]

    def __str__(self) -> str:
        suffix = " reversed" if self.is_reversed else ""
        return f"{self.being}: {self.card.name}{suffix}"


class BeingFacet(SharedMemoryModel):
    """A favored aesthetic facet of a WorshippedBeing (#3776).

    Draws from the same shared Facet pool characters use via Motif — double-dipping is
    fine (a character's own bound facet and their patron's favored facet can be the
    same row). No policing mechanism; bounded in practice by ordinary authoring
    discretion, matching the existing light-touch precedent for Facet application.
    """

    being = models.ForeignKey(
        WorshippedBeing, on_delete=models.CASCADE, related_name="being_facets"
    )
    facet = models.ForeignKey(
        "arxii.Facet", on_delete=models.PROTECT, related_name="favored_by_beings"
    )
    invocation_ease_points = models.PositiveIntegerField(
        default=2,
        db_default=2,
        help_text=(
            "Difficulty points eased on an invocation of this being, per meaning point of a "
            "worn piece carrying this facet. A worn piece with no meaning adds nothing, "
            "whatever it cost (#4520)."
        ),
    )
    earning_bonus_percent = models.PositiveIntegerField(
        default=1,
        db_default=1,
        help_text=(
            "Percent added to the earning rate with this being, per meaning point of a worn "
            "piece carrying this facet (#4520)."
        ),
    )

    class Meta:
        ordering = ["being", "facet__name"]
        constraints = [
            models.UniqueConstraint(fields=["being", "facet"], name="unique_being_facet"),
        ]

    def __str__(self) -> str:
        return f"{self.being}: {self.facet.name}"


class BeingResonance(SharedMemoryModel):
    """A resonance a being favors or is associated with (#3776).

    No cap on how many a being holds. FAVORED acts pay double, ASSOCIATED pays the
    ordinary rate — models "different kinds of worshippers" for the same being.
    """

    being = models.ForeignKey(WorshippedBeing, on_delete=models.CASCADE, related_name="resonances")
    resonance = models.ForeignKey(
        "arxii.Resonance", on_delete=models.PROTECT, related_name="favored_by_beings"
    )
    tier = models.CharField(max_length=20, choices=BeingResonanceTier.choices)

    class Meta:
        ordering = ["being", "-tier", "resonance__name"]
        constraints = [
            models.UniqueConstraint(fields=["being", "resonance"], name="unique_being_resonance"),
        ]

    def __str__(self) -> str:
        return f"{self.being}: {self.resonance.name} ({self.get_tier_display()})"


class BeingNickname(SharedMemoryModel):
    """An alternate name a being's worshippers use (#3776).

    No reverent/irreverent distinction field — a nickname is just a name; its tone is
    prose, not data. Every being should carry at least one row (repeating the canonical
    name if nothing else) so an Organization always has something to point at.
    """

    being = models.ForeignKey(WorshippedBeing, on_delete=models.CASCADE, related_name="nicknames")
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["being", "name"]
        constraints = [
            models.UniqueConstraint(fields=["being", "name"], name="unique_being_nickname"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.being})"


class BeingRelationship(SharedMemoryModel):
    """A public relationship fact between two gods (#3776).

    Two public prose fields, one per side (#4198: ``story_from_a`` is being_a's own
    telling, ``story_from_b`` being_b's; each god's page edits and shows its own), and
    no hidden-truth field on this model at all. A real hidden truth (why two beings
    actually feud) lives entirely as a separately-authored, separately-gated
    CodexEntry reached through a Clue; putting it here instead would leak
    presence/absence of a mystery even with the text hidden.

    ALLY/RIVAL/FEUD/UNKNOWN all read as undirected facts — being_a/being_b carry no
    meaning of their own beyond which side happened to be passed first. Without
    normalization, a caller creating (Fleshreaper, Leviathan) and a second caller
    creating (Leviathan, Fleshreaper) would each satisfy ``unique_being_relationship_pair``
    (different ordered pairs) and produce two rows for the same fact (#3776 Task 8
    investigation). ``save()``/``clean()`` sort the pair into pk-ascending order
    (mirroring ``scenes.PersonaDiscovery`` and ``positioning.PositionEdge``) so every
    caller — including a future creation service/admin — gets this for free; the
    ``being_relationship_canonical_order`` constraint enforces it at the DB level too,
    for writes that bypass ``save()`` (raw SQL, ``bulk_create``).
    """

    being_a = models.ForeignKey(
        WorshippedBeing, on_delete=models.CASCADE, related_name="relationships_as_a"
    )
    being_b = models.ForeignKey(
        WorshippedBeing, on_delete=models.CASCADE, related_name="relationships_as_b"
    )
    valence = models.CharField(max_length=20, choices=BeingRelationshipValence.choices)
    story_from_a = models.TextField(blank=True, help_text="being_a's own telling of it.")
    story_from_b = models.TextField(blank=True, help_text="being_b's own telling of it.")

    class Meta:
        ordering = ["being_a", "being_b"]
        constraints = [
            models.CheckConstraint(
                check=~models.Q(being_a=models.F("being_b")),
                name="being_relationship_not_self",
            ),
            models.CheckConstraint(
                check=models.Q(being_a__lt=models.F("being_b")),
                name="being_relationship_canonical_order",
            ),
            models.UniqueConstraint(
                fields=["being_a", "being_b"], name="unique_being_relationship_pair"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.being_a} {self.get_valence_display()} {self.being_b}"

    def clean(self) -> None:
        super().clean()
        self._normalize_order()

    def save(self, *args: object, **kwargs: object) -> None:
        self._normalize_order()
        super().save(*args, **kwargs)

    def _normalize_order(self) -> None:
        """Swap being_a/being_b into canonical (pk-ascending) order, in place.

        The stories swap with their sides, so a caller who built the row the other
        way round still has each god telling its own.
        """
        if (
            self.being_a_id is not None
            and self.being_b_id is not None
            and self.being_a_id > self.being_b_id
        ):
            self.being_a, self.being_b = self.being_b, self.being_a
            self.story_from_a, self.story_from_b = self.story_from_b, self.story_from_a

    def story_from(self, being_id: int) -> str:
        """This god's own telling of the relationship."""
        return self.story_from_a if being_id == self.being_a_id else self.story_from_b

    def set_story_from(self, being_id: int, story: str) -> None:
        if being_id == self.being_a_id:
            self.story_from_a = story
        else:
            self.story_from_b = story


class WorshipGrant(SharedMemoryModel):
    """Audit ledger row for worship received by a being (mirrors ResonanceGrant)."""

    being = models.ForeignKey(WorshippedBeing, on_delete=models.PROTECT, related_name="grants")
    amount = models.PositiveIntegerField()
    granted_by = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="worship_grants",
    )
    reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.amount} to {self.being} ({self.reason or 'unspecified'})"


class DevotionStanding(SharedMemoryModel):
    """One-way PC→god relationship: accumulated favor from worship acts.

    Deliberately NOT a ``CharacterRelationship`` (hard-typed sheet↔sheet); a god
    only enters that machinery via an ``avatar_sheet``. Miracles (#2360) read
    favor; the God's Favorite achievement tracks the per-being top (Decision 6).
    """

    character_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="devotion_standings",
    )
    being = models.ForeignKey(
        WorshippedBeing, on_delete=models.CASCADE, related_name="devotion_standings"
    )
    favor = models.IntegerField(default=0)
    lifetime_favor = models.IntegerField(default=0)
    valence = models.CharField(
        max_length=20,
        choices=PatronageValence.choices,
        null=True,
        blank=True,
        help_text=(
            "Set when this being chose the character as their champion. Null = ordinary worship."
        ),
    )
    established_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the patronage was established. Null for ordinary worship.",
    )
    released_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when the patron released the Chosen. Null = active patronage.",
    )

    class Meta:
        ordering = ["-favor"]
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet", "being"], name="unique_devotion_standing"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.character_sheet} → {self.being}: {self.favor}"


class WorshipDeclaration(SharedMemoryModel):
    """A character's declared worship: public front + optional secret truth.

    Set at CG (#2355); the secret side mints a ``Secret`` (same pattern as
    secret-by-default distinctions). ``secret_being`` is never serialized to
    non-owners — the sheet API exposes the public name only.
    """

    character_sheet = models.OneToOneField(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="worship_declaration",
    )
    public_being = models.ForeignKey(
        WorshippedBeing,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="public_worshippers",
    )
    public_is_sincere = models.BooleanField(
        default=True,
        help_text=(
            "Heart vs lip service (#2361 Ratified amendment #2): whether the character "
            "genuinely believes the public declaration (True) or it is performative only "
            "(False). Set explicitly at conversion; defaults True for CG declarations, "
            "where public and inward faith are the same thing by construction. PRIVATE — "
            "never leaves owner/staff surfaces, same leak-table pattern as current_mood "
            "in world.character_sheets.serializers._build_identity."
        ),
    )
    secret_being = models.ForeignKey(
        WorshippedBeing,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="secret_worshippers",
    )
    secret = models.ForeignKey(
        "arxii.Secret",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="The minted worship Secret when secret_being is set.",
    )

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        public = self.public_being.name if self.public_being else "none"
        return f"{self.character_sheet}: {public}"


class DivineInterventionConfig(SharedMemoryModel):
    """Singleton config for divine intervention tuning (#2360).

    Staff-tunable knobs: favor threshold for trigger installation,
    per-character cooldown, minimum pool for any miracle.
    """

    objects = ArxSharedMemoryManager()

    favor_threshold = models.PositiveIntegerField(
        default=50,
        help_text="Minimum DevotionStanding.favor to install the intervention trigger.",
    )
    cooldown_hours = models.PositiveIntegerField(
        default=24,
        help_text="Per-character cooldown between interventions (hours).",
    )
    min_pool_for_intervention = models.PositiveIntegerField(
        default=100,
        help_text="Minimum resonance_pool a being must have to perform any miracle.",
    )

    class Meta:
        verbose_name = "Divine Intervention Config"
        verbose_name_plural = "Divine Intervention Config"

    def __str__(self) -> str:
        return f"DivineInterventionConfig(favor>={self.favor_threshold}, cd={self.cooldown_hours}h)"


class Miracle(SharedMemoryModel):
    """An authored miracle a WorshippedBeing can perform (#2360).

    Miracles spend from the being's ``resonance_pool``. Effects are authored
    as payload rows (conditions, capabilities, damage profiles) reusing the
    Abstract* bases from ``world.magic.models.techniques``.
    """

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    being = models.ForeignKey(
        WorshippedBeing,
        on_delete=models.PROTECT,
        related_name="miracles",
    )
    resonance_pool_cost = models.PositiveIntegerField(
        help_text="Amount deducted from being.resonance_pool when performed.",
    )
    intervention_trigger = models.CharField(
        max_length=20,
        choices=MiracleTrigger.choices,
        help_text="Danger context this miracle responds to.",
    )
    favor_threshold = models.PositiveIntegerField(
        default=50,
        help_text="Minimum DevotionStanding.favor required for this miracle to fire.",
    )
    narrative_text = models.TextField(
        help_text="Narrative broadcast (EMIT) when this miracle fires.",
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["being", "sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["being", "name"],
                name="unique_miracle_per_being_name",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.being})"


class MiracleAppliedCondition(AbstractAppliedCondition):
    """Applied condition payload row for a Miracle (#2360).

    The MVP mechanical effect surface for divine intervention.
    """

    miracle = models.ForeignKey(
        Miracle,
        on_delete=models.CASCADE,
        related_name="condition_applications",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["miracle", "condition", "target_kind"],
                name="miracle_applied_condition_unique",
            ),
        ]


class MiracleDamageProfile(AbstractDamageProfile):
    """Damage profile payload row for a Miracle (#2360)."""

    miracle = models.ForeignKey(
        Miracle,
        on_delete=models.CASCADE,
        related_name="damage_profiles",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["miracle", "damage_type"],
                condition=models.Q(damage_type__isnull=False),
                name="miracle_damage_profile_per_type",
            ),
            models.UniqueConstraint(
                fields=["miracle"],
                condition=models.Q(damage_type__isnull=True),
                name="miracle_untyped_damage_profile",
            ),
        ]


class MiraclePerformance(SharedMemoryModel):
    """Immutable audit row for each miracle firing (#2360)."""

    miracle = models.ForeignKey(Miracle, on_delete=models.PROTECT, related_name="performances")
    being = models.ForeignKey(
        WorshippedBeing, on_delete=models.PROTECT, related_name="miracle_performances"
    )
    target_character = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="miracle_performances",
    )
    scene = models.ForeignKey(
        "arxii.Scene",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="miracle_performances",
    )
    resonance_spent = models.PositiveIntegerField()
    trigger_event = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Miracle Performance"
        verbose_name_plural = "Miracle Performances"

    def __str__(self) -> str:
        return f"{self.miracle} → {self.target_character} ({self.trigger_event})"


class ChosenFavorConfig(SharedMemoryModel):
    """Staff-tunable favor thresholds for Chosen benefits (#2550).

    Singleton (pk=1), lazy-created via ``get_chosen_favor_config()``.
    Only ``anima_recovery_*`` fields are wired; ``ceremony_edge_*`` fields are
    defined for shape stability but inert until a future issue wires them.
    """

    anima_recovery_threshold = models.PositiveIntegerField(
        default=10,
        help_text="Minimum favor for the Chosen's anima ritual bonus.",
    )
    anima_recovery_bonus = models.PositiveIntegerField(
        default=5,
        help_text="Extra anima recovered when favor meets the threshold.",
    )
    ceremony_edge_threshold = models.PositiveIntegerField(
        default=25,
        help_text="DEFERRED — minimum favor for ceremony check bonus. Inert until wired.",
    )
    ceremony_edge_bonus = models.PositiveSmallIntegerField(
        default=1,
        help_text="DEFERRED — bonus weight added to the Devotion aspect. Inert until wired.",
    )
    earn_bonus_percent = models.PositiveIntegerField(
        default=100,
        help_text=(
            "Added to the 100% base rate for a character whose active patronage is this "
            "being. Adds with favor earning modifiers."
        ),
    )
    invocation_ease_points = models.PositiveIntegerField(
        default=30,
        help_text=(
            "Points eased when invoking the character's own patron (30 is two bands). "
            "Adds with favor eases and favor invocation modifiers."
        ),
    )

    class Meta:
        verbose_name = CHOSEN_FAVOR_CONFIG_VERBOSE
        verbose_name_plural = CHOSEN_FAVOR_CONFIG_VERBOSE

    def __str__(self) -> str:
        return CHOSEN_FAVOR_CONFIG_VERBOSE


class DevotionConfig(SharedMemoryModel):
    """Singleton of the favor terms that apply to every character (#4333).

    Lazy-created via ``get_devotion_config()``. Slice 1 holds the invocation
    check terms; the Chosen terms stay on ``ChosenFavorConfig``. Every number
    is example tuning.
    """

    objects = ArxSharedMemoryManager()

    invocation_check_type = models.ForeignKey(
        "arxii.CheckType",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text=(
            "Used when a being has no override of its own. Rolled with the being's "
            "tradition specialization, as worship rites are. Invoking is refused until "
            "this is set."
        ),
    )
    base_difficulty = models.CharField(
        max_length=20,
        choices=DifficultyChoice.choices,
        default=DifficultyChoice.DAUNTING,
        help_text="The invocation check's difficulty before any ease.",
    )
    favor_ease_low_threshold = models.PositiveIntegerField(
        default=30, help_text="Favor at which the first favor ease applies."
    )
    favor_ease_low_points = models.PositiveIntegerField(
        default=15, help_text="Points eased at the first favor threshold (15 is one band)."
    )
    favor_ease_high_threshold = models.PositiveIntegerField(
        default=60, help_text="Favor at which the second favor ease applies instead."
    )
    favor_ease_high_points = models.PositiveIntegerField(
        default=30, help_text="Points eased at the second favor threshold."
    )
    invocations_per_week = models.PositiveIntegerField(
        default=3,
        help_text=(
            "Per being, per character, per game week. A failed invocation counts. "
            "Favor is not spent."
        ),
    )
    favored_deed_percent = models.PositiveIntegerField(
        default=100,
        help_text=(
            "Base deed favor, as a percent of the resonance granted, for a resonance the "
            "being holds as Favored."
        ),
    )
    associated_deed_percent = models.PositiveIntegerField(
        default=50,
        help_text=(
            "Base deed favor, as a percent of the resonance granted, for a resonance the "
            "being holds as Associated."
        ),
    )
    weekly_deed_favor_cap = models.PositiveIntegerField(
        default=8,
        help_text="Base favor from deeds per game week, counted before the earning rate.",
    )
    steward_answer_days = models.PositiveIntegerField(
        default=3,
        help_text=(
            "Days a stewarded being's table GM has to answer a closed pledge. After "
            "this, or when the GM dismisses the prompt, an authored answer is drawn."
        ),
    )
    sacrifice_min_carried_days = models.PositiveIntegerField(
        default=14,
        db_default=14,
        help_text=(
            "Days an item must be held before its personal meaning signals count "
            "(carried, gift, heirloom, own work, made by a tie). Stops making an item and "
            "giving it up the same day."
        ),
    )
    sacrifice_carried_days_per_point = models.PositiveIntegerField(
        default=90,
        db_default=90,
        help_text=(
            "One more carried point per this many days held beyond the minimum. Carried "
            "counts only when the item has another signal: holding alone is never meaning."
        ),
    )
    sacrifice_carried_max_points = models.PositiveIntegerField(
        default=3, db_default=3, help_text="Most meaning points that carrying an item can give."
    )
    maker_tie_max_points = models.PositiveIntegerField(
        default=3,
        db_default=3,
        help_text=(
            "Made by a tie: the pair tier between the holder and the item's maker, up to "
            "this many points. The best maker counts, never the sum."
        ),
    )
    made_for_max_points = models.PositiveIntegerField(
        default=4,
        db_default=4,
        help_text=(
            "Made for: 1 plus the holder's claimed tier toward whoever dedicated the piece, "
            "up to this many points. Nothing when the holder bought it from the dedicator."
        ),
    )
    made_from_max_points = models.PositiveIntegerField(
        default=3,
        db_default=3,
        help_text=(
            "Made from: the meaning the worked-in item had to the crafter when it was used "
            "up, up to this many points."
        ),
    )
    shown_window_weeks = models.PositiveIntegerField(
        default=4,
        db_default=4,
        help_text="Shown: only settled, successful showings in this many game weeks count.",
    )
    shown_engagements_per_point = models.PositiveIntegerField(
        default=2,
        db_default=2,
        help_text="Shown: other players' engagements it takes to earn one point, per showing.",
    )
    shown_max_points = models.PositiveIntegerField(
        default=3, db_default=3, help_text="Shown: most points all showings of an item give."
    )
    sacrifice_ease_per_point = models.PositiveIntegerField(
        default=10,
        db_default=10,
        help_text=(
            "Points the sacrifice check's difficulty is eased by, per meaning point of the "
            "item, never below Trivial. Nothing here reads an item's price."
        ),
    )
    odds_reference_roller_points = models.PositiveIntegerField(
        default=48,
        db_default=48,
        help_text=(
            "Check points of the reference roller the odds read-outs use (Devotion config "
            "and the GM's sacrifice detail). 48 is a Competent roller. A read-out only: "
            "no roll uses it."
        ),
    )
    sacrifices_per_week = models.PositiveIntegerField(
        default=3,
        db_default=3,
        help_text=(
            "Items with meaning points that count per being, per character, per game "
            "week, at shrines and in ceremonies together. Items past the limit are given "
            "up for nothing."
        ),
    )
    worn_item_max_points = models.PositiveIntegerField(
        default=8,
        db_default=8,
        help_text="Most meaning points one worn piece brings to an invocation (#4520).",
    )
    worn_items_counted = models.PositiveIntegerField(
        default=3,
        db_default=3,
        help_text=(
            "Worn pieces carrying a facet the being favors that count per invocation, "
            "highest meaning first (#4520)."
        ),
    )
    resonance_fed_per_point = models.PositiveIntegerField(
        default=10,
        db_default=10,
        help_text=(
            "Resonance an item's facets fed its holder, in a resonance the being lists, per "
            "meaning point; doubled for a favored resonance. Counts only alongside another "
            "signal, so a bought piece worn for months still adds nothing (#4520)."
        ),
    )
    resonance_fed_max_points = models.PositiveIntegerField(
        default=3,
        db_default=3,
        help_text="Most meaning points the resonance fed signal gives one item (#4520).",
    )
    invocation_meaning_ease_max = models.PositiveIntegerField(
        default=40,
        db_default=40,
        help_text=(
            "Cap on the ease all meaning together gives one invocation (worn pieces now; "
            "keepsakes and a Relic later) (#4520)."
        ),
    )

    class Meta:
        verbose_name = "Devotion config"
        verbose_name_plural = "Devotion config"

    def __str__(self) -> str:
        return "Devotion config"

    def clean(self) -> None:
        super().clean()
        if self.favor_ease_high_threshold <= self.favor_ease_low_threshold:
            msg = "The second favor threshold must be above the first."
            raise ValidationError({"favor_ease_high_threshold": msg})


class FavorOutcomeAward(SharedMemoryModel):
    """One scalar per (kind, outcome tier) of favor terms (#4333).

    Not a subclass of ``checks.OutcomeTierAward``: that base's one-to-one on the
    outcome allows one row per outcome, and this table holds two kinds per
    outcome. A missing INVOCATION row reads as no bonus.
    """

    config = models.ForeignKey(
        DevotionConfig, on_delete=models.CASCADE, related_name="outcome_awards"
    )
    kind = models.CharField(max_length=20, choices=FavorAwardKind.choices)
    outcome_tier = models.ForeignKey(
        "arxii.CheckOutcome", on_delete=models.PROTECT, related_name="favor_outcome_awards"
    )
    amount = models.PositiveIntegerField(
        help_text=(
            "Invocation: check points added to the check the invocation was declared on. "
            "Closing: base favor paid when a closing rite resolves a pledge. "
            "Sacrifice: base favor paid when a sacrifice's check lands on this tier."
        )
    )

    class Meta:
        ordering = ["kind", "-outcome_tier__success_level"]
        constraints = [
            models.UniqueConstraint(
                fields=["config", "kind", "outcome_tier"], name="unique_favor_outcome_award"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} / {self.outcome_tier}: {self.amount}"


class FavorInvocation(SharedMemoryModel):
    """One invocation of a being's favor before a check (#4333): the weekly
    counter and the log.

    Written when the invocation check rolls. Favor is never spent; the row's
    existence is what uses one of the week's invocations, whatever the outcome.
    ``player_line`` is the one line of player text an invocation stores.
    """

    character_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL, on_delete=models.CASCADE, related_name="favor_invocations"
    )
    being = models.ForeignKey(
        WorshippedBeing, on_delete=models.CASCADE, related_name="favor_invocations"
    )
    game_week = models.ForeignKey(
        "arxii.GameWeek", on_delete=models.PROTECT, related_name="favor_invocations"
    )
    outcome_tier = models.ForeignKey(
        "arxii.CheckOutcome", on_delete=models.PROTECT, related_name="favor_invocations"
    )
    bonus = models.PositiveIntegerField(
        default=0, help_text="Check points added to the check the invocation was declared on."
    )
    player_line = models.CharField(
        max_length=FAVOR_INVOCATION_LINE_MAX_LENGTH,
        blank=True,
        default="",
        help_text="The player's optional one-line description of how it shows.",
    )
    scene = models.ForeignKey(
        "arxii.Scene",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="favor_invocations",
    )
    mission_instance = models.ForeignKey(
        "arxii.MissionInstance",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="favor_invocations",
    )
    scene_action_request = models.OneToOneField(
        "arxii.SceneActionRequest",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="favor_invocation",
        help_text="The scene action whose check this invocation was declared on.",
    )
    worn_ease = models.PositiveIntegerField(
        default=0,
        db_default=0,
        help_text=(
            "Difficulty points the worn pieces eased this invocation by, after the cap "
            "(#4520). The pieces behind it are the rows under this one."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["character_sheet", "being", "game_week"],
                name="favor_invocation_sheet_week",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.character_sheet} invoked {self.being} ({self.outcome_tier})"


class InvocationPiece(SharedMemoryModel):
    """A worn piece that counted on one invocation, as it was when the check rolled
    (#4520, #4462 section 6.4).

    A snapshot, like ``OfferingSignal``: the piece can be given up, unworn or edited
    afterwards, and the GM's invocation detail still reads what it meant that day. The
    points were computed by ``world.items.services.meaning.item_meaning``, which reads
    records and never a price.
    """

    invocation = models.ForeignKey(FavorInvocation, on_delete=models.CASCADE, related_name="pieces")
    item_name = models.CharField(max_length=200)
    facet_name = models.CharField(
        max_length=100, help_text="The favored facet that made the piece count."
    )
    points = models.PositiveSmallIntegerField(
        help_text="Meaning points counted, after the worn-piece cap."
    )
    ease_per_point = models.PositiveIntegerField(
        help_text="The facet's invocation ease per meaning point."
    )

    class Meta:
        ordering = ["-points", "id"]

    def __str__(self) -> str:
        return f"{self.item_name}: {self.points} x {self.ease_per_point}"

    @property
    def ease(self) -> int:
        return self.points * self.ease_per_point


class InvocationPieceSignal(SharedMemoryModel):
    """One meaning signal of a worn piece on one invocation (#4520)."""

    piece = models.ForeignKey(InvocationPiece, on_delete=models.CASCADE, related_name="signals")
    kind = models.CharField(max_length=20, choices=MeaningSignalKind.choices)
    points = models.PositiveSmallIntegerField()
    detail = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.points}"


class RiteKind(SharedMemoryModel):
    """A generic kind of worship rite shared by the whole pantheon (#3777).

    Vigil, Sermon, Canticle and Blessing might all be Devotional (tier 1) kinds;
    a demanding service sits at tier 2 and a dangerous one at tier 3. Many
    differently named kinds share one tier, and the tier is the only mechanical
    fact a kind carries: a being's own ``WorshipRite`` rows supply the flavor.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, default="")
    tier = models.PositiveSmallIntegerField(
        choices=RiteTier.choices,
        default=RiteTier.DEVOTIONAL,
        help_text="Sets the AP cost (1 per tier) and the award table row; tier 3 is a Ceremony.",
    )

    class Meta:
        ordering = ["tier", "name"]

    def __str__(self) -> str:
        return f"{self.name} (tier {self.tier})"


class WorshipRite(SharedMemoryModel):
    """One being's own instantiation of a RiteKind (#3777).

    The kind supplies the tier and nothing else; this row carries the being's
    flavor (Fleshreaper's Vigil is "The Long Bleeding Watch"), the check it
    rolls and which of the being's resonances it channels. No difficulty, cost
    or reward field lives here: all of that is read from the kind's tier.
    """

    being = models.ForeignKey(WorshippedBeing, on_delete=models.CASCADE, related_name="rites")
    kind = models.ForeignKey(RiteKind, on_delete=models.PROTECT, related_name="rites")
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    check_type = models.ForeignKey(
        "arxii.CheckType", on_delete=models.PROTECT, related_name="worship_rites"
    )
    resonance = models.ForeignKey(
        BeingResonance,
        on_delete=models.PROTECT,
        related_name="rites",
        help_text="Which of this being's own resonances the rite channels (must belong to being).",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["being", "kind__tier", "name"]
        constraints = [
            models.UniqueConstraint(fields=["being", "name"], name="unique_being_rite_name"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.being})"

    @property
    def tier(self) -> int:
        return self.kind.tier

    def clean(self) -> None:
        super().clean()
        if (
            self.resonance_id is not None
            and self.being_id is not None
            and self.resonance.being_id != self.being_id
        ):
            msg = "A rite channels one of its own being's resonances."
            raise ValidationError({"resonance": msg})


class WorshipRiteTierAward(SharedMemoryModel):
    """The payout of a worship rite, per (tier, outcome) (#3777).

    The same shape as ``AnimaRitualBudgetAward`` (one authored row per canonical
    CheckOutcome tier), keyed additionally by rite tier, so three tiers are tuned
    once and every god's every rite reads the same table. Not a subclass of
    ``OutcomeTierAward``: that base's OneToOne on the outcome allows one row per
    outcome, and this table needs one per (tier, outcome). Every (tier, outcome)
    pair must be seeded; a missing row raises rather than paying 0.
    """

    tier = models.PositiveSmallIntegerField(choices=RiteTier.choices)
    outcome_tier = models.ForeignKey(
        "arxii.CheckOutcome", on_delete=models.PROTECT, related_name="worship_rite_awards"
    )
    resonance_amount = models.PositiveIntegerField(
        help_text="Resonance granted to the performer for this tier and outcome."
    )
    favor_amount = models.PositiveIntegerField(
        help_text=(
            "Devotion favor granted (at most once per rite per week) for this tier and outcome."
        )
    )

    class Meta:
        ordering = ["tier", "outcome_tier__success_level"]
        constraints = [
            models.UniqueConstraint(
                fields=["tier", "outcome_tier"], name="unique_worship_rite_tier_award"
            ),
        ]

    def __str__(self) -> str:
        return (
            f"tier {self.tier} / {self.outcome_tier}: {self.resonance_amount}r {self.favor_amount}f"
        )


class WorshipRitePerformance(SharedMemoryModel):
    """One performance of a rite by one character (#3777): the audit row, the
    ledger source of the resonance it granted, and the weekly devotion cap.

    Devotion is rate-limited per rite: a character gains favor from a given rite
    at most once per game week (``favor_granted > 0`` on a row in that week);
    resonance is never capped, so repeating a rite stays fine for RP.
    """

    character_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL, on_delete=models.CASCADE, related_name="rite_performances"
    )
    rite = models.ForeignKey(WorshipRite, on_delete=models.PROTECT, related_name="performances")
    game_week = models.ForeignKey(
        "arxii.GameWeek", on_delete=models.PROTECT, related_name="rite_performances"
    )
    scene = models.ForeignKey(
        "arxii.Scene",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rite_performances",
    )
    ceremony = models.OneToOneField(
        "arxii.Ceremony",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rite_performance",
        help_text="Set for a tier 3 rite: the Ceremony whose finish resolved it.",
    )
    outcome_tier = models.ForeignKey(
        "arxii.CheckOutcome", on_delete=models.PROTECT, related_name="rite_performances"
    )
    resonance_granted = models.PositiveIntegerField(default=0)
    favor_granted = models.PositiveIntegerField(default=0)
    performed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-performed_at"]
        indexes = [
            models.Index(
                fields=["character_sheet", "rite", "game_week"], name="rite_perf_sheet_rite_week"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.character_sheet} performed {self.rite} ({self.outcome_tier})"


class Relic(SharedMemoryModel):
    """A specific sacred item of a being (#3777): one named ItemInstance, not an
    archetype ("this particular scythe", never "any scythe"). Distinct from the
    offering facet bonus, which applies to any item carrying a favored facet.
    Surfaced on the being's tracking dashboard (#3780)."""

    being = models.ForeignKey(WorshippedBeing, on_delete=models.CASCADE, related_name="relics")
    item_instance = models.OneToOneField(
        "arxii.ItemInstance", on_delete=models.CASCADE, related_name="relic_of"
    )
    lore = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["being", "created_at"]

    def __str__(self) -> str:
        return f"{self.item_instance} (relic of {self.being})"


class ShrineDetails(SharedMemoryModel):
    """The room-level holy site (#3778): a SHRINE ``RoomFeatureInstance``'s sidecar.

    Reuses Sanctum's machinery wholesale (one feature per room, soft-delete via
    ``dissolved_at``, ``active()`` queryset); this row adds the being and a plain
    ``consecration_points`` counter that grows when that being's rites are
    performed in the room. Deliberately not the ``LocationValueModifier``
    resonance cascade, which is #3771's question.
    """

    feature_instance = models.OneToOneField(
        "arxii.RoomFeatureInstance", on_delete=models.CASCADE, related_name="shrine_details"
    )
    being = models.ForeignKey(WorshippedBeing, on_delete=models.PROTECT, related_name="shrines")
    founder_character_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="founded_shrines",
    )
    consecration_points = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["being", "-consecration_points"]

    def __str__(self) -> str:
        return f"Shrine of {self.being} @ room {self.feature_instance.room_profile_id}"


class TempleDedication(SharedMemoryModel):
    """The building-level holy site (#3778): a whole ``Building`` dedicated to a being.

    Not a room feature (those are room-scoped): every room whose area is the
    Building's node counts as sanctified with no per-room duplication, and one
    shared ``consecration_points`` total grows from any rite of the being
    performed anywhere inside. Soft-deleted by ``dissolved_at``; one active
    dedication per building.
    """

    building = models.ForeignKey(
        "arxii.Building", on_delete=models.CASCADE, related_name="temple_dedications"
    )
    being = models.ForeignKey(WorshippedBeing, on_delete=models.PROTECT, related_name="temples")
    founder_character_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="founded_temples",
    )
    consecration_points = models.PositiveIntegerField(default=0)
    dedicated_at = models.DateTimeField(auto_now_add=True)
    dissolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["being", "-consecration_points"]
        constraints = [
            models.UniqueConstraint(
                fields=["building"],
                condition=models.Q(dissolved_at__isnull=True),
                name="unique_active_temple_per_building",
            ),
        ]

    def __str__(self) -> str:
        return f"Temple of {self.being} @ building {self.building_id}"


class ConsecrationTier(SharedMemoryModel):
    """An authored consecration tier (#3778): from ``min_points`` up, a holy site
    of this scope adds ``bonus_percent`` to a rite award of its own being.
    Shrine and Temple have separate, differently sized tables; their bonuses
    stack by addition, never max()."""

    scope = models.CharField(max_length=10, choices=ConsecrationScope.choices)
    name = models.CharField(max_length=60)
    min_points = models.PositiveIntegerField()
    bonus_percent = models.PositiveIntegerField(
        help_text="Percent added to a rite award of the site's own being at this tier."
    )

    class Meta:
        ordering = ["scope", "min_points"]
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "min_points"], name="unique_consecration_tier"
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.get_scope_display()} {self.name} ({self.min_points}+: +{self.bonus_percent}%)"
        )


class Prayer(SharedMemoryModel):
    """A character's freeform words to a being (#3779).

    A plain log with no mechanical effect of its own: one of the few freeform
    channels a player has straight to staff. A prayer becomes mechanically
    meaningful only through the qualifying conditions ``pray`` records on it,
    each independent and stackable: ``devotion_granted`` for the first prayer
    of the game week made at a shrine or temple of the being, ``dire_straits``
    plus ``intervention`` when the character prayed in Soulfray or near death
    and a miracle answered.
    """

    character_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL, on_delete=models.CASCADE, related_name="prayers"
    )
    being = models.ForeignKey(WorshippedBeing, on_delete=models.PROTECT, related_name="prayers")
    text = models.TextField()
    room_profile = models.ForeignKey(
        "arxii.RoomProfile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="prayers",
        help_text="Where the prayer was made; a shrine or temple here is what pays devotion.",
    )
    game_week = models.ForeignKey(
        "arxii.GameWeek", on_delete=models.PROTECT, related_name="prayers"
    )
    devotion_granted = models.PositiveIntegerField(
        default=0, help_text="Favor paid by the weekly holy-site prayer; 0 for every other."
    )
    dire_straits = models.CharField(
        max_length=12, choices=DireStraitsKind.choices, blank=True, default=""
    )
    intervention = models.OneToOneField(
        MiraclePerformance,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="answered_prayer",
        help_text="The miracle that answered a dire-straits prayer, when one did.",
    )
    prayed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-prayed_at"]
        verbose_name = "Prayer"
        verbose_name_plural = "Prayers"

    def __str__(self) -> str:
        return f"{self.character_sheet} to {self.being} ({self.prayed_at:%Y-%m-%d})"


class Vision(SharedMemoryModel):
    """A GM-sent vision (#3779): prose a being sends one character.

    First-class and standalone: the prose is the point, meaningful because it
    happened. ``reveal_source`` decides whether the recipient is told which
    being sent it (the twisted-rite leak shape: a true being the record keeps,
    a face the recipient sees). Delivery rides the narrative message system
    (``message``, category VISIONS), so an offline recipient receives it at
    login and it lists beside the sheet's other messages. Two attachments,
    each optional: a Codex ``clue`` when the vision doubles as the starter of a
    real mystery, an ``episode`` when it is a personal beat of a story the
    recipient is in. Rarity is not enforced: a GM composes each one.
    """

    recipient = models.ForeignKey(
        CHARACTER_SHEET_MODEL, on_delete=models.CASCADE, related_name="visions"
    )
    being = models.ForeignKey(WorshippedBeing, on_delete=models.PROTECT, related_name="visions")
    sent_by = models.ForeignKey(
        ACCOUNT_DB_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="visions_sent",
        help_text="The GM who composed it; null once that account is gone.",
    )
    body = models.TextField()
    reveal_source = models.BooleanField(
        default=False, help_text="Whether the recipient is told which being sent it."
    )
    prayer = models.ForeignKey(
        Prayer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="visions",
        help_text="The prayer this answers, when it answers one.",
    )
    clue = models.ForeignKey(
        "arxii.Clue",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="visions",
        help_text="A Codex clue the vision hands the recipient (a mystery's starter).",
    )
    episode = models.ForeignKey(
        "arxii.Episode",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="visions",
        help_text="The episode this is a personal beat of; the recipient must be in its story.",
    )
    message = models.OneToOneField(
        "arxii.NarrativeMessage",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="vision",
        help_text="The narrative message (category VISIONS) that delivered it.",
    )
    answer = models.ForeignKey(
        "arxii.Answer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="visions",
        help_text=(
            "The written-ahead answer this vision delivered (#4333); its follow-up clue "
            "and cost are read from it. Empty for a vision a person sent live."
        ),
    )
    resonance_spent = models.PositiveIntegerField(default=0)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_at"]
        verbose_name = "Vision"
        verbose_name_plural = "Visions"

    def __str__(self) -> str:
        return f"Vision to {self.recipient} from {self.being} ({self.sent_at:%Y-%m-%d})"


class Pledge(CreditedContent, SharedMemoryModel):
    """A pledge type: a being's authored offer of service (#4333 slice 2).

    A character who takes one has ``span_weeks`` game weeks to earn
    ``favor_target`` favor with the being, from any source, and then closes it
    by performing ``closing_rite``. Progress is the favor itself
    (``Project.current_progress`` on the character's PLEDGE project), never a
    separate counter.
    """

    being = models.ForeignKey(WorshippedBeing, on_delete=models.CASCADE, related_name="pledges")
    name = models.CharField(max_length=100)
    description = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Shown to the player when they take the pledge. Progress is counted "
            "automatically from favor."
        ),
    )
    favor_target = models.PositiveIntegerField(
        default=20, help_text="Favor to earn with the being after pledging, before closing."
    )
    span_weeks = models.PositiveSmallIntegerField(
        default=2, help_text="Game weeks the character has to earn the target and close."
    )
    closing_rite = models.ForeignKey(
        WorshipRite,
        on_delete=models.PROTECT,
        related_name="closing_for_pledges",
        help_text="One of the being's own tier 1 or 2 rites; performing it closes the pledge.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["being", "name"]
        constraints = [
            models.UniqueConstraint(fields=["being", "name"], name="unique_being_pledge_name"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.being})"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.favor_target == 0:
            errors["favor_target"] = "A pledge needs a favor target above zero."
        if self.span_weeks == 0:
            errors["span_weeks"] = "A pledge lasts at least one game week."
        if self.closing_rite_id is not None and self.being_id is not None:
            rite = self.closing_rite
            if rite.being_id != self.being_id:
                errors["closing_rite"] = "The closing rite must be one of this being's own rites."
            elif rite.kind.tier == RiteTier.PERILOUS:
                errors["closing_rite"] = (
                    "The closing rite must be tier 1 or 2; a tier 3 rite is a ceremony."
                )
        if errors:
            raise ValidationError(errors)


class PledgeDetails(SharedMemoryModel):
    """Per-kind details of a PLEDGE ``Project`` (#4333 slice 2): one character's
    open or finished pledge.

    The project carries the favor target (``threshold_target``), the span
    (``time_limit``) and the progress (``current_progress``). This sidecar names
    who pledged what, the prayer they pledged with, and how the closing went:
    ``close_attempts`` counts closing rites (a first failure leaves one retry,
    Ruling 17) and ``closing_performance`` is the rite that resolved it. A
    resolved pledge with no closing performance lapsed.
    """

    project = models.OneToOneField(
        "arxii.Project", on_delete=models.CASCADE, related_name="pledge_details"
    )
    character_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL, on_delete=models.CASCADE, related_name="pledges"
    )
    pledge = models.ForeignKey(Pledge, on_delete=models.PROTECT, related_name="taken")
    prayer = models.ForeignKey(
        Prayer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="The player's prayer when taking the pledge; the text lives on the Prayer.",
    )
    closing_performance = models.OneToOneField(
        WorshipRitePerformance,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="closed_pledge",
        help_text="The closing rite that resolved the pledge. Empty for an open or lapsed one.",
    )
    close_attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Pledge details"
        verbose_name_plural = "Pledge details"

    def __str__(self) -> str:
        return f"{self.character_sheet} pledged {self.pledge} (project #{self.project_id})"


class PledgeCredit(SharedMemoryModel):
    """One favor credit to a pledge, with its calculation (#4333 slice 2).

    The audit row behind the pledge card's list: every favor write for the
    pledge's being while it is open, plus the closing or lapse award. The
    counter is ``Project.current_progress``; these rows explain it. ``base`` is
    the favor before the earning rate, ``earning_rate_percent`` the rate applied
    and ``credited`` what landed. The typed source rows say what the credit was
    for: the resonance grant of a deed, the offering of a sacrifice, the rite
    performance of a rite.
    """

    pledge_details = models.ForeignKey(
        PledgeDetails, on_delete=models.CASCADE, related_name="credits"
    )
    source = models.CharField(max_length=20, choices=PledgeCreditSource.choices)
    base = models.PositiveIntegerField(help_text="Favor before the earning rate.")
    earning_rate_percent = models.PositiveIntegerField()
    credited = models.PositiveIntegerField(help_text="Favor credited, at the earning rate.")
    game_week = models.ForeignKey(
        "arxii.GameWeek", on_delete=models.PROTECT, related_name="pledge_credits"
    )
    resonance_grant = models.OneToOneField(
        "arxii.ResonanceGrant",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pledge_credit",
    )
    offering = models.OneToOneField(
        "arxii.CeremonyOffering",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pledge_credit",
    )
    rite_performance = models.ForeignKey(
        WorshipRitePerformance,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pledge_credits",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        indexes = [
            models.Index(fields=["source", "game_week"], name="pledge_credit_source_week"),
        ]

    def __str__(self) -> str:
        return f"{self.get_source_display()} +{self.credited} ({self.pledge_details})"


#: The answer field a tier or a clue kind can refuse; named once for both checks.
_FACT_CLUE_FIELD = "fact_clue"


def answer_part_errors(
    *,
    success_level: int,
    fact_text: str,
    has_fact_clue: bool,
    has_follow_up_clue: bool,
) -> dict[str, str]:
    """The parts an answer at ``success_level`` may not carry (#4333 design 4).

    Fact text and a fact clue only on Success and Critical Success ("no fact
    below Success"); a follow-up clue on Partial Success and above. Failure and
    Critical Failure carry delay, answer and cost only. ``Answer.clean`` reports
    these, and delivery leaves out any part this refuses, so a row saved past
    the form still never hands over a fact below Success.
    """
    errors: dict[str, str] = {}
    if success_level < ANSWER_FACT_MIN_SUCCESS_LEVEL:
        if fact_text.strip():
            errors["fact_text"] = "Fact text is allowed on Success and Critical Success only."
        if has_fact_clue:
            errors[_FACT_CLUE_FIELD] = (
                "A fact clue is allowed on Success and Critical Success only."
            )
    if success_level < ANSWER_FOLLOW_UP_MIN_SUCCESS_LEVEL and has_follow_up_clue:
        errors["follow_up_clue"] = (
            "A follow-up clue is allowed on Partial Success and above; Failure and "
            "Critical Failure carry delay, answer and cost only."
        )
    return errors


class Answer(CreditedContent, SharedMemoryModel):
    """Text staff wrote ahead for a being at one outcome tier (#4333 slice 3).

    Delivered as a ``Vision`` when a closing rite resolves a pledge: the draw
    (``answer_services.draw_answer``) prefers rows for the pledge type, then the
    being's rows with no pledge type, at the closing tier and then each lower
    tier. The parts, in the order the vision reads them: ``delay_text`` (the
    effort was acknowledged), ``answer_text`` followed by the sacrifice lines,
    ``fact_text`` with ``fact_clue`` (one fact, no reason given), ``cost_text``
    with ``cost_pool``, ``follow_up_text`` with ``follow_up_clue`` (a next
    action, usually a mission). Which parts a tier may carry is
    ``answer_part_errors``. ``onlooker_line`` is the one room line others see;
    ``conceals_source`` delivers the vision without naming the being.
    """

    being = models.ForeignKey(WorshippedBeing, on_delete=models.CASCADE, related_name="answers")
    pledge = models.ForeignKey(
        Pledge,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="answers",
        help_text="The pledge type this answers; empty for the being's general answers.",
    )
    outcome_tier = models.ForeignKey(
        "arxii.CheckOutcome", on_delete=models.PROTECT, related_name="being_answers"
    )
    delay_text = models.TextField(
        help_text="Opens the vision and states that the character's effort was acknowledged."
    )
    answer_text = models.TextField(
        blank=True, default="", help_text="The main body. Sacrifice lines are added after it."
    )
    fact_text = models.TextField(
        blank=True,
        default="",
        help_text="States one fact. Success and Critical Success only.",
    )
    fact_clue = models.ForeignKey(
        "arxii.Clue",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="answers_as_fact",
        help_text="A Codex or secret clue handed over with the fact.",
    )
    cost_text = models.TextField(
        blank=True,
        default="",
        help_text="A cost, or a notice that the being has marked the character.",
    )
    cost_pool = models.ForeignKey(
        "arxii.ConsequencePool",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="being_answers",
        help_text="Consequences applied at this answer's outcome tier when it is delivered.",
    )
    follow_up_text = models.TextField(
        blank=True, default="", help_text="A next action, usually a mission."
    )
    follow_up_clue = models.ForeignKey(
        "arxii.Clue",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="answers_as_follow_up",
        help_text="Handed over with the vision. Partial Success and above.",
    )
    onlooker_line = models.CharField(
        max_length=ANSWER_ONLOOKER_LINE_MAX_LENGTH,
        blank=True,
        default="",
        help_text=(
            "Sent to the room as a public line. Others in the room see this line and "
            "nothing else from the answer."
        ),
    )
    conceals_source = models.BooleanField(
        default=False,
        help_text="Deliver the vision without telling the recipient which being sent it.",
    )
    weight = models.PositiveSmallIntegerField(
        default=1, help_text="Relative chance among the answers that fit a draw."
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["being", "pledge", "-outcome_tier__success_level", "pk"]
        indexes = [
            models.Index(fields=["being", "pledge", "outcome_tier"], name="answer_draw_cell"),
        ]

    def __str__(self) -> str:
        scope = self.pledge.name if self.pledge_id is not None else "no pledge type"
        return f"{self.being} answer, {scope}, {self.outcome_tier}"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.outcome_tier_id is not None:
            errors.update(
                answer_part_errors(
                    success_level=self.outcome_tier.success_level,
                    fact_text=self.fact_text,
                    has_fact_clue=self.fact_clue_id is not None,
                    has_follow_up_clue=self.follow_up_clue_id is not None,
                )
            )
        if (
            self.pledge_id is not None
            and self.being_id is not None
            and self.pledge.being_id != self.being_id
        ):
            errors["pledge"] = "The pledge type must be one of this being's own."
        fact_clue_refused = errors.get(_FACT_CLUE_FIELD)
        if self.fact_clue_id is not None and fact_clue_refused is None:
            from world.clues.constants import ClueTargetKind  # noqa: PLC0415

            if self.fact_clue.target_kind not in (ClueTargetKind.CODEX, ClueTargetKind.SECRET):
                errors[_FACT_CLUE_FIELD] = "A fact clue must point at a Codex entry or a secret."
        if self.weight == 0:
            errors["weight"] = "A weight of 0 would never be drawn; clear Active instead."
        if errors:
            raise ValidationError(errors)


class AnswerSacrificeLine(SharedMemoryModel):
    """One authored line of an answer for one facet (#4333 slice 3).

    The vision adds the line once for each distinct facet recorded on the
    pledge's sacrifices (``CeremonyOffering.facet``), after the answer text.
    """

    answer = models.ForeignKey(Answer, on_delete=models.CASCADE, related_name="sacrifice_lines")
    facet = models.ForeignKey(
        "arxii.Facet", on_delete=models.PROTECT, related_name="answer_sacrifice_lines"
    )
    text = models.TextField()

    class Meta:
        ordering = ["answer", "facet__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["answer", "facet"], name="unique_answer_sacrifice_line_facet"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.answer}: {self.facet}"


class PendingAnswer(SharedMemoryModel):
    """An answer drawn at a pledge's close that the being's worship pool could not
    yet pay for (#4333 slice 3).

    Held, never dropped: the daily tick (``deliver_held_answers``) sends it as a
    vision once the pool can pay, and deletes this row; the ``Vision`` it
    becomes is the lasting record. Staff see held answers on the being's
    dashboard.
    """

    character_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL, on_delete=models.CASCADE, related_name="pending_answers"
    )
    answer = models.ForeignKey(Answer, on_delete=models.PROTECT, related_name="pending")
    pledge_details = models.OneToOneField(
        PledgeDetails, on_delete=models.CASCADE, related_name="pending_answer"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]

    def __str__(self) -> str:
        return f"Held answer for {self.character_sheet} ({self.answer})"


class BeingSteward(SharedMemoryModel):
    """A GM table that answers for a being (#4333 slice 4, design 5).

    Staff assign it from the being's admin page. The table's GM writes the
    being's pledge types and answers on the table page, and a closing rite of a
    pledge to it goes to that GM as a ``BEING_ANSWER`` prompt instead of a draw.
    Only the table's members can pledge to, invoke or pray to a stewarded being.
    Refused for a table whose GM is below Senior and for a being that shows a
    sign of being a god (``steward_services.steward_refusals``).
    """

    being = models.OneToOneField(WorshippedBeing, on_delete=models.CASCADE, related_name="steward")
    table = models.ForeignKey(
        "arxii.GMTable", on_delete=models.PROTECT, related_name="stewarded_beings"
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["being__name"]
        verbose_name = "Being steward"
        verbose_name_plural = "Being stewards"

    def __str__(self) -> str:
        return f"{self.being} stewarded by {self.table.name}"

    def clean(self) -> None:
        super().clean()
        if self.being_id is None or self.table_id is None:
            return
        from world.worship.steward_services import steward_refusals  # noqa: PLC0415

        refusals = steward_refusals(self.being, self.table)
        if refusals:
            raise ValidationError({"table": refusals})
