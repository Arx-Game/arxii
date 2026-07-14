"""Estate models (#1985): wills, bequests, executors, settlements, claims.

Estates is a CONSUMER app (ADR-0010): every FK points outward at primitives
(items, currency, buildings, scenes, societies, character_sheets) — nothing
points back into estates. The settlement lifecycle contract (three doors,
first wins; debts before bequests; estate-heir fall-through chain) lives in
``services.execute_settlement``; these models only hold the declared state.
"""

from django.core.exceptions import ValidationError
from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from world.estates.constants import BequestKind, SettlementDoor, SettlementStatus


class Will(SharedMemoryModel):
    """A character's unilateral testament — the will member of the agreements family.

    Freely editable while the author lives; frozen (service-guarded, see
    ``services.will_is_frozen``) once an ``EstateSettlement`` opens.
    """

    character_sheet = models.OneToOneField(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="will",
    )
    testament_text = models.TextField(
        blank=True,
        help_text="Player-authored prose an executor reads aloud at the will-reading.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["character_sheet_id"]

    def __str__(self) -> str:
        return f"Will of {self.character_sheet}"


class WillExecutor(SharedMemoryModel):
    """A persona tagged to perform the will-reading; any one executor suffices."""

    will = models.ForeignKey(Will, on_delete=models.CASCADE, related_name="executors")
    persona = models.ForeignKey(
        "scenes.Persona", on_delete=models.PROTECT, related_name="executor_duties"
    )

    class Meta:
        ordering = ["will_id", "id"]
        constraints = [
            models.UniqueConstraint(fields=["will", "persona"], name="unique_will_executor"),
        ]

    def __str__(self) -> str:
        return f"{self.persona} executes {self.will}"


class Bequest(SharedMemoryModel):
    """One line of a will. Execution is kind-major (spec order), ``order`` within kind.

    Recipient is exactly one of (persona, organization) — the typed-pair shape
    ``Contract``/``CurrencyTransfer`` use. Target coherence per kind is enforced
    in ``clean()`` AND mirrored in the serializer (DRF never calls ``clean()``).
    """

    will = models.ForeignKey(Will, on_delete=models.CASCADE, related_name="bequests")
    order = models.PositiveSmallIntegerField(
        default=0, help_text="Execution order within this bequest's kind."
    )
    kind = models.CharField(max_length=20, choices=BequestKind.choices)
    item = models.ForeignKey(
        "items.ItemInstance",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bequests",
    )
    building = models.ForeignKey(
        "buildings.Building",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bequests",
    )
    business = models.ForeignKey(
        "currency.Business",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bequests",
    )
    amount = models.PositiveBigIntegerField(
        default=0, help_text="Coppers; COIN_AMOUNT bequests only."
    )
    recipient_persona = models.ForeignKey(
        "scenes.Persona",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="bequests_received",
    )
    recipient_organization = models.ForeignKey(
        "societies.Organization",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="bequests_received",
    )

    class Meta:
        ordering = ["will_id", "kind", "order", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(recipient_persona__isnull=False)
                    ^ models.Q(recipient_organization__isnull=False)
                ),
                name="bequest_one_recipient",
            ),
            models.UniqueConstraint(
                fields=["will"],
                condition=models.Q(kind="residuary"),
                name="one_residuary_per_will",
            ),
        ]

    _KIND_TARGET_FIELD = {
        BequestKind.SPECIFIC_ITEM: "item",
        BequestKind.BUILDING: "building",
        BequestKind.BUSINESS: "business",
    }

    def clean(self) -> None:
        target_field = self._KIND_TARGET_FIELD.get(BequestKind(self.kind))
        for field in ("item", "building", "business"):
            value = getattr(self, field)
            if field == target_field and value is None:
                raise ValidationError({field: f"A {self.kind} bequest requires {field}."})
            if field != target_field and value is not None:
                raise ValidationError({field: f"A {self.kind} bequest may not set {field}."})
        if self.kind == BequestKind.COIN_AMOUNT and self.amount == 0:
            raise ValidationError({"amount": "A coin bequest requires a positive amount."})
        if self.kind != BequestKind.COIN_AMOUNT and self.amount != 0:
            raise ValidationError({"amount": f"A {self.kind} bequest may not carry an amount."})

    def __str__(self) -> str:
        return f"Bequest({self.kind}) in {self.will}"


class EstateSettlement(SharedMemoryModel):
    """The settlement window opened by death (``_mark_dead`` -> ``open_settlement``).

    PENDING until a door executes; SETTLED is terminal; PARKED means the
    escheat target was unresolvable and ZERO mutations were applied (the
    execution transaction rolled back) — a staff queue, never a half-estate.
    """

    character_sheet = models.OneToOneField(
        "character_sheets.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="estate_settlement",
    )
    opened_at = models.DateTimeField(auto_now_add=True)
    deadline = models.DateTimeField(
        help_text="When the sweeper door auto-settles (opened_at + config window)."
    )
    status = models.CharField(
        max_length=20, choices=SettlementStatus.choices, default=SettlementStatus.PENDING
    )
    settled_via = models.CharField(
        max_length=20, choices=SettlementDoor.choices, blank=True, default=""
    )
    settled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-opened_at"]

    def __str__(self) -> str:
        return f"Estate of {self.character_sheet} ({self.status})"


class EstateClaim(SharedMemoryModel):
    """An inherited grievance: an item stolen from the deceased, never recovered.

    Minted at settlement execution. Visible to the claimant (and staff) ONLY —
    the current holder is never notified; discovery is investigation gameplay.
    Receiving a claim is receiving a grievance, not stolen goods: the
    stolen-goods consent gate does not apply.
    """

    settlement = models.ForeignKey(
        EstateSettlement, on_delete=models.CASCADE, related_name="claims"
    )
    item = models.ForeignKey(
        "items.ItemInstance", on_delete=models.PROTECT, related_name="estate_claims"
    )
    claimant_persona = models.ForeignKey(
        "scenes.Persona",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="estate_claims",
    )
    claimant_organization = models.ForeignKey(
        "societies.Organization",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="estate_claims",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["settlement_id", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(claimant_persona__isnull=False)
                    ^ models.Q(claimant_organization__isnull=False)
                ),
                name="claim_one_claimant",
            ),
        ]

    def __str__(self) -> str:
        return f"Claim on {self.item} from {self.settlement}"


class EstateConfig(SharedMemoryModel):
    """Staff-tunable singleton — PLACEHOLDER values (spec Decision 2).

    Access via ``get_estate_config()`` (singleton-by-convention, mirrors
    ``get_ceremony_config``).
    """

    settlement_window_days = models.PositiveSmallIntegerField(
        default=14,
        help_text="Real days from death until the sweeper door auto-settles the estate.",
    )

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"EstateConfig (pk={self.pk})"


def get_estate_config() -> EstateConfig:
    """Get-or-create the first EstateConfig row (singleton-by-convention)."""
    config = EstateConfig.objects.first()
    if config is None:
        config = EstateConfig.objects.create()
    return config
