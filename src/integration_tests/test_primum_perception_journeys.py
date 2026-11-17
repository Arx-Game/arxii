"""Journeys for sensing Primum through a Magesight check (#5125).

Mira works an ice gift. Her Magesight technique rolls a check whose pool carries two
consequences: a plain Success lets her sense the strongest substance in the place, a Critical
Success every substance. The hall holds Some fire (10 Primum), Massive stone (100) and Trace
steam is not there; fire works against ice and stone is unrelated. Tomas stands in the hall
without a Magesight check. Names are invented.
"""

from __future__ import annotations

from django.urls import reverse
from rest_framework import status

from actions.factories import (
    ConsequencePoolEntryFactory,
    ConsequencePoolFactory,
)
from integration_tests.harness import JourneyCase
from world.checks.constants import EffectType, PrimumRevealScope
from world.checks.factories import ConsequenceEffectFactory, ConsequenceFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import OpponentStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CreatureTemplateFactory,
)
from world.locations.constants import StatKey
from world.magic.constants import SubstanceDirection, SubstanceRelationKind, TargetKind
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterGiftFactory,
    CharacterResonanceFactory,
    CreaturePrimumFactory,
    GiftFactory,
    PlacePrimumFactory,
    ResonanceFactory,
    SubstanceFactory,
    SubstanceRelationFactory,
    ThreadFactory,
    ensure_canonical_affinities,
    seed_primum_tuning,
)
from world.magic.models import Affinity, PrimumSighting
from world.magic.services.primum_perception import perceived_substance_ids
from world.magic.tests._cache_isolation import ResonanceCacheIsolationMixin
from world.scenes.factories import SceneFactory
from world.scenes.tests.cast_test_helpers import grant_technique, make_benign_castable_technique
from world.traits.factories import CheckOutcomeFactory, CheckSystemSetupFactory
from world.vitals.models import CharacterVitals

UNPERCEIVED = "Something here works against your ice"


class _Magesight(ResonanceCacheIsolationMixin, JourneyCase):
    """Mira, an ice caster with a Magesight technique, in a hall holding fire and stone."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        Affinity.objects.clear_cache()
        _celestial, primal, _abyssal = ensure_canonical_affinities()
        seed_primum_tuning()

        self.room = self.make_room("The Long Hall")
        self.profile = self.room.room_profile
        self.mira = self.make_player("Mira", room=self.room)
        self.tomas = self.make_player("Tomas", room=self.room)
        self.sheet = self.mira.sheet_data
        CharacterAnimaFactory(character=self.sheet, current=40, maximum=40)
        CharacterVitals.objects.create(
            character_sheet=self.sheet, health=50, max_health=50, base_max_health=50
        )
        self.scene = SceneFactory(room=self.room)

        self.ice = SubstanceFactory(
            name="ice", stat_key=StatKey.COLD, direction=SubstanceDirection.RISING
        )
        self.fire = SubstanceFactory(
            name="fire", stat_key=StatKey.HEAT, direction=SubstanceDirection.RISING
        )
        self.stone = SubstanceFactory(name="stone")
        SubstanceRelationFactory(
            substance_a=self.ice, substance_b=self.fire, kind=SubstanceRelationKind.OPPOSED
        )
        self.stock(self.fire, 10)
        self.stock(self.stone, 100)

        rime = ResonanceFactory(name="Rime", affinity=primal)
        self.gift = GiftFactory(name="Rimecraft", substance=self.ice)
        self.gift.resonances.add(rime)
        CharacterGiftFactory(character=self.sheet, gift=self.gift)
        ThreadFactory(
            owner=self.sheet,
            target_kind=TargetKind.GIFT,
            target_trait=None,
            target_gift=self.gift,
            resonance=rime,
            level=100,
        )
        CharacterResonanceFactory(
            character_sheet=self.sheet, resonance=rime, balance=10, lifetime_earned=10
        )
        self.frost = self.give_technique("Frost", gift=self.gift)
        self.magesight = self.give_technique("Magesight", pool=self.magesight_pool())
        self.mira.threads.invalidate()
        self.watch(self.mira, self.tomas)

    # -- the place and the technique ------------------------------------------------

    def stock(self, substance, amount: int) -> None:
        PlacePrimumFactory(
            room_profile=self.profile,
            substance=substance,
            capacity=max(amount, 1),
            stored_amount=amount,
        )

    @staticmethod
    def magesight_pool():
        """Success senses the strongest substance; Critical Success senses them all."""
        pool = ConsequencePoolFactory(name="Magesight")
        for tier, label, scope in (
            (CheckOutcomeFactory(name="Success", success_level=1), "Sense one", "strongest"),
            (CheckOutcomeFactory(name="Critical Success", success_level=2), "Sense all", "all"),
        ):
            consequence = ConsequenceFactory(outcome_tier=tier, label=label)
            ConsequenceEffectFactory(
                consequence=consequence,
                effect_type=EffectType.REVEAL_PRIMUM,
                primum_reveal=PrimumRevealScope(scope),
            )
            ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
        return pool

    def give_technique(self, name: str, *, gift=None, pool=None):
        technique = make_benign_castable_technique()
        technique.name = name
        technique.anima_cost = 1
        if gift is not None:
            technique.gift = gift
        technique.save()
        if pool is not None:
            template = technique.action_template
            template.consequence_pool = pool
            template.save(update_fields=["consequence_pool"])
        grant_technique(self.sheet.primary_persona, technique)
        return technique

    # -- seams ------------------------------------------------------------------------

    def cast_magesight(self, outcome_name: str) -> dict:
        """Mira casts Magesight through the scene's web cast endpoint, the check forced."""
        outcome = CheckOutcomeFactory(name=outcome_name)
        with force_check_outcome(outcome):
            response = self.api(self.account_of(self.mira)).post(
                reverse("sceneactionrequest-cast"),
                {
                    "scene": self.scene.pk,
                    "initiator_persona": self.sheet.primary_persona.pk,
                    "technique_id": self.magesight.pk,
                },
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        return response.json()["result"]

    def frost_card_texts(self) -> list[str]:
        """What the scene panel's Frost card says about the hall's surroundings."""
        response = self.api(self.account_of(self.mira)).get(
            reverse("sceneactionrequest-castable-techniques"),
            {"initiator_persona": self.sheet.primary_persona.pk},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        (row,) = [r for r in response.json() if r["id"] == self.frost.pk]
        return [line["text"] for line in row["cast_preview"]["surroundings"]]

    def look_as_mira(self) -> str:
        """What Mira is told when she looks at the hall over telnet."""
        return self.telnet(self.mira, "look").rstrip()

    def sensed(self, sheet=None) -> set[str]:
        sheet = sheet or self.sheet
        return {
            s.substance.name
            for s in PrimumSighting.objects.filter(character_sheet=sheet).select_related(
                "substance"
            )
        }


class SensingPrimumThroughACheck(_Magesight):
    def test_plain_success_names_the_strongest_substance_only(self) -> None:
        self.cast_magesight("Success")

        self.assertTrue(
            self.look_as_mira().endswith("You sense stone Primum: Massive."), self.look_as_mira()
        )
        self.assertNotIn("fire", self.look_as_mira())

    def test_good_success_names_them_all_strongest_first(self) -> None:
        self.cast_magesight("Critical Success")

        told = self.look_as_mira()
        self.assertTrue(
            told.endswith("You sense stone Primum: Massive. You sense fire Primum: Some."), told
        )

    def test_a_creature_the_party_fights_is_sensed_with_the_place(self) -> None:
        wyrm = CreatureTemplateFactory(name="Cinder wyrm")
        CombatOpponentFactory(
            encounter=CombatEncounterFactory(room=self.room),
            creature_template=wyrm,
            status=OpponentStatus.ACTIVE,
        )
        embers = SubstanceFactory(name="embers")
        CreaturePrimumFactory(creature_template=wyrm, substance=embers, amount=500)

        self.cast_magesight("Success")

        self.assertEqual(self.sensed(), {"embers"})


class WhatSheSensesLastsWhileSheStays(_Magesight):
    def test_the_sighting_lasts_until_she_leaves_and_clears_on_move_logout(self) -> None:
        self.assertIn(UNPERCEIVED, self.frost_card_texts())

        self.cast_magesight("Critical Success")

        self.assertTrue(
            any(t.endswith("Some fire, opposed to ice") for t in self.frost_card_texts()),
            self.frost_card_texts(),
        )
        self.assertNotIn(UNPERCEIVED, self.frost_card_texts())

        self.mira.move_to(self.make_room("The Yard"), quiet=True)
        self.mira.move_to(self.room, quiet=True)
        self.assertIn(UNPERCEIVED, self.frost_card_texts())
        self.assertNotIn("Primum", self.look_as_mira())

        self.cast_magesight("Critical Success")
        self.assertIn("You sense fire Primum: Some.", self.look_as_mira())
        self.mira.at_post_unpuppet()
        self.assertNotIn("Primum", self.look_as_mira())

    def test_her_own_gifts_substance_is_always_perceived_without_a_cast(self) -> None:
        self.assertIn(self.ice.pk, perceived_substance_ids(self.mira, self.room))
        self.assertNotIn(self.fire.pk, perceived_substance_ids(self.mira, self.room))

    def test_an_unperceived_hostile_substance_reads_something_here_works_against_your_ice(
        self,
    ) -> None:
        texts = self.frost_card_texts()

        self.assertIn(UNPERCEIVED, texts)
        self.assertFalse(any("fire" in text.lower() for text in texts))

    def test_a_foreign_character_does_not_inherit_her_sighting(self) -> None:
        self.cast_magesight("Critical Success")

        self.assertEqual(self.sensed(self.tomas.sheet_data), set())
        self.assertNotIn(self.fire.pk, perceived_substance_ids(self.tomas, self.room))
        self.assertIn(self.fire.pk, perceived_substance_ids(self.mira, self.room))
