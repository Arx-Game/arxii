# Websocket Message Types

This document describes the payload structure for messages exchanged between the frontend client and the backend over the websocket connection.

## `text`

Standard text messages. The payload contains the text and optional channel information.

```json
["text", ["<content>"], { "from_channel": "<channel>?" }]
```

## `logged_in`

Sent by the server after a successful login.

> **Possibly stale:** future clients may rely solely on HTTP session state and drop this message.

```json
["logged_in", [], {}]
```

## `vn_message`

Visual-novel style message with rich metadata.

```json
[
  "vn_message",
  [],
  {
    "text": "Hello there!",
    "speaker": { "key": "Alice", "id": 1, "avatar_url": null, "display_name": "Alice" },
    "presentation": { "side": "left", "tone": "normal", "emotion": "neutral", "background": null },
    "interaction": { "message_id": "abc123", "allow_reactions": true, "tags": [] },
    "timing": { "timestamp": "2024-01-01T00:00:00Z", "typing_speed": "normal" }
  }
]
```

## `message_reaction`

Represents a reaction to a previous message.

```json
[
  "message_reaction",
  [],
  {
    "message_id": "abc123",
    "reaction": "\uD83D\uDC4D",
    "actor": { "id": 1, "key": "Alice" },
    "counts": { "\uD83D\uDC4D": 3 }
  }
]
```

## `commands`

Sends one or more commands for the frontend client to execute. Each command
object contains the command name and optional parameters and is provided in the
args array.

```json
[
  "commands",
  [{ "command": "open_panel", "params": { "target": "inventory" } }],
  {}
]
```

For the structure of each command object, refer to [CommandDescriptor Format](./command_descriptor.md), which shows how these descriptors power context menus, icon buttons, and prompts.

## `room_state`

Describes the player's current location. The payload includes the room, nearby objects and characters, and exits.

```json
[
  "room_state",
  [],
  {
    "room": { "dbref": "#1", "name": "Courtyard", "thumbnail_url": null, "commands": [] },
    "objects": [
      { "dbref": "#2", "name": "Bench", "thumbnail_url": null, "commands": ["sit"] }
    ],
    "exits": [
      { "dbref": "#3", "name": "North", "thumbnail_url": null, "commands": ["north"] }
    ]
  }
]
```

Clients should display placeholder icons when `thumbnail_url` is null.


## Same-connection room-state recovery

The live `/game` client can request a fresh viewer-relative snapshot without
reconnecting:

```json
["request_room_state", [], {"client_request_id": "550e8400-e29b-41d4-a716-446655440000"}]
```

The server sends a normal `room_state` first. It includes `state_epoch` and
monotonic `state_sequence`, and echoes the validated request id as
`resync_request_id`. It then sends a requester-only acknowledgement:

```json
["state_resync", [], {
  "client_request_id": "550e8400-e29b-41d4-a716-446655440000",
  "state_epoch": "<server-epoch>", "state_sequence": 42,
  "room_dbref": "#123", "room_id": 123, "scene_id": 17
}]
```

Errors use stable codes and never echo an invalid id:

```json
["state_resync_error", [], {
  "client_request_id": null, "code": "invalid_request"
}]
```

`retry_after_ms` is included only for `rate_limited`. The client keeps the
request pending for six seconds; a snapshot without its acknowledgement is a
retryable partial success. Portal-parser forms that cannot reach the inputfunc
remain an ingress limitation of the current Evennia websocket seam.
