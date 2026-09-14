"""Direct-mutation regression for ``Interaction.cached_endorsements`` (#3816, Defect B).

``create_pose_endorsement`` mutates ``interaction.cached_endorsements`` directly at
its write site rather than relying on a later Prefetch to pick up the new row, so a
warm cache reflects the new endorsement with no extra query.
"""

from django.test import TestCase

from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
from world.magic.models import PoseEndorsement
from world.magic.services.gain import account_for_sheet, create_pose_endorsement
from world.roster.factories import RosterTenureFactory
from world.scenes.factories import InteractionFactory, SceneFactory, SceneParticipationFactory


class EndorsementCachedPropertyTests(TestCase):
    """``cached_endorsements`` reflects a write-site mutation without a requery.

    ``setUp`` (not ``setUpTestData``) deliberately builds a fresh ``Interaction`` and
    ``CharacterSheet`` per test: these are idmapper ``SharedMemoryModel`` rows, so a
    shared class-level instance mutated by ``create_pose_endorsement`` in one test
    would carry a warmed (and, post-rollback, zombie-pk'd) ``cached_endorsements``
    list into the next test rather than resetting with the transaction.
    """

    def setUp(self) -> None:
        endorser_tenure = RosterTenureFactory()
        self.endorser_sheet = endorser_tenure.roster_entry.character_sheet
        endorsee_tenure = RosterTenureFactory()
        endorsee_sheet = endorsee_tenure.roster_entry.character_sheet

        self.scene = SceneFactory()
        endorser_account = account_for_sheet(self.endorser_sheet)
        SceneParticipationFactory(scene=self.scene, account=endorser_account)

        # CharacterSheetFactory already creates a PRIMARY persona (post_generation hook).
        endorsee_persona = endorsee_sheet.primary_persona
        self.resonance = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=endorsee_sheet, resonance=self.resonance)

        self.interaction = InteractionFactory(scene=self.scene, persona=endorsee_persona)

    def test_create_endorsement_updates_cache_without_requery(self) -> None:
        _ = self.interaction.cached_endorsements  # warm the cache to []

        create_pose_endorsement(self.endorser_sheet, self.interaction, self.resonance)

        with self.assertNumQueries(0):
            cached = self.interaction.cached_endorsements

        self.assertEqual(len(cached), 1)
        self.assertIsInstance(cached[0], PoseEndorsement)
        self.assertEqual(cached[0].endorser_sheet, self.endorser_sheet)

    def test_create_endorsement_does_not_mutate_a_cold_cache(self) -> None:
        """A cold cache is left alone -- the next real read recomputes fresh."""
        create_pose_endorsement(self.endorser_sheet, self.interaction, self.resonance)

        self.assertNotIn("cached_endorsements", self.interaction.__dict__)
        self.assertEqual(len(self.interaction.cached_endorsements), 1)
