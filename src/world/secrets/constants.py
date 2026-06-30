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


# PLACEHOLDER magnitudes — the default direct standing hit a victim takes when a secret of a
# given level is exposed (used when a SecretVictim sets no explicit severity). Values are
# load-bearing only in relative ordering; tune in a later balance pass (#1429). Scaled against
# the -1000..+1000 reputation range so a Dangerous secret roughly reaches "Reviled".
DEFAULT_VICTIM_SEVERITY_BY_LEVEL: dict[int, int] = {
    1: 150,
    2: 350,
    3: 600,
    4: 1000,
}


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


# --- Gossip (#1572): regional Level-1-secret spread "heat". ---
# PLACEHOLDER magnitudes (Apostate's tuning pass later — build the mechanism, defer the numbers).
GOSSIP_CHECK_TYPE_NAME = "Gossip"  # the seeded charm + Persuasion + Gossip-spec check
GOSSIP_DECAY_FLOOR = 1  # heat decays toward this; once gossiped it lingers findable. Suppress → 0.
GOSSIP_PUBLIC_THRESHOLD = 40  # heat ≥ this → public (ambient echo + region society exposure)
GOSSIP_SPECIAL_SUCCESS_LEVEL = 2  # CheckOutcome.success_level ≥ this counts as a "special" success
GOSSIP_PLANT_REGULAR = 1  # heat added by a regular-success plant
GOSSIP_PLANT_SPECIAL = 2  # heat added by a special-success plant (spec counts double)
GOSSIP_SUPPRESS_REGULAR = 1  # heat removed by a regular-success suppress
GOSSIP_SUPPRESS_SPECIAL = 2  # heat removed by a special-success suppress
