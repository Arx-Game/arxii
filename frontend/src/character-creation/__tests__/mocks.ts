/**
 * Character Creation Test Mocks
 *
 * Mock utilities for testing character creation:
 * - API response mocks
 * - Store mocks
 */

import type { AccountData } from '@/evennia_replacements/types';

// =============================================================================
// Account Mocks
// =============================================================================

export interface MockAccountOptions {
  isStaff?: boolean;
  canCreateCharacters?: boolean;
  isGM?: boolean;
}

/**
 * Create a mock account with specified options
 */
export function createMockAccount(options: MockAccountOptions = {}): AccountData {
  const { isStaff = false, canCreateCharacters = true, isGM = false } = options;

  return {
    id: 1,
    username: isStaff ? 'staffuser' : 'testplayer',
    display_name: isStaff ? 'Staff User' : 'Test Player',
    last_login: new Date().toISOString(),
    email: isStaff ? 'staff@test.com' : 'player@test.com',
    email_verified: true,
    can_create_characters: canCreateCharacters,
    is_staff: isStaff,
    is_gm: isGM,
    available_characters: [],
    pending_applications: [],
    selected_entry_id: null,
    selected_entry: null,
  };
}

/** Pre-built account: Regular player */
export const mockPlayerAccount = createMockAccount({ isStaff: false });

/** Pre-built account: Staff member */
export const mockStaffAccount = createMockAccount({ isStaff: true });

/** Pre-built account: Player who cannot create characters */
export const mockRestrictedAccount = createMockAccount({
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
