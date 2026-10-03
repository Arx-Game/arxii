/**
 * Tests for TableMemberRoster's GM-only "Prepared text" button (#4101 Task 11
 * fix round 1, item 5) -- hidden for a non-GM `viewer_role`, shown for both
 * 'gm' and 'staff'.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { GMTable, GMTableMembership, GMTableViewerRole } from '../types';

vi.mock('../queries', () => ({
  useTableMembers: vi.fn(),
}));

import { useTableMembers } from '../queries';
import { TableMemberRoster } from '../components/TableMemberRoster';

function makeTable(viewerRole: GMTableViewerRole): GMTable {
  return {
    id: 1,
    gm: 10,
    gm_username: 'gmUser',
    name: 'Test Table',
    description: 'A test table',
    status: 'active',
    created_at: '2026-01-01T00:00:00Z',
    archived_at: null,
    member_count: 1,
    story_count: 0,
    viewer_role: viewerRole,
  };
}

function makeMembership(overrides: Partial<GMTableMembership> = {}): GMTableMembership {
  return {
    id: 5,
    table: 1,
    table_name: 'Test Table',
    persona: 30,
    persona_name: 'Rowan Ashcombe',
    character_sheet: 42,
    joined_at: '2026-01-01T00:00:00Z',
    left_at: null,
    ...overrides,
  };
}

function mockMembers(members: GMTableMembership[]) {
  vi.mocked(useTableMembers).mockReturnValue({
    data: { count: members.length, next: null, previous: null, results: members },
    isLoading: false,
  } as unknown as ReturnType<typeof useTableMembers>);
}

describe('TableMemberRoster -- Prepared text button visibility', () => {
  it('hides "Prepared text" for a non-GM viewer (member)', () => {
    mockMembers([makeMembership()]);
    render(<TableMemberRoster table={makeTable('member')} />);
    expect(screen.queryByRole('button', { name: 'Prepared text' })).toBeNull();
  });

  it('hides "Prepared text" for a guest viewer', () => {
    mockMembers([makeMembership()]);
    render(<TableMemberRoster table={makeTable('guest')} />);
    expect(screen.queryByRole('button', { name: 'Prepared text' })).toBeNull();
  });

  it('shows "Prepared text" for the table GM', () => {
    mockMembers([makeMembership()]);
    render(<TableMemberRoster table={makeTable('gm')} />);
    expect(screen.getByRole('button', { name: 'Prepared text' })).toBeInTheDocument();
  });

  it('shows "Prepared text" for staff', () => {
    mockMembers([makeMembership()]);
    render(<TableMemberRoster table={makeTable('staff')} />);
    expect(screen.getByRole('button', { name: 'Prepared text' })).toBeInTheDocument();
  });
});
