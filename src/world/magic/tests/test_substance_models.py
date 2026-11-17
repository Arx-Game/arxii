"""Schema rules of the Substance and Primum models (#5125): the constraints the database holds."""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from world.items.factories import ItemTemplateFactory
from world.locations.constants import StatKey
from world.magic.constants import GiftKind, SubstanceDirection, SubstanceRelationKind
from world.magic.factories import (
    GiftFactory,
    PlacePrimumFactory,
    PrimumCallUpFactory,
    SubstanceFactory,
    SubstanceRelationFactory,
)
from world.magic.models import SubstanceRelation
from world.scenes.factories import SceneFactory


class SubstanceRelationTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.fire = SubstanceFactory(name="Fire")
        cls.ice = SubstanceFactory(name="Ice")

    def test_relation_pair_saved_in_pk_order(self) -> None:
        low, high = sorted([self.fire, self.ice], key=lambda s: s.pk)
        relation = SubstanceRelationFactory(
            substance_a=high, substance_b=low, kind=SubstanceRelationKind.OPPOSED
        )
        relation.refresh_from_db()
        self.assertEqual((relation.substance_a_id, relation.substance_b_id), (low.pk, high.pk))

    def test_relation_to_self_refused(self) -> None:
        relation = SubstanceRelation(
            substance_a=self.fire, substance_b=self.fire, kind=SubstanceRelationKind.RELATED
        )
        with self.assertRaises(ValidationError):
            relation.full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            relation.save()

    def test_relation_unique_per_pair(self) -> None:
        SubstanceRelationFactory(
            substance_a=self.fire, substance_b=self.ice, kind=SubstanceRelationKind.OPPOSED
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            # The reversed pair is the same pair once saved in pk order.
            SubstanceRelationFactory(
                substance_a=self.ice, substance_b=self.fire, kind=SubstanceRelationKind.RELATED
            )


class SubstanceTests(TestCase):
    def test_substance_condition_and_direction_both_or_neither(self) -> None:
        SubstanceFactory()
        SubstanceFactory(stat_key=StatKey.LIGHTING, direction=SubstanceDirection.FALLING)
        for stat_key, direction in [
            (StatKey.LIGHTING, ""),
            ("", SubstanceDirection.RISING),
        ]:
            with (
                self.subTest(stat_key=stat_key, direction=direction),
                self.assertRaises(IntegrityError),
                transaction.atomic(),
            ):
                SubstanceFactory(stat_key=stat_key, direction=direction)

    def test_minor_gift_cannot_hold_substance(self) -> None:
        substance = SubstanceFactory()
        major = GiftFactory(kind=GiftKind.MAJOR, substance=substance)
        self.assertEqual(major.substance_id, substance.pk)
        minor = GiftFactory(kind=GiftKind.MINOR)
        minor.substance = substance
        with self.assertRaises(ValidationError) as raised:
            minor.full_clean()
        self.assertIn("substance", raised.exception.message_dict)
        with self.assertRaises(IntegrityError), transaction.atomic():
            minor.save()


class PlacePrimumTests(TestCase):
    def test_place_primum_current_amount(self) -> None:
        stamped = timezone.now()
        place = PlacePrimumFactory(
            capacity=10, stored_amount=2, refill_per_day=3, stamped_at=stamped
        )
        self.assertEqual(place.current_amount(stamped + timedelta(days=1, hours=23)), 5)
        self.assertEqual(place.current_amount(stamped + timedelta(days=30)), 10)
        self.assertEqual(place.current_amount(stamped - timedelta(days=2)), 2)
        finite = PlacePrimumFactory(
            capacity=10, stored_amount=2, refill_per_day=3, stamped_at=stamped, is_finite=True
        )
        self.assertEqual(finite.current_amount(stamped + timedelta(days=30)), 2)

    def test_place_primum_stored_amount_cannot_exceed_capacity(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            PlacePrimumFactory(capacity=5, stored_amount=6)


class PrimumCallUpTests(TestCase):
    def test_call_up_needs_exactly_one_owner(self) -> None:
        scene = SceneFactory()
        PrimumCallUpFactory(scene=None)
        PrimumCallUpFactory(caster=None, scene=scene)
        for owned_by_caster, owned_by_scene in [(False, False), (True, True)]:
            with (
                self.subTest(caster=owned_by_caster, scene=owned_by_scene),
                self.assertRaises(IntegrityError),
                transaction.atomic(),
            ):
                kwargs = {}
                if not owned_by_caster:
                    kwargs["caster"] = None
                if owned_by_scene:
                    kwargs["scene"] = scene
                PrimumCallUpFactory(**kwargs)


class PrimumTemplateTests(TestCase):
    def test_primum_template_unique_per_substance(self) -> None:
        substance = SubstanceFactory()
        ItemTemplateFactory(primum_substance=substance)
        ItemTemplateFactory()
        ItemTemplateFactory()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ItemTemplateFactory(primum_substance=substance)
