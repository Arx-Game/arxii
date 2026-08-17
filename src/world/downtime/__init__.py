"""Scheduled-downtime announcements (#3194).

Staff declare maintenance windows; the host's own scheduled reboot
(unattended-upgrades) feeds the same announcement mechanism by being read
from systemd's scheduled-shutdown file rather than typed twice.
"""
