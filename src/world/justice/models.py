"""Justice — local law, crime taxonomy, and persona pursuit heat (#1765).

Heat is *how actively local forces hunt a specific persona in a specific
place* — distinct from ``SocietyReputation`` (how a group regards you).
Laws live on the ``areas.Area`` tree and resolve most-specific-wins;
jurisdiction is judged once, at the commit/allegation location, and heat
only mints inside the enforcing society's dominion (ADR: heat jurisdiction).
"""

from django.core.validators import MinValueValidator
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.justice.constants import DEFAULT_HEAT_WEIGHT, EVIDENCE_BASE_QUALITY, EvidenceState

# App-qualified model path repeated across FK references; centralized for dedup.
_LEGEND_ENTRY_MODEL = "societies.LegendEntry"
_SOCIETY_MODEL = "societies.Society"
_AREA_MODEL = "areas.Area"
_PERSONA_MODEL = "scenes.Persona"


class CrimeKind(SharedMemoryModel):
    """A normalized crime category ("murder", "theft", …) that laws reference.

    Kinds are data rows (seeded/admin-authored), deliberately normalized so a
    deed tagged once is prosecutable wherever a law names the kind — missed
    crimes, not over-flagging, are the failure mode to guard against.

    CONTENT RULE (user-ratified, #1765): no sexual crimes of any nature are
    ever represented here — no rape, sexual assault, or sexual-crime kinds.
    Such crimes canonically exist in-world but are never represented in game
    data or mechanics, out of respect for survivors among the player base.
    Do not add one; do not accept a seed row containing one.
    """

    slug = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["slug"]

    def __str__(self) -> str:
        return self.name


class AreaLaw(SharedMemoryModel):
    """One area's posture toward one crime kind — the feudal local knob.

    Resolution is most-specific-wins up the area tree: a barony row (including
    an ``exempts`` row) beats the kingdom default, and gaps fall through to the
    liege's law. Because the local row overrides, ``heat_weight`` expresses both
    "illegal here" and "how hard the local authority pursues it" in one place.
    """

    area = models.ForeignKey(
        _AREA_MODEL,
        on_delete=models.CASCADE,
        related_name="laws",
    )
    crime_kind = models.ForeignKey(
        CrimeKind,
        on_delete=models.PROTECT,
        related_name="laws",
    )
    heat_weight = models.IntegerField(
        default=DEFAULT_HEAT_WEIGHT,
        validators=[MinValueValidator(0)],
        help_text="Heat minted per accrual event here (PLACEHOLDER magnitudes).",
    )
    exempts = models.BooleanField(
        default=False,
        help_text="Explicitly legal here despite an ancestor's ban (short-circuits the cascade).",
    )
    punishment = models.CharField(
        max_length=200,
        blank=True,
        help_text="Admin-editable flavor shown on the crime tab (PLACEHOLDER until authored).",
    )

    class Meta:
        ordering = ["area_id", "crime_kind_id"]
        constraints = [
            models.UniqueConstraint(fields=["area", "crime_kind"], name="unique_area_crime_law"),
        ]

    def __str__(self) -> str:
        verb = "exempts" if self.exempts else "outlaws"
        return f"{self.area} {verb} {self.crime_kind}"


class DeedCrimeTag(SharedMemoryModel):
    """Marks a legend deed as an instance of a crime kind.

    Lives in justice (not societies) so the reusable Legend primitive stays
    dependency-free — the consumer points into the primitive (FK direction:
    specific→general).
    """

    deed = models.ForeignKey(
        _LEGEND_ENTRY_MODEL,
        on_delete=models.CASCADE,
        related_name="crime_tags",
    )
    crime_kind = models.ForeignKey(
        CrimeKind,
        on_delete=models.PROTECT,
        related_name="deed_tags",
    )

    class Meta:
        ordering = ["deed_id", "crime_kind_id"]
        constraints = [
            models.UniqueConstraint(fields=["deed", "crime_kind"], name="unique_deed_crime_tag"),
        ]

    def __str__(self) -> str:
        return f"deed {self.deed_id} tagged {self.crime_kind}"


class PersonaHeat(SharedMemoryModel):
    """Accumulated pursuit heat for one persona, in one area, under one warrant.

    Subject is the persona *as presented* — deliberately including TEMPORARY
    masks (divergence from ``SocietyReputation.clean()``): a mask soaks the
    heat and burning it genuinely sheds pursuit, at the cost that a temporary
    persona holds no reputation, renown, or property. ``society`` is the
    enforcing society captured at mint time, so the warrant survives later
    changes of an area's dominance.
    """

    persona = models.ForeignKey(
        _PERSONA_MODEL,
        on_delete=models.CASCADE,
        related_name="heat_rows",
    )
    area = models.ForeignKey(
        _AREA_MODEL,
        on_delete=models.CASCADE,
        related_name="heat_rows",
    )
    society = models.ForeignKey(
        _SOCIETY_MODEL,
        on_delete=models.CASCADE,
        related_name="heat_rows",
    )
    value = models.PositiveIntegerField(default=0)
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-value"]
        constraints = [
            models.UniqueConstraint(
                fields=["persona", "area", "society"], name="unique_persona_area_society_heat"
            ),
        ]
        indexes = [
            models.Index(fields=["persona", "society"]),
        ]
        verbose_name = "Persona heat"
        verbose_name_plural = "Persona heat"

    def __str__(self) -> str:
        return f"heat {self.value} for persona {self.persona_id} in area {self.area_id}"


class HeatSource(SharedMemoryModel):
    """Provenance for a heat row — the *allegation* trail feeding the crime tab.

    Records an alleged deed against the accused persona (via ``heat``) and
    never verifies actorship: a false accusation is just a divergence between
    allegation and truth, not a stored flag.
    """

    heat = models.ForeignKey(
        PersonaHeat,
        on_delete=models.CASCADE,
        related_name="sources",
    )
    deed = models.ForeignKey(
        _LEGEND_ENTRY_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="heat_sources",
    )
    amount = models.IntegerField()
    created_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_date"]

    def __str__(self) -> str:
        return f"+{self.amount} heat on row {self.heat_id}"


class AccusationCrimeClaim(SharedMemoryModel):
    """The bridge from a player-authored ACCUSATION secret into pursuit heat (#1825).

    Frame-jobs (``secrets`` #1825) let a player author a false scandal against a
    target; this row is what makes a *criminal* accusation bite the justice
    system rather than only reputation. The tier is emergent from how much real
    crime sits underneath:

    * **Wild accusation (L2)** — ``real_deed`` is null. The accuser names a
      ``crime_kind`` off a dropdown with no crime underneath ("they murdered
      someone I invented"). It still mints heat, but it is fragile: scrutiny
      finds no corroborating deed, so it is easily refuted.
    * **Frame for a real crime (L3)** — ``real_deed`` anchors a crime that
      genuinely happened (a ``LegendEntry`` the accuser is shifting blame away
      from, often their own) but which the subject did not commit. Robust:
      the crime is real, so refuting it means proving the subject's innocence,
      not disproving the crime.

    Actorship is never verified here (false accusations are first-class, #1765) —
    the row records the *allegation*. Lives justice-side (FK into
    ``secrets.Secret``) so ``secrets`` stays dependency-free (ADR-0010).
    """

    secret = models.OneToOneField(
        "secrets.Secret",
        on_delete=models.CASCADE,
        related_name="accusation_crime_claim",
    )
    crime_kind = models.ForeignKey(
        CrimeKind,
        on_delete=models.PROTECT,
        related_name="accusation_claims",
    )
    real_deed = models.ForeignKey(
        _LEGEND_ENTRY_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="frame_claims",
        help_text="The real crime being pinned on the subject (L3 frame); null for a wild L2.",
    )
    retracted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Set by nullification (#1825): a retracted claim accrues no further heat; "
            "already-minted heat decays out on its own."
        ),
    )
    created_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_date"]

    @property
    def is_wild(self) -> bool:
        """L2: a claimed crime with no real deed underneath — the fragile kind."""
        return self.real_deed_id is None

    def __str__(self) -> str:
        kind = "wild" if self.is_wild else "frame"
        return f"{kind} accusation claim: secret {self.secret_id} alleges {self.crime_kind}"


class AccusationNullification(SharedMemoryModel):
    """The record that an accusation was proven fabricated (#1825).

    Written once by ``nullify_accusation`` (the investigation project's payoff). The
    accusation Secret itself STAYS — the claim was really made; truth stays emergent —
    but its reputation damage is compensated, its gossip heat zeroed, and its criminal
    claim retracted. ``authorship_secret`` is the falseness made discoverable: an
    ACTION_ANCHORED secret **about the framer**, granted to no one at mint — unearthing
    it (the harder author-unmask trail) is what arms the denounce/backfire step.
    """

    secret = models.OneToOneField(
        "secrets.Secret",
        on_delete=models.CASCADE,
        related_name="nullification",
        help_text="The ACCUSATION secret that was proven fabricated.",
    )
    authorship_secret = models.OneToOneField(
        "secrets.Secret",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="nullification_authorship",
        help_text="The 'fabricated by <framer>' secret; null for authorless accusations.",
    )
    nullified_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-nullified_at"]
        verbose_name = "Accusation nullification"
        verbose_name_plural = "Accusation nullifications"

    def __str__(self) -> str:
        return f"nullification of secret {self.secret_id}"


class FrameJobDetails(SharedMemoryModel):
    """Per-kind details for a FRAME_JOB ``Project`` (#1825) — the evidence being perverted.

    Follows the details-model pattern (``RoomFeatureProgressionDetails``): a OneToOne
    payload the completion handler reads. The frame only ever grows from a real crime's
    gathered evidence, doctored in a Workshop of Iniquity with Forgery checks; on a
    successful completion ``resolve_frame_job`` files the anchored L3 accusation.
    """

    project = models.OneToOneField(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="frame_job_details",
    )
    evidence = models.ForeignKey(
        "justice.CrimeEvidence",
        on_delete=models.PROTECT,
        related_name="frame_jobs",
        help_text="The gathered evidence being doctored.",
    )
    subject_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.PROTECT,
        related_name="frame_jobs_against",
        help_text="The patsy the crime is being pinned on.",
    )
    crime_kind = models.ForeignKey(
        CrimeKind,
        on_delete=models.PROTECT,
        related_name="frame_jobs",
        help_text="The alleged crime — must be one the evidence's deed is tagged with.",
    )
    content = models.TextField(help_text="The claim the finished frame will assert.")

    class Meta:
        verbose_name = "Frame job details"
        verbose_name_plural = "Frame job details"

    def __str__(self) -> str:
        return f"frame job on sheet {self.subject_sheet_id} (project #{self.project_id})"


class DenounceRecord(SharedMemoryModel):
    """One character's public denunciation of an unmasked framer (#1825).

    The consent-gated backfire's once-only guard: exposing the authorship secret is
    idempotent on the exposure engine's side, but the level-scaled heat must not
    stack per repeat — one denounce per denouncer per authorship secret.
    """

    authorship_secret = models.ForeignKey(
        "secrets.Secret",
        on_delete=models.CASCADE,
        related_name="denouncements",
    )
    denouncer_sheet = models.ForeignKey(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="denouncements_made",
    )
    created_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["authorship_secret", "denouncer_sheet"],
                name="uniq_denounce_secret_denouncer",
            ),
        ]
        ordering = ["-created_date"]
        verbose_name = "Denounce record"
        verbose_name_plural = "Denounce records"

    def __str__(self) -> str:
        return f"denounce of secret {self.authorship_secret_id} by sheet {self.denouncer_sheet_id}"


class CrimeEvidence(SharedMemoryModel):
    """Physical evidence a crime-tagged deed left at the scene (#1825).

    Generated by ``tag_deed_crimes`` when the deed has a located scene — one row
    per deed. Evidence is *physical*: gathering it mints a real inventory item
    (``item_instance``), so hand-offs, theft, and stashing ride the item system,
    and holding it is what lets a character start the counter-investigation.
    The perpetrator's moves are **dispose** (destroy the trail — dampens future
    deed-knowledge heat) and **tamper** (a frame-job project perverts it into an
    L3 accusation anchor; ``tamper_quality`` records the forger's craft and is
    the examine check's target). Lives justice-side; FK into ``items`` follows
    ADR-0010 (consumer → primitive).
    """

    deed = models.OneToOneField(
        _LEGEND_ENTRY_MODEL,
        on_delete=models.CASCADE,
        related_name="crime_evidence",
    )
    room_profile = models.ForeignKey(
        "evennia_extensions.RoomProfile",
        on_delete=models.PROTECT,
        related_name="crime_evidence",
        help_text="The scene of the crime — where the evidence lies until gathered.",
    )
    item_instance = models.OneToOneField(
        "items.ItemInstance",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="crime_evidence",
        help_text="The physical item, once gathered (null while at the scene or off-grid).",
    )
    state = models.CharField(
        max_length=12,
        choices=EvidenceState.choices,
        default=EvidenceState.AT_SCENE,
    )
    quality = models.PositiveIntegerField(
        default=EVIDENCE_BASE_QUALITY,
        help_text="Gather/dispose check difficulty (PLACEHOLDER magnitude).",
    )
    tamper_quality = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="The frame-job's craft — the Scrutinize Evidence check's target difficulty.",
    )
    created_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_date"]
        verbose_name = "Crime evidence"
        verbose_name_plural = "Crime evidence"

    def __str__(self) -> str:
        return f"evidence for deed {self.deed_id} ({self.state})"


class LieLowState(SharedMemoryModel):
    """A persona's declared go-to-ground state in one area (#1826).

    Declared, never automatic: the cost is muting their presence — extra heat
    decay there, and their rackets miss them (CRIME_KICKUP collection malus).
    Broken the moment they take IC action in the area (interaction or fresh
    heat). Self-visible only — leaking it would defeat it.
    """

    persona = models.ForeignKey(
        _PERSONA_MODEL,
        on_delete=models.CASCADE,
        related_name="lie_low_states",
    )
    area = models.ForeignKey(
        _AREA_MODEL,
        on_delete=models.CASCADE,
        related_name="lie_low_states",
    )
    declared_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-declared_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["persona", "area"],
                condition=models.Q(ended_at__isnull=True),
                name="one_active_lie_low_per_persona_area",
            ),
        ]

    def __str__(self) -> str:
        state = "active" if self.ended_at is None else "ended"
        return f"lie-low ({state}) persona {self.persona_id} in area {self.area_id}"


class PardonGrant(SharedMemoryModel):
    """Audit row for a lord's pardon (#1826) — a public act with a real holder."""

    granter_persona = models.ForeignKey(
        _PERSONA_MODEL,
        on_delete=models.PROTECT,
        related_name="pardons_granted",
    )
    target_persona = models.ForeignKey(
        _PERSONA_MODEL,
        on_delete=models.CASCADE,
        related_name="pardons_received",
    )
    area = models.ForeignKey(
        _AREA_MODEL,
        on_delete=models.CASCADE,
        related_name="pardons",
    )
    society = models.ForeignKey(
        _SOCIETY_MODEL,
        on_delete=models.CASCADE,
        related_name="pardons",
    )
    heat_cleared = models.PositiveIntegerField(default=0)
    created_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_date"]

    def __str__(self) -> str:
        return f"pardon of persona {self.target_persona_id} in area {self.area_id}"


class GuardEncounter(SharedMemoryModel):
    """One guard-pressure event against a wanted persona (#2378).

    Event-driven rolls, never patrol simulation: minted by the trigger ladder
    (NPC transaction / public interaction / room arrival, by tier) and resolved
    by an evasion check. Capture opens a JusticeCase.
    """

    persona = models.ForeignKey(
        _PERSONA_MODEL, on_delete=models.CASCADE, related_name="guard_encounters"
    )
    area = models.ForeignKey(_AREA_MODEL, on_delete=models.CASCADE, related_name="guard_encounters")
    trigger = models.CharField(max_length=30)
    outcome = models.CharField(max_length=20, blank=True, default="")
    opened_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-opened_at"]

    def __str__(self) -> str:
        return f"guard encounter ({self.trigger}) persona {self.persona_id}"


class JusticeCase(SharedMemoryModel):
    """Custody state from arrest to release/trial (#2378).

    The trial waits on the CAPTIVE to initiate — no forced trials, no
    in-absentia verdicts. Helpers can only help: exculpatory submissions past
    the threshold release outright. ``failed_outs`` counts spent chances (a
    lost trial, an evidence push that fell short) — the exhaustion input to
    the lethal wall.
    """

    persona = models.ForeignKey(
        _PERSONA_MODEL, on_delete=models.CASCADE, related_name="justice_cases"
    )
    area = models.ForeignKey(_AREA_MODEL, on_delete=models.CASCADE, related_name="justice_cases")
    society = models.ForeignKey(
        _SOCIETY_MODEL, on_delete=models.CASCADE, related_name="justice_cases"
    )
    captivity = models.ForeignKey(
        "captivity.Captivity",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="justice_cases",
    )
    status = models.CharField(max_length=30, default="awaiting_trial")
    prosecution_weight = models.PositiveIntegerField(
        default=0, help_text="Snapshot of the heat behind the arrest."
    )
    failed_outs = models.PositiveSmallIntegerField(default=0)
    verdict = models.CharField(max_length=20, blank=True, default="")
    sentence_kind = models.CharField(max_length=20, blank=True, default="")
    sentence_amount = models.PositiveIntegerField(
        default=0, help_text="Fine coppers or brig days, per sentence_kind."
    )
    opened_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-opened_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["persona", "area"],
                condition=models.Q(status="awaiting_trial"),
                name="one_open_case_per_persona_area",
            ),
        ]

    def __str__(self) -> str:
        return f"case ({self.status}) persona {self.persona_id} in area {self.area_id}"


class ExculpatoryEvidence(SharedMemoryModel):
    """A helper's exculpatory submission on a case (#2378). Help-only by design.

    Submissions can only LOWER a case's effective weight; there is no hostile
    path. A manufactured submission later exposed backfires on the SUBMITTER
    (an evidence-tampering crime), never on the accused.
    """

    case = models.ForeignKey(
        JusticeCase, on_delete=models.CASCADE, related_name="exculpatory_evidence"
    )
    submitter_persona = models.ForeignKey(
        _PERSONA_MODEL, on_delete=models.CASCADE, related_name="exculpatory_submissions"
    )
    weight = models.PositiveIntegerField(default=0)
    manufactured = models.BooleanField(default=False)
    exposed = models.BooleanField(default=False)
    created_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_date"]

    def __str__(self) -> str:
        return f"evidence (w{self.weight}) on case {self.case_id}"
