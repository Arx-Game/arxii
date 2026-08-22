"""Models for tavern games: coin-stakes dice gambling at a Place (#3292).

``TavernGame`` rows are curated, staff-authored content (one dice game at
MVP). ``GameSession`` is a live table at a scene ``Place``; ``GameSeat`` is
one persona's seat at that table. Money only ever moves through
``world.currency.services.transfer`` - the session's ``pot`` is an escrow
integer, never a parallel ledger (see ``services.py``'s module docstring).
"""

from __future__ import annotations

from django.db import models
from evennia.utils.idmapper.models import SharedMemoryModel

from core.managers import ArxSharedMemoryManager
from core.natural_keys import NaturalKeyManager, NaturalKeyMixin
from world.tavern_games.constants import GameResolutionKind, GameSessionState

CHARACTER_SHEET_MODEL = "arxii.CharacterSheet"


class TavernGame(NaturalKeyMixin, SharedMemoryModel):
    """Authored coin-stakes game vocabulary. One row at MVP: a dice contest."""

    name = models.CharField(max_length=100, unique=True)
    rules_blurb = models.TextField(
        blank=True,
        help_text="Player-facing rules summary shown before opening a session.",
    )
    min_ante = models.PositiveIntegerField(
        default=1,
        help_text="Smallest ante an opener may set, in coppers.",
    )
    max_ante = models.PositiveIntegerField(
        default=1000,
        help_text="Largest ante an opener may set, in coppers.",
    )
    resolution_kind = models.CharField(
        max_length=30,
        choices=GameResolutionKind.choices,
        default=GameResolutionKind.HIGHEST_ROLL,
    )
    is_active = models.BooleanField(default=True)

    objects = NaturalKeyManager()

    class NaturalKeyConfig:
        fields = ["name"]

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class TavernGamblingConfig(SharedMemoryModel):
    """Singleton (pk=1) - the PLACEHOLDER weekly loss cap (#3292).

    Mirrors ``world.gm.models.GMRewardConfig``'s singleton shape: a single
    staff-editable row rather than a hardcoded module constant, so the cap
    can be tuned without a deploy.
    """

    objects = ArxSharedMemoryManager()

    weekly_loss_cap = models.PositiveIntegerField(
        default=500,
        help_text=(
            "PLACEHOLDER - coppers a character may ante into tavern games in one "
            "IC week. Winnings do not offset it (#3292 decision 4)."
        ),
    )

    class Meta:
        verbose_name = "Tavern Gambling Config"
        verbose_name_plural = "Tavern Gambling Config"

    @classmethod
    def load(cls) -> TavernGamblingConfig:
        """Fetch (or lazily create) the singleton row."""
        obj = cls.objects.cached_singleton()
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self) -> str:
        return f"TavernGamblingConfig(cap={self.weekly_loss_cap})"


class GameSession(SharedMemoryModel):
    """A live table: one game, one Place, an escrowed pot, and seated players."""

    place = models.ForeignKey(
        "arxii.Place",
        on_delete=models.CASCADE,
        related_name="tavern_game_sessions",
    )
    game = models.ForeignKey(
        TavernGame,
        on_delete=models.PROTECT,
        related_name="sessions",
    )
    state = models.CharField(
        max_length=20,
        choices=GameSessionState.choices,
        default=GameSessionState.OPEN,
    )
    ante = models.PositiveIntegerField(help_text="Fixed ante every seat pays to join, in coppers.")
    pot = models.PositiveIntegerField(
        default=0,
        help_text="Coppers currently escrowed at the table (sum of unrefunded antes).",
    )
    opened_by = models.ForeignKey(
        "arxii.Persona",
        on_delete=models.CASCADE,
        related_name="opened_tavern_game_sessions",
    )
    opened_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-opened_at"]

    def __str__(self) -> str:
        return f"{self.game.name} @ {self.place.name} ({self.get_state_display()})"


class GameSeat(SharedMemoryModel):
    """One persona's seat at a ``GameSession``: their ante and (once rolled) result."""

    session = models.ForeignKey(
        GameSession,
        on_delete=models.CASCADE,
        related_name="seats",
    )
    persona = models.ForeignKey(
        "arxii.Persona",
        on_delete=models.CASCADE,
        related_name="tavern_game_seats",
    )
    ante_paid = models.PositiveIntegerField()
    roll_result = models.PositiveSmallIntegerField(null=True, blank=True)
    seated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["seated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "persona"],
                name="unique_seat_per_session_persona",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.persona.name} at session #{self.session_id}"


class GamblingLossLedger(SharedMemoryModel):
    """One character's tavern-game ante spend for one IC week (#3292 decision 4).

    Shape mirrors ``world.currency.models.PurseDrainWeek``: one row per
    (character_sheet, game_week), created on first ante of the week. Every
    ante, win or lose, adds to ``total_lost``; winnings never subtract
    from it (the simplest honest read of "a weekly loss cap").
    """

    character_sheet = models.ForeignKey(
        CHARACTER_SHEET_MODEL,
        on_delete=models.CASCADE,
        related_name="gambling_loss_ledgers",
    )
    game_week = models.ForeignKey(
        "arxii.GameWeek",
        on_delete=models.CASCADE,
        related_name="gambling_loss_ledgers",
    )
    total_lost = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-game_week"]
        constraints = [
            models.UniqueConstraint(
                fields=["character_sheet", "game_week"],
                name="unique_gambling_loss_ledger_per_sheet_week",
            ),
        ]

    def __str__(self) -> str:
        return f"GamblingLossLedger(sheet={self.character_sheet_id}, lost={self.total_lost})"
