"""Journeys for giving things up by meaning, never by price (#4500, slice 1 of #4462).

Ysmay worships Ombrin and stands at its shrine. A gilt hand mirror she bought months ago
and a knitted scarf her rival Tamar gave her are both held a long time; only the scarf
means something to her, so only the scarf earns anything. Offerings in a ceremony count by
the same reading. Every step goes through the real commands (`give`, `sacrifice`,
`ceremony/offering`) and reads back the favor, the pool, the signals and the soft-destroyed
row.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.ceremonies.constants import CeremonyTypeKey
from world.ceremonies.factories import CeremonyTypeFactory
from world.ceremonies.models import CeremonyOffering
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.items.constants import MeaningSignalKind
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory, meaningful_item_for
from world.items.models import ItemInstance
from world.relationships.factories import CharacterRelationshipFactory, RelationshipTierFactory
from world.traits.factories import CheckOutcomeFactory
from world.worship.constants import FavorAwardKind
from world.worship.factories import (
    FavorOutcomeAwardFactory,
    ShrineDetailsFactory,
    WorshippedBeingFactory,
)
from world.worship.invocation_services import get_devotion_config
from world.worship.models import DevotionStanding, WorshipDeclaration


class GivingThingsUpByMeaning(JourneyCase):
    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Shrine of Ombrin")
        profile = RoomProfileFactory(objectdb=self.room)
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.tamar = self.make_player("Tamar", room=self.room)
        self.watch(self.ysmay, self.tamar)
        self.sheet = self.ysmay.sheet_data

        self.ombrin = WorshippedBeingFactory(name="Ombrin", resonance_pool=100)
        ShrineDetailsFactory(feature_instance__room_profile=profile, being=self.ombrin)
        WorshipDeclaration.objects.create(character_sheet=self.sheet, public_being=self.ombrin)

        self.success = CheckOutcomeFactory(name="Success", success_level=1)
        config = get_devotion_config()
        config.invocation_check_type = CheckTypeFactory()
        config.save(update_fields=["invocation_check_type"])
        FavorOutcomeAwardFactory(
            config=config, kind=FavorAwardKind.SACRIFICE, outcome_tier=self.success, amount=4
        )
        for number in (1, 2, 3):
            RelationshipTierFactory(tier_number=number, depth_threshold=number * 100)
        # Ysmay's side of the tie with her rival is claimed to tier 3.
        CharacterRelationshipFactory(
            source=self.sheet, target=self.tamar.sheet_data, scene_depth=350, tier=3
        )

    def _carry(self, holder, name: str, *, value: int):
        template = ItemTemplateFactory(name=name, value=value)
        obj = ObjectDBFactory(db_key=name, db_typeclass_path="typeclasses.objects.Object")
        obj.db_location = holder
        obj.save(update_fields=["db_location"])
        return ItemInstanceFactory(
            template=template, game_object=obj, holder_character_sheet=holder.sheet_data
        )

    def _favor(self) -> int:
        standing = DevotionStanding.objects.filter(
            character_sheet=self.sheet, being=self.ombrin
        ).first()
        return standing.favor if standing is not None else 0

    def test_a_bought_mirror_earns_nothing_however_much_it_cost(self) -> None:
        mirror = self._carry(self.ysmay, "gilt hand mirror", value=400)
        mirror.held_since = timezone.now() - timedelta(days=200)
        mirror.save(update_fields=["held_since"])

        with force_check_outcome(self.success) as capture:
            self.telnet(self.ysmay, "sacrifice gilt hand mirror")

        self.assertTold(self.ysmay, "No meaning points: given up, no roll, no favor")
        self.assertIsNone(capture.check_type)
        self.assertEqual(self._favor(), 0)
        self.ombrin.refresh_from_db()
        self.assertEqual(self.ombrin.resonance_pool, 100)
        self.assertIsNotNone(ItemInstance.objects.get(pk=mirror.pk).destroyed_at)
        offering = CeremonyOffering.objects.get()
        self.assertFalse(offering.counted)
        self.assertEqual(offering.signals.count(), 0)

    def test_a_scarf_given_by_a_rival_rolls_eased_and_pays_favor(self) -> None:
        scarf = self._carry(self.tamar, "knitted scarf", value=3)
        self.telnet(self.tamar, "give knitted scarf to Ysmay")
        scarf.refresh_from_db()
        self.assertEqual(scarf.holder_character_sheet, self.sheet)
        self.assertEqual(scarf.holding_event.event_type, "given")
        scarf.held_since = timezone.now() - timedelta(days=120)
        scarf.save(update_fields=["held_since"])

        with force_check_outcome(self.success) as capture:
            self.telnet(self.ysmay, "sacrifice knitted scarf")

        self.assertTold(self.ysmay, "carried 2 (held 120 days), gift 4")
        self.assertIsNotNone(capture.check_type)
        # Six meaning points ease the difficulty by sixty, down toward the Trivial floor.
        self.assertLessEqual(capture.target_difficulty, 25)
        self.assertEqual(self._favor(), 4)
        self.ombrin.refresh_from_db()
        self.assertEqual(self.ombrin.resonance_pool, 100 + 6 * 5)
        offering = CeremonyOffering.objects.get()
        self.assertEqual(offering.outcome_tier, self.success)
        self.assertEqual(
            {s.kind: s.points for s in offering.signals.all()},
            {MeaningSignalKind.CARRIED: 2, MeaningSignalKind.GIFT: 4},
        )
        gone = ItemInstance.objects.get(pk=scarf.pk)
        self.assertIsNotNone(gone.destroyed_at)
        self.assertIsNone(gone.holder_character_sheet)

    def test_a_ceremony_offering_counts_by_the_same_reading(self) -> None:
        CeremonyTypeFactory(key=CeremonyTypeKey.BLESSING, name="Blessing")
        made = meaningful_item_for(self.sheet, template__name="reed whistle", template__value=1)
        made_obj = ObjectDBFactory(
            db_key="reed whistle", db_typeclass_path="typeclasses.objects.Object"
        )
        made_obj.db_location = self.ysmay
        made_obj.save(update_fields=["db_location"])
        made.game_object = made_obj
        made.save(update_fields=["game_object"])
        self._carry(self.ysmay, "gilt hand mirror", value=400)

        self.telnet(self.ysmay, "ceremony/blessing")
        self.telnet(self.ysmay, "ceremony/offering reed whistle, gilt hand mirror")

        offerings = {
            o.item_name: o for o in CeremonyOffering.objects.filter(ceremony__isnull=False)
        }
        self.assertTrue(offerings["reed whistle"].counted)
        self.assertFalse(offerings["gilt hand mirror"].counted)
        self.ombrin.refresh_from_db()
        # Two points (own work, carried) at 5 pool each; the mirror feeds nothing.
        self.assertEqual(self.ombrin.resonance_pool, 100 + 2 * 5)
        self.assertEqual(self._favor(), 2 * 5)
