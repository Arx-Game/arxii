"""Gossip — the casual, regional Level-1-secret spread mechanic (#1572).

Three Gossip-check actions, performed **at a social hub**, operating on per-``(secret, region)``
heat (``SecretGossip``):

- **plant** — a character who has *come into* a Level-1 secret spreads it, raising regional heat.
- **seek** — a seeker rolls to surface a hot (``heat >= 1``) secret they don't yet know.
- **suppress** — lower a secret's heat (the only path back to 0; decay alone floors at 1).

The check is the seeded **Gossip** CheckType (charm + Persuasion + the Gossip specialization), so a
character's Gossip spec folds into the roll automatically (the #1688 engine). Use is gated on
**Gossip >= 1** and on standing in a ``RoomProfile.is_social_hub`` room. At the public threshold a
secret goes ambient and is exposed to the region's societies (one-shot). All magnitudes are
PLACEHOLDER (see ``constants``). This is the pre-exposure, skill-gated tier — distinct from the
formal ``expose_secret`` / tidings path.
"""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import TYPE_CHECKING

from world.secrets.constants import (
    GOSSIP_CHECK_TYPE_NAME,
    GOSSIP_DECAY_FLOOR,
    GOSSIP_PLANT_REGULAR,
    GOSSIP_PLANT_SPECIAL,
    GOSSIP_PUBLIC_THRESHOLD,
    GOSSIP_SPECIAL_SUCCESS_LEVEL,
    GOSSIP_SUPPRESS_REGULAR,
    GOSSIP_SUPPRESS_SPECIAL,
    SecretLevel,
)
from world.secrets.models import Secret, SecretGossip, SecretKnowledge
from world.secrets.services import grant_secret_knowledge

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.areas.models import Area


_NOT_HUB = "You can only work the rumor mill at a social hub."
_NO_REGION = "This place isn't part of any region."
_NO_SKILL = "You don't have the ear for it (requires Gossip 1+)."
_NOT_LEVEL_1 = "Only the lightest secrets travel as idle gossip."
_NOT_HELD = "You can only spread gossip you've actually come into."


class GossipError(Exception):
    """A gossip action could not proceed (carries a user-facing message)."""

    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


@dataclass(frozen=True)
class GossipResult:
    """Outcome of a gossip action (#1572).

    ``success`` = the check landed and changed something; ``heat`` = the secret's resulting regional
    heat (0 for a seek that found nothing); ``surfaced_secret_id`` is set for a successful seek.
    """

    success: bool
    heat: int = 0
    went_public: bool = False
    surfaced_secret_id: int | None = None


# --- resolution helpers -------------------------------------------------------------------


def _gossip_check_type():
    from world.checks.models import CheckType  # noqa: PLC0415

    return CheckType.objects.get(name=GOSSIP_CHECK_TYPE_NAME, category__name="Social")


def _gossip_specialization():
    from world.skills.models import Specialization  # noqa: PLC0415

    return Specialization.objects.get(name="Gossip", parent_skill__trait__name="Persuasion")


def _region_for_room(room: ObjectDB) -> Area | None:
    from world.areas.constants import AreaLevel  # noqa: PLC0415
    from world.areas.services import get_ancestor_at_level, get_room_profile  # noqa: PLC0415

    profile = get_room_profile(room)
    if profile.area is None:
        return None
    return get_ancestor_at_level(profile.area, AreaLevel.REGION)


def _require_hub_region(room: ObjectDB) -> Area:
    """The room must be a social hub in a region; returns that region or raises GossipError."""
    from world.areas.services import get_room_profile  # noqa: PLC0415

    if not get_room_profile(room).is_social_hub:
        raise GossipError(_NOT_HUB)
    region = _region_for_room(room)
    if region is None:
        raise GossipError(_NO_REGION)
    return region


def _require_gossip_skill(character: ObjectDB) -> None:
    from world.skills.services import has_specialization  # noqa: PLC0415

    if not has_specialization(character, _gossip_specialization(), minimum_rank=1):
        raise GossipError(_NO_SKILL)


def _roster_entry(character: ObjectDB):
    from world.roster.models import RosterEntry  # noqa: PLC0415

    sheet = character.sheet_data  # type: ignore[attr-defined] — ObjectDB typeclass extension
    return RosterEntry.objects.filter(character_sheet=sheet).first()


def _check_tier(character: ObjectDB) -> int:
    """Run the Gossip check; return its ``success_level`` (>=1 success, >=2 special)."""
    from world.checks.services import perform_check  # noqa: PLC0415

    return perform_check(character, _gossip_check_type()).success_level


def _delta_for(tier: int, regular: int, special: int) -> int:
    if tier >= GOSSIP_SPECIAL_SUCCESS_LEVEL:
        return special
    if tier >= 1:
        return regular
    return 0


def _maybe_go_public(row: SecretGossip) -> None:
    """At/above the public threshold, expose the secret to the region's societies (one-shot)."""
    if row.went_public or row.heat < GOSSIP_PUBLIC_THRESHOLD:
        return
    from world.secrets.services import expose_secret  # noqa: PLC0415

    societies = _societies_for_region(row.region)
    if societies:
        expose_secret(row.secret, societies=societies)
    row.went_public = True
    row.save(update_fields=["went_public", "updated_date"])


def _societies_for_region(region: Area) -> list:
    """Societies that match a region — dominant society if set, else all sharing its realm.

    Mirrors ``world.areas.services.societies_for_scene``'s precedence at the region tier.
    """
    from world.societies.models import Society  # noqa: PLC0415

    if region.dominant_society_id:
        return [region.dominant_society]
    if region.realm_id is None:
        return []
    return list(Society.objects.filter(realm_id=region.realm_id))


# --- actions ------------------------------------------------------------------------------


def plant_gossip(character: ObjectDB, secret: Secret, *, room: ObjectDB) -> GossipResult:
    """Spread a Level-1 secret you've come into, raising its regional heat (#1572).

    Guards: Gossip >= 1, standing in a social hub, the secret is Level-1, and you **hold** it
    (``SecretKnowledge``) or it is **about you** (self-seeded gossip). A regular success adds
    ``GOSSIP_PLANT_REGULAR`` heat, a special success ``GOSSIP_PLANT_SPECIAL`` (by anyone, no cap).
    """
    _require_gossip_skill(character)
    region = _require_hub_region(room)
    if secret.level != SecretLevel.UNCOMMON_KNOWLEDGE:
        raise GossipError(_NOT_LEVEL_1)
    if not _can_spread(character, secret):
        raise GossipError(_NOT_HELD)

    delta = _delta_for(_check_tier(character), GOSSIP_PLANT_REGULAR, GOSSIP_PLANT_SPECIAL)
    row, _ = SecretGossip.objects.get_or_create(secret=secret, region=region)
    if delta:
        row.heat += delta
        row.save(update_fields=["heat", "updated_date"])
        _maybe_go_public(row)
    return GossipResult(
        success=delta > 0,
        heat=row.heat,
        went_public=row.went_public,
        surfaced_secret_id=secret.pk,
    )


def seek_gossip(character: ObjectDB, *, room: ObjectDB) -> GossipResult:
    """Roll to overhear a hot Level-1 secret in this region you don't yet know (#1572).

    Surfaces a ``heat >= 1`` secret (weighted by heat) the seeker doesn't already hold; on success
    grants the **fact only** (never category/consequences). Empty result on a miss or empty
    empty pool.
    """
    _require_gossip_skill(character)
    region = _require_hub_region(room)
    if _check_tier(character) < 1:
        return GossipResult(success=False)

    entry = _roster_entry(character)
    if entry is None:
        return GossipResult(success=False)
    known_ids = SecretKnowledge.objects.filter(roster_entry=entry).values_list(
        "secret_id", flat=True
    )
    pool = list(
        SecretGossip.objects.filter(
            region=region, heat__gte=1, secret__level=SecretLevel.UNCOMMON_KNOWLEDGE
        )
        .exclude(secret_id__in=known_ids)
        .select_related("secret")
    )
    if not pool:
        return GossipResult(success=False)
    chosen = random.choices(pool, weights=[row.heat for row in pool], k=1)[0]  # noqa: S311
    grant_secret_knowledge(roster_entry=entry, secret=chosen.secret)
    return GossipResult(success=True, heat=chosen.heat, surfaced_secret_id=chosen.secret_id)


def suppress_gossip(character: ObjectDB, secret: Secret, *, room: ObjectDB) -> GossipResult:
    """Talk a Level-1 secret's heat down — the only path back to 0 (#1572).

    Regular success removes ``GOSSIP_SUPPRESS_REGULAR`` heat, special ``GOSSIP_SUPPRESS_SPECIAL``;
    floored at 0 (decay alone only reaches ``GOSSIP_DECAY_FLOOR``).
    """
    _require_gossip_skill(character)
    region = _require_hub_region(room)
    row = SecretGossip.objects.filter(secret=secret, region=region).first()
    if row is None or row.heat == 0:
        return GossipResult(success=False, heat=0)
    delta = _delta_for(_check_tier(character), GOSSIP_SUPPRESS_REGULAR, GOSSIP_SUPPRESS_SPECIAL)
    if delta:
        row.heat = max(0, row.heat - delta)
        row.save(update_fields=["heat", "updated_date"])
    return GossipResult(success=delta > 0, heat=row.heat, went_public=row.went_public)


def gossip_decay_tick() -> int:
    """Daily tick: decay every gossip's heat by 1 toward the floor (#1572). Returns rows touched.

    A secret that has ever been gossiped lingers findable at ``GOSSIP_DECAY_FLOOR`` — only active
    suppression takes it to 0. Registered as a daily ``game_clock`` task.
    """
    from django.db.models import F  # noqa: PLC0415

    return SecretGossip.objects.filter(heat__gt=GOSSIP_DECAY_FLOOR).update(heat=F("heat") - 1)


def has_gossip_skill(character: ObjectDB) -> bool:
    """Whether a character has Gossip >= 1 (the surface-eligibility gate, #1572)."""
    from world.skills.services import has_specialization  # noqa: PLC0415

    return has_specialization(character, _gossip_specialization(), minimum_rank=1)


def spreadable_secrets(character: ObjectDB) -> list[Secret]:
    """The Level-1 secrets a character may spread as gossip — ones they own or hold (#1572).

    Self-secrets (you may always gossip about yourself) plus the Level-1 secrets you've come into
    (`SecretKnowledge`), deduped. The plant/suppress surfaces number this list.
    """
    sheet = character.sheet_data  # type: ignore[attr-defined] — ObjectDB typeclass extension
    owned = Secret.objects.filter(subject_sheet=sheet, level=SecretLevel.UNCOMMON_KNOWLEDGE)
    entry = _roster_entry(character)
    held_ids = (
        list(SecretKnowledge.objects.filter(roster_entry=entry).values_list("secret_id", flat=True))
        if entry is not None
        else []
    )
    held = Secret.objects.filter(pk__in=held_ids, level=SecretLevel.UNCOMMON_KNOWLEDGE)
    seen: set[int] = set()
    result: list[Secret] = []
    for secret in [*owned, *held]:
        if secret.pk not in seen:
            seen.add(secret.pk)
            result.append(secret)
    return result


def region_heat_for(secret: Secret, *, room: ObjectDB) -> int:
    """Current gossip heat for a secret in the room's region (0 if none / no region) (#1572)."""
    region = _region_for_room(room)
    if region is None:
        return 0
    row = SecretGossip.objects.filter(secret=secret, region=region).first()
    return row.heat if row is not None else 0


def public_gossip_lines(room: ObjectDB, *, limit: int = 3) -> list[str]:
    """Source-ambiguous ambient lines for a hub room's *public* gossip (#1572).

    Empty unless the room is a social hub (the cheap ``is_social_hub`` check short-circuits before
    any region resolution, so non-hub rooms — the overwhelming majority — never touch the region
    closure). For a hub, returns what an arriving character overhears as common knowledge: the
    ``went_public`` secrets of the room's region, hottest first, attribution-free ("Word has it…").
    """
    from world.areas.services import get_room_profile  # noqa: PLC0415

    if not get_room_profile(room).is_social_hub:
        return []
    region = _region_for_room(room)
    if region is None:
        return []
    rows = (
        SecretGossip.objects.filter(region=region, went_public=True)
        .select_related("secret")
        .order_by("-heat")[:limit]
    )
    return [f"|xWord has it:|n {row.secret.content}" for row in rows]


def _can_spread(character: ObjectDB, secret: Secret) -> bool:
    """You may spread a secret you hold (SecretKnowledge) or one that is about you (self-seed)."""
    sheet = character.sheet_data  # type: ignore[attr-defined] — ObjectDB typeclass extension
    if secret.subject_sheet_id == sheet.pk:
        return True
    entry = _roster_entry(character)
    return (
        entry is not None
        and SecretKnowledge.objects.filter(roster_entry=entry, secret=secret).exists()
    )
