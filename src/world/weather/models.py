"""Models for the weather system (#1522).

``Climate`` is the regional *baseline* for the environmental exposure axes — the flat,
year-round "extent" of a region's temperature and moisture. It attaches to an ``Area``
via ``Area.climate`` and resolves most-specific-wins up the area hierarchy (mirroring
``Area.realm`` / ``get_effective_realm``), so a parent region can stay temperate while a
sub-region designates desert. A global per-month temperature shift
(``constants.MONTH_TEMPERATURE_SHIFT``) rides on top of the baseline; transient weather
(a later slice) writes decaying exposure modifiers over it.

The signed ``temperature``/``moisture`` weights decompose onto the floored exposure axes
(``world.locations.constants``): ``temperature`` > 0 → HEAT, < 0 → COLD; ``moisture`` > 0
→ WET, < 0 → DRY. The decomposition + fold-into-comfort lives in
``world.weather.services`` and ``world.locations.services.felt_exposure``.
"""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

_CODEX_SUBJECT_FK = "codex.CodexSubject"


class Climate(SharedMemoryModel):
    """An authorable regional climate: a flat temperature/moisture baseline (#1522).

    Designated on a region ``Area`` (``Area.climate``) and resolved most-specific-wins down
    the hierarchy. Its player-facing lore lives in the linked ``CodexSubject``, surfaced
    inline at point-of-use rather than siloed in the Codex app.
    """

    name = models.CharField(max_length=100, unique=True)
    codex_subject = models.ForeignKey(
        _CODEX_SUBJECT_FK,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="climates",
        help_text=(
            "Player-facing lore/description for this climate, surfaced inline at "
            "point-of-use. PLACEHOLDER prose seeded from the authored region lore."
        ),
    )
    temperature = models.IntegerField(
        default=0,
        help_text=(
            "Signed baseline temperature 'weight': positive feeds the HEAT exposure axis "
            "(tropical/desert), negative feeds COLD (arctic). 0 is temperate. The global "
            "per-month shift is added to this before it decomposes onto an axis."
        ),
    )
    moisture = models.IntegerField(
        default=0,
        help_text=(
            "Signed baseline moisture 'weight': positive feeds the WET exposure axis "
            "(tropical/coastal), negative feeds DRY (desert). 0 is moderate."
        ),
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this climate can be assigned to regions.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
