"""Journeys: the Rite of Re-swearing changes a chosen vow pick (#4940, slice 7 of #4844).

Ysmay holds the Quicksilver vow at vow level 20 and has chosen Strike from the Flank and
Quick Recovery, 2 points each, which fills level 10's budget of 4. Between fights she
performs the rite on the web and through ``vow reswear`` to give up Quick Recovery for
Feint and Vanish (also 2 points). The rite takes ``VowFocusPickConfig.respec_ap_cost``
action points (3 by default) plus its own anima and components. In a fight, short of
action points, across levels, or over the level's budget after the swap, it is refused
and nothing is spent. The numbers come from the rules the covenants doc states: a
pick's price is ``max(1, value x frequency / 10 - reductions)``, and a level's chosen
picks may cost no more than the budget.
"""

from __future__ import annotations

from django.utils import timezone
from evennia.objects.models import ObjectDB

from integration_tests.harness import JourneyCase
from web.admin.tuning.required_content import (
    _probe_reswear_ritual,
    _probe_reswear_ritual_web_payable,
    _probe_single_reswear_ritual,
)
from world.action_points.models import ActionPointPool
from world.combat.constants import ParticipantStatus
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.covenants.constants import CovenantType, FocusPickLimitKind
from world.covenants.factories import (
    CharacterVowFocusPickFactory,
    CovenantFactory,
    CovenantRoleFactory,
    VowFocusPickFactory,
    VowFocusPickLimitFactory,
    engage_vow_with_thread,
)
from world.covenants.focus_picks import chosen_pick_ids_by_holder
from world.covenants.models import CharacterVowFocusPick, VowFocusPick, VowFocusPickConfig
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemInstance
from world.items.services.materialize import materialize_item_game_object
from world.magic.exceptions import HedgeInaccessibleError
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterAuraFactory,
    ReswearRiteFactory,
    ThreadRetuneRiteFactory,
)
from world.magic.models import CharacterAnima, RitualComponentRequirement
from world.scenes.constants import RoundStatus

PERFORM_URL = "/api/magic/rituals/perform/"
OPTIONS_URL = "/api/covenants/character-roles/reswear-options/"
RITE = "Rite of Re-swearing"
NO_RITE = "No ritual can change a chosen vow pick yet."


class _ReswearCase(JourneyCase):
    """Ysmay, level 10 full with Strike from the Flank and Quick Recovery, 10 AP left."""

    def setUp(self) -> None:
        super().setUp()
        self.rite = ReswearRiteFactory()
        self.room = self.make_room("The Fencing Hall")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.sheet = self.ysmay.sheet_data
        CharacterAuraFactory(character=self.sheet)
        self.covenant = CovenantFactory(name="The Quicksilver Hall")
        self.vow = CovenantRoleFactory(name="Quicksilver", covenant_type=CovenantType.DURANCE)
        self.membership = engage_vow_with_thread(
            self.sheet, self.vow, covenant=self.covenant, thread_level=20
        )
        # Level 10: prices 2, 2, 2 and 4. The Target limit met 5 times in 10 halves 4 to 2.
        self.flank = self.pick("Strike from the Flank", level=10, value=4)
        VowFocusPickLimitFactory(
            pick=self.flank, kind=FocusPickLimitKind.TARGET, frequency_tenths=5
        )
        self.recovery = self.pick("Quick Recovery", level=10, value=2)
        self.feint = self.pick("Feint and Vanish", level=10, value=2)
        self.light = self.pick("Light on Your Feet", level=10, value=4)
        self.bleeding = self.pick("Bleeding Cut", level=20, value=3)
        for pick in (self.flank, self.recovery):
            CharacterVowFocusPickFactory(character_role=self.membership, pick=pick)
        self.pool = ActionPointPool.get_or_create_for_character(self.ysmay)
        self.pool.current = 10
        self.pool.maximum = 10
        self.pool.save()

    def pick(self, name: str, *, level: int, value: int) -> VowFocusPick:
        return VowFocusPickFactory(covenant_role=self.vow, name=name, pick_level=level, value=value)

    def chosen_names(self) -> set[str]:
        return set(
            CharacterVowFocusPick.objects.filter(character_role=self.membership).values_list(
                "pick__name", flat=True
            )
        )

    def ap(self) -> int:
        return ActionPointPool.objects.filter(pk=self.pool.pk).values_list("current", flat=True)[0]

    def perform(self, old: VowFocusPick, new: VowFocusPick, components: list[int] | None = None):
        return self.api(self.account_of(self.ysmay)).post(
            PERFORM_URL,
            {
                "character_sheet_id": self.sheet.pk,
                "ritual_id": self.rite.pk,
                "kwargs": {
                    "old_pick_id": old.pk,
                    "new_pick_id": new.pk,
                    "covenant_id": self.covenant.pk,
                },
                "components": components or [],
            },
            format="json",
        )

    def options(self, character=None):
        character = character or self.ysmay
        return self.api(self.account_of(character)).get(
            OPTIONS_URL, {"character_sheet": character.sheet_data.pk}
        )

    def assert_refused(self, response, message: str) -> None:
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json(), {"detail": message})
        self.assertEqual(self.chosen_names(), {"Strike from the Flank", "Quick Recovery"})
        self.assertEqual(self.ap(), 10)


class ReswearingBetweenFights(_ReswearCase):
    def test_the_web_rite_swaps_the_pick_and_spends_a_weeks_action_points(self) -> None:
        response = self.perform(self.recovery, self.feint)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.json()["message"],
            f"You perform {RITE}. You give up Quick Recovery and take Feint and Vanish. "
            "Level 10: 4 of 4. 3 AP spent.",
        )
        self.assertEqual(self.chosen_names(), {"Strike from the Flank", "Feint and Vanish"})
        self.assertEqual(self.ap(), 7)
        # What every fight reads to fire a pick's rows (the combat payload readers).
        chosen = chosen_pick_ids_by_holder([self.sheet.pk])[self.sheet.pk]
        self.assertIn(self.feint.pk, chosen)
        self.assertNotIn(self.recovery.pk, chosen)

    def test_telnet_vow_reswear_makes_the_same_swap(self) -> None:
        told = self.telnet(self.ysmay, "vow reswear quick recovery=Feint and Vanish")

        self.assertIn(
            f"You perform {RITE}. You give up Quick Recovery and take Feint and Vanish. "
            "Level 10: 4 of 4. 3 AP spent.",
            told,
        )
        self.assertEqual(self.chosen_names(), {"Strike from the Flank", "Feint and Vanish"})
        self.assertEqual(self.ap(), 7)

    def test_the_cost_is_the_one_staff_set(self) -> None:
        VowFocusPickConfig.objects.update_or_create(pk=1, defaults={"respec_ap_cost": 5})

        self.telnet(
            self.ysmay, f"ritual {RITE} old_pick_id={self.recovery.pk} new_pick_id={self.feint.pk}"
        )

        self.assertEqual(self.chosen_names(), {"Strike from the Flank", "Feint and Vanish"})
        self.assertEqual(self.ap(), 5)

    def test_the_rites_anima_and_component_are_paid_from_the_dialogs_options(self) -> None:
        token = ItemTemplateFactory(name="Token of the Vow")
        RitualComponentRequirement.objects.create(ritual=self.rite, item_template=token)
        self.rite.anima_requirement = 4
        self.rite.save(update_fields=["anima_requirement"])
        CharacterAnimaFactory(character=self.sheet, current=10, maximum=10)
        item = ItemInstanceFactory(template=token, holder_character_sheet=self.sheet)
        materialize_item_game_object(item, self.sheet)
        item_pk, object_pk = item.pk, item.game_object_id

        options = self.options()
        self.assertEqual(options.status_code, 200, options.content)
        self.assertEqual(
            options.json(),
            {
                "ritual_id": self.rite.pk,
                "ap_cost": 3,
                "anima_cost": 4,
                "components": ["Token of the Vow"],
                "component_ids": [item.pk],
                "unavailable_reason": "",
            },
        )
        response = self.perform(self.recovery, self.feint, options.json()["component_ids"])

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.chosen_names(), {"Strike from the Flank", "Feint and Vanish"})
        self.assertEqual(CharacterAnima.objects.get(character=self.sheet).current, 6)
        # A token with no history is deleted outright, its game object with it.
        self.assertFalse(ItemInstance.objects.filter(pk=item_pk).exists())
        self.assertFalse(ObjectDB.objects.filter(pk=object_pk).exists())
        self.assertNotIn(item_pk, [carried.pk for carried in self.ysmay.carried_items.all()])


class ReswearingRefused(_ReswearCase):
    def test_in_a_fight_nothing_is_spent(self) -> None:
        token = ItemTemplateFactory(name="Token of the Vow")
        RitualComponentRequirement.objects.create(ritual=self.rite, item_template=token)
        self.rite.anima_requirement = 4
        self.rite.save(update_fields=["anima_requirement"])
        CharacterAnimaFactory(character=self.sheet, current=10, maximum=10)
        item = ItemInstanceFactory(template=token, holder_character_sheet=self.sheet)
        materialize_item_game_object(item, self.sheet)
        encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.room
        )
        CombatParticipantFactory(
            encounter=encounter, character_sheet=self.sheet, status=ParticipantStatus.ACTIVE
        )

        self.assert_refused(
            self.perform(self.recovery, self.feint, [item.pk]),
            "You cannot re-swear a vow pick during a fight.",
        )
        told = self.telnet(self.ysmay, "vow reswear Quick Recovery=Feint and Vanish")
        self.assertIn("You cannot re-swear a vow pick during a fight.", told)
        self.assertEqual(CharacterAnima.objects.get(character=self.sheet).current, 10)
        self.assertEqual(ItemInstance.objects.get(pk=item.pk).quantity, item.quantity)
        self.assertIsNone(ItemInstance.objects.get(pk=item.pk).destroyed_at)

    def test_short_of_action_points_nothing_is_spent(self) -> None:
        self.pool.current = 2
        self.pool.save(update_fields=["current"])

        response = self.perform(self.recovery, self.feint)

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(
            response.json(), {"detail": "The rite takes 3 action points, and you have 2."}
        )
        self.assertEqual(self.chosen_names(), {"Strike from the Flank", "Quick Recovery"})
        self.assertEqual(self.ap(), 2)

    def test_a_pick_of_another_level(self) -> None:
        self.assert_refused(
            self.perform(self.recovery, self.bleeding),
            "Bleeding Cut is a level 20 pick and Quick Recovery is level 10; a pick changes "
            "only for one of the same level.",
        )

    def test_a_swap_over_the_levels_budget(self) -> None:
        self.assert_refused(
            self.perform(self.recovery, self.light),
            "Light on Your Feet costs 4; giving up Quick Recovery leaves 2 of the 4 points "
            "for level 10 picks.",
        )

    def test_a_pick_she_has_not_chosen_or_already_holds(self) -> None:
        self.assert_refused(self.perform(self.feint, self.light), "You have not chosen that pick.")
        self.assert_refused(
            self.perform(self.recovery, self.flank),
            "You have already chosen Strike from the Flank.",
        )

    def test_another_vows_pick(self) -> None:
        other = VowFocusPickFactory(covenant_role=CovenantRoleFactory(), pick_level=10, value=2)

        self.assert_refused(self.perform(self.recovery, other), "Your vow offers no such pick.")

    def test_a_vow_she_has_left(self) -> None:
        self.membership.left_at = timezone.now()
        self.membership.save(update_fields=["left_at"])

        self.assert_refused(self.perform(self.recovery, self.feint), "You no longer hold this vow.")

    def test_telnet_names_a_pick_she_has_not_chosen(self) -> None:
        told = self.telnet(self.ysmay, "vow reswear Light on Your Feet=Feint and Vanish")

        self.assertIn("You have not chosen a pick named Light on Your Feet.", told)
        told = self.telnet(self.ysmay, "vow reswear Quick Recovery")
        self.assertIn("Usage: vow reswear <chosen pick>=<new pick> [in <covenant>]", told)


class TheDialogsOptions(_ReswearCase):
    def test_another_account_cannot_read_them(self) -> None:
        hobb = self.make_player("Hobb", room=self.room)
        response = self.api(self.account_of(hobb)).get(
            OPTIONS_URL, {"character_sheet": self.sheet.pk}
        )

        self.assertEqual(response.status_code, 404)

    def test_no_rite_authored_says_so(self) -> None:
        self.rite.delete()

        options = self.options().json()

        self.assertIsNone(options["ritual_id"])
        self.assertEqual(
            options["unavailable_reason"], "No ritual can change a chosen vow pick yet."
        )
        told = self.telnet(self.ysmay, "vow reswear Quick Recovery=Feint and Vanish")
        self.assertIn(NO_RITE, told)


class ANonMagicalHolder(_ReswearCase):
    def test_a_rite_she_cannot_perform_is_not_offered(self) -> None:
        hobb = self.make_player("Hobb", room=self.room)  # no aura: no magical profile
        engage_vow_with_thread(hobb.sheet_data, self.vow, covenant=self.covenant, thread_level=10)

        options = self.options(hobb).json()

        self.assertIsNone(options["ritual_id"])
        self.assertEqual(options["unavailable_reason"], HedgeInaccessibleError.user_message)


class RequiredContentForTheRite(JourneyCase):
    def test_a_missing_rite_is_listed(self) -> None:
        result = _probe_reswear_ritual()
        self.assertFalse(result.present)
        self.assertEqual(result.missing, ("the Rite of Re-swearing",))

        ReswearRiteFactory()
        self.assertTrue(_probe_reswear_ritual().present)

    def test_a_second_rite_is_listed_by_name(self) -> None:
        ReswearRiteFactory()
        self.assertTrue(_probe_single_reswear_ritual().present)

        ReswearRiteFactory(name="Second Re-swearing")
        result = _probe_single_reswear_ritual()
        self.assertFalse(result.present)
        self.assertEqual(result.missing, ("Second Re-swearing",))

    def test_a_target_resonance_offering_cannot_be_paid(self) -> None:
        rite = ReswearRiteFactory()
        RitualComponentRequirement.objects.create(
            ritual=rite, item_template=ItemTemplateFactory(name="Token of the Vow")
        )
        self.assertTrue(_probe_reswear_ritual_web_payable().present)

        RitualComponentRequirement.objects.create(
            ritual=rite, matches_target_resonance=True, quantity=1
        )
        result = _probe_reswear_ritual_web_payable()
        self.assertFalse(result.present)
        self.assertEqual(result.missing, (RITE,))

    def test_the_retune_rite_is_not_counted(self) -> None:
        ThreadRetuneRiteFactory()

        self.assertFalse(_probe_reswear_ritual().present)
