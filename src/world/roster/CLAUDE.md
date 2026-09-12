# Roster System - Claude Code Instructions

This file provides specific guidance for working with the roster system in Arx II.

## Core Principles

### Web-First Architecture
- **No In-Game Registration**: Account registration happens on the web, not in-game
- **No Guest Access**: Players must have approved characters to log into the game
- **Web-Based Applications**: Character applications submitted via web interface
- **Django Social Auth**: Support Facebook, Google, etc. for account registration
- **Automated Email**: Password resets, application notifications handled automatically

### Account and Character Management
- **No Character Creation on Login**: Account registration is separate from character acquisition
- **Application Process**: Players apply for available roster characters through a structured workflow
- **Approval Workflow**: Applications reviewed by staff (`CanApproveApplications`)
- **One Account Per Player**: Single login for each real person, multiple characters possible
- **Player Anonymity**: Players identified only as "1st player of X", "2nd player of X", etc.

### What We're Fixing from ArxI
**ArxI's apps_manager.py was a disaster** - here's what we're avoiding:
- ❌ **Storing data in Evennia attributes** (`self.db.apps_by_num = {}`)
- ❌ **Physical in-game object managing applications** (AppsManager(Object))
- ❌ **Manual password generation and emailing** (insecure random strings)
- ❌ **Hardcoded application format** (arrays with magic indices)
- ❌ **No proper data validation** or relationships
- ❌ **Email/roster management scattered** across multiple systems

**ArxII Improvements**:
- ✅ **Proper Django models** with relationships and validation
- ✅ **Web-based application workflow** with proper forms
- ✅ **Django's built-in authentication** with social auth
- ✅ **Structured approval process** with audit trails
- ✅ **Separation of concerns** between roster, applications, and accounts

### Approval is staff-only; there is no trust axis (ADR-0292)
- **Automated Where Possible**: Routine roster management should be automated
- **Staff Approval**: `PlayerData.can_approve_applications()` gates the review queue
- **No trust score**: #3726 removed the `trust_evaluation`/`can_auto_approve` placeholders
  and the `INSUFFICIENT_TRUST_LEVEL` denial reason. Nothing ever granted a trust level, so
  every gate reading one refused everyone. If per-thing approval powers are ever wanted,
  they get designed as explicit permissions then — not as a dormant number to gate on

## Models Overview

### Core Models (world/roster/models.py)
- **Roster**: Character categories (Active, Inactive, Available, etc.)
- **RosterEntry**: Bridge linking characters to rosters (distinguishes PCs from objects)
- **RosterTenure**: Player↔Character history with anonymity system
- **RosterApplication**: Application workflow before tenures are created
- **TenureDisplaySettings**: Character-specific UI settings tied to tenures
- **TenureMedia**: Photo galleries tied to tenures (prevents loss on character handoff)

### Extended Models (evennia_extensions/models.py)
- **PlayerData**: Extends AccountDB with player preferences and session tracking
- **PlayerMail**: OOC, player-to-player mail with tenure-to-tenure targeting, routed by
  `RosterTenure` so the current player of a character receives it regardless of who that
  is. Web-only surface (`/profile/mail` + in-scene "Message the player" quick-compose);
  no telnet mail command exists or is planned (ADR-0226; IC missives are #3289's separate
  system).
- **PlayerAllowList**: Social contact allowlist. The old account-level `PlayerBlockList` was
  removed (#1278) — block/mute now lives on `world.scenes.Block`/`Mute` (see
  `world/scenes/CLAUDE.md`).

## Command Implementation Guidelines

### Account Management Commands
When implementing commands like `@ic`, `@characters`, `@apply`:

1. **Use Models, Not Flows**: Account/roster management uses Django patterns, NOT flows
2. **Check Permissions**: Verify player has access to requested character via RosterTenure
3. **Maintain Anonymity**: Never expose player identities across characters
4. **Approval Actions**: Use explicit permission classes, never a per-account score

### Application Process
1. **Player Applies**: `@apply <character>` creates RosterApplication
2. **Review Process**: Staff review applications
3. **Approval Creates Tenure**: Approved applications create RosterTenure with proper player_number
4. **Automatic Cleanup**: System should handle edge cases (duplicate applications, etc.)

## Key Implementation Notes

### Character Switching
- Login puppets the account's character (#3812, ADR-0293): the durable
  `PlayerData.selected_entry`, else Evennia's `_last_puppet`, else a sole
  character. Nobody sees an OOC "now pick a character" step on any protocol.
- `@ic <character>` switches between available characters; puppeting records
  the new one as the durable selection through `set_selected_entry`
  (ADR-0241 as amended — selecting still never puppets)
- Sessions share a character: a second window on the same character joins it
  (`MULTISESSION_MODE = 3`); it is never refused and never kicks the first
- Must verify character is available via active RosterTenure

### Mail System (OOC player-to-player)
- Web-only: players compose at `/profile/mail`, or quick-compose in-scene from a character's
  card (pre-filled `ComposeMailForm` via `MessagePlayerDialog`, #2160) — no telnet mail command
  exists; telnet parity is deliberately out of scope (ADR-0226).
- Players target a character name; the system routes to that character's current player via
  `RosterTenure.recipient_tenure`
- Maintains character context while preserving player anonymity
- Recipient gets a `MAIL_ARRIVED` websocket push (tenure-display-only payload) plus an unread
  badge/count in the web header; `mark-read`/`unread-count` are `PlayerMailViewSet` actions
- **Account block/mute (#2996 final review):** the write always succeeds (write-then-filter —
  `PlayerMailViewSet.perform_create` never skips the save), but the `MAIL_ARRIVED` push is
  suppressed outright when the recipient has an active account-level `Block` against the sender
  (`block_services.account_block_active`) or an account-level `Mute` naming them
  (`mute_services.account_muted`) — the live ping names the sender + subject directly, a
  different leak surface than the inbox-row exclusion/auto-file, so it needs its own gate rather
  than relying on the recipient never opening their mail list.

### Approval auditing
- System should log all approval actions for audit trail
- GM authority elsewhere in the codebase is `GMProfile.level` (staff-set and audited,
  ADR-0097) — the only trust-shaped ladder that exists

## Database Relationships

```
AccountDB (Evennia) → PlayerData (evennia_extensions)
ObjectDB (Evennia) → RosterEntry → Roster
ObjectDB → RosterTenure ← PlayerData
RosterTenure → TenureDisplaySettings
RosterTenure → TenureMedia
RosterTenure → PlayerMail.recipient_tenure
```

## Critical Success Criteria

- [ ] Zero attribute usage (`self.db.anything`) - all data in proper models
- [ ] Player anonymity maintained across all character interactions
- [ ] Single login per real person with character switching functionality
- [ ] Staff approval flow for character applications, with an audit trail
- [ ] Proper tenure-based ownership of personal data (photos, settings)
