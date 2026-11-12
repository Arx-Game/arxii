"""Being pacts (#4341): a standing bargain a character strikes with a being.

A ``PactOffer`` is a being's authored offer, carried by a pledge and accepted at
its close. Signing it creates a ``CharacterPact`` tied to the character's
``DevotionStanding``, applies the offer's staged condition (its first stage is
the everyday benefit, its later stages the souring), and opens one PACT_PERIOD
project per graded commitment. Each period is graded once, recorded on its
``PactPeriodDetails`` sidecar, and the favor that counted toward it is itemised as
``PactCredit`` rows.

This sub-package points into worship, conditions, checks and projects; none of
them import it (ADR-0010). The one FK the other way, ``Pledge.pact_offer``, is a
string reference so worship's models never import this module.
"""

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from core.models import ArxSharedMemoryModel as SharedMemoryModel
from world.contributors.models import CreditedContent
from world.pacts.constants import CharacterPactCommitmentKind, CharacterPactEnding
from world.worship.constants import PledgeCreditSource
from world.worship.models import CHARACTER_SHEET_MODEL

#: A pact condition needs at least this many severity-threshold stages: the first
#: is the everyday benefit, the rest are how the pact sours toward breach.
MIN_PACT_CONDITION_STAGES = 2


class PactOffer(CreditedContent, SharedMemoryModel):
    """A being's authored offer of a pact (#4341).

    Staff write the offer's text, its period length, the staged condition the
    holder carries, and how far a missed period pushes that condition. A pledge
    carries an offer (``Pledge.pact_offer``); a character accepts it when she
    closes that pledge well. The commitments every holder owes are the offer's
    ``commitments`` rows.
    """

    being = models.ForeignKey(
        "arxii.WorshippedBeing",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="pact_offers",
        help_text="The being making the offer.",
    )
    name = models.CharField(max_length=100)
    offer_text = models.TextField(help_text="The offer as the being puts it, shown on the pledge.")
    closing_text = models.TextField(
        blank=True,
        default="",
        help_text="Shown to the holder when the pact ends in breach.",
    )
    onlooker_line = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Shown to the room when the pact ends (breach or renouncement). Never states the "
            "reason. Blank = nothing is shown."
        ),
    )
    period_weeks = models.PositiveSmallIntegerField(
        default=2,
        validators=[MinValueValidator(1)],
        help_text="Game weeks in one period; each commitment is graded once per period.",
    )
    condition = models.ForeignKey(
        "arxii.ConditionTemplate",
        on_delete=models.PROTECT,
        related_name="pact_offers",
        help_text=(
            "The staged condition the holder carries. Its first stage is the pact's "
            "everyday benefit; later stages are how the pact sours."
        ),
    )
    severity_per_miss = models.PositiveSmallIntegerField(
        default=10,
        validators=[MinValueValidator(1)],
        help_text=(
            "Condition severity a wholly missed period adds; a met period eases it by "
            "the same scale."
        ),
    )
    is_active = models.BooleanField(
        default=True, help_text="Inactive offers are not offered at a pledge's close."
    )

    class Meta:
        ordering = ["being", "name"]
        constraints = [
            # Exactly one party column is set. Today the only party is a being; the
            # follower pacts issue adds its party column and widens this check to
            # "exactly one of being, follower".
            models.CheckConstraint(
                condition=models.Q(being__isnull=False), name="pact_offer_has_one_party"
            ),
            models.UniqueConstraint(fields=["being", "name"], name="unique_being_pact_offer_name"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.being})"

    def clean(self) -> None:
        super().clean()
        if self.condition_id is None:
            return
        condition = self.condition
        if not condition.has_progression:
            raise ValidationError({"condition": "A pact's condition must progress through stages."})
        staged = condition.stages.filter(severity_threshold__isnull=False).count()
        if staged < MIN_PACT_CONDITION_STAGES:
            raise ValidationError(
                {
                    "condition": (
                        "A pact's condition needs at least two stages with a severity "
                        "threshold: the everyday benefit and at least one worse stage."
                    )
                }
            )


class PactOfferCommitment(SharedMemoryModel):
    """One thing every holder of an offer commits to (#4341).

    The sibling of ``PactCommitment`` on a marriage pact, for a being's offer:
    FAVOR_EARNED is graded each period by a PACT_PERIOD project; CUSTOM is a
    promise recorded in ``notes``, shown and never checked. Commitments live on the
    offer because every holder of it owes the same thing.
    """

    offer = models.ForeignKey(PactOffer, on_delete=models.CASCADE, related_name="commitments")
    kind = models.CharField(max_length=20, choices=CharacterPactCommitmentKind.choices)
    owed_by_holder = models.BooleanField(
        default=True,
        help_text=(
            "True when the character who holds the pact owes this. Every commitment "
            "is owed by the holder for now."
        ),
    )
    amount = models.PositiveIntegerField(
        default=0, help_text="For favor earned: favor to earn with the being each period."
    )
    notes = models.TextField(
        blank=True, default="", help_text="For a custom commitment: the promise, as shown."
    )

    class Meta:
        ordering = ["offer", "pk"]

    def __str__(self) -> str:
        if self.kind == CharacterPactCommitmentKind.FAVOR_EARNED:
            return f"{self.offer}: {self.amount} favor per period"
        return f"{self.offer}: {self.get_kind_display()}"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.kind == CharacterPactCommitmentKind.FAVOR_EARNED and self.amount == 0:
            errors["amount"] = "A favor commitment needs an amount above zero."
        if self.kind == CharacterPactCommitmentKind.CUSTOM and not self.notes.strip():
            errors["notes"] = "A custom commitment needs the promise written in its notes."
        if not self.owed_by_holder:
            errors["owed_by_holder"] = "Every pact commitment is owed by the holder for now."
        if errors:
            raise ValidationError(errors)


class CharacterPact(SharedMemoryModel):
    """A character's signed pact with a being (#4341).

    Tied to her ``DevotionStanding`` with the being: one active pact per standing.
    The standing keeps its own patronage lifecycle; ending the pact releases a
    PACT patronage. ``condition_instance`` is the offer's condition on her, which
    each graded period moves. A dissolved pact keeps its row as the record.
    """

    character_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="pacts",
        help_text=(
            "The holder, in every pact kind: a follower pact will have no devotion "
            "standing. Matches the devotion standing's character when there is one."
        ),
    )
    offer = models.ForeignKey(PactOffer, on_delete=models.PROTECT, related_name="signed")
    devotion_standing = models.ForeignKey(
        "arxii.DevotionStanding",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="pacts",
        help_text="The holder's standing with the being the pact is struck with.",
    )
    condition_instance = models.ForeignKey(
        "arxii.ConditionInstance",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pacts",
        help_text="The offer's condition on the holder. Empty once it has eased away.",
    )
    signed_at = models.DateTimeField(default=timezone.now)
    dissolved_at = models.DateTimeField(
        null=True, blank=True, help_text="When the pact ended. Empty = active."
    )
    dissolution_reason = models.CharField(
        max_length=20,
        choices=CharacterPactEnding.choices,
        blank=True,
        default="",
        help_text="Why the pact ended. Set exactly when it has ended.",
    )

    class Meta:
        ordering = ["-signed_at", "pk"]
        constraints = [
            # Exactly one party column is set. Today the only party is a being (through
            # the standing); the follower pacts issue adds its party column and widens
            # this check to "exactly one of devotion_standing, follower".
            models.CheckConstraint(
                condition=models.Q(devotion_standing__isnull=False),
                name="character_pact_has_one_party",
            ),
            models.UniqueConstraint(
                fields=["devotion_standing"],
                condition=models.Q(dissolved_at__isnull=True),
                name="unique_active_pact_per_standing",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(dissolved_at__isnull=True, dissolution_reason="")
                    | (models.Q(dissolved_at__isnull=False) & ~models.Q(dissolution_reason=""))
                ),
                name="character_pact_reason_iff_dissolved",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.character_sheet} pact: {self.offer}"

    @property
    def is_active(self) -> bool:
        """True while the pact has not been dissolved."""
        return self.dissolved_at is None

    def clean(self) -> None:
        super().clean()
        if self.devotion_standing_id is None:
            return
        standing = self.devotion_standing
        errors: dict[str, str] = {}
        if self.character_sheet_id is not None and (
            standing.character_sheet_id != self.character_sheet_id
        ):
            errors["devotion_standing"] = "The standing must be the holder's own."
        if self.offer_id is not None and standing.being_id != self.offer.being_id:
            errors["offer"] = "The offer must be from the being the standing is with."
        if errors:
            raise ValidationError(errors)


class PactPeriodDetails(SharedMemoryModel):
    """Sidecar of one PACT_PERIOD ``Project`` (#4341): one period of one pact.

    The project carries the period's span and the favor earned toward it; this row
    names the pact and the commitment being graded and records the grading once it
    runs: the resist roll's outcome (when one was needed), the severity change and
    the stage the condition ended on. The project and this row are the receipt that
    makes each period's check run once. A null ``commitment`` is an ease-out period
    opened after the pact ended, which only lets the condition fade.
    """

    project = models.OneToOneField(
        "arxii.Project", on_delete=models.CASCADE, related_name="pact_period_details"
    )
    pact = models.ForeignKey(CharacterPact, on_delete=models.CASCADE, related_name="periods")
    commitment = models.ForeignKey(
        PactOfferCommitment,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="periods",
        help_text="The commitment graded this period. Empty = an ease-out period after the end.",
    )
    resist_outcome = models.ForeignKey(
        "arxii.CheckOutcome",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The resist roll's outcome, when a short period reached a worse stage.",
    )
    severity_change = models.IntegerField(
        null=True,
        blank=True,
        help_text="Severity added (positive) or eased (negative) at grading. Empty = not graded.",
    )
    stage_after = models.ForeignKey(
        "arxii.ConditionStage",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="The condition's stage after grading.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "pk"]
        verbose_name = "Pact period details"
        verbose_name_plural = "Pact period details"

    def __str__(self) -> str:
        return f"{self.pact} period (project #{self.project_id})"


class PactCredit(SharedMemoryModel):
    """One favor credit toward a pact period, by source (#4341).

    The itemised list behind the pact card ("Deeds +4, rite +2"). The counter is
    the period project's ``current_progress``; these rows say where it came from.
    Mirrors ``PledgeCredit``. ``base`` is what one favor write takes from the weekly
    deed cap, counted once: a write that also credited a pledge is counted on its
    ``PledgeCredit``, and a write credited to several open periods of one pact is
    counted on the first period's row only; every other row carries 0.
    """

    period = models.ForeignKey(PactPeriodDetails, on_delete=models.CASCADE, related_name="credits")
    source = models.CharField(max_length=20, choices=PledgeCreditSource.choices)
    base = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Favor before the earning rate; what the weekly deed cap counts. 0 when the same "
            "favor write is already counted (on its pledge credit, or on an earlier period's "
            "credit)."
        ),
    )
    credited = models.PositiveIntegerField(help_text="Favor credited toward the period.")
    game_week = models.ForeignKey(
        "arxii.GameWeek",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pact_credits",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]

    def __str__(self) -> str:
        return f"{self.get_source_display()} +{self.credited} ({self.period})"
