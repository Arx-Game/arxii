"""Gossip — the casual Level-1-secret spread mechanic (#1572), climbing the area ladder (#4085).

Three Gossip-check actions, performed **at a social hub**, operating on per-``(secret, area)``
heat (``SecretGossip``), where the area is the rumor's **reach**:

- **plant** — a character who has *come into* a Level-1 secret spreads it, raising heat at the
  hub's own area; heat past a parent's ``GOSSIP_CLIMB_THRESHOLDS`` entry moves the rumor up
  (``climb_gossip``), merging with any row already there, so a hot rumor is heard across a
  county and a faint one across a street.
- **seek** — a seeker rolls to surface a hot (``heat >= 1``) secret they don't yet know, from
  every rumor whose reach contains the hub.
- **suppress** — lower a secret's heat (the only path back to 0; decay alone floors at 1). A
  rumor never climbs back down; suppression is the counter-play.

The check is the seeded **Gossip** CheckType (charm + Persuasion + the Gossip specialization), so a
character's Gossip spec folds into the roll automatically (the #1688 engine). Use is gated on
**Gossip >= 1** and on standing in a ``RoomProfile.is_social_hub`` room. At the public threshold a
secret goes ambient and is exposed to the reach's societies (one-shot). All magnitudes are
PLACEHOLDER (see ``constants``). This is the pre-exposure, skill-gated tier — distinct from the
formal ``expose_secret`` / tidings path.
"""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import TYPE_CHECKING

from world.secrets.constants import (
    GOSSIP_CHECK_TYPE_NAME,
    GOSSIP_CLIMB_THRESHOLDS,
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
    from world.character_sheets.models import CharacterSheet


_NOT_HUB = "You can only work the rumor mill at a social hub."
_NO_AREA = "This place isn't on the map of anywhere."
_NO_SKILL = "You don't have the ear for it (requires Gossip 1+)."
_NOT_LEVEL_1 = "Only the lightest secrets travel as idle gossip."
_NOT_HELD = "You can only spread gossip you've actually come into."
_NO_SELF_SMEAR = "Smearing yourself would be a novel strategy — no."
_SMEAR_CONSENT_BLOCKED = (
    "They have not opened themselves to being antagonised. "
    "You can't manufacture a scandal against them."
)
_NOT_AN_ACCUSATION = "That's not a manufactured scandal — there's nothing to refute."
_REFUTE_NOT_KNOWN = "You can only dispute a rumor you've actually come into."
_ALREADY_REFUTED = "You have already made your case against this rumor."


class GossipError(Exception):
    """A gossip action could not proceed (carries a user-facing message)."""

    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


@dataclass(frozen=True)
class GossipResult:
    """Outcome of a gossip action (#1572).

    ``success`` = the check landed and changed something; ``heat`` = the secret's resulting heat
    at its reach (0 for a seek that found nothing); ``surfaced_secret_id`` is set for a successful
    seek.
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


def _area_for_room(room: ObjectDB) -> Area | None:
    from world.areas.services import get_room_profile  # noqa: PLC0415

    return get_room_profile(room).area


def _reach_ids(room: ObjectDB) -> list[int]:
    """The ids of every area whose reach contains the room: its own area, then each parent."""
    from world.areas.services import containing_areas  # noqa: PLC0415

    return [area.pk for area in containing_areas(_area_for_room(room))]


def _require_hub_area(room: ObjectDB) -> Area:
    """The room must be a social hub on the map; returns its own area or raises GossipError."""
    from world.areas.services import get_room_profile  # noqa: PLC0415

    profile = get_room_profile(room)
    if not profile.is_social_hub:
        raise GossipError(_NOT_HUB)
    if profile.area is None:
        raise GossipError(_NO_AREA)
    return profile.area


def climb_gossip(row: SecretGossip) -> SecretGossip:
    """Move a rumor up the ladder as far as its heat carries it; return the row holding it.

    While the reach has a parent whose ``GOSSIP_CLIMB_THRESHOLDS`` entry the heat meets, the
    rumor climbs one rung. A row already at the parent (the same secret planted elsewhere
    and climbed) absorbs this one's heat and this row is deleted, so a secret has one row per
    reach. A level with no entry can never be climbed onto. Never descends (#4085).
    """
    while True:
        parent = row.area.parent
        if parent is None:
            return row
        threshold = GOSSIP_CLIMB_THRESHOLDS.get(parent.level)
        if threshold is None or row.heat < threshold:
            return row
        above = SecretGossip.objects.filter(secret_id=row.secret_id, area=parent).first()
        if above is None:
            row.area = parent
            row.save(update_fields=["area", "updated_date"])
            continue
        above.heat += row.heat
        above.went_public = above.went_public or row.went_public
        above.save(update_fields=["heat", "went_public", "updated_date"])
        row.delete()
        row = above


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
    from world.checks.services import perform_check_with_modifiers  # noqa: PLC0415

    return perform_check_with_modifiers(character, _gossip_check_type()).success_level


def _delta_for(tier: int, regular: int, special: int) -> int:
    if tier >= GOSSIP_SPECIAL_SUCCESS_LEVEL:
        return special
    if tier >= 1:
        return regular
    return 0


def _maybe_go_public(row: SecretGossip) -> None:
    """At/above the public threshold, expose the secret to the reach's societies (one-shot)."""
    if row.went_public or row.heat < GOSSIP_PUBLIC_THRESHOLD:
        return
    from world.secrets.services import expose_secret  # noqa: PLC0415

    societies = _societies_for_area(row.area)
    if societies:
        expose_secret(row.secret, societies=societies)
    row.went_public = True
    row.save(update_fields=["went_public", "updated_date"])


def _societies_for_area(area: Area) -> list:
    """Societies that judge an area's public — dominant society if set, else all sharing its realm.

    Mirrors ``world.areas.services.societies_for_scene``'s precedence, at whatever rung the
    rumor has reached.
    """
    from world.societies.models import Society  # noqa: PLC0415

    if area.dominant_society_id:
        return [area.dominant_society]
    if area.realm_id is None:
        return []
    return list(Society.objects.filter(realm_id=area.realm_id))


# --- actions ------------------------------------------------------------------------------


def plant_gossip(character: ObjectDB, secret: Secret, *, room: ObjectDB) -> GossipResult:
    """Spread a Level-1 secret you've come into, raising its heat at this hub's area (#1572).

    Guards: Gossip >= 1, standing in a social hub, the secret is Level-1, and you **hold** it
    (``SecretKnowledge``) or it is **about you** (self-seeded gossip). A regular success adds
    ``GOSSIP_PLANT_REGULAR`` heat, a special success ``GOSSIP_PLANT_SPECIAL`` (by anyone, no cap).
    The rumor starts at the hub's own area and climbs as far as its heat allows (#4085).
    """
    _require_gossip_skill(character)
    area = _require_hub_area(room)
    if secret.level != SecretLevel.UNCOMMON_KNOWLEDGE:
        raise GossipError(_NOT_LEVEL_1)
    if not _can_spread(character, secret):
        raise GossipError(_NOT_HELD)

    delta = _delta_for(_check_tier(character), GOSSIP_PLANT_REGULAR, GOSSIP_PLANT_SPECIAL)
    row = _row_reaching(secret, room) or SecretGossip.objects.create(secret=secret, area=area)
    if delta:
        row.heat += delta
        row.save(update_fields=["heat", "updated_date"])
        row = climb_gossip(row)
        _maybe_go_public(row)
    return GossipResult(
        success=delta > 0,
        heat=row.heat,
        went_public=row.went_public,
        surfaced_secret_id=secret.pk,
    )


def plant_smear(
    character: ObjectDB,
    subject_sheet: CharacterSheet,
    content: str,
    *,
    room: ObjectDB,
) -> GossipResult:
    """Mint an L1 accusation and seed its heat at this hub's area in one move (#1825).

    The light-smear tier as a *type of gossip*: Gossip >= 1, standing at a social hub,
    the target's ``hostile`` consent category open to you, and not yourself. One Gossip
    roll drives everything — a miss mints nothing (no consolation accusation); a success
    mints the ACCUSATION Secret at Level 1, seeds its ``SecretGossip`` heat at the
    plant delta, and plants the counter-clue in the hubs of its reach with difficulty
    seeded from the same roll (your craft sets how hard your trail is to unearth).
    """
    from world.secrets.constants import (  # noqa: PLC0415
        SMEAR_CLUE_BASE_DIFFICULTY,
        SMEAR_CLUE_DIFFICULTY_PER_LEVEL,
    )
    from world.secrets.services import accusation_permitted, mint_accusation  # noqa: PLC0415

    _require_gossip_skill(character)
    area = _require_hub_area(room)
    smearer_sheet = character.sheet_data  # type: ignore[attr-defined] — typeclass extension
    if smearer_sheet.pk == subject_sheet.pk:
        raise GossipError(_NO_SELF_SMEAR)
    if not accusation_permitted(framer_sheet=smearer_sheet, target_sheet=subject_sheet):
        raise GossipError(_SMEAR_CONSENT_BLOCKED)

    tier = _check_tier(character)
    if tier < 1:
        return GossipResult(success=False)

    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    secret = mint_accusation(
        accuser_persona=active_persona_for_sheet(smearer_sheet),
        subject_sheet=subject_sheet,
        content=content,
        level=SecretLevel.UNCOMMON_KNOWLEDGE,
    )
    delta = _delta_for(tier, GOSSIP_PLANT_REGULAR, GOSSIP_PLANT_SPECIAL)
    row = SecretGossip.objects.create(secret=secret, area=area, heat=delta)
    row = climb_gossip(row)
    _maybe_go_public(row)

    from world.clues.services import create_accusation_counter_clue  # noqa: PLC0415

    difficulty = SMEAR_CLUE_BASE_DIFFICULTY + tier * SMEAR_CLUE_DIFFICULTY_PER_LEVEL
    create_accusation_counter_clue(secret, area=row.area, difficulty=difficulty)
    return GossipResult(
        success=True,
        heat=row.heat,
        went_public=row.went_public,
        surfaced_secret_id=secret.pk,
    )


def refute_accusation(character: ObjectDB, secret: Secret, *, room: ObjectDB) -> GossipResult:
    """Attack an accusation's credibility at a hub — the consentless defense (#1825).

    Anyone holding knowledge of an ACCUSATION secret (or its subject) may make the
    case against it: a Gossip-composition check vs a level-scaled difficulty. Success
    applies a **partial** compensating reputation reversal (nullification via the
    investigation project is the full clear). One attempt per refuter, success or
    failure — the case has been made. **No consent gate and no skill floor** — the
    Tom/Bob/Fred rule: defending the accused is open; only naming-and-attacking the
    author (denounce) needs the author's hostile-consent opt-in.
    """
    from world.checks.services import perform_check_with_modifiers  # noqa: PLC0415
    from world.secrets.constants import (  # noqa: PLC0415
        REFUTE_BASE_DIFFICULTY,
        REFUTE_DIFFICULTY_PER_LEVEL,
        REFUTE_REVERSAL_DENOMINATOR,
        REFUTE_REVERSAL_NUMERATOR,
        SecretProvenance,
    )
    from world.secrets.models import AccusationRebuttal  # noqa: PLC0415
    from world.secrets.services import reverse_secret_exposure  # noqa: PLC0415

    _require_hub_area(room)
    if secret.provenance != SecretProvenance.ACCUSATION:
        raise GossipError(_NOT_AN_ACCUSATION)
    if not _can_spread(character, secret):
        raise GossipError(_REFUTE_NOT_KNOWN)
    refuter_sheet = character.sheet_data  # type: ignore[attr-defined] — typeclass extension
    if AccusationRebuttal.objects.filter(secret=secret, refuter_sheet=refuter_sheet).exists():
        raise GossipError(_ALREADY_REFUTED)

    difficulty = REFUTE_BASE_DIFFICULTY + secret.level * REFUTE_DIFFICULTY_PER_LEVEL
    result = perform_check_with_modifiers(
        character, _gossip_check_type(), target_difficulty=difficulty
    )
    succeeded = result.success_level >= 1
    AccusationRebuttal.objects.create(
        secret=secret, refuter_sheet=refuter_sheet, succeeded=succeeded
    )
    if succeeded:
        reverse_secret_exposure(
            secret,
            numerator=REFUTE_REVERSAL_NUMERATOR,
            denominator=REFUTE_REVERSAL_DENOMINATOR,
        )
    return GossipResult(success=succeeded, surfaced_secret_id=secret.pk)


def seek_gossip(character: ObjectDB, *, room: ObjectDB) -> GossipResult:
    """Roll to overhear a hot Level-1 secret whose reach holds this hub (#1572, #4085).

    Surfaces a ``heat >= 1`` secret (weighted by heat) the seeker doesn't already hold, from every
    rumor whose reach contains the room; on success grants the **fact only** (never
    category/consequences). Empty result on a miss or an empty pool.
    """
    _require_gossip_skill(character)
    _require_hub_area(room)
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
            area_id__in=_reach_ids(room),
            heat__gte=1,
            secret__level=SecretLevel.UNCOMMON_KNOWLEDGE,
        )
        .exclude(secret_id__in=known_ids)
        .select_related("secret")
    )
    if not pool:
        return GossipResult(success=False)
    weights = [row.heat for row in pool]
    chosen = random.choices(pool, weights=weights, k=1)[0]  # noqa: S311 # NOSONAR game RNG
    grant_secret_knowledge(roster_entry=entry, secret=chosen.secret)
    return GossipResult(success=True, heat=chosen.heat, surfaced_secret_id=chosen.secret_id)


def suppress_gossip(character: ObjectDB, secret: Secret, *, room: ObjectDB) -> GossipResult:
    """Talk a Level-1 secret's heat down — the only path back to 0 (#1572).

    Regular success removes ``GOSSIP_SUPPRESS_REGULAR`` heat, special ``GOSSIP_SUPPRESS_SPECIAL``;
    floored at 0 (decay alone only reaches ``GOSSIP_DECAY_FLOOR``). Acts on the rumor whose reach
    holds this hub; at 0 it is unheard everywhere below that reach (#4085).
    """
    _require_gossip_skill(character)
    _require_hub_area(room)
    row = _row_reaching(secret, room)
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

    return SecretGossip.objects.filter(heat__gt=GOSSIP_DECAY_FLOOR).update_with_reason(
        reason="issue #3817: intentional atomic write",
        heat=F("heat") - 1,
    )


def hub_area_for(room: ObjectDB) -> Area:
    """Public seam: the hub room's own area, requiring a social hub (raises GossipError).

    Consumers outside this module (justice's denounce, #1825) gate hub-audience
    actions through the same rule the gossip verbs use.
    """
    return _require_hub_area(room)


def societies_for_area(area: Area) -> list:
    """Public seam: the societies that judge an area's public — see `_societies_for_area`."""
    return _societies_for_area(area)


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


def _row_reaching(secret: Secret, room: ObjectDB) -> SecretGossip | None:
    """The secret's rumor whose reach holds the room, nearest reach first; None if unheard here."""
    ids = _reach_ids(room)
    rows = {row.area_id: row for row in SecretGossip.objects.filter(secret=secret, area_id__in=ids)}
    for area_id in ids:
        if area_id in rows:
            return rows[area_id]
    return None


def heat_for(secret: Secret, *, room: ObjectDB) -> int:
    """Current gossip heat for a secret as heard in the room (0 if unheard here) (#1572)."""
    row = _row_reaching(secret, room)
    return row.heat if row is not None else 0


def public_gossip_lines(room: ObjectDB, *, limit: int = 3) -> list[str]:
    """Source-ambiguous ambient lines for a hub room's *public* gossip (#1572).

    Empty unless the room is a social hub (the cheap ``is_social_hub`` check short-circuits before
    any ancestry walk, so non-hub rooms — the overwhelming majority — never touch it). For a hub,
    returns what an arriving character overhears as common knowledge: the ``went_public`` secrets
    whose reach holds the room, hottest first, attribution-free ("Word has it…").
    """
    from world.areas.services import get_room_profile  # noqa: PLC0415

    if not get_room_profile(room).is_social_hub:
        return []
    rows = (
        SecretGossip.objects.filter(area_id__in=_reach_ids(room), went_public=True)
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
