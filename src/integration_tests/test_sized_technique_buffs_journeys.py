"""Journeys for sized technique buffs on checks (#4594, slice c1 of #4551).

Maren casts buff techniques on Corin the way the web client does (``cast_technique``
through dispatch). Each technique authors its applied condition at a size; the cast's
power and outcome resolve the buff's level from the cast-level rows; the buffed
character's next check reads the value table through ``collect_check_modifiers``, and a
pile of buffs tapers lightly (each extra at 7/8, never below 2/3). The rows are the
example seed, so these journeys also prove the seed is coherent.

- One Large buff adds the value table's number for its level, not its flat authored value.
- Ten Large buffs add the tapered total, less than ten times one buff.
- The same buff is the same number on a lower- and a higher-level character, which is a
  bigger share of the lower one's rank band. Nothing reads the bearer's level.
- Staff saving a two-effect technique whose buff is sized Large see the size warning.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse
from evennia.objects.models import ObjectDB

from actions.factories import ActionTemplateFactory
from integration_tests.harness import JourneyCase
from world.checks.constants import ModifierLane, ModifierSize
from world.checks.factories import CheckTypeFactory, CheckTypeTraitFactory
from world.checks.modifier_models import ModifierValue
from world.checks.modifier_values import load_value_table, rank_band_share
from world.checks.services import collect_check_modifiers, perform_check_with_modifiers
from world.checks.test_helpers import force_check_outcome
from world.checks.types import CheckResult
from world.classes.factories import CharacterClassFactory, CharacterClassLevelFactory
from world.conditions.factories import ConditionCheckModifierFactory, ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.conditions.services import opponent_condition_opposition
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterAnimaFactory,
    GiftFactory,
    TechniqueAppliedConditionFactory,
    TechniqueDamageProfileFactory,
    TechniqueFactory,
)
from world.magic.models import Technique
from world.magic.models.techniques import ConditionTargetKind
from world.scenes.factories import SceneFactory
from world.scenes.tests.cast_test_helpers import grant_technique
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.modifier_values import seed_modifier_value_tables
from world.traits.factories import StatTraitFactory
from world.traits.models import CheckOutcome
from world.vitals.models import CharacterVitals

# The flat value each buff condition authors; a sized buff must NOT add this.
FLAT_AUTHORED = 5


class SizedBuffsOnChecks(JourneyCase):
    """Maren buffs Corin (level 6), Pell (level 1) and Hale (level 16)."""

    def setUp(self) -> None:
        super().setUp()
        seed_check_resolution_tables()
        seed_modifier_value_tables()
        self.room = self.make_room("The Watch Hall")
        SceneFactory(room=self.room)
        self.ward_reading = CheckTypeFactory(name="Ward Reading")
        self.stat = StatTraitFactory()
        CheckTypeTraitFactory(check_type=self.ward_reading, trait=self.stat, weight=1)
        self.template = ActionTemplateFactory(check_type=CheckTypeFactory(name="Casting"))
        self.character_class = CharacterClassFactory()

        self.buffs = [self.buff_technique(index) for index in range(10)]
        self.maren = self.player("Maren", level=6)
        self.corin = self.player("Corin", level=6)
        self.pell = self.player("Pell", level=1)
        self.hale = self.player("Hale", level=16)

    # -- setup helpers ----------------------------------------------------------

    def buff_technique(self, index: int) -> Technique:
        """A castable technique whose whole effect is one Large ally buff to Ward Reading."""
        technique = TechniqueFactory(
            name=f"Ward Sight {index + 1}",
            gift=GiftFactory(),
            intensity=20,
            anima_cost=1,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=self.template,
        )
        condition = ConditionTemplateFactory(name=f"Ward Sight {index + 1}")
        ConditionCheckModifierFactory(
            condition=condition, check_type=self.ward_reading, modifier_value=FLAT_AUTHORED
        )
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=condition,
            target_kind=ConditionTargetKind.ALLY,
            minimum_success_level=1,
            modifier_size=ModifierSize.LARGE,
        )
        return technique

    def player(self, name: str, *, level: int) -> ObjectDB:
        character = self.make_player(name, room=self.room)
        sheet = character.sheet_data
        CharacterClassLevelFactory(
            character=sheet, character_class=self.character_class, level=level, is_primary=True
        )
        for technique in self.buffs:
            grant_technique(sheet.primary_persona, technique)
        CharacterAnimaFactory(character=sheet, current=50, maximum=50)
        CharacterVitals.objects.create(
            character_sheet=sheet, health=50, max_health=50, base_max_health=50
        )
        character.traits.set_trait_value(self.stat.name, 20)
        return character

    # -- the cast and the check -------------------------------------------------

    def cast(
        self, caster: ObjectDB, target: ObjectDB, technique: Technique, *, outcome: str = "Success"
    ) -> None:
        with force_check_outcome(CheckOutcome.objects.get(name=outcome)):
            result = self.web(
                caster,
                "cast_technique",
                technique_id=technique.pk,
                target_persona_id=target.sheet_data.primary_persona.pk,
            )
        self.assertTrue(result.detail.success, result.detail.message)

    def ward_check(self, character: ObjectDB) -> CheckResult:
        return perform_check_with_modifiers(character, self.ward_reading, target_difficulty=50)

    def landed(self, character: ObjectDB) -> list[ConditionInstance]:
        return list(
            ConditionInstance.objects.filter(
                target=character, condition__name__startswith="Ward Sight"
            )
        )

    # -- journeys -----------------------------------------------------------------

    def test_one_large_buff_adds_its_value_table_number(self) -> None:
        before = self.ward_check(self.corin)

        self.cast(self.maren, self.corin, self.buffs[0])

        (instance,) = self.landed(self.corin)
        self.assertEqual(instance.modifier_size, ModifierSize.LARGE)
        expected = load_value_table().value(instance.modifier_level, ModifierSize.LARGE)
        self.assertIsNotNone(expected)
        self.assertNotEqual(expected, FLAT_AUTHORED)
        after = self.ward_check(self.corin)
        self.assertEqual(after.total_points - before.total_points, expected)

    def test_ten_large_buffs_taper(self) -> None:
        before = self.ward_check(self.corin)

        for technique in self.buffs:
            self.cast(self.maren, self.corin, technique)

        self.assertEqual(len(self.landed(self.corin)), 10)
        breakdown = collect_check_modifiers(self.corin.sheet_data, self.ward_reading)
        one = breakdown.contributions[0].value
        self.assertTrue(all(c.value == one for c in breakdown.contributions))
        # 1 + 7/8 + (7/8)^2 + (7/8)^3 + six at the 2/3 floor = 7.31 buffs' worth.
        self.assertEqual(breakdown.total, round(one * 7.3107))
        self.assertLess(breakdown.total, one * 10)
        after = self.ward_check(self.corin)
        self.assertEqual(after.total_points - before.total_points, breakdown.total)
        self.assertGreater(after.roller_rank.rank, before.roller_rank.rank)

    def test_the_same_buff_matters_more_to_a_lower_level_character(self) -> None:
        pell_before = self.ward_check(self.pell)
        hale_before = self.ward_check(self.hale)

        self.cast(self.maren, self.pell, self.buffs[0])
        self.cast(self.maren, self.hale, self.buffs[0])

        (pell_buff,) = self.landed(self.pell)
        (hale_buff,) = self.landed(self.hale)
        # The buff's level comes from Maren's cast, never from who carries it.
        self.assertEqual(pell_buff.modifier_level, hale_buff.modifier_level)
        pell_gain = self.ward_check(self.pell).total_points - pell_before.total_points
        hale_gain = self.ward_check(self.hale).total_points - hale_before.total_points
        self.assertEqual(pell_gain, hale_gain)
        self.assertGreater(
            rank_band_share(pell_gain, pell_before.total_points),
            rank_band_share(hale_gain, hale_before.total_points),
        )

    def test_without_a_value_row_the_buff_keeps_its_flat_value(self) -> None:
        ModifierValue.objects.filter(lane=ModifierLane.CHECK).delete()
        before = self.ward_check(self.corin)

        self.cast(self.maren, self.corin, self.buffs[0])

        self.assertEqual(self.ward_check(self.corin).total_points - before.total_points, 5)

    def test_totals_ranks_and_charts_through_the_check(self) -> None:
        """Own totals are the stat's 20 points plus LEVEL_POINTS_PER_LEVEL (5) per level."""
        corin = self.ward_check(self.corin)
        self.assertEqual((corin.total_points, corin.roller_rank.name), (50, "Expert"))
        self.assertEqual(corin.rank_difference, 0)

        self.cast(self.maren, self.corin, self.buffs[0])
        (instance,) = self.landed(self.corin)
        # Intensity 20 at Success sits in the seed's 16-29 power row: level 6, Large = 10.
        self.assertEqual(instance.modifier_level, 6)
        one = self.ward_check(self.corin)
        self.assertEqual((one.total_points, one.roller_rank.name), (60, "Expert"))
        self.assertEqual(one.chart.rank_difference, 0)

        for technique in self.buffs[1:]:
            self.cast(self.maren, self.corin, technique)
        ten = self.ward_check(self.corin)
        self.assertEqual((ten.total_points, ten.roller_rank.name), (123, "Grandmaster"))
        self.assertEqual(ten.chart.rank_difference, 2)

        breakdown = collect_check_modifiers(self.corin.sheet_data, self.ward_reading)
        # The recorded provenance rows add up to the tapered total.
        self.assertEqual(sum(breakdown.counted_values()), 73)
        # An opponent carrying the same pile presents the same tapered total.
        self.assertEqual(opponent_condition_opposition(self.corin, self.ward_reading), 73)

        self.assertEqual(self.ward_check(self.pell).total_points, 25)
        self.assertEqual(self.ward_check(self.hale).total_points, 100)

    def test_the_cast_outcome_shifts_the_level(self) -> None:
        self.cast(self.maren, self.corin, self.buffs[0], outcome="Critical Success")
        _set_rows(self.buffs[1], minimum_success_level=0)
        self.cast(self.maren, self.pell, self.buffs[1], outcome="Partial Success")

        (critical,) = self.landed(self.corin)
        (partial,) = self.landed(self.pell)
        # The seed's outcome rows: Critical Success +2, Partial Success -1.
        self.assertEqual(critical.modifier_level, 8)
        self.assertEqual(partial.modifier_level, 5)

    def test_an_unsized_buff_keeps_its_flat_value(self) -> None:
        _set_rows(self.buffs[0], modifier_size=None)
        before = self.ward_check(self.corin)

        self.cast(self.maren, self.corin, self.buffs[0])

        (instance,) = self.landed(self.corin)
        self.assertIsNone(instance.modifier_level)
        self.assertIsNone(instance.modifier_size)
        self.assertEqual(
            self.ward_check(self.corin).total_points - before.total_points, FLAT_AUTHORED
        )


class StaffSeeTheSizeCheck(JourneyCase):
    """Staff saving a technique in admin see the size warning (#4551 section 5.3)."""

    def setUp(self) -> None:
        super().setUp()
        staff = get_user_model().objects.create_user(
            username="tuner", password="pw", is_staff=True, is_superuser=True
        )
        self.client.force_login(staff)
        ward_reading = CheckTypeFactory(name="Ward Reading")
        self.buff = ConditionTemplateFactory(name="Ward Sight")
        ConditionCheckModifierFactory(
            condition=self.buff, check_type=ward_reading, modifier_value=5
        )

    def technique(self, *, with_damage: bool) -> Technique:
        technique = TechniqueFactory(name="Searing Ward", damage_profile=False)
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=self.buff,
            target_kind=ConditionTargetKind.ALLY,
            modifier_size=ModifierSize.LARGE,
        )
        if with_damage:
            TechniqueDamageProfileFactory(technique=technique)
        return technique

    def resave(self, technique: Technique) -> list[str]:
        """Post the technique's change page back unchanged, as staff pressing Save."""
        url = reverse("admin:arxii_technique_change", args=[technique.pk])
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        data = _filled(page.context["adminform"].form)
        for inline in page.context["inline_admin_formsets"]:
            formset = inline.formset
            data.update(_filled(formset.management_form))
            for form in formset.forms:
                data.update(_filled(form))
        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)
        errors = page.context["adminform"].form.errors
        self.assertFalse(errors, errors)
        return [str(message) for message in response.context["messages"]]

    def test_a_two_effect_technique_sized_large_warns_on_save(self) -> None:
        messages = self.resave(self.technique(with_damage=True))

        self.assertIn(
            "Ward Sight is sized Large, but Searing Ward does 1 other thing as well, so this "
            "buff shares the cast's power: at most Moderate.",
            messages,
        )

    def test_a_buff_only_technique_sized_large_saves_quietly(self) -> None:
        messages = self.resave(self.technique(with_damage=False))

        self.assertFalse([m for m in messages if "is sized" in m], messages)

    def test_narrow_use_allows_one_step_more(self) -> None:
        technique = self.technique(with_damage=True)
        _set_rows(technique, narrow_use=True)

        messages = self.resave(technique)

        self.assertFalse([m for m in messages if "is sized" in m], messages)

    def test_a_sized_condition_that_changes_no_check_warns(self) -> None:
        technique = TechniqueFactory(name="Empty Gesture", damage_profile=False)
        TechniqueAppliedConditionFactory(
            technique=technique,
            condition=ConditionTemplateFactory(name="Hollow"),
            target_kind=ConditionTargetKind.ALLY,
            modifier_size=ModifierSize.LARGE,
        )

        messages = self.resave(technique)

        self.assertIn(
            "Hollow is sized Large, but it changes no check, so its size has nothing to act "
            "on yet.",
            messages,
        )


class StaffTuneTheValueTable(JourneyCase):
    """Staff author the rows in admin and read a pile on the tuning dashboard (#4594)."""

    def setUp(self) -> None:
        super().setUp()
        seed_check_resolution_tables()
        seed_modifier_value_tables()
        staff = get_user_model().objects.create_user(
            username="tuner", password="pw", is_staff=True, is_superuser=True
        )
        self.client.force_login(staff)

    def test_every_new_table_has_an_admin_page(self) -> None:
        for name in (
            "modifiervalue",
            "modifierlevelbaseline",
            "modifiertaper",
            "castpowerlevel",
            "castoutcomelevelshift",
        ):
            response = self.client.get(reverse(f"admin:arxii_{name}_changelist"))
            self.assertEqual(response.status_code, 200, name)

    def test_staff_add_a_value_row_and_read_it_in_ranks(self) -> None:
        response = self.client.post(
            reverse("admin:arxii_modifiervalue_add"),
            {
                "lane": ModifierLane.CHECK,
                "level": "7",
                "size": str(ModifierSize.LARGE),
                "value": "15",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        row = ModifierValue.objects.get(level=7, size=ModifierSize.LARGE)
        self.assertEqual(row.value, 15)

        page = self.client.get(reverse("admin:arxii_modifiervalue_change", args=[row.pk]))

        # Level 7 reads the level-6 baseline of 58 (Expert, a 30-point band): 15 is 26% of
        # the total and half a rank.
        self.assertContains(
            page,
            "A level-7 character&#x27;s typical total is 58: this value is 26% of it; "
            "0.50 of a rank band at that total.",
        )

    def test_the_dashboard_shows_a_tapered_pile(self) -> None:
        response = self.client.get(
            reverse("admin_tuning_checks"),
            {
                "pile_character_level": "6",
                "pile_modifier_level": "6",
                "pile_size": str(ModifierSize.LARGE),
                "pile_count": "10",
            },
        )

        self.assertEqual(response.status_code, 200)
        pile = response.context["pile"]
        self.assertEqual(
            (pile.baseline, pile.modifier_value, pile.plain_total, pile.tapered_total),
            (58, 10, 100, 73),
        )
        self.assertEqual(pile.rank_before, "Expert (rank 3)")
        self.assertEqual(pile.rank_after, "Grandmaster (rank 5)")
        self.assertContains(response, "+73: Grandmaster (rank 5)")


def _set_rows(technique: Technique, **fields: object) -> None:
    """Edit a technique's applied-condition rows the way an admin save does (one save each)."""
    for row in technique.condition_applications.all():
        for name, value in fields.items():
            setattr(row, name, value)
        row.save()


def _filled(bound_fields) -> dict[str, str]:
    """What a browser posts for these bound fields untouched; unchecked boxes are left out."""
    data: dict[str, str] = {}
    for bound in bound_fields:
        value = bound.value()
        if isinstance(value, bool):
            if value:
                data[bound.html_name] = "on"
        elif isinstance(value, list | tuple):
            data[bound.html_name] = [str(item) for item in value]
        else:
            data[bound.html_name] = "" if value is None else str(value)
    return data
