"""Idempotent deploy/test-DB seeds for the roster app (#2483, #2728).

Invoked by the Big Button seeder (``world.seeds.clusters``) — migrations are
ephemeral pre-production and must contain no data seeding (ADR-0013).
"""

from __future__ import annotations

from typing import NamedTuple

from world.roster.models import Roster
from world.roster.models.choices import RosterType


class RosterSeedSpec(NamedTuple):
    """One shelf's seed defaults. Named fields — the three consecutive booleans
    (``is_active``/``is_public``/``allow_applications``) silently transposed when this
    was a bare positional tuple; a NamedTuple makes each spec self-documenting and
    keyword-constructible."""

    name: str
    description: str
    is_active: bool
    is_public: bool
    allow_applications: bool


_ROSTER_SEED: dict[str, RosterSeedSpec] = {
    RosterType.ACTIVE: RosterSeedSpec(
        name="Active Characters",
        description="Currently played characters.",
        is_active=True,
        is_public=True,
        allow_applications=False,
    ),
    RosterType.AVAILABLE: RosterSeedSpec(
        name="Available Characters",
        description="Characters players may apply for.",
        is_active=True,
        is_public=True,
        allow_applications=True,
    ),
    RosterType.INACTIVE: RosterSeedSpec(
        name="Inactive Characters",
        description="Characters whose player has lapsed.",
        is_active=True,
        is_public=True,
        allow_applications=True,
    ),
    RosterType.PENDING: RosterSeedSpec(
        name="Pending Characters",
        description="Characters awaiting staff approval.",
        is_active=False,
        is_public=False,
        allow_applications=False,
    ),
    RosterType.RESTRICTED: RosterSeedSpec(
        name="Restricted Characters",
        description="Characters requiring special approval to play.",
        is_active=True,
        is_public=True,
        allow_applications=True,
    ),
    RosterType.FROZEN: RosterSeedSpec(
        name="Frozen Characters",
        description="Characters set aside by their player during an OC swap.",
        is_active=True,
        is_public=False,
        allow_applications=False,
    ),
    RosterType.NPC: RosterSeedSpec(
        name="NPCs",
        description="Story and standing NPCs. Never claimable, never swept.",
        is_active=True,
        is_public=False,
        allow_applications=False,
    ),
}


def ensure_rosters() -> dict[str, Roster]:
    """Create every roster shelf exactly once. Idempotent.

    Two seed paths previously created "Active"/"Available" and "Active
    Characters"/"Available Characters" as separate rows, while Inactive,
    Frozen and Restricted were never created at all. This is the single
    source (#2728).

    Returns a mapping of ``RosterType`` value to ``Roster``.
    """
    rosters: dict[str, Roster] = {}
    for roster_type, spec in _ROSTER_SEED.items():
        roster, _created = Roster.objects.get_or_create(
            roster_type=roster_type,
            defaults={
                "name": spec.name,
                "description": spec.description,
                "is_active": spec.is_active,
                "is_public": spec.is_public,
                "allow_applications": spec.allow_applications,
            },
        )
        rosters[roster_type] = roster
    return rosters


def seed_invite_trust_category() -> None:
    """Seed the INVITE TrustCategory for game invite eligibility (#2483).

    ``world.roster.services.invite_services._inviter_meets_trust_threshold``
    looks up this category by name ("INVITE") with a BASIC minimum level.
    Without this row, every invite-creation attempt raises PermissionError
    (the category lookup returns UNTRUSTED when absent). Idempotent via
    ``update_or_create``.
    """
    from world.stories.models import TrustCategory  # noqa: PLC0415

    TrustCategory.objects.update_or_create(
        name="INVITE",
        defaults={
            "display_name": "Game Invites",
            "description": "Can send game invites to friends",
            "is_active": True,
        },
    )


class NPCPresetSeedSpec(NamedTuple):
    """One starter statline preset's authored defaults (#3427).

    ``trait_lines``/``skill_lines`` name their Trait/Skill by the name a
    real content deploy already seeds (the 12 core stats, the Melee
    Combat/Persuasion/Performance/Investigation skill catalog) — a name that
    isn't authored/sampled yet is skipped, not invented, by
    ``ensure_starter_npc_presets``.
    """

    name: str
    description: str
    #: (STAT trait name, display-scale value 1-10).
    trait_lines: tuple[tuple[str, int], ...]
    #: (SKILL name, true 1-100 value).
    skill_lines: tuple[tuple[str, int], ...]


_NPC_PRESET_SEED: tuple[NPCPresetSeedSpec, ...] = (
    NPCPresetSeedSpec(
        name="Guard",
        description=(
            "A trained watchman or house guard — solid in a fight, "
            "unremarkable everywhere else. Staff rewrite freely."
        ),
        trait_lines=(("strength", 3), ("stamina", 3)),
        skill_lines=(("Melee Combat", 25),),
    ),
    NPCPresetSeedSpec(
        name="Courtier",
        description=(
            "A polished court fixture — persuasive and composed under scrutiny. "
            "Staff rewrite freely."
        ),
        trait_lines=(("charm", 3), ("presence", 3)),
        skill_lines=(("Persuasion", 25), ("Performance", 15)),
    ),
    NPCPresetSeedSpec(
        name="Innkeeper",
        description=(
            "A venue-running fixture NPC — personable enough to run a room. Staff rewrite freely."
        ),
        trait_lines=(("charm", 2), ("presence", 2)),
        skill_lines=(("Persuasion", 15),),
    ),
    NPCPresetSeedSpec(
        name="Investigator",
        description=(
            "A sharp-eyed inquirer, good at noticing what others miss. Staff rewrite freely."
        ),
        trait_lines=(("wits", 3), ("perception", 3)),
        skill_lines=(("Investigation", 25),),
    ),
)


def ensure_starter_npc_presets() -> None:
    """Look up (or, under ``SEED_SAMPLE_CONTENT``, invent) the starter preset catalog (#3427).

    ``NPCStatlinePreset`` is content-repo-owned (#2698) — looked up via
    ``authored_or_sample`` rather than invented unless sampling is on. Its
    trait/skill line rows are not themselves in ``CONTENT_MODELS`` (mirrors
    ``skills.Specialization`` under a content-gated parent ``Skill`` — see
    ``combat_checks.ensure_weapon_specializations``), so once a preset exists
    they're created unconditionally via ``get_or_create``, idempotent across
    re-runs. A line whose named Trait/Skill isn't itself authored (or
    sampled) yet is skipped rather than invented — a later re-seed picks it
    up once that Trait/Skill exists.
    """
    from world.roster.models import (  # noqa: PLC0415
        NPCPresetSkillLine,
        NPCPresetTraitLine,
        NPCStatlinePreset,
    )
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415
    from world.skills.models import Skill  # noqa: PLC0415
    from world.traits.models import Trait, TraitType  # noqa: PLC0415

    for spec in _NPC_PRESET_SEED:
        preset = authored_or_sample(
            NPCStatlinePreset, {"description": spec.description}, name=spec.name
        )
        if preset is None:
            continue

        for trait_name, display_value in spec.trait_lines:
            trait = Trait.objects.filter(name__iexact=trait_name, trait_type=TraitType.STAT).first()
            if trait is None:
                continue
            NPCPresetTraitLine.objects.get_or_create(
                preset=preset,
                trait=trait,
                defaults={"display_value": display_value},
            )

        for skill_name, value in spec.skill_lines:
            skill = Skill.objects.filter(trait__name__iexact=skill_name).first()
            if skill is None:
                continue
            NPCPresetSkillLine.objects.get_or_create(
                preset=preset,
                skill=skill,
                defaults={"value": value},
            )
