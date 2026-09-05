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

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.contributors.models import CreditedContent
from world.currency.constants import IncomeStreamKind
from world.items.constants import MaterialSourceKind
from world.societies.houses.constants import (
    CRISIS_INCOME_FACTORS,
    DOMAIN_PROSPERITY_BASELINE,
    CrisisAudience,
    CrisisIntelSource,
    CrisisOrigin,
    CrisisResolution,
    CrisisResolutionKind,
    CrisisValence,
    DomainCrisisSeverity,
    HouseClaimStatus,
    OrgPactDissolutionReason,
    PactCommitmentKind,
    PactDissolutionReason,
    RecognitionRuleKind,
    StatureShiftCause,
    SuccessionDerivation,
    SuccessionOrdering,
    TitleTier,
)

_ORG_FK = "arxii.Organization"
_KINSPERSON_FK = "arxii.Kinsperson"
_REALM_FK = "arxii.Realm"
_PERSONA_FK = "arxii.Persona"


class NobiliaryParticle(SharedMemoryModel):
    """Per-realm × family-type × tier-band nobiliary particle (#1884, #3261).

    Canon vocabulary ratified 2026-08-17 (seeded in ``world.seeds.houses``).
    Derived names render ``first + particle + house_name`` for born/founding
    members and ``first + taken_in_particle + house_name`` for everyone who
    entered the name another way (married, adopted, legitimized, granted).
    ``tier_floor`` bands a realm's particles by the house's highest held
    title (Luxen: ``du`` at duchy+, attached ``D'`` below); the blank-floor
    row is the realm's default band. A realm with no rows (Arx) renders bare
    names — absence is its signature. A particle ending in ``'`` joins the
    house name with no space ("Sybel D'Regente").
    """

    realm = models.ForeignKey(
        _REALM_FK,
        on_delete=models.CASCADE,
        related_name="nobiliary_particles",
    )
    kind = models.ForeignKey(
        "arxii.FamilyKind",
        on_delete=models.PROTECT,
        related_name="particles",
        help_text="The family kind this particle applies to (#3617).",
    )
    tier_floor = models.CharField(
        max_length=20,
        choices=TitleTier.choices,
        blank=True,
        default="",
        help_text=(
            "Lowest TitleTier this band covers (#3261): the row applies when "
            "the house's highest held title ranks at or above this floor. "
            "Blank = the realm's default band."
        ),
    )
    particle = models.CharField(
        max_length=20,
        help_text='Born/founding-member form between first and house name (e.g. "du").',
    )
    taken_in_particle = models.CharField(
        max_length=20,
        blank=True,
        help_text=(
            "Taken-in form (#3261, widened from the #3091 spouse form): worn by "
            "every non-born member — married-in, adopted, legitimized, granted "
            '("dau", "vosk"). Blank = fall back to the born form.'
        ),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["realm", "kind", "tier_floor"],
                name="societies_particle_unique_per_realm_type_band",
            ),
        ]
        ordering = ["realm", "kind", "tier_floor"]

    def __str__(self) -> str:
        band = f" ({self.tier_floor}+)" if self.tier_floor else ""
        return f"{self.realm} {self.kind}{band}: '{self.particle}'"


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


class SuccessionLaw(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """How a house (or one title) passes: candidate derivation + ordering (#1884).

    Every realm case from the lore is one row: Umbral matrilineal
    recognition + Tanistry for the Imperial title; Luxen primogeniture-in-
    wedlock with enatic tiebreak; Inferna female-line with consort children
    ennobled; Ariwn chosen-heir; Lycan/Aythirmok most-powerful-Gifted of the
    legitimate.

    Authored content (#2875): the house charter's succession vocabulary is
    the lore repo's to write, so it carries a natural key and is registered
    in ``CONTENT_MODELS``. ``description`` is the writer's field: the prose a
    charter author sets to explain how this law shapes inheritance, and what
    the backlog/Workbench (`web/admin/authoring`) tracks credit against.
    """

    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(
        blank=True, help_text="Player-facing: how this law shapes inheritance."
    )
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

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

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
        "arxii.Domain",
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
    # #3261 styled-degree personal styles ("Queen Sharlotte…"). Authorable per
    # title row; blank falls back to DEFAULT_TIER_STYLES for the tier.
    holder_style_male = models.CharField(
        max_length=60,
        blank=True,
        help_text='Personal style for a male holder (e.g. "King"). Blank = tier default.',
    )
    holder_style_female = models.CharField(
        max_length=60,
        blank=True,
        help_text='Personal style for a female holder (e.g. "Queen"). Blank = tier default.',
    )
    holder_style_neutral = models.CharField(
        max_length=60,
        blank=True,
        help_text=(
            'Personal style for any other/unset gender (e.g. "Monarch"). Blank = tier default.'
        ),
    )

    class Meta:
        ordering = ["realm", "tier", "name"]

    def __str__(self) -> str:
        return self.name


class Domain(SharedMemoryModel):
    """An org-owned landholding decorating an Area (seeds use ``AreaLevel.REGION``;
    no DOMAIN level exists) (#1884, #930 ruling).

    Abstract for now — civ stats + holdings feeding the org books; visitable
    room grids are a flagged later phase. Stats are PLACEHOLDER magnitudes.
    """

    area = models.OneToOneField(
        "arxii.Area",
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


class HoldingKind(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """Authorable catalog of domain holdings (farmland, mine, port...) (#1884).

    Authored content (#2875): part of the house charter, so it carries a
    natural key and is registered in ``CONTENT_MODELS``.
    """

    name = models.CharField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    stream_kind = models.CharField(
        max_length=20,
        choices=IncomeStreamKind.choices,
        help_text="currency.IncomeStreamKind value the materialized stream uses.",
    )
    base_gross = models.PositiveBigIntegerField(
        help_text="Default coppers-per-cycle gross for a new holding. PLACEHOLDER.",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

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
        "arxii.OrgIncomeStream",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="domain_holding",
        help_text="The materialized stream feeding the owner org's books.",
    )

    class Meta:
        ordering = ["domain", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.domain.name})"


class HoldingMaterialSource(SharedMemoryModel):
    """One material-producing source on a holding (#2540 slice 2).

    Replaces ``DomainHolding.mine_quality``/``common_gem_tier`` with a proper row so a
    holding can carry more than one production source and so non-gem bulk yields (farms,
    quarries, etc.) share the same shape as a gem mine. ``source_kind`` distinguishes a
    gem mine (rolls rare finds alongside flat value) from a plain bulk yield (flat value
    only); ``quality`` drives the magnitude of the weekly haul.
    """

    holding = models.ForeignKey(
        DomainHolding,
        on_delete=models.CASCADE,
        related_name="material_sources",
    )
    material_category = models.ForeignKey(
        "arxii.MaterialCategory",
        on_delete=models.PROTECT,
        related_name="+",
    )
    quality = models.PositiveSmallIntegerField(
        default=1,
        help_text="Production strength. PLACEHOLDER magnitudes.",
    )
    source_kind = models.CharField(
        max_length=20,
        choices=MaterialSourceKind.choices,
        default=MaterialSourceKind.BULK,
    )

    class Meta:
        ordering = ["holding_id", "material_category_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["holding", "material_category"],
                name="houses_holdingmaterialsource_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.holding_id} {self.material_category}: {self.get_source_kind_display()}"


class DomainImprovementDetails(SharedMemoryModel):
    """Per-(DOMAIN_IMPROVEMENT Project) payload (#1884).

    Long, difficult, expensive: completion raises the target stat or the
    holding's gross; the bottom outcome tiers open a ``DomainCrisis``
    instead — catastrophe is content, not just a debuff.
    """

    project = models.OneToOneField(
        "arxii.Project",
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


class EdictKind(SharedMemoryModel):
    """Authored standing-policy catalog for domains (#2842) — PLACEHOLDER rows.

    Each kind carries its inherent stance (enacting it IS proclaiming that
    philosophy — the social bill) plus the mechanical payload (the bite).
    Military knobs wait on positional troop state.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    stance = models.ForeignKey(
        "arxii.StanceArchetype",
        on_delete=models.PROTECT,
        related_name="edict_kinds",
        help_text="The philosophy this policy embodies; proclaimed at enactment.",
    )
    income_gross_pct = models.SmallIntegerField(
        default=0,
        help_text="Percent adjustment to the domain's stream gross at weekly accrual. PLACEHOLDER.",
    )
    weekly_unrest_delta = models.SmallIntegerField(
        default=0,
        help_text="Unrest applied each weekly tick while active (clamped 0-100). PLACEHOLDER.",
    )
    weekly_upkeep_coppers = models.PositiveIntegerField(
        default=0,
        help_text="Treasury drain per weekly tick while active (skipped if broke). PLACEHOLDER.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class DomainEdict(SharedMemoryModel):
    """A standing policy enacted on a domain (#2842). One active per domain.

    Enactment issues the kind's stance as a Proclamation (the social bill);
    this row is the mechanical residue the weekly tick and stream accrual
    read — and what a rival's domain report can see.
    """

    domain = models.ForeignKey(
        Domain,
        on_delete=models.CASCADE,
        related_name="edicts",
    )
    kind = models.ForeignKey(
        EdictKind,
        on_delete=models.PROTECT,
        related_name="enactments",
    )
    proclamation = models.ForeignKey(
        "arxii.Proclamation",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="edicts",
        help_text="The proclaiming act that enacted this policy.",
    )
    enacted_by = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.CASCADE,
        related_name="edicts_enacted",
    )
    enacted_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-enacted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["domain"],
                condition=models.Q(revoked_at__isnull=True),
                name="one_active_edict_per_domain",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind.name} in {self.domain.name}"


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
    valence = models.CharField(
        max_length=20,
        choices=CrisisValence.choices,
        default=CrisisValence.THREAT,
        help_text="Threats bite the target; opportunities pay whoever seizes them (#2837).",
    )
    audience = models.CharField(
        max_length=20,
        choices=CrisisAudience.choices,
        default=CrisisAudience.DOMAIN,
        help_text="What this type spawns against; criminal flavor is content, not code (#2837).",
    )
    ignores_stature = models.BooleanField(
        default=False,
        help_text=(
            "Affliction-class types (#3093): spawn odds NEVER scale by the "
            "target's stature band — deterrence means nothing to the dead."
        ),
    )
    affliction_spreads = models.BooleanField(
        default=False,
        help_text=(
            "While unresolved, weekly chance to open a sibling outbreak one "
            "domain over (same realm), capped per root (#3093)."
        ),
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
        "arxii.MissionTemplate",
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
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="crises",
    )
    # One machinery, two fictions (the CRIME_KICKUP precedent): the same row
    # is a crisis on a house's lands OR on the organization itself (#2837).
    org = models.ForeignKey(
        _ORG_FK,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="org_crises",
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
        "arxii.MissionInstance",
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
    surfaces_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Generated crises stay covert until this moment; null = public from"
            " the start. Spy sweeps mint CrisisIntel to see through the window (#2837)."
        ),
    )
    aggressor_band = models.ForeignKey(
        "arxii.PredatorBand",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="authored_crises",
        help_text="The predator band behind this crisis, when one is (#3093).",
    )
    spread_count = models.PositiveSmallIntegerField(
        default=0,
        help_text="Sibling outbreaks already spawned from THIS root (Affliction spread cap).",
    )

    class Meta:
        ordering = ["-opened_at"]
        verbose_name_plural = "Domain crises"
        constraints = [
            models.CheckConstraint(
                condition=(
                    (models.Q(domain__isnull=False) & models.Q(org__isnull=True))
                    | (models.Q(domain__isnull=True) & models.Q(org__isnull=False))
                ),
                name="crisis_targets_exactly_one_of_domain_or_org",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_severity_display()} on {self.target_label}"

    @property
    def target_label(self) -> str:
        return self.domain.name if self.domain_id is not None else self.org.name

    @property
    def target_org(self):
        """The organization whose problem (or windfall) this is."""
        return self.domain.owner_org if self.domain_id is not None else self.org

    @property
    def valence(self) -> str:
        """Typeless (staff freeform) crises are threats."""
        return self.crisis_type.valence if self.crisis_type_id is not None else CrisisValence.THREAT

    @property
    def is_surfaced(self) -> bool:
        from django.utils import timezone  # noqa: PLC0415

        return self.surfaces_at is None or self.surfaces_at <= timezone.now()

    @property
    def income_factor(self) -> float:
        """Severity-scaled income malus while open (#2238). 1.0 once resolved.

        Opportunities never bite (#2837), and a still-covert threat has not
        yet hit the books.
        """
        if self.resolved_at is not None or not self.is_surfaced:
            return 1.0
        if self.valence == CrisisValence.OPPORTUNITY:
            return 1.0
        return CRISIS_INCOME_FACTORS.get(self.severity, 1.0)


class CrisisIntel(SharedMemoryModel):
    """An organization's early knowledge of a still-covert crisis (#2837).

    Minted by spy sweeps (or staff). Your own spymaster buys reaction time;
    sweeping a rival reveals their hidden troubles to exploit. Rows persist
    after surfacing as a record of who knew first.
    """

    crisis = models.ForeignKey(DomainCrisis, on_delete=models.CASCADE, related_name="intel")
    org = models.ForeignKey(_ORG_FK, on_delete=models.CASCADE, related_name="crisis_intel")
    source = models.CharField(
        max_length=20,
        choices=CrisisIntelSource.choices,
        default=CrisisIntelSource.SPY_SWEEP,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["crisis", "org"], name="unique_intel_per_crisis_org"),
        ]

    def __str__(self) -> str:
        return f"{self.org.name} knows of {self.crisis}"


class MarriagePact(SharedMemoryModel):
    """A union-bound alliance between a senior and junior house (#1884).

    CK2 rule: bound to the LIVING union — a spouse dies, the pact dissolves
    that instant (explicit service call from the lifecycle setter, never a
    signal). The junior party takes the senior's name and house; the senior
    house owes the coded commitments. PCs are all Gifted — the pact's core
    asset is the person.
    """

    union = models.OneToOneField(
        "arxii.Union",
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
        "arxii.OrgObligation",
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


class HouseTemplate(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """A realm's recipe for CG-defined houses on set-aside titles (#1884 Phase D).

    The claimable ``Title`` is the slot; the template carries the automated
    thematic gates (name pattern per the realm's naming conventions,
    principle ranges) and the materialization package (society, liege,
    succession law, holdings, starting kin slots). Numbers are PLACEHOLDER.

    Authored content (#2875): part of the house charter, so it carries a
    natural key and is registered in ``CONTENT_MODELS``.
    """

    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    realm = models.ForeignKey(
        _REALM_FK,
        on_delete=models.CASCADE,
        related_name="house_templates",
    )
    kind = models.ForeignKey(
        "arxii.FamilyKind",
        on_delete=models.PROTECT,
        related_name="house_templates",
        help_text="The kind the defined family gets (#3617).",
    )
    society = models.ForeignKey(
        "arxii.Society",
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
        "arxii.HouseAspectDefinition",
        blank=True,
        related_name="templates",
        help_text="Required catalog choices for claims on this template (#2079).",
    )
    features = models.ManyToManyField(
        "arxii.HouseFeature",
        blank=True,
        related_name="templates",
        help_text="Cultural facts stamped on materialized houses (#2079).",
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

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
        "arxii.CharacterDraft",
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


class HouseAspectDefinition(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """An authored, required catalog choice for houses of a template (#2079).

    Catalog-only by design: there is no free-text answer path. The normalized
    option list IS the thematic fence (see ADR-0101). Attach to templates via
    ``HouseTemplate.aspect_definitions``; a definition shared by two templates
    shares one catalog — a diverged catalog means a second definition.

    Authored content (#2868): the definition and its options are the lore
    repo's to write, so both carry a natural key and are registered in
    ``CONTENT_MODELS``. The seeder may no longer invent them.
    """

    name = models.CharField(max_length=120, unique=True)
    prompt = models.TextField(
        help_text="Player-facing question the founder answers by picking options."
    )
    min_picks = models.PositiveSmallIntegerField(default=1)
    max_picks = models.PositiveSmallIntegerField(default=1)
    display_order = models.PositiveSmallIntegerField(default=0)

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self) -> str:
        return self.name


class HouseAspectOption(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """One authored answer in a definition's catalog (#2079).

    Inferna's seven House Quiddities are options on one definition. Each is a
    piece of authored lore in its own right, so an option may bind the
    ``CodexEntry`` that carries its write-up — the same shape as
    ``Species.codex_entry`` (#2868). The link is a property of the catalog row,
    NOT a grant: picking a Quiddity for your house does not award the entry to
    a character, which is what the ``*CodexGrant`` models are for.
    """

    definition = models.ForeignKey(
        HouseAspectDefinition, on_delete=models.CASCADE, related_name="options"
    )
    name = models.CharField(max_length=120)
    description = models.TextField(
        blank=True, help_text="Player-facing blurb shown on the option card."
    )
    codex_entry = models.ForeignKey(
        "arxii.CodexEntry",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="house_aspect_options",
        help_text="Lore entry this option is bound to, if any.",
    )
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["definition", "name"]
        dependencies = ["arxii.HouseAspectDefinition"]

    class Meta:
        ordering = ["definition", "display_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["definition", "name"], name="unique_option_name_per_definition"
            )
        ]

    def __str__(self) -> str:
        return f"{self.definition.name}: {self.name}"


class HouseFeature(NaturalKeyMixin, CreditedContent, SharedMemoryModel):
    """A structural cultural fact about houses of a template (#2079).

    No player input - features orient the founder at CG ("this is how a house
    like yours conducts itself") and anchor future systems: a ledger UI checks
    the org has the feature slug ``black-ledger``, never a bespoke code path.

    Authored content (#2875): part of the house charter, so it carries a
    natural key and is registered in ``CONTENT_MODELS``. The natural key is
    ``name``, not ``slug`` (the content convention every other charter model
    follows) - ``slug`` stays the stable code anchor a future system keys off
    (e.g. ``org.features`` carrying ``black-ledger``), a separate concern from
    the identity the export/import round trip resolves rows by.
    """

    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=60, unique=True, help_text="Stable code anchor.")
    description = models.TextField(help_text="Player-facing: how this shapes play.")
    display_order = models.PositiveSmallIntegerField(default=0)

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

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

    organization = models.ForeignKey(_ORG_FK, on_delete=models.CASCADE, related_name="aspects")
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

    organization = models.ForeignKey(_ORG_FK, on_delete=models.CASCADE, related_name="features")
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


# ---------------------------------------------------------------------------
# House Stature (#3091) — perceived-vs-true deterrence spine
# ---------------------------------------------------------------------------


class StatureBand(NaturalKeyMixin, SharedMemoryModel):
    """Authored qualitative stature tier (#3091): Unassailable ... Imperiled.

    Assigned by percentile within a (continent x org-category) cohort of
    landed orgs. Supplies the org page's qualitative headline and the
    predation multiplier ambient crisis generation reads. PLACEHOLDER prose
    on seeds; admin-editable at content time.
    """

    name = models.CharField(max_length=40, unique=True)
    rank = models.PositiveSmallIntegerField(
        help_text="1 = highest band; bands are ordered, not overlapping.",
    )
    min_percentile = models.PositiveSmallIntegerField(
        help_text="Lowest cohort percentile (0-100) that earns this band.",
    )
    threat_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1,
        help_text=(
            "Ambient threat chance is scaled by this for orgs in this band — "
            "weak-looking houses get probed harder (#3091 predation)."
        ),
    )
    headline_template = models.TextField(
        blank=True,
        help_text=(
            "Qualitative headline for the org page; '{org}' interpolates the "
            "org name. PLACEHOLDER prose pending the tuning pass."
        ),
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["rank"]

    def __str__(self) -> str:
        return f"{self.name} (band {self.rank})"


class HouseStature(SharedMemoryModel):
    """A landed org's true vs perceived strength (#3091).

    True side recomputes weekly (renown + military + economic + allied -
    crisis penalty, per-component weights in constants). Perceived converges
    toward true with lag; shocks (deaths, pact changes, surfaced crises,
    whisper campaigns) move it immediately. Bands are cohort percentiles.
    """

    organization = models.OneToOneField(
        _ORG_FK,
        on_delete=models.CASCADE,
        related_name="stature",
    )
    renown_strength = models.IntegerField(default=0)
    military_strength = models.IntegerField(default=0)
    economic_strength = models.IntegerField(default=0)
    allied_strength = models.IntegerField(default=0)
    crisis_penalty = models.IntegerField(
        default=0,
        help_text="Deduction from open threats (blood in the water); cleared on resolve.",
    )
    true_total = models.IntegerField(default=0)
    perceived_total = models.IntegerField(
        default=0,
        help_text="What the world believes; converges toward true_total weekly.",
    )
    band = models.ForeignKey(
        StatureBand,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_orgs",
    )
    previous_band = models.ForeignKey(
        StatureBand,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Band before the last assignment — drives the trend display.",
    )
    prestige_rank = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="1-based rank among ALL orgs by prestige standing (#3091, rank-relative).",
    )
    realm_rank = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="1-based perceived-stature rank among the realm's landed polities.",
    )
    realm_cohort_size = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="How many landed polities the realm rank compares against.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-perceived_total"]

    def __str__(self) -> str:
        return f"{self.organization}: {self.perceived_total} perceived / {self.true_total} true"


class StatureShift(SharedMemoryModel):
    """Why a house's stature moved (#3091) — display history + tidings source."""

    organization = models.ForeignKey(
        _ORG_FK,
        on_delete=models.CASCADE,
        related_name="stature_shifts",
    )
    cause = models.CharField(max_length=20, choices=StatureShiftCause.choices)
    delta_true = models.IntegerField(default=0)
    delta_perceived = models.IntegerField(default=0)
    subject_kinsperson = models.ForeignKey(
        _KINSPERSON_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="The person whose death/marriage moved the number, when one did.",
    )
    subject_persona = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.organization} {self.cause}: {self.delta_perceived:+d} perceived"


class PrestigeRankBand(NaturalKeyMixin, SharedMemoryModel):
    """Authored rank-relative prestige benefit tier (#3091).

    Benefits key on RANK, never raw prestige (being #1 matters identically at
    twenty thousand or a billion). Shape per ruling: declining scale across
    the top 100, minimal 101-1000, penalties for negative prestige scaled by
    how negative (negative_only rows).
    """

    class Scope(models.TextChoices):
        ORG = "org", "Organization"
        PERSONA = "persona", "Persona"

    name = models.CharField(max_length=60, unique=True)
    scope = models.CharField(max_length=10, choices=Scope.choices, default=Scope.ORG)
    min_rank = models.PositiveIntegerField(
        help_text="Best (lowest) 1-based rank this band covers.",
    )
    max_rank = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Worst rank covered; null = everything below min_rank.",
    )
    negative_only = models.BooleanField(
        default=False,
        help_text="Applies only to holders of NEGATIVE prestige (rank is ignored).",
    )
    prosperity_bonus = models.SmallIntegerField(
        default=0,
        help_text=(
            "Weekly prosperity drift for landed orgs in this band with zero "
            "open threats (#3091: prestige pays through bounded prosperity)."
        ),
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["negative_only", "min_rank"]

    def __str__(self) -> str:
        return self.name


class OrgPrestigeRank(SharedMemoryModel):
    """Prestige rank storage for orgs that carry no HouseStature (#3091).

    Crime syndicates and other unlanded orgs rank on the same contextual
    ladder without the stature spine; landed orgs store rank on HouseStature.
    """

    organization = models.OneToOneField(
        _ORG_FK,
        on_delete=models.CASCADE,
        related_name="prestige_rank_row",
    )
    prestige_rank = models.PositiveIntegerField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["prestige_rank"]

    def __str__(self) -> str:
        return f"{self.organization}: prestige rank {self.prestige_rank}"


# ---------------------------------------------------------------------------
# Org pacts & betrothal (#2999) — diplomacy beyond marriage
# ---------------------------------------------------------------------------


class PactKind(NaturalKeyMixin, SharedMemoryModel):
    """Authored pact vocabulary (#2999): terms are LEVERS, never prose.

    Per the ADR-0178 payload rule, every effect a pact has is a typed column
    read mechanically — allied stature share, income tithe, non-aggression.
    Rows: Defensive Compact, Trade Agreement, Non-Aggression Pact.
    """

    name = models.CharField(max_length=60, unique=True)
    description = models.TextField(
        blank=True,
        help_text="PLACEHOLDER display prose pending the content pass.",
    )
    allied_share_pct = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Percent of the counterpart's NET strength that flows into each "
            "party's allied stature component while the pact stands."
        ),
    )
    income_share_pct = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            "Percent-of-income tithe from party_a to party_b, minted as a "
            "currency.OrgObligation at ratification. Zero = no tithe."
        ),
    )
    non_aggression = models.BooleanField(
        default=False,
        help_text=(
            "Parties are pledged not to move against each other; hostile acts "
            "stamp BETRAYAL. Future war declarations read this."
        ),
    )
    mutual_defense = models.BooleanField(
        default=False,
        help_text=(
            "The counterpart's raids/crises are yours to answer — content "
            "hooks auto-invite the ally's members (wiring lands with the "
            "crisis-response content pass)."
        ),
    )

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class OrgPact(SharedMemoryModel):
    """A non-embodied diplomatic instrument between two orgs (#2999).

    Sibling of MarriagePact, never a replacement: marriage stays the
    embodied instrument (union-bound, dies with the person); OrgPact is the
    signed-paper kind — proposed by one leadership, ratified by the other,
    dissolved by agreement or stamped BETRAYAL as a world event.
    """

    kind = models.ForeignKey(
        PactKind,
        on_delete=models.PROTECT,
        related_name="pacts",
    )
    party_a = models.ForeignKey(
        _ORG_FK,
        on_delete=models.CASCADE,
        related_name="pacts_as_party_a",
        help_text="The proposing org (owes any income tithe).",
    )
    party_b = models.ForeignKey(
        _ORG_FK,
        on_delete=models.CASCADE,
        related_name="pacts_as_party_b",
    )
    proposed_by = models.ForeignKey(
        _PERSONA_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    obligation = models.OneToOneField(
        "arxii.OrgObligation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pact",
        help_text="The tithe minted at ratification when the kind carries one.",
    )
    proposed_at = models.DateTimeField(auto_now_add=True)
    ratified_at = models.DateTimeField(null=True, blank=True)
    dissolved_at = models.DateTimeField(null=True, blank=True)
    dissolution_reason = models.CharField(
        max_length=20,
        choices=OrgPactDissolutionReason.choices,
        blank=True,
    )

    class Meta:
        ordering = ["-proposed_at"]

    def __str__(self) -> str:
        if self.dissolved_at:
            state = self.get_dissolution_reason_display()
        elif self.ratified_at:
            state = "standing"
        else:
            state = "proposed"
        return f"{self.kind.name}: {self.party_a} & {self.party_b} ({state})"

    @property
    def is_standing(self) -> bool:
        return self.ratified_at is not None and self.dissolved_at is None


# How a betrothal ended up, as shown in ``Betrothal.__str__``.
_BETROTHAL_WED = "wed"
_BETROTHAL_BROKEN = "broken"
_BETROTHAL_PROMISED = "promised"


class Betrothal(SharedMemoryModel):
    """A promised union (#2999): negotiated terms held in draft until the wedding.

    Carries a fraction of the eventual alliance's stature weight (the world
    treats the match as likely); breaking it is a scandal. The WEDDING
    ceremony solemnizes it: union + marriage pact + tier prestige in one rite.
    """

    kinsperson_a = models.ForeignKey(
        _KINSPERSON_FK,
        on_delete=models.CASCADE,
        related_name="betrothals_as_a",
    )
    kinsperson_b = models.ForeignKey(
        _KINSPERSON_FK,
        on_delete=models.CASCADE,
        related_name="betrothals_as_b",
    )
    senior_house = models.ForeignKey(
        _ORG_FK,
        on_delete=models.CASCADE,
        related_name="betrothals_as_senior",
    )
    junior_house = models.ForeignKey(
        _ORG_FK,
        on_delete=models.CASCADE,
        related_name="betrothals_as_junior",
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="An unfulfilled promise lapses quietly after this; null = open-ended.",
    )
    broken_at = models.DateTimeField(null=True, blank=True)
    wed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Betrothals"

    def _state_label(self) -> str:
        """Where a betrothal ended up: married, called off, or still standing."""
        if self.wed_at:
            return _BETROTHAL_WED
        if self.broken_at:
            return _BETROTHAL_BROKEN
        return _BETROTHAL_PROMISED

    def __str__(self) -> str:
        state = self._state_label()
        return f"{self.kinsperson_a} & {self.kinsperson_b} ({state})"

    @property
    def is_active(self) -> bool:
        from django.utils import timezone  # noqa: PLC0415

        if self.broken_at is not None or self.wed_at is not None:
            return False
        return self.expires_at is None or self.expires_at > timezone.now()


class BetrothalTerm(SharedMemoryModel):
    """One negotiated commitment held in draft on a betrothal (#2999).

    Mirrors CommitmentSpec; becomes a real PactCommitment when the wedding
    signs the marriage pact.
    """

    betrothal = models.ForeignKey(
        Betrothal,
        on_delete=models.CASCADE,
        related_name="terms",
    )
    kind = models.CharField(max_length=20, choices=PactCommitmentKind.choices)
    owed_by_senior = models.BooleanField(default=True)
    committed_person = models.ForeignKey(
        _KINSPERSON_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    amount = models.PositiveBigIntegerField(default=0)
    percent = models.PositiveSmallIntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["betrothal", "pk"]

    def __str__(self) -> str:
        return f"{self.betrothal}: {self.get_kind_display()}"
