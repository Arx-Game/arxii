"""Anima resource service functions for the magic system."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import IntegrityError, transaction

from world.checks.constants import ModifierLane
from world.checks.modifier_values import level_baseline
from world.magic.models import CharacterAnima
from world.magic.types.ritual import AnimaRegenTickSummary, RitualOutcome

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from evennia.accounts.models import AccountDB
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.magic.models.affinity import Resonance
    from world.magic.models.rituals import Ritual
    from world.roster.models import RosterEntry
    from world.scenes.models import Persona, Scene
    from world.skills.models import Skill
    from world.traits.models import CheckOutcome, Trait

logger = logging.getLogger(__name__)


def deduct_anima(character: ObjectDB, effective_cost: int, *, lethal: bool = True) -> int:
    """Deduct anima from character, returning the overburn deficit.

    Uses select_for_update inside transaction.atomic for race-condition
    safety, following the ActionPointPool.spend() pattern.
    Returns 0 if no overburn, positive int if life force is drawn.

    ``lethal`` defaults to ``True`` so existing callers are unaffected. In a
    NON-LETHAL encounter (``lethal=False``) the effective cost is clamped to the
    caster's currently available anima, so the deduction never draws life force
    past zero and the returned deficit is always ``0`` (no overburn).
    """
    if effective_cost <= 0:
        return 0

    with transaction.atomic():
        anima = CharacterAnima.objects.select_for_update().get(character_id=character.pk)
        if not lethal:
            # Non-lethal: never spend past available anima — no life-force draw.
            effective_cost = min(effective_cost, anima.current + anima.glut)
        # #2853 ruled "spends draw glut first" (the feeding high burns before the
        # real pool); implemented here in #3001 — it was documented but inert.
        from_glut = min(effective_cost, anima.glut)
        remainder = effective_cost - from_glut
        deficit = max(remainder - anima.current, 0)
        anima.glut -= from_glut
        anima.current = max(anima.current - remainder, 0)
        anima.save(update_fields=["current", "glut"])
    return deficit


def recompute_max_anima(character_sheet: CharacterSheet) -> int:
    """Recompute maximum anima from character level (#3001).

    maximum = ``AnimaConfig.level_zero_maximum`` at level < 1, else the ANIMA_POOL lane's
    ``ModifierLevelBaseline`` at that level (#5093). Raising the maximum never fills
    it — ``current`` is untouched on growth (a fresh level is a big empty pool
    begging for ritual, feeding, or blood) and clamped on shrink
    (clamp-not-injure, mirroring ``recompute_max_health``).

    No-op (returns 0) when the sheet has no CharacterAnima row.
    """
    from world.magic.models.anima import AnimaConfig  # noqa: PLC0415
    from world.progression.services.advancement import primary_class_level  # noqa: PLC0415

    try:
        anima = character_sheet.anima
    except CharacterAnima.DoesNotExist:
        return 0

    config = AnimaConfig.get_singleton()
    # No CharacterClassLevel row at all = a true level-0 quiescent (NPCs, sheets
    # mid-CG) — get_character_path_level's default of 1 would wrongly give them
    # a Gifted-sized pool, so detect rowlessness explicitly.
    class_level = primary_class_level(character_sheet.character)
    level = class_level.level if class_level is not None else 0
    new_max = (
        config.level_zero_maximum if level < 1 else level_baseline(level, ModifierLane.ANIMA_POOL)
    )

    update_fields: list[str] = []
    if anima.maximum != new_max:
        anima.maximum = new_max
        update_fields.append("maximum")
    if anima.current > new_max:
        anima.current = new_max
        update_fields.append("current")
    if update_fields:
        anima.save(update_fields=update_fields)
    return new_max


def character_scene_action_rituals(character_id: int) -> QuerySet[Ritual]:
    """The SCENE_ACTION rituals the character knows: her anima ritual (#5280).

    The anima ritual is in character, so it belongs to the character, never to the account
    that plays her: it is the ritual her roster entry has a ``CharacterRitualKnowledge`` row
    for, which creation writes beside the ritual. Takes the character's id (a CharacterSheet
    shares its character's pk), so it works for a character nobody is logged in as.
    """
    from world.magic.constants import RitualExecutionKind  # noqa: PLC0415
    from world.magic.models.rituals import Ritual  # noqa: PLC0415

    return Ritual.objects.filter(
        known_by_records__roster_entry__character_sheet_id=character_id,
        execution_kind=RitualExecutionKind.SCENE_ACTION,
    )


def get_character_anima_ritual(character):  # noqa: OBJECTDB_PARAM — Evennia character
    """The character's own SCENE_ACTION ritual (with check_config), or None."""
    return (
        character_scene_action_rituals(character.pk)
        .select_related("check_config")
        .order_by("pk")
        .first()
    )


def get_character_cast_check(character):  # noqa: OBJECTDB_PARAM — Evennia character
    """The CheckType a character's technique casts roll, or None for fallback."""
    ritual = get_character_anima_ritual(character)
    if ritual is None or not hasattr(ritual, "check_config"):
        return None
    return ritual.check_config.check_type


def ritual_succeeded(outcome: CheckOutcome) -> bool:
    """True when a roll counts as a success for the anima ritual: Partial Success and above.

    The one place the boundary lives (maintainer ruling, 2026-11-22). A success pays its own
    tier's anima budget and resonance award; only Failure and Critical Failure are failures,
    and a failed roll gives no anima and no Primal resonance.
    """
    return outcome.success_level >= 0


def _chosen_patron_share(character_sheet: CharacterSheet, outcome: object) -> tuple[str, int]:
    """(the patron's name, the anima it adds) when the character is a Chosen whose patron favor
    meets the Chosen favor config's threshold: the CHOSEN_ANIMA award for the ritual's result
    (#2550, #4349). ("", 0) otherwise."""
    from world.worship.constants import FavorAwardKind  # noqa: PLC0415
    from world.worship.favor_services import chosen_patronages_for  # noqa: PLC0415
    from world.worship.invocation_services import outcome_award  # noqa: PLC0415
    from world.worship.services import get_chosen_favor_config  # noqa: PLC0415

    patronages = chosen_patronages_for(character_sheet)
    if not patronages or patronages[0].favor < get_chosen_favor_config().anima_recovery_threshold:
        return "", 0
    share = outcome_award(FavorAwardKind.CHOSEN_ANIMA, outcome) or 0  # ty: ignore[invalid-argument-type]
    return patronages[0].being.name, share


def apply_anima_ritual_outcome(  # noqa: PLR0913
    *,
    ritual: Ritual,
    outcome: CheckOutcome,
    scene: Scene,
    character_sheet: CharacterSheet,
    partner_sheet: CharacterSheet | None = None,
    performer_persona: Persona | None = None,
) -> RitualOutcome:
    """Apply a pre-computed check outcome to anima/soulfray + create audit row.

    ``resolve_ritual_request`` (the partner ritual's accepted request) drives the check and
    passes the outcome here.

    Args:
        ritual: The Ritual (SCENE_ACTION kind) being performed.
        outcome: The check outcome / result object (must have success_level).
        scene: The scene in which the ritual is performed.
        character_sheet: The character performing the ritual.
        partner_sheet: The character who took part (#5181), recorded on the performance row.
        performer_persona: The persona the performer wore (the request's initiator persona),
            recorded on the performance row so the partner's card never shows a masked name.

    Returns:
        RitualOutcome describing what was recovered and reduced.
    """
    from world.conditions.models import ConditionInstance  # noqa: PLC0415
    from world.conditions.services import decay_condition_severity  # noqa: PLC0415
    from world.magic.exceptions import RitualAlreadyPerformedThisScene  # noqa: PLC0415
    from world.magic.models.anima import AnimaRitualPerformance  # noqa: PLC0415
    from world.magic.models.soulfray import SoulfrayConfig  # noqa: PLC0415
    from world.magic.services.soulfray import soulfray_condition_id  # noqa: PLC0415

    character = character_sheet.character

    config = SoulfrayConfig.objects.cached_singleton()
    succeeded = ritual_succeeded(outcome)
    # A failed roll gives no anima and eases no Soulfray, whatever the tier's row holds.
    budget = _budget_for_outcome(outcome) if succeeded else 0

    anima = CharacterAnima.objects.select_for_update().get(character=character_sheet)

    # Once per scene must hold when two requests resolve at once: the lock above makes the second
    # wait for the first to commit, and only then does this read, so it sees the first's row.
    if has_performed_anima_ritual_in_scene(ritual=ritual, scene=scene):
        raise RitualAlreadyPerformedThisScene

    soulfray_inst = (
        ConditionInstance.objects.select_for_update()
        .filter(target=character, condition_id=soulfray_condition_id(), resolved_at__isnull=True)
        .first()
    )

    severity_reduced = 0
    soulfray_resolved = False
    stage_after = None
    if soulfray_inst is not None:
        stage_after = soulfray_inst.current_stage
    # checks.CheckType is content-repo-owned (#2698); SoulfrayConfig.
    # resilience_check_type is a required FK, so seed_magic_config() skips the
    # singleton entirely when the "Magical Endurance" CheckType isn't
    # authored — config may legitimately be None here. Severity reduction is
    # skipped gracefully (the anima refill below still applies, and
    # soulfray_stage_after still reports the current stage above) rather than
    # crashing on config.ritual_severity_cost_per_point.
    if soulfray_inst is not None and config is not None:
        while budget >= config.ritual_severity_cost_per_point and soulfray_inst.severity > 0:
            decay_result = decay_condition_severity(soulfray_inst, amount=1)
            severity_reduced += 1
            budget -= config.ritual_severity_cost_per_point
            stage_after = decay_result.new_stage
            if decay_result.resolved:
                soulfray_resolved = True
                break

    # Chosen patronage share (#2550, #4349): the CHOSEN_ANIMA award for the ritual's result,
    # additive to the leftover budget after soulfray reduction, before the anima refill. Both
    # call paths (resolve_ritual_request and _resolve_anima_ritual) converge here.
    patron_name, patron_share = ("", 0)
    if succeeded:
        patron_name, patron_share = _chosen_patron_share(character_sheet, outcome)
    budget += patron_share

    anima_before = anima.current
    anima.current = min(anima.current + max(0, budget), anima.maximum)

    success_level = outcome.success_level
    if success_level >= 2:  # noqa: PLR2004 - chart success degrees
        anima.current = anima.maximum

    anima.save(update_fields=["current"])
    anima_recovered = anima.current - anima_before
    # A critical success refills anima whatever the patron adds, and the patron's share cannot
    # be more than what was recovered: the line the player reads names only what it did.
    patron_bonus = 0 if success_level >= 2 else min(patron_share, anima_recovered)  # noqa: PLR2004

    performance = AnimaRitualPerformance.objects.create(
        ritual=ritual,
        scene=scene,
        was_successful=succeeded,
        anima_recovered=anima_recovered,
        outcome=outcome,
        severity_reduced=severity_reduced,
        target_character=partner_sheet,
        performer_persona=performer_persona,
    )

    return RitualOutcome(
        performance=performance,
        outcome=outcome,
        severity_reduced=severity_reduced,
        anima_recovered=anima_recovered,
        soulfray_stage_after=stage_after,
        soulfray_resolved=soulfray_resolved,
        patron_bonus=patron_bonus,
        patron_name=patron_name if patron_bonus else "",
    )


def _uniquify_ritual_name(base: str) -> str:
    """Return ``base``, or ``base (2)``/``base (3)``/… when the name is taken.

    ``Ritual.name`` is ``unique=True``, and a player's anima ritual name defaults to
    ``"<first name>'s Anima Ritual"`` — so two characters sharing a first name used to
    collide, and because provisioning runs inside character creation's atomic block the
    ``IntegrityError`` rolled back the entire finalization (#2724). Collisions are
    routine rather than exotic, so they are resolved silently instead of surfaced: the
    player never learns that another character took the name.

    Terminates because each candidate is distinct and only finitely many rows exist.
    Truncates the base so a suffixed result still fits ``max_length``.

    NOT race-safe by itself: this does a plain ``SELECT`` and returns — the actual
    ``INSERT`` happens later, in a separate statement, so two concurrent callers can
    both pass this check for the same candidate before either commits (TOCTOU under
    PostgreSQL READ COMMITTED). The retry loop in `provision_player_anima_ritual`'s
    caller is what closes that window; this function only narrows it.
    """
    from world.magic.models.rituals import Ritual  # noqa: PLC0415

    # Django's public-if-underscored model-introspection API.
    max_length = Ritual._meta.get_field("name").max_length  # noqa: SLF001
    candidate = base[:max_length]
    if not Ritual.objects.filter(name=candidate).exists():
        return candidate
    attempt = 2
    while True:
        suffix = f" ({attempt})"
        candidate = f"{base[: max_length - len(suffix)]}{suffix}"
        if not Ritual.objects.filter(name=candidate).exists():
            return candidate
        attempt += 1


# Cap on create-Ritual retries after a name-uniqueness race (#2724 follow-up). Each
# attempt re-samples _uniquify_ritual_name inside its own savepoint (nested
# transaction.atomic()); on IntegrityError the savepoint rolls back cleanly so the
# surrounding finalize_magic_data atomic block stays usable, and the next attempt
# tries again against the now-updated row set. Exhausting every attempt means
# max_length-truncated candidates are colliding faster than we can resolve them — no
# longer "routine" — so the final IntegrityError is deliberately left to propagate
# (see the raise below) rather than silently skipping ritual creation for the player.
_RITUAL_NAME_ATTEMPTS = 5


@transaction.atomic
def provision_player_anima_ritual(  # noqa: PLR0913
    account: AccountDB,
    character_sheet: CharacterSheet,
    roster_entry: RosterEntry,
    *,
    ritual_name: str,
    stat: Trait | None = None,
    skill: Skill | None = None,
    primal_resonance: Resonance | None = None,
    outward_resonance: Resonance | None = None,
) -> Ritual | None:
    """Create a SCENE_ACTION Ritual + sidecar + CharacterRitualKnowledge for a player.

    Called during character creation finalization (Phase 8 §8.1; explicit
    stat/skill wiring #2426). When ``stat``/``skill`` are provided (the
    player's CG Anima Check pick), they are used as-is — no default
    resolution. When omitted (legacy/test-only callers), falls back to
    Willpower for the stat and the character's highest-valued skill (or the
    first active skill) for the skill. Both can be changed post-CG via the
    ritual management UI. Description and narrative prose are derived from
    ``ritual_name``.

    Returns the created Ritual, or None when no suitable stat/skill can be
    resolved (logged as a warning — finalization is not blocked).

    Args:
        account: The player account (author_account on the Ritual).
        character_sheet: The character's CharacterSheet.
        roster_entry: The character's RosterEntry (for CharacterRitualKnowledge).
        ritual_name: Name for the Ritual row (also seeds description/narrative prose).
        stat: Explicit Anima Check stat; falls back to Willpower when None.
        skill: Explicit Anima Check skill; falls back to the character's
            highest-valued skill (or first active skill) when None.
        primal_resonance: The Primal resonance the ritual grows for its performer
            (the CG pick, #5280), written onto the created ``RitualCheckConfig``.
            ``None`` when unset (legacy/test-only callers).
        outward_resonance: The Celestial or Abyssal resonance the ritual reaches for
            in its partner, written onto the same row. ``None`` when unset.
    """
    from world.magic.constants import RitualExecutionKind  # noqa: PLC0415
    from world.magic.models import CharacterRitualKnowledge  # noqa: PLC0415
    from world.magic.models.ritual_check_config import RitualCheckConfig  # noqa: PLC0415
    from world.magic.models.rituals import Ritual  # noqa: PLC0415
    from world.skills.models import Skill  # noqa: PLC0415
    from world.traits.models import Trait, TraitType  # noqa: PLC0415

    character = character_sheet.character

    # 1. Resolve stat — explicit CG pick wins; else default to Willpower.
    stat_trait = stat
    if stat_trait is None:
        try:
            stat_trait = Trait.objects.get(name="willpower", trait_type=TraitType.STAT)
        except Trait.DoesNotExist:
            logger.warning(
                "provision_player_anima_ritual: Willpower stat not found; skipping ritual "
                "creation for character %s",
                character.pk,
            )
            return None

    # 2. Resolve skill — explicit CG pick wins; else the character's highest CG
    #    skill value.
    if skill is None:
        rated = sorted(
            character.traits.get_traits_by_type(TraitType.SKILL).values(),
            key=lambda row: row.value,
            reverse=True,
        )
        skill = next((row.trait for row in rated), None)
        if skill is None:
            # Fallback: first active skill in the database (edge case for test accounts).
            skill = Skill.objects.filter(is_active=True).first()

    if skill is None:
        logger.warning(
            "provision_player_anima_ritual: No skill available; skipping ritual "
            "creation for character %s",
            character.pk,
        )
        return None

    # 3. Create the Ritual row (no service_function_path, no flow — SCENE_ACTION).
    # Description and narrative prose are placeholder text editable post-CG.
    # _uniquify_ritual_name's uniqueness check and this create() are two separate
    # statements, so a concurrent request can pass the check for the same candidate
    # before either commits (#2724 follow-up). Each attempt runs in its own nested
    # transaction.atomic() (a savepoint): a losing IntegrityError rolls back just that
    # savepoint, leaving the outer finalize_magic_data atomic block usable for the next
    # attempt — a bare try/except here would instead poison the whole outer transaction
    # (any further query would raise TransactionManagementError).
    ritual: Ritual | None = None
    for attempt in range(_RITUAL_NAME_ATTEMPTS):
        try:
            with transaction.atomic():
                ritual = Ritual.objects.create(
                    name=_uniquify_ritual_name(ritual_name),
                    description=(
                        "A personal ritual for restoring anima. "
                        "Edit this description to match your character's practice."
                    ),
                    narrative_prose=f"{ritual_name} is performed to restore anima.",
                    execution_kind=RitualExecutionKind.SCENE_ACTION,
                    service_function_path="",
                    author_account=account,
                )
            break
        except IntegrityError:
            if attempt == _RITUAL_NAME_ATTEMPTS - 1:
                # Every retry raced and lost the same name-uniqueness race — deliberately
                # not swallowed: raising is safer than silently skipping ritual creation.
                raise
            continue
    # Unreachable with ritual still None: every loop exit is either `break` (ritual
    # just assigned) or `raise` (propagates, skipping everything below).
    assert ritual is not None  # noqa: S101  # type narrowing for mypy/ty

    # 4. Synthesize the character's personal magic check (#1306) — rolled by this
    # ritual AND by the character's technique casts. Idempotent.
    from world.magic.seeds_checks import (  # noqa: PLC0415
        ensure_character_magic_check_type,
    )

    check_type = ensure_character_magic_check_type(character_sheet, stat=stat_trait, skill=skill)

    RitualCheckConfig.objects.create(
        ritual=ritual,
        stat=stat_trait,
        skill=skill,
        check_type=check_type,
        primal_resonance=primal_resonance,
        outward_resonance=outward_resonance,
    )

    # 5. Grant knowledge so the ritual appears in the scene action menu.
    CharacterRitualKnowledge.objects.get_or_create(
        roster_entry=roster_entry,
        ritual=ritual,
        defaults={"learned_from": None},
    )

    return ritual


def has_performed_anima_ritual_in_scene(
    *,
    ritual: Ritual,
    scene: Scene,
) -> bool:
    """Return True when the given ritual has already been performed in this scene.

    Used by the menu contributor to enforce the once-per-scene cap without
    re-running the full gate logic in ``check_partner_ritual``.
    """
    from world.magic.models.anima import AnimaRitualPerformance  # noqa: PLC0415

    return AnimaRitualPerformance.objects.filter(ritual=ritual, scene=scene).exists()


def anima_ritual_open_in_scene(
    character,  # noqa: OBJECTDB_PARAM — Evennia character
    scene: Scene,
) -> bool:
    """True when the character has an Anima ritual set up and not yet performed in ``scene``.

    One query, so the persona menu can tell the web client whether to offer the ritual (#5181).
    The ritual and the once-per-scene cap are the same ones ``check_partner_ritual`` enforces.
    """
    return (
        character_scene_action_rituals(character.pk)
        .filter(check_config__check_type__isnull=False)
        .exclude(performances__scene=scene)
        .exists()
    )


def _budget_for_outcome(outcome: object) -> int:
    """Return the anima/severity budget for the tier of a roll that counts as a success.

    ``apply_anima_ritual_outcome`` calls this only when ``ritual_succeeded`` is true (Partial
    Success and above), so a Failure or Critical Failure roll never reads its tier's row: those
    two rows hold no meaning (#5280). The success tiers must be seeded (unlike
    GangTurfReputationAward's "missing row = 0" convention): a missing anima budget must not
    silently grant 0 recovery on a legitimate ritual attempt.

    Raises AnimaRitualBudgetAward.DoesNotExist if a success tier has no authored row.
    """
    from world.magic.models.soulfray import AnimaRitualBudgetAward  # noqa: PLC0415

    return AnimaRitualBudgetAward.objects.get(outcome_tier=outcome).budget


def anima_regen_tick() -> AnimaRegenTickSummary:
    """Scheduler entry point. Daily anima regen across all characters.

    Per spec §5.5. Skips engaged characters and characters whose active
    condition stages carry the blocking Property. Skip sets are bulk-
    fetched in 2 queries before the loop to avoid N+1.
    """
    from django.db.models import F  # noqa: PLC0415, I001
    from world.conditions.models import ConditionInstance  # noqa: PLC0415
    from world.magic.models.anima import AnimaConfig  # noqa: PLC0415
    from world.mechanics.engagement import CharacterEngagement  # noqa: PLC0415
    from world.mechanics.models import Property  # noqa: PLC0415

    config = AnimaConfig.get_singleton()
    blocker = Property.objects.get(name=config.daily_regen_blocking_property_key)

    engaged_ids = set(
        CharacterEngagement.objects.values_list("character_id", flat=True),
    )
    # #2853: appetite holders (vampires, dhampir, Vulpi, Vesperi, shades) never
    # regenerate naturally — feeding and anima rituals are their only paths.
    from world.magic.services.appetites import appetite_holder_sheet_ids  # noqa: PLC0415

    appetite_ids = appetite_holder_sheet_ids()
    blocked_ids = set(
        ConditionInstance.objects.filter(
            resolved_at__isnull=True,
            current_stage__properties=blocker,
        )
        .values_list("target_id", flat=True)
        .distinct(),
    )

    qs = CharacterAnima.objects.filter(
        current__lt=F("maximum"),
    ).select_related("character")

    examined = 0
    regenerated = 0
    engagement_blocked = 0
    condition_blocked = 0
    to_update = []

    for row in qs:
        examined += 1
        char_id = row.character_id
        if char_id in engaged_ids:
            engagement_blocked += 1
            continue
        if char_id in blocked_ids:
            condition_blocked += 1
            continue
        if char_id in appetite_ids:
            continue
        # #3001: flat trickle, deliberately painful at scale — a level-20 pool of
        # 2000 refills in years. Anima rituals, feeding, and blood sacrifice are
        # the real recovery economy; this is the floor under all of them.
        if config.daily_regen_amount <= 0:
            continue
        row.current = min(row.current + config.daily_regen_amount, row.maximum)
        to_update.append(row)
        regenerated += 1

    # Bulk update all at once
    if to_update:
        CharacterAnima.objects.bulk_update_with_reason(
            to_update,
            ["current"],
            batch_size=1000,
            reason="issue #3817: intentional bulk write",
        )

    return AnimaRegenTickSummary(
        examined=examined,
        regenerated=regenerated,
        engagement_blocked=engagement_blocked,
        condition_blocked=condition_blocked,
    )
