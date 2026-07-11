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


# PLACEHOLDER (agent-drafted onboarding/settings copy — Apostate to rewrite, #2170).
# The "explain the pros and cons of each mode" surface: shown alongside the consent-mode
# picker (web settings + telnet `consent`) so a player chooses their antagonism openness
# understanding the trade-off, rather than being silently defaulted. Keyed by ConsentMode value.
CONSENT_MODE_GUIDANCE: dict[str, str] = {
    ConsentMode.EVERYONE.value: (
        "Wide open: anyone may do this to you. Most spontaneous conflict and story, but you "
        "can't refuse a particular player short of blocking them outright."
    ),
    ConsentMode.ALL_BUT_BLACKLIST.value: (
        "Open, with exceptions: anyone may do this to you except the specific people you list. "
        "Good when you're happy to be antagonised in general but not by one or two players."
    ),
    ConsentMode.FRIENDS_WHITELIST.value: (
        "Opt-in: only your OOC friends (and anyone you add to this category's allow list) may do "
        "this to you. The safe default — antagonism comes only from players you already trust."
    ),
    ConsentMode.RIVALS.value: (
        "Feuds only: only characters you've each declared a mutual rival (plus your allow list) "
        "may do this to you. Choose this to invite antagonism, but only from partners you've both "
        "agreed to feud with."
    ),
    ConsentMode.ALLOWLIST.value: (
        "Locked down: only the specific people you add to this category's allow list may do this "
        "to you — friendship or rivalry alone is not enough. The strictest setting."
    ),
}


def consent_mode_guidance() -> list[dict[str, str]]:
    """Mode picker rows — ``{value, label, guidance}`` in permissive→restrictive order (#2170).

    The read surface both the web settings page and the telnet ``consent`` help render so a
    player sees what each mode means before choosing. Order matches the ConsentMode axis.
    """
    return [
        {"value": mode.value, "label": mode.label, "guidance": CONSENT_MODE_GUIDANCE[mode.value]}
        for mode in ConsentMode
    ]
