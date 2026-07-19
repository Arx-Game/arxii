"""Model validation tests for AmbientEmoteLine (#2471)."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.areas.factories import AreaFactory
from world.distinctions.factories import DistinctionFactory
from world.locations.constants import LocationParentType
from world.magic.factories import ResonanceFactory
from world.narrative.constants import AmbientTriggerType
from world.narrative.models import AmbientEmoteLine
from world.societies.constants import FameTier
from world.societies.factories import SocietyFactory
from world.species.factories import SpeciesFactory


class AmbientEmoteLineParentDiscriminatorTests(TestCase):
    def test_room_parent_requires_room_profile(self) -> None:
        line = AmbientEmoteLine(
            parent_type=LocationParentType.ROOM,
            arriver_body="A shadow crosses the doorway.",
        )
        with self.assertRaises(ValidationError):
            line.save()

    def test_area_parent_requires_area(self) -> None:
        line = AmbientEmoteLine(
            parent_type=LocationParentType.AREA,
            arriver_body="The wind carries a strange scent.",
        )
        with self.assertRaises(ValidationError):
            line.save()

    def test_valid_room_line_saves(self) -> None:
        profile = RoomProfileFactory()
        line = AmbientEmoteLine(
            parent_type=LocationParentType.ROOM,
            room_profile=profile,
            arriver_body="Dust motes drift in the light.",
        )
        line.save()
        self.assertIsNotNone(line.pk)


class AmbientEmoteLineTriggerTypeTests(TestCase):
    def setUp(self) -> None:
        self.profile = RoomProfileFactory()

    def _base_kwargs(self, **overrides):
        defaults = {
            "parent_type": LocationParentType.ROOM,
            "room_profile": self.profile,
            "arriver_body": "PLACEHOLDER",
        }
        defaults.update(overrides)
        return defaults

    def test_none_rejects_bystander_body(self) -> None:
        line = AmbientEmoteLine(
            **self._base_kwargs(
                trigger_type=AmbientTriggerType.NONE,
                bystander_body="Everyone notices.",
            )
        )
        with self.assertRaises(ValidationError):
            line.save()

    def test_none_with_only_arriver_body_saves(self) -> None:
        line = AmbientEmoteLine(**self._base_kwargs(trigger_type=AmbientTriggerType.NONE))
        line.save()
        self.assertIsNotNone(line.pk)

    def test_species_requires_trigger_species(self) -> None:
        line = AmbientEmoteLine(
            **self._base_kwargs(
                trigger_type=AmbientTriggerType.SPECIES,
                bystander_body="A murmur runs through the crowd.",
            )
        )
        with self.assertRaises(ValidationError):
            line.save()

    def test_species_with_species_saves(self) -> None:
        species = SpeciesFactory()
        line = AmbientEmoteLine(
            **self._base_kwargs(
                trigger_type=AmbientTriggerType.SPECIES,
                trigger_species=species,
                bystander_body="A murmur runs through the crowd.",
            )
        )
        line.save()
        self.assertIsNotNone(line.pk)

    def test_resonance_min_requires_resonance_and_minimum(self) -> None:
        resonance = ResonanceFactory()
        line = AmbientEmoteLine(
            **self._base_kwargs(
                trigger_type=AmbientTriggerType.RESONANCE_MIN,
                trigger_resonance=resonance,
                bystander_body="The air grows heavy.",
            )
        )
        with self.assertRaises(ValidationError):
            line.save()

    def test_resonance_min_with_both_saves(self) -> None:
        resonance = ResonanceFactory()
        line = AmbientEmoteLine(
            **self._base_kwargs(
                trigger_type=AmbientTriggerType.RESONANCE_MIN,
                trigger_resonance=resonance,
                trigger_minimum_value=50,
                bystander_body="The air grows heavy.",
            )
        )
        line.save()
        self.assertIsNotNone(line.pk)

    def test_distinction_requires_trigger_distinction(self) -> None:
        line = AmbientEmoteLine(
            **self._base_kwargs(
                trigger_type=AmbientTriggerType.DISTINCTION,
                bystander_body="Recognition dawns.",
            )
        )
        with self.assertRaises(ValidationError):
            line.save()

    def test_distinction_with_distinction_saves(self) -> None:
        distinction = DistinctionFactory()
        line = AmbientEmoteLine(
            **self._base_kwargs(
                trigger_type=AmbientTriggerType.DISTINCTION,
                trigger_distinction=distinction,
                bystander_body="Recognition dawns.",
            )
        )
        line.save()
        self.assertIsNotNone(line.pk)

    def test_renown_min_requires_min_fame_tier(self) -> None:
        line = AmbientEmoteLine(
            **self._base_kwargs(
                trigger_type=AmbientTriggerType.RENOWN_MIN,
                bystander_body="Heads turn.",
            )
        )
        with self.assertRaises(ValidationError):
            line.save()

    def test_renown_min_with_tier_and_optional_society_saves(self) -> None:
        society = SocietyFactory()
        line = AmbientEmoteLine(
            **self._base_kwargs(
                trigger_type=AmbientTriggerType.RENOWN_MIN,
                trigger_min_fame_tier=FameTier.CELEBRITY,
                trigger_perceiving_society=society,
                bystander_body="Heads turn.",
            )
        )
        line.save()
        self.assertIsNotNone(line.pk)

    def test_requires_at_least_one_body(self) -> None:
        line = AmbientEmoteLine(
            parent_type=LocationParentType.ROOM,
            room_profile=self.profile,
            trigger_type=AmbientTriggerType.NONE,
        )
        with self.assertRaises(ValidationError):
            line.save()

    def test_area_scoped_line_saves(self) -> None:
        area = AreaFactory()
        line = AmbientEmoteLine(
            parent_type=LocationParentType.AREA,
            area=area,
            trigger_type=AmbientTriggerType.NONE,
            arriver_body="A hush lies over the district.",
        )
        line.save()
        self.assertIsNotNone(line.pk)

    def test_discriminator_and_trigger_type_errors_both_reported(self) -> None:
        """A bad parent_type discriminator AND a bad trigger_type must both surface
        in the same ValidationError, instead of the discriminator error masking the
        trigger-type error (#2471 review finding #2)."""
        line = AmbientEmoteLine(
            parent_type=LocationParentType.ROOM,
            room_profile=None,
            trigger_type=AmbientTriggerType.SPECIES,
            trigger_species=None,
            bystander_body="A murmur runs through the crowd.",
        )
        with self.assertRaises(ValidationError) as ctx:
            line.save()
        message_dict = ctx.exception.message_dict
        self.assertIn("room_profile", message_dict)
        self.assertIn("trigger_species", message_dict)
