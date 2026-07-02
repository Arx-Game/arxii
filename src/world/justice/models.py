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

from world.justice.constants import DEFAULT_HEAT_WEIGHT


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
        "areas.Area",
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
        "societies.LegendEntry",
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
        "scenes.Persona",
        on_delete=models.CASCADE,
        related_name="heat_rows",
    )
    area = models.ForeignKey(
        "areas.Area",
        on_delete=models.CASCADE,
        related_name="heat_rows",
    )
    society = models.ForeignKey(
        "societies.Society",
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
        "societies.LegendEntry",
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
