# Mail - In-Character Mail System

In-character mail system with tenure-based routing and character-to-character communication.

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

- **Character-based Mail**: Mail tied to character tenures, not user accounts
- **Recipient Search**: Send mail using character names
- **Tenure Routing**: Mail routes to current player of target character
- **Character Context**: Maintains in-character communication

## Integration Points

- **Backend Models**: Direct integration with world.roster.PlayerMail
- **Tenure System**: Mail routing through character ownership
- **Character System**: Integration with character identity management
