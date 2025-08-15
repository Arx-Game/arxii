"""
PlayerMail model for roster-based mail system.
"""

from django.db import models
from django.utils import timezone


class PlayerMail(models.Model):
    """
    Mail system with tenure targeting.
    Players send "mail Ariel" → routes to current player via RosterTenure.
    """

    # Sender info via tenure
    sender_tenure = models.ForeignKey(
        "roster.RosterTenure",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_mail",
        help_text="Tenure used when sending the mail",
    )

    # Recipient info (references tenure for anonymity)
    recipient_tenure = models.ForeignKey(
        "roster.RosterTenure",
        on_delete=models.CASCADE,
        related_name="received_mail",
        help_text="Mail targets the character, routes to current player via roster entry",
    )

    # Mail content
    subject = models.CharField(max_length=200)
    message = models.TextField()

    # State tracking
    sent_date = models.DateTimeField(auto_now_add=True)
    read_date = models.DateTimeField(null=True, blank=True)
    archived = models.BooleanField(default=False)

    # Thread support
    in_reply_to = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="replies"
    )

    @property
    def is_read(self):
        """True if recipient has read this mail"""
        return self.read_date is not None

    def mark_read(self):
        """Mark mail as read"""
        if not self.is_read:
            self.read_date = timezone.now()
            self.save()

    def get_thread_messages(self):
        """Get all messages in this thread"""
        # Find root message
        root = self
        while root.in_reply_to:
            root = root.in_reply_to

        # Get all replies in chronological order
        return PlayerMail.objects.filter(
            models.Q(pk=root.pk) | models.Q(in_reply_to=root)
        ).order_by("sent_date")

    def __str__(self):
        sender = (
            self.sender_tenure.player_data.account.username
            if self.sender_tenure
            else "Unknown"
        )
        recipient = (
            self.recipient_tenure.roster_entry.character.name
            if self.recipient_tenure
            else "Unknown"
        )
        return f"Mail from {sender} to {recipient}"

    class Meta:
        ordering = ["-sent_date"]
        indexes = [
            models.Index(fields=["recipient_tenure", "read_date"]),
            models.Index(fields=["sender_tenure", "sent_date"]),
        ]
