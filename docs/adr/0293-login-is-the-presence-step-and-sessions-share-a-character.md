# ADR-0293: Login is the presence step, sessions share a character, and puppeting records the selection

Logging in used to land every player on Evennia's stock OOC screen (``charcreate``, ``ic <name>``
...) and wait for ``@ic``: ``AUTO_PUPPET_ON_LOGIN`` was off and ``Account.at_post_login`` said, in
so many words, "let player choose via @ic". #3812 removes that step. Who a player is playing is
decided before they connect — the durable ``PlayerData.selected_entry`` on the web (ADR-0241), the
last character on telnet — so ``at_post_login`` resolves it (selection, then Evennia's
``_last_puppet``, then a sole character; several with nothing recorded gets a one-line list, never a
silent first pick) and puppets it on every protocol. ``@ic`` remains for switching and is idempotent
for the session's own puppet, so the web client's ``@ic <name>`` on socket-open is a safety net
rather than the thing entry depends on. Two decisions ride with it. **Sessions share a character**:
``MULTISESSION_MODE`` goes from 2 to 3 and ``MAX_NR_SIMULTANEOUS_PUPPETS`` to unlimited, because a
phone and a laptop on the same character are two windows onto one ``Character`` object, and it does
not matter which one you type in (Arx 1 worked this way; ``who`` already blurs idle so alts cannot
be correlated). Hooks that assumed one window per character now fire per *character*: the friends
"came online" alert and the offline story catch-up on the first session, "gone offline" and the
presence-buff clear on the last. **Puppeting records the selection** through ``set_selected_entry``:
taking a character up is the most explicit choice a player makes, so it becomes the one fact the
website shows and the next login resolves. That amends ADR-0241 in one direction only — selecting
still never puppets. We rejected keeping mode 2's takeover (a half-dead socket blocked a reconnect
until it timed out, and the second tab sat at "Entering world" forever), rejected auto-puppeting
only for telnet (two entry contracts for one game), and rejected Evennia's own
``AUTO_PUPPET_ON_LOGIN`` (it puppets ``_last_puppet`` blindly and raises when there is none).

> Status: accepted · Source: issue #3812, the reviewer's 2026-09-12 ruling in session · Amends
> ADR-0241 (puppeting now selects; selecting still never puppets) · Related #3412, #3752, #3596
