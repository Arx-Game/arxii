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
- **Approval Workflow**: Applications reviewed by staff or trusted player GMs
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

### Trust-Based Approval System
- **Automated Where Possible**: Routine roster management should be automated
- **Player GM Approval**: Trusted players can approve character applications within their scope
- **Granular Permissions**: Approval powers are specific to character types, stories, or domains
- **Revocable Trust**: Approval permissions can be revoked if abused

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
- **PlayerMail**: Mail system with tenure targeting ("mail Ariel" → routes to current player)
- **PlayerAllowList/PlayerBlockList**: Social lists for player communication

## Command Implementation Guidelines

### Account Management Commands
When implementing commands like `@ic`, `@characters`, `@apply`:

1. **Use Models, Not Flows**: Account/roster management uses Django patterns, NOT flows
2. **Check Permissions**: Verify player has access to requested character via RosterTenure
3. **Maintain Anonymity**: Never expose player identities across characters
4. **Trust-Based Actions**: Use granular permission checks for approval actions

### Application Process
1. **Player Applies**: `@apply <character>` creates RosterApplication
2. **Review Process**: Staff or trusted player GMs review applications
3. **Approval Creates Tenure**: Approved applications create RosterTenure with proper player_number
4. **Automatic Cleanup**: System should handle edge cases (duplicate applications, etc.)

## Key Implementation Notes

### Character Switching
- Players use `@ic <character>` to switch between their available characters
- System updates PlayerData.current_character field
- Must verify character is available via active RosterTenure

### Mail System
- Players send "mail Ariel" targeting character names
- System routes to current player via RosterTenure.recipient_tenure
- Maintains character context while preserving player anonymity

### Trust-Based Permissions
- Approval permissions are tied to specific characters, stories, or domains
- Player GMs have limited scope based on their demonstrated trust
- System should log all approval actions for audit trail

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
- [ ] Trust-based approval system for character applications
- [ ] Proper tenure-based ownership of personal data (photos, settings)
