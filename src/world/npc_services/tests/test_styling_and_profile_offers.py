"""STYLING + PROFILE_RECORDING offer kinds (#2632)."""

from __future__ import annotations

from django.test import TestCase

from world.currency.services import get_or_create_purse, transfer
from world.forms.factories import (
    CharacterFormFactory,
    CharacterFormValueFactory,
    FormTraitFactory,
    FormTraitOptionFactory,
)
from world.npc_services.constants import OfferKind, RecordedProfileStatus
from world.npc_services.effects import (
    dispatch_offer_effect,
    run_profile_recording_offer,
    run_styling_offer,
)
from world.npc_services.factories import (
    NPCRoleFactory,
    NPCServiceOfferFactory,
    ProfileRecordingOfferDetailsFactory,
    StylingOfferDetailsFactory,
)
from world.npc_services.models import RecordedProfile
from world.npc_services.services import (
    RecordedProfileError,
    complete_recorded_profile,
)
from world.scenes.factories import PersonaFactory


def _fund(sheet, amount: int) -> None:
    transfer(amount=amount, reason="test faucet", to_purse=get_or_create_purse(sheet))


class StylingOfferTests(TestCase):
    def setUp(self) -> None:
        self.persona = PersonaFactory()
        self.sheet = self.persona.character_sheet
        self.trait = FormTraitFactory(name="hair_color_npc", is_cosmetic=True)
        self.raven = FormTraitOptionFactory(trait=self.trait, name="raven")
        self.crimson = FormTraitOptionFactory(trait=self.trait, name="crimson")
        form = CharacterFormFactory(character=self.sheet.character)
        CharacterFormValueFactory(form=form, trait=self.trait, option=self.raven)
        self.form = form
        role = NPCRoleFactory(name="Silver Shears Stylist")
        self.offer = NPCServiceOfferFactory(
            role=role, kind=OfferKind.STYLING, label="Crimson dye", is_final=True
        )
        self.details = StylingOfferDetailsFactory(
            offer=self.offer,
            trait=self.trait,
            target_option=self.crimson,
            price_coppers=100,
        )

    def test_styling_charges_and_restyles(self) -> None:
        _fund(self.sheet, 150)
        result = run_styling_offer(self.offer, self.persona)

        self.assertIn("crimson", result.message.lower())
        value = self.form.values.get(trait=self.trait)
        self.assertEqual(value.option, self.crimson)
        self.assertEqual(get_or_create_purse(self.sheet).balance, 50)

    def test_insufficient_funds_soft_refusal(self) -> None:
        _fund(self.sheet, 10)
        result = run_styling_offer(self.offer, self.persona)

        self.assertIn("afford", result.message)
        value = self.form.values.get(trait=self.trait)
        self.assertEqual(value.option, self.raven)
        self.assertEqual(get_or_create_purse(self.sheet).balance, 10)

    def test_dispatch_reaches_styling_handler(self) -> None:
        _fund(self.sheet, 150)
        result = dispatch_offer_effect(self.offer, self.persona)
        self.assertEqual(result.kind, OfferKind.STYLING.value)


class ProfileRecordingOfferTests(TestCase):
    def setUp(self) -> None:
        self.persona = PersonaFactory()
        self.sheet = self.persona.character_sheet
        role = NPCRoleFactory(name="Great Archive Profile Scribe")
        self.offer = NPCServiceOfferFactory(
            role=role,
            kind=OfferKind.PROFILE_RECORDING,
            label="Commission a profile",
            is_final=True,
        )
        ProfileRecordingOfferDetailsFactory(offer=self.offer, price_coppers=500)

    def test_sitting_charges_and_commissions(self) -> None:
        _fund(self.sheet, 600)
        result = run_profile_recording_offer(self.offer, self.persona)

        profile = RecordedProfile.objects.get(pk=result.object_pk)
        self.assertEqual(profile.status, RecordedProfileStatus.COMMISSIONED)
        self.assertEqual(profile.price_paid, 500)
        self.assertEqual(profile.recorded_by_label, "Great Archive Profile Scribe")
        self.assertEqual(get_or_create_purse(self.sheet).balance, 100)

    def test_insufficient_funds_soft_refusal(self) -> None:
        result = run_profile_recording_offer(self.offer, self.persona)
        self.assertIn("afford", result.message)
        self.assertFalse(RecordedProfile.objects.exists())

    def test_complete_sets_description_and_archives(self) -> None:
        _fund(self.sheet, 500)
        result = run_profile_recording_offer(self.offer, self.persona)
        profile = RecordedProfile.objects.get(pk=result.object_pk)

        complete_recorded_profile(profile, "A figure of impossible elegance.")

        profile.refresh_from_db()
        self.assertEqual(profile.status, RecordedProfileStatus.RECORDED)
        self.assertIsNotNone(profile.recorded_at)
        self.sheet.refresh_from_db()
        self.assertEqual(self.sheet.additional_desc, "A figure of impossible elegance.")

    def test_complete_twice_rejected(self) -> None:
        _fund(self.sheet, 500)
        result = run_profile_recording_offer(self.offer, self.persona)
        profile = RecordedProfile.objects.get(pk=result.object_pk)
        complete_recorded_profile(profile, "First text.")
        with self.assertRaises(RecordedProfileError):
            complete_recorded_profile(profile, "Second text.")

    def test_complete_empty_text_rejected(self) -> None:
        _fund(self.sheet, 500)
        result = run_profile_recording_offer(self.offer, self.persona)
        profile = RecordedProfile.objects.get(pk=result.object_pk)
        with self.assertRaises(RecordedProfileError):
            complete_recorded_profile(profile, "   ")


class DisplayDescriptionFallbackTests(TestCase):
    """The display-desc chain reads additional_desc now (#2632 rewire)."""

    def test_roster_description_shows_additional_desc(self) -> None:
        from world.character_sheets.services import set_physical_description

        persona = PersonaFactory()
        sheet = persona.character_sheet
        set_physical_description(sheet, "A weathered traveler.")
        self.assertEqual(
            sheet.character.item_data.get_display_description(), "A weathered traveler."
        )
