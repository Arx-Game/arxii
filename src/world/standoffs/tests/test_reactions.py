"""Reaction lines (banding, precedence, substitution) and the critical terms upgrade."""

from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from actions.constants import ActionBackend
from actions.types import ActionRef
from world.combat.constants import CauseKind
from world.combat.factories import CombatOpponentFactory, CreatureTemplateFactory
from world.conditions.models import ConditionInstance
from world.standoffs.constants import StandoffGroupState, TermsEffect
from world.standoffs.factories import (
    StandoffApproachFactory,
    StandoffReactionLineFactory,
    StandoffTermsFactory,
)
from world.standoffs.models import StandoffGroup
from world.standoffs.services.reactions import best_reaction_line, reaction_text
from world.standoffs.services.verbs import standoff_terms
from world.standoffs.tests.test_dispatch_e2e import StandoffJourneyBase
from world.standoffs.tests.test_verbs import CHECK, VerbBase, forced
from world.traits.factories import CheckOutcomeFactory

ANNOUNCE = "world.combat.interaction_services.broadcast_action_outcome"


class BandingTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.approach = StandoffApproachFactory()
        cls.creature = CreatureTemplateFactory()
        cls.other = CreatureTemplateFactory()

    def _line(self, floor: int, text: str, creature=None):
        return StandoffReactionLineFactory(
            approach=self.approach,
            min_success_level=floor,
            text=text,
            creature_template=creature,
        )

    def test_highest_floor_at_or_below_the_roll_wins(self) -> None:
        self._line(-2, "low")
        self._line(1, "mid")
        self._line(2, "top")
        for level, text in ((-2, "low"), (0, "low"), (1, "mid"), (2, "top")):
            line = best_reaction_line(self.approach, self.creature.pk, level)
            self.assertEqual(line.text, text, level)

    def test_creature_specific_beats_generic_at_the_same_floor(self) -> None:
        self._line(1, "generic")
        self._line(1, "specific", self.creature)
        self.assertEqual(best_reaction_line(self.approach, self.creature.pk, 1).text, "specific")
        self.assertEqual(best_reaction_line(self.approach, self.other.pk, 1).text, "generic")

    def test_a_higher_generic_floor_beats_a_lower_specific_one(self) -> None:
        self._line(1, "specific", self.creature)
        self._line(2, "generic top")
        self.assertEqual(best_reaction_line(self.approach, self.creature.pk, 2).text, "generic top")

    def test_no_line_is_none(self) -> None:
        self._line(2, "only crit")
        self.assertIsNone(best_reaction_line(self.approach, self.creature.pk, 1))
        self.assertIsNone(
            reaction_text(
                self.approach,
                creature_template_id=self.creature.pk,
                group_name="g",
                actor_name="a",
                success_level=1,
            )
        )

    def test_placeholders_are_filled(self) -> None:
        self._line(1, "<actor> stares down the <group>.")
        text = reaction_text(
            self.approach,
            creature_template_id=self.creature.pk,
            group_name="Wolves",
            actor_name="Masked",
            success_level=1,
        )
        self.assertEqual(text, "Masked stares down the Wolves.")

    def test_a_name_holding_a_placeholder_is_not_substituted_again(self) -> None:
        self._line(1, "<actor> faces <group>.")
        text = reaction_text(
            self.approach,
            creature_template_id=self.creature.pk,
            group_name="Wolves",
            actor_name="<group> Jr",
            success_level=1,
        )
        self.assertEqual(text, "<group> Jr faces Wolves.")

    def test_a_line_needs_exactly_one_parent(self) -> None:
        from django.db import IntegrityError, transaction

        terms = StandoffTermsFactory()
        with self.assertRaises(IntegrityError), transaction.atomic():
            StandoffReactionLineFactory(approach=self.approach, terms=terms)
        with self.assertRaises(IntegrityError), transaction.atomic():
            StandoffReactionLineFactory(approach=None, terms=None)


class CriticalEffectTests(VerbBase):
    def setUp(self) -> None:
        super().setUp()
        # A second open group keeps the standoff from completing (and clearing) on settle.
        other = CreatureTemplateFactory(cause=CauseKind.NONE)
        CombatOpponentFactory(encounter=self.encounter, creature_template=other)
        StandoffGroup.objects.create(encounter=self.encounter, creature_template=other)

    def test_clean_rejects_a_critical_effect_equal_to_the_effect(self) -> None:
        terms = StandoffTermsFactory(effect=TermsEffect.PASS, critical_effect=TermsEffect.PASS)
        with self.assertRaises(ValidationError):
            terms.clean()
        terms.critical_effect = TermsEffect.TURN
        terms.clean()

    def test_a_critical_applies_the_critical_effect_instead(self) -> None:
        terms = StandoffTermsFactory(effect=TermsEffect.PASS, critical_effect=TermsEffect.TURN)
        with patch(CHECK, return_value=forced(2)):
            result = standoff_terms(self.participant, self.group, terms)
        self.assertTrue(result.settled)
        self.group.refresh_from_db()
        self.assertEqual(self.group.settled_outcome.success_level, 2)
        for member in self.members:
            self.assertTrue(
                ConditionInstance.objects.filter(
                    target=member.objectdb, condition=self.config.turn_condition
                ).exists()
            )
            self.assertFalse(
                ConditionInstance.objects.filter(
                    target=member.objectdb, condition=self.config.pass_condition
                ).exists()
            )

    def test_a_plain_success_uses_the_usual_effect(self) -> None:
        terms = StandoffTermsFactory(effect=TermsEffect.PASS, critical_effect=TermsEffect.TURN)
        with patch(CHECK, return_value=forced(1)):
            standoff_terms(self.participant, self.group, terms)
        for member in self.members:
            self.assertTrue(
                ConditionInstance.objects.filter(
                    target=member.objectdb, condition=self.config.pass_condition
                ).exists()
            )
            self.assertFalse(
                ConditionInstance.objects.filter(
                    target=member.objectdb, condition=self.config.turn_condition
                ).exists()
            )

    def test_a_critical_with_no_upgrade_does_the_usual_effect(self) -> None:
        terms = StandoffTermsFactory(effect=TermsEffect.PASS)
        with patch(CHECK, return_value=forced(2)):
            standoff_terms(self.participant, self.group, terms)
        self.assertTrue(
            ConditionInstance.objects.filter(condition=self.config.pass_condition).exists()
        )


def _ref(key: str) -> ActionRef:
    return ActionRef(backend=ActionBackend.REGISTRY, registry_key=key)


class RoomLineTests(StandoffJourneyBase):
    def setUp(self) -> None:
        super().setUp()
        self.creature.cause = CauseKind.NONE
        self.creature.save(update_fields=["cause"])
        self._open()
        self.who = self.character.sheet_data.primary_persona.name

    def _lines(self, broadcast) -> list[str]:
        return [call.kwargs["narration"] for call in broadcast.call_args_list]

    def test_an_authored_line_replaces_the_plain_press_line(self) -> None:
        StandoffReactionLineFactory(
            approach=self.approach, min_success_level=1, text="<actor> awes the <group>."
        )
        with (
            patch(ANNOUNCE) as broadcast,
            patch(
                CHECK,
                return_value=SimpleNamespace(
                    success_level=1, outcome=self.success_tier, chart=None
                ),
            ),
        ):
            self._do("standoff_press", group_id=self.group.pk, approach_id=self.approach.pk)
        self.assertEqual(self._lines(broadcast), [f"{self.who} awes the {self.creature.name}."])

    def test_a_critical_gets_the_bigger_line_through_a_real_check(self) -> None:
        crit = CheckOutcomeFactory(name="Journey crit", success_level=2)
        StandoffReactionLineFactory(approach=self.approach, min_success_level=1, text="ok <actor>")
        StandoffReactionLineFactory(approach=self.approach, min_success_level=2, text="WOW <actor>")
        from world.checks.test_helpers import force_check_outcome

        with patch(ANNOUNCE) as broadcast, force_check_outcome(crit):
            self._do("standoff_press", group_id=self.group.pk, approach_id=self.approach.pk)
        self.assertEqual(self._lines(broadcast), [f"WOW {self.who}"])

    def test_terms_line_replaces_the_plain_terms_line_and_never_uses_the_key(self) -> None:
        from world.scenes.constants import PersonaType
        from world.scenes.factories import PersonaFactory
        from world.scenes.services import set_active_persona

        sheet = self.character.sheet_data
        alt = PersonaFactory(
            character_sheet=sheet, name="Masked Stranger", persona_type=PersonaType.ESTABLISHED
        )
        set_active_persona(sheet, alt)
        self.who = "Masked Stranger"
        StandoffReactionLineFactory(
            approach=None, terms=self.terms, min_success_level=0, text="<actor> bargains."
        )
        from world.checks.test_helpers import force_check_outcome

        with patch(ANNOUNCE) as broadcast, force_check_outcome(self.success_tier):
            self._do("standoff_terms", group_id=self.group.pk, terms_id=self.terms.pk)
        lines = self._lines(broadcast)
        self.assertIn(f"{self.who} bargains.", lines)
        self.assertEqual(len([line for line in lines if "bargains" in line]), 1)
        self.assertFalse([line for line in lines if " names " in line])
        self.assertNotEqual(self.who, self.character.key)

    def test_the_press_line_comes_before_the_morale_shift_line(self) -> None:
        from world.combat.models import CombatOpponent

        self.approach.damages_morale = True
        self.approach.save(update_fields=["damages_morale"])
        StandoffReactionLineFactory(approach=self.approach, min_success_level=1, text="PRESS")
        crit = CheckOutcomeFactory(name="Journey crit morale", success_level=2)
        for member in CombatOpponent.objects.filter(encounter=self.encounter):
            member.morale = 55
            member.save(update_fields=["morale"])
        from world.checks.test_helpers import force_check_outcome

        with patch(ANNOUNCE) as broadcast, force_check_outcome(crit):
            self._do("standoff_press", group_id=self.group.pk, approach_id=self.approach.pk)
        lines = self._lines(broadcast)
        self.assertEqual(lines[0], "PRESS")
        self.assertIn(" shakes the ", lines[1])
        self.assertEqual(len(lines), 2)

    def test_the_attack_line_comes_after_the_press_and_morale_lines(self) -> None:
        from world.checks.test_helpers import force_check_outcome
        from world.combat.models import CombatOpponent

        self.creature.cause = CauseKind.PREDATION
        self.creature.cause_margin_percent = 100000
        self.creature.save(update_fields=["cause", "cause_margin_percent"])
        self.approach.damages_morale = True
        self.approach.save(update_fields=["damages_morale"])
        for member in CombatOpponent.objects.filter(encounter=self.encounter):
            member.morale = 55
            member.save(update_fields=["morale"])
        crit = CheckOutcomeFactory(name="Journey crit attack", success_level=2)
        with (
            patch(ANNOUNCE) as broadcast,
            self.captureOnCommitCallbacks(execute=True),
            force_check_outcome(crit),
        ):
            self._do("standoff_press", group_id=self.group.pk, approach_id=self.approach.pk)
        lines = self._lines(broadcast)
        self.assertEqual(len(lines), 3, lines)
        self.assertIn(" presses ", lines[0])
        self.assertIn(" shakes ", lines[1])
        self.assertTrue(lines[2].endswith(" attack!"), lines[2])

    def test_no_line_authored_keeps_the_plain_line(self) -> None:
        with (
            patch(ANNOUNCE) as broadcast,
            patch(
                CHECK,
                return_value=SimpleNamespace(
                    success_level=1, outcome=self.success_tier, chart=None
                ),
            ),
        ):
            self._do("standoff_press", group_id=self.group.pk, approach_id=self.approach.pk)
        self.assertEqual(
            self._lines(broadcast),
            [f"{self.who} presses the {self.creature.name} with {self.approach.name}: success."],
        )

    def test_a_refusal_announces_nothing_even_with_a_line(self) -> None:
        StandoffReactionLineFactory(approach=self.approach, min_success_level=-2, text="x")
        self.group.state = StandoffGroupState.SETTLED
        self.group.save(update_fields=["state"])
        with patch(ANNOUNCE) as broadcast:
            self._do("standoff_press", group_id=self.group.pk, approach_id=self.approach.pk)
        broadcast.assert_not_called()


class CriticalLabelTests(VerbBase):
    def test_terms_rows_carry_the_critical_upgrade_label(self) -> None:
        from world.standoffs.services.view import build_standoff_view

        StandoffTermsFactory(effect=TermsEffect.PASS, critical_effect=TermsEffect.TURN)
        StandoffTermsFactory(effect=TermsEffect.PASS)
        view = build_standoff_view(self.encounter, self.participant.character_sheet)
        labels = sorted(terms.critical_label for terms in view.terms)
        self.assertEqual(labels, ["", "Turn"])
