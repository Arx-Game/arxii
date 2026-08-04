"""Credit identities for authored content (#2980).

A ``ContentContributor`` is a person credited for authored content: a writer, a
reviewer, or (the intended second consumer) an artist. It is a CONTENT model, so
it exports to the lore repo and loads on any database by natural key, which is
what lets a fixture row name one without depending on an account existing there.

The account link deliberately lives on the ACCOUNT side
(``evennia_extensions.PlayerData.contributor``), per ADR-0010: the
installation-specific row points at the reusable primitive, never the reverse. An
FK here would put a username into every exported contributor row, and
``_resolve_natural_key_fields`` would then skip that row on any database where
the account does not exist, silently losing the credit.

``Artist`` (``evennia_extensions.models``) is NOT this model. It is a player
commission profile with a required ``PlayerData`` O2O, so it can credit nobody
without an account and has no natural key to export by. See ADR-0196.
"""

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.natural_keys import NaturalKeyManager, NaturalKeyMixin


class ContentContributor(NaturalKeyMixin, SharedMemoryModel):
    """A person credited for authored content: writer, reviewer or artist."""

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Credited name. Free of an account on purpose - an outside "
        "writer or a commissioned artist may never have one.",
    )
    notes = models.TextField(
        blank=True,
        default="",
        help_text="Staff-only context: contact, commission terms, what this person worked on.",
    )

    objects = NaturalKeyManager()

    class Meta:
        ordering = ["name"]

    class NaturalKeyConfig:
        fields = ["name"]

    def __str__(self) -> str:
        return self.name


class CreditedContent(models.Model):
    """Abstract parent: who wrote this row's prose, and who reviewed it (#2980).

    Inherited by every content model that carries a prose field. A null
    ``written_by`` means the prose is still a placeholder, which is what the
    backlog report counts. There is deliberately no separate status enum: the
    state is derivable from these names and a stored copy would drift out of
    step with them.

    All four columns round-trip through the content pipeline with no extra
    plumbing on the JSON path - ``content_export`` serializes every column into
    ``fields`` and ``load_entries`` passes them back as ``update_or_create``
    defaults. The four markdown domains declare them in their ``meta`` instead
    (see ``core_management.content_fixtures``).

    ``related_name="+"``: 83 inheriting models would otherwise need 166 distinct
    reverse accessors on ``ContentContributor``, all of them useless.
    """

    written_by = models.ForeignKey(
        ContentContributor,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Who wrote this row's prose. Null means it is still a placeholder.",
    )
    written_on = models.DateField(
        null=True,
        blank=True,
        help_text="Date the prose was written.",
    )
    reviewed_by = models.ForeignKey(
        ContentContributor,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Who reviewed this row's prose, if anyone. Distinct from writing it.",
    )
    reviewed_on = models.DateField(
        null=True,
        blank=True,
        help_text="Date the prose was reviewed.",
    )

    class Meta:
        abstract = True
