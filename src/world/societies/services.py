"""Service functions for the societies legend system.

Provides functions for creating and spreading legendary deeds,
and querying legend totals from materialized views.
"""

from decimal import Decimal

from django.db import transaction
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB

from world.character_sheets.models import Guise
from world.scenes.models import Scene
from world.skills.models import Skill
from world.societies.models import (
    CharacterLegendSummary,
    GuiseLegendSummary,
    LegendEntry,
    LegendEvent,
    LegendSourceType,
    LegendSpread,
    Society,
    refresh_legend_views,
)
from world.stories.models import Story


@transaction.atomic
def create_solo_deed(  # noqa: PLR0913
    guise: Guise,
    title: str,
    source_type: LegendSourceType,
    base_value: int,
    *,
    description: str = "",
    scene: Scene | None = None,
    story: Story | None = None,
) -> LegendEntry:
    """Create a legend deed not tied to a shared event.

    Args:
        guise: The guise earning legend for this deed.
        title: Short name for the deed.
        source_type: Category of legend source.
        base_value: Initial legend value.
        description: Optional description of the deed.
        scene: Optional scene where this occurred.
        story: Optional story this is part of.

    Returns:
        The created LegendEntry.
    """
    entry = LegendEntry.objects.create(
        guise=guise,
        title=title,
        source_type=source_type,
        base_value=base_value,
        description=description,
        scene=scene,
        story=story,
        event=None,
    )
    refresh_legend_views()
    return entry


@transaction.atomic
def create_legend_event(  # noqa: PLR0913
    title: str,
    source_type: LegendSourceType,
    base_value: int,
    guises: list[Guise],
    *,
    description: str = "",
    scene: Scene | None = None,
    story: Story | None = None,
    created_by: AccountDB | None = None,
) -> tuple[LegendEvent, list[LegendEntry]]:
    """Create a shared event and individual deeds for each participant.

    Args:
        title: Short name for the event.
        source_type: Category of legend source.
        base_value: Base legend value for each participant.
        guises: List of guises participating in the event.
        description: Optional description of the event.
        scene: Optional scene where this occurred.
        story: Optional story this is part of.
        created_by: Optional account that created this event.

    Returns:
        Tuple of (LegendEvent, list of LegendEntry instances).
    """
    event = LegendEvent.objects.create(
        title=title,
        source_type=source_type,
        base_value=base_value,
        description=description,
        scene=scene,
        story=story,
        created_by=created_by,
    )
    entries = LegendEntry.objects.bulk_create(
        [
            LegendEntry(
                guise=guise,
                title=title,
                source_type=source_type,
                base_value=base_value,
                description=description,
                scene=scene,
                story=story,
                event=event,
            )
            for guise in guises
        ]
    )
    refresh_legend_views()
    return event, entries


@transaction.atomic
def spread_deed(  # noqa: PLR0913
    deed: LegendEntry,
    spreader_guise: Guise,
    value_added: int,
    *,
    description: str = "",
    method: str = "",
    skill: Skill | None = None,
    audience_factor: Decimal = Decimal("1.0"),
    scene: Scene | None = None,
    societies_reached: list[Society] | None = None,
) -> LegendSpread:
    """Record a spreading action and add legend value, clamped to capacity.

    Args:
        deed: The legend entry being spread.
        spreader_guise: The guise spreading this legend.
        value_added: Desired value to add (will be clamped).
        description: Optional embellished version of the deed.
        method: How it was spread (e.g., bard song, tavern gossip).
        skill: Optional skill used for spreading.
        audience_factor: Multiplier based on audience size/quality.
        scene: Optional scene where spreading occurred.
        societies_reached: Optional list of societies that heard this.

    Returns:
        The created LegendSpread.
    """
    clamped_value = min(value_added, deed.remaining_spread_capacity)
    spread = LegendSpread.objects.create(
        legend_entry=deed,
        spreader_guise=spreader_guise,
        value_added=clamped_value,
        description=description,
        method=method,
        skill=skill,
        audience_factor=audience_factor,
        scene=scene,
    )
    if societies_reached:
        spread.societies_reached.set(societies_reached)
    refresh_legend_views()
    return spread


@transaction.atomic
def spread_event(  # noqa: PLR0913
    event: LegendEvent,
    spreader_guise: Guise,
    value_per_deed: int,
    *,
    description: str = "",
    method: str = "",
    skill: Skill | None = None,
    audience_factor: Decimal = Decimal("1.0"),
    scene: Scene | None = None,
    societies_reached: list[Society] | None = None,
) -> list[LegendSpread]:
    """Spread all active deeds linked to an event at once.

    Args:
        event: The legend event whose deeds to spread.
        spreader_guise: The guise spreading this legend.
        value_per_deed: Desired value per deed (each clamped independently).
        description: Optional embellished version.
        method: How it was spread.
        skill: Optional skill used for spreading.
        audience_factor: Multiplier based on audience size/quality.
        scene: Optional scene where spreading occurred.
        societies_reached: Optional list of societies that heard this.

    Returns:
        List of created LegendSpread instances.
    """
    deeds = event.deeds.filter(is_active=True)
    spreads: list[LegendSpread] = []
    for deed in deeds:
        clamped_value = min(value_per_deed, deed.remaining_spread_capacity)
        spread = LegendSpread.objects.create(
            legend_entry=deed,
            spreader_guise=spreader_guise,
            value_added=clamped_value,
            description=description,
            method=method,
            skill=skill,
            audience_factor=audience_factor,
            scene=scene,
        )
        if societies_reached:
            spread.societies_reached.set(societies_reached)
        spreads.append(spread)
    refresh_legend_views()
    return spreads


def get_character_legend_total(character: ObjectDB) -> int:
    """Fast lookup of a character's total legend from materialized view.

    Args:
        character: The character ObjectDB instance.

    Returns:
        The character's personal legend total, or 0 if no row exists.
    """
    try:
        summary = CharacterLegendSummary.objects.get(character=character)
        return summary.personal_legend
    except CharacterLegendSummary.DoesNotExist:
        return 0


def get_guise_legend_total(guise: Guise) -> int:
    """Per-persona legend lookup from materialized view.

    Args:
        guise: The Guise instance.

    Returns:
        The guise's legend total, or 0 if no row exists.
    """
    try:
        summary = GuiseLegendSummary.objects.get(guise=guise)
        return summary.guise_legend
    except GuiseLegendSummary.DoesNotExist:
        return 0
