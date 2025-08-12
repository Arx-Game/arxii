# Websocket Message Types

This document describes the payload structure for messages exchanged between the frontend client and the backend over the websocket connection.

## `text`

Standard text messages. The payload contains the text and optional channel information.

```json
["text", ["<content>"], { "from_channel": "<channel>?" }]
```

## `logged_in`

Sent by the server after a successful login.

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
