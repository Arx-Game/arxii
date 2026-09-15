/**
 * NominationsPanel (#3738): the nominator's own list for the week, withdrawable,
 * with the invisibility rule stated; nothing about nominations received.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const mockWithdraw = vi.fn();
const mockMine = vi.fn();
vi.mock('../nominationQueries', () => ({
  useMyNominationsQuery: () => ({ data: mockMine(), isLoading: false }),
  useWithdrawNominationMutation: () => ({ mutate: mockWithdraw, isPending: false }),
}));

import { NominationsPanel } from '../components/NominationsPanel';

describe('NominationsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('lists whom you nominated and for what, and withdraws on the X', async () => {
    mockMine.mockReturnValue([
      {
        id: 31,
        target_type: 'interaction',
        target_id: 7,
        nominee_name: 'Alice',
        target_name: 'She lifts the lantern...',
        created_at: '2026-09-09T00:00:00Z',
      },
      {
        id: 32,
        target_type: 'journal',
        target_id: 9,
        nominee_name: 'Bob',
        target_name: 'On the road north',
        created_at: '2026-09-09T00:00:00Z',
      },
    ]);
    render(<NominationsPanel />);

    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('She lifts the lantern...')).toBeInTheDocument();
    expect(screen.getByText('Journal')).toBeInTheDocument();
    expect(screen.getByText(/they never learn who/i)).toBeInTheDocument();

    await userEvent.click(screen.getByLabelText('Withdraw nomination of Bob'));
    expect(mockWithdraw).toHaveBeenCalledWith(32, expect.anything());
  });

  it('explains what to do when there are none yet, and never shows a budget', () => {
    mockMine.mockReturnValue([]);
    render(<NominationsPanel />);

    expect(screen.getByText(/nobody nominated yet this week/i)).toBeInTheDocument();
    expect(screen.queryByText(/remaining/i)).toBeNull();
  });
});
