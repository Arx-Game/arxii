from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import GainSource
from world.magic.exceptions import DramaticMomentCapExceeded, EndorsementValidationError
from world.magic.factories import (
    CharacterResonanceFactory,
    DramaticMomentTagFactory,
    DramaticMomentTypeFactory,
    ResonanceFactory,
)
from world.magic.models import CharacterResonance, ResonanceGrant
from world.magic.models.dramatic_moment import DramaticMomentTag
from world.magic.services.gain import create_dramatic_moment_tag
from world.scenes.factories import SceneFactory
from world.societies.models import PhilosophicalArchetype


class DramaticMomentTypeModelTest(TestCase):
    def test_create(self):
        dmt = DramaticMomentTypeFactory(label="Grand Entrance", resonance_amount=15)
        self.assertEqual(dmt.label, "Grand Entrance")
        self.assertEqual(dmt.resonance_amount, 15)
        self.assertIsNotNone(dmt.resonance_id)

    def test_str(self):
        dmt = DramaticMomentTypeFactory(label="Grand Entrance")
        self.assertEqual(str(dmt), "Grand Entrance")


class DramaticMomentTagModelTest(TestCase):
    def test_create(self):
        tag = DramaticMomentTagFactory()
        self.assertIsInstance(tag, DramaticMomentTag)
        self.assertIsNotNone(tag.moment_type_id)
        self.assertIsNotNone(tag.character_sheet_id)
        self.assertIsNotNone(tag.tagged_by_id)
        self.assertIsNotNone(tag.tagged_at)

    def test_str(self):
        tag = DramaticMomentTagFactory()
        self.assertIn("DramaticMomentTag", str(tag))

    def test_tag_can_anchor_to_interaction(self):
        from world.scenes.factories import InteractionFactory, SceneFactory

        scene = SceneFactory()
        interaction = InteractionFactory(scene=scene)
        tag = DramaticMomentTagFactory(
            scene=scene,
            interaction=interaction,
            interaction_timestamp=interaction.timestamp,
        )
        self.assertEqual(tag.interaction_id, interaction.id)
        self.assertEqual(tag.interaction_timestamp, interaction.timestamp)
        # Back-relation resolves.
        self.assertIn(tag, list(interaction.dramatic_moment_tags.all()))


class CreateDramaticMomentTagServiceTest(TestCase):
    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=0,
            lifetime_earned=0,
        )
        self.moment_type = DramaticMomentTypeFactory(
            resonance=self.resonance,
            resonance_amount=15,
        )
        self.tagger = AccountFactory()

    def test_creates_dramatic_moment_tag(self):
        tag = create_dramatic_moment_tag(
            character_sheet=self.sheet,
            moment_type=self.moment_type,
            tagged_by=self.tagger,
            scene=None,
        )
        self.assertIsInstance(tag, DramaticMomentTag)
        self.assertEqual(tag.character_sheet, self.sheet)
        self.assertEqual(tag.moment_type, self.moment_type)
        self.assertEqual(tag.tagged_by, self.tagger)

    def test_grants_resonance_from_moment_type(self):
        create_dramatic_moment_tag(
            character_sheet=self.sheet,
            moment_type=self.moment_type,
            tagged_by=self.tagger,
            scene=None,
        )
        cr = CharacterResonance.objects.get(character_sheet=self.sheet, resonance=self.resonance)
        self.assertEqual(cr.balance, 15)

    def test_writes_grant_ledger_row(self):
        create_dramatic_moment_tag(
            character_sheet=self.sheet,
            moment_type=self.moment_type,
            tagged_by=self.tagger,
            scene=None,
        )
        grant = ResonanceGrant.objects.get(source=GainSource.DRAMATIC_MOMENT)
        self.assertEqual(grant.amount, 15)

    def test_fires_renown_award_when_persona_exists(self):
        # CharacterSheetFactory creates a PRIMARY persona via post_generation,
        # so fire_renown_award should be called once.
        with patch("world.societies.renown.fire_renown_award") as mock_award:
            create_dramatic_moment_tag(
                character_sheet=self.sheet,
                moment_type=self.moment_type,
                tagged_by=self.tagger,
                scene=None,
            )
            mock_award.assert_called_once()

    def test_character_must_have_claimed_resonance(self):
        other_resonance = ResonanceFactory()
        other_type = DramaticMomentTypeFactory(resonance=other_resonance)
        with self.assertRaises(EndorsementValidationError):
            create_dramatic_moment_tag(
                character_sheet=self.sheet,
                moment_type=other_type,
                tagged_by=self.tagger,
                scene=None,
            )

    def test_persists_interaction_and_denormalized_timestamp(self):
        from world.magic.services.gain import create_dramatic_moment_tag
        from world.scenes.factories import InteractionFactory, SceneFactory

        scene = SceneFactory()
        interaction = InteractionFactory(scene=scene)
        tag = create_dramatic_moment_tag(
            character_sheet=self.sheet,
            moment_type=self.moment_type,
            tagged_by=self.tagger,
            scene=scene,
            interaction=interaction,
        )
        self.assertEqual(tag.interaction_id, interaction.id)
        self.assertEqual(tag.interaction_timestamp, interaction.timestamp)


class DramaticMomentCapTest(TestCase):
    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=0,
            lifetime_earned=0,
        )
        self.moment_type = DramaticMomentTypeFactory(
            resonance=self.resonance,
            resonance_amount=5,
            per_scene_cap=1,
        )
        self.tagger = AccountFactory()
        self.scene = SceneFactory()

    def test_cap_blocks_when_limit_reached(self):
        create_dramatic_moment_tag(
            character_sheet=self.sheet,
            moment_type=self.moment_type,
            tagged_by=self.tagger,
            scene=self.scene,
        )
        with self.assertRaises(DramaticMomentCapExceeded):
            create_dramatic_moment_tag(
                character_sheet=self.sheet,
                moment_type=self.moment_type,
                tagged_by=self.tagger,
                scene=self.scene,
            )

    def test_cap_independent_per_sheet(self):
        other_sheet = CharacterSheetFactory()
        CharacterResonanceFactory(
            character_sheet=other_sheet,
            resonance=self.resonance,
            balance=0,
            lifetime_earned=0,
        )
        create_dramatic_moment_tag(
            character_sheet=self.sheet,
            moment_type=self.moment_type,
            tagged_by=self.tagger,
            scene=self.scene,
        )
        # Different sheet in same scene — cap is independent, should not raise
        create_dramatic_moment_tag(
            character_sheet=other_sheet,
            moment_type=self.moment_type,
            tagged_by=self.tagger,
            scene=self.scene,
        )

    def test_cap_independent_per_scene(self):
        other_scene = SceneFactory()
        create_dramatic_moment_tag(
            character_sheet=self.sheet,
            moment_type=self.moment_type,
            tagged_by=self.tagger,
            scene=self.scene,
        )
        # Same sheet, different scene — cap is independent, should not raise
        create_dramatic_moment_tag(
            character_sheet=self.sheet,
            moment_type=self.moment_type,
            tagged_by=self.tagger,
            scene=other_scene,
        )


class DramaticMomentArchetypesTest(TestCase):
    def setUp(self):
        self.sheet = CharacterSheetFactory()
        self.resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=self.resonance,
            balance=0,
            lifetime_earned=0,
        )
        self.moment_type = DramaticMomentTypeFactory(
            resonance=self.resonance,
            resonance_amount=10,
        )
        self.tagger = AccountFactory()

    def test_archetypes_passed_to_renown_award(self):
        archetype = PhilosophicalArchetype.objects.create(name="Heroic-Test")
        self.moment_type.archetypes.add(archetype)
        with patch("world.societies.renown.fire_renown_award") as mock_award:
            create_dramatic_moment_tag(
                character_sheet=self.sheet,
                moment_type=self.moment_type,
                tagged_by=self.tagger,
                scene=None,
            )
            call_kwargs = mock_award.call_args[1]
            self.assertIn(archetype, call_kwargs["archetypes"])
