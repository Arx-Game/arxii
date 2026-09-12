"""TypedDict definitions for scene interaction payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypedDict

from actions.types import PendingActionResolution
from world.magic.types import TechniqueUseResult

if TYPE_CHECKING:
    from world.combat.models import CombatEncounter
    from world.magic.models import FuryTier
    from world.magic.types import SoulfrayWarning
    from world.magic.types.power_ledger import PowerLedger
    from world.scenes.action_models import SceneActionRequest
    from world.scenes.models import Interaction


class PersonaPayload(TypedDict):
    """Persona data embedded in interaction payloads."""

    id: int
    name: str
    thumbnail_url: str


class ReplyParentPayload(TypedDict):
    """The row a reply answered, as the parent chip needs it.

    Exactly the shape ``InteractionSerializer.get_reply_to`` returns over REST (a
    stringified id and an ISO timestamp), so the frontend reads one type on both
    channels: the id plus the parent's timestamp is a thread selector, never the
    parent's content or author.
    """

    id: str
    timestamp: str


class InteractionPayload(TypedDict):
    """Structured interaction payload for WebSocket delivery."""

    id: int
    persona: PersonaPayload
    content: str
    mode: str
    timestamp: str
    thread_id: str | None
    scene_id: int | None
    place_id: int | None
    place_name: str | None
    receiver_persona_ids: list[int]
    target_persona_ids: list[int]
    language_id: int | None
    language_name: str | None
    attributed_companion_id: int | None
    attributed_companion_name: str | None
    reply_to: ReplyParentPayload | None


class ReactionAggregation(TypedDict):
    """Aggregated emoji reaction with current-user flag."""

    emoji: str
    count: int
    reacted: bool


@dataclass
class EnhancedSceneActionResult:
    """Combined result of a social action, optionally technique-enhanced."""

    action_resolution: PendingActionResolution
    action_key: str
    technique_result: TechniqueUseResult | None = None
    power_ledger: PowerLedger | None = None
    fury_committed: FuryTier | None = None
    fizzle_note: str | None = None
    """When a thread pull was declared but failed at charge time (#1919), this
    carries the player-facing explanation so the OUTCOME pose can note the
    fizzle. ``None`` when no pull was declared or the pull succeeded."""
    disposition_message: str | None = None
    """Set when this action's resolution moved a persona-bearing NPC's
    NPCStanding.affection (#1591) — a ready-to-toast qualitative message
    (#2158). None when no NPC-affection movement occurred."""


@dataclass(frozen=True)
class CastResult:
    """Outcome of routing a standalone technique cast.

    Exactly one of the optional payloads is populated per the routing matrix:
    - immediate self/room/no-target cast → ``result`` + ``outcome_interaction`` + ``power_ledger``,
    - benign cast at another PC → only ``request`` (PENDING; resolves on accept),
    - hostile cast at another PC → ``encounter`` (combat seeded/fed).
    - soulfray gate not confirmed → ``soulfray_warning`` set, ``result`` is None.

    ``power_ledger`` is present only on the immediate path (BASE + ENVIRONMENT stages).
    It is None on benign-PENDING and hostile paths (no resolution has occurred yet).

    ``soulfray_warning`` is set when ``use_technique`` returned ``confirmed=False``
    (the cast was halted for soulfray consent). The caller should prompt the actor
    to confirm or decline before re-dispatching with ``confirm_soulfray_risk=True``.

    ``combat_seated`` is True when a benign cast at an embattled ally seated the
    caster in that ally's encounter (#2226). Callers append a notification when
    True so the caster knows they've been drawn into the fight.
    """

    request: SceneActionRequest | None = None
    result: EnhancedSceneActionResult | None = None
    encounter: CombatEncounter | None = None
    outcome_interaction: Interaction | None = None
    power_ledger: PowerLedger | None = None
    soulfray_warning: SoulfrayWarning | None = None
    combat_seated: bool = False


@dataclass(frozen=True)
class CharacterAttention:
    """What is waiting for one character (#3774).

    `direct` is a count of poses aimed at this character's personas and not yet
    read. `ambient` is whether a scene this character is still in has moved
    without them. Two tiers rather than one number because the badge answers
    two different questions: did someone speak to me, or did something happen
    near me.
    """

    direct: int
    ambient: bool


@dataclass(frozen=True)
class AccountAttention:
    """One account's attention across all of its characters (#3774).

    `by_character` is keyed by `character_sheet_id`. `as_of_id` is the largest
    `Interaction.id` the service considered; the client drops session
    interactions at or below it so a live WebSocket delta and this server
    baseline cannot count the same pose twice.
    """

    by_character: dict[int, CharacterAttention]
    as_of_id: int
