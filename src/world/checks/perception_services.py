"""The canonical perception-check seam (#2997, ratified amendment).

``resolve_perception_check`` is the ONE perception check every
perceive-the-real mechanic resolves through — noticing an illusion is off,
sensing a dreamside presence, spotting the concealed. AD&D-style: a single
roll, on the PERCEPTION primary stat, through the standard ``perform_check``
pipeline. No elaborate override framework beyond it — mirrors
``resolve_security_check`` (this package's ``security_services.py``), the
existing thin kind-to-CheckType wrapper this one is modeled on.

**ADR-0033 boundary (preserved, not renegotiated here):** a passed check may
reveal that something is amiss — a tell, a wrongness — never WHO is behind
a mask. Identification stays clue-driven (PERSONA_LINK), never an automatic
roll. The pierce *contest* in ``world.forms.services.identification`` is a
separate substrate (TehomCD's) — when it wires up, it should call this seam
for its "something's off" half, never fold identity resolution into it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.checks.perception_constants import PERCEPTION_CHECK_TYPE_NAME
from world.checks.services import perform_check

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.checks.types import CheckResult
    from world.skills.models import Specialization


def resolve_perception_check(
    observer_sheet: CharacterSheet,
    *,
    difficulty: int,
    specialization: Specialization | None = None,
) -> CheckResult:
    """Resolve the canonical perception check for ``observer_sheet``.

    The single AD&D-style perception check (#2997 ratified amendment): every
    perception-gated mechanic (noticing an illusion is off, sensing a
    dreamside presence, spotting the concealed) calls THIS seam rather than
    minting its own roll. Rolls the seeded, stat-only "Perception" CheckType
    (PERCEPTION primary stat) through ``perform_check``, passing ``difficulty``
    straight through as ``target_difficulty`` and ``specialization`` unchanged.

    **ADR-0033 boundary:** a passed check may reveal that something is amiss —
    a tell, a wrongness — never identity. Identification stays clue-driven
    (PERSONA_LINK), never an automatic roll.

    Args:
        observer_sheet: The perceiving character's CharacterSheet.
        difficulty: Target difficulty in points — see
            ``world.checks.perception_constants`` for PLACEHOLDER
            EASY/STANDARD/HARD magnitudes callers may use until a real
            consumer calibrates its own.
        specialization: Optional owned specialization to fold into the roll
            (e.g. a Perception specialization in "spotting the uncanny").

    Returns:
        CheckResult from ``perform_check``.

    Raises:
        ValueError: If the "Perception" CheckType is not seeded/active.
    """
    from world.checks.models import CheckType  # noqa: PLC0415

    check_type = CheckType.objects.filter(name=PERCEPTION_CHECK_TYPE_NAME, is_active=True).first()
    if check_type is None:
        msg = (
            f"Perception CheckType '{PERCEPTION_CHECK_TYPE_NAME}' is not seeded or "
            "not active. Run the 'investigation' seed cluster."
        )
        raise ValueError(msg)
    return perform_check(
        observer_sheet.character,
        check_type,
        target_difficulty=difficulty,
        specialization=specialization,
    )
