# Missives (#3289)

In-character letters carried from one persona to another. A missive is written under a
face, travels by a staff-tuned **transmission method** (a messenger runner at MVP) for an
in-game delay, and arrives in the recipient's missive list. Coin and items can ride along
and are held until the recipient accepts or refuses them.

This is not `PlayerMail`. Mail is the OOC, tenure-routed player-to-player surface
(`world.roster`, ADR-0226). A missive is IC: authored and addressed by persona, delayed in
game time, and carrying goods. The two do not share storage.

Source: `src/world/messengers/` (models, services, display, tasks, notifications, views,
serializers, filters, seeds), `src/actions/definitions/missives.py`,
`src/commands/missives.py`, `frontend/src/missives/`. Journey tests:
`src/integration_tests/test_missives_journeys.py`.

## Models (`world.messengers.models`)

- **`TransmissionMethod`** - natural key `name`. `description` (fiction copy),
  `ic_delay_minutes`, `can_carry_items`, `can_carry_coin`, `is_universal` (anyone may use
  it), `required_capability` (nullable FK to `CapabilityType`, the hook for a magical method).
  Check constraint `messenger_universal_method_has_no_capability`: a method is universal or
  capability-gated, never both. The only model with an admin (staff tune it there).
- **`Missive`** - `sender_persona` / `recipient_persona` (FK `scenes.Persona`, PROTECT:
  a persona with correspondence is history, so `remove_persona` is refused by
  `ProtectedError`), `method` (PROTECT), `body`, `ic_sent_at` (game-clock time, null when no
  clock runs), `sent_at` (real), `available_at` (real arrival time), `arrival_notified_at`
  (the sweep's stamp), `undeliverable` (the block flag, never shown to anyone), `read_at`,
  `in_reply_to` (self FK, SET_NULL). Indexes: `(recipient_persona, available_at)`,
  `(sender_persona, sent_at)`, and a partial `available_at` index over rows not yet
  announced (the sweep's scan).
- **`MissiveAttachment`** - one item or one sum of coin on a missive. `item` (FK
  `ItemInstance`, CASCADE: the XOR constraint needs it set, and PROTECT would block
  hard-deleting any item ever sent) or `coin_amount` (positive big integer), `resolution`
  (`AttachmentResolution`: pending / accepted / refused), `resolved_at`. Check constraint
  `messenger_attachment_item_xor_coin` (exactly one of item or positive coin); partial
  unique constraint `messenger_item_in_transit_once` (an item is in transit on at most one
  pending attachment).

Constants (`world.messengers.constants`): `AttachmentResolution`, `MissiveDirection`
(received / sent, the REST filter), `AttachmentKind` (item / coin, the REST list).

**No admin for `Missive` or `MissiveAttachment`.** Letters are private between players;
staff do not browse them. Only `TransmissionMethod` is registered.

## The display rule (`world.messengers.display`)

One rule for every surface that names a missive's correspondents (telnet list and read, the
REST list, send and reply confirmations):

- The **sender** always reads through the viewer's eyes: a mask stays a mask until the
  viewer has seen through it (`resolve_display_for_viewer`, batched per page by
  `display_map_for` over `build_persona_display_map`).
- The **recipient** reads as the viewer typed it when the viewer wrote a fresh letter (the
  exact name it addressed), and through the viewer's eyes otherwise. A reply to a masked
  writer therefore never names what the mask hides.
- `sent_by(sheet, missive)` is the one "I wrote this to someone else" test. A letter
  between two faces of one character counts as received, so its reply goes back to the face
  that wrote it. `sent_by_q` is the same rule as a queryset filter.
- A reply goes out under the face the original was **written to** (`reply_sender_for`), so
  answering a letter sent to a mask never unmasks the writer.

## Services (`world.messengers.services`)

Every refusal is a `MissiveError` (`exceptions.py`) whose `user_message` is plain play copy;
callers show it as-is and never `str(exc)`.

- Methods: `available_methods_for(sheet)` (universal ones, plus capability-gated ones whose
  effective capability value is above zero), `default_method_for`.
- Addressing: `find_addressable_persona(name)` (case-insensitive exact name; one match
  only), `addressable_persona(pk)`. Refusal wording never depends on who owns the persona.
- `send_missive(sender_persona, recipient_persona, body, method, coin_amount, items,
  in_reply_to)` (atomic): checks the method can carry what rides along, locks the items
  (the sender must hold them, no natural weapons, none already in transit), takes coin out
  of the sender's purse (a sink; the attachment row is the custody) and puts each item into
  row custody (off the body, game object dematerialized, no holder, the org vault's
  `_take_into_custody` shape). The arrival time is the IC delay through the game clock
  (`get_real_time_for_ic_date`), falling back to real minutes when the clock is paused,
  absent or zero-ratio; a zero-delay method is due at once.
- Reading: `visible_missives_for(sheet)` (everything any of the character's faces sent, plus
  what any face received once `available_at` has passed and it is not `undeliverable`),
  `get_visible_missive` (one refusal for "not found" and "not yours"), `unread_count_for`,
  `read_missive` (first read by the recipient stamps `read_at`; a sender's read is a no-op).
  The attachments are never prefetched onto the identity-mapped missive rows (a prefetch
  would go stale after accept or refuse, ADR-0263); the REST view loads them fresh per
  request.
- Attachments: `accept_missive` (coin to the recipient's purse; items go to the recipient as
  a `GIVEN` `OwnershipEvent` voiced by persona on both sides, `notes="missive #<pk>"`, and
  are materialized again) and `refuse_missive` (everything goes back to the sender's
  character). Both lock the pending rows, stamp `resolution` and `resolved_at`, and send
  the sender a one-line notice after commit, only if someone is playing the sender
  character (the notice names the recipient persona the sender addressed).
- `deliver_due_missives(now)`: the arrival sweep, see Delivery.

## Delivery

Availability is **lazy**: a missive is readable once `available_at` has passed, whether or
not anything has run. Three pieces sit on top.

1. **The sweep.** Task `missives.deliver` (`world.messengers.tasks`, registered from
   `world.game_clock.tasks`, a real-time cron every 5 minutes) calls
   `deliver_due_missives`. For each due, unannounced, deliverable missive it locks the row
   (`skip_locked`, so overlapping sweeps never push twice), re-checks the block, stamps
   `arrival_notified_at`, and after commit (robust) sends the arrival push. It stamps the
   missive whether or not the recipient is online; an offline recipient is carried by the
   unread count.
2. **Read-time block settle.** Because availability is lazy, a block placed while a letter
   travelled must not let it through in the window before the next sweep.
   `_settle_arrivals_for(sheet)` runs inside `visible_missives_for` and `unread_count_for`,
   and `_is_delivered_to` runs before read, accept and refuse; each applies the same
   `_suppress_if_blocked` re-check the sweep makes.
3. **The push.** See "Push frame".

Seeding: the Big Button cluster `messengers` (`world.seeds.clusters._seed_messengers`)
calls `ensure_messenger_method`, a `get_or_create` that never overwrites a tuned row.

## Actions and telnet

Registry actions (`actions/definitions/missives.py`, all `category="social"`, target
`SELF`); the web dispatches them over the websocket and telnet converges on the same
`action.run()`. Kwargs arrive as JSON types from the web and as strings from telnet, so
every id and amount is parsed in the action.

| Key | Kwargs | Notes |
|---|---|---|
| `send_missive` | `body`; `recipient_persona_id` (web) or `recipient_name` (telnet); optional `sender_persona_id` (one of the actor's own faces, default the active one), `coin_amount`, `item_ids` (web) or `item_names` (telnet), `method_id` | Confirmation reads the recipient as typed. |
| `reply_missive` | `missive_id`, `body`; optional `sender_persona_id`, `coin_amount`, `item_ids` / `item_names`, `method_id` | Goes to the original's sender when the actor received it, to its recipient when the actor sent it. |
| `read_missive` | `missive_id` | Returns the rendered letter as `message`; marks it read. |
| `accept_missive` | `missive_id` | Takes what came with it. |
| `refuse_missive` | `missive_id` | Sends what came with it back. |

Telnet (`CmdMissive`, key `missive`, parsing only):

```
missive                                          your missives, newest first (a * marks unread)
missive/list                                     the same
missive/read <id>
missive/send <name>[+coin <n>][+item <item>]...=<message>
missive/reply <id>[+coin <n>][+item <item>]...=<message>
missive/accept <id>
missive/refuse <id>
```

An item named on telnet is matched against what the character carries (exact name, else a
single partial match).

## REST (`/api/missives/`, read-only)

`MissiveViewSet` (list, retrieve, `unread-count`), `IsAuthenticated`, page size 20 (max 50
via `page_size`). The acting character is the request's selected roster entry
(`?entry_id=`, #3479); a request that plays nobody gets an empty list. Writes go through
action dispatch, not this API.

- `GET /api/missives/?direction=received|sent&unread=true|false` - newest first.
- `GET /api/missives/{id}/` - one missive the character may see; anything else is a 404.
- `GET /api/missives/unread-count/` - `{"count": n}`.

Row fields: `id`, `direction`, `counterpart_name` (the other side as this reader sees them),
`own_persona_id`, `own_persona_name` (the reader's own face on it), `method_name`, `body`,
`ic_date`, `sent_at`, `is_read`, `in_reply_to` (id), `attachments`
(`{id, kind: item|coin, label, resolution}`).

## Push frame

`WebsocketMessageType.MISSIVE_ARRIVED` = `missive_arrived`, payload `MissiveArrivedPayload`
(`web/webclient/message_types.py`): `missive_id`, `recipient_persona_name` (the face the
letter was addressed to, so a player with several faces knows which was written to),
`sender_display` (the sender as this recipient sees them). A slim ping: clients refetch the
list and unread count on receipt (`frontend/src/hooks/handleMissiveArrivedPayload.ts`).
Telnet sessions get a plain-text twin (`send_text_to_non_web`) so a browser never shows it
twice. Built by `world.messengers.notifications.notify_missive_arrived`.

## Privacy rules

- **Persona-addressed.** A missive is written to a persona, never a character. Addressing
  refusals ("There is no one by that name to send to.") use the same wording whoever owns
  the persona.
- **The owner join is never serialized.** The persona to sheet to tenure to account join is
  used server-side (block checks, delivery to the right character) and never reaches a REST
  field, a push payload, a telnet line or a notice. A row carries the counterpart's display
  name only, no persona id, sheet, character or account of the other side. The one persona
  id on a row is the reader's own.
- **Write-then-suppress.** A send between players with an active block is written exactly
  like any other and flagged `undeliverable`. The sender gets the same "on its way"
  confirmation, sees `is_read` as true, and is never told. The recipient never sees it.
  See ADR-3289-A.
- **Content is player-private.** No admin for `Missive` or `MissiveAttachment`, and no staff
  listing; the only readers are the two correspondents' characters.

## Overridable defaults

These are decisions made to ship the MVP without waiting on a ruling. Each is cheap to
change; the owner can override any of them.

1. **Addressing by exact name, no discovery gate.** Any `PRIMARY` or `ESTABLISHED`
   non-system persona can be addressed by its exact name (case-insensitive), whether or not
   the sender has met or discovered it (`PersonaDiscovery` is not consulted). Temporary and
   system personas are not addressable. To gate it, narrow `_addressable_personas()` in
   `services.py`.
2. **Attachments on an undeliverable missive stay held.** When a block makes a missive
   undeliverable, its coin and items stay `PENDING` in custody and are never auto-returned,
   because a return would tell the sender about the block. Nothing recovers them without
   staff. To change it, add a return path that does not signal the block (for example a
   delayed, generic "the messenger could not deliver" return for every undeliverable cause).
3. **The seeded Messenger delay is a placeholder.** The seeded universal `Messenger` method
   carries `ic_delay_minutes=30`, a 30 IC-minute guess. Staff tune it (and add methods,
   including capability-gated magical ones) in the admin; the seed never overwrites an
   existing row.

## Tests

`world/messengers/tests/` (models and constraints, services, API smoke),
`integration_tests/test_missives_journeys.py` (send, arrive, read, reply, accept and refuse
through telnet, web dispatch and REST).
