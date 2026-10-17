/**
 * Tests for the Hooks tab (#4397): a GM reads each member's hooks with the truths under
 * them and writes a truth or a hook through the table route.
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { GMTable, GMTableMembership, TableHook } from '../types';

const mutate = vi.fn();

vi.mock('../queries', () => ({
  useTableMembers: vi.fn(),
  usePlayerHooks: vi.fn(),
  useAddPlayerHook: vi.fn(() => ({ mutate, isPending: false })),
}));

import { usePlayerHooks, useTableMembers } from '../queries';
import { TableHooks } from '../components/TableHooks';

const table: GMTable = {
  id: 1,
  gm: 10,
  gm_username: 'gmUser',
  name: 'The Lantern',
  description: '',
  status: 'active',
  created_at: '2026-01-01T00:00:00Z',
  archived_at: null,
  member_count: 1,
  story_count: 0,
  viewer_role: 'gm',
};

const calista: GMTableMembership = {
  id: 5,
  table: 1,
  table_name: 'The Lantern',
  persona: 30,
  persona_name: 'Calista',
  character_sheet: 42,
  joined_at: '2026-01-01T00:00:00Z',
  left_at: null,
};

const dreams: TableHook = {
  id: 7,
  kind: 'Unknown',
  content: 'Dreams that tell.',
  consequences: '',
  level: 1,
  provenance: 'gm',
  aware: true,
  truths: [
    {
      id: 8,
      content: 'The naga schemer sends them.',
      consequences: '',
      level: 1,
      category_name: null,
      subject_aware: false,
    },
  ],
};

function mockAll(hooks: TableHook[]) {
  vi.mocked(useTableMembers).mockReturnValue({
    data: { count: 1, next: null, previous: null, results: [calista] },
    isLoading: false,
  } as unknown as ReturnType<typeof useTableMembers>);
  vi.mocked(usePlayerHooks).mockReturnValue({
    data: hooks,
    isLoading: false,
  } as unknown as ReturnType<typeof usePlayerHooks>);
}

describe('TableHooks', () => {
  it("lists a member's hooks with the truths underneath, marked unknown to the player", () => {
    mockAll([dreams]);
    render(<TableHooks table={table} />);
    const section = screen.getByRole('region', { name: 'Calista' });
    expect(within(section).getByText('Dreams that tell.')).toBeInTheDocument();
    expect(within(section).getByText('The naga schemer sends them.')).toBeInTheDocument();
    expect(within(section).getByText('(the player does not know this)')).toBeInTheDocument();
  });

  it('writes a truth under a hook through the route', async () => {
    mutate.mockClear();
    mockAll([dreams]);
    const user = userEvent.setup();
    render(<TableHooks table={table} />);
    await user.click(screen.getByRole('button', { name: 'Add a truth' }));
    await user.type(screen.getByLabelText('The truth under it'), 'Her warden set the seal.');
    await user.click(screen.getByRole('button', { name: 'Write it' }));
    expect(mutate).toHaveBeenCalledWith({ hook: 7, content: 'Her warden set the seal.' });
  });

  it("adds a hook of the GM's own", async () => {
    mutate.mockClear();
    mockAll([]);
    const user = userEvent.setup();
    render(<TableHooks table={table} />);
    expect(screen.getByText('No hooks yet.')).toBeInTheDocument();
    await user.type(screen.getByLabelText('Add a hook'), 'Someone paid for her passage.');
    await user.click(screen.getByRole('button', { name: 'Add hook' }));
    expect(mutate).toHaveBeenCalledWith(
      { content: 'Someone paid for her passage.' },
      expect.objectContaining({ onSuccess: expect.any(Function) })
    );
  });
});
