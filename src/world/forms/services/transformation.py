from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.forms.models import ActiveAlternateSelf, AlternateSelf

SCALE = 10


def trigger_transformation(
    sheet: "CharacterSheet",
    alt: "AlternateSelf",
    *,
    cause: str,
    instance_value: float = 1.0,
) -> "ActiveAlternateSelf":
    """Cause-path seam for assuming an alternate self.

    All non-voluntary assumption paths (technique, trigger, command invocation)
    flow through this function so audits and per-instance variance are applied
    consistently. ``cause`` is a tag for logging/audit (e.g. ``"technique"``,
    ``"trigger"``, ``"command"``); it currently has no side effects but keeps
    the seam uniform for future audit hooks.

    Args:
        sheet: the character assuming the alt-self.
        alt: the ``AlternateSelf`` grant being assumed.
        cause: audit tag describing why the transformation happened.
        instance_value: per-instance multiplier for the granted stat-suite
            (default 1.0 = no scaling).

    Returns:
        The ``ActiveAlternateSelf`` row created or updated by the assumption.
    """
    # Lazy import to avoid a circular dependency with the services package.
    from world.forms.services import assume_alternate_self  # noqa: PLC0415

    _ = cause  # Reserved for future audit/telemetry hooks.
    return assume_alternate_self(sheet, alt, instance_value=instance_value)
