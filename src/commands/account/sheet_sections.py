"""Telnet ``sheet/<section>`` views (#1334+) — the sheet's sections, mirroring the web tabs.

The character sheet is the hub; each **section** is a part of a character you reference off it
(secrets first; renown, relationships, society/org standings, covenant, magic etc. as they're
built). A section is a renderer ``(command) -> list[str]``; register it in ``SHEET_SECTIONS``
keyed by its switch name. Each section reads the same services as its web tab, so the two faces
can't drift. ``CmdSheet`` dispatches ``sheet/<section>`` here; bare ``sheet`` shows the overview.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

from commands.exceptions import CommandError

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from evennia import Command

    from world.character_sheets.models import CharacterSheet
    from world.roster.models import ParentageEdge as ParentageEdgeType
    from world.secrets.models import Secret, SecretKnowledge

_UNKNOWN = "Unknown"
_NO_IDENTITY = "You have no active character to view sections with."


def _viewer_sheet(command: Command) -> CharacterSheet:
    """The active character's sheet (the viewer). Raises ``CommandError`` if there's no puppet."""
    try:
        return command.caller.puppet.sheet_data
    except (AttributeError, ObjectDoesNotExist) as exc:
        raise CommandError(_NO_IDENTITY) from exc


def _resolve_target_sheet(command: Command, name: str) -> CharacterSheet | None:
    """Resolve a named character to its sheet; None when the search fails (already notified)."""
    target = command.caller.search(name, global_search=True)
    if target is None:
        return None
    try:
        return target.sheet_data
    except (AttributeError, ObjectDoesNotExist):
        command.caller.msg(f"{target} is not a character.")
        return None


def _render_secret_section(command: Command) -> list[str]:
    """The secrets section: your own secrets, or the ones you know about another character (#1334).

    Mirrors the web Secrets tab. Your own show in full; secrets about others render any layer you
    haven't uncovered as "Unknown". Scoped to the active (viewing) character.
    """
    from world.secrets.services import known_secrets_for, secrets_owned_by  # noqa: PLC0415

    viewer = _viewer_sheet(command)
    arg = (command.args or "").strip()
    if not arg:
        return _render_own(secrets_owned_by(viewer))
    entry = viewer.roster_entry
    if entry is None:
        raise CommandError(_NO_IDENTITY)
    target_sheet = _resolve_target_sheet(command, arg)
    if target_sheet is None:
        return []
    return _render_known(known_secrets_for(entry, subject_sheet=target_sheet))


def _anchor_summary(secret: Secret) -> str | None:
    """A one-line "the truth behind …" summary of a secret's act anchors (#1573), or None.

    One secret = one act; the act may surface through several records (legend / mission deed /
    scene), so they fold into a single context line — never implying several secrets.
    """
    parts: list[str] = []
    if secret.legend_deed_id:
        parts.append(f'the legend "{secret.legend_deed.title}"')
    if secret.mission_deed_id:
        parts.append("a recorded mission deed")
    if secret.scene_id:
        parts.append(secret.scene.name or f"scene #{secret.scene_id}")
    if not parts:
        return None
    return "The truth behind: " + ", ".join(parts)


def _render_own(secrets: QuerySet[Secret]) -> list[str]:
    rows = list(secrets)
    if not rows:
        return ["You have no secrets of your own."]
    lines = ["|wYour secrets:|n"]
    for secret in rows:
        category = secret.category.name if secret.category_id else _UNKNOWN
        lines.append(f"  |c[{secret.get_level_display()}]|n {secret.content}")
        lines.append(
            f"      Category: {category} | Consequences: {secret.consequences or _UNKNOWN}"
        )
        anchor = _anchor_summary(secret)
        if anchor:
            lines.append(f"      {anchor}")
    return lines


def _render_known(held_rows: QuerySet[SecretKnowledge]) -> list[str]:
    rows = list(held_rows)
    if not rows:
        return ["You know none of their secrets."]
    lines = ["|wSecrets you know:|n"]
    for held in rows:
        secret = held.secret
        category = (
            secret.category.name if (held.knows_category and secret.category_id) else _UNKNOWN
        )
        consequences = (
            secret.consequences if (held.knows_consequences and secret.consequences) else _UNKNOWN
        )
        lines.append(f"  |c[{secret.get_level_display()}]|n {secret.content}")
        lines.append(f"      Category: {category} | Consequences: {consequences}")
        anchor = _anchor_summary(secret)
        if anchor:
            lines.append(f"      {anchor}")
    return lines


def _render_renown_section(command: Command) -> list[str]:
    """The renown section: your standing — prestige, fame tier, society reputations (#676).

    Mirrors the web Renown tab (the owner's ``RenownPanel``) for your active character. Viewing
    another character's renown *card* (tiers only, from their perspective) is a follow-up.
    """
    from world.societies.renown_serializers import build_renown_payload  # noqa: PLC0415

    viewer = _viewer_sheet(command)
    return _format_renown(build_renown_payload(viewer.primary_persona))


def _format_renown(payload: dict) -> list[str]:
    fame = payload["fame"]
    prestige = payload["prestige"]
    lines = [
        f"|wRenown — {payload['persona_name']}|n",
        f"  Fame: {fame['tier_label']} ({fame['points']} pts)",
        (
            f"  Prestige: {prestige['total']}  (deeds {prestige['deeds']}, orgs {prestige['orgs']},"
            f" dwellings {prestige['dwellings']}, items {prestige['items']},"
            f" fashion {prestige['fashion']})"
        ),
    ]
    reputation = payload["reputation"]
    if reputation:
        lines.append("  Standing:")
        lines.extend(f"    {row['society_name']}: {row['tier']}" for row in reputation)
    else:
        lines.append("  Standing: none recorded.")
    return lines


def _render_relationships_section(command: Command) -> list[str]:
    """The relationships section: your regard toward others (relationships app).

    Mirrors the web Relationships tab for your active character — each relationship with a
    qualitative read of its affection (warm / cold / neutral) + status. Numeric points stay OOC.
    """
    from django.db.models import Prefetch  # noqa: PLC0415

    from world.relationships.models import (  # noqa: PLC0415
        CharacterRelationship,
        RelationshipTrackProgress,
    )

    viewer = _viewer_sheet(command)
    relationships = (
        CharacterRelationship.objects.filter(source=viewer)
        .select_related("target__character")
        .prefetch_related(
            Prefetch(
                "track_progress",
                queryset=RelationshipTrackProgress.objects.select_related("track"),
                to_attr="cached_track_progress",
            )
        )
        .order_by("-updated_at")
    )
    return _format_relationships(list(relationships))


def _format_relationships(relationships: list) -> list[str]:
    if not relationships:
        return ["You have no relationships recorded."]
    lines = ["|wYour relationships:|n"]
    for relationship in relationships:
        target = relationship.target.character.db_key
        affection = relationship.affection
        tone = "|gwarm|n" if affection > 0 else ("|rcold|n" if affection < 0 else "neutral")
        status = " (pending)" if relationship.is_pending else ""
        tether = (
            f" |m[tether: {relationship.soul_tether_role}]|n" if relationship.is_soul_tether else ""
        )
        lines.append(f"  {target}: {tone}{status}{tether}")
    return lines


def _render_standing_section(command: Command) -> list[str]:
    """The standing section: your formal positions in organizations (societies app).

    Your **organizational** standing — org memberships (with rank titles) and org reputations —
    scoped to your active persona. Distinct from ``sheet/renown`` (fame / prestige / *society*
    reputation); this is the formal-position view. Society standing lives on the renown section.
    """
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415
    from world.societies.models import (  # noqa: PLC0415
        OrganizationMembership,
        OrganizationReputation,
    )

    viewer = _viewer_sheet(command)
    persona = active_persona_for_sheet(viewer)
    memberships = list(
        OrganizationMembership.objects.filter(persona=persona)
        .select_related("organization", "organization__org_type", "rank")
        .order_by("rank__tier", "organization__name")
    )
    reputations = list(
        OrganizationReputation.objects.filter(persona=persona)
        .select_related("organization")
        .order_by("organization__name")
    )
    return _format_standing(memberships, reputations)


def _format_standing(memberships: list, reputations: list) -> list[str]:
    if not memberships and not reputations:
        return ["You hold no organizational standing."]
    lines = ["|wYour standing:|n"]
    if memberships:
        lines.append("  Memberships:")
        for membership in memberships:
            tier = membership.rank.tier
            title = membership.organization.get_rank_title(tier)
            lines.append(f"    {membership.organization.name}: {title} (rank {tier})")
    if reputations:
        lines.append("  Reputation:")
        lines.extend(
            f"    {reputation.organization.name}: {reputation.get_tier().value.title()}"
            for reputation in reputations
        )
    return lines


def _render_covenant_section(command: Command) -> list[str]:
    """The covenant section: your covenant membership(s) and role (covenants app).

    Each active covenant assignment with its role, rank, and which one you're currently *engaged*
    in. Read-only — joining/role changes are covenant actions, not a sheet view.
    """
    from world.covenants.models import CharacterCovenantRole  # noqa: PLC0415

    viewer = _viewer_sheet(command)
    assignments = list(
        CharacterCovenantRole.objects.filter(character_sheet=viewer, left_at__isnull=True)
        .select_related("covenant", "covenant_role", "rank")
        .order_by("covenant__name")
    )
    return _format_covenant(assignments)


def _format_covenant(assignments: list) -> list[str]:
    if not assignments:
        return ["You belong to no covenant."]
    lines = ["|wYour covenant:|n"]
    for assignment in assignments:
        rank = f", {assignment.rank.name}" if assignment.rank_id else ""
        engaged = " |g[engaged]|n" if assignment.engaged else ""
        name = assignment.covenant.name
        role = assignment.covenant_role.name
        lines.append(f"  {name}: {role}{rank}{engaged}")
    return lines


def _render_titles_section(command: Command) -> list[str]:
    """The titles section: the earned, displayable titles your active character holds (#1522).

    Mirrors the web Titles tab. Titles are cosmetic — the mechanical reward attached to the
    achievement, not the title. Scoped to the active (viewing) character.
    """
    from world.achievements.models import CharacterTitle  # noqa: PLC0415

    viewer = _viewer_sheet(command)
    titles = list(
        CharacterTitle.objects.filter(character_sheet=viewer)
        .select_related("reward")
        .order_by("-earned_at")
    )
    return _format_titles(titles)


def _format_titles(titles: list) -> list[str]:
    if not titles:
        return ["You have earned no titles."]
    lines = ["|wYour titles:|n"]
    lines.extend(f"  {title.reward.name}" for title in titles)
    return lines


def _render_crime_section(command: Command) -> list[str]:
    """The crime section (#1765): where your active persona is wanted, and for what.

    Mirrors the web Crime tab. Self-only by construction — it renders the *viewing*
    character's active persona and never accepts a target argument (heat is private
    risk information; see the #1765 leak table). Allegations show as recorded: a
    false accusation reads the same as a true one.
    """
    from world.justice.constants import tier_for_value  # noqa: PLC0415
    from world.justice.models import PersonaHeat  # noqa: PLC0415
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    viewer = _viewer_sheet(command)
    persona = active_persona_for_sheet(viewer)
    if persona is None:
        raise CommandError(_NO_IDENTITY)
    rows = list(
        PersonaHeat.objects.filter(persona=persona, value__gt=0).select_related("area", "society")
    )
    if not rows:
        return ["So far as you know, no one is hunting you anywhere."]
    lines = [f"|wWanted — {persona.name}:|n"]
    for row in rows:
        tier = tier_for_value(row.value)
        deeds = [source.deed.title for source in row.sources.select_related("deed") if source.deed]
        alleged = f" — for: {', '.join(sorted(set(deeds)))}" if deeds else ""
        lines.append(f"  {row.area.name} ({row.society.name}) — {tier.label}{alleged}")
    return lines


def _render_distinction_section(command: Command) -> list[str]:
    """The distinctions section (#1446): the active character's distinctions.

    Mirrors the web Distinctions tab — both faces read ``_build_distinctions``. Self-only
    (privileged view): the owner sees gated entries with a ``(secret)`` marker; the web serves
    foreign viewers the filtered public list through the sheet serializer instead.
    """
    from world.character_sheets.serializers import (  # noqa: PLC0415
        _build_distinctions,
        get_character_sheet_queryset,
    )

    viewer = _viewer_sheet(command)
    sheet = get_character_sheet_queryset().get(pk=viewer.pk)
    entries = _build_distinctions(sheet, privileged=True)
    if not entries:
        return ["You have no distinctions."]
    lines = ["|wYour distinctions:|n"]
    for entry in entries:
        secret = " |m(secret)|n" if entry["is_secret"] else ""
        notes = f" — {entry['notes']}" if entry["notes"] else ""
        lines.append(f"  {entry['name']} (rank {entry['rank']}){secret}{notes}")
    return lines


def _render_magic_section(command: Command) -> list[str]:
    """The magic section (#1446): the active character's spellbook/status view.

    Mirrors the web Magic tab — both faces read ``_build_magic``. The sheet describes; the
    scene does: this lists gifts, techniques, motif, and aura — casting/weaving stays with
    the in-scene commands (``cast``, ``weave``, ``ritual``).
    """
    from world.character_sheets.serializers import (  # noqa: PLC0415
        _build_magic,
        get_character_sheet_queryset,
    )

    viewer = _viewer_sheet(command)
    sheet = get_character_sheet_queryset().get(pk=viewer.pk)
    magic = _build_magic(sheet)
    if magic is None:
        return ["Nothing is known of your magic."]
    lines = ["|wYour spellbook:|n"]
    for gift in magic["gifts"]:
        lines.append(f"  |w{gift['name']}|n")
        lines.extend(
            f"    {technique['name']} (level {technique['level']})"
            for technique in gift["techniques"]
        )
        if gift["resonances"]:
            lines.append(f"    resonances: {', '.join(gift['resonances'])}")
    motif = magic["motif"]
    if motif:
        resonances = ", ".join(entry["name"] for entry in motif["resonances"])
        lines.append(f"  Motif: {motif['description'] or resonances}")
        if motif["description"] and resonances:
            lines.append(f"    resonances: {resonances}")
    aura = magic["aura"]
    if aura and aura["glimpse_story"]:
        lines.append(f"  Aura: {aura['glimpse_story']}")
    resonances = magic["resonances"]
    if resonances:
        lines.append("  Resonance:")
        lines.extend(
            f"    {entry['name']}: {entry['balance']} (lifetime {entry['lifetime_earned']})"
            for entry in resonances
        )
    return lines


def _render_status_section(command: Command) -> list[str]:
    """The status section (#1446): condition, purse, and AP for the active character.

    Mirrors the web Status panel — health/stamina/anima render as WORDS (wound bands,
    fatigue zones, anima band) over the same vocabularies; coin and AP are currencies
    and show numbers. Self-only, read-only.
    """
    from world.action_points.models import ActionPointPool  # noqa: PLC0415
    from world.currency.constants import format_coppers  # noqa: PLC0415
    from world.currency.services import get_or_create_purse  # noqa: PLC0415
    from world.fatigue.services import get_full_status  # noqa: PLC0415
    from world.magic.constants import anima_band_for  # noqa: PLC0415
    from world.vitals.services import derive_character_status  # noqa: PLC0415

    viewer = _viewer_sheet(command)
    character = viewer.character

    lines = [f"|wStatus — {character.key}:|n"]

    vitals = viewer.vitals_or_none
    wound = vitals.wound_description if vitals else "a healthy appearance"
    lines.append(f"  Condition: {derive_character_status(viewer)} — {wound}")

    fatigue_pool = viewer.fatigue_or_none
    fatigue = get_full_status(viewer, pool=fatigue_pool)
    zones = ", ".join(
        f"{category}: {data['zone']}"
        for category, data in fatigue.items()
        if isinstance(data, dict)
    )
    lines.append(f"  Fatigue: {zones}")

    anima = character.anima_or_none
    if anima is not None:
        lines.append(f"  Anima: {anima_band_for(anima.current, anima.maximum)}")

    purse = get_or_create_purse(viewer)
    lines.append(f"  Coin: {format_coppers(purse.balance)}")

    pool = ActionPointPool.get_or_create_for_character(character)
    banked = f" (+{pool.banked} banked)" if pool.banked else ""
    lines.append(f"  AP: {pool.current} of {pool.get_effective_maximum()} this week{banked}")
    return lines


def _parent_line(edge: ParentageEdgeType) -> str:
    from world.roster.constants import ParentageKind  # noqa: PLC0415

    label = "Foster parent" if edge.kind == ParentageKind.FOSTER else "Parent"
    plain = (ParentageKind.BIOLOGICAL, ParentageKind.FOSTER)
    qualifier = "" if edge.kind in plain else f" ({edge.kind})"
    return f"  {label}: {edge.parent.display_name}{qualifier}"


def _render_family_section(command: object) -> list[str]:
    """``sheet/family`` (#2062) — the viewer's own visible kin, walked live.

    Shows what THIS character knows: the public record plus hidden truths
    they've learned. Blood, marriage, foster, and step relations are labeled
    distinctly (the Arx 1 in-law ambiguity is gone by construction).
    """
    character = command.caller
    sheet = character.character_sheet
    if sheet is None:
        return ["No character sheet."]
    from world.roster.models import Kinsperson, RosterEntry  # noqa: PLC0415
    from world.roster.services.kinship import (  # noqa: PLC0415
        children_of,
        incarnation_chain_of,
        parents_of,
        siblings_of,
        spouses_of,
        step_parents_of,
    )

    node = Kinsperson.objects.filter(sheet=sheet).first()
    if node is None:
        return ["  No recorded kin."]
    try:
        viewer = sheet.roster_entry
    except RosterEntry.DoesNotExist:
        viewer = None

    lines: list[str] = ["|wFamily|n"]
    if node.family is not None:
        lines.append(f"  House: {node.family.name}")
    parent_edges = parents_of(node, viewer, include_foster=True)
    if parent_edges:
        lines.extend(_parent_line(edge) for edge in parent_edges)
    else:
        lines.append("  Parents: unknown")
    sibling_labels = siblings_of(node, viewer)
    if sibling_labels:
        people = {p.pk: p for p in Kinsperson.objects.filter(pk__in=sibling_labels)}
        for pk, label in sibling_labels.items():
            lines.append(f"  {label.replace('-', ' ').title()}: {people[pk].display_name}")
    from world.roster.constants import ParentageKind  # noqa: PLC0415

    lines.extend(f"  Spouse: {s.display_name}" for s in spouses_of(node, viewer))
    lines.extend(f"  Step-parent: {s.display_name}" for s in step_parents_of(node, viewer))
    foster_kind = ParentageKind.FOSTER
    lines.extend(
        f"  {'Foster child' if e.kind == foster_kind else 'Child'}: {e.child.display_name}"
        for e in children_of(node, viewer, include_foster=True)
    )
    lines.extend(
        f"  Past life: {i.kinsperson.display_name}" for i in incarnation_chain_of(node, viewer)
    )
    if len(lines) == 1:
        lines.append("  No recorded kin.")
    return lines


# Switch name → renderer. Add a section by writing a renderer and registering it here (and in
# SECTION_NAMES for the overview footer). Aliases (secret/secrets) map to the same renderer.


def _render_house_section(command: object) -> list[str]:
    """``sheet/house`` (#1884) — the character's house: fealty, titles, tidings."""
    character = command.caller
    sheet = character.character_sheet
    if sheet is None:
        return ["No character sheet."]
    from world.roster.models import Kinsperson  # noqa: PLC0415
    from world.societies.houses.services import (  # noqa: PLC0415
        full_display_name,
        house_for_family,
        liege_chain_of,
    )
    from world.tidings.services import house_feed_for  # noqa: PLC0415

    node = Kinsperson.objects.filter(sheet=sheet).select_related("family").first()
    house = house_for_family(node.family) if node is not None else None
    if node is None or house is None:
        return ["  No house."]
    lines: list[str] = [f"|wHouse|n {house.name}", f"  Name: {full_display_name(node)}"]
    if house.words:
        lines.append(f'  Words: "{house.words}"')
    if house.colors:
        lines.append(f"  Colors: {house.colors}")
    lines.extend(
        f"  {facet.definition.name}: {facet.option.name}"
        for facet in house.aspects.select_related("definition", "option")
    )
    lines.extend(
        f"  [{stamped.feature.name}] {stamped.feature.description}"
        for stamped in house.features.select_related("feature")
    )
    chain = liege_chain_of(house)
    if chain:
        lines.append("  Fealty: " + " -> ".join(liege.name for liege in chain))
    titles = list(node.titles_held.all())
    if titles:
        lines.append("  Titles: " + ", ".join(title.name for title in titles))
    feed = house_feed_for(house, limit=5)
    if feed:
        lines.append("  |wTidings|n")
        lines.extend(f"    {item.subject}: {item.headline}" for item in feed)
    return lines


SHEET_SECTIONS: dict[str, Callable[..., list[str]]] = {
    "secret": _render_secret_section,
    "secrets": _render_secret_section,
    "renown": _render_renown_section,
    "relationship": _render_relationships_section,
    "relationships": _render_relationships_section,
    "standing": _render_standing_section,
    "standings": _render_standing_section,
    "covenant": _render_covenant_section,
    "title": _render_titles_section,
    "titles": _render_titles_section,
    "crime": _render_crime_section,
    "crimes": _render_crime_section,
    "distinction": _render_distinction_section,
    "distinctions": _render_distinction_section,
    "magic": _render_magic_section,
    "family": _render_family_section,
    "kin": _render_family_section,
    "house": _render_house_section,
    "status": _render_status_section,
}

# Canonical section names shown in the bare-``sheet`` footer (deduped; one per real section).
SECTION_NAMES: tuple[str, ...] = (
    "secret",
    "renown",
    "relationship",
    "standing",
    "covenant",
    "title",
    "crime",
    "distinction",
    "magic",
    "family",
    "house",
    "status",
)
