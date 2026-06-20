"""A blocked viewer sees nothing the blocked party says or does (#1278, slice 4).

``hidden_persona_ids_for_viewer`` returns the persona ids whose interactions/presence are hidden
from a viewer. Persona-scoped blocks hide the exact blocked/blocker face; account_level hides all
of the blocker's currently-played faces. Mutual; anti-derivation-safe.
"""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerData
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.block_services import hidden_persona_ids_for_viewer
from world.scenes.factories import PersonaFactory
from world.scenes.models import Block


class BlockFeedVisibilityTests(TestCase):
    def _side(self):
        account = AccountFactory()
        player_data, _ = PlayerData.objects.get_or_create(account=account)
        entry = RosterEntryFactory()
        RosterTenureFactory(player_data=player_data, roster_entry=entry)
        sheet = entry.character_sheet
        return account, player_data, sheet, sheet.primary_persona

    def setUp(self) -> None:
        self.blocker_acct, self.blocker_pd, self.blocker_sheet, self.blocker_face = self._side()
        self.target_acct, self.target_pd, self.target_sheet, self.target_face = self._side()

    def _block(self, **kwargs):
        return Block.objects.create(
            owner=self.blocker_pd,
            blocked_player=self.target_pd,
            blocker_persona=self.blocker_face,
            blocked_persona=self.target_face,
            **kwargs,
        )

    def test_no_block_hides_nothing(self) -> None:
        assert hidden_persona_ids_for_viewer(viewer_account=self.blocker_acct) == set()

    def test_blocker_does_not_see_the_blocked_face(self) -> None:
        self._block()
        assert hidden_persona_ids_for_viewer(viewer_account=self.blocker_acct) == {
            self.target_face.pk
        }

    def test_blocked_does_not_see_the_blocker_face(self) -> None:
        # Mutual, persona-scoped: the blocked viewer loses exactly the blocker's blocking face.
        self._block()
        assert hidden_persona_ids_for_viewer(viewer_account=self.target_acct) == {
            self.blocker_face.pk
        }

    def test_account_level_hides_all_of_the_blockers_faces(self) -> None:
        blocker_alt = PersonaFactory(character_sheet=self.blocker_sheet, name="Blocker Alt")
        Block.objects.create(
            owner=self.blocker_pd,
            blocked_player=self.target_pd,
            blocker_persona=None,
            blocked_persona=self.target_face,
            account_level=True,
        )
        hidden = hidden_persona_ids_for_viewer(viewer_account=self.target_acct)
        assert {self.blocker_face.pk, blocker_alt.pk} <= hidden

    def test_anonymous_viewer_hides_nothing(self) -> None:
        from django.contrib.auth.models import AnonymousUser

        self._block()
        assert hidden_persona_ids_for_viewer(viewer_account=AnonymousUser()) == set()
