# Boards glossary

**Board**:
The model (`Board`) anchoring a persistent bulletin surface to exactly one of two
places: a room (LOCATION board, riding the Notice Board room feature) or an
organization (ORG board). Never anchored to both, never to neither (DB check
constraint). One board per anchor - a room or org cannot carry two.
_Avoid_: bboard, bulletin board system, BBS (Arx I naming this app deliberately
does not reuse).

**Notice**:
The player-facing name for a `BoardPost` - a signed, exact-text, persistent
message pinned to a Board. "Notice" is the in-fiction word ("pin a notice to
the board"); `BoardPost` is the model name. Distinct from a rumor (#2986) -
a rumor distorts and spreads on its own; a notice is deliberate and never
mutates once posted (only the author can edit it).
_Avoid_: post (ambiguous with journal/table-bulletin posts elsewhere in the
codebase - qualify as "board post" or "notice" in code and docs), message
(reserve for narrative/mail systems), announcement (the Notice Board room
feature's read-only tidings hint uses this word for a different, derived
surface - see Tidings below).

**LOCATION board**:
A `Board` anchored to a `RoomProfile` - physically standing in the room
(NOT merely having visited it, and not remote access) is required to pin a
notice or to remove your own. Reading is public; no presence check applies
to reading.
_Avoid_: room board, public board (a LOCATION board is public by construction,
but "public board" invites confusion with a hypothetical realm-wide board
this system does not have).

**ORG board**:
A `Board` anchored to an `Organization`. Posting requires the poster's
active `OrganizationMembership.rank.can_post_to_board`; removing another
member's notice requires `can_moderate_board` or staff. Reading is
membership-gated on both web and API - a non-member's list/retrieve calls
return nothing, not a permission error (silent, not confirming the board's
existence to outsiders).
_Avoid_: org bulletin (see Notice's _Avoid_ note - this app's board/notice
vocabulary supersedes "bulletin" outside `TableBulletinPost`, which is a
separate, GM-only, OOC system this app does not touch).

**Tidings** (adjacent term, defined in `world/tidings/`):
The Notice Board room feature's OTHER surface - a derived, read-only feed of
deeds/scandals/menace/proclamations (`tidings local`). Boards and Tidings
share a room feature (NOTICE_BOARD) but are entirely separate data: Tidings
is computed and never player-written; a Board's Notices are player-authored
and persistent. See the "Tidings / Public-reaction feed" entry in `docs/systems/INDEX.md` and
`docs/systems/boards.md`.
