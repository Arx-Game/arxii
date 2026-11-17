"""Journeys for extracting Primum from a lair or a slain creature (#5125).

Mira and Tomas stand in the Ash Cavern, a lair that holds fire Primum. Mira works no fire gift
and has sensed the fire (a sighting), as has Tomas; a test gives Mira the fire gift when it
needs her thread. The tuning is the starter Primum steps (``seed_primum_tuning``: Trace from 1
Primum, Some from 10, Rich from 30, Massive from 100) and a harvest check that a forced
Success settles: a Success takes 5 Primum and gives 2 Primum items; the config's thread bonus
is 5, times 2 at the test's thread (level 200, rung 20). Names are invented.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

from integration_tests.harness import JourneyCase
from world.checks import services as check_services
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import OpponentStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CreatureTemplateFactory,
)
from world.combat.models import CombatOpponent
from world.items.factories import ItemTemplateFactory, QualityTierFactory
from world.items.models import ItemInstance
from world.locations.constants import StatKey
from world.locations.services import set_room_stat_modifier
from world.magic.constants import SubstanceDirection, TargetKind
from world.magic.factories import (
    CharacterGiftFactory,
    CreaturePrimumFactory,
    GiftFactory,
    HarvestOutcomeFactory,
    PlacePrimumFactory,
    PrimumCallUpFactory,
    PrimumSightingFactory,
    ResonanceFactory,
    SubstanceFactory,
    ThreadFactory,
    ensure_canonical_affinities,
    seed_primum_tuning,
)
from world.magic.models import Affinity, PlacePrimum
from world.magic.services.resonance_environment import get_resonance_environment_config
from world.magic.tests._cache_isolation import ResonanceCacheIsolationMixin
from world.missions.constants import DeedRewardKind, DeedRewardSink
from world.missions.factories import MissionDeedRecordFactory, MissionDeedRewardLineFactory
from world.missions.services import apply_deed_rewards
from world.skills.factories import MagicSkillFactory
from world.traits.factories import CheckOutcomeFactory, CheckSystemSetupFactory

NOTHING_LEFT = "There is nothing left to extract."
EXTRACTED = "You draw out 2 Fire Primum"


class _Lair(ResonanceCacheIsolationMixin, JourneyCase):
    """The Ash Cavern: a lair of fire Primum, Mira and Tomas, and a tuned harvest."""

    def setUp(self) -> None:
        super().setUp()
        CheckSystemSetupFactory.create()
        Affinity.objects.clear_cache()
        ensure_canonical_affinities()
        seed_primum_tuning()

        self.room = self.make_room("The Ash Cavern")
        self.profile = self.room.room_profile
        self.mira = self.make_player("Mira", room=self.room)
        self.tomas = self.make_player("Tomas", room=self.room)
        self.fire = SubstanceFactory(
            name="fire", stat_key=StatKey.HEAT, direction=SubstanceDirection.RISING
        )
        for who in (self.mira, self.tomas):
            PrimumSightingFactory(
                character_sheet=who.sheet_data, room_profile=self.profile, substance=self.fire
            )

        self.success = CheckOutcomeFactory(name="Success", success_level=1)
        self.primum = ItemTemplateFactory(
            name="Fire Primum", primum_substance=self.fire, is_stackable=True, max_stack_size=20
        )
        self.quality = QualityTierFactory(name="Fine")
        self.success_row = HarvestOutcomeFactory(
            outcome_tier=self.success, amount_taken=5, quantity=2, quality_tier=self.quality
        )
        self.tune()
        self.watch(self.mira, self.tomas)

    def tune(self) -> None:
        """Staff set up harvesting: a check type and a magic skill."""
        config = get_resonance_environment_config()
        config.harvest_check_type = CheckTypeFactory(
            name="Harvest Primum", category=CheckCategoryFactory(name="Magic")
        )
        config.harvest_skill = MagicSkillFactory(name="Primum harvesting")
        config.save(update_fields=["harvest_check_type", "harvest_skill"])

    def stock(self, amount: int, *, capacity: int | None = None, **fields) -> PlacePrimum:
        return PlacePrimumFactory(
            room_profile=self.profile,
            substance=self.fire,
            capacity=capacity if capacity is not None else max(amount, 1),
            stored_amount=amount,
            **fields,
        )

    def slain_elemental(self, carries: int = 100):
        """A slain elemental in the cavern, a kind that carries ``carries`` fire Primum."""
        template = CreatureTemplateFactory(name="Cinder elemental")
        CreaturePrimumFactory(creature_template=template, substance=self.fire, amount=carries)
        return CombatOpponentFactory(
            encounter=CombatEncounterFactory(room=self.room),
            creature_template=template,
            name="elemental",
            status=OpponentStatus.DEFEATED,
        )

    @staticmethod
    def stored(lair: PlacePrimum) -> int:
        """The lair's stored Primum as the database holds it, not the cached instance."""
        return PlacePrimum.objects.filter(pk=lair.pk).values_list("stored_amount", flat=True).get()

    @staticmethod
    def held(lair: PlacePrimum) -> int:
        """The Primum the lair holds now, from the database row."""
        values = (
            PlacePrimum.objects.filter(pk=lair.pk)
            .values("stored_amount", "stamped_at", "refill_per_day", "capacity", "is_finite")
            .get()
        )
        return PlacePrimum.amount_at(**values)

    @staticmethod
    def harvested_at(foe):
        return (
            CombatOpponent.objects.filter(pk=foe.pk)
            .values_list("primum_harvested_at", flat=True)
            .get()
        )

    def hand_of(self, who) -> int:
        """The Primum items ``who`` carries."""
        return sum(
            item.quantity
            for item in ItemInstance.objects.filter(
                template=self.primum, holder_character_sheet=who.sheet_data
            )
        )

    def extract(self, who, line: str, outcome=None) -> str:
        with force_check_outcome(outcome or self.success):
            return self.telnet(who, line)


class ExtractingFromALair(_Lair):
    def test_extract_in_a_lair_over_telnet_and_web_mint_primum_and_deplete_the_place(
        self,
    ) -> None:
        lair = self.stock(20)

        self.assertIn("You can extract fire Primum (Some) here.", self.telnet(self.mira, "extract"))
        told = self.extract(self.mira, "extract fire")
        with force_check_outcome(self.success):
            result = self.web(self.tomas, "harvest_primum", substance="fire")

        self.assertIn(EXTRACTED, told)
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertIn(EXTRACTED, result.detail.message)
        self.assertEqual(result.detail.data["remaining_line"], "Fire Primum here is now Some.")
        self.assertEqual((self.hand_of(self.mira), self.hand_of(self.tomas)), (2, 2))
        self.assertEqual(self.stored(lair), 10)
        item = ItemInstance.objects.get(
            template=self.primum, holder_character_sheet=self.mira.sheet_data
        )
        self.assertEqual(item.quality_tier, self.quality)
        self.assertEqual(item.game_object.location, self.mira)

    def test_two_extracts_in_a_row_on_a_place_are_capped_by_what_it_holds(self) -> None:
        lair = self.stock(7)

        self.extract(self.mira, "extract fire")  # takes 5, 2 items
        self.extract(self.mira, "extract fire")  # holds 2: takes 2, 1 item
        third = self.extract(self.mira, "extract fire")

        self.assertEqual(self.hand_of(self.mira), 3)
        self.assertEqual(self.stored(lair), 0)
        self.assertIn(NOTHING_LEFT, third)

    def test_finite_place_goes_dead_and_is_no_longer_offered(self) -> None:
        self.stock(5, is_finite=True, refill_per_day=3)

        self.extract(self.mira, "extract fire")
        listing = self.telnet(self.mira, "extract")
        again = self.extract(self.tomas, "extract fire")

        self.assertEqual(self.hand_of(self.mira), 2)
        self.assertIn("nothing here for you to extract", listing)
        self.assertIn(NOTHING_LEFT, again)
        self.assertEqual(self.hand_of(self.tomas), 0)

    def test_slow_refill_gives_stock_back_over_days(self) -> None:
        lair = self.stock(10, refill_per_day=2)
        self.extract(self.mira, "extract fire")  # 10 -> 5, stamped now
        self.assertEqual(self.held(lair), 5)

        drained = PlacePrimum.objects.get(pk=lair.pk)
        drained.stamped_at = timezone.now() - timedelta(days=2)
        drained.save(update_fields=["stamped_at"])
        self.assertEqual(self.held(lair), 9)
        self.extract(self.mira, "extract fire")

        self.assertEqual(self.stored(lair), 4)
        self.assertEqual(self.hand_of(self.mira), 4)


class ExtractingFromASlainCreature(_Lair):
    def test_extract_from_a_slain_creature_works_once_for_one_person(self) -> None:
        foe = self.slain_elemental()

        self.assertIn(
            "You can extract fire Primum (Massive) from elemental.",
            self.telnet(self.mira, "extract"),
        )
        first = self.extract(self.mira, "extract fire from elemental")
        second = self.extract(self.tomas, "extract fire from elemental")

        self.assertIn(EXTRACTED, first)
        self.assertIn(NOTHING_LEFT, second)
        self.assertEqual((self.hand_of(self.mira), self.hand_of(self.tomas)), (2, 0))
        self.assertIsNotNone(self.harvested_at(foe))

    def test_a_creature_gives_up_no_more_than_it_carries(self) -> None:
        self.slain_elemental(carries=3)

        self.extract(self.mira, "extract fire from elemental")

        self.assertEqual(self.hand_of(self.mira), 1)


class WhatIsOffered(_Lair):
    def test_no_offer_where_nothing_is_perceived_and_none_from_an_ordinary_forge(self) -> None:
        self.stock(20)
        stranger = self.make_player("Odo", room=self.room)
        forge = self.make_room("The Forge")
        set_room_stat_modifier(forge.room_profile, StatKey.HEAT, source="builder", value=5)
        PrimumCallUpFactory(
            room_profile=forge.room_profile, substance=self.fire, caster=self.mira.sheet_data
        )
        self.mira.move_to(forge, quiet=True)
        PrimumSightingFactory(
            character_sheet=self.mira.sheet_data,
            room_profile=forge.room_profile,
            substance=self.fire,
        )

        unperceived = self.extract(stranger, "extract fire")
        in_forge = self.extract(self.mira, "extract fire")

        self.assertIn(NOTHING_LEFT, unperceived)
        self.assertIn(NOTHING_LEFT, in_forge)
        self.assertEqual(
            self.telnet(self.mira, "extract"), "There is nothing here for you to extract."
        )
        self.assertEqual(self.hand_of(stranger), 0)
        self.assertEqual(self.hand_of(self.mira), 0)

    def test_an_unperceived_substance_asked_for_by_pk_is_refused_without_naming_it(self) -> None:
        ice = SubstanceFactory(name="ice")
        PlacePrimumFactory(room_profile=self.profile, substance=ice, capacity=20, stored_amount=20)

        result = self.web(self.mira, "harvest_primum", substance=ice.pk)

        self.assertFalse(result.detail.success)
        self.assertEqual(result.detail.message, NOTHING_LEFT)
        self.assertNotIn("ice", str(result.detail.data).lower())


class TheRoll(_Lair):
    def test_a_thread_in_the_matching_gift_adds_the_bonus_to_the_roll(self) -> None:
        self.stock(40)
        rime = ResonanceFactory(name="Ember", affinity=Affinity.objects.get(name="Primal"))
        gift = GiftFactory(name="Pyrecraft", substance=self.fire)
        gift.resonances.add(rime)
        CharacterGiftFactory(character=self.mira.sheet_data, gift=gift)
        ThreadFactory(
            owner=self.mira.sheet_data,
            target_kind=TargetKind.GIFT,
            target_trait=None,
            target_gift=gift,
            resonance=rime,
            level=200,
        )
        self.mira.threads.invalidate()
        rolls = []
        real = check_services.collect_check_modifiers

        def spy(*args, **kwargs):
            breakdown = real(*args, **kwargs)
            rolls.append(breakdown)
            return breakdown

        with patch.object(check_services, "collect_check_modifiers", spy):
            self.extract(self.tomas, "extract fire")
            self.extract(self.mira, "extract fire")

        def thread_lines(breakdown) -> list[int]:
            return [c.value for c in breakdown.contributions if "thread" in c.source_label]

        self.assertEqual([thread_lines(roll) for roll in rolls], [[], [10]])


class WhenTheTuningIsIncomplete(_Lair):
    def test_unset_tuning_answers_plainly_and_changes_nothing(self) -> None:
        lair = self.stock(20)
        config = get_resonance_environment_config()
        config.harvest_check_type = None
        config.save(update_fields=["harvest_check_type"])

        unset_check = self.extract(self.mira, "extract fire")
        self.tune()
        self.primum.primum_substance = None
        self.primum.save(update_fields=["primum_substance"])
        no_item = self.extract(self.mira, "extract fire")

        self.assertIn("Primum cannot be extracted yet.", unset_check)
        self.assertIn("Primum cannot be extracted yet.", no_item)
        self.assertEqual(self.stored(lair), 20)
        self.assertEqual(ItemInstance.objects.filter(template=self.primum).count(), 0)

    def test_a_roll_with_no_outcome_row_takes_nothing_and_can_be_tried_again(self) -> None:
        foe = self.slain_elemental()
        miss = CheckOutcomeFactory(name="Failure", success_level=-1)

        failed = self.extract(self.mira, "extract fire from elemental", outcome=miss)
        retried = self.extract(self.mira, "extract fire from elemental")

        self.assertIn("You draw out no Primum.", failed)
        self.assertIn(EXTRACTED, retried)
        self.assertIsNotNone(self.harvested_at(foe))


class APrimumItemFromAMission(_Lair):
    def test_mission_reward_mints_a_usable_primum_item(self) -> None:
        deed = MissionDeedRecordFactory(actor=self.mira.sheet_data)
        MissionDeedRewardLineFactory(
            deed=deed,
            recipient=self.mira.sheet_data,
            kind=DeedRewardKind.IMMEDIATE,
            sink=DeedRewardSink.ITEM,
            item_template=self.primum,
        )

        apply_deed_rewards(deed)

        item = ItemInstance.objects.get(template=self.primum)
        self.assertEqual(item.holder_character_sheet, self.mira.sheet_data)
        self.assertEqual(item.template.primum_substance, self.fire)
        self.assertIsNone(item.quality_tier)
