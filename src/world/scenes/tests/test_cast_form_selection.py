"""The web's half of choosing a technique's form (#2901).

Telnet has offered ``variant=<resonance>`` since #1619 and ``base`` since #1581,
but the web cast request carried only ``use_base_form`` — so a multi-resonance
caster could reach the base form or the default form from a browser and nothing
else, and no surface told them the other forms existed at all.

Two contracts here: the cast list ships the caster's reachable forms, and the
cast request accepts the one they picked.
"""

from __future__ import annotations

from typing import ClassVar

from django.test import TestCase

from actions.factories import ActionTemplateFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.models import CharacterSheet
from world.magic.constants import TargetKind
from world.magic.factories import (
    BinaryEffectTypeFactory,
    CharacterTechniqueFactory,
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
)
from world.magic.models import Gift, Resonance, Technique, Thread
from world.magic.specialization.models import TechniqueVariant
from world.magic.specialization.services import provision_latent_gift_thread
from world.scenes.action_serializers import (
    CastableTechniqueSerializer,
    TechniqueCastCreateSerializer,
)


class CastableTechniqueFormsTest(TestCase):
    """``forms`` on the in-scene cast list."""

    sheet: ClassVar[CharacterSheet]
    gift: ClassVar[Gift]
    resonance: ClassVar[Resonance]
    technique: ClassVar[Technique]
    variant: ClassVar[TechniqueVariant]

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.gift = GiftFactory()
        cls.resonance = ResonanceFactory(name="Cinder")
        cls.gift.resonances.add(cls.resonance)
        cls.technique = TechniqueFactory(
            gift=cls.gift,
            effect_type=BinaryEffectTypeFactory(),
            damage_profile=False,
            action_template=ActionTemplateFactory(),
        )
        cls.link = CharacterTechniqueFactory(character=cls.sheet, technique=cls.technique)
        cls.variant = TechniqueVariant.objects.create(
            parent_technique=cls.technique,
            resonance=cls.resonance,
            unlock_thread_level=3,
            name_override="Ashfall Lash",
        )

    def _thread_at(self, level: int) -> Thread:
        provision_latent_gift_thread(self.sheet, self.gift, resonance=self.resonance)
        thread = Thread.objects.get(
            owner=self.sheet, target_kind=TargetKind.GIFT, target_gift=self.gift
        )
        thread.level = level
        thread.save(update_fields=["level"])
        self.sheet.character.threads.invalidate()
        return thread

    def _serialize(self) -> dict:
        return CastableTechniqueSerializer(
            self.technique,
            context={
                "character": self.sheet.character,
                "character_sheet": self.sheet,
                "character_techniques": {self.technique.pk: self.link},
            },
        ).data

    def test_ships_the_base_form_when_nothing_is_unlocked(self) -> None:
        data = self._serialize()
        self.assertEqual(len(data["forms"]), 1)
        self.assertIsNone(data["forms"][0]["variant_id"])
        self.assertTrue(data["forms"][0]["is_default"])

    def test_ships_base_and_variant_once_the_thread_reaches_the_unlock(self) -> None:
        """A variant adds a form; it does not replace the technique."""
        self._thread_at(3)
        data = self._serialize()

        self.assertEqual(len(data["forms"]), 2)
        base, variant = data["forms"]
        self.assertIsNone(base["variant_id"])
        self.assertFalse(base["is_default"])
        self.assertEqual(variant["variant_id"], self.variant.pk)
        self.assertTrue(variant["is_default"])
        # The resonance name IS the token a player passes to `variant=`.
        self.assertEqual(variant["resonance_name"], "Cinder")

    def test_locked_forms_are_omitted_from_the_scene(self) -> None:
        """The scene shows what you can work now; the sheet shows the goal."""
        self._thread_at(1)
        data = self._serialize()

        self.assertEqual([f["variant_id"] for f in data["forms"]], [None])

    def test_forms_is_never_absent_without_a_caster_in_context(self) -> None:
        """Schema generation and caster-less reads still get a well-formed field."""
        data = CastableTechniqueSerializer(self.technique).data
        self.assertEqual(len(data["forms"]), 1)
        self.assertIsNone(data["forms"][0]["variant_id"])

    def test_each_form_carries_the_shared_effect_block(self) -> None:
        self._thread_at(3)
        data = self._serialize()
        for form in data["forms"]:
            self.assertIn("summary", form["effect_summary"])


class CastRequestFormSelectionTest(TestCase):
    """``preferred_resonance_id`` on the cast request — telnet's ``variant=`` for the web."""

    def _validated(self, **extra) -> dict:
        serializer = TechniqueCastCreateSerializer(
            data={"scene": 1, "initiator_persona": 1, "technique_id": 1, **extra}
        )
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def test_preferred_resonance_id_is_accepted_and_carried(self) -> None:
        self.assertEqual(self._validated(preferred_resonance_id=7)["preferred_resonance_id"], 7)

    def test_omitting_it_means_the_default_form(self) -> None:
        """No pick is not the same as picking the base form."""
        validated = self._validated()
        self.assertIsNone(validated["preferred_resonance_id"])
        self.assertFalse(validated["use_base_form"])

    def test_base_form_opt_out_still_works_alongside_it(self) -> None:
        validated = self._validated(use_base_form=True)
        self.assertTrue(validated["use_base_form"])
        self.assertIsNone(validated["preferred_resonance_id"])
