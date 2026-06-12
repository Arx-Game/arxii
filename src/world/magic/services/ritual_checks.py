"""Shared check-roll helper for rituals with an authored RitualCheckConfig."""

from __future__ import annotations

import dataclasses
import enum
from typing import TYPE_CHECKING

from world.magic.exceptions import RitualCheckConfigMissing

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.checks.types import CheckResult


class OutcomeTier(enum.Enum):
    """Graded tier derived from CheckOutcome.success_level (canonical scale)."""

    CRIT = "crit"
    SUCCESS = "success"
    FAIL = "fail"
    BOTCH = "botch"


_CRIT_LEVEL = 2
_SUCCESS_LEVEL = 1
_BOTCH_LEVEL = -2


def outcome_tier(success_level: int) -> OutcomeTier:
    """Map a success_level (full −10..+10 scale) to a graded tier."""
    if success_level >= _CRIT_LEVEL:
        return OutcomeTier.CRIT
    if success_level >= _SUCCESS_LEVEL:
        return OutcomeTier.SUCCESS
    if success_level > _BOTCH_LEVEL:
        return OutcomeTier.FAIL
    return OutcomeTier.BOTCH


@dataclasses.dataclass(frozen=True)
class RitualCheckRoll:
    """Result of perform_ritual_check: the raw CheckResult plus derived tier."""

    check_result: CheckResult
    success_level: int
    tier: OutcomeTier


def perform_ritual_check(
    ritual_name: str,
    character: ObjectDB,  # noqa: OBJECTDB_PARAM
    *,
    founder_standing: bool = True,
) -> RitualCheckRoll:
    """Roll the named ritual's authored check.

    Difficulty comes from the ritual's RitualCheckConfig:
    ``non_founder_target_difficulty`` when present and the actor lacks
    founder standing, else ``target_difficulty``.

    Raises RitualCheckConfigMissing when:
    - the Ritual row itself is missing (run ensure_sanctum_rituals() +
      ensure_magic_check_content())
    - the ritual has no config row or the config has no check_type (seed gap)
    """
    from world.checks.services import perform_check  # noqa: PLC0415
    from world.magic.models import Ritual  # noqa: PLC0415

    try:
        ritual = Ritual.objects.select_related("check_config__check_type").get(name=ritual_name)
    except Ritual.DoesNotExist as exc:
        msg = (
            f"Ritual row {ritual_name!r} not found. "
            "Run ensure_sanctum_rituals() + ensure_magic_check_content()."
        )
        raise RitualCheckConfigMissing(msg) from exc

    # GETATTR_LITERAL noqa: reverse OneToOne may legitimately be absent.
    config = getattr(ritual, "check_config", None)  # noqa: GETATTR_LITERAL
    if config is None or config.check_type is None:
        msg = (
            f"Ritual {ritual_name!r} has no usable RitualCheckConfig. "
            "Run world.magic.seeds_checks.ensure_magic_check_content()."
        )
        raise RitualCheckConfigMissing(msg)

    difficulty = config.target_difficulty
    if not founder_standing and config.non_founder_target_difficulty is not None:
        difficulty = config.non_founder_target_difficulty

    check_result = perform_check(
        character,
        check_type=config.check_type,
        target_difficulty=difficulty,
    )
    success_level = int(check_result.outcome.success_level)
    tier = outcome_tier(success_level)
    return RitualCheckRoll(check_result=check_result, success_level=success_level, tier=tier)
