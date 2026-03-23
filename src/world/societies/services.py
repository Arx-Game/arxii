"""Service functions for the societies legend system.

Provides functions for creating and spreading legendary deeds,
and querying legend totals from materialized views.
"""

from decimal import Decimal

from django.db import transaction
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB

from world.scenes.models import Persona, Scene
from world.skills.models import Skill
from world.societies.models import (
    CharacterLegendSummary,
    LegendEntry,
    LegendEvent,
    LegendSourceType,
    LegendSpread,
    PersonaLegendSummary,
    Society,
    SpreadingConfig,
    refresh_legend_views,
)
from world.stories.models import Story


@transaction.atomic
def create_solo_deed(  # noqa: PLR0913
    persona: Persona,
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
        persona: The persona earning legend for this deed.
        title: Short name for the deed.
        source_type: Category of legend source.
        base_value: Initial legend value.
        description: Optional description of the deed.
        scene: Optional scene where this occurred.
        story: Optional story this is part of.

    Returns:
        The created LegendEntry.
    """
    config = SpreadingConfig.get_active_config()
    entry = LegendEntry.objects.create(
        persona=persona,
        title=title,
        source_type=source_type,
        base_value=base_value,
        description=description,
        scene=scene,
        story=story,
        event=None,
        spread_multiplier=config.default_spread_multiplier,
    )
    refresh_legend_views()
    return entry


@transaction.atomic
def create_legend_event(  # noqa: PLR0913
    title: str,
    source_type: LegendSourceType,
    base_value: int,
    personas: list[Persona],
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
        personas: List of personas participating in the event.
        description: Optional description of the event.
        scene: Optional scene where this occurred.
        story: Optional story this is part of.
        created_by: Optional account that created this event.

    Returns:
        Tuple of (LegendEvent, list of LegendEntry instances).
    """
    config = SpreadingConfig.get_active_config()
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
                persona=persona,
                title=title,
                source_type=source_type,
                base_value=base_value,
                description=description,
                scene=scene,
                story=story,
                event=event,
                spread_multiplier=config.default_spread_multiplier,
            )
            for persona in personas
        ]
    )
    refresh_legend_views()
    return event, entries


@transaction.atomic
def spread_deed(  # noqa: PLR0913
    deed: LegendEntry,
    spreader_persona: Persona,
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
        spreader_persona: The persona spreading this legend.
        value_added: Desired value to add (will be clamped).
        description: Optional embellished version of the deed.
        method: How it was spread (e.g., bard song, tavern gossip).
        skill: Optional skill used for spreading.
        audience_factor: Multiplier based on audience size/quality.
        scene: Optional scene where spreading occurred.
        societies_reached: Optional list of societies that heard this.

    Returns:
        The created LegendSpread.

    Raises:
        ValueError: If the deed is inactive.
    """
    # Lock the deed row to prevent concurrent spreads from exceeding the cap.
    deed = LegendEntry.objects.select_for_update().get(pk=deed.pk)
    if not deed.is_active:
        msg = "Cannot spread an inactive deed."
        raise ValueError(msg)
    clamped_value = min(value_added, deed.remaining_spread_capacity)
    spread = LegendSpread.objects.create(
        legend_entry=deed,
        spreader_persona=spreader_persona,
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
    spreader_persona: Persona,
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
        spreader_persona: The persona spreading this legend.
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
    # Loop is intentional: each deed's remaining_spread_capacity depends on its
    # existing spreads, so clamping must be calculated per-deed individually.
    for deed in deeds:
        clamped_value = min(value_per_deed, deed.remaining_spread_capacity)
        spread = LegendSpread.objects.create(
            legend_entry=deed,
            spreader_persona=spreader_persona,
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


def get_persona_legend_total(persona: Persona) -> int:
    """Per-persona legend lookup from materialized view.

    Args:
        persona: The Persona instance.

    Returns:
        The persona's legend total, or 0 if no row exists.
    """
    try:
        summary = PersonaLegendSummary.objects.get(persona=persona)
        return summary.persona_legend
    except PersonaLegendSummary.DoesNotExist:
        return 0
