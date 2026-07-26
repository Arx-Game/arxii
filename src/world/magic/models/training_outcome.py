"""Training outcome award model for check-based technique learning (#2727).

TrainingOutcomeAward: per-CheckOutcome-tier dev-point multiplier, read by
resolve_training_check. Reuses the OutcomeTierAward abstract base.
"""

from django.db import models

from world.checks.models import OutcomeTierAward


class TrainingOutcomeAward(OutcomeTierAward):
    """Dev-point multiplier per CheckOutcome tier for technique training (#2727).

    Read by resolve_training_check; a missing row yields multiplier 0.0
    (a content gap, not a crash). Staff-tunable — no hardcoded multipliers
    in service code.
    """

    dev_point_multiplier = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        help_text=(
            "Multiplier on the learner's AP investment for this outcome tier. "
            "0.00 = no progress (AP wasted); 1.00 = full; 1.50 = bonus."
        ),
    )

    def __str__(self) -> str:
        return f"{self.outcome_tier}: x{self.dev_point_multiplier}"
