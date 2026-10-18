"""Lending a major NPC to a GM or Guide to play (#4418).

``StoryNPCSettings`` holds the holder's choices for one NPC; ``NPCLoan`` is one
loan of it. Only one loan per NPC may be active at a time.
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.db.models import Q

from core.models import ArxSharedMemoryModel as SharedMemoryModel
from evennia_extensions.mixins import RelatedCacheClearingMixin
from world.roster.constants import NPCBorrowAudience, NPCLendPolicy, NPCLoanStatus


class StoryNPCSettings(SharedMemoryModel):
    """The holder's choices about lending one major NPC."""

    roster_entry = models.OneToOneField(
        "arxii.RosterEntry",
        on_delete=models.CASCADE,
        related_name="story_npc_settings",
    )
    listed_on_npc_roster = models.BooleanField(
        default=False,
        help_text="Show this NPC on the roster of NPCs GMs and Guides can browse.",
    )
    lend_policy = models.CharField(
        max_length=20,
        choices=NPCLendPolicy.choices,
        default=NPCLendPolicy.NOT_LENT,
    )
    borrow_audience = models.CharField(
        max_length=20,
        choices=NPCBorrowAudience.choices,
        default=NPCBorrowAudience.GMS,
        help_text="Who may borrow this NPC when it is lent.",
    )
    notes_for_player = models.TextField(
        blank=True,
        help_text="What the holder wants a borrower to know about playing this NPC.",
    )
    is_template = models.BooleanField(
        default=False,
        help_text="A template NPC: copies are made for a borrower instead of lending it.",
    )

    class Meta:
        verbose_name = "Story NPC Settings"
        verbose_name_plural = "Story NPC Settings"

    def __str__(self) -> str:
        return f"StoryNPCSettings({self.roster_entry_id})"


class NPCLoan(RelatedCacheClearingMixin, SharedMemoryModel):
    """One loan of a major NPC to a borrowing account."""

    # Clear the borrower's and the holder's account and PlayerData caches when a loan
    # changes: Account.cached_roster_entries and PlayerData.cached_npc_loans both read it.
    related_cache_fields: ClassVar[list[str]] = [
        "borrower",
        "borrower.player_data",
        "roster_entry.current_tenure.player_data",
        "roster_entry.current_tenure.player_data.account",
    ]

    roster_entry = models.ForeignKey(
        "arxii.RosterEntry",
        on_delete=models.CASCADE,
        related_name="npc_loans",
    )
    borrower = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.CASCADE,
        related_name="npc_loans_borrowed",
    )
    offered_by = models.ForeignKey(
        "accounts.AccountDB",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="The account that made the offer or took the request.",
    )
    scene = models.ForeignKey(
        "arxii.Scene",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="npc_loans",
        help_text="The scene this loan is for, if it was lent for one.",
    )
    status = models.CharField(
        max_length=20,
        choices=NPCLoanStatus.choices,
        default=NPCLoanStatus.OFFERED,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["roster_entry"],
                condition=Q(status=NPCLoanStatus.ACTIVE),
                name="one_active_npc_loan_per_entry",
            ),
        ]

    def __str__(self) -> str:
        return f"NPCLoan({self.roster_entry_id} -> {self.borrower_id}, {self.status})"
