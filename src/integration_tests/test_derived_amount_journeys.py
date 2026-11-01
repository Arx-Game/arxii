"""Journeys for a modifier that derives its amount from a level, a thread or a check rank (#4878).

The owner's shared menu (#4824): a distinction effect or a condition modifier effect picks
an input, a "per N" step and a cap; its own amount is the amount per step.

* Check rank. Corvin haggles at the River Market and holds "+1 Haggling per 2 ranks of
  Athletics, at most +3". Athletics is one stat at weight 1, so with the seeded 1:1 stat
  conversion its rating is his stored stat plus 5 per level, read against the seeded rank
  ladder (Peerless, rank 6, from 155; Mythic, rank 8, from 250; Novice, rank 1, from 10).
  Stat 100 at level 11 is 155, rank 6: +3. Stat 100 at level 30 is 250, rank 8: 4 steps,
  held at +3. Stat 10 at level 1 is 15, rank 1: no whole step, +0.
* Thread level. Hobb charges a bandit (5 damage with no modifier) and holds "+1 Charge
  damage per level of his Wolf thread". At shown level 3 the charge does 8; with no Wolf
  thread, 5.
* Character level. A condition on Hobb carries "+1 Charge to hit per 2 character levels".
  At level 11 the charge adds 10 + 5 = 15 to hit, and a stage multiplier of 2 changes
  nothing: the input replaces the condition's own scaling.
* Staff on the distinction effect admin page cannot save an input with a size, a check-rank
  input on a stat, or a thread input that names no anchor.
"""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from integration_tests.harness import JourneyCase
from integration_tests.test_charge_effect_journeys import DAMAGE, TO_HIT
from integration_tests.test_facet_effect_bonus_journeys import _WolfFangField
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.services import perform_check_with_modifiers
from world.classes.factories import CharacterClassLevelFactory
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionModifierEffectFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import ConditionModifierEffect
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.distinctions.models import DERIVED_AMOUNT_SIZE_REFUSAL, DistinctionEffect
from world.distinctions.services import grant_distinction
from world.distinctions.types import DistinctionOrigin
from world.magic.factories import FacetFactory
from world.magic.models import Thread
from world.magic.services.facets import merge_facets
from world.mechanics.constants import (
    MANEUVER_EFFECT_CATEGORY_NAME,
    AmountInput,
    ManeuverEffectKey,
)
from world.mechanics.effect_targets import effect_modifier_total
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.mechanics.maneuver_effects import get_maneuver_effect
from world.mechanics.models import ModifierCategory
from world.seeds.checks import seed_check_resolution_tables
from world.traits.factories import StatTraitFactory

ATHLETICS_CAP = 3


def _at_level(character, level: int) -> None:
    CharacterClassLevelFactory(character=character.sheet_data, level=level, is_primary=True)
    character.sheet_data.invalidate_class_level_cache()


class ACheckRankDrivesAHaggle(JourneyCase):
    """Corvin's "+1 Haggling per 2 Athletics ranks, at most +3"."""

    def setUp(self) -> None:
        super().setUp()
        seed_check_resolution_tables()
        self.room = self.make_room("The River Market")
        self.haggling = CheckTypeFactory(name="Haggling")
        self.athletics = CheckTypeFactory(name="Athletics")
        self.wits = StatTraitFactory(name="wits")
        self.strength = StatTraitFactory(name="strength")
        CheckTypeTraitFactory(check_type=self.haggling, trait=self.wits, weight=1)
        CheckTypeTraitFactory(check_type=self.athletics, trait=self.strength, weight=1)
        self.target = ModifierTargetFactory(
            name="haggling_check",
            category=ModifierCategoryFactory(name="check"),
            target_check_type=self.haggling,
        )
        distinction = DistinctionFactory(name="Dockhand's Frame", slug="dockhands-frame")
        DistinctionEffectFactory(
            distinction=distinction,
            target=self.target,
            value_per_rank=1,
            amount_input=AmountInput.CHECK_RANK,
            amount_check_type=self.athletics,
            amount_per=2,
            amount_cap=ATHLETICS_CAP,
        )
        self.distinction = distinction

    def gain(self, *, strength: int, level: int) -> int:
        corvin = self.make_player(f"Corvin{strength}x{level}", room=self.room)
        corvin.traits.set_trait_value(self.wits.name, 20)
        corvin.traits.set_trait_value(self.strength.name, strength)
        _at_level(corvin, level)
        before = perform_check_with_modifiers(corvin, self.haggling, target_difficulty=50)
        grant_distinction(corvin.sheet_data, self.distinction, origin=DistinctionOrigin.GM_AWARD)
        after = perform_check_with_modifiers(corvin, self.haggling, target_difficulty=50)
        return after.total_points - before.total_points

    def test_rank_six_gives_three(self) -> None:
        self.assertEqual(self.gain(strength=100, level=11), 3)

    def test_rank_eight_is_held_at_the_cap(self) -> None:
        self.assertEqual(self.gain(strength=100, level=30), ATHLETICS_CAP)

    def test_rank_one_is_no_whole_step(self) -> None:
        self.assertEqual(self.gain(strength=10, level=1), 0)

    def test_a_rank_row_on_the_stat_its_check_reads_does_not_loop(self) -> None:
        # Written past clean() (a fixture or a script): "+1 strength per 2 Athletics
        # ranks", where Athletics reads strength. The inner read of strength, inside the
        # Athletics rating, counts the row as 0, so the rating is 100 + 5 x 11 = 155, rank
        # 6, and the outer read adds 3: 103, not a RecursionError.
        strength_target = ModifierTargetFactory(
            name="strength",
            category=ModifierCategoryFactory(name="stat"),
            target_trait=self.strength,
        )
        looping = DistinctionFactory(name="Self-Made", slug="self-made")
        DistinctionEffectFactory(
            distinction=looping,
            target=strength_target,
            value_per_rank=1,
            amount_input=AmountInput.CHECK_RANK,
            amount_check_type=self.athletics,
            amount_per=2,
        )
        corvin = self.make_player("Corvin", room=self.room)
        corvin.traits.set_trait_value(self.strength.name, 100)
        _at_level(corvin, 11)
        grant_distinction(corvin.sheet_data, looping, origin=DistinctionOrigin.GM_AWARD)

        self.assertEqual(corvin.traits.get_trait_value(self.strength.name), 103)


class AThreadAndALevelDriveTheCharge(_WolfFangField):
    """Hobb's Charge with a thread-driven distinction and a level-driven condition."""

    def grant_wolf_damage(self) -> None:
        distinction = DistinctionFactory(name="Wolfsworn", slug="wolfsworn")
        DistinctionEffectFactory(
            distinction=distinction,
            target=self.charge_damage,
            value_per_rank=1,
            amount_input=AmountInput.THREAD_LEVEL,
            amount_thread_facet=self.wolf,
        )
        grant_distinction(self.sheet, distinction, origin=DistinctionOrigin.GM_AWARD)

    def test_a_wolf_thread_at_shown_level_three_adds_three_damage(self) -> None:
        self.grant_wolf_damage()
        self.thread_on(self.wolf, shown_level=3)

        to_hit, damage = self.charge_and_resolve()

        self.assertEqual(damage, DAMAGE + 3)
        self.assertEqual(to_hit, TO_HIT)

    def test_with_no_wolf_thread_it_adds_nothing(self) -> None:
        self.grant_wolf_damage()
        self.thread_on(self.silk, shown_level=3)

        _to_hit, damage = self.charge_and_resolve()

        self.assertEqual(damage, DAMAGE)

    def test_after_a_facet_merge_the_row_reads_the_winners_thread(self) -> None:
        # The row names "Wolves"; staff merge Wolves into Wolf, where Hobb's thread is.
        # Before the merge Wolves has no thread of his: 5. After it, the row names Wolf
        # and reads his level 3 thread: 8.
        wolves = FacetFactory(name="Wolves")
        distinction = DistinctionFactory(name="Packsworn", slug="packsworn")
        effect = DistinctionEffectFactory(
            distinction=distinction,
            target=self.charge_damage,
            value_per_rank=1,
            amount_input=AmountInput.THREAD_LEVEL,
            amount_thread_facet=wolves,
        )
        grant_distinction(self.sheet, distinction, origin=DistinctionOrigin.GM_AWARD)
        self.thread_on(self.wolf, shown_level=3)
        # Charge's own damage term reads this (``kind_wide=False``); nothing yet.
        before = effect_modifier_total(self.sheet, ManeuverEffectKey.CHARGE_DAMAGE, kind_wide=False)
        self.assertEqual(before, 0)

        merge_facets(self.wolf, [wolves])

        effect.refresh_from_db()
        self.assertEqual(effect.amount_thread_facet_id, self.wolf.pk)
        _to_hit, damage = self.charge_and_resolve()
        self.assertEqual(damage, DAMAGE + 3)

    def test_a_retired_wolf_thread_adds_nothing(self) -> None:
        self.grant_wolf_damage()
        self.thread_on(self.wolf, shown_level=3)
        thread = Thread.objects.get(owner=self.sheet)
        thread.retired_at = timezone.now()
        thread.save(update_fields=["retired_at"])
        self.hobb.threads.invalidate()

        _to_hit, damage = self.charge_and_resolve()

        self.assertEqual(damage, DAMAGE)

    def eager_condition(self, *, staged: bool) -> None:
        category = ModifierCategory.objects.get(name=MANEUVER_EFFECT_CATEGORY_NAME)
        to_hit = ModifierTargetFactory(
            category=category,
            name="Charge: to hit",
            scope_maneuver_effect=get_maneuver_effect(ManeuverEffectKey.CHARGE_TO_HIT),
        )
        condition = ConditionTemplateFactory(name="Battle-eager")
        ConditionModifierEffectFactory(
            condition=condition,
            modifier_target=to_hit,
            value=1,
            amount_input=AmountInput.CHARACTER_LEVEL,
            amount_per=2,
        )
        stage = None
        if staged:
            stage = ConditionStageFactory(
                condition=condition, severity_multiplier=Decimal(2), stage_order=1
            )
        ConditionInstanceFactory(target=self.hobb, condition=condition, current_stage=stage)

    def test_a_condition_adds_one_to_hit_per_two_levels(self) -> None:
        _at_level(self.hobb, 11)
        self.eager_condition(staged=False)

        to_hit, damage = self.charge_and_resolve()

        self.assertEqual(to_hit, TO_HIT + 5)
        self.assertEqual(damage, DAMAGE)

    def test_a_stage_multiplier_does_not_scale_a_derived_amount(self) -> None:
        _at_level(self.hobb, 11)
        self.eager_condition(staged=True)

        to_hit, _damage = self.charge_and_resolve()

        self.assertEqual(to_hit, TO_HIT + 5)


class TheMenuOnTheEffectAdminPage(_WolfFangField):
    """Staff author derived amounts on the distinction effect admin page."""

    def setUp(self) -> None:
        super().setUp()
        staff = get_user_model().objects.create_user(
            username="warden", password="pw", is_staff=True, is_superuser=True
        )
        self.client.force_login(staff)
        self.distinction = DistinctionFactory(name="Wolfsworn", slug="wolfsworn")
        self.athletics = CheckTypeFactory(name="Athletics")

    def save_effect(self, target, **menu):
        data = {
            "distinction": self.distinction.pk,
            "target": target.pk,
            "value_per_rank": "1",
            "amplifies_sources_by": "",
            "modifier_size": "",
            "description": "",
            "amount_input": "",
            "amount_per": "1",
            "amount_cap": "",
            "amount_check_type": "",
            "amount_thread_trait": "",
            "amount_thread_facet": "",
            "rank_sizes-TOTAL_FORMS": "0",
            "rank_sizes-INITIAL_FORMS": "0",
            "rank_sizes-MIN_NUM_FORMS": "0",
            "rank_sizes-MAX_NUM_FORMS": "1000",
        }
        data.update({key: str(value) for key, value in menu.items()})
        return self.client.post(reverse("admin:arxii_distinctioneffect_add"), data)

    def test_a_thread_input_on_the_wolf_facet_saves(self) -> None:
        response = self.save_effect(
            self.charge_damage,
            amount_input=AmountInput.THREAD_LEVEL,
            amount_thread_facet=self.wolf.pk,
            amount_cap=4,
        )

        self.assertEqual(response.status_code, 302, response.content)
        effect = DistinctionEffect.objects.get(distinction=self.distinction)
        self.assertEqual(
            (effect.amount_input, effect.amount_thread_facet_id, effect.amount_cap),
            (AmountInput.THREAD_LEVEL, self.wolf.pk, 4),
        )

    def test_an_input_with_a_size_is_refused(self) -> None:
        response = self.save_effect(
            self.charge_damage,
            amount_input=AmountInput.CHARACTER_LEVEL,
            modifier_size=3,
        )

        self.assertContains(response, DERIVED_AMOUNT_SIZE_REFUSAL)
        self.assertFalse(DistinctionEffect.objects.filter(distinction=self.distinction).exists())

    def test_a_check_rank_on_a_stat_is_refused(self) -> None:
        stat_target = ModifierTargetFactory(
            name="strength", category=ModifierCategoryFactory(name="stat")
        )

        response = self.save_effect(
            stat_target, amount_input=AmountInput.CHECK_RANK, amount_check_type=self.athletics.pk
        )

        self.assertContains(response, "cannot take a check rank input")
        self.assertFalse(DistinctionEffect.objects.filter(distinction=self.distinction).exists())

    def test_a_thread_input_with_no_anchor_is_refused(self) -> None:
        response = self.save_effect(self.charge_damage, amount_input=AmountInput.THREAD_LEVEL)

        self.assertContains(response, "Name one trait or one facet whose thread is read.")
        self.assertFalse(DistinctionEffect.objects.filter(distinction=self.distinction).exists())

    def test_a_condition_effect_cannot_derive_and_scale_with_severity(self) -> None:
        effect = ConditionModifierEffect(
            condition=ConditionTemplateFactory(name="Battle-eager"),
            modifier_target=self.charge_damage,
            value=1,
            scales_with_severity=True,
            amount_input=AmountInput.CHARACTER_LEVEL,
        )

        with self.assertRaises(ValidationError) as caught:
            effect.full_clean()

        self.assertIn("scales_with_severity", caught.exception.message_dict)
