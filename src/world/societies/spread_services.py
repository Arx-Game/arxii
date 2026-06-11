"""Player-driven legend spreading services (#745 — Spread a Tale).

`get_spreadable_deeds` powers the deed picker; the value formula + resolver
(added in later tasks) turn a scene-action check outcome into a `spread_deed`
call.
"""

from __future__ import annotations

from django.db.models import QuerySet

from world.scenes.action_resolvers import register_resolver
from world.societies.models import LegendEntry

SPREAD_TALE_ACTION_KEY = "spread_a_tale"
# Display name shared by the Spread a Tale ActionTemplate and its CheckType.
SPREAD_TALE_TEMPLATE_NAME = "Spread a Tale"

# success_level -> fraction of base_value (failure / <=0 yields 0). Tunable.
TIER_PAYOFF: dict[int, float] = {0: 0.0, 1: 0.10, 2: 0.30, 3: 0.60, 4: 1.00}

# Maps a room's activity multiplier to the fame-bump "audience" magnitude.
_FAME_AUDIENCE_PER_MULTIPLIER = 10


def compute_spread_value(*, base_value: int, success_level: int, multiplier: float) -> int:
    """Legend value a single telling adds, before the per-deed cap clamp.

    ``base × tier_payoff(success_level) × traffic_multiplier``. Failures (or
    success_level <= 0) add nothing. success_level above the table tops out at
    the max payoff fraction.
    """
    if success_level <= 0:
        return 0
    payoff = TIER_PAYOFF.get(success_level, max(TIER_PAYOFF.values()))
    return round(base_value * payoff * multiplier)


# Spreading a tale ("story-weaving") takes a FORM, modelled as a specialization
# under a parent skill (#745). The chosen form sets which SKILL the check rolls
# (its parent — Performance for the artistic forms, Persuasion for propaganda);
# no form rolls plain Performance. A form the teller HAS stacks its value.
PERFORMANCE_SKILL_NAME = "Performance"
PERSUASION_SKILL_NAME = "Persuasion"

# (form name, parent skill name, description)
SPREAD_FORMS: list[tuple[str, str, str]] = [
    ("Oratory", PERFORMANCE_SKILL_NAME, "Telling the deed aloud — a rousing speech."),
    ("Prose", PERFORMANCE_SKILL_NAME, "Telling the deed in writing."),
    ("Singing", PERFORMANCE_SKILL_NAME, "Telling the deed in song."),
    ("Propaganda", PERSUASION_SKILL_NAME, "Bending the deed's telling toward a cause."),
]

_SKILL_DESCRIPTIONS = {
    PERFORMANCE_SKILL_NAME: "Captivating an audience through music, oration, or storytelling.",
    PERSUASION_SKILL_NAME: "Swaying others through argument, charm, and rhetoric.",
}


def _ensure_skill(name: str):
    from world.skills.models import Skill  # noqa: PLC0415
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415

    trait, _ = Trait.objects.get_or_create(
        name=name,
        defaults={
            "trait_type": TraitType.SKILL,
            "category": TraitCategory.SOCIAL,
            "description": _SKILL_DESCRIPTIONS.get(name, ""),
        },
    )
    skill, _ = Skill.objects.get_or_create(trait=trait)
    return skill


def ensure_spread_skills() -> None:
    """Idempotently ensure the spread skills (Performance, Persuasion) + their
    form specializations exist.

    Called several times per spread (template build, modifiers, form list). The
    repo bans data migrations / seed commands pre-production, so this is the
    seed-on-first-use path — but the fast-path keeps the steady state at a single
    count query instead of re-running the get_or_creates every request.
    """
    from world.skills.models import Specialization  # noqa: PLC0415

    form_names = [name for name, _, _ in SPREAD_FORMS]
    already_seeded = Specialization.objects.filter(
        name__in=form_names,
        parent_skill__trait__name__in=[PERFORMANCE_SKILL_NAME, PERSUASION_SKILL_NAME],
    ).count() == len(SPREAD_FORMS)
    if already_seeded:
        return

    skills_by_name = {
        PERFORMANCE_SKILL_NAME: _ensure_skill(PERFORMANCE_SKILL_NAME),
        PERSUASION_SKILL_NAME: _ensure_skill(PERSUASION_SKILL_NAME),
    }
    for form_name, parent_name, description in SPREAD_FORMS:
        Specialization.objects.get_or_create(
            parent_skill=skills_by_name[parent_name],
            name=form_name,
            defaults={"description": description},
        )


def get_spread_specializations():
    """The forms a teller may apply when spreading (across Performance + Persuasion)."""
    from world.skills.models import Specialization  # noqa: PLC0415

    ensure_spread_skills()
    form_names = [name for name, _, _ in SPREAD_FORMS]
    # Scope to the spread skills' parents — Specialization.name is unique only
    # per parent_skill, so a same-named spec under another skill must not leak in.
    return Specialization.objects.filter(
        name__in=form_names,
        parent_skill__trait__name__in=[PERFORMANCE_SKILL_NAME, PERSUASION_SKILL_NAME],
        is_active=True,
    ).order_by("display_order", "name")


def _value_points(value) -> int:
    from world.traits.models import PointConversionRange, TraitType  # noqa: PLC0415

    if not value:
        return 0
    return PointConversionRange.calculate_points(TraitType.SKILL, value)


def spread_check_modifiers(character, specialization=None) -> int:
    """Roller-point bonus for a spread: the form's parent skill + the form itself.

    No form rolls plain Performance. A form/skill the character lacks contributes
    nothing for that part (you may attempt a form you're unskilled in).
    """
    from world.skills.models import (  # noqa: PLC0415
        CharacterSkillValue,
        CharacterSpecializationValue,
    )

    ensure_spread_skills()
    skill = specialization.parent_skill if specialization else _ensure_skill(PERFORMANCE_SKILL_NAME)
    skill_value = (
        CharacterSkillValue.objects.filter(character=character, skill=skill)
        .values_list("value", flat=True)
        .first()
    )
    total = _value_points(skill_value)
    if specialization is not None:
        spec_value = (
            CharacterSpecializationValue.objects.filter(
                character=character, specialization=specialization
            )
            .values_list("value", flat=True)
            .first()
        )
        total += _value_points(spec_value)
    return total


def get_or_create_spread_a_tale_template():
    """Ensure the 'Spread a Tale' ActionTemplate exists, returning it.

    Idempotent. The base check is a light presence read; the form's SKILL +
    specialization are added as roller modifiers by the spread flow (so the skill
    flexes with the chosen form — Performance or Persuasion). Area action; charges
    20 AP + light social fatigue.
    """
    from decimal import Decimal  # noqa: PLC0415

    from actions.constants import ActionTargetType, Pipeline  # noqa: PLC0415
    from actions.models.action_templates import ActionTemplate  # noqa: PLC0415
    from world.checks.models import CheckCategory, CheckType, CheckTypeTrait  # noqa: PLC0415
    from world.traits.models import Trait, TraitCategory, TraitType  # noqa: PLC0415

    # Fast-path: once seeded, the template (and its skills) exist, so a single
    # fetch per spread suffices instead of replaying every get_or_create below.
    existing = ActionTemplate.objects.filter(name=SPREAD_TALE_TEMPLATE_NAME).first()
    if existing is not None:
        return existing

    ensure_spread_skills()
    category, _ = CheckCategory.objects.get_or_create(name="Social")
    check_type, _ = CheckType.objects.get_or_create(
        name=SPREAD_TALE_TEMPLATE_NAME,
        defaults={
            "category": category,
            "description": "Telling a deed's tale to a crowd.",
        },
    )
    presence, _ = Trait.objects.get_or_create(
        name="presence",
        defaults={"trait_type": TraitType.STAT, "category": TraitCategory.SOCIAL},
    )
    CheckTypeTrait.objects.get_or_create(
        check_type=check_type, trait=presence, defaults={"weight": Decimal("0.5")}
    )
    template, _ = ActionTemplate.objects.get_or_create(
        name=SPREAD_TALE_TEMPLATE_NAME,
        defaults={
            "check_type": check_type,
            "target_type": ActionTargetType.AREA,
            "category": "social",
            "pipeline": Pipeline.SINGLE,
            "ap_cost": 20,
            "social_fatigue_cost": 3,
            "accepts_pose_text": True,
            "icon": "megaphone",
        },
    )
    return template


def get_spreadable_deeds(persona) -> QuerySet[LegendEntry]:
    """Active deeds the persona KNOWS (#902 union).

    Society awareness (org memberships) ∪ their own deeds ∪ witnessed /
    heard-told knowledge rows ∪ common knowledge (total ≥ 5× base). Inactive
    deeds and tales the persona has no path to are excluded.
    """
    from world.societies.knowledge_services import known_deed_ids  # noqa: PLC0415

    return LegendEntry.objects.filter(pk__in=known_deed_ids(persona)).order_by("-created_at")


def save_deed_story(*, author_persona, deed, text: str):
    """Upsert ``author_persona``'s written account of ``deed`` (#745 Phase 4).

    One account per (deed, author) — re-saving replaces the prior text. The
    caller is responsible for awareness/ownership gating; this is a pure write.
    """
    from world.societies.models import LegendDeedStory  # noqa: PLC0415

    story, _ = LegendDeedStory.objects.update_or_create(
        deed=deed, author=author_persona, defaults={"text": text}
    )
    return story


def get_deed_stories(deed):
    """The written accounts of ``deed``, newest-edited first (#745 Phase 4)."""
    from world.societies.models import LegendDeedStory  # noqa: PLC0415

    return (
        LegendDeedStory.objects.filter(deed=deed).select_related("author").order_by("-updated_at")
    )


def _resolve_spread_tale(action_request, result) -> None:
    """Post-resolution side-effect for the ``spread_a_tale`` scene action.

    On a successful check, adds traffic-scaled legend to the deed (clamped to
    its cap by ``spread_deed``), bumps the subject's fame, and notifies them.
    No-op on failure, missing deed, or no check outcome.
    """
    from decimal import Decimal  # noqa: PLC0415

    from world.locations.activity_services import room_activity_band  # noqa: PLC0415
    from world.societies.notifications import notify_spread_event  # noqa: PLC0415
    from world.societies.renown import apply_spread_fame_bump  # noqa: PLC0415
    from world.societies.services import spread_deed  # noqa: PLC0415

    deed = action_request.spread_deed_target
    main = result.action_resolution.main_result
    if deed is None or main is None or main.check_result is None:
        return
    success_level = main.check_result.success_level
    if success_level <= 0:
        return

    room = action_request.scene.location if action_request.scene else None
    band = room_activity_band(room)
    value = compute_spread_value(
        base_value=deed.base_value, success_level=success_level, multiplier=band.multiplier
    )
    if value <= 0:
        return

    spread_deed(
        deed=deed,
        spreader_persona=action_request.initiator_persona,
        value_added=value,
        description=action_request.pose_text,
        method=action_request.action_key,
        audience_factor=Decimal(str(band.multiplier)),
        scene=action_request.scene,
    )
    if action_request.scene is not None:
        # #902 — everyone on the scene list heard the tale told and may now
        # see it on the subject's card and retell it themselves.
        from world.societies.constants import DeedKnowledgeSource  # noqa: PLC0415
        from world.societies.knowledge_services import (  # noqa: PLC0415
            grant_deed_knowledge,
            scene_witness_personas,
        )

        grant_deed_knowledge(
            deed=deed,
            personas=scene_witness_personas(action_request.scene),
            source=DeedKnowledgeSource.HEARD_TOLD,
        )
    tier_changed = apply_spread_fame_bump(
        deed,
        npc_audience=int(band.multiplier * _FAME_AUDIENCE_PER_MULTIPLIER),
        success_level=success_level,
    )
    notify_spread_event(deed, fame_tier_changed=tier_changed)


register_resolver(SPREAD_TALE_ACTION_KEY, _resolve_spread_tale)
