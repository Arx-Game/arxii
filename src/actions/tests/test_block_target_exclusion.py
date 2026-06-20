"""Block removes the blocked persona from the actor's target picker (#1278, slice 3).

Exercises the match logic of ``_block_excluded_persona_ids`` directly: persona-scoped blocks apply
only while the actor presents the relevant face; account_level covers all the blocker's faces;
mutual; and never excludes a player's *other* faces (anti-derivation).
"""

from django.test import TestCase

from actions.player_interface import _block_excluded_persona_ids
from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerData
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import PersonaFactory
from world.scenes.models import Block


class BlockTargetExclusionTests(TestCase):
    def _side(self):
        account = AccountFactory()
        player_data, _ = PlayerData.objects.get_or_create(account=account)
        entry = RosterEntryFactory()
        tenure = RosterTenureFactory(player_data=player_data, roster_entry=entry)
        sheet = entry.character_sheet
        return player_data, tenure, sheet, sheet.primary_persona

    def setUp(self) -> None:
        self.blocker_pd, self.blocker_tenure, self.blocker_sheet, self.blocker_face = self._side()
        self.target_pd, self.target_tenure, self.target_sheet, self.target_face = self._side()
        self.target_alt = PersonaFactory(character_sheet=self.target_sheet, name="Target Alt")

    def _block(self, **kwargs):
        return Block.objects.create(
            owner=self.blocker_pd,
            blocked_player=self.target_pd,
            blocker_persona=self.blocker_face,
            blocked_persona=self.target_face,
            **kwargs,
        )

    def _excluded(self, actor_tenure, actor_persona_id):
        return _block_excluded_persona_ids(actor_tenure, actor_persona_id, [self.target_tenure])

    def test_no_blocks_excludes_nothing(self) -> None:
        assert self._excluded(self.blocker_tenure, self.blocker_face.pk) == set()

    def test_blocker_presenting_the_blocking_face_cannot_target_the_blocked_face(self) -> None:
        self._block()
        excluded = self._excluded(self.blocker_tenure, self.blocker_face.pk)
        assert excluded == {self.target_face.pk}
        # Anti-derivation: the target's OTHER face is still targetable.
        assert self.target_alt.pk not in excluded

    def test_blocker_presenting_a_different_face_is_not_persona_scoped_block(self) -> None:
        # The coded block is the exact pair; switching to a non-blocking face doesn't carry it.
        self._block()
        other_face = PersonaFactory(character_sheet=self.blocker_sheet, name="Blocker Other")
        assert self._excluded(self.blocker_tenure, other_face.pk) == set()

    def test_account_level_block_excludes_all_targets_faces_from_any_actor_face(self) -> None:
        Block.objects.create(
            owner=self.blocker_pd,
            blocked_player=self.target_pd,
            blocker_persona=None,
            blocked_persona=self.target_face,
            account_level=True,
        )
        other_face = PersonaFactory(character_sheet=self.blocker_sheet, name="Blocker Other")
        # account_level covers the exact blocked face regardless of which face the actor wears.
        assert self._excluded(self.blocker_tenure, other_face.pk) == {self.target_face.pk}

    def test_blocked_actor_cannot_target_the_blocker_face(self) -> None:
        # Mutual: run the resolver from the blocked side against the blocker's tenure.
        self._block()
        excluded = _block_excluded_persona_ids(
            self.target_tenure, self.target_face.pk, [self.blocker_tenure]
        )
        assert excluded == {self.blocker_face.pk}

    def test_blocked_actor_on_a_different_face_keeps_persona_scoping(self) -> None:
        self._block()
        excluded = _block_excluded_persona_ids(
            self.target_tenure, self.target_alt.pk, [self.blocker_tenure]
        )
        assert excluded == set()
