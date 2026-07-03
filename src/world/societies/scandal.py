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
- **Public room, scandalous** → a containment check (best of the actor's
  social tools; difficulty grows with the crowd). Success = contained Secret;
  failure = the scandal leaks (aware + reputation + fame-scaled spread).

Mechanics stay tribal: thresholds/difficulties live in constants, never in
player-facing docs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from world.societies.constants import (
    CONTAINMENT_BASE_DIFFICULTY,
    CONTAINMENT_DIFFICULTY_PER_WITNESS,
    FAME_SPREAD_FACTORS,
    SCANDAL_SECRET_LEVEL_FLOORS,
    SCANDAL_THRESHOLD,
)
from world.societies.renown import _archetype_dot_product

if TYPE_CHECKING:
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


def _run_containment_check(character, witness_count: int, *, household: bool = False) -> bool:
    """The hush-it-up roll: the actor's best social tool against the crowd size.

    Own-household witnesses → Household Command (presence + Leadership +
    Stewardship — you are obeyed, not believed; Apostate 2026-07-03).
    Otherwise auto-picks between Con (charm + Persuasion + Manipulation) and
    Intimidation (presence + Persuasion + Intimidation) by the stronger stat —
    "a range of skills based on character capability"; the interactive
    approach-fanned surface is a later slice. Unseeded worlds fail closed
    (nothing to roll → the scandal leaks).
    """
    from world.checks.models import CheckType  # noqa: PLC0415
    from world.checks.services import perform_check  # noqa: PLC0415

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


def route_deed_reach(
    *,
    entry: LegendEntry,
    scene: Scene | None,
    actor_persona: Persona,
    witnesses: list[Persona],
) -> DeedReachResult:
    """The #1464 birth fork. Called after witness knowledge is granted.

    No scene, no room, or an untagged deed → legacy no-op (nothing minted,
    nothing aware — exactly the pre-#1464 behavior).
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
        contained = not is_public or _run_containment_check(
            actor_persona.character_sheet.character,
            len(witnesses),
            household=_witnesses_are_own_household(actor_persona, witnesses),
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
