# Webclient Game Plan

The `/game` endpoint will evolve into a full-featured webclient built on the new frontend stack. This document outlines desired features and backend support.

## Core features

- Large chat-centric interface where most interactions happen via text.
- Messages include contextual data about the sender so the UI can show thumbnails and link to character sheets.
- UI components such as who list, map, inventory and others can be moved around or toggled within the chat window.
- Filters allowing players to separate channels, private messages, out-of-character messages and room chatter into different views.
- Notifications when the player is mentioned or directly addressed.

## Technical notes

- Communication continues over the existing websocket system.
- Backend endpoints may require expansion to deliver the additional context for messages.
- Redux Toolkit manages websocket state and chat history on the client.

This plan will expand as the modern webclient progresses.
