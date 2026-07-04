"""Scandal reach & containment minting (#1464).

Public reaction is knowledge propagation (the heat shape, #1765): an act
becomes known somewhere, a local filter judges it, consequence accrues. The
filter here is *outrage* — a deed's archetype vectors dot-producted against a
society's six principles, at or below ``SCANDAL_THRESHOLD`` — so "is this a
scandal" is a per-society judgment derived from data rows, never a new
taxonomy (adultery, oath-breaking, dullness-to-the-Nox are all just archetype
rows with the right signs).

At scene-deed birth the fork runs (``route_deed_reach``):

- **Private room** → a scandalous act mints a contained ``Secret`` (actor-
  anchored, act-anchored via #1573, ACTION_ANCHORED provenance) — instant
  blackmail material inside the mystery loop. Witnesses keep their
  ``PersonaDeedKnowledge``; society awareness never fires.
- **Public room, not scandalous** → news: the realm walk's societies become
  aware, reputation fires, spread scales with fame.
- **Public room, scandalous** → a containment check (a declared witness-
  handling approach when one was chosen — the #1824 capability list — else
  the actor's best social tool; difficulty grows with the crowd). Success =
  contained Secret; failure = the scandal leaks (aware + reputation +
  fame-scaled spread). An act-time Stealth declaration (#1824) sheds
  witnesses before the fork; a full concealment success auto-contains.

Mechanics stay tribal: thresholds/difficulties live in constants, never in
player-facing docs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from world.societies.constants import (
    CONCEALMENT_FULL_LEVEL,
    CONCEALMENT_PARTIAL_LEVEL,
    CONTAINMENT_BASE_DIFFICULTY,
    CONTAINMENT_DIFFICULTY_PER_WITNESS,
    FAME_SPREAD_FACTORS,
    SCANDAL_SECRET_LEVEL_FLOORS,
    SCANDAL_THRESHOLD,
)
from world.societies.renown import _archetype_dot_product

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.checks.models import CheckType
    from world.scenes.models import Persona, Scene
    from world.societies.models import LegendEntry, PhilosophicalArchetype, Society


@dataclass(frozen=True)
class DeedReachResult:
    """What the birth fork did with one deed."""

    contained: bool = False
    secret_id: int | None = None
    aware_society_ids: list[int] = field(default_factory=list)
    spread_multiplier: int | None = None
    scandalous: bool = False


def scandalous_societies(
    archetypes: list[PhilosophicalArchetype], societies: list[Society]
) -> dict[int, int]:
    """The societies (pk → dot) that read these archetypes as scandal.

    A strongly negative dot (≤ ``SCANDAL_THRESHOLD``) marks outrage; zero and
    positive reads are news or glory. Empty archetypes → nothing is scandalous
    (missed tags = missed scandals — the library is load-bearing vocabulary).
    """
    if not archetypes:
        return {}
    return {
        society.pk: dot
        for society in societies
        if (dot := _archetype_dot_product(archetypes, society)) <= SCANDAL_THRESHOLD
    }


def _scandal_secret_level(worst_dot: int) -> int:
    """Map how badly the act reads onto the contained Secret's level."""
    magnitude = abs(worst_dot)
    for level, floor in SCANDAL_SECRET_LEVEL_FLOORS:
        if magnitude >= floor:
            return level
    return SCANDAL_SECRET_LEVEL_FLOORS[-1][0]


def _containment_difficulty(witness_count: int) -> int:
    return CONTAINMENT_BASE_DIFFICULTY + CONTAINMENT_DIFFICULTY_PER_WITNESS * witness_count


def _witnesses_are_own_household(actor_persona, witnesses) -> bool:
    """Every witness shares an organization with the actor (and there is at least one).

    The trusted-servants case: containment among your own people is command,
    not deception (Apostate 2026-07-03).
    """
    if not witnesses:
        return False
    from world.societies.models import OrganizationMembership  # noqa: PLC0415

    actor_orgs = set(
        OrganizationMembership.objects.filter(
            persona=actor_persona, left_at__isnull=True, exiled_at__isnull=True
        ).values_list("organization_id", flat=True)
    )
    if not actor_orgs:
        return False
    for witness in witnesses:
        if witness.pk == actor_persona.pk:
            continue
        witness_orgs = set(
            OrganizationMembership.objects.filter(
                persona=witness, left_at__isnull=True, exiled_at__isnull=True
            ).values_list("organization_id", flat=True)
        )
        if not (witness_orgs & actor_orgs):
            return False
    return True


@dataclass(frozen=True)
class WitnessApproach:
    """One entry of the witness-handling capability list (#1824, ratified 2026-07-03).

    ``check_type_name`` of None means the approach resolves between Con and
    Deceive by the actor's stronger social stat (the #1811 charm/presence
    split). ``mints_crime_slug`` marks approaches whose *attempt* is itself a
    crime (bribery — the compounding risk): the deed gets that CrimeKind tag
    at declaration, latent while contained, soaking heat if it ever leaks.
    """

    key: str
    label: str
    check_type_name: str | None
    household_only: bool = False
    mints_crime_slug: str | None = None


# Ordered as ratified on #1824. Extensible: a new tool is a new entry (and a
# seeded CheckType), never a new code path.
WITNESS_APPROACHES: tuple[WitnessApproach, ...] = (
    WitnessApproach(key="intimidation", label="Intimidation", check_type_name="Intimidation"),
    WitnessApproach(key="seduction", label="Seduction", check_type_name="Seduction"),
    WitnessApproach(key="manipulation", label="Manipulation", check_type_name=None),
    WitnessApproach(
        key="bribery", label="Bribery", check_type_name="Bribery", mints_crime_slug="bribery"
    ),
    WitnessApproach(
        key="household",
        label="Household Command",
        check_type_name="Household Command",
        household_only=True,
    ),
)


def _resolve_approach_check_type(approach: WitnessApproach, character) -> CheckType | None:
    """The approach's CheckType row, or None when the world hasn't seeded it."""
    from world.checks.models import CheckType  # noqa: PLC0415

    name = approach.check_type_name
    if name is None:
        # Manipulation ("they didn't see what they saw") is deception — the
        # #1811 split: Con rides charm, Deceive rides presence.
        handler = character.traits
        charm = handler.get_trait_value("charm")
        presence = handler.get_trait_value("presence")
        name = "Con" if charm >= presence else "Deceive"
    return CheckType.objects.filter(name__iexact=name).first()


def witness_approaches_for(character, *, household: bool = False) -> list[WitnessApproach]:
    """The capability list: which witness-handling tools this character can bring.

    One predicate drives visibility AND selectability: an approach is offered
    when its CheckType is seeded (and, for Household Command, when every
    witness is the actor's own household). Social stats are universal, so
    capability shapes the odds, not the menu.
    """
    return [
        approach
        for approach in WITNESS_APPROACHES
        if (household or not approach.household_only)
        and _resolve_approach_check_type(approach, character) is not None
    ]


def _approach_for_key(key: str | None) -> WitnessApproach | None:
    if key is None:
        return None
    for approach in WITNESS_APPROACHES:
        if approach.key == key:
            return approach
    return None


def reduce_witnesses_by_stealth(
    characters: list[ObjectDB], actor_personas: list[Persona], witnesses: list[Persona]
) -> tuple[list[Persona], bool]:
    """Act-time concealment (#1824): roll Stealth against the crowd, shed watchers.

    Group jobs are weakest-link: every acting character rolls and the worst
    result governs. Returns ``(witnesses, fully_concealed)``: a full success
    leaves only the actors in the witness set AND flags the act unwitnessed
    (the reach fork auto-contains — even a public room holds no one who saw);
    a partial sheds half the outsiders; a failure changes nothing. Unseeded
    worlds (no Stealth CheckType) change nothing.
    """
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.checks.services import perform_check  # noqa: PLC0415

    if not characters:
        return witnesses, False
    check_type = CheckType.objects.filter(name__iexact="Stealth").first()
    if check_type is None:
        return witnesses, False
    actor_pks = {actor.pk for actor in actor_personas}
    outsider_count = sum(1 for w in witnesses if w.pk not in actor_pks)
    worst: int | None = None
    for character in characters:
        result = perform_check(
            character,
            check_type,
            target_difficulty=_containment_difficulty(outsider_count),
        )
        level = result.outcome.success_level if result.outcome is not None else 0
        worst = level if worst is None else min(worst, level)
    if worst is None or worst < CONCEALMENT_PARTIAL_LEVEL:
        return witnesses, False
    if worst >= CONCEALMENT_FULL_LEVEL:
        return [w for w in witnesses if w.pk in actor_pks], True
    # Partial: half the outsiders never noticed. Deterministic (pk order) so
    # tests and re-runs agree; which half is flavor, not fairness.
    outsiders = sorted((w for w in witnesses if w.pk not in actor_pks), key=lambda w: w.pk)
    kept_outsiders = outsiders[: len(outsiders) // 2]
    kept_pks = actor_pks | {w.pk for w in kept_outsiders}
    return [w for w in witnesses if w.pk in kept_pks], False


def _run_containment_check(
    character,
    witness_count: int,
    *,
    household: bool = False,
    approach_key: str | None = None,
) -> bool:
    """The hush-it-up roll: a declared tool, or the actor's best one.

    A declared ``approach_key`` (from ``WITNESS_APPROACHES``) resolves to its
    CheckType — the #1824 capability surface. With no declaration (or an
    unknown/unseeded key) the legacy auto-pick stands: own-household witnesses
    → Household Command (you are obeyed, not believed; Apostate 2026-07-03),
    else Con vs Intimidation by the stronger stat. Unseeded worlds fail closed
    (nothing to roll → the scandal leaks).
    """
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.checks.services import perform_check  # noqa: PLC0415

    check_type = None
    declared = _approach_for_key(approach_key)
    if declared is not None and (household or not declared.household_only):
        check_type = _resolve_approach_check_type(declared, character)
    if check_type is None:
        handler = character.traits  # ObjectDB typeclass extension (checks/services idiom)
        charm = handler.get_trait_value("charm")
        presence = handler.get_trait_value("presence")
        if household:
            preferred = "Household Command"
        else:
            preferred = "Con" if charm >= presence else "Intimidation"
        check_type = (
            CheckType.objects.filter(name__iexact=preferred).first()
            or CheckType.objects.filter(name__iexact="Intimidation").first()
            or CheckType.objects.filter(name__iexact="Con").first()
        )
    if check_type is None:
        return False
    result = perform_check(
        character,
        check_type,
        target_difficulty=_containment_difficulty(witness_count),
    )
    return result.outcome is not None and result.outcome.success_level >= 1


def _fame_scaled_multiplier(entry: LegendEntry, personas: list[Persona]) -> int:
    """Spread extent scales with who was involved (Apostate, #1464).

    The highest denormalized fame tier among the involved personas picks the
    factor applied to the config default: a dockworker's brawl caps in the
    ward, an Archduke's adultery goes continental.
    """
    from world.societies.constants import FAME_TIER_ORDER  # noqa: PLC0415

    best = 0
    for persona in personas:
        tier = persona.fame_tier
        if tier in FAME_TIER_ORDER:
            best = max(best, FAME_TIER_ORDER.index(tier))
    factor = FAME_SPREAD_FACTORS.get(FAME_TIER_ORDER[best], 1)
    return entry.spread_multiplier * factor


def _mint_contained_secret(
    entry: LegendEntry, scene: Scene, actor_persona: Persona, worst_dot: int
) -> int | None:
    """The contained branch: the truth exists, held close — blackmail material.

    ACTION_ANCHORED provenance + scene/deed anchors satisfy ``Secret.clean()``;
    archetypes copy across so a later ``expose_secret`` fires the same
    reputation math the leak would have. Content template approved (2026-07-03).
    """
    from world.secrets.services import SecretError, author_secret  # noqa: PLC0415

    sheet = actor_persona.character_sheet
    if sheet is None:
        return None
    from world.secrets.constants import SecretProvenance  # noqa: PLC0415

    try:
        secret = author_secret(
            subject_sheet=sheet,
            provenance=SecretProvenance.ACTION_ANCHORED,
            level=_scandal_secret_level(worst_dot),
            content=f"The truth of what happened during '{entry.title}'.",
            legend_deed=entry,
            scene=scene,
        )
    except SecretError:
        return None
    secret.archetypes.set(entry.archetypes.all())
    return secret.pk


def _tag_approach_crime(entry: LegendEntry, approach: WitnessApproach) -> None:
    """Bribery's compounding risk: the attempt itself is a crime (#1824).

    Tagged at declaration, before the roll — a contained scandal keeps the tag
    latent (heat only accrues as knowledge spreads), a leak compounds. Missing
    seed rows are a silent no-op (unseeded worlds have no law to break).
    """
    from world.justice.models import CrimeKind  # noqa: PLC0415
    from world.justice.services import tag_deed_crimes  # noqa: PLC0415

    kind = CrimeKind.objects.filter(slug=approach.mints_crime_slug).first()
    if kind is not None:
        tag_deed_crimes(entry, [kind])


def route_deed_reach(  # noqa: PLR0913
    *,
    entry: LegendEntry,
    scene: Scene | None,
    actor_persona: Persona,
    witnesses: list[Persona],
    containment_approach: str | None = None,
    fully_concealed: bool = False,
) -> DeedReachResult:
    """The #1464 birth fork. Called after witness knowledge is granted.

    No scene, no room, or an untagged deed → legacy no-op (nothing minted,
    nothing aware — exactly the pre-#1464 behavior). ``containment_approach``
    (#1824) is a declared ``WitnessApproach.key``; None keeps the auto-pick.
    ``fully_concealed`` (#1824) is the act-time Stealth full success: nobody
    saw, so a scandal auto-contains without a hush-up roll. (An empty witness
    list alone does NOT auto-contain — a public room holds an ambient crowd.)
    """
    from evennia_extensions.models import room_is_publicly_listed  # noqa: PLC0415
    from world.areas.services import societies_for_scene  # noqa: PLC0415
    from world.societies.renown import apply_archetype_society_reputation  # noqa: PLC0415

    if scene is None or scene.location is None:
        return DeedReachResult()
    archetypes = list(entry.archetypes.all())
    if not archetypes:
        return DeedReachResult()
    societies = societies_for_scene(scene)
    if not societies:
        return DeedReachResult()

    scandal_dots = scandalous_societies(archetypes, societies)
    is_public = room_is_publicly_listed(scene.location)

    if scandal_dots:
        declared = _approach_for_key(containment_approach)
        needs_hush = is_public and not fully_concealed
        if declared is not None and declared.mints_crime_slug and needs_hush:
            # Only a *used* tool mints the crime — a private or fully
            # concealed act never reached the bribing stage.
            _tag_approach_crime(entry, declared)
        contained = not needs_hush or _run_containment_check(
            actor_persona.character_sheet.character,
            len(witnesses),
            household=_witnesses_are_own_household(actor_persona, witnesses),
            approach_key=containment_approach,
        )
        if contained:
            worst = min(scandal_dots.values())
            secret_id = _mint_contained_secret(entry, scene, actor_persona, worst)
            return DeedReachResult(contained=True, secret_id=secret_id, scandalous=True)
    elif not is_public:
        # Private and unremarkable: nothing to mint, nothing to spread.
        return DeedReachResult()

    # The act is out — news or leaked scandal: awareness, reputation, spread.
    entry.societies_aware.set(societies)
    multiplier = _fame_scaled_multiplier(entry, [actor_persona, *witnesses])
    if multiplier != entry.spread_multiplier:
        entry.spread_multiplier = multiplier
        entry.save(update_fields=["spread_multiplier"])
    apply_archetype_society_reputation(actor_persona, societies, archetypes)
    return DeedReachResult(
        aware_society_ids=[society.pk for society in societies],
        spread_multiplier=multiplier,
        scandalous=bool(scandal_dots),
    )
