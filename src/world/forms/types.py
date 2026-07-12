from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from world.scenes.models import PersonaDiscovery


@dataclass(frozen=True)
class PresentedTrait:
    """One appearance trait as presented to a viewer.

    ``normalized`` is the searchable bucket (the option's display value); ``descriptor``
    is the active persona's free-text flavor (empty when none); ``display`` is what
    prose shows — the descriptor when present, else the normalized value.
    """

    trait_name: str
    trait_display: str
    normalized: str
    descriptor: str
    display: str


@dataclass(frozen=True)
class IdentificationOdds:
    """The Identification check's target difficulty for one viewer/target pair (#1107 slice 5).

    ``applicable`` is False when the target presents no fake overlay and no fake-name persona —
    there's nothing to identify, and the caller should surface a clean "nothing to identify"
    outcome rather than roll. When applicable:

    - ``baseline`` is the raw difficulty from what the target is presenting (overlay
      kind/concealment, or the flat "mask floor" for a name-only mask).
    - ``familiarity_ease`` is how much the viewer's relationship to / the target's fame reduces
      that baseline (already subtracted into ``difficulty``).
    - ``guess_ease`` is the ease a *correct* named guess would apply — exposed but NOT subtracted
      into ``difficulty`` here, since this service doesn't know the guess; the caller
      (``attempt_identification``) subtracts it only when the guess matches.
    - ``difficulty`` is ``max(0, baseline - familiarity_ease)`` — the ``perform_check``
      ``target_difficulty`` before any guess ease.
    - ``auto_fail`` is True when the pre-clamp gap is so vast (Decision 4) that no roll can
      close it — the caller should short-circuit without calling ``perform_check`` at all.
    """

    applicable: bool
    difficulty: int
    auto_fail: bool
    baseline: int
    familiarity_ease: int
    guess_ease: int
    kit_quality_bonus: int


class IdentificationOutcome(Enum):
    """How an ``attempt_identification`` call resolved (#1107 slice 5 Task 2).

    Plain runtime enum (not ``TextChoices``) — this never backs a model field, it's a return-value
    discriminator, matching the ``ReputationTier`` precedent (``world.societies.types``).
    """

    SUCCESS = "success"
    FAILURE = "failure"
    BOTCH_FAKE_ID = "botch_fake_id"
    ALREADY_KNOWN = "already_known"
    AUTO_FAIL = "auto_fail"


@dataclass(frozen=True)
class IdentificationResult:
    """The outcome of one ``attempt_identification`` call (#1107 slice 5 Task 2).

    - ``revealed_name`` is the target's TRUE (PRIMARY) persona name on ``SUCCESS``/
      ``ALREADY_KNOWN``, the fake-IDed ``Functionary.display_name`` on ``BOTCH_FAKE_ID``
      (never a PC name — the spec's oracle rule), and empty on ``FAILURE``/``AUTO_FAIL``.
    - ``persona_discovery`` is the written/pre-existing row on ``SUCCESS``/``ALREADY_KNOWN``
      (``None`` when the presented/true persona pair was degenerate — nothing to link — or on
      any other outcome).
    - ``player_message`` is the safe, player-facing line. **``FAILURE`` and ``AUTO_FAIL`` always
      share the identical string** — the oracle rule (a player must not be able to distinguish
      "you rolled and missed" from "this was never rollable") — verified by a dedicated test
      rather than left to eyeballing call sites.
    """

    outcome: IdentificationOutcome
    revealed_name: str = ""
    persona_discovery: PersonaDiscovery | None = None
    player_message: str = ""
