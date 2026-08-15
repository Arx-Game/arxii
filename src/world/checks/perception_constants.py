"""PLACEHOLDER constants for the canonical perception-check seam (#2997).

``resolve_perception_check`` (``world.checks.perception_services``) is the ONE
perception check every perceive-the-real mechanic resolves through — see
``docs/systems/scenes.md``'s "Perception & altered reality" section. The
difficulty magnitudes below are unturned placeholders, sized against the
seeded ``CheckRank`` ladder (``world/seeds/checks.py``'s ``_CHECK_RANKS``:
0 / 10 / 25 / 50 / 80 / ...) so they land on real rank rungs (Novice /
Competent / Expert), not arbitrary numbers. The first real consumer
(dreamside noticing, an illusion tell, a disguise tell) should retune these
against actual play, not treat them as final.
"""

PERCEPTION_CHECK_TYPE_NAME = "Perception"
"""Name of the seeded, stat-only CheckType ``resolve_perception_check`` rolls.

Seeded (PERCEPTION stat, weight 1.0, no skill leg — the AD&D-style "one
passive perception roll" the ratified spec calls for, deliberately simpler
than the stat+skill Search/Identification checks) by
``world.seeds.investigation_checks.ensure_perception_check``.
"""

PERCEPTION_DIFFICULTY_EASY = 10

PERCEPTION_DIFFICULTY_STANDARD = 25

PERCEPTION_DIFFICULTY_HARD = 50
