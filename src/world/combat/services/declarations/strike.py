"""The basic Strike (#4858): an attack any character makes with no technique.

The player picks one of their equipped weapons, or bare hands, and an opponent. At
resolution the Strike rolls a hit roll on the strike skill for the weapon's gear kind
(``STRIKE_CHECK_TYPE_BY_ARCHETYPE``) against the opponent, through the shared attack-roll
seam (``CombatTechniqueResolver.roll_check_with_breakdown``), so effort, pulls, bonds,
wind, the intensity to hit, check modifiers and CHECK_BONUS vow perks all count. If it
lands, a damage roll of the same skill (no difficulty, no modifiers) scales the weapon's
damage by the damage multiplier for its success level, never below the Strike's base
damage. Bare hands are the weakest Unarmed weapon, their own floor. Modifiers on "Strike:
base damage" (a vow's stat scaling, say) add to every landed Strike. A miss raises the
attacker's intensity (``record_miss_intensity``).

Both rolls are recorded as ``ConsequenceOutcome`` rows on the Strike's combat interaction,
hit roll first, each summary naming the strike skill and stat, so the web turn panel shows
the hit roll and then the damage roll.
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from django.db import transaction

from world.combat import services as _svc
from world.combat.constants import (
    ENTITY_TYPE_PC,
    STRIKE_CHECK_TYPE_BY_ARCHETYPE,
    STRIKE_HIT_QUALITY,
    UNARMED_STRIKE_CHECK_TYPE_NAME,
    ActionCategory,
    CombatManeuver,
    OpponentStatus,
)
from world.combat.models import CombatOpponent, CombatParticipant, CombatRoundAction
from world.combat.types import ActionOutcome, StrikeWeapon
from world.fatigue.constants import EffortLevel
from world.items.constants import WEAPON_ARCHETYPES, GearArchetype
from world.scenes.constants import RoundStatus

if TYPE_CHECKING:
    from collections.abc import Sequence

    from typeclasses.characters import Character
    from world.checks.models import CheckType
    from world.checks.outcome_models import ConsequenceOutcome
    from world.checks.types import CheckResult, ModifierBreakdown, RollBreakdown, RollLine
    from world.combat.types import OpponentDamageResult
    from world.conditions.models import DamageType
    from world.items.models import ItemInstance

    StrikeRoll = tuple[CheckType, ModifierBreakdown, str, int | None]

BARE_HANDS_NAME = "bare hands"
_RANGED_ARCHETYPES = frozenset({GearArchetype.RANGED, GearArchetype.THROWN})


# ---------------------------------------------------------------------------
# Weapons and the strike skill
# ---------------------------------------------------------------------------


def bare_hands() -> StrikeWeapon:
    """Bare hands: the Unarmed weapon every character has, needing no item."""
    return StrikeWeapon(
        item_instance=None,
        name=BARE_HANDS_NAME,
        gear_archetype=GearArchetype.UNARMED,
        check_type_name=UNARMED_STRIKE_CHECK_TYPE_NAME,
    )


def strike_weapon_for_item(item_instance: ItemInstance) -> StrikeWeapon | None:
    """``item_instance`` as a Strike weapon, or None when its gear kind is not a weapon."""
    archetype = item_instance.template.gear_archetype
    if archetype not in WEAPON_ARCHETYPES:
        return None
    return StrikeWeapon(
        item_instance=item_instance,
        name=item_instance.display_name,
        gear_archetype=archetype,
        check_type_name=STRIKE_CHECK_TYPE_BY_ARCHETYPE[archetype],
    )


def strike_weapon_options(character: Character) -> list[StrikeWeapon]:
    """What ``character`` can Strike with: each equipped weapon, then bare hands."""
    options: list[StrikeWeapon] = []
    seen: set[int] = set()
    for equipped in character.equipped_items:
        inst = equipped.item_instance
        if inst.pk in seen:
            continue
        weapon = strike_weapon_for_item(inst)
        if weapon is not None:
            seen.add(inst.pk)
            options.append(weapon)
    options.append(bare_hands())
    return options


def strike_check_type(weapon: StrikeWeapon) -> CheckType | None:
    """The active check type of ``weapon``'s strike skill, or None when it is not authored.

    The Required content dashboard lists a missing strike check type.
    """
    from world.checks.models import CheckType  # noqa: PLC0415

    return CheckType.objects.filter(name=weapon.check_type_name, is_active=True).first()


def strike_reaches(attacker: Character, weapon: StrikeWeapon, opponent: CombatOpponent) -> bool:
    """Whether ``weapon`` reaches ``opponent`` from where ``attacker`` stands.

    A bow or a thrown weapon reaches anywhere in the room; every other Strike reaches the
    attacker's own position or the next, the waiting strike's melee reach. Lenient when
    either side is unplaced, as every reach check is.
    """
    from world.areas.positioning.services import position_of, position_reachable  # noqa: PLC0415
    from world.magic.constants import TechniqueReach  # noqa: PLC0415

    if opponent.objectdb is None:
        return True
    origin = position_of(attacker)
    target = position_of(opponent.objectdb)
    if origin is None or target is None:
        return True
    reach = (
        TechniqueReach.ANY
        if weapon.gear_archetype in _RANGED_ARCHETYPES
        else TechniqueReach.ADJACENT
    )
    return position_reachable(origin, target, reach)


def _weapon_of(action: CombatRoundAction) -> StrikeWeapon:
    """The weapon a declared Strike is made with: its item, or bare hands."""
    if action.item_instance is None:
        return bare_hands()
    return strike_weapon_for_item(action.item_instance) or bare_hands()


# ---------------------------------------------------------------------------
# Declaring
# ---------------------------------------------------------------------------


def declare_strike(
    participant: CombatParticipant,
    opponent: CombatOpponent,
    item_instance: ItemInstance | None = None,
) -> CombatRoundAction:
    """Declare a Strike at ``opponent`` with ``item_instance`` (None: bare hands).

    The weapon must be one of the character's equipped weapons. The strike skill for its
    gear kind must have an authored check type. The Strike is the round's one action:
    it replaces any technique declared this round.

    Raises ValueError with a plain message for each refusal.
    """
    from world.vitals.services import can_act  # noqa: PLC0415

    encounter = participant.encounter
    if not can_act(participant.character_sheet):
        msg = "Cannot strike: character is dead or incapacitated."
        raise ValueError(msg)
    if encounter.status != RoundStatus.DECLARING:
        msg = (
            f"Cannot strike: encounter status is "
            f"'{encounter.get_status_display()}', expected 'Declaring'."
        )
        raise ValueError(msg)
    if opponent.encounter_id != encounter.pk or opponent.status != OpponentStatus.ACTIVE:
        msg = "Cannot strike: that opponent is not fighting in this encounter."
        raise ValueError(msg)

    character = participant.character_sheet.character
    if item_instance is None:
        weapon = bare_hands()
    else:
        weapon = next(
            (
                option
                for option in strike_weapon_options(character)
                if option.item_instance is not None and option.item_instance.pk == item_instance.pk
            ),
            None,
        )
        if weapon is None:
            msg = "Cannot strike: you have no such weapon equipped."
            raise ValueError(msg)
    if strike_check_type(weapon) is None:
        msg = f"Cannot strike with {weapon.name}: {weapon.check_type_name} is not set up yet."
        raise ValueError(msg)
    if not strike_reaches(character, weapon, opponent):
        msg = f"Cannot strike: {opponent.name} is out of reach of your {weapon.name}."
        raise ValueError(msg)

    action, _created = CombatRoundAction.objects.update_or_create(
        participant=participant,
        round_number=encounter.round_number,
        defaults={
            "focused_action": None,
            "focused_category": ActionCategory.PHYSICAL,
            "effort_level": EffortLevel.MEDIUM,
            "focused_opponent_target": opponent,
            "focused_ally_target": None,
            "maneuver": CombatManeuver.STRIKE,
            "item_instance": item_instance,
            "physical_passive": None,
            "social_passive": None,
            "mental_passive": None,
            "combo_upgrade": None,
            "is_ready": False,
        },
    )
    return action


# ---------------------------------------------------------------------------
# Resolving
# ---------------------------------------------------------------------------


def _stat_label(check_type: CheckType, stat_override: str | int | None) -> str:
    """The stat a strike roll used, as a player reads it."""
    from world.traits.models import TraitType  # noqa: PLC0415

    if isinstance(stat_override, str):
        return stat_override.capitalize()
    if isinstance(stat_override, int):
        return "Strength and Agility"
    stat = next(
        (
            leg.trait.name
            for leg in check_type.traits.select_related("trait")
            if leg.trait.trait_type == TraitType.STAT
        ),
        None,
    )
    return stat.capitalize() if stat else "no stat"


def _weapon_damage(participant: CombatParticipant, weapon: StrikeWeapon) -> tuple[int, int]:
    """(the weapon's damage, the floor a landed Strike never drops below)."""
    from world.combat.services.equipment.combat_target_bonus import (  # noqa: PLC0415
        _combat_target_bonus,
    )
    from world.items.constants import WEAPON_DAMAGE_TARGET_NAME  # noqa: PLC0415
    from world.mechanics.constants import ManeuverEffectKey  # noqa: PLC0415
    from world.mechanics.effect_targets import effect_modifier_total  # noqa: PLC0415
    from world.mechanics.maneuver_effects import get_maneuver_effect  # noqa: PLC0415

    sheet = participant.character_sheet
    if weapon.item_instance is None:
        # Only modifiers scoped to bare hands themselves: a broad damage modifier is
        # counted once, through "Strike: base damage" below.
        key = ManeuverEffectKey.STRIKE_BARE_HANDS_DAMAGE
        damage = max(
            0,
            get_maneuver_effect(key).base_value
            + effect_modifier_total(sheet, key, kind_wide=False),
        )
        return damage, damage
    damage = weapon.item_instance.effective_weapon_damage + _combat_target_bonus(
        sheet, WEAPON_DAMAGE_TARGET_NAME
    )
    # The base damage's own modifiers are added by _strike_damage, to every landed Strike.
    floor = get_maneuver_effect(ManeuverEffectKey.STRIKE_BASE_DAMAGE).base_value
    return max(0, damage), floor


def _strike_damage(
    participant: CombatParticipant, weapon: StrikeWeapon, damage_roll: CheckResult
) -> tuple[int, int, DamageType | None]:
    """(the weapon's damage before the roll, what the landed Strike deals before soak, and
    its damage type: the weapon's, untyped being Physical)."""
    from world.conditions.services import (  # noqa: PLC0415
        get_damage_multiplier,
        resolved_damage_type,
        scaled_outgoing_damage,
    )
    from world.mechanics.constants import ManeuverEffectKey  # noqa: PLC0415
    from world.mechanics.effect_targets import effect_modifier_total  # noqa: PLC0415

    weapon_damage, floor = _weapon_damage(participant, weapon)
    multiplier = get_damage_multiplier(damage_roll.success_level or 0)
    rolled = max(floor, int(weapon_damage * multiplier))
    total = max(
        0,
        rolled
        + effect_modifier_total(participant.character_sheet, ManeuverEffectKey.STRIKE_BASE_DAMAGE),
    )
    damage_type = resolved_damage_type(
        weapon.item_instance.effective_weapon_damage_type
        if weapon.item_instance is not None
        else None
    )
    dealt = scaled_outgoing_damage(participant.character_sheet.character, total, damage_type)
    return weapon_damage, dealt, damage_type


def _skill_rating(participant: CombatParticipant, check_type: CheckType) -> int | None:
    """The striker's rating in the skill ``check_type`` weights, now; None with no skill.

    Stored with each roll so the breakdown shows what was rolled, not a later rating.
    """
    from world.traits.models import CharacterTraitValue  # noqa: PLC0415

    skill, _stats = strike_check_traits({check_type.pk})[check_type.pk]
    if skill is None:
        return None
    return (
        CharacterTraitValue.objects.filter(character=participant.character_sheet, trait__name=skill)
        .values_list("value", flat=True)
        .first()
    )


def _roll_hit(
    participant: CombatParticipant, action: CombatRoundAction, check_type: CheckType
) -> tuple[CheckResult, ModifierBreakdown]:
    """The hit roll through the shared attack-roll seam, with its modifiers."""
    from world.combat.services.techniques.technique_resolver import (  # noqa: PLC0415
        CombatTechniqueResolver,
    )

    resolver = CombatTechniqueResolver(
        participant=participant,
        action=action,
        pull_flat_bonus=0,
        fatigue_category=ActionCategory.PHYSICAL,
        offense_check_type=check_type,
        offense_check_fn=None,
        strike_weapon=_weapon_of(action),
    )
    return resolver.roll_check_with_breakdown()


def hit_quality(success_level: int | None) -> str:
    """The word for how well a landed Strike hit (``STRIKE_HIT_QUALITY``)."""
    level = success_level or 0
    word = STRIKE_HIT_QUALITY[0][1]
    for threshold, name in STRIKE_HIT_QUALITY:
        if level >= threshold:
            word = name
    return word


def hit_result_line(success_level: int | None, *, missed: bool) -> str:
    """The hit roll's result line: "Miss", or "Hit, <quality>"."""
    return "Miss" if missed else f"Hit, {hit_quality(success_level)}"


def strike_narration(  # noqa: PLR0913 - one narration line, its parts
    *,
    actor: str,
    target: str,
    weapon: StrikeWeapon,
    success_level: int | None,
    damage: int | None,
    defeated: bool = False,
    second_person: bool = False,
) -> str:
    """The line a Strike is told in: second person for the striker, third for the room.

    ``damage`` None is a miss. "You strike Bandit with your rapier. A good hit: 11 damage."
    and "Hobb strikes Bandit with a rapier. A good hit: 11 damage."
    """
    from core.text import with_indefinite_article  # noqa: PLC0415

    if second_person:
        subject, verb = "You", "strike"
        with_weapon = f"with your {weapon.name}"
    else:
        subject, verb = actor, "strikes"
        with_weapon = (
            f"with {weapon.name}"
            if weapon.is_bare_hands
            else f"with {with_indefinite_article(weapon.name)}"
        )
    if damage is None:
        miss = "miss" if second_person else "misses"
        return f"{subject} {verb} at {target} {with_weapon} and {miss}."
    tail = ", defeating them" if defeated else ""
    quality = with_indefinite_article(hit_quality(success_level))
    return (
        f"{subject} {verb} {target} {with_weapon}. "
        f"{quality[0].upper()}{quality[1:]} hit: {damage} damage{tail}."
    )


def _broadcast_strike(  # noqa: PLR0913 - one narration, its parts
    participant: CombatParticipant,
    action: CombatRoundAction,
    weapon: StrikeWeapon,
    target: CombatOpponent,
    hit: CheckResult,
    damage: OpponentDamageResult | None,
    rolls: list[StrikeRoll],
) -> None:
    """Record the Strike's interaction and its two rolls, narrate it to the room in the
    third person, and tell the striker in the second person (telnet hears that line
    instead of the room's)."""
    from world.checks.services import record_consequence_outcome  # noqa: PLC0415
    from world.combat.interaction_services import (  # noqa: PLC0415
        broadcast_action_outcome,
        create_action_interaction,
        render_action_declaration_label,
    )
    from world.scenes.interaction_services import (  # noqa: PLC0415
        non_web_sessions,
        push_interaction,
    )
    from world.scenes.services import active_persona_for_sheet  # noqa: PLC0415

    sheet = participant.character_sheet
    character = sheet.character
    interaction = create_action_interaction(
        participant=participant,
        round_number=action.round_number,
        summary_label=render_action_declaration_label(action),
    )
    if interaction is not None:
        action.interaction = interaction
        action.interaction_timestamp = interaction.timestamp
        action.save(update_fields=["interaction", "interaction_timestamp"])
        push_interaction(interaction)
        for check_type, breakdown, summary, skill_rating in rolls:
            record_consequence_outcome(
                sheet,
                check_type,
                None,
                None,
                breakdown,
                combat_interaction=interaction,
                summary=summary[:255],
                skill_rating=skill_rating,
            )

    narrate = partial(
        strike_narration,
        actor=active_persona_for_sheet(sheet).name,
        target=target.name,
        weapon=weapon,
        success_level=hit.success_level,
        damage=damage.damage_dealt if damage is not None else None,
        defeated=bool(damage is not None and damage.defeated),
    )
    broadcast_action_outcome(
        encounter=participant.encounter,
        narration=narrate(),
        telnet_exclude=(character,),
    )
    own_line = narrate(second_person=True)

    def _tell_striker() -> None:
        sessions = non_web_sessions(character)
        if sessions:
            character.msg(own_line, session=sessions)

    transaction.on_commit(_tell_striker)


def _resolve_strike(participant: CombatParticipant, action: CombatRoundAction) -> ActionOutcome:
    """Resolve a declared Strike: the hit roll, then the damage roll if it lands.

    Each roll is recorded with its result line as the summary ("Hit, good", "Miss",
    "11 damage"); ``strike_roll_breakdowns`` lays the rows out at read time.
    """
    from world.checks.types import ModifierBreakdown as _Breakdown  # noqa: PLC0415
    from world.combat.services.techniques.allegiance_break import (  # noqa: PLC0415
        _attempt_allegiance_breaks_for_action,
    )
    from world.combat.services.techniques.intensity import (  # noqa: PLC0415
        is_miss,
        record_miss_intensity,
    )
    from world.combat.services.techniques.npc_regard import (  # noqa: PLC0415
        _maybe_record_npc_regard_on_defeat,
    )
    from world.combat.stat_mapping import weapon_stat_for  # noqa: PLC0415
    from world.fatigue.services import apply_fatigue  # noqa: PLC0415

    outcome = ActionOutcome(entity_type=ENTITY_TYPE_PC, entity_label=str(participant))
    outcome.participant_id = participant.pk
    target = action.focused_opponent_target
    if target is None:
        return outcome
    target.refresh_from_db()
    if target.status != OpponentStatus.ACTIVE:
        return outcome

    character = participant.character_sheet.character
    weapon = _weapon_of(action)
    check_type = strike_check_type(weapon)
    if check_type is None:
        message = f"Your strike falters: {weapon.check_type_name} is not set up yet."
        transaction.on_commit(lambda: character.msg(message))
        return outcome
    if not strike_reaches(character, weapon, target):
        from world.combat.services.techniques.pc_action import (  # noqa: PLC0415
            _broadcast_fizzle_no_one_in_reach,
        )

        _broadcast_fizzle_no_one_in_reach(participant, action)
        return outcome

    rating = _skill_rating(participant, check_type)
    hit, hit_breakdown = _roll_hit(participant, action, check_type)
    missed = is_miss(hit.success_level)
    rolls: list[StrikeRoll] = [
        (check_type, hit_breakdown, hit_result_line(hit.success_level, missed=missed), rating)
    ]
    damage: OpponentDamageResult | None = None
    if missed:
        record_miss_intensity(participant)
    else:
        damage_roll = _svc.perform_check(
            character,
            check_type,
            target_difficulty=0,
            stat_override=weapon_stat_for(weapon.item_instance),
        )
        _weapon_damage_before, dealt, damage_type = _strike_damage(participant, weapon, damage_roll)
        damage = _svc.apply_damage_to_opponent(
            target, dealt, damage_type=damage_type, source_sheet=participant.character_sheet
        )
        outcome.damage_results.append(damage)
        if weapon.item_instance is not None:
            from world.items.services.durability import (  # noqa: PLC0415
                decrement_item_durability,
            )

            decrement_item_durability(item_instance=weapon.item_instance)
        rolls.append((check_type, _Breakdown(), f"{damage.damage_dealt} damage", rating))

    _attempt_allegiance_breaks_for_action(participant, outcome)
    apply_fatigue(participant.character_sheet, ActionCategory.PHYSICAL, 0, action.effort_level)
    _broadcast_strike(participant, action, weapon, target, hit, damage, rolls)
    _maybe_record_npc_regard_on_defeat(participant, action, target, outcome)
    return outcome


# ---------------------------------------------------------------------------
# Reading a Strike's rolls back (#4858)
# ---------------------------------------------------------------------------


def _gear_kind_words(weapon: StrikeWeapon) -> str:
    """ "one-handed melee", "bare hands": the weapon's kind as a row reads it."""
    if weapon.is_bare_hands:
        return "bare hands"
    return GearArchetype(weapon.gear_archetype).label.lower()


def _weapon_line(weapon: StrikeWeapon) -> RollLine:
    from world.checks.types import RollLine  # noqa: PLC0415

    if weapon.item_instance is None:
        return RollLine(label="Bare hands", value="", detail="the weakest Unarmed weapon")
    tier = weapon.item_instance.quality_tier
    label = f"{weapon.name}, {tier.name.lower()} quality" if tier is not None else weapon.name
    return RollLine(label=label, value="", detail="weapon damage and quality")


def strike_check_traits(check_type_ids: set[int]) -> dict[int, tuple[str | None, list[str]]]:
    """Per check type: (its strike skill's name or None, its stats' names). One query.

    The breakdown names the skill a check type actually weights, never assuming it shares
    the check type's name; production's Ranged Attack weights no skill at all.
    """
    from world.checks.models import CheckTypeTrait  # noqa: PLC0415
    from world.traits.models import TraitType  # noqa: PLC0415

    traits: dict[int, tuple[str | None, list[str]]] = {pk: (None, []) for pk in check_type_ids}
    for leg in CheckTypeTrait.objects.filter(check_type_id__in=check_type_ids).select_related(
        "trait"
    ):
        skill, stats = traits[leg.check_type_id]
        if leg.trait.trait_type == TraitType.SKILL and skill is None:
            skill = leg.trait.name
        elif leg.trait.trait_type == TraitType.STAT:
            stats = [*stats, leg.trait.name]
        traits[leg.check_type_id] = (skill, stats)
    return traits


def strike_skill_names(check_type_names: set[str]) -> dict[str, str]:
    """Per strike check type name, what a player calls it: its strike skill, or the check
    type's own name when it weights no skill."""
    from world.checks.models import CheckType  # noqa: PLC0415

    by_name = {ct.pk: ct.name for ct in CheckType.objects.filter(name__in=check_type_names)}
    traits = strike_check_traits(set(by_name))
    names = {name: name for name in check_type_names}
    for pk, name in by_name.items():
        names[name] = traits[pk][0] or name
    return names


def strike_roll_breakdowns(outcomes: Sequence[ConsequenceOutcome]) -> dict[int, RollBreakdown]:
    """The rows of each Strike roll among ``outcomes``, keyed by outcome pk.

    A Strike records its hit roll and then its damage roll on its interaction; the first
    is the hit roll. The rows name the strike skill the check type weights (with the
    rating stored with the roll; no skill row when it weights none), the stat or stats the
    roll used, the weapon and its quality, and the result line the roll was recorded
    with. The roll's modifiers are the caller's to add (it knows which a viewer may see).
    Outcomes from anything but a Strike are left out. A fixed number of queries however
    many outcomes.
    """
    from django.db.models import Min  # noqa: PLC0415

    from world.checks.outcome_models import ConsequenceOutcome  # noqa: PLC0415
    from world.checks.types import RollBreakdown, RollLine  # noqa: PLC0415
    from world.combat.stat_mapping import weapon_stat_for  # noqa: PLC0415

    interaction_ids = {o.combat_interaction_id for o in outcomes if o.combat_interaction_id}
    if not interaction_ids:
        return {}
    actions = {
        action.interaction_id: action
        for action in CombatRoundAction.objects.filter(
            interaction_id__in=interaction_ids, maneuver=CombatManeuver.STRIKE
        ).select_related(
            "item_instance__template", "item_instance__quality_tier", "focused_opponent_target"
        )
    }
    if not actions:
        return {}
    hit_pks = set(
        ConsequenceOutcome.objects.filter(combat_interaction_id__in=actions)
        .values("combat_interaction_id")
        .annotate(first=Min("pk"))
        .values_list("first", flat=True)
    )
    strike_outcomes = [o for o in outcomes if o.combat_interaction_id in actions]
    traits = strike_check_traits({o.check_type_id for o in strike_outcomes})

    breakdowns: dict[int, RollBreakdown] = {}
    for o in strike_outcomes:
        action = actions[o.combat_interaction_id]
        weapon = _weapon_of(action)
        skill, stats = traits[o.check_type_id]
        skill_lines: list[RollLine] = []
        # The rating stored with the roll: what was rolled, not today's rating.
        skill_value = str(o.skill_rating) if o.skill_rating is not None else ""
        if o.pk in hit_pks:
            if skill is not None:
                skill_lines.append(
                    RollLine(skill, skill_value, f"strike skill for {_gear_kind_words(weapon)}")
                )
            override = weapon_stat_for(weapon.item_instance)
            stat_names = (
                [_stat_label(o.check_type, override)]
                if override is not None
                else [stat.capitalize() for stat in stats]
            )
            stat_lines = [
                RollLine(stat, "", f"stat for {_gear_kind_words(weapon)}") for stat in stat_names
            ]
            target = action.focused_opponent_target
            heading = (
                f"Hit roll against {target.name}'s defense" if target is not None else "Hit roll"
            )
            lines = [*skill_lines, *stat_lines]
        else:
            heading = "Damage roll"
            if skill is not None:
                skill_lines.append(RollLine(skill, skill_value, "strike skill"))
            lines = [_weapon_line(weapon), *skill_lines]
        breakdowns[o.pk] = RollBreakdown(heading=heading, lines=lines, result=o.summary)
    return breakdowns
