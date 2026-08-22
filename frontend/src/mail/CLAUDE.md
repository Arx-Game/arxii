# Mail - OOC Player-to-Player Messages

Out-of-character mail between players, addressed via characters for anonymity
(tenure-based routing) rather than sent by account. This is NOT the in-character
letters/missives system (#3289, a separate, not-yet-built system with its own
storage) - see ADR-0226 and the "Mail (PlayerMail)" entry in
`src/world/roster/AGENT_GLOSSARY.md`.

## Key Directories

### `components/`

- **`ReceivedMailList.tsx`**: Inbox interface for received messages
- **`ComposeMailForm.tsx`**: Mail composition with recipient search

### `pages/`

- **`MailPage.tsx`**: Main mail interface with inbox and composition

## Key Files

### API Integration

- **`api.ts`**: REST API functions for mail operations
- **`queries.ts`**: React Query hooks for mail data
- **`types.ts`**: TypeScript definitions for mail data structures

## Key Features

- **Tenure-Routed Mail**: Mail is addressed to a character (for anonymity) but
  delivered to that character's current player, not tied to a user account
- **Recipient Search**: Send mail using character names
- **Tenure Routing**: Mail routes to current player of target character
- **Player Anonymity**: The recipient is addressed and displayed as "the current
  player of Character X," never by account

## Integration Points

- **Backend Models**: Direct integration with world.roster.PlayerMail
- **Tenure System**: Mail routing through character ownership
- **Character System**: In-scene "Message the player" quick-compose from the
  character card (`MessagePlayerDialog` in `frontend/src/game/components/`)
