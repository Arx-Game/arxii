# ADR-4321: Presence is a server fact; a tab's socket is its fast path

**Status:** Accepted (#4321, 2026-10-13). Amends ADR-0295 (navigation keeps presence; the
menu item renamed) and ADR-0241 (selection is not presence).

**Context.** ApostateCD opened the character sheet from the game's top bar, which lands in a
new browser tab to protect the socket, and that tab's header chip and Hall card said "Not in
the world" about a character standing in a room in the tab beside it. #3859 had made the chip
read the tab's own socket store (`gameSlice.sessions[name].isConnected`) instead of the route,
which was right for one tab and wrong for two: a fresh tab has a fresh store that never opened
a socket, and nothing on the roster payload said otherwise. The same gap made "Enter the
world" and "Leave the world" mean different things in different tabs.

**Decision.** A character is in the world while a session puppets it, and only the server
knows that for every tab and device, so the roster `mine` payload carries `session_count` and
`room_name`, read from Evennia's session handler (`world.roster.services.presence`), never a
column. The client has one presence rule, `useCharacterPresence`: this tab's socket first
(correct the instant it opens or closes, and the only source of the room while a session is
still entering), the server's count when the tab has none. Every surface that states presence
reads it there. "Return to the world" from a tab without a socket opens another socket on the
same character (`MULTISESSION_MODE = 3` joins; both move the same body). "Disconnect
Character" closes this tab's socket when it has one and one session; asks the server to close
every session (`POST /api/roster/entries/{id}/disconnect/`, each with the `quit` reason the
client already reads as leaving) when the tab has none; and offers "This connection" /
"Every connection" only when it has a socket and the character has another session. The `/`
redirect keeps reading the local socket alone, so a fresh tab is never pulled into the game
because the character is in the world elsewhere.

*Rejected:* syncing the socket store across tabs with a BroadcastChannel. It would have
answered the symptom for tabs in one browser and nothing for a second computer, and it would
have made a browser-side copy the source of a fact the server owns. *Rejected:* a new close
reason or frame type for the everywhere disconnect; `quit` is what it is, and the parity test
on `SERVER_QUIT_CLOSE_REASONS` already pins the client to it.

**Consequences.** Two read-only fields and one endpoint on the roster API; the header polls the
roster list every 30 s while a chip is up and the socket hook refetches it on open and close.
The vocabulary is "Log Out Account" and "Disconnect Character" everywhere (world menu, profile
dropdown, chip), so logging out never reads as leaving the world. The Who tab's Online list
opens the account menu from the player's own name, in-tab, so nobody needs a second window to
reach their sheet; the top bar's sheet icon stays. The form switcher is drawn only once there
is a form to switch to.
