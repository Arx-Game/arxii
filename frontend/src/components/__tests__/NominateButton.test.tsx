/**
 * NominateButton (#3738): a pressed/unpressed toggle that shows nothing about
 * anyone else — no count, no budget — and names only what it does.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const mockNominate = vi.fn();
const mockWithdraw = vi.fn();
const mockMine = vi.fn();
vi.mock('@/progression/nominationQueries', () => ({
  useMyNominationsQuery: () => ({ data: mockMine() }),
  useNominateMutation: () => ({ mutate: mockNominate, isPending: false }),
  useWithdrawNominationMutation: () => ({ mutate: mockWithdraw, isPending: false }),
}));

import { NominateButton } from '../NominateButton';

describe('NominateButton', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('nominates the writer of a piece not yet cited, and says they will not know who', async () => {
    mockMine.mockReturnValue([]);
    render(<NominateButton targetType="interaction" targetId={7} nomineeName="Alice" />);

    const button = screen.getByTestId('nominate-button');
    expect(button).toHaveAttribute('aria-pressed', 'false');
    expect(button).toHaveAttribute('title', 'Nominate Alice for good RP (they will not know who)');
    expect(button.textContent).toBe('');

    await userEvent.click(button);
    expect(mockNominate).toHaveBeenCalledWith(
      { targetType: 'interaction', targetId: 7 },
      expect.anything()
    );
  });

  it('withdraws a piece already cited this week', async () => {
    mockMine.mockReturnValue([
      {
        id: 31,
        target_type: 'interaction',
        target_id: 7,
        nominee_name: 'Alice',
        target_name: 'A pose',
        created_at: '2026-09-09T00:00:00Z',
      },
    ]);
    render(<NominateButton targetType="interaction" targetId={7} nomineeName="Alice" />);

    const button = screen.getByTestId('nominate-button');
    expect(button).toHaveAttribute('aria-pressed', 'true');
    expect(button).toHaveAttribute('title', 'Withdraw your nomination of Alice');

    await userEvent.click(button);
    expect(mockWithdraw).toHaveBeenCalledWith(31, expect.anything());
  });
});
