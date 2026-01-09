/**
 * Character Creation Test Mocks
 *
 * Mock utilities for testing character creation, including:
 * - Trust/permission system mocks (forward-looking scaffolding)
 * - API response mocks
 * - Store mocks
 */

import type { AccountData } from '@/evennia_replacements/types';

// =============================================================================
// Trust/Permission System Mocks (Forward-Looking Scaffolding)
// =============================================================================

/**
 * Trust levels for the permission system.
 * Structure designed for future expansion to area-based trust.
 * Currently a simple integer, but mocked as an object for forward compatibility.
 *
 * NOTE: Trust system is not yet implemented. These mocks are scaffolding for
 * future trust-based permission tests.
 */
export interface MockTrust {
  /** Overall trust level (0 = none, higher = more trusted) */
  level: number;
  /**
   * Future: Area-specific trust levels
   * e.g., { characterCreation: 5, storytelling: 3 }
   */
  // areas?: Record<string, number>;
}

/** No trust - basic player */
export const TRUST_NONE: MockTrust = { level: 0 };

/** Low trust - verified player */
export const TRUST_LOW: MockTrust = { level: 1 };

/** High trust - trusted builder/helper */
export const TRUST_HIGH: MockTrust = { level: 5 };

/** Staff trust level */
export const TRUST_STAFF: MockTrust = { level: 10 };

/**
 * Check if user has staff-level trust
 */
function isStaffTrust(trust: MockTrust): boolean {
  return trust.level >= TRUST_STAFF.level;
}

// =============================================================================
// Account Mocks
// =============================================================================

export interface MockAccountOptions {
  trust?: MockTrust;
  isStaff?: boolean;
  canCreateCharacters?: boolean;
}

/**
 * Create a mock account with specified options
 */
export function createMockAccount(options: MockAccountOptions = {}): AccountData {
  const { trust = TRUST_NONE, isStaff = false, canCreateCharacters = true } = options;

  return {
    id: 1,
    username: isStaff ? 'staffuser' : 'testplayer',
    display_name: isStaff ? 'Staff User' : 'Test Player',
    last_login: new Date().toISOString(),
    email: isStaff ? 'staff@test.com' : 'player@test.com',
    email_verified: true,
    can_create_characters: canCreateCharacters,
    is_staff: isStaff || isStaffTrust(trust),
  };
}

/** Pre-built account: Regular player */
export const mockPlayerAccount = createMockAccount({
  trust: TRUST_LOW,
  isStaff: false,
});

/** Pre-built account: Staff member */
export const mockStaffAccount = createMockAccount({
  trust: TRUST_STAFF,
  isStaff: true,
});

/** Pre-built account: Player who cannot create characters */
export const mockRestrictedAccount = createMockAccount({
  trust: TRUST_NONE,
  isStaff: false,
  canCreateCharacters: false,
});

// =============================================================================
// API Response Mocks
// =============================================================================

export interface CanCreateResponse {
  can_create: boolean;
  reason: string;
}

export const mockCanCreateYes: CanCreateResponse = {
  can_create: true,
  reason: '',
};

export const mockCanCreateNo: CanCreateResponse = {
  can_create: false,
  reason: 'You have reached the maximum number of characters.',
};
