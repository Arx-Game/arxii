"""A push warms the shared row's cached properties; later writes must still show (#4508).

``push_interaction`` reads ``cached_reactions``, ``cached_endorsements``,
``cached_reaction_windows``, ``cached_dramatic_moment_tags`` and the author's
``cached_resonances`` on the idmapper-shared row. Each write seam below runs AFTER a
push and the serializer must show the new data on the same instance and on a fresh fetch.
"""

from evennia_extensions.factories import AccountFactory
from world.magic.factories import (
    CharacterResonanceFactory,
    DramaticMomentTypeFactory,
    ResonanceFactory,
)
from world.magic.services.gain import (
    account_for_sheet,
    create_dramatic_moment_tag,
    create_pose_endorsement,
)
from world.scenes.constants import ReactionWindowKind
from world.scenes.factories import SceneParticipationFactory
from world.scenes.interaction_serializers import InteractionListSerializer
from world.scenes.models import Interaction
from world.scenes.reaction_services import open_reaction_window, react_to_window
from world.scenes.reaction_toggle_services import toggle_interaction_reaction
from world.scenes.tests.test_push_feed_fields import (
    PushScene,
    register_binary_entrance_kind,
    sheet_with_tenure,
)


class PushCacheFreshnessTests(PushScene):
    def assert_feed(self, field: str, check) -> None:
        """``check`` holds for the feed field on the pushed instance and on a fresh fetch."""
        same = InteractionListSerializer(self.interaction, context={}).data[field]
        fresh_row = Interaction.objects.get(
            pk=self.interaction.pk, timestamp=self.interaction.timestamp
        )
        fresh = InteractionListSerializer(fresh_row, context={}).data[field]
        for label, value in (("same instance", same), ("fresh fetch", fresh)):
            with self.subTest(field=field, row=label):
                self.assertTrue(check(value), value)

    def test_reaction_after_push(self):
        self.push()
        toggle_interaction_reaction(
            interaction=self.interaction, account=AccountFactory(), emoji="🔥"
        )
        self.assert_feed("reactions", lambda v: [r["emoji"] for r in v] == ["🔥"])

    def test_endorsement_after_push(self):
        endorser = sheet_with_tenure()
        SceneParticipationFactory(scene=self.scene, account=account_for_sheet(endorser))
        self.push()
        create_pose_endorsement(endorser, self.interaction, self.resonance)
        self.assert_feed("pose_endorsers", lambda v: len(v) == 1)

    def test_dramatic_tag_after_push(self):
        self.push()
        create_dramatic_moment_tag(
            character_sheet=self.author,
            moment_type=DramaticMomentTypeFactory(resonance=self.resonance),
            tagged_by=AccountFactory(),
            scene=self.scene,
            interaction=self.interaction,
        )
        self.assert_feed("dramatic_moment_tags", lambda v: len(v) == 1)

    def test_window_and_window_reaction_after_push(self):
        register_binary_entrance_kind(self)
        reactor = sheet_with_tenure()
        SceneParticipationFactory(scene=self.scene, account=account_for_sheet(reactor))
        self.push()
        window = open_reaction_window(
            interaction=self.interaction, kind=ReactionWindowKind.ENTRANCE
        )
        self.assert_feed("reaction_windows", lambda v: len(v) == 1)
        react_to_window(window=window, reactor_persona=reactor.primary_persona, choice="acclaim")
        self.assert_feed("reaction_windows", lambda v: v[0]["counts"] == {"acclaim": 1})

    def test_window_reaction_after_a_push_that_saw_the_window(self):
        """The push warms the window's own reaction rows too; a later reaction must show."""
        register_binary_entrance_kind(self)
        reactor = sheet_with_tenure()
        SceneParticipationFactory(scene=self.scene, account=account_for_sheet(reactor))
        window = open_reaction_window(
            interaction=self.interaction, kind=ReactionWindowKind.ENTRANCE
        )
        self.push()
        react_to_window(window=window, reactor_persona=reactor.primary_persona, choice="acclaim")
        self.assert_feed("reaction_windows", lambda v: v[0]["counts"] == {"acclaim": 1})

    def test_newly_claimed_resonance_after_push(self):
        self.push()
        extra = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=self.author, resonance=extra)
        self.assert_feed("endorsable_resonances", lambda v: extra.pk in {r["id"] for r in v})
