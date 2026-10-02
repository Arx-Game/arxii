"""Personalizing a technique in character creation (#4099)."""

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

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

    def test_personalization_costs_push_the_purse_over_budget(self) -> None:
        """The 8-point pick total overspends a purse with no room for it (#4099)."""
        from world.character_creation.models import CGPointBudget
        from world.character_creation.validators import get_purse_errors

        CGPointBudget.objects.create(name="Tight Purse", is_active=True, starting_points=0)
        draft = CharacterDraftFactory(
            draft_data={
                "selected_technique_ids": [self.technique.pk],
                TECHNIQUE_PERSONALIZATIONS_KEY: self._personalization(),
            }
        )
        self.assertEqual(get_purse_errors(draft), ["CG points over budget by 8"])

    def test_deselected_technique_is_never_charged_in_the_breakdown(self) -> None:
        draft = CharacterDraftFactory(
            draft_data={
                "selected_technique_ids": [],
                TECHNIQUE_PERSONALIZATIONS_KEY: self._personalization(),
            }
        )
        magic = [e for e in draft.calculate_cg_points_breakdown() if e["category"] == "magic"]
        self.assertEqual(magic, [])


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

    def test_custom_name_colliding_with_another_known_techniques_catalog_name(self) -> None:
        """A custom name must not equal, case-insensitively, the catalog name of
        another selected technique (#4099 final fix) — telnet/cast and
        SpellbookTab's React key would otherwise collide."""
        other = TechniqueFactory(gift=self.gift, name="Winterbite")
        picks = parse_personalization_picks(
            self._personalization(custom_name="winterbite"), technique_ids=[self.technique.pk]
        )
        errors = personalization_pick_errors(
            picks, techniques=[self.technique, other], resonance_id=self.frost.pk
        )
        self.assertTrue(errors)

    def test_flourish_exceeding_a_level_0_technique_anchor_cap_is_rejected(self) -> None:
        """A level-0 technique has anchor cap 0 (#4099 final fix) - any flourish
        needing a deeper thread must fail validation here, not at finalize."""
        zero_level_technique = TechniqueFactory(gift=self.gift, name="Ember Spark", level=0)
        picks = parse_personalization_picks(
            {str(zero_level_technique.pk): {"signature_bonus_id": self.flourish.pk}},
            technique_ids=[zero_level_technique.pk],
        )
        errors = personalization_pick_errors(
            picks, techniques=[zero_level_technique], resonance_id=self.frost.pk
        )
        self.assertTrue(errors)

    def test_custom_name_matching_its_own_technique_name_is_not_a_collision(self) -> None:
        """Renaming a technique to its own catalog name is a no-op, not a collision."""
        picks = parse_personalization_picks(
            self._personalization(custom_name=self.technique.name),
            technique_ids=[self.technique.pk],
        )
        errors = personalization_pick_errors(
            picks, techniques=[self.technique], resonance_id=self.frost.pk
        )
        self.assertEqual(errors, [])


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

        for bad in (
            [],
            {"x": {}},
            {str(self.technique.pk): {"price_id": "nope"}},
            # A digit character `int()` can't parse (superscript two, #4099 fix
            # round 1) — `isdigit()` alone would have let this through.
            {"²": {}},
        ):
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

    def test_finalize_then_hold_for_shows_the_picks(self) -> None:
        """Exercises the cache invalidation apply_creation_personalizations calls."""
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
        # Warm the handler's hold cache before finalize writes anything, mirroring
        # a caller that read the (pre-pick) hold map earlier in the same process.
        sheet.character.techniques.hold_for(self.technique)
        finalize_magic_data(draft, sheet)

        hold = sheet.character.techniques.hold_for(self.technique)
        self.assertIsNotNone(hold)
        self.assertEqual(hold.custom_name, "Winterbite")
        self.assertEqual(hold.price, self.price)
        self.assertEqual(hold.early_form, self.form)

    def test_deselected_technique_picks_are_not_written_at_finalize(self) -> None:
        sheet = CharacterSheetFactory()
        draft = CharacterDraftFactory(
            selected_tradition=TraditionFactory(),
            draft_data={
                "selected_gift_id": self.gift.pk,
                "selected_technique_ids": [],
                "selected_gift_resonance_id": self.frost.pk,
                TECHNIQUE_PERSONALIZATIONS_KEY: self._personalization(),
            },
        )
        finalize_magic_data(draft, sheet)
        self.assertFalse(
            CharacterTechnique.objects.filter(character=sheet, technique=self.technique).exists()
        )

    def test_apply_refuses_an_early_form_belonging_to_another_technique(self) -> None:
        from django.core.exceptions import ValidationError

        from world.magic.services.creation_personalization import (
            apply_creation_personalizations,
        )
        from world.magic.types.personalization import TechniquePersonalizationPick

        other_technique = TechniqueFactory(gift=self.gift)
        foreign_form = TechniqueVariantFactory(
            parent_technique=other_technique,
            resonance=self.frost,
            unlock_thread_level=1,
            creation_point_cost=1,
        )
        sheet = CharacterSheetFactory()
        CharacterTechnique.objects.create(character=sheet, technique=self.technique)
        pick = TechniquePersonalizationPick(
            technique_id=self.technique.pk, early_form_id=foreign_form.pk
        )
        with self.assertRaises(ValidationError):
            apply_creation_personalizations(sheet, [pick], resonance=self.frost)


class PriceFitTests(_Catalog, TestCase):
    """Direct coverage of `_price_fits` (#4099 fix round 1)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls._make_catalog()

    def test_price_fits_rejects_a_price_whose_allowed_effect_types_exclude_the_technique(
        self,
    ) -> None:
        from world.magic.factories import EffectTypeFactory
        from world.magic.services.creation_personalization import (
            _allowed_effect_type_ids_by_price,
            _price_fits,
        )

        other_effect_type = EffectTypeFactory()
        price = PriceFactory(creation_point_cost=1)
        price.allowed_effect_types.set([other_effect_type])
        allowed_by_price = _allowed_effect_type_ids_by_price([price])
        self.assertNotEqual(other_effect_type.pk, self.technique.effect_type_id)
        self.assertFalse(_price_fits(price, allowed_by_price, self.technique))


class PersonalizationOptionsEndpointTests(_Catalog, TestCase):
    """GET drafts/{id}/personalization-options/ (#4099)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls._make_catalog()

    def setUp(self) -> None:
        from rest_framework.test import APIClient

        from evennia_extensions.factories import AccountFactory

        self.account = AccountFactory()
        self.client = APIClient()
        self.client.force_authenticate(self.account)

    def _draft(self, resonance_id):
        return CharacterDraftFactory(
            account=self.account,
            draft_data={
                "selected_gift_id": self.gift.pk,
                "selected_technique_ids": [self.technique.pk],
                "selected_gift_resonance_id": resonance_id,
            },
        )

    def test_offers_per_selected_technique(self) -> None:
        draft = self._draft(self.frost.pk)
        response = self.client.get(
            f"/api/character-creation/drafts/{draft.pk}/personalization-options/"
        )
        self.assertEqual(response.status_code, 200)
        [entry] = response.data
        self.assertEqual(entry["technique_id"], self.technique.pk)
        self.assertFalse(entry["needs_resonance"])
        self.assertEqual([f["cost"] for f in entry["flourishes"]], [3])
        self.assertEqual(entry["forms"][0]["name"], "Scorch Lash, frost-formed")
        self.assertEqual(entry["prices"][0]["power_bonus"], 4)
        self.assertEqual(entry["prices"][0]["consumes"], [])
        self.assertIsNone(entry["prices"][0]["inflicts"])
        self.assertEqual(entry["flourishes"][0]["consumes"], [])
        self.assertIsNone(entry["forms"][0]["inflicts"])

    def test_a_price_option_carries_its_real_cost(self) -> None:
        """A player sees what a price consumes and inflicts before choosing it (#4099)."""
        from world.conditions.factories import ConditionTemplateFactory
        from world.items.factories import ItemTemplateFactory
        from world.magic.models import PriceComponentRequirement

        self.price.inflicted_condition = ConditionTemplateFactory(name="Numb hands")
        self.price.save(update_fields=["inflicted_condition"])
        PriceComponentRequirement.objects.create(
            restriction=self.price,
            item_template=ItemTemplateFactory(name="Vial of snowmelt"),
            quantity=3,
        )
        draft = self._draft(self.frost.pk)
        response = self.client.get(
            f"/api/character-creation/drafts/{draft.pk}/personalization-options/"
        )
        [entry] = response.data
        [price] = entry["prices"]
        self.assertEqual(price["consumes"], [{"name": "Vial of snowmelt", "quantity": 3}])
        self.assertEqual(price["inflicts"], "Numb hands")

    def test_without_a_resonance_flourishes_and_forms_wait(self) -> None:
        draft = self._draft(None)
        response = self.client.get(
            f"/api/character-creation/drafts/{draft.pk}/personalization-options/"
        )
        [entry] = response.data
        self.assertTrue(entry["needs_resonance"])
        self.assertEqual(entry["flourishes"], [])
        self.assertEqual(entry["forms"], [])
        self.assertEqual(len(entry["prices"]), 1)

    def test_other_accounts_draft_is_not_found(self) -> None:
        other = CharacterDraftFactory()
        response = self.client.get(
            f"/api/character-creation/drafts/{other.pk}/personalization-options/"
        )
        self.assertEqual(response.status_code, 404)

    def test_an_ultimate_in_selected_technique_ids_gets_no_entry(self) -> None:
        """A draft PATCH could put an ultimate's pk in selected_technique_ids; the
        endpoint must never reveal an undiscovered ultimate's name or options (#4099
        fix round 1)."""
        from world.magic.factories import UltimateTechniqueFactory

        ultimate = UltimateTechniqueFactory(gift=self.gift, name="Secret Finisher")
        draft = CharacterDraftFactory(
            account=self.account,
            draft_data={
                "selected_gift_id": self.gift.pk,
                "selected_technique_ids": [self.technique.pk, ultimate.pk],
                "selected_gift_resonance_id": self.frost.pk,
            },
        )
        response = self.client.get(
            f"/api/character-creation/drafts/{draft.pk}/personalization-options/"
        )
        self.assertEqual(response.status_code, 200)
        technique_ids = [entry["technique_id"] for entry in response.data]
        self.assertEqual(technique_ids, [self.technique.pk])
        self.assertNotIn(ultimate.pk, technique_ids)

    def test_query_count_is_fixed_regardless_of_technique_count(self) -> None:
        from world.magic.factories import TechniqueFactory, TechniqueVariantFactory

        second_technique = TechniqueFactory(gift=self.gift, name="Frost Needle", level=1)
        TechniqueVariantFactory(
            parent_technique=second_technique,
            resonance=self.frost,
            unlock_thread_level=1,
            name_override="Frost Needle, forged",
            creation_point_cost=2,
        )
        one_draft = self._draft(self.frost.pk)
        two_draft = CharacterDraftFactory(
            account=self.account,
            draft_data={
                "selected_gift_id": self.gift.pk,
                "selected_technique_ids": [self.technique.pk, second_technique.pk],
                "selected_gift_resonance_id": self.frost.pk,
            },
        )

        # Warm up one-time, non-view costs (content-type cache, session/auth
        # queries on the first authenticated request) so they land on neither
        # measured call below and don't confound the comparison.
        self.client.get(f"/api/character-creation/drafts/{one_draft.pk}/personalization-options/")

        with CaptureQueriesContext(connection) as one_capture:
            response = self.client.get(
                f"/api/character-creation/drafts/{one_draft.pk}/personalization-options/"
            )
        self.assertEqual(response.status_code, 200)

        with CaptureQueriesContext(connection) as two_capture:
            response = self.client.get(
                f"/api/character-creation/drafts/{two_draft.pk}/personalization-options/"
            )
        self.assertEqual(response.status_code, 200)

        self.assertEqual(len(one_capture), len(two_capture))

    def test_multi_technique_options_do_not_leak_across_techniques(self) -> None:
        from world.magic.factories import TechniqueFactory, TechniqueVariantFactory

        second_technique = TechniqueFactory(gift=self.gift, name="Frost Needle", level=1)
        second_form = TechniqueVariantFactory(
            parent_technique=second_technique,
            resonance=self.frost,
            unlock_thread_level=1,
            name_override="Frost Needle, forged",
            creation_point_cost=2,
        )
        draft = CharacterDraftFactory(
            account=self.account,
            draft_data={
                "selected_gift_id": self.gift.pk,
                "selected_technique_ids": [self.technique.pk, second_technique.pk],
                "selected_gift_resonance_id": self.frost.pk,
            },
        )
        response = self.client.get(
            f"/api/character-creation/drafts/{draft.pk}/personalization-options/"
        )
        self.assertEqual(response.status_code, 200)
        by_technique_id = {entry["technique_id"]: entry for entry in response.data}
        first_forms = by_technique_id[self.technique.pk]["forms"]
        second_forms = by_technique_id[second_technique.pk]["forms"]
        self.assertEqual([f["id"] for f in first_forms], [self.form.pk])
        self.assertEqual([f["id"] for f in second_forms], [second_form.pk])
