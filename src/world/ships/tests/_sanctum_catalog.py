"""Shared builders for ship-sanctum catalog tests (#2736).

Since #2736 a ship's sanctum grants only what the ``ThreadPullEffect`` catalog
authors, so every test of that path has to install a sanctum, weave a thread, AND
author the row it expects to be paid for. These three steps are identical in
``test_sanctum_bonus`` and ``test_battle_bridge``; sharing them keeps the two suites
from drifting into disagreeing about what an authored row looks like.

Not a factory module: these compose existing factories, they do not define new ones.
"""

from __future__ import annotations

from evennia_extensions.factories import RoomProfileFactory
from world.magic.constants import EffectKind, SanctumSlotKind, TargetKind
from world.magic.factories import ResonanceFactory, ThreadFactory, ThreadPullEffectFactory
from world.magic.models import SanctumDetails, SanctumOwnerMode
from world.room_features.factories import RoomFeatureInstanceFactory


def sanctum_for_ship(ship, *, level: int = 1) -> SanctumDetails:
    """Install an active sanctum on one of ``ship``'s rooms.

    ``level`` is the shrine's installed level — the power figure
    ``ship_sanctum_capability_grants`` curves its grants by, so a test that wants the
    curve to do anything must raise it above 0.
    """
    room_profile = RoomProfileFactory(area=ship.building.area)
    feature_instance = RoomFeatureInstanceFactory(room_profile=room_profile, level=level)
    return SanctumDetails.objects.create(
        feature_instance=feature_instance,
        resonance_type=ResonanceFactory(),
        owner_mode=SanctumOwnerMode.PERSONAL,
    )


def weave(sanctum, resonance, *, level: int, slot=SanctumSlotKind.PERSONAL_OWN, **kwargs):
    """Weave a SANCTUM thread of ``resonance`` onto ``sanctum`` at ``level``."""
    return ThreadFactory(
        target_kind=TargetKind.SANCTUM,
        target_trait=None,
        target_sanctum_details=sanctum,
        slot_kind=slot,
        resonance=resonance,
        level=level,
        **kwargs,
    )


def author_stat_row(resonance, vital_target, amount, *, min_thread_level=0):
    """Author the tier-0 VITAL_BONUS row giving ``resonance`` its ship-stat lean."""
    return ThreadPullEffectFactory(
        target_kind=TargetKind.SANCTUM,
        resonance=resonance,
        tier=0,
        min_thread_level=min_thread_level,
        effect_kind=EffectKind.VITAL_BONUS,
        flat_bonus_amount=None,  # threadpulleffect_vital_bonus_payload constraint
        vital_target=vital_target,
        vital_bonus_amount=amount,
    )


def author_capability_row(resonance, capability, *, base=2, min_thread_level=3):
    """Author the tier-0 CAPABILITY_GRANT row for ``resonance``.

    ``min_thread_level`` defaults to 3 because that is the depth content authors the
    first unlock at — but it is the row's gate, not the code's, so a test may move it.
    A stat row and a capability row for one resonance must differ in
    ``min_thread_level``: ``threadpulleffect_lookup_key`` admits one row per
    ``(target_kind, resonance, tier, min_thread_level)``.
    """
    return ThreadPullEffectFactory(
        target_kind=TargetKind.SANCTUM,
        resonance=resonance,
        tier=0,
        min_thread_level=min_thread_level,
        effect_kind=EffectKind.CAPABILITY_GRANT,
        flat_bonus_amount=None,
        capability_grant=capability,
        capability_grant_value=base,
    )
