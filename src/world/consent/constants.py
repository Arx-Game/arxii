"""Consent system constants."""

from django.db import models


class ConsentMode(models.TextChoices):
    """Who may target a character with a given social-action category.

    The modes span the permissive→restrictive axis:

    - ``EVERYONE`` — anyone may target (default-allow).
    - ``ALL_BUT_BLACKLIST`` — anyone *except* people on this category's antagonism
      blacklist (default-allow with exceptions). The "I'll RP with anyone, but not
      *that* person" setting (#1698).
    - ``FRIENDS_WHITELIST`` — only OOC friends (``scenes.Friendship``) plus anyone on
      the explicit per-category whitelist (default-deny, friends auto-pass) (#1698).
    - ``RIVALS`` — only your **declared mutual rivals** (``scenes.Rivalry``, double
      opt-in) plus the per-category whitelist. The "bring it on, but only from the
      characters I've agreed to feud with" setting (#2170).
    - ``ALLOWLIST`` — only actors on the explicit per-category whitelist (strict
      default-deny; friendship/rivalry alone is not enough).
    """

    EVERYONE = "everyone", "Everyone"
    ALL_BUT_BLACKLIST = "all_but_blacklist", "Everyone except my blacklist"
    FRIENDS_WHITELIST = "friends_whitelist", "Friends and my whitelist"
    RIVALS = "rivals", "My declared rivals (and whitelist)"
    ALLOWLIST = "allowlist", "Allowlist only"
