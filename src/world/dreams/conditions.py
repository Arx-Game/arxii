"""Dream-specific condition templates: Nightmares and Madness (#2290).

Seeded idempotently by ``ensure_dream_conditions()``.
"""

from world.conditions.constants import DurationType
from world.conditions.models import (
    CapabilityType,
    ConditionCapabilityEffect,
    ConditionCategory,
    ConditionCheckModifier,
    ConditionTemplate,
)
from world.dreams.constants import (
    MADNESS_CATEGORY_NAME,
    MADNESS_CONDITION_NAME,
    NIGHTMARES_CATEGORY_NAME,
    NIGHTMARES_CONDITION_NAME,
)

# Shared description for mental-focus check condition templates.
_FOCUS_CHECK_DESCRIPTION = "Mental focus and concentration checks."


def _ensure_nightmares_category() -> ConditionCategory:
    """Return the Dream Affliction condition category (non-behavior-altering)."""
    category, _ = ConditionCategory.objects.get_or_create(
        name=NIGHTMARES_CATEGORY_NAME,
        defaults={
            "description": "Persistent dream afflictions — debuffs from dream trauma.",
            "is_negative": True,
            "alters_behavior": False,
            "display_order": 60,
        },
    )
    return category


def _ensure_madness_category() -> ConditionCategory:
    """Return the Madness condition category (behavior-altering)."""
    category, _ = ConditionCategory.objects.get_or_create(
        name=MADNESS_CATEGORY_NAME,
        defaults={
            "description": "Severe psychological damage from dream trauma.",
            "is_negative": True,
            "alters_behavior": True,
            "display_order": 61,
        },
    )
    return category


def ensure_nightmares_condition() -> ConditionTemplate:
    """Ensure the Nightmares condition template.

    A persistent debuff applied to a waking character after a Dream Peril
    outcome. Reduces mental capability and applies a check penalty.
    Treatable via the treatment system; duration until treated or dawn reset.
    """
    from world.conditions.constants import FoundationalCapability  # noqa: PLC0415

    category = _ensure_nightmares_category()
    template, _ = ConditionTemplate.objects.get_or_create(
        name=NIGHTMARES_CONDITION_NAME,
        defaults={
            "category": category,
            "description": (
                "Plagued by nightmares from the dream realm. Mental faculties "
                "are clouded by lingering visions."
            ),
            "player_description": (
                "Your sleep is troubled by dark dreams, and their shadow "
                "lingers into your waking hours."
            ),
            "observer_description": "looks haggard, as if plagued by bad dreams.",
            "default_duration_type": DurationType.UNTIL_CURED,
            "default_duration_value": 0,
            "is_visible_to_others": True,
        },
    )

    # Reduce awareness capability (mental clouding). CapabilityType is
    # content-repo-owned (#2698) — a real deploy without the row authored
    # degrades by skipping this effect, same as the rest of the capability
    # system does when unseeded (see ensure_foundational_capabilities).
    awareness = CapabilityType.objects.filter(name=FoundationalCapability.AWARENESS).first()
    if awareness is not None:
        ConditionCapabilityEffect.objects.get_or_create(
            condition=template,
            stage=None,
            capability=awareness,
            defaults={"value": -20},
        )

    # Apply a mental check penalty
    from world.checks.models import CheckCategory, CheckType  # noqa: PLC0415

    mental_category, _ = CheckCategory.objects.get_or_create(
        name="Mental",
        defaults={"description": _FOCUS_CHECK_DESCRIPTION, "display_order": 30},
    )
    mental_check, _ = CheckType.objects.get_or_create(
        name="Mental",
        category=mental_category,
        defaults={"description": _FOCUS_CHECK_DESCRIPTION},
    )
    ConditionCheckModifier.objects.get_or_create(
        condition=template,
        stage=None,
        check_type=mental_check,
        defaults={"modifier_value": -10, "scales_with_severity": False},
    )

    return template


def ensure_madness_condition() -> ConditionTemplate:
    """Ensure the Madness condition template.

    A severe persistent condition representing psychological damage from
    dream trauma. Behavior-altering (alters_behavior=True) — subject to
    consent (ADR-0024).
    """
    from world.conditions.constants import FoundationalCapability  # noqa: PLC0415

    category = _ensure_madness_category()
    template, _ = ConditionTemplate.objects.get_or_create(
        name=MADNESS_CONDITION_NAME,
        defaults={
            "category": category,
            "description": (
                "The mind has fractured under dream trauma. Perception and "
                "judgment are deeply impaired."
            ),
            "player_description": (
                "Something in the dream has broken inside your mind. The "
                "world looks different now — wrong, perhaps, or too right."
            ),
            "observer_description": "has a wild, unfocused look in their eyes.",
            "default_duration_type": DurationType.UNTIL_CURED,
            "default_duration_value": 0,
            "is_visible_to_others": True,
        },
    )

    # Significantly reduce awareness and movement (impaired function).
    # CapabilityType is content-repo-owned (#2698) — a real deploy without a
    # row authored degrades by skipping that effect, same as the rest of the
    # capability system does when unseeded (see ensure_foundational_capabilities).
    for cap_name, value in (
        (FoundationalCapability.AWARENESS, -50),
        (FoundationalCapability.MOVEMENT, -10),
    ):
        capability = CapabilityType.objects.filter(name=cap_name).first()
        if capability is None:
            continue
        ConditionCapabilityEffect.objects.get_or_create(
            condition=template,
            stage=None,
            capability=capability,
            defaults={"value": value},
        )

    # Apply a severe mental check penalty
    from world.checks.models import CheckCategory, CheckType  # noqa: PLC0415

    mental_category, _ = CheckCategory.objects.get_or_create(
        name="Mental",
        defaults={"description": _FOCUS_CHECK_DESCRIPTION, "display_order": 30},
    )
    mental_check, _ = CheckType.objects.get_or_create(
        name="Mental",
        category=mental_category,
        defaults={"description": _FOCUS_CHECK_DESCRIPTION},
    )
    ConditionCheckModifier.objects.get_or_create(
        condition=template,
        stage=None,
        check_type=mental_check,
        defaults={"modifier_value": -30, "scales_with_severity": False},
    )

    return template


def ensure_dream_conditions() -> None:
    """Ensure all dream-specific condition templates + DreamPerilConfig exist."""
    from world.vitals.seeds import ensure_foundational_capabilities  # noqa: PLC0415

    ensure_foundational_capabilities()
    ensure_nightmares_condition()
    ensure_madness_condition()
    _ensure_dream_peril_config()


def _ensure_dream_peril_config() -> None:
    """Ensure DreamPerilConfig singleton has a resist check type configured.

    `resist_check_type` is stamped once and never revisited (the early return below),
    so — unlike fatigue/fury's self-healing checks — a config prerequisite (#2724) that
    ran here before the `stability` Trait existed and skipped attaching it would be
    permanent: the check would roll on an empty composition forever, with no later
    gameplay call site to self-heal it. Both the trait attachment and the underlying
    Trait row are therefore unconditional/ensured here, exactly as fatigue does via
    `ensure_stat_trait`.
    """
    from world.checks.models import CheckCategory, CheckType, CheckTypeTrait  # noqa: PLC0415
    from world.dreams.models import DreamPerilConfig  # noqa: PLC0415
    from world.traits.constants import PrimaryStat  # noqa: PLC0415
    from world.traits.services import ensure_stat_trait  # noqa: PLC0415

    config, _ = DreamPerilConfig.objects.get_or_create(pk=1)
    if config.resist_check_type is not None:
        return  # Already configured

    # Create a stability-based check type for Dream Peril resistance
    category, _ = CheckCategory.objects.get_or_create(
        name="Mental",
        defaults={"description": _FOCUS_CHECK_DESCRIPTION, "display_order": 30},
    )
    check_type, _ = CheckType.objects.get_or_create(
        name="Dream Peril Resolve",
        category=category,
        defaults={"description": "Resistance check against Dream Peril collapse."},
    )
    # Unconditional (not gated on `created`) so a pre-existing (e.g. fixture-supplied)
    # bare CheckType still gets its trait attached (#2724); get_or_create's defaults let
    # an authored weight survive a re-run. `ensure_stat_trait` also guarantees the
    # `stability` Trait row itself exists — this can run before the content load
    # populates the STAT Trait fixtures.
    stability = ensure_stat_trait(PrimaryStat.STABILITY.value)
    CheckTypeTrait.objects.get_or_create(
        check_type=check_type, trait=stability, defaults={"weight": 1.0}
    )

    config.resist_check_type = check_type
    config.save(update_fields=["resist_check_type"])
