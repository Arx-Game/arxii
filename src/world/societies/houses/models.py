"""Houses models (#1884): fealty & titles, recognition, domains, pacts.

A house IS an ``Organization`` (noble/merchant/crime are org rows with
different holdings vocabularies); the org side holds the FK to the kinship
``Family`` (specific→general, ADR-0010). Fealty is an org→org edge forming
the realm tree; ``Title`` is first-class with succession law on the house
and per-title overrides. Domains ride the #930 ruling (abstract Areas with
civ stats) and feed the existing streams→treasury spine. Marriage pacts are
union-bound (CK2 rule: a spouse dies, the pact dies) with coded commitments.
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.societies.houses.constants import (
    CRISIS_INCOME_FACTORS,
    DOMAIN_PROSPERITY_BASELINE,
    CrisisOrigin,
    CrisisResolution,
    CrisisResolutionKind,
    DomainCrisisSeverity,
    HouseClaimStatus,
    PactCommitmentKind,
    PactDissolutionReason,
    RecognitionRuleKind,
    SuccessionDerivation,
    SuccessionOrdering,
    TitleTier,
)

_ORG_FK = "societies.Organization"
_KINSPERSON_FK = "roster.Kinsperson"
_REALM_FK = "realms.Realm"


class NobiliaryParticle(SharedMemoryModel):
    """Per-realm × family-type nobiliary particle (#1884).

    Derived names render ``first_name + particle + house_name`` (e.g.
    former-Luxen houses carry "du"). Particle strings are PLACEHOLDER in
    seeds — the real per-realm particles are authored at content time.
    """

    realm = models.ForeignKey(
        _REALM_FK,
        on_delete=models.CASCADE,
        related_name="nobiliary_particles",
    )
    family_type = models.CharField(
        max_length=20,
        help_text="roster.Family.FamilyType value this particle applies to.",
    )
    particle = models.CharField(
        max_length=20,
        help_text='The particle between first and house name (e.g. "du"). PLACEHOLDER.',
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["realm", "family_type"],
                name="societies_particle_unique_per_realm_type",
            ),
        ]
        ordering = ["realm", "family_type"]

    def __str__(self) -> str:
        return f"{self.realm} {self.family_type}: '{self.particle}'"


class HouseRecognitionRule(SharedMemoryModel):
    """A realm's law for recognizing births into houses (#1884)."""

    realm = models.ForeignKey(
        _REALM_FK,
        on_delete=models.CASCADE,
        related_name="recognition_rules",
    )
    kind = models.CharField(max_length=30, choices=RecognitionRuleKind.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["realm", "kind"],
                name="societies_recognition_rule_unique",
            ),
        ]
        ordering = ["realm", "kind"]

    def __str__(self) -> str:
        return f"{self.realm}: {self.get_kind_display()}"


class FealtyEdge(SharedMemoryModel):
    """Vassal → liege edge in the realm tree (#1884). One liege per vassal."""

    vassal = models.OneToOneField(
        _ORG_FK,
        on_delete=models.CASCADE,
        related_name="fealty",
        help_text="The sworn house.",
    )
    liege = models.ForeignKey(
        _ORG_FK,
        on_delete=models.PROTECT,
        related_name="vassal_edges",
        help_text="The house fealty is sworn to.",
    )
    sworn_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["liege", "vassal"]

    def __str__(self) -> str:
        return f"{self.vassal} sworn to {self.liege}"


class SuccessionLaw(SharedMemoryModel):
    """How a house (or one title) passes: candidate derivation + ordering (#1884).

    Every realm case from the lore is one row: Umbral matrilineal
    recognition + Tanistry for the Imperial title; Luxen primogeniture-in-
    wedlock with enatic tiebreak; Inferna female-line with consort children
    ennobled; Ariwn chosen-heir; Lycan/Aythirmok most-powerful-Gifted of the
    legitimate.
    """

    name = models.CharField(max_length=120, unique=True)
    derivation = models.CharField(max_length=30, choices=SuccessionDerivation.choices)
    ordering_rule = models.CharField(
        max_length=30,
        choices=SuccessionOrdering.choices,
        default=SuccessionOrdering.ELDEST,
    )
    enatic_tiebreak = models.BooleanField(
        default=False,
        help_text="Prefer the mother's line in disputes (Luxen).",
    )
    require_wedlock = models.BooleanField(
        default=False,
        help_text="Only in-wedlock births qualify (reads born_within_union + kind wedlock).",
    )
    chosen_heir = models.ForeignKey(
        _KINSPERSON_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="CHOSEN_HEIR derivation: the named heir.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Title(SharedMemoryModel):
    """A landed/dynastic title (#1884): name, tier, realm, seat, holder.

    ``succession_law`` overrides the holding house's default (the Imperial
    Tanistry case). Vacant titles (holder null) with ``is_claimable`` are the
    house-creator's app-in targets (Phase D).
    """

    name = models.CharField(max_length=120, unique=True)
    tier = models.CharField(max_length=20, choices=TitleTier.choices)
    realm = models.ForeignKey(
        _REALM_FK,
        on_delete=models.PROTECT,
        related_name="titles",
    )
    house = models.ForeignKey(
        _ORG_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="titles",
        help_text="The house currently holding this title.",
    )
    holder = models.ForeignKey(
        _KINSPERSON_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="titles_held",
        help_text="The person holding the title (PC or NPC kinsperson node).",
    )
    seat_domain = models.ForeignKey(
        "societies.Domain",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="seat_of",
        help_text="The domain that is this title's seat, if any.",
    )
    succession_law = models.ForeignKey(
        SuccessionLaw,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="titles",
        help_text="Per-title override of the house's default law (Imperial Tanistry).",
    )
    is_claimable = models.BooleanField(
        default=False,
        help_text="Vacant slot set aside for the Phase D house creator.",
    )

    class Meta:
        ordering = ["realm", "tier", "name"]

    def __str__(self) -> str:
        return self.name


class Domain(SharedMemoryModel):
    """An org-owned landholding decorating a DOMAIN-level Area (#1884, #930 ruling).

    Abstract for now — civ stats + holdings feeding the org books; visitable
    room grids are a flagged later phase. Stats are PLACEHOLDER magnitudes.
    """

    area = models.OneToOneField(
        "areas.Area",
        on_delete=models.CASCADE,
        related_name="domain_profile",
        primary_key=True,
    )
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(
        blank=True,
        help_text="The lands, described — CG lands_writeup materializes here (#2079).",
    )
    owner_org = models.ForeignKey(
        _ORG_FK,
        on_delete=models.PROTECT,
        related_name="domains",
    )
    population = models.PositiveIntegerField(default=1000)
    prosperity = models.PositiveSmallIntegerField(default=50, help_text="0-100 PLACEHOLDER.")
    unrest = models.PositiveSmallIntegerField(default=10, help_text="0-100 PLACEHOLDER.")

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def income_multiplier(self) -> float:
        """How prosperity scales a holding's gross this cycle (#2238).

        A neutral 1.0 at ``DOMAIN_PROSPERITY_BASELINE``; a thriving domain
        over-yields, a struggling one under-yields, and a collapsed domain
        (prosperity 0) earns nothing. PLACEHOLDER curve — deliberately linear.

        An open crisis further scales this by its severity factor — the
        damaged-but-stable neutral state (#2238): the penalty holds while the
        crisis is open but never compounds on its own.
        """
        base = self.prosperity / DOMAIN_PROSPERITY_BASELINE
        open_crisis = self.crises.filter(resolved_at__isnull=True).first()
        if open_crisis is not None:
            base *= open_crisis.income_factor
        return base


class HoldingKind(SharedMemoryModel):
    """Authorable catalog of domain holdings (farmland, mine, port...) (#1884)."""

    name = models.CharField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    stream_kind = models.CharField(
        max_length=20,
        help_text="currency.IncomeStreamKind value the materialized stream uses.",
    )
    base_gross = models.PositiveBigIntegerField(
        help_text="Default coppers-per-cycle gross for a new holding. PLACEHOLDER.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class DomainHolding(SharedMemoryModel):
    """One holding on a domain, materialized as an OrgIncomeStream (#1884)."""

    domain = models.ForeignKey(
        Domain,
        on_delete=models.CASCADE,
        related_name="holdings",
    )
    kind = models.ForeignKey(
        HoldingKind,
        on_delete=models.PROTECT,
        related_name="holdings",
    )
    name = models.CharField(max_length=120)
    income_stream = models.OneToOneField(
        "currency.OrgIncomeStream",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="domain_holding",
        help_text="The materialized stream feeding the owner org's books.",
    )
    mine_quality = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Gem-mining lode quality (Build 0b): drives the weekly haul — raises the "
            "Rare-Find chance and shifts every axis roll up. 0 = not a gem mine. "
            "PLACEHOLDER magnitudes."
        ),
    )
    common_gem_tier = models.ForeignKey(
        "items.MaterialCategory",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text=(
            "The gem tier this mine's common bulk output is denominated in (a "
            "'semiprecious mine' vs a 'precious mine'). Required to accrue common value."
        ),
    )

    class Meta:
        ordering = ["domain", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.domain.name})"


class DomainImprovementDetails(SharedMemoryModel):
    """Per-(DOMAIN_IMPROVEMENT Project) payload (#1884).

    Long, difficult, expensive: completion raises the target stat or the
    holding's gross; the bottom outcome tiers open a ``DomainCrisis``
    instead — catastrophe is content, not just a debuff.
    """

    project = models.OneToOneField(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="domain_improvement_details",
        primary_key=True,
    )
    domain = models.ForeignKey(
        Domain,
        on_delete=models.CASCADE,
        related_name="improvement_details",
    )
    holding = models.ForeignKey(
        DomainHolding,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="improvement_details",
        help_text="Null = improves the domain's prosperity instead of one holding.",
    )
    gross_increase = models.PositiveBigIntegerField(
        default=0,
        help_text="Coppers/cycle added to the holding's stream on success. PLACEHOLDER.",
    )
    prosperity_increase = models.PositiveSmallIntegerField(
        default=0,
        help_text="Prosperity points added on success (domain-target projects).",
    )
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "Domain improvement details"

    def __str__(self) -> str:
        return f"Improvement of {self.domain_id} (project {self.project_id})"


class DomainCrisisType(SharedMemoryModel):
    """Authored crisis catalog row (#2238) — resolution is per-type, not global.

    A minor "protests" type can be paid off; an invasion type offers no gold
    option and must be defeated. ``automated=True`` rows are eligible for the
    system spawners (improvement failure / unrest boil-over); staff may attach
    any type by hand. Rows are PLACEHOLDER seeds pending the content pass.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(
        blank=True, help_text="PLACEHOLDER prose shown on the crisis card."
    )
    default_severity = models.CharField(
        max_length=20,
        choices=DomainCrisisSeverity.choices,
        default=DomainCrisisSeverity.TROUBLE,
    )
    automated = models.BooleanField(
        default=True,
        help_text="Eligible for system spawners (improvement failure / unrest boil-over).",
    )
    spawn_weight = models.PositiveSmallIntegerField(
        default=10, help_text="Relative weight among same-severity automated types."
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class DomainCrisisTypeOption(SharedMemoryModel):
    """One resolution option a crisis type offers (#2238). Columns per kind, no JSON.

    PAY: ``cost_coppers`` (severity-scaled at runtime). MISSION:
    ``mission_template`` (consumer-side FK, ADR-0010). WAIT: the chosen-ignore
    option — ``self_resolve_pct`` / ``worsen_pct`` roll weekly ONLY once chosen.
    """

    crisis_type = models.ForeignKey(
        DomainCrisisType, on_delete=models.CASCADE, related_name="options"
    )
    kind = models.CharField(max_length=20, choices=CrisisResolutionKind.choices)
    cost_coppers = models.PositiveBigIntegerField(
        default=0, help_text="PAY only: base cost, scaled by severity at runtime. PLACEHOLDER."
    )
    mission_template = models.ForeignKey(
        "missions.MissionTemplate",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="crisis_options",
        help_text="MISSION only: the org-scoped mission this option mints.",
    )
    self_resolve_pct = models.PositiveSmallIntegerField(
        default=0, help_text="WAIT only: weekly %% chance it blows over. PLACEHOLDER."
    )
    worsen_pct = models.PositiveSmallIntegerField(
        default=0, help_text="WAIT only: weekly %% chance severity bumps. PLACEHOLDER."
    )

    class Meta:
        ordering = ["crisis_type", "kind"]
        constraints = [
            models.UniqueConstraint(
                fields=["crisis_type", "kind"], name="unique_option_kind_per_crisis_type"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(kind="mission", mission_template__isnull=False)
                    | ~models.Q(kind="mission")
                ),
                name="crisis_option_mission_requires_template",
            ),
        ]

    def clean(self) -> None:
        from django.core.exceptions import ValidationError  # noqa: PLC0415

        if self.kind == CrisisResolutionKind.MISSION and self.mission_template_id is None:
            msg = "MISSION options require a mission_template."
            raise ValidationError(msg)
        if self.kind != CrisisResolutionKind.MISSION and self.mission_template_id is not None:
            msg = "Only MISSION options may carry a mission_template."
            raise ValidationError(msg)

    def __str__(self) -> str:
        return f"{self.crisis_type.name}: {self.get_kind_display()}"


class DomainCrisis(SharedMemoryModel):
    """A crisis opened on a domain (#1884) — content, not just a debuff.

    Opened by catastrophic improvement outcomes (or staff); surfaces on the
    house feed with response hooks; conversion into missions/situations is
    the GM's move (situations need room anchors; domains are abstract).
    """

    domain = models.ForeignKey(
        Domain,
        on_delete=models.CASCADE,
        related_name="crises",
    )
    severity = models.CharField(
        max_length=20,
        choices=DomainCrisisSeverity.choices,
        default=DomainCrisisSeverity.CRISIS,
    )
    description = models.TextField(
        blank=True,
        help_text="PLACEHOLDER prose describing what went wrong.",
    )
    crisis_type = models.ForeignKey(
        DomainCrisisType,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="crises",
        help_text="Null = staff freeform (no options; GM resolves by hand).",
    )
    origin = models.CharField(
        max_length=20,
        choices=CrisisOrigin.choices,
        default=CrisisOrigin.STAFF,
    )
    chosen_option = models.ForeignKey(
        DomainCrisisTypeOption,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="chosen_on",
        help_text="The administrator's judgment call. WAIT only rolls once chosen (#2238).",
    )
    chosen_at = models.DateTimeField(null=True, blank=True)
    minted_mission = models.ForeignKey(
        "missions.MissionInstance",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="source_crisis",
        help_text="The org-scoped mission this crisis minted, when a MISSION path is live.",
    )
    resolution = models.CharField(
        max_length=30, choices=CrisisResolution.choices, blank=True, default=""
    )
    opened_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-opened_at"]
        verbose_name_plural = "Domain crises"

    def __str__(self) -> str:
        return f"{self.get_severity_display()} on {self.domain.name}"

    @property
    def income_factor(self) -> float:
        """Severity-scaled income malus while open (#2238). 1.0 once resolved."""
        if self.resolved_at is not None:
            return 1.0
        return CRISIS_INCOME_FACTORS.get(self.severity, 1.0)


class MarriagePact(SharedMemoryModel):
    """A union-bound alliance between a senior and junior house (#1884).

    CK2 rule: bound to the LIVING union — a spouse dies, the pact dissolves
    that instant (explicit service call from the lifecycle setter, never a
    signal). The junior party takes the senior's name and house; the senior
    house owes the coded commitments. PCs are all Gifted — the pact's core
    asset is the person.
    """

    union = models.OneToOneField(
        "roster.Union",
        on_delete=models.PROTECT,
        related_name="marriage_pact",
    )
    senior_house = models.ForeignKey(
        _ORG_FK,
        on_delete=models.PROTECT,
        related_name="pacts_as_senior",
    )
    junior_house = models.ForeignKey(
        _ORG_FK,
        on_delete=models.PROTECT,
        related_name="pacts_as_junior",
    )
    signed_at = models.DateTimeField(auto_now_add=True)
    dissolved_at = models.DateTimeField(null=True, blank=True)
    dissolution_reason = models.CharField(
        max_length=20,
        choices=PactDissolutionReason.choices,
        blank=True,
    )

    class Meta:
        ordering = ["-signed_at"]

    def __str__(self) -> str:
        state = "dissolved" if self.dissolved_at else "standing"
        return f"Pact {self.senior_house} ↔ {self.junior_house} ({state})"


class PactCommitment(SharedMemoryModel):
    """One coded commitment on a pact (#1884). Fires mechanically; breach is
    scandalous (fame/reputation hit + public tiding)."""

    pact = models.ForeignKey(
        MarriagePact,
        on_delete=models.CASCADE,
        related_name="commitments",
    )
    kind = models.CharField(max_length=20, choices=PactCommitmentKind.choices)
    owed_by_senior = models.BooleanField(
        default=True,
        help_text="Whether the senior house owes this (dowries/subsidies usually do).",
    )
    committed_person = models.ForeignKey(
        _KINSPERSON_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pact_commitments",
        help_text="The named Gifted for CRISIS_RESPONSE/RESIDENCY commitments.",
    )
    amount = models.PositiveBigIntegerField(
        default=0,
        help_text="Coppers: dowry lump (DOWRY kind). PLACEHOLDER.",
    )
    percent = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "SUBSIDY kind: percent of declared income owed per settlement "
            "(materialized as the OrgObligation's percent). PLACEHOLDER."
        ),
    )
    obligation = models.OneToOneField(
        "currency.OrgObligation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pact_commitment",
        help_text="The materialized recurring obligation (SUBSIDY kind).",
    )
    notes = models.TextField(blank=True, help_text="CUSTOM commitments: the prose terms.")
    breached_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["pact", "kind"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} on pact {self.pact_id}"


class HouseTemplate(SharedMemoryModel):
    """A realm's recipe for CG-defined houses on set-aside titles (#1884 Phase D).

    The claimable ``Title`` is the slot; the template carries the automated
    thematic gates (name pattern per the realm's naming conventions,
    principle ranges) and the materialization package (society, liege,
    succession law, holdings, starting kin slots). Numbers are PLACEHOLDER.
    """

    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    realm = models.ForeignKey(
        _REALM_FK,
        on_delete=models.CASCADE,
        related_name="house_templates",
    )
    family_type = models.CharField(
        max_length=20,
        help_text="roster.Family.FamilyType the defined family gets.",
    )
    society = models.ForeignKey(
        "societies.Society",
        on_delete=models.PROTECT,
        related_name="house_templates",
        help_text="The society the materialized org joins.",
    )
    liege = models.ForeignKey(
        _ORG_FK,
        on_delete=models.PROTECT,
        related_name="house_templates",
        help_text="The org the new house swears fealty to.",
    )
    default_succession_law = models.ForeignKey(
        SuccessionLaw,
        on_delete=models.PROTECT,
        related_name="house_templates",
    )
    name_pattern = models.CharField(
        max_length=200,
        default=r"[A-Z][a-z]{2,19}",
        help_text=(
            "Full-match regex the proposed house name must satisfy — the "
            "realm's naming conventions as an automated gate. PLACEHOLDER."
        ),
    )
    mercy_min = models.SmallIntegerField(default=-5)
    mercy_max = models.SmallIntegerField(default=5)
    method_min = models.SmallIntegerField(default=-5)
    method_max = models.SmallIntegerField(default=5)
    status_min = models.SmallIntegerField(default=-5)
    status_max = models.SmallIntegerField(default=5)
    change_min = models.SmallIntegerField(default=-5)
    change_max = models.SmallIntegerField(default=5)
    allegiance_min = models.SmallIntegerField(default=-5)
    allegiance_max = models.SmallIntegerField(default=5)
    power_min = models.SmallIntegerField(default=-5)
    power_max = models.SmallIntegerField(default=5)
    holdings = models.ManyToManyField(
        HoldingKind,
        blank=True,
        related_name="house_templates",
        help_text="Holdings materialized on the title's seat domain at finalization.",
    )
    starting_kin_slots = models.PositiveSmallIntegerField(
        default=3,
        help_text="KinSlotPool capacity minted for the new family. PLACEHOLDER.",
    )
    aspect_definitions = models.ManyToManyField(
        "societies.HouseAspectDefinition",
        blank=True,
        related_name="templates",
        help_text="Required catalog choices for claims on this template (#2079).",
    )
    features = models.ManyToManyField(
        "societies.HouseFeature",
        blank=True,
        related_name="templates",
        help_text="Cultural facts stamped on materialized houses (#2079).",
    )

    class Meta:
        ordering = ["realm", "name"]

    def __str__(self) -> str:
        return self.name


class HouseClaim(SharedMemoryModel):
    """A CG application defining the house behind a claimable title (#1884 Phase D).

    CG-only by design (Apostate ruling): the character enters play as a
    representative of a house that has always existed in fiction — founding
    a brand-new house in play is a separate future loop. Rides the
    ``CharacterDraft`` (dies with it, like the other Draft-scoped rows);
    staff review happens in admin; the approved claim materializes at CG
    finalization so an abandoned application never leaves a ghost house.
    """

    draft = models.OneToOneField(
        "character_creation.CharacterDraft",
        on_delete=models.CASCADE,
        related_name="house_claim",
    )
    title = models.ForeignKey(
        Title,
        on_delete=models.CASCADE,
        related_name="claims",
        help_text="The vacant claimable title this house is defined behind.",
    )
    template = models.ForeignKey(
        HouseTemplate,
        on_delete=models.CASCADE,
        related_name="claims",
    )
    house_name = models.CharField(
        max_length=100,
        help_text='The family name (org renders "House <name>" for nobles).',
    )
    backstory = models.TextField(
        help_text="The thematic pitch staff reviews — the house as it has always been.",
    )
    words = models.CharField(max_length=200, default="", help_text="House words / motto (#2079).")
    colors = models.CharField(max_length=200, default="", help_text="House colors, prose (#2079).")
    sigil_description = models.TextField(default="", help_text="The sigil, described (#2079).")
    lands_writeup = models.TextField(
        blank=True,
        help_text="The seat domain's lands, described (required for landed titles, #2079).",
    )
    mercy = models.SmallIntegerField(default=0)
    method = models.SmallIntegerField(default=0)
    status_principle = models.SmallIntegerField(default=0)
    change = models.SmallIntegerField(default=0)
    allegiance = models.SmallIntegerField(default=0)
    power = models.SmallIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=HouseClaimStatus.choices,
        default=HouseClaimStatus.PENDING,
    )
    reviewed_by = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"House {self.house_name} claim ({self.get_status_display()})"


class HouseAspectDefinition(SharedMemoryModel):
    """An authored, required catalog choice for houses of a template (#2079).

    Catalog-only by design: there is no free-text answer path. The normalized
    option list IS the thematic fence (see ADR-0101). Attach to templates via
    ``HouseTemplate.aspect_definitions``; a definition shared by two templates
    shares one catalog — a diverged catalog means a second definition.
    """

    name = models.CharField(max_length=120, unique=True)
    prompt = models.TextField(
        help_text="Player-facing question the founder answers by picking options."
    )
    min_picks = models.PositiveSmallIntegerField(default=1)
    max_picks = models.PositiveSmallIntegerField(default=1)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self) -> str:
        return self.name


class HouseAspectOption(SharedMemoryModel):
    """One authored answer in a definition's catalog (#2079). PLACEHOLDER content."""

    definition = models.ForeignKey(
        HouseAspectDefinition, on_delete=models.CASCADE, related_name="options"
    )
    name = models.CharField(max_length=120)
    description = models.TextField(
        blank=True, help_text="Player-facing blurb shown on the option card."
    )
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["definition", "display_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["definition", "name"], name="unique_option_name_per_definition"
            )
        ]

    def __str__(self) -> str:
        return f"{self.definition.name}: {self.name}"


class HouseFeature(SharedMemoryModel):
    """A structural cultural fact about houses of a template (#2079).

    No player input — features orient the founder at CG ("this is how a house
    like yours conducts itself") and anchor future systems: a ledger UI checks
    the org has the feature slug ``black-ledger``, never a bespoke code path.
    """

    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=60, unique=True, help_text="Stable code anchor.")
    description = models.TextField(help_text="Player-facing: how this shapes play.")
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self) -> str:
        return self.name


class HouseClaimAspect(SharedMemoryModel):
    """One picked option on a CG house claim (#2079)."""

    claim = models.ForeignKey(HouseClaim, on_delete=models.CASCADE, related_name="aspects")
    definition = models.ForeignKey(
        HouseAspectDefinition, on_delete=models.PROTECT, related_name="+"
    )
    option = models.ForeignKey(HouseAspectOption, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["claim", "definition", "option"]
        constraints = [
            models.UniqueConstraint(fields=["claim", "option"], name="unique_claim_option")
        ]

    def __str__(self) -> str:
        return f"claim {self.claim_id}: {self.option}"


class OrganizationAspect(SharedMemoryModel):
    """A house's permanent identity facet (#2079).

    Written at claim materialization; also directly authorable so staff-seeded
    houses carry facets without a claim.
    """

    organization = models.ForeignKey(
        "societies.Organization", on_delete=models.CASCADE, related_name="aspects"
    )
    definition = models.ForeignKey(
        HouseAspectDefinition, on_delete=models.PROTECT, related_name="+"
    )
    option = models.ForeignKey(HouseAspectOption, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["organization", "definition", "option"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "option"], name="unique_org_option")
        ]

    def __str__(self) -> str:
        return f"{self.organization}: {self.option}"


class OrganizationFeature(SharedMemoryModel):
    """A cultural feature stamped on a house org (#2079)."""

    organization = models.ForeignKey(
        "societies.Organization", on_delete=models.CASCADE, related_name="features"
    )
    feature = models.ForeignKey(
        HouseFeature, on_delete=models.PROTECT, related_name="organization_features"
    )

    class Meta:
        ordering = ["organization", "feature"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "feature"], name="unique_org_feature")
        ]

    def __str__(self) -> str:
        return f"{self.organization}: {self.feature}"
