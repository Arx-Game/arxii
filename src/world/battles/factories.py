"""FactoryBoy factories for the battles system tests."""

from __future__ import annotations

import factory
import factory.django as factory_django

from world.battles.constants import (
    DEFAULT_VICTORY_THRESHOLD,
    BattleActionKind,
    BattleParticipantStatus,
    BattleSideRole,
    BattleUnitStatus,
)
from world.battles.models import (
    Battle,
    BattleActionDeclaration,
    BattleParticipant,
    BattlePlace,
    BattleRound,
    BattleSide,
    BattleUnit,
)
from world.magic.factories import TechniqueFactory
from world.scenes.constants import RoundStatus


class BattleFactory(factory_django.DjangoModelFactory):
    """Creates a Battle; the backing Scene is auto-created by Battle.save()."""

    class Meta:
        model = Battle

    name = factory.Sequence(lambda n: f"Battle {n}")
    # Do NOT pass scene — save() auto-creates it.


class BattleSideFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = BattleSide

    battle = factory.SubFactory(BattleFactory)
    role = BattleSideRole.ATTACKER
    victory_threshold = DEFAULT_VICTORY_THRESHOLD


class BattlePlaceFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = BattlePlace

    battle = factory.SubFactory(BattleFactory)
    name = factory.Sequence(lambda n: f"Place {n}")


class BattleUnitFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = BattleUnit

    battle = factory.SubFactory(BattleFactory)
    side = factory.SubFactory(BattleSideFactory, battle=factory.SelfAttribute("..battle"))
    name = factory.Sequence(lambda n: f"Unit {n}")
    descriptor = "generic"
    strength = 100
    status = BattleUnitStatus.ACTIVE


class BattleRoundFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = BattleRound

    battle = factory.SubFactory(BattleFactory)
    round_number = 1
    status = RoundStatus.BETWEEN_ROUNDS


class BattleParticipantFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = BattleParticipant

    battle = factory.SubFactory(BattleFactory)
    side = factory.SubFactory(BattleSideFactory, battle=factory.SelfAttribute("..battle"))
    character_sheet = factory.SubFactory("world.character_sheets.factories.CharacterSheetFactory")
    status = BattleParticipantStatus.ACTIVE


class BattleActionDeclarationFactory(factory_django.DjangoModelFactory):
    class Meta:
        model = BattleActionDeclaration

    battle_round = factory.SubFactory(BattleRoundFactory)
    participant = factory.SubFactory(
        BattleParticipantFactory,
        battle=factory.SelfAttribute("..battle_round.battle"),
    )
    technique = factory.SubFactory(TechniqueFactory, action_template=None)
    action_kind = BattleActionKind.STRIKE
    resolved = False
    success_level = 0


def ensure_battle_command_modifier_target():
    """Idempotently seed the "Battle Command" ModifierTarget (#1711).

    category="stat" is already in EQUIPMENT_RELEVANT_CATEGORIES
    (world/mechanics/constants.py), so authored covenant-role/facet/mantle
    bonuses against this target flow through the existing
    get_modifier_total/equipment_walk_total seam with no new plumbing —
    only the target row itself is new. Mirrors world/vitals/factories.py's
    ensure_surrounded_content idempotent-seed pattern.
    """
    from world.battles.constants import BATTLE_COMMAND_TARGET_NAME
    from world.mechanics.constants import STAT_CATEGORY_NAME
    from world.mechanics.models import ModifierCategory, ModifierTarget

    stat_category, _ = ModifierCategory.objects.get_or_create(
        name=STAT_CATEGORY_NAME,
        defaults={"description": "Primary character statistics.", "display_order": 10},
    )
    target, _ = ModifierTarget.objects.get_or_create(
        category=stat_category,
        name=BATTLE_COMMAND_TARGET_NAME,
        defaults={
            "description": "Leadership bonus a commander grants to participants "
            "fighting alongside their commanded unit (#1711).",
            "is_active": True,
        },
    )
    return target
