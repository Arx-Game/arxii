"""Choices for the Character Secrets system (#1334).

Level names are PLACEHOLDER — a player-facing flavor pass for Apostate (spec §10 open fork:
the names + the 4-vs-5 call). The *values* (the 1–4 ordinal) are structural and load-bearing
(they drive the default share-scope and the anchor-scales-with-level rule); only the display
labels are provisional.
"""

from django.db import models


class SecretLevel(models.IntegerChoices):
    """How deep/dangerous a secret is — narrative weight + default share-scope.

    Four levels (the spec's 4-vs-5 call landed on 4 + decoupled: the level *defaults* the
    share-scope but does not dictate it, so "unshareable" is just an empty share-list rather
    than a distinct top tier). PLACEHOLDER display names — workshop with Apostate.
    """

    UNCOMMON_KNOWLEDGE = 1, "Uncommon Knowledge"  # PLACEHOLDER name
    WHISPERS = 2, "Whispers"  # PLACEHOLDER name
    CAREFULLY_KEPT = 3, "Carefully Kept"  # PLACEHOLDER name
    DANGEROUS = 4, "Dangerous Secret"  # PLACEHOLDER name


class SecretProvenance(models.TextChoices):
    """Where a secret came from — drives the anchor-scales-with-level rule and OOC attribution.

    Read as a canonicity spectrum: GM-authored (canon) → action-anchored (true because it
    happened) → player-flavor (unverified, no mechanical stakes). Free player authoring is
    capped at ``PLAYER_FLAVOR`` + Level 1; anything heavier must be ``GM_AUTHORED`` or
    ``ACTION_ANCHORED`` so it cannot masquerade as canon.
    """

    GM_AUTHORED = "gm", "GM/Staff authored (canon)"
    ACTION_ANCHORED = "action", "Action-anchored (minted by play)"
    PLAYER_FLAVOR = "flavor", "Player flavor (unverified)"
