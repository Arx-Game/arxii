# Player Channels (#3299)

Persistent named out-of-character chat: one curated PUBLIC channel, one ORG
channel for each non-covert organization, and optional STAFF channels. A player
reads and posts from a right-hand "Channels" mode in the play sidebar, from a
standalone `/channels` page, or from telnet. Each player speaks as a roster
tenure they choose per channel; an account name is never stored on a message or
shown anywhere. Each player tunes each channel (join, mute, collapse,
notification level, order), so channels never crowd IC play.

Channels are **OOC only.** IC speech (say, pose, whisper) lives in scenes and
never touches this system. The decisions and their rejected alternatives are in
[ADR-3299](../adr/adr-3299-player-channels-tenure-identity.md).

**Evennia channels are retired.** Before #3299 the game inherited Evennia's
stock `@channel` command and its IRC/RSS/Grapevine/Discord bridge commands from
the account cmdset, and #1884 kept an Evennia `house_<pk>` channel per house.
All of that is gone: the stock and bridge commands are removed from the
`AccountCmdSet` (`commands/default_cmdsets.py`), `DEFAULT_CHANNELS = []`
(`server/conf/settings.py`), and migration `0393_channels_carry_from_evennia`
deleted the Evennia `Public` and `house_*` `ChannelDB` rows, the Attribute rows
they owned, and the channel nicks on accounts. Old Evennia history and
subscriptions were deliberately discarded (Evennia keeps channel lines in log
files only, so there was no history in the database to carry); players opt in
again. `CHANNEL_MUDINFO` stays: it is Evennia's staff connection log, not a
player channel.

## Models (`world.channels.models`)

- **`Channel`** - `name` (unique slot), `description`, `kind`
  (`ChannelKind`: PUBLIC / ORG / STAFF), `organization` (nullable O2O to
  `Organization`, `related_name="ooc_channel"`), `is_active`, `created_at`. DB
  check constraint `channel_org_kind_iff_organization`: an ORG channel has an
  organization and no other kind does. `display_name` is what players see and
  type: an ORG channel reads its organization's name live, so an org rename
  never leaves a stale label (the stored `name` may carry an " (org)" suffix
  from a provisioning clash).
- **`ChannelMessage`** - `channel`, `author_tenure` (FK `RosterTenure`, the
  identity spoken as, frozen at post time), `body`, `created_at`. No account
  column.
- **`ChannelSubscription`** - one per (account, channel): `display_tenure`
  (nullable FK `RosterTenure`, the identity this account speaks as here),
  `muted`, `collapsed`, `notification_level` (`ChannelNotificationLevel`: ALL /
  BADGE / NONE), `sort_order`, `last_read_at`.
- **`ChannelBan`** - one per (channel, account): `banned_by`, `reason`. Its own
  table so a ban outlives the subscription it removes.

Constants (`world.channels.constants`, PLACEHOLDER tunables):
`CHANNEL_HISTORY_CAP = 500`, `CHANNEL_MESSAGE_MAX_LENGTH = 2000`,
`PUBLIC_CHANNEL_NAME = "Public"`. Errors: `world.channels.types.ChannelError`,
always raised with one of its allowlisted player-facing messages
(`exc.user_message`).

## Speaker identity

A speaker is `RosterTenure.speaker_name`: the bare character name for the
first player of a character (`player_number == 1`), else the anonymous
"2nd player of Ariel" form. It is chosen per channel
(`ChannelSubscription.display_tenure`) from the tenures **eligible** for that
channel, and frozen on each message as `author_tenure`.

- **PUBLIC / STAFF:** any current tenure (`end_date IS NULL`) of the account.
- **ORG:** only a current tenure whose character's **primary persona** holds an
  active `OrganizationMembership` (`left_at` and `exiled_at` null) in the
  channel's organization or in a non-covert vassal of it (below). A membership
  held by an established face (an alter ego, a Presumed Dead guise) never
  counts, for eligibility, access or delivery alike: the true character's first
  post would tell the room who the face is.

`default_tenure_for` pre-fills the choice: the account's puppet when it is
eligible, else `PlayerData.selected_entry`'s tenure when no puppet is up. There
is no stored account-wide default. Posting needs a subscription
(`NOT_SUBSCRIBED`), and with no identity set the player must pick one before
the first post (`NO_IDENTITY`). A post re-checks eligibility, so a
tenure that left the org or ended is refused (`INELIGIBLE_IDENTITY`).

The identity picker (`GET /api/channels/channels/<id>/identities/`) lists only
the requester's own eligible tenures. No API serializes another account's
tenures, a message's author account, or its author tenure id.

## Access

`accessible_channels_for(account)` / `can_access_channel(account, channel)`:

- **PUBLIC:** every account.
- **ORG:** account-union, as with codex knowledge (ADR-0221): the account has a
  current tenure eligible as above. The **house vassal cascade from #1884 is
  kept**: members of a vassal house reach the liege's channel
  (`vassals_of(org, recursive=True, include_covert=False)` walking down,
  `FealtyEdge` with `liege__is_covert=False` walking up). A covert vassal cuts
  its whole branch: neither it nor anything sworn under it reaches the liege.
  This replaces the Evennia house channel's `sync_house_channel` audience,
  which is deleted; access is derived live, so there is no audience to sync
  after membership or fealty changes.
- **STAFF:** staff accounts.
- **Staff read every non-covert channel** for moderation (an ORG channel they
  are not a member of included). Posting stays identity-gated: staff with no
  eligible member tenure get `NO_IDENTITY` in an org channel like anyone else.
- **Banned** accounts lose access and cannot re-subscribe or post (`BANNED`,
  checked before access so the reason is the real one).

`findable_channels_for` (reachable, subscribed or banned) is what name and id
lookups resolve against, so an unreachable org channel answers "No such
channel.", the same as a missing one, and never confirms it exists.

**Covert orgs get no channel** (`Organization.is_covert`): a channel roster
would leak membership secrets. **Covenant-backed orgs get no channel** either:
covenant membership is `CharacterCovenantRole`, not `OrganizationMembership`,
so nobody could reach one. `provision_org_channel` returns None for both.

## Provisioning

Explicit calls, no signals. `provision_org_channel(org)` is idempotent and
runs where orgs are made: `build_family_org` (CG name path, noble claim,
Almanach founding), claim materialization and `publish_house`, gang creation
(`turf_services`), the placeholder treasury org (`buildings.services`), and
`OrganizationAdmin.save_model` (every save, so an org staff un-cover gets its
channel). `ensure_public_channel()` makes the PUBLIC row; the `channels` seed
cluster calls it and backfills seeded orgs. Migration 0393 created the Public
channel and one ORG channel per existing non-covert, non-covenant org.

## Reading and delivery

- **History** (`history_for`): newest first, paged (`page_size` 50, max 100).
  Account-muted authors (`world.scenes.mute_services`) are dropped silently.
  Blocked authors (either direction, `world.scenes.block_services`) stay in
  the page as rows with `is_hidden: true`, empty `speaker` and `body`; the
  client folds each run into one "N hidden" divider (`HiddenDivider`, the
  #2087 scene-OOC pattern). Both block shapes count: an account-level block
  (`hidden_author_player_ids`) and a persona-scoped block on the author's
  character's **primary persona** (`hidden_author_sheet_ids`, from
  `hidden_persona_ids_for_viewer`). A block on an established face never hides
  the true character's posts, since that would link the two.
- **Live push** (`deliver_channel_message`, after every post): to each
  subscriber with access who has not muted the channel, is not banned, has no
  block with the author (account-level, or on the author's character's primary
  persona via `block_services.account_ids_hiding_persona`) and has not
  account-muted the author. Web sessions
  (`WEB_PROTOCOL_KEYS`) get one `channel_message` frame
  (`ChannelMessagePayload`: `message_id`, `channel_id`, `channel_name`,
  `speaker`, `body`, `created_at`, `is_own`, and the recipient's
  `notification_level`), never a `text` line, so a channel message never lands
  in the IC feed. Other sessions get the text line
  `[<channel>] <speaker>: <body>`. The author always gets the echo. Hidden-mode
  (`private_mode`) players still get channels.
- **Muted channel** = no push and no unread badge; still readable when opened.
  `notification_level` NONE also zeroes the badge; ALL toasts on the web.
- **Unread** (`unread_counts`): messages after `last_read_at`, not your own,
  not from muted or blocked authors (either block shape above). `subscribe`
  sets `last_read_at` when the subscription is created, so a new subscriber
  starts caught up; `mark_read` sets it; posting marks the channel read. The
  web client refetches the channel list and open lanes when its socket
  reconnects, since frames pushed while it was down never arrived.
- **Staff delete** pushes `channel_message_removed`
  (`ChannelMessageRemovedPayload`: `message_id`, `channel_id`) to subscribers'
  web sessions, and open readers drop the row.
- **Pruning:** history is capped, not archival. The hourly REAL-time
  `channels.prune_history` task (`world.channels.tasks`, `CronPhase.CLEANUP`)
  keeps the newest `CHANNEL_HISTORY_CAP` messages per channel
  (`prune_channel_history`).

## Actions, telnet, API

- **Actions** (`actions/definitions/channels.py`): REGISTRY actions run with
  `actor=None, account=<AccountDB>`, so they work with no puppet:
  `post_to_channel`, `join_channel`, `leave_channel`, `set_channel_mute`,
  `set_channel_identity`, and staff `delete_channel_message` /
  `ban_channel_author`. `account` must be an `AccountDB` instance.
- **`account` is server-supplied.** `dispatch_player_action` strips every key
  in `SERVER_SUPPLIED_KWARGS` (`actions/player_interface.py`) from client
  kwargs, so a websocket or REST dispatch can never name another account.
  Channel actions reached through dispatch therefore always refuse ("You must
  be logged in to use channels."); **web writes go through the REST views**,
  which pass `request.user` as `account`. The same strip closed a forged-account
  hole in the events, ceremonies, dramatic moments, GM standoff and worship
  account-authorized actions.
- **Telnet** (`commands/channels.py`): `CmdChannel` (`channel`, aliases `chan`,
  `channels`; deliberately no `@channel` alias) on the `AccountCmdSet`:
  `channel` / `channel list`, `channel join|leave|mute|unmute <name>`,
  `channel as <name>[=<number>]`, `channel <name>=<message>`. Names match
  case-insensitively on `display_name`. Telnet has no moderation subverbs (its
  lines carry no message ids).
- **API** (`/api/channels/`, `world/channels/views.py`):
  - `channels/` (read-only): the account's accessible channels, each with its
    own `subscription` (or null); `channels/<id>/identities/` (the self-only
    picker).
  - `subscriptions/`: list, POST (join), PATCH (`display_tenure`, `muted`,
    `collapsed`, `notification_level`, `sort_order`), DELETE (leave),
    `subscriptions/<id>/mark-read/`.
  - `messages/?channel=<id>`: history; POST runs `PostToChannelAction`;
    staff DELETE `messages/<id>/` and POST `messages/<id>/ban/` run the
    moderation actions.

## Web

`frontend/src/channels/`: `ChannelsPanel` (joined lanes in `sort_order`, then
`ChannelDirectory` for unjoined channels), `ChannelLane` (header toggles
collapse; history with the hidden divider; composer, or the Speak as picker
when no identity is set), `ChannelControls` (Speak as, Mute, Collapse,
Notifications, Move up/down, Leave), `MessageModeration` (staff Delete/Ban on
each row), `ChannelsPage` at `/channels`. The panel is the right-hand
`PlaySidebar` "Channels" mode on `/game`, with an unread badge on the mode
button. Channels never render in the center IC feed or the conversation rail.
The socket handler (`hooks/handleChannelMessagePayload.ts`) writes a pushed row
into that channel's cached history and bumps the badge unless the lane is open.

## Tests

`integration_tests/test_channels_journeys.py` (rows in
`docs/testing/journeys.md`): telnet to web on Public, org identity and
non-member denial, leaving the org, covert orgs and the vassal cascade,
blocks/mutes/controls, staff delete/ban/read, and a forged dispatch
`account`. `world/channels/tests/` covers what no journey reaches (pruning,
eligibility edge cases, naming clashes).
