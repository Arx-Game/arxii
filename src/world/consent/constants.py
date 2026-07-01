"""Consent system constants."""

from django.db import models


class ConsentMode(models.TextChoices):
    """Who may target a character with a given social-action category.

    The four modes span the permissive→restrictive axis:

    - ``EVERYONE`` — anyone may target (default-allow).
    - ``ALL_BUT_BLACKLIST`` — anyone *except* people on this category's antagonism
      blacklist (default-allow with exceptions). The "I'll RP with anyone, but not
      *that* person" setting (#1698).
    - ``FRIENDS_WHITELIST`` — only OOC friends (``scenes.Friendship``) plus anyone on
      the explicit per-category whitelist (default-deny, friends auto-pass) (#1698).
    - ``ALLOWLIST`` — only actors on the explicit per-category whitelist (strict
      default-deny; friendship alone is not enough).
    """

    EVERYONE = "everyone", "Everyone"
    ALL_BUT_BLACKLIST = "all_but_blacklist", "Everyone except my blacklist"
    FRIENDS_WHITELIST = "friends_whitelist", "Friends and my whitelist"
    ALLOWLIST = "allowlist", "Allowlist only"
