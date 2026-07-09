"""Seed the relationship magnitude scale + reaction-emoji catalog (#1699).

Ambient bumps (``apply_relationship_bump``) write to two generic system tracks
looked up by ``RelationshipTrack.system_key`` — Regard (positive) and Friction
(negative). Each track gets the four named magnitude bands ratified on #1699
(25 / 100 / 500 / 2000), and the web door gets a starter ``ReactionEmoji``
catalog (👍 stays cosmetic; one positive, one negative).

All player-visible names/descriptions here are PLACEHOLDER prose for Apostate's
rewrite (track names, tier names, emoji selection pending playtest).

Upsert semantics: ``update_or_create`` keyed on the stable lookup (system_key /
(track, tier_number) / emoji) so edited seed values re-apply on re-seed —
``loaddata`` cannot update idmapper rows (#946).
"""

from __future__ import annotations

# (threshold, PLACEHOLDER regard name, PLACEHOLDER friction name) per band, tier 1-4.
_TIER_BANDS: list[tuple[int, str, str]] = [
    (25, "Noticed", "Irritant"),
    (100, "Valued", "Grating"),
    (500, "Cherished", "Despised"),
    (2000, "Inseparable", "Nemesis"),
]

# (emoji, valence, sort_order) — PLACEHOLDER selection pending playtest (#1699).
_STARTER_EMOJI: list[tuple[str, int, int]] = [
    ("\U0001f44d", 0, 0),  # 👍 keeps today's cosmetic behavior
    ("❤️", 1, 1),  # ❤️ warms
    ("\U0001f620", -1, 2),  # 😠 cools
]


def ensure_system_tracks() -> dict[str, object]:
    """Upsert the Regard/Friction system tracks (names PLACEHOLDER)."""
    from world.relationships.constants import TrackSign, TrackSystemKey  # noqa: PLC0415
    from world.relationships.models import RelationshipTrack  # noqa: PLC0415

    specs = [
        (
            TrackSystemKey.REGARD,
            "Regard",
            TrackSign.POSITIVE,
            "General warmth accrued from ordinary play — rel plus and warm reactions land here.",
        ),
        (
            TrackSystemKey.FRICTION,
            "Friction",
            TrackSign.NEGATIVE,
            "General grievance accrued from ordinary play — rel neg and cold reactions land here.",
        ),
    ]
    tracks: dict[str, object] = {}
    for key, name, sign, description in specs:
        track, _ = RelationshipTrack.objects.update_or_create(
            system_key=key,
            defaults={
                "name": name,
                "slug": key.value,
                "sign": sign,
                "description": description,
            },
        )
        tracks[key.value] = track
    return tracks


def ensure_tier_bands(tracks: dict[str, object]) -> None:
    """Upsert the four magnitude bands per system track (names PLACEHOLDER)."""
    from world.relationships.constants import TrackSystemKey  # noqa: PLC0415
    from world.relationships.models import RelationshipTier  # noqa: PLC0415

    for tier_number, (threshold, regard_name, friction_name) in enumerate(_TIER_BANDS, start=1):
        for key, name in (
            (TrackSystemKey.REGARD, regard_name),
            (TrackSystemKey.FRICTION, friction_name),
        ):
            RelationshipTier.objects.update_or_create(
                track=tracks[key.value],
                tier_number=tier_number,
                defaults={"name": name, "point_threshold": threshold},
            )


def ensure_reaction_emoji() -> None:
    """Upsert the starter reaction-emoji catalog (selection PLACEHOLDER)."""
    from world.scenes.models import ReactionEmoji  # noqa: PLC0415

    for emoji, valence, sort_order in _STARTER_EMOJI:
        ReactionEmoji.objects.update_or_create(
            emoji=emoji,
            defaults={"valence": valence, "is_active": True, "sort_order": sort_order},
        )


def seed_relationship_scale_content() -> None:
    """Cluster entry — system tracks, tier bands, and the reaction-emoji catalog."""
    tracks = ensure_system_tracks()
    ensure_tier_bands(tracks)
    ensure_reaction_emoji()
