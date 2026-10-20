"""The live frame carries the room-wide fields the REST feed carries (#4508).

A pose that arrived over the websocket used to show without its endorse buttons,
entrance endorsement or tags until a reload, because the frame had fewer fields than
``InteractionListSerializer`` and the page filled the gap with placeholders.
"""

from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.factories import (
    CharacterResonanceFactory,
    DramaticMomentTypeFactory,
    SceneEntryEndorsementFactory,
)
from world.magic.services.gain import (
    account_for_sheet,
    create_dramatic_moment_tag,
    create_pose_endorsement,
)
from world.roster.factories import RosterTenureFactory
from world.scenes.constants import InteractionMode, PoseKind, ReactionWindowKind
from world.scenes.factories import (
    InteractionFactory,
    PersonaFactory,
    SceneFactory,
    SceneParticipationFactory,
)
from world.scenes.interaction_serializers import InteractionListSerializer
from world.scenes.interaction_services import (
    push_interaction,
    scene_entry_endorsements_for,
)
from world.scenes.reaction_services import (
    _KIND_REGISTRY,
    open_reaction_window,
    react_to_window,
    register_reaction_kind,
)
from world.scenes.reaction_toggle_services import toggle_interaction_reaction
from world.scenes.tests.test_reaction_windows import _binary_kind

# Measured at 9 for an ordinary pose: receivers, targets, entry endorsers, resonances,
# pose endorsers, reactions, windows, tags, action rows. A new query here is a regression.
QUERY_BOUND = 9

FEED_FIELDS = (
    "visibility",
    "pose_kind",
    "endorsee_sheet_id",
    "endorsable_resonances",
    "conversation",
    "availability",
    "pose_endorsers",
    "entry_endorsers",
    "reactions",
    "reaction_windows",
    "dramatic_moment_tags",
)


def register_binary_entrance_kind(test: TestCase) -> None:
    """Give ENTRANCE windows two choices for this test, then put the real kind back."""
    original = _KIND_REGISTRY.get(ReactionWindowKind.ENTRANCE)
    if original is not None:
        test.addCleanup(register_reaction_kind, ReactionWindowKind.ENTRANCE, original)
    register_reaction_kind(ReactionWindowKind.ENTRANCE, _binary_kind())


def sheet_with_tenure():
    """A character sheet with a current player, as an endorser or reactor needs."""
    return RosterTenureFactory().roster_entry.character_sheet


class PushScene(TestCase):
    """A room, a scene, an author with a claimed resonance and a located character.

    ``setUp`` (not ``setUpTestData``) because the rows are idmapper-shared and the push
    warms cached properties on them; a class-level row would carry that into the next test.
    """

    def setUp(self):
        self.room = ObjectDBFactory(db_key="Hall", db_typeclass_path="typeclasses.rooms.Room")
        self.author = CharacterSheetFactory(character=CharacterFactory(db_key="Author"))
        self.author.character.location = self.room
        self.scene = SceneFactory()
        self.resonance = CharacterResonanceFactory(character_sheet=self.author).resonance
        self.interaction = InteractionFactory(
            persona=self.author.primary_persona,
            mode=InteractionMode.POSE,
            pose_kind=PoseKind.ENTRY,
            scene=self.scene,
        )

    def push(self) -> dict:
        with patch("world.scenes.interaction_services._broadcast_to_location") as broadcast:
            push_interaction(self.interaction)
        return broadcast.call_args.args[1]

    def rest(self, interaction=None) -> dict:
        context = {
            "character_sheet_ids": {sheet_with_tenure().pk},
            "scene_entry_endorsements": scene_entry_endorsements_for(self.scene),
        }
        return InteractionListSerializer(interaction or self.interaction, context=context).data


class PushFeedFieldsTests(PushScene):
    def _populate(self):
        """One of each room-wide thing a pose can carry, before the push."""
        endorser = sheet_with_tenure()
        SceneParticipationFactory(scene=self.scene, account=account_for_sheet(endorser))
        create_pose_endorsement(endorser, self.interaction, self.resonance)
        toggle_interaction_reaction(
            interaction=self.interaction, account=AccountFactory(), emoji="🔥"
        )
        create_dramatic_moment_tag(
            character_sheet=self.author,
            moment_type=DramaticMomentTypeFactory(resonance=self.resonance),
            tagged_by=AccountFactory(),
            scene=self.scene,
            interaction=self.interaction,
        )
        reactor = sheet_with_tenure()
        SceneParticipationFactory(scene=self.scene, account=account_for_sheet(reactor))
        register_binary_entrance_kind(self)
        window = open_reaction_window(
            interaction=self.interaction, kind=ReactionWindowKind.ENTRANCE
        )
        react_to_window(
            window=window,
            reactor_persona=reactor.primary_persona,
            choice="acclaim",
        )

    def test_live_pose_carries_room_wide_feed_fields(self):
        self._populate()
        payload = self.push()
        rest = self.rest()
        for field in FEED_FIELDS:
            with self.subTest(field=field):
                self.assertEqual(payload[field], rest[field])
        # Populated, so the equality above is not two empty lists agreeing.
        for field in ("pose_endorsers", "reactions", "reaction_windows", "dramatic_moment_tags"):
            with self.subTest(populated=field):
                self.assertTrue(payload[field])
        self.assertEqual(payload["pose_kind"], "entry")
        self.assertEqual(
            payload["endorsable_resonances"],
            [{"id": self.resonance.pk, "name": self.resonance.name}],
        )

    def test_an_ordinary_pose_push_stays_within_its_query_bound(self):
        with CaptureQueriesContext(connection) as queries:
            self.push()
        self.assertLessEqual(len(queries), QUERY_BOUND)

    def test_second_entrance_carries_existing_entry_endorsers(self):
        endorser = sheet_with_tenure()
        SceneEntryEndorsementFactory(
            endorser_sheet=endorser,
            endorsee_sheet=self.author,
            scene=self.scene,
            resonance=self.resonance,
        )
        payload = self.push()
        self.assertEqual(
            [e["persona_id"] for e in payload["entry_endorsers"]],
            [endorser.primary_persona.pk],
        )

    def test_disguised_author_hides_the_sheet_id_on_the_push(self):
        mask = PersonaFactory(character_sheet=self.author, is_fake_name=True)
        self.interaction = InteractionFactory(
            persona=mask, mode=InteractionMode.POSE, scene=self.scene
        )
        self.assertIsNone(self.push()["endorsee_sheet_id"])
