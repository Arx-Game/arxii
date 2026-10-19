"""Organizations an act names as harmed or helped, and how they react (#4473, #4339).

Authors name organizations where a deed is defined (``NamedOrganization`` rows on a mission
renown award or a LEGEND_AWARD consequence effect). When the deed fires, each named
organization reacts through ``bump_organization_reputation``, the one writer, citing the deed.

A reaction's total is ``sign * base + adjustment``:

- ``base`` is a mission award's per-magnitude amount
  (``RenownMagnitudeAward.named_organization_award``), or a consequence row's base amount
  times the outcome tier's multiplier;
- ``adjustment`` is the deed's archetype vectors against the organization's *effective*
  principles (its override, else its society's value, else 0), times
  ``NAMED_ORG_PRINCIPLE_SCALE``, signed toward approval and capped at half the base;
- the total never crosses zero: a harmed organization stays at or below 0, a helped one at
  or above 0.

The organization's current opinion of the character does not change the size of the reaction,
and a reputation change never makes a character associated with the organization.

A harmed row marked "only if exposed", and any harmed row of an act the scene's reach check
kept quiet, does not react now. It becomes a victim on a secret about the actor, and reacts
if that secret is exposed (``secrets.services.expose_secret``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from types import SimpleNamespace
from typing import TYPE_CHECKING

from world.societies.constants import (
    MAGNITUDE_NAMED_ORGANIZATION_AWARDS,
    NAMED_ORG_PRINCIPLE_SCALE,
    PRINCIPLE_FIELD_NAMES,
    NamedActReach,
    NamedOrganizationRole,
    OrganizationReputationCause,
)
from world.societies.renown import _archetype_dot_product, bump_organization_reputation

if TYPE_CHECKING:
    from world.checks.models import ConsequenceEffect
    from world.missions.models import MissionDeedRecord
    from world.scenes.models import Persona, Scene
    from world.secrets.models import Secret
    from world.societies.models import LegendEntry, NamedOrganization, Organization


@dataclass(frozen=True)
class NamedReaction:
    """One named organization's authored reaction, sized and ready to apply.

    ``base`` is the positive size before the organization's principles adjust it.
    """

    organization: Organization
    role: str
    only_if_exposed: bool
    base: int


def named_organization_bases() -> dict[str, int]:
    """What a mission award of each magnitude pays each named organization, before principles.

    ``RenownMagnitudeAward`` is the staff-tuned table; a tier with no row, or a row that
    leaves the column blank, pays the ``MAGNITUDE_NAMED_ORGANIZATION_AWARDS`` default. One
    query for every tier, so a caller handling several awards reads it once.
    """
    from world.societies.models import RenownMagnitudeAward  # noqa: PLC0415

    bases = dict(MAGNITUDE_NAMED_ORGANIZATION_AWARDS)
    for row in RenownMagnitudeAward.objects.exclude(named_organization_award=None):
        bases[row.magnitude] = int(row.named_organization_award)
    return bases


def named_organization_base(magnitude: str | None) -> int:
    """What a mission award of this magnitude pays each named organization, before principles."""
    return named_organization_bases().get(magnitude, 0) if magnitude else 0


def mission_reactions(
    rows: Sequence[NamedOrganization], magnitude: str, bases: dict[str, int]
) -> list[NamedReaction]:
    """The reactions a mission renown award's named organization rows carry, sized by magnitude.

    The caller loads the rows for all of a route's awards at once (see
    ``emit_terminal_renown_awards``); ``bases`` is ``named_organization_bases()``, read once.
    """
    base = bases.get(magnitude, 0) if magnitude else 0
    return [NamedReaction(row.organization, row.role, row.only_if_exposed, base) for row in rows]


def consequence_reactions(effect: ConsequenceEffect, tier_multiplier: float) -> list[NamedReaction]:
    """The reactions a LEGEND_AWARD effect's named organizations carry.

    Each row's base amount is multiplied by the outcome tier's multiplier
    (``effect_handlers._tier_multiplier``).
    """
    return [
        NamedReaction(
            row.organization,
            row.role,
            row.only_if_exposed,
            round(row.base_amount * tier_multiplier),
        )
        for row in effect.named_organizations.select_related("organization__society")
    ]


def effective_principles(organization: Organization) -> SimpleNamespace:
    """The organization's six principle values, override first, then its society's, else 0."""
    return SimpleNamespace(
        **{name: organization.get_effective_principle(name) for name in PRINCIPLE_FIELD_NAMES}
    )


def principle_adjustment(reaction: NamedReaction, archetypes: Sequence) -> int:
    """The deed's methods against the organization's own principles, capped at half the base.

    Signed toward approval: positive means the organization approves of how it was done.
    """
    if not archetypes:
        return 0
    product = _archetype_dot_product(archetypes, effective_principles(reaction.organization))
    cap = reaction.base // 2
    return max(-cap, min(cap, product * NAMED_ORG_PRINCIPLE_SCALE))


def reaction_total(reaction: NamedReaction, archetypes: Sequence) -> int:
    """The signed reputation change a named organization takes, never across zero."""
    adjustment = principle_adjustment(reaction, archetypes)
    if reaction.role == NamedOrganizationRole.HARMED:
        return min(0, adjustment - reaction.base)
    return max(0, adjustment + reaction.base)


def record_deed_organizations(
    reactions: Sequence[NamedReaction],
    *,
    legend_entry: LegendEntry | None = None,
    mission_deed: MissionDeedRecord | None = None,
) -> None:
    """Store which organizations a deed named, so the contained-secret copy can read them."""
    from world.societies.models import DeedOrganization  # noqa: PLC0415

    for reaction in reactions:
        DeedOrganization.objects.update_or_create(
            legend_entry=legend_entry,
            mission_deed=mission_deed,
            organization=reaction.organization,
            defaults={"role": reaction.role},
        )


def copy_harmed_organizations_to_secret(entry: LegendEntry, secret: Secret) -> None:
    """A contained deed's secret holds the harmed organizations as victims.

    They keep no size of their own: the secret's level decides, as for any victim.
    """
    from world.secrets.services import add_secret_victim  # noqa: PLC0415

    for named in entry.named_organizations.filter(role=NamedOrganizationRole.HARMED).select_related(
        "organization"
    ):
        add_secret_victim(secret, organization=named.organization)


def _secret_level_for(severity: int) -> int:
    """The highest secret level whose default victim hit fits within ``severity``, at least 1."""
    from world.secrets.constants import DEFAULT_VICTIM_SEVERITY_BY_LEVEL  # noqa: PLC0415

    fitting = [lvl for lvl, hit in DEFAULT_VICTIM_SEVERITY_BY_LEVEL.items() if hit <= severity]
    return max(fitting, default=min(DEFAULT_VICTIM_SEVERITY_BY_LEVEL))


def _mint_exposure_secret(  # noqa: PLR0913 - keyword-only; each is a distinct anchor
    persona: Persona,
    harmed: Sequence[tuple[Organization, int]],
    *,
    title: str,
    legend_entry: LegendEntry | None,
    mission_deed: MissionDeedRecord | None,
    scene: Scene | None,
) -> Secret:
    """A secret about the actor that holds each harmed organization as a victim.

    On exposure each organization's reputation of the actor drops by the size the act
    carried (stored as the victim's severity), and the secret's level is the largest fit.
    """
    from world.secrets.constants import SecretProvenance  # noqa: PLC0415
    from world.secrets.services import add_secret_victim, author_secret  # noqa: PLC0415

    secret = author_secret(
        subject_sheet=persona.character_sheet,
        provenance=SecretProvenance.ACTION_ANCHORED,
        level=_secret_level_for(max(severity for _, severity in harmed)),
        content=f"The truth of what happened during '{title}'.",
        legend_deed=legend_entry,
        mission_deed=mission_deed,
        scene=scene,
    )
    for organization, severity in harmed:
        add_secret_victim(secret, organization=organization, severity=severity)
    return secret


def react_to_named_organizations(  # noqa: PLR0913 - keyword-only; each is a distinct input
    *,
    persona: Persona,
    reactions: Sequence[NamedReaction],
    archetypes: Sequence,
    reach: str = NamedActReach.OPEN,
    title: str = "",
    legend_entry: LegendEntry | None = None,
    mission_deed: MissionDeedRecord | None = None,
    scene: Scene | None = None,
) -> dict[int, int]:
    """Apply an act's named-organization reactions; returns ``{organization pk: applied change}``.

    OPEN acts: every reaction applies at once, except a harmed row marked "only if exposed",
    which becomes a victim on a secret about ``persona``. PRIVATE acts: the harmed rows go on
    that secret, helped rows do not react. CONTAINED acts do nothing here (the reach check's
    own secret already holds the harmed organizations, ``copy_harmed_organizations_to_secret``).
    A persona that cannot hold reputation reacts to nothing.
    """
    if reach == NamedActReach.CONTAINED or not persona.is_established_or_primary:
        return {}
    applied: dict[int, int] = {}
    covert: list[tuple[Organization, int]] = []
    for reaction in reactions:
        if reaction.base <= 0:
            continue
        total = reaction_total(reaction, archetypes)
        if total == 0:
            continue
        harmed = reaction.role == NamedOrganizationRole.HARMED
        if harmed and (reaction.only_if_exposed or reach == NamedActReach.PRIVATE):
            covert.append((reaction.organization, -total))
        elif reach == NamedActReach.OPEN:
            before = _current_value(persona, reaction.organization)
            new_value = bump_organization_reputation(
                persona,
                reaction.organization,
                total,
                cause=OrganizationReputationCause.DEED_NAMED,
                legend_entry=legend_entry,
                mission_deed=mission_deed,
            )
            if new_value is not None and new_value != before:
                applied[reaction.organization.pk] = new_value - before
    if covert:
        _mint_exposure_secret(
            persona,
            covert,
            title=title,
            legend_entry=legend_entry,
            mission_deed=mission_deed,
            scene=scene,
        )
    return applied


def _current_value(persona: Persona, organization: Organization) -> int:
    """The persona's reputation value with the organization, 0 when there is no row yet."""
    from world.societies.models import OrganizationReputation  # noqa: PLC0415

    row = OrganizationReputation.objects.filter(persona=persona, organization=organization).first()
    return row.value if row is not None else 0


def _stance(organization: Organization, name: str) -> str | None:
    """One principle as the author sees it: "method -4 (override; society: 1)", else None."""
    override = getattr(organization, f"{name}_override")
    society_value = getattr(organization.society, name) if organization.society_id else None
    if override is not None:
        society = f"society: {society_value}" if society_value is not None else "no society"
        return f"{name} {override} (override; {society})"
    if society_value:
        return f"{name} {society_value} (society value)"
    return None


def _adjustment_working(reaction: NamedReaction, archetypes: Sequence) -> str:
    """The adjustment's arithmetic, one term per axis the deed and the organization share."""
    values = vars(effective_principles(reaction.organization))
    terms = []
    for name in PRINCIPLE_FIELD_NAMES:
        value = values[name]
        if not value:
            continue
        # The dot product through this one axis alone is (deed's axis sum) x (value).
        alone = SimpleNamespace(**{other: value if other == name else 0 for other in values})
        product = _archetype_dot_product(archetypes, alone)
        if product:
            terms.append(f"{product // value} x {value} = {product:+d}")
    if not terms:
        return "+0"
    total = _archetype_dot_product(archetypes, SimpleNamespace(**values))
    scaled = total * NAMED_ORG_PRINCIPLE_SCALE
    return f"{', '.join(terms)}, x {NAMED_ORG_PRINCIPLE_SCALE} = {scaled:+d}"


def estimate_for_staff(named: NamedOrganization) -> str:
    """What a named-organization row would pay, for the admin inline. Staff only.

    Shows the organization's effective principles, then the base, the adjustment's working
    and the total with the tier it moves to from Unknown. A mission row reads the award's
    magnitude and archetypes; a consequence row is shown at the base tier multiplier of 1.0.
    """
    from world.societies.types import ReputationTier  # noqa: PLC0415

    organization = named.organization
    stances = [
        stance
        for name in PRINCIPLE_FIELD_NAMES
        if (stance := _stance(organization, name)) is not None
    ]
    if named.mission_award_id:
        base = named_organization_base(named.mission_award.magnitude)
        archetypes = list(named.mission_award.archetypes.all())
    else:
        base = named.base_amount or 0
        archetypes = []
    reaction = NamedReaction(organization, named.role, named.only_if_exposed, base)
    total = reaction_total(reaction, archetypes)
    tier = ReputationTier.from_value(total).display_name
    sign = -1 if named.role == NamedOrganizationRole.HARMED else 1
    outcome = f"Total {total:+d}: Unknown to {tier}."
    if named.only_if_exposed:
        outcome = (
            f"Total {total:+d} ({tier}), applied only if exposed: recorded as a victim on a "
            "secret about the award holder."
        )
    return (
        f"{'; '.join(stances) or 'No principles'}. "
        f"Base {sign * base:+d}. Adjustment: {_adjustment_working(reaction, archetypes)} "
        f"(cap {base // 2}). {outcome}"
    )
