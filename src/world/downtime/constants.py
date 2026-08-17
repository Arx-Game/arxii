"""Constants for scheduled-downtime announcements (#3194)."""

from django.db import models


class DowntimeSource(models.TextChoices):
    """Where an announced window came from."""

    STAFF = "staff", "Staff-declared window"
    SYSTEM = "system", "Automatic host reboot"


# The banner copy for a derived host reboot; staff windows carry their own message.
SYSTEM_REBOOT_MESSAGE = "Automatic security update: the server will restart briefly."

# unattended-upgrades reboots take about two minutes end to end (observed
# 2026-08-16); five minutes is a safe player-facing expectation.
SYSTEM_REBOOT_DURATION_MINUTES = 5
