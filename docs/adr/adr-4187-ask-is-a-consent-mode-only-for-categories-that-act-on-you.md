# Ask is a consent mode, offered only by categories whose deed waits for your answer

**Status:** Accepted (2026-10-07) · **Issue:** #4187

A makeover of another player's character (hair dye, a cut, lenses) was refused for everyone:
the `makeover` consent category defaulted to allowlist, and nothing created the row. The
maintainer ruled the right default is to **ask**: the target is told what is offered and grants
or declines, with a setting of Ask me (default), Always allow or Never, plus the category's
existing whitelist (skip the ask) and blacklist (always refuse) for specific people. We added
one `ConsentMode` member, `ASK`, and one flag on the category, `asks_before_acting`, and made
the decision three-valued (`consent_outcome` → ALLOW / ASK / REFUSE) with the old yes/no gate
as its REFUSE face. `ASK` is offered in the Privacy picker, and accepted by the rule
serializer, only for a category whose `asks_before_acting` is set; on every other category it
reads as EVERYONE. The reason is that the five social-action modes answer a different
question, *who may ask*, because a flirt or an intimidation already prompts the target for any
permitted actor; "ask me" would be a no-op there and a trap in the picker. A makeover is the
first deed where the action itself waits, so the mode means something only where the flag is
set. **Rejected:** keeping the five modes as "who gets through without a prompt" and adding a
per-category ask/refuse switch for everyone else, which is more expressive and much harder to
explain to a player choosing a setting; and a makeover-only tri-state outside `ConsentMode`,
which would have left the whitelist and blacklist, the inheritance walk and the telnet summary
unable to see it. **Also rejected:** a `RunPython` migration to create the `makeover` row on
production; the repo bans seed rows in migrations (ADR-0013), so the row ships in the seed for
empty databases and is named by the staff dashboard's required-content sentinel on populated
ones. The ask itself is its own small row (`MakeoverConsentRequest`), not a `SceneActionRequest`,
which needs a scene and carries a contested-roll response that means nothing for a haircut.
