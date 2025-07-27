"""
Extensions to Evennia models.
This app extends Evennia's core models rather than replacing them.
"""

from django.db import models
from evennia.accounts.models import AccountDB
from evennia.objects.models import ObjectDB


class PlayerData(models.Model):
    """
    Extends Evennia's AccountDB with additional player data.
    Uses evennia_extensions pattern instead of replacing Account entirely.
    Replaces all ArxI attribute usage with proper model fields.
    """

    account = models.OneToOneField(
        AccountDB,
        on_delete=models.CASCADE,
        related_name="player_data",
        primary_key=True,
    )

    # Player preferences (replaces attributes like db.hide_from_watch)
    display_name = models.CharField(
        max_length=100, blank=True, help_text="How they appear to others"
    )
    karma = models.PositiveIntegerField(default=0)
    hide_from_watch = models.BooleanField(default=False)
    private_mode = models.BooleanField(default=False)

    # Staff data
    gm_notes = models.TextField(blank=True, help_text="Staff notes about player")

    # Session tracking (replaces attributes)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    # Timestamps
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    def get_available_characters(self):
        """Returns characters this player can currently play"""
        return ObjectDB.objects.filter(
            tenures__player_data=self,
            tenures__end_date__isnull=True,
            roster_entry__isnull=False,  # Must be rostered character
        )

    def __str__(self):
        return f"PlayerData for {self.account.username}"

    class Meta:
        verbose_name = "Player Data"
        verbose_name_plural = "Player Data"


class PlayerAllowList(models.Model):
    """
    Players this account allows to contact them (friends/allowlist).
    """

    owner = models.ForeignKey(
        PlayerData, on_delete=models.CASCADE, related_name="allow_list"
    )
    allowed_player = models.ForeignKey(
        PlayerData, on_delete=models.CASCADE, related_name="allowed_by"
    )
    added_date = models.DateTimeField(auto_now_add=True)
    notes = models.CharField(
        max_length=200, blank=True, help_text="Optional note about this player"
    )

    def __str__(self):
        return f"{self.owner.account.username} allows {self.allowed_player.account.username}"

    class Meta:
        unique_together = ["owner", "allowed_player"]
        verbose_name = "Player Allow List Entry"
        verbose_name_plural = "Player Allow List Entries"


class PlayerBlockList(models.Model):
    """
    Players this account blocks from contacting them.
    """

    owner = models.ForeignKey(
        PlayerData, on_delete=models.CASCADE, related_name="block_list"
    )
    blocked_player = models.ForeignKey(
        PlayerData, on_delete=models.CASCADE, related_name="blocked_by"
    )
    blocked_date = models.DateTimeField(auto_now_add=True)
    reason = models.CharField(
        max_length=200, blank=True, help_text="Optional reason for blocking"
    )

    def __str__(self):
        return f"{self.owner.account.username} blocks {self.blocked_player.account.username}"

    class Meta:
        unique_together = ["owner", "blocked_player"]
        verbose_name = "Player Block List Entry"
        verbose_name_plural = "Player Block List Entries"
