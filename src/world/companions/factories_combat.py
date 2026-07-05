"""Factory for companion defeat consequence pool (#1873).

Mirrors ``world.vitals.factories.create_bleed_out_terminal_pool``. The pool
is only consulted at EXTREME/LETHAL risk levels; LOW/MODERATE/HIGH skip the
pool entirely and the persistent Companion is untouched.
"""

from __future__ import annotations

COMPANION_DEFEAT_POOL_NAME = "companion_defeat"

# Outcome-tier label constants (mirrors vitals/factories.py).
_OUTCOME_FAILURE = "Failure"
_OUTCOME_PARTIAL = "Partial Success"
_OUTCOME_SUCCESS = "Success"


def _get_or_create_outcome(name: str, success_level: int):
    """Return a CheckOutcome with the given name, creating it if absent."""
    from world.traits.factories import CheckOutcomeFactory  # noqa: PLC0415

    return CheckOutcomeFactory(name=name, success_level=success_level)


def _seed_pool_consequences(pool, consequence_specs) -> None:
    """Idempotently seed Consequence + ConsequencePoolEntry rows for a pool.

    Mirrors ``world.vitals.factories._seed_pool_consequences``.
    """
    from actions.models import ConsequencePoolEntry  # noqa: PLC0415
    from world.checks.models import Consequence  # noqa: PLC0415

    for outcome_tier, label, weight, character_loss in consequence_specs:
        consequence, _ = Consequence.objects.get_or_create(
            outcome_tier=outcome_tier,
            label=label,
            defaults={"weight": weight, "character_loss": character_loss},
        )
        ConsequencePoolEntry.objects.get_or_create(
            pool=pool,
            consequence=consequence,
            defaults={"weight_override": weight, "is_excluded": False},
        )


def create_companion_defeat_pool():
    """Create (or return existing) the companion_defeat ConsequencePool.

    Outcomes authored:
    - ``recover`` (Success tier, weight=2): companion survives and recovers.
    - ``stay_incapacitated`` (Partial Success tier, weight=3): companion is
      incapacitated but not dead — survives to fight another day.
    - ``die`` (Failure tier, weight=1, character_loss=True): companion is
      released (``release_companion``). Only reachable at EXTREME/LETHAL risk.

    Returns the ConsequencePool instance (idempotent — safe to call multiple
    times).
    """
    from actions.models import ConsequencePool  # noqa: PLC0415

    pool, _ = ConsequencePool.objects.get_or_create(
        name=COMPANION_DEFEAT_POOL_NAME,
        defaults={
            "description": (
                "Companion defeat at lethal stakes (EXTREME/LETHAL risk). "
                "The companion may recover, be incapacitated, or die (released)."
            ),
        },
    )

    failure = _get_or_create_outcome(_OUTCOME_FAILURE, success_level=-1)
    partial = _get_or_create_outcome(_OUTCOME_PARTIAL, success_level=0)
    success = _get_or_create_outcome(_OUTCOME_SUCCESS, success_level=1)

    _seed_pool_consequences(
        pool,
        [
            (success, "companion_recover", 2, False),
            (partial, "companion_stay_incapacitated", 3, False),
            (failure, "companion_die", 1, True),
        ],
    )

    return pool
