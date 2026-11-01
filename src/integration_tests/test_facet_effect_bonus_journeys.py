"""Journeys for a gear facet's bonus to a maneuver effect (#4815, slice 4 of #4783).

Hobb charges the bandit as in the charge journeys (``_ChargeField``): every check is forced to
Success, his technique does no damage of its own, and the bandit's lost health is the charge's
own damage, 5 with no modifier anywhere.

The owner ruled on 2026-11-01 that the facet itself names the effect it boosts, whatever the
thread's resonance. Staff give the Wolf facet "+2 Charge: damage" on the Facet admin page. It
counts while Hobb wears an item carrying Wolf and has a facet thread on Wolf, scaled like a
facet passive: amount x item quality x attachment quality x the thread level he sees. So at
shown level 3 on plain quality the charge deals 5 + 2 x 3 = 11; on an item of quality 2.00
with an attachment of 1.50 at shown level 1 it deals 5 + 2 x 2 x 1.5 x 1 = 11. Taking the item
off, a thread on another facet, or no thread at all leaves it at 5.
"""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse

from integration_tests.test_charge_effect_journeys import DAMAGE, _ChargeField
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    ItemFacetFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    QualityTierFactory,
)
from world.items.models import EquippedItem
from world.magic.constants import TargetKind
from world.magic.factories import FacetFactory, ResonanceFactory, ThreadFactory
from world.magic.models import FacetEffectBonus
from world.mechanics.constants import MANEUVER_EFFECT_CATEGORY_NAME, ManeuverEffectKey
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.mechanics.maneuver_effects import get_maneuver_effect
from world.mechanics.models import ModifierCategory

BONUS = 2


class _WolfFangField(_ChargeField):
    """Hobb, the bandit, a Wolf and a Silk facet, and a Charge damage target."""

    def setUp(self) -> None:
        super().setUp()
        self.wolf = FacetFactory(name="Wolf")
        self.silk = FacetFactory(name="Silk")
        self.charge_damage = ModifierTargetFactory(
            category=ModifierCategory.objects.get(name=MANEUVER_EFFECT_CATEGORY_NAME),
            name="Charge: damage",
            scope_maneuver_effect=get_maneuver_effect(ManeuverEffectKey.CHARGE_DAMAGE),
        )

    def wear(
        self,
        facet,
        *,
        item_quality="1.00",
        attachment_quality="1.00",
        layer=EquipmentLayer.OUTER,
    ) -> EquippedItem:
        """Hobb puts on a garment carrying ``facet``."""
        cloak = ItemInstanceFactory(
            template=ItemTemplateFactory(facet_capacity=1),
            quality_tier=QualityTierFactory(stat_multiplier=Decimal(item_quality)),
        )
        ItemFacetFactory(
            item_instance=cloak,
            facet=facet,
            attachment_quality_tier=QualityTierFactory(stat_multiplier=Decimal(attachment_quality)),
        )
        worn = EquippedItem.objects.create(
            character=self.sheet,
            item_instance=cloak,
            body_region=BodyRegion.TORSO,
            equipment_layer=layer,
        )
        self.hobb.equipped_items.invalidate()
        return worn

    def thread_on(self, facet, *, shown_level: int) -> None:
        """Hobb weaves a facet thread on ``facet`` (stored levels are x10)."""
        ThreadFactory(
            owner=self.sheet,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.FACET,
            target_facet=facet,
            target_trait=None,
            level=shown_level * 10,
        )
        self.hobb.threads.invalidate()


class AFacetBoostsTheChargeItNames(_WolfFangField):
    def setUp(self) -> None:
        super().setUp()
        FacetEffectBonus.objects.create(facet=self.wolf, target=self.charge_damage, amount=BONUS)

    def test_a_worn_threaded_wolf_fang_adds_its_bonus_per_shown_level(self) -> None:
        self.wear(self.wolf)
        self.thread_on(self.wolf, shown_level=3)

        _to_hit, damage = self.charge_and_resolve()

        self.assertEqual(damage, DAMAGE + BONUS * 3)

    def test_item_and_attachment_quality_scale_the_bonus(self) -> None:
        self.wear(self.wolf, item_quality="2.00", attachment_quality="1.50")
        self.thread_on(self.wolf, shown_level=1)

        _to_hit, damage = self.charge_and_resolve()

        self.assertEqual(damage, DAMAGE + 6)  # 2 x 2.00 x 1.50 x 1

    def test_taking_the_item_off_ends_the_bonus(self) -> None:
        worn = self.wear(self.wolf)
        self.thread_on(self.wolf, shown_level=3)
        worn.delete()
        self.hobb.equipped_items.invalidate()

        _to_hit, damage = self.charge_and_resolve()

        self.assertEqual(damage, DAMAGE)

    def test_a_thread_on_another_facet_gives_nothing(self) -> None:
        # He wears Wolf, but his thread is on Silk, and Silk boosts nothing.
        self.wear(self.wolf)
        self.wear(self.silk, layer=EquipmentLayer.BASE)
        self.thread_on(self.silk, shown_level=3)

        _to_hit, damage = self.charge_and_resolve()

        self.assertEqual(damage, DAMAGE)

    def test_a_worn_wolf_fang_with_no_thread_gives_nothing(self) -> None:
        self.wear(self.wolf)

        _to_hit, damage = self.charge_and_resolve()

        self.assertEqual(damage, DAMAGE)


class StaffAuthorTheBonusOnTheFacetPage(_WolfFangField):
    def setUp(self) -> None:
        super().setUp()
        staff = get_user_model().objects.create_user(
            username="warden", password="pw", is_staff=True, is_superuser=True
        )
        self.client.force_login(staff)

    def post_wolf(self, target_pk: int, amount: str):
        return self.client.post(
            reverse("admin:arxii_facet_change", args=[self.wolf.pk]),
            {
                "name": "Wolf",
                "description": "",
                "aliases-TOTAL_FORMS": "0",
                "aliases-INITIAL_FORMS": "0",
                "effect_bonuses-TOTAL_FORMS": "1",
                "effect_bonuses-INITIAL_FORMS": "0",
                "effect_bonuses-0-target": str(target_pk),
                "effect_bonuses-0-amount": amount,
            },
        )

    def test_a_bonus_saved_on_the_facet_page_reaches_the_charge(self) -> None:
        response = self.post_wolf(self.charge_damage.pk, str(BONUS))
        self.assertEqual(response.status_code, 302, response.content)
        saved = FacetEffectBonus.objects.get(facet=self.wolf)
        self.assertEqual((saved.target_id, saved.amount), (self.charge_damage.pk, BONUS))

        self.wear(self.wolf)
        self.thread_on(self.wolf, shown_level=2)
        _to_hit, damage = self.charge_and_resolve()

        self.assertEqual(damage, DAMAGE + BONUS * 2)

    def test_the_facet_page_refuses_a_target_that_is_not_a_maneuver_effect(self) -> None:
        strength = ModifierTargetFactory(
            category=ModifierCategoryFactory(name="stat"), name="strength"
        )

        response = self.post_wolf(strength.pk, str(BONUS))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select a valid choice")
        self.assertFalse(FacetEffectBonus.objects.exists())

    def test_the_facet_page_refuses_a_bonus_of_nothing(self) -> None:
        response = self.post_wolf(self.charge_damage.pk, "0")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A bonus of 0 adds nothing.")
        self.assertFalse(FacetEffectBonus.objects.exists())
