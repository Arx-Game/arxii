"""Journeys for Poise and Composure modifiers on social resist (#4720).

Ysmay tries to persuade three people in the Lantern, each a major NPC a GM plays, so each
resists at the same fixed effort and her request resolves at once. They are alike in every
way but one:

- Hobb carries nothing on Composure rolls.
- Marta holds Good Breeding, a distinction that grants +7 poise. Poise is a modifier scoped
  to the Composure check, and she gained it through ``grant_distinction``, the one seam
  every distinction is granted through.
- Tam is Flustered, a condition staff gave a -10 modifier on Composure checks, applied
  through ``apply_condition``.

Each Persuade is sent to ``/api/action-requests/``, the request the browser sends, and the
difficulty the roll was graded at is read off the check itself. A target resists with what
they would bring to a Composure roll: Marta is 7 harder to persuade than Hobb, Tam 10
easier.
"""

from __future__ import annotations

from evennia.objects.models import ObjectDB
from rest_framework import status

from actions.factories import ActionTemplateFactory
from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.test_helpers import force_check_outcome
from world.conditions.factories import ConditionCheckModifierFactory, ConditionTemplateFactory
from world.conditions.services import apply_condition
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.distinctions.services import grant_distinction
from world.distinctions.types import DistinctionOrigin
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.roster.factories import RosterFactory
from world.roster.models.choices import RosterType
from world.scenes.factories import SceneFactory
from world.traits.factories import (
    CharacterTraitValueFactory,
    CheckOutcomeFactory,
    StatTraitFactory,
)
from world.traits.models import PointConversionRange, TraitType

POISE = 7
FLUSTERED = -10


def persona_of(character: ObjectDB):
    return character.sheet_data.primary_persona


class PoiseOnSocialResist(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        npcs = RosterFactory(roster_type=RosterType.NPC)
        self.hobb, self.marta, self.tam = (
            self.make_player(name, room=self.room) for name in ("Hobb", "Marta", "Tam")
        )
        for npc in (self.hobb, self.marta, self.tam):
            npc.sheet_data.roster_entry.move_to_roster(npcs)
        self.scene = SceneFactory(room=self.room)
        ActionTemplateFactory(name="Persuade", check_type=CheckTypeFactory(name="Persuasion"))
        # Composure weighs the composure stat, and all three have the same one: resist
        # never goes below zero, so the penalty needs a rating to come off.
        self.composure = CheckTypeFactory(name="Composure")
        stat = StatTraitFactory(name="composure")
        CheckTypeTraitFactory(check_type=self.composure, trait=stat)
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.STAT,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        for npc in (self.hobb, self.marta, self.tam):
            CharacterTraitValueFactory(character=npc.sheet_data, trait=stat, value=30)
        self.landed = CheckOutcomeFactory(name="PoiseJourneySuccess", success_level=1)

        poise = ModifierTargetFactory(
            name="poise",
            category=ModifierCategoryFactory(name="roll_modifier"),
            target_check_type=self.composure,
        )
        good_breeding = DistinctionFactory(name="Good Breeding", slug="good-breeding")
        DistinctionEffectFactory(distinction=good_breeding, target=poise, value_per_rank=POISE)
        grant_distinction(self.marta.sheet_data, good_breeding, origin=DistinctionOrigin.GM_AWARD)

        flustered = ConditionTemplateFactory(name="Flustered")
        ConditionCheckModifierFactory(
            condition=flustered, check_type=self.composure, modifier_value=FLUSTERED
        )
        apply_condition(self.tam, flustered)

    def persuade(self, target: ObjectDB) -> int:
        """Ysmay persuades ``target``; the difficulty her roll was graded at."""
        with force_check_outcome(self.landed) as capture:
            response = self.api(self.account_of(self.ysmay)).post(
                "/api/action-requests/",
                {
                    "scene": self.scene.pk,
                    "initiator_persona": persona_of(self.ysmay).pk,
                    "target_persona": persona_of(target).pk,
                    "action_key": "persuade",
                },
                format="json",
            )
        self.assertIn(response.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))
        self.assertEqual(response.json()["status"], "resolved")
        self.assertEqual(capture.check_type.name, "Persuasion")
        return capture.target_difficulty

    def test_poise_makes_her_harder_to_persuade_by_its_value(self) -> None:
        self.assertEqual(self.persuade(self.marta) - self.persuade(self.hobb), POISE)

    def test_a_flustered_target_is_easier_to_persuade_by_the_penalty(self) -> None:
        self.assertEqual(self.persuade(self.tam) - self.persuade(self.hobb), FLUSTERED)
