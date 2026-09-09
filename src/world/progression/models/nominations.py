"""Weekly nominations for good RP (#3738).

A nomination is an OOC act by a player's account: "I am voting this person for
good RP because of this." The row hangs off the prose the nominator read (a
pose or a journal entry, ``target_type`` + ``target_id``) and names the
character who wrote it (``nominee``). One account nominating one character in
one week is one nomination no matter how many of their pieces it marks; the
further rows only cite more prose, which is what "most nominated prose" and
"best in scene" count.

No budget. Nothing to spend early or lose at week's end; the scarcity is that
you can only nominate prose from this week that you could see. Nominations are
invisible to the nominee until the week settles (no toast, no count, no names),
because knowing who voted for you creates pressure to return it. The
``nominator`` is the account (every alt and persona collapses to one), the
``nominee`` is the character (XP is per sheet), so two characters of one
player are two nominees.

Settlement (``services.nomination_processing``) runs on the weekly rollover
and pays four paths on one stepped curve; see ``constants.NOMINATION_*``.
"""

from django.db import models
from evennia.accounts.models import AccountDB
from evennia.utils.idmapper.models import SharedMemoryModel

from world.progression.constants import NominationTargetType


class Nomination(SharedMemoryModel):
    """One piece of prose a nominator cited when nominating its writer this week.

    ``target_type`` + ``target_id`` form a generic reference without a
    database-level cascade (the interaction table is partitioned); a deleted
    piece leaves the row, which still counts as the nomination it was.
    """

    nominator = models.ForeignKey(
        AccountDB,
        on_delete=models.CASCADE,
        related_name="nominations_given",
        help_text="The player nominating: the account, so alts and personas cannot stack.",
    )
    game_week = models.ForeignKey(
        "arxii.GameWeek",
        on_delete=models.CASCADE,
        related_name="nominations",
    )
    nominee = models.ForeignKey(
        "arxii.CharacterSheet",
        on_delete=models.CASCADE,
        related_name="nominations_received",
        help_text="The character whose prose it was; the XP lands on this sheet's player.",
    )
    target_type = models.CharField(
        max_length=25,
        choices=NominationTargetType.choices,
        help_text="What the nominator read: a pose (interaction) or a journal entry.",
    )
    target_id = models.PositiveIntegerField(
        help_text="PK of the cited piece (not a FK: the interaction table is partitioned).",
    )
    processed = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Set True by the weekly settlement after XP is awarded.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["nominator", "target_type", "target_id", "game_week"],
                name="unique_nomination_per_piece_per_week",
            ),
        ]
        indexes = [
            models.Index(fields=["nominee", "game_week"], name="nomination_nominee_week_idx"),
        ]

    def __str__(self) -> str:
        return (
            f"{self.nominator} nominated sheet {self.nominee_id} for "
            f"{self.target_type}:{self.target_id} ({self.game_week})"
        )
