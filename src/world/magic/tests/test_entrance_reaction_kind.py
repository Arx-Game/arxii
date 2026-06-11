"""Make an Entrance as a reaction-window kind (#904 first consumer)."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from world.magic.factories import CharacterResonanceFactory
from world.magic.models import SceneEntryEndorsement
from world.scenes.constants import PoseKind, ReactionWindowKind, ScenePrivacyMode
from world.scenes.factories import InteractionFactory, SceneFactory
from world.scenes.reaction_models import WindowReaction
from world.scenes.reaction_services import (
    get_reaction_kind,
    open_reaction_window,
    react_to_window,
)
from world.scenes.tests.test_reaction_windows import make_participant


class EntranceReactionKindTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        cls.entrant = make_participant(cls.scene)
        cls.endorser = make_participant(cls.scene)
        cls.claimed = CharacterResonanceFactory(
            character_sheet=cls.entrant.character_sheet,
        )
        cls.entry_pose = InteractionFactory(
            persona=cls.entrant,
            scene=cls.scene,
            pose_kind=PoseKind.ENTRY,
        )

    def setUp(self) -> None:
        self.window = open_reaction_window(
            interaction=self.entry_pose, kind=ReactionWindowKind.ENTRANCE
        )

    def test_choices_are_entrants_claimed_resonances(self) -> None:
        config = get_reaction_kind(ReactionWindowKind.ENTRANCE)
        choices = config.choices_for(self.window)
        assert [c.slug for c in choices] == [str(self.claimed.resonance_id)]
        assert choices[0].label == self.claimed.resonance.name

    def test_reaction_creates_endorsement_and_grants(self) -> None:
        before = self.claimed.lifetime_earned
        reaction = react_to_window(
            window=self.window,
            reactor_persona=self.endorser,
            choice=str(self.claimed.resonance_id),
        )
        assert WindowReaction.objects.filter(pk=reaction.pk).exists()
        endorsement = SceneEntryEndorsement.objects.get(
            endorser_sheet=self.endorser.character_sheet,
            endorsee_sheet=self.entrant.character_sheet,
            scene=self.scene,
        )
        assert endorsement.entry_interaction_id == self.entry_pose.pk
        self.claimed.refresh_from_db()
        assert self.claimed.lifetime_earned > before

    def test_domain_rejection_rolls_back_reaction(self) -> None:
        """A second endorsement of the same entrant in the scene is blocked.

        The endorsement service's one-per-(endorser, endorsee, scene) rule
        fires inside on_reaction; the WindowReaction row must roll back too.
        Achieved here via a second window on a second ENTRY pose by the same
        entrant — same endorser, same scene.
        """
        react_to_window(
            window=self.window,
            reactor_persona=self.endorser,
            choice=str(self.claimed.resonance_id),
        )
        second_pose = InteractionFactory(
            persona=self.entrant,
            scene=self.scene,
            pose_kind=PoseKind.ENTRY,
        )
        second_window = open_reaction_window(
            interaction=second_pose, kind=ReactionWindowKind.ENTRANCE
        )
        with self.assertRaises(ValidationError):
            react_to_window(
                window=second_window,
                reactor_persona=self.endorser,
                choice=str(self.claimed.resonance_id),
            )
        assert WindowReaction.objects.filter(window=second_window).count() == 0
