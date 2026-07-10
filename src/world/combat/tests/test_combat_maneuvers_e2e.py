"""E2E: combat verbs through the shared dispatch seam (#1453, #1452).

Each test dispatches a verb's REGISTRY ``ActionRef`` via ``dispatch_player_action``
— the exact path both telnet (``CmdCombat``) and the web viewset use — and asserts
real encounter state, proving telnet/web convergence end to end.
"""

from __future__ import annotations

from django.test import TestCase

from actions.constants import ActionBackend
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import (
    CombatManeuver,
    EncounterType,
    ParticipantStatus,
)
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.models import CombatParticipant, CombatRoundAction
from world.scenes.constants import RoundStatus
from world.vitals.models import CharacterVitals


def _ref(registry_key: str) -> ActionRef:
    return ActionRef(backend=ActionBackend.REGISTRY, registry_key=registry_key)


class CombatManeuverDispatchE2E(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING,
            round_number=1,
        )
        cls.char = CharacterFactory(db_key="e2echar")
        cls.sheet = CharacterSheetFactory(character=cls.char)
        cls.participant = CombatParticipantFactory(
            encounter=cls.encounter,
            character_sheet=cls.sheet,
            status=ParticipantStatus.ACTIVE,
        )
        CharacterVitals.objects.get_or_create(
            character_sheet=cls.sheet,
            defaults={"health": 50, "max_health": 100},
        )

    def _round_action(self) -> CombatRoundAction:
        return CombatRoundAction.objects.get(participant=self.participant, round_number=1)

    def test_flee_then_ready_toggle(self) -> None:
        result = dispatch_player_action(self.char, _ref("combat_flee"), {})
        self.assertTrue(result.detail.success, result.detail.message)
        action = self._round_action()
        self.assertEqual(action.maneuver, CombatManeuver.FLEE)
        self.assertTrue(action.is_ready)  # flee auto-readies
        dispatch_player_action(self.char, _ref("combat_ready"), {})
        action.refresh_from_db()
        self.assertFalse(action.is_ready)

    def test_cover_targets_ally(self) -> None:
        ally = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=CharacterSheetFactory(character=CharacterFactory(db_key="e2eally")),
            status=ParticipantStatus.ACTIVE,
        )
        result = dispatch_player_action(
            self.char, _ref("combat_cover"), {"ally_participant_id": ally.pk}
        )
        self.assertTrue(result.detail.success, result.detail.message)
        action = self._round_action()
        self.assertEqual(action.maneuver, CombatManeuver.COVER)
        self.assertEqual(action.focused_ally_target_id, ally.pk)

    def test_interpose_no_target(self) -> None:
        result = dispatch_player_action(self.char, _ref("combat_interpose"), {})
        self.assertTrue(result.detail.success, result.detail.message)
        action = self._round_action()
        self.assertEqual(action.maneuver, CombatManeuver.INTERPOSE)
        self.assertIsNone(action.focused_ally_target_id)

    def test_use_item_by_name_targets_ally(self) -> None:
        """The ``combat use <item> on <ally>`` telnet grammar's dispatch kwargs (#2120)."""
        from evennia_extensions.factories import ObjectDBFactory
        from world.items.factories import ItemInstanceFactory, ItemTemplateFactory

        item_obj = ObjectDBFactory(db_key="e2e potion", location=self.char)
        item = ItemInstanceFactory(template=ItemTemplateFactory(), game_object=item_obj)
        ally = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=CharacterSheetFactory(
                character=CharacterFactory(db_key="e2eusetarget")
            ),
            status=ParticipantStatus.ACTIVE,
        )
        result = dispatch_player_action(
            self.char,
            _ref("combat_use"),
            {"item_name": "e2e potion", "ally_participant_id": ally.pk},
        )
        self.assertTrue(result.detail.success, result.detail.message)
        action = self._round_action()
        self.assertEqual(action.maneuver, CombatManeuver.USE_ITEM)
        self.assertEqual(action.item_instance_id, item.pk)
        self.assertEqual(action.focused_ally_target_id, ally.pk)


class UseItemDispatchResolveE2E(TestCase):
    """Declare-and-resolve a USE_ITEM round through dispatch_player_action (#2120).

    The shared telnet+web dispatch seam this test drives is exactly what
    ``CmdCombat``'s ``combat use <item> on <target>`` subverb and the web
    ``use_item`` action both reach — proving the round-resolution half (pool
    effect applied to the declared ally, item charge decremented) works
    end-to-end, not just the declare-side wiring.
    """

    def test_declare_and_resolve_applies_effect_to_ally_and_decrements_charge(self) -> None:
        from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
        from evennia_extensions.factories import ObjectDBFactory
        from world.checks.constants import EffectTarget
        from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
        from world.combat.constants import OpponentTier
        from world.combat.factories import CombatOpponentFactory
        from world.combat.services import resolve_round
        from world.conditions.factories import ConditionTemplateFactory
        from world.conditions.models import ConditionInstance
        from world.items.factories import ItemInstanceFactory, ItemTemplateFactory

        encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        CombatOpponentFactory(encounter=encounter, tier=OpponentTier.MOOK)
        actor = CharacterFactory(db_key="e2eresolveuser")
        actor_sheet = CharacterSheetFactory(character=actor)
        actor_participant = CombatParticipantFactory(
            encounter=encounter, character_sheet=actor_sheet, status=ParticipantStatus.ACTIVE
        )
        ally = CharacterFactory(db_key="e2eresolveally", location=actor.location)
        ally_sheet = CharacterSheetFactory(character=ally)
        ally_participant = CombatParticipantFactory(
            encounter=encounter, character_sheet=ally_sheet, status=ParticipantStatus.ACTIVE
        )
        for sheet in (actor_sheet, ally_sheet):
            CharacterVitals.objects.get_or_create(
                character_sheet=sheet, defaults={"health": 50, "max_health": 100}
            )

        condition = ConditionTemplateFactory()
        pool = ConsequencePoolFactory()
        consequence = ConsequenceFactory(label="E2EUseItemTarget")
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type="apply_condition",
            target=EffectTarget.TARGET,
            condition_template=condition,
        )
        template = ItemTemplateFactory(
            name="E2EUseItemPotion",
            is_consumable=True,
            max_charges=2,
            on_use_pool=pool,
            on_use_check_type=None,
            on_use_target_kind="character",
        )
        item_obj = ObjectDBFactory(db_key="e2e heal potion", location=actor)
        item = ItemInstanceFactory(template=template, game_object=item_obj, charges=2)

        result = dispatch_player_action(
            actor,
            _ref("combat_use"),
            {"item_instance_id": item.pk, "ally_participant_id": ally_participant.pk},
        )
        self.assertTrue(result.detail.success, result.detail.message)
        action = CombatRoundAction.objects.get(
            participant=actor_participant, round_number=encounter.round_number
        )
        self.assertEqual(action.maneuver, CombatManeuver.USE_ITEM)

        resolve_round(encounter)

        self.assertTrue(ConditionInstance.objects.filter(target=ally, condition=condition).exists())
        self.assertFalse(
            ConditionInstance.objects.filter(target=actor, condition=condition).exists()
        )
        item.refresh_from_db()
        self.assertEqual(item.charges, 1)


class JoinLeaveDispatchE2E(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.encounter = CombatEncounterFactory(
            encounter_type=EncounterType.OPEN_ENCOUNTER,
            status=RoundStatus.BETWEEN_ROUNDS,
            round_number=1,
        )
        # An anchor participant so the leave does not abandon the encounter.
        CombatParticipantFactory(
            encounter=cls.encounter,
            character_sheet=CharacterSheetFactory(character=CharacterFactory(db_key="anchore2e")),
            status=ParticipantStatus.ACTIVE,
        )
        cls.joiner = CharacterFactory(db_key="joindispatch")
        cls.joiner_sheet = CharacterSheetFactory(character=cls.joiner)

    def test_join_then_leave(self) -> None:
        joined = dispatch_player_action(
            self.joiner,
            _ref("combat_join"),
            {"encounter_id": self.encounter.pk, "character_sheet_id": self.joiner_sheet.pk},
        )
        self.assertTrue(joined.detail.success, joined.detail.message)
        self.assertTrue(
            CombatParticipant.objects.filter(
                encounter=self.encounter,
                character_sheet=self.joiner_sheet,
                status=ParticipantStatus.ACTIVE,
            ).exists()
        )
        left = dispatch_player_action(self.joiner, _ref("combat_leave"), {})
        self.assertTrue(left.detail.success, left.detail.message)
        self.assertFalse(
            CombatParticipant.objects.filter(
                encounter=self.encounter,
                character_sheet=self.joiner_sheet,
                status=ParticipantStatus.ACTIVE,
            ).exists()
        )

    def test_join_resolves_room_encounter_without_id(self) -> None:
        """Telnet path: no ids — encounter resolves from the actor's room, sheet from the actor."""
        self.joiner.location = self.encounter.room
        result = dispatch_player_action(self.joiner, _ref("combat_join"), {})
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertTrue(
            CombatParticipant.objects.filter(
                encounter=self.encounter,
                character_sheet=self.joiner_sheet,
                status=ParticipantStatus.ACTIVE,
            ).exists()
        )
