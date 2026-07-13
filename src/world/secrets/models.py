"""Character Secrets (#1334) — hidden facts about a concrete entity.

A ``Secret`` is the missing fourth primitive alongside Distinction (permanent trait) /
Condition (live state) / Resonance: a hidden FACT or RELATIONSHIP that must be earned and
shared, carrying consequences. Bio/story stay public; sensitive information lives here.

This module owns the secret *content* (slice 1). Discovery + the per-knower held record
(partial knowledge), the clue-target wiring, and the display tab are later slices.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.secrets.constants import SecretLevel, SecretProvenance

# App-qualified model path repeated across FK references; centralized for dedup.
_CHARACTER_SHEET_MODEL = "character_sheets.CharacterSheet"


class SecretCategory(SharedMemoryModel):
    """What a secret is *about* — gossip, scandal, magical, family, incriminating, …

    A staff-editable lookup (not ``TextChoices``) so the taxonomy can grow without a
    migration. A secret with no category reads as **Unknown** — a first-class state, not a
    gap: a knower may hold the fact without having placed its category.
    """

    name = models.CharField(
        max_length=60, unique=True, help_text="Category label (player-visible)."
    )
    description = models.TextField(blank=True, help_text="Staff note on what belongs here.")
    is_active = models.BooleanField(default=True, help_text="Offer this category to authors.")

    class Meta:
        verbose_name = "Secret category"
        verbose_name_plural = "Secret categories"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Secret(SharedMemoryModel):
    """A hidden fact about a character, with a level, a category, and consequences.

    Subject-anchored and **always single-owner**: ``subject_sheet`` is who the secret is *about*
    and owns it (authorship ≠ ownership — a GM-written secret *for* a character is owned by that
    character, who knows it; others discover it). There are no group/shared secrets: a multi-party
    situation (affair, blackmail) is two *distinct* secrets, one owned by each character — never a
    shared row. ``category`` and ``consequences`` may be left blank/null to mean **Unknown** (a
    deliberate puzzle state).

    Provenance + the anchor-scales-with-level invariant (``clean``) keep player-flavor from
    masquerading as canon: only Level-1 player-flavor secrets may be free-authored; anything
    heavier must be GM- or action-anchored.
    """

    subject_sheet = models.ForeignKey(
        _CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="secrets",
        help_text="The character this secret is about — and its sole owner.",
    )
    level = models.PositiveSmallIntegerField(
        choices=SecretLevel.choices,
        default=SecretLevel.UNCOMMON_KNOWLEDGE,
        help_text="How deep/dangerous — narrative weight + default share-scope.",
    )
    category = models.ForeignKey(
        SecretCategory,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="secrets",
        help_text="What the secret is about. Null = Unknown (not yet placed).",
    )
    consequences = models.TextField(
        blank=True,
        help_text="What happens if it surfaces. Blank = Unknown.",
    )
    content = models.TextField(
        blank=True,
        help_text="The secret itself, as narrated. Player- or GM-authored prose.",
    )
    provenance = models.CharField(
        max_length=10,
        choices=SecretProvenance.choices,
        help_text="Where the secret came from (drives the anchor rule + OOC attribution).",
    )
    subject_aware = models.BooleanField(
        default=True,
        help_text=(
            "Whether the subject starts knowing this secret about themselves. False for "
            "subject-unaware truths (#2062 — e.g. hidden parentage a Misbegotten hasn't "
            "discovered): excluded from the subject's own-secrets shelf until a "
            "SecretKnowledge row grants it."
        ),
    )
    author_persona = models.ForeignKey(
        "scenes.Persona",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="authored_secrets",
        help_text="The narrating persona (player-authored). Null for GM/staff-authored.",
    )
    # --- Act anchor (#1573): the recorded act this secret is the hidden truth behind. ---
    # ONE secret = one act. That act surfaces through several *records* — a mission deed (the
    # mechanical act), a legend entry (the public, embellished telling), and/or the scene it
    # happened in — but they are co-facets of the *same* act, so they live as independent optional
    # FKs on the single secret. They are never fragmented into one-secret-per-record (which would
    # leave a knower thinking they hold three secrets about one event). The distinct *consequences*
    # (legend, criminal, society) ride the #1429 reputation payload below, not these links. Any
    # subset may be set; all-null = unanchored (the common case). FK direction is specific→general
    # per ADR-0010: the secret (consumer) points at the reusable record primitives, and `scenes`/
    # `missions` stay free of any dependency on `secrets`.
    legend_deed = models.ForeignKey(
        "societies.LegendEntry",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="explaining_secrets",
        help_text="The public legend telling of the act this secret is the truth behind (#1573).",
    )
    mission_deed = models.ForeignKey(
        "missions.MissionDeedRecord",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="explaining_secrets",
        help_text="The recorded mission act this secret is the truth behind (#1573).",
    )
    scene = models.ForeignKey(
        "scenes.Scene",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="explaining_secrets",
        help_text="Scene the act happened in — freeform/blackmail context (#1573).",
    )
    # --- Reputation payload (#1429): how this fact reads when it becomes known. ---
    # The diffuse channel — a vector of moral framings dot-producted against each aware society's
    # principles, so the same fact reads positive to one society and negative to another. Empty =
    # no diffuse reputational impact. Authored, or generated (e.g. a mission seeds them by act).
    archetypes = models.ManyToManyField(
        "societies.PhilosophicalArchetype",
        blank=True,
        related_name="secrets",
        help_text="Moral framings that drive the diffuse per-society reputation hit on reveal.",
    )
    # One-shot tracking: societies this secret has already been exposed to, so re-exposure never
    # double-fires the reputation hit (mirrors LegendEntry.societies_aware).
    societies_exposed = models.ManyToManyField(
        "societies.Society",
        blank=True,
        related_name="exposed_secrets",
        help_text="Societies already exposed to this secret (so reveal fires once per society).",
    )
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_date"]
        indexes = [
            models.Index(fields=["subject_sheet", "level"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_level_display()} secret about {self.subject_sheet_id}"

    @property
    def is_act_anchored(self) -> bool:
        """Whether this secret is the hidden truth behind a recorded act (#1573).

        True if any of the act-record anchors (legend deed / mission deed / scene) is set —
        the several records are facets of one act, so any one of them makes the secret anchored.
        """
        return bool(self.legend_deed_id or self.mission_deed_id or self.scene_id)

    def clean(self) -> None:
        """Enforce the secret invariants (#1334, #1573).

        - **Anchor scales with level:** player-flavor secrets carry no mechanical effect, so
          their truth is moot — but that only holds at Level 1. Anything heavier must be GM- or
          action-anchored (what stops a player free-writing a Dangerous-tier "I killed a god").
        - **Anchored ⇒ evidenced:** a secret tied to a recorded act (legend/mission/scene) is
          true-because-it-happened, so it can never be player-flavor (unverified) — minting it
          from play uses ``ACTION_ANCHORED`` provenance.

        Both rules are ``PLAYER_FLAVOR``-specific by design. ``ACCUSATION`` (#1825) is
        deliberately **exempt** — a player-authored false scandal is *meant* to carry weight and
        anchor to an alleged deed; its guard is the consent gate at the mint action, not the
        model. Do not widen these checks to catch ``ACCUSATION``.
        """
        super().clean()
        if (
            self.provenance == SecretProvenance.PLAYER_FLAVOR
            and self.level != SecretLevel.UNCOMMON_KNOWLEDGE
        ):
            msg = "Player-authored secrets above Level 1 must be GM- or action-anchored."
            raise ValidationError({"level": msg})
        if self.is_act_anchored and self.provenance == SecretProvenance.PLAYER_FLAVOR:
            msg = "A secret anchored to a recorded act is evidenced, not player-flavor."
            raise ValidationError({"provenance": msg})


class SecretVictim(SharedMemoryModel):
    """A specific entity directly harmed by a secret's underlying fact (#1429).

    The **relational / targeted** reputation channel, distinct from the diffuse archetype reading:
    a named victim is hit directly and **independently of their own philosophy** (an org that
    prizes cunning still turns on you for killing its head). Exactly one of ``organization`` /
    ``persona`` is set.

    On reveal the bridge fires an ``OrganizationReputation`` hit for **organization** victims.
    **Persona** victims are recorded but their effect (a personal grudge) is a deferred follow-up:
    the relationship system is consent-gated, so the right home for persona enmity is an open
    design decision — see the bridge service.
    """

    secret = models.ForeignKey(
        Secret,
        on_delete=models.CASCADE,
        related_name="victims",
        help_text="The secret whose underlying fact harmed this entity.",
    )
    organization = models.ForeignKey(
        "societies.Organization",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="secret_victimhoods",
        help_text="The victim organization (collective victim).",
    )
    persona = models.ForeignKey(
        "scenes.Persona",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="secret_victimhoods",
        help_text="The victim persona (individual victim).",
    )
    severity = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Optional magnitude of the direct standing hit. Null = derive from secret level.",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(organization__isnull=False, persona__isnull=True)
                    | models.Q(organization__isnull=True, persona__isnull=False)
                ),
                name="secret_victim_exactly_one_target",
            ),
        ]

    def __str__(self) -> str:
        target = self.organization_id or f"persona {self.persona_id}"
        return f"victim {target} of secret {self.secret_id}"


class SecretGrievance(SharedMemoryModel):
    """Records that a secret's victim has answered it with a grievance — one per victim (#1429).

    Grieving is a **one-time choice**: this row marks the secret *answered* for that victim, so it
    drops off the grievance menu / `can_grieve` flag and a second attempt is rejected (no stacking
    grudge swings). Links the `RelationshipCapstone` the answer applied, so a past response can be
    shown.
    """

    secret = models.ForeignKey(
        Secret,
        on_delete=models.CASCADE,
        related_name="grievances",
        help_text="The secret that was answered.",
    )
    victim_sheet = models.ForeignKey(
        _CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="secret_grievances",
        help_text="The wronged character who answered it.",
    )
    capstone = models.ForeignKey(
        "relationships.RelationshipCapstone",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="The relationship capstone this grievance applied.",
    )
    created_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["secret", "victim_sheet"], name="one_grievance_per_secret_victim"
            ),
        ]

    def __str__(self) -> str:
        return f"grievance by {self.victim_sheet_id} for secret {self.secret_id}"


class SecretKnowledge(SharedMemoryModel):
    """A character's held knowledge of a secret, with partial-knowledge layers (#1334).

    Roster-scoped like ``CharacterClue`` (knowledge follows the character across players).
    Holding the row means you know the **fact**; ``knows_category`` / ``knows_consequences``
    track whether you've *also* placed its category or learned its fallout — so a secret's
    Unknown layers can persist per-knower even after the fact itself is out. Layers only ever
    unlock (monotonic); they're never re-hidden.
    """

    roster_entry = models.ForeignKey(
        "roster.RosterEntry",
        on_delete=models.CASCADE,
        related_name="secrets_known",
        help_text="The character who holds this knowledge.",
    )
    secret = models.ForeignKey(
        Secret,
        on_delete=models.CASCADE,
        related_name="known_by",
        help_text="The secret this character knows.",
    )
    knows_category = models.BooleanField(
        default=False,
        help_text="Whether this knower has placed the secret's category (else it reads Unknown).",
    )
    knows_consequences = models.BooleanField(
        default=False,
        help_text="Whether this knower has learned the secret's consequences.",
    )
    found_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["roster_entry", "secret"]
        ordering = ["-found_at"]
        verbose_name = "Secret knowledge"
        verbose_name_plural = "Secret knowledge"

    def __str__(self) -> str:
        return f"{self.roster_entry_id} knows secret {self.secret_id}"


class SecretGossip(SharedMemoryModel):
    """Regional spread "heat" for a Level-1 secret — the casual gossip tier (#1572).

    Per-``(secret, region)`` decaying counter, where ``region`` is the `areas.Area` at
    ``AreaLevel.REGION``. ``heat == 0`` ⇒ never gossiped here (not findable via gossip);
    ``heat >= 1`` ⇒ findable (and lingers at the decay floor unless actively suppressed to 0).
    Planting raises heat (a Gossip check), seeking surfaces ``heat >= 1`` secrets, suppression
    lowers it; a daily tick decays heat toward the floor. At the public threshold the gossip goes
    ambient and exposes to the region's societies (``went_public`` one-shots that). Distinct from
    the formal ``expose_secret``/`tidings` path — this is the pre-exposure, skill-gated tier.
    """

    secret = models.ForeignKey(
        Secret,
        on_delete=models.CASCADE,
        related_name="gossip_heat",
        help_text="The Level-1 secret being gossiped.",
    )
    region = models.ForeignKey(
        "areas.Area",
        on_delete=models.CASCADE,
        related_name="gossip_heat",
        help_text="The region (Area at AreaLevel.REGION) this heat is scoped to.",
    )
    heat = models.PositiveIntegerField(
        default=0,
        help_text="Spread heat: ≥1 findable, decays toward the floor, public at the threshold.",
    )
    went_public = models.BooleanField(
        default=False,
        help_text="Whether heat crossed the public threshold (one-shot: ambient + exposure).",
    )
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["secret", "region"]
        indexes = [
            models.Index(fields=["region", "heat"]),
        ]
        verbose_name = "Secret gossip"
        verbose_name_plural = "Secret gossip"

    def __str__(self) -> str:
        return f"gossip heat {self.heat} for secret {self.secret_id} in region {self.region_id}"


class Leverage(SharedMemoryModel):
    """Coercive leverage one character holds over another, founded on a Secret (#1680).

    Minted when a **blackmail** action succeeds (the actor knows a ``Secret`` about the
    target and presses it). A **standing** marker, not one-shot:

    - **vs an NPC** it makes ``FAVOR`` ``NPCServiceOffer`` rows claimable — the
      ``has_leverage_over`` predicate leaf reads the actor's leverage — and each claim is
      throttled per-time by the existing ``OfferCooldown`` (the "trade-in").
    - **vs a PC** it is the coded anchor for a reveal-threat; the demand itself is RP.

    Both ends anchor on ``CharacterSheet`` (the source-of-truth character handle, held by
    PCs and NPCs alike); per ADR-0010 the consumer (leverage) points at the ``Secret``
    primitive, so ``secrets`` gains no dependency on its consumers.
    """

    holder_sheet = models.ForeignKey(
        _CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="leverage_held",
        help_text="The character who holds this leverage (the blackmailer).",
    )
    subject_sheet = models.ForeignKey(
        _CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="leverage_against",
        help_text="The character the leverage is over (PC or NPC).",
    )
    founded_on = models.ForeignKey(
        Secret,
        on_delete=models.CASCADE,
        related_name="leverage",
        help_text="The secret this leverage is built from.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["holder_sheet", "subject_sheet", "founded_on"],
                name="uniq_leverage_holder_subject_secret",
            ),
        ]
        ordering = ["subject_sheet", "holder_sheet"]
        verbose_name = "Leverage"
        verbose_name_plural = "Leverage"

    def __str__(self) -> str:
        return f"leverage {self.holder_sheet_id} over {self.subject_sheet_id}"
