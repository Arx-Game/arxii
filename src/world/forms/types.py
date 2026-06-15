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
