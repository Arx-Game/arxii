/**
 * ApplicationSlot tests (#2162 task 6)
 *
 * Covers:
 * 1. A pending application for THIS character renders the pending-notice panel
 *    and does NOT render the application form.
 * 2. A pending application for a DIFFERENT character still renders the
 *    application form (no pending notice).
 * 3. No pending applications + can_apply renders the application form.
 * 4. No pending applications + !can_apply renders nothing.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ApplicationSlot } from '../ApplicationSlot';
import type { RosterEntryData } from '@/roster/types';
import type { AccountData } from '@/evennia_replacements/types';

vi.mock('../CharacterApplicationForm', () => ({
  CharacterApplicationForm: ({ entryId }: { entryId: number }) => (
    <div data-testid="application-form-mock" data-entry-id={entryId} />
  ),
}));

function makeEntry(overrides: Partial<RosterEntryData> = {}): RosterEntryData {
  return {
    id: 1,
    character: { id: 42, name: 'Test Character', galleries: [] },
    profile_picture: null,
    tenures: [],
    can_apply: true,
    fullname: 'Test Character',
    quote: '',
    description: '',
    creation_provenance: 'player',
    creation_provenance_display: 'Player-created',
    created_for_table_name: null,
    ...overrides,
  };
}

function makeAccount(overrides: Partial<AccountData> = {}): AccountData {
  return {
    id: 1,
    username: 'tester',
    display_name: 'Tester',
    last_login: null,
    email: 'tester@example.com',
    email_verified: true,
    can_create_characters: true,
    is_staff: false,
    available_characters: [],
    pending_applications: [],
    ...overrides,
  };
}

describe('ApplicationSlot', () => {
  it('renders the pending notice and hides the form when a pending app matches this character', () => {
    const entry = makeEntry();
    const account = makeAccount({
      pending_applications: [
        {
          id: 9,
          character_id: 42,
          character_name: 'Test Character',
          status: 'pending',
          applied_date: '2026-07-01',
        },
      ],
    });
    render(<ApplicationSlot entry={entry} account={account} />);

    expect(screen.getByText(/Application pending/i)).toBeInTheDocument();
    expect(screen.queryByTestId('application-form-mock')).not.toBeInTheDocument();
  });

  it('renders the form when the pending app is for a different character', () => {
    const entry = makeEntry();
    const account = makeAccount({
      pending_applications: [
        {
          id: 9,
          character_id: 99,
          character_name: 'Someone Else',
          status: 'pending',
          applied_date: '2026-07-01',
        },
      ],
    });
    render(<ApplicationSlot entry={entry} account={account} />);

    expect(screen.queryByText(/Application pending/i)).not.toBeInTheDocument();
    expect(screen.getByTestId('application-form-mock')).toHaveAttribute('data-entry-id', '1');
  });

  it('renders the form when there are no pending applications and the entry is applyable', () => {
    const entry = makeEntry({ can_apply: true });
    const account = makeAccount({ pending_applications: [] });
    render(<ApplicationSlot entry={entry} account={account} />);

    expect(screen.getByTestId('application-form-mock')).toBeInTheDocument();
  });

  it('renders nothing when there is no pending app and the entry is not applyable', () => {
    const entry = makeEntry({ can_apply: false });
    const account = makeAccount({ pending_applications: [] });
    const { container } = render(<ApplicationSlot entry={entry} account={account} />);

    expect(container).toBeEmptyDOMElement();
  });

  it('renders the form when account is null and the entry is applyable', () => {
    const entry = makeEntry({ can_apply: true });
    render(<ApplicationSlot entry={entry} account={null} />);

    expect(screen.getByTestId('application-form-mock')).toBeInTheDocument();
  });
});
