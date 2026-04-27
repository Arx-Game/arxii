"""Tests for TableBulletinPost + TableBulletinReply models (Wave 10 Task 10.1)."""

from django.test import TestCase

from world.gm.factories import GMTableFactory
from world.scenes.factories import PersonaFactory
from world.stories.factories import (
    StoryFactory,
    TableBulletinPostFactory,
    TableBulletinReplyFactory,
)
from world.stories.models import TableBulletinPost, TableBulletinReply


class TableBulletinPostModelTests(TestCase):
    """Round-trip and field-level tests for TableBulletinPost."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.table = GMTableFactory()
        cls.persona = PersonaFactory()
        cls.story = StoryFactory()

    def test_table_wide_post_created(self) -> None:
        """story=None → table-wide post."""
        post = TableBulletinPostFactory(
            table=self.table,
            author_persona=self.persona,
            story=None,
            title="Announcements",
            body="Welcome to the table.",
        )
        fetched = TableBulletinPost.objects.get(pk=post.pk)
        self.assertEqual(fetched.table_id, self.table.pk)
        self.assertIsNone(fetched.story_id)
        self.assertEqual(fetched.title, "Announcements")
        self.assertEqual(fetched.body, "Welcome to the table.")
        self.assertTrue(fetched.allow_replies)

    def test_story_scoped_post_created(self) -> None:
        """story=set → story-scoped post."""
        post = TableBulletinPostFactory(
            table=self.table,
            author_persona=self.persona,
            story=self.story,
            title="Story Update",
        )
        fetched = TableBulletinPost.objects.get(pk=post.pk)
        self.assertEqual(fetched.story_id, self.story.pk)

    def test_allow_replies_default_true(self) -> None:
        post = TableBulletinPostFactory(table=self.table)
        self.assertTrue(post.allow_replies)

    def test_allow_replies_can_be_false(self) -> None:
        post = TableBulletinPostFactory(table=self.table, allow_replies=False)
        self.assertFalse(post.allow_replies)

    def test_persona_deletion_preserves_post(self) -> None:
        """Persona deletion sets author_persona to None (SET_NULL); post survives."""
        persona = PersonaFactory()
        post = TableBulletinPostFactory(
            table=self.table,
            author_persona=persona,
        )
        post_pk = post.pk
        persona.delete()
        # Bypass SharedMemoryModel identity map via .values() to get the raw DB value.
        row = TableBulletinPost.objects.filter(pk=post_pk).values("author_persona_id").first()
        self.assertIsNotNone(row, "Post must survive persona deletion")
        self.assertIsNone(row["author_persona_id"])  # type: ignore[index]

    def test_ordering_newest_first(self) -> None:
        """Posts are ordered newest-first by default."""
        post1 = TableBulletinPostFactory(table=self.table)
        post2 = TableBulletinPostFactory(table=self.table)
        posts = list(
            TableBulletinPost.objects.filter(table=self.table).values_list("pk", flat=True)
        )
        # post2 was created after post1, so it should come first
        self.assertEqual(posts[0], post2.pk)
        self.assertEqual(posts[1], post1.pk)

    def test_str_table_wide(self) -> None:
        post = TableBulletinPostFactory(table=self.table, story=None)
        self.assertIn("table-wide", str(post))

    def test_str_story_scoped(self) -> None:
        post = TableBulletinPostFactory(table=self.table, story=self.story)
        self.assertIn(f"story #{self.story.pk}", str(post))


class TableBulletinReplyModelTests(TestCase):
    """Round-trip and field-level tests for TableBulletinReply."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.table = GMTableFactory()
        cls.post = TableBulletinPostFactory(table=cls.table)

    def test_reply_created(self) -> None:
        reply = TableBulletinReplyFactory(post=self.post, body="First reply.")
        fetched = TableBulletinReply.objects.get(pk=reply.pk)
        self.assertEqual(fetched.post_id, self.post.pk)
        self.assertEqual(fetched.body, "First reply.")

    def test_multiple_replies(self) -> None:
        """Multiple replies on one post; all survive."""
        r1 = TableBulletinReplyFactory(post=self.post)
        r2 = TableBulletinReplyFactory(post=self.post)
        r3 = TableBulletinReplyFactory(post=self.post)
        pks = set(TableBulletinReply.objects.filter(post=self.post).values_list("pk", flat=True))
        self.assertIn(r1.pk, pks)
        self.assertIn(r2.pk, pks)
        self.assertIn(r3.pk, pks)

    def test_replies_ordered_oldest_first(self) -> None:
        """Replies are ordered oldest-first by default."""
        r1 = TableBulletinReplyFactory(post=self.post)
        r2 = TableBulletinReplyFactory(post=self.post)
        replies = list(
            TableBulletinReply.objects.filter(post=self.post).values_list("pk", flat=True)
        )
        self.assertEqual(replies[0], r1.pk)
        self.assertEqual(replies[1], r2.pk)

    def test_persona_deletion_preserves_reply(self) -> None:
        """Persona deletion sets author_persona to None; reply survives."""
        persona = PersonaFactory()
        reply = TableBulletinReplyFactory(post=self.post, author_persona=persona)
        reply_pk = reply.pk
        persona.delete()
        # Bypass SharedMemoryModel identity map via .values() to get the raw DB value.
        row = TableBulletinReply.objects.filter(pk=reply_pk).values("author_persona_id").first()
        self.assertIsNotNone(row, "Reply must survive persona deletion")
        self.assertIsNone(row["author_persona_id"])  # type: ignore[index]

    def test_post_deletion_cascades_to_replies(self) -> None:
        """Deleting a post also deletes all its replies."""
        post = TableBulletinPostFactory(table=self.table)
        r1 = TableBulletinReplyFactory(post=post)
        r2 = TableBulletinReplyFactory(post=post)
        post.delete()
        self.assertFalse(TableBulletinReply.objects.filter(pk__in=[r1.pk, r2.pk]).exists())

    def test_str(self) -> None:
        reply = TableBulletinReplyFactory(post=self.post)
        self.assertIn(f"post=#{self.post.pk}", str(reply))
