"""Personalizing a technique in character creation (#4099)."""

from django.test import TestCase

from world.character_creation.constants import TECHNIQUE_PERSONALIZATIONS_KEY
from world.character_creation.factories import CharacterDraftFactory
from world.character_creation.serializers import CharacterDraftSerializer
from world.character_creation.services import finalize_magic_data
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    GiftFactory,
    PriceFactory,
    ResonanceFactory,
    SignatureMotifBonusFactory,
    TechniqueFactory,
    TechniqueVariantFactory,
    TraditionFactory,
)
from world.magic.models import CharacterTechnique
from world.magic.services.creation_personalization import (
    parse_personalization_picks,
    personalization_pick_errors,
    priced_personalization_lines,
)


class _Catalog:
    @classmethod
    def _make_catalog(cls) -> None:
        cls.gift = GiftFactory(name="Ember")
        cls.frost = ResonanceFactory(name="Frost")
        cls.other_resonance = ResonanceFactory(name="Ash")
        cls.technique = TechniqueFactory(gift=cls.gift, name="Scorch Lash", level=1)
        cls.flourish = SignatureMotifBonusFactory(
            name="A chill rides your voice",
            required_resonance=cls.frost,
            min_crossing_level=1,
            creation_point_cost=3,
        )
        cls.form = TechniqueVariantFactory(
            parent_technique=cls.technique,
            resonance=cls.frost,
            unlock_thread_level=1,
            name_override="Scorch Lash, frost-formed",
            creation_point_cost=4,
        )
        cls.price = PriceFactory(name="Frost on the skin", creation_point_cost=1, power_bonus=4)

    def _personalization(self, **overrides) -> dict:
        entry = {
            "custom_name": "Winterbite",
            "custom_description": "Flame gutters to white.",
            "signature_bonus_id": self.flourish.pk,
            "early_form_id": self.form.pk,
            "price_id": self.price.pk,
        }
        entry.update(overrides)
        return {str(self.technique.pk): entry}


class PricingTests(_Catalog, TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls._make_catalog()

    def test_each_pick_is_one_priced_line(self) -> None:
        picks = parse_personalization_picks(
            self._personalization(), technique_ids=[self.technique.pk]
        )
        lines = priced_personalization_lines(
            picks, techniques_by_id={self.technique.pk: self.technique}
        )
        self.assertEqual(sorted(line.cost for line in lines), [1, 3, 4])
        self.assertTrue(all(line.technique_name == "Scorch Lash" for line in lines))

    def test_unselected_technique_is_never_charged(self) -> None:
        picks = parse_personalization_picks(self._personalization(), technique_ids=[])
        self.assertEqual(picks, [])

    def test_draft_breakdown_carries_the_lines(self) -> None:
        draft = CharacterDraftFactory(
            draft_data={
                "selected_technique_ids": [self.technique.pk],
                TECHNIQUE_PERSONALIZATIONS_KEY: self._personalization(),
            }
        )
        magic = [e for e in draft.calculate_cg_points_breakdown() if e["category"] == "magic"]
        self.assertEqual(sum(e["cost"] for e in magic), 8)


class PickErrorTests(_Catalog, TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls._make_catalog()

    def _errors(self, resonance_id, **overrides) -> list[str]:
        picks = parse_personalization_picks(
            self._personalization(**overrides), technique_ids=[self.technique.pk]
        )
        return personalization_pick_errors(
            picks, techniques=[self.technique], resonance_id=resonance_id
        )

    def test_valid_picks_have_no_errors(self) -> None:
        self.assertEqual(self._errors(self.frost.pk), [])

    def test_resonance_change_invalidates_flourish_and_form(self) -> None:
        self.assertTrue(self._errors(self.other_resonance.pk))

    def test_design_restriction_is_not_a_price(self) -> None:
        from world.magic.factories import RestrictionFactory

        self.assertTrue(self._errors(self.frost.pk, price_id=RestrictionFactory().pk))

    def test_uncosted_flourish_is_not_offered(self) -> None:
        uncosted = SignatureMotifBonusFactory(required_resonance=self.frost, min_crossing_level=1)
        self.assertTrue(self._errors(self.frost.pk, signature_bonus_id=uncosted.pk))


class DraftSerializerTests(_Catalog, TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls._make_catalog()

    def test_name_hygiene_runs_on_save(self) -> None:
        serializer = CharacterDraftSerializer()
        cleaned = serializer.validate_draft_data(
            {TECHNIQUE_PERSONALIZATIONS_KEY: self._personalization(custom_name="  Winter  bite ")}
        )
        entry = cleaned[TECHNIQUE_PERSONALIZATIONS_KEY][str(self.technique.pk)]
        self.assertEqual(entry["custom_name"], "Winter bite")

    def test_dash_in_a_name_is_refused(self) -> None:
        from rest_framework import serializers

        # Computed, not a literal dash character (ruff-format would unescape a `—`
        # literal into the real character, which then trips the identifier-dashes
        # linter's AST scan for an actual em-dash in a `*name=` kwarg; #4099 Task 1).
        dashed_name = f"A{chr(0x2014)}B"
        with self.assertRaises(serializers.ValidationError):
            CharacterDraftSerializer().validate_draft_data(
                {TECHNIQUE_PERSONALIZATIONS_KEY: self._personalization(custom_name=dashed_name)}
            )

    def test_malformed_shape_is_refused(self) -> None:
        from rest_framework import serializers

        for bad in ([], {"x": {}}, {str(self.technique.pk): {"price_id": "nope"}}):
            with self.assertRaises(serializers.ValidationError):
                CharacterDraftSerializer().validate_draft_data(
                    {TECHNIQUE_PERSONALIZATIONS_KEY: bad}
                )


class FinalizeTests(_Catalog, TestCase):
    """Creation finalize writes priced rows (spec test seam)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls._make_catalog()

    def test_finalize_writes_the_hold_thread_and_motif(self) -> None:
        sheet = CharacterSheetFactory()
        draft = CharacterDraftFactory(
            selected_tradition=TraditionFactory(),
            draft_data={
                "selected_gift_id": self.gift.pk,
                "selected_technique_ids": [self.technique.pk],
                "selected_gift_resonance_id": self.frost.pk,
                TECHNIQUE_PERSONALIZATIONS_KEY: self._personalization(),
            },
        )
        finalize_magic_data(draft, sheet)

        hold = CharacterTechnique.objects.get(character=sheet, technique=self.technique)
        self.assertEqual(hold.custom_name, "Winterbite")
        self.assertEqual(hold.custom_description, "Flame gutters to white.")
        self.assertEqual(hold.price, self.price)
        self.assertEqual(hold.early_form, self.form)
        thread = next(
            t
            for t in sheet.character.threads.all()
            if t.target_kind == TargetKind.TECHNIQUE and t.target_technique_id == self.technique.pk
        )
        self.assertEqual(thread.level, 1)
        self.assertEqual(thread.resonance, self.frost)
        self.assertEqual(thread.signature_bonus, self.flourish)
        self.assertTrue(sheet.motif.resonances.filter(resonance=self.frost).exists())

    def test_finalize_without_picks_still_seeds_the_motif(self) -> None:
        sheet = CharacterSheetFactory()
        draft = CharacterDraftFactory(
            selected_tradition=TraditionFactory(),
            draft_data={
                "selected_gift_id": self.gift.pk,
                "selected_technique_ids": [self.technique.pk],
                "selected_gift_resonance_id": self.frost.pk,
            },
        )
        finalize_magic_data(draft, sheet)
        self.assertTrue(sheet.motif.resonances.filter(resonance=self.frost).exists())
