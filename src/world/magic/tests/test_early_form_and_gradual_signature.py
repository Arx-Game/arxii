"""Early forms and flourishes that grow with the thread (#4099)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.covenants.factories import CharacterCovenantRoleFactory
from world.magic.constants import TargetKind
from world.magic.exceptions import CreationThreadLevelTooHigh, TechniqueNotOwned
from world.magic.factories import (
    CharacterTechniqueFactory,
    GiftFactory,
    ResonanceFactory,
    SignatureMotifBonusFactory,
    TechniqueFactory,
    TechniqueVariantFactory,
)
from world.magic.models import CharacterResonance, CharacterTechnique, Thread
from world.magic.serializers import TechniqueFormSerializer
from world.magic.services.resonance import spend_resonance_for_imbuing
from world.magic.services.signature import (
    available_signature_bonuses,
    next_signature_bonus,
    set_signature_bonus,
)
from world.magic.services.technique_forms import available_technique_forms
from world.magic.services.technique_personalization import seed_motif_from_gift_resonance
from world.magic.services.threads import weave_creation_technique_thread
from world.magic.specialization.services import (
    _ResolvedTechnique,
    provision_latent_gift_thread,
    resolve_specialized_variant,
)


class EarlyFormTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.gift = GiftFactory()
        cls.frost = ResonanceFactory(name="Frost")
        cls.ash = ResonanceFactory(name="Ash")
        cls.technique = TechniqueFactory(gift=cls.gift, name="Scorch Lash")
        cls.frost_form = TechniqueVariantFactory(
            parent_technique=cls.technique,
            resonance=cls.frost,
            unlock_thread_level=1,
            name_override="Scorch Lash, frost-formed",
            creation_point_cost=4,
        )
        cls.ash_form = TechniqueVariantFactory(
            parent_technique=cls.technique,
            resonance=cls.ash,
            unlock_thread_level=1,
            creation_point_cost=4,
        )
        provision_latent_gift_thread(cls.sheet, cls.gift, resonance=cls.frost)  # level 0

    def _hold(self, early_form=None):
        hold = CharacterTechniqueFactory(character=self.sheet, technique=self.technique)
        hold.early_form = early_form
        hold.save(update_fields=["early_form"])
        self.sheet.character.techniques.invalidate()
        return hold

    def test_bought_form_applies_before_the_thread_reaches_it(self) -> None:
        self._hold(self.frost_form)
        resolved = resolve_specialized_variant(
            entity=self.technique, character=self.sheet.character
        )
        self.assertIsInstance(resolved, _ResolvedTechnique)
        self.assertEqual(resolved.variant, self.frost_form)

    def test_no_bought_form_means_the_base_technique_at_level_zero(self) -> None:
        self._hold(None)
        resolved = resolve_specialized_variant(
            entity=self.technique, character=self.sheet.character
        )
        self.assertEqual(resolved, self.technique)

    def test_bought_form_at_another_resonance_does_not_apply(self) -> None:
        self._hold(self.ash_form)
        resolved = resolve_specialized_variant(
            entity=self.technique, character=self.sheet.character
        )
        self.assertEqual(resolved, self.technique)

    def test_sheet_forms_mark_the_early_form_and_do_not_list_it_as_locked(self) -> None:
        hold = self._hold(self.frost_form)
        forms = available_technique_forms(
            self.sheet.character, self.technique, character_technique=hold, sheet=self.sheet
        )
        early = [f for f in forms if f["variant_id"] == self.frost_form.pk]
        self.assertEqual(len(early), 1)
        self.assertTrue(early[0]["is_early"])
        self.assertFalse(early[0]["is_locked"])

    def test_is_early_reaches_the_serialized_form(self) -> None:
        """TechniqueFormSerializer declares its fields explicitly, so a new payload
        key must be added to it by name or it is silently dropped (fix round 1)."""
        hold = self._hold(self.frost_form)
        forms = available_technique_forms(
            self.sheet.character, self.technique, character_technique=hold, sheet=self.sheet
        )
        serialized = TechniqueFormSerializer(forms, many=True).data
        early = next(f for f in serialized if f["variant_id"] == self.frost_form.pk)
        self.assertTrue(early["is_early"])

    def test_another_character_without_the_form_does_not_get_it(self) -> None:
        """A true non-buyer: a second character's own hold, same resonance, no pick."""
        other_sheet = CharacterSheetFactory()
        CharacterTechniqueFactory(character=other_sheet, technique=self.technique)
        provision_latent_gift_thread(other_sheet, self.gift, resonance=self.frost)

        resolved = resolve_specialized_variant(
            entity=self.technique, character=other_sheet.character
        )
        self.assertEqual(resolved, self.technique)

    def test_naturally_reached_higher_form_beats_the_early_form(self) -> None:
        hold = self._hold(self.frost_form)  # unlock_thread_level=1
        ascended_form = TechniqueVariantFactory(
            parent_technique=self.technique,
            resonance=self.frost,
            unlock_thread_level=2,
            name_override="Scorch Lash, frost-ascended",
        )
        thread = Thread.objects.get(
            owner=self.sheet, target_kind=TargetKind.GIFT, target_gift=self.gift
        )
        thread.level = 2
        thread.save(update_fields=["level"])
        self.sheet.character.threads.invalidate()

        resolved = resolve_specialized_variant(
            entity=self.technique, character=self.sheet.character, character_technique=hold
        )
        self.assertIsInstance(resolved, _ResolvedTechnique)
        self.assertEqual(resolved.variant, ascended_form)

    def test_is_early_becomes_false_once_the_thread_reaches_the_forms_level(self) -> None:
        hold = self._hold(self.frost_form)  # unlock_thread_level=1
        thread = Thread.objects.get(
            owner=self.sheet, target_kind=TargetKind.GIFT, target_gift=self.gift
        )
        thread.level = 1
        thread.save(update_fields=["level"])
        self.sheet.character.threads.invalidate()

        forms = available_technique_forms(
            self.sheet.character, self.technique, character_technique=hold, sheet=self.sheet
        )
        early = next(f for f in forms if f["variant_id"] == self.frost_form.pk)
        self.assertFalse(early["is_early"])
        self.assertFalse(early["is_locked"])

    def test_role_granted_hold_does_not_leak_early_form(self) -> None:
        """A role-granted hold's early_form never applies, even when the caller omits
        ``character_technique`` — the gate reads the hold's own role_source_id, not
        only the (possibly-absent) caller-supplied flag (fix round 1)."""
        membership = CharacterCovenantRoleFactory(character_sheet=self.sheet)
        CharacterTechnique.objects.create(
            character=self.sheet,
            technique=self.technique,
            role_source=membership,
            early_form=self.frost_form,
        )
        self.sheet.character.techniques.invalidate()

        resolved = resolve_specialized_variant(
            entity=self.technique, character=self.sheet.character
        )
        self.assertEqual(resolved, self.technique)


class GradualSignatureTests(TestCase):
    """Weaving a thread unlocks the next flourish (spec test seam)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.sheet = CharacterSheetFactory()
        cls.resonance = ResonanceFactory()
        cls.technique = TechniqueFactory(level=1)  # TECHNIQUE anchor cap = level x 10
        CharacterTechniqueFactory(character=cls.sheet, technique=cls.technique)
        seed_motif_from_gift_resonance(cls.sheet, cls.resonance)
        cls.modest = SignatureMotifBonusFactory(
            required_resonance=cls.resonance, min_crossing_level=1, creation_point_cost=3
        )
        cls.stronger = SignatureMotifBonusFactory(
            required_resonance=cls.resonance, min_crossing_level=3
        )

    def test_flourish_at_level_one_needs_no_crossing(self) -> None:
        thread = weave_creation_technique_thread(
            self.sheet, self.technique, self.resonance, level=1
        )
        set_signature_bonus(thread, self.modest)
        self.assertEqual(thread.signature_bonus, self.modest)

    def test_weaving_further_unlocks_the_next_flourish(self) -> None:
        thread = weave_creation_technique_thread(
            self.sheet, self.technique, self.resonance, level=1
        )
        catalog = [self.modest, self.stronger]
        self.assertEqual(next_signature_bonus(thread, catalog), self.stronger)
        self.assertNotIn(self.stronger, available_signature_bonuses(self.sheet, thread=thread))

        cr, _ = CharacterResonance.objects.get_or_create(
            character_sheet=self.sheet, resonance=self.resonance
        )
        cr.balance = 9999
        cr.save(update_fields=["balance"])
        spend_resonance_for_imbuing(self.sheet, thread, 2)  # 1 -> 3

        self.assertEqual(thread.level, 3)
        self.assertIn(self.stronger, available_signature_bonuses(self.sheet, thread=thread))
        self.assertIsNone(next_signature_bonus(thread, catalog))
        set_signature_bonus(thread, self.stronger)

    def test_creation_thread_never_reaches_a_crossing(self) -> None:
        with self.assertRaises(CreationThreadLevelTooHigh):
            weave_creation_technique_thread(self.sheet, self.technique, self.resonance, level=3)

    def test_creation_thread_is_a_technique_thread(self) -> None:
        thread = weave_creation_technique_thread(
            self.sheet, self.technique, self.resonance, level=0
        )
        self.assertEqual(thread.target_kind, TargetKind.TECHNIQUE)
        self.assertEqual(thread.target_technique, self.technique)

    def test_weaving_at_exactly_level_two_succeeds(self) -> None:
        """CREATION_PERSONALIZATION_MAX_LEVEL (2) is the inclusive ceiling."""
        thread = weave_creation_technique_thread(
            self.sheet, self.technique, self.resonance, level=2
        )
        self.assertEqual(thread.level, 2)

    def test_creation_weave_of_unowned_technique_raises_technique_not_owned(self) -> None:
        unowned_technique = TechniqueFactory(level=1)
        with self.assertRaises(TechniqueNotOwned):
            weave_creation_technique_thread(self.sheet, unowned_technique, self.resonance, level=1)
