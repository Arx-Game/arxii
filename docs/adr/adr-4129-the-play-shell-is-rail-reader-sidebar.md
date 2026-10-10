# ADR-4129: The play shell is rail, reader, sidebar

**Status:** Accepted (2026-10-10, ApostateCD)
**Issue:** #4129
**Related:** #3758 (one reader, one contextual sidebar), #2165 (conversation tabs), #4128
(poses as prose), #3299 (channels)

## Context

#3758 composed `/game` as one wide reader with one contextual sidebar, and put the
scene's conversations behind that sidebar's Conversations mode; #2165 let several of them
open at once as a tab strip above the feed. Nothing listed a quiet room's whispers or a
page at all, and the kind chips (#3856) and the conversation tabs were two filters on one
column with no stated relationship. The maintainer's ruling, after seven demo rounds: the
chips on top are the filter by kind, and the left is the specific conversations a player
might want to see alone.

## Decision

The play shell is three columns: the **conversation rail** on the far left (200 to 320px,
or a 44px strip of counts), the reader and composer, and the contextual sidebar (Here and
History). The rail lists every conversation the current character is in, grouped (Here,
OOC Pages, Channels reserved), and **one row is selected at a time**: a picked row shows
that conversation alone and in full, clears its count, and locks the composer to it; All
is the whole feed; the chips keep filtering by kind inside whichever is selected. The rail
is built from the live session (the scene's threads, the quiet room's interactions grouped
the same way, the session's typed page frames), never from the stored-conversations API,
so everything not tied to a scene starts empty at login. The tab strip, the sidebar's
Conversations mode and the persisted open-tab layout are removed rather than kept beside
the rail.

## Consequences

One conversation at a time: a player who kept three whisper tabs now switches rows. The
reader's empty measure margin became the rail, which never scrolls with the feed and has
a pane of its own below 960px. A page is a typed `text` frame with its correspondent
(`CmdPage`), still a note, still never stored. Channels in the rail wait on #3299's owner,
whose approved spec puts them in a right-hand tab.

## Alternatives rejected

- **The rail inside the story pane** scrolls with the feed and has nowhere to go on a
  narrow screen.
- **Rows from the stored-conversations API** would mean "refreshed at login" is a server
  query, and the API knows nothing of pages.
- **Keeping the tab strip beside the rail** keeps two surfaces for one selection, the
  shape that produced the stale-audience mis-send #2165 had to guard against.
