"""Tests for StoryViewSet.get_queryset() — Phase 5 Task 1.3 tightening.

Verifies the queryset scoping rules added in Wave 1:
- Staff see all stories.
- GM (table owner) sees all stories at their tables.
- CHARACTER-scope: visible to the character sheet's owner.
- Active StoryParticipation: visible to participants.
- Owned stories (M2M): visible to owners.
- GLOBAL scope: visible to any authenticated user.
- PUBLIC privacy: visible to any authenticated user (for apply-to-participate).
- GROUP scope + no membership: not enumerable by non-members.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.scenes.factories import PersonaFactory
from world.stories.constants import StoryScope
from world.stories.factories import (
    StoryFactory,
    StoryParticipationFactory,
)
from world.stories.types import StoryPrivacy


def _sheet_for_account(account):
    """Create a CharacterSheet whose character.db_account is account."""
    char = CharacterFactory()
    char.db_account = account
    char.save()
    return CharacterSheetFactory(character=char)


def _persona_for_account(account):
    """Create a Persona linked to account via character_sheet -> character -> db_account."""
    sheet = _sheet_for_account(account)
    return PersonaFactory(character_sheet=sheet), sheet.character


class StoryQuerysetScopeTest(APITestCase):
    """Verify Phase 5 Task 1.3 queryset rules for StoryViewSet."""

    @classmethod
    def setUpTestData(cls):
        # --- accounts ----------------------------------------------------------
        cls.staff = AccountFactory(is_staff=True)

        cls.gm_account = AccountFactory()
        cls.gm_profile = GMProfileFactory(account=cls.gm_account)
        cls.gm_table = GMTableFactory(gm=cls.gm_profile)

        cls.owner_account = AccountFactory()

        cls.participant_account = AccountFactory()
        cls.participant_char = CharacterFactory()
        cls.participant_char.db_account = cls.participant_account
        cls.participant_char.save()

        cls.character_owner_account = AccountFactory()
        cls.character_owner_sheet = _sheet_for_account(cls.character_owner_account)

        cls.outsider_account = AccountFactory()

        # --- stories -----------------------------------------------------------

        # Story at GM's table
        cls.table_story = StoryFactory(primary_table=cls.gm_table)

        # CHARACTER-scope story owned via character_sheet
        cls.character_story = StoryFactory(
            scope=StoryScope.CHARACTER,
            character_sheet=cls.character_owner_sheet,
            privacy=StoryPrivacy.PRIVATE,  # private — only visible via character_sheet path
        )

        # Story with a participant
        cls.participant_story = StoryFactory(privacy=StoryPrivacy.PRIVATE)
        cls.participation = StoryParticipationFactory(
            story=cls.participant_story,
            character=cls.participant_char,
            is_active=True,
        )

        # Story owned via M2M
        cls.owned_story = StoryFactory(
            owners=[cls.owner_account],
            privacy=StoryPrivacy.PRIVATE,
        )

        # GLOBAL-scope story
        cls.global_story = StoryFactory(
            scope=StoryScope.GLOBAL,
            privacy=StoryPrivacy.PRIVATE,
        )

        # PUBLIC-privacy story (allows apply-to-participate from any user)
        cls.public_story = StoryFactory(privacy=StoryPrivacy.PUBLIC)

        # GROUP story that nobody in our test has membership for
        cls.group_story = StoryFactory(
            scope=StoryScope.GROUP,
            privacy=StoryPrivacy.PRIVATE,
        )

    def _ids(self, account):
        self.client.force_authenticate(user=account)
        resp = self.client.get(reverse("story-list"))
        assert resp.status_code == status.HTTP_200_OK
        return {item["id"] for item in resp.data["results"]}

    # --- staff ----------------------------------------------------------------

    def test_staff_sees_all_stories(self):
        ids = self._ids(self.staff)
        for story in [
            self.table_story,
            self.character_story,
            self.participant_story,
            self.owned_story,
            self.global_story,
            self.public_story,
            self.group_story,
        ]:
            assert story.pk in ids, f"Staff should see story {story.pk}"

    # --- GM (table owner) -----------------------------------------------------

    def test_gm_sees_stories_at_their_table(self):
        ids = self._ids(self.gm_account)
        assert self.table_story.pk in ids

    def test_gm_cannot_see_private_story_at_another_gms_table(self):
        other_gm = GMProfileFactory()
        other_table = GMTableFactory(gm=other_gm)
        private_story = StoryFactory(
            privacy=StoryPrivacy.PRIVATE,
            primary_table=other_table,
        )
        ids = self._ids(self.gm_account)
        # GM should NOT see a private story at someone else's table
        assert private_story.pk not in ids

    # --- CHARACTER-scope via character_sheet ----------------------------------

    def test_character_owner_sees_their_character_story(self):
        ids = self._ids(self.character_owner_account)
        assert self.character_story.pk in ids

    def test_outsider_cannot_see_private_character_story(self):
        ids = self._ids(self.outsider_account)
        assert self.character_story.pk not in ids

    # --- StoryParticipation ---------------------------------------------------

    def test_participant_sees_their_story(self):
        ids = self._ids(self.participant_account)
        assert self.participant_story.pk in ids

    def test_outsider_cannot_see_private_participant_story(self):
        ids = self._ids(self.outsider_account)
        assert self.participant_story.pk not in ids

    # --- Story.owners M2M -----------------------------------------------------

    def test_owner_sees_their_private_story(self):
        ids = self._ids(self.owner_account)
        assert self.owned_story.pk in ids

    def test_outsider_cannot_see_private_owned_story(self):
        ids = self._ids(self.outsider_account)
        assert self.owned_story.pk not in ids

    # --- GLOBAL scope ---------------------------------------------------------

    def test_any_user_sees_global_story(self):
        ids = self._ids(self.outsider_account)
        assert self.global_story.pk in ids

    # --- PUBLIC privacy -------------------------------------------------------

    def test_any_user_sees_public_story(self):
        """PUBLIC-privacy stories are visible to allow apply-to-participate."""
        ids = self._ids(self.outsider_account)
        assert self.public_story.pk in ids

    # --- GROUP scope, no membership -------------------------------------------

    def test_non_member_cannot_see_private_group_story(self):
        """Non-participants cannot enumerate GROUP-scope private stories."""
        ids = self._ids(self.outsider_account)
        assert self.group_story.pk not in ids

    def test_lead_gm_can_see_group_story_at_their_table(self):
        """Lead GM can enumerate GROUP stories at their table."""
        group_table_story = StoryFactory(
            scope=StoryScope.GROUP,
            privacy=StoryPrivacy.PRIVATE,
            primary_table=self.gm_table,
        )
        ids = self._ids(self.gm_account)
        assert group_table_story.pk in ids
