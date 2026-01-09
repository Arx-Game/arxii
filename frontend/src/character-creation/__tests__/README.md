# Character Creation Tests

This directory contains comprehensive tests for the character creation feature.

## Structure

```
__tests__/
├── fixtures.ts           # Mock data for tests
├── mocks.ts              # Mock utilities (trust, accounts, API responses)
├── testUtils.tsx         # Test rendering utilities
├── queries.test.tsx      # React Query hooks tests
├── CharacterCreationPage.test.tsx  # Main page integration tests
└── components/
    ├── OriginStage.test.tsx      # Origin selection tests
    ├── HeritageStage.test.tsx    # Heritage/species/gender tests
    ├── LineageStage.test.tsx     # Family selection tests
    ├── IdentityStage.test.tsx    # Name/description tests
    └── ReviewStage.test.tsx      # Review & submit tests
```

## Running Tests

```bash
# Run all tests
pnpm test

# Run character creation tests only
pnpm test character-creation

# Run with coverage
pnpm test --coverage
```

## Mock Philosophy

### Trust System

The trust system is mocked with a simple integer-based structure designed for future expansion.
**Note:** Trust system is not yet implemented - these mocks are forward-looking scaffolding.

```typescript
interface MockTrust {
  level: number;
  // Future: areas?: Record<string, number>;
}
```

Current trust levels:

- `TRUST_NONE (0)` - Basic player
- `TRUST_LOW (1)` - Verified player
- `TRUST_HIGH (5)` - Trusted builder/helper
- `TRUST_STAFF (10)` - Staff member

### API Mocking

All API calls are mocked at the module level using Vitest's `vi.mock()`. Tests use
`seedQueryData()` to pre-populate React Query cache for synchronous testing.

### Account Mocking

Pre-built account fixtures:

- `mockPlayerAccount` - Regular player
- `mockStaffAccount` - Staff member
- `mockRestrictedAccount` - Player who cannot create characters

## Test Categories

### Component Tests

Each stage component has tests for:

- Rendering with various draft states
- User interactions
- Loading and error states
- Permission-based UI variations

### Integration Tests

The `CharacterCreationPage.test.tsx` covers:

- Full page loading flow
- Draft creation
- Stage navigation
- Staff vs player visibility

### Query Tests

The `queries.test.tsx` covers:

- Hook behavior with successful responses
- Error handling
- Conditional fetching (enabled/disabled queries)
- Query key generation

## Writing New Tests

1. Import fixtures from `./fixtures.ts`
2. Use `renderWithCharacterCreationProviders()` for component tests
3. Use `createTestQueryClient()` and `seedQueryData()` for query mocking
4. Test both player and staff scenarios

## Git Commands (For Agents)

When reviewing test changes, **never** use git commands that open a pager (vim/less):

```bash
# BAD - opens vim/less pager, causes agent to hang
git diff
git log
git show

# GOOD - pipe to cat to avoid pager
git diff | cat
git log | cat
git show | cat
```
