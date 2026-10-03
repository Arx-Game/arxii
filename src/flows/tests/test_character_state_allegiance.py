"""Tests for ``CharacterState.get_display_allegiance`` (#4091 task 13).

Telnet ``look`` on a charmed/turned/calmed NPC shows the active hold, its fade, and
the SAME verbs the live commands gate on — never a parallel check. Demo Screen 2
(approved) is the exact-string fixture for the full-verb case.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import ObjectDBFactory
from flows.object_states.character_state import CharacterState
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import OpponentStatus
from world.combat.factories import CombatEncounterFactory, CombatOpponentFactory
from world.conditions.constants import Allegiance, DurationType
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)


class CharacterStateAllegianceFullVerbTests(TestCase):
    """Demo Screen 2: a named charmed NPC, seen by its charmer vs a bystander."""

    def setUp(self) -> None:
        self.room = ObjectDBFactory(
            db_key="Allegiance Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.wren = ObjectDBFactory(
            db_key="Wren",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.tamsin = ObjectDBFactory(
            db_key="Tamsin",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.captain = ObjectDBFactory(
            db_key="Captain Hale",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        CharacterSheetFactory(character=self.wren)
        CharacterSheetFactory(character=self.tamsin)
        CharacterSheetFactory(character=self.captain)

        self.enthralled = ConditionTemplateFactory(
            name="Enthralled",
            sets_allegiance=Allegiance.ALLY_OF_CASTER,
            has_progression=True,
            default_duration_type=DurationType.INGAME_TIME,
            is_visible_to_others=True,
        )
        ConditionStageFactory(condition=self.enthralled, stage_order=1, name="Smitten")
        self.fond_stage = ConditionStageFactory(
            condition=self.enthralled, stage_order=2, name="Fond"
        )
        ConditionStageFactory(condition=self.enthralled, stage_order=3, name="Devoted")

        self.instance = ConditionInstanceFactory(
            target=self.captain,
            condition=self.enthralled,
            current_stage=self.fond_stage,
            source_character=self.wren,
            # 3h20m rounds UP to "about 4 hours left" (brief's rounding rule).
            expires_at=timezone.now() + timedelta(hours=3, minutes=20),
        )

        self.context = MagicMock()
        self.context.get_state_by_pk = MagicMock(return_value=None)
        self.captain_state = CharacterState(self.captain, context=self.context)
        self.wren_state = CharacterState(self.wren, context=self.context)
        self.tamsin_state = CharacterState(self.tamsin, context=self.context)

    def test_source_sees_the_hold_and_every_verb(self) -> None:
        result = self.captain_state.get_display_allegiance(looker=self.wren_state)
        expected = (
            "Enthralled (Fond, stage 2 of 3), from Wren: about 4 hours left.\n"
            "You can: settle captain hale, retain captain hale, sendaway captain hale, "
            "cast <technique> at captain hale"
        )
        self.assertEqual(result, expected)

    def test_bystander_sees_the_hold_but_only_settle_and_cast(self) -> None:
        result = self.captain_state.get_display_allegiance(looker=self.tamsin_state)
        expected = (
            "Enthralled (Fond, stage 2 of 3), from Wren: about 4 hours left.\n"
            "You can: settle captain hale, cast <technique> at captain hale"
        )
        self.assertEqual(result, expected)

    def test_outranked_calmer_still_sees_sendaway(self) -> None:
        """#4091 final review: sendaway uses the send_away action's own predicate,
        not only the designating instance, so Tamsin's Calm under Wren's charm
        still offers her the verb the action would accept."""
        calm = ConditionTemplateFactory(
            name="Hushed",
            sets_allegiance=Allegiance.NEUTRAL,
            default_duration_type=DurationType.INGAME_TIME,
            is_visible_to_others=True,
        )
        ConditionInstanceFactory(
            target=self.captain,
            condition=calm,
            source_character=self.tamsin,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        result = self.captain_state.get_display_allegiance(looker=self.tamsin_state)
        self.assertIn("Enthralled (Fond, stage 2 of 3), from Wren", result)
        self.assertIn("sendaway captain hale", result)
        self.assertNotIn("retain captain hale", result)

    def test_omitted_from_return_appearance_when_no_hold(self) -> None:
        from world.conditions.services import remove_condition

        remove_condition(self.captain, self.enthralled)
        result = self.captain_state.return_appearance(looker=self.wren_state)
        self.assertNotIn("Enthralled", result)
        self.assertNotIn("You can:", result)

    def test_included_in_return_appearance_when_held(self) -> None:
        result = self.captain_state.return_appearance(looker=self.wren_state)
        self.assertIn("Enthralled (Fond, stage 2 of 3), from Wren: about 4 hours left.", result)
        self.assertIn("You can: settle captain hale", result)


class CharacterStateAllegianceVisibilityTests(TestCase):
    """A hidden hold shows nothing to anyone but its own source."""

    def setUp(self) -> None:
        self.room = ObjectDBFactory(
            db_key="Shadow Hall",
            db_typeclass_path="typeclasses.rooms.Room",
        )
        self.wren = ObjectDBFactory(
            db_key="Wren Hidden",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.tamsin = ObjectDBFactory(
            db_key="Tamsin Hidden",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        self.captain = ObjectDBFactory(
            db_key="Captain Shade",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        CharacterSheetFactory(character=self.wren)
        CharacterSheetFactory(character=self.tamsin)
        CharacterSheetFactory(character=self.captain)

        self.hidden = ConditionTemplateFactory(
            name="Secretly Turned",
            sets_allegiance=Allegiance.TURNED,
            is_visible_to_others=False,
            default_duration_type=DurationType.ROUNDS,
        )
        ConditionInstanceFactory(
            target=self.captain,
            condition=self.hidden,
            source_character=self.wren,
        )

        self.context = MagicMock()
        self.context.get_state_by_pk = MagicMock(return_value=None)
        self.captain_state = CharacterState(self.captain, context=self.context)
        self.wren_state = CharacterState(self.wren, context=self.context)
        self.tamsin_state = CharacterState(self.tamsin, context=self.context)

    def test_hidden_hold_shows_nothing_to_a_bystander(self) -> None:
        result = self.captain_state.get_display_allegiance(looker=self.tamsin_state)
        self.assertEqual(result, "")

    def test_hidden_hold_still_shows_to_its_own_source(self) -> None:
        result = self.captain_state.get_display_allegiance(looker=self.wren_state)
        self.assertIn("Secretly Turned", result)

    def test_rounds_measured_hold_reads_holds_until_settled(self) -> None:
        result = self.captain_state.get_display_allegiance(looker=self.wren_state)
        self.assertIn("holds until settled", result)


class CharacterStateAllegianceNamelessTests(TestCase):
    """A nameless charmed NPC offers ``companion promote`` instead of ``retain``."""

    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory()
        self.room = self.encounter.room
        self.opponent = CombatOpponentFactory(
            encounter=self.encounter, status=OpponentStatus.WON_OVER
        )
        self.nameless_target = self.opponent.objectdb

        self.wren = ObjectDBFactory(
            db_key="Wren Nameless",
            db_typeclass_path="typeclasses.characters.Character",
            location=self.room,
        )
        CharacterSheetFactory(character=self.wren)

        self.charm = ConditionTemplateFactory(
            name="Charmed Nameless",
            sets_allegiance=Allegiance.ALLY_OF_CASTER,
            default_duration_type=DurationType.ROUNDS,
        )
        ConditionInstanceFactory(
            target=self.nameless_target,
            condition=self.charm,
            source_character=self.wren,
        )

        self.context = MagicMock()
        self.context.get_state_by_pk = MagicMock(return_value=None)
        self.target_state = CharacterState(self.nameless_target, context=self.context)
        self.wren_state = CharacterState(self.wren, context=self.context)

    def test_nameless_charm_offers_companion_promote_not_retain(self) -> None:
        result = self.target_state.get_display_allegiance(looker=self.wren_state)
        self.assertIn("companion promote", result)
        self.assertNotIn("retain", result)

    def test_nameless_charm_offers_no_settle(self) -> None:
        # Settle is persona-backed only (ruling R2) -- a nameless body has none.
        # ("holds until settled" legitimately contains the substring "settle",
        # so check the verb line's tokens, not the whole result.)
        result = self.target_state.get_display_allegiance(looker=self.wren_state)
        verb_line = result.splitlines()[-1]
        self.assertNotIn("settle ", verb_line)

    def test_nameless_charm_still_offers_sendaway_and_cast(self) -> None:
        result = self.target_state.get_display_allegiance(looker=self.wren_state)
        self.assertIn("sendaway", result)
        self.assertIn("cast <technique> at", result)
