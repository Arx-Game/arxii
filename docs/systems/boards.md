# Boards (#3286)

Player-postable bulletin boards: a character can pin a written notice to a
board and other characters read it. Two board kinds share one model pair -
public boards physically located in a room (the shipped Notice Board room
feature) and org-internal boards visible to members from the org page.
Boards were a core Arx I information-economy surface (event advertisements,
proclamations, org coordination, commerce) that Arx II had a read side for
(`tidings`) and a room fiction for (Notice Board) but nothing a player could
write to.

Not a duplicate of two adjacent surfaces: **#2986 rumors** are the
*distorting* channel - planted content that spreads and mutates with heat.
A board post is the *deliberate* channel - signed, exact-text, persistent,
audience-scoped. **`TableBulletinPost`** is a real post/reply board, but
GM-only posting, OOC, and table-scoped (`world/stories/permissions.py`) -
different user goal, untouched by this system.

## Models (`world.boards.models`)

- **`Board`** - anchored to EITHER `room_profile` (`evennia_extensions.RoomProfile`,
  nullable) OR `organization` (`societies.Organization`, nullable), never
  both/neither: a DB `CheckConstraint` (XOR) plus a per-anchor
  `UniqueConstraint` (one board per room, one per org - mirrors
  `RoomFeatureInstance`'s one-per-room shape). `name`, `max_active_posts`
  (default 30) - the newest-first display cap; older posts fall off the
  display but are retained in the DB. No auto-expiry at MVP (Decision 5) -
  IC-time expiry is deferred, hangs off the existing `game_clock` task seam
  when wanted.
- **`BoardPost`** - `board` FK, `author_persona` FK (`scenes.Persona` - IC
  authorship; a masked persona posts under its false identity, consistent
  with the 2026-08-19 IC/OOC messaging split ruling), `title`, `body`,
  `created_at`, `edited_at`, and soft-delete fields `removed_by_persona`
  (nullable FK, `SET_NULL`) / `removed_at`. `Meta.ordering = ["-created_at"]`.
  Moderation is always a soft-delete - story-significant data is never
  hard-deleted.

Two new booleans on `societies.OrganizationRank`: `can_post_to_board`
(every rung of the default five-tier ladder grants it - org boards are
rank-and-file coordination, not a leadership-only megaphone) and
`can_moderate_board` (leadership-only by default - tier 1, mirroring
`can_manage_ranks`'s shape).

## Permissions (`world.boards.services`)

Permission logic lives in the service layer, not the Actions/viewsets that
call it (mirrors `world.covenants`) - every mutator raises a typed
`BoardError` on refusal (`world/boards/types.py`), mapped to a user-facing
`ActionResult`/API error by the caller:

| Board kind | Post | Remove own | Remove another's |
|---|---|---|---|
| LOCATION | present in the board's room | present in the board's room | staff only |
| ORG | active membership with `can_post_to_board` | active membership (no presence check) | `can_moderate_board` rank, or staff |

Editing your own post (`edit_board_post`) is author-only on both board
kinds - presence is **not** required to edit, only to post or remove-own on
a LOCATION board (Decision 3: you must be physically at the board to pin or
take down a notice, but a typo fix doesn't require walking back).

Read helpers: `visible_posts_for_board` (active, newest-first, capped to
`max_active_posts`) and `exclude_blocked_and_muted_board_authors`, which
mirrors `journals.services.exclude_blocked_and_muted_authors`'s batched
roster-tenure walk - an account-level Block hides posts both directions, an
account-level Mute narrows only the muter's own feed.

## Room-feature integration

A LOCATION board rides the existing NOTICE_BOARD room feature
(`world.room_features`, #1450). `room_features.services.handle_notice_board_progression`
get-or-creates the board row when the feature installs; `PostToBoardAction`
also lazily get-or-creates it at first post, so a room whose Notice Board
predates #3286 still gets a working board the first time someone posts.

## Actions, telnet, API

- **Actions** (`actions/definitions/boards.py`, ADR-0001): `PostToBoardAction`,
  `EditBoardPostAction`, `RemoveBoardPostAction` - thin wrappers over the
  services, `BoardError` → failure `ActionResult(exc.user_message)`.
- **Telnet** (`commands/boards.py`): `CmdBoard` - `board` (list), `board read
  <n>`, `board post <title>=<body>`, `board remove <n>`, scoped to the
  LOCATION board in the caller's current room (org boards have no telnet
  surface - the web OrgPage Board section is their front door; both routes
  dispatch the same Actions).
- **API** (`world/boards/views.py`): `BoardViewSet` / `BoardPostViewSet`,
  read-only (list/retrieve) - writes always go through action dispatch, never
  a viewset `create`/`update`/`destroy`. ORG board visibility is gated on
  active `OrganizationMembership` (mirrors `tasking.views.OrgTaskViewSet`);
  LOCATION boards are public reads.
- **Web:** `boards/components/BoardPanel.tsx` is the shared read/post
  widget, mounted from both the room panel (`game/components/RoomPanel.tsx`,
  when the room's hub is a NOTICE_BOARD) and the OrgPage Board section
  (`orgs/pages/OrgPage.tsx`).
- **Examine:** `actions/definitions/examine_extras.py`'s room section
  renders the LOCATION board's current postings (numbered, author-attributed)
  under the existing Notice Board hint line - the telnet/web `look` output
  for a Notice Board room now shows the actual notices, not just the hint.

## Poster identity

A post's author renders via the same per-viewer persona display resolution
used everywhere else (`scenes.persona_display.resolve_display_for_viewer`):
an anonymous/masked persona shows the mask (or a composed sdesc if
undiscovered), a discovered mask reveals `"<mask> (<real>)"`, staff see
through every mask. See `docs/adr/0228-board-posts-are-authored-by-persona.md`
for why authorship is IC (persona), not OOC (account).

## Tests

`world/boards/tests/` - model constraints (XOR anchor, per-anchor
uniqueness, soft-delete queryset), service permission/soft-delete/block-mute
tests, API read-gating tests. `actions/tests/test_board_actions.py` -
Action-level wrapping. `integration_tests/pipeline/test_boards_telnet_e2e.py`
- one full journey per board kind (post → read as the right audience →
denied as the wrong audience → moderate).
