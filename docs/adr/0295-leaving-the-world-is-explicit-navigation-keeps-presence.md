# ADR-0295: Leaving the world is explicit; navigation keeps presence; nobody enters nowhere

**Status:** Accepted (#3818, 2026-09-13). Amends ADR-0241 (selection is not presence)
and ADR-0294 (puppeting records selection); related ADR-0247 (state-3 mode coherence,
the `/` redirect), #2121 (guaranteed starting room), #3813.

**Context.** Apostate's first production login after #3813 landed on a `/game` screen
that waited forever for a location, behind a hamburger that flickered and did nothing.
Three things were true at once: the character had no location, no
`prelogout_location` and no `home`, so Evennia's `DefaultCharacter.at_pre_puppet`
left them nowhere; the canonical fallback room had been renamed "City Center" by staff,
so the by-name lookup #2121 wired into `CharacterDraft.get_starting_room` missed it;
and the top-bar "menu" was a `<Link to="/">`, which ADR-0247's redirect sends straight
back to `/game` for anyone with a live connection. Fixing the menu raised the question
this ADR records: what does leaving `/game` mean for the character on the grid.

**Decision 1: The fallback room is an identity, never a name.** Every reader of the
canonical fallback starting room goes through
`world.character_creation.services.resolve_fallback_starting_room`, which finds it by
`RoomProfile.fixture_key == "arx/fallback-starting-room"` and falls back to the seeded
name only for a room seeded before fixture keys existed. The seeder reuses whatever that
resolves to, so a rename never mints a second room. Staff own the room's name; code owns
its key.

*Rejected:* teaching the seeder to rename the room back, or documenting "do not rename
The Wanderer's Rest". Names are the staff's to change (the Atlas edits them in place);
a code invariant that depends on a name the admin lets anyone edit is already broken.

**Decision 2: A character with nowhere to be enters the fallback room.**
`Character.at_pre_puppet` sets `home` to the fallback room when location, restored
location and home are all empty, then lets Evennia's own hook do the move. A logged-in
character with `location=None` is a screen that never completes, a `send_room_state`
that has nothing to send, and a body no one can find; there is no play state in which it
is the right answer. This is the third tier of #2121's guarantee, applied at puppet time
rather than only at finalize.

*Rejected:* a client-side "you are nowhere, pick a room" affordance. The player has no
information to choose with and the game has a canonical answer; making them pick is
making them debug.

**Decision 3: Navigating away keeps a character in the world; leaving is explicit.**
Sessions and sockets live in Redux/module scope and `GamePage` has no teardown, so
opening the Hall, the roster or settings from the world menu keeps every character tab
connected and every puppet on the grid; `/game` resumes them. The one way a character
leaves the grid short of logging out is the menu's "Leave the world as <name>"
(`useGameSocket().disconnect(name)`), which closes that character's socket so the server
unpuppets them (the last session on a puppet going is what unpuppets; #3813's shared
sessions mean a second window keeps them present), drops the session, keeps the account
signed in, and keeps the durable selection so offscreen play still knows who the player
is. `useLogout` already closes every socket, so logging out never strands a puppet.

*Rejected:* tearing down sockets on route change. Dan's constraint cuts both ways: players
must be able to do things with their characters when not in the game view, and a
character must never be left puppeted, unpiloted and visible on the grid. Route-change
teardown satisfies the second by breaking the first (the roster page would end the
scene), and it is invisible: the player would not know that opening settings made their
character vanish mid-pose. An explicit item the player chooses satisfies both and is
legible. The residual gap, a browser tab closed without leaving, is a socket close the
server already treats as unpuppet, so nothing is stranded there either.

**Decision 4: `/hall` is a route that never redirects.** ADR-0247's `/` redirect is
correct for the front door and wrong for a menu item; a link whose destination is the
page you are on is a bug, not a shortcut. The Hall now also lives at `/hall`, reachable
from inside the world, and `/` keeps its redirect.

**Consequences.** Renaming the fallback room is safe. A character can be built with no
location and still play. The hamburger is a menu with the exits a player expects, and the
only presence change it makes is one the player asked for by name. Enter sends and
Shift+Enter breaks a line, matching every chat RP client; that was a one-prop override in
`GameWindow` and carries no design weight beyond this note.
