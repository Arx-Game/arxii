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
from evennia.objects.models import ObjectDB

from world.progression.models import RandomSceneCompletion, RandomSceneTarget
from world.progression.services.awards import award_xp
from world.progression.types import ProgressionReason
from world.relationships.models import CharacterRelationship
from world.roster.models import RosterEntry, RosterTenure
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


def _get_account_for_character(character: ObjectDB) -> AccountDB | None:
    """Get the account currently playing a character, via roster tenure."""
    tenure = (
        RosterTenure.objects.filter(
            roster_entry__character=character,
            end_date__isnull=True,
        )
        .select_related("player_data__account")
        .first()
    )
    if tenure is None:
        return None
    return tenure.player_data.account


def _get_active_character_ids() -> list[int]:
    """Return IDs of characters with a current (active) roster tenure."""
    return list(
        RosterTenure.objects.filter(
            end_date__isnull=True,
        ).values_list("roster_entry__character_id", flat=True)
    )


def _get_own_character_ids(account: AccountDB) -> list[int]:
    """Return character IDs belonging to the account's roster entries."""
    entries = RosterEntry.objects.for_account(account)
    return list(entries.values_list("character_id", flat=True))


def _get_completed_character_ids(account: AccountDB) -> list[int]:
    """Return character IDs this account has already completed RS with."""
    return list(
        RandomSceneCompletion.objects.filter(
            account=account,
        ).values_list("target_character_id", flat=True)
    )


def _is_first_time(account: AccountDB, target_character: ObjectDB) -> bool:
    """Return True if no RandomSceneCompletion exists for this account+target."""
    return not RandomSceneCompletion.objects.filter(
        account=account,
        target_character=target_character,
    ).exists()


def _get_relationship_character_ids(own_character_ids: list[int]) -> list[int]:
    """Return character IDs that have a CharacterRelationship with any of the given characters.

    CharacterRelationship uses CharacterSheet FKs (source/target), which have
    character_id as PK pointing to ObjectDB.
    """
    # source and target are CharacterSheet FKs where PK = character_id
    source_targets = CharacterRelationship.objects.filter(
        source__character_id__in=own_character_ids,
    ).values_list("target__character_id", flat=True)
    target_sources = CharacterRelationship.objects.filter(
        target__character_id__in=own_character_ids,
    ).values_list("source__character_id", flat=True)
    return list(set(source_targets) | set(target_sources))


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

    Slots 1-3: prefer characters the player has NEVER completed RS with.
    Slots 4-5: prefer characters with an existing CharacterRelationship.
    Falls back to general active pool when not enough candidates.

    Args:
        account: The account to generate targets for.
        week_start: Monday of the RS week.

    Returns:
        List of 5 RandomSceneTarget instances.
    """
    own_ids = _get_own_character_ids(account)
    active_ids = _get_active_character_ids()
    completed_ids = set(_get_completed_character_ids(account))
    own_set = set(own_ids)
    already_picked: set[int] = set()

    # Slots 1-3: strangers (never completed RS with)
    stranger_pool = [cid for cid in active_ids if cid not in own_set and cid not in completed_ids]
    stranger_picks = _pick_random_from_pool(stranger_pool, STRANGER_SLOTS, already_picked)
    already_picked.update(stranger_picks)

    # Fill from general active pool if not enough strangers
    if len(stranger_picks) < STRANGER_SLOTS:
        needed = STRANGER_SLOTS - len(stranger_picks)
        general_pool = [cid for cid in active_ids if cid not in own_set]
        fill_picks = _pick_random_from_pool(general_pool, needed, already_picked)
        stranger_picks.extend(fill_picks)
        already_picked.update(fill_picks)

    # Slots 4-5: characters with relationships
    relationship_ids = _get_relationship_character_ids(own_ids)
    relationship_pool = [
        cid for cid in relationship_ids if cid in set(active_ids) and cid not in own_set
    ]
    relationship_picks = _pick_random_from_pool(
        relationship_pool, RELATIONSHIP_SLOTS, already_picked
    )
    already_picked.update(relationship_picks)

    # Fill from general active pool if not enough relationships
    if len(relationship_picks) < RELATIONSHIP_SLOTS:
        needed = RELATIONSHIP_SLOTS - len(relationship_picks)
        general_pool = [cid for cid in active_ids if cid not in own_set]
        fill_picks = _pick_random_from_pool(general_pool, needed, already_picked)
        relationship_picks.extend(fill_picks)
        already_picked.update(fill_picks)

    all_picks = stranger_picks + relationship_picks

    # Create target rows
    targets: list[RandomSceneTarget] = []
    for slot_num, char_id in enumerate(all_picks, start=1):
        target_char = ObjectDB.objects.get(pk=char_id)
        first_time = _is_first_time(account, target_char)
        target = RandomSceneTarget.objects.create(
            account=account,
            target_character=target_char,
            week_start=week_start,
            slot_number=slot_num,
            first_time=first_time,
        )
        targets.append(target)

    return targets


def validate_random_scene_claim(
    account: AccountDB,
    target_character: ObjectDB,
    week_start: datetime.date,
) -> bool:
    """Check if account and target's account shared a scene or interaction this week.

    Args:
        account: The claimer's account.
        target_character: The target character ObjectDB instance.
        week_start: Monday of the RS week.

    Returns:
        True if shared scene or interaction evidence found this week.
    """
    week_start_dt = datetime.datetime.combine(week_start, datetime.time.min, tzinfo=datetime.UTC)
    week_end_dt = week_start_dt + datetime.timedelta(days=7)

    # Get target character's account via roster
    target_account = _get_account_for_character(target_character)
    if target_account is None:
        return False

    # Check 1: shared SceneParticipation (both accounts in same scene this week)
    claimer_scene_ids = SceneParticipation.objects.filter(
        account=account,
        joined_at__gte=week_start_dt,
        joined_at__lt=week_end_dt,
    ).values_list("scene_id", flat=True)

    shared_scene = SceneParticipation.objects.filter(
        account=target_account,
        scene_id__in=claimer_scene_ids,
    ).exists()

    if shared_scene:
        return True

    # Check 2: shared Interactions via Personas this week
    own_ids = _get_own_character_ids(account)
    target_ids = [target_character.pk]

    own_persona_ids = list(
        Persona.objects.filter(character_id__in=own_ids).values_list("pk", flat=True)
    )
    target_persona_ids = list(
        Persona.objects.filter(character_id__in=target_ids).values_list("pk", flat=True)
    )

    # Check if both have interactions this week (organic RP)
    own_has_interactions = Interaction.objects.filter(
        persona_id__in=own_persona_ids,
        timestamp__gte=week_start_dt,
        timestamp__lt=week_end_dt,
    ).exists()

    target_has_interactions = Interaction.objects.filter(
        persona_id__in=target_persona_ids,
        timestamp__gte=week_start_dt,
        timestamp__lt=week_end_dt,
    ).exists()

    if own_has_interactions and target_has_interactions:
        return True

    return False


def claim_random_scene(
    account: AccountDB,
    target_id: int,
) -> RandomSceneTarget:
    """Claim a random scene target, awarding XP to both parties.

    Args:
        account: The claimer's account.
        target_id: The RandomSceneTarget PK.

    Returns:
        The updated RandomSceneTarget.

    Raises:
        ValueError: If target not found, already claimed, or no evidence of shared scene.
    """
    with transaction.atomic():
        try:
            target = RandomSceneTarget.objects.select_for_update().get(
                pk=target_id,
                account=account,
            )
        except RandomSceneTarget.DoesNotExist as exc:
            msg = "Random scene target not found for this account"
            raise ValueError(msg) from exc

        if target.claimed:
            msg = "Target already claimed"
            raise ValueError(msg)

        if not validate_random_scene_claim(account, target.target_character, target.week_start):
            msg = "No evidence of shared scene or interaction this week"
            raise ValueError(msg)

        # Get target character's account
        target_account = _get_account_for_character(target.target_character)

        # Award XP to claimer
        claimer_xp = 5
        if target.first_time:
            claimer_xp += 10
        award_xp(
            account=account,
            amount=claimer_xp,
            reason=ProgressionReason.RANDOM_SCENE,
            description=f"Random scene with {target.target_character}",
        )

        # Award XP to target's account
        if target_account is not None:
            award_xp(
                account=target_account,
                amount=5,
                reason=ProgressionReason.RANDOM_SCENE,
                description="Random scene partner reward",
            )

        # Create completion record
        RandomSceneCompletion.objects.get_or_create(
            account=account,
            target_character=target.target_character,
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

    Args:
        account: The account requesting the reroll.
        slot_number: The slot number (1-5) to reroll.
        week_start: Monday of the RS week.

    Returns:
        The updated RandomSceneTarget.

    Raises:
        ValueError: If target not found, already rerolled this week, or no candidates.
    """
    try:
        target = RandomSceneTarget.objects.get(
            account=account,
            week_start=week_start,
            slot_number=slot_number,
        )
    except RandomSceneTarget.DoesNotExist as exc:
        msg = "Random scene target not found for this slot"
        raise ValueError(msg) from exc

    # Check if any target this week has already been rerolled
    already_rerolled = RandomSceneTarget.objects.filter(
        account=account,
        week_start=week_start,
        rerolled=True,
    ).exists()

    if already_rerolled:
        msg = "Already used reroll this week"
        raise ValueError(msg)

    # Pick a new random active character (exclude own + current targets this week)
    own_ids = set(_get_own_character_ids(account))
    active_ids = _get_active_character_ids()

    current_target_ids = set(
        RandomSceneTarget.objects.filter(
            account=account,
            week_start=week_start,
        ).values_list("target_character_id", flat=True)
    )

    exclude = own_ids | current_target_ids
    candidates = [cid for cid in active_ids if cid not in exclude]

    if not candidates:
        msg = "No available characters to reroll to"
        raise ValueError(msg)

    new_char_id = secrets.choice(candidates)
    new_char = ObjectDB.objects.get(pk=new_char_id)

    target.target_character = new_char
    target.first_time = _is_first_time(account, new_char)
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

    for account in active_accounts:
        # Skip if already generated this week
        if RandomSceneTarget.objects.filter(account=account, week_start=week_start).exists():
            continue
        generate_random_scene_targets(account, week_start)
