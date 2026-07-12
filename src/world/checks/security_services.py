"""Security check resolution helpers (#2180).

Thin mapping layer that maps a SecurityCheckKind to its CheckType and
delegates to the existing perform_check pipeline. Callers (child issues
#2176, #2178, #2179) compute target_difficulty from domain context (lock
level, guard level, window height) and pass it as an int.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.checks.constants import SECURITY_CHECK_TYPE_NAMES, SecurityCheckKind
from world.checks.services import perform_check

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.checks.types import CheckResult


def resolve_security_check(
    kind: SecurityCheckKind,
    actor: ObjectDB,
    *,
    target_difficulty: int = 0,
    extra_modifiers: int = 0,
) -> CheckResult:
    """Map a security situation to its CheckType and resolve through perform_check.

    The caller computes target_difficulty from domain context (lock level,
    guard level, window height, etc.) and passes it as an int. The helper
    does not couple to domain models — it is a kind→CheckType lookup +
    delegation to the standard pipeline.

    Args:
        kind: Which security check to resolve (sneak, lockpick, etc.).
        actor: The character performing the check.
        target_difficulty: Target difficulty in points, computed by the caller.
        extra_modifiers: Additional modifiers from caller (equipment, conditions, etc.).

    Returns:
        CheckResult from perform_check.

    Raises:
        ValueError: If the CheckType for this kind is not seeded/active.
    """
    from world.checks.models import CheckType  # noqa: PLC0415

    check_type_name = SECURITY_CHECK_TYPE_NAMES[kind]
    check_type = CheckType.objects.filter(name=check_type_name, is_active=True).first()
    if check_type is None:
        msg = (
            f"Security check type '{check_type_name}' (kind={kind.value}) "
            "is not seeded or not active. Run the 'security' seed cluster."
        )
        raise ValueError(msg)
    return perform_check(
        actor,
        check_type,
        target_difficulty=target_difficulty,
        extra_modifiers=extra_modifiers,
    )
