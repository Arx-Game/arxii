"""Services for TableBulletinPost and TableBulletinReply (Wave 10)."""

from world.gm.models import GMTable
from world.scenes.models import Persona
from world.stories.models import Story, TableBulletinPost, TableBulletinReply


def create_bulletin_post(  # noqa: PLR0913 — keyword-only args, acceptable here
    *,
    table: GMTable,
    author_persona: Persona,
    title: str,
    body: str,
    story: Story | None = None,
    allow_replies: bool = True,
) -> TableBulletinPost:
    """Create a top-level bulletin post.

    Service receives pre-validated inputs — permissions/role enforcement
    happens in the serializer/view per the canonical three-layer pattern.
    """
    return TableBulletinPost.objects.create(
        table=table,
        story=story,
        author_persona=author_persona,
        title=title,
        body=body,
        allow_replies=allow_replies,
    )


def reply_to_post(
    *,
    post: TableBulletinPost,
    author_persona: Persona,
    body: str,
) -> TableBulletinReply:
    """Reply to a bulletin post.

    Pre-validation: post.allow_replies and viewer permission to read
    the post — enforced in the serializer/view.
    """
    return TableBulletinReply.objects.create(
        post=post,
        author_persona=author_persona,
        body=body,
    )


def edit_bulletin_post(
    *,
    post: TableBulletinPost,
    title: str | None = None,
    body: str | None = None,
    allow_replies: bool | None = None,
) -> TableBulletinPost:
    """Edit a post (author only — enforced at the API layer)."""
    update_fields: list[str] = ["updated_at"]
    if title is not None:
        post.title = title
        update_fields.append("title")
    if body is not None:
        post.body = body
        update_fields.append("body")
    if allow_replies is not None:
        post.allow_replies = allow_replies
        update_fields.append("allow_replies")
    post.save(update_fields=update_fields)
    return post


def delete_bulletin_post(*, post: TableBulletinPost) -> None:
    """Delete a post and cascade its replies."""
    post.delete()
