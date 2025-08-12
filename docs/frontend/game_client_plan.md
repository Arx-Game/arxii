# Webclient Game Plan

The `/game` endpoint will evolve into a full-featured webclient built on the new frontend stack. This document outlines desired
features, current progress, and remaining work.

## Progress

- Out-of-band messaging hooks are in place using Evennia's websocket payloads.
- Backend tasks send available command descriptors and contextual room/object data.
- Early client parsing exists for these payloads.

## Core features

- Large chat-centric interface where most interactions happen via text.
- Messages include contextual data about the sender so the UI can show thumbnails and link to character sheets.
- Location panel lists objects, exits, and characters with context-based commands.
- Right-clicking commands that require additional text opens a modal for one or two fields, or a side drawer for more complex forms.
- Placeholder icons appear when an object or character lacks a thumbnail.
- Rich message window displays avatars and supports reactions.
- Scene window shows active scene information and can convert recent room conversation into scene messages.

## Technical notes

- Communication continues over the existing websocket system.
- Backend flows and service functions must emit context updates at appropriate times.
- Redux Toolkit manages websocket state and chat history on the client.

## Possibly stale

- UI components such as who list, map, inventory and others can be moved around or toggled within the chat window.
- Filters allowing players to separate channels, private messages, out-of-character messages and room chatter into different views.
- Notifications when the player is mentioned or directly addressed.

This plan will expand as the modern webclient progresses.
