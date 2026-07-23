"""Banded NPC reaction lines (#2632) — data-authored, allure-keyed."""

from __future__ import annotations

from django.test import TestCase

from world.currency.services import get_or_create_purse, transfer
from world.forms.factories import (
    CharacterFormFactory,
    CharacterFormValueFactory,
    FormTraitFactory,
    FormTraitOptionFactory,
)
from world.npc_services.constants import OfferKind, ReactionMetric
from world.npc_services.effects import run_styling_offer
from world.npc_services.factories import (
    NPCRoleFactory,
    NPCServiceOfferFactory,
    StylingOfferDetailsFactory,
)
from world.npc_services.models import NPCReactionLine
from world.npc_services.reactions import reaction_line_for
from world.scenes.factories import PersonaFactory


def _grant_allure(sheet, amount: int) -> None:
    # Bare/unknown ModifierSources contribute nothing (#909) — grant through a
    # distinction-backed source, the same shape the Attractive ranks use.
    from world.mechanics.factories import DistinctionModifierSourceFactory
    from world.mechanics.models import (
        CharacterModifier,
        ModifierCategory,
        ModifierTarget,
    )

    category, _ = ModifierCategory.objects.get_or_create(name="roll_modifier")
    target, _ = ModifierTarget.objects.get_or_create(name="allure", defaults={"category": category})
    source = DistinctionModifierSourceFactory(distinction_effect__target=target)
    CharacterModifier.objects.create(character=sheet, target=target, value=amount, source=source)


class ReactionLineSelectionTests(TestCase):
    def setUp(self) -> None:
        self.role = NPCRoleFactory(name="Stylist Role")
        self.persona = PersonaFactory()
        self.sheet = self.persona.character_sheet
        for floor, text in [
            (-999, "<name> gets a dubious look."),
            (1, "<name> draws interest."),
            (11, "<name> is truly worthy."),
            (31, "<name> is a work of art."),
        ]:
            NPCReactionLine.objects.create(
                role=self.role,
                metric=ReactionMetric.ALLURE,
                band_floor=floor,
                template=text,
            )

    def _line(self):
        return reaction_line_for(
            role=self.role,
            functionary=None,
            metric=ReactionMetric.ALLURE.value,
            sheet=self.sheet,
            name=self.persona.name,
        )

    def test_zero_allure_hits_bottom_band(self) -> None:
        self.assertEqual(self._line(), f"{self.persona.name} gets a dubious look.")

    def test_mid_band(self) -> None:
        _grant_allure(self.sheet, 12)
        self.assertEqual(self._line(), f"{self.persona.name} is truly worthy.")

    def test_top_band(self) -> None:
        _grant_allure(self.sheet, 40)
        self.assertEqual(self._line(), f"{self.persona.name} is a work of art.")

    def test_unauthored_metric_returns_none(self) -> None:
        NPCReactionLine.objects.all().delete()
        self.assertIsNone(self._line())


class StylingHandlerReactionTests(TestCase):
    def setUp(self) -> None:
        self.persona = PersonaFactory()
        self.sheet = self.persona.character_sheet
        self.trait = FormTraitFactory(name="hair_color_rx", is_cosmetic=True)
        self.black = FormTraitOptionFactory(trait=self.trait, name="raven")
        self.red = FormTraitOptionFactory(trait=self.trait, name="crimson", display_name="Crimson")
        form = CharacterFormFactory(character=self.sheet.character)
        CharacterFormValueFactory(form=form, trait=self.trait, option=self.black)
        self.role = NPCRoleFactory(name="Reaction Stylist")
        self.offer = NPCServiceOfferFactory(
            role=self.role, kind=OfferKind.STYLING, label="Crimson", is_final=True
        )
        StylingOfferDetailsFactory(
            offer=self.offer, trait=self.trait, target_option=self.red, price_coppers=10
        )
        transfer(amount=50, reason="test", to_purse=get_or_create_purse(self.sheet))

    def test_authored_reaction_leads_the_message(self) -> None:
        NPCReactionLine.objects.create(
            role=self.role,
            metric=ReactionMetric.ALLURE,
            band_floor=-999,
            template="The stylist sees to <name>, looking at them dubiously.",
        )
        result = run_styling_offer(self.offer, self.persona)
        self.assertIn(
            f"The stylist sees to {self.persona.name}, looking at them dubiously.",
            result.message,
        )
        self.assertIn("Crimson", result.message)

    def test_unauthored_falls_back_to_generic(self) -> None:
        result = run_styling_offer(self.offer, self.persona)
        self.assertIn("works their craft", result.message)
