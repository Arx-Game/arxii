from dataclasses import dataclass


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
