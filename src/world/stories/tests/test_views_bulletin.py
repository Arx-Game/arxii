"""Tests for TableBulletinPost and TableBulletinReply ViewSets (Wave 10 Task 10.2).

Permission matrix:
- Staff: all access
- Lead GM of post.table: all access
- Active table member (table-wide post): read
- Story participant (story-scoped post): read
- No-relation user: no access
- Non-Lead-GM: cannot create top-level post
- allow_replies=False (non-staff): cannot reply
"""

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.gm.factories import (
    GMProfileFactory,
    GMTableFactory,
    GMTableMembershipFactory,
)
from world.scenes.factories import PersonaFactory
from world.stories.constants import StoryScope
from world.stories.factories import (
    StoryFactory,
    StoryParticipationFactory,
    TableBulletinPostFactory,
    TableBulletinReplyFactory,
)
from world.stories.models import TableBulletinPost, TableBulletinReply


class BulletinViewSetSetup(TestCase):
    """Base setup for bulletin ViewSet tests.

    Creates:
    - staff_user: staff account
    - lead_gm_user: account with GMProfile that owns the table
    - member_user: account with active GMTableMembership (ESTABLISHED persona)
    - participant_user: account with active StoryParticipation on story
    - outsider_user: account with no relation to the table or story
    - non_lead_gm_user: account with GMProfile but does NOT own the table

    - table: GMTable owned by lead_gm_user's GMProfile
    - story: Story with primary_table=table
    - member_persona: Persona used for member_user's membership
    - participant_character: ObjectDB for participant_user's StoryParticipation
    """

    @classmethod
    def setUpTestData(cls) -> None:
        # Accounts
        cls.staff_user = AccountFactory(username="bulletin_staff")
        cls.staff_user.is_staff = True
        cls.staff_user.is_superuser = True
        cls.staff_user.save()

        cls.lead_gm_user = AccountFactory(username="bulletin_lead_gm")
        cls.member_user = AccountFactory(username="bulletin_member")
        cls.participant_user = AccountFactory(username="bulletin_participant")
        cls.outsider_user = AccountFactory(username="bulletin_outsider")
        cls.non_lead_gm_user = AccountFactory(username="bulletin_non_lead_gm")

        # GM profiles
        cls.lead_gm_profile = GMProfileFactory(account=cls.lead_gm_user)
        cls.non_lead_gm_profile = GMProfileFactory(account=cls.non_lead_gm_user)

        # Table owned by lead_gm
        cls.table = GMTableFactory(gm=cls.lead_gm_profile)

        # A second table (for "other table" scenarios)
        cls.other_table = GMTableFactory(gm=cls.non_lead_gm_profile)

        # Member persona + membership
        cls.member_persona = PersonaFactory()
        # Override character_sheet.character.db_account to be member_user

        member_sheet = cls.member_persona.character_sheet
        member_sheet.character.db_account = cls.member_user
        member_sheet.character.save()
        GMTableMembershipFactory(table=cls.table, persona=cls.member_persona)

        # Author persona (GM posts as one of their personas)
        cls.lead_gm_persona = PersonaFactory()
        lead_gm_sheet = cls.lead_gm_persona.character_sheet
        lead_gm_sheet.character.db_account = cls.lead_gm_user
        lead_gm_sheet.character.save()

        # Story with primary_table
        cls.story = StoryFactory(
            scope=StoryScope.GROUP,
            primary_table=cls.table,
        )

        # Participant persona + StoryParticipation
        cls.participant_persona = PersonaFactory()
        participant_sheet = cls.participant_persona.character_sheet
        participant_sheet.character.db_account = cls.participant_user
        participant_sheet.character.save()
        cls.story_participation = StoryParticipationFactory(
            story=cls.story,
            character=participant_sheet.character,
        )

    def _client(self, user: object) -> APIClient:
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    def _staff(self) -> APIClient:
        return self._client(self.staff_user)

    def _lead_gm(self) -> APIClient:
        return self._client(self.lead_gm_user)

    def _member(self) -> APIClient:
        return self._client(self.member_user)

    def _participant(self) -> APIClient:
        return self._client(self.participant_user)

    def _outsider(self) -> APIClient:
        return self._client(self.outsider_user)

    def _non_lead_gm(self) -> APIClient:
        return self._client(self.non_lead_gm_user)


# ---------------------------------------------------------------------------
# TableBulletinPost: create (GM/staff only)
# ---------------------------------------------------------------------------


class BulletinPostCreateTests(BulletinViewSetSetup):
    """Tests for POST /api/table-bulletin-posts/."""

    def test_lead_gm_can_create_table_wide_post(self) -> None:
        payload = {
            "table": self.table.pk,
            "author_persona": self.lead_gm_persona.pk,
            "title": "Welcome",
            "body": "Hello table!",
            "allow_replies": True,
        }
        res = self._lead_gm().post("/api/table-bulletin-posts/", payload, format="json")
        self.assertEqual(res.status_code, 201, res.json())
        self.assertIsNone(res.json()["story"])

    def test_lead_gm_can_create_story_scoped_post(self) -> None:
        payload = {
            "table": self.table.pk,
            "story": self.story.pk,
            "author_persona": self.lead_gm_persona.pk,
            "title": "Story Update",
            "body": "Chapter 1 begins.",
        }
        res = self._lead_gm().post("/api/table-bulletin-posts/", payload, format="json")
        self.assertEqual(res.status_code, 201, res.json())
        self.assertEqual(res.json()["story"], self.story.pk)

    def test_staff_can_create_post(self) -> None:
        payload = {
            "table": self.table.pk,
            "author_persona": self.lead_gm_persona.pk,
            "title": "Staff Post",
            "body": "Staff message.",
        }
        res = self._staff().post("/api/table-bulletin-posts/", payload, format="json")
        self.assertEqual(res.status_code, 201)

    def test_non_lead_gm_cannot_create_on_others_table(self) -> None:
        """A GM who is not the Lead GM of the target table cannot post."""
        payload = {
            "table": self.table.pk,  # owned by lead_gm, NOT non_lead_gm
            "author_persona": self.lead_gm_persona.pk,
            "title": "Unauthorized",
            "body": "Oops.",
        }
        res = self._non_lead_gm().post("/api/table-bulletin-posts/", payload, format="json")
        self.assertEqual(res.status_code, 400)

    def test_member_cannot_create_post(self) -> None:
        """Active table members cannot create top-level posts."""
        payload = {
            "table": self.table.pk,
            "author_persona": self.member_persona.pk,
            "title": "Player post",
            "body": "Not allowed.",
        }
        res = self._member().post("/api/table-bulletin-posts/", payload, format="json")
        self.assertEqual(res.status_code, 400)

    def test_story_not_on_table_rejected(self) -> None:
        """Creating a story-scoped post where story.primary_table != table is rejected."""
        other_story = StoryFactory(scope=StoryScope.GROUP, primary_table=self.other_table)
        payload = {
            "table": self.table.pk,
            "story": other_story.pk,
            "author_persona": self.lead_gm_persona.pk,
            "title": "Mismatch",
            "body": "Story not on this table.",
        }
        res = self._lead_gm().post("/api/table-bulletin-posts/", payload, format="json")
        self.assertEqual(res.status_code, 400)


# ---------------------------------------------------------------------------
# TableBulletinPost: list (read access)
# ---------------------------------------------------------------------------


class BulletinPostReadTests(BulletinViewSetSetup):
    """Tests for GET /api/table-bulletin-posts/ and retrieve."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        # Table-wide post
        cls.table_wide_post = TableBulletinPostFactory(
            table=cls.table,
            story=None,
            author_persona=cls.lead_gm_persona,
        )
        # Story-scoped post
        cls.story_post = TableBulletinPostFactory(
            table=cls.table,
            story=cls.story,
            author_persona=cls.lead_gm_persona,
        )

    def test_staff_sees_all_posts(self) -> None:
        res = self._staff().get("/api/table-bulletin-posts/")
        self.assertEqual(res.status_code, 200)
        result_ids = {r["id"] for r in res.json()["results"]}
        self.assertIn(self.table_wide_post.pk, result_ids)
        self.assertIn(self.story_post.pk, result_ids)

    def test_lead_gm_sees_all_posts(self) -> None:
        res = self._lead_gm().get("/api/table-bulletin-posts/")
        self.assertEqual(res.status_code, 200)
        result_ids = {r["id"] for r in res.json()["results"]}
        self.assertIn(self.table_wide_post.pk, result_ids)
        self.assertIn(self.story_post.pk, result_ids)

    def test_active_member_sees_table_wide_only(self) -> None:
        """Active members see table-wide posts but NOT story-scoped posts they're not in."""
        res = self._member().get("/api/table-bulletin-posts/")
        self.assertEqual(res.status_code, 200)
        result_ids = {r["id"] for r in res.json()["results"]}
        self.assertIn(self.table_wide_post.pk, result_ids)
        self.assertNotIn(self.story_post.pk, result_ids)

    def test_story_participant_sees_story_scoped_post(self) -> None:
        """Story participants see story-scoped posts for their story."""
        res = self._participant().get("/api/table-bulletin-posts/")
        self.assertEqual(res.status_code, 200)
        result_ids = {r["id"] for r in res.json()["results"]}
        self.assertIn(self.story_post.pk, result_ids)

    def test_outsider_sees_no_posts(self) -> None:
        res = self._outsider().get("/api/table-bulletin-posts/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["results"], [])

    def test_unauthenticated_cannot_list(self) -> None:
        res = APIClient().get("/api/table-bulletin-posts/")
        self.assertEqual(res.status_code, 403)

    def test_filter_by_table(self) -> None:
        res = self._staff().get(f"/api/table-bulletin-posts/?table={self.table.pk}")
        self.assertEqual(res.status_code, 200)
        for item in res.json()["results"]:
            self.assertEqual(item["table"], self.table.pk)

    def test_filter_by_story(self) -> None:
        res = self._staff().get(f"/api/table-bulletin-posts/?story={self.story.pk}")
        self.assertEqual(res.status_code, 200)
        result_ids = {r["id"] for r in res.json()["results"]}
        self.assertIn(self.story_post.pk, result_ids)
        self.assertNotIn(self.table_wide_post.pk, result_ids)


# ---------------------------------------------------------------------------
# TableBulletinPost: update/delete (author / staff)
# ---------------------------------------------------------------------------


class BulletinPostWriteTests(BulletinViewSetSetup):
    """Tests for PATCH/DELETE /api/table-bulletin-posts/{id}/."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.post = TableBulletinPostFactory(
            table=cls.table,
            story=None,
            author_persona=cls.lead_gm_persona,
            title="Original",
        )

    def test_lead_gm_can_edit_post(self) -> None:
        res = self._lead_gm().patch(
            f"/api/table-bulletin-posts/{self.post.pk}/",
            {"title": "Updated"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["title"], "Updated")

    def test_staff_can_edit_post(self) -> None:
        res = self._staff().patch(
            f"/api/table-bulletin-posts/{self.post.pk}/",
            {"title": "Staff Edit"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)

    def test_member_cannot_edit_post(self) -> None:
        res = self._member().patch(
            f"/api/table-bulletin-posts/{self.post.pk}/",
            {"title": "Hacked"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_lead_gm_can_delete_post(self) -> None:
        post = TableBulletinPostFactory(table=self.table, story=None)
        res = self._lead_gm().delete(f"/api/table-bulletin-posts/{post.pk}/")
        self.assertEqual(res.status_code, 204)
        self.assertFalse(TableBulletinPost.objects.filter(pk=post.pk).exists())

    def test_member_cannot_delete_post(self) -> None:
        res = self._member().delete(f"/api/table-bulletin-posts/{self.post.pk}/")
        self.assertEqual(res.status_code, 403)


# ---------------------------------------------------------------------------
# TableBulletinReply: create
# ---------------------------------------------------------------------------


class BulletinReplyCreateTests(BulletinViewSetSetup):
    """Tests for POST /api/table-bulletin-replies/."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.post_replies_on = TableBulletinPostFactory(
            table=cls.table,
            story=None,
            allow_replies=True,
        )
        cls.post_replies_off = TableBulletinPostFactory(
            table=cls.table,
            story=None,
            allow_replies=False,
        )

    def test_member_can_reply_when_allow_replies_true(self) -> None:
        payload = {
            "post": self.post_replies_on.pk,
            "author_persona": self.member_persona.pk,
            "body": "Great post!",
        }
        res = self._member().post("/api/table-bulletin-replies/", payload, format="json")
        self.assertEqual(res.status_code, 201, res.json())

    def test_member_cannot_reply_when_allow_replies_false(self) -> None:
        payload = {
            "post": self.post_replies_off.pk,
            "author_persona": self.member_persona.pk,
            "body": "Trying to reply.",
        }
        res = self._member().post("/api/table-bulletin-replies/", payload, format="json")
        self.assertEqual(res.status_code, 400)

    def test_staff_can_reply_even_when_replies_disabled(self) -> None:
        """Staff bypass the allow_replies check."""
        payload = {
            "post": self.post_replies_off.pk,
            "author_persona": self.lead_gm_persona.pk,
            "body": "Staff override.",
        }
        res = self._staff().post("/api/table-bulletin-replies/", payload, format="json")
        self.assertEqual(res.status_code, 201)

    def test_outsider_cannot_reply(self) -> None:
        """User with no table relation cannot reply even if allow_replies=True."""
        outsider_persona = PersonaFactory()
        payload = {
            "post": self.post_replies_on.pk,
            "author_persona": outsider_persona.pk,
            "body": "Infiltrator!",
        }
        res = self._outsider().post("/api/table-bulletin-replies/", payload, format="json")
        self.assertEqual(res.status_code, 400)

    def test_lead_gm_can_reply(self) -> None:
        payload = {
            "post": self.post_replies_on.pk,
            "author_persona": self.lead_gm_persona.pk,
            "body": "Lead GM reply.",
        }
        res = self._lead_gm().post("/api/table-bulletin-replies/", payload, format="json")
        self.assertEqual(res.status_code, 201)


# ---------------------------------------------------------------------------
# TableBulletinReply: list (read scoping)
# ---------------------------------------------------------------------------


class BulletinReplyReadTests(BulletinViewSetSetup):
    """Tests for GET /api/table-bulletin-replies/?post=<id>."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.table_wide_post = TableBulletinPostFactory(
            table=cls.table,
            story=None,
        )
        cls.story_post = TableBulletinPostFactory(
            table=cls.table,
            story=cls.story,
        )
        cls.reply_on_table_wide = TableBulletinReplyFactory(post=cls.table_wide_post)
        cls.reply_on_story = TableBulletinReplyFactory(post=cls.story_post)

    def test_staff_sees_all_replies(self) -> None:
        res = self._staff().get("/api/table-bulletin-replies/")
        self.assertEqual(res.status_code, 200)
        result_ids = {r["id"] for r in res.json()["results"]}
        self.assertIn(self.reply_on_table_wide.pk, result_ids)
        self.assertIn(self.reply_on_story.pk, result_ids)

    def test_member_sees_only_table_wide_replies(self) -> None:
        res = self._member().get("/api/table-bulletin-replies/")
        self.assertEqual(res.status_code, 200)
        result_ids = {r["id"] for r in res.json()["results"]}
        self.assertIn(self.reply_on_table_wide.pk, result_ids)
        self.assertNotIn(self.reply_on_story.pk, result_ids)

    def test_participant_sees_story_reply(self) -> None:
        res = self._participant().get("/api/table-bulletin-replies/")
        self.assertEqual(res.status_code, 200)
        result_ids = {r["id"] for r in res.json()["results"]}
        self.assertIn(self.reply_on_story.pk, result_ids)

    def test_outsider_sees_no_replies(self) -> None:
        res = self._outsider().get("/api/table-bulletin-replies/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["results"], [])

    def test_filter_by_post(self) -> None:
        res = self._staff().get(f"/api/table-bulletin-replies/?post={self.table_wide_post.pk}")
        self.assertEqual(res.status_code, 200)
        for item in res.json()["results"]:
            self.assertEqual(item["post"], self.table_wide_post.pk)


# ---------------------------------------------------------------------------
# TableBulletinReply: edit/delete (author or staff)
# ---------------------------------------------------------------------------


class BulletinReplyWriteTests(BulletinViewSetSetup):
    """Tests for PATCH/DELETE /api/table-bulletin-replies/{id}/."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.table_wide_post = TableBulletinPostFactory(
            table=cls.table, story=None, allow_replies=True
        )
        # Reply authored by member
        cls.member_reply = TableBulletinReplyFactory(
            post=cls.table_wide_post,
            author_persona=cls.member_persona,
        )

    def test_reply_author_can_edit(self) -> None:
        res = self._member().patch(
            f"/api/table-bulletin-replies/{self.member_reply.pk}/",
            {"body": "Edited."},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["body"], "Edited.")

    def test_staff_can_edit_any_reply(self) -> None:
        res = self._staff().patch(
            f"/api/table-bulletin-replies/{self.member_reply.pk}/",
            {"body": "Staff edited."},
            format="json",
        )
        self.assertEqual(res.status_code, 200)

    def test_non_author_cannot_edit(self) -> None:
        """Lead GM cannot edit a reply they didn't author."""
        res = self._lead_gm().patch(
            f"/api/table-bulletin-replies/{self.member_reply.pk}/",
            {"body": "Hacked."},
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_reply_author_can_delete(self) -> None:
        reply = TableBulletinReplyFactory(
            post=self.table_wide_post,
            author_persona=self.member_persona,
        )
        res = self._member().delete(f"/api/table-bulletin-replies/{reply.pk}/")
        self.assertEqual(res.status_code, 204)
        self.assertFalse(TableBulletinReply.objects.filter(pk=reply.pk).exists())

    def test_staff_can_delete_any_reply(self) -> None:
        reply = TableBulletinReplyFactory(post=self.table_wide_post)
        res = self._staff().delete(f"/api/table-bulletin-replies/{reply.pk}/")
        self.assertEqual(res.status_code, 204)

    def test_non_author_cannot_delete(self) -> None:
        res = self._lead_gm().delete(f"/api/table-bulletin-replies/{self.member_reply.pk}/")
        self.assertEqual(res.status_code, 403)


# ---------------------------------------------------------------------------
# Services unit tests
# ---------------------------------------------------------------------------


class BulletinServiceTests(BulletinViewSetSetup):
    """Direct service function tests."""

    def test_create_post_service(self) -> None:
        from world.stories.services.bulletin import create_bulletin_post

        post = create_bulletin_post(
            table=self.table,
            author_persona=self.lead_gm_persona,
            title="Service Post",
            body="Body text.",
        )
        self.assertEqual(post.table_id, self.table.pk)
        self.assertIsNone(post.story_id)
        self.assertEqual(post.title, "Service Post")

    def test_edit_post_service(self) -> None:
        from world.stories.services.bulletin import edit_bulletin_post

        post = TableBulletinPostFactory(table=self.table)
        updated = edit_bulletin_post(post=post, title="New Title", allow_replies=False)
        self.assertEqual(updated.title, "New Title")
        self.assertFalse(updated.allow_replies)

    def test_reply_service(self) -> None:
        from world.stories.services.bulletin import reply_to_post

        post = TableBulletinPostFactory(table=self.table, allow_replies=True)
        reply = reply_to_post(post=post, author_persona=self.member_persona, body="Hello!")
        self.assertEqual(reply.post_id, post.pk)
        self.assertEqual(reply.body, "Hello!")

    def test_delete_post_service(self) -> None:
        from world.stories.services.bulletin import delete_bulletin_post

        post = TableBulletinPostFactory(table=self.table)
        post_pk = post.pk
        delete_bulletin_post(post=post)
        self.assertFalse(TableBulletinPost.objects.filter(pk=post_pk).exists())

    def test_delete_post_cascades_replies(self) -> None:
        from world.stories.services.bulletin import delete_bulletin_post

        post = TableBulletinPostFactory(table=self.table)
        r1 = TableBulletinReplyFactory(post=post)
        r2 = TableBulletinReplyFactory(post=post)
        delete_bulletin_post(post=post)
        self.assertFalse(TableBulletinReply.objects.filter(pk__in=[r1.pk, r2.pk]).exists())
