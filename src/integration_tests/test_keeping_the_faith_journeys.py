"""Journeys for the commands ledger (#3657, tranche 16): the worship group. An officiant
conducts a ceremony; a convert answers a conversion rite; a character prays and staff
answer with a vision; a would-be vower asks the Sphinx of Black Quartz. Each types what
the person types through the real command handler and asserts what they were told and
what the rows now hold."""

from __future__ import annotations

from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.ceremonies.constants import CeremonyStatus, CeremonyTypeKey, ConversionOfferStatus
from world.ceremonies.factories import CeremonyTypeFactory
from world.ceremonies.models import Ceremony, WorshipConversionOffer
from world.covenants.factories import CovenantRoleFactory, CovenantRoleTechniqueSpecialtyFactory
from world.items.factories import ItemInstanceFactory
from world.items.models import ItemInstance
from world.magic.constants import TechniqueFunction
from world.magic.factories import (
    CharacterGiftFactory,
    CharacterTechniqueFactory,
    TechniqueFactory,
    TechniqueFunctionTagFactory,
)
from world.societies.models import LegendEntry
from world.vitals.constants import CharacterLifeState
from world.vitals.factories import CharacterVitalsFactory
from world.worship.constants import RiteTier
from world.worship.factories import (
    RiteKindFactory,
    ShrineDetailsFactory,
    WorshipDeclarationFactory,
    WorshippedBeingFactory,
    WorshipRiteFactory,
)
from world.worship.models import Prayer, Vision, WorshipDeclaration, WorshippedBeing


def staff(case: JourneyCase, character) -> None:
    """Make ``character``'s account staff, with the Admin permission a staff lock reads."""
    account = case.account_of(character)
    account.is_staff = True
    account.save(update_fields=["is_staff"])
    account.permissions.add("Admin")


def carried(character, name: str, *, value: int = 20) -> ItemInstance:
    """An item called ``name`` in ``character``'s hands."""
    obj = ObjectDBFactory(db_key=name, db_typeclass_path="typeclasses.objects.Object")
    obj.db_location = character
    obj.save(update_fields=["db_location"])
    return ItemInstanceFactory(
        template__name=name,
        template__value=value,
        game_object=obj,
        holder_character_sheet=character.sheet_data,
    )


def worships(character, being: WorshippedBeing) -> WorshipDeclaration:
    """``character`` publicly worships ``being``."""
    return WorshipDeclarationFactory(character_sheet=character.sheet_data, public_being=being)


def pool_of(being: WorshippedBeing) -> int:
    return WorshippedBeing.objects.get(pk=being.pk).resonance_pool


class ConductingACeremony(JourneyCase):
    """Ysmay, who worships the Shepherd, officiates in the chapel; Hobb and Marrow stand
    with her; Wat lies dead. Every ceremony type the telnet verb opens is typed."""

    def setUp(self) -> None:
        super().setUp()
        self.chapel = self.make_room("The Chapel")
        RoomProfileFactory(objectdb=self.chapel)
        self.ysmay = self.make_player("Ysmay", room=self.chapel)
        self.hobb = self.make_player("Hobb", room=self.chapel)
        self.marrow = self.make_player("Marrow", room=self.chapel)
        self.wat = self.make_player("Wat", room=self.make_room("The Crypt"))
        CharacterVitalsFactory(
            character_sheet=self.wat.sheet_data, life_state=CharacterLifeState.DEAD
        )
        self.shepherd = WorshippedBeingFactory(name="The Shepherd")
        self.tide = WorshippedBeingFactory(name="The Tide")
        worships(self.ysmay, self.shepherd)
        for key, name in (
            (CeremonyTypeKey.FUNERAL, "Funeral"),
            (CeremonyTypeKey.BLESSING, "Blessing"),
            (CeremonyTypeKey.SERMON, "Sermon"),
            (CeremonyTypeKey.RITE, "Rite"),
        ):
            CeremonyTypeFactory(key=key, name=name)
        perilous = RiteKindFactory(name="Perilous", tier=RiteTier.PERILOUS)
        self.walk_of_ash = WorshipRiteFactory(
            being=self.shepherd, kind=perilous, name="The Walk of Ash"
        )
        WorshipRiteFactory(being=self.tide, kind=perilous, name="The Tide Hymn")
        WorshipRiteFactory(
            being=self.shepherd,
            kind=RiteKindFactory(name="Devotional", tier=RiteTier.DEVOTIONAL),
            name="The Morning Vigil",
        )

    def _open(self) -> Ceremony:
        return Ceremony.objects.get(status=CeremonyStatus.OPEN)

    def test_a_blessing_with_an_offering_and_a_speech_is_concluded(self) -> None:
        self.assertIn("No ceremony is underway here.", self.telnet(self.ysmay, "ceremony"))
        self.assertIn(
            "Usage: ceremony/<funeral | blessing | sermon | conversion | rite | offering | "
            "speech | finish | abandon>",
            self.telnet(self.ysmay, "ceremony banquet"),
        )
        self.assertIn(
            "No ceremony is underway here.", self.telnet(self.ysmay, "ceremony/offering chalice")
        )
        self.assertIn(
            "Hobb still lives; the rite of passing is not theirs.",
            self.telnet(self.ysmay, "ceremony/funeral Hobb"),
        )
        self.assertIn(
            "A funeral needs at least one deceased to honor.",
            self.telnet(self.ysmay, "ceremony/funeral"),
        )
        self.assertIn(
            "No character 'Nobody' found.", self.telnet(self.ysmay, "ceremony/blessing Nobody")
        )
        self.assertIn(
            "No worshipped being 'The Void' is known.",
            self.telnet(self.ysmay, "ceremony/blessing Hobb=The Void"),
        )
        # Marrow worships nobody publicly, so a rite of his must name its being.
        self.assertIn(
            "You must name the being this rite is for",
            self.telnet(self.marrow, "ceremony/blessing Hobb"),
        )
        self.assertFalse(Ceremony.objects.exists())

        self.assertIn(
            "You open a blessing in the name of The Shepherd.",
            self.telnet(self.ysmay, "ceremony/blessing Hobb"),
        )
        ceremony = self._open()
        self.assertEqual(ceremony.officiant_id, self.ysmay.sheet_data.primary_persona.pk)
        self.assertEqual(
            [h.honoree_sheet_id for h in ceremony.honorees.all()], [self.hobb.sheet_data.pk]
        )
        shown = self.telnet(self.ysmay, "ceremony")
        self.assertIn("Blessing — in the name of The Shepherd", shown)
        self.assertIn("Officiant: Ysmay", shown)
        self.assertIn("Honoring: Hobb", shown)
        self.assertIn("Offerings: 0", shown)
        self.assertIn("Speeches: 0", shown)
        self.assertIn(
            "A ceremony is already underway here.",
            self.telnet(self.marrow, "ceremony/sermon=The Tide"),
        )

        # Only the officiant directs it.
        self.assertIn(
            "Only the officiant may direct the ceremony.",
            self.telnet(self.hobb, "ceremony/speech Marrow"),
        )
        self.assertIn(
            "Only the officiant or staff may abandon the ceremony.",
            self.telnet(self.hobb, "ceremony/abandon"),
        )

        # The offering: an item in her hands is consumed and feeds the being's pool.
        chalice = carried(self.ysmay, "golden chalice", value=20)
        pool_before = pool_of(self.shepherd)
        self.assertIn("Offer what?", self.telnet(self.ysmay, "ceremony/offering"))
        self.assertIn(
            "No offering 'candle' is within reach.",
            self.telnet(self.ysmay, "ceremony/offering candle"),
        )
        self.assertIn(
            "The offering is consumed: golden chalice.",
            self.telnet(self.ysmay, "ceremony/offering golden chalice"),
        )
        self.assertIsNotNone(ItemInstance.objects.get(pk=chalice.pk).destroyed_at)
        self.assertGreater(pool_of(self.shepherd), pool_before)
        self.assertEqual(ceremony.offerings.count(), 1)

        # The speech.
        self.assertIn("Recognize whom?", self.telnet(self.ysmay, "ceremony/speech"))
        self.assertIn(
            "No character 'Nobody' found.", self.telnet(self.ysmay, "ceremony/speech Nobody")
        )
        self.assertIn(
            "'Ysmay' is not honored by this rite.",
            self.telnet(self.ysmay, "ceremony/speech Marrow=Ysmay"),
        )
        self.assertIn(
            "Marrow is recognized before the gathering.",
            self.telnet(self.ysmay, "ceremony/speech Marrow=Hobb"),
        )
        speech = ceremony.speeches.get()
        self.assertEqual(speech.speaker_id, self.marrow.sheet_data.primary_persona.pk)
        self.assertEqual(speech.target_honoree.honoree_sheet_id, self.hobb.sheet_data.pk)
        shown = self.telnet(self.ysmay, "ceremony")
        self.assertIn("Offerings: 1", shown)
        self.assertIn("Speeches: 1", shown)

        # The conclusion tallies Hobb's honor as a deed.
        self.assertIn(
            "The rite concludes; its honors are spoken and recorded.",
            self.telnet(self.ysmay, "ceremony/finish"),
        )
        ceremony = Ceremony.objects.get(pk=ceremony.pk)
        self.assertEqual(ceremony.status, CeremonyStatus.COMPLETED)
        self.assertGreater(ceremony.honorees.get().prestige_awarded, 0)
        self.assertTrue(
            LegendEntry.objects.filter(
                persona=self.hobb.sheet_data.primary_persona,
                title="Honored at a blessing PLACEHOLDER",
            ).exists()
        )
        self.assertIn("No ceremony is underway here.", self.telnet(self.ysmay, "ceremony/finish"))
        self.assertIn("No ceremony is underway here.", self.telnet(self.ysmay, "ceremony"))

    def test_a_funeral_a_sermon_abandoned_by_staff_and_a_tier_three_rite(self) -> None:
        staff(self, self.marrow)
        self.assertIn(
            "You open a funeral in the name of The Shepherd.",
            self.telnet(self.ysmay, "ceremony/funeral Wat"),
        )
        shown = self.telnet(self.hobb, "ceremony")
        self.assertIn("Funeral — in the name of The Shepherd", shown)
        self.assertIn("Honoring: Wat", shown)
        self.assertIn("The rite is left unfinished.", self.telnet(self.ysmay, "ceremony/abandon"))
        self.assertEqual(Ceremony.objects.get().status, CeremonyStatus.ABANDONED)

        # The space form opens a sermon with nobody honored; staff may abandon it.
        self.assertIn(
            "You open a sermon in the name of The Shepherd.",
            self.telnet(self.ysmay, "ceremony sermon"),
        )
        self.assertEqual(self._open().honorees.count(), 0)
        self.assertIn("The rite is left unfinished.", self.telnet(self.marrow, "ceremony/abandon"))

        # A tier 3 rite is a ceremony; a lesser rite and another being's are refused.
        self.assertIn(
            "Name the rite this ceremony performs.", self.telnet(self.ysmay, "ceremony/rite")
        )
        self.assertIn(
            "No rite 'Nothing' is known.", self.telnet(self.ysmay, "ceremony/rite Nothing")
        )
        self.assertIn(
            "That rite is a scene act, not a ceremony; perform it where you stand.",
            self.telnet(self.ysmay, "ceremony/rite The Morning Vigil"),
        )
        self.assertIn(
            "That rite is not one of this being's.",
            self.telnet(self.ysmay, "ceremony/rite The Tide Hymn"),
        )
        self.assertIn(
            "No rite 'The Walk of Ash' is known.",
            self.telnet(self.ysmay, "ceremony/rite The Walk of Ash=The Tide"),
        )
        self.assertIn(
            "You open The Walk of Ash in the name of The Shepherd.",
            self.telnet(self.ysmay, "ceremony/rite The Walk of Ash,Hobb"),
        )
        rite = self._open()
        self.assertEqual(rite.worship_rite_id, self.walk_of_ash.pk)
        self.assertEqual(rite.honorees.get().honoree_sheet_id, self.hobb.sheet_data.pk)
        self.assertIn("Rite — in the name of The Shepherd", self.telnet(self.ysmay, "ceremony"))
        self.assertIn("The rite is left unfinished.", self.telnet(self.ysmay, "ceremony/abandon"))


class AnsweringAConversion(JourneyCase):
    """Ysmay opens a conversion rite for Hobb, who answers it from his own inbox; Marrow
    is nobody's convert. A conversion of her own needs no answer."""

    def setUp(self) -> None:
        super().setUp()
        self.chapel = self.make_room("The Chapel")
        RoomProfileFactory(objectdb=self.chapel)
        self.ysmay = self.make_player("Ysmay", room=self.chapel)
        self.hobb = self.make_player("Hobb", room=self.chapel)
        self.marrow = self.make_player("Marrow", room=self.chapel)
        self.shepherd = WorshippedBeingFactory(name="The Shepherd")
        self.tide = WorshippedBeingFactory(name="The Tide")
        worships(self.ysmay, self.shepherd)
        CeremonyTypeFactory(key=CeremonyTypeKey.CONVERSION, name="Conversion")

    def _offer(self) -> WorshipConversionOffer:
        return WorshipConversionOffer.objects.get()

    def _open_for_hobb(self) -> WorshipConversionOffer:
        self.assertIn(
            "A conversion rite has exactly one convert.",
            self.telnet(self.ysmay, "ceremony/conversion"),
        )
        self.assertIn(
            "A conversion rite has exactly one convert.",
            self.telnet(self.ysmay, "ceremony/conversion Hobb,Marrow"),
        )
        self.assertIn(
            "You open a conversion in the name of The Shepherd.",
            self.telnet(self.ysmay, "ceremony/conversion Hobb"),
        )
        offer = self._offer()
        self.assertEqual(offer.status, ConversionOfferStatus.PENDING)
        return offer

    def test_the_convert_accepts_and_the_rite_converts_him(self) -> None:
        self.assertIn(
            "No conversion rite is waiting on your answer.", self.telnet(self.hobb, "conversion")
        )
        offer = self._open_for_hobb()
        listing = self.telnet(self.hobb, "conversion")
        self.assertIn("Pending conversion offers:", listing)
        self.assertIn(f"  [{offer.pk}] Hobb, called to The Shepherd at The Chapel", listing)
        self.assertIn(f"[{offer.pk}]", self.telnet(self.hobb, "conversion offers"))
        self.assertIn(
            "No conversion rite is waiting on your answer.",
            self.telnet(self.marrow, "conversion"),
        )
        self.assertIn("Usage: conversion [offers", self.telnet(self.hobb, "conversion banquet"))
        self.assertIn("Usage: conversion accept <id>", self.telnet(self.hobb, "conversion accept"))
        self.assertIn(
            "That's not a valid offer id.", self.telnet(self.hobb, "conversion decline soon")
        )
        self.assertIn(
            "Which offer? Provide an offer id.",
            self.telnet(self.hobb, "conversion accept 999999"),
        )
        self.assertIn(
            "That isn't your character to answer for.",
            self.telnet(self.marrow, f"conversion accept {offer.pk}"),
        )
        self.assertEqual(self._offer().status, ConversionOfferStatus.PENDING)

        self.assertIn(
            "You accept the offered conversion.",
            self.telnet(self.hobb, f"conversion accept {offer.pk}"),
        )
        offer = self._offer()
        self.assertEqual(offer.status, ConversionOfferStatus.ACCEPTED)
        self.assertTrue(offer.is_sincere)
        self.assertIn(
            "That offer has already been answered.",
            self.telnet(self.hobb, f"conversion accept {offer.pk}"),
        )
        self.assertIn(
            "No conversion rite is waiting on your answer.", self.telnet(self.hobb, "conversion")
        )
        # Hobb's worship is repointed only when the rite concludes.
        self.assertFalse(WorshipDeclaration.objects.filter(character_sheet=self.hobb.sheet_data))
        self.assertIn(
            "The rite concludes; its honors are spoken and recorded.",
            self.telnet(self.ysmay, "ceremony/finish"),
        )
        declaration = WorshipDeclaration.objects.get(character_sheet=self.hobb.sheet_data)
        self.assertEqual(declaration.public_being_id, self.shepherd.pk)
        self.assertTrue(
            LegendEntry.objects.filter(
                persona=self.hobb.sheet_data.primary_persona,
                title="Converted to The Shepherd PLACEHOLDER",
            ).exists()
        )

    def test_the_convert_declines_and_a_closed_rite_takes_no_answer(self) -> None:
        offer = self._open_for_hobb()
        self.assertIn(
            "You decline the offered conversion.",
            self.telnet(self.hobb, f"conversion decline {offer.pk}"),
        )
        self.assertEqual(self._offer().status, ConversionOfferStatus.DECLINED)
        self.assertIsNone(self._offer().is_sincere)
        self.assertIn(
            "That offer has already been answered.",
            self.telnet(self.hobb, f"conversion accept {offer.pk}"),
        )
        self.assertIn(
            "The rite concludes; its honors are spoken and recorded.",
            self.telnet(self.ysmay, "ceremony/finish"),
        )
        self.assertFalse(WorshipDeclaration.objects.filter(character_sheet=self.hobb.sheet_data))
        self.assertFalse(LegendEntry.objects.filter(persona=self.hobb.sheet_data.primary_persona))

        # A second rite, abandoned before he answers: the inbox no longer lists it.
        self.telnet(self.ysmay, "ceremony/conversion Hobb")
        pending = WorshipConversionOffer.objects.get(status=ConversionOfferStatus.PENDING)
        self.assertIn(f"[{pending.pk}]", self.telnet(self.hobb, "conversion"))
        self.assertIn("The rite is left unfinished.", self.telnet(self.ysmay, "ceremony/abandon"))
        self.assertIn(
            "That conversion rite has already closed.",
            self.telnet(self.hobb, f"conversion accept {pending.pk}"),
        )
        self.assertIn(
            "No conversion rite is waiting on your answer.", self.telnet(self.hobb, "conversion")
        )

    def test_her_own_conversion_needs_no_answer(self) -> None:
        self.assertIn(
            "You open a conversion in the name of The Tide.",
            self.telnet(self.ysmay, "ceremony/conversion Ysmay=The Tide"),
        )
        self.assertFalse(WorshipConversionOffer.objects.exists())
        self.assertIn(
            "No conversion rite is waiting on your answer.", self.telnet(self.ysmay, "conversion")
        )
        self.assertIn(
            "The rite concludes; its honors are spoken and recorded.",
            self.telnet(self.ysmay, "ceremony/finish"),
        )
        declaration = WorshipDeclaration.objects.get(character_sheet=self.ysmay.sheet_data)
        self.assertEqual(declaration.public_being_id, self.tide.pk)


class PrayingAndTheVision(JourneyCase):
    """Ysmay prays at the Shepherd's shrine and Hobb from the gallery; Marrow, staff,
    answers Hobb with a vision."""

    def setUp(self) -> None:
        super().setUp()
        self.chapel = self.make_room("The Chapel")
        chapel_profile = RoomProfileFactory(objectdb=self.chapel)
        self.gallery = self.make_room("The Gallery")
        RoomProfileFactory(objectdb=self.gallery)
        self.ysmay = self.make_player("Ysmay", room=self.chapel)
        self.hobb = self.make_player("Hobb", room=self.gallery)
        self.marrow = self.make_player("Marrow", room=self.gallery)
        staff(self, self.marrow)
        self.shepherd = WorshippedBeingFactory(name="The Shepherd", resonance_pool=0)
        ShrineDetailsFactory(feature_instance__room_profile=chapel_profile, being=self.shepherd)

    def test_prayers_at_the_shrine_and_away_from_it(self) -> None:
        usage = "Usage: pray <being>=<your words>"
        self.assertIn(usage, self.telnet(self.ysmay, "pray"))
        self.assertIn(usage, self.telnet(self.ysmay, "pray The Shepherd"))
        self.assertIn(usage, self.telnet(self.ysmay, "pray The Shepherd="))
        self.assertIn(
            "No being 'The Void' is known.", self.telnet(self.ysmay, "pray The Void=hear me")
        )
        self.assertFalse(Prayer.objects.exists())

        told = self.telnet(self.ysmay, "pray The Shepherd=keep us whole")
        self.assertIn("You pray to The Shepherd.", told)
        self.assertIn("An act of devotion: +1 favor.", told)
        prayer = Prayer.objects.get()
        self.assertEqual(prayer.text, "keep us whole")
        self.assertEqual(prayer.room_profile_id, self.chapel.pk)
        self.assertEqual(prayer.devotion_granted, 1)

        # The week's devotion is paid once.
        told = self.telnet(self.ysmay, "pray The Shepherd=and keep us still")
        self.assertIn("You pray to The Shepherd.", told)
        self.assertNotIn("devotion", told)
        self.assertEqual(Prayer.objects.filter(character_sheet=self.ysmay.sheet_data).count(), 2)
        self.assertIn(
            "That prayer is too long.",
            self.telnet(self.ysmay, "pray The Shepherd=" + "o" * 2001),
        )

        # Away from any holy site a prayer is heard and pays nothing.
        told = self.telnet(self.hobb, "pray The Shepherd=a word from the gallery")
        self.assertIn("You pray to The Shepherd.", told)
        self.assertNotIn("devotion", told)
        self.assertEqual(
            Prayer.objects.get(character_sheet=self.hobb.sheet_data).devotion_granted, 0
        )

    def test_staff_answer_a_prayer_with_a_vision(self) -> None:
        self.telnet(self.hobb, "pray The Shepherd=show me the road")
        hobbs_prayer = Prayer.objects.get(character_sheet=self.hobb.sheet_data)
        self.telnet(self.ysmay, "pray The Shepherd=keep us whole")
        ysmays_prayer = Prayer.objects.get(character_sheet=self.ysmay.sheet_data)

        self.assertIn(
            "Command 'vision Hobb/The Shepherd=A door opens.' is not available.",
            self.telnet(self.ysmay, "vision Hobb/The Shepherd=A door opens."),
        )
        usage = "Usage: vision[/reveal] <character>/<being>=<prose>"
        self.assertIn(usage, self.telnet(self.marrow, "vision"))
        self.assertIn(usage, self.telnet(self.marrow, "vision Hobb=A door opens."))
        self.assertIn(
            "Usage: vision/prayer <id> <character>/<being>=<prose>",
            self.telnet(self.marrow, "vision/prayer soon Hobb/The Shepherd=A door opens."),
        )
        self.assertIn(
            "No character 'Nobody' is known.",
            self.telnet(self.marrow, "vision Nobody/The Shepherd=A door opens."),
        )
        self.assertIn(
            "No being 'The Void' is known.",
            self.telnet(self.marrow, "vision Hobb/The Void=A door opens."),
        )
        self.assertIn(
            "A vision needs its prose.", self.telnet(self.marrow, "vision Hobb/The Shepherd=")
        )
        self.assertIn(
            "That being's pool cannot pay for a vision.",
            self.telnet(self.marrow, "vision Hobb/The Shepherd=A door opens."),
        )
        self.assertFalse(Vision.objects.exists())

        self.shepherd.resonance_pool = 100
        self.shepherd.save(update_fields=["resonance_pool"])
        self.assertIn(
            "A vision from The Shepherd reaches Hobb.",
            self.telnet(self.marrow, "vision Hobb/The Shepherd=A door opens."),
        )
        vision = Vision.objects.get()
        self.assertEqual(vision.recipient_id, self.hobb.sheet_data.pk)
        self.assertEqual(vision.body, "A door opens.")
        self.assertFalse(vision.reveal_source)
        self.assertEqual(vision.message.body, "A door opens.")
        self.assertEqual(vision.message.category, "visions")
        self.assertEqual(pool_of(self.shepherd), 90)

        self.assertIn(
            "A vision from The Shepherd reaches Hobb.",
            self.telnet(self.marrow, "vision/reveal Hobb/The Shepherd=The road bends."),
        )
        revealed = Vision.objects.get(body="The road bends.")
        self.assertTrue(revealed.reveal_source)
        self.assertEqual(
            revealed.message.body,
            "The road bends.\n\nYou know whose vision this is: The Shepherd.",
        )

        self.assertIn(
            "That prayer was not this character's.",
            self.telnet(
                self.marrow, f"vision/prayer {ysmays_prayer.pk} Hobb/The Shepherd=Not yours."
            ),
        )
        self.assertIn(
            "No prayer with id 999999.",
            self.telnet(self.marrow, "vision/prayer 999999 Hobb/The Shepherd=Nobody's."),
        )
        self.assertIn(
            "A vision from The Shepherd reaches Hobb.",
            self.telnet(
                self.marrow, f"vision/prayer {hobbs_prayer.pk} Hobb/The Shepherd=The road is east."
            ),
        )
        self.assertEqual(Vision.objects.get(body="The road is east.").prayer_id, hobbs_prayer.pk)
        self.assertEqual(pool_of(self.shepherd), 70)


class AskingTheSphinx(JourneyCase):
    """Ysmay asks the Sphinx of Black Quartz whether a vow would take on her."""

    def setUp(self) -> None:
        super().setUp()
        self.academy = self.make_room("The Shroudwatch Academy")
        self.ysmay = self.make_player("Ysmay", room=self.academy)
        self.sheet = self.ysmay.sheet_data

    def test_the_sphinx_judges_three_vows(self) -> None:
        self.assertIn("Usage: sphinx <vow name>", self.telnet(self.ysmay, "sphinx"))
        self.assertIn(
            "The Sphinx does not know of a vow named 'Nonexistent Vow'.",
            self.telnet(self.ysmay, "sphinx Nonexistent Vow"),
        )

        # Every demand answered: the vow takes.
        sundering = CovenantRoleFactory(name="Sundering Vow")
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=sundering, function=TechniqueFunction.WEAKEN
        )
        blow = TechniqueFactory(name="Sundering Blow")
        TechniqueFunctionTagFactory(technique=blow, function=TechniqueFunction.WEAKEN)
        CharacterTechniqueFactory(character=self.sheet, technique=blow)
        told = self.telnet(self.ysmay, "sphinx sundering vow")
        self.assertIn("Sphinx of Black Quartz, judge my vow: Sundering Vow.", told)
        self.assertIn("The vow will take.", told)
        self.assertIn("Answered by: Sundering Blow.", told)

        # One demand of two answered: dormant in places.
        half = CovenantRoleFactory(name="Half Answered Vow")
        CovenantRoleTechniqueSpecialtyFactory(covenant_role=half, function=TechniqueFunction.WEAKEN)
        CovenantRoleTechniqueSpecialtyFactory(covenant_role=half, function=TechniqueFunction.CHARM)
        told = self.telnet(self.ysmay, "sphinx Half Answered Vow")
        self.assertIn("The vow would lie dormant in places:", told)
        self.assertIn("unanswered.", told)
        self.assertNotIn("Seek:", told)

        # Nothing answered, and a technique of a gift she holds would: the Sphinx names it.
        unready = CovenantRoleFactory(name="Unready Vow")
        CovenantRoleTechniqueSpecialtyFactory(
            covenant_role=unready, function=TechniqueFunction.BARRIER
        )
        ward = TechniqueFactory(name="Ward of Black Quartz")
        TechniqueFunctionTagFactory(technique=ward, function=TechniqueFunction.BARRIER)
        CharacterGiftFactory(character=self.sheet, gift=ward.gift)
        told = self.telnet(self.ysmay, "sphinx Unready Vow")
        self.assertIn("The vow will not take. Yet.", told)
        self.assertIn("unanswered.", told)
        self.assertIn("Seek:", told)
        self.assertIn("Ward of Black Quartz", told)
