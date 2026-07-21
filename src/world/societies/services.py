"""Service functions for the societies legend system.

Provides functions for creating and spreading legendary deeds,
and querying legend totals from materialized views.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Sum
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB

from world.covenants.models import Covenant
from world.scenes.models import Persona, Scene
from world.skills.models import Skill
from world.societies.constants import DeedKnowledgeSource
from world.societies.models import (
    CharacterLegendSummary,
    CovenantLegendCredit,
    CovenantLegendSummary,
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

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.covenants.models import CovenantRole


def _shed_witnesses_if_concealed(
    concealed: bool, personas: list[Persona], witnesses: list[Persona]
) -> tuple[list[Persona], bool]:
    """#1824 — a declared-sneaky act rolls Stealth before anyone "saw" it.

    Group acts are weakest-link: every actor rolls and the worst result
    governs how many outsiders noticed. Undeclared acts pass through.
    """
    if not concealed:
        return witnesses, False
    from world.societies.scandal import reduce_witnesses_by_stealth  # noqa: PLC0415

    characters = [p.character_sheet.character for p in personas if p.character_sheet]
    return reduce_witnesses_by_stealth(characters, personas, witnesses)


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
    crime_kinds: list | None = None,
    archetypes: list | None = None,
    concealed: bool = False,
    containment_approach: str | None = None,
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
        crime_kinds: Optional ``justice.CrimeKind`` rows this deed is an instance
            of (#1765) — criminality is declared at deed birth, so knowledge
            spreading mints pursuit heat wherever a law matches.
        archetypes: Optional ``PhilosophicalArchetype`` rows framing the act
            (#1464) — deed sources SHOULD tag; untagged deeds can never read as
            scandal (missed tags = missed scandals) and skip the reach fork.
        concealed: #1824 — the act was declared sneaky: a Stealth roll sheds
            witnesses before knowledge is minted.
        containment_approach: #1824 — a declared ``WitnessApproach.key`` for
            the hush-up roll; None keeps the auto-pick.

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
    if crime_kinds:
        from world.justice.services import tag_deed_crimes  # noqa: PLC0415

        tag_deed_crimes(entry, crime_kinds)
    if archetypes:
        entry.archetypes.set(archetypes)
    if scene is not None:
        # #902 — everyone on the scene list witnessed the deed's birth.
        from world.societies.knowledge_services import (  # noqa: PLC0415
            grant_deed_knowledge,
            scene_witness_personas,
        )

        witnesses = scene_witness_personas(scene)
        witnesses, fully_concealed = _shed_witnesses_if_concealed(concealed, [persona], witnesses)
        grant_deed_knowledge(
            deed=entry,
            personas=witnesses,
            source=DeedKnowledgeSource.WITNESSED,
            room=scene.location,
        )
        # #1464 — the reach fork: contained Secret vs society awareness.
        from world.societies.scandal import route_deed_reach  # noqa: PLC0415

        route_deed_reach(
            entry=entry,
            scene=scene,
            actor_persona=persona,
            witnesses=witnesses,
            containment_approach=containment_approach,
            fully_concealed=fully_concealed,
        )
    new_credits = credit_engaged_covenants(entry=entry)
    refresh_legend_views()
    entry.persona.clear_cached_properties()
    from world.covenants.services import recompute_covenant_level  # noqa: PLC0415

    for credit in new_credits:
        recompute_covenant_level(covenant=credit.covenant)
    return entry


@transaction.atomic
def create_legend_event(  # noqa: PLR0913, C901
    title: str,
    source_type: LegendSourceType,
    base_value: int,
    personas: list[Persona],
    *,
    description: str = "",
    scene: Scene | None = None,
    story: Story | None = None,
    created_by: AccountDB | None = None,
    crime_kinds: list | None = None,
    archetypes: list | None = None,
    concealed: bool = False,
    containment_approach: str | None = None,
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
        crime_kinds: Optional ``justice.CrimeKind`` rows the shared act is an
            instance of (#1765) — criminality belongs to the act, so every
            participant's entry gets tagged and soaks heat as word spreads.
        archetypes: Optional ``PhilosophicalArchetype`` rows framing the shared
            act (#1464) — every participant's entry carries them; the reach
            fork routes each entry (each participant hushes their own part).
        concealed: #1824 — the act was declared sneaky: every actor rolls
            Stealth (weakest link governs) to shed witnesses before knowledge
            is minted.
        containment_approach: #1824 — a declared ``WitnessApproach.key`` for
            each entry's hush-up roll; None keeps the auto-pick.

    Returns:
        Tuple of (LegendEvent, list of LegendEntry instances).

    Note:
        Each created LegendEntry is also credited to the persona's
        currently-engaged covenants via credit_engaged_covenants.
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
    if crime_kinds:
        from world.justice.services import tag_deed_crimes  # noqa: PLC0415

        for e in entries:
            tag_deed_crimes(e, crime_kinds)
    if archetypes:
        for e in entries:
            e.archetypes.set(archetypes)
    if scene is not None:
        # #902 — scene-list witnesses know every deed born from the event.
        from world.societies.knowledge_services import (  # noqa: PLC0415
            grant_deed_knowledge,
            scene_witness_personas,
        )
        from world.societies.scandal import route_deed_reach  # noqa: PLC0415

        witnesses = scene_witness_personas(scene)
        witnesses, fully_concealed = _shed_witnesses_if_concealed(
            concealed, list(personas), witnesses
        )
        for e in entries:
            grant_deed_knowledge(
                deed=e,
                personas=witnesses,
                source=DeedKnowledgeSource.WITNESSED,
                room=scene.location,
            )
            # #1464 — each participant routes (and hushes) their own part.
            route_deed_reach(
                entry=e,
                scene=scene,
                actor_persona=e.persona,
                witnesses=witnesses,
                containment_approach=containment_approach,
                fully_concealed=fully_concealed,
            )
    all_credits: list[CovenantLegendCredit] = []
    for e in entries:
        all_credits.extend(credit_engaged_covenants(entry=e))
    refresh_legend_views()
    for e in entries:
        e.persona.clear_cached_properties()
    from world.covenants.services import recompute_covenant_level  # noqa: PLC0415

    seen_covenant_ids: set[int] = set()
    for credit in all_credits:
        if credit.covenant_id not in seen_covenant_ids:
            seen_covenant_ids.add(credit.covenant_id)
            recompute_covenant_level(covenant=credit.covenant)
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
    deed.persona.clear_cached_properties()
    from world.covenants.services import recompute_covenant_level  # noqa: PLC0415
    from world.societies.renown import (  # noqa: PLC0415
        apply_spread_fame_bump,
        extend_deed_awareness,
    )

    for credit in deed.covenant_credits.all():
        recompute_covenant_level(covenant=credit.covenant)
    # #676 Phase H: subject's fame buffer rises by ``1 × npc_audience × success_level``.
    # Existing admin spread API doesn't carry NPC/check data yet → no-op on fame.
    apply_spread_fame_bump(deed)
    # #737: extend deed awareness to scene's Realm; re-fire archetype
    # dot-product reputation deltas on newly-aware societies.
    extend_deed_awareness(deed, scene=scene)
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
    deeds = list(event.deeds.filter(is_active=True))
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
    for spread in spreads:
        spread.legend_entry.persona.clear_cached_properties()
    from world.covenants.services import recompute_covenant_level  # noqa: PLC0415

    seen_covenant_ids: set[int] = set()
    for deed in deeds:
        for credit in deed.covenant_credits.all():
            if credit.covenant_id not in seen_covenant_ids:
                seen_covenant_ids.add(credit.covenant_id)
                recompute_covenant_level(covenant=credit.covenant)
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


def credit_engaged_covenants(*, entry: LegendEntry) -> list[CovenantLegendCredit]:
    """Snapshot the persona's currently-engaged covenants and create credit rows.

    Called immediately after a LegendEntry is created (solo deed or event entry).
    Idempotent on retry via get_or_create per (entry, covenant).

    Args:
        entry: The newly-created LegendEntry to credit.

    Returns:
        List of CovenantLegendCredit rows (created or found).
    """
    # `active_memberships` returns all rows with left_at IS NULL.
    # Filter to engaged=True in Python — no DB hit (identity-map cached).
    sheet = entry.persona.character_sheet
    handler = sheet.character.covenant_roles
    memberships = [m for m in handler.active_memberships if m.engaged]
    result: list[CovenantLegendCredit] = []
    for m in memberships:
        credit, _ = CovenantLegendCredit.objects.get_or_create(entry=entry, covenant=m.covenant)
        result.append(credit)
    return result


def get_covenant_legend_total(covenant: Covenant) -> int:
    """Return the covenant's total legend from the materialized view.

    Args:
        covenant: The Covenant instance.

    Returns:
        The covenant's legend total, or 0 if no view row exists yet.

    Note: Uses values_list to bypass the SharedMemoryModel identity-map cache,
    which would otherwise return stale totals after a view refresh.
    """
    row = CovenantLegendSummary.objects.filter(pk=covenant.pk).values_list(
        "legend_total", flat=True
    )
    result = list(row)
    return result[0] if result else 0


def get_covenant_legend_totals(covenant_ids: list[int]) -> dict[int, int]:
    """Bulk sibling of ``get_covenant_legend_total`` — one query for a page of covenants.

    Args:
        covenant_ids: Covenant pks to look up.

    Returns:
        ``{covenant_id: legend_total}``. Covenants with no view row are absent
        (callers default to 0).

    Note: Like the single-covenant version, uses ``values_list`` to bypass the
    SharedMemoryModel identity-map cache, which would otherwise return stale
    totals after a view refresh.
    """
    if not covenant_ids:
        return {}
    rows = CovenantLegendSummary.objects.filter(pk__in=covenant_ids).values_list(
        "pk", "legend_total"
    )
    return dict(rows)


def get_character_role_legend(
    *,
    character_sheet: CharacterSheet,
    role: CovenantRole,
    covenant_ids: list[int] | None = None,
) -> int:
    """Sum the legend this character earned that was credited to covenants where they held ``role``.

    "Legend earned in role" signal for the COVENANT_ROLE anchor cap (issue #517).
    Counts each LegendEntry once (distinct-entry) to avoid the spread-join /
    multi-covenant-credit fan-out double-count. Active entries only.

    ``covenant_ids`` may be supplied by a caller that already has the character's
    held-role covenants cached (the anchor-cap path reads them from the
    ``CharacterCovenantRoleHandler`` cache) to skip the membership query.
    """
    if covenant_ids is None:
        from world.covenants.models import CharacterCovenantRole  # noqa: PLC0415

        covenant_ids = list(
            CharacterCovenantRole.objects.filter(
                character_sheet=character_sheet, covenant_role=role
            ).values_list("covenant_id", flat=True)
        )
    if not covenant_ids:
        return 0

    entry_ids = set(
        CovenantLegendCredit.objects.filter(
            covenant_id__in=covenant_ids,
            entry__persona__character_sheet=character_sheet,
            entry__is_active=True,
        ).values_list("entry_id", flat=True)
    )
    if not entry_ids:
        return 0

    base = LegendEntry.objects.filter(id__in=entry_ids).aggregate(t=Sum("base_value"))["t"] or 0
    spreads = (
        LegendSpread.objects.filter(legend_entry_id__in=entry_ids).aggregate(t=Sum("value_added"))[
            "t"
        ]
        or 0
    )
    return int(base + spreads)
