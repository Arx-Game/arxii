"""
Random Scene service functions.

Handles generating weekly random scene targets, validating claims,
awarding XP, and rerolling targets.
"""

from __future__ import annotations

import datetime
import secrets

from django.db import transaction
from django.utils import timezone
from evennia.accounts.models import AccountDB

from world.progression.constants import RS_BASE_XP, RS_FIRST_TIME_BONUS, RS_PARTNER_XP
from world.progression.models import RandomSceneCompletion, RandomSceneTarget
from world.progression.services.awards import award_xp
from world.progression.types import ProgressionError, ProgressionReason
from world.relationships.models import CharacterRelationship
from world.roster.models import RosterEntry
from world.roster.selectors import get_account_for_character
from world.scenes.constants import PersonaType
from world.scenes.models import Interaction, Persona, SceneParticipation

STRANGER_SLOTS = 3
RELATIONSHIP_SLOTS = 2


def _secure_sample(population: list[int], k: int) -> list[int]:
    """Cryptographically random sample without replacement."""
    if k >= len(population):
        return list(population)
    result: list[int] = []
    pool = list(population)
    for _ in range(k):
        idx = secrets.randbelow(len(pool))
        result.append(pool.pop(idx))
    return result


def _get_active_persona_ids() -> list[int]:
    """Return PRIMARY Persona PKs for characters with an active (current) tenure."""
    active_character_ids = RosterEntry.objects.filter(
        tenures__end_date__isnull=True,
    ).values_list("character_id", flat=True)
    return list(
        Persona.objects.filter(
            character_id__in=active_character_ids,
            persona_type=PersonaType.PRIMARY,
        ).values_list("pk", flat=True)
    )


def _get_own_persona_ids(account: AccountDB) -> list[int]:
    """Return PRIMARY Persona PKs belonging to the account's active roster entries."""
    entries = RosterEntry.objects.for_account(account)
    own_character_ids = list(entries.values_list("character_id", flat=True))
    return list(
        Persona.objects.filter(
            character_id__in=own_character_ids,
            persona_type=PersonaType.PRIMARY,
        ).values_list("pk", flat=True)
    )


def _get_completed_persona_ids(account: AccountDB) -> list[int]:
    """Return Persona PKs this account has already completed RS with."""
    return list(
        RandomSceneCompletion.objects.filter(
            account=account,
        ).values_list("target_persona_id", flat=True)
    )


def _is_first_time(account: AccountDB, target_persona: Persona) -> bool:
    """Return True if no RandomSceneCompletion exists for this account+target persona."""
    return not RandomSceneCompletion.objects.filter(
        account=account,
        target_persona=target_persona,
    ).exists()


def _get_relationship_persona_ids(own_persona_ids: list[int]) -> list[int]:
    """Return PRIMARY Persona PKs that have a CharacterRelationship with own personas' characters.

    CharacterRelationship uses CharacterSheet FKs (source/target), which have
    character_id as PK pointing to ObjectDB. We map from Persona → character_id
    for the query, then back to Persona PKs.
    """
    own_character_ids = list(
        Persona.objects.filter(pk__in=own_persona_ids).values_list("character_id", flat=True)
    )
    # source and target are CharacterSheet FKs where PK = character_id
    source_target_char_ids = CharacterRelationship.objects.filter(
        source__character_id__in=own_character_ids,
    ).values_list("target__character_id", flat=True)
    target_source_char_ids = CharacterRelationship.objects.filter(
        target__character_id__in=own_character_ids,
    ).values_list("source__character_id", flat=True)
    related_char_ids = set(source_target_char_ids) | set(target_source_char_ids)
    # Map back to PRIMARY Persona PKs
    return list(
        Persona.objects.filter(
            character_id__in=related_char_ids,
            persona_type=PersonaType.PRIMARY,
        ).values_list("pk", flat=True)
    )


def _pick_random_from_pool(
    pool: list[int],
    count: int,
    exclude: set[int],
) -> list[int]:
    """Pick up to `count` random IDs from pool, excluding the given IDs."""
    available = [cid for cid in pool if cid not in exclude]
    return _secure_sample(available, min(count, len(available)))


def generate_random_scene_targets(
    account: AccountDB,
    week_start: datetime.date,
) -> list[RandomSceneTarget]:
    """Generate 5 weekly random scene targets for an account.

    Slots 1-3: prefer personas the player has NEVER completed RS with.
    Slots 4-5: prefer personas with an existing CharacterRelationship.
    Falls back to general active pool when not enough candidates.

    Args:
        account: The account to generate targets for.
        week_start: Monday of the RS week.

    Returns:
        List of 5 RandomSceneTarget instances.
    """
    own_ids = _get_own_persona_ids(account)
    active_ids = _get_active_persona_ids()
    completed_ids = set(_get_completed_persona_ids(account))
    own_set = set(own_ids)
    already_picked: set[int] = set()

    # Slots 1-3: strangers (never completed RS with)
    stranger_pool = [pid for pid in active_ids if pid not in own_set and pid not in completed_ids]
    stranger_picks = _pick_random_from_pool(stranger_pool, STRANGER_SLOTS, already_picked)
    already_picked.update(stranger_picks)

    # Fill from general active pool if not enough strangers
    if len(stranger_picks) < STRANGER_SLOTS:
        needed = STRANGER_SLOTS - len(stranger_picks)
        general_pool = [pid for pid in active_ids if pid not in own_set]
        fill_picks = _pick_random_from_pool(general_pool, needed, already_picked)
        stranger_picks.extend(fill_picks)
        already_picked.update(fill_picks)

    # Slots 4-5: personas with relationships
    relationship_ids = _get_relationship_persona_ids(own_ids)
    relationship_pool = [
        pid for pid in relationship_ids if pid in set(active_ids) and pid not in own_set
    ]
    relationship_picks = _pick_random_from_pool(
        relationship_pool, RELATIONSHIP_SLOTS, already_picked
    )
    already_picked.update(relationship_picks)

    # Fill from general active pool if not enough relationships
    if len(relationship_picks) < RELATIONSHIP_SLOTS:
        needed = RELATIONSHIP_SLOTS - len(relationship_picks)
        general_pool = [pid for pid in active_ids if pid not in own_set]
        fill_picks = _pick_random_from_pool(general_pool, needed, already_picked)
        relationship_picks.extend(fill_picks)
        already_picked.update(fill_picks)

    all_picks = stranger_picks + relationship_picks

    # Batch lookups to avoid N+1 queries
    personas_by_id = {p.pk: p for p in Persona.objects.filter(pk__in=all_picks)}
    completed_ids = set(
        RandomSceneCompletion.objects.filter(
            account=account,
            target_persona_id__in=all_picks,
        ).values_list("target_persona_id", flat=True)
    )

    # Create target rows
    targets = RandomSceneTarget.objects.bulk_create(
        [
            RandomSceneTarget(
                account=account,
                target_persona=personas_by_id[persona_id],
                week_start=week_start,
                slot_number=slot_num,
                first_time=persona_id not in completed_ids,
            )
            for slot_num, persona_id in enumerate(all_picks, start=1)
        ]
    )
    RandomSceneTarget.flush_instance_cache()
    return targets


def validate_random_scene_claim(
    account: AccountDB,
    target_persona: Persona,
    week_start: datetime.date,
) -> bool:
    """Check if account and target's account shared a scene or interaction this week.

    Args:
        account: The claimer's account.
        target_persona: The target Persona instance.
        week_start: Monday of the RS week.

    Returns:
        True if shared scene or interaction evidence found this week.
    """
    week_start_dt = datetime.datetime.combine(week_start, datetime.time.min, tzinfo=datetime.UTC)
    week_end_dt = week_start_dt + datetime.timedelta(days=7)

    # Get target character's account via roster
    target_account = get_account_for_character(target_persona.character)
    if target_account is None:
        return False

    # Check 1: shared SceneParticipation (both accounts in same scene this week)
    claimer_scene_ids = SceneParticipation.objects.filter(
        account=account,
        joined_at__gte=week_start_dt,
        joined_at__lt=week_end_dt,
    ).values_list("scene_id", flat=True)

    # Target must also have joined during the same week (prevents claiming via old scenes)
    shared_scene = SceneParticipation.objects.filter(
        account=target_account,
        scene_id__in=claimer_scene_ids,
        joined_at__gte=week_start_dt,
        joined_at__lt=week_end_dt,
    ).exists()

    if shared_scene:
        return True

    # Check 2: shared Interactions in the SAME scene this week (organic RP)
    own_char_ids = list(
        RosterEntry.objects.filter(
            pk__in=RosterEntry.objects.for_account(account).values_list("pk", flat=True),
        ).values_list("character_id", flat=True)
    )
    target_char_id = target_persona.character_id

    own_persona_ids = list(
        Persona.objects.filter(character_id__in=own_char_ids).values_list("pk", flat=True)
    )
    target_persona_ids = list(
        Persona.objects.filter(character_id=target_char_id).values_list("pk", flat=True)
    )

    # Find scenes where own personas have interactions this week
    own_scene_ids = set(
        Interaction.objects.filter(
            persona_id__in=own_persona_ids,
            scene__isnull=False,
            timestamp__gte=week_start_dt,
            timestamp__lt=week_end_dt,
        ).values_list("scene_id", flat=True)
    )

    if not own_scene_ids:
        return False

    # Check if target also has interactions in any of those scenes
    return Interaction.objects.filter(
        persona_id__in=target_persona_ids,
        scene_id__in=own_scene_ids,
        timestamp__gte=week_start_dt,
        timestamp__lt=week_end_dt,
    ).exists()


def claim_random_scene(
    account: AccountDB,
    target_id: int,
    claimer_entry: RosterEntry | None = None,
) -> RandomSceneTarget:
    """Claim a random scene target, awarding XP to both parties.

    Args:
        account: The claimer's account.
        target_id: The RandomSceneTarget PK.
        claimer_entry: The RosterEntry the claimer is playing as. If None,
            uses the account's first active entry.

    Returns:
        The updated RandomSceneTarget.

    Raises:
        ProgressionError: If target not found, already claimed, or no evidence of shared scene.
    """
    with transaction.atomic():
        try:
            target = RandomSceneTarget.objects.select_for_update().get(
                pk=target_id,
                account=account,
            )
        except RandomSceneTarget.DoesNotExist as exc:
            raise ProgressionError(ProgressionError.RS_NOT_FOUND) from exc

        if target.claimed:
            raise ProgressionError(ProgressionError.RS_ALREADY_CLAIMED)

        if not validate_random_scene_claim(account, target.target_persona, target.week_start):
            raise ProgressionError(ProgressionError.RS_NO_EVIDENCE)

        # Resolve claimer entry if not provided
        if claimer_entry is None:
            claimer_entry = RosterEntry.objects.for_account(account).first()
        if claimer_entry is None:
            raise ProgressionError(ProgressionError.RS_NOT_FOUND)

        # Get target character's account
        target_account = get_account_for_character(target.target_persona.character)

        # Award XP to claimer
        claimer_xp = RS_BASE_XP
        if target.first_time:
            claimer_xp += RS_FIRST_TIME_BONUS
        award_xp(
            account=account,
            amount=claimer_xp,
            reason=ProgressionReason.RANDOM_SCENE,
            description=f"Random scene with {target.target_persona.name}",
        )

        # Award XP to target's account
        if target_account is not None:
            award_xp(
                account=target_account,
                amount=RS_PARTNER_XP,
                reason=ProgressionReason.RANDOM_SCENE,
                description="Random scene partner reward",
            )

        # Create completion record
        RandomSceneCompletion.objects.get_or_create(
            account=account,
            target_persona=target.target_persona,
            defaults={"claimer_entry": claimer_entry},
        )

        # Mark as claimed
        target.claimed = True
        target.claimed_at = timezone.now()
        target.save()

        return target


def reroll_random_scene_target(
    account: AccountDB,
    slot_number: int,
    week_start: datetime.date,
) -> RandomSceneTarget:
    """Reroll a single random scene target slot (one reroll per week).

    Uses select_for_update to prevent concurrent reroll race conditions.
    """
    with transaction.atomic():
        try:
            target = RandomSceneTarget.objects.select_for_update().get(
                account=account,
                week_start=week_start,
                slot_number=slot_number,
            )
        except RandomSceneTarget.DoesNotExist as exc:
            raise ProgressionError(ProgressionError.RS_NOT_FOUND) from exc

        if target.claimed:
            raise ProgressionError(ProgressionError.RS_CLAIMED_REROLL)

        # Check if any target this week has already been rerolled
        already_rerolled = RandomSceneTarget.objects.filter(
            account=account,
            week_start=week_start,
            rerolled=True,
        ).exists()

        if already_rerolled:
            raise ProgressionError(ProgressionError.RS_ALREADY_REROLLED)

        # Pick a new random active persona (exclude own + current targets this week)
        own_ids = set(_get_own_persona_ids(account))
        active_ids = _get_active_persona_ids()

        current_target_ids = set(
            RandomSceneTarget.objects.filter(
                account=account,
                week_start=week_start,
            ).values_list("target_persona_id", flat=True)
        )

        exclude = own_ids | current_target_ids
        candidates = [pid for pid in active_ids if pid not in exclude]

        if not candidates:
            raise ProgressionError(ProgressionError.RS_NO_CANDIDATES)

        new_persona_id = secrets.choice(candidates)
        new_persona = Persona.objects.get(pk=new_persona_id)

        target.target_persona = new_persona
        target.first_time = _is_first_time(account, new_persona)
        target.rerolled = True
        target.save()

        return target


def weekly_random_scene_generation_task() -> None:
    """Cron wrapper: generate random scene targets for all active players."""
    today = timezone.now().date()
    week_start = today - datetime.timedelta(days=today.weekday())

    active_accounts = AccountDB.objects.filter(
        player_data__tenures__end_date__isnull=True,
    ).distinct()

    already_generated = set(
        RandomSceneTarget.objects.filter(week_start=week_start)
        .values_list("account_id", flat=True)
        .distinct()
    )

    for account in active_accounts:
        if account.pk in already_generated:
            continue
        generate_random_scene_targets(account, week_start)
